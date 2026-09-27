import pathlib
from slides.model import Deck, Image, Slide, Table, TextItem

EMU_PER_POINT = 12700


def read(path: str | pathlib.Path) -> Deck:
    import pptx
    root = pathlib.Path(path)
    presentation = pptx.Presentation(str(root))
    deck = Deck(
        title=root.stem,
        width=presentation.slide_width / EMU_PER_POINT,
        height=presentation.slide_height / EMU_PER_POINT,
        source=str(root),
        kind="pptx",
    )
    for number, raw in enumerate(presentation.slides, start=1):
        deck.slides.append(_slide(number, raw))
    return deck


def _slide(number: int, raw: "pptx.slide.Slide") -> Slide:
    slide = Slide(number=number)
    title_shape = raw.shapes.title
    if title_shape is not None and title_shape.has_text_frame:
        slide.title = title_shape.text_frame.text.strip() or None
    for shape in raw.shapes:
        if shape.has_text_frame:
            text = shape.text_frame.text.strip()
            if text:
                role = "title" if text == slide.title else "body"
                slide.items.append(TextItem(
                    text=text,
                    role=role,
                    x=_points(shape.left),
                    y=_points(shape.top),
                    w=_points(shape.width),
                    h=_points(shape.height),
                ))
        if shape.has_table:
            slide.tables.append(Table(rows=[
                [cell.text.strip() for cell in row.cells]
                for row in shape.table.rows
            ]))
        if shape.shape_type == 13:
            slide.images.append(Image(
                path=getattr(shape.image, "filename", None),
                x=_points(shape.left),
                y=_points(shape.top),
                w=_points(shape.width),
                h=_points(shape.height),
            ))
    if raw.has_notes_slide:
        slide.notes = raw.notes_slide.notes_text_frame.text.strip()
    return slide


def _points(value: int | None) -> float | None:
    if value is None:
        return None
    return value / EMU_PER_POINT
