import shutil
import pathlib
from slides.readers import read
from slides.keynote import build, finish
from slides.model import Shape

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def a_spec(tmp_path: pathlib.Path) -> dict:
    return build.Spec(read(FIXTURE), tmp_path).build()


def test_text_takes_the_elements_own_look(tmp_path):
    spec = a_spec(tmp_path)
    title = spec["slides"][0]["texts"][0]
    assert title["text"] == "Opening"
    assert title["style"]["size"] > 0
    assert len(title["style"]["color"]) == 3
    assert title["align"] in ("left", "center", "right", "justify")


def test_every_made_object_carries_its_deckwerk_id(tmp_path):
    spec = a_spec(tmp_path)
    for slide in spec["slides"]:
        for made in slide["images"] + slide["texts"] + slide["tables"]:
            assert "id" in made


def test_a_table_with_math_becomes_text(tmp_path):
    deck = read(FIXTURE)
    deck.slides[1].tables[0].rows = [["Model", "Loss"], ["Linear", "$w^2$"]]
    spec = build.Spec(deck, tmp_path).build()
    assert spec["slides"][1]["tables"] == []
    assert "$w^2$" in [t["text"] for t in spec["slides"][1]["texts"]]


def test_a_rotated_arrow_fits_its_canvas():
    svg, box = build._shape_svg(Shape(kind="arrow", x=10.0, y=20.0, w=300.0, h=6.0, rot=127.0, stroke="#a5d75f", stroke_width=6.0, arrow_end=True))
    assert "<polygon" in svg and "rotate(127.0)" in svg
    x, y, w, h = box
    assert w == h and w > 300.0
    assert abs((x + w / 2.0) - 160.0) < 1e-6 and abs((y + h / 2.0) - 23.0) < 1e-6


def test_finish_paints_backgrounds_into_the_saved_deck(tmp_path):
    deck = tmp_path / "deck.key"
    shutil.copyfile(build.BLANK, deck)
    finish.finish(deck, [{"background": "#0d1e1c", "texts": [], "images": [], "tables": [], "builds": []}])
    assert read(deck).slides[0].background == "#0d1e1c"
