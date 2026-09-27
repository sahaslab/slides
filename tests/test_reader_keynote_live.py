import shutil
import pytest
from slides.keynote import jxa
from slides.readers import keynote_live

has_osascript = pytest.mark.skipif(
    shutil.which("osascript") is None,
    reason="not a Mac",
)


def test_reports_when_no_document_is_open(monkeypatch):
    def explode(script: str):
        raise jxa.KeynoteError("Error: no document")

    monkeypatch.setattr(jxa, "run_json", explode)
    with pytest.raises(jxa.KeynoteError, match="no document"):
        keynote_live.read()


def test_builds_a_deck_from_the_payload(monkeypatch):
    payload = {
        "name": "Live talk",
        "width": 1920,
        "height": 1080,
        "slides": [
            {
                "title": "One",
                "items": ["One", "Body text"],
                "notes": "Say it.",
                "tables": [[["a", "b"], ["1", "2"]]],
            }
        ],
    }
    monkeypatch.setattr(jxa, "run_json", lambda script: payload)
    deck = keynote_live.read()
    assert deck.title == "Live talk"
    assert deck.kind == "live"
    assert deck.slides[0].title == "One"
    assert [i.text for i in deck.slides[0].body_items()] == ["Body text"]
    assert deck.slides[0].tables[0].rows[1] == ["1", "2"]


@has_osascript
def test_quoted_keeps_a_backslash_literal():
    name = "back\\slash"
    script = "JSON.stringify(%s)" % (jxa.literal(name),)
    assert jxa.run_json(script) == name


@has_osascript
def test_quoted_keeps_a_backslash_and_a_quote_literal():
    name = "back\\slash \"quoted\""
    script = "JSON.stringify(%s)" % (jxa.literal(name),)
    assert jxa.run_json(script) == name
