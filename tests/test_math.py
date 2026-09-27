import os
import shutil
import hashlib
import pathlib
import zipfile
import argparse
import pytest
from keynote_parser.codec import IWAFile
from slides.keynote import math
from slides.commands import math as math_command
from slides.readers.keynote_file import archives, read

REAL = pathlib.Path(os.path.expanduser(
    "~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote"
    "/09_oct14_tfidf_imbalance_eval.key"
))
needs_real = pytest.mark.skipif(not REAL.exists(), reason="no sample .key")
SOURCE_TEXT = "[TSWP.EquationInfoArchive.equation_source_text]"
PROPERTIES = "[TSWP.EquationInfoArchive.equation_text_properties]"
WHITE = {"a": 1.0, "b": 1.0, "g": 1.0, "model": "rgb", "r": 1.0, "rgbspace": "srgb"}
Converted = tuple[pathlib.Path, int, str]


def test_finds_inline_math() -> None:
    found = math.find_equations("Let $N$ be the count.")
    assert found == [(4, 7, "N")]


def test_finds_display_math_before_inline() -> None:
    found = math.find_equations("Before $$a + b$$ after")
    assert found == [(7, 16, "a + b")]


def test_finds_several_in_order() -> None:
    found = math.find_equations("$a$ then $$b$$ then $c$")
    assert [latex for _, _, latex in found] == ["a", "b", "c"]


def test_ignores_bare_dollars_and_currency() -> None:
    assert math.find_equations("costs $5 and $10 per unit") == []
    assert math.find_equations("no math here") == []


def test_does_not_match_across_a_blank_line() -> None:
    assert math.find_equations("$start\n\nend$") == []


# Storage edits, on hand-built archives

def test_places_an_equation_after_an_emoji_in_utf16_units() -> None:
    # The emoji is two UTF-16 units, so the placeholder lands at 3, not 2.
    arch, obj = storage("\N{BAR CHART} $N$\nnext", [0, 7])
    math.convert_storage(arch, obj, "1", iter(["10", "11", "12", "13"]), {}, "99")
    assert obj["tableAttachment"]["entries"] == [{"characterIndex": 3, "object": {"identifier": "10"}}]
    assert utf16_at(obj["text"][0], 3) == math.PLACEHOLDER
    assert indices(obj["tableParaStyle"]) == [0, 5]


def test_drops_entries_that_began_inside_the_math() -> None:
    arch, obj = storage("a $x\ny$ b", [0, 5])
    obj["tableCharStyle"] = {"entries": [{"characterIndex": 0}, {"characterIndex": 8}]}
    math.convert_storage(arch, obj, "1", iter(["10", "11", "12", "13"]), {}, "99")
    assert obj["text"] == ["a %s b" % (math.PLACEHOLDER,)]
    assert indices(obj["tableParaStyle"]) == [0]
    assert indices(obj["tableCharStyle"]) == [0, 4]


def test_shifts_existing_attachments_past_the_math() -> None:
    arch, obj = storage("$x$ and %s" % (math.PLACEHOLDER,), [0])
    obj["tableAttachment"] = {"entries": [{"characterIndex": 8, "object": {"identifier": "5"}}]}
    math.convert_storage(arch, obj, "1", iter(["10", "11", "12", "13"]), {}, "99")
    assert indices(obj["tableAttachment"]) == [0, 6]
    assert all(utf16_at(obj["text"][0], index) == math.PLACEHOLDER for index in [0, 6])


def test_resolves_appearance_through_the_parent_chain() -> None:
    styles = {
        "child": {"charProperties": {"fontSize": 40.0}, "super": {"parent": {"identifier": "base"}}},
        "base": {"charProperties": {"fontName": "Avenir", "fontColor": WHITE}},
    }
    properties = math.text_properties("child", styles)
    assert (properties["fontName"], properties["fontSize"]) == ("Avenir", 40.0)
    assert properties["fontColor"] == WHITE
    assert properties["tsdFill"] == {"color": WHITE}


def test_unresolved_appearance_falls_back_to_black() -> None:
    properties = math.text_properties(None, {})
    assert (properties["fontName"], properties["fontSize"]) == (math.FALLBACK_FONT, math.FALLBACK_SIZE)
    assert properties["fontColor"] == math.BLACK


def test_prefers_an_equation_style_then_the_image_style() -> None:
    image = {"_pbtype": "TSD.MediaStyleArchive", "super": {"styleIdentifier": "image-0-imageStyle"}}
    equation = {"_pbtype": "TSD.MediaStyleArchive", "super": {"styleIdentifier": "equation-0-imageStyle"}}
    sheet = {"identifier": "9"}
    assert math.equation_style(sheet, {"1": image, "2": equation}) == ("9", "2")
    assert math.equation_style(sheet, {"1": image}) == ("9", "1")


# The sample deck

@pytest.fixture(scope="module")
def converted(tmp_path_factory: pytest.TempPathFactory) -> Converted:
    before = digest(REAL)
    out = tmp_path_factory.mktemp("math") / "converted.key"
    count = math.convert(REAL, out, min_slide=1)
    return out, count, before


@pytest.fixture(scope="module")
def late(tmp_path_factory: pytest.TempPathFactory) -> tuple[pathlib.Path, int]:
    out = tmp_path_factory.mktemp("late") / "late.key"
    return out, math.convert(REAL, out, min_slide=20)


@needs_real
def test_converts_and_produces_an_openable_deck(converted: Converted) -> None:
    out, count, before = converted
    assert count > 0
    assert out.exists()
    deck = read(out)
    assert len(deck.slides) == len(read(REAL).slides)
    assert digest(REAL) == before


@needs_real
def test_every_equation_sits_on_a_placeholder(converted: Converted) -> None:
    out, count, _ = converted
    index = archives(out)
    equations = [obj for obj in index.values() if SOURCE_TEXT in obj]
    assert len(equations) == count
    assert all("$" not in obj[SOURCE_TEXT] for obj in equations)
    placed = 0
    for obj in index.values():
        if obj.get("_pbtype") != "TSWP.StorageArchive":
            continue
        text = "".join(obj.get("text") or [])
        for entry in obj.get("tableAttachment", {}).get("entries", []):
            assert utf16_at(text, entry["characterIndex"]) == math.PLACEHOLDER
            placed += 1
    assert placed >= count


@needs_real
def test_no_style_or_attachment_index_runs_past_its_text(converted: Converted) -> None:
    out, _, _ = converted
    for obj in archives(out).values():
        if obj.get("_pbtype") != "TSWP.StorageArchive":
            continue
        length = math.utf16_len("".join(obj.get("text") or []))
        for key, table in obj.items():
            if key.startswith("table") and isinstance(table, dict):
                found = indices(table)
                assert found == sorted(set(found))
                assert all(index <= length for index in found)


@needs_real
def test_equations_take_their_host_paragraph_appearance(converted: Converted) -> None:
    out, _, _ = converted
    equations = {obj[SOURCE_TEXT]: obj[PROPERTIES] for obj in archives(out).values() if SOURCE_TEXT in obj}
    display = equations["\\text{df}_t = |\\{d \\in D : t \\in d\\}|"]
    assert (display["fontName"], display["fontSize"]) == ("STIXTwoMath-Regular", 38.0)
    assert min(display["fontColor"][channel] for channel in "rgb") > 0.99


@needs_real
def test_new_ids_collide_with_nothing(converted: Converted) -> None:
    out, _, _ = converted
    ids = archive_ids(out)
    assert len(ids) == len(set(ids))
    package = next(obj for obj in archives(out).values() if obj.get("_pbtype") == "TSP.PackageMetadata")
    assert max(int(ident) for ident in ids) <= int(package["lastObjectIdentifier"])


@needs_real
def test_converting_its_own_output_adds_no_duplicate_ids(
    converted: Converted,
    late: tuple[pathlib.Path, int],
    tmp_path: pathlib.Path
) -> None:
    _, everything, _ = converted
    late_out, first = late
    second = math.convert(late_out, tmp_path / "all.key", min_slide=1)
    assert first + second == everything
    ids = archive_ids(tmp_path / "all.key")
    assert len(ids) == len(set(ids))


@needs_real
def test_min_slide_protects_leading_slides(
    converted: Converted,
    late: tuple[pathlib.Path, int]
) -> None:
    _, everything, _ = converted
    _, protected = late
    assert protected < everything


@needs_real
def test_converts_a_directory_bundle_into_a_zipped_deck(
    converted: Converted,
    tmp_path: pathlib.Path
) -> None:
    bundle = tmp_path / "bundle.key"
    with zipfile.ZipFile(REAL) as package:
        package.extractall(bundle)
    out = tmp_path / "from-bundle.key"
    assert math.convert(bundle, out) == converted[1]
    assert zipfile.is_zipfile(out)


@needs_real
def test_command_defaults_to_a_suffixed_copy(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture
) -> None:
    source = tmp_path / "deck.key"
    shutil.copy(REAL, source)
    before = digest(source)
    args = argparse.Namespace(target=str(source), output=None, min_slide=1)
    assert math_command.run(args) == 0
    out = tmp_path / "deck-math.key"
    assert out.exists()
    assert capsys.readouterr().out.strip() == str(out)
    assert digest(source) == before


# Helpers

def storage(
    text: str,
    para_starts: list[int]
) -> tuple[dict, dict]:
    arch = {"header": {"identifier": "1", "messageInfos": [{}]}}
    entries = [{"characterIndex": index, "object": {"identifier": "p"}} for index in para_starts]
    obj = {"_pbtype": "TSWP.StorageArchive", "text": [text], "tableParaStyle": {"entries": entries}}
    return arch, obj


def indices(table: dict) -> list[int]:
    return [entry.get("characterIndex", 0) for entry in table.get("entries", [])]


def utf16_at(
    text: str,
    index: int
) -> str:
    return text.encode("utf-16-le")[2 * index:2 * index + 2].decode("utf-16-le")


def archive_ids(path: pathlib.Path) -> list[str]:
    ids = []
    with zipfile.ZipFile(path) as package:
        for name in package.namelist():
            if name.endswith(".iwa"):
                parsed = IWAFile.from_buffer(package.read(name), name).to_dict()
                ids.extend(arch["header"]["identifier"] for chunk in parsed["chunks"] for arch in chunk["archives"])
    return ids


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
