import os
import pathlib
import zipfile
import pytest
from slides.color import to_oklch
from slides.readers.keynote_file import _resolve_background, clean, read

REAL = pathlib.Path(os.path.expanduser(
    "~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote"
    "/09_oct14_tfidf_imbalance_eval.key"
))
needs_real = pytest.mark.skipif(not REAL.exists(), reason="no sample .key")

REFERENCE = pathlib.Path(os.path.expanduser(
    "~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/REFERENCE.key"
))
needs_reference = pytest.mark.skipif(not REFERENCE.exists(), reason="no REFERENCE.key")


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


@needs_real
def test_background_and_text_colours_reflect_actual_usage():
    deck = read(REAL)
    with_background = [s for s in deck.slides if s.background == "#0d1e1c"]
    assert len(with_background) >= len(deck.slides) - 2

    chromatic = [
        c for c in deck.colors
        if c.kind == "text" and to_oklch(c.hex)[1] >= 0.05
    ]
    assert chromatic
    heaviest = max(chromatic, key=lambda c: c.weight)
    assert heaviest.hex == "#a5d75f"

    by_hex = {c.hex: c.weight for c in deck.colors}
    for flat in ("#000000", "#f9f9f9"):
        assert by_hex.get(flat, 0.0) < heaviest.weight


def test_background_uses_the_slides_own_solid_fill():
    index = {
        "slide-style": {
            "slideProperties": {
                "fill": {"color": {"r": 1.0, "g": 0.0, "b": 0.0}},
            },
        },
    }
    raw = {"style": {"identifier": "slide-style"}}
    assert _resolve_background(raw, index, {}) == "#ff0000"


def test_background_is_none_for_an_image_fill_even_when_the_master_is_solid():
    index = {
        "slide-style": {
            "slideProperties": {
                "fill": {"image": {"identifier": "some-image"}},
            },
        },
        "master-style": {
            "slideProperties": {
                "fill": {"color": {"r": 0.0, "g": 0.0, "b": 0.0}},
            },
        },
        "master-slide": {"style": {"identifier": "master-style"}},
    }
    raw = {
        "style": {"identifier": "slide-style"},
        "templateSlide": {"identifier": "master-slide"},
    }
    assert _resolve_background(raw, index, {}) is None


def test_background_falls_back_to_the_master_when_its_own_style_has_no_fill():
    index = {
        "slide-style": {"slideProperties": {}},
        "master-style": {
            "slideProperties": {
                "fill": {"color": {"r": 0.0, "g": 1.0, "b": 0.0}},
            },
        },
        "master-slide": {"style": {"identifier": "master-style"}},
    }
    raw = {
        "style": {"identifier": "slide-style"},
        "templateSlide": {"identifier": "master-slide"},
    }
    assert _resolve_background(raw, index, {}) == "#00ff00"


@needs_reference
def test_reference_deck_image_background_is_not_the_master_colour():
    deck = read(REFERENCE)
    assert deck.slides[0].background is None
