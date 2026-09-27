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
FIRST_ID = 820000
PARA_TABLES = (
    "tableParaStyle",
    "tableParaStarts",
    "tableParaBidi",
    "tableParaData",
    "tableListStyle",
    "tableDropCapStyle",
)
# The equation media style and the stylesheet component holding it, kept as
# apply_headless_equations.py found them empirically.
EQUATION_STYLE = "15056"
STYLESHEET_COMPONENT = "7907"


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
        unpack_deck(source, work)
        count = process_presentation(pathlib.Path(work), min_slide)
        repack_deck(work, out)
    return count


# keynote-parser CLI

def unpack_deck(key_path: str | pathlib.Path, unpack_dir: str | pathlib.Path) -> None:
    run_parser("unpack", str(key_path), "-o", str(unpack_dir))


def repack_deck(unpack_dir: str | pathlib.Path, out_path: str | pathlib.Path) -> None:
    run_parser("pack", str(unpack_dir), "-o", str(out_path))


def run_parser(*args: str) -> None:
    # keynote-parser ships no __main__, so the module fallback is command_line.
    found = shutil.which("keynote-parser")
    command = [found] if found else [sys.executable, "-m", "keynote_parser.command_line"]
    result = subprocess.run(command + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("keynote-parser %s failed:\n%s" % (args[0], result.stderr))


# Archive edits

def process_presentation(unpack_dir: pathlib.Path, min_slide: int = 1) -> int:
    index_dir = unpack_dir / "Index"
    slide_map = get_slide_mapping(unpack_dir)
    targets = [
        slide_map[number]
        for number in range(min_slide, len(slide_map) + 1)
        if slide_map.get(number)
    ]
    ids = (str(ident) for ident in itertools.count(FIRST_ID))
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
        slide_data = yaml.safe_load(slide_file.read_text(encoding="utf-8"))
        new_archives = convert_slide(slide_data, ids)
        if not new_archives:
            continue
        # Each equation adds an attachment, the equation, a caption and a title.
        total += len(new_archives) // 4
        slide_data["chunks"][0]["archives"].extend(new_archives)
        slide_file.write_text(yaml.safe_dump(slide_data), encoding="utf-8")
        modified_components[locator] = [arch["header"]["identifier"] for arch in new_archives]
    if modified_components:
        register_components(index_dir / "Metadata.iwa.yaml", modified_components)
    return total


def get_slide_mapping(unpack_dir: pathlib.Path) -> dict[int, str | None]:
    # 1-based slide number -> slide archive identifier, in presentation order.
    doc_path = unpack_dir / "Index" / "Document.iwa.yaml"
    doc_data = yaml.safe_load(doc_path.read_text(encoding="utf-8"))
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


def convert_slide(slide_data: dict, ids: Iterator[str]) -> list[dict]:
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
                new_archives.extend(convert_storage(arch, obj, storage_id, ids))
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
    ids: Iterator[str]
) -> list[dict]:
    full_text = "".join(obj["text"])
    matches = find_equations(full_text)
    if not matches:
        return []
    obj_refs = arch["header"]["messageInfos"][0].setdefault("objectReferences", [])
    all_attachments = list(obj.get("tableAttachment", {}).get("entries", []))
    new_text_parts: list[str] = []
    shift_points: list[tuple[int, int]] = []
    new_archives: list[dict] = []
    last_pos = 0
    for start, end, eq_source in matches:
        new_text_parts.append(full_text[last_pos:start])
        curr_char_idx = sum(len(part) for part in new_text_parts)
        new_text_parts.append(PLACEHOLDER)
        shift_points.append((start, len(PLACEHOLDER) - (end - start)))
        attach_id, eq_id, caption_id, title_id = next(ids), next(ids), next(ids), next(ids)
        obj_refs.append(attach_id)
        all_attachments.append({"characterIndex": curr_char_idx, "object": {"identifier": attach_id}})
        new_archives.extend([
            attachment_archive(attach_id, eq_id),
            equation_archive(eq_id, caption_id, title_id, storage_id, eq_source),
            caption_archive(caption_id),
            caption_archive(title_id),
        ])
        last_pos = end
    new_text_parts.append(full_text[last_pos:])
    obj["text"] = ["".join(new_text_parts)]
    all_attachments.sort(key=lambda entry: entry["characterIndex"])
    obj["tableAttachment"] = {"entries": all_attachments}
    for key in PARA_TABLES:
        for entry in obj.get(key, {}).get("entries", []):
            if entry.get("characterIndex", 0) > 0:
                entry["characterIndex"] = remap_char_index(entry["characterIndex"], shift_points)
    return new_archives


def remap_char_index(old_idx: int, shift_points: list[tuple[int, int]]) -> int:
    shift = sum(delta for pos, delta in shift_points if old_idx > pos)
    return max(0, old_idx + shift)


# New archives

def attachment_archive(attach_id: str, eq_id: str) -> dict:
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
    eq_source: str
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
                "objectReferences": [caption_id, title_id, EQUATION_STYLE],
                "type": 3005,
                "version": [1, 0, 5],
            }],
        },
        "objects": [{
            "_pbtype": "TSD.ImageArchive",
            "[TSWP.EquationInfoArchive.equation_depth]": 0.369,
            "[TSWP.EquationInfoArchive.equation_source_old]": eq_source,
            "[TSWP.EquationInfoArchive.equation_source_text]": eq_source,
            "[TSWP.EquationInfoArchive.equation_text_properties]": {
                "fontColor": text_color(),
                "fontName": "LibreFranklin-Thin_Regular",
                "fontSize": 28.0,
                "tsdFill": {"color": text_color()},
            },
            "flags": 0,
            "interpretsUntaggedImageDataAsGeneric": False,
            "naturalSize": {"height": 25.0, "width": 80.0},
            "originalSize": {"height": 25.0, "width": 80.0},
            "style": {"identifier": EQUATION_STYLE},
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


def text_color() -> dict:
    return {"a": 1.0, "b": 0.9447617, "g": 0.9561592, "model": "rgb", "r": 0.9317923, "rgbspace": "srgb"}


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
    meta_path: pathlib.Path,
    modified_components: dict[str, list[str]]
) -> None:
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    for chunk in meta.get("chunks", []):
        for arch in chunk.get("archives", []):
            for comp in arch.get("objects", [])[0].get("components", []):
                if comp.get("locator") in modified_components:
                    register_component(comp, modified_components[comp["locator"]])
    meta_path.write_text(yaml.safe_dump(meta), encoding="utf-8")


def register_component(comp: dict, new_ids: list[str]) -> None:
    comp["documentReadVersion"] = [4, 1, 0]
    comp["documentWriteVersion"] = [4, 1, 0]
    features = comp.setdefault("featureInfos", [])
    feat_ids = set(feature.get("identifier") for feature in features)
    if "TSWPEquations" not in feat_ids:
        features.append({"identifier": "TSWPEquations", "readVersion": [2, 0, 0], "writeVersion": [2, 1, 0]})
    if "TSWPInlineDrawables" not in feat_ids:
        features.append({"identifier": "TSWPInlineDrawables", "readVersion": [4, 1, 0], "writeVersion": [4, 1, 0]})
    ext_refs = comp.setdefault("externalReferences", [])
    if not any(ref.get("objectIdentifier") == EQUATION_STYLE for ref in ext_refs):
        ext_refs.append({"componentIdentifier": STYLESHEET_COMPONENT, "objectIdentifier": EQUATION_STYLE})
    uuid_entries = comp.setdefault("objectUuidMapEntries", [])
    for ident in new_ids:
        uuid_entries.append({
            "identifier": ident,
            "uuid": {"lower": str(random.getrandbits(64)), "upper": str(random.getrandbits(64))},
        })
