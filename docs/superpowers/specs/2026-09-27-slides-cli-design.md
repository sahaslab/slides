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
    slides theme TARGET               the deck's palette, for plots
    slides info TARGET                what a deck contains, and what converted badly

`TARGET` is auto-detected: a `.key` file, a `.pptx` file, a DeckWerk folder, or —
for `dump` only — omitted, meaning the front Keynote document. `dump` is the
only command that touches the live application without being told to; everything
else takes an explicit path, so no command surprises a deck that happens to be
open.

### `slides dump`

Emits Markdown (default), JSON, or plain text; `--notes-only` restricts output to
presenter notes numbered by slide. `--clipboard` copies instead of printing.
`--out-dir` writes one file per input for batch runs. `--assets-dir` names the
sidecar folder for interactive demos; `--copy-media` includes video files.

Markdown shape follows keydump: `# Deck`, `## Slide N`, `### Title`, body text as
bullets, tables as pipe tables, presenter notes as blockquotes. Body text items
are de-duplicated against the title, since Keynote's text items include the title
placeholder.

JSON is the structured form — per-slide title, text items, tables, notes, and
geometry where the reader can supply it. `slides patch` accepts it directly, so
a deck's titles and notes can be dumped, edited programmatically, and applied
back (see `patch` below for why only those two).

### Interactive demos, video and fallback tables

A deck is not only text. DeckWerk decks carry `web` elements (a complete,
self-contained HTML page shown in a sandboxed frame — a playground, a live
Python REPL), `video` elements, and `html` elements, which are the importer's
fallback for content it could not convert natively and which in practice hold
**tables**. A dump that silently drops all three turns an interactive slide
into a blank one.

So `dump` handles each:

- **`web`** — the page is copied out beside the dump as a self-contained file,
  and the slide gets a link to it. The pages are already self-contained by
  construction: DeckWerk stages them under `assets/web/` to run in an
  `<iframe sandbox>` with no access to the deck, so copying the file is
  enough. A dump of a deck therefore yields a folder of working demos
  next to the Markdown, openable in any browser.
- **`video`** — linked, not copied. Video files are large and already on disk;
  the link points at the source. `--copy-media` copies them too.
- **`html`** — parsed. When the markup is a table, it becomes a real `Table`
  and renders as a pipe table like any other. Otherwise its text is extracted.

The sidecar directory is named after the output file (`talk.md` →
`talk_assets/`) or given by `--assets-dir`. Dumping to stdout copies nothing
and links to the paths inside the deck, because there is no output location to
copy beside; `dump` says so on stderr rather than silently producing dead
links.

Markdown shape:

    ### Try it: fit line by hand

    [Interactive: Least-squares playground](talk_assets/playground.html)

JSON carries the same information structurally, under an `embeds` key, so a
caller can find every demo in a deck without parsing Markdown.

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

`patch` also accepts a `slides dump -f json` document. From a dump it applies
`title` and `notes` only, and says so on stderr: those two each map onto exactly
one thing on a slide, so writing them back is safe. A dump's `body` is every
text box on the slide merged together, and writing it into the body placeholder
would pull text out of the others; its `images` are paths that `patch` would
add a second time. Those go through a patch spec, where the intent is explicit.

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

### `slides theme` and `slides.theme`

Plots and figures that go beside a deck should match it, and a deck already
states its colours and fonts. This component extracts a palette from any deck
and emits it for whatever is drawing.

**Naive extraction does not work.** Counting colour frequency in a real Keynote
file returns, in order: `#000000` (606), `#ffffff` (394), `#f9f9f9` (324),
`#fefffe` (54), `#888888` (30), and only then `#a5d75f` (27) — which is the
deck's actual accent. Keynote's stock stylesheet ships hundreds of preset
swatches that swamp the colours the deck really uses. So extraction is a
two-stage process: gather candidates, then infer roles perceptually.

**Gathering.** Colours that are *used* outrank colours that merely *exist*. In
descending priority: slide background fills, text fills referenced by drawables
actually on slides, shape and stroke fills on slides, and only then the document
stylesheet. Each candidate carries a usage weight and the area it covers.

**Role inference**, in OKLab/OKLCH — perceptually uniform, so "similar" and
"readable" mean what they should. Implemented in about forty lines of pure
Python; no dependency.

- `background` — the slide background fill, which is known outright rather than
  guessed. Where several differ, the one covering the most slides.
- `foreground` — among text colours, the one with the highest WCAG contrast
  against the background, broken by usage weight.
- `muted` — text colours sitting between about 2:1 and the foreground's
  contrast, nearest the foreground in hue.
- `accents` — chromatic candidates (OKLCH chroma above threshold) clearing a
  minimum contrast against the background, ordered by usage and then spread by
  hue so a categorical scale gets distinct hues rather than four blues.
- `grid` — the lowest-contrast non-background colour, in the 1.1:1 to 2:1 band.

Near-duplicates collapse by OKLab ΔE before roles are assigned, so a preset
gradient family (`#00a2ff`, `#0085d1`, `#0093e8`, `#1fa3ff`) becomes one accent
rather than four. Any accent returned for a categorical scale is guaranteed to
clear its contrast floor; one that does not is lightened or darkened in OKLCH
with its hue held.

**Emitters.** The extracted `DeckTheme` renders to:

- **matplotlib** — an `rcParams` dict and `deck_style()` as a context manager in
  the library; on the command line, a style sheet for `plt.style.use()`.
- **ggplot2** — R source defining `theme_deck()` plus `scale_colour_deck()` and
  `scale_fill_deck()`, written tidyverse-style for sourcing from an analysis.
- **JSON** — the roles, for anything else.
- **CSS** — custom properties, for a web element or an HTML figure.

    slides theme TARGET [-f matplotlib|ggplot|json|css] [--accents N]

```python
from slides import read_deck
from slides.theme import extract
from slides.emit.matplotlib import deck_style

theme = extract(read_deck("talk/"))
theme.background, theme.foreground, theme.accents

with deck_style(theme):
    fig, ax = plt.subplots()
```

The tool ships no palette of its own; every colour comes from the deck in hand.
A caller with no deck can build a `DeckTheme` directly.


## Architecture

A normalised deck model is the spine: every reader produces it, every writer
consumes it. Four readers and four writers become eight pieces instead of
sixteen, and the model is the thing that makes the package worth importing.

    slides/
      model.py          Deck, Slide, TextItem, Table, Image, Embed  (dataclasses)
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
      color.py            OKLab/OKLCH, WCAG contrast, perceptual dedupe
      theme.py            palette extraction and role inference
      emit/
        matplotlib.py  ggplot.py  css.py
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
`matplotlib`. Colour science is pure Python — no `colormath`, no `numpy`
on that path.

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
- Rendering plots. `slides theme` hands over a palette; the caller draws.
- Anything that needs to know a deck's subject matter.
