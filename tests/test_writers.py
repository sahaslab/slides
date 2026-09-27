import json as jsonlib
from slides.model import Deck, Slide, Table, TextItem
from slides.writers import json as json_writer
from slides.writers import markdown, render, text


def a_deck() -> Deck:
    return Deck(
        title="Talk",
        slides=[
            Slide(
                number=1,
                title="Fitting a line",
                items=[
                    TextItem(text="Fitting a line", role="title"),
                    TextItem(text="Minimize squared error\nCheck residuals"),
                ],
                notes="Ask for a show of hands.",
            ),
            Slide(
                number=2,
                title="Results",
                items=[TextItem(text="Results", role="title")],
                tables=[Table(rows=[["Model", "MSE"], ["Linear", "3.2"]])],
            ),
        ],
    )


def test_markdown_shape():
    out = markdown.render(a_deck())
    assert out.startswith("# Talk\n")
    assert "## Slide 1" in out
    assert "### Fitting a line" in out
    assert "- Minimize squared error\n- Check residuals" in out
    assert "> Ask for a show of hands." in out


def test_markdown_tables_get_a_separator_row():
    out = markdown.render(a_deck())
    assert "| Model | MSE |" in out
    assert "| --- | --- |" in out


def test_markdown_does_not_repeat_the_title_as_a_bullet():
    out = markdown.render(a_deck())
    assert "- Fitting a line" not in out


def test_notes_only_drops_everything_else():
    out = markdown.render(a_deck(), notes_only=True)
    assert "Ask for a show of hands." in out
    assert "Minimize squared error" not in out
    assert "Results" not in out


def test_empty_deck_still_renders_a_header():
    out = markdown.render(Deck(title="Nothing"))
    assert out.strip() == "# Nothing"


def test_slide_without_a_title_renders_its_body():
    deck = Deck(title="T", slides=[Slide(number=1, items=[TextItem(text="Only body")])])
    out = markdown.render(deck)
    assert "## Slide 1" in out
    assert "- Only body" in out
    assert "### " not in out


def test_text_writer_has_no_markup():
    out = text.render(a_deck())
    assert "Fitting a line" in out
    assert "#" not in out
    assert "- " not in out


def test_json_writer_round_trips():
    parsed = jsonlib.loads(json_writer.render(a_deck()))
    assert parsed["title"] == "Talk"
    assert parsed["slides"][0]["title"] == "Fitting a line"
    assert parsed["slides"][0]["notes"] == "Ask for a show of hands."
    assert parsed["slides"][1]["tables"][0][0] == ["Model", "MSE"]


def test_render_dispatches_on_format():
    deck = a_deck()
    assert render(deck, "md") == markdown.render(deck)
    assert render(deck, "txt") == text.render(deck)
    assert render(deck, "json") == json_writer.render(deck)
