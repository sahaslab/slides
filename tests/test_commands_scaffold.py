import json
import argparse
from slides.keynote import scaffold
from slides.commands import scaffold as scaffold_command


def test_passes_the_spec_and_template_straight_through(tmp_path, monkeypatch, capsys):
    captured = {}

    def fake_build(spec, template=None, output=None):
        captured["spec"] = spec
        captured["template"] = template
        captured["output"] = output
        return {"created": 2, "firstIndex": 1}

    monkeypatch.setattr(scaffold, "build", fake_build)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps({"1": {"title": "One"}}))

    args = argparse.Namespace(spec=str(spec_file), template=None, output=None)
    assert scaffold_command.run(args) == 0
    assert captured["spec"] == {"1": {"title": "One"}}
    assert captured["template"] is None
    assert captured["output"] is None
    assert "Created 2 slides" in capsys.readouterr().err


def test_output_defaults_to_the_spec_path_with_a_key_suffix(tmp_path, monkeypatch):
    captured = {}

    def fake_build(spec, template=None, output=None):
        captured["output"] = output
        return {"created": 1, "firstIndex": 1}

    monkeypatch.setattr(scaffold, "build", fake_build)
    spec_file = tmp_path / "deck.json"
    spec_file.write_text(json.dumps({"1": {"title": "x"}}))

    args = argparse.Namespace(spec=str(spec_file), template="/tmp/t.key", output=None)
    scaffold_command.run(args)
    assert captured["output"] == str(tmp_path / "deck.key")


def test_output_flag_overrides_the_default(tmp_path, monkeypatch):
    captured = {}

    def fake_build(spec, template=None, output=None):
        captured["output"] = output
        return {"created": 1, "firstIndex": 1}

    monkeypatch.setattr(scaffold, "build", fake_build)
    spec_file = tmp_path / "deck.json"
    spec_file.write_text(json.dumps({"1": {"title": "x"}}))

    args = argparse.Namespace(
        spec=str(spec_file),
        template="/tmp/t.key",
        output="/tmp/custom.key",
    )
    scaffold_command.run(args)
    assert captured["output"] == "/tmp/custom.key"


def test_output_is_ignored_without_a_template(tmp_path, monkeypatch):
    captured = {}

    def fake_build(spec, template=None, output=None):
        captured["output"] = output
        return {"created": 1, "firstIndex": 1}

    monkeypatch.setattr(scaffold, "build", fake_build)
    spec_file = tmp_path / "deck.json"
    spec_file.write_text(json.dumps({"1": {"title": "x"}}))

    args = argparse.Namespace(spec=str(spec_file), template=None, output="/tmp/ignored.key")
    scaffold_command.run(args)
    assert captured["output"] is None
