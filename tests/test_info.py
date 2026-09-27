import pathlib
import argparse
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
