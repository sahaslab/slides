from slides.model import Deck


def render(
    deck: Deck,
    notes_only: bool = False
) -> str:
    out = [deck.title, ""]
    for slide in deck.slides:
        if notes_only:
            if slide.notes.strip():
                out.append(slide.notes.strip())
                out.append("")
            continue
        if slide.title:
            out.append(slide.title)
        for item in slide.body_items():
            out.append(item.text.strip())
        for table in slide.tables:
            for row in table.rows:
                out.append("\t".join(str(c).strip() for c in row))
        if slide.notes.strip():
            out.append(slide.notes.strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
