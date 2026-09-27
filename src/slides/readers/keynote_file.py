import re
import pathlib
import zipfile
import warnings
from collections.abc import Iterator
from slides.model import ColorUse, Deck, Slide, TextItem

STORAGE_KEYS = ("ownedStorage", "deprecatedStorage", "containedStorage")
WHITESPACE = re.compile(r"[    ]+")
BLANK_LINES = re.compile(r"\n{2,}")


def read(
    path: str | pathlib.Path,
    via_deckwerk: bool = False,
) -> Deck:
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


def _first(
    index: dict[str, dict],
    pbtype: str,
) -> dict:
    for obj in index.values():
        if obj.get("_pbtype") == pbtype:
            return obj
    raise ValueError("no %s in this deck" % (pbtype,))


def _slide(
    number: int,
    raw: dict,
    index: dict,
    colors: dict,
) -> Slide:
    slide = Slide(number=number)
    slide.background = _resolve_background(raw, index, colors)
    title_id = raw.get("titlePlaceholder", {}).get("identifier")
    for ref in raw.get("drawablesZOrder", []):
        drawable_id = ref["identifier"]
        drawable = index.get(drawable_id)
        storage = _storage_of(drawable, index) if drawable is not None else None
        _harvest_fill(drawable, index, colors)
        if storage is not None:
            _harvest_text_colors(storage, index, colors)
        text = clean(_text_from_storage(storage))
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


def _text_of(
    drawable: dict | None,
    index: dict,
) -> str:
    if drawable is None:
        return ""
    return _text_from_storage(_storage_of(drawable, index))


def _text_from_storage(storage: dict | None) -> str:
    if storage is None:
        return ""
    return "".join(storage.get("text") or [])


def _storage_of(
    drawable: dict,
    index: dict,
) -> dict | None:
    for holder in (drawable, drawable.get("super") or {}):
        for key in STORAGE_KEYS:
            ref = holder.get(key)
            if isinstance(ref, dict) and "identifier" in ref:
                return index.get(ref["identifier"])
    return None


def _resolve_background(
    raw: dict,
    index: dict,
    colors: dict,
) -> str | None:
    style_id = raw.get("style", {}).get("identifier")
    found, color = _resolve_color(style_id, index, "slideProperties", "fill")
    if not found:
        # The slide's own style chain never mentions a fill at all -- only
        # then does it fall back to inheriting its master's. A style chain
        # that DOES mention a fill (even a non-solid one, found=True with
        # color=None) must not fall back: that fill was deliberately set.
        template = index.get(raw.get("templateSlide", {}).get("identifier")) or {}
        template_style_id = template.get("style", {}).get("identifier")
        _, color = _resolve_color(template_style_id, index, "slideProperties", "fill")
    if color is None:
        return None
    hexvalue = _to_hex(color)
    colors[(hexvalue, "background")] = colors.get((hexvalue, "background"), 0.0) + 1.0
    return hexvalue


def _harvest_fill(
    drawable: dict | None,
    index: dict,
    colors: dict,
) -> None:
    if drawable is None:
        return
    style_id = _style_ref(drawable)
    if style_id is None:
        return
    _, color = _resolve_color(style_id, index, "shapeProperties", "fill")
    if color is None:
        return
    hexvalue = _to_hex(color)
    colors[(hexvalue, "fill")] = colors.get((hexvalue, "fill"), 0.0) + 1.0


def _harvest_text_colors(
    storage: dict,
    index: dict,
    colors: dict,
) -> None:
    text_length = sum(len(run) for run in (storage.get("text") or []))
    if text_length == 0:
        return
    entries = sorted(
        storage.get("tableParaStyle", {}).get("entries", []),
        key=lambda entry: entry["characterIndex"],
    )
    for position, entry in enumerate(entries):
        start = entry["characterIndex"]
        end = (
            entries[position + 1]["characterIndex"]
            if position + 1 < len(entries)
            else text_length
        )
        length = end - start
        if length <= 0:
            continue
        style_id = entry.get("object", {}).get("identifier")
        if style_id is None:
            continue
        _, color = _resolve_color(style_id, index, "charProperties", "fontColor")
        if color is None:
            continue
        hexvalue = _to_hex(color)
        weight = colors.get((hexvalue, "text"), 0.0)
        colors[(hexvalue, "text")] = weight + float(length)


def _style_ref(drawable: dict) -> str | None:
    # A drawable's own shape style sits behind a chain of base-class "super"
    # wrappers whose depth varies by drawable type (placeholders wrap one
    # more level than plain shapes), so walk down looking for it.
    node = drawable
    while isinstance(node, dict):
        ref = node.get("style")
        if isinstance(ref, dict) and "identifier" in ref:
            return ref["identifier"]
        node = node.get("super")
    return None


def _style_parent(style: dict) -> str | None:
    # Likewise, a style's "parent" (its named/master style, one level up the
    # override chain) sits behind a variable number of "super" wrappers.
    node = style
    while isinstance(node, dict):
        parent = node.get("parent")
        if isinstance(parent, dict) and "identifier" in parent:
            return parent["identifier"]
        node = node.get("super")
    return None


def _color_at(
    node: dict,
    group: str,
    prop: str,
) -> tuple[bool, dict | None]:
    props = node.get(group)
    if not isinstance(props, dict):
        return False, None
    if prop == "fill":
        if "fill" not in props:
            return False, None
        fill = props["fill"]
        color = fill.get("color") if isinstance(fill, dict) else None
    else:
        if prop not in props:
            return False, None
        color = props[prop]
    if isinstance(color, dict) and {"r", "g", "b"} <= set(color.keys()):
        return True, color
    # The property is set at this level but isn't a solid colour (an image
    # or gradient fill, or an explicit null) -- stop, don't inherit a stale
    # colour from a parent style this level deliberately overrode.
    return True, None


def _resolve_color(
    style_id: str | None,
    index: dict,
    group: str,
    prop: str,
) -> tuple[bool, dict | None]:
    seen: set[str] = set()
    while style_id is not None and style_id not in seen:
        seen.add(style_id)
        style = index.get(style_id)
        if style is None:
            return False, None
        node = style
        while isinstance(node, dict):
            found, color = _color_at(node, group, prop)
            if found:
                return True, color
            node = node.get("super")
        style_id = _style_parent(style)
    return False, None


def _to_hex(color: dict) -> str:
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, int(round(float(color[k]) * 255))))
        for k in ("r", "g", "b")
    )


def clean(text: str) -> str:
    # ￼ is the object-replacement character Keynote leaves where an image,
    # equation or other inline drawable sits inside a text run.
    text = text.replace("￼", "")
    text = WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return BLANK_LINES.sub("\n", text).strip()
