import os
import sys
import shutil
import pathlib
import argparse
import subprocess
from slides import readers, writers
from slides.model import Deck

SUFFIX = {"md": ".md", "txt": ".txt", "json": ".json"}


def run(args: argparse.Namespace) -> int:
    deck = readers.read(args.target, via_deckwerk=args.via_deckwerk)
    destination = None if args.clipboard else _destination(args, deck)
    _link_embeds(deck, args, destination)
    rendered = writers.render(deck, args.format, notes_only=args.notes_only)
    if args.clipboard:
        subprocess.run(["pbcopy"], input=rendered, text=True, check=True)
        sys.stderr.write("Copied %d slides to the clipboard\n" % (len(deck.slides),))
        return 0
    if destination is None:
        sys.stdout.write(rendered)
        return 0
    destination.write_text(rendered)
    sys.stderr.write("Wrote %s\n" % (destination,))
    return 0


def _destination(
    args: argparse.Namespace,
    deck: Deck
) -> pathlib.Path | None:
    if args.output:
        return pathlib.Path(args.output)
    if args.out_dir:
        directory = pathlib.Path(args.out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stem = pathlib.Path(deck.source).stem if deck.source else deck.title
        return directory / ("%s%s" % (stem, SUFFIX[args.format]))
    return None


def _link_embeds(
    deck: Deck,
    args: argparse.Namespace,
    destination: pathlib.Path | None
) -> None:
    embeds = [embed for slide in deck.slides for embed in slide.embeds]
    if not embeds:
        return
    root = pathlib.Path(deck.source)
    if destination is None:
        for embed in embeds:
            embed.src = str(root / embed.src)
        sys.stderr.write("Embeds were not copied; links point at the deck.\n")
        return
    assets_dir = (
        pathlib.Path(args.assets_dir) if args.assets_dir
        else destination.parent / ("%s_assets" % (destination.stem,))
    )
    written = copy_embeds(deck, assets_dir, copy_media=args.copy_media)
    for embed in embeds:
        if embed.src in written:
            embed.src = os.path.relpath(written[embed.src], destination.parent)
        else:
            embed.src = str(root / embed.src)


def copy_embeds(
    deck: Deck,
    destination: pathlib.Path,
    copy_media: bool = False
) -> dict[str, str]:
    root = pathlib.Path(deck.source)
    written: dict[str, str] = {}
    for slide in deck.slides:
        for embed in slide.embeds:
            if embed.kind == "video" and not copy_media:
                continue
            source = root / embed.src
            if not source.exists():
                sys.stderr.write("Missing asset: %s\n" % (source,))
                continue
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / pathlib.Path(embed.src).name
            shutil.copyfile(source, target)
            written[embed.src] = str(target)
    return written
