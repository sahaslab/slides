import sys
import subprocess
import pytest
from slides.cli import build_parser

COMMANDS = ["dump", "convert", "scaffold", "patch", "math", "theme", "info"]


@pytest.mark.parametrize("command", COMMANDS)
def test_every_subcommand_has_help(command):
    result = subprocess.run(
        [sys.executable, "-m", "slides.cli", command, "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout


def test_no_subcommand_is_still_dispatchable():
    parser = build_parser()
    action = [a for a in parser._actions if a.dest == "command"][0]
    assert set(action.choices) == set(COMMANDS)
