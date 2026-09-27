import sys
import re
import shutil
import pathlib
import random
import tempfile
import subprocess
import itertools
import yaml
from collections.abc import Iterator

DISPLAY = re.compile(r"\$\$(?!\s)((?:[^$\n]|\n(?!\n))+?)(?<!\s)\$\$")
INLINE = re.compile(r"(?<!\$)\$(?!\s)((?:[^$\n]|\n(?!\n))+?)(?<!\s)\$(?!\$)")
PLACEHOLDER = "\N{OBJECT REPLACEMENT CHARACTER}"
# Only used when the host paragraph's style chain does not set the property.
FALLBACK_FONT = "LibreFranklin-Thin_Regular"
FALLBACK_SIZE = 28.0
BLACK = {"a": 1.0, "b": 0.0, "g": 0.0, "model": "rgb", "r": 0.0, "rgbspace": "srgb"}
# libyaml when it is installed: several times faster on a large stylesheet.
LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
DUMPER = getattr(yaml, "CSafeDumper", yaml.SafeDumper)


def find_equations(text: str) -> list[tuple[int, int, str]]:
    # Display math first, so $$...$$ never parses as two empty inline spans.
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


def convert(
    source: str | pathlib.Path,
    out: str | pathlib.Path,
    min_slide: int = 1
) -> int:
    with tempfile.TemporaryDirectory(prefix="slides-math-") as work:
        deck = pathlib.Path(work) / "deck"
        unpack_deck(zipped(pathlib.Path(source), pathlib.Path(work)), deck)
        count = process_presentation(deck, min_slide)
        repack_deck(deck, out)
    return count


# keynote-parser CLI

def zipped(
    source: pathlib.Path,
    work: pathlib.Path
) -> pathlib.Path:
    # keynote-parser only reads zipped decks, but Keynote also saves bundles.
    if not source.is_dir():
        return source
    archive = shutil.make_archive(str(work / "source"), "zip", root_dir=source)
    return pathlib.Path(archive).rename(work / "source.key")


def unpack_deck(
    key_path: str | pathlib.Path,
    unpack_dir: str | pathlib.Path
) -> None:
    run_parser("unpack", str(key_path), "-o", str(unpack_dir))


def repack_deck(
    unpack_dir: str | pathlib.Path,
    out_path: str | pathlib.Path
) -> None:
    run_parser("pack", str(unpack_dir), "-o", str(out_path))


def run_parser(*args: str) -> None:
    # keynote-parser ships no __main__, so the module fallback is command_line.
    found = shutil.which("keynote-parser")
    command = [found] if found else [sys.executable, "-m", "keynote_parser.command_line"]
    result = subprocess.run(command + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("keynote-parser %s failed:\n%s" % (args[0], result.stderr))


# Archive edits

def process_presentation(
    unpack_dir: pathlib.Path,
    min_slide: int = 1
) -> int:
    index_dir = unpack_dir / "Index"
    meta_path = index_dir / "Metadata.iwa.yaml"
    meta = load(meta_path)
    package = meta["chunks"][0]["archives"][0]["objects"][0]
    sheet_component = next(
        comp
        for comp in package["components"]
        if comp.get("preferredLocator") == "DocumentStylesheet"
    )
    sheet_name = sheet_component.get("locator", sheet_component["preferredLocator"])
    sheet_styles = archive_objects(load(index_dir / ("%s.iwa.yaml" % (sheet_name,))))
    component, style = equation_style(sheet_component, sheet_styles)
    # New archives take identifiers above every one the deck has handed out.
    ids = (str(ident) for ident in itertools.count(int(package["lastObjectIdentifier"]) + 1))
    slide_map = get_slide_mapping(unpack_dir)
    targets = [
        slide_map[number]
        for number in range(min_slide, len(slide_map) + 1)
        if slide_map.get(number)
    ]
    modified_components: dict[str, list[str]] = {}
    total = 0
    for slide_archive_id in targets:
        # Exact names only: a bare "Slide-<id>*" glob also catches longer ids.
        slide_files = sorted(
            list(index_dir.glob("Slide-%s.iwa.yaml" % (slide_archive_id,)))
            + list(index_dir.glob("Slide-%s-*.iwa.yaml" % (slide_archive_id,)))
        )
        if not slide_files:
            continue
        slide_file = slide_files[-1]
        locator = slide_file.name.replace(".iwa.yaml", "")
        slide_data = load(slide_file)
        styles = {**sheet_styles, **archive_objects(slide_data)}
        new_archives = convert_slide(slide_data, ids, styles, style)
        if not new_archives:
            continue
        # Each equation adds an attachment, the equation, a caption and a title.
        total += len(new_archives) // 4
        slide_data["chunks"][0]["archives"].extend(new_archives)
        dump(slide_data, slide_file)
        modified_components[locator] = [arch["header"]["identifier"] for arch in new_archives]
    if modified_components:
        register_components(package, modified_components, component, style)
        dump(meta, meta_path)
    return total


def equation_style(
    sheet_component: dict,
    styles: dict[str, dict]
) -> tuple[str, str]:
    # The (stylesheet component, media style) pair every new equation points
    # at. This reuses a media style the deck already has; if Keynote needs a
    # dedicated equation style instead, this is the one place to create it.
    media = {
        obj.get("super", {}).get("styleIdentifier"): ident
        for ident, obj in styles.items()
        if obj.get("_pbtype") == "TSD.MediaStyleArchive"
    }
    for name in ("equation-0-imageStyle", "image-0-imageStyle"):
        if name in media:
            return sheet_component["identifier"], media[name]
    return sheet_component["identifier"], next(iter(media.values()))


def get_slide_mapping(unpack_dir: pathlib.Path) -> dict[int, str | None]:
    # 1-based slide number -> slide archive identifier, in presentation order.
    doc_data = load(unpack_dir / "Index" / "Document.iwa.yaml")
    archives = doc_data["chunks"][0]["archives"]
    show = next(
        obj
        for arch in archives
        for obj in arch.get("objects", [])
        if obj.get("_pbtype") == "KN.ShowArchive"
    )
    slide_nodes = [node["identifier"] for node in show["slideTree"]["slides"]]
    node_to_slide = {}
    for arch in archives:
        ident = arch["header"]["identifier"]
        if ident in slide_nodes:
            slide_ref = arch["objects"][0].get("slide", {}).get("identifier")
            if slide_ref:
                node_to_slide[ident] = str(slide_ref)
    return {number: node_to_slide.get(node) for number, node in enumerate(slide_nodes, start=1)}


def convert_slide(
    slide_data: dict,
    ids: Iterator[str],
    styles: dict[str, dict],
    style: str
) -> list[dict]:
    # Presenter notes stay plain text, so their storages are never touched.
    note_ids = note_storage_ids(slide_data)
    new_archives: list[dict] = []
    for chunk in slide_data.get("chunks", []):
        for arch in chunk.get("archives", []):
            storage_id = str(arch["header"]["identifier"])
            if storage_id in note_ids:
                continue
            for obj in arch.get("objects", []):
                if obj.get("_pbtype") != "TSWP.StorageArchive" or not obj.get("text"):
                    continue
                new_archives.extend(convert_storage(arch, obj, storage_id, ids, styles, style))
    return new_archives


def note_storage_ids(slide_data: dict) -> set[str]:
    found = set()
    for chunk in slide_data.get("chunks", []):
        for arch in chunk.get("archives", []):
            for obj in arch.get("objects", []):
                if obj.get("_pbtype") != "KN.NoteArchive":
                    continue
                for key in ("containedStorage", "ownedStorage"):
                    storage_id = obj.get(key, {}).get("identifier")
                    if storage_id:
                        found.add(str(storage_id))
    return found


def convert_storage(
    arch: dict,
    obj: dict,
    storage_id: str,
    ids: Iterator[str],
    styles: dict[str, dict],
    style: str
) -> list[dict]:
    # Keynote's character indices count UTF-16 code units, not code points.
    full_text = "".join(obj["text"])
    matches = find_equations(full_text)
    if not matches:
        return []
    obj_refs = arch["header"]["messageInfos"][0].setdefault("objectReferences", [])
    new_text_parts: list[str] = []
    shift_points: list[tuple[int, int]] = []
    new_attachments: list[dict] = []
    new_archives: list[dict] = []
    last_pos = 0
    for start, end, eq_source in matches:
        start16 = utf16_len(full_text[:start])
        shift_points.append((start16, start16 + utf16_len(full_text[start:end])))
        properties = text_properties(host_style(obj, start16), styles)
        new_text_parts.append(full_text[last_pos:start])
        curr_char_idx = utf16_len("".join(new_text_parts))
        new_text_parts.append(PLACEHOLDER)
        attach_id, eq_id, caption_id, title_id = next(ids), next(ids), next(ids), next(ids)
        obj_refs.append(attach_id)
        new_attachments.append({"characterIndex": curr_char_idx, "object": {"identifier": attach_id}})
        equation = equation_archive(
            eq_id,
            caption_id,
            title_id,
            storage_id,
            eq_source,
            style,
            properties
        )
        new_archives.append(attachment_archive(attach_id, eq_id))
        new_archives.append(equation)
        new_archives.append(caption_archive(caption_id))
        new_archives.append(caption_archive(title_id))
        last_pos = end
    new_text_parts.append(full_text[last_pos:])
    obj["text"] = ["".join(new_text_parts)]
    for key, table in obj.items():
        if key.startswith("table") and isinstance(table, dict) and "entries" in table:
            table["entries"] = remap_entries(table["entries"], shift_points)
    attachments = obj.get("tableAttachment", {}).get("entries", []) + new_attachments
    obj["tableAttachment"] = {"entries": sorted(attachments, key=lambda entry: entry["characterIndex"])}
    return new_archives


def remap_entries(
    entries: list[dict],
    shift_points: list[tuple[int, int]]
) -> list[dict]:
    # An entry that began inside a replaced span has no character left to
    # begin at (a paragraph break inside the math, say), so it is dropped.
    kept = []
    for entry in entries:
        index = remap_char_index(entry.get("characterIndex", 0), shift_points)
        if index is None:
            continue
        if "characterIndex" in entry:
            entry["characterIndex"] = index
        kept.append(entry)
    return kept


def remap_char_index(
    old_idx: int,
    shift_points: list[tuple[int, int]]
) -> int | None:
    # Each (start, end) span of the old text is now one placeholder character.
    shift = 0
    for start, end in shift_points:
        if start < old_idx < end:
            return None
        if old_idx >= end:
            shift += 1 - (end - start)
    return old_idx + shift


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


# Equation appearance, from the paragraph style the equation sits in

def host_style(
    obj: dict,
    index: int
) -> str | None:
    # An entry with no style continues the one before it; Keynote's own PDF
    # export renders those paragraphs that way.
    style_id = None
    for entry in obj.get("tableParaStyle", {}).get("entries", []):
        if entry.get("characterIndex", 0) > index:
            break
        style_id = entry.get("object", {}).get("identifier", style_id)
    return style_id


def text_properties(
    style_id: str | None,
    styles: dict[str, dict]
) -> dict:
    font = char_property(style_id, styles, "fontName") or FALLBACK_FONT
    size = char_property(style_id, styles, "fontSize") or FALLBACK_SIZE
    color = char_property(style_id, styles, "fontColor") or BLACK
    return {
        "fontColor": dict(color),
        "fontName": font,
        "fontSize": size,
        "tsdFill": {"color": dict(color)},
    }


def char_property(
    style_id: str | None,
    styles: dict[str, dict],
    prop: str
) -> object:
    # A style's own value wins, else its parent's, up the chain. Either can
    # sit behind any number of "super" wrappers.
    while style_id is not None:
        node = styles.get(style_id)
        parent = None
        while isinstance(node, dict):
            value = node.get("charProperties", {}).get(prop)
            if value is not None:
                return value
            parent = parent or node.get("parent", {}).get("identifier")
            node = node.get("super")
        style_id = parent
    return None


# New archives

def attachment_archive(
    attach_id: str,
    eq_id: str
) -> dict:
    return {
        "header": {
            "_pbtype": "TSP.ArchiveInfo",
            "identifier": attach_id,
            "messageInfos": [{"objectReferences": [eq_id], "type": 2003, "version": [1, 0, 5]}],
        },
        "objects": [{
            "_pbtype": "TSWP.DrawableAttachmentArchive",
            "drawable": {"identifier": eq_id},
            "hOffset": 0.0,
            "hOffsetType": 0,
            "vOffset": 0.0,
            "vOffsetType": 0,
        }],
    }


def equation_archive(
    eq_id: str,
    caption_id: str,
    title_id: str,
    storage_id: str,
    eq_source: str,
    style: str,
    properties: dict
) -> dict:
    return {
        "header": {
            "_pbtype": "TSP.ArchiveInfo",
            "identifier": eq_id,
            "messageInfos": [{
                "fieldInfos": [
                    {"path": {"path": [101, 46]}, "type": "Message", "unknownFieldRule": "IgnoreAndPreserve"},
                    {"path": {"path": [101]}, "type": "Message", "unknownFieldRule": "IgnoreAndPreserve"},
                    {"path": {"path": [100]}, "unknownFieldRule": "IgnoreAndPreserve"},
                    {"path": {"path": [103]}, "unknownFieldRule": "IgnoreAndPreserve"},
                    {"path": {"path": [1, 12]}, "unknownFieldRule": "IgnoreAndPreserve"},
                    {"path": {"path": [1, 13]}, "unknownFieldRule": "IgnoreAndPreserve"},
                ],
                "objectReferences": [caption_id, title_id, style],
                "type": 3005,
                "version": [1, 0, 5],
            }],
        },
        "objects": [{
            "_pbtype": "TSD.ImageArchive",
            "[TSWP.EquationInfoArchive.equation_depth]": 0.369,
            "[TSWP.EquationInfoArchive.equation_source_old]": eq_source,
            "[TSWP.EquationInfoArchive.equation_source_text]": eq_source,
            "[TSWP.EquationInfoArchive.equation_text_properties]": properties,
            "flags": 0,
            "interpretsUntaggedImageDataAsGeneric": False,
            "naturalSize": {"height": 25.0, "width": 80.0},
            "originalSize": {"height": 25.0, "width": 80.0},
            "style": {"identifier": style},
            "super": {
                "aspectRatioLocked": True,
                "caption": {"identifier": caption_id},
                "captionHidden": False,
                "exteriorTextWrap": {
                    "alphaThreshold": 0.5,
                    "direction": 2,
                    "fitType": 1,
                    "isHtmlWrap": False,
                    "margin": 12.0,
                    "type": 0,
                },
                "geometry": {
                    "angle": 0.0,
                    "flags": 3,
                    "position": {"x": 0.0, "y": 0.0},
                    "size": {"height": 25.0, "width": 80.0},
                },
                "locked": False,
                "parent": {"identifier": storage_id},
                "title": {"identifier": title_id},
                "titleHidden": False,
            },
        }],
    }


def caption_archive(ident: str) -> dict:
    return {
        "header": {
            "_pbtype": "TSP.ArchiveInfo",
            "identifier": ident,
            "messageInfos": [{"type": 3097, "version": [10, 1, 0]}],
        },
        "objects": [{"_pbtype": "TSD.StandinCaptionArchive"}],
    }


# Component metadata: without these declarations Keynote offers to repair the file.

def register_components(
    package: dict,
    modified_components: dict[str, list[str]],
    component: str,
    style: str
) -> None:
    new_ids = [int(ident) for idents in modified_components.values() for ident in idents]
    package["lastObjectIdentifier"] = str(max(new_ids))
    for comp in package["components"]:
        if comp.get("locator") in modified_components:
            register_component(comp, modified_components[comp["locator"]], component, style)


def register_component(
    comp: dict,
    new_ids: list[str],
    component: str,
    style: str
) -> None:
    comp["documentReadVersion"] = [4, 1, 0]
    comp["documentWriteVersion"] = [4, 1, 0]
    features = comp.setdefault("featureInfos", [])
    feat_ids = set(feature.get("identifier") for feature in features)
    if "TSWPEquations" not in feat_ids:
        features.append({"identifier": "TSWPEquations", "readVersion": [2, 0, 0], "writeVersion": [2, 1, 0]})
    if "TSWPInlineDrawables" not in feat_ids:
        features.append({"identifier": "TSWPInlineDrawables", "readVersion": [4, 1, 0], "writeVersion": [4, 1, 0]})
    ext_refs = comp.setdefault("externalReferences", [])
    if not any(ref.get("objectIdentifier") == style for ref in ext_refs):
        ext_refs.append({"componentIdentifier": component, "objectIdentifier": style})
    uuid_entries = comp.setdefault("objectUuidMapEntries", [])
    for ident in new_ids:
        uuid = {"lower": str(random.getrandbits(64)), "upper": str(random.getrandbits(64))}
        uuid_entries.append({"identifier": ident, "uuid": uuid})


# YAML

def load(path: pathlib.Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=LOADER)


def dump(
    data: dict,
    path: pathlib.Path
) -> None:
    path.write_text(yaml.dump(data, Dumper=DUMPER), encoding="utf-8")


def archive_objects(data: dict) -> dict[str, dict]:
    return {
        str(arch["header"]["identifier"]): arch["objects"][0]
        for chunk in data["chunks"]
        for arch in chunk["archives"]
        if arch.get("objects")
    }
