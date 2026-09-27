from slides.model import Deck
from slides.writers import json, markdown, text

WRITERS = {"md": markdown, "txt": text, "json": json}


def render(
    deck: Deck,
    fmt: str,
    notes_only: bool = False
) -> str:
    return WRITERS[fmt].render(deck, notes_only=notes_only)
