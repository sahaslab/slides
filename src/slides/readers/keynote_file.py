import re
import pathlib
import zipfile
import warnings
from collections.abc import Iterator
from slides.model import ColorUse, Deck, Slide, TextItem

STORAGE_KEYS = ("ownedStorage", "deprecatedStorage", "containedStorage")
TITLE_KIND = "kKindTitlePlaceholder"
WHITESPACE = re.compile(r"[    ]+")
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
    for obj in index.values():
        _harvest_colors(obj, colors)
    order = show.get("slideTree", {}).get("slides", [])
    for number, node_ref in enumerate(order, start=1):
        node = index.get(node_ref["identifier"])
        if node is None:
            continue
        slide_id = node.get("slide", {}).get("identifier")
        raw = index.get(slide_id)
        if raw is None:
            continue
        deck.slides.append(_slide(number, raw, index))
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


def _streams(root: pathlib.Path) -> Iterator[tuple[str, bytes]]:
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


def _slide(number: int, raw: dict, index: dict) -> Slide:
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


def _harvest_colors(node: object, colors: dict, weight: float = 1.0) -> None:
    if isinstance(node, dict):
        if {"r", "g", "b"} <= set(node.keys()):
            value = "#%02x%02x%02x" % tuple(
                max(0, min(255, int(round(float(node[k]) * 255))))
                for k in ("r", "g", "b")
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
