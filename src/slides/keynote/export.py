import pathlib
from slides.keynote import jxa

# Shared by both templates. Cocoa apps hand back the existing document when
# you ask to open a file that is already open, so `app.open` alone can never
# tell a fresh open from a reused one. Instead, capture the ids of every
# document open *before* the call, then check whether the returned document's
# id was already in that set: the document was already open exactly when it
# was. This is identity, not a path comparison, so it can't be fooled by
# /tmp vs /private/tmp, a symlinked home, or Unicode filename variants.
# `doc` and `alreadyOpen` are left in scope for the caller to finish.
_GUARD = """
var app = Application(%s);
app.includeStandardAdditions = true;
var sourcePath = %s;
var outPath = %s;
var before = app.documents.id();
var doc = app.open(Path(sourcePath));
var alreadyOpen = before.indexOf(doc.id()) !== -1;
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
