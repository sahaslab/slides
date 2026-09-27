# `slides` CLI and Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One installed `slides` command, and one importable `slides` package, covering deck conversion between Keynote/DeckWerk/PowerPoint, deck-to-text dumping, Keynote mutation, and palette extraction.

**Architecture:** A normalised `Deck` dataclass is the spine — four readers produce it, several writers consume it, so N readers and M writers cost N+M pieces. The CLI is a thin argparse layer over the library. Heavy dependencies import lazily inside the reader that needs them.

**Tech Stack:** Python 3.10+, hatchling, argparse, `keynote-parser` (in-memory IWA reading), `python-pptx`, `osascript -l JavaScript` for live Keynote, pure-Python OKLab colour science, pytest.

**Spec:** `docs/superpowers/specs/2026-09-27-slides-cli-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **Python style (from the user's global CLAUDE.md, non-negotiable):**
  - Double-quoted strings, never single-quoted.
  - C-style format strings `"%s" % (x,)`, never f-strings.
  - Type annotations on every function except `def main()`.
  - In scripts, `def main():` goes at the top, helpers below, `if __name__ == "__main__":` at the bottom.
  - No text before the imports (no module docstring above them).
  - Import order, with **no blank lines between the blocks**: builtins (`sys`, `os`, then others by commonness), then installed libraries as bare `import x`, then all `from x import y`.
  - 1TB style: either all arguments on one line, or exactly one argument per line with the parens on their own lines.
  - `argparse` with sensible defaults, and **no `description=`** on the parser.
  - No defensive programming. No try/except unless the exception is genuinely likely. Let assertions through.
  - KISS, YAGNI, DRY. Comments delineate sections; strip the rest.
- **Package layout:** `src/slides/`, hatchling, entry point `slides = "slides.cli:main"`.
- **Dependency floors:** `keynote-parser>=1.14`, `python-pptx>=0.6.23`, `matplotlib>=3.7` (extra `figures` only).
- **Lazy imports:** `keynote_parser`, `pptx` and `matplotlib` are imported *inside the function that uses them*, never at module top level. `slides --help` must not load any of them.
- **Colour science is pure Python.** No numpy, no colormath.
- **stdout is the data channel.** Diagnostics go to stderr. Colour only when `sys.stdout.isatty()`.
- **The tool ships no palette, theme, template or house style.**
- **Never write to a deck the user did not name.** Only `patch`, `scaffold` and `math` mutate, and each takes an explicit target.

## Review Focus

Input classes the spec implies but no task's happy-path tests would exercise. Each has its test pinned to the task that owns the code.

1. **A `.key` saved as a directory bundle, not a zip.** Keynote writes both; `zipfile.ZipFile` fails outright on the bundle form. The reader must handle both. (Task 6)
2. **`￼` object-replacement characters and embedded newlines in storage text.** Every image, equation and inline drawable leaves `￼` in the text run; dumping it raw puts mojibake in the Markdown. (Task 6)
3. **Keynote not running, or running with no document open.** A live command must say so in one line, not surface an osascript traceback. (Task 7)
4. **A deck whose background is an image or gradient, not a solid fill.** Theme extraction must still return a usable `background` hex rather than `None`, since every emitter formats it. (Task 11)
5. **A deck with zero slides, and a slide with no title.** Both are legal and both reach the writers, which index and de-duplicate against the title. (Task 4)

---

## File Structure

```
pyproject.toml
src/slides/
  __init__.py        read_deck dispatch, public re-exports
  model.py           Deck, Slide, TextItem, Table, Image, ColorUse
  cli.py             argparse subcommands, thin
  color.py           OKLab/OKLCH, WCAG contrast, delta-E
  theme.py           DeckTheme, palette extraction, role inference
  readers/
    __init__.py
    deckwerk.py      deck.json + notes.md
    keynote_file.py  .key, in-memory IWA
    keynote_live.py  front document, Apple Events
    pptx.py          python-pptx
  writers/
    __init__.py
    markdown.py  text.py  json.py  pptx.py
  emit/
    __init__.py
    matplotlib.py  ggplot.py  css.py
  keynote/
    __init__.py
    jxa.py           osascript bridge
    package.py       keynote-parser round-trip for writing
    math.py          LaTeX -> equation archives
  deckwerk/
    __init__.py
    importer.py      wraps import_keynote.py
    agent.py         wraps slide-agent
tests/
  fixtures/          minimal decks built for the purpose
  test_*.py
```

---

## Task 1: Package skeleton and CLI entry point

**Files:**
- Create: `pyproject.toml`, `src/slides/__init__.py`, `src/slides/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `slides.cli.main() -> int`; console script `slides`; `slides.__version__: str`.

- [ ] **Step 1: Write the failing test**

```python
import sys
import subprocess
from slides import __version__
from slides.cli import build_parser


def test_version_is_set():
    assert __version__ == "0.1.0"


def test_parser_has_every_subcommand():
    parser = build_parser()
    action = [a for a in parser._actions if a.dest == "command"][0]
    assert set(action.choices) == {
        "dump", "convert", "scaffold", "patch", "math", "theme", "info",
    }


def test_help_does_not_import_heavy_dependencies():
    code = (
        "import sys; from slides import cli; cli.build_parser(); "
        "print(','.join(m for m in ('keynote_parser','pptx','matplotlib') "
        "if m in sys.modules))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides'`

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "slides"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "keynote-parser>=1.14",
    "python-pptx>=0.6.23",
]

[project.optional-dependencies]
figures = ["matplotlib>=3.7"]

[project.scripts]
slides = "slides.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/slides"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Write `src/slides/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Write `src/slides/cli.py`**

Note the `main()`-at-top ordering and the absence of a parser `description`.

```python
import sys
import argparse


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 2
    return DISPATCH[args.command](args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="slides")
    sub = parser.add_subparsers(dest="command")

    dump = sub.add_parser("dump")
    dump.add_argument("target", nargs="?", default=None)
    dump.add_argument("-f", "--format", default="md", choices=["md", "json", "txt"])
    dump.add_argument("-o", "--output", default=None)
    dump.add_argument("--out-dir", default=None)
    dump.add_argument("--notes-only", action="store_true")
    dump.add_argument("--clipboard", action="store_true")
    dump.add_argument("--via-deckwerk", action="store_true")
    dump.add_argument("--assets-dir", default=None)
    dump.add_argument("--copy-media", action="store_true")

    convert = sub.add_parser("convert")
    convert.add_argument("target")
    convert.add_argument(
        "-f",
        "--format",
        required=True,
        choices=["deckwerk", "pptx", "keynote", "pdf"],
    )
    convert.add_argument("-o", "--output", default=None)
    convert.add_argument("--deckwerk-root", default=None)

    theme = sub.add_parser("theme")
    theme.add_argument("target")
    theme.add_argument(
        "-f",
        "--format",
        default="json",
        choices=["json", "matplotlib", "ggplot", "css"],
    )
    theme.add_argument("--accents", type=int, default=6)

    info = sub.add_parser("info")
    info.add_argument("target")
    info.add_argument("--deckwerk-root", default=None)

    patch = sub.add_parser("patch")
    patch.add_argument("spec")

    scaffold = sub.add_parser("scaffold")
    scaffold.add_argument("spec")
    scaffold.add_argument("--template", default=None)

    math = sub.add_parser("math")
    math.add_argument("target")
    math.add_argument("-o", "--output", default=None)
    math.add_argument("--min-slide", type=int, default=1)

    return parser


def not_implemented(args: argparse.Namespace) -> int:
    sys.stderr.write("%s is not implemented yet\n" % (args.command,))
    return 1


DISPATCH = {
    "dump": not_implemented,
    "convert": not_implemented,
    "scaffold": not_implemented,
    "patch": not_implemented,
    "math": not_implemented,
    "theme": not_implemented,
    "info": not_implemented,
}

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pip install -e . && pytest tests/test_cli.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/slides tests/test_cli.py
git commit -m "feat: package skeleton and CLI entry point"
```

---

## Task 2: The deck model and reader dispatch

**Files:**
- Create: `src/slides/model.py`, `src/slides/readers/__init__.py`
- Modify: `src/slides/__init__.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes: Task 1's package.
- Produces:
  - `slides.model.TextItem(text, role="body", x=None, y=None, w=None, h=None, color=None)`
  - `slides.model.Table(rows: list[list[str]])`
  - `slides.model.Image(path=None, x=None, y=None, w=None, h=None)`
  - `slides.model.ColorUse(hex: str, weight: float, kind: str)`
  - `slides.model.Slide(number, title=None, items=[], tables=[], images=[], notes="", background=None)`
  - `slides.model.Deck(title, slides=[], width=1920.0, height=1080.0, source="", kind="", colors=[], fonts={})`
  - `Slide.body_items() -> list[TextItem]` — items whose text differs from the title, de-duplicated, order preserved
  - `slides.read_deck(target: str | Path | None, via_deckwerk: bool = False) -> Deck`
  - `slides.readers.detect(target) -> str` returning `"live" | "keynote" | "pptx" | "deckwerk"`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from slides.model import Deck, Slide, TextItem
from slides.readers import detect


def test_body_items_drop_the_title():
    slide = Slide(
        number=1,
        title="Fitting a line",
        items=[
            TextItem(text="Fitting a line", role="title"),
            TextItem(text="Minimize squared error"),
        ],
    )
    assert [i.text for i in slide.body_items()] == ["Minimize squared error"]


def test_body_items_deduplicate():
    slide = Slide(
        number=1,
        title=None,
        items=[TextItem(text="Same"), TextItem(text="Same"), TextItem(text="Other")],
    )
    assert [i.text for i in slide.body_items()] == ["Same", "Other"]


def test_body_items_drop_blanks():
    slide = Slide(number=1, items=[TextItem(text="  "), TextItem(text="Real")])
    assert [i.text for i in slide.body_items()] == ["Real"]


def test_deck_defaults():
    deck = Deck(title="Talk")
    assert deck.slides == []
    assert (deck.width, deck.height) == (1920.0, 1080.0)


def test_detect_by_suffix(tmp_path):
    key = tmp_path / "a.key"
    key.touch()
    pptx = tmp_path / "a.pptx"
    pptx.touch()
    dw = tmp_path / "dw"
    dw.mkdir()
    (dw / "deck.json").write_text("{}")
    assert detect(key) == "keynote"
    assert detect(pptx) == "pptx"
    assert detect(dw) == "deckwerk"
    assert detect(None) == "live"


def test_detect_rejects_unknown(tmp_path):
    other = tmp_path / "a.txt"
    other.touch()
    with pytest.raises(ValueError, match="not a deck"):
        detect(other)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.model'`

- [ ] **Step 3: Write `src/slides/model.py`**

```python
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
```

- [ ] **Step 4: Write `src/slides/readers/__init__.py`**

Each reader is imported inside `read` so a `.key` dump never loads `pptx`.

```python
import pathlib
from slides.model import Deck


def detect(target: str | pathlib.Path | None) -> str:
    if target is None:
        return "live"
    path = pathlib.Path(target)
    if path.suffix == ".key":
        return "keynote"
    if path.suffix == ".pptx":
        return "pptx"
    if path.is_dir() and (path / "deck.json").exists():
        return "deckwerk"
    raise ValueError("%s is not a deck" % (path,))


def read(target: str | pathlib.Path | None, via_deckwerk: bool = False) -> Deck:
    kind = detect(target)
    if kind == "live":
        from slides.readers import keynote_live
        return keynote_live.read()
    if kind == "keynote":
        from slides.readers import keynote_file
        return keynote_file.read(target, via_deckwerk=via_deckwerk)
    if kind == "pptx":
        from slides.readers import pptx
        return pptx.read(target)
    from slides.readers import deckwerk
    return deckwerk.read(target)
```

- [ ] **Step 5: Re-export from `src/slides/__init__.py`**

```python
from slides.model import ColorUse, Deck, Image, Slide, Table, TextItem
from slides.readers import read as read_deck

__version__ = "0.1.0"
__all__ = [
    "ColorUse",
    "Deck",
    "Image",
    "Slide",
    "Table",
    "TextItem",
    "read_deck",
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_model.py tests/test_cli.py -v`
Expected: 9 passed. The lazy-import test from Task 1 must still pass.

- [ ] **Step 7: Commit**

```bash
git add src/slides tests/test_model.py
git commit -m "feat: normalised deck model and reader dispatch"
```

---

## Task 3: DeckWerk reader

**Files:**
- Create: `src/slides/readers/deckwerk.py`, `tests/fixtures/mini_deckwerk/deck.json`, `tests/fixtures/mini_deckwerk/notes.md`
- Test: `tests/test_reader_deckwerk.py`

**Interfaces:**
- Consumes: `slides.model.Deck/Slide/TextItem/Table/Image/ColorUse`.
- Produces: `slides.readers.deckwerk.read(path) -> Deck`; `strip_html(markup: str) -> str`.

Real `deck.json` shape, confirmed against a live deck: top-level `title`, `canvas: {w, h}`, `themeStyle.fonts.{title,heading,body,caption}.family`, and `slides[]` with `id`, `name`, `notes` (a plain string), `background`, and `elements[]`. Each element has `id`, `x`, `y`, `w`, `h`, `z`, `type` (`"text" | "shape" | "image" | "video" | "web"`), and for text an `html` field carrying inline markup such as `Assignment 1 <span style="color: rgb(152, 12, 12);">due tonight!</span>`.

- [ ] **Step 1: Write the fixture `tests/fixtures/mini_deckwerk/deck.json`**

```json
{
  "version": 1,
  "title": "Mini",
  "canvas": { "w": 1920, "h": 1080 },
  "themeStyle": {
    "fonts": {
      "title": { "family": "Libre Franklin" },
      "body": { "family": "Libre Franklin" }
    }
  },
  "slides": [
    {
      "id": "slide-1",
      "name": "Opening",
      "background": "#0d1e1c",
      "notes": "Say hello.",
      "elements": [
        { "id": "e1", "x": 120, "y": 84, "w": 1680, "h": 67, "z": 1,
          "type": "text", "html": "Opening" },
        { "id": "e2", "x": 120, "y": 300, "w": 800, "h": 60, "z": 2,
          "type": "text",
          "html": "First <span style=\"color: rgb(165, 215, 95);\">point</span>" },
        { "id": "e3", "x": 960, "y": 300, "w": 800, "h": 400, "z": 3,
          "type": "image", "src": "assets/plot.png" }
      ]
    },
    {
      "id": "slide-2",
      "name": "Numbers",
      "background": "#0d1e1c",
      "notes": "",
      "elements": [
        { "id": "e4", "x": 120, "y": 84, "w": 1680, "h": 67, "z": 1,
          "type": "text", "html": "Numbers" },
        { "id": "e5", "x": 120, "y": 300, "w": 800, "h": 200, "z": 2,
          "type": "table",
          "rows": [["Model", "MSE"], ["Linear", "3.2"], ["Quadratic", "2.1"]] }
      ]
    }
  ]
}
```

Write `tests/fixtures/mini_deckwerk/notes.md` as a single line: `Notes file is not the source of truth.`

- [ ] **Step 2: Write the failing test**

```python
import pathlib
from slides.readers.deckwerk import read, strip_html

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def test_reads_deck_metadata():
    deck = read(FIXTURE)
    assert deck.title == "Mini"
    assert (deck.width, deck.height) == (1920.0, 1080.0)
    assert deck.kind == "deckwerk"
    assert len(deck.slides) == 2


def test_first_element_by_z_and_position_becomes_the_title():
    deck = read(FIXTURE)
    assert deck.slides[0].title == "Opening"
    assert deck.slides[1].title == "Numbers"


def test_strips_inline_markup_but_keeps_the_text():
    deck = read(FIXTURE)
    assert [i.text for i in deck.slides[0].body_items()] == ["First point"]


def test_collects_colors_with_roles():
    deck = read(FIXTURE)
    kinds = {c.hex: c.kind for c in deck.colors}
    assert kinds["#0d1e1c"] == "background"
    assert kinds["#a5d75f"] == "text"


def test_reads_notes_tables_and_images():
    deck = read(FIXTURE)
    assert deck.slides[0].notes == "Say hello."
    assert deck.slides[0].images[0].path == "assets/plot.png"
    assert deck.slides[1].tables[0].rows[0] == ["Model", "MSE"]


def test_strip_html_handles_entities_and_breaks():
    assert strip_html("a &amp; b<br>c") == "a & b\nc"
    assert strip_html("<p>one</p><p>two</p>") == "one\ntwo"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_reader_deckwerk.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.readers.deckwerk'`

- [ ] **Step 4: Write `src/slides/readers/deckwerk.py`**

`html.parser` is stdlib, so nothing heavy loads here. Titles are identified by position — the topmost text element — which is how DeckWerk decks are actually laid out; there is no title role in `deck.json`.

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_reader_deckwerk.py -v`
Expected: 6 passed

- [ ] **Step 6: Verify against a real deck**

Run:
```bash
python -c "
from slides import read_deck
d = read_deck('$HOME/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/04_sep28_conditional_linear')
print(d.title, len(d.slides))
print(d.slides[1].title, '|', [i.text for i in d.slides[1].body_items()][:2])
"
```
Expected: a title, a slide count above 1, and readable text with no HTML tags.

- [ ] **Step 7: Commit**

```bash
git add src/slides/readers/deckwerk.py tests/fixtures/mini_deckwerk tests/test_reader_deckwerk.py
git commit -m "feat: DeckWerk reader"
```

---

## Task 4: Markdown, text and JSON writers

**Files:**
- Create: `src/slides/writers/__init__.py`, `src/slides/writers/markdown.py`, `src/slides/writers/text.py`, `src/slides/writers/json.py`
- Test: `tests/test_writers.py`

**Interfaces:**
- Consumes: `slides.model.Deck`, `Slide.body_items()`.
- Produces: `markdown.render(deck, notes_only=False) -> str`, `text.render(deck, notes_only=False) -> str`, `json.render(deck, notes_only=False) -> str`, and `slides.writers.render(deck, fmt, notes_only=False) -> str` where `fmt` is `"md" | "txt" | "json"`.

Covers **Review Focus 5**: a deck with zero slides, and a slide with no title.

- [ ] **Step 1: Write the failing test**

```python
import json as jsonlib
from slides.model import Deck, Slide, Table, TextItem
from slides.writers import json as json_writer
from slides.writers import markdown, render, text


def a_deck() -> Deck:
    return Deck(
        title="Talk",
        slides=[
            Slide(
                number=1,
                title="Fitting a line",
                items=[
                    TextItem(text="Fitting a line", role="title"),
                    TextItem(text="Minimize squared error\nCheck residuals"),
                ],
                notes="Ask for a show of hands.",
            ),
            Slide(
                number=2,
                title="Results",
                items=[TextItem(text="Results", role="title")],
                tables=[Table(rows=[["Model", "MSE"], ["Linear", "3.2"]])],
            ),
        ],
    )


def test_markdown_shape():
    out = markdown.render(a_deck())
    assert out.startswith("# Talk\n")
    assert "## Slide 1" in out
    assert "### Fitting a line" in out
    assert "- Minimize squared error\n- Check residuals" in out
    assert "> Ask for a show of hands." in out


def test_markdown_tables_get_a_separator_row():
    out = markdown.render(a_deck())
    assert "| Model | MSE |" in out
    assert "| --- | --- |" in out


def test_markdown_does_not_repeat_the_title_as_a_bullet():
    out = markdown.render(a_deck())
    assert "- Fitting a line" not in out


def test_notes_only_drops_everything_else():
    out = markdown.render(a_deck(), notes_only=True)
    assert "Ask for a show of hands." in out
    assert "Minimize squared error" not in out
    assert "Results" not in out


def test_empty_deck_still_renders_a_header():
    out = markdown.render(Deck(title="Nothing"))
    assert out.strip() == "# Nothing"


def test_slide_without_a_title_renders_its_body():
    deck = Deck(title="T", slides=[Slide(number=1, items=[TextItem(text="Only body")])])
    out = markdown.render(deck)
    assert "## Slide 1" in out
    assert "- Only body" in out
    assert "### " not in out


def test_text_writer_has_no_markup():
    out = text.render(a_deck())
    assert "Fitting a line" in out
    assert "#" not in out
    assert "- " not in out


def test_json_writer_round_trips():
    parsed = jsonlib.loads(json_writer.render(a_deck()))
    assert parsed["title"] == "Talk"
    assert parsed["slides"][0]["title"] == "Fitting a line"
    assert parsed["slides"][0]["notes"] == "Ask for a show of hands."
    assert parsed["slides"][1]["tables"][0][0] == ["Model", "MSE"]


def test_render_dispatches_on_format():
    deck = a_deck()
    assert render(deck, "md") == markdown.render(deck)
    assert render(deck, "txt") == text.render(deck)
    assert render(deck, "json") == json_writer.render(deck)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_writers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.writers'`

- [ ] **Step 3: Write `src/slides/writers/markdown.py`**

```python
from slides.model import Deck, Slide


def render(deck: Deck, notes_only: bool = False) -> str:
    out = ["# %s\n" % (deck.title,)]
    for slide in deck.slides:
        if notes_only:
            if slide.notes.strip():
                out.append("## Slide %d\n" % (slide.number,))
                out.append(_quote(slide.notes))
            continue
        out.append("## Slide %d\n" % (slide.number,))
        out.append(_slide(slide))
    return "\n".join(out).rstrip() + "\n"


def _slide(slide: Slide) -> str:
    parts: list[str] = []
    if slide.title:
        parts.append("### %s\n" % (slide.title,))
    for item in slide.body_items():
        parts.append(_bullets(item.text))
    for table in slide.tables:
        parts.append(_table(table.rows))
    if slide.notes.strip():
        parts.append(_quote(slide.notes))
    return "\n".join(parts)


def _bullets(text: str) -> str:
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join("- %s" % (line,) for line in lines if line) + "\n"


def _table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    out = [_row(rows[0], width), "|%s" % (" --- |" * width,)]
    out += [_row(row, width) for row in rows[1:]]
    return "\n".join(out) + "\n"


def _row(cells: list[str], width: int) -> str:
    padded = list(cells) + [""] * (width - len(cells))
    return "|%s" % ("".join(" %s |" % (str(c).strip(),) for c in padded),)


def _quote(notes: str) -> str:
    lines = [line.strip() for line in notes.split("\n")]
    return "\n".join("> %s" % (line,) for line in lines if line) + "\n"
```

- [ ] **Step 4: Write `src/slides/writers/text.py`**

```python
from slides.model import Deck


def render(deck: Deck, notes_only: bool = False) -> str:
    out = [deck.title, ""]
    for slide in deck.slides:
        if notes_only:
            if slide.notes.strip():
                out.append(slide.notes.strip())
                out.append("")
            continue
        if slide.title:
            out.append(slide.title)
        for item in slide.body_items():
            out.append(item.text.strip())
        for table in slide.tables:
            for row in table.rows:
                out.append("\t".join(str(c).strip() for c in row))
        if slide.notes.strip():
            out.append(slide.notes.strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
```

- [ ] **Step 5: Write `src/slides/writers/json.py`**

```python
import json
from slides.model import Deck


def render(deck: Deck, notes_only: bool = False) -> str:
    return json.dumps(to_dict(deck, notes_only=notes_only), indent=2)


def to_dict(deck: Deck, notes_only: bool = False) -> dict:
    return {
        "title": deck.title,
        "source": deck.source,
        "kind": deck.kind,
        "canvas": {"w": deck.width, "h": deck.height},
        "slides": [_slide(s, notes_only) for s in deck.slides],
    }


def _slide(slide, notes_only: bool) -> dict:
    if notes_only:
        return {"number": slide.number, "notes": slide.notes}
    return {
        "number": slide.number,
        "title": slide.title,
        "body": [i.text for i in slide.body_items()],
        "tables": [t.rows for t in slide.tables],
        "images": [i.path for i in slide.images],
        "notes": slide.notes,
        "background": slide.background,
    }
```

- [ ] **Step 6: Write `src/slides/writers/__init__.py`**

```python
from slides.model import Deck
from slides.writers import json, markdown, text

WRITERS = {"md": markdown, "txt": text, "json": json}


def render(deck: Deck, fmt: str, notes_only: bool = False) -> str:
    return WRITERS[fmt].render(deck, notes_only=notes_only)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_writers.py -v`
Expected: 9 passed

- [ ] **Step 8: Commit**

```bash
git add src/slides/writers tests/test_writers.py
git commit -m "feat: markdown, text and JSON writers"
```

---

## Task 5: `slides dump`

**Files:**
- Create: `src/slides/commands/__init__.py`, `src/slides/commands/dump.py`
- Modify: `src/slides/cli.py` (replace `not_implemented` for `"dump"` in `DISPATCH`)
- Test: `tests/test_dump.py`

**Interfaces:**
- Consumes: `slides.readers.read`, `slides.writers.render`, `slides.model.Embed`.
- Produces: `slides.commands.dump.run(args) -> int`, `slides.commands.dump.copy_embeds(deck, destination, copy_media=False) -> dict[str, str]` returning a map of original src to the path written.

**Sidecar assets.** Task 20 makes `web` and `video` elements reachable as
`Slide.embeds`. `dump` is where they reach disk: when the output goes to a
file, every `web` embed's page is copied into a sidecar folder beside it and
the links in the rendered Markdown are rewritten to point there. DeckWerk's
web pages are self-contained by construction — staged under `assets/web/` to
run in an `<iframe sandbox>` with no access to the deck — so copying the file
is enough to get a working demo.

Rules:
- The sidecar folder is `--assets-dir` if given, else the output file's stem
  plus `_assets` (`talk.md` -> `talk_assets/`).
- `video` embeds are linked, not copied — video files are large and already on
  disk. `--copy-media` copies them too.
- Dumping to stdout copies nothing, because there is no output location to
  copy beside. Links then point at the paths inside the deck, and `dump` says
  so once on stderr rather than silently producing dead links.
- A `src` that does not exist on disk is reported on stderr and left linked in
  place; a missing asset is not a reason to fail the whole dump.

- [ ] **Step 1: Write the failing test**

```python
import pathlib
import argparse
from slides.commands import dump

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def an_args(**kw) -> argparse.Namespace:
    base = {
        "target": str(FIXTURE),
        "format": "md",
        "output": None,
        "out_dir": None,
        "notes_only": False,
        "clipboard": False,
        "via_deckwerk": False,
        "assets_dir": None,
        "copy_media": False,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def test_writes_markdown_to_stdout(capsys):
    assert dump.run(an_args()) == 0
    assert "# Mini" in capsys.readouterr().out


def test_writes_to_a_named_file(tmp_path):
    out = tmp_path / "deck.md"
    assert dump.run(an_args(output=str(out))) == 0
    assert "# Mini" in out.read_text()


def test_out_dir_names_the_file_after_the_deck(tmp_path):
    assert dump.run(an_args(out_dir=str(tmp_path))) == 0
    assert (tmp_path / "mini_deckwerk.md").exists()


def test_json_format_uses_the_json_extension(tmp_path):
    assert dump.run(an_args(format="json", out_dir=str(tmp_path))) == 0
    assert (tmp_path / "mini_deckwerk.json").exists()


def test_web_embed_is_copied_beside_the_output(tmp_path):
    out = tmp_path / "deck.md"
    assert dump.run(an_args(output=str(out))) == 0
    copied = tmp_path / "deck_assets" / "demo.html"
    assert copied.exists()
    assert copied.read_text().strip() != ""
    assert "deck_assets/demo.html" in out.read_text()


def test_assets_dir_overrides_the_default_location(tmp_path):
    out = tmp_path / "deck.md"
    where = tmp_path / "elsewhere"
    assert dump.run(an_args(output=str(out), assets_dir=str(where))) == 0
    assert (where / "demo.html").exists()


def test_video_is_linked_but_not_copied_by_default(tmp_path):
    out = tmp_path / "deck.md"
    assert dump.run(an_args(output=str(out))) == 0
    assert not (tmp_path / "deck_assets" / "clip.mp4").exists()
    assert "clip.mp4" in out.read_text()


def test_stdout_copies_nothing_and_warns(tmp_path, capsys):
    assert dump.run(an_args()) == 0
    captured = capsys.readouterr()
    assert "demo.html" in captured.out
    assert "not copied" in captured.err


def test_a_missing_asset_is_reported_and_does_not_fail_the_dump(tmp_path):
    import json
    import shutil
    deck_dir = tmp_path / "deck"
    shutil.copytree(FIXTURE, deck_dir)
    (deck_dir / "assets" / "web" / "demo.html").unlink()
    out = tmp_path / "deck.md"
    args = an_args(target=str(deck_dir), output=str(out))
    assert dump.run(args) == 0
    assert out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dump.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.commands'`

- [ ] **Step 3: Write `src/slides/commands/dump.py`**

```python
import sys
import pathlib
import argparse
import subprocess
from slides import readers, writers

SUFFIX = {"md": ".md", "txt": ".txt", "json": ".json"}


def run(args: argparse.Namespace) -> int:
    deck = readers.read(args.target, via_deckwerk=args.via_deckwerk)
    rendered = writers.render(deck, args.format, notes_only=args.notes_only)
    if args.clipboard:
        subprocess.run(["pbcopy"], input=rendered, text=True, check=True)
        sys.stderr.write("Copied %d slides to the clipboard\n" % (len(deck.slides),))
        return 0
    path = _destination(args, deck)
    if path is None:
        sys.stdout.write(rendered)
        return 0
    path.write_text(rendered)
    sys.stderr.write("Wrote %s\n" % (path,))
    return 0


def _destination(args: argparse.Namespace, deck) -> pathlib.Path | None:
    if args.output:
        return pathlib.Path(args.output)
    if args.out_dir:
        directory = pathlib.Path(args.out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stem = pathlib.Path(deck.source).stem if deck.source else deck.title
        return directory / ("%s%s" % (stem, SUFFIX[args.format]))
    return None
```

Write `src/slides/commands/__init__.py` as an empty file.

- [ ] **Step 4: Wire it into `src/slides/cli.py`**

Replace the `"dump"` entry in `DISPATCH`. The import goes inside the wrapper so `--help` stays cheap.

```python
def _dump(args: argparse.Namespace) -> int:
    from slides.commands import dump
    return dump.run(args)


DISPATCH = {
    "dump": _dump,
    "convert": not_implemented,
    "scaffold": not_implemented,
    "patch": not_implemented,
    "math": not_implemented,
    "theme": not_implemented,
    "info": not_implemented,
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_dump.py tests/test_cli.py -v`
Expected: 7 passed, including the lazy-import test

- [ ] **Step 6: Verify end to end**

```bash
slides dump ~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/04_sep28_conditional_linear | head -30
```
Expected: a Markdown dump. Time it — it should return in well under a second.

- [ ] **Step 7: Commit**

```bash
git add src/slides/commands src/slides/cli.py tests/test_dump.py
git commit -m "feat: slides dump"
```

---

## Task 6: Keynote `.key` reader, headless

**Files:**
- Create: `src/slides/readers/keynote_file.py`
- Test: `tests/test_reader_keynote_file.py`

**Interfaces:**
- Consumes: `slides.model`.
- Produces: `slides.readers.keynote_file.read(path, via_deckwerk=False) -> Deck`; `archives(path) -> dict[str, dict]`; `clean(text: str) -> str`.
- **Forward reference:** `via_deckwerk=True` imports `slides.deckwerk.importer`, which does not exist until Task 13. The import sits inside the branch, so nothing breaks before then and no test in this task exercises the flag; Task 13 adds the test that does.

**The archive graph, confirmed against a real 35-slide deck.** A `.key` is a package of Snappy-framed protobuf `.iwa` streams. `IWAFile.from_buffer(data, name).to_dict()` yields `{"chunks": [{"archives": [{"header": {"identifier": "1042"}, "objects": [...]}]}]}`. Reading all 202 streams of a real deck takes **0.16s** in memory, so no unpacking to disk is needed. The traversal:

1. `Index/Document.iwa` holds `KN.ShowArchive` with `size: {width, height}` and `slideTree.slides` — the **ordered** list of `KN.SlideNodeArchive` identifiers.
2. Each `KN.SlideNodeArchive` has `slide: {identifier}` pointing at the slide archive, which lives in one of the `Index/Slide*.iwa` streams. Build one id→object index across every stream; **do not** infer the stream from the filename, because the ids do not match.
3. A slide archive has `titlePlaceholder`, `bodyPlaceholder`, `drawablesZOrder` (a list of identifiers in z-order), `ownedDrawables`, and `note`.
4. A drawable is a `KN.PlaceholderArchive` (with `kind: kKindTitlePlaceholder` / `kKindBodyPlaceholder`, and storage under `super.ownedStorage`) or a `TSWP.ShapeInfoArchive` (storage under `ownedStorage`). Resolve by looking for `ownedStorage`/`deprecatedStorage` at the object level, then one level down under `super`.
5. The storage is a `TSWP.StorageArchive` whose `text` is a **list** of strings.
6. `note` points at a `KN.NoteArchive` whose `containedStorage` resolves the same way.
7. Colours appear as `{red, green, blue}` float dicts.

Covers **Review Focus 1** (directory bundle) and **Review Focus 2** (`￼`).

- [ ] **Step 1: Write the failing test**

The fixture is generated once from any `.key` on the machine and committed, so the test is hermetic. If no `.key` is available the real-deck tests skip.

```python
import os
import pathlib
import zipfile
import pytest
from slides.readers.keynote_file import clean, read

REAL = pathlib.Path(os.path.expanduser(
    "~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote"
    "/09_oct14_tfidf_imbalance_eval.key"
))
needs_real = pytest.mark.skipif(not REAL.exists(), reason="no sample .key")


def test_clean_strips_object_replacement_characters():
    assert clean("before ￼ after") == "before after"
    assert clean("￼") == ""


def test_clean_normalises_whitespace_but_keeps_line_breaks():
    assert clean("a\n\n\nb") == "a\nb"
    assert clean("  padded  ") == "padded"
    assert clean("a b") == "a b"


@needs_real
def test_reads_slides_in_presentation_order():
    deck = read(REAL)
    assert deck.kind == "keynote"
    assert len(deck.slides) == 35
    assert (deck.width, deck.height) == (1920.0, 1080.0)
    assert [s.number for s in deck.slides] == list(range(1, 36))


@needs_real
def test_titles_and_notes_come_through():
    deck = read(REAL)
    assert any(s.title for s in deck.slides)
    assert any(s.notes.strip() for s in deck.slides)


@needs_real
def test_no_object_replacement_characters_survive():
    deck = read(REAL)
    for slide in deck.slides:
        assert "￼" not in (slide.title or "")
        assert "￼" not in slide.notes
        for item in slide.items:
            assert "￼" not in item.text


@needs_real
def test_collects_colour_candidates():
    deck = read(REAL)
    assert deck.colors
    assert all(c.hex.startswith("#") and len(c.hex) == 7 for c in deck.colors)


@needs_real
def test_reads_a_directory_bundle_identically(tmp_path):
    bundle = tmp_path / "bundle.key"
    bundle.mkdir()
    with zipfile.ZipFile(REAL) as archive:
        archive.extractall(bundle)
    assert len(read(bundle).slides) == len(read(REAL).slides)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reader_keynote_file.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.readers.keynote_file'`

- [ ] **Step 3: Write `src/slides/readers/keynote_file.py`**

```python
import re
import pathlib
import zipfile
import warnings
from slides.model import ColorUse, Deck, Slide, TextItem

STORAGE_KEYS = ("ownedStorage", "deprecatedStorage", "containedStorage")
TITLE_KIND = "kKindTitlePlaceholder"
WHITESPACE = re.compile(r"[   ]")
BLANK_LINES = re.compile(r"\n{2,}")


def read(path: str | pathlib.Path, via_deckwerk: bool = False) -> Deck:
    root = pathlib.Path(path)
    if via_deckwerk:
        from slides.deckwerk import importer
        return importer.read_via_import(root)
    index = archives(root)
    show = _first(index, "KN.ShowArchive")
    size = show.get("size", {})
    deck = Deck(
        title=root.stem,
        width=float(size.get("width", 1920.0)),
        height=float(size.get("height", 1080.0)),
        source=str(root),
        kind="keynote",
    )
    colors: dict[tuple[str, str], float] = {}
    order = show.get("slideTree", {}).get("slides", [])
    for number, node_ref in enumerate(order, start=1):
        node = index.get(node_ref["identifier"])
        if node is None:
            continue
        slide_id = node.get("slide", {}).get("identifier")
        raw = index.get(slide_id)
        if raw is None:
            continue
        deck.slides.append(_slide(number, raw, index, colors))
    deck.colors = [
        ColorUse(hex=key[0], weight=weight, kind=key[1])
        for key, weight in sorted(colors.items(), key=lambda kv: -kv[1])
    ]
    return deck


def archives(root: pathlib.Path) -> dict[str, dict]:
    warnings.simplefilter("ignore")
    from keynote_parser.codec import IWAFile
    index: dict[str, dict] = {}
    for name, data in _streams(root):
        parsed = IWAFile.from_buffer(data, name).to_dict()
        for chunk in parsed["chunks"]:
            for archive in chunk["archives"]:
                objects = archive.get("objects") or [{}]
                index[archive["header"]["identifier"]] = objects[0]
    return index


def _streams(root: pathlib.Path):
    # A .key is either a zip or a directory bundle; Keynote writes both.
    if root.is_dir():
        for path in sorted(root.glob("Index/*.iwa")):
            yield "Index/%s" % (path.name,), path.read_bytes()
        return
    with zipfile.ZipFile(root) as package:
        for name in package.namelist():
            if name.endswith(".iwa"):
                yield name, package.read(name)


def _first(index: dict[str, dict], pbtype: str) -> dict:
    for obj in index.values():
        if obj.get("_pbtype") == pbtype:
            return obj
    raise ValueError("no %s in this deck" % (pbtype,))


def _slide(number: int, raw: dict, index: dict, colors: dict) -> Slide:
    slide = Slide(number=number)
    title_id = raw.get("titlePlaceholder", {}).get("identifier")
    for ref in raw.get("drawablesZOrder", []):
        drawable_id = ref["identifier"]
        text = clean(_text_of(index.get(drawable_id), index))
        if not text:
            continue
        role = "title" if drawable_id == title_id else "body"
        slide.items.append(TextItem(text=text, role=role))
        if role == "title":
            slide.title = text
    if slide.title is None and slide.items:
        slide.title = slide.items[0].text
        slide.items[0].role = "title"
    note_id = raw.get("note", {}).get("identifier")
    slide.notes = clean(_text_of(index.get(note_id), index))
    _harvest_colors(raw, colors)
    return slide


def _text_of(drawable: dict | None, index: dict) -> str:
    if drawable is None:
        return ""
    storage = _storage_of(drawable, index)
    if storage is None:
        return ""
    return "".join(storage.get("text") or [])


def _storage_of(drawable: dict, index: dict) -> dict | None:
    for holder in (drawable, drawable.get("super") or {}):
        for key in STORAGE_KEYS:
            ref = holder.get(key)
            if isinstance(ref, dict) and "identifier" in ref:
                return index.get(ref["identifier"])
    return None


def _harvest_colors(node, colors: dict, weight: float = 1.0) -> None:
    if isinstance(node, dict):
        if {"red", "green", "blue"} <= set(node.keys()):
            value = "#%02x%02x%02x" % tuple(
                max(0, min(255, int(round(float(node[k]) * 255))))
                for k in ("red", "green", "blue")
            )
            colors[(value, "fill")] = colors.get((value, "fill"), 0.0) + weight
        for child in node.values():
            _harvest_colors(child, colors, weight)
    elif isinstance(node, list):
        for child in node:
            _harvest_colors(child, colors, weight)


def clean(text: str) -> str:
    # ￼ is the object-replacement character Keynote leaves where an image,
    # equation or other inline drawable sits inside a text run.
    text = text.replace("￼", "")
    text = WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return BLANK_LINES.sub("\n", text).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reader_keynote_file.py -v`
Expected: 7 passed

- [ ] **Step 5: Check the speed budget**

```bash
python -c "
import time
from slides import read_deck
t = time.time()
d = read_deck('$HOME/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/09_oct14_tfidf_imbalance_eval.key')
print('%d slides in %.2fs' % (len(d.slides), time.time() - t))
"
```
Expected: under 1.5s. If it is slower, the cause is parsing every `.iwa`; restrict `_streams` to `Index/Document.iwa` and `Index/Slide*.iwa`.

- [ ] **Step 6: Commit**

```bash
git add src/slides/readers/keynote_file.py tests/test_reader_keynote_file.py
git commit -m "feat: headless Keynote .key reader"
```

---

## Task 7: Live Keynote reader

**Files:**
- Create: `src/slides/keynote/__init__.py`, `src/slides/keynote/jxa.py`, `src/slides/readers/keynote_live.py`
- Test: `tests/test_jxa.py`, `tests/test_reader_keynote_live.py`

**Interfaces:**
- Consumes: `slides.model`.
- Produces:
  - `slides.keynote.jxa.run(script: str) -> str` — raises `KeynoteError` on failure
  - `slides.keynote.jxa.run_json(script: str) -> object`
  - `slides.keynote.jxa.KeynoteError(Exception)`
  - `slides.keynote.jxa.app_name() -> str`
  - `slides.readers.keynote_live.read() -> Deck`

Two details that matter. First, the user's existing `keydump.applescript` targets an application named **"Keynote Creator Studio"**, not "Keynote", so the app name must be overridable — `$SLIDES_KEYNOTE_APP`, defaulting to `"Keynote"`. Second, keydump's two-phase discipline is the whole performance story: one JXA call gathers everything into a JSON payload, and Python does all the string work. Do not make one Apple Events call per slide.

Covers **Review Focus 3**: Keynote not running, or no document open.

- [ ] **Step 1: Write the failing test**

```python
import os
import shutil
import pytest
from slides.keynote import jxa

has_osascript = pytest.mark.skipif(
    shutil.which("osascript") is None,
    reason="not a Mac",
)


def test_app_name_defaults_to_keynote(monkeypatch):
    monkeypatch.delenv("SLIDES_KEYNOTE_APP", raising=False)
    assert jxa.app_name() == "Keynote"


def test_app_name_honours_the_environment(monkeypatch):
    monkeypatch.setenv("SLIDES_KEYNOTE_APP", "Keynote Creator Studio")
    assert jxa.app_name() == "Keynote Creator Studio"


@has_osascript
def test_run_returns_stdout():
    assert jxa.run("'hello'").strip() == "hello"


@has_osascript
def test_run_json_parses():
    assert jxa.run_json("JSON.stringify({a: 1})") == {"a": 1}


@has_osascript
def test_failure_raises_a_readable_error():
    with pytest.raises(jxa.KeynoteError) as caught:
        jxa.run("throw new Error('boom')")
    assert "boom" in str(caught.value)
```

And `tests/test_reader_keynote_live.py`:

```python
import pytest
from slides.keynote import jxa
from slides.readers import keynote_live


def test_reports_when_no_document_is_open(monkeypatch):
    def explode(script: str):
        raise jxa.KeynoteError("Error: no document")

    monkeypatch.setattr(jxa, "run_json", explode)
    with pytest.raises(jxa.KeynoteError, match="no document"):
        keynote_live.read()


def test_builds_a_deck_from_the_payload(monkeypatch):
    payload = {
        "name": "Live talk",
        "width": 1920,
        "height": 1080,
        "slides": [
            {
                "title": "One",
                "items": ["One", "Body text"],
                "notes": "Say it.",
                "tables": [[["a", "b"], ["1", "2"]]],
            }
        ],
    }
    monkeypatch.setattr(jxa, "run_json", lambda script: payload)
    deck = keynote_live.read()
    assert deck.title == "Live talk"
    assert deck.kind == "live"
    assert deck.slides[0].title == "One"
    assert [i.text for i in deck.slides[0].body_items()] == ["Body text"]
    assert deck.slides[0].tables[0].rows[1] == ["1", "2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jxa.py tests/test_reader_keynote_live.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.keynote'`

- [ ] **Step 3: Write `src/slides/keynote/jxa.py`**

```python
import os
import json
import subprocess


class KeynoteError(Exception):
    pass


def app_name() -> str:
    return os.environ.get("SLIDES_KEYNOTE_APP", "Keynote")


def run(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise KeynoteError(result.stderr.strip() or "osascript failed")
    return result.stdout


def run_json(script: str) -> object:
    return json.loads(run(script))
```

- [ ] **Step 4: Write `src/slides/readers/keynote_live.py`**

The JXA gathers in one pass. `objectText` on every text item includes the title placeholder, which `body_items()` de-duplicates later.

```python
from slides.keynote import jxa
from slides.model import Deck, Slide, Table, TextItem

SCRIPT = """
var app = Application(%s);
if (app.documents.length === 0) { throw new Error("No presentation is open."); }
var doc = app.documents[0];
var out = {
  name: doc.name(),
  width: doc.width(),
  height: doc.height(),
  slides: []
};
var slides = doc.slides;
for (var i = 0; i < slides.length; i++) {
  var s = slides[i];
  var items = [];
  var texts = s.textItems;
  for (var j = 0; j < texts.length; j++) { items.push(texts[j].objectText()); }
  var tables = [];
  var tbs = s.tables;
  for (var t = 0; t < tbs.length; t++) {
    var rows = [];
    var rs = tbs[t].rows;
    for (var r = 0; r < rs.length; r++) {
      var cells = [];
      var cs = rs[r].cells;
      for (var c = 0; c < cs.length; c++) { cells.push(cs[c].value()); }
      rows.push(cells);
    }
    tables.push(rows);
  }
  out.slides.push({
    title: s.defaultTitleItem.objectText(),
    items: items,
    tables: tables,
    notes: s.presenterNotes()
  });
}
JSON.stringify(out);
"""


def read() -> Deck:
    payload = jxa.run_json(SCRIPT % (_quoted(jxa.app_name()),))
    deck = Deck(
        title=payload.get("name", "Untitled"),
        width=float(payload.get("width", 1920.0)),
        height=float(payload.get("height", 1080.0)),
        source="",
        kind="live",
    )
    for number, raw in enumerate(payload.get("slides", []), start=1):
        deck.slides.append(_slide(number, raw))
    return deck


def _slide(number: int, raw: dict) -> Slide:
    title = (raw.get("title") or "").strip() or None
    slide = Slide(
        number=number,
        title=title,
        notes=(raw.get("notes") or "").strip(),
    )
    for text in raw.get("items", []):
        cleaned = (text or "").strip()
        if cleaned:
            role = "title" if cleaned == title else "body"
            slide.items.append(TextItem(text=cleaned, role=role))
    for rows in raw.get("tables", []):
        slide.tables.append(Table(rows=[[str(c or "") for c in row] for row in rows]))
    return slide


def _quoted(name: str) -> str:
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % (escaped,)
```

Write `src/slides/keynote/__init__.py` as an empty file.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_jxa.py tests/test_reader_keynote_live.py -v`
Expected: 7 passed

- [ ] **Step 6: Verify against the real app**

Open any presentation in Keynote, then:
```bash
slides dump | head -20
```
Expected: Markdown for the open deck. With Keynote closed, expect a one-line `No presentation is open.` on stderr — not a traceback.

- [ ] **Step 7: Commit**

```bash
git add src/slides/keynote src/slides/readers/keynote_live.py tests/test_jxa.py tests/test_reader_keynote_live.py
git commit -m "feat: live Keynote reader over Apple Events"
```

---

## Task 8: `.pptx` reader

**Files:**
- Create: `src/slides/readers/pptx.py`, `tests/fixtures/make_fixtures.py`
- Test: `tests/test_reader_pptx.py`

**Interfaces:**
- Consumes: `slides.model`.
- Produces: `slides.readers.pptx.read(path) -> Deck`.

- [ ] **Step 1: Write the fixture generator `tests/fixtures/make_fixtures.py`**

A committed generator plus a committed `.pptx`, so the test needs no network and no real project content.

```python
import pathlib
import pptx
from pptx.util import Inches, Pt


def main():
    here = pathlib.Path(__file__).parent
    build_pptx(here / "mini.pptx")
    print("wrote %s" % (here / "mini.pptx",))


def build_pptx(path: pathlib.Path) -> None:
    deck = pptx.Presentation()
    layout = deck.slide_layouts[1]
    first = deck.slides.add_slide(layout)
    first.shapes.title.text = "Opening"
    first.placeholders[1].text = "First point\nSecond point"
    first.notes_slide.notes_text_frame.text = "Say hello."
    second = deck.slides.add_slide(deck.slide_layouts[5])
    second.shapes.title.text = "Numbers"
    table = second.shapes.add_table(
        2,
        2,
        Inches(1),
        Inches(2),
        Inches(4),
        Inches(1),
    ).table
    table.cell(0, 0).text = "Model"
    table.cell(0, 1).text = "MSE"
    table.cell(1, 0).text = "Linear"
    table.cell(1, 1).text = "3.2"
    deck.save(path)


if __name__ == "__main__":
    main()
```

Run it once and commit `tests/fixtures/mini.pptx`.

- [ ] **Step 2: Write the failing test**

```python
import pathlib
from slides.readers.pptx import read

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini.pptx"


def test_reads_titles_body_notes_and_tables():
    deck = read(FIXTURE)
    assert deck.kind == "pptx"
    assert len(deck.slides) == 2
    assert deck.slides[0].title == "Opening"
    assert [i.text for i in deck.slides[0].body_items()] == ["First point\nSecond point"]
    assert deck.slides[0].notes == "Say hello."
    assert deck.slides[1].tables[0].rows == [["Model", "MSE"], ["Linear", "3.2"]]


def test_canvas_comes_from_the_presentation():
    deck = read(FIXTURE)
    assert deck.width > 0 and deck.height > 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_reader_pptx.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.readers.pptx'`

- [ ] **Step 4: Write `src/slides/readers/pptx.py`**

```python
import pathlib
from slides.model import Deck, Image, Slide, Table, TextItem

EMU_PER_POINT = 12700


def read(path: str | pathlib.Path) -> Deck:
    import pptx
    root = pathlib.Path(path)
    presentation = pptx.Presentation(str(root))
    deck = Deck(
        title=root.stem,
        width=presentation.slide_width / EMU_PER_POINT,
        height=presentation.slide_height / EMU_PER_POINT,
        source=str(root),
        kind="pptx",
    )
    for number, raw in enumerate(presentation.slides, start=1):
        deck.slides.append(_slide(number, raw))
    return deck


def _slide(number: int, raw) -> Slide:
    slide = Slide(number=number)
    title_shape = raw.shapes.title
    if title_shape is not None and title_shape.has_text_frame:
        slide.title = title_shape.text_frame.text.strip() or None
    for shape in raw.shapes:
        if shape.has_text_frame:
            text = shape.text_frame.text.strip()
            if text:
                role = "title" if text == slide.title else "body"
                slide.items.append(TextItem(
                    text=text,
                    role=role,
                    x=_points(shape.left),
                    y=_points(shape.top),
                    w=_points(shape.width),
                    h=_points(shape.height),
                ))
        if shape.has_table:
            slide.tables.append(Table(rows=[
                [cell.text.strip() for cell in row.cells]
                for row in shape.table.rows
            ]))
        if shape.shape_type == 13:
            slide.images.append(Image(
                path=getattr(shape.image, "filename", None),
                x=_points(shape.left),
                y=_points(shape.top),
                w=_points(shape.width),
                h=_points(shape.height),
            ))
    if raw.has_notes_slide:
        slide.notes = raw.notes_slide.notes_text_frame.text.strip()
    return slide


def _points(value) -> float | None:
    if value is None:
        return None
    return value / EMU_PER_POINT
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_reader_pptx.py tests/test_cli.py -v`
Expected: 5 passed, lazy-import test still green

- [ ] **Step 6: Commit**

```bash
git add src/slides/readers/pptx.py tests/fixtures/make_fixtures.py tests/fixtures/mini.pptx tests/test_reader_pptx.py
git commit -m "feat: pptx reader"
```

---

## Task 9: `slides info`

**Files:**
- Create: `src/slides/commands/info.py`
- Modify: `src/slides/cli.py`
- Test: `tests/test_info.py`

**Interfaces:**
- Consumes: `slides.readers.read`, `slides.readers.detect`.
- Produces: `slides.commands.info.run(args) -> int`, `slides.commands.info.summarise(deck) -> str`.

Per the spec, `info` reports what the target can supply: inventory everywhere, plus the importer's `--report` for a `.key` and `slide-agent validate` for a DeckWerk folder. Those two extras arrive in Task 13; this task builds the inventory and leaves the hooks behind a capability check so no placeholder text ships.

- [ ] **Step 1: Write the failing test**

```python
import pathlib
import argparse
from slides.commands import info
from slides.readers import read

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def test_summarises_the_inventory():
    out = info.summarise(read(FIXTURE))
    assert "Mini" in out
    assert "2 slides" in out
    assert "1920" in out and "1080" in out


def test_counts_text_tables_images_and_notes():
    out = info.summarise(read(FIXTURE))
    assert "1 table" in out
    assert "1 image" in out
    assert "1 slide with notes" in out


def test_run_prints_and_succeeds(capsys):
    args = argparse.Namespace(target=str(FIXTURE), deckwerk_root=None)
    assert info.run(args) == 0
    assert "Mini" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_info.py -v`
Expected: FAIL with `ImportError: cannot import name 'info'`

- [ ] **Step 3: Write `src/slides/commands/info.py`**

```python
import sys
import argparse
from slides import readers
from slides.model import Deck


def run(args: argparse.Namespace) -> int:
    deck = readers.read(args.target)
    sys.stdout.write(summarise(deck) + "\n")
    return 0


def summarise(deck: Deck) -> str:
    tables = sum(len(s.tables) for s in deck.slides)
    images = sum(len(s.images) for s in deck.slides)
    noted = sum(1 for s in deck.slides if s.notes.strip())
    words = sum(
        len(i.text.split())
        for s in deck.slides
        for i in s.body_items()
    )
    lines = [
        "%s  (%s)" % (deck.title, deck.kind),
        "%d slides, %.0f x %.0f" % (len(deck.slides), deck.width, deck.height),
        "%s, %s, %s" % (
            _plural(tables, "table"),
            _plural(images, "image"),
            _plural(noted, "slide with notes", "slides with notes"),
        ),
        "%d words of body text" % (words,),
    ]
    if deck.fonts:
        lines.append("fonts: %s" % (", ".join(sorted(set(deck.fonts.values()))),))
    if deck.colors:
        top = ", ".join(c.hex for c in deck.colors[:6])
        lines.append("colours: %s" % (top,))
    return "\n".join(lines)


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return "1 %s" % (singular,)
    return "%d %s" % (count, plural or (singular + "s"))
```

- [ ] **Step 4: Wire into `src/slides/cli.py`**

```python
def _info(args: argparse.Namespace) -> int:
    from slides.commands import info
    return info.run(args)
```

and set `"info": _info` in `DISPATCH`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_info.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/slides/commands/info.py src/slides/cli.py tests/test_info.py
git commit -m "feat: slides info"
```

---

## Task 10: Colour science

**Files:**
- Create: `src/slides/color.py`
- Test: `tests/test_color.py`

**Interfaces:**
- Consumes: nothing.
- Produces, all in `slides.color`:
  - `to_rgb(hex: str) -> tuple[float, float, float]` (0..1)
  - `to_hex(r: float, g: float, b: float) -> str`
  - `to_oklab(hex: str) -> tuple[float, float, float]`
  - `from_oklab(L: float, a: float, b: float) -> str`
  - `to_oklch(hex: str) -> tuple[float, float, float]` — L, C, H in degrees
  - `from_oklch(L: float, C: float, H: float) -> str`
  - `luminance(hex: str) -> float` — WCAG relative luminance
  - `contrast(one: str, other: str) -> float` — WCAG ratio, 1.0..21.0
  - `delta_e(one: str, other: str) -> float` — Euclidean distance in OKLab
  - `mix(one: str, other: str, amount: float) -> str` — OKLab interpolation
  - `with_contrast(colour: str, against: str, ratio: float) -> str` — adjust L in OKLCH, holding hue and chroma, until the ratio is met

Pure Python, no numpy. OKLab is Björn Ottosson's matrix formulation.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from slides import color


def test_hex_round_trips():
    assert color.to_hex(*color.to_rgb("#a5d75f")) == "#a5d75f"


def test_oklab_round_trips():
    for value in ("#000000", "#ffffff", "#a5d75f", "#0d1e1c", "#980c0c"):
        assert color.from_oklab(*color.to_oklab(value)) == value


def test_oklch_round_trips():
    for value in ("#a5d75f", "#0d1e1c", "#5ce1e6"):
        assert color.from_oklch(*color.to_oklch(value)) == value


def test_luminance_endpoints():
    assert color.luminance("#000000") == pytest.approx(0.0, abs=1e-6)
    assert color.luminance("#ffffff") == pytest.approx(1.0, abs=1e-6)


def test_contrast_is_symmetric_and_bounded():
    assert color.contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert color.contrast("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)
    assert color.contrast("#a5d75f", "#a5d75f") == pytest.approx(1.0, abs=1e-6)


def test_delta_e_orders_by_perceptual_distance():
    near = color.delta_e("#00a2ff", "#0093e8")
    far = color.delta_e("#00a2ff", "#a5d75f")
    assert near < far
    assert near < 0.08


def test_mix_endpoints_and_midpoint():
    assert color.mix("#000000", "#ffffff", 0.0) == "#000000"
    assert color.mix("#000000", "#ffffff", 1.0) == "#ffffff"
    middle = color.mix("#000000", "#ffffff", 0.5)
    assert 0.1 < color.luminance(middle) < 0.4


def test_with_contrast_lightens_against_a_dark_ground():
    fixed = color.with_contrast("#1a3330", "#0d1e1c", 4.5)
    assert color.contrast(fixed, "#0d1e1c") >= 4.5


def test_with_contrast_darkens_against_a_light_ground():
    fixed = color.with_contrast("#eeeeee", "#ffffff", 4.5)
    assert color.contrast(fixed, "#ffffff") >= 4.5


def test_with_contrast_holds_hue():
    before = color.to_oklch("#00a2ff")[2]
    after = color.to_oklch(color.with_contrast("#00a2ff", "#ffffff", 4.5))[2]
    assert abs(before - after) < 2.0


def test_with_contrast_is_a_no_op_when_already_sufficient():
    assert color.with_contrast("#ffffff", "#000000", 4.5) == "#ffffff"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_color.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.color'`

- [ ] **Step 3: Write `src/slides/color.py`**

```python
import math

LUMA = (0.2126, 0.7152, 0.0722)


def to_rgb(value: str) -> tuple[float, float, float]:
    text = value.lstrip("#")
    return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def to_hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, int(round(c * 255.0)))) for c in (r, g, b)
    )


def to_oklab(value: str) -> tuple[float, float, float]:
    r, g, b = (_linear(c) for c in to_rgb(value))
    l = _cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = _cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = _cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def from_oklab(L: float, a: float, b: float) -> str:
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return to_hex(
        _srgb(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
        _srgb(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
        _srgb(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s),
    )


def to_oklch(value: str) -> tuple[float, float, float]:
    L, a, b = to_oklab(value)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360.0


def from_oklch(L: float, C: float, H: float) -> str:
    radians = math.radians(H)
    return from_oklab(L, C * math.cos(radians), C * math.sin(radians))


def luminance(value: str) -> float:
    return sum(k * _linear(c) for k, c in zip(LUMA, to_rgb(value)))


def contrast(one: str, other: str) -> float:
    a, b = luminance(one), luminance(other)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def delta_e(one: str, other: str) -> float:
    first, second = to_oklab(one), to_oklab(other)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(first, second)))


def mix(one: str, other: str, amount: float) -> str:
    first, second = to_oklab(one), to_oklab(other)
    return from_oklab(*[x + (y - x) * amount for x, y in zip(first, second)])


def with_contrast(colour: str, against: str, ratio: float) -> str:
    if contrast(colour, against) >= ratio:
        return colour
    L, C, H = to_oklch(colour)
    target = 1.0 if luminance(against) < 0.5 else 0.0
    low, high = L, target
    best = from_oklch(target, C, H)
    # Binary search on lightness: contrast is monotone as L moves away from
    # the ground, so 24 halvings land within a rounding step of the boundary.
    for _ in range(24):
        middle = (low + high) / 2.0
        candidate = from_oklch(middle, C, H)
        if contrast(candidate, against) >= ratio:
            best = candidate
            high = middle
        else:
            low = middle
    return best


def _linear(c: float) -> float:
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _srgb(c: float) -> float:
    c = max(0.0, min(1.0, c))
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1 / 2.4)) - 0.055


def _cbrt(x: float) -> float:
    return math.copysign(abs(x) ** (1 / 3), x)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_color.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/slides/color.py tests/test_color.py
git commit -m "feat: OKLab colour science"
```

---

## Task 11: Palette extraction and role inference

**Files:**
- Create: `src/slides/theme.py`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: `slides.color`, `slides.model.Deck/ColorUse`.
- Produces:
  - `slides.theme.DeckTheme(background, foreground, muted, grid, accents, fonts, source)` with `to_dict() -> dict`
  - `slides.theme.extract(deck: Deck, accents: int = 6) -> DeckTheme`

**Why this cannot be frequency counting.** Counting colours in a real `.key` returns `#000000` (606 hits), `#ffffff` (394), `#f9f9f9` (324), `#fefffe` (54), `#888888` (30), and only then `#a5d75f` (27) — the deck's actual accent. Keynote's stock stylesheet swamps the deck's own colours. So: gather with usage weights and a role hint, then infer perceptually.

Inference order, each step using what the previous one fixed:

1. **background** — the explicit slide background when the reader supplied one (DeckWerk always does), taking the value covering the most slides. Otherwise the heaviest near-neutral candidate (OKLCH chroma < 0.04). Otherwise the heaviest candidate outright. **Always returns a hex**, which is Review Focus 4: an image or gradient background leaves `slide.background` empty and must still yield something every emitter can format.
2. **foreground** — among text-role candidates clearing 4.5:1 against the background, the heaviest; ties broken by contrast. If nothing clears 4.5:1, the highest-contrast candidate, raised to 4.5:1 with `with_contrast`.
3. **muted** — candidates between 2:1 and the foreground's contrast, nearest the foreground in hue. Failing that, the foreground mixed 55% toward the background.
4. **grid** — the heaviest candidate between 1.1:1 and 2:1. Failing that, the foreground mixed 85% toward the background.
5. **accents** — chromatic candidates (chroma ≥ 0.05) clearing 3:1, collapsed by ΔE < 0.06 so a preset gradient family becomes one entry, then chosen greedily for hue spread rather than by weight alone, then clamped to 3:1. When the deck yields fewer than asked, the remainder are derived by rotating the deck's own accent hues — never from a shipped palette.

- [ ] **Step 1: Write the failing test**

```python
from slides import color
from slides.model import ColorUse, Deck, Slide
from slides.theme import DeckTheme, extract


def a_deck(colors: list[ColorUse], background: str | None = "#0d1e1c") -> Deck:
    return Deck(
        title="T",
        slides=[Slide(number=1, background=background)],
        colors=colors,
        fonts={"title": "Libre Franklin", "body": "Libre Franklin"},
    )


def test_background_comes_from_the_slides_when_known():
    deck = a_deck([ColorUse("#ffffff", 900.0, "stylesheet")])
    assert extract(deck).background == "#0d1e1c"


def test_stock_stylesheet_does_not_beat_the_real_accent():
    # The exact frequencies measured in a real .key.
    deck = a_deck([
        ColorUse("#000000", 606.0, "stylesheet"),
        ColorUse("#ffffff", 394.0, "stylesheet"),
        ColorUse("#f9f9f9", 324.0, "stylesheet"),
        ColorUse("#888888", 30.0, "stylesheet"),
        ColorUse("#a5d75f", 27.0, "text"),
    ])
    theme = extract(deck)
    assert theme.background == "#0d1e1c"
    assert "#a5d75f" in theme.accents


def test_foreground_clears_the_contrast_floor():
    deck = a_deck([
        ColorUse("#edf4f1", 40.0, "text"),
        ColorUse("#152e2a", 80.0, "text"),
    ])
    theme = extract(deck)
    assert color.contrast(theme.foreground, theme.background) >= 4.5


def test_background_falls_back_when_slides_have_no_solid_fill():
    deck = a_deck(
        [ColorUse("#101010", 50.0, "fill"), ColorUse("#a5d75f", 10.0, "text")],
        background=None,
    )
    theme = extract(deck)
    assert theme.background == "#101010"
    assert theme.foreground


def test_background_falls_back_again_when_nothing_is_neutral():
    deck = a_deck([ColorUse("#a5d75f", 10.0, "fill")], background=None)
    assert extract(deck).background == "#a5d75f"


def test_near_duplicate_accents_collapse():
    deck = a_deck([
        ColorUse("#00a2ff", 24.0, "fill"),
        ColorUse("#0093e8", 24.0, "fill"),
        ColorUse("#0085d1", 24.0, "fill"),
        ColorUse("#1fa3ff", 24.0, "fill"),
        ColorUse("#a5d75f", 20.0, "fill"),
    ])
    accents = extract(deck, accents=4).accents
    blues = [a for a in accents if abs(color.to_oklch(a)[2] - 250.0) < 40.0]
    assert len(blues) == 1


def test_accents_clear_their_contrast_floor():
    deck = a_deck([ColorUse("#123c36", 30.0, "fill")])
    for accent in extract(deck).accents:
        assert color.contrast(accent, "#0d1e1c") >= 3.0


def test_accents_are_padded_to_the_requested_count():
    deck = a_deck([ColorUse("#a5d75f", 20.0, "fill")])
    accents = extract(deck, accents=5).accents
    assert len(accents) == 5
    assert len(set(accents)) == 5


def test_muted_sits_between_grid_and_foreground():
    deck = a_deck([ColorUse("#edf4f1", 40.0, "text")])
    theme = extract(deck)
    ground = theme.background
    assert (color.contrast(theme.grid, ground)
            <= color.contrast(theme.muted, ground)
            <= color.contrast(theme.foreground, ground))


def test_fonts_carry_through_and_to_dict_is_complete():
    theme = extract(a_deck([ColorUse("#edf4f1", 10.0, "text")]))
    assert theme.fonts["body"] == "Libre Franklin"
    keys = set(theme.to_dict())
    assert keys == {
        "background", "foreground", "muted", "grid", "accents", "fonts", "source",
    }


def test_a_deck_with_no_colours_still_yields_a_theme():
    theme = extract(Deck(title="Bare"))
    assert isinstance(theme, DeckTheme)
    assert theme.background and theme.foreground
    assert color.contrast(theme.foreground, theme.background) >= 4.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_theme.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.theme'`

- [ ] **Step 3: Write `src/slides/theme.py`**

```python
import collections
from dataclasses import dataclass, field
from slides import color
from slides.model import ColorUse, Deck

NEUTRAL_CHROMA = 0.04
ACCENT_CHROMA = 0.05
ACCENT_CONTRAST = 3.0
TEXT_CONTRAST = 4.5
DUPLICATE = 0.06


@dataclass
class DeckTheme:
    background: str
    foreground: str
    muted: str
    grid: str
    accents: list[str] = field(default_factory=list)
    fonts: dict[str, str] = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "background": self.background,
            "foreground": self.foreground,
            "muted": self.muted,
            "grid": self.grid,
            "accents": list(self.accents),
            "fonts": dict(self.fonts),
            "source": self.source,
        }


def extract(deck: Deck, accents: int = 6) -> DeckTheme:
    candidates = list(deck.colors)
    background = _background(deck, candidates)
    foreground = _foreground(candidates, background)
    return DeckTheme(
        background=background,
        foreground=foreground,
        muted=_muted(candidates, background, foreground),
        grid=_grid(candidates, background, foreground),
        accents=_accents(candidates, background, accents),
        fonts=dict(deck.fonts),
        source=deck.source,
    )


def _background(deck: Deck, candidates: list[ColorUse]) -> str:
    explicit = [s.background for s in deck.slides if s.background]
    if explicit:
        return collections.Counter(explicit).most_common(1)[0][0]
    neutral = [c for c in candidates if color.to_oklch(c.hex)[1] < NEUTRAL_CHROMA]
    pool = neutral or candidates
    if not pool:
        return "#ffffff"
    return max(pool, key=lambda c: c.weight).hex


def _foreground(candidates: list[ColorUse], background: str) -> str:
    text = [c for c in candidates if c.kind == "text"] or candidates
    if not text:
        return color.with_contrast(
            "#ffffff" if color.luminance(background) < 0.5 else "#000000",
            background,
            TEXT_CONTRAST,
        )
    clearing = [c for c in text if color.contrast(c.hex, background) >= TEXT_CONTRAST]
    if clearing:
        return max(
            clearing,
            key=lambda c: (c.weight, color.contrast(c.hex, background)),
        ).hex
    best = max(text, key=lambda c: color.contrast(c.hex, background))
    return color.with_contrast(best.hex, background, TEXT_CONTRAST)


def _muted(candidates: list[ColorUse], background: str, foreground: str) -> str:
    ceiling = color.contrast(foreground, background)
    band = [
        c for c in candidates
        if 2.0 <= color.contrast(c.hex, background) < ceiling
    ]
    if not band:
        return color.mix(foreground, background, 0.55)
    target_hue = color.to_oklch(foreground)[2]
    return min(band, key=lambda c: _hue_gap(color.to_oklch(c.hex)[2], target_hue)).hex


def _grid(candidates: list[ColorUse], background: str, foreground: str) -> str:
    band = [c for c in candidates if 1.1 <= color.contrast(c.hex, background) < 2.0]
    if not band:
        return color.mix(foreground, background, 0.85)
    return max(band, key=lambda c: c.weight).hex


def _accents(candidates: list[ColorUse], background: str, count: int) -> list[str]:
    chromatic = [c for c in candidates if color.to_oklch(c.hex)[1] >= ACCENT_CHROMA]
    chromatic.sort(key=lambda c: -c.weight)
    kept: list[str] = []
    for candidate in chromatic:
        raised = color.with_contrast(candidate.hex, background, ACCENT_CONTRAST)
        if all(color.delta_e(raised, other) >= DUPLICATE for other in kept):
            kept.append(raised)
    spread = _spread(kept, count)
    return _pad(spread, background, count)


def _spread(accents: list[str], count: int) -> list[str]:
    if len(accents) <= count:
        return accents
    chosen = [accents[0]]
    remaining = accents[1:]
    while len(chosen) < count and remaining:
        pick = max(
            remaining,
            key=lambda c: min(
                _hue_gap(color.to_oklch(c)[2], color.to_oklch(p)[2]) for p in chosen
            ),
        )
        chosen.append(pick)
        remaining.remove(pick)
    return chosen


def _pad(accents: list[str], background: str, count: int) -> list[str]:
    # Derive the shortfall by rotating the deck's own hues, never from a
    # palette shipped with the tool.
    if not accents:
        seed = color.with_contrast(
            color.from_oklch(0.75, 0.15, 150.0), background, ACCENT_CONTRAST
        )
        accents = [seed]
    out = list(accents)
    step = 360.0 / max(count, 1)
    index = 0
    while len(out) < count:
        L, C, H = color.to_oklch(accents[index % len(accents)])
        rotated = color.with_contrast(
            color.from_oklch(L, C, (H + step * (index // len(accents) + 1)) % 360.0),
            background,
            ACCENT_CONTRAST,
        )
        if all(color.delta_e(rotated, other) >= DUPLICATE for other in out):
            out.append(rotated)
        index += 1
        if index > count * 12:
            break
    return out[:count]


def _hue_gap(one: float, other: float) -> float:
    gap = abs(one - other) % 360.0
    return min(gap, 360.0 - gap)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_theme.py -v`
Expected: 11 passed

- [ ] **Step 5: Sanity-check against a real deck**

```bash
python -c "
from slides import read_deck
from slides.theme import extract
t = extract(read_deck('$HOME/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/04_sep28_conditional_linear'))
print(t.background, t.foreground, t.muted, t.grid)
print(t.accents)
"
```
Expected: a dark background, a light foreground, and accents that look like the deck rather than like Keynote's stock swatches.

- [ ] **Step 6: Commit**

```bash
git add src/slides/theme.py tests/test_theme.py
git commit -m "feat: perceptual palette extraction and role inference"
```

---

## Task 12: Theme emitters and `slides theme`

**Files:**
- Create: `src/slides/emit/__init__.py`, `src/slides/emit/matplotlib.py`, `src/slides/emit/ggplot.py`, `src/slides/emit/css.py`, `src/slides/commands/theme.py`
- Modify: `src/slides/cli.py`
- Test: `tests/test_emit.py`

**Interfaces:**
- Consumes: `slides.theme.DeckTheme`, `slides.color`.
- Produces:
  - `slides.emit.matplotlib.rc_params(theme) -> dict`
  - `slides.emit.matplotlib.deck_style(theme)` — a context manager
  - `slides.emit.ggplot.render(theme) -> str` — R source
  - `slides.emit.css.render(theme) -> str`
  - `slides.emit.render(theme, fmt) -> str` for `"json" | "matplotlib" | "ggplot" | "css"`
  - `slides.commands.theme.run(args) -> int`

`matplotlib` stays out of `rc_params`, which returns a plain dict — only `deck_style` imports it, so `slides theme -f matplotlib` works without the extra installed. The ggplot emitter follows the user's R preferences: tidyverse idiom, `%>%` where a pipe is natural, one argument per line.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from slides.emit import css, ggplot, render
from slides.emit import matplotlib as mpl
from slides.theme import DeckTheme


def a_theme() -> DeckTheme:
    return DeckTheme(
        background="#0d1e1c",
        foreground="#edf4f1",
        muted="#93a69f",
        grid="#2c403b",
        accents=["#a5d75f", "#5ce1e6", "#ff6b6b"],
        fonts={"title": "Libre Franklin", "body": "Libre Franklin"},
        source="talk/",
    )


def test_rc_params_carry_the_roles():
    params = mpl.rc_params(a_theme())
    assert params["figure.facecolor"] == "#0d1e1c"
    assert params["text.color"] == "#edf4f1"
    assert params["grid.color"] == "#2c403b"
    assert params["xtick.color"] == "#93a69f"
    assert params["font.sans-serif"][0] == "Libre Franklin"


def test_rc_params_cycle_uses_the_accents():
    params = mpl.rc_params(a_theme())
    assert "#a5d75f" in str(params["axes.prop_cycle"])


def test_rc_params_needs_no_matplotlib(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    assert mpl.rc_params(a_theme())["figure.facecolor"] == "#0d1e1c"


def test_ggplot_emits_sourceable_r():
    out = ggplot.render(a_theme())
    assert "theme_deck <- function(" in out
    assert "scale_colour_deck <- function(" in out
    assert "scale_fill_deck <- function(" in out
    assert '"#a5d75f"' in out
    assert "#0d1e1c" in out
    assert "'" not in out.replace("don't", "")


def test_ggplot_defines_the_palette_once():
    out = ggplot.render(a_theme())
    assert out.count("deck_palette <- ") == 1


def test_css_emits_custom_properties():
    out = css.render(a_theme())
    assert "--deck-background: #0d1e1c;" in out
    assert "--deck-accent-1: #a5d75f;" in out
    assert ":root {" in out


def test_render_dispatches():
    theme = a_theme()
    assert render(theme, "css") == css.render(theme)
    assert render(theme, "ggplot") == ggplot.render(theme)
    assert "\"background\": \"#0d1e1c\"" in render(theme, "json")
    assert "figure.facecolor" in render(theme, "matplotlib")


def test_deck_style_restores_previous_settings():
    matplotlib = pytest.importorskip("matplotlib", reason="figures extra not installed")
    before = matplotlib.rcParams["figure.facecolor"]
    with mpl.deck_style(a_theme()):
        assert matplotlib.rcParams["figure.facecolor"] == "#0d1e1c"
    assert matplotlib.rcParams["figure.facecolor"] == before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_emit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.emit'`

- [ ] **Step 3: Write `src/slides/emit/matplotlib.py`**

```python
import contextlib
from slides.theme import DeckTheme


def rc_params(theme: DeckTheme) -> dict:
    family = theme.fonts.get("body") or theme.fonts.get("title") or "DejaVu Sans"
    cycle = "cycler('color', %r)" % (list(theme.accents),)
    return {
        "figure.facecolor": theme.background,
        "figure.edgecolor": theme.background,
        "savefig.facecolor": theme.background,
        "savefig.edgecolor": theme.background,
        "axes.facecolor": theme.background,
        "axes.edgecolor": theme.grid,
        "axes.labelcolor": theme.foreground,
        "axes.titlecolor": theme.foreground,
        "axes.grid": True,
        "axes.prop_cycle": cycle,
        "grid.color": theme.grid,
        "grid.linewidth": 0.8,
        "text.color": theme.foreground,
        "xtick.color": theme.muted,
        "ytick.color": theme.muted,
        "legend.facecolor": theme.background,
        "legend.edgecolor": theme.grid,
        "legend.labelcolor": theme.foreground,
        "font.family": "sans-serif",
        "font.sans-serif": [family, "DejaVu Sans"],
    }


@contextlib.contextmanager
def deck_style(theme: DeckTheme):
    import matplotlib
    from cycler import cycler
    params = rc_params(theme)
    params["axes.prop_cycle"] = cycler("color", list(theme.accents))
    with matplotlib.rc_context(params):
        yield
```

- [ ] **Step 4: Write `src/slides/emit/ggplot.py`**

```python
from slides.theme import DeckTheme

TEMPLATE = """# Generated by `slides theme -f ggplot` from %(source)s
library(ggplot2)

deck_palette <- c(%(palette)s)

deck_colours <- list(
    background = "%(background)s",
    foreground = "%(foreground)s",
    muted = "%(muted)s",
    grid = "%(grid)s"
)

theme_deck <- function(
    base_size = 12,
    base_family = "%(family)s"
) {
    theme_minimal(
        base_size = base_size,
        base_family = base_family
    ) +
        theme(
            plot.background = element_rect(fill = "%(background)s", colour = NA),
            panel.background = element_rect(fill = "%(background)s", colour = NA),
            panel.grid.major = element_line(colour = "%(grid)s", linewidth = 0.3),
            panel.grid.minor = element_blank(),
            axis.text = element_text(colour = "%(muted)s"),
            axis.title = element_text(colour = "%(foreground)s"),
            plot.title = element_text(colour = "%(foreground)s"),
            plot.subtitle = element_text(colour = "%(muted)s"),
            legend.background = element_rect(fill = "%(background)s", colour = NA),
            legend.key = element_rect(fill = "%(background)s", colour = NA),
            legend.text = element_text(colour = "%(foreground)s"),
            legend.title = element_text(colour = "%(foreground)s"),
            strip.text = element_text(colour = "%(foreground)s")
        )
}

scale_colour_deck <- function(...) {
    discrete_scale(
        aesthetics = "colour",
        palette = function(n) deck_palette[seq_len(n)],
        ...
    )
}

scale_color_deck <- scale_colour_deck

scale_fill_deck <- function(...) {
    discrete_scale(
        aesthetics = "fill",
        palette = function(n) deck_palette[seq_len(n)],
        ...
    )
}
"""


def render(theme: DeckTheme) -> str:
    return TEMPLATE % {
        "source": theme.source or "a deck",
        "palette": ", ".join('"%s"' % (a,) for a in theme.accents),
        "background": theme.background,
        "foreground": theme.foreground,
        "muted": theme.muted,
        "grid": theme.grid,
        "family": theme.fonts.get("body") or theme.fonts.get("title") or "sans",
    }
```

- [ ] **Step 5: Write `src/slides/emit/css.py`**

```python
from slides.theme import DeckTheme


def render(theme: DeckTheme) -> str:
    lines = [
        ":root {",
        "  --deck-background: %s;" % (theme.background,),
        "  --deck-foreground: %s;" % (theme.foreground,),
        "  --deck-muted: %s;" % (theme.muted,),
        "  --deck-grid: %s;" % (theme.grid,),
    ]
    for number, accent in enumerate(theme.accents, start=1):
        lines.append("  --deck-accent-%d: %s;" % (number, accent))
    for role, family in sorted(theme.fonts.items()):
        lines.append("  --deck-font-%s: %s;" % (role, family))
    lines.append("}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 6: Write `src/slides/emit/__init__.py`**

```python
import json
from slides.emit import css, ggplot
from slides.emit import matplotlib as matplotlib_emit
from slides.theme import DeckTheme


def render(theme: DeckTheme, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(theme.to_dict(), indent=2) + "\n"
    if fmt == "css":
        return css.render(theme)
    if fmt == "ggplot":
        return ggplot.render(theme)
    params = matplotlib_emit.rc_params(theme)
    body = ",\n".join("    %r: %s" % (k, _value(v)) for k, v in params.items())
    return "rc_params = {\n%s,\n}\n" % (body,)


def _value(value) -> str:
    if isinstance(value, str) and value.startswith("cycler("):
        return value
    return repr(value)
```

- [ ] **Step 7: Write `src/slides/commands/theme.py` and wire the CLI**

```python
import sys
import argparse
from slides import emit, readers
from slides.theme import extract


def run(args: argparse.Namespace) -> int:
    deck = readers.read(args.target)
    sys.stdout.write(emit.render(extract(deck, accents=args.accents), args.format))
    return 0
```

In `cli.py`:

```python
def _theme(args: argparse.Namespace) -> int:
    from slides.commands import theme
    return theme.run(args)
```

and set `"theme": _theme` in `DISPATCH`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_emit.py tests/test_cli.py -v`
Expected: 9 passed (one skipped without the `figures` extra)

- [ ] **Step 9: Verify the R output actually parses**

```bash
slides theme tests/fixtures/mini_deckwerk -f ggplot > /tmp/deck_theme.R
Rscript -e 'source("/tmp/deck_theme.R"); print(deck_palette); print(class(theme_deck()))'
```
Expected: the palette vector and `"theme" "gg"`. Skip this step if R is not installed.

- [ ] **Step 10: Commit**

```bash
git add src/slides/emit src/slides/commands/theme.py src/slides/cli.py tests/test_emit.py
git commit -m "feat: matplotlib, ggplot, CSS and JSON theme emitters"
```

---

## Task 13: DeckWerk importer wrapper and `convert -f deckwerk`

**Files:**
- Create: `src/slides/deckwerk/__init__.py`, `src/slides/deckwerk/importer.py`, `src/slides/deckwerk/agent.py`, `src/slides/commands/convert.py`
- Modify: `src/slides/cli.py`, `src/slides/commands/info.py`
- Test: `tests/test_deckwerk_importer.py`

**Interfaces:**
- Consumes: `slides.readers.deckwerk.read`.
- Produces:
  - `slides.deckwerk.importer.find_root(explicit: str | None = None) -> pathlib.Path`
  - `slides.deckwerk.importer.interpreter(root: pathlib.Path) -> str`
  - `slides.deckwerk.importer.import_key(key, out, root=None) -> dict` — the importer's report
  - `slides.deckwerk.importer.report(key, root=None) -> dict` — `--report`, writes nothing
  - `slides.deckwerk.importer.read_via_import(key) -> Deck`
  - `slides.deckwerk.importer.MissingDeckWerk(Exception)`
  - `slides.deckwerk.agent.validate(deck_dir, root=None) -> dict`
  - `slides.commands.convert.run(args) -> int`

The importer writes JSON to stdout and diagnostics to stderr, so only stdout is parsed. `.venv-import/bin/python` is preferred when present; otherwise the tool's own interpreter, which already carries `keynote-parser` as a core dependency.

- [ ] **Step 1: Write the failing test**

```python
import os
import json
import pathlib
import pytest
from slides.deckwerk import importer

REAL_ROOT = pathlib.Path(os.path.expanduser("~/src/deckwerk"))
needs_deckwerk = pytest.mark.skipif(
    not (REAL_ROOT / "importers/keynote/import_keynote.py").exists(),
    reason="no DeckWerk checkout",
)


def test_find_root_prefers_the_explicit_argument(tmp_path):
    (tmp_path / "importers/keynote").mkdir(parents=True)
    (tmp_path / "importers/keynote/import_keynote.py").touch()
    assert importer.find_root(str(tmp_path)) == tmp_path


def test_find_root_reads_the_environment(tmp_path, monkeypatch):
    (tmp_path / "importers/keynote").mkdir(parents=True)
    (tmp_path / "importers/keynote/import_keynote.py").touch()
    monkeypatch.setenv("SLIDES_DECKWERK_ROOT", str(tmp_path))
    assert importer.find_root() == tmp_path


def test_missing_checkout_says_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setenv("SLIDES_DECKWERK_ROOT", str(tmp_path / "nope"))
    with pytest.raises(importer.MissingDeckWerk) as caught:
        importer.find_root()
    assert "SLIDES_DECKWERK_ROOT" in str(caught.value)


def test_interpreter_prefers_the_import_venv(tmp_path):
    venv = tmp_path / ".venv-import/bin"
    venv.mkdir(parents=True)
    python = venv / "python"
    python.touch(mode=0o755)
    assert importer.interpreter(tmp_path) == str(python)


def test_interpreter_falls_back_to_our_own(tmp_path):
    import sys
    assert importer.interpreter(tmp_path) == sys.executable


@needs_deckwerk
def test_read_via_import_matches_the_fast_path():
    key = pathlib.Path(os.path.expanduser(
        "~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote"
        "/09_oct14_tfidf_imbalance_eval.key"
    ))
    if not key.exists():
        pytest.skip("no sample .key")
    from slides.readers.keynote_file import read
    assert len(importer.read_via_import(key).slides) == len(read(key).slides)


@needs_deckwerk
def test_report_runs_without_writing(tmp_path):
    key = pathlib.Path(os.path.expanduser(
        "~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote"
        "/09_oct14_tfidf_imbalance_eval.key"
    ))
    if not key.exists():
        pytest.skip("no sample .key")
    result = importer.report(key)
    assert isinstance(result, dict)
    assert not list(tmp_path.iterdir())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deckwerk_importer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.deckwerk'`

- [ ] **Step 3: Write `src/slides/deckwerk/importer.py`**

```python
import os
import sys
import json
import shutil
import pathlib
import tempfile
import subprocess
from slides.model import Deck

RELATIVE = "importers/keynote/import_keynote.py"
DEFAULT_ROOT = "~/src/deckwerk"


class DeckWerkError(Exception):
    pass


class MissingDeckWerk(DeckWerkError):
    pass


class ImporterFailed(DeckWerkError):
    pass


def find_root(explicit: str | None = None) -> pathlib.Path:
    for candidate in (explicit, os.environ.get("SLIDES_DECKWERK_ROOT"), DEFAULT_ROOT):
        if not candidate:
            continue
        root = pathlib.Path(os.path.expanduser(candidate))
        if (root / RELATIVE).exists():
            return root
    raise MissingDeckWerk(
        "No DeckWerk checkout found. Pass --deckwerk-root, set "
        "SLIDES_DECKWERK_ROOT, or clone it to %s" % (DEFAULT_ROOT,)
    )


def interpreter(root: pathlib.Path) -> str:
    candidate = root / ".venv-import/bin/python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def import_key(key, out, root: str | None = None) -> dict:
    return _invoke(key, root, ["--out", str(out)])


def report(key, root: str | None = None) -> dict:
    return _invoke(key, root, ["--report"])


def read_via_import(key) -> Deck:
    from slides.readers import deckwerk
    staging = pathlib.Path(tempfile.mkdtemp(prefix="slides-import-"))
    target = staging / "deck"
    import_key(key, target)
    deck = deckwerk.read(target)
    deck.source = str(key)
    deck.kind = "keynote"
    shutil.rmtree(staging, ignore_errors=True)
    return deck


def _invoke(key, root: str | None, extra: list[str]) -> dict:
    checkout = find_root(root)
    command = [interpreter(checkout), str(checkout / RELATIVE), str(key)] + extra
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ImporterFailed(
            "DeckWerk importer failed:\n%s" % (result.stderr.strip(),)
        )
    return json.loads(result.stdout)
```

- [ ] **Step 4: Write `src/slides/deckwerk/agent.py`**

```python
import json
import subprocess
from slides.deckwerk.importer import find_root


def validate(deck_dir, root: str | None = None) -> dict:
    checkout = find_root(root)
    result = subprocess.run(
        [str(checkout / "bin/slide-agent"), "validate", str(deck_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {"available": False, "detail": result.stderr.strip()}
    return json.loads(result.stdout)
```

Write `src/slides/deckwerk/__init__.py` as an empty file.

- [ ] **Step 5: Write `src/slides/commands/convert.py` with the deckwerk route only**

The other formats arrive in Tasks 14 and 15; each raises until then, which is real behaviour rather than a placeholder.

```python
import sys
import pathlib
import argparse
from slides import readers
from slides.deckwerk import importer


def run(args: argparse.Namespace) -> int:
    source = pathlib.Path(args.target)
    kind = readers.detect(source)
    route = (kind, args.format)
    if route == ("keynote", "deckwerk"):
        return _to_deckwerk(args, source)
    raise ValueError("cannot convert %s to %s" % (kind, args.format))


def _to_deckwerk(args: argparse.Namespace, source: pathlib.Path) -> int:
    out = pathlib.Path(args.output) if args.output else source.with_suffix("")
    result = importer.import_key(source, out, root=args.deckwerk_root)
    counts = result.get("report", {})
    sys.stderr.write("Imported %s -> %s\n" % (source.name, out))
    unsupported = counts.get("unsupported") or counts.get("unsupportedCount")
    if unsupported:
        sys.stderr.write("%s elements came through as placeholders\n" % (unsupported,))
    sys.stdout.write("%s\n" % (out,))
    return 0
```

- [ ] **Step 6: Add the `info` hooks**

In `src/slides/commands/info.py`, extend `run` so a `.key` also prints the importer's coverage report and a DeckWerk folder also prints `slide-agent validate`. Both degrade to a single stderr line when DeckWerk is absent.

```python
def run(args: argparse.Namespace) -> int:
    deck = readers.read(args.target)
    sys.stdout.write(summarise(deck) + "\n")
    kind = readers.detect(args.target)
    if kind == "keynote":
        _extra(lambda: _coverage(args))
    elif kind == "deckwerk":
        _extra(lambda: _validation(args))
    return 0


def _extra(work) -> None:
    from slides.deckwerk.importer import DeckWerkError
    try:
        sys.stdout.write(work())
    except DeckWerkError as problem:
        sys.stderr.write("%s\n" % (problem,))


def _coverage(args: argparse.Namespace) -> str:
    from slides.deckwerk import importer
    result = importer.report(args.target, root=args.deckwerk_root)
    return "coverage: %s\n" % (json.dumps(result.get("report", {}), indent=2),)


def _validation(args: argparse.Namespace) -> str:
    from slides.deckwerk import agent
    result = agent.validate(args.target, root=args.deckwerk_root)
    return "validate: %s\n" % (json.dumps(result, indent=2),)
```

Add `import json` to that module's builtins block. This is the one place a `try/except` earns its keep: a missing DeckWerk checkout is expected on any machine but this one, and the whole point is to degrade rather than fail.

- [ ] **Step 7: Wire `convert` into `cli.py`**

```python
def _convert(args: argparse.Namespace) -> int:
    from slides.commands import convert
    return convert.run(args)
```

and set `"convert": _convert`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_deckwerk_importer.py tests/test_info.py -v`
Expected: 7 passed (the real-checkout tests skip without one)

- [ ] **Step 9: Verify end to end**

```bash
cd /tmp && slides convert ~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/09_oct14_tfidf_imbalance_eval.key -f deckwerk -o /tmp/lecture09
slides info /tmp/lecture09
```
Expected: a deck folder with `deck.json`, then an inventory plus validation output.

- [ ] **Step 10: Commit**

```bash
git add src/slides/deckwerk src/slides/commands tests/test_deckwerk_importer.py
git commit -m "feat: DeckWerk importer wrapper and convert -f deckwerk"
```

---

## Task 14: pptx writer and `convert -f pptx`

**Files:**
- Create: `src/slides/writers/pptx.py`
- Modify: `src/slides/commands/convert.py`
- Test: `tests/test_writer_pptx.py`

**Interfaces:**
- Consumes: `slides.model.Deck`.
- Produces: `slides.writers.pptx.write(deck: Deck, path) -> None`.

Geometry is used when the reader supplied it, which is the DeckWerk case; otherwise a title-and-body fallback. Points convert to EMU at 12700 per point, matching the reader.

- [ ] **Step 1: Write the failing test**

```python
import pathlib
import pptx
from slides.model import Deck, Slide, Table, TextItem
from slides.writers.pptx import write


def a_deck() -> Deck:
    return Deck(
        title="Talk",
        width=1920.0,
        height=1080.0,
        slides=[
            Slide(
                number=1,
                title="Opening",
                items=[
                    TextItem(text="Opening", role="title", x=120, y=84, w=1680, h=67),
                    TextItem(text="A point", x=120, y=300, w=800, h=60),
                ],
                notes="Say hello.",
                background="#0d1e1c",
            ),
            Slide(
                number=2,
                title="Numbers",
                items=[TextItem(text="Numbers", role="title")],
                tables=[Table(rows=[["Model", "MSE"], ["Linear", "3.2"]])],
            ),
        ],
    )


def test_round_trips_through_the_reader(tmp_path):
    from slides.readers.pptx import read
    out = tmp_path / "out.pptx"
    write(a_deck(), out)
    back = read(out)
    assert len(back.slides) == 2
    assert back.slides[0].title == "Opening"
    assert "A point" in [i.text for i in back.slides[0].body_items()]
    assert back.slides[0].notes == "Say hello."
    assert back.slides[1].tables[0].rows == [["Model", "MSE"], ["Linear", "3.2"]]


def test_canvas_size_is_preserved(tmp_path):
    out = tmp_path / "out.pptx"
    write(a_deck(), out)
    deck = pptx.Presentation(str(out))
    assert round(deck.slide_width / 12700) == 1920
    assert round(deck.slide_height / 12700) == 1080


def test_slides_without_geometry_still_lay_out(tmp_path):
    deck = Deck(title="Bare", slides=[
        Slide(number=1, title="T", items=[TextItem(text="Body with no box")]),
    ])
    out = tmp_path / "bare.pptx"
    write(deck, out)
    from slides.readers.pptx import read
    assert read(out).slides[0].title == "T"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_writer_pptx.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slides.writers.pptx'`

- [ ] **Step 3: Write `src/slides/writers/pptx.py`**

```python
import pathlib
from slides.color import to_rgb
from slides.model import Deck, Slide, TextItem

EMU_PER_POINT = 12700
BLANK_LAYOUT = 6


def write(deck: Deck, path: str | pathlib.Path) -> None:
    import pptx
    from pptx.util import Emu
    presentation = pptx.Presentation()
    presentation.slide_width = Emu(int(deck.width * EMU_PER_POINT))
    presentation.slide_height = Emu(int(deck.height * EMU_PER_POINT))
    layout = presentation.slide_layouts[BLANK_LAYOUT]
    for slide in deck.slides:
        _slide(presentation.slides.add_slide(layout), slide, deck)
    presentation.save(str(path))


def _slide(target, slide: Slide, deck: Deck) -> None:
    if slide.background:
        _paint(target, slide.background)
    for index, item in enumerate(slide.items):
        _text_box(target, item, index, deck)
    for offset, table in enumerate(slide.tables):
        _table(target, table.rows, offset, deck)
    if slide.notes.strip():
        target.notes_slide.notes_text_frame.text = slide.notes


def _paint(target, value: str) -> None:
    from pptx.dml.color import RGBColor
    red, green, blue = (int(round(c * 255)) for c in to_rgb(value))
    fill = target.background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(red, green, blue)


def _text_box(target, item: TextItem, index: int, deck: Deck) -> None:
    from pptx.util import Emu, Pt
    box = target.shapes.add_textbox(
        Emu(int(_or(item.x, deck.width * 0.06) * EMU_PER_POINT)),
        Emu(int(_or(item.y, 80.0 + index * 90.0) * EMU_PER_POINT)),
        Emu(int(_or(item.w, deck.width * 0.88) * EMU_PER_POINT)),
        Emu(int(_or(item.h, 70.0) * EMU_PER_POINT)),
    )
    frame = box.text_frame
    frame.word_wrap = True
    lines = item.text.split("\n")
    frame.text = lines[0]
    for line in lines[1:]:
        frame.add_paragraph().text = line
    size = Pt(40) if item.role == "title" else Pt(24)
    for paragraph in frame.paragraphs:
        for run in paragraph.runs:
            run.font.size = size


def _table(target, rows: list[list[str]], offset: int, deck: Deck) -> None:
    from pptx.util import Emu
    if not rows:
        return
    columns = max(len(row) for row in rows)
    shape = target.shapes.add_table(
        len(rows),
        columns,
        Emu(int(deck.width * 0.06 * EMU_PER_POINT)),
        Emu(int((deck.height * 0.45 + offset * 200.0) * EMU_PER_POINT)),
        Emu(int(deck.width * 0.5 * EMU_PER_POINT)),
        Emu(int(len(rows) * 40.0 * EMU_PER_POINT)),
    )
    for r, row in enumerate(rows):
        for c in range(columns):
            shape.table.cell(r, c).text = str(row[c]) if c < len(row) else ""


def _or(value: float | None, fallback: float) -> float:
    return fallback if value is None else value
```

- [ ] **Step 4: Add the route to `src/slides/commands/convert.py`**

```python
    if route in (("deckwerk", "pptx"), ("keynote", "pptx")):
        return _to_pptx(args, source, kind)
```

```python
def _to_pptx(args: argparse.Namespace, source: pathlib.Path, kind: str) -> int:
    from slides.writers import pptx as writer
    out = pathlib.Path(args.output) if args.output else source.with_suffix(".pptx")
    deck = readers.read(source)
    writer.write(deck, out)
    sys.stderr.write("Builds and transitions do not survive this route\n")
    sys.stdout.write("%s\n" % (out,))
    return 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_writer_pptx.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/slides/writers/pptx.py src/slides/commands/convert.py tests/test_writer_pptx.py
git commit -m "feat: pptx writer and convert -f pptx"
```

---

## Task 15: `convert -f keynote` and `-f pdf`

**Files:**
- Create: `src/slides/keynote/export.py`
- Modify: `src/slides/commands/convert.py`
- Test: `tests/test_keynote_export.py`

**Interfaces:**
- Consumes: `slides.keynote.jxa`, `slides.writers.pptx.write`.
- Produces:
  - `slides.keynote.export.open_and_save(source, out) -> None` — open any deck Keynote can read, save as `.key`
  - `slides.keynote.export.export_pdf(source, out) -> None`
  - `slides.keynote.export.SCRIPT_SAVE`, `SCRIPT_PDF` — the JXA templates, exposed so they can be tested without running Keynote

The DeckWerk → Keynote route is DeckWerk → pptx → Keynote, per the spec. Only the final save needs the app.

- [ ] **Step 1: Write the failing test**

```python
import shutil
import pytest
from slides.keynote import export, jxa


def test_save_script_quotes_both_paths():
    script = export.SCRIPT_SAVE % ('"Keynote"', '"/a/in.pptx"', '"/b/out.key"')
    assert "/a/in.pptx" in script and "/b/out.key" in script


def test_open_and_save_invokes_jxa(monkeypatch):
    seen = {}
    monkeypatch.setattr(jxa, "run", lambda script: seen.setdefault("script", script))
    export.open_and_save("/a/in.pptx", "/b/out.key")
    assert "in.pptx" in seen["script"]
    assert "out.key" in seen["script"]


def test_export_pdf_asks_for_pdf(monkeypatch):
    seen = {}
    monkeypatch.setattr(jxa, "run", lambda script: seen.setdefault("script", script))
    export.export_pdf("/a/in.key", "/b/out.pdf")
    assert "PDF" in seen["script"]


@pytest.mark.skipif(shutil.which("osascript") is None, reason="not a Mac")
def test_paths_with_quotes_do_not_break_the_script(monkeypatch):
    seen = {}
    monkeypatch.setattr(jxa, "run", lambda script: seen.setdefault("script", script))
    export.open_and_save('/a/we"ird.pptx', "/b/out.key")
    assert '\\"' in seen["script"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_keynote_export.py -v`
Expected: FAIL with `ImportError: cannot import name 'export'`

- [ ] **Step 3: Write `src/slides/keynote/export.py`**

```python
import pathlib
from slides.keynote import jxa

SCRIPT_SAVE = """
var app = Application(%s);
app.includeStandardAdditions = true;
var doc = app.open(Path(%s));
doc.save({in: Path(%s)});
doc.close({saving: "no"});
"savedn";
"""

SCRIPT_PDF = """
var app = Application(%s);
app.includeStandardAdditions = true;
var doc = app.open(Path(%s));
app.export(doc, {to: Path(%s), as: "PDF"});
doc.close({saving: "no"});
"exported";
"""


def open_and_save(source, out) -> None:
    jxa.run(SCRIPT_SAVE % (
        _quoted(jxa.app_name()),
        _quoted(str(pathlib.Path(source).resolve())),
        _quoted(str(pathlib.Path(out).resolve())),
    ))


def export_pdf(source, out) -> None:
    jxa.run(SCRIPT_PDF % (
        _quoted(jxa.app_name()),
        _quoted(str(pathlib.Path(source).resolve())),
        _quoted(str(pathlib.Path(out).resolve())),
    ))


def _quoted(value: str) -> str:
    return '"%s"' % (value.replace("\\", "\\\\").replace('"', '\\"'),)
```

- [ ] **Step 4: Add the routes to `convert.py`**

```python
    if args.format == "keynote":
        return _to_keynote(args, source, kind)
    if args.format == "pdf":
        return _to_pdf(args, source, kind)
```

```python
def _to_keynote(args: argparse.Namespace, source: pathlib.Path, kind: str) -> int:
    import tempfile
    from slides.keynote import export
    from slides.writers import pptx as writer
    out = pathlib.Path(args.output) if args.output else source.with_suffix(".key")
    if kind == "keynote":
        raise ValueError("%s is already a Keynote deck" % (source,))
    staging = pathlib.Path(tempfile.mkdtemp(prefix="slides-key-")) / "deck.pptx"
    writer.write(readers.read(source), staging)
    export.open_and_save(staging, out)
    sys.stderr.write("Builds and transitions do not survive this route\n")
    sys.stdout.write("%s\n" % (out,))
    return 0


def _to_pdf(args: argparse.Namespace, source: pathlib.Path, kind: str) -> int:
    import tempfile
    from slides.keynote import export
    from slides.writers import pptx as writer
    out = pathlib.Path(args.output) if args.output else source.with_suffix(".pdf")
    if kind == "keynote":
        export.export_pdf(source, out)
    else:
        staging = pathlib.Path(tempfile.mkdtemp(prefix="slides-pdf-")) / "deck.pptx"
        writer.write(readers.read(source), staging)
        export.export_pdf(staging, out)
    sys.stdout.write("%s\n" % (out,))
    return 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_keynote_export.py -v`
Expected: 4 passed

- [ ] **Step 6: Verify against the real app**

```bash
slides convert tests/fixtures/mini_deckwerk -f keynote -o /tmp/mini.key
open /tmp/mini.key
```
Expected: Keynote opens a two-slide deck. **If `doc.save({in: ...})` does not produce a `.key`**, the working alternative is `app.export(doc, {to: Path(out), as: "Keynote 09"})` — verify which one this Keynote version accepts and keep the one that works, adjusting `SCRIPT_SAVE` and its test together.

- [ ] **Step 7: Commit**

```bash
git add src/slides/keynote/export.py src/slides/commands/convert.py tests/test_keynote_export.py
git commit -m "feat: convert to keynote and pdf via the app"
```

---

## Task 16: `slides patch`

**Files:**
- Create: `src/slides/keynote/patch.py`, `src/slides/commands/patch.py`
- Modify: `src/slides/cli.py`
- Test: `tests/test_patch.py`

**Interfaces:**
- Consumes: `slides.keynote.jxa`.
- Produces:
  - `slides.keynote.patch.apply(spec: dict, app: str | None = None) -> dict` — returns `{"updated": int, "skipped": list[int]}`
  - `slides.keynote.patch.SCRIPT` — the JXA template
  - `slides.commands.patch.run(args) -> int`

The spec is keyed by slide number as a string, matching `slides dump -f json` output so a deck can be dumped, edited and applied back. Fields are all optional: `title`, `body`, `notes`, `images`, `tables`. The JXA reads the spec from a temp file rather than being string-interpolated, which is what the existing `apply_applied_lecture_update.js` does and what keeps quoting safe.

- [ ] **Step 1: Write the failing test**

```python
import json
import pytest
from slides.keynote import jxa, patch


def test_writes_the_spec_to_a_file_and_reports(monkeypatch):
    captured = {}

    def fake_run_json(script: str):
        captured["script"] = script
        path = script.split('readSpec("')[1].split('")')[0]
        captured["spec"] = json.load(open(path))
        return {"updated": 2, "skipped": []}

    monkeypatch.setattr(jxa, "run_json", fake_run_json)
    spec = {"1": {"title": "New"}, "2": {"notes": "Say it."}}
    result = patch.apply(spec)
    assert result == {"updated": 2, "skipped": []}
    assert captured["spec"] == spec


def test_rejects_a_spec_that_is_not_keyed_by_slide_number():
    with pytest.raises(ValueError, match="slide number"):
        patch.apply({"first": {"title": "x"}})


def test_rejects_unknown_fields():
    with pytest.raises(ValueError, match="colour"):
        patch.apply({"1": {"colour": "red"}})


def test_accepts_every_documented_field(monkeypatch):
    monkeypatch.setattr(jxa, "run_json", lambda script: {"updated": 1, "skipped": []})
    spec = {
        "1": {
            "title": "T",
            "body": ["a", "b"],
            "notes": "n",
            "images": ["/tmp/x.png"],
            "tables": [[["a", "b"]]],
        }
    }
    assert patch.apply(spec)["updated"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_patch.py -v`
Expected: FAIL with `ImportError: cannot import name 'patch'`

- [ ] **Step 3: Write `src/slides/keynote/patch.py`**

```python
import json
import tempfile
from slides.keynote import jxa

FIELDS = {"title", "body", "notes", "images", "tables"}

SCRIPT = """
ObjC.import("Foundation");
function readSpec(path) {
  var s = $.NSString.stringWithContentsOfFileEncodingError(
    path, $.NSUTF8StringEncoding, null);
  return JSON.parse(ObjC.unwrap(s));
}
var spec = readSpec("%s");
var app = Application(%s);
if (app.documents.length === 0) { throw new Error("No presentation is open."); }
var doc = app.documents[0];
var updated = 0;
var skipped = [];
for (var key in spec) {
  var index = parseInt(key, 10) - 1;
  if (index < 0 || index >= doc.slides.length) { skipped.push(parseInt(key, 10)); continue; }
  var slide = doc.slides[index];
  var entry = spec[key];
  if (entry.title !== undefined) { slide.defaultTitleItem.objectText = entry.title; }
  if (entry.notes !== undefined) { slide.presenterNotes = entry.notes; }
  if (entry.body !== undefined) {
    var text = Array.isArray(entry.body) ? entry.body.join("\\n") : entry.body;
    slide.defaultBodyItem.objectText = text;
  }
  if (entry.images !== undefined) {
    for (var i = 0; i < entry.images.length; i++) {
      slide.images.push(app.Image({file: Path(entry.images[i])}));
    }
  }
  if (entry.tables !== undefined) {
    for (var t = 0; t < entry.tables.length && t < slide.tables.length; t++) {
      var rows = entry.tables[t];
      for (var r = 0; r < rows.length && r < slide.tables[t].rows.length; r++) {
        for (var c = 0; c < rows[r].length; c++) {
          slide.tables[t].rows[r].cells[c].value = rows[r][c];
        }
      }
    }
  }
  updated += 1;
}
JSON.stringify({updated: updated, skipped: skipped});
"""


def apply(spec: dict, app: str | None = None) -> dict:
    _check(spec)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="slides-patch-",
        delete=False,
    )
    json.dump(spec, handle)
    handle.close()
    name = app or jxa.app_name()
    return jxa.run_json(SCRIPT % (handle.name, '"%s"' % (name,)))


def _check(spec: dict) -> None:
    for key, entry in spec.items():
        if not str(key).isdigit():
            raise ValueError("%r is not a slide number" % (key,))
        unknown = set(entry) - FIELDS
        if unknown:
            raise ValueError(
                "unknown field(s) %s; expected any of %s"
                % (", ".join(sorted(unknown)), ", ".join(sorted(FIELDS)))
            )
```

- [ ] **Step 4: Write `src/slides/commands/patch.py` and wire the CLI**

```python
import sys
import json
import pathlib
import argparse
from slides.keynote import patch


def run(args: argparse.Namespace) -> int:
    spec = json.loads(pathlib.Path(args.spec).read_text())
    result = patch.apply(spec)
    sys.stderr.write("Updated %d slides\n" % (result["updated"],))
    if result["skipped"]:
        sys.stderr.write("No such slides: %s\n" % (result["skipped"],))
    return 0
```

In `cli.py`:

```python
def _patch(args: argparse.Namespace) -> int:
    from slides.commands import patch
    return patch.run(args)
```

and set `"patch": _patch`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_patch.py -v`
Expected: 4 passed

- [ ] **Step 6: Verify against the real app**

Open a presentation, then:
```bash
echo '{"1": {"notes": "Patched from the CLI."}}' > /tmp/spec.json
slides patch /tmp/spec.json
slides dump --notes-only | head -5
```
Expected: `Updated 1 slides`, and the note comes back in the dump.

- [ ] **Step 7: Commit**

```bash
git add src/slides/keynote/patch.py src/slides/commands/patch.py src/slides/cli.py tests/test_patch.py
git commit -m "feat: slides patch"
```

---

## Task 17: `slides scaffold`

**Files:**
- Create: `src/slides/keynote/scaffold.py`, `src/slides/commands/scaffold.py`
- Modify: `src/slides/cli.py`
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Consumes: `slides.keynote.jxa`, `slides.keynote.patch.apply`.
- Produces:
  - `slides.keynote.scaffold.build(spec: dict, template: str | None = None) -> dict` — `{"created": int}`
  - `slides.keynote.scaffold.SCRIPT_CREATE`
  - `slides.commands.scaffold.run(args) -> int`

`scaffold` is `patch` preceded by slide creation, exactly as the spec says. The spec gains one optional per-slide field, `master`, naming a master slide in the template; slides are created in numeric key order, then `patch.apply` fills them. The tool ships no template — `--template` names one, and without it the frontmost document is used.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from slides.keynote import jxa, scaffold


def test_creates_then_patches(monkeypatch):
    calls = []
    monkeypatch.setattr(jxa, "run_json", lambda script: calls.append(script) or {"created": 2})
    monkeypatch.setattr(
        "slides.keynote.patch.apply",
        lambda spec, app=None: calls.append("patch") or {"updated": 2, "skipped": []},
    )
    spec = {"1": {"title": "One"}, "2": {"title": "Two", "master": "Title & Bullets"}}
    result = scaffold.build(spec)
    assert result["created"] == 2
    assert calls[-1] == "patch"


def test_master_is_stripped_before_patching(monkeypatch):
    seen = {}
    monkeypatch.setattr(jxa, "run_json", lambda script: {"created": 1})
    monkeypatch.setattr(
        "slides.keynote.patch.apply",
        lambda spec, app=None: seen.update(spec=spec) or {"updated": 1, "skipped": []},
    )
    scaffold.build({"1": {"title": "One", "master": "Blank"}})
    assert "master" not in seen["spec"]["1"]
    assert seen["spec"]["1"]["title"] == "One"


def test_slides_are_created_in_numeric_order(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        jxa,
        "run_json",
        lambda script: seen.setdefault("script", script) or {"created": 3},
    )
    monkeypatch.setattr(
        "slides.keynote.patch.apply", lambda spec, app=None: {"updated": 3, "skipped": []}
    )
    scaffold.build({"10": {"title": "Ten"}, "2": {"title": "Two"}, "1": {"title": "One"}})
    masters = seen["script"]
    assert masters.index('"1"') < masters.index('"2"') < masters.index('"10"')


def test_rejects_a_bad_spec():
    with pytest.raises(ValueError, match="slide number"):
        scaffold.build({"first": {"title": "x"}})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scaffold.py -v`
Expected: FAIL with `ImportError: cannot import name 'scaffold'`

- [ ] **Step 3: Write `src/slides/keynote/scaffold.py`**

```python
import json
from slides.keynote import jxa, patch

SCRIPT_CREATE = """
var app = Application(%s);
app.includeStandardAdditions = true;
var doc = %s;
var wanted = %s;
var created = 0;
for (var i = 0; i < wanted.length; i++) {
  var name = wanted[i].master;
  var made;
  if (name) {
    made = app.Slide({baseSlide: doc.masterSlides.byName(name)});
  } else {
    made = app.Slide();
  }
  doc.slides.push(made);
  created += 1;
}
JSON.stringify({created: created});
"""

OPEN_TEMPLATE = 'app.open(Path("%s"))'
FRONT_DOCUMENT = "app.documents[0]"


def build(spec: dict, template: str | None = None) -> dict:
    patch._check(spec)
    order = sorted(spec, key=lambda k: int(k))
    wanted = [{"key": key, "master": spec[key].get("master")} for key in order]
    document = OPEN_TEMPLATE % (template,) if template else FRONT_DOCUMENT
    result = jxa.run_json(SCRIPT_CREATE % (
        '"%s"' % (jxa.app_name(),),
        document,
        json.dumps(wanted),
    ))
    patch.apply(_without_master(spec, order))
    return result


def _without_master(spec: dict, order: list[str]) -> dict:
    return {
        str(position): {k: v for k, v in spec[key].items() if k != "master"}
        for position, key in enumerate(order, start=1)
    }
```

Note that `_without_master` re-keys by creation position, not by the spec's own keys, because the new slides land at the end of the document in the order they were created. Add `"master"` to `patch.FIELDS` so `_check` accepts it.

- [ ] **Step 4: Write `src/slides/commands/scaffold.py` and wire the CLI**

```python
import sys
import json
import pathlib
import argparse
from slides.keynote import scaffold


def run(args: argparse.Namespace) -> int:
    spec = json.loads(pathlib.Path(args.spec).read_text())
    result = scaffold.build(spec, template=args.template)
    sys.stderr.write("Created %d slides\n" % (result["created"],))
    return 0
```

In `cli.py`:

```python
def _scaffold(args: argparse.Namespace) -> int:
    from slides.commands import scaffold
    return scaffold.run(args)
```

and set `"scaffold": _scaffold`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scaffold.py tests/test_patch.py -v`
Expected: 8 passed

- [ ] **Step 6: Verify against the real app**

```bash
cat > /tmp/scaffold.json <<'EOF'
{
  "1": {"title": "First", "body": ["One point"], "notes": "Open here."},
  "2": {"title": "Second", "body": ["Another point"]}
}
EOF
slides scaffold /tmp/scaffold.json
```
Expected: two slides appended to the front document with those titles, bodies and notes.

- [ ] **Step 7: Commit**

```bash
git add src/slides/keynote/scaffold.py src/slides/commands/scaffold.py src/slides/cli.py tests/test_scaffold.py
git commit -m "feat: slides scaffold"
```

---

## Task 18: `slides math`

**Files:**
- Create: `src/slides/keynote/math.py`, `src/slides/commands/math.py`
- Modify: `src/slides/cli.py`
- Test: `tests/test_math.py`

**Interfaces:**
- Consumes: `keynote-parser`.
- Produces:
  - `slides.keynote.math.find_equations(text: str) -> list[tuple[int, int, str]]` — `(start, end, latex)`, display `$$...$$` before inline `$...$`
  - `slides.keynote.math.convert(source, out, min_slide: int = 1) -> int` — number of equations converted
  - `slides.commands.math.run(args) -> int`

**This ports a proven algorithm; do not invent one.** The reference implementation is `~/Desktop/Git/Class/introml/scripts/apply_headless_equations.py`. Read it first. The mechanism, per storage archive:

1. Unpack the `.key` to YAML with the `keynote-parser` CLI.
2. For each `TSWP.StorageArchive` that is **not** reached from a `KN.NoteArchive` — presenter notes stay plain text — scan its `text` entries for `$$...$$` and `$...$`.
3. Replace each match in the text with a single `￼`, recording the character index where it landed.
4. Append a `TSWP.DrawableAttachmentArchive` entry to `tableAttachment.entries` at that `characterIndex`, referencing a new `TSWP.EquationInfoArchive` carrying `[TSWP.EquationInfoArchive.equation_source_text]` (and `equation_source_old`) set to the delimiter-stripped LaTeX.
5. Remap the character indices of every later attachment by the accumulated shift, which is what `remap_char_index` and its `shift_points` list exist for.
6. Sort `tableAttachment.entries` by `characterIndex`.
7. In `Document.iwa.yaml`, ensure `featureInfos` declares `TSWPEquations` and `TSWPInlineDrawables`, and that `externalReferences` points at the equation style. Without this, Keynote offers to repair the file on open.
8. Repack with the `keynote-parser` CLI.

Required changes when porting: drop the hardcoded `find_keynote_parser` candidate paths in favour of `shutil.which("keynote-parser")` falling back to `sys.executable -m keynote_parser`; make `min_slide` default to `1` rather than `8`; make the output default to a suffixed copy rather than in-place; and strip the course-specific slide-protection logic.

- [ ] **Step 1: Write the failing test**

```python
import os
import pathlib
import shutil
import pytest
from slides.keynote import math

REAL = pathlib.Path(os.path.expanduser(
    "~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote"
    "/09_oct14_tfidf_imbalance_eval.key"
))
needs_real = pytest.mark.skipif(not REAL.exists(), reason="no sample .key")


def test_finds_inline_math():
    found = math.find_equations("Let $N$ be the count.")
    assert found == [(4, 7, "N")]


def test_finds_display_math_before_inline():
    found = math.find_equations("Before $$a + b$$ after")
    assert found == [(7, 16, "a + b")]


def test_finds_several_in_order():
    found = math.find_equations("$a$ then $$b$$ then $c$")
    assert [latex for _, _, latex in found] == ["a", "b", "c"]


def test_ignores_bare_dollars_and_currency():
    assert math.find_equations("costs $5 and $10 per unit") == []
    assert math.find_equations("no math here") == []


def test_does_not_match_across_a_blank_line():
    assert math.find_equations("$start\n\nend$") == []


@needs_real
def test_converts_and_produces_an_openable_deck(tmp_path):
    out = tmp_path / "converted.key"
    count = math.convert(REAL, out, min_slide=1)
    assert count > 0
    assert out.exists()
    from slides.readers.keynote_file import read
    deck = read(out)
    assert len(deck.slides) == len(read(REAL).slides)


@needs_real
def test_min_slide_protects_leading_slides(tmp_path):
    out = tmp_path / "partial.key"
    everything = math.convert(REAL, tmp_path / "all.key", min_slide=1)
    protected = math.convert(REAL, out, min_slide=20)
    assert protected < everything
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_math.py -v`
Expected: FAIL with `ImportError: cannot import name 'math'`

- [ ] **Step 3: Write the `find_equations` scanner**

This is the one part worth writing fresh, because the reference's regex is entangled with its slide filter. Display math is matched first so `$$...$$` never parses as two empty inline spans.

```python
import re

DISPLAY = re.compile(r"\$\$(?!\s)((?:[^$\n]|\n(?!\n))+?)(?<!\s)\$\$")
INLINE = re.compile(r"(?<!\$)\$(?!\s)((?:[^$\n]|\n(?!\n))+?)(?<!\s)\$(?!\$)")


def find_equations(text: str) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    taken: list[tuple[int, int]] = []
    for match in DISPLAY.finditer(text):
        found.append((match.start(), match.end(), match.group(1).strip()))
        taken.append((match.start(), match.end()))
    for match in INLINE.finditer(text):
        if any(start <= match.start() < end for start, end in taken):
            continue
        found.append((match.start(), match.end(), match.group(1).strip()))
    found.sort(key=lambda item: item[0])
    return found
```

- [ ] **Step 4: Port `convert` from the reference implementation**

Read `~/Desktop/Git/Class/introml/scripts/apply_headless_equations.py` and port `unpack_deck`, `repack_deck`, `get_slide_mapping`, `remap_char_index` and `process_presentation` into `slides/keynote/math.py`, applying the four changes listed above and calling `find_equations` in place of the reference's inline regex. Keep the `TSWP.EquationInfoArchive` field names and the `Document.iwa.yaml` feature registration exactly as they are — those constants were found empirically and Keynote rejects the file without them.

Signature:

```python
def convert(source, out, min_slide: int = 1) -> int:
```

- [ ] **Step 5: Write `src/slides/commands/math.py` and wire the CLI**

```python
import sys
import pathlib
import argparse
from slides.keynote import math


def run(args: argparse.Namespace) -> int:
    source = pathlib.Path(args.target)
    out = pathlib.Path(args.output) if args.output else source.with_name(
        "%s-math%s" % (source.stem, source.suffix)
    )
    count = math.convert(source, out, min_slide=args.min_slide)
    sys.stderr.write("Converted %d equations\n" % (count,))
    sys.stdout.write("%s\n" % (out,))
    return 0
```

In `cli.py`:

```python
def _math(args: argparse.Namespace) -> int:
    from slides.commands import math
    return math.run(args)
```

and set `"math": _math`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_math.py -v`
Expected: 7 passed

- [ ] **Step 7: Verify Keynote opens the result without offering to repair it**

```bash
slides math ~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/09_oct14_tfidf_imbalance_eval.key -o /tmp/math.key
open /tmp/math.key
```
Expected: Keynote opens it with no repair prompt, and the equations render as typeset math rather than raw `$...$`.

- [ ] **Step 8: Commit**

```bash
git add src/slides/keynote/math.py src/slides/commands/math.py src/slides/cli.py tests/test_math.py
git commit -m "feat: slides math"
```

---

## Task 20: Interactive demos, video and fallback tables

**Files:**
- Modify: `src/slides/model.py`, `src/slides/readers/deckwerk.py`, `src/slides/writers/markdown.py`, `src/slides/writers/text.py`, `src/slides/writers/json.py`
- Test: `tests/test_embeds.py`, and extend `tests/fixtures/mini_deckwerk/deck.json`

**Interfaces:**
- Consumes: the existing model and DeckWerk reader.
- Produces:
  - `slides.model.Embed(kind: str, src: str, title: str | None = None, poster: str | None = None, x=None, y=None, w=None, h=None)` — `kind` is `"web"` or `"video"`
  - `slides.model.Slide.embeds: list[Embed]`
  - `slides.writers.markdown.render` emits a link line per embed
  - `slides.writers.json.to_dict` emits an `"embeds"` list per slide

**Why this task exists.** The DeckWerk reader currently recognises `text`,
`image`, `table` and `shape`, and silently drops everything else. Measured
against a real 68-slide deck, that loses: 2 `web` elements (a least-squares
playground and a live Python REPL), 2 `video` elements, and 4 `html` elements.
A slide whose whole content is an interactive demo dumps as a blank slide.

The real element shapes, read from that deck's `deck.json`:

```json
{"type": "web", "w": 1680, "h": 780,
 "src": "assets/web/playground.3898dd78.html",
 "poster": "assets/web/playground.3898dd78.poster.png",
 "title": "Least-squares playground"}

{"type": "video", "w": 1200, "h": 528, "src": "assets/vid_rotate.mp4",
 "poster": null}

{"type": "html", "w": "998.06", "h": "464.88",
 "html": "<table class=\"tbl b element element-html\" ...>",
 "css": "...", "sandboxed": "True",
 "fallbackReason": "TABLE is preserved as HTML"}
```

Note `html` is the importer's **fallback**, not a first-class type, and in
practice it holds a table. Its `w`/`h` arrive as strings, not numbers.

- [ ] **Step 1: Add the fixture elements**

Add to `tests/fixtures/mini_deckwerk/deck.json` a third slide carrying one of
each, so every branch has a test:

```json
{
  "id": "slide-3",
  "name": "Demos",
  "background": "#0d1e1c",
  "notes": "",
  "elements": [
    { "id": "e6", "x": 120, "y": 84, "w": 1680, "h": 67, "z": 1,
      "type": "text", "html": "Demos" },
    { "id": "e7", "x": 120, "y": 200, "w": 1680, "h": 780, "z": 2,
      "type": "web", "src": "assets/web/demo.html",
      "poster": "assets/web/demo.poster.png", "title": "A demo" },
    { "id": "e8", "x": 120, "y": 1000, "w": 1200, "h": 528, "z": 3,
      "type": "video", "src": "assets/clip.mp4", "poster": null },
    { "id": "e9", "x": 120, "y": 1100, "w": "998.06", "h": "464.88", "z": 4,
      "type": "html", "sandboxed": "True",
      "fallbackReason": "TABLE is preserved as HTML",
      "html": "<table><tr><td>Model</td><td>MSE</td></tr><tr><td>Linear</td><td>3.2</td></tr></table>" }
  ]
}
```

Also create `tests/fixtures/mini_deckwerk/assets/web/demo.html` containing a
minimal self-contained page, so the copy path in Task 5 has something real to
copy.

- [ ] **Step 2: Write the failing test**

```python
import pathlib
from slides.model import Deck, Embed, Slide
from slides.readers.deckwerk import read
from slides.writers import json as json_writer
from slides.writers import markdown

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def test_web_element_becomes_an_embed():
    slide = read(FIXTURE).slides[2]
    web = [e for e in slide.embeds if e.kind == "web"]
    assert len(web) == 1
    assert web[0].src == "assets/web/demo.html"
    assert web[0].title == "A demo"
    assert web[0].poster == "assets/web/demo.poster.png"


def test_video_element_becomes_an_embed():
    slide = read(FIXTURE).slides[2]
    video = [e for e in slide.embeds if e.kind == "video"]
    assert len(video) == 1
    assert video[0].src == "assets/clip.mp4"
    assert video[0].poster is None


def test_html_fallback_table_becomes_a_real_table():
    slide = read(FIXTURE).slides[2]
    assert [row for row in slide.tables[0].rows] == [
        ["Model", "MSE"],
        ["Linear", "3.2"],
    ]


def test_html_fallback_is_not_also_emitted_as_body_text():
    slide = read(FIXTURE).slides[2]
    assert not any("Model" in i.text for i in slide.body_items())


def test_markdown_links_a_web_embed():
    out = markdown.render(read(FIXTURE))
    assert "[Interactive: A demo](assets/web/demo.html)" in out


def test_markdown_links_a_video_embed_by_filename():
    out = markdown.render(read(FIXTURE))
    assert "[Video: clip.mp4](assets/clip.mp4)" in out


def test_markdown_names_an_untitled_web_embed_by_filename():
    deck = Deck(
        title="T",
        slides=[Slide(number=1, embeds=[Embed(kind="web", src="a/b/thing.html")])],
    )
    assert "[Interactive: thing.html](a/b/thing.html)" in markdown.render(deck)


def test_notes_only_drops_embeds():
    out = markdown.render(read(FIXTURE), notes_only=True)
    assert "demo.html" not in out


def test_json_carries_embeds_structurally():
    import json as jsonlib
    parsed = jsonlib.loads(json_writer.render(read(FIXTURE)))
    embeds = parsed["slides"][2]["embeds"]
    assert {"kind": "web", "src": "assets/web/demo.html", "title": "A demo"} in [
        {"kind": e["kind"], "src": e["src"], "title": e["title"]} for e in embeds
    ]


def test_text_writer_names_embeds_without_markup():
    from slides.writers import text
    out = text.render(read(FIXTURE))
    assert "A demo" in out
    assert "[" not in out
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_embeds.py -v`
Expected: FAIL with `ImportError: cannot import name 'Embed' from 'slides.model'`

- [ ] **Step 4: Add `Embed` to `src/slides/model.py`**

Place it after `Image`, and add the field to `Slide`.

```python
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
```

In `Slide`, beside `images`:

```python
    embeds: list[Embed] = field(default_factory=list)
```

- [ ] **Step 5: Handle the three element types in the DeckWerk reader**

In `_slide`, alongside the existing branches. `_number` guards the string
geometry that `html` elements carry.

```python
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
            rows = _html_table(element.get("html") or "")
            if rows:
                slide.tables.append(Table(rows=rows))
```

and the two helpers:

```python
def _number(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _html_table(markup: str) -> list[list[str]]:
    parser = _TableParser()
    parser.feed(markup)
    return parser.rows
```

`_TableParser` subclasses `HTMLParser` the same way `_Stripper` does: it
collects `<tr>` into rows and `<td>`/`<th>` into cells, keeping the cell text
stripped. Write it beside `_Stripper`.

- [ ] **Step 6: Render embeds in the writers**

In `markdown._slide`, after the tables loop:

```python
    for embed in slide.embeds:
        parts.append("%s
" % (_link(embed),))
```

```python
def _link(embed: Embed) -> str:
    name = embed.title or pathlib.PurePosixPath(embed.src).name
    label = "Interactive" if embed.kind == "web" else "Video"
    return "[%s: %s](%s)" % (label, name, embed.src)
```

Add `import pathlib` to that module's builtins block, and import `Embed`.

In `text.render`, append `embed.title or the filename` as a bare line. In
`json._slide`, add:

```python
        "embeds": [
            {
                "kind": e.kind,
                "src": e.src,
                "title": e.title,
                "poster": e.poster,
            }
            for e in slide.embeds
        ],
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/ -v`
Expected: every test passes, including the whole existing suite.

- [ ] **Step 8: Verify against the real deck**

```bash
python -c "
from slides import read_deck
d = read_deck('$HOME/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/04_sep28_conditional_linear')
print('embeds:', [(e.kind, e.title or e.src) for s in d.slides for e in s.embeds])
print('tables:', sum(len(s.tables) for s in d.slides))
"
```
Expected: 2 web embeds (one of them "Least-squares playground"), 2 video
embeds, and a table count that has risen by the 4 recovered `html` fallbacks.

- [ ] **Step 9: Commit**

```bash
git add src/slides/model.py src/slides/readers/deckwerk.py src/slides/writers tests/
git commit -m "feat: read and render interactive demos, video and fallback tables"
```

---

## Task 19: README, install, and the full run

**Files:**
- Create: `README.md`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: everything.
- Produces: an installed `slides` command.

- [ ] **Step 1: Write the smoke test**

```python
import sys
import subprocess
import pytest
from slides.cli import build_parser

COMMANDS = ["dump", "convert", "scaffold", "patch", "math", "theme", "info"]


@pytest.mark.parametrize("command", COMMANDS)
def test_every_subcommand_has_help(command):
    result = subprocess.run(
        [sys.executable, "-m", "slides.cli", command, "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout


def test_no_subcommand_is_still_dispatchable():
    parser = build_parser()
    action = [a for a in parser._actions if a.dest == "command"][0]
    assert set(action.choices) == set(COMMANDS)
```

- [ ] **Step 2: Run it**

Run: `pytest tests/test_smoke.py -v`
Expected: 8 passed. If `python -m slides.cli` fails, the `if __name__ == "__main__"` block from Task 1 is missing.

- [ ] **Step 3: Write `README.md`**

Cover, in this order: what the tool is in two sentences; the `uv tool install --editable .` line; a table of the seven commands with one example each; the library example (`read_deck` plus a writer, and `extract` plus `deck_style`); the `SLIDES_DECKWERK_ROOT` and `SLIDES_KEYNOTE_APP` environment variables; and a short "what this does not do" list taken from the spec's out-of-scope section. No course or project names anywhere.

- [ ] **Step 4: Install and verify the real entry point**

```bash
uv tool install --editable /Users/nikhilsingh/Desktop/Git/Other/slides
which slides
slides --help
slides info tests/fixtures/mini_deckwerk
```
Expected: `slides` resolves to a uv tool shim, help lists all seven commands, and `info` prints the inventory.

- [ ] **Step 5: Check the startup budget**

```bash
time slides --help
python -X importtime -m slides.cli --help 2>&1 | grep -E "keynote_parser|pptx|matplotlib" | head
```
Expected: help returns in well under 100ms, and the grep finds nothing.

- [ ] **Step 6: Run the whole suite**

Run: `pytest -v`
Expected: everything passes; only the tests guarded by `skipif` for a missing Keynote, DeckWerk checkout, R or sample `.key` are skipped.

- [ ] **Step 7: Commit**

```bash
git add README.md tests/test_smoke.py
git commit -m "docs: README and smoke tests"
```
