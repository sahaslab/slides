import shutil
import pathlib
from slides.readers import read
from slides.keynote import build, finish, math
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


def a_slide(tmp_path: pathlib.Path) -> tuple:
    # blank.key's one slide, holding a single stand-in picture as drawable 999.
    unpacked = tmp_path / "deck"
    math.unpack_deck(math.zipped(build.BLANK, tmp_path), unpacked)
    finisher = finish.Finisher(unpacked)
    data = math.load(next(iter(finisher._slide_files().values())))
    slide = next(a for a in finish.chunk(data) if finish.kind(a) == "KN.SlideArchive")
    slide["objects"][0]["drawablesZOrder"] = [{"identifier": "999"}]
    finish.chunk(data).append({"header": {"identifier": "999"}, "objects": [{"_pbtype": "TSD.ImageArchive"}]})
    entry = next(c for c in finisher.package["components"] if c["identifier"] == slide["header"]["identifier"])
    return finisher, data, slide, entry


STEP = {"target": "a", "effect": "appear", "trigger": "click", "delay": 0.0}


def test_each_build_chunk_names_its_builds_uuid(tmp_path):
    # Keynote finds a chunk's build by the build's object UUID; a mismatch
    # leaves the build playing but impossible to edit or delete.
    finisher, data, slide, entry = a_slide(tmp_path)
    finisher._builds(data, slide, entry, {"images": [{"id": "a"}], "texts": [], "tables": [], "builds": [STEP, STEP]})
    uuids = {e["identifier"]: e["uuid"] for e in entry["objectUuidMapEntries"]}
    chunks = [a for a in finish.chunk(data) if finish.kind(a) == "KN.BuildChunkArchive"]
    assert len(chunks) == 2
    for made in chunks:
        assert made["header"]["identifier"] not in uuids
        assert made["objects"][0]["buildId"] == uuids[made["objects"][0]["build"]["identifier"]]


def test_keynotes_own_movie_build_stays_and_autoplays(tmp_path):
    # Keynote gives each movie it makes a Start Movie build on click.
    finisher, data, slide, entry = a_slide(tmp_path)
    own, own_chunk = finisher._build_pair("999", STEP, "click", False)
    finish.chunk(data).extend([own, own_chunk])
    slide["objects"][0]["builds"] = [{"identifier": own["header"]["identifier"]}]
    slide["objects"][0]["buildChunks"] = [{"identifier": own_chunk["header"]["identifier"]}]
    clicks = finisher._builds(data, slide, entry, {"images": [{"id": "a", "autoplay": True}], "texts": [], "tables": [], "builds": [STEP]})
    listed = [b["identifier"] for b in slide["objects"][0]["builds"]]
    assert listed[0] == own["header"]["identifier"] and len(listed) == 2
    assert own_chunk["objects"][0]["automatic"] is True
    assert clicks == 1
