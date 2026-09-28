import sys
import pathlib
import argparse
from slides.commands import taken
from slides.keynote import math


def run(args: argparse.Namespace) -> int:
    source = pathlib.Path(args.target)
    out = pathlib.Path(args.output) if args.output else default_output(source)
    # keynote-parser writes a zip only for a .key path, and never overwrite:
    # an existing output could be the source deck itself.
    if out.suffix != ".key":
        sys.stderr.write("%s does not end in .key; pass -o with a .key path\n" % (out,))
        return 1
    if taken(out):
        return 1
    count = math.convert(source, out, min_slide=args.min_slide)
    sys.stderr.write("Converted %d equations\n" % (count,))
    sys.stdout.write("%s\n" % (out,))
    return 0


def default_output(source: pathlib.Path) -> pathlib.Path:
    return source.with_name("%s-math%s" % (source.stem, source.suffix))
