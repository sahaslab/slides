import os
import sys
import json
import shutil
import pathlib
import tempfile
import subprocess
from slides.model import Deck

RELATIVE = "importers/keynote/import_keynote.py"
DEFAULT_ROOT = "~/src/deckwerk"


class DeckWerkError(Exception):
    pass


class MissingDeckWerk(DeckWerkError):
    pass


class ImporterFailed(DeckWerkError):
    pass


def find_root(explicit: str | None = None) -> pathlib.Path:
    for candidate in (explicit, os.environ.get("SLIDES_DECKWERK_ROOT"), DEFAULT_ROOT):
        if not candidate:
            continue
        root = pathlib.Path(os.path.expanduser(candidate))
        if (root / RELATIVE).exists():
            return root
    raise MissingDeckWerk(
        "No DeckWerk checkout found. Pass --deckwerk-root, set "
        "SLIDES_DECKWERK_ROOT, or clone it to %s" % (DEFAULT_ROOT,)
    )


def interpreter(root: pathlib.Path) -> str:
    candidate = root / ".venv-import/bin/python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def import_key(
    key: str | pathlib.Path,
    out: str | pathlib.Path,
    root: str | None = None
) -> dict:
    return _invoke(key, root, ["--out", str(out)])


def report(
    key: str | pathlib.Path,
    root: str | None = None
) -> dict:
    return _invoke(key, root, ["--report"])


def read_via_import(key: str | pathlib.Path) -> Deck:
    from slides.readers import deckwerk
    staging = pathlib.Path(tempfile.mkdtemp(prefix="slides-import-"))
    target = staging / "deck"
    import_key(key, target)
    deck = deckwerk.read(target)
    deck.source = str(key)
    deck.kind = "keynote"
    shutil.rmtree(staging, ignore_errors=True)
    return deck


def _invoke(
    key: str | pathlib.Path,
    root: str | None,
    extra: list[str]
) -> dict:
    checkout = find_root(root)
    command = [interpreter(checkout), str(checkout / RELATIVE), str(key)] + extra
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ImporterFailed(
            "DeckWerk importer failed:\n%s" % (result.stderr.strip(),)
        )
    return json.loads(result.stdout)
