from slides.keynote import jxa
from slides.model import Deck, Slide, Table, TextItem

SCRIPT = """
var app = Application(%s);
if (app.documents.length === 0) { throw new Error("No presentation is open."); }
var doc = app.documents[0];
var out = {
  name: doc.name(),
  width: doc.width(),
  height: doc.height(),
  slides: []
};
var slides = doc.slides;
for (var i = 0; i < slides.length; i++) {
  var s = slides[i];
  var items = [];
  var texts = s.textItems;
  for (var j = 0; j < texts.length; j++) { items.push(texts[j].objectText()); }
  var tables = [];
  var tbs = s.tables;
  for (var t = 0; t < tbs.length; t++) {
    var rows = [];
    var rs = tbs[t].rows;
    for (var r = 0; r < rs.length; r++) {
      var cells = [];
      var cs = rs[r].cells;
      for (var c = 0; c < cs.length; c++) { cells.push(cs[c].value()); }
      rows.push(cells);
    }
    tables.push(rows);
  }
  out.slides.push({
    title: s.defaultTitleItem.objectText(),
    items: items,
    tables: tables,
    notes: s.presenterNotes()
  });
}
JSON.stringify(out);
"""


def read() -> Deck:
    payload = jxa.run_json(SCRIPT % (jxa.literal(jxa.app_name()),))
    deck = Deck(
        title=payload.get("name", "Untitled"),
        width=float(payload.get("width", 1920.0)),
        height=float(payload.get("height", 1080.0)),
        source="",
        kind="live",
    )
    for number, raw in enumerate(payload.get("slides", []), start=1):
        deck.slides.append(_slide(number, raw))
    return deck


def _slide(
    number: int,
    raw: dict,
) -> Slide:
    title = (raw.get("title") or "").strip() or None
    slide = Slide(
        number=number,
        title=title,
        notes=(raw.get("notes") or "").strip(),
    )
    for text in raw.get("items", []):
        cleaned = (text or "").strip()
        if cleaned:
            role = "title" if cleaned == title else "body"
            slide.items.append(TextItem(text=cleaned, role=role))
    for rows in raw.get("tables", []):
        slide.tables.append(Table(rows=[[str(c or "") for c in row] for row in rows]))
    return slide
