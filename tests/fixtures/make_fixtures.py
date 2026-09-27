import pathlib
import pptx
from pptx.util import Inches


def main():
    here = pathlib.Path(__file__).parent
    build_pptx(here / "mini.pptx")
    print("wrote %s" % (here / "mini.pptx",))


def build_pptx(path: pathlib.Path) -> None:
    deck = pptx.Presentation()
    layout = deck.slide_layouts[1]
    first = deck.slides.add_slide(layout)
    first.shapes.title.text = "Opening"
    first.placeholders[1].text = "First point\nSecond point"
    first.notes_slide.notes_text_frame.text = "Say hello."
    second = deck.slides.add_slide(deck.slide_layouts[5])
    second.shapes.title.text = "Numbers"
    table = second.shapes.add_table(
        2,
        2,
        Inches(1),
        Inches(2),
        Inches(4),
        Inches(1),
    ).table
    table.cell(0, 0).text = "Model"
    table.cell(0, 1).text = "MSE"
    table.cell(1, 0).text = "Linear"
    table.cell(1, 1).text = "3.2"
    deck.save(path)


if __name__ == "__main__":
    main()
