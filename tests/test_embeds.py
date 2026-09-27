import pathlib
from slides.model import Deck, Embed, Slide
from slides.readers.deckwerk import read
from slides.writers import json as json_writer
from slides.writers import markdown

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mini_deckwerk"


def test_web_element_becomes_an_embed():
    slide = read(FIXTURE).slides[2]
    web = [e for e in slide.embeds if e.kind == "web"]
    assert len(web) == 1
    assert web[0].src == "assets/web/demo.html"
    assert web[0].title == "A demo"
    assert web[0].poster == "assets/web/demo.poster.png"


def test_video_element_becomes_an_embed():
    slide = read(FIXTURE).slides[2]
    video = [e for e in slide.embeds if e.kind == "video"]
    assert len(video) == 1
    assert video[0].src == "assets/clip.mp4"
    assert video[0].poster is None


def test_html_fallback_table_becomes_a_real_table():
    slide = read(FIXTURE).slides[2]
    assert [row for row in slide.tables[0].rows] == [
        ["Model", "MSE"],
        ["Linear", "3.2"],
    ]


def test_html_fallback_is_not_also_emitted_as_body_text():
    slide = read(FIXTURE).slides[2]
    assert not any("Model" in i.text for i in slide.body_items())


def test_markdown_links_a_web_embed():
    out = markdown.render(read(FIXTURE))
    assert "[Interactive: A demo](assets/web/demo.html)" in out


def test_markdown_links_a_video_embed_by_filename():
    out = markdown.render(read(FIXTURE))
    assert "[Video: clip.mp4](assets/clip.mp4)" in out


def test_markdown_names_an_untitled_web_embed_by_filename():
    deck = Deck(
        title="T",
        slides=[Slide(number=1, embeds=[Embed(kind="web", src="a/b/thing.html")])],
    )
    assert "[Interactive: thing.html](a/b/thing.html)" in markdown.render(deck)


def test_notes_only_drops_embeds():
    out = markdown.render(read(FIXTURE), notes_only=True)
    assert "demo.html" not in out


def test_json_carries_embeds_structurally():
    import json as jsonlib
    parsed = jsonlib.loads(json_writer.render(read(FIXTURE)))
    embeds = parsed["slides"][2]["embeds"]
    assert {"kind": "web", "src": "assets/web/demo.html", "title": "A demo"} in [
        {"kind": e["kind"], "src": e["src"], "title": e["title"]} for e in embeds
    ]


def test_text_writer_names_embeds_without_markup():
    from slides.writers import text
    out = text.render(read(FIXTURE))
    assert "A demo" in out
    assert "[" not in out
