import json
import tempfile
from slides.keynote import jxa

FIELDS = {"title", "body", "notes", "images", "tables", "master"}

SCRIPT = """
ObjC.import("Foundation");
function readSpec(path) {
  var s = $.NSString.stringWithContentsOfFileEncodingError(
    path, $.NSUTF8StringEncoding, null);
  return JSON.parse(ObjC.unwrap(s));
}
var spec = readSpec(%s);
var app = Application(%s);
var documentId = %s;
var doc;
if (documentId) {
  doc = app.documents.byId(documentId);
  if (!doc.exists()) { throw new Error("No open document with id " + documentId); }
} else {
  if (app.documents.length === 0) { throw new Error("No presentation is open."); }
  doc = app.documents[0];
}
var updated = 0;
var skipped = [];
for (var key in spec) {
  var index = parseInt(key, 10) - 1;
  if (index < 0 || index >= doc.slides.length) { skipped.push(parseInt(key, 10)); continue; }
  var slide = doc.slides[index];
  var entry = spec[key];
  if (entry.title !== undefined) { slide.defaultTitleItem.objectText = entry.title; }
  if (entry.notes !== undefined) { slide.presenterNotes = entry.notes; }
  if (entry.body !== undefined) {
    var text = Array.isArray(entry.body) ? entry.body.join("\\n") : entry.body;
    slide.defaultBodyItem.objectText = text;
  }
  if (entry.images !== undefined) {
    for (var i = 0; i < entry.images.length; i++) {
      slide.images.push(app.Image({file: Path(entry.images[i])}));
    }
  }
  if (entry.tables !== undefined) {
    for (var t = 0; t < entry.tables.length && t < slide.tables.length; t++) {
      var rows = entry.tables[t];
      for (var r = 0; r < rows.length && r < slide.tables[t].rows.length; r++) {
        for (var c = 0; c < rows[r].length && c < slide.tables[t].rows[r].cells.length; c++) {
          slide.tables[t].rows[r].cells[c].value = rows[r][c];
        }
      }
    }
  }
  updated += 1;
}
JSON.stringify({updated: updated, skipped: skipped});
"""


def apply(
    spec: dict,
    app: str | None = None,
    document: str | None = None,
) -> dict:
    _check(spec)
    name = app or jxa.app_name()
    document_id = jxa.literal(document) if document is not None else "null"
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="slides-patch-",
    ) as handle:
        json.dump(spec, handle)
        handle.flush()
        script = SCRIPT % (
            jxa.literal(handle.name),
            jxa.literal(name),
            document_id,
        )
        return jxa.run_json(script)


def from_dump(document: dict) -> dict:
    spec = {}
    for slide in document.get("slides", []):
        entry = {"notes": slide.get("notes", "")}
        if slide.get("title") is not None:
            entry["title"] = slide["title"]
        spec[str(slide["number"])] = entry
    return spec


def _check(spec: dict) -> None:
    for key, entry in spec.items():
        if not str(key).isdigit():
            raise ValueError("%r is not a slide number" % (key,))
        unknown = set(entry) - FIELDS
        if unknown:
            raise ValueError(
                "unknown field(s) %s; expected any of %s"
                % (", ".join(sorted(unknown)), ", ".join(sorted(FIELDS)))
            )
