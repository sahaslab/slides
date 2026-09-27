import sys
import types
import argparse
import subprocess
from slides import __version__
from slides.cli import build_parser, dispatch


def test_version_is_set():
    assert __version__ == "0.1.0"


def test_parser_has_every_subcommand():
    parser = build_parser()
    action = [a for a in parser._actions if a.dest == "command"][0]
    assert set(action.choices) == {
        "dump", "convert", "scaffold", "patch", "math", "theme", "info",
    }


def test_help_does_not_import_heavy_dependencies():
    code = (
        "import sys; from slides import cli; cli.build_parser(); "
        "print(','.join(m for m in ('keynote_parser','pptx','matplotlib') "
        "if m in sys.modules))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == ""


def test_dispatch_runs_the_command_module(monkeypatch):
    module = types.ModuleType("slides.commands.info")
    module.run = lambda args: 7
    monkeypatch.setitem(sys.modules, "slides.commands.info", module)
    assert dispatch(argparse.Namespace(command="info")) == 7
