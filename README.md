# slides

`slides` is a command-line tool and Python library for working with decks: it
reads Keynote, PowerPoint and DeckWerk files into one shared model, converts
between those formats, and turns any deck into text an agent (or a person) can
read. It carries no house style, palette or content of its own — every colour,
font and word it reports comes from the deck you hand it.

## Install

```
uv tool install --editable .
```

This builds an isolated environment for the `slides` command whose source
edits take effect immediately, no reinstall needed. Drop `--editable` for a
frozen install; the same command also works against a git URL.

## Commands

Every `TARGET` is auto-detected from its path: a `.key` file, a `.pptx` file,
or a DeckWerk folder (a directory containing `deck.json`). `slides dump` alone
also accepts no target, meaning the front document in live Keynote — it is the
only command that touches the running application without being told to.

| Command | What it does | Example |
| --- | --- | --- |
| `slides dump [TARGET]` | Deck to text: Markdown, JSON, or plain text. | `slides dump talk.key -o talk.md` |
| `slides convert TARGET -f FORMAT` | Deck to another deck format: `deckwerk`, `pptx`, `keynote`, `pdf`. | `slides convert talk.key -f deckwerk -o talk/` |
| `slides scaffold SPEC` | Build a new deck in live Keynote from a per-slide JSON spec. | `slides scaffold spec.json --template blank.key -o talk.key` |
| `slides patch SPEC` | Apply a per-slide JSON spec to the open Keynote deck. | `slides patch spec.json` |
| `slides math TARGET` | `$...$` / `$$...$$` LaTeX in a `.key` file to native Keynote equations. | `slides math talk.key` |
| `slides theme TARGET` | The deck's palette and fonts, for a plot to match it. | `slides theme talk.key -f matplotlib > deck.mplstyle` |
| `slides info TARGET` | Slide count, dimensions, asset inventory, plus coverage or validation. | `slides info talk.key` |

### `dump` in more detail

`-f md|json|txt` picks the output form (default `md`); `-o FILE` writes one
file, `--out-dir DIR` writes one file per input for batch runs, and
`--clipboard` copies instead of printing. `--notes-only` restricts the output
to presenter notes, numbered by slide.

A deck's interactive `web` pages, `video` links and fallback `html` tables all
survive the dump: pages are copied beside the output (into `<output>_assets/`,
or `--assets-dir`) and linked from the Markdown; video is linked to its
existing location, and copied too with `--copy-media`; `html` that is really a
table renders as a pipe table. Dumping to stdout copies nothing — `dump` says
so on stderr and links point back into the source deck instead.

### `patch` and `scaffold` in more detail

One engine, two entry points. A patch spec is JSON keyed by slide number
(as a string), each entry any of `title`, `body`, `notes`, `images`, `tables`:

```json
{"1": {"title": "New title", "notes": "Say hello."}}
```

`patch` writes this to the open Keynote document. `scaffold` does the same
after creating one new slide per spec entry — from a named master with
`"master": "..."` in that entry, sorted by key — either in the front document
or, with `--template`, in a copy of a template `.key` (or DeckWerk-style
folder) opened for the purpose; `-o` names that copy.

`patch` also accepts a `slides dump -f json` file directly, applying only its
`title` and `notes` (and saying so on stderr): a dump's `body` is every text
box on the slide merged into one field, and its `images` are paths already on
the slide, so writing either back through `patch` would duplicate or
scramble content. Use an explicit patch spec for those.

### `theme` in more detail

`-f json|matplotlib|ggplot|css` (default `json`); `--accents N` sets how
many accent colours to extract (default 6, padded out by hue rotation if the
deck does not have that many).

- `matplotlib` prints a style sheet for `plt.style.use()`.
- `css` defines `--deck-background`, `--deck-foreground`, `--deck-muted`,
  `--deck-grid`, `--deck-accent-1` through `--deck-accent-N`, and
  `--deck-font-<role>` for each font role the deck has (typically `title` and
  `body`). These names are a stable contract a web page can rely on.
- `ggplot` prints R source defining `theme_deck()`, `scale_colour_deck()` /
  `scale_fill_deck()` (and the `scale_color_deck()` alias), sourced from an
  analysis script. A scale that needs more colours than `--accents` gave it
  stops with a message naming the `--accents` value to regenerate with.

### Safety

`convert`, `math` and `scaffold` never overwrite an existing output path and
never modify their source; `scaffold` works on a copy of its template, not the
template itself. `patch` and `scaffold` are the only commands that drive the
Keynote application and change the document they target — no other command
touches a deck that happens to be open without being told to (`dump` with no
target is the exception, and it only reads the front document).

## Library

```python
from slides import read_deck
from slides.writers import markdown

deck = read_deck("talk.key")
print(markdown.render(deck, notes_only=True))
```

```python
from slides import read_deck
from slides.theme import extract
from slides.emit.matplotlib import deck_style

theme = extract(read_deck("talk/"))
theme.background, theme.foreground, theme.accents

with deck_style(theme):
    fig, ax = plt.subplots()
```

`read_deck` dispatches on the target the same way the CLI does, so the two
always agree.

## Environment variables

- `SLIDES_DECKWERK_ROOT` — path to a DeckWerk checkout, used by
  `convert -f deckwerk`, by `info` on a `.key` target for its coverage report,
  and by `info` on a DeckWerk folder for its validation. Overridable per call
  with `--deckwerk-root`; falls back to `~/src/deckwerk`.
- `SLIDES_KEYNOTE_APP` — the application name JXA drives: `patch`, `scaffold`,
  `dump` with no target, and `convert`'s `keynote`/`pdf` export routes.
  Defaults to `"Keynote"`.

## What this does not do

- Live JXA LaTeX conversion (Find → Cut → ⌥⌘E). It steals focus and is slow;
  `slides math` covers the cases that matter headlessly.
- Write `.key` files directly with keynote-parser. Brittle across Keynote
  versions — the pptx round trip covers a DeckWerk or PowerPoint deck going
  to Keynote instead.
- Ship any built-in palette, theme, template or house style. Every colour and
  font `slides theme` reports comes from the deck you hand it.
- Render plots. `slides theme` hands over a palette; the caller draws.
- Anything that needs to know what a deck is about.

## Tests

`pytest` runs the suite against the small fixtures in `tests/fixtures` in a few
seconds. A handful of regression tests need real decks, because only a real
file exercises the archive shapes that appear in the wild; point
`SLIDES_SAMPLE_DECKS` at a folder of them to run those too. They skip
otherwise.
