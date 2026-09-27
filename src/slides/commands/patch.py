import sys
import json
import pathlib
import argparse
from slides.keynote import patch


def run(args: argparse.Namespace) -> int:
    document = json.loads(pathlib.Path(args.spec).read_text())
    if "slides" in document:
        spec = patch.from_dump(document)
        sys.stderr.write("Dump input: only titles and notes are applied.\n")
    else:
        spec = document
    result = patch.apply(spec)
    sys.stderr.write("Updated %d slides\n" % (result["updated"],))
    if result["skipped"]:
        sys.stderr.write("No such slides: %s\n" % (result["skipped"],))
    return 0
