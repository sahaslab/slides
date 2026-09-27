import json
import pytest
from slides.keynote import jxa, patch


def test_writes_the_spec_to_a_file_and_reports(monkeypatch):
    captured = {}

    def fake_run_json(script: str) -> dict:
        captured["script"] = script
        path = script.split("readSpec(\"")[1].split("\")")[0]
        captured["spec"] = json.load(open(path))
        return {"updated": 2, "skipped": []}

    monkeypatch.setattr(jxa, "run_json", fake_run_json)
    spec = {"1": {"title": "New"}, "2": {"notes": "Say it."}}
    result = patch.apply(spec)
    assert result == {"updated": 2, "skipped": []}
    assert captured["spec"] == spec


def test_rejects_a_spec_that_is_not_keyed_by_slide_number():
    with pytest.raises(ValueError, match="slide number"):
        patch.apply({"first": {"title": "x"}})


def test_rejects_unknown_fields():
    with pytest.raises(ValueError, match="colour"):
        patch.apply({"1": {"colour": "red"}})


def test_accepts_every_documented_field(monkeypatch):
    monkeypatch.setattr(jxa, "run_json", lambda script: {"updated": 1, "skipped": []})
    spec = {
        "1": {
            "title": "T",
            "body": ["a", "b"],
            "notes": "n",
            "images": ["/tmp/x.png"],
            "tables": [[["a", "b"]]],
        }
    }
    assert patch.apply(spec)["updated"] == 1
