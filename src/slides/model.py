import pathlib
from dataclasses import dataclass, field


@dataclass
class Run:
    # A span of an item's text whose look differs from the item's own: CSS
    # properties such as color or font-weight, over characters start..end.
    start: int
    end: int
    style: dict[str, str] = field(default_factory=dict)


@dataclass
class TextItem:
    text: str
    role: str = "body"
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    style: dict[str, str] = field(default_factory=dict)
    runs: list[Run] = field(default_factory=list)
    id: str | None = None


@dataclass
class Table:
    rows: list[list[str]] = field(default_factory=list)
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    style: dict[str, str] = field(default_factory=dict)
    id: str | None = None


@dataclass
class Image:
    path: str | None = None
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    fit: str = "contain"
    mask: str | None = None
    radius: float = 0.0
    crop: tuple[float, float, float, float] | None = None
    id: str | None = None


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
    id: str | None = None

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
class Build:
    # One step of a slide's animation: what appears or goes, and what starts it
    # ("click", "afterPrev" or "withPrev"), after delay seconds.
    target: str
    effect: str
    trigger: str = "click"
    delay: float = 0.0


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
    transition: str | None = None
    transition_duration: float = 1.0
    builds: list[Build] = field(default_factory=list)

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
