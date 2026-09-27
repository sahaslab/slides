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
    assert clean("a b") == "a b"


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
