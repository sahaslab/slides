import pytest
from slides.model import Deck, Slide, TextItem
from slides.readers import detect


def test_body_items_drop_the_title():
    slide = Slide(
        number=1,
        title="Fitting a line",
        items=[
            TextItem(text="Fitting a line", role="title"),
            TextItem(text="Minimize squared error"),
        ],
    )
    assert [i.text for i in slide.body_items()] == ["Minimize squared error"]


def test_body_items_deduplicate():
    slide = Slide(
        number=1,
        title=None,
        items=[TextItem(text="Same"), TextItem(text="Same"), TextItem(text="Other")],
    )
    assert [i.text for i in slide.body_items()] == ["Same", "Other"]


def test_body_items_drop_blanks():
    slide = Slide(number=1, items=[TextItem(text="  "), TextItem(text="Real")])
    assert [i.text for i in slide.body_items()] == ["Real"]


def test_deck_defaults():
    deck = Deck(title="Talk")
    assert deck.slides == []
    assert (deck.width, deck.height) == (1920.0, 1080.0)


def test_detect_by_suffix(tmp_path):
    key = tmp_path / "a.key"
    key.touch()
    pptx = tmp_path / "a.pptx"
    pptx.touch()
    dw = tmp_path / "dw"
    dw.mkdir()
    (dw / "deck.json").write_text("{}")
    assert detect(key) == "keynote"
    assert detect(pptx) == "pptx"
    assert detect(dw) == "deckwerk"
    assert detect(None) == "live"


def test_detect_rejects_unknown(tmp_path):
    other = tmp_path / "a.txt"
    other.touch()
    with pytest.raises(ValueError, match="not a deck"):
        detect(other)
