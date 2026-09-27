import sys
import argparse
from slides import emit, readers
from slides.theme import extract


def run(args: argparse.Namespace) -> int:
    deck = readers.read(args.target)
    sys.stdout.write(emit.render(extract(deck, accents=args.accents), args.format))
    return 0
