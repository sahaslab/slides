import json
from slides.model import Deck, Slide


def render(
    deck: Deck,
    notes_only: bool = False
) -> str:
    return json.dumps(to_dict(deck, notes_only=notes_only), indent=2)


def to_dict(
    deck: Deck,
    notes_only: bool = False
) -> dict:
    return {
        "title": deck.title,
        "source": deck.source,
        "kind": deck.kind,
        "canvas": {"w": deck.width, "h": deck.height},
        "slides": [_slide(s, notes_only) for s in deck.slides],
    }


def _slide(
    slide: Slide,
    notes_only: bool
) -> dict:
    if notes_only:
        return {"number": slide.number, "notes": slide.notes}
    return {
        "number": slide.number,
        "title": slide.title,
        "body": [i.text for i in slide.body_items()],
        "tables": [t.rows for t in slide.tables],
        "images": [i.path for i in slide.images],
        "embeds": [
            {
                "kind": e.kind,
                "src": e.src,
                "title": e.title,
                "poster": e.poster,
            }
            for e in slide.embeds
        ],
        "notes": slide.notes,
        "background": slide.background,
    }
