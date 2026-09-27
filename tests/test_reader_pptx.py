import pathlib
import pytest
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


def test_reads_a_picture_shape_as_an_image():
    deck = read(FIXTURE)
    images = deck.slides[1].images
    assert len(images) == 1
    image = images[0]
    assert image.path == "image.png"
    assert image.x == pytest.approx(72.0)
    assert image.y == pytest.approx(288.0)
    assert image.w == pytest.approx(72.0)
    assert image.h == pytest.approx(72.0)
