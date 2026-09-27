import pytest
from slides.emit import css, fonts, ggplot, render
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


def test_rc_params_splits_a_sans_serif_css_stack():
    theme = a_theme()
    theme.fonts = {
        "body": "\"Avenir Next\", Avenir, \"Helvetica Neue\", Inter, system-ui, sans-serif",
    }
    params = mpl.rc_params(theme)
    assert params["font.family"] == "sans-serif"
    assert params["font.sans-serif"] == [
        "Avenir Next", "Avenir", "Helvetica Neue", "Inter", "DejaVu Sans",
    ]


def test_rc_params_splits_a_serif_css_stack():
    theme = a_theme()
    theme.fonts = {
        "body": "Charter, \"Iowan Old Style\", \"New York\", Palatino, Georgia, serif",
    }
    params = mpl.rc_params(theme)
    assert params["font.family"] == "serif"
    assert params["font.serif"] == [
        "Charter", "Iowan Old Style", "New York", "Palatino", "Georgia", "DejaVu Serif",
    ]


def test_rc_params_splits_a_monospace_css_stack():
    theme = a_theme()
    theme.fonts = {"body": "\"Fira Code\", monospace"}
    params = mpl.rc_params(theme)
    assert params["font.family"] == "monospace"
    assert params["font.monospace"] == ["Fira Code", "DejaVu Sans Mono"]


def test_rc_params_dedupes_repeated_family_names():
    theme = a_theme()
    theme.fonts = {"body": "Helvetica, Helvetica, sans-serif"}
    params = mpl.rc_params(theme)
    assert params["font.sans-serif"] == ["Helvetica", "DejaVu Sans"]


def test_rc_params_falls_back_once_with_no_fonts():
    theme = a_theme()
    theme.fonts = {}
    params = mpl.rc_params(theme)
    assert params["font.family"] == "sans-serif"
    assert params["font.sans-serif"] == ["DejaVu Sans"]


def test_split_stack_keeps_a_quoted_family_named_like_a_generic():
    generic, names = fonts.split_stack("\"Serif\", Arial, sans-serif")
    assert generic == "sans-serif"
    assert names == ["Serif", "Arial", "DejaVu Sans"]


def test_split_stack_defaults_to_sans_serif_without_a_bare_generic():
    generic, names = fonts.split_stack("\"Serif\"")
    assert generic == "sans-serif"
    assert names == ["Serif", "DejaVu Sans"]


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


def test_ggplot_palette_getter_fails_loudly_past_its_length():
    out = ggplot.render(a_theme())
    assert "deck_palette_at <- function(n) {" in out
    assert "if (n > length(deck_palette)) {" in out
    assert "deck_palette has %d colours but this scale needs %d" in out
    assert "regenerate with slides theme talk/ -f ggplot --accents %d" in out
    assert "palette = deck_palette_at" in out
    assert "function(n) deck_palette[seq_len(n)]" not in out


def test_ggplot_extracts_the_primary_family_from_a_css_stack():
    theme = a_theme()
    theme.fonts = {
        "body": "\"Avenir Next\", Avenir, \"Helvetica Neue\", Inter, system-ui, sans-serif",
    }
    out = ggplot.render(theme)
    assert "base_family = \"Avenir Next\"" in out
    assert "system-ui" not in out
    assert "Helvetica Neue" not in out


def test_ggplot_falls_back_to_sans_with_no_fonts():
    theme = a_theme()
    theme.fonts = {}
    out = ggplot.render(theme)
    assert "base_family = \"sans\"" in out


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


def test_matplotlib_format_is_a_style_sheet_not_a_dict_literal():
    out = render(a_theme(), "matplotlib")
    assert out.startswith("# plt.style.use(\"deck.mplstyle\")")
    assert "rc_params = {" not in out
    assert "figure.facecolor: \"#0d1e1c\"" in out
    assert "axes.prop_cycle: cycler(\"color\", [\"#a5d75f\", \"#5ce1e6\", \"#ff6b6b\"])" in out
    assert "'" not in out


def test_matplotlib_style_sheet_round_trips(tmp_path):
    matplotlib = pytest.importorskip("matplotlib", reason="figures extra not installed")
    import matplotlib.style
    path = tmp_path / "deck.mplstyle"
    path.write_text(render(a_theme(), "matplotlib"))
    with matplotlib.style.context(str(path)):
        assert matplotlib.rcParams["axes.facecolor"] == "#0d1e1c"
        assert matplotlib.rcParams["text.color"] == "#edf4f1"
        cycled = [entry["color"] for entry in matplotlib.rcParams["axes.prop_cycle"]]
        assert cycled == ["#a5d75f", "#5ce1e6", "#ff6b6b"]
        assert matplotlib.rcParams["font.sans-serif"][0] == "Libre Franklin"
