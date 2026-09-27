from slides.theme import DeckTheme


def render(theme: DeckTheme) -> str:
    lines = [
        ":root {",
        "  --deck-background: %s;" % (theme.background,),
        "  --deck-foreground: %s;" % (theme.foreground,),
        "  --deck-muted: %s;" % (theme.muted,),
        "  --deck-grid: %s;" % (theme.grid,),
    ]
    for number, accent in enumerate(theme.accents, start=1):
        lines.append("  --deck-accent-%d: %s;" % (number, accent))
    for role, family in sorted(theme.fonts.items()):
        lines.append("  --deck-font-%s: %s;" % (role, family))
    lines.append("}")
    return "\n".join(lines) + "\n"
