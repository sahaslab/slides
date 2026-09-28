import pathlib
from slides.keynote import jxa

# Shared by both templates: find a document already open at `sourcePath` (so
# the script never closes something the user had open); otherwise open it
# fresh. `doc` and `alreadyOpen` are left in scope for the caller to finish.
_GUARD = """
var app = Application(%s);
app.includeStandardAdditions = true;
var sourcePath = %s;
var outPath = %s;
var alreadyOpen = false;
var doc = null;
for (var i = 0; i < app.documents.length; i++) {
  var candidate = app.documents[i];
  var candidateFile = null;
  try { candidateFile = candidate.file().toString(); } catch (e) {}
  if (candidateFile === sourcePath) {
    doc = candidate;
    alreadyOpen = true;
    break;
  }
}
if (!doc) {
  doc = app.open(Path(sourcePath));
}
"""

SCRIPT_SAVE = _GUARD + """app.export(doc, {to: Path(outPath), as: "Keynote 09"});
if (!alreadyOpen) {
  doc.close({saving: "no"});
}
"saved";
"""

SCRIPT_PDF = _GUARD + """app.export(doc, {to: Path(outPath), as: "PDF"});
if (!alreadyOpen) {
  doc.close({saving: "no"});
}
"exported";
"""


def open_and_save(
    source: str | pathlib.Path,
    out: str | pathlib.Path,
) -> None:
    script = SCRIPT_SAVE % (
        jxa.literal(jxa.app_name()),
        jxa.literal(str(pathlib.Path(source).resolve())),
        jxa.literal(str(pathlib.Path(out).resolve())),
    )
    jxa.run(script)


def export_pdf(
    source: str | pathlib.Path,
    out: str | pathlib.Path,
) -> None:
    script = SCRIPT_PDF % (
        jxa.literal(jxa.app_name()),
        jxa.literal(str(pathlib.Path(source).resolve())),
        jxa.literal(str(pathlib.Path(out).resolve())),
    )
    jxa.run(script)
