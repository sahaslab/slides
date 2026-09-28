import re
import json
import shutil
import pathlib
import tempfile
import subprocess
from slides import color, theme
from slides.emit import fonts
from slides.keynote import finish, jxa, math
from slides.model import Deck, Image, Run, Shape, Slide, Table, TextItem
from slides.writers import pptx as layout

# Keynote builds the deck itself, so the file it saves is one it can open.
# One osascript run reads a JSON spec and lays out every slide; a headless
# pass then sets what Keynote's scripting cannot (backgrounds, alignment),
# and slides math turns $...$ into native equations.
SCRIPT = """
ObjC.import("Foundation");
function readSpec(path) {
  var s = $.NSString.stringWithContentsOfFileEncodingError(
    path, $.NSUTF8StringEncoding, null);
  return JSON.parse(ObjC.unwrap(s));
}
var spec = readSpec(%s);
var app = Application(%s);
// The deck is a copy of a blank .key at the output path, opened rather than
// made untitled, so Keynote autosaves into it and never into iCloud.
app.includeStandardAdditions = true;
var before = app.documents.id();
var doc = app.open(Path(%s));
// open returns before the deck has finished loading.
for (var w = 0; w < 100; w++) {
  try { if (doc.slides.length > 0) { break; } } catch (e) {}
  delay(0.1);
}
if (before.indexOf(doc.id()) !== -1) { throw new Error("the output deck was already open"); }
doc.width = spec.width;
doc.height = spec.height;
var blank = doc.slideLayouts.byName("Blank");
var where = "opening";
try {
// A face Keynote will not take (some variable-font instances) falls back
// to its family, then to the default, rather than failing the whole deck.
function face(set, s) {
  var names = [s.font, s.family];
  for (var k = 0; k < names.length; k++) {
    if (!names[k]) { continue; }
    try { set(names[k]); return; } catch (e) {}
  }
}
function look(text, s) {
  face(function (name) { text.font = name; }, s);
  if (s.size) { text.size = s.size; }
  if (s.color) { text.color = s.color; }
}
for (var n = 0; n < spec.slides.length; n++) {
  var want = spec.slides[n];
  where = "slide " + (n + 1);
  var slide;
  if (n === 0) {
    slide = doc.slides[0];
    slide.baseLayout = blank;
  } else {
    doc.slides.push(app.Slide({baseLayout: blank}));
    slide = doc.slides[doc.slides.length - 1];
  }
  for (var i = 0; i < want.images.length; i++) {
    var img = want.images[i];
    where = "slide " + (n + 1) + ", image " + (i + 1);
    slide.images.push(app.Image({file: Path(img.path), position: {x: img.x, y: img.y}, width: img.w, height: img.h}));
  }
  // New text items land ahead of the layout's hidden placeholders, so the
  // i-th one made here is textItems[i], not the last in the list.
  for (var i = 0; i < want.texts.length; i++) {
    var t = want.texts[i];
    where = "slide " + (n + 1) + ", text " + (i + 1);
    slide.textItems.push(app.TextItem({objectText: t.text, position: {x: t.x, y: t.y}, width: t.w, height: t.h}));
    var item = slide.textItems[i];
    look(item.objectText, t.style);
    // Keynote fits the box to its text from the top; DeckWerk may centre or
    // bottom-align it in a taller box.
    if (t.valign === "middle" || t.valign === "bottom") {
      var spare = t.h - item.height();
      if (spare > 0) { item.position = {x: t.x, y: t.y + (t.valign === "middle" ? spare / 2 : spare)}; }
    }
  }
  for (var i = 0; i < want.tables.length; i++) {
    var tb = want.tables[i];
    where = "slide " + (n + 1) + ", table " + (i + 1);
    slide.tables.push(app.Table({
      rowCount: tb.rows.length,
      columnCount: tb.columns,
      position: {x: tb.x, y: tb.y},
      width: tb.w,
      height: tb.h
    }));
    var made = slide.tables[slide.tables.length - 1];
    made.headerColumnCount = 0;
    made.footerRowCount = 0;
    var all = made.cellRange;
    face(function (name) { all.fontName = name; }, tb.style);
    all.fontSize = tb.style.size;
    all.textColor = tb.style.color;
    all.backgroundColor = tb.fill;
    for (var r = 0; r < tb.rows.length; r++) {
      for (var c = 0; c < tb.rows[r].length; c++) {
        made.rows[r].cells[c].value = tb.rows[r][c];
      }
    }
  }
  where = "slide " + (n + 1) + ", notes and transition";
  slide.presenterNotes = want.notes;
  if (want.transition && n > 0) {
    doc.slides[n - 1].transitionProperties = {
      transitionEffect: want.transition,
      transitionDuration: want.transitionDuration,
      automaticTransition: false
    };
  }
}
where = "saving";
doc.save();
} catch (error) {
  doc.close({saving: "no"});
  throw new Error(String(error) + " (" + where + ")");
}
var count = doc.slides.length;
doc.close({saving: "no"});
JSON.stringify({slides: count});
"""

FACES_SCRIPT = """
ObjC.import("AppKit");
var families = %s;
var manager = $.NSFontManager.sharedFontManager;
var out = {};
for (var i = 0; i < families.length; i++) {
  var members = manager.availableMembersOfFontFamily(families[i]);
  out[families[i]] = members.isNil() ? null : ObjC.deepUnwrap(members).map(function (m) { return [m[0], m[2], m[3]]; });
}
JSON.stringify(out);
"""

METRICS_SCRIPT = """
ObjC.import("AppKit");
var names = %s;
var out = {};
for (var i = 0; i < names.length; i++) {
  var font = $.NSFont.fontWithNameSize(names[i], 100);
  out[names[i]] = font.isNil() ? null : (font.ascender - font.descender + font.leading) / 100;
}
JSON.stringify(out);
"""
PLAYABLE = (".mp4", ".mov", ".m4v")

# CSS font-weight to AppKit's 0-15 weight scale.
APPKIT_WEIGHT = {100: 2, 200: 3, 300: 4, 400: 5, 500: 6, 600: 8, 700: 9, 800: 10, 900: 11}
ITALIC_TRAIT = 1
BAKE_SCALE = 2.0
BLANK = pathlib.Path(__file__).with_name("blank.key")


def build(
    deck: Deck,
    out: pathlib.Path,
    equations: bool = True
) -> dict:
    with tempfile.TemporaryDirectory(prefix="slides-build-") as staging:
        work = pathlib.Path(staging)
        spec = Spec(deck, work).build()
        path = work / "deck.json"
        path.write_text(json.dumps(spec))
        shutil.copyfile(BLANK, out)
        script = SCRIPT % (
            jxa.literal(str(path)),
            jxa.literal(jxa.app_name()),
            jxa.literal(str(out.resolve())),
        )
        result = jxa.run_json(script)
        finish.finish(out, spec["slides"])
        if equations and any("$" in t["text"] for s in spec["slides"] for t in s["texts"]):
            converted = work / "equations.key"
            result["equations"] = math.convert(out, converted)
            _replace(out, converted)
    return result


class Spec:
    def __init__(
        self,
        deck: Deck,
        work: pathlib.Path
    ) -> None:
        self.deck = deck
        self.work = work
        self.palette = theme.extract(deck)
        self.faces = Faces(_stacks(deck))
        self.baked = 0

    def build(self) -> dict:
        slides = [self._slide(slide) for slide in self.deck.slides]
        _line_spacing([t for s in slides for t in s["texts"]])
        return {
            "width": int(self.deck.width),
            "height": int(self.deck.height),
            "slides": slides,
        }

    def _slide(self, slide: Slide) -> dict:
        ground = slide.background or self.palette.background
        styles = layout._styles(self.deck, self.palette, ground)
        texts = []
        for index, item in enumerate(slide.items):
            role = "title" if item.role == "title" else "body"
            fallback = layout._scaled(layout.TITLE_BOX, self.deck) if role == "title" else layout._body_slot(index, len(slide.items), self.deck)
            texts.append(dict(self._text(item, layout._geometry(item) or fallback, styles[role]), id=item.id))
        # Shapes go down first, under pictures and text, as DeckWerk's cards
        # and rules sit under what they frame.
        images = [dict(self._shape(shape), id=shape.id) for shape in slide.shapes]
        for image in slide.images:
            box = self._image(image)
            if box:
                images.append(dict(box, id=image.id))
        for embed in slide.embeds:
            movie = layout._resolve(self.deck, embed.src) if embed.kind == "video" else None
            if movie is not None and movie.suffix.lower() in PLAYABLE:
                # Keynote makes a movie from a video file handed over as an image.
                x, y, w, h = layout._geometry(embed) or layout._scaled(layout.MEDIA_BOX, self.deck)
                images.append({"path": str(movie.resolve()), "x": x, "y": y, "w": w, "h": h, "id": embed.id})
                continue
            poster = self._image(Image(path=embed.poster, x=embed.x, y=embed.y, w=embed.w, h=embed.h))
            if poster:
                images.append(dict(poster, id=embed.id))
            else:
                box = layout._geometry(embed) or layout._scaled(layout.MEDIA_BOX, self.deck)
                texts.append(dict(self._text(TextItem(text=embed.label()), box, styles["body"]), id=embed.id))
        tables = []
        for offset, table in enumerate(slide.tables):
            if not table.rows:
                continue
            if any("$" in str(cell) for row in table.rows for cell in row):
                # Keynote tables cannot hold equations; a grid of text boxes can.
                texts.extend(dict(cell, id=table.id) for cell in self._grid(table, offset, styles["table"]))
            else:
                tables.append(dict(self._table(table, offset, styles["table"], ground), id=table.id))
        return {
            "background": ground,
            "texts": texts,
            "images": images,
            "tables": tables,
            "notes": slide.notes,
            "transition": slide.transition,
            "transitionDuration": slide.transition_duration,
            "builds": [
                {"target": b.target, "effect": b.effect, "trigger": b.trigger, "delay": b.delay}
                for b in slide.builds
            ],
        }

    def _text(
        self,
        item: TextItem,
        box: tuple[float, float, float, float],
        fallback: "layout.TextStyle"
    ) -> dict:
        x, y, w, h = box
        look = self._look(item.style, fallback)
        return {
            "text": item.text,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "style": look,
            "runs": [self._run(run, item.style) for run in item.runs],
            "align": item.style.get("text-align", "left"),
            "valign": item.style.get("vertical-align", "top"),
            "lineHeight": _line_height(item.style.get("line-height"), look["size"]),
            "spaceAfter": _px(item.style.get("paragraph-spacing")) or 0.0,
        }

    def _look(
        self,
        css: dict[str, str],
        fallback: "layout.TextStyle"
    ) -> dict:
        size = _px(css.get("font-size"))
        colour = _css_colour(css.get("color")) or fallback.color
        stack = css.get("font-family") or fallback.font
        return {
            "font": self.faces.name(stack, css.get("font-weight"), css.get("font-style")),
            "family": self.faces.family(stack),
            "size": size if size else fallback.size,
            "color": _jxa_colour(colour),
        }

    def _run(
        self,
        run: Run,
        base: dict[str, str]
    ) -> dict:
        # Only what the run changes: re-sending the item's own look for every
        # character would cost an Apple Event each for nothing.
        merged = dict(base)
        merged.update(run.style)
        look = {}
        if "color" in run.style and _css_colour(run.style["color"]):
            look["color"] = _css_colour(run.style["color"])
        if "font-size" in run.style and _px(run.style["font-size"]):
            look["size"] = _px(run.style["font-size"])
        if "font-weight" in run.style or "font-style" in run.style or "font-family" in run.style:
            look["font"] = self.faces.name(merged.get("font-family") or "", merged.get("font-weight"), merged.get("font-style"))
        return {"start": run.start, "end": run.end, "style": look}

    def _image(self, image: Image) -> dict | None:
        source = layout._resolve(self.deck, image.path)
        if source is None:
            return None
        x, y, w, h = layout._geometry(image) or layout._scaled(layout.MEDIA_BOX, self.deck)
        if image.mask or image.radius or image.crop or image.fit in ("cover", "fill"):
            baked = self._bake(source, image, w, h)
            if baked is not None:
                return {"path": str(baked), "x": x, "y": y, "w": w, "h": h}
        width, height = _natural_size(source)
        scale = min(w / width, h / height)
        return {
            "path": str(source.resolve()),
            "x": x + (w - width * scale) / 2.0,
            "y": y + (h - height * scale) / 2.0,
            "w": width * scale,
            "h": height * scale,
        }

    def _shape(self, shape: Shape) -> dict:
        # Keynote's scripting can neither fill a shape nor make an ellipse or
        # arrow, but it places an SVG as vector art: draw the shape as one.
        self.baked += 1
        path = self.work / ("shape-%d.svg" % (self.baked,))
        svg, box = _shape_svg(shape)
        path.write_text(svg)
        x, y, w, h = box
        return {"path": str(path), "x": x, "y": y, "w": w, "h": h}

    def _bake(
        self,
        source: pathlib.Path,
        image: Image,
        w: float,
        h: float
    ) -> pathlib.Path | None:
        # Keynote's scripting can neither crop nor mask, so the picture is
        # drawn as DeckWerk shows it, window, crop and mask included.
        import PIL.Image
        import PIL.ImageDraw
        picture = _raster(source, self.work, max(w, h) * BAKE_SCALE * 2)
        if picture is None:
            return None
        pw, ph = picture.size
        if image.crop:
            sx, sy, sw, sh = image.crop
        elif image.fit == "fill":
            sx, sy, sw, sh = 0.0, 0.0, w, h
        else:
            scale = max(w / pw, h / ph) if image.fit == "cover" else min(w / pw, h / ph)
            sw, sh = pw * scale, ph * scale
            sx, sy = (w - sw) / 2.0, (h - sh) / 2.0
        k = BAKE_SCALE
        canvas = PIL.Image.new("RGBA", (int(round(w * k)), int(round(h * k))), (0, 0, 0, 0))
        placed = picture.convert("RGBA").resize((max(1, int(round(sw * k))), max(1, int(round(sh * k)))))
        canvas.paste(placed, (int(round(sx * k)), int(round(sy * k))), placed)
        mask = PIL.Image.new("L", canvas.size, 0)
        draw = PIL.ImageDraw.Draw(mask)
        box = (0, 0, canvas.size[0] - 1, canvas.size[1] - 1)
        if image.mask == "circle":
            draw.ellipse(box, fill=255)
        else:
            draw.rounded_rectangle(box, radius=image.radius * k, fill=255)
        canvas.putalpha(_multiply(canvas.getchannel("A"), mask))
        self.baked += 1
        path = self.work / ("image-%d.png" % (self.baked,))
        canvas.save(path)
        return path

    def _grid(
        self,
        table: Table,
        offset: int,
        fallback: "layout.TextStyle"
    ) -> list[dict]:
        rows = [[str(cell) for cell in row] for row in table.rows]
        columns = max(len(row) for row in rows)
        x = table.x if table.x is not None else self.deck.width * layout.MARGIN
        y = table.y if table.y is not None else self.deck.height * (layout.TABLE_TOP + offset * layout.TABLE_STEP)
        w = table.w if table.w is not None else self.deck.width * layout.TABLE_WIDTH
        h = table.h if table.h is not None else len(rows) * fallback.size * layout.ROW_SCALE
        cell_w, cell_h = w / columns, h / len(rows)
        base = dict(table.style)
        base.setdefault("text-align", "center")
        base["vertical-align"] = "middle"
        cells = []
        for r, row in enumerate(rows):
            style = dict(base, **({"font-weight": "700"} if r == 0 else {}))
            for c, cell in enumerate(row):
                if not cell.strip():
                    continue
                item = TextItem(text=cell, style=style)
                cells.append(self._text(item, (x + c * cell_w, y + r * cell_h, cell_w, cell_h), fallback))
        return cells

    def _table(
        self,
        table: Table,
        offset: int,
        fallback: "layout.TextStyle",
        ground: str
    ) -> dict:
        rows = [[str(cell) for cell in row] for row in table.rows]
        x = table.x if table.x is not None else self.deck.width * layout.MARGIN
        y = table.y if table.y is not None else self.deck.height * (layout.TABLE_TOP + offset * layout.TABLE_STEP)
        w = table.w if table.w is not None else self.deck.width * layout.TABLE_WIDTH
        h = table.h if table.h is not None else len(rows) * fallback.size * layout.ROW_SCALE
        # Keynote will not edit the cells of a table that hangs off the slide.
        w, h = min(w, self.deck.width), min(h, self.deck.height)
        x = max(0.0, min(x, self.deck.width - w))
        y = max(0.0, min(y, self.deck.height - h))
        look = self._look(table.style, fallback)
        look["size"] = min(look["size"], fallback.size)
        return {
            "rows": rows,
            "columns": max(len(row) for row in rows),
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "style": look,
            "fill": _jxa_colour(color.mix(self.palette.foreground, ground, 0.92)),
        }


class Faces:
    # CSS font stacks, weights and styles to the installed face Keynote
    # should use, looked up once per build through AppKit.
    def __init__(self, stacks: list[str]) -> None:
        families = sorted(set(name for stack in stacks for name in fonts.split_stack(stack)[1]))
        self.members: dict[str, list] = {}
        if families:
            script = FACES_SCRIPT % (json.dumps(families),)
            result = subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True, check=True)
            self.members = {k: v for k, v in json.loads(result.stdout).items() if v}

    def family(self, stack: str) -> str | None:
        return next((f for f in fonts.split_stack(stack)[1] if f in self.members), None)

    def name(
        self,
        stack: str,
        weight: str | None,
        style: str | None
    ) -> str:
        wanted = APPKIT_WEIGHT.get(_weight(weight), 5)
        italic = (style or "").strip() == "italic"
        for family in fonts.split_stack(stack)[1]:
            members = self.members.get(family)
            if not members:
                continue
            same = [m for m in members if bool(m[2] & ITALIC_TRAIT) == italic] or members
            return min(same, key=lambda m: (abs(m[1] - wanted), m[0]))[0]
        return "HelveticaNeue"


def _shape_svg(shape: Shape) -> tuple[str, tuple[float, float, float, float]]:
    import math as maths
    w, h = max(shape.w, 1.0), max(shape.h, 1.0)
    pad = shape.stroke_width * 3.0 + 2.0
    fill = shape.fill or "none"
    stroke = shape.stroke or "none"
    width = shape.stroke_width if shape.stroke else 0.0
    if shape.kind == "ellipse":
        body = "<ellipse cx=\"0\" cy=\"0\" rx=\"%s\" ry=\"%s\"/>" % (w / 2.0, h / 2.0)
    elif shape.kind in ("line", "arrow"):
        body = "<line x1=\"%s\" y1=\"0\" x2=\"%s\" y2=\"0\"/>" % (-w / 2.0, w / 2.0)
        head = max(width * 3.0, 8.0)
        tips = ([(w / 2.0, 1.0)] if shape.arrow_end else []) + ([(-w / 2.0, -1.0)] if shape.arrow_start else [])
        for tip, direction in tips:
            back = tip - direction * head
            body += "<polygon points=\"%s,0 %s,%s %s,%s\" fill=\"%s\" stroke=\"none\"/>" % (tip, back, -head / 2.0, back, head / 2.0, stroke)
        fill = "none"
    elif shape.kind == "path" and shape.path:
        sx, sy = (w / shape.path_size[0], h / shape.path_size[1]) if shape.path_size else (1.0, 1.0)
        body = "<path transform=\"translate(%s %s) scale(%s %s)\" d=\"%s\"/>" % (-w / 2.0, -h / 2.0, sx, sy, shape.path)
    else:
        body = "<rect x=\"%s\" y=\"%s\" width=\"%s\" height=\"%s\" rx=\"%s\"/>" % (-w / 2.0, -h / 2.0, w, h, shape.radius)
    if shape.rot:
        side = maths.hypot(w, h) + 2.0 * pad
        canvas = (side, side)
    else:
        canvas = (w + 2.0 * pad, h + 2.0 * pad)
    cx, cy = shape.x + shape.w / 2.0, shape.y + shape.h / 2.0
    svg = (
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"%s\" height=\"%s\" viewBox=\"0 0 %s %s\">"
        "<g transform=\"translate(%s %s) rotate(%s)\" fill=\"%s\" stroke=\"%s\" stroke-width=\"%s\" opacity=\"%s\">%s</g></svg>"
    ) % (canvas[0], canvas[1], canvas[0], canvas[1], canvas[0] / 2.0, canvas[1] / 2.0, shape.rot, fill, stroke, width, shape.opacity, body)
    return svg, (cx - canvas[0] / 2.0, cy - canvas[1] / 2.0, canvas[0], canvas[1])


def _line_height(
    value: str | None,
    size: float
) -> float | None:
    # CSS line-height as a multiple of the font size.
    if not value:
        return None
    value = value.strip()
    if value.endswith("px"):
        return float(value[:-2]) / size
    if value.endswith("%"):
        return float(value[:-1]) / 100.0
    return float(value) if re.fullmatch(r"[\d.]+", value) else None


def _line_spacing(texts: list[dict]) -> None:
    # Keynote spaces lines as a multiple of the face's own natural height, CSS
    # as a multiple of the font size; convert with each face's metrics.
    names = sorted(set(t["style"]["font"] for t in texts if t["lineHeight"]))
    if not names:
        return
    script = METRICS_SCRIPT % (json.dumps(names),)
    result = subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True, check=True)
    natural = json.loads(result.stdout)
    for text in texts:
        ratio = natural.get(text["style"]["font"]) if text["lineHeight"] else None
        text["lineSpacing"] = round(text["lineHeight"] / ratio, 3) if ratio else None


def _stacks(deck: Deck) -> list[str]:
    found = [stack for stack in deck.fonts.values()]
    for slide in deck.slides:
        for item in slide.items:
            found.append(item.style.get("font-family", ""))
        for table in slide.tables:
            found.append(table.style.get("font-family", ""))
    return [stack for stack in found if stack]


def _weight(value: str | None) -> int:
    if not value:
        return 400
    value = value.strip().lower()
    if value == "bold":
        return 700
    if value == "normal":
        return 400
    number = int(float(value)) if re.fullmatch(r"\d+(\.\d+)?", value) else 400
    return min(APPKIT_WEIGHT, key=lambda w: abs(w - number))


def _px(value: str | None) -> float | None:
    found = re.match(r"\s*([\d.]+)px", value or "")
    return float(found.group(1)) if found else None


def _css_colour(value: str | None) -> str | None:
    from slides.readers.deckwerk import _colors_in
    found = _colors_in(value or "")
    return found[0] if found else None


def _multiply(one: "PIL.Image.Image", other: "PIL.Image.Image") -> "PIL.Image.Image":
    import PIL.ImageChops
    return PIL.ImageChops.multiply(one, other)


def _raster(
    source: pathlib.Path,
    work: pathlib.Path,
    width: float
) -> "PIL.Image.Image | None":
    import io
    import PIL.Image
    if not layout._is_svg(source):
        return PIL.Image.open(source)
    if shutil.which(layout.RASTERISER) is None:
        return None
    command = [layout.RASTERISER, "--width", str(int(width)), str(source)]
    return PIL.Image.open(io.BytesIO(subprocess.run(command, capture_output=True, check=True).stdout))


def _natural_size(path: pathlib.Path) -> tuple[float, float]:
    if layout._is_svg(path):
        return _svg_size(path.read_text(encoding="utf-8", errors="replace"))
    import PIL.Image
    with PIL.Image.open(path) as picture:
        return float(picture.size[0]), float(picture.size[1])


def _svg_size(markup: str) -> tuple[float, float]:
    box = re.search(r"viewBox=[\"']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)", markup)
    if box:
        return float(box.group(1)), float(box.group(2))
    width = re.search(r"\swidth=[\"']([\d.]+)", markup)
    height = re.search(r"\sheight=[\"']([\d.]+)", markup)
    return float(width.group(1)), float(height.group(1))


def _jxa_colour(value: str) -> list[int]:
    return [int(round(channel * 65535)) for channel in color.to_rgb(value)]


def _replace(
    target: pathlib.Path,
    replacement: pathlib.Path
) -> None:
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    shutil.move(str(replacement), str(target))
