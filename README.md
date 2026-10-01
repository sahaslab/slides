# slides

A command-line tool and Python library for working with slide decks. It reads Keynote, PowerPoint and DeckWerk decks into one shared model, converts between them, and dumps any deck to text. It can also build a DeckWerk deck as a native Keynote deck, with its fonts, images, shapes, equations, movies and builds intact.

## Setup

```bash
uv tool install git+https://github.com/sahaslab/slides
```

This puts a `slides` command on your path. Anything that drives Keynote needs macOS with Keynote installed. The first time, macOS asks whether your terminal may control Keynote; if a command fails with `-1743`, allow it under System Settings > Privacy & Security > Automation.

## Usage

A target is a `.key` file, a `.pptx` file, or a DeckWerk folder (any directory with a `deck.json`).

* **dump**: A deck as Markdown, JSON or plain text, e.g. for an agent to read. With no target, it reads the front document in Keynote. `slides dump talk.key -o talk.md`
* **convert**: A deck in another format: `keynote`, `pdf`, `pptx` or `deckwerk`. `slides convert talk/ -f keynote`
* **math**: Turns `$...$` and `$$...$$` LaTeX in a `.key` file into native Keynote equations. `slides math talk.key`
* **theme**: A deck's colours and fonts, as JSON or as a matplotlib, ggplot or CSS theme for figures that match it. `slides theme talk.key -f matplotlib > talk.mplstyle`
* **info**: Slide count, size and assets. `slides info talk.key`
* **patch**: Writes titles, body text, notes, images and tables into the open Keynote deck from a JSON spec keyed by slide number. `slides patch spec.json`
* **scaffold**: Like `patch`, but makes a new slide per entry, optionally in a copy of a template. `slides scaffold spec.json --template blank.key -o talk.key`

Run `slides <command> --help` for the rest of each command's options. No command overwrites an existing file or changes its source; only `patch` and `scaffold` edit a deck that is open in Keynote.

### DeckWerk to Keynote

`slides convert talk/ -f keynote` has Keynote build the deck itself, so the result opens cleanly and edits like any other Keynote deck. Text keeps its fonts, weights, colours, alignment, spacing and inline styling. Images keep their crops and masks, shapes come across as vector art, videos as movies, math as native equations, morphs as Magic Move, and timeline steps as ordinary builds. A table with math in it becomes a grid of text boxes, since Keynote tables cannot hold equations. Interactive web demos come across as their poster image. A 68-slide deck takes about a minute.

Converting a deck *to* DeckWerk, and `dump --via-deckwerk`, use DeckWerk's own importer, so they need a DeckWerk checkout. Point `SLIDES_DECKWERK_ROOT` (or `--deckwerk-root`) at it; it defaults to `~/src/deckwerk`.

## Library

To use it as a library, install it into your environment instead. The `figures` extra adds matplotlib, which `deck_style` needs.

```bash
uv pip install "slides[figures] @ git+https://github.com/sahaslab/slides"
```

```python
from slides import read_deck
from slides.writers import markdown

deck = read_deck("talk.key")
print(markdown.render(deck, notes_only=True))
```

```python
import matplotlib.pyplot as plt
from slides import read_deck
from slides.theme import extract
from slides.emit.matplotlib import deck_style

with deck_style(extract(read_deck("talk/"))):
    fig, ax = plt.subplots()
```

## Development

```bash
conda create -n slides python=3.12
conda activate slides
pip install uv
cd path/to/slides
uv pip install -e . pytest
pytest
```

The tests run against the small decks in `tests/fixtures` and never drive Keynote. A few more need real decks; point `SLIDES_SAMPLE_DECKS` at a folder of them to run those too.
