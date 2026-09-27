import pytest
from slides.emit import css, ggplot, render
from slides.emit import matplotlib as mpl
from slides.theme import DeckTheme


def a_theme() -> DeckTheme:
    return DeckTheme(
        background="#0d1e1c",
        foreground="#edf4f1",
        muted="#93a69f",
        grid="#2c403b",
        accents=["#a5d75f", "#5ce1e6", "#ff6b6b"],
        fonts={"title": "Libre Franklin", "body": "Libre Franklin"},
        source="talk/",
    )


def test_rc_params_carry_the_roles():
    params = mpl.rc_params(a_theme())
    assert params["figure.facecolor"] == "#0d1e1c"
    assert params["text.color"] == "#edf4f1"
    assert params["grid.color"] == "#2c403b"
    assert params["xtick.color"] == "#93a69f"
    assert params["font.sans-serif"][0] == "Libre Franklin"


def test_rc_params_cycle_uses_the_accents():
    params = mpl.rc_params(a_theme())
    assert "#a5d75f" in str(params["axes.prop_cycle"])


def test_rc_params_needs_no_matplotlib(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    assert mpl.rc_params(a_theme())["figure.facecolor"] == "#0d1e1c"


def test_ggplot_emits_sourceable_r():
    out = ggplot.render(a_theme())
    assert "theme_deck <- function(" in out
    assert "scale_colour_deck <- function(" in out
    assert "scale_fill_deck <- function(" in out
    assert '"#a5d75f"' in out
    assert "#0d1e1c" in out
    assert "'" not in out.replace("don't", "")


def test_ggplot_defines_the_palette_once():
    out = ggplot.render(a_theme())
    assert out.count("deck_palette <- ") == 1


def test_css_emits_custom_properties():
    out = css.render(a_theme())
    assert "--deck-background: #0d1e1c;" in out
    assert "--deck-accent-1: #a5d75f;" in out
    assert ":root {" in out


def test_render_dispatches():
    theme = a_theme()
    assert render(theme, "css") == css.render(theme)
    assert render(theme, "ggplot") == ggplot.render(theme)
    assert "\"background\": \"#0d1e1c\"" in render(theme, "json")
    assert "figure.facecolor" in render(theme, "matplotlib")


def test_deck_style_restores_previous_settings():
    matplotlib = pytest.importorskip("matplotlib", reason="figures extra not installed")
    before = matplotlib.rcParams["figure.facecolor"]
    with mpl.deck_style(a_theme()):
        assert matplotlib.rcParams["figure.facecolor"] == "#0d1e1c"
    assert matplotlib.rcParams["figure.facecolor"] == before
