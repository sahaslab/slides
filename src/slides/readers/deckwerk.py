import re
import json
import pathlib
from html.parser import HTMLParser
from slides.model import Build, Run, Shape, ColorUse, Deck, Embed, Image, Slide, Table, TextItem

BREAK_TAGS = {"br", "p", "div", "li", "tr"}
RGB = re.compile(r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)")
HEX6 = re.compile(r"#([0-9a-fA-F]{6})\b")
HEX3 = re.compile(r"#([0-9a-fA-F]{3})\b")
SLIDE_NUMBER_MARKER = "data-slide-number"
TITLE_ROLE_CLASS = "role-title"
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_AT_RULE = re.compile(r"@(?:media|supports)\b[^{]*\{")
CSS_BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_DECLARATION = re.compile(r"([a-zA-Z-]+)\s*:\s*([^;]+)")
ROOT_SELECTOR = ".slide"
KATEX_CLASS = "katex"
KATEX_DISPLAY_CLASS = "katex-display"
TEX_ANNOTATION_ENCODING = "application/x-tex"
FONT_SIZE = re.compile(r"font-size:\s*([\d.]+)px")
TEXT_PROPERTIES = ("color", "font-family", "font-size", "font-weight", "font-style", "text-align", "line-height")
EMPHASIS = {"b": {"font-weight": "700"}, "strong": {"font-weight": "700"}, "i": {"font-style": "italic"}, "em": {"font-style": "italic"}}


def _classes(attrs: list) -> set[str]:
    for name, value in attrs:
        if name == "class" and value:
            return set(value.split())
    return set()


def _attr_value(
    attrs: list,
    name: str
) -> str | None:
    for key, value in attrs:
        if key == name:
            return value
    return None


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class _KatexAware:
    # A rendered KaTeX span nests three things inside one `<span
    # class="katex">`: the MathML tree (readable-ish glyph text via <mi>/
    # <mo>/...), an <annotation encoding="application/x-tex"> holding the
    # author's real TeX source, and a `katex-html` tree of positioned glyph
    # spans. Only the annotation is real content; the rest is dropped.
    # _Stripper and _TableParser both mix this in so the state machine for
    # "am I inside a katex span, and is it display or inline" lives once.
    def _katex_init(self) -> None:
        self._span_classes: list[set[str]] = []
        self._katex_depth = 0
        self._display = False
        self._in_annotation = False
        self._tex_parts: list[str] = []

    def _katex_starttag(
        self,
        tag: str,
        attrs: list
    ) -> bool:
        if tag == "span":
            classes = _classes(attrs)
            self._span_classes.append(classes)
            if self._katex_depth == 0 and KATEX_CLASS in classes:
                self._katex_depth = 1
                self._display = any(
                    KATEX_DISPLAY_CLASS in c for c in self._span_classes
                )
            elif self._katex_depth > 0:
                self._katex_depth += 1
            return self._katex_depth > 0
        if tag == "annotation" and self._katex_depth > 0:
            if _attr_value(attrs, "encoding") == TEX_ANNOTATION_ENCODING:
                self._in_annotation = True
                self._tex_parts = []
            return True
        return self._katex_depth > 0

    def _katex_endtag(
        self,
        tag: str
    ) -> str | None:
        if tag == "annotation" and self._in_annotation:
            self._in_annotation = False
            tex = "".join(self._tex_parts)
            wrapper = "$$%s$$" if self._display else "$%s$"
            return wrapper % (tex,)
        if tag == "span":
            if self._span_classes:
                self._span_classes.pop()
            if self._katex_depth > 0:
                self._katex_depth -= 1
        return None

    def _katex_data(
        self,
        data: str
    ) -> bool:
        if self._in_annotation:
            self._tex_parts.append(data)
            return True
        return self._katex_depth > 0


class _Stripper(HTMLParser, _KatexAware):
    # Collects the text, and beside each piece the inline style in force
    # there, so a coloured or bold span survives as a Run.
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.styles: list[dict[str, str]] = []
        self._open: list[tuple[str, dict[str, str]]] = []
        self._katex_init()

    def _style(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for _, style in self._open:
            merged.update(style)
        return merged

    def _add(
        self,
        text: str
    ) -> None:
        self.parts.append(text)
        self.styles.append(self._style())

    def handle_data(
        self,
        data: str
    ) -> None:
        if self._katex_data(data):
            return
        self._add(data)

    def handle_starttag(
        self,
        tag: str,
        attrs: list
    ) -> None:
        if self._katex_starttag(tag, attrs):
            return
        if tag in BREAK_TAGS and self.parts:
            self._add("\n")
        style = dict(EMPHASIS.get(tag, {}))
        style.update(_inline_style(_attr_value(attrs, "style") or ""))
        if tag not in ("br", "img", "hr"):
            self._open.append((tag, style))

    def handle_endtag(
        self,
        tag: str
    ) -> None:
        wrapped = self._katex_endtag(tag)
        if wrapped is not None:
            self._add(wrapped)
            return
        if self._katex_depth:
            return
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index][0] == tag:
                del self._open[index:]
                break
        if tag in BREAK_TAGS and self.parts:
            self._add("\n")


class _TableParser(HTMLParser, _KatexAware):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None
        self._text: list[str] = []
        self._katex_init()

    def handle_starttag(
        self,
        tag: str,
        attrs: list
    ) -> None:
        if self._katex_starttag(tag, attrs):
            return
        if tag == "tr":
            self._cell = []
        elif tag in ("td", "th"):
            self._text = []
        elif tag == "br":
            self._text.append(" ")

    def handle_endtag(
        self,
        tag: str
    ) -> None:
        wrapped = self._katex_endtag(tag)
        if wrapped is not None:
            self._text.append(wrapped)
            return
        if self._katex_depth:
            return
        if tag in ("td", "th") and self._cell is not None:
            self._cell.append(_collapse_ws("".join(self._text)))
        elif tag == "tr" and self._cell is not None:
            self.rows.append(self._cell)
            self._cell = None

    def handle_data(
        self,
        data: str
    ) -> None:
        if self._katex_data(data):
            return
        self._text.append(data)


def strip_html(markup: str) -> str:
    return rich_text(markup)[0]


def rich_text(markup: str) -> tuple[str, list[Run]]:
    # The text as strip_html has always produced it, plus the spans whose
    # inline style differs; both come from one per-character pass so the
    # spans' offsets survive the whitespace clean-up.
    stripper = _Stripper()
    stripper.feed(markup)
    chars: list[str] = []
    styles: list[dict[str, str]] = []
    for part, style in zip(stripper.parts, stripper.styles):
        for char in part:
            if char == "\n" and chars and chars[-1] == "\n":
                continue
            chars.append(char)
            styles.append(style)
    start = 0
    while start < len(chars) and chars[start].isspace():
        start += 1
    end = len(chars)
    while end > start and chars[end - 1].isspace():
        end -= 1
    chars, styles = chars[start:end], styles[start:end]
    runs: list[Run] = []
    for index, style in enumerate(styles):
        if not style:
            continue
        if runs and runs[-1].end == index and runs[-1].style == style:
            runs[-1].end = index + 1
        else:
            runs.append(Run(start=index, end=index + 1, style=style))
    return "".join(chars), runs


def _inline_style(declarations: str) -> dict[str, str]:
    found = {}
    for prop, value in CSS_DECLARATION.findall(declarations):
        prop = prop.strip().lower()
        if prop in TEXT_PROPERTIES:
            found[prop] = value.strip()
    return found


def _computed(
    element: dict,
    rules: dict[str, dict[str, str]]
) -> dict[str, str]:
    # The element's own look: the root rule every slide inherits, then the
    # theme rules whose rightmost selector names only classes it carries, then
    # its own style. A simplification of the CSS cascade that fits how
    # DeckWerk themes are written.
    classes = set(element.get("class") or [])
    style: dict[str, str] = {}
    for selector, declarations in rules.items():
        if _applies(selector, classes):
            style.update({k: v for k, v in declarations.items() if k in TEXT_PROPERTIES})
    style.update({k: str(v) for k, v in (element.get("style") or {}).items() if k in TEXT_PROPERTIES})
    # The box's own alignment is what DeckWerk lays the text out by.
    if element.get("align"):
        style["text-align"] = element["align"]
    if element.get("valign"):
        style["vertical-align"] = element["valign"]
    if element.get("paragraphSpacing") is not None:
        style["paragraph-spacing"] = "%spx" % (element["paragraphSpacing"],)
    return style


def _applies(
    selector: str,
    classes: set[str]
) -> bool:
    for part in selector.split(","):
        words = part.split()
        if not words:
            continue
        last = words[-1]
        if last == ROOT_SELECTOR:
            return True
        names = re.findall(r"\.([\w-]+)", last)
        if last.startswith(".") and names and not re.search(r"[:\[#>+~*]", last) and set(names) <= classes:
            return True
    return False


def read(path: str | pathlib.Path) -> Deck:
    root = pathlib.Path(path)
    data = json.loads((root / "deck.json").read_text())
    canvas = data.get("canvas", {})
    deck = Deck(
        title=data.get("title", root.name),
        width=float(canvas.get("w", 1920)),
        height=float(canvas.get("h", 1080)),
        source=str(root),
        kind="deckwerk",
        fonts=_fonts(data),
    )
    colors: dict[tuple[str, str], float] = {}
    rules = _theme_rules(root, data)
    for number, raw in enumerate(data.get("slides", []), start=1):
        deck.slides.append(_slide(number, raw, colors, rules))
    _harvest_theme_colors(colors, rules, deck.slides)
    deck.colors = [
        ColorUse(hex=key[0], weight=weight, kind=key[1])
        for key, weight in sorted(colors.items(), key=lambda kv: -kv[1])
    ]
    return deck


def _fonts(data: dict) -> dict[str, str]:
    fonts = (data.get("themeStyle") or {}).get("fonts") or {}
    return {
        role: spec["family"]
        for role, spec in fonts.items()
        if isinstance(spec, dict) and "family" in spec
    }


def _slide(
    number: int,
    raw: dict,
    colors: dict,
    rules: dict[str, dict[str, str]]
) -> Slide:
    background = _background(raw)
    if background:
        _add_color(colors, background, "background", 10.0)
    slide = Slide(
        number=number,
        notes=raw.get("notes") or "",
        background=background,
        transition="magic move" if raw.get("morphFromPrevious") else None,
        transition_duration=float(raw.get("morphDuration") or 1000) / 1000.0,
        builds=[_build(step) for step in raw.get("timeline") or []],
    )
    elements = sorted(
        raw.get("elements", []),
        key=lambda e: (e.get("y", 0.0), e.get("z", 0.0)),
    )
    title_item: TextItem | None = None
    largest_item: TextItem | None = None
    largest_size = -1.0
    for element in elements:
        kind = element.get("type")
        if kind == "text":
            markup = element.get("html") or ""
            if SLIDE_NUMBER_MARKER in markup:
                continue
            text, runs = rich_text(markup)
            if not text:
                continue
            for value in _colors_in(markup):
                _add_color(colors, value, "text", 1.0)
            item = TextItem(
                text=text,
                x=element.get("x"),
                y=element.get("y"),
                w=element.get("w"),
                h=element.get("h"),
                style=_computed(element, rules),
                runs=runs,
                id=element.get("id"),
            )
            slide.items.append(item)
            if title_item is None and _is_title(element):
                title_item = item
            size = _max_font_size(markup)
            if size is not None and size > largest_size:
                largest_size = size
                largest_item = item
        elif kind == "image":
            box = element.get("sourceBox")
            slide.images.append(Image(
                path=element.get("src"),
                x=element.get("x"),
                y=element.get("y"),
                w=element.get("w"),
                h=element.get("h"),
                fit=element.get("fit") or "contain",
                mask=element.get("maskShape") if element.get("maskShape") == "circle" else None,
                radius=float(element.get("borderRadius") or 0.0),
                crop=(box["x"], box["y"], box["w"], box["h"]) if box else None,
                id=element.get("id"),
            ))
        elif kind == "table":
            slide.tables.append(Table(rows=element.get("rows", [])))
        elif kind == "shape":
            for key in ("fill", "stroke"):
                value = element.get(key)
                if isinstance(value, str):
                    _add_color(colors, value, "fill", 0.5)
            size = element.get("pathSize") or {}
            slide.shapes.append(Shape(
                kind=element.get("shape") or "rect",
                x=float(element.get("x") or 0.0),
                y=float(element.get("y") or 0.0),
                w=float(element.get("w") or 0.0),
                h=float(element.get("h") or 0.0),
                rot=float(element.get("rot") or 0.0),
                fill=element.get("fill"),
                stroke=element.get("stroke"),
                stroke_width=float(element.get("strokeWidth") or 0.0),
                radius=float(element.get("radius") or 0.0),
                path=element.get("path"),
                path_size=(size["w"], size["h"]) if size else None,
                arrow_start=bool(element.get("arrowStart")),
                arrow_end=bool(element.get("arrowEnd")),
                opacity=float(element.get("opacity") if element.get("opacity") is not None else 1.0),
                id=element.get("id"),
            ))
        elif kind in ("web", "video"):
            slide.embeds.append(Embed(
                kind=kind,
                src=element.get("src") or "",
                title=element.get("title"),
                poster=element.get("poster"),
                x=_number(element.get("x")),
                y=_number(element.get("y")),
                w=_number(element.get("w")),
                h=_number(element.get("h")),
                autoplay=bool(element.get("autoplay")),
                loop=bool(element.get("loop")),
                id=element.get("id"),
            ))
        elif kind == "html":
            markup = element.get("html") or ""
            rows = _html_table(markup)
            if rows:
                slide.tables.append(Table(
                    rows=rows,
                    x=_number(element.get("x")),
                    y=_number(element.get("y")),
                    w=_number(element.get("w")),
                    h=_number(element.get("h")),
                    style=_computed(element, rules),
                    id=element.get("id"),
                ))
            elif SLIDE_NUMBER_MARKER not in markup:
                text = strip_html(markup)
                if text:
                    slide.items.append(TextItem(
                        text=text,
                        x=element.get("x"),
                        y=element.get("y"),
                        w=element.get("w"),
                        h=element.get("h"),
                    ))
    chosen = (
        title_item
        or largest_item
        or (slide.items[0] if slide.items else None)
    )
    if chosen is not None:
        slide.title = chosen.text
        chosen.role = "title"
    return slide


def _build(step: dict) -> Build:
    trigger = step.get("trigger") or {}
    action = step.get("action") or {}
    return Build(
        target=action.get("target") or "",
        effect=action.get("type") or "appear",
        trigger=trigger.get("on") or "click",
        delay=float(trigger.get("delay") or 0) / 1000.0,
    )


def _is_title(element: dict) -> bool:
    if element.get("morphId") == "title":
        return True
    return TITLE_ROLE_CLASS in (element.get("class") or [])


def _max_font_size(markup: str) -> float | None:
    sizes = [float(v) for v in FONT_SIZE.findall(markup)]
    return max(sizes) if sizes else None


def _background(raw: dict) -> str | None:
    value = raw.get("background")
    if isinstance(value, dict):
        if value.get("image"):
            return None
        value = value.get("color")
    if not isinstance(value, str):
        return None
    found = _colors_in(value)
    return found[0] if found else None


def _number(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _html_table(markup: str) -> list[list[str]]:
    parser = _TableParser()
    parser.feed(markup)
    return parser.rows


def _hex6(value: str) -> str:
    return "#%s" % (value.lower(),)


def _hex3(value: str) -> str:
    doubled = "".join(ch * 2 for ch in value.lower())
    return "#%s" % (doubled,)


def _colors_in(markup: str) -> list[str]:
    found = ["#%02x%02x%02x" % tuple(int(v) for v in m) for m in RGB.findall(markup)]
    found += [_hex6(m) for m in HEX6.findall(markup)]
    found += [_hex3(m) for m in HEX3.findall(markup)]
    return found


def _add_color(
    colors: dict,
    value: str,
    kind: str,
    weight: float
) -> None:
    match = HEX6.search(value) or RGB.search(value) or HEX3.search(value)
    if match is None:
        return
    if match.re is HEX6:
        normalised = _hex6(match.group(1))
    elif match.re is HEX3:
        normalised = _hex3(match.group(1))
    else:
        normalised = "#%02x%02x%02x" % tuple(int(g) for g in match.groups())
    colors[(normalised, kind)] = colors.get((normalised, kind), 0.0) + weight


def _without_conditional_rules(text: str) -> str:
    # @media/@supports bodies can repeat a selector this file already
    # tracks (most importantly .slide), and the naive block regex below
    # cannot balance their nested braces on its own (it would otherwise
    # mis-parse the block header as a bogus rule and its first nested rule
    # as the real one — see the @keyframes case this already tolerates).
    # Drop each conditional block wholesale via manual brace counting so
    # its declarations never join the unconditional cascade.
    out = []
    pos = 0
    for match in CSS_AT_RULE.finditer(text):
        if match.start() < pos:
            continue
        out.append(text[pos:match.start()])
        depth = 1
        i = match.end()
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        pos = i
    out.append(text[pos:])
    return "".join(out)


def _theme_rules(
    root: pathlib.Path,
    data: dict
) -> dict[str, dict[str, str]]:
    path = root / (data.get("theme") or "theme.css")
    if not path.exists():
        return {}
    text = CSS_COMMENT.sub("", path.read_text())
    text = _without_conditional_rules(text)
    rules: dict[str, dict[str, str]] = {}
    for selector, body in CSS_BLOCK.findall(text):
        selector = selector.strip()
        if not selector:
            continue
        declarations = rules.setdefault(selector, {})
        for prop, value in CSS_DECLARATION.findall(body):
            declarations[prop.strip().lower()] = value.strip()
    return rules


def _harvest_theme_colors(
    colors: dict,
    rules: dict[str, dict[str, str]],
    slides: list[Slide]
) -> None:
    # The root .slide rule is the base every slide's text inherits, so its
    # `color` is weighted by the slide count; its `background` only counts
    # for slides that set none of their own, and not at all when there are
    # none. Every other rule's declarations get a flat weight of 1.
    root_declarations = rules.get(ROOT_SELECTOR, {})
    bare_count = sum(1 for slide in slides if not slide.background)
    for prop, value in root_declarations.items():
        if prop == "color":
            _add_color(colors, value, "text", float(len(slides)))
        elif prop in ("background", "background-color") and bare_count:
            _add_color(colors, value, "background", float(bare_count))
    for selector, declarations in rules.items():
        if selector == ROOT_SELECTOR:
            continue
        for prop, value in declarations.items():
            if prop == "color":
                _add_color(colors, value, "text", 1.0)
            elif prop in ("background", "background-color"):
                _add_color(colors, value, "fill", 1.0)
