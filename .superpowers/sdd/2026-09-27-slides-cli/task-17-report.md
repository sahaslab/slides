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
