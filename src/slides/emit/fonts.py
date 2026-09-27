GENERIC_KEYWORDS = {
    "serif",
    "sans-serif",
    "monospace",
    "cursive",
    "fantasy",
    "system-ui",
    "ui-serif",
    "ui-sans-serif",
    "ui-monospace",
    "-apple-system",
    "blinkmacsystemfont",
}

FALLBACK = {
    "serif": "DejaVu Serif",
    "sans-serif": "DejaVu Sans",
    "monospace": "DejaVu Sans Mono",
}


def split_stack(spec: str) -> tuple[str, list[str]]:
    tokens = _tokens(spec)
    generics = [name.lower() for name, quoted in tokens if not quoted]
    if "monospace" in generics or "ui-monospace" in generics:
        generic = "monospace"
    elif "serif" in generics or "ui-serif" in generics:
        generic = "serif"
    else:
        generic = "sans-serif"
    names = []
    for name, quoted in tokens:
        if not quoted and name.lower() in GENERIC_KEYWORDS:
            continue
        if name not in names:
            names.append(name)
    fallback = FALLBACK[generic]
    if fallback not in names:
        names.append(fallback)
    return generic, names


def _tokens(spec: str) -> list[tuple[str, bool]]:
    # A quoted token ("Serif") is a literal CSS family name even if it reads
    # like a generic keyword; only a bare, unquoted token is the keyword.
    tokens = []
    for raw in spec.split(","):
        raw = raw.strip()
        quoted = len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]
        name = raw[1:-1] if quoted else raw
        if name:
            tokens.append((name, quoted))
    return tokens


def primary_family(
    spec: str,
    default: str
) -> str:
    for name in split_stack(spec)[1]:
        if name not in FALLBACK.values():
            return name
    return default
