import re
import json
import html
import pathlib
from html.parser import HTMLParser
from slides.model import ColorUse, Deck, Image, Slide, Table, TextItem

BREAK_TAGS = {"br", "p", "div", "li", "tr"}
RGB = re.compile(r"rgb\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)")
HEX = re.compile(r"#([0-9a-fA-F]{6})\b")


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in BREAK_TAGS and self.parts:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in BREAK_TAGS and self.parts:
            self.parts.append("\n")


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
    deck.colors = [
        ColorUse(hex=key[0], weight=weight, kind=key[1])
        for key, weight in sorted(colors.items(), key=lambda kv: -kv[1])
    ]
    return deck


def _fonts(data: dict) -> dict[str, str]:
    fonts = data.get("themeStyle", {}).get("fonts", {})
    return {
        role: spec["family"]
        for role, spec in fonts.items()
        if isinstance(spec, dict) and "family" in spec
    }


def _slide(number: int, raw: dict, colors: dict) -> Slide:
    background = raw.get("background")
    if isinstance(background, str):
        _add_color(colors, background, "background", 10.0)
    slide = Slide(
        number=number,
        notes=raw.get("notes") or "",
        background=background if isinstance(background, str) else None,
    )
    elements = sorted(
        raw.get("elements", []),
        key=lambda e: (e.get("y", 0.0), e.get("z", 0.0)),
    )
    for element in elements:
        kind = element.get("type")
        if kind == "text":
            text = strip_html(element.get("html") or "")
            if not text:
                continue
            for value in _colors_in(element.get("html") or ""):
                _add_color(colors, value, "text", 1.0)
            slide.items.append(TextItem(
                text=text,
                x=element.get("x"),
                y=element.get("y"),
                w=element.get("w"),
                h=element.get("h"),
            ))
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
    if slide.items:
        slide.title = slide.items[0].text
        slide.items[0].role = "title"
    return slide


def _colors_in(markup: str) -> list[str]:
    found = ["#%02x%02x%02x" % tuple(int(v) for v in m) for m in RGB.findall(markup)]
    found += ["#%s" % (m.lower(),) for m in HEX.findall(markup)]
    return found


def _add_color(colors: dict, value: str, kind: str, weight: float) -> None:
    match = HEX.search(value) or RGB.search(value)
    if match is None:
        return
    if match.re is HEX:
        normalised = "#%s" % (match.group(1).lower(),)
    else:
        normalised = "#%02x%02x%02x" % tuple(int(g) for g in match.groups())
    colors[(normalised, kind)] = colors.get((normalised, kind), 0.0) + weight
