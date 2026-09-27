import json
import pathlib
import subprocess
from slides.deckwerk.importer import find_root


def validate(
    deck_dir: str | pathlib.Path,
    root: str | None = None
) -> dict:
    checkout = find_root(root)
    result = subprocess.run(
        [str(checkout / "bin/slide-agent"), "validate", str(deck_dir)],
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        return {"available": False, "detail": result.stderr.strip()}
    return json.loads(result.stdout)
