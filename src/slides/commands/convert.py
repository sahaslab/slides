import sys
import pathlib
import argparse
from slides import readers
from slides.deckwerk import importer


def run(args: argparse.Namespace) -> int:
    source = pathlib.Path(args.target)
    kind = readers.detect(source)
    route = (kind, args.format)
    if route == ("keynote", "deckwerk"):
        return _to_deckwerk(args, source)
    raise ValueError("cannot convert %s to %s" % (kind, args.format))


def _to_deckwerk(
    args: argparse.Namespace,
    source: pathlib.Path
) -> int:
    out = pathlib.Path(args.output) if args.output else source.with_suffix("")
    result = importer.import_key(source, out, root=args.deckwerk_root)
    counts = result.get("report", {})
    sys.stderr.write("Imported %s -> %s\n" % (source.name, out))
    unsupported = sum(counts.get("unsupported", {}).values())
    if unsupported:
        sys.stderr.write(
            "%d elements came through as placeholders\n" % (unsupported,)
        )
    sys.stdout.write("%s\n" % (out,))
    return 0
