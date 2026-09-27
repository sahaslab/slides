import sys
import json
import pathlib
import argparse
from slides.keynote import patch


def run(args: argparse.Namespace) -> int:
    spec = json.loads(pathlib.Path(args.spec).read_text())
    result = patch.apply(spec)
    sys.stderr.write("Updated %d slides\n" % (result["updated"],))
    if result["skipped"]:
        sys.stderr.write("No such slides: %s\n" % (result["skipped"],))
    return 0
