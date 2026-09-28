from slides import color
from slides.model import ColorUse, Deck, Slide
from slides.theme import NEUTRAL_CHROMA, DeckTheme, extract


def a_deck(
    colors: list[ColorUse],
    background: str | None = "#0d1e1c",
) -> Deck:
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


def test_accent_needing_the_gamut_clamp_holds_its_hue():
    # #6500ff's chroma (0.294) is genuinely out of gamut at the lightness
    # with_contrast must reach for 3:1 against #0d1e1c, so this exercises
    # the chroma refit, not just the lightness search.
    deck = a_deck([ColorUse("#6500ff", 30.0, "fill")])
    accents = extract(deck).accents
    raised = accents[0]
    assert color.contrast(raised, "#0d1e1c") >= 3.0
    assert abs(color.to_oklch(raised)[2] - color.to_oklch("#6500ff")[2]) < 1.0


def test_mid_grey_background_reaches_contrast_floors():
    deck = a_deck([ColorUse("#3355aa", 10.0, "fill")], background="#999999")
    theme = extract(deck, accents=8)
    assert color.contrast(theme.foreground, theme.background) >= 4.5
    assert len(theme.accents) == 8
    for accent in theme.accents:
        assert color.contrast(accent, theme.background) >= 3.0


def test_neutral_muted_and_grid_ignore_saturated_candidates():
    deck = a_deck([
        ColorUse("#e7e7e6", 68.0, "text"),
        ColorUse("#a5d75f", 3.0, "text"),
        ColorUse("#93a69f", 2.0, "text"),
        ColorUse("#f0a35e", 1.0, "text"),
        ColorUse("#79b8e8", 1.0, "text"),
        ColorUse("#2c403b", 3.0, "fill"),
        ColorUse("#980c0c", 5.0, "text"),
    ])
    theme = extract(deck)
    assert theme.muted == "#93a69f"
    assert theme.grid == "#2c403b"


def test_muted_ignores_a_neutral_fill_in_its_band():
    deck = a_deck([
        ColorUse("#edf4f1", 40.0, "text"),
        ColorUse("#5a6b68", 30.0, "fill"),
    ])
    assert extract(deck).muted != "#5a6b68"


def test_muted_does_not_nearly_duplicate_the_foreground():
    deck = a_deck([
        ColorUse("#edf4f1", 40.0, "text"),
        ColorUse("#c7d0cd", 30.0, "text"),
    ])
    theme = extract(deck)
    assert theme.muted != "#c7d0cd"
    assert color.delta_e(theme.muted, theme.foreground) >= 2.0 * 0.06


def test_grid_stays_on_the_same_side_as_the_foreground():
    deck = a_deck([
        ColorUse("#edf4f1", 40.0, "text"),
        ColorUse("#000000", 30.0, "fill"),
    ])
    assert extract(deck).grid != "#000000"


def test_muted_breaks_weight_ties_on_contrast_before_hex():
    deck = a_deck(
        [
            ColorUse("#111827", 50.0, "text"),
            ColorUse("#6b7280", 1.0, "text"),
            ColorUse("#94a3b8", 1.0, "text"),
        ],
        background="#ffffff",
    )
    assert extract(deck).muted == "#6b7280"


def test_synthesised_foreground_targets_seven_not_four_point_five():
    needs_raise = a_deck([ColorUse("#9b7653", 40.0, "text")], background="#ffffff")
    theme = extract(needs_raise)
    assert color.contrast(theme.foreground, "#ffffff") >= 7.0

    already_clears = a_deck([ColorUse("#cc0000", 40.0, "text")], background="#ffffff")
    assert extract(already_clears).foreground == "#cc0000"


def test_a_near_miss_neutral_beats_a_clearing_accent_colour():
    deck = a_deck(
        [ColorUse("#777777", 80.0, "text"), ColorUse("#cc0000", 5.0, "text")],
        background="#ffffff",
    )
    theme = extract(deck)
    assert color.contrast(theme.foreground, theme.background) >= 4.5
    assert color.to_oklch(theme.foreground)[1] < NEUTRAL_CHROMA
    assert theme.foreground != "#cc0000"


def test_background_kind_wins_over_a_heavier_neutral_fill():
    deck = a_deck(
        [
            ColorUse("#f5f5f5", 100.0, "fill"),
            ColorUse("#101820", 10.0, "background"),
            ColorUse("#a5d75f", 5.0, "text"),
        ],
        background=None,
    )
    assert extract(deck).background == "#101820"


def test_padding_never_runs_short():
    for background in ["#ffffff", "#000000", "#0d1e1c"]:
        deck = a_deck([ColorUse("#a5d75f", 20.0, "fill")], background=background)
        for count in range(1, 17):
            accents = extract(deck, accents=count).accents
            assert len(accents) == count
            assert len(set(accents)) == count


def test_padding_never_runs_short_on_mid_tones():
    # #707070-#888888 clear ACCENT_CONTRAST by only a hair in either
    # direction; #2e8b57/#cc6633/#669966 are mid-toned, saturated
    # backgrounds. All are the cases that used to come up short at N>=12.
    backgrounds = ["#777777", "#2e8b57", "#cc6633", "#669966", "#3355aa"]
    for background in backgrounds:
        deck = a_deck([ColorUse("#a5d75f", 20.0, "fill")], background=background)
        for count in (1, 6, 12, 16):
            accents = extract(deck, accents=count).accents
            assert len(accents) == count
            assert len(set(accents)) == count
            for accent in accents:
                assert color.contrast(accent, background) >= 3.0
