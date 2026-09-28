import sys
import pathlib
import argparse
import tempfile
from slides import readers
from slides.commands import taken
from slides.deckwerk import importer


def run(args: argparse.Namespace) -> int:
    source = pathlib.Path(args.target)
    kind = readers.detect(source)
    route = (kind, args.format)
    if route == ("keynote", "deckwerk"):
        return _to_deckwerk(args, source)
    if route in (("deckwerk", "pptx"), ("keynote", "pptx")):
        return _to_pptx(args, source)
    if route in (("deckwerk", "keynote"), ("pptx", "keynote")):
        return _to_keynote(args, source, kind)
    if route in (("deckwerk", "pdf"), ("keynote", "pdf"), ("pptx", "pdf")):
        return _to_pdf(args, source, kind)
    raise ValueError("cannot convert %s to %s" % (kind, args.format))


def _to_deckwerk(
    args: argparse.Namespace,
    source: pathlib.Path
) -> int:
    out = pathlib.Path(args.output) if args.output else source.with_suffix("")
    if out.exists() and (out.is_file() or any(out.iterdir())):
        sys.stderr.write("%s already exists; pass -o with a new folder\n" % (out,))
        return 1
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


def _to_pptx(
    args: argparse.Namespace,
    source: pathlib.Path
) -> int:
    from slides.writers import pptx as writer
    out = pathlib.Path(args.output) if args.output else source.with_suffix(".pptx")
    if taken(out):
        return 1
    writer.write(readers.read(source), out)
    sys.stderr.write("Builds and transitions do not survive this route\n")
    sys.stdout.write("%s\n" % (out,))
    return 0


def _to_keynote(
    args: argparse.Namespace,
    source: pathlib.Path,
    kind: str
) -> int:
    from slides.keynote import build, export
    out = pathlib.Path(args.output) if args.output else source.with_suffix(".key")
    if taken(out):
        return 1
    if kind == "pptx":
        export.open_and_save(source, out)
    else:
        build.build(readers.read(source), out)
    sys.stdout.write("%s\n" % (out,))
    return 0


def _to_pdf(
    args: argparse.Namespace,
    source: pathlib.Path,
    kind: str
) -> int:
    from slides.keynote import build, export
    out = pathlib.Path(args.output) if args.output else source.with_suffix(".pdf")
    if taken(out):
        return 1
    if kind == "deckwerk":
        with tempfile.TemporaryDirectory(prefix="slides-pdf-") as staging:
            deck = pathlib.Path(staging) / "deck.key"
            build.build(readers.read(source), deck)
            export.export_pdf(deck, out)
    else:
        export.export_pdf(source, out)
    sys.stdout.write("%s\n" % (out,))
    return 0
