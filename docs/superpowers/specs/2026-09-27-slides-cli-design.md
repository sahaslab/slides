# `slides` — a CLI and library for deck work

Design, 2026-09-27.

## Purpose

One installed command, and one importable package, for every deck operation on
this machine: converting between Keynote, DeckWerk and PowerPoint, getting any
deck out as text an agent can read, pushing work back toward Keynote, and the
Keynote surgery that otherwise gets rewritten as a one-off script each time.

The tool is general-purpose and long-lived. It carries no house style, no
palette, no writing rules and no knowledge of any particular deck, course or
project. Those belong in whatever is using it — a skill, a deck's own
`scripts/`, a project repo. What lives here is the machinery: read a deck, write
a deck, change a deck.

Success: converting a deck, dumping it to Markdown, and applying a batch of slide
edits are each a single command that works without reading source; and every one
of those operations is callable from Python with the same fidelity.

## Constraints

- Python. Installable with `uv tool install`. No TUI.
- The CLI is a thin layer over the library; the library is the product.
- Fast enough to sit in a loop: no heavy imports on paths that do not need them.
- Never reimplement what DeckWerk already does well.
- Nothing domain-specific. If a feature needs to know what a deck is *about*, it
  does not belong here.

## What already exists

- **DeckWerk's Keynote importer**, `~/src/deckwerk/importers/keynote/import_keynote.py`:
  3,213 lines, headless, keynote-parser based, designed never to fail outright
  (unrecognised drawables become `unsupported` placeholders keeping their
  geometry). Takes `input`, `--out`, `--report`. Writes JSON to stdout and all
  diagnostics to stderr. **Keynote → DeckWerk is a solved problem; this tool
  wraps it and gives it the CLI path `slide-agent` lacks.**
- **`slide-agent`**, the DeckWerk agent CLI: `context`, `inspect`, `apply`,
  `render`, `validate`, `theme`, `web`, `transaction`, and more. No `import`
  command — hence the gap above.
- **`keydump.applescript`**: dumps the front Keynote document to Markdown over
  Apple Events. Its two-phase design — one bulk extraction inside the `tell`
  block, all string work outside it — is a ~4x win and is carried forward.
- **Assorted one-off scripts** accumulated on this machine, from which four
  pieces of reusable machinery are lifted: the keynote-parser
  unpack/edit/repack round-trip, headless LaTeX→equation conversion, the
  JXA batch-apply pattern (write a JSON spec, have JXA walk the open document
  applying it), and deriving a matplotlib style from a deck's theme. Their
  content — the actual slides, text and plots they built — stays behind.

**DeckWerk → Keynote does not exist in any form and is inferred from the ground
up here.**

## Command surface

    slides dump [TARGET]              deck -> text
    slides convert TARGET -f FORMAT   deck -> another deck format
    slides scaffold SPEC              build a new deck in live Keynote
    slides patch SPEC                 apply a per-slide spec to the open deck
    slides math TARGET                LaTeX -> native Keynote equations
    slides info TARGET                what a deck contains, and what converted badly

`TARGET` is auto-detected: a `.key` file, a `.pptx` file, a DeckWerk folder, or —
for `dump` only — omitted, meaning the front Keynote document. `dump` is the
only command that touches the live application without being told to; everything
else takes an explicit path, so no command surprises a deck that happens to be
open.

### `slides dump`

Emits Markdown (default), JSON, or plain text; `--notes-only` restricts output to
presenter notes numbered by slide. `--clipboard` copies instead of printing.
`--out-dir` writes one file per input for batch runs.

Markdown shape follows keydump: `# Deck`, `## Slide N`, `### Title`, body text as
bullets, tables as pipe tables, presenter notes as blockquotes. Body text items
are de-duplicated against the title, since Keynote's text items include the title
placeholder.

JSON is the structured form — per-slide title, text items, tables, notes, and
geometry where the reader can supply it. It is deliberately the same shape
`slides patch` consumes, so a deck can be dumped, edited programmatically, and
applied back.

### `slides convert`

| From | To | How |
| --- | --- | --- |
| `.key` | `deckwerk` | wraps `import_keynote.py`, manages its venv, surfaces `--report` |
| `deckwerk` | `pptx` | writes PowerPoint from the deck model |
| `deckwerk` | `keynote` | via pptx, then Keynote opens and saves `.key` |
| `.key` | `pptx`, `pdf` | via Keynote's own scriptable export |

The DeckWerk → Keynote route is lossy on builds and transitions; the command says
so on stderr rather than pretending otherwise. It is the default reverse path
because it is fully headless up to the final save and works today.

### `slides scaffold` and `slides patch`

One engine, two entry points. `patch` takes a JSON spec keyed by slide number
with `title`, `body`, `notes`, `images` and `tables` fields, writes it to a temp
file, and runs a JXA script that walks the open document applying it.

`scaffold` is `patch` preceded by slide creation: it opens a template `.key`,
creates slides from named masters, then applies the same spec. The output is a
starting point to finish by hand, not a round-trip of a finished DeckWerk deck.
The template is whatever `.key` the caller names; the tool ships none.

### `slides math`

Headless LaTeX conversion: unpack the `.key` with keynote-parser, rewrite
`$...$` and `$$...$$` inside text boxes as native Keynote equation objects,
repack. Presenter notes (`KN.NoteArchive`) are skipped so speaker notes stay
plain text. `--min-slide` protects leading slides; `-o` names the output,
defaulting to a suffixed copy rather than in-place mutation.

The live JXA route (Find → Cut → ⌥⌘E) is **out of scope**: it steals focus, it is
slow, and the headless path covers the cases that matter.

### `slides info`

The cheap way to check whether a conversion landed. What it reports depends on
the target, because the importer's coverage report is printed, not persisted:

- On a `.key`: slide count, canvas dimensions, theme, asset inventory, plus the
  importer's `--report` coverage output (what would convert badly, run without
  writing anything).
- On a DeckWerk folder: the same inventory read from `deck.json`, plus
  `slide-agent validate` for schema errors, broken references, import gaps and
  canvas overflows.
- On a `.pptx`: inventory only.

### `slides.figures`

Library only, no command. Plots that go on a deck should match the deck, and the
deck already states its colours and fonts — in `theme.css` and `deck.json` for
DeckWerk, in the theme for Keynote and PowerPoint. So this module *derives* a
matplotlib style from a deck rather than hardcoding one:

```python
from slides import read_deck
from slides.figures import deck_style

with deck_style(read_deck("talk/")):
    fig, ax = plt.subplots()
    ...
```

It extracts background, text, muted-text, grid and a sequence of accent colours,
maps them onto `rcParams`, and yields. A palette can be overridden or supplied
outright for callers with no deck in hand. The tool ships no palette of its own.

## Architecture

A normalised deck model is the spine: every reader produces it, every writer
consumes it. Four readers and four writers become eight pieces instead of
sixteen, and the model is the thing that makes the package worth importing.

    slides/
      model.py          Deck, Slide, TextItem, Table, Image, Notes  (dataclasses)
      readers/
        keynote_file.py   .key, headless, via keynote-parser
        keynote_live.py   front document, via Apple Events
        pptx.py           via python-pptx
        deckwerk.py       deck.json + notes.md
      writers/
        markdown.py  json.py  text.py  pptx.py
      keynote/
        jxa.py            the Apple Events / JXA bridge
        package.py        keynote-parser unpack -> edit -> repack
        math.py           LaTeX -> equation objects, on top of package.py
      deckwerk/
        importer.py       wraps import_keynote.py, manages its venv
        agent.py          wraps slide-agent
      figures.py          matplotlib style derived from a deck's theme
      cli.py              argparse subcommands, thin

Library use:

```python
from slides import read_deck
from slides.writers import markdown

deck = read_deck("talk.key")
print(markdown.render(deck, notes_only=True))
```

`read_deck` dispatches on the target the same way the CLI does, so the two agree
by construction.

### Reading `.key` headlessly

Two routes, with a deliberate default. Walking the keynote-parser YAML directly
is fast and depends only on keynote-parser. Running DeckWerk's importer into a
temp directory and reading the resulting `deck.json` resolves masters, geometry
and styling far better, but costs seconds per deck.

The YAML walk is the default; `--via-deckwerk` selects the other when the fast
path produces something wrong.

### Efficiency

- Heavy dependencies import lazily inside the reader that needs them.
  `keynote-parser`, `python-pptx` and `matplotlib` never load for a command that
  does not touch them; `slides --help` and `slides dump` on a DeckWerk folder
  stay under 100ms.
- The live-Keynote reader keeps keydump's two-phase discipline: one bulk
  extraction using `every`, then all string work in Python.
- Batch `.key` work goes through a process pool; keynote-parser is CPU-bound.
- No `rich`. Output is plain, coloured only when stdout is a tty.

### Errors

Assertions and real exceptions propagate. The only guarded paths are the ones
where failure is expected and informative: a missing DeckWerk checkout, a missing
importer venv, Keynote not running when a live command needs it, and an
unrecognised target type. Each reports what to do about it.

## Packaging

`pyproject.toml`, hatchling, `slides = "slides.cli:main"`.

    uv tool install --editable ~/Desktop/Git/Other/slides

Isolated environment, no conda pollution, source edits live. Without
`--editable`, a frozen install; the same command works against a git URL.

Core dependencies: `keynote-parser`, `python-pptx`. Extra `[figures]`:
`matplotlib`.

DeckWerk is located by `--deckwerk-root`, then `$SLIDES_DECKWERK_ROOT`, then
`~/src/deckwerk`. On first use of `convert -f deckwerk` a missing importer venv
is offered rather than raised as an import error.

## Testing

pytest, test-first. Readers are tested against real fixture decks — a small
`.key`, a `.pptx`, a DeckWerk folder — not mocks, because every bug worth catching
here lives in real file structure. Fixtures are minimal decks built for the
purpose, committed to the repo, with no content from any real project. Writers
are tested on a hand-built `Deck`. Round-trip tests assert that dump →
patch-spec → apply preserves text.

JXA paths get thin integration tests, skipped when Keynote is absent.

## Out of scope

- The live JXA LaTeX conversion route.
- Writing `.key` files directly with keynote-parser. It is possible, but brittle
  across Keynote versions, and the pptx route covers the need.
- Any built-in palette, theme, template, or house style.
- Anything that needs to know a deck's subject matter.
