import pathlib
from slides.readers.deckwerk import read, strip_html

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def test_reads_deck_metadata():
    deck = read(FIXTURE)
    assert deck.title == "Mini"
    assert (deck.width, deck.height) == (1920.0, 1080.0)
    assert deck.kind == "deckwerk"
    assert len(deck.slides) == 3


def test_first_element_by_z_and_position_becomes_the_title():
    deck = read(FIXTURE)
    assert deck.slides[0].title == "Opening"
    assert deck.slides[1].title == "Numbers"


def test_strips_inline_markup_but_keeps_the_text():
    deck = read(FIXTURE)
    assert [i.text for i in deck.slides[0].body_items()] == ["First point"]


def test_collects_colors_with_roles():
    deck = read(FIXTURE)
    kinds = {c.hex: c.kind for c in deck.colors}
    assert kinds["#0d1e1c"] == "background"
    assert kinds["#a5d75f"] == "text"
    assert kinds["#c86432"] == "fill"


def test_reads_notes_tables_and_images():
    deck = read(FIXTURE)
    assert deck.slides[0].notes == "Say hello."
    assert deck.slides[0].images[0].path == "assets/plot.png"
    assert deck.slides[1].tables[0].rows[0] == ["Model", "MSE"]


def test_slide_number_field_produces_no_body_item():
    deck = read(FIXTURE)
    assert [i.text for i in deck.slides[1].items] == ["Numbers"]


def test_strip_html_handles_entities_and_breaks():
    assert strip_html("a &amp; b<br>c") == "a & b\nc"
    assert strip_html("<p>one</p><p>two</p>") == "one\ntwo"
