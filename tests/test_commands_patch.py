import json
import argparse
from slides.keynote import patch
from slides.commands import patch as patch_command


def test_passes_a_spec_straight_through(
    tmp_path,
    monkeypatch,
    capsys
):
    captured = {}

    def fake_apply(spec: dict) -> dict:
        captured["spec"] = spec
        return {"updated": 1, "skipped": []}

    monkeypatch.setattr(patch, "apply", fake_apply)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps({"1": {"title": "x"}}))

    assert patch_command.run(argparse.Namespace(spec=str(spec_file))) == 0
    assert captured["spec"] == {"1": {"title": "x"}}
    assert "Dump input" not in capsys.readouterr().err


def test_converts_a_dump_document_and_warns(
    tmp_path,
    monkeypatch,
    capsys
):
    document = {
        "title": "Talk",
        "slides": [{"number": 1, "title": "T", "notes": "n", "body": ["ignored"]}],
    }
    captured = {}

    def fake_apply(spec: dict) -> dict:
        captured["spec"] = spec
        return {"updated": 1, "skipped": []}

    monkeypatch.setattr(patch, "apply", fake_apply)
    spec_file = tmp_path / "dump.json"
    spec_file.write_text(json.dumps(document))

    assert patch_command.run(argparse.Namespace(spec=str(spec_file))) == 0
    assert captured["spec"] == patch.from_dump(document)
    assert "only titles and notes" in capsys.readouterr().err
