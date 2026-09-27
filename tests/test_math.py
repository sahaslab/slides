import os
import shutil
import hashlib
import pathlib
import argparse
import pytest
from slides.keynote import math
from slides.commands import math as math_command
from slides.readers.keynote_file import archives, read

REAL = pathlib.Path(os.path.expanduser(
    "~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote"
    "/09_oct14_tfidf_imbalance_eval.key"
))
needs_real = pytest.mark.skipif(not REAL.exists(), reason="no sample .key")
SOURCE_TEXT = "[TSWP.EquationInfoArchive.equation_source_text]"
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


@pytest.fixture(scope="module")
def converted(tmp_path_factory: pytest.TempPathFactory) -> Converted:
    before = digest(REAL)
    out = tmp_path_factory.mktemp("math") / "converted.key"
    count = math.convert(REAL, out, min_slide=1)
    return out, count, before


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
            assert text[entry["characterIndex"]] == math.PLACEHOLDER
            placed += 1
    assert placed >= count


@needs_real
def test_min_slide_protects_leading_slides(
    converted: Converted,
    tmp_path: pathlib.Path
) -> None:
    _, everything, _ = converted
    protected = math.convert(REAL, tmp_path / "partial.key", min_slide=20)
    assert protected < everything


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


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
