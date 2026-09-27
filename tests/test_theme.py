from slides import color
from slides.model import ColorUse, Deck, Slide
from slides.theme import DeckTheme, extract


def a_deck(colors: list[ColorUse], background: str | None = "#0d1e1c") -> Deck:
    return Deck(
        title="T",
        slides=[Slide(number=1, background=background)],
        colors=colors,
        fonts={"title": "Libre Franklin", "body": "Libre Franklin"},
    )


def test_background_comes_from_the_slides_when_known():
    deck = a_deck([ColorUse("#ffffff", 900.0, "stylesheet")])
    assert extract(deck).background == "#0d1e1c"


def test_stock_stylesheet_does_not_beat_the_real_accent():
    # The exact frequencies measured in a real .key.
    deck = a_deck([
        ColorUse("#000000", 606.0, "stylesheet"),
        ColorUse("#ffffff", 394.0, "stylesheet"),
        ColorUse("#f9f9f9", 324.0, "stylesheet"),
        ColorUse("#888888", 30.0, "stylesheet"),
        ColorUse("#a5d75f", 27.0, "text"),
    ])
    theme = extract(deck)
    assert theme.background == "#0d1e1c"
    assert "#a5d75f" in theme.accents


def test_foreground_clears_the_contrast_floor():
    deck = a_deck([
        ColorUse("#edf4f1", 40.0, "text"),
        ColorUse("#152e2a", 80.0, "text"),
    ])
    theme = extract(deck)
    assert color.contrast(theme.foreground, theme.background) >= 4.5


def test_background_falls_back_when_slides_have_no_solid_fill():
    deck = a_deck(
        [ColorUse("#101010", 50.0, "fill"), ColorUse("#a5d75f", 10.0, "text")],
        background=None,
    )
    theme = extract(deck)
    assert theme.background == "#101010"
    assert theme.foreground


def test_background_falls_back_again_when_nothing_is_neutral():
    deck = a_deck([ColorUse("#a5d75f", 10.0, "fill")], background=None)
    assert extract(deck).background == "#a5d75f"


def test_near_duplicate_accents_collapse():
    deck = a_deck([
        ColorUse("#00a2ff", 24.0, "fill"),
        ColorUse("#0093e8", 24.0, "fill"),
        ColorUse("#0085d1", 24.0, "fill"),
        ColorUse("#1fa3ff", 24.0, "fill"),
        ColorUse("#a5d75f", 20.0, "fill"),
    ])
    accents = extract(deck, accents=4).accents
    blues = [a for a in accents if abs(color.to_oklch(a)[2] - 250.0) < 40.0]
    assert len(blues) == 1


def test_accents_clear_their_contrast_floor():
    deck = a_deck([ColorUse("#123c36", 30.0, "fill")])
    for accent in extract(deck).accents:
        assert color.contrast(accent, "#0d1e1c") >= 3.0


def test_accents_are_padded_to_the_requested_count():
    deck = a_deck([ColorUse("#a5d75f", 20.0, "fill")])
    accents = extract(deck, accents=5).accents
    assert len(accents) == 5
    assert len(set(accents)) == 5


def test_muted_sits_between_grid_and_foreground():
    deck = a_deck([ColorUse("#edf4f1", 40.0, "text")])
    theme = extract(deck)
    ground = theme.background
    assert (color.contrast(theme.grid, ground)
            <= color.contrast(theme.muted, ground)
            <= color.contrast(theme.foreground, ground))


def test_fonts_carry_through_and_to_dict_is_complete():
    theme = extract(a_deck([ColorUse("#edf4f1", 10.0, "text")]))
    assert theme.fonts["body"] == "Libre Franklin"
    keys = set(theme.to_dict())
    assert keys == {
        "background", "foreground", "muted", "grid", "accents", "fonts", "source",
    }


def test_a_deck_with_no_colours_still_yields_a_theme():
    theme = extract(Deck(title="Bare"))
    assert isinstance(theme, DeckTheme)
    assert theme.background and theme.foreground
    assert color.contrast(theme.foreground, theme.background) >= 4.5
