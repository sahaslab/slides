import sys
import json
import pathlib
import argparse
from slides.keynote import scaffold


def run(args: argparse.Namespace) -> int:
    spec_path = pathlib.Path(args.spec)
    spec = json.loads(spec_path.read_text())
    result = scaffold.build(
        spec,
        template=args.template,
        output=_resolve_output(args, spec_path),
    )
    sys.stderr.write("Created %d slides\n" % (result["created"],))
    return 0


def _resolve_output(
    args: argparse.Namespace,
    spec_path: pathlib.Path,
) -> str | None:
    if args.template is None:
        return None
    if args.output is not None:
        return args.output
    return str(spec_path.with_suffix(".key"))
