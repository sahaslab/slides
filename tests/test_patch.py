import os
import json
import pathlib
import pytest
from slides.keynote import jxa, patch
from slides.readers.deckwerk import read
from slides.writers import json as json_writer

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


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


def test_removes_the_temp_file_after_returning(monkeypatch):
    seen = {}

    def fake_run_json(script: str) -> dict:
        path = script.split("readSpec(\"")[1].split("\")")[0]
        seen["path"] = path
        assert os.path.exists(path)
        return {"updated": 1, "skipped": []}

    monkeypatch.setattr(jxa, "run_json", fake_run_json)
    patch.apply({"1": {"title": "x"}})
    assert not os.path.exists(seen["path"])


def test_table_writes_are_bounded_by_the_live_cell_count():
    # JXA only; exercised for real by the controller's live-app check.
    assert "c < slide.tables[t].rows[r].cells.length" in patch.SCRIPT


def test_script_contains_the_byid_branch():
    # JXA only; exercised for real by the controller's live-app check.
    assert "app.documents.byId(documentId)" in patch.SCRIPT
    assert "No open document with id " in patch.SCRIPT


def test_without_a_document_id_the_front_document_is_targeted(monkeypatch):
    captured = {}

    def fake_run_json(script: str) -> dict:
        captured["script"] = script
        return {"updated": 1, "skipped": []}

    monkeypatch.setattr(jxa, "run_json", fake_run_json)
    patch.apply({"1": {"title": "x"}})
    assert "var documentId = null;" in captured["script"]
    assert "doc = app.documents[0];" in captured["script"]


def test_a_document_id_selects_that_document_by_id(monkeypatch):
    captured = {}

    def fake_run_json(script: str) -> dict:
        captured["script"] = script
        return {"updated": 1, "skipped": []}

    monkeypatch.setattr(jxa, "run_json", fake_run_json)
    patch.apply({"1": {"title": "x"}}, document="doc-123")
    assert "var documentId = \"doc-123\";" in captured["script"]


def test_from_dump_takes_only_title_and_notes():
    document = {
        "slides": [
            {"number": 1, "title": "T1", "notes": "n1", "body": ["ignored"]},
            {"number": 2, "title": None, "notes": "n2"},
        ]
    }
    assert patch.from_dump(document) == {
        "1": {"title": "T1", "notes": "n1"},
        "2": {"notes": "n2"},
    }


def test_from_dump_round_trips_a_real_dump(monkeypatch):
    document = json_writer.to_dict(read(FIXTURE))
    spec = patch.from_dump(document)
    assert spec
    for entry in spec.values():
        assert set(entry) <= {"title", "notes"}

    monkeypatch.setattr(jxa, "run_json", lambda script: {"updated": len(spec), "skipped": []})
    assert patch.apply(spec)["updated"] == len(spec)
