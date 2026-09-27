import json
from slides.emit import css, ggplot
from slides.emit import matplotlib as matplotlib_emit
from slides.theme import DeckTheme


def render(
    theme: DeckTheme,
    fmt: str
) -> str:
    if fmt == "json":
        return json.dumps(theme.to_dict(), indent=2) + "\n"
    if fmt == "css":
        return css.render(theme)
    if fmt == "ggplot":
        return ggplot.render(theme)
    return matplotlib_emit.style_sheet(theme)
