import shutil
import pytest
from slides.keynote import export, jxa


def test_save_script_quotes_both_paths():
    script = export.SCRIPT_SAVE % ("\"Keynote\"", "\"/a/in.pptx\"", "\"/b/out.key\"")
    assert "/a/in.pptx" in script and "/b/out.key" in script


def test_open_and_save_invokes_jxa(monkeypatch):
    seen = {}
    monkeypatch.setattr(jxa, "run", lambda script: seen.setdefault("script", script))
    export.open_and_save("/a/in.pptx", "/b/out.key")
    assert "in.pptx" in seen["script"]
    assert "out.key" in seen["script"]


def test_export_pdf_asks_for_pdf(monkeypatch):
    seen = {}
    monkeypatch.setattr(jxa, "run", lambda script: seen.setdefault("script", script))
    export.export_pdf("/a/in.key", "/b/out.pdf")
    assert "PDF" in seen["script"]


@pytest.mark.skipif(shutil.which("osascript") is None, reason="not a Mac")
def test_paths_with_quotes_do_not_break_the_script(monkeypatch):
    seen = {}
    monkeypatch.setattr(jxa, "run", lambda script: seen.setdefault("script", script))
    export.open_and_save("/a/we\"ird.pptx", "/b/out.key")
    assert "\\\"" in seen["script"]


def test_already_open_guard_captures_ids_before_opening():
    # JXA only; exercised for real by the controller's live-app check.
    for script in (export.SCRIPT_SAVE, export.SCRIPT_PDF):
        before_at = script.index("var before = app.documents.id();")
        open_at = script.index("app.open(Path(sourcePath))")
        assert before_at < open_at
        assert "alreadyOpen = before.indexOf(doc.id()) !== -1;" in script


def test_no_template_compares_document_file_paths():
    # The guard decides identity by document id, not by comparing paths.
    for script in (export.SCRIPT_SAVE, export.SCRIPT_PDF):
        assert ".file()" not in script
        assert "candidateFile" not in script


def test_close_is_conditional_on_the_already_open_guard():
    # JXA only; exercised for real by the controller's live-app check.
    for script in (export.SCRIPT_SAVE, export.SCRIPT_PDF):
        assert "if (!alreadyOpen) {" in script
        assert "doc.close({saving: \"no\"});" in script
