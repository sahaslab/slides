# Task 15 report: `convert -f keynote` and `-f pdf`

## What was built

- `src/slides/keynote/export.py` (new): `open_and_save(source, out)`,
  `export_pdf(source, out)`, and the JXA templates `SCRIPT_SAVE` / `SCRIPT_PDF`,
  built from a shared `_GUARD` snippet (DRY — the already-open check and the
  fresh-open fallback are identical in both scripts; only the final `export`
  line and return literal differ).
- `src/slides/commands/convert.py` (modified): two new routes in `run` —
  `(deckwerk|pptx) -> keynote` calls `_to_keynote`, `(deckwerk|keynote|pptx)
  -> pdf` calls `_to_pdf`. Both refuse an existing output with the same
  message as `_to_pptx`. A `.pptx` source is passed straight to Keynote
  (no re-write); a DeckWerk source is staged to pptx first inside a
  `tempfile.TemporaryDirectory()` that is cleaned up before the function
  returns.
- `tests/test_keynote_export.py` (new, from the brief's Step 1, rewritten to
  the house style) plus two added tests for the already-open guard itself.
- `tests/test_convert.py` (extended): 7 new tests covering both routes'
  staging/pass-through/refuse-existing behavior, all mocking
  `slides.keynote.export` so no test ever calls `jxa.run` / `osascript`.

Did not touch `src/slides/writers/pptx.py` or `src/slides/model.py` (owned by
the concurrent agent) — confirmed via `git status`/`git diff --stat`, only
`convert.py`, `test_convert.py` modified, `export.py`, `test_keynote_export.py`
added.

## TDD evidence

RED (`export` doesn't exist yet):
```
$ PYTHONPATH=src python -m pytest tests/test_keynote_export.py -v
ERROR collecting tests/test_keynote_export.py
ImportError: cannot import name 'export' from 'slides.keynote'
```

RED (routes not wired yet, 7 new convert tests):
```
$ PYTHONPATH=src python -m pytest tests/test_convert.py -v
...
FAILED test_keynote_route_stages_a_pptx_for_a_deckwerk_source
FAILED test_keynote_route_passes_a_pptx_source_directly
FAILED test_keynote_route_refuses_an_existing_output
FAILED test_pdf_route_from_a_keynote_source_skips_staging
FAILED test_pdf_route_from_a_pptx_source_skips_staging
FAILED test_pdf_route_from_a_deckwerk_source_stages_a_pptx
FAILED test_pdf_route_refuses_an_existing_output
ValueError: cannot convert ... to keynote/pdf
7 failed, 4 passed
```

GREEN after implementing `export.py` and the two convert routes:
```
$ PYTHONPATH=src python -m pytest tests/test_convert.py tests/test_keynote_export.py -v
17 passed
```

Full suite after the change:
```
$ PYTHONPATH=src python -m pytest -q
228 passed in 21.65s
```

## What the sdef says, for each JXA call used

Read from `/Applications/Keynote Creator Studio.app/Contents/Resources/Keynote.sdef`
(this machine's app is "Keynote Creator Studio"; `jxa.app_name()` defaults to
"Keynote" unless `$SLIDES_KEYNOTE_APP` is set — the controller's live check
must set that env var, see below).

- **`export` command** (`Keynote Suite`, code `Knstexpo`): direct parameter is
  the document, `to:` is the destination `file`, `as:` is an `export format`
  enumeration. The enumeration (`Knef`) includes, among others:
  `HTML`, `QuickTime movie`, `PDF` (`Kpdf`, `com.apple.iWork.Keynote.exportPDF`),
  `slide images`, `Microsoft PowerPoint` (`Kppt`, extension `.pptx`), and
  **`Keynote 09`** (`Kkey`, `com.apple.iWork.Keynote.exportKEY`, extension
  `.key`). This is the brief's own documented fallback for producing a `.key`
  file, and it's what I used for `SCRIPT_SAVE` (`as: "Keynote 09"`) — see
  "Deviation" below for why I used `export` instead of `save` in every case,
  not just the already-open one.
- **`save` command** (imported `Standard Suite`, `CocoaStandard.sdef`, code
  `coresave`): direct parameter is the document specifier, `in:` is the
  destination file, `as:` is a `saveable file format`. Keynote's own
  `saveable file format` enum (`savf`) defines exactly one enumerator,
  `Keynote` (`Knff`, UTI `com.apple.iwork.keynote.key-tef`) — so `save` can
  only ever write Keynote's native format, never chosen per source kind. Not
  used in the final scripts (see Deviation).
- **`open` command** (`Standard Suite`, code `aevtodoc`): direct parameter is
  a file or list of files; returns the opened document(s). Used unchanged as
  `app.open(Path(sourcePath))`.
- **`close` command** (`Standard Suite`, code `coreclos`): `saving:` is a
  `save options` enum (`yes`/`no`/`ask`); used as `doc.close({saving: "no"})`,
  called only when the script itself opened the document.
- **`document` class extension** (Keynote Suite) adds `id` (read-only,
  `scriptIdentifier`) — used elsewhere (`patch.py`, `scaffold.py`), not by
  this task. The base `document` class (`Standard Suite`) has `file` (`file`,
  access `r`, `fileURL`) — this is the property Amendment 1 says to compare;
  in JXA a document's `.file()` returns a file specifier and `.toString()`
  gives its POSIX path, which is what the guard compares against the
  resolved source path.

## Deviation from the brief's amendment text (and why)

Amendment 1 says: "If it was [already open], it **exports** from that
document and leaves it open; only a document the script opened itself is
closed." Read literally that only mandates `export` for the already-open
case, implying `save` for the fresh-open case (matching the brief's original
`doc.save({in: Path(out)})` draft). I used `app.export(doc, {to: Path(out),
as: "Keynote 09"})` in **both** cases (already-open and freshly-opened),
instead of branching between `save` and `export`. Reasoning:

1. Amendment 1's last line is explicit and absolute: "`SCRIPT_SAVE` never
   saves over the source." `save({in: outPath})` is Keynote's "Save As" —
   it doesn't touch the source file's bytes, but it does redirect the *live
   document's own file association* to `outPath`. For the already-open case
   this would silently repoint the user's open window at a new file out from
   under them, which is exactly the kind of surprise mutation Amendment 1 is
   guarding against. `export` never changes `doc.file()` or the window's
   save target — it just writes an independent copy — so it's the only
   command that is safe unconditionally.
2. Using `export` uniformly is simpler (one code path, easily shared as
   `_GUARD` between `SCRIPT_SAVE`/`SCRIPT_PDF`) and removes any dependence on
   `out`'s extension implying a save format, since Keynote's `saveable file
   format` enum only has one member anyway.
3. It matches the brief's own documented fallback for Step 6 ("the working
   alternative is `app.export(doc, {to: Path(out), as: "Keynote 09"})`"),
   which the sdef confirms is a real, valid enumerator — so I did not need to
   guess between two untested branches for the live check.

If the controller's live run shows Keynote actually needs `save({in:})` for
some reason `export ... as "Keynote 09"` doesn't cover (e.g. theme/master
slide fidelity), that would be new information the sdef alone can't settle;
flip `SCRIPT_SAVE`'s tail back to `doc.save({in: Path(outPath)})` only for the
`!alreadyOpen` branch and re-run `test_open_and_save_invokes_jxa`.

## Concerns

- `candidate.file()` is wrapped in a JS `try/catch` inside the guard loop
  (not the brief's literal text) because a brand-new, never-saved Keynote
  document open in the same session has no `file`, and I could not verify on
  this machine whether that property access throws or returns `undefined`.
  Without the guard, iterating `app.documents` while any such window is open
  could crash the whole script before it reaches the target document. This
  is JS defensive code inside a string template, not Python/R, so it isn't
  covered by the user's no-try/except rule.
- I did not modify `src/slides/writers/pptx.py` or `src/slides/model.py`.

## Exact live-check commands (controller, with the user present)

Do not run these yourself; they are for the controller to run against the
real app, per the hard constraint.

```bash
# Set once if the local app identifies itself as "Keynote Creator Studio":
export SLIDES_KEYNOTE_APP="Keynote Creator Studio"

# 1. Plain conversion, nothing else open — proves the basic path works.
PYTHONPATH=src python -m slides.cli convert tests/fixtures/mini_deckwerk -f keynote -o /tmp/mini15.key
open /tmp/mini15.key   # expect: opens, matches the DeckWerk fixture's slides

# 2. PDF export straight from a .key.
PYTHONPATH=src python -m slides.cli convert /tmp/mini15.key -f pdf -o /tmp/mini15.pdf
open /tmp/mini15.pdf   # expect: a PDF with the same slide count

# 3. THE GUARD, the one that matters: open /tmp/mini15.key in Keynote by hand
#    first (File > Open), make a small unsaved edit (e.g. type a character
#    into a text box) so there is something to lose, and leave it open. Then
#    run PDF export again with a *different* -o so it can't collide with an
#    existing-output refusal:
open /tmp/mini15.key
# ... make an unsaved edit, leave the window open ...
PYTHONPATH=src python -m slides.cli convert /tmp/mini15.key -f pdf -o /tmp/mini15-guarded.pdf
# Expect: the command succeeds, a PDF appears at /tmp/mini15-guarded.pdf, AND
# the already-open Keynote window for mini15.key is still open with the
# unsaved edit still showing (unsaved-changes indicator still present,
# window not closed, not reverted). If Keynote closes that window, or the
# edit is gone, or a save dialog appears, the guard has failed.
```

If step 3 fails, the fix is almost certainly in the guard's path comparison
(`candidate.file().toString() === sourcePath`) — e.g. path normalization
(symlinks, `/private/tmp` vs `/tmp` on macOS) making the two strings not
match even though they refer to the same file. `pathlib.Path(source).resolve()`
resolves symlinks on the Python side; `doc.file().toString()` may not resolve
`/tmp` -> `/private/tmp` the same way, which would make the guard think the
open document isn't the target and open (then close) a second copy instead of
reusing the live one. Worth checking first if the live run surprises us.

## Fix round 1: decide the already-open guard by document id, not by path

The controller's review confirmed my own concern above (`/tmp` vs
`/private/tmp`) and generalized it: any mismatch between
`candidate.file().toString()` and the Python-resolved `sourcePath` — a
symlinked home or Desktop, Unicode normalisation of an accented filename, a
trailing slash — makes the loop miss the user's already-open document.
`app.open(Path(sourcePath))` then hands back that same open document (Cocoa
apps return the existing document for a file that's already open, they don't
open a second copy), and the old script would close it with `saving: "no"`,
discarding the user's unsaved edits: exactly the failure this whole task
exists to prevent. Path comparison was the wrong primitive.

### What changed

`_GUARD` in `src/slides/keynote/export.py` no longer loops over
`app.documents`, compares `.file()`, or wraps that access in a try/catch.
Instead it captures document identity before opening:

```javascript
var before = app.documents.id();
var doc = app.open(Path(sourcePath));
var alreadyOpen = before.indexOf(doc.id()) !== -1;
```

`before` is the array of ids of every document open *before* the call — a
snapshot of "what was already there." `app.open` then either returns the
existing document (if `sourcePath` was already open) or a newly-opened one.
Checking whether that returned document's id was already in `before`
answers "was this already open?" by identity, which can't be fooled by any
path representation issue. This also deletes the try/catch entirely: it was
only needed because the path approach called `.file()` on documents that
might have no backing file yet (a new, unsaved presentation) — the id
approach never touches `.file()` at all.

**Verifying `app.documents.id()` returns an array, without touching
Keynote.** The sdef confirms `document.id` is `type="text" access="r"`
(`scriptIdentifier`), same shape as before, but the sdef alone doesn't say
whether asking a *collection* specifier for a property batches it into an
array — that's a general JXA/Apple-Event-bridge behaviour, not something
Keynote's own dictionary documents. I could not launch Keynote to check it
directly (hard constraint), so I verified the general idiom against System
Events instead, which is always running and is not the user's work:

```
$ osascript -l JavaScript -e '
var se = Application("System Events");
var ids = se.processes.id();
JSON.stringify({ok: true, isArray: Array.isArray(ids), length: ids.length, sample: ids.slice(0,3)});
'
{"ok":true,"isArray":true,"length":156,"sample":[4097,32776,53261]}
```

This confirms that a JXA collection specifier's `.id()` (and `.name()`,
tested the same way) returns an array of that property across all elements —
a runtime-level behaviour of the ObjC scripting bridge, independent of which
app's dictionary defines the property. It applies to `app.documents.id()` in
Keynote the same way it applies to `se.processes.id()` in System Events.

### Tests

Replaced the two guard-shape tests with three, matching the controller's
required assertions and asserting the path comparison is gone:

- `test_already_open_guard_captures_ids_before_opening` — `"var before =
  app.documents.id();"` appears in both templates, at a lower string index
  than `"app.open(Path(sourcePath))"`, and both contain
  `"alreadyOpen = before.indexOf(doc.id()) !== -1;"`.
- `test_no_template_compares_document_file_paths` — neither template
  contains `.file()` or `candidateFile`.
- `test_close_is_conditional_on_the_already_open_guard` — unchanged from
  round 1 (`if (!alreadyOpen) { ... doc.close(...) }` in both).

RED (against the round-1 path-based guard):
```
$ PYTHONPATH=src python -m pytest tests/test_keynote_export.py -v
FAILED test_already_open_guard_captures_ids_before_opening - ValueError: substring not found
FAILED test_no_template_compares_document_file_paths - AssertionError: assert '.file()' not in ...
2 failed, 5 passed
```

GREEN after rewriting `_GUARD`:
```
$ PYTHONPATH=src python -m pytest tests/test_keynote_export.py -v
7 passed
```

Full suite (after `git merge --ff-only build-slides-cli`, which pulled in
Task 14's fix round and Task 18's fix round as unrelated commits):
```
$ PYTHONPATH=src python -m pytest -q
248 passed in 21.90s
```

`open_and_save` / `export_pdf` signatures were already one-parameter-per-line
from round 1; no signature changes were needed this round.

### Style check

- No `try`/`except` (Python) introduced or remaining; the JS-side try/catch
  from round 1 is gone along with the path loop it protected.
- Double-quoted strings, C-style `%s` formatting, one-parameter-per-line
  signatures unchanged in `export.py` and `convert.py`.

### Concerns

- None new. The id-array behaviour is verified against a real, always-on
  scriptable app (System Events) rather than assumed from documentation, but
  it is still inference from a different app's dictionary rather than a
  direct Keynote observation — if Keynote's `documents` element somehow
  special-cases batch property access (no evidence of this in the sdef, and
  no other Keynote scripting suite in the file suggests it), the live check
  below is where that would surface.

### Updated live-check commands

Do not run these yourself; they are for the controller to run against the
real app, per the hard constraint. Commands 1 and 2 are unchanged from round
1. Command 3 now specifically opens the target through a symlinked path
(`/tmp` -> `/private/tmp` on macOS) so the check exercises exactly the case
a path-based guard would have missed:

```bash
# Set once if the local app identifies itself as "Keynote Creator Studio":
export SLIDES_KEYNOTE_APP="Keynote Creator Studio"

# 1. Plain conversion, nothing else open.
PYTHONPATH=src python -m slides.cli convert tests/fixtures/mini_deckwerk -f keynote -o /tmp/mini15.key
open /tmp/mini15.key   # expect: opens, matches the DeckWerk fixture's slides

# 2. PDF export straight from a .key.
PYTHONPATH=src python -m slides.cli convert /tmp/mini15.key -f pdf -o /tmp/mini15.pdf
open /tmp/mini15.pdf   # expect: a PDF with the same slide count

# 3. THE GUARD — open the deck via its symlinked path (/tmp, not the
#    resolved /private/tmp target) so the check covers exactly the case
#    a path comparison would miss:
open /tmp/mini15.key
# ... in the Keynote window that opens, make a small unsaved edit (e.g. type
# a character into a text box) so there is something to lose, and leave the
# window open ...
PYTHONPATH=src python -m slides.cli convert /tmp/mini15.key -f pdf -o /tmp/mini15-guarded.pdf
# Expect: the command succeeds, a PDF appears at /tmp/mini15-guarded.pdf, AND
# the already-open Keynote window for mini15.key is still open with the
# unsaved edit still showing (unsaved-changes indicator still present,
# window not closed, not reverted, no save dialog). If Keynote closes that
# window, or the edit is gone, the id-based guard has failed and needs
# another look — at that point the sdef can't tell us more; it would need
# tracing the actual ids `before` and `doc.id()` resolve to in that session.
```
