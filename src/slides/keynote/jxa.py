import os
import json
import subprocess


class KeynoteError(Exception):
    pass


def app_name() -> str:
    return os.environ.get("SLIDES_KEYNOTE_APP", "Keynote")


def run(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise KeynoteError(result.stderr.strip() or "osascript failed")
    return result.stdout


def run_json(script: str) -> object:
    return json.loads(run(script))
