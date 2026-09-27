import pathlib
from slides.model import Deck, Embed, Slide


def render(
    deck: Deck,
    notes_only: bool = False
) -> str:
    out = ["# %s\n" % (deck.title,)]
    for slide in deck.slides:
        if notes_only:
            if slide.notes.strip():
                out.append("## Slide %d\n" % (slide.number,))
                out.append(_quote(slide.notes))
            continue
        out.append("## Slide %d\n" % (slide.number,))
        out.append(_slide(slide))
    return "\n".join(out).rstrip() + "\n"


def _slide(slide: Slide) -> str:
    parts: list[str] = []
    if slide.title:
        parts.append("### %s\n" % (slide.title,))
    for item in slide.body_items():
        parts.append(_bullets(item.text))
    for table in slide.tables:
        parts.append(_table(table.rows))
    for embed in slide.embeds:
        parts.append("%s\n" % (_link(embed),))
    if slide.notes.strip():
        parts.append(_quote(slide.notes))
    return "\n".join(parts)


def _bullets(text: str) -> str:
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join("- %s" % (line,) for line in lines if line) + "\n"


def _table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    out = [_row(rows[0], width), "|%s" % (" --- |" * width,)]
    out += [_row(row, width) for row in rows[1:]]
    return "\n".join(out) + "\n"


def _row(
    cells: list[str],
    width: int
) -> str:
    padded = list(cells) + [""] * (width - len(cells))
    return "|%s" % ("".join(" %s |" % (str(c).strip(),) for c in padded),)


def _link(embed: Embed) -> str:
    name = embed.title or pathlib.PurePosixPath(embed.src).name
    label = "Interactive" if embed.kind == "web" else "Video"
    return "[%s: %s](%s)" % (label, name, embed.src)


def _quote(notes: str) -> str:
    lines = [line.strip() for line in notes.split("\n")]
    return "\n".join("> %s" % (line,) for line in lines if line) + "\n"
