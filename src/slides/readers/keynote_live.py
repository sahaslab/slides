from slides.keynote import jxa
from slides.model import Deck, Slide, Table, TextItem

SCRIPT = """
var app = Application(%s);
if (app.documents.length === 0) { throw new Error("No presentation is open."); }
var doc = app.documents[0];
// One Apple Event per property across every slide: per-item calls cost a
// round trip each and made a 35-slide deck take eight seconds.
var slides = doc.slides;
var titles = slides.defaultTitleItem.objectText();
var items = slides.textItems.objectText();
var notes = slides.presenterNotes();
var tables = slides.tables.rows.cells.value();
var out = {name: doc.name(), width: doc.width(), height: doc.height(), slides: []};
for (var i = 0; i < titles.length; i++) {
  out.slides.push({title: titles[i], items: items[i], tables: tables[i], notes: notes[i]});
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
