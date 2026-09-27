import sys
import json
import argparse
import collections.abc
from slides import readers
from slides.model import Deck


def run(args: argparse.Namespace) -> int:
    deck = readers.read(args.target)
    sys.stdout.write(summarise(deck) + "\n")
    kind = readers.detect(args.target)
    if kind == "keynote":
        _extra(lambda: _coverage(args))
    elif kind == "deckwerk":
        _extra(lambda: _validation(args))
    return 0


def _extra(work: collections.abc.Callable[[], str]) -> None:
    from slides.deckwerk.importer import MissingDeckWerk
    try:
        sys.stdout.write(work())
    except MissingDeckWerk as problem:
        sys.stderr.write("%s\n" % (problem,))


def _coverage(args: argparse.Namespace) -> str:
    from slides.deckwerk import importer
    result = importer.report(args.target, root=args.deckwerk_root)
    return "coverage: %s\n" % (json.dumps(result.get("report", {}), indent=2),)


def _validation(args: argparse.Namespace) -> str:
    from slides.deckwerk import agent
    result = agent.validate(args.target, root=args.deckwerk_root)
    return "validate: %s\n" % (json.dumps(result, indent=2),)


def summarise(deck: Deck) -> str:
    tables = sum(len(s.tables) for s in deck.slides)
    images = sum(len(s.images) for s in deck.slides)
    noted = sum(1 for s in deck.slides if s.notes.strip())
    words = sum(
        len(i.text.split())
        for s in deck.slides
        for i in s.body_items()
    )
    lines = [
        "%s  (%s)" % (deck.title, deck.kind),
        "%d slides, %.0f x %.0f" % (len(deck.slides), deck.width, deck.height),
        "%s, %s, %s" % (
            _plural(tables, "table"),
            _plural(images, "image"),
            _plural(noted, "slide with notes", "slides with notes"),
        ),
        "%d words of body text" % (words,),
    ]
    kinds = [e.kind for s in deck.slides for e in s.embeds]
    if kinds:
        lines.append("%s, %s" % (
            _plural(kinds.count("web"), "web page"),
            _plural(kinds.count("video"), "video"),
        ))
    if deck.fonts:
        lines.append("fonts: %s" % (", ".join(sorted(set(deck.fonts.values()))),))
    if deck.colors:
        top = ", ".join(c.hex for c in deck.colors[:6])
        lines.append("colours: %s" % (top,))
    return "\n".join(lines)


def _plural(
    count: int,
    singular: str,
    plural: str | None = None
) -> str:
    if count == 1:
        return "1 %s" % (singular,)
    return "%d %s" % (count, plural or (singular + "s"))
