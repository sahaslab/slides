import sys
import os
import shutil
import subprocess
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


@pytest.mark.parametrize(
    "text",
    [
        "$5-$10",
        "$10k\N{EN DASH}$20k",
        "$5,$6",
        "US$5 vs US$6",
        "\\$5 and \\$6",
        "$20,000 to $500,000",
        "$10 now or $14",
    ],
)
def test_leaves_currency_alone(text: str) -> None:
    assert math.find_equations(text) == []


def test_an_escaped_dollar_can_sit_inside_math() -> None:
    assert math.find_equations("cost in $\\$^2$ units") == [(8, 14, "\\$^2")]


def test_importing_the_converter_leaves_yaml_unloaded() -> None:
    code = "import sys; import slides.keynote.math; print(\"yaml\" in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# Storage edits, on hand-built archives

def test_places_an_equation_after_an_emoji_in_utf16_units() -> None:
    # The emoji is two UTF-16 units, so the placeholder lands at 3, not 2.
    arch, obj = storage("\N{BAR CHART} $N$\nnext", [0, 7])
    math.convert_storage(arch, obj, "1", iter(["10", "11", "12", "13"]), {}, "99", 1)
    assert obj["tableAttachment"]["entries"] == [{"characterIndex": 3, "object": {"identifier": "10"}}]
    assert utf16_at(obj["text"][0], 3) == math.PLACEHOLDER
    assert indices(obj["tableParaStyle"]) == [0, 5]


def test_a_run_that_starts_inside_the_math_resumes_after_it() -> None:
    # Bold starts at "+", so " now" was bold and has to stay bold.
    arch, obj = storage("see $a+b$ now", [0])
    obj["tableCharStyle"] = {"entries": [{"characterIndex": 0}, {"characterIndex": 6, "object": {"identifier": "bold"}}]}
    obj["tableListStyle"] = {"entries": [{"characterIndex": 0}, {"characterIndex": 7}]}
    math.convert_storage(arch, obj, "1", iter(["10", "11", "12", "13"]), {}, "99", 1)
    assert obj["text"] == ["see %s now" % (math.PLACEHOLDER,)]
    assert obj["tableCharStyle"]["entries"] == [{"characterIndex": 0}, {"characterIndex": 5, "object": {"identifier": "bold"}}]
    assert indices(obj["tableListStyle"]) == [0]


def test_a_later_run_at_the_same_place_wins() -> None:
    arch, obj = storage("see $a+b$ now", [0])
    entries = [{"characterIndex": 0}, {"characterIndex": 6, "object": {"identifier": "bold"}}, {"characterIndex": 9}]
    obj["tableCharStyle"] = {"entries": entries}
    math.convert_storage(arch, obj, "1", iter(["10", "11", "12", "13"]), {}, "99", 1)
    assert obj["tableCharStyle"]["entries"] == [{"characterIndex": 0}, {"characterIndex": 5}]


def test_math_across_a_paragraph_break_is_left_as_text(capsys: pytest.CaptureFixture) -> None:
    arch, obj = storage("a $x\ny$ b", [0, 5])
    assert math.convert_storage(arch, obj, "1", iter(["10", "11", "12", "13"]), {}, "99", 7) == []
    assert obj["text"] == ["a $x\ny$ b"]
    assert indices(obj["tableParaStyle"]) == [0, 5]
    assert "slide 7" in capsys.readouterr().err


def test_shifts_existing_attachments_past_the_math() -> None:
    arch, obj = storage("$x$ and %s" % (math.PLACEHOLDER,), [0])
    obj["tableAttachment"] = {"entries": [{"characterIndex": 8, "object": {"identifier": "5"}}]}
    math.convert_storage(arch, obj, "1", iter(["10", "11", "12", "13"]), {}, "99", 1)
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


def test_a_paragraph_without_a_style_continues_the_one_before() -> None:
    # Keynote's own PDF export renders such paragraphs in the previous style.
    arch, obj = storage("first\nthen $x$", [0])
    obj["tableParaStyle"]["entries"].append({"characterIndex": 6})
    styles = {"p": {"charProperties": {"fontName": "Avenir", "fontSize": 40.0, "fontColor": WHITE}}}
    added = math.convert_storage(arch, obj, "1", iter(["10", "11", "12", "13"]), styles, "99", 1)
    properties = added[1]["objects"][0][PROPERTIES]
    assert (properties["fontName"], properties["fontSize"], properties["fontColor"]) == ("Avenir", 40.0, WHITE)


def test_unresolved_appearance_falls_back_to_black_system_text() -> None:
    properties = math.text_properties(None, {})
    assert (properties["fontName"], properties["fontSize"]) == ("HelveticaNeue", math.FALLBACK_SIZE)
    assert properties["fontColor"] == math.BLACK


def test_new_ids_start_above_every_identifier_in_use(tmp_path: pathlib.Path) -> None:
    # A deck whose recorded counter lags behind an identifier it already uses.
    (tmp_path / "Tables").mkdir()
    (tmp_path / "Slide-1.iwa.yaml").write_text("- header:\n    identifier: '40'\n", encoding="utf-8")
    (tmp_path / "Tables" / "DataList-2.iwa.yaml").write_text("    identifier: '75'\n", encoding="utf-8")
    # Deck 06's Metadata holds a UUID-shaped identifier that is not an object id.
    (tmp_path / "Metadata.iwa.yaml").write_text("  identifier: 45335732-691B-4B8B-A714-13A7D1EEA0AC\n", encoding="utf-8")
    assert math.first_free_id(tmp_path, {"lastObjectIdentifier": "50"}) == 76
    assert math.first_free_id(tmp_path, {"lastObjectIdentifier": "90"}) == 91


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
def test_presenter_notes_are_untouched(converted: Converted) -> None:
    out, _, _ = converted
    before = archives(REAL)
    after = archives(out)
    notes = [
        obj[key]["identifier"]
        for obj in before.values()
        if obj.get("_pbtype") == "KN.NoteArchive"
        for key in ("containedStorage", "ownedStorage")
        if key in obj
    ]
    assert any("$" in "".join(before[ident].get("text") or []) for ident in notes)
    assert all(after[ident] == before[ident] for ident in notes)


@needs_real
def test_equations_take_their_host_paragraph_appearance(converted: Converted) -> None:
    out, _, _ = converted
    equations = {obj[SOURCE_TEXT]: obj[PROPERTIES] for obj in archives(out).values() if SOURCE_TEXT in obj}
    display = equations["\\text{df}_t = |\\{d \\in D : t \\in d\\}|"]
    assert (display["fontName"], display["fontSize"]) == ("STIXTwoMath-Regular", 38.0)
    assert min(display["fontColor"][channel] for channel in "rgb") > 0.99
    # Every host paragraph in this deck has a resolvable style, so none falls back.
    assert all(properties["fontName"] != math.FALLBACK_FONT for properties in equations.values())


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


@pytest.mark.parametrize(
    "output",
    [
        None,
        "deck.key",
    ],
)
def test_command_refuses_to_overwrite(
    output: str | None,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture
) -> None:
    # None: the default deck-math.key already exists. "deck.key": the source itself.
    source = tmp_path / "deck.key"
    source.write_bytes(b"not really a deck")
    (tmp_path / "deck-math.key").write_bytes(b"an earlier conversion")
    before = digest(source)
    out = tmp_path / output if output else None
    args = argparse.Namespace(target=str(source), output=str(out) if out else None, min_slide=1)
    assert math_command.run(args) == 1
    expected = out if out else tmp_path / "deck-math.key"
    assert capsys.readouterr().err == "%s already exists; pass -o with a new path\n" % (expected,)
    assert digest(source) == before
    assert (tmp_path / "deck-math.key").read_bytes() == b"an earlier conversion"


def test_command_refuses_an_output_that_is_not_a_key_file(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture
) -> None:
    source = tmp_path / "deck.key"
    source.write_bytes(b"not really a deck")
    args = argparse.Namespace(target=str(source), output=str(tmp_path / "converted"), min_slide=1)
    assert math_command.run(args) == 1
    assert "does not end in .key" in capsys.readouterr().err
    assert not (tmp_path / "converted").exists()


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
