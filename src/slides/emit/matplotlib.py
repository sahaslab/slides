import contextlib
from collections.abc import Iterator
from slides.emit import fonts
from slides.theme import DeckTheme


def rc_params(theme: DeckTheme) -> dict:
    stack = theme.fonts.get("body") or theme.fonts.get("title") or ""
    generic, family = fonts.split_stack(stack)
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
        "axes.prop_cycle": list(theme.accents),
        "grid.color": theme.grid,
        "grid.linewidth": 0.8,
        "text.color": theme.foreground,
        "xtick.color": theme.muted,
        "ytick.color": theme.muted,
        "legend.facecolor": theme.background,
        "legend.edgecolor": theme.grid,
        "legend.labelcolor": theme.foreground,
        "font.family": generic,
        "font.%s" % (generic,): family,
    }


@contextlib.contextmanager
def deck_style(theme: DeckTheme) -> Iterator[None]:
    import matplotlib
    from cycler import cycler
    params = rc_params(theme)
    params["axes.prop_cycle"] = cycler("color", list(theme.accents))
    with matplotlib.rc_context(params):
        yield


def style_sheet(theme: DeckTheme) -> str:
    params = rc_params(theme)
    lines = ["# plt.style.use(\"deck.mplstyle\")"]
    for key, value in params.items():
        lines.append("%s: %s" % (key, _rc_value(key, value)))
    return "\n".join(lines) + "\n"


def _rc_value(
    key: str,
    value: object
) -> str:
    if key == "axes.prop_cycle":
        colours = ", ".join("\"%s\"" % (colour,) for colour in value)
        return "cycler(\"color\", [%s])" % (colours,)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, str) and value.startswith("#"):
        return "\"%s\"" % (value,)
    return str(value)
