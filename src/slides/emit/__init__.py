import json
from slides.emit import css, ggplot
from slides.emit import matplotlib as matplotlib_emit
from slides.theme import DeckTheme


def render(theme: DeckTheme, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(theme.to_dict(), indent=2) + "\n"
    if fmt == "css":
        return css.render(theme)
    if fmt == "ggplot":
        return ggplot.render(theme)
    params = matplotlib_emit.rc_params(theme)
    body = ",\n".join("    %r: %s" % (k, _value(v)) for k, v in params.items())
    return "rc_params = {\n%s,\n}\n" % (body,)


def _value(value: object) -> str:
    if isinstance(value, str) and value.startswith("cycler("):
        return value
    return repr(value)
