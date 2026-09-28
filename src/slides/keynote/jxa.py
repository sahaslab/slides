import os
import json
import subprocess

# macOS refuses Apple events from an app the user has not let control Keynote.
NOT_PERMITTED = "(-1743)"


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
    if NOT_PERMITTED in result.stderr:
        raise KeynoteError(refused())
    if result.returncode != 0:
        raise KeynoteError(result.stderr.strip() or "osascript failed")
    return result.stdout


def refused() -> str:
    # macOS names the app a terminal session runs in; its reset re-asks.
    terminal = os.environ.get("__CFBundleIdentifier")
    fix = "Allow it under System Settings > Privacy & Security > Automation"
    if terminal:
        fix += ", or run `tccutil reset AppleEvents %s` and accept the prompt on the next run" % (terminal,)
    return "macOS will not let this terminal control %s (-1743). %s" % (app_name(), fix)


def run_json(script: str) -> object:
    return json.loads(run(script))


def literal(value: object) -> str:
    return json.dumps(value)
