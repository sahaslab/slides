import os
import pathlib
import tempfile
import pytest
from slides.deckwerk import importer

REAL_ROOT = pathlib.Path(os.path.expanduser("~/src/deckwerk"))
needs_deckwerk = pytest.mark.skipif(
    not (REAL_ROOT / "importers/keynote/import_keynote.py").exists(),
    reason="no DeckWerk checkout",
)


def test_find_root_prefers_the_explicit_argument(tmp_path):
    (tmp_path / "importers/keynote").mkdir(parents=True)
    (tmp_path / "importers/keynote/import_keynote.py").touch()
    assert importer.find_root(str(tmp_path)) == tmp_path


def test_find_root_reads_the_environment(
    tmp_path,
    monkeypatch
):
    (tmp_path / "importers/keynote").mkdir(parents=True)
    (tmp_path / "importers/keynote/import_keynote.py").touch()
    monkeypatch.setenv("SLIDES_DECKWERK_ROOT", str(tmp_path))
    assert importer.find_root() == tmp_path


def test_missing_checkout_says_what_to_do(
    tmp_path,
    monkeypatch
):
    # DEFAULT_ROOT is also neutralised: this suite runs on the very machine
    # that has a real checkout at ~/src/deckwerk, so leaving it in place
    # would let find_root() fall through to it instead of raising.
    monkeypatch.setenv("SLIDES_DECKWERK_ROOT", str(tmp_path / "nope"))
    monkeypatch.setattr(importer, "DEFAULT_ROOT", str(tmp_path / "also-nope"))
    with pytest.raises(importer.MissingDeckWerk) as caught:
        importer.find_root()
    assert "SLIDES_DECKWERK_ROOT" in str(caught.value)


def test_interpreter_prefers_the_import_venv(tmp_path):
    venv = tmp_path / ".venv-import/bin"
    venv.mkdir(parents=True)
    python = venv / "python"
    python.touch(mode=0o755)
    assert importer.interpreter(tmp_path) == str(python)


def test_interpreter_falls_back_to_our_own(tmp_path):
    import sys
    assert importer.interpreter(tmp_path) == sys.executable


def test_read_via_import_cleans_up_its_staging_dir_on_failure(monkeypatch):
    def fail(
        *args: object,
        **kwargs: object
    ) -> dict:
        raise importer.ImporterFailed("boom")

    monkeypatch.setattr(importer, "import_key", fail)
    with pytest.raises(importer.ImporterFailed):
        importer.read_via_import("whatever.key")
    leftovers = list(pathlib.Path(tempfile.gettempdir()).glob("slides-import-*"))
    assert leftovers == []


@needs_deckwerk
def test_read_via_import_matches_the_fast_path():
    key = pathlib.Path(os.path.expanduser(
        "~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote"
        "/09_oct14_tfidf_imbalance_eval.key"
    ))
    if not key.exists():
        pytest.skip("no sample .key")
    from slides.readers.keynote_file import read
    assert len(importer.read_via_import(key).slides) == len(read(key).slides)


@needs_deckwerk
def test_report_runs_without_writing(tmp_path):
    key = pathlib.Path(os.path.expanduser(
        "~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote"
        "/09_oct14_tfidf_imbalance_eval.key"
    ))
    if not key.exists():
        pytest.skip("no sample .key")
    result = importer.report(key)
    assert isinstance(result, dict)
    assert not list(tmp_path.iterdir())
