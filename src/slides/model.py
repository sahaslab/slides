import pathlib
from dataclasses import dataclass, field


@dataclass
class TextItem:
    text: str
    role: str = "body"
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    color: str | None = None


@dataclass
class Table:
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class Image:
    path: str | None = None
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None


@dataclass
class Embed:
    kind: str
    src: str
    title: str | None = None
    poster: str | None = None
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None

    def label(self) -> str:
        name = self.title or pathlib.PurePosixPath(self.src).name
        kind = "Interactive" if self.kind == "web" else "Video"
        return "%s: %s" % (kind, name)


@dataclass
class ColorUse:
    hex: str
    weight: float
    kind: str


@dataclass
class Slide:
    number: int
    title: str | None = None
    items: list[TextItem] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    embeds: list[Embed] = field(default_factory=list)
    notes: str = ""
    background: str | None = None

    def body_items(self) -> list[TextItem]:
        seen: set[str] = set()
        if self.title:
            seen.add(self.title.strip())
        out: list[TextItem] = []
        for item in self.items:
            text = item.text.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(item)
        return out


@dataclass
class Deck:
    title: str
    slides: list[Slide] = field(default_factory=list)
    width: float = 1920.0
    height: float = 1080.0
    source: str = ""
    kind: str = ""
    colors: list[ColorUse] = field(default_factory=list)
    fonts: dict[str, str] = field(default_factory=dict)
