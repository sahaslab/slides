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
    tokens = [token.strip().strip("\"'") for token in spec.split(",")]
    tokens = [token for token in tokens if token]
    lowered = [token.lower() for token in tokens]
    if "monospace" in lowered or "ui-monospace" in lowered:
        generic = "monospace"
    elif "serif" in lowered or "ui-serif" in lowered:
        generic = "serif"
    else:
        generic = "sans-serif"
    names = []
    for token in tokens:
        if token.lower() in GENERIC_KEYWORDS:
            continue
        if token not in names:
            names.append(token)
    fallback = FALLBACK[generic]
    if fallback not in names:
        names.append(fallback)
    return generic, names


def primary_family(
    spec: str,
    default: str
) -> str:
    for name in split_stack(spec)[1]:
        if name not in FALLBACK.values():
            return name
    return default
