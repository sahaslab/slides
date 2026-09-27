import pytest
from slides.keynote import jxa, scaffold


def test_creates_then_patches(monkeypatch):
    calls = []
    monkeypatch.setattr(
        jxa,
        "run_json",
        lambda script: calls.append(script) or {"created": 2, "firstIndex": 1, "id": "doc-1"},
    )
    monkeypatch.setattr(
        "slides.keynote.patch.apply",
        lambda spec, app=None, document=None: calls.append("patch")
        or {"updated": 2, "skipped": []},
    )
    spec = {"1": {"title": "One"}, "2": {"title": "Two", "master": "Title & Bullets"}}
    result = scaffold.build(spec)
    assert result["created"] == 2
    assert calls[-1] == "patch"


def test_master_is_stripped_before_patching(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        jxa, "run_json", lambda script: {"created": 1, "firstIndex": 1, "id": "doc-1"}
    )
    monkeypatch.setattr(
        "slides.keynote.patch.apply",
        lambda spec, app=None, document=None: seen.update(spec=spec)
        or {"updated": 1, "skipped": []},
    )
    scaffold.build({"1": {"title": "One", "master": "Blank"}})
    assert "master" not in seen["spec"]["1"]
    assert seen["spec"]["1"]["title"] == "One"


def test_slides_are_created_in_numeric_order(monkeypatch):
    seen = {}

    def fake_run_json(script: str) -> dict:
        seen["script"] = script
        return {"created": 3, "firstIndex": 1, "id": "doc-1"}

    monkeypatch.setattr(jxa, "run_json", fake_run_json)
    monkeypatch.setattr(
        "slides.keynote.patch.apply",
        lambda spec, app=None, document=None: {"updated": 3, "skipped": []},
    )
    scaffold.build({"10": {"title": "Ten"}, "2": {"title": "Two"}, "1": {"title": "One"}})
    masters = seen["script"]
    assert masters.index("\"1\"") < masters.index("\"2\"") < masters.index("\"10\"")


def test_rejects_a_bad_spec():
    with pytest.raises(ValueError, match="slide number"):
        scaffold.build({"first": {"title": "x"}})


def test_patch_keys_start_after_the_documents_existing_slides(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        jxa, "run_json", lambda script: {"created": 2, "firstIndex": 6, "id": "doc-1"}
    )
    monkeypatch.setattr(
        "slides.keynote.patch.apply",
        lambda spec, app=None, document=None: seen.update(spec=spec)
        or {"updated": 2, "skipped": []},
    )
    scaffold.build({"1": {"title": "One"}, "2": {"title": "Two"}})
    assert set(seen["spec"]) == {"6", "7"}
    assert seen["spec"]["6"]["title"] == "One"
    assert seen["spec"]["7"]["title"] == "Two"
    assert "1" not in seen["spec"]


def test_checks_masters_exist_before_creating_any_slide():
    checked_at = scaffold.SCRIPT_CREATE.index("available.indexOf(name) === -1")
    created_at = scaffold.SCRIPT_CREATE.index("doc.slides.push(made)")
    assert checked_at < created_at
    assert "No master slide named " in scaffold.SCRIPT_CREATE
    assert "available: " in scaffold.SCRIPT_CREATE


def test_front_document_path_guards_against_no_open_presentation():
    assert "No presentation is open." in scaffold.FRONT_DOCUMENT
    guarded_at = scaffold.FRONT_DOCUMENT.index("app.documents.length === 0")
    assigned_at = scaffold.FRONT_DOCUMENT.index("var doc = app.documents[0];")
    assert guarded_at < assigned_at


def test_template_is_copied_and_the_copy_is_opened_not_the_template(
    tmp_path,
    monkeypatch
):
    template = tmp_path / "template.key"
    template.write_bytes(b"TEMPLATE-BYTES")
    output = tmp_path / "out.key"
    captured = {}
    monkeypatch.setattr(
        jxa,
        "run_json",
        lambda script: captured.update(script=script)
        or {"created": 1, "firstIndex": 1, "id": "doc-1"},
    )
    monkeypatch.setattr(
        "slides.keynote.patch.apply",
        lambda spec, app=None, document=None: {"updated": 1, "skipped": []},
    )

    scaffold.build(
        {"1": {"title": "One"}},
        template=str(template),
        output=str(output),
    )

    assert output.read_bytes() == b"TEMPLATE-BYTES"
    assert template.read_bytes() == b"TEMPLATE-BYTES"
    assert str(output) in captured["script"]
    assert str(template) not in captured["script"]


def test_template_as_a_directory_bundle_is_copied_with_copytree(
    tmp_path,
    monkeypatch
):
    template = tmp_path / "template.key"
    template.mkdir()
    (template / "Index").mkdir()
    (template / "Index" / "Document.iwa").write_bytes(b"IWA-BYTES")
    output = tmp_path / "out.key"
    captured = {}
    monkeypatch.setattr(
        jxa,
        "run_json",
        lambda script: captured.update(script=script)
        or {"created": 1, "firstIndex": 1, "id": "doc-1"},
    )
    monkeypatch.setattr(
        "slides.keynote.patch.apply",
        lambda spec, app=None, document=None: {"updated": 1, "skipped": []},
    )

    scaffold.build(
        {"1": {"title": "One"}},
        template=str(template),
        output=str(output),
    )

    assert output.is_dir()
    assert (output / "Index" / "Document.iwa").read_bytes() == b"IWA-BYTES"
    assert (template / "Index" / "Document.iwa").read_bytes() == b"IWA-BYTES"
    assert str(output) in captured["script"]


def test_refuses_to_overwrite_an_existing_output(
    tmp_path,
    monkeypatch
):
    template = tmp_path / "template.key"
    template.write_text("t")
    output = tmp_path / "out.key"
    output.write_text("existing")

    def fail_if_called(script: str) -> dict:
        raise AssertionError("must not run JXA when output already exists")

    monkeypatch.setattr(jxa, "run_json", fail_if_called)

    with pytest.raises(FileExistsError, match="already exists"):
        scaffold.build(
            {"1": {"title": "One"}},
            template=str(template),
            output=str(output),
        )
    assert output.read_text() == "existing"


def test_without_template_uses_the_front_document_and_ignores_output(
    monkeypatch,
    tmp_path
):
    captured = {}
    monkeypatch.setattr(
        jxa,
        "run_json",
        lambda script: captured.update(script=script)
        or {"created": 1, "firstIndex": 1, "id": "doc-1"},
    )
    monkeypatch.setattr(
        "slides.keynote.patch.apply",
        lambda spec, app=None, document=None: {"updated": 1, "skipped": []},
    )
    ignored_output = tmp_path / "ignored.key"

    scaffold.build(
        {"1": {"title": "One"}},
        template=None,
        output=str(ignored_output),
    )

    assert scaffold.FRONT_DOCUMENT in captured["script"]
    assert not ignored_output.exists()


def test_document_id_flows_from_create_into_the_patch_script(monkeypatch):
    scripts = []

    def fake_run_json(script: str) -> dict:
        scripts.append(script)
        if len(scripts) == 1:
            return {"created": 1, "firstIndex": 1, "id": "doc-abc"}
        return {"updated": 1, "skipped": []}

    monkeypatch.setattr(jxa, "run_json", fake_run_json)
    scaffold.build({"1": {"title": "One"}})

    patch_script = scripts[1]
    assert "var documentId = \"doc-abc\";" in patch_script
    assert "app.documents.byId(documentId)" in patch_script
