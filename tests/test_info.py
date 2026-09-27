import pathlib
import argparse
import pytest
from slides.commands import info
from slides.readers import read

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def test_summarises_the_inventory():
    out = info.summarise(read(FIXTURE))
    assert "Mini" in out
    assert "3 slides" in out
    assert "1920" in out and "1080" in out


def test_counts_text_tables_images_and_notes():
    out = info.summarise(read(FIXTURE))
    assert "2 tables" in out
    assert "1 image" in out
    assert "1 slide with notes" in out


def test_counts_web_pages_and_videos():
    out = info.summarise(read(FIXTURE))
    assert "1 web page, 1 video" in out


def test_run_prints_and_succeeds(capsys):
    args = argparse.Namespace(target=str(FIXTURE), deckwerk_root=None)
    assert info.run(args) == 0
    assert "Mini" in capsys.readouterr().out


def test_a_missing_checkout_degrades_to_one_stderr_line(
    monkeypatch,
    capsys
):
    from slides.deckwerk import agent, importer

    def fake_validate(
        *args: object,
        **kwargs: object
    ) -> dict:
        raise importer.MissingDeckWerk("no checkout here")

    monkeypatch.setattr(agent, "validate", fake_validate)
    args = argparse.Namespace(target=str(FIXTURE), deckwerk_root=None)

    assert info.run(args) == 0
    assert "no checkout here" in capsys.readouterr().err


def test_an_importer_crash_is_not_swallowed(monkeypatch):
    from slides.deckwerk import agent, importer

    def fake_validate(
        *args: object,
        **kwargs: object
    ) -> dict:
        raise importer.ImporterFailed("crashed")

    monkeypatch.setattr(agent, "validate", fake_validate)
    args = argparse.Namespace(target=str(FIXTURE), deckwerk_root=None)

    with pytest.raises(importer.ImporterFailed):
        info.run(args)
