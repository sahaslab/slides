import contextlib
from collections.abc import Iterator
from slides.theme import DeckTheme


def rc_params(theme: DeckTheme) -> dict:
    family = theme.fonts.get("body") or theme.fonts.get("title") or "DejaVu Sans"
    cycle = "cycler('color', %r)" % (list(theme.accents),)
    return {
        "figure.facecolor": theme.background,
        "figure.edgecolor": theme.background,
        "savefig.facecolor": theme.background,
        "savefig.edgecolor": theme.background,
        "axes.facecolor": theme.background,
        "axes.edgecolor": theme.grid,
        "axes.labelcolor": theme.foreground,
        "axes.titlecolor": theme.foreground,
        "axes.grid": True,
        "axes.prop_cycle": cycle,
        "grid.color": theme.grid,
        "grid.linewidth": 0.8,
        "text.color": theme.foreground,
        "xtick.color": theme.muted,
        "ytick.color": theme.muted,
        "legend.facecolor": theme.background,
        "legend.edgecolor": theme.grid,
        "legend.labelcolor": theme.foreground,
        "font.family": "sans-serif",
        "font.sans-serif": [family, "DejaVu Sans"],
    }


@contextlib.contextmanager
def deck_style(theme: DeckTheme) -> Iterator[None]:
    import matplotlib
    from cycler import cycler
    params = rc_params(theme)
    params["axes.prop_cycle"] = cycler("color", list(theme.accents))
    with matplotlib.rc_context(params):
        yield
