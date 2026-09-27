# Task 17: `slides scaffold` — Report

## What was built

- `src/slides/keynote/scaffold.py` — `SCRIPT_CREATE` (JXA), `FRONT_DOCUMENT`, `build(spec, template=None, output=None) -> dict`, `_document_expression`, `_without_master`.
- `src/slides/commands/scaffold.py` — `run(args) -> int`, `_resolve_output(args, spec_path)`.
- `src/slides/keynote/patch.py` — added `"master"` to `FIELDS` so `_check` accepts the per-slide `master` key.
- `src/slides/cli.py` — added `-o/--output` to the `scaffold` subparser (default `None`); no other changes (`--template` and `spec` already existed).
- `tests/test_scaffold.py` (new) — library-level tests.
- `tests/test_commands_scaffold.py` (new) — command-layer tests.
- `tests/test_cli.py` — added two small parser tests for the new `-o/--output` flag.

## Design vs. the brief (per the controller's rulings)

1. **Firstindex re-keying (ruling 1).** `SCRIPT_CREATE` computes `firstIndex = doc.slides.length + 1` *before* creating any slide and returns `{created, firstIndex}`. `_without_master` now takes `first_index` and keys the patch spec `first_index, first_index+1, ...` via `enumerate(order, start=first_index)`, instead of `enumerate(order, start=1)`. This is the change that prevents `patch.apply` from silently overwriting a non-empty document's existing slides.

2. **Template is never touched (ruling 2).** `build` gained an `output: str | None = None` parameter. `_document_expression`:
   - Without `--template`: returns `FRONT_DOCUMENT` (`"app.documents[0]"`), and `output` is ignored entirely (never read, never written).
   - With `--template`: refuses if `pathlib.Path(output)` already exists (`raise FileExistsError(...)`, no JXA call happens — verified by a test that fails the run if `jxa.run_json` is invoked), otherwise `shutil.copyfile(template, destination)` and returns `"app.open(Path(%s))" % (jxa.literal(str(destination)),)` — the JXA script only ever references the **copy's** path, never the template's.
   - `cli.py` gained `-o/--output`; `commands/scaffold.py._resolve_output` computes the default (`spec_path.with_suffix(".key")`) only when `--template` is given, and passes `None` through untouched otherwise, matching "`-o` is ignored with no output file" when there's no template.

3. **Missing-master pre-flight check (ruling 3).** `SCRIPT_CREATE` builds `available` from `doc.masterSlides[i].name()`, then loops over every wanted slide and throws `"No master slide named " + name + "; available: " + available.join(", ")` **before** the creation loop runs (`doc.slides.push` is untouched if any master is missing). This is JXA-only behavior; it's exercised at the script-text level (see RED/GREEN below), same technique `patch.py` already uses for its own JXA-only table-bounds check (`test_table_writes_are_bounded_by_the_live_cell_count`). The controller's real-app check is the place this actually runs.

4. `result["created"]` and the `"Created %d slides\n"` stderr line are unchanged from the brief.

## Style deviations from the brief's literal code

- Rewrote `'"%s"' % (jxa.app_name(),)` as `jxa.literal(jxa.app_name())` (per the task's explicit instruction — this was the pattern Task 7/16 reviews rejected).
- Rewrote `app.open(Path("%s"))` (brief's `OPEN_TEMPLATE`) as `"app.open(Path(%s))" % (jxa.literal(str(destination)),)` — same reason, and now points at the copy, not the template.
- All function signatures with >1 parameter are one-parameter-per-line (`build`, `_document_expression`, `_without_master`, `_resolve_output`).
- Double-quoted strings throughout; the brief's test literals like `'"1"'` were rewritten as `"\"1\""` (escaped double quotes) so no single-quoted string literals remain in the new test file (one pre-existing single-quoted literal in `tests/test_cli.py`'s untouched `test_help_does_not_import_heavy_dependencies` was left alone — out of scope for this task).
- Import order in both new files: builtins, then `from slides...`, no blank line between blocks (matches `patch.py`'s existing convention).
- No `try/except` added anywhere; `FileExistsError`, `TypeError` (bad spec keys), and any real JXA/osascript failures are all left to propagate naturally.

## TDD evidence

**RED** — before writing `scaffold.py`/`commands/scaffold.py`:
```
ERROR collecting tests/test_scaffold.py
ImportError: cannot import name 'scaffold' from 'slides.keynote'
ERROR collecting tests/test_commands_scaffold.py
ImportError: cannot import name 'scaffold' from 'slides.keynote'
2 errors in 0.08s
```

One more RED cycle surfaced mid-implementation: my first draft of `test_slides_are_created_in_numeric_order` used the brief's `lambda script: seen.setdefault("script", script) or {"created": 3, "firstIndex": 1}` idiom. `dict.setdefault` returns the (truthy, non-empty) script string on first insert, so `string or {...}` evaluated to the *string*, not the dict — harmless in the brief's original version (which never read `result["firstIndex"]`), but with ruling 1's `_without_master(spec, order, result["firstIndex"])` it surfaced as `TypeError: string indices must be integers, not 'str'`. Fixed by replacing the lambda with a small `def fake_run_json` that sets `seen["script"]` as a side effect and returns the dict directly.

**GREEN** — full suite after implementation:
```
$ PYTHONPATH=src python -m pytest -q
........................................................................ [ 51%]
.....................................................................    [100%]
141 passed in 2.79s
```
(126 pre-existing + 9 in `test_scaffold.py` + 4 in `test_commands_scaffold.py` + 2 new in `test_cli.py` = 141.)

Key individual assertions worth calling out:
- `test_patch_keys_start_after_the_documents_existing_slides` — mocks `run_json` to return `firstIndex: 6` and asserts the patch spec handed to `patch.apply` is keyed `{"6", "7"}`, with `"1" not in seen["spec"]` (ruling 1, using the controller's exact "5 existing slides -> firstIndex 6" scenario).
- `test_checks_masters_exist_before_creating_any_slide` — asserts the position of `available.indexOf(name) === -1` precedes `doc.slides.push(made)` in `SCRIPT_CREATE`, and that both `"No master slide named "` and `"available: "` appear in the script (ruling 3).
- `test_template_is_copied_and_the_copy_is_opened_not_the_template` — real `tmp_path` template + output files; asserts the output file has the template's bytes, the template file is byte-for-byte unchanged, the emitted script contains the output path and does **not** contain the template path (ruling 2).
- `test_refuses_to_overwrite_an_existing_output` — output file pre-exists; `jxa.run_json` is monkeypatched to raise `AssertionError` if called at all; asserts `FileExistsError` with `"already exists"` and that the pre-existing output content is untouched (ruling 2).
- `test_without_template_uses_the_front_document_and_ignores_output` — `template=None` with an `output` path passed anyway; asserts the script uses `FRONT_DOCUMENT` and that the ignored output path was never created on disk (ruling 2).

## Files changed

- `src/slides/keynote/scaffold.py` (new)
- `src/slides/commands/scaffold.py` (new)
- `src/slides/keynote/patch.py` (`FIELDS` += `"master"`)
- `src/slides/cli.py` (`-o/--output` added to `scaffold` subparser)
- `tests/test_scaffold.py` (new)
- `tests/test_commands_scaffold.py` (new)
- `tests/test_cli.py` (two new parser tests)

## Concerns / notes for the controller

- I did not add a "no presentation is open" guard to the `FRONT_DOCUMENT` path inside `SCRIPT_CREATE` (patch.py's `SCRIPT` and `readers/keynote_live.py`'s `SCRIPT` both do this for their own `app.documents[0]` access). It wasn't asked for by any ruling, and adding it would have been scope creep beyond the four rulings; if you want parity with those two scripts' readable-error behavior, it's a one-line addition (`if (app.documents.length === 0) { throw new Error("No presentation is open."); }` right after `var doc = %s;`, guarded to the front-document path only).
- `build()`'s call to `patch.apply(...)` doesn't pass `app=`; it relies on `patch.apply`'s own `jxa.app_name()` fallback resolving to the same value `build` already used. No behavioral difference since both reads happen in the same process against the same `SLIDES_KEYNOTE_APP` env var, but it's worth a one-line note in case a future task wants `scaffold` and `patch` pinned to the exact same resolved name.
- No `NEEDS_CONTEXT`: nothing in the rulings conflicted with what I found in `patch.py`, `jxa.py`, or `cli.py`.

## Live-app check commands (NOT run by me — Step 6 / launching Keynote was out of scope per the hard constraints)

A real sample `.key` exists on this machine and is already used by other tests in this repo (`tests/test_reader_keynote_file.py`'s `REAL` fixture):
`~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/09_oct14_tfidf_imbalance_eval.key`

**1) With `--template` (never touches the source `.key`):**

```bash
rm -f /tmp/scaffold-template-out.key
cat > /tmp/scaffold-template.json <<'EOF'
{
  "1": {"title": "First", "body": ["One point"], "notes": "Open here."},
  "2": {"title": "Second", "body": ["Another point"]}
}
EOF
PYTHONPATH=src python -m slides.cli scaffold /tmp/scaffold-template.json \
  --template ~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/09_oct14_tfidf_imbalance_eval.key \
  -o /tmp/scaffold-template-out.key
```
Expect: Keynote opens `/tmp/scaffold-template-out.key` (a fresh copy of the source deck) with 2 new slides appended at the end, titled "First"/"Second" with the given body/notes. Confirm the original `.key` under `~/Desktop/Git/Class/...` is byte-for-byte unchanged (e.g. `git status` there, or compare mtimes). Re-running the exact same command a second time should fail fast with an `"already exists"` error and must not touch Keynote at all.

**2) Against a front document that already has slides (exercises ruling 1):**

```bash
cp ~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/09_oct14_tfidf_imbalance_eval.key /tmp/scaffold-front-check.key
open /tmp/scaffold-front-check.key   # let Keynote finish opening it and bring it frontmost
cat > /tmp/scaffold-front.json <<'EOF'
{
  "1": {"title": "New First", "body": ["Point"], "notes": "Appended."},
  "2": {"title": "New Second", "body": ["Another point"]}
}
EOF
PYTHONPATH=src python -m slides.cli scaffold /tmp/scaffold-front.json
```
Expect: 2 new slides appended **after** the deck's existing slides (whatever count `/tmp/scaffold-front-check.key` already has), titled "New First"/"New Second" — never overwriting the deck's existing slide 1/2. This is the direct live-app confirmation of ruling 1 (`firstIndex` re-keying), using a throwaway copy so the real teaching deck under `~/Desktop/Git/Class/...` is never opened directly.

---

# Fix round 1: document identity, bundle templates, front-document guard

Reviewed commit: `4d3765f` (Merge Task 17: slides scaffold). Synced with `git merge --ff-only build-slides-cli` (fast-forwarded 85ac8d6 -> b9319dd, pulling in Task 12/Math/etc. merges from other implementers; no conflicts).

## What changed and why

### 1. (Critical) Document identity now threads through both JXA calls

`build()` ran `SCRIPT_CREATE` in one `osascript` process and `patch.apply()`'s `SCRIPT` in a second, separate `osascript` process, and neither carried any reference to *which* document the first call had just created slides in. The second call resolved `app.documents[0]` — whatever Keynote considers frontmost at that later moment. Any focus change between the two calls (user clicks another deck, a slow master-slide loop, the newly-opened copy not yet being key) would silently write the new slides' content into the wrong live document.

Fix, per the ruling:
- `scaffold.SCRIPT_CREATE`'s final `JSON.stringify` now also reports `id: doc.id()`, alongside `created` and `firstIndex`.
- `patch.apply` gained a third, optional parameter: `document: str | None = None`. `patch.SCRIPT` itself (the static template, not something assembled per-call) now contains both branches explicitly:
  ```js
  var documentId = %s;
  var doc;
  if (documentId) {
    doc = app.documents.byId(documentId);
    if (!doc.exists()) { throw new Error("No open document with id " + documentId); }
  } else {
    if (app.documents.length === 0) { throw new Error("No presentation is open."); }
    doc = app.documents[0];
  }
  ```
  `apply()` splices `jxa.literal(document)` when `document` is given, or the bare JS `null` when it is not (`document_id = jxa.literal(document) if document is not None else "null"`), so `documentId` is always a real JS value — never a raw, unescaped Python string. `slides patch` (the CLI command, and every existing caller) never passes `document`, so its behavior is byte-for-byte unchanged: `documentId` is `null`, the `else` branch runs, `app.documents[0]` is used exactly as before.
- `scaffold.build()` now passes `document=result["id"]` into `patch.apply(...)`, so the fill always targets the exact document `SCRIPT_CREATE` just created slides in, by its stable Keynote-assigned id — regardless of what becomes frontmost afterward.
- `exists()` and `byId()` are standard, universal AppleScript/JXA Standard-Suite mechanics: any element class whose sdef declares a unique `id` property (Keynote's `document` class does — the reviewer confirmed this from the sdef) gets an auto-generated `.byId()` accessor on its containing collection, and `.exists()` is available on any object specifier and returns `false` rather than throwing when the reference doesn't resolve — the same idiom already used throughout this codebase's sibling scripts for `byName()`.

### 2. (Important) Directory-bundle templates no longer crash the copy

`_document_expression` (renamed `_document_statement` — see below) called `shutil.copyfile(template, destination)` unconditionally. Keynote saves `.key` files as either a single zip or a directory bundle (confirmed precedent: `readers/keynote_file.py`'s `_streams()` and `keynote/math.py`'s `zipped()` both branch on `path.is_dir()` for exactly this reason) — `shutil.copyfile` raises `IsADirectoryError` on the latter. Fixed:
```python
if source.is_dir():
    shutil.copytree(source, destination)
else:
    shutil.copyfile(source, destination)
```
Both branches are exercised by tests using real `tmp_path` fixtures (one a plain file, one a directory with a nested `Index/Document.iwa`, mirroring the shape `keynote_file.py` reads).

### 3. (Minor) Front-document path now gives a readable error when nothing is open

`FRONT_DOCUMENT` was the bare expression `"app.documents[0]"`. `SCRIPT_CREATE` spliced it directly into `var doc = %s;`, so an empty Keynote (no open presentation, no `--template`) hit Keynote's own opaque native error. `FRONT_DOCUMENT` is now the full statement pair patch.py and `readers/keynote_live.py` already use:
```python
FRONT_DOCUMENT = (
    "if (app.documents.length === 0) "
    "{ throw new Error(\"No presentation is open.\"); }\n"
    "var doc = app.documents[0];"
)
```
`SCRIPT_CREATE`'s placeholder changed from `var doc = %s;` to a bare `%s`, since both branches (`FRONT_DOCUMENT` and the template-open branch) now supply their own full `var doc = ...;` statement. The template-open branch's return value changed correspondingly: `"var doc = app.open(Path(%s));" % (...)` (previously just the right-hand-side expression).

## Renames / signature changes

- `scaffold._document_expression` -> `scaffold._document_statement` (it now returns a full JS statement, or two, not a bare expression). No test referenced the old private name directly, so this is a safe internal rename — confirmed by grep before renaming.
- `patch.apply(spec, app=None)` -> `patch.apply(spec, app=None, document=None)`. `FIELDS`, `_check`, and `from_dump` are untouched, as instructed.
- `scaffold.build()`'s call into `patch.apply` changed from a single positional arg to `patch.apply(_without_master(...), document=result["id"])`.

## TDD evidence

**RED** (ran immediately after applying the three source fixes, before touching any test file):
```
$ PYTHONPATH=src python -m pytest -q tests/test_scaffold.py tests/test_patch.py tests/test_commands_scaffold.py
...
FAILED tests/test_scaffold.py::test_creates_then_patches - KeyError: 'id'
FAILED tests/test_scaffold.py::test_master_is_stripped_before_patching - KeyError: 'id'
FAILED tests/test_scaffold.py::test_slides_are_created_in_numeric_order - KeyError: 'id'
FAILED tests/test_scaffold.py::test_patch_keys_start_after_the_documents_existing_slides - KeyError: 'id'
FAILED tests/test_scaffold.py::test_template_is_copied_and_the_copy_is_opened_not_the_template - KeyError: 'id'
FAILED tests/test_scaffold.py::test_without_template_uses_the_front_document_and_ignores_output - KeyError: 'id'
6 failed, 15 passed in 0.09s
```
This is exactly the expected fallout: every existing test whose mocked `jxa.run_json` returned a `SCRIPT_CREATE`-shaped dict without an `"id"` key now fails on `result["id"]` inside `build()`, since `patch.apply` is called with `document=result["id"]` unconditionally. (The mocked `patch.apply` replacements in those same tests also needed `document=None` added to their lambda signatures, or the *next* run would have failed with `unexpected keyword argument 'document'` instead — caught and fixed in the same pass.)

**GREEN** — full suite after updating the existing mocks (`+"id": "doc-1"` on every `SCRIPT_CREATE`-shaped fake return, `document=None` on every mocked `patch.apply`) and adding the new tests below:
```
$ PYTHONPATH=src python -m pytest -q
........................................................................ [ 36%]
........................................................................ [ 72%]
.......................................................                  [100%]
199 passed in 20.67s
```
(141 from the original Task 17 submission + 52 pulled in by the `git merge --ff-only build-slides-cli` from other tasks' work, all pre-existing and unaffected, + this round's 6 new tests: 3 in `tests/test_scaffold.py`, 3 in `tests/test_patch.py`. `tests/test_scaffold.py` now has 12 tests total, `tests/test_patch.py` now has 11.)

New tests added this round:
- `tests/test_scaffold.py::test_document_id_flows_from_create_into_the_patch_script` — mocks only `jxa.run_json` (not `patch.apply`), so both the real `scaffold.build` and the real `patch.apply` run; captures both emitted scripts and asserts the second (patch) script contains `var documentId = "doc-abc";` and `app.documents.byId(documentId)`, sourced from the first (create) call's mocked `"id": "doc-abc"`.
- `tests/test_scaffold.py::test_template_as_a_directory_bundle_is_copied_with_copytree` — builds a real directory template with a nested `Index/Document.iwa` file, asserts the output is a directory with the same nested file byte-for-byte, and the template is untouched.
- `tests/test_scaffold.py::test_front_document_path_guards_against_no_open_presentation` — asserts `"No presentation is open."` is in `FRONT_DOCUMENT` and that the length guard textually precedes the `var doc = app.documents[0];` assignment.
- `tests/test_patch.py::test_script_contains_the_byid_branch` — asserts `patch.SCRIPT` (the static constant) itself contains `"app.documents.byId(documentId)"` and `"No open document with id "`.
- `tests/test_patch.py::test_without_a_document_id_the_front_document_is_targeted` — `patch.apply(spec)` (no `document`) still emits `var documentId = null;` and reaches `doc = app.documents[0];` — i.e. `slides patch` alone is unchanged.
- `tests/test_patch.py::test_a_document_id_selects_that_document_by_id` — `patch.apply(spec, document="doc-123")` emits `var documentId = "doc-123";`.

All pre-existing tests in `test_patch.py` (`test_writes_the_spec_to_a_file_and_reports`, `test_accepts_every_documented_field`, `test_removes_the_temp_file_after_returning`, `test_from_dump_round_trips_a_real_dump`, etc.) needed **no changes** — they all call `patch.apply(spec)` without `document`, which is exactly the unchanged, backward-compatible default path.

## Style / lint check

`ruff check src/slides/keynote/scaffold.py src/slides/keynote/patch.py` -> `All checks passed!`. Double-quoted strings only, C-style `%` formatting, one-parameter-per-line signatures (`_document_statement`, `apply`), no new `try/except`, import order unchanged.

## Files changed this round

- `src/slides/keynote/patch.py` — `SCRIPT` gains the `documentId`/`byId` branch; `apply()` gains `document: str | None = None`.
- `src/slides/keynote/scaffold.py` — `SCRIPT_CREATE` reports `id: doc.id()` and takes a full doc-statement placeholder instead of a bare expression; `FRONT_DOCUMENT` gains the "no presentation open" guard; `_document_expression` renamed `_document_statement` and branches `copytree`/`copyfile` on `source.is_dir()`; `build()` threads `document=result["id"]` into `patch.apply`.
- `tests/test_patch.py` — 3 new tests (byId branch, front-document-still-default, document-id-selects-by-id).
- `tests/test_scaffold.py` — all `SCRIPT_CREATE`-shaped fakes gained `"id"`, all mocked `patch.apply` lambdas gained `document=None`, plus 3 new tests (id-flows-through, directory-bundle template, front-document guard).

No changes needed to `src/slides/cli.py` or `src/slides/commands/scaffold.py` this round — the fix is entirely internal plumbing between `scaffold.build` and `patch.apply`.

## Concerns

- None of the three fixes required touching `commands/patch.py` or exposing `document` on the CLI's `slides patch` — it's scaffold-internal wiring, matching the ruling's scope exactly.
- `exists()`/`byId()` correctness rests on Keynote's sdef declaring `document.id` as a `scriptingIdentifier` property (the reviewer already confirmed this from the sdef) and on `exists` being a Standard-Suite command Keynote supports on object specifiers generally — both are well-established JXA/AppleScript conventions but, like every other JXA behavior in this codebase, only truly verified by the controller's real-app check below.
- No `NEEDS_CONTEXT`: no conflict found between these three rulings and the merged codebase.

## Updated live-check commands

Commands 1 and 2 from the original submission are unchanged and still valid (template-copy safety, and firstIndex re-keying against a front document with existing slides). Command 2 is now extended to also exercise the document-identity fix, per the coordinator's request — a second, unrelated deck stays open throughout and must remain completely untouched:

**1) With `--template` (never touches the source `.key`) — unchanged from the original submission:**

```bash
rm -f /tmp/scaffold-template-out.key
cat > /tmp/scaffold-template.json <<'EOF'
{
  "1": {"title": "First", "body": ["One point"], "notes": "Open here."},
  "2": {"title": "Second", "body": ["Another point"]}
}
EOF
PYTHONPATH=src python -m slides.cli scaffold /tmp/scaffold-template.json \
  --template ~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/09_oct14_tfidf_imbalance_eval.key \
  -o /tmp/scaffold-template-out.key
```
Expect: as before, plus — try this once against a **directory-bundle** `.key` if one is available on this machine (`file` a candidate `.key` to check; a bundle shows as a directory, not a Zip archive) to exercise the new `copytree` branch; if none is at hand, `ditto -k --sequesterRsrc --keepParent <the .key above> /tmp/scaffold-bundle-template.key` first converts a zip-form `.key` into a directory bundle for this purpose.

**2) Front document with existing slides, PLUS a second open deck to confirm document-identity targeting:**

```bash
cp ~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/09_oct14_tfidf_imbalance_eval.key /tmp/scaffold-deck-a.key
cp ~/Desktop/Git/Class/introml/slides/drafts/early_term_2026/keynote/09_oct14_tfidf_imbalance_eval.key /tmp/scaffold-deck-b.key
open /tmp/scaffold-deck-b.key   # open the "other" deck first...
open /tmp/scaffold-deck-a.key   # ...then deck A, so deck A ends up frontmost
cat > /tmp/scaffold-front.json <<'EOF'
{
  "1": {"title": "New First", "body": ["Point"], "notes": "Appended."},
  "2": {"title": "New Second", "body": ["Another point"]}
}
EOF
PYTHONPATH=src python -m slides.cli scaffold /tmp/scaffold-front.json
```
Expect:
- `/tmp/scaffold-deck-a.key` (frontmost at the moment `scaffold` ran) gets exactly 2 new slides, "New First"/"New Second", appended **after** its existing slides — never overwriting slide 1/2 (ruling 1, `firstIndex`).
- `/tmp/scaffold-deck-b.key` — the second, non-frontmost deck — has **zero** new slides and an unchanged slide count. This is the direct confirmation that `SCRIPT_CREATE`'s `doc.id()` and `patch.apply`'s `byId` lookup keep the fill pinned to the exact document scaffold created into, not whichever document Keynote considers frontmost by the time the second `osascript` call runs — the scenario the Critical ruling exists to prevent. For an even stronger check, bring deck B frontmost (click its window) in the brief window between `scaffold`'s two internal `osascript` calls if you can manage the timing; if the fix works, deck A still receives the fill regardless.
- Both throwaway copies live under `/tmp`, so the real teaching deck under `~/Desktop/Git/Class/...` is never opened directly by either command.
