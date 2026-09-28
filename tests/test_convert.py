import pathlib
import argparse
from slides.deckwerk import importer
from slides.commands import convert
from slides.keynote import build, export

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def an_args(**kw) -> argparse.Namespace:
    base = {
        "target": None,
        "format": "deckwerk",
        "output": None,
        "deckwerk_root": None,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def test_refuses_a_populated_default_output(
    tmp_path,
    monkeypatch,
    capsys
):
    # Mirrors a real course folder: 04_sep28_conditional_linear.key sits next
    # to a hand-edited 04_sep28_conditional_linear/ deck.json.
    source = tmp_path / "04_sep28_conditional_linear.key"
    source.touch()
    out = tmp_path / "04_sep28_conditional_linear"
    out.mkdir()
    deck_json = out / "deck.json"
    deck_json.write_bytes(b'{"edited": "minutes ago"}')
    before = deck_json.read_bytes()

    called = []
    monkeypatch.setattr(importer, "import_key", lambda *a, **kw: called.append(1))

    code = convert.run(an_args(target=str(source)))

    assert code != 0
    assert called == []
    assert deck_json.read_bytes() == before
    assert "already exists" in capsys.readouterr().err


def test_refuses_a_populated_explicit_output(
    tmp_path,
    monkeypatch
):
    source = tmp_path / "deck.key"
    source.touch()
    out = tmp_path / "somewhere_else"
    out.mkdir()
    (out / "deck.json").write_text("{}")

    called = []
    monkeypatch.setattr(importer, "import_key", lambda *a, **kw: called.append(1))

    code = convert.run(an_args(target=str(source), output=str(out)))

    assert code != 0
    assert called == []


def test_allows_an_existing_empty_directory(
    tmp_path,
    monkeypatch
):
    source = tmp_path / "deck.key"
    source.touch()
    out = tmp_path / "deck"
    out.mkdir()
    monkeypatch.setattr(
        importer, "import_key", lambda *a, **kw: {"report": {"unsupported": {}}}
    )

    assert convert.run(an_args(target=str(source))) == 0


def test_allows_a_brand_new_default_output(
    tmp_path,
    monkeypatch
):
    source = tmp_path / "deck.key"
    source.touch()
    monkeypatch.setattr(
        importer, "import_key", lambda *a, **kw: {"report": {"unsupported": {}}}
    )

    assert convert.run(an_args(target=str(source))) == 0


def test_keynote_route_builds_a_deckwerk_source_in_keynote(
    tmp_path,
    monkeypatch
):
    seen = {}
    monkeypatch.setattr(
        build,
        "build",
        lambda deck, out: seen.update(slides=len(deck.slides), out=str(out)),
    )
    out = tmp_path / "deck.key"

    code = convert.run(
        an_args(target=str(FIXTURE), format="keynote", output=str(out))
    )

    assert code == 0
    assert seen == {"slides": 3, "out": str(out)}


def test_keynote_route_passes_a_pptx_source_directly(
    tmp_path,
    monkeypatch
):
    source = tmp_path / "deck.pptx"
    source.touch()
    seen = {}
    monkeypatch.setattr(
        export,
        "open_and_save",
        lambda source, out: seen.update(source=str(source), out=str(out)),
    )
    out = tmp_path / "deck.key"

    code = convert.run(
        an_args(target=str(source), format="keynote", output=str(out))
    )

    assert code == 0
    assert seen["source"] == str(source)


def test_keynote_route_refuses_an_existing_output(
    tmp_path,
    monkeypatch,
    capsys
):
    source = tmp_path / "deck.pptx"
    source.touch()
    out = tmp_path / "deck.key"
    out.touch()
    called = []
    monkeypatch.setattr(export, "open_and_save", lambda *a, **kw: called.append(1))

    code = convert.run(
        an_args(target=str(source), format="keynote", output=str(out))
    )

    assert code != 0
    assert called == []
    assert "already exists" in capsys.readouterr().err


def test_pdf_route_from_a_keynote_source_skips_staging(
    tmp_path,
    monkeypatch
):
    source = tmp_path / "deck.key"
    source.touch()
    seen = {}
    monkeypatch.setattr(
        export,
        "export_pdf",
        lambda source, out: seen.update(source=str(source), out=str(out)),
    )
    out = tmp_path / "deck.pdf"

    code = convert.run(an_args(target=str(source), format="pdf", output=str(out)))

    assert code == 0
    assert seen["source"] == str(source)


def test_pdf_route_from_a_pptx_source_skips_staging(
    tmp_path,
    monkeypatch
):
    source = tmp_path / "deck.pptx"
    source.touch()
    seen = {}
    monkeypatch.setattr(
        export,
        "export_pdf",
        lambda source, out: seen.update(source=str(source), out=str(out)),
    )
    out = tmp_path / "deck.pdf"

    code = convert.run(an_args(target=str(source), format="pdf", output=str(out)))

    assert code == 0
    assert seen["source"] == str(source)


def test_pdf_route_builds_a_deckwerk_source_then_exports_it(
    tmp_path,
    monkeypatch
):
    seen = {}
    monkeypatch.setattr(build, "build", lambda deck, out: seen.update(built=str(out)))
    monkeypatch.setattr(
        export,
        "export_pdf",
        lambda source, out: seen.update(source=str(source), out=str(out)),
    )
    out = tmp_path / "deck.pdf"

    code = convert.run(an_args(target=str(FIXTURE), format="pdf", output=str(out)))

    assert code == 0
    assert seen["source"] == seen["built"]
    assert seen["source"].endswith(".key")
    assert not pathlib.Path(seen["source"]).exists()


def test_pdf_route_refuses_an_existing_output(
    tmp_path,
    monkeypatch,
    capsys
):
    source = tmp_path / "deck.key"
    source.touch()
    out = tmp_path / "deck.pdf"
    out.touch()
    called = []
    monkeypatch.setattr(export, "export_pdf", lambda *a, **kw: called.append(1))

    code = convert.run(an_args(target=str(source), format="pdf", output=str(out)))

    assert code != 0
    assert called == []
    assert "already exists" in capsys.readouterr().err
