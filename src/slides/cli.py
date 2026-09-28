import sys
import signal
import argparse
import importlib
from slides.deckwerk.importer import DeckWerkError
from slides.keynote.jxa import KeynoteError


def main():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 2
    # The tool's own failures (no presentation open, not a deck, an output that
    # already exists) are expected, so they read as one line, not a traceback.
    try:
        return dispatch(args)
    except (DeckWerkError, KeynoteError, FileExistsError, FileNotFoundError, ValueError) as problem:
        sys.stderr.write("slides: %s\n" % (problem,))
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="slides")
    sub = parser.add_subparsers(dest="command")

    dump = sub.add_parser("dump")
    dump.add_argument("target", nargs="?", default=None)
    dump.add_argument("-f", "--format", default="md", choices=["md", "json", "txt"])
    dump.add_argument("-o", "--output", default=None)
    dump.add_argument("--out-dir", default=None)
    dump.add_argument("--notes-only", action="store_true")
    dump.add_argument("--clipboard", action="store_true")
    dump.add_argument("--via-deckwerk", action="store_true")
    dump.add_argument("--assets-dir", default=None)
    dump.add_argument("--copy-media", action="store_true")

    convert = sub.add_parser("convert")
    convert.add_argument("target")
    convert.add_argument(
        "-f",
        "--format",
        required=True,
        choices=["deckwerk", "pptx", "keynote", "pdf"],
    )
    convert.add_argument("-o", "--output", default=None)
    convert.add_argument("--deckwerk-root", default=None)

    theme = sub.add_parser("theme")
    theme.add_argument("target")
    theme.add_argument(
        "-f",
        "--format",
        default="json",
        choices=["json", "matplotlib", "ggplot", "css"],
    )
    theme.add_argument("--accents", type=int, default=6)

    info = sub.add_parser("info")
    info.add_argument("target")
    info.add_argument("--deckwerk-root", default=None)

    patch = sub.add_parser("patch")
    patch.add_argument("spec")

    scaffold = sub.add_parser("scaffold")
    scaffold.add_argument("spec")
    scaffold.add_argument("--template", default=None)
    scaffold.add_argument("-o", "--output", default=None)

    math = sub.add_parser("math")
    math.add_argument("target")
    math.add_argument("-o", "--output", default=None)
    math.add_argument("--min-slide", type=int, default=1)

    return parser


def dispatch(args: argparse.Namespace) -> int:
    command = importlib.import_module("slides.commands.%s" % (args.command,))
    return command.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
