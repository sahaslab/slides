import io
import sys
import shutil
import pathlib
import subprocess
from dataclasses import dataclass
from slides import color, theme
from slides.emit import fonts
from slides.model import Deck, Embed, Image, Slide, TextItem

EMU_PER_POINT = 12700
TITLE_ONLY_LAYOUT = 5
TITLE_SCALE = 0.06
BODY_SCALE = 0.036
TABLE_SCALE = 0.7
ROW_SCALE = 1.6
MARGIN = 0.06
TITLE_BOX = (MARGIN, 0.06, 1.0 - 2.0 * MARGIN, 0.12)
BODY_TOP = 0.22
BODY_BOTTOM = 0.94
MEDIA_BOX = (0.2, 0.2, 0.6, 0.6)
TABLE_TOP = 0.45
TABLE_STEP = 0.2
TABLE_WIDTH = 0.5
RASTERISER = "rsvg-convert"
RASTER_SCALE = 2.0

Box = tuple[float, float, float, float]


@dataclass
class TextStyle:
    size: int
    color: str
    font: str


def write(
    deck: Deck,
    path: str | pathlib.Path
) -> None:
    import pptx
    presentation = pptx.Presentation()
    presentation.slide_width = _emu(deck.width)
    presentation.slide_height = _emu(deck.height)
    palette = theme.extract(deck)
    styles = _styles(deck, palette)
    rasterise = shutil.which(RASTERISER) is not None
    if not rasterise:
        _warn_svg_skipped(deck)
    layout = presentation.slide_layouts[TITLE_ONLY_LAYOUT]
    for slide in deck.slides:
        target = presentation.slides.add_slide(layout)
        _slide(target, slide, deck, palette.background, styles, rasterise)
    presentation.save(str(path))


def _styles(
    deck: Deck,
    palette: theme.DeckTheme
) -> dict[str, TextStyle]:
    accent = palette.accents[0]
    legible = color.contrast(accent, palette.background) >= theme.TEXT_CONTRAST
    title_font = fonts.primary_family(palette.fonts.get("title", ""), "")
    body_font = fonts.primary_family(palette.fonts.get("body", ""), "")
    body_size = deck.height * BODY_SCALE
    return {
        "title": TextStyle(
            size=round(deck.height * TITLE_SCALE),
            color=accent if legible else palette.foreground,
            font=title_font,
        ),
        "body": TextStyle(size=round(body_size), color=palette.foreground, font=body_font),
        "table": TextStyle(size=round(body_size * TABLE_SCALE), color=palette.foreground, font=body_font),
    }


def _slide(
    target: "pptx.slide.Slide",
    slide: Slide,
    deck: Deck,
    background: str,
    styles: dict[str, TextStyle],
    rasterise: bool
) -> None:
    from pptx.enum.text import PP_ALIGN
    _paint(target, slide.background or background)
    for image in slide.images:
        _image(target, image, slide.number, deck, rasterise)
    for embed in slide.embeds:
        _embed(target, embed, deck, styles["body"])
    heading = next((item for item in slide.items if item.role == "title"), None)
    if heading is None and slide.title:
        heading = TextItem(text=slide.title, role="title")
    _title(target, heading, deck, styles["title"])
    body = [item for item in slide.items if item is not heading]
    for index, item in enumerate(body):
        box = _geometry(item) or _body_slot(index, len(body), deck)
        _text_box(target, item.text, box, styles["body"], PP_ALIGN.LEFT)
    for offset, table in enumerate(slide.tables):
        _table(target, table.rows, offset, deck, styles["table"])
    if slide.notes.strip():
        target.notes_slide.notes_text_frame.text = slide.notes


def _paint(
    target: "pptx.slide.Slide",
    value: str
) -> None:
    fill = target.background.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(value)


def _title(
    target: "pptx.slide.Slide",
    heading: TextItem | None,
    deck: Deck,
    style: TextStyle
) -> None:
    from pptx.enum.text import PP_ALIGN
    placeholder = target.shapes.title
    if heading is None:
        placeholder.element.getparent().remove(placeholder.element)
        return
    x, y, w, h = _geometry(heading) or _scaled(TITLE_BOX, deck)
    placeholder.left = _emu(x)
    placeholder.top = _emu(y)
    placeholder.width = _emu(w)
    placeholder.height = _emu(h)
    _fill(placeholder.text_frame, heading.text, style, PP_ALIGN.LEFT)


def _text_box(
    target: "pptx.slide.Slide",
    text: str,
    box: Box,
    style: TextStyle,
    align: "pptx.enum.text.PP_ALIGN"
) -> "pptx.shapes.autoshape.Shape":
    x, y, w, h = box
    shape = target.shapes.add_textbox(_emu(x), _emu(y), _emu(w), _emu(h))
    shape.text_frame.word_wrap = True
    _fill(shape.text_frame, text, style, align)
    return shape


def _fill(
    frame: "pptx.text.text.TextFrame",
    text: str,
    style: TextStyle,
    align: "pptx.enum.text.PP_ALIGN"
) -> None:
    from pptx.enum.text import MSO_AUTO_SIZE
    from pptx.util import Pt
    # Shrink on overflow: DeckWerk sized its boxes for its own type sizes.
    frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    frame.text = text
    for paragraph in frame.paragraphs:
        paragraph.alignment = align
        for run in paragraph.runs:
            run.font.size = Pt(style.size)
            run.font.color.rgb = _rgb(style.color)
            if style.font:
                run.font.name = style.font


def _table(
    target: "pptx.slide.Slide",
    rows: list[list[str]],
    offset: int,
    deck: Deck,
    style: TextStyle
) -> None:
    from pptx.enum.text import PP_ALIGN
    if not rows:
        return
    columns = max(len(row) for row in rows)
    shape = target.shapes.add_table(
        len(rows),
        columns,
        _emu(deck.width * MARGIN),
        _emu(deck.height * (TABLE_TOP + offset * TABLE_STEP)),
        _emu(deck.width * TABLE_WIDTH),
        _emu(len(rows) * style.size * ROW_SCALE),
    )
    for r, row in enumerate(rows):
        for c in range(columns):
            cell = shape.table.cell(r, c)
            cell.fill.background()
            _fill(cell.text_frame, str(row[c]) if c < len(row) else "", style, PP_ALIGN.LEFT)


def _image(
    target: "pptx.slide.Slide",
    image: Image,
    number: int,
    deck: Deck,
    rasterise: bool
) -> None:
    path = _resolve(deck, image.path)
    if path is None:
        sys.stderr.write("Slide %d: skipped image %s, not a file\n" % (number, image.path))
        return
    if _is_svg(path) and not rasterise:
        return
    _picture(target, path, _geometry(image) or _scaled(MEDIA_BOX, deck))


def _embed(
    target: "pptx.slide.Slide",
    embed: Embed,
    deck: Deck,
    style: TextStyle
) -> None:
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    box = _geometry(embed) or _scaled(MEDIA_BOX, deck)
    poster = _resolve(deck, embed.poster)
    if poster is None:
        shape = _text_box(target, embed.label(), box, style, PP_ALIGN.CENTER)
        shape.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    else:
        shape = _picture(target, poster, box)
    url = (pathlib.Path(deck.source) / embed.src).resolve().as_uri()
    shape.click_action.hyperlink.address = url


def _picture(
    target: "pptx.slide.Slide",
    path: pathlib.Path,
    box: Box
) -> "pptx.shapes.picture.Picture":
    # Fit inside the box at the image's own aspect ratio, centred, as
    # DeckWerk's default `contain` fit draws it.
    x, y, w, h = box
    picture = target.shapes.add_picture(_picture_source(path, w), _emu(x), _emu(y))
    width, height = picture.image.size
    scale = min(w / width, h / height)
    picture.left = _emu(x + (w - width * scale) / 2.0)
    picture.top = _emu(y + (h - height * scale) / 2.0)
    picture.width = _emu(width * scale)
    picture.height = _emu(height * scale)
    return picture


def _picture_source(
    path: pathlib.Path,
    width: float
) -> str | io.BytesIO:
    # python-pptx embeds raster formats only: SVG is rasterised at twice its
    # box width, and WebP is re-encoded as PNG.
    if _is_svg(path):
        command = [RASTERISER, "--width", str(int(width * RASTER_SCALE)), str(path)]
        return io.BytesIO(subprocess.run(command, capture_output=True, check=True).stdout)
    if path.suffix.lower() == ".webp":
        import PIL.Image
        buffer = io.BytesIO()
        PIL.Image.open(path).save(buffer, format="PNG")
        return buffer
    return str(path)


def _warn_svg_skipped(deck: Deck) -> None:
    # Without the rasteriser SVG images are left out, not fatal: most
    # machines have no librsvg.
    paths = [_resolve(deck, image.path) for slide in deck.slides for image in slide.images]
    count = sum(1 for path in paths if path is not None and _is_svg(path))
    if count:
        noun = "image" if count == 1 else "images"
        fix = "install librsvg (brew install librsvg) for %s" % (RASTERISER,)
        sys.stderr.write("%d SVG %s skipped: %s\n" % (count, noun, fix))


def _is_svg(path: pathlib.Path) -> bool:
    return path.suffix.lower() == ".svg"


def _resolve(
    deck: Deck,
    relative: str | None
) -> pathlib.Path | None:
    if not relative:
        return None
    path = pathlib.Path(deck.source) / relative
    return path if path.is_file() else None


def _geometry(thing: TextItem | Image | Embed) -> Box | None:
    # The DeckWerk reader passes html elements' numbers through as found,
    # and deck.json sometimes writes them as strings.
    box = (thing.x, thing.y, thing.w, thing.h)
    if None in box:
        return None
    return tuple(float(value) for value in box)


def _body_slot(
    index: int,
    count: int,
    deck: Deck
) -> Box:
    step = (BODY_BOTTOM - BODY_TOP) * deck.height / count
    top = BODY_TOP * deck.height + index * step
    return deck.width * MARGIN, top, deck.width * (1.0 - 2.0 * MARGIN), step


def _scaled(
    fractions: Box,
    deck: Deck
) -> Box:
    x, y, w, h = fractions
    return x * deck.width, y * deck.height, w * deck.width, h * deck.height


def _rgb(value: str) -> "pptx.dml.color.RGBColor":
    from pptx.dml.color import RGBColor
    return RGBColor.from_string(value.lstrip("#"))


def _emu(points: float) -> "pptx.util.Length":
    from pptx.util import Emu
    return Emu(int(round(points * EMU_PER_POINT)))
