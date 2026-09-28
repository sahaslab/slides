# Task 14 report: pptx writer and `convert -f pptx`

Status: DONE_WITH_CONCERNS (see "Concerns": SVG images need `rsvg-convert`, a
decision the controller should confirm).

## What was built

`src/slides/writers/pptx.py` exposes `write(deck, path) -> None`. python-pptx is
imported lazily inside functions. `tests/test_cli.py::test_help_does_not_import_heavy_dependencies`
still passes.

How it lays out a converted deck (this is what Task 15 inherits):

- **Canvas.** Slide size is `deck.width x deck.height` points at 12700 EMU per point.
- **Theme (amendment 1).** `slides.theme.extract(deck)` runs once per deck.
  - Every slide is painted with its own `background`, or with `theme.background`
    when it has none, so the theme foreground is always on a background it was
    chosen against.
  - Every text run (body, tables, embed labels) is coloured `theme.foreground`.
  - Titles take `theme.accents[0]` when `color.contrast(accent, theme.background) >= theme.TEXT_CONTRAST`
    (4.5), and `theme.foreground` otherwise.
- **Sizes (amendment 2).** Titles are `round(deck.height * 0.06)` pt (65 at 1080),
  body is `round(deck.height * 0.036)` pt (39), and tables are `round(body * 0.7)` pt (27).
- **Fonts (amendment 2).** The title font is `fonts.primary_family(theme.fonts["title"], "")`
  and the body font uses `theme.fonts["body"]`, via the existing `slides.emit.fonts`
  helper. When a deck has no stack (the Keynote reader sets none), the name is
  left at the template default.
- **Titles.** Slides use the "Title Only" layout, and the title goes in the real
  title placeholder, so the pptx reader, PowerPoint and Keynote's importer all see
  a slide title.
  - The placeholder is moved to the title item's geometry, or to a fallback band
    across the top (6% margins, 12% of the height).
  - Title paragraphs are left-aligned; the master centres them by default.
  - A slide with no title has the empty placeholder removed.
- **Body text.** Each non-title `TextItem` becomes a word-wrapped text box at its
  geometry. Items without geometry share equal slices of a body area spanning 22%
  to 94% of the slide height. This is the title-and-body fallback the Keynote
  route uses.
- **Tables.** Tables go where the brief puts them (there is no geometry in the
  model), with cell fills cleared so the default blue table style cannot put
  light text on a light fill.
- **Images (amendment 3).**
  - `Image.path` is resolved against `deck.source` and placed at its geometry, or
    in a centred 60% box when it has none.
  - Pictures are fitted inside the box at their own aspect ratio and centred,
    like DeckWerk's default `fit: contain`. On the real deck, 10 of the 30 images
    have boxes whose aspect ratio differs from the image's by 4 to 22%. Stretching
    would distort them.
  - A path that does not resolve is skipped with one stderr line
    (`Slide N: skipped image <path>, not a file`), and the conversion continues.
  - python-pptx only embeds BMP, GIF, JPEG, PNG, TIFF and WMF. SVG is rasterised
    to PNG with `rsvg-convert` at twice its box width, and WebP is re-encoded to
    PNG with Pillow (already a python-pptx dependency).
- **Embeds (amendment 4).** Each embed becomes its poster picture when
  `Embed.poster` resolves. Otherwise it becomes a text box centred in the embed's
  box, with the same label text as the Markdown writer (`Interactive: <title>` /
  `Video: <title or file name>`). Either way the shape carries a click hyperlink
  to `(deck.source / src).resolve().as_uri()`.
- **Notes.** Notes go into the notes slide.
- **Z-order.** Background first, then images, then embeds, then the title, body
  text and tables. Text therefore sits above figures.

`src/slides/commands/convert.py`:
- New branch: `("deckwerk", "pptx")` and `("keynote", "pptx")` go to `_to_pptx(args, source)`.
  The deckwerk route is untouched, and the edit is only that branch plus the new
  function at the end of the file.
- The output is `-o`, or else `source.with_suffix(".pptx")`.
- If the output exists, it writes `<path> already exists; pass -o with a new path`
  on stderr and returns 1, without writing anything.
- On success it writes "Builds and transitions do not survive this route" to
  stderr and the output path to stdout.
- The brief's unused `kind` parameter is gone.

## TDD evidence

- **RED 1.** I wrote all the tests first. `PYTHONPATH=src python -m pytest -q tests/test_writer_pptx.py`
  gave `ModuleNotFoundError: No module named 'slides.writers.pptx'`, a collection
  error.
- **RED 2.** With the writer in place and the convert route not yet added, the run
  gave `3 failed, 11 passed`:
  - `test_convert_writes_a_pptx` and `test_convert_refuses_to_overwrite_an_existing_pptx`
    failed with `ValueError: cannot convert deckwerk to pptx`.
  - The fixture-image test failed on my own over-specified `image.path == "plot.png"`
    assertion. After a save and reload, python-pptx names every image part
    `image.png`, which the pptx reader's own test also expects. I dropped that
    assertion and kept the geometry checks.
- **GREEN.** `tests/test_writer_pptx.py` has 16 passed. The full suite is
  `170 passed` (the baseline was 154).
- **Added after the implementation.**
  - `test_a_slide_without_a_title_keeps_no_empty_title_placeholder`.
  - `test_webp_images_are_re_encoded`. I checked by hand that python-pptx's
    `add_picture` raises on WebP (`ValueError: unsupported image format`) and on
    SVG (`UnidentifiedImageError`), so the WebP and SVG tests fail without the
    conversions.

The tests in `tests/test_writer_pptx.py`:
- The brief's three: round trip, canvas size, no-geometry layout. The last one
  also checks that the body text survives.
- Amendment tests:
  - Foreground on a dark background.
  - Title accent only when it clears 4.5:1 (one deck that clears, one that does not).
  - Font size scales with the canvas (65/39/27 at 1080, 32/19 at 540).
  - Fonts are the first family of each stack.
  - A fixture image comes back from the pptx reader as an `Image`.
  - An unresolved image is skipped with exactly one stderr line.
  - SVG is rasterised; skipped when `rsvg-convert` is absent.
  - WebP is re-encoded.
  - A web embed's shape links to a `file:///...assets/web/demo.html` URL, and the
    video's to `.../assets/clip.mp4`.
  - An embed with a poster becomes a linked picture instead of a label.
- Convert tests: it writes a pptx, and it refuses to overwrite one.

About the fixture: the DeckWerk fixture's `assets/plot.png` and
`assets/web/demo.poster.png` are not committed files. The image and poster tests
copy the fixture into `tmp_path` and write a small PNG there, so the shared
fixture is unchanged. The unmodified fixture is what the skip-with-stderr and
label tests use.

## Real-deck conversion

The DeckWerk deck `early_term_2026/keynote/04_sep28_conditional_linear` was
converted into a scratchpad `mktemp -d` dir with `-o`. It took 2.4 s, the output
is 23.4 MB, and the exit code was 0. I then re-read it with `slides.readers.pptx.read`
and inspected it with python-pptx:

- **Slides.** 68, all titled, canvas 1920x1080. 66 slides have notes, matching
  the source.
- **Theme.** Background `#0d1e1c`, foreground `#e7e7e6`, accent `#a5d75f` (10.2:1
  against the background, so titles take it). Every slide background is `0D1E1C`.
- **Text runs.**
  - 305 body runs are `E7E7E6` at 39 pt in Avenir Next.
  - 69 title runs are `A5D75F` at 65 pt in Charter (one title has two lines).
  - 108 table-cell runs are `E7E7E6` at 27 pt in Avenir Next.
  - There is no black text anywhere.
- **Pictures.** 32: the 30 images (27 of them rasterised from SVG), plus the 2
  web-embed posters. 4 tables.
- **Hyperlinks.** 4, and each resolves to an existing file:
  - Slide 16: poster picture linking to `assets/web/playground.3898dd78.html`.
  - Slide 68: poster picture linking to `assets/web/python_repl.ed758583.html`.
  - Slide 24: text box "Video: vid_rotate.mp4" linking to `assets/vid_rotate.mp4`.
  - Slide 25: text box "Video: vid_center.mp4" linking to `assets/vid_center.mp4`.
- **Size.** 20.4 MB of the 23.4 MB is the source's own 4096x2563 screenshot
  (`Screenshot.7b1bcaf5.png`, 20 MB on disk), embedded as-is. The 27 SVG rasters
  together come to about 2 MB.

I drew the shape boxes, pictures (from the embedded blobs) and text with
matplotlib into PNGs and looked at them:

- **Slide 2.** The Galton figure sits at its box, crisp, on the slate background.
  "Conditional Prediction" is in green Charter.
- **Slide 13 (timeline).** Two portraits, contain-fitted into their 140 pt boxes,
  and eight text boxes. At 39 pt, some body text spills below boxes that DeckWerk
  sized for smaller text. That follows from amendment 2's single body size.
- **Slide 16.** The playground poster fills the embed box, with the hyperlink on
  the picture.
- **Slide 24.** A centred "Video: vid_rotate.mp4" label in the video's box, linked
  to the mp4.
- **Slide 54.** Three figures with their captions.
- **Slide 1.** The full-slide screenshot, contain-fitted. Its 1.60 aspect ratio in
  a 1.78 box gives thin side bars.

I also converted `04_sep28_conditional_linear.key` (0.5 s):
- 61 slides, all titled, every background `0D1E1C`.
- 414 body runs `FEFFFE` at 39 pt and 61 title runs `A5D75F` at 65 pt, in the
  template font (the Keynote reader supplies no fonts).
- No pictures, because the Keynote reader reads no images or geometry.
- The rendered slides 12 and 40 show the fallback layout working: a title band
  across the top, then body boxes stacked below.

The overwrite guard, run against the CLI: a second conversion to the same `-o`
printed `... already exists; pass -o with a new path` and exited 1. I did not run
the no-`-o` default against the user's folder. There, `04_sep28_conditional_linear.pptx`
already exists and the guard would refuse, but I kept every write in temp dirs as
instructed.

## Files changed

- `src/slides/writers/pptx.py` (new)
- `src/slides/commands/convert.py` (the pptx branch and `_to_pptx`)
- `tests/test_writer_pptx.py` (new, 16 tests)
- `.superpowers/sdd/2026-09-27-slides-cli/task-14-report.md` (this report)

## Deviations from the brief

- **Title Only layout, not Blank.** The brief's code uses the Blank layout
  (index 6). With no title placeholder there, its own round-trip test cannot pass:
  the pptx reader takes titles from `shapes.title`.
- **Body text is not the brief's per-coordinate fallback.** A box with geometry
  keeps it. Boxes without geometry share the body area, instead of 90 pt rows at
  fixed 24/40 pt sizes, which overlap at amendment 2's sizes.
- **Contain-fitting images.** Not asked for. It stops 10 of the 30 real images
  from being stretched by up to 22%.
- **SVG and WebP conversion.** Not in the amendment, which assumes python-pptx can
  take any image. It cannot, and without these 27 of the 30 real images are lost
  (see Concerns).
- **The spec's `.key -> pptx` route.** The spec says this goes through Keynote's
  own export. Following the brief, `("keynote", "pptx")` reads the `.key` with the
  file reader and uses this writer, so Keynote is never launched. The output is
  therefore text only: no images, no geometry.
- **`_to_pptx`** takes no `kind` parameter; it was unused.

## Concerns

1. **`rsvg-convert` is a new external runtime dependency (Homebrew `librsvg`).**
   It is installed on this machine (2.60.0). I checked the alternatives:
   - python-pptx cannot embed SVG, and neither Pillow nor matplotlib can read it.
   - macOS `sips` renders these matplotlib SVGs wrongly: the text glyphs come out
     as giant filled shapes.
   - `qlmanage` pads the output to a square.

   If `rsvg-convert` is missing, `subprocess` raises `FileNotFoundError` naming
   it, in line with the user's no-defensive-programming rule. The alternative is
   native SVG in the pptx through the Office `asvg:svgBlip` extension. That keeps
   vectors in PowerPoint, but it still needs a raster fallback blip, and I do not
   know whether Keynote's pptx importer reads the SVG. PNG is the format Keynote
   certainly imports, which matters for Task 15. Please confirm the dependency, or
   say if you would rather have svgBlip.
2. **Label text is duplicated from the Markdown writer.** `_label` repeats the
   three lines of `slides.writers.markdown._link`'s label logic, because I could
   only touch my three files. A shared `label(embed)` in `markdown.py`, used by
   both writers, would remove the duplicate.
3. **String geometry from the DeckWerk reader.** It passes html elements' x/y/w/h
   through raw. `deck.json` can hold them as strings (fixture e9: `"w": "998.06"`),
   while web and video elements go through `_number`. `_geometry` coerces with
   `float()` so the writer cannot crash on them. The reader should normalise
   them instead.
4. **The DeckWerk reader carries KaTeX markup into text.** Math comes through
   three times, as MathML text, the TeX annotation and the HTML render. For
   example, slide 24's body reads `(xˉ,yˉ)(\bar{x}, \bar{y})(xˉ,yˉ)`, and slide
   33's formula table is unreadable. The same text shows up in `dump`. This is a
   reader problem, not a writer one, but it is the most visible flaw in the
   converted deck.
5. **The DeckWerk reader picks slide 1's title badly.** It chooses the topmost
   text, "Nikhil Singh, Fall 2026", so that line is set at the title's 65 pt in a
   box sized for a byline.
6. **One body size overflows some boxes.** Amendment 2's single 39 pt body size
   spills out of boxes DeckWerk sized for smaller text (the slide 13 timeline).
   The deck's own per-element sizes are not in the model.
7. **Nothing opened in a real presentation app.** LibreOffice is absent and
   Keynote must not be launched. Validity rests on python-pptx and the pptx reader
   re-reading the file, plus my own matplotlib rendering of the shapes.

## Fix round 1

This round started from `git merge --ff-only build-slides-cli` (fast-forward to
343dc59). convert.py and readers/deckwerk.py were not touched.

1. **A missing `rsvg-convert` no longer kills the conversion.**
   - `write` calls `shutil.which(RASTERISER)` once.
   - When it returns nothing, `_warn_svg_skipped` counts the images whose path
     resolves to an `.svg` file and writes one stderr line, for example
     `27 SVG images skipped: install librsvg (brew install librsvg) for rsvg-convert`.
     It says "image" when the count is 1.
   - `_image` then skips those SVGs, and the conversion carries on.
   - Missing files still get their own "not a file" line, as before.
   - rsvg-convert is still the rasteriser.
   - Test: `test_without_rsvg_convert_svg_images_are_skipped_with_one_stderr_line`
     monkeypatches `shutil.which` to return None. It uses 2 SVGs on two slides plus
     one PNG, and asserts the exact stderr line and 1/0 pictures on the two slides.
   - Real deck with `PATH=/usr/bin:/bin`, so `rsvg-convert` is not found: the exact
     27-image line, exit 0, and 68 slides with 5 pictures (3 raster images and 2
     posters) and 4 links. With `rsvg-convert` available: 32 pictures, as before.
   - SVG posters are not covered. DeckWerk writes its posters as PNG, and the
     ruling was about images.
2. **Shrink on overflow.**
   - `_fill` sets `frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE` (normAutofit)
     on every text frame it writes: the title placeholder, body boxes, embed labels
     and table cells. This replaces python-pptx's default text-box `spAutoFit`,
     which grew the shape instead of shrinking the text.
   - `fit_text()` is not used.
   - Test: `test_every_text_frame_shrinks_on_overflow` checks every text frame and
     table cell of the converted DeckWerk fixture.
   - Real deck: all 275 text frames and 108 table cells carry normAutofit.
   - Caveat for the live check: normAutofit is only a flag. python-pptx writes no
     `fontScale`, so the application computes the shrink itself. PowerPoint is
     known to apply it only when it re-lays out the text, which may not happen
     until the text is edited. Whether Keynote honours it on import is untested
     here, and is part of the controller's live check.
3. **Label logic in one place.**
   - `Embed.label() -> str` is now on the model in `src/slides/model.py`.
   - `writers/markdown.py`'s `_link` is `"[%s](%s)" % (embed.label(), embed.src)`,
     and its unused `pathlib` import is gone.
   - `writers/pptx.py` uses `embed.label()`, and `_label` is deleted.
   - The Markdown output is byte-identical: the existing embed tests pass, and the
     real deck's Markdown matches the old `_link` exactly (4 embed links).
   - Test: `test_the_embed_label_is_shared_with_the_markdown_writer`.

TDD:
- **RED.** All 3 new tests failed. The SVG test got empty stderr, because the real
  rasteriser ran. The autofit test failed with `all(...)` returning False. The
  label test failed with `AttributeError: 'Embed' object has no attribute 'label'`.
- **GREEN.** `PYTHONPATH=src python -m pytest -q` gives 218 passed (19 in
  tests/test_writer_pptx.py).

Files changed this round:
- `src/slides/writers/pptx.py`
- `src/slides/model.py`
- `src/slides/writers/markdown.py`
- `tests/test_writer_pptx.py`
- this report

## Fix round 2

This round started from `git merge --ff-only build-slides-cli` (fast-forward to
7c51416). convert.py was not touched.

1. **Text colour per slide.**
   - `theme.extract(deck)` still runs once per deck.
   - `write` now paints each slide with `ground = slide.background or theme.background`
     and resolves that slide's styles with `_styles(deck, palette, ground)`, cached
     in a dict keyed by `ground`. So each distinct background is resolved once.
   - Body, table and label text use
     `color.with_contrast(theme.foreground, ground, theme.TEXT_CONTRAST)`. This
     returns the foreground unchanged when it already clears 4.5:1. Otherwise it
     searches lightness toward the pole that `color.contrast_extreme(ground)`
     picks; that is the headroom rule, which `with_contrast` calls internally.
   - Titles take `theme.accents[0]` when it clears 4.5:1 against `ground`, and the
     resolved text colour otherwise.
   - `_slide` paints the `ground` it is given.
   - Test: `test_every_run_clears_text_contrast_against_its_own_slide`. It builds
     two white slides and one `#0d1e1c` slide with a table, from a theme whose
     majority background is white and whose foreground is `#111111`. It reads the
     painted background of each slide back from the pptx and asserts all 8 runs
     clear 4.5:1. Before the fix, the dark slide's text came out at 1.10:1.
2. **SVG posters.**
   - The rasterise check is now a small `SvgSupport(available, skipped)` object.
     Its `allows(path)` returns False for an SVG when rsvg-convert is absent, and
     counts it.
   - `_image` and `_embed` both go through it.
   - A poster that is not allowed falls back to the labelled text box, with the
     same `file://` hyperlink as an embed that has no poster.
   - Skipped posters are counted in the same single stderr line.
   - Test: `test_without_rsvg_convert_an_svg_poster_falls_back_to_a_linked_label`
     monkeypatches `shutil.which` to None, with one SVG image and one SVG poster.
     It asserts the exact `2 SVG images skipped: ...` line, the "Interactive: Demo"
     label whose hyperlink is the absolute URI of `demo.html`, and no pictures.
   - Also run for real with `PATH=/usr/bin:/bin`, so `rsvg-convert` is actually
     absent: a deck with an SVG poster wrote a pptx and exited 0 with
     `1 SVG image skipped: ...`.
3. **Skip count computed where the work happens.**
   - `SvgSupport.allows` increments the count as each image or poster is refused.
   - `write` prints the line after the slides are built.
   - `_warn_svg_skipped` now only formats the message, and the second pass that
     resolved every path again is gone.

TDD:
- **RED.** Both new tests failed. The mixed deck's slide-3 run was at 1.097:1. The
  poster test got `1 SVG image skipped` instead of `2 SVG images skipped`, because
  the poster went straight to the rasteriser.
- **GREEN.** `PYTHONPATH=src python -m pytest -q` gives 249 passed (21 in
  tests/test_writer_pptx.py).

Real decks, re-converted into a `mktemp -d` dir:

| Conversion | Slides | Runs | Weakest run contrast | Pictures | Links | Exit |
| --- | --- | --- | --- | --- | --- | --- |
| DeckWerk deck | 68 | 482 | 10.24:1 | 32 | 4 | 0 |
| DeckWerk deck, `rsvg-convert` off PATH | 68 | 482 | 10.24:1 | 5 | 4 | 0 |
| `.key` | 61 | 475 | 10.24:1 | 0 | 0 | 0 |

The run without `rsvg-convert` also printed the `27 SVG images skipped: ...`
line. The real deck's posters are PNG, which is why its 5 pictures include both
of them.

Files changed this round:
- `src/slides/writers/pptx.py`
- `tests/test_writer_pptx.py`
- this report
