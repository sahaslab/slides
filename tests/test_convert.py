import argparse
from slides.deckwerk import importer
from slides.commands import convert


def an_args(**kw) -> argparse.Namespace:
    base = {
        "target": None,
        "format": "deckwerk",
        "output": None,
        "deckwerk_root": None,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def test_refuses_a_populated_default_output(tmp_path, monkeypatch, capsys):
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


def test_refuses_a_populated_explicit_output(tmp_path, monkeypatch):
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


def test_allows_an_existing_empty_directory(tmp_path, monkeypatch):
    source = tmp_path / "deck.key"
    source.touch()
    out = tmp_path / "deck"
    out.mkdir()
    monkeypatch.setattr(
        importer, "import_key", lambda *a, **kw: {"report": {"unsupported": {}}}
    )

    assert convert.run(an_args(target=str(source))) == 0


def test_allows_a_brand_new_default_output(tmp_path, monkeypatch):
    source = tmp_path / "deck.key"
    source.touch()
    monkeypatch.setattr(
        importer, "import_key", lambda *a, **kw: {"report": {"unsupported": {}}}
    )

    assert convert.run(an_args(target=str(source))) == 0
