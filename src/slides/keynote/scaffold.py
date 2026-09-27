import json
import pathlib
import shutil
from slides.keynote import jxa, patch

FRONT_DOCUMENT = (
    "if (app.documents.length === 0) "
    "{ throw new Error(\"No presentation is open.\"); }\n"
    "var doc = app.documents[0];"
)

SCRIPT_CREATE = """
var app = Application(%s);
app.includeStandardAdditions = true;
%s
var wanted = %s;
var available = [];
for (var m = 0; m < doc.masterSlides.length; m++) {
  available.push(doc.masterSlides[m].name());
}
for (var i = 0; i < wanted.length; i++) {
  var name = wanted[i].master;
  if (name && available.indexOf(name) === -1) {
    throw new Error(
      "No master slide named " + name + "; available: " + available.join(", ")
    );
  }
}
var firstIndex = doc.slides.length + 1;
var created = 0;
for (var i = 0; i < wanted.length; i++) {
  var name = wanted[i].master;
  var made;
  if (name) {
    made = app.Slide({baseSlide: doc.masterSlides.byName(name)});
  } else {
    made = app.Slide();
  }
  doc.slides.push(made);
  created += 1;
}
JSON.stringify({created: created, firstIndex: firstIndex, id: doc.id()});
"""


def build(
    spec: dict,
    template: str | None = None,
    output: str | None = None,
) -> dict:
    patch._check(spec)
    order = sorted(spec, key=lambda k: int(k))
    wanted = [{"key": key, "master": spec[key].get("master")} for key in order]
    document = _document_statement(template, output)
    script = SCRIPT_CREATE % (
        jxa.literal(jxa.app_name()),
        document,
        json.dumps(wanted),
    )
    result = jxa.run_json(script)
    patch.apply(
        _without_master(spec, order, result["firstIndex"]),
        document=result["id"],
    )
    return result


def _document_statement(
    template: str | None,
    output: str | None,
) -> str:
    if template is None:
        return FRONT_DOCUMENT
    source = pathlib.Path(template)
    destination = pathlib.Path(output)
    if destination.exists():
        raise FileExistsError("%s already exists; refusing to overwrite" % (destination,))
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copyfile(source, destination)
    return "var doc = app.open(Path(%s));" % (jxa.literal(str(destination)),)


def _without_master(
    spec: dict,
    order: list[str],
    first_index: int,
) -> dict:
    return {
        str(position): {k: v for k, v in spec[key].items() if k != "master"}
        for position, key in enumerate(order, start=first_index)
    }
