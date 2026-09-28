import pathlib
from slides.readers.deckwerk import (
    _colors_in,
    _html_table,
    _max_font_size,
    read,
    strip_html,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"

# A real-shaped rendered KaTeX span: MathML (readable-ish glyph text), the
# author's real TeX source in the annotation, and katex-html glyph spans.
# Only the annotation should survive strip_html/_html_table.
KATEX_INLINE = (
    "<span class=\"katex\"><span class=\"katex-mathml\"><math><semantics>"
    "<mrow><mi>y</mi></mrow>"
    "<annotation encoding=\"application/x-tex\">"
    "\\displaystyle \\hat{y} = 4.0 \\text{ min}"
    "</annotation></semantics></math></span>"
    "<span class=\"katex-html\" aria-hidden=\"true\">"
    "<span class=\"mord\">4.0</span></span></span>"
)
KATEX_TEX = "\\displaystyle \\hat{y} = 4.0 \\text{ min}"


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


def test_slide_background_accepts_bare_string_and_object_form():
    deck = read(FIXTURE)
    assert deck.slides[0].background == "#0d1e1c"
    assert deck.slides[1].background == "#0d1e1c"


def test_theme_css_contributes_stylesheet_colors():
    deck = read(FIXTURE)
    kinds = {c.hex: c.kind for c in deck.colors}
    assert kinds["#e7e7e6"] == "text"
    assert kinds["#2c403b"] == "fill"
    assert kinds["#93a69f"] == "text"
    # Every fixture slide sets its own background, so the root .slide
    # rule's (overridden) background must not be harvested at all.
    assert "#0a0905" not in kinds


def test_title_marker_wins_over_position():
    deck = read(FIXTURE)
    assert deck.slides[2].title == "Demos"


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


def test_html_table_treats_a_cell_break_as_a_space():
    markup = "<table><tr><td>Linear<br>fit</td><td>3.2</td></tr></table>"
    assert _html_table(markup) == [["Linear fit", "3.2"]]


def test_a_null_theme_style_reads_with_no_fonts(tmp_path):
    (tmp_path / "deck.json").write_text(
        "{\"title\": \"Old\", \"themeStyle\": null, \"slides\": [{\"elements\": []}]}"
    )
    assert read(tmp_path).fonts == {}


def test_an_rgb_background_is_normalised_to_hex(tmp_path):
    (tmp_path / "deck.json").write_text(
        "{\"slides\": [{\"background\": {\"color\": \"rgb(13, 30, 28)\", \"image\": null}, \"elements\": []}]}"
    )
    assert read(tmp_path).slides[0].background == "#0d1e1c"


def test_an_image_background_has_no_single_colour(tmp_path):
    (tmp_path / "deck.json").write_text(
        "{\"slides\": [{\"background\": {\"color\": \"#0d1e1c\", \"image\": \"bg.png\"}, \"elements\": []}]}"
    )
    assert read(tmp_path).slides[0].background is None


def test_colors_in_accepts_rgba_and_three_digit_hex():
    assert _colors_in("rgba(200, 100, 50, 0.5)") == ["#c86432"]
    assert _colors_in("#abc") == ["#aabbcc"]


def test_media_query_slide_rule_does_not_join_the_cascade():
    # The fixture's theme.css has a trailing "@media print { .slide { color:
    # #f00 } }" after the real, unconditional .slide rules. It must not
    # contribute to the root-rule cascade at all.
    deck = read(FIXTURE)
    kinds = {c.hex: c.kind for c in deck.colors}
    assert "#ff0000" not in kinds
    # The unconditional cascade winner is unaffected by the trailing block.
    assert kinds["#e7e7e6"] == "text"


def test_html_table_collapses_a_double_break_to_one_space():
    markup = "<table><tr><td>Linear<br><br>fit</td></tr></table>"
    assert _html_table(markup) == [["Linear fit"]]


def test_max_font_size_finds_the_largest_inline_px_value():
    assert _max_font_size("<p style=\"font-size: 48px;\">Byline</p>") == 48.0
    assert _max_font_size("<span style=\"font-size: 120px;\">Title</span>") == 120.0
    assert _max_font_size("<p>No inline size here</p>") is None


def test_title_falls_back_to_largest_font_size_when_no_marker(tmp_path):
    (tmp_path / "deck.json").write_text(
        "{\"slides\": [{\"elements\": ["
        "{\"type\": \"text\", \"y\": 51, \"html\": \"<p style='font-size: 48px;'>Byline</p>\"},"
        "{\"type\": \"text\", \"y\": 300, \"html\": \"<span style='font-size: 120px;'>Title</span>\"}"
        "]}]}"
    )
    assert read(tmp_path).slides[0].title == "Title"


def test_title_marker_wins_even_over_a_larger_font_size(tmp_path):
    (tmp_path / "deck.json").write_text(
        "{\"slides\": [{\"elements\": ["
        "{\"type\": \"text\", \"y\": 51, \"morphId\": \"title\", "
        "\"html\": \"<p style='font-size: 48px;'>Real Title</p>\"},"
        "{\"type\": \"text\", \"y\": 300, "
        "\"html\": \"<span style='font-size: 120px;'>Loud Byline</span>\"}"
        "]}]}"
    )
    assert read(tmp_path).slides[0].title == "Real Title"


def test_katex_inline_span_becomes_dollar_wrapped_tex_in_a_paragraph():
    markup = "<p>Predicted value: %s.</p>" % (KATEX_INLINE,)
    assert strip_html(markup) == "Predicted value: $%s$." % (KATEX_TEX,)


def test_katex_display_span_becomes_double_dollar_wrapped_tex():
    markup = "<p><span class=\"katex-display\">%s</span></p>" % (KATEX_INLINE,)
    assert strip_html(markup) == "$$%s$$" % (KATEX_TEX,)


def test_katex_in_a_table_cell_becomes_wrapped_tex():
    markup = "<table><tr><td>slope</td><td>%s</td></tr></table>" % (KATEX_INLINE,)
    assert _html_table(markup) == [["slope", "$%s$" % (KATEX_TEX,)]]
