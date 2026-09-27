import re
import json
import pathlib
from html.parser import HTMLParser
from slides.model import ColorUse, Deck, Embed, Image, Slide, Table, TextItem

BREAK_TAGS = {"br", "p", "div", "li", "tr"}
RGB = re.compile(r"rgb\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)")
HEX = re.compile(r"#([0-9a-fA-F]{6})\b")
SLIDE_NUMBER_MARKER = "data-slide-number"
TITLE_ROLE_CLASS = "role-title"
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_DECLARATION = re.compile(r"([a-zA-Z-]+)\s*:\s*([^;]+)")
ROOT_SELECTOR = ".slide"


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(
        self,
        data: str
    ) -> None:
        self.parts.append(data)

    def handle_starttag(
        self,
        tag: str,
        attrs: list
    ) -> None:
        if tag in BREAK_TAGS and self.parts:
            self.parts.append("\n")

    def handle_endtag(
        self,
        tag: str
    ) -> None:
        if tag in BREAK_TAGS and self.parts:
            self.parts.append("\n")


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None
        self._text: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list
    ) -> None:
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
        if tag in ("td", "th") and self._cell is not None:
            self._cell.append("".join(self._text).strip())
        elif tag == "tr" and self._cell is not None:
            self.rows.append(self._cell)
            self._cell = None

    def handle_data(
        self,
        data: str
    ) -> None:
        self._text.append(data)


def strip_html(markup: str) -> str:
    stripper = _Stripper()
    stripper.feed(markup)
    text = "".join(stripper.parts)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


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
    for number, raw in enumerate(data.get("slides", []), start=1):
        deck.slides.append(_slide(number, raw, colors))
    _harvest_theme_colors(colors, _theme_rules(root, data), deck.slides)
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
    colors: dict
) -> Slide:
    background = _background(raw)
    if background:
        _add_color(colors, background, "background", 10.0)
    slide = Slide(
        number=number,
        notes=raw.get("notes") or "",
        background=background,
    )
    elements = sorted(
        raw.get("elements", []),
        key=lambda e: (e.get("y", 0.0), e.get("z", 0.0)),
    )
    title_item: TextItem | None = None
    for element in elements:
        kind = element.get("type")
        if kind == "text":
            markup = element.get("html") or ""
            if SLIDE_NUMBER_MARKER in markup:
                continue
            text = strip_html(markup)
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
            )
            slide.items.append(item)
            if title_item is None and _is_title(element):
                title_item = item
        elif kind == "image":
            slide.images.append(Image(
                path=element.get("src"),
                x=element.get("x"),
                y=element.get("y"),
                w=element.get("w"),
                h=element.get("h"),
            ))
        elif kind == "table":
            slide.tables.append(Table(rows=element.get("rows", [])))
        elif kind == "shape":
            for key in ("fill", "stroke"):
                value = element.get(key)
                if isinstance(value, str):
                    _add_color(colors, value, "fill", 0.5)
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
            ))
        elif kind == "html":
            markup = element.get("html") or ""
            rows = _html_table(markup)
            if rows:
                slide.tables.append(Table(rows=rows))
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
    chosen = title_item or (slide.items[0] if slide.items else None)
    if chosen is not None:
        slide.title = chosen.text
        chosen.role = "title"
    return slide


def _is_title(element: dict) -> bool:
    if element.get("morphId") == "title":
        return True
    return TITLE_ROLE_CLASS in (element.get("class") or [])


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


def _colors_in(markup: str) -> list[str]:
    found = ["#%02x%02x%02x" % tuple(int(v) for v in m) for m in RGB.findall(markup)]
    found += ["#%s" % (m.lower(),) for m in HEX.findall(markup)]
    return found


def _add_color(
    colors: dict,
    value: str,
    kind: str,
    weight: float
) -> None:
    match = HEX.search(value) or RGB.search(value)
    if match is None:
        return
    if match.re is HEX:
        normalised = "#%s" % (match.group(1).lower(),)
    else:
        normalised = "#%02x%02x%02x" % tuple(int(g) for g in match.groups())
    colors[(normalised, kind)] = colors.get((normalised, kind), 0.0) + weight


def _theme_rules(
    root: pathlib.Path,
    data: dict
) -> dict[str, dict[str, str]]:
    path = root / (data.get("theme") or "theme.css")
    if not path.exists():
        return {}
    text = CSS_COMMENT.sub("", path.read_text())
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
