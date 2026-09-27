import pathlib
import shutil
import argparse
from slides.commands import dump

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def an_args(**kw) -> argparse.Namespace:
    base = {
        "target": str(FIXTURE),
        "format": "md",
        "output": None,
        "out_dir": None,
        "notes_only": False,
        "clipboard": False,
        "via_deckwerk": False,
        "assets_dir": None,
        "copy_media": False,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def test_writes_markdown_to_stdout(capsys):
    assert dump.run(an_args()) == 0
    assert "# Mini" in capsys.readouterr().out


def test_writes_to_a_named_file(tmp_path):
    out = tmp_path / "deck.md"
    assert dump.run(an_args(output=str(out))) == 0
    assert "# Mini" in out.read_text()


def test_out_dir_names_the_file_after_the_deck(tmp_path):
    assert dump.run(an_args(out_dir=str(tmp_path))) == 0
    assert (tmp_path / "mini_deckwerk.md").exists()


def test_json_format_uses_the_json_extension(tmp_path):
    assert dump.run(an_args(format="json", out_dir=str(tmp_path))) == 0
    assert (tmp_path / "mini_deckwerk.json").exists()


def test_web_embed_is_copied_beside_the_output(tmp_path):
    out = tmp_path / "deck.md"
    assert dump.run(an_args(output=str(out))) == 0
    copied = tmp_path / "deck_assets" / "demo.html"
    assert copied.exists()
    assert copied.read_text().strip() != ""
    assert "deck_assets/demo.html" in out.read_text()


def test_assets_dir_overrides_the_default_location(tmp_path):
    out = tmp_path / "deck.md"
    where = tmp_path / "elsewhere"
    assert dump.run(an_args(output=str(out), assets_dir=str(where))) == 0
    assert (where / "demo.html").exists()


def test_video_is_linked_but_not_copied_by_default(tmp_path):
    out = tmp_path / "deck.md"
    assert dump.run(an_args(output=str(out))) == 0
    assert not (tmp_path / "deck_assets" / "clip.mp4").exists()
    assert "clip.mp4" in out.read_text()


def test_stdout_copies_nothing_and_warns(tmp_path, capsys):
    assert dump.run(an_args()) == 0
    captured = capsys.readouterr()
    assert "demo.html" in captured.out
    assert "not copied" in captured.err


def test_a_missing_asset_is_reported_and_does_not_fail_the_dump(tmp_path):
    deck_dir = tmp_path / "deck"
    shutil.copytree(FIXTURE, deck_dir)
    (deck_dir / "assets" / "web" / "demo.html").unlink()
    out = tmp_path / "deck.md"
    args = an_args(target=str(deck_dir), output=str(out))
    assert dump.run(args) == 0
    assert out.exists()
