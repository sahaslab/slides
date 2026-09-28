import shutil
import pathlib
import argparse
import pptx
import pytest
import PIL.Image
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE
from slides import color, theme
from slides.commands import convert
from slides.model import ColorUse, Deck, Embed, Image, Slide, Table, TextItem
from slides.readers import deckwerk
from slides.readers.pptx import read
from slides.writers import markdown
from slides.writers.pptx import write

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"
SVG = (
    "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"40\" height=\"20\">"
    "<rect width=\"40\" height=\"20\" fill=\"#c83c3c\"/></svg>"
)


def a_deck() -> Deck:
    return Deck(
        title="Talk",
        width=1920.0,
        height=1080.0,
        slides=[
            Slide(
                number=1,
                title="Opening",
                items=[
                    TextItem(text="Opening", role="title", x=120, y=84, w=1680, h=67),
                    TextItem(text="A point", x=120, y=300, w=800, h=60),
                ],
                notes="Say hello.",
                background="#0d1e1c",
            ),
            Slide(
                number=2,
                title="Numbers",
                items=[TextItem(text="Numbers", role="title")],
                tables=[Table(rows=[["Model", "MSE"], ["Linear", "3.2"]])],
            ),
        ],
    )


def test_round_trips_through_the_reader(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "out.pptx"
    write(a_deck(), out)
    back = read(out)
    assert len(back.slides) == 2
    assert back.slides[0].title == "Opening"
    assert "A point" in [i.text for i in back.slides[0].body_items()]
    assert back.slides[0].notes == "Say hello."
    assert back.slides[1].tables[0].rows == [["Model", "MSE"], ["Linear", "3.2"]]


def test_canvas_size_is_preserved(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "out.pptx"
    write(a_deck(), out)
    deck = pptx.Presentation(str(out))
    assert round(deck.slide_width / 12700) == 1920
    assert round(deck.slide_height / 12700) == 1080


def test_slides_without_geometry_still_lay_out(tmp_path: pathlib.Path) -> None:
    deck = Deck(
        title="Bare",
        slides=[Slide(number=1, title="T", items=[TextItem(text="Body with no box")])],
    )
    out = tmp_path / "bare.pptx"
    write(deck, out)
    back = read(out)
    assert back.slides[0].title == "T"
    assert [i.text for i in back.slides[0].body_items()] == ["Body with no box"]


def test_a_slide_without_a_title_keeps_no_empty_title_placeholder(
    tmp_path: pathlib.Path
) -> None:
    deck = Deck(title="Untitled", slides=[Slide(number=1)])
    out = tmp_path / "untitled.pptx"
    write(deck, out)
    assert list(pptx.Presentation(str(out)).slides[0].shapes) == []


def test_body_text_takes_the_theme_foreground_on_a_dark_background(
    tmp_path: pathlib.Path
) -> None:
    deck = a_deck()
    palette = theme.extract(deck)
    assert color.luminance(palette.background) < 0.1
    out = tmp_path / "out.pptx"
    write(deck, out)
    runs = _runs(_shape_with_text(out, 0, "A point"))
    assert runs
    assert all(str(run.font.color.rgb) == palette.foreground.lstrip("#").upper() for run in runs)


def test_every_run_clears_text_contrast_against_its_own_slide(tmp_path: pathlib.Path) -> None:
    deck = Deck(
        title="Mixed",
        colors=[ColorUse(hex="#111111", weight=10.0, kind="text")],
        slides=[
            _two_item_slide(1, "#ffffff"),
            _two_item_slide(2, "#ffffff"),
            _two_item_slide(3, "#0d1e1c"),
        ],
    )
    deck.slides[2].tables = [Table(rows=[["Model", "MSE"]])]
    assert theme.extract(deck).background == "#ffffff"
    out = tmp_path / "mixed.pptx"
    write(deck, out)
    checked = 0
    for slide in pptx.Presentation(str(out)).slides:
        ground = "#%s" % (slide.background.fill.fore_color.rgb,)
        frames = [s.text_frame for s in slide.shapes if s.has_text_frame]
        for shape in slide.shapes:
            if shape.has_table:
                frames += [cell.text_frame for row in shape.table.rows for cell in row.cells]
        for frame in frames:
            for paragraph in frame.paragraphs:
                for run in paragraph.runs:
                    assert color.contrast("#%s" % (run.font.color.rgb,), ground) >= 4.5
                    checked += 1
    assert checked == 8


def test_title_takes_the_first_accent_only_when_it_clears_text_contrast(
    tmp_path: pathlib.Path
) -> None:
    clear = _titled_deck("#0d1e1c", "#eef3f0", "#a5d75f")
    faint = _titled_deck("#ffffff", "#111111", "#ffcc00")
    clear_theme = theme.extract(clear)
    faint_theme = theme.extract(faint)
    assert color.contrast(clear_theme.accents[0], clear_theme.background) >= 4.5
    assert color.contrast(faint_theme.accents[0], faint_theme.background) < 4.5
    write(clear, tmp_path / "clear.pptx")
    write(faint, tmp_path / "faint.pptx")
    clear_run = _runs(_shape_with_text(tmp_path / "clear.pptx", 0, "Heading"))[0]
    faint_run = _runs(_shape_with_text(tmp_path / "faint.pptx", 0, "Heading"))[0]
    assert str(clear_run.font.color.rgb) == clear_theme.accents[0].lstrip("#").upper()
    assert str(faint_run.font.color.rgb) == faint_theme.foreground.lstrip("#").upper()


def test_font_size_scales_with_the_canvas(tmp_path: pathlib.Path) -> None:
    full = a_deck()
    half = a_deck()
    half.width = 960.0
    half.height = 540.0
    write(full, tmp_path / "full.pptx")
    write(half, tmp_path / "half.pptx")
    assert _runs(_shape_with_text(tmp_path / "full.pptx", 0, "Opening"))[0].font.size.pt == 65
    assert _runs(_shape_with_text(tmp_path / "full.pptx", 0, "A point"))[0].font.size.pt == 39
    assert _runs(_shape_with_text(tmp_path / "half.pptx", 0, "Opening"))[0].font.size.pt == 32
    assert _runs(_shape_with_text(tmp_path / "half.pptx", 0, "A point"))[0].font.size.pt == 19
    shapes = pptx.Presentation(str(tmp_path / "full.pptx")).slides[1].shapes
    table = [s for s in shapes if s.has_table][0]
    cell_run = table.table.cell(0, 0).text_frame.paragraphs[0].runs[0]
    assert cell_run.font.size.pt == 27


def test_fonts_are_the_first_family_of_the_theme_stacks(tmp_path: pathlib.Path) -> None:
    deck = a_deck()
    deck.fonts = {
        "title": "Charter, \"Iowan Old Style\", Georgia, serif",
        "body": "\"Avenir Next\", Avenir, system-ui, sans-serif",
    }
    out = tmp_path / "out.pptx"
    write(deck, out)
    assert _runs(_shape_with_text(out, 0, "Opening"))[0].font.name == "Charter"
    assert _runs(_shape_with_text(out, 0, "A point"))[0].font.name == "Avenir Next"


def test_an_image_in_the_deckwerk_fixture_comes_back_as_an_image(
    tmp_path: pathlib.Path
) -> None:
    folder = _fixture_copy(tmp_path)
    PIL.Image.new("RGB", (20, 20), "#c83c3c").save(folder / "assets" / "plot.png")
    out = tmp_path / "out.pptx"
    write(deckwerk.read(folder), out)
    images = read(out).slides[0].images
    assert len(images) == 1
    image = images[0]
    assert image.w == pytest.approx(400.0)
    assert image.h == pytest.approx(400.0)
    assert image.x == pytest.approx(960.0 + 200.0)
    assert image.y == pytest.approx(300.0)


def test_an_image_that_does_not_resolve_is_skipped_with_one_stderr_line(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture
) -> None:
    out = tmp_path / "out.pptx"
    write(deckwerk.read(FIXTURE), out)
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1
    assert "assets/plot.png" in err
    back = read(out)
    assert len(back.slides) == 3
    assert back.slides[0].images == []


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="needs rsvg-convert")
def test_svg_images_are_rasterised(tmp_path: pathlib.Path) -> None:
    (tmp_path / "figure.svg").write_text(SVG)
    _assert_one_image_fills_its_box(tmp_path, "figure.svg")


def test_without_rsvg_convert_svg_images_are_skipped_with_one_stderr_line(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    (tmp_path / "one.svg").write_text(SVG)
    (tmp_path / "two.svg").write_text(SVG)
    PIL.Image.new("RGB", (40, 20), "#c83c3c").save(tmp_path / "photo.png")
    deck = Deck(
        title="Figures",
        source=str(tmp_path),
        slides=[
            Slide(number=1, images=[Image(path="one.svg"), Image(path="photo.png")]),
            Slide(number=2, images=[Image(path="two.svg")]),
        ],
    )
    out = tmp_path / "out.pptx"
    write(deck, out)
    assert capsys.readouterr().err == (
        "2 SVG images skipped: install librsvg (brew install librsvg) for rsvg-convert\n"
    )
    back = read(out)
    assert [len(slide.images) for slide in back.slides] == [1, 0]


def test_without_rsvg_convert_an_svg_poster_falls_back_to_a_linked_label(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    (tmp_path / "poster.svg").write_text(SVG)
    (tmp_path / "figure.svg").write_text(SVG)
    embed = Embed(kind="web", src="demo.html", title="Demo", poster="poster.svg", x=100, y=100, w=800, h=400)
    deck = Deck(
        title="Demos",
        source=str(tmp_path),
        slides=[Slide(number=1, images=[Image(path="figure.svg")], embeds=[embed])],
    )
    out = tmp_path / "out.pptx"
    write(deck, out)
    assert capsys.readouterr().err == (
        "2 SVG images skipped: install librsvg (brew install librsvg) for rsvg-convert\n"
    )
    label = _shape_with_text(out, 0, "Interactive: Demo")
    assert label.click_action.hyperlink.address == (tmp_path / "demo.html").resolve().as_uri()
    assert read(out).slides[0].images == []


def test_webp_images_are_re_encoded(tmp_path: pathlib.Path) -> None:
    PIL.Image.new("RGB", (40, 20), "#c83c3c").save(tmp_path / "photo.webp")
    _assert_one_image_fills_its_box(tmp_path, "photo.webp")


def test_every_text_frame_shrinks_on_overflow(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "out.pptx"
    write(deckwerk.read(FIXTURE), out)
    frames = []
    for slide in pptx.Presentation(str(out)).slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                frames.append(shape.text_frame)
            if shape.has_table:
                frames += [cell.text_frame for row in shape.table.rows for cell in row.cells]
    assert len(frames) > 5
    assert all(frame.auto_size == MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE for frame in frames)


def test_the_embed_label_is_shared_with_the_markdown_writer() -> None:
    embed = Embed(kind="video", src="assets/clip.mp4")
    assert embed.label() == "Video: clip.mp4"
    deck = Deck(title="T", slides=[Slide(number=1, embeds=[embed])])
    assert "[Video: clip.mp4](assets/clip.mp4)" in markdown.render(deck)


def test_a_web_embed_links_to_its_src(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "out.pptx"
    write(deckwerk.read(FIXTURE), out)
    shape = _shape_with_text(out, 2, "Interactive: A demo")
    address = shape.click_action.hyperlink.address
    assert address.startswith("file:///")
    assert address.endswith("assets/web/demo.html")
    video = _shape_with_text(out, 2, "Video: clip.mp4")
    assert video.click_action.hyperlink.address.endswith("assets/clip.mp4")


def test_an_embed_with_a_poster_becomes_a_linked_picture(tmp_path: pathlib.Path) -> None:
    folder = _fixture_copy(tmp_path)
    PIL.Image.new("RGB", (40, 20), "#335577").save(folder / "assets" / "web" / "demo.poster.png")
    out = tmp_path / "out.pptx"
    write(deckwerk.read(folder), out)
    slide = pptx.Presentation(str(out)).slides[2]
    pictures = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pictures) == 1
    assert pictures[0].click_action.hyperlink.address.endswith("assets/web/demo.html")
    assert not any(s.has_text_frame and s.text_frame.text.startswith("Interactive") for s in slide.shapes)


def test_convert_writes_a_pptx(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture
) -> None:
    out = tmp_path / "out.pptx"
    assert convert.run(_convert_args(FIXTURE, out)) == 0
    assert capsys.readouterr().out.strip() == str(out)
    assert len(read(out).slides) == 3


def test_convert_refuses_to_overwrite_an_existing_pptx(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture
) -> None:
    out = tmp_path / "out.pptx"
    out.write_bytes(b"keep me")
    assert convert.run(_convert_args(FIXTURE, out)) != 0
    assert capsys.readouterr().err == "%s already exists; pass -o with a new path\n" % (out,)
    assert out.read_bytes() == b"keep me"


def _titled_deck(
    background: str,
    text: str,
    accent: str
) -> Deck:
    return Deck(
        title="Accent",
        colors=[
            ColorUse(hex=text, weight=10.0, kind="text"),
            ColorUse(hex=accent, weight=5.0, kind="text"),
        ],
        slides=[
            Slide(
                number=1,
                title="Heading",
                items=[TextItem(text="Heading", role="title", x=120, y=84, w=1680, h=67)],
                background=background,
            ),
        ],
    )


def _assert_one_image_fills_its_box(
    folder: pathlib.Path,
    name: str
) -> None:
    deck = Deck(
        title="Figures",
        source=str(folder),
        slides=[Slide(number=1, images=[Image(path=name, x=100, y=100, w=800, h=400)])],
    )
    out = folder / "out.pptx"
    write(deck, out)
    images = read(out).slides[0].images
    assert len(images) == 1
    assert images[0].w == pytest.approx(800.0)
    assert images[0].h == pytest.approx(400.0)


def _two_item_slide(
    number: int,
    background: str
) -> Slide:
    return Slide(
        number=number,
        title="Title %d" % (number,),
        items=[
            TextItem(text="Title %d" % (number,), role="title", x=120, y=84, w=1680, h=67),
            TextItem(text="Body %d" % (number,), x=120, y=300, w=800, h=60),
        ],
        background=background,
    )


def _fixture_copy(tmp_path: pathlib.Path) -> pathlib.Path:
    folder = tmp_path / "deck"
    shutil.copytree(FIXTURE, folder)
    return folder


def _convert_args(
    target: pathlib.Path,
    output: pathlib.Path
) -> argparse.Namespace:
    return argparse.Namespace(target=str(target), format="pptx", output=str(output), deckwerk_root=None)


def _shape_with_text(
    path: pathlib.Path,
    index: int,
    text: str
) -> "pptx.shapes.base.BaseShape":
    slide = pptx.Presentation(str(path)).slides[index]
    return [s for s in slide.shapes if s.has_text_frame and s.text_frame.text == text][0]


def _runs(shape: "pptx.shapes.base.BaseShape") -> list:
    return [run for paragraph in shape.text_frame.paragraphs for run in paragraph.runs]
