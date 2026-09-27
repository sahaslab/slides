import shutil
import pytest
from slides.keynote import jxa

has_osascript = pytest.mark.skipif(
    shutil.which("osascript") is None,
    reason="not a Mac",
)


def test_app_name_defaults_to_keynote(monkeypatch):
    monkeypatch.delenv("SLIDES_KEYNOTE_APP", raising=False)
    assert jxa.app_name() == "Keynote"


def test_app_name_honours_the_environment(monkeypatch):
    monkeypatch.setenv("SLIDES_KEYNOTE_APP", "Keynote Creator Studio")
    assert jxa.app_name() == "Keynote Creator Studio"


@has_osascript
def test_run_returns_stdout():
    assert jxa.run("'hello'").strip() == "hello"


@has_osascript
def test_run_json_parses():
    assert jxa.run_json("JSON.stringify({a: 1})") == {"a": 1}


@has_osascript
def test_failure_raises_a_readable_error():
    with pytest.raises(jxa.KeynoteError) as caught:
        jxa.run("throw new Error('boom')")
    assert "boom" in str(caught.value)


@has_osascript
def test_literal_round_trips_quotes_backslashes_and_newlines():
    value = "back\\slash \"quoted\"\nnewline"
    script = "JSON.stringify(%s)" % (jxa.literal(value),)
    assert jxa.run_json(script) == value
