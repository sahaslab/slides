import pathlib
import shutil
import argparse
from slides.commands import dump
from slides.model import Deck, Embed, Slide

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def an_args(**kw: object) -> argparse.Namespace:
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


def test_stdout_copies_nothing_and_warns(
    tmp_path,
    capsys
):
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


def test_basename_collision_gets_a_unique_sidecar_name(tmp_path):
    deck_dir = tmp_path / "deck"
    (deck_dir / "assets" / "web" / "a").mkdir(parents=True)
    (deck_dir / "assets" / "web" / "b").mkdir(parents=True)
    (deck_dir / "assets" / "web" / "a" / "index.html").write_text("<p>A</p>")
    (deck_dir / "assets" / "web" / "b" / "index.html").write_text("<p>B</p>")
    deck = Deck(
        title="Two demos",
        source=str(deck_dir),
        slides=[
            Slide(number=1, embeds=[Embed(kind="web", src="assets/web/a/index.html")]),
            Slide(number=2, embeds=[Embed(kind="web", src="assets/web/b/index.html")]),
        ],
    )
    written = dump.copy_embeds(deck, tmp_path / "out_assets")
    assert set(written) == {"assets/web/a/index.html", "assets/web/b/index.html"}
    a_path = pathlib.Path(written["assets/web/a/index.html"])
    b_path = pathlib.Path(written["assets/web/b/index.html"])
    assert a_path != b_path
    assert a_path.exists() and b_path.exists()
    assert a_path.read_text() == "<p>A</p>"
    assert b_path.read_text() == "<p>B</p>"


def test_same_src_seen_twice_is_copied_once(tmp_path):
    deck_dir = tmp_path / "deck"
    (deck_dir / "assets" / "web").mkdir(parents=True)
    (deck_dir / "assets" / "web" / "index.html").write_text("<p>Shared</p>")
    deck = Deck(
        title="Repeated demo",
        source=str(deck_dir),
        slides=[
            Slide(number=1, embeds=[Embed(kind="web", src="assets/web/index.html")]),
            Slide(number=2, embeds=[Embed(kind="web", src="assets/web/index.html")]),
        ],
    )
    out_dir = tmp_path / "out_assets"
    written = dump.copy_embeds(deck, out_dir)
    assert written == {"assets/web/index.html": str(out_dir / "index.html")}
    assert [p.name for p in out_dir.iterdir()] == ["index.html"]
