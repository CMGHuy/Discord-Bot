# Task-implementer token diet — node tooling

**Spec:** [Task-implementer token diet](../specs/2026-10-29-v199-task-implementer-token-diet.md)
**Index:** [Goal, constraints, parallelisation and task ledger](2026-10-29-v199-task-implementer-token-diet_0-index.md)

Follow the index's Global Constraints, Review Focus and cross-task contracts. This part is Chain A: three disjoint node-tooling tasks that may run in either order. `<wt>` is the plan's worktree; every command uses absolute paths or `git -C <wt>`, never `cd`. No task here needs the database, the network or production, except the optional `browse.mjs` smoke in V199-2.

`frontend/node_modules` may be absent from a fresh worktree. The pure `node --test` files below never import from it; the two smoke steps that do need it say so and are skipped with a `NOTES` line when it is missing (never run `npm ci` inside a task).

# Phase 1 — node tests and UI tooling

### Task V199-1: Run frontend node tests under the tooling suite
**Model:** haiku — one new test file wrapping an existing command, no production code.

**Files:**
- Create: `tests/scripts/test_node_scripts.py`

**Interfaces:**
- Consumes: nothing from other tasks. Discovers `frontend/scripts/*.test.mjs` by glob, so `browse-lib.test.mjs` (V199-2) and `ng-test-lib.test.mjs` (V199-3) join automatically whenever they land.
- Produces: `node_test_files(scripts_dir: Path = SCRIPTS) -> list[Path]` — sorted `*.test.mjs` files directly in `scripts_dir`; `run_node_test(test_file: Path) -> subprocess.CompletedProcess[str]` — `node --test <file>` with `cwd=ROOT`. Every node test file passes or the `tooling` suite fails; with no `node` on `PATH` the run tests skip with a reason. This brings the existing `frontend/scripts/layout-audit-lib.test.mjs` (35 passing at authoring, controller-confirmed) under CI: the `backend-test (tooling)` job on `ubuntu-latest` has the runner's preinstalled Node, and `node:test` needs no `node_modules`.

`tests/scripts/` is already in suite `tooling` (`tests/suites.toml:69-71`); no `suites.toml` change.

- [ ] **Step 1: Confirm the existing node tests are green before CI depends on them**

Run: `node --test <wt>/frontend/scripts/layout-audit-lib.test.mjs`
Expected: the summary ends with `# pass 35` and `# fail 0`. If anything fails, stop and return `BLOCKED:` naming the failing test — fixing `layout-audit-lib` is outside this task.

- [ ] **Step 2: Write the wrapper test file**

Create `tests/scripts/test_node_scripts.py`:

```python
"""Run the frontend's pure node tests (frontend/scripts/*.test.mjs) under pytest.

`node --test` files had no runner in CI; this wrapper puts them in the
`tooling` suite. They import only node built-ins and sibling `*-lib.mjs`
files, never `node_modules`, so they need Node and nothing else.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "frontend" / "scripts"
NODE = shutil.which("node")
NO_NODE = "node is not on PATH; frontend/scripts/*.test.mjs need Node 20+"


def node_test_files(scripts_dir: Path = SCRIPTS) -> list[Path]:
    """Every `*.test.mjs` directly in `scripts_dir`, sorted by name."""
    return sorted(scripts_dir.glob("*.test.mjs"))


def run_node_test(test_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NODE, "--test", str(test_file)], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )


def test_node_test_files_finds_layout_audit_lib():
    assert SCRIPTS / "layout-audit-lib.test.mjs" in node_test_files()


def test_node_test_files_is_empty_for_a_dir_without_tests(tmp_path):
    (tmp_path / "browse.mjs").write_text("", encoding="utf-8")
    assert node_test_files(tmp_path) == []


def test_node_test_files_keeps_only_test_mjs_sorted(tmp_path):
    for name in ("b.test.mjs", "a.test.mjs", "lib.mjs", "c.test.js"):
        (tmp_path / name).write_text("", encoding="utf-8")
    assert node_test_files(tmp_path) == [tmp_path / "a.test.mjs", tmp_path / "b.test.mjs"]


@pytest.mark.skipif(NODE is None, reason=NO_NODE)
def test_run_node_test_reports_a_failing_file(tmp_path):
    failing = tmp_path / "fails.test.mjs"
    failing.write_text(
        "import { test } from 'node:test';\n"
        "import { strict as assert } from 'node:assert';\n"
        "test('always fails', () => assert.equal(1, 2));\n",
        encoding="utf-8",
    )
    assert run_node_test(failing).returncode != 0


@pytest.mark.skipif(NODE is None, reason=NO_NODE)
@pytest.mark.parametrize("test_file", node_test_files(), ids=lambda p: p.name)
def test_node_test_file_passes(test_file):
    result = run_node_test(test_file)
    assert result.returncode == 0, (
        f"node --test {test_file.name} failed:\n"
        f"{result.stdout[-4000:]}\n{result.stderr[-2000:]}"
    )
```

- [ ] **Step 3: Run it**

Run: `python <wt>/scripts/dev/testrun.py file tests/scripts/test_node_scripts.py`
Expected: `0 failed`, with `test_node_test_file_passes[layout-audit-lib.test.mjs]` passing (plus `[browse-lib.test.mjs]` / `[ng-test-lib.test.mjs]` if V199-2 / V199-3 are already committed in this worktree). `test_run_node_test_reports_a_failing_file` passes, which shows a red node file would turn the suite red.

- [ ] **Step 4: Complexity**

Run: `git -C <wt> add tests/scripts/test_node_scripts.py`, then `python -m radon cc -s -n C <wt>/tests/scripts/test_node_scripts.py` and `python <wt>/scripts/dev/complexity_gate.py`
Expected: radon prints nothing; the gate exits 0.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add tests/scripts/test_node_scripts.py
git -C <wt> commit -m "test(v199): run frontend node tests under the tooling suite" -m "<attribution line passed by the controller>"
```

### Task V199-2: Element-clipped screenshots in `browse.mjs shots --clip`
**Model:** sonnet — moves a parser into a new lib and wires a Playwright option; no browser in the unit tests.

**Files:**
- Create: `frontend/scripts/browse-lib.mjs`
- Create: `frontend/scripts/browse-lib.test.mjs`
- Modify: `frontend/scripts/browse.mjs` (usage comment L1-26, `parseArgs` L37-52 removed, `shots` L129-166)

**Interfaces:**
- Consumes: nothing from other tasks. V199-1's wrapper picks up `browse-lib.test.mjs` by glob.
- Produces (V199-12 documents the CLI):
  - `export const CLIP_MARGIN_PX = 8;`
  - `export function clipBox(box, page, margin = CLIP_MARGIN_PX)` — `box` is Playwright's `{x, y, width, height}` or `null`/`undefined`; `page` is `{width, height}` (the grown viewport). Returns a whole-pixel `{x, y, width, height}` or `null`.
  - `export function parseArgs(argv)` — moved verbatim from `browse.mjs`, plus `clip: null` in the defaults and `--clip <css selector>`.
  - CLI: `node frontend/scripts/browse.mjs shots --out <dir> --path <p> [--clip <sel>]`. With `--clip`, each `<slug>@<width>.png` is only the first visible match's box plus the margin. No visible match exits 1 with an error naming the selector and the path; it never falls back to a full page. Without `--clip`, `page.screenshot` gets exactly today's options.

Why a lib: `browse.mjs` launches Chromium and signs in at top level (L175-184), so a test cannot import it. Pure logic lives in `browse-lib.mjs`, which imports nothing (it needs no built-ins either), in the `layout-audit-lib.mjs` style (`export const` / `export function`).

- [ ] **Step 1: Write the failing tests**

Create `frontend/scripts/browse-lib.test.mjs`:

```js
// node --test frontend/scripts/browse-lib.test.mjs
import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { CLIP_MARGIN_PX, clipBox, parseArgs } from './browse-lib.mjs';

const PAGE = { width: 1440, height: 2000 };

test('CLIP_MARGIN_PX is 8', () => {
  assert.equal(CLIP_MARGIN_PX, 8);
});

test('clipBox pads the box by the margin on every side', () => {
  assert.deepEqual(clipBox({ x: 100, y: 200, width: 300, height: 50 }, PAGE),
    { x: 92, y: 192, width: 316, height: 66 });
});

test('clipBox honours an explicit margin', () => {
  assert.deepEqual(clipBox({ x: 100, y: 200, width: 300, height: 50 }, PAGE, 0),
    { x: 100, y: 200, width: 300, height: 50 });
});

test('clipBox clamps to the page at the top-left', () => {
  assert.deepEqual(clipBox({ x: 3, y: 0, width: 50, height: 20 }, PAGE),
    { x: 0, y: 0, width: 61, height: 28 });
});

test('clipBox clamps to the page at the bottom-right', () => {
  assert.deepEqual(clipBox({ x: 1400, y: 1980, width: 40, height: 20 }, PAGE),
    { x: 1392, y: 1972, width: 48, height: 28 });
});

test('clipBox rounds outward to whole pixels', () => {
  assert.deepEqual(clipBox({ x: 10.4, y: 20.6, width: 5.2, height: 5.2 }, PAGE, 0),
    { x: 10, y: 20, width: 6, height: 6 });
});

test('clipBox keeps an element taller than the viewport whole', () => {
  assert.deepEqual(clipBox({ x: 0, y: 100, width: 1440, height: 5000 }, { width: 1440, height: 6000 }),
    { x: 0, y: 92, width: 1440, height: 5016 });
});

test('clipBox returns null for a missing or zero-size box', () => {
  assert.equal(clipBox(null, PAGE), null);
  assert.equal(clipBox(undefined, PAGE), null);
  assert.equal(clipBox({ x: 10, y: 10, width: 0, height: 40 }, PAGE), null);
  assert.equal(clipBox({ x: 10, y: 10, width: 40, height: 0 }, PAGE), null);
});

test('clipBox returns null for a box entirely outside the page', () => {
  assert.equal(clipBox({ x: 2000, y: 10, width: 10, height: 10 }, PAGE), null);
  assert.equal(clipBox({ x: 10, y: 2100, width: 10, height: 10 }, PAGE), null);
});

test('parseArgs keeps the old defaults and adds clip: null', () => {
  assert.deepEqual(parseArgs(['shots']), {
    cmd: 'shots', paths: [], widths: [1440, 1024, 768, 390], base: 'https://bomeo-capital.com',
    out: null, clicks: [], settle: 1500, clip: null,
  });
  assert.equal(parseArgs([]).cmd, 'login');
});

test('parseArgs keeps the existing flags', () => {
  const opts = parseArgs(['shots', '--path', 'trades/x', '--path', '/risk', '--widths', '768,390',
    '--base', 'http://localhost:1234/', '--out', 'shots', '--click', '.a', '--click', '.b', '--settle', '300']);
  assert.deepEqual(opts.paths, ['/trades/x', '/risk']);
  assert.deepEqual(opts.widths, [768, 390]);
  assert.equal(opts.base, 'http://localhost:1234');
  assert.equal(opts.out, 'shots');
  assert.deepEqual(opts.clicks, ['.a', '.b']);
  assert.equal(opts.settle, 300);
});

test('parseArgs stores the --clip selector', () => {
  assert.equal(parseArgs(['shots', '--path', 'risk', '--clip', '.risk-card']).clip, '.risk-card');
});

test('parseArgs rejects --clip without a selector', () => {
  assert.throws(() => parseArgs(['shots', '--clip']), /--clip needs a CSS selector/);
});

test('parseArgs still rejects an unknown flag', () => {
  assert.throws(() => parseArgs(['shots', '--nope', 'x']), /unknown flag --nope/);
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `node --test <wt>/frontend/scripts/browse-lib.test.mjs`
Expected: FAIL — `Cannot find module` for `./browse-lib.mjs`.

- [ ] **Step 3: Implement `frontend/scripts/browse-lib.mjs`**

A short header comment (pure helpers for `browse.mjs`; tested by `browse-lib.test.mjs`), then:

- `parseArgs(argv)` — the body of `browse.mjs:37-52` moved unchanged (keep its Git Bash leading-slash comment), with `clip: null` added to the defaults and one branch: `else if (flag === '--clip') { if (!value) throw new Error('--clip needs a CSS selector'); opts.clip = value; }`. A repeated `--clip` keeps the last one.
- `clipBox(box, page, margin = CLIP_MARGIN_PX)` — the algorithm the tests pin (pad, round outward, clamp, reject empty):

```js
export function clipBox(box, page, margin = CLIP_MARGIN_PX) {
  if (!box || box.width <= 0 || box.height <= 0) return null;
  const x = Math.max(0, Math.floor(box.x - margin));
  const y = Math.max(0, Math.floor(box.y - margin));
  const right = Math.min(page.width, Math.ceil(box.x + box.width + margin));
  const bottom = Math.min(page.height, Math.ceil(box.y + box.height + margin));
  if (right <= x || bottom <= y) return null;
  return { x, y, width: right - x, height: bottom - y };
}
```

- [ ] **Step 4: Run the lib tests to see them pass**

Run: `node --test <wt>/frontend/scripts/browse-lib.test.mjs`
Expected: `# pass 14`, `# fail 0`.

- [ ] **Step 5: Wire `--clip` into `browse.mjs`**

In `frontend/scripts/browse.mjs`:

1. Add `import { clipBox, parseArgs } from './browse-lib.mjs';` beside the other imports and delete the local `parseArgs` (L37-52). The call at L175 is unchanged.
2. Add, after `clickFirst`, a helper that turns the selector into a clip or fails:

```js
/** --clip: the first match's box, measured after the viewport grow. No
 *  visible match is fatal -- a full-page fallback would hide the miss. */
async function clipRegion(page, selector, path, viewport) {
  const target = page.locator(selector).first();
  await target.waitFor({ timeout: 10_000 }).catch(() => {}); // late data, as in clickFirst
  const box = (await target.count()) === 0 ? null : await target.boundingBox();
  const clip = clipBox(box, viewport);
  if (!clip) throw new Error(`--clip matched no visible element on ${path}: ${selector}`);
  return clip;
}
```

3. In `shots`, keep the grown viewport in a variable and spread the clip in only when asked, so a run without `--clip` calls `page.screenshot` with exactly today's options:

```js
      const grown = { width, height: Math.min(Math.ceil(tallest) + 40, 8000) };
      await page.setViewportSize(grown);
      await page.waitForTimeout(500);
      const clip = opts.clip ? { clip: await clipRegion(page, opts.clip, path, grown) } : {};
      await page.screenshot({ path: `${name}.png`, fullPage: true, ...clip });
```

The thrown error propagates out of the top-level `try`; the `finally` closes the browser and Node exits 1 printing the message. The `.txt` file and its `page-scroll-x` line are unchanged.

4. Usage comment: add `[--clip <css selector>]` to the `shots` line, and a paragraph after the `--click` one: "--clip captures only the FIRST match's bounding box plus 8 px (`CLIP_MARGIN_PX`), clamped to the page, measured after the viewport grows to the tallest scroller, so an element taller than the viewport is captured whole. No visible match (missing, hidden, zero size) exits 1 naming the selector; it never falls back to a full page. UI tasks read clipped shots only (`docs/claude/ui-design.md`)."

- [ ] **Step 6: Check syntax and the wrapper**

Run: `node --check <wt>/frontend/scripts/browse.mjs` and `node --test <wt>/frontend/scripts/browse-lib.test.mjs`
Expected: `--check` prints nothing and exits 0; the lib tests still `# fail 0`.
If `<wt>/tests/scripts/test_node_scripts.py` exists (V199-1 committed), also run `python <wt>/scripts/dev/testrun.py file tests/scripts/test_node_scripts.py` — expected `0 failed`, including `[browse-lib.test.mjs]`.

- [ ] **Step 7: Smoke the CLI (only when `<wt>/frontend/node_modules/playwright` exists and `.env` holds the admin credentials)**

It drives production read-only through Playwright with the `.env` login, which the repo allows; it never prints the credentials. `<out>` is a fresh directory in your scratchpad.

Run: `node <wt>/frontend/scripts/browse.mjs shots --out <out> --path dashboard --widths 390 --clip main`
Expected: exit 0; `<out>/dashboard@390.png` exists.

Run: `node <wt>/frontend/scripts/browse.mjs shots --out <out> --path dashboard --widths 390 --clip "#v199-no-such-element"`
Expected: exit 1; stderr contains `--clip matched no visible element on /dashboard: #v199-no-such-element`.

If `node_modules` is absent, the credentials are missing, or the browser would wait for a manual sign-in, skip this step and say so in `NOTES` (the controller runs it after merge). Do not read the PNGs; the exit codes are the check.

- [ ] **Step 8: Commit**

```bash
git -C <wt> add frontend/scripts/browse-lib.mjs frontend/scripts/browse-lib.test.mjs frontend/scripts/browse.mjs
git -C <wt> commit -m "feat(v199): element-clipped screenshots in browse.mjs shots --clip" -m "<attribution line passed by the controller>"
```

### Task V199-3: Cwd-free Angular test wrapper `ng-test.mjs`
**Model:** sonnet — small new CLI plus pure lib; the only subtlety is cwd and exit-code passthrough.

**Files:**
- Create: `frontend/scripts/ng-test-lib.mjs`
- Create: `frontend/scripts/ng-test-lib.test.mjs`
- Create: `frontend/scripts/ng-test.mjs`

**Interfaces:**
- Consumes: nothing from other tasks. V199-1's wrapper picks up `ng-test-lib.test.mjs` by glob.
- Produces:
  - `export function parseNgTestArgs(argv) -> { frontend: string, includes: string[] }` — `argv` is `process.argv.slice(2)`: exactly one positional (the frontend directory, returned `path.resolve`d) and any number of `--include <spec>` pairs, in order.
  - `export function ngTestInvocation(opts, execPath) -> { command, args, cwd }` — `command = execPath`; `args = [<frontend>/node_modules/@angular/cli/bin/ng.js, 'test', '--watch=false', then '--include', <spec> per include]`; `cwd = opts.frontend`.
  - CLI: `node <wt>/frontend/scripts/ng-test.mjs <wt>/frontend [--include <spec>]...` runs the Angular CLI with `cwd=<frontend>` and exits with its status. A usage error or a missing `ng.js` exits 2 with a one-line message.
  - V199-6 pins `NG_TEST_WRAPPER = "frontend/scripts/ng-test.mjs"` and asserts the file exists; the path must be exactly this.

Why: the implementer may not `cd` (repo hook), and `npx ng test` needs the frontend as cwd. Today the only cwd-free form is buried in `frontend/scripts/check-compact-interactions.mjs:11-21`, which spawns `process.execPath` on `<frontend>/node_modules/@angular/cli/bin/ng.js` with `cwd: frontend`. This task makes that pattern a general CLI. The flaky 60 s `START_TIMEOUT` under load (`docs/claude/testing-cost.md:238-246`) is unchanged; a re-run fixes it.

- [ ] **Step 1: Write the failing tests**

Create `frontend/scripts/ng-test-lib.test.mjs`. The last two tests drive the real CLI against a stub `ng.js` in a temp directory, so they need no Angular install:

```js
// node --test frontend/scripts/ng-test-lib.test.mjs
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { ngTestInvocation, parseNgTestArgs } from './ng-test-lib.mjs';

const CLI = join(dirname(fileURLToPath(import.meta.url)), 'ng-test.mjs');
const NG_JS = ['node_modules', '@angular', 'cli', 'bin', 'ng.js'];

test('parseNgTestArgs resolves the frontend dir and starts with no includes', () => {
  assert.deepEqual(parseNgTestArgs(['some/frontend']), { frontend: resolve('some/frontend'), includes: [] });
});

test('parseNgTestArgs keeps --include specs in order', () => {
  const opts = parseNgTestArgs(['fe', '--include', 'src/a.spec.ts', '--include', 'src/b.spec.ts']);
  assert.deepEqual(opts.includes, ['src/a.spec.ts', 'src/b.spec.ts']);
});

test('parseNgTestArgs accepts --include before the frontend dir', () => {
  assert.deepEqual(parseNgTestArgs(['--include', 'src/a.spec.ts', 'fe']),
    { frontend: resolve('fe'), includes: ['src/a.spec.ts'] });
});

test('parseNgTestArgs requires the frontend dir', () => {
  assert.throws(() => parseNgTestArgs([]), /usage: node frontend\/scripts\/ng-test\.mjs <frontend dir>/);
  assert.throws(() => parseNgTestArgs(['--include', 'src/a.spec.ts']), /usage:/);
});

test('parseNgTestArgs rejects --include without a spec', () => {
  assert.throws(() => parseNgTestArgs(['fe', '--include']), /--include needs a spec path/);
});

test('parseNgTestArgs rejects an unknown flag and a second positional', () => {
  assert.throws(() => parseNgTestArgs(['fe', '--watch']), /unknown flag --watch/);
  assert.throws(() => parseNgTestArgs(['fe', 'other']), /unexpected argument other/);
});

test('ngTestInvocation runs ng.js test once, from the frontend dir', () => {
  const fe = resolve('fe');
  assert.deepEqual(ngTestInvocation({ frontend: fe, includes: [] }, '/opt/node'), {
    command: '/opt/node', args: [join(fe, ...NG_JS), 'test', '--watch=false'], cwd: fe,
  });
});

test('ngTestInvocation appends one --include pair per spec', () => {
  const fe = resolve('fe');
  const { args } = ngTestInvocation({ frontend: fe, includes: ['src/a.spec.ts', 'src/b.spec.ts'] }, 'node');
  assert.deepEqual(args.slice(1), ['test', '--watch=false', '--include', 'src/a.spec.ts', '--include', 'src/b.spec.ts']);
});

test('ng-test.mjs runs ng.js in the frontend dir and passes its exit code through', () => {
  const fe = mkdtempSync(join(tmpdir(), 'v199-ng-'));
  try {
    mkdirSync(join(fe, ...NG_JS.slice(0, -1)), { recursive: true });
    writeFileSync(join(fe, ...NG_JS),
      'process.stdout.write(JSON.stringify({ cwd: process.cwd(), argv: process.argv.slice(2) }));\nprocess.exit(7);\n');
    const run = spawnSync(process.execPath, [CLI, fe, '--include', 'src/a.spec.ts'], { encoding: 'utf8' });
    assert.equal(run.status, 7);
    const seen = JSON.parse(run.stdout);
    assert.equal(realpathSync(seen.cwd), realpathSync(fe));
    assert.deepEqual(seen.argv, ['test', '--watch=false', '--include', 'src/a.spec.ts']);
  } finally {
    rmSync(fe, { recursive: true, force: true });
  }
});

test('ng-test.mjs exits 2 naming the missing Angular CLI', () => {
  const fe = mkdtempSync(join(tmpdir(), 'v199-ng-'));
  try {
    const run = spawnSync(process.execPath, [CLI, fe], { encoding: 'utf8' });
    assert.equal(run.status, 2);
    assert.match(run.stderr, /no Angular CLI at .*ng\.js -- run npm ci in /);
  } finally {
    rmSync(fe, { recursive: true, force: true });
  }
});

test('ng-test.mjs exits 2 with the usage line when the frontend dir is missing', () => {
  const run = spawnSync(process.execPath, [CLI], { encoding: 'utf8' });
  assert.equal(run.status, 2);
  assert.match(run.stderr, /usage: node frontend\/scripts\/ng-test\.mjs <frontend dir>/);
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `node --test <wt>/frontend/scripts/ng-test-lib.test.mjs`
Expected: FAIL — `Cannot find module` for `./ng-test-lib.mjs`.

- [ ] **Step 3: Implement `frontend/scripts/ng-test-lib.mjs`**

Imports `join` and `resolve` from `node:path` only. Export `USAGE = 'usage: node frontend/scripts/ng-test.mjs <frontend dir> [--include <spec>]...'` and throw `new Error(USAGE)` when no positional was given.

- `parseNgTestArgs(argv)`: walk `argv` with an index; `--include` consumes the next value (`--include needs a spec path` when it is missing or starts with `--`); any other `--` token throws `unknown flag <token>`; the first bare token is the frontend dir, a second throws `unexpected argument <token>`. Return `{ frontend: resolve(dir), includes }`.
- `ngTestInvocation(opts, execPath)`: build the shape in Interfaces with `join(opts.frontend, 'node_modules', '@angular', 'cli', 'bin', 'ng.js')` and `opts.includes.flatMap((spec) => ['--include', spec])`.

- [ ] **Step 4: Implement `frontend/scripts/ng-test.mjs`**

```js
#!/usr/bin/env node
/**
 * Run the Angular unit tests from ANY directory -- no `cd frontend` first,
 * which the repo hooks forbid for agents:
 *
 *   node <wt>/frontend/scripts/ng-test.mjs <wt>/frontend [--include <spec>]...
 *
 * Spawns <frontend>/node_modules/@angular/cli/bin/ng.js test --watch=false
 * with cwd=<frontend> and exits with its status (2 for a usage error or a
 * missing Angular CLI). Same spawn as check-compact-interactions.mjs.
 */
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { ngTestInvocation, parseNgTestArgs } from './ng-test-lib.mjs';

let opts;
try {
  opts = parseNgTestArgs(process.argv.slice(2));
} catch (err) {
  console.error(err.message);
  process.exit(2);
}
const { command, args, cwd } = ngTestInvocation(opts, process.execPath);
if (!existsSync(args[0])) {
  console.error(`no Angular CLI at ${args[0]} -- run npm ci in ${cwd}`);
  process.exit(2);
}
const result = spawnSync(command, args, { cwd, stdio: 'inherit' });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `node --test <wt>/frontend/scripts/ng-test-lib.test.mjs`
Expected: `# pass 11`, `# fail 0`.
If `<wt>/tests/scripts/test_node_scripts.py` exists (V199-1 committed), also run `python <wt>/scripts/dev/testrun.py file tests/scripts/test_node_scripts.py` — expected `0 failed`, including `[ng-test-lib.test.mjs]`.

- [ ] **Step 6: Smoke against the real Angular CLI (only when `<wt>/frontend/node_modules/@angular/cli/bin/ng.js` exists)**

Run from the session's normal working directory (not the frontend): `node <wt>/frontend/scripts/ng-test.mjs <wt>/frontend --include src/app/ui/data-table/data-table.spec.ts`
Expected: Karma reports the data-table specs with `0 FAILED` and the command exits 0. A `START_TIMEOUT` under load is re-run once. If `node_modules` is absent, skip and say so in `NOTES`; the stub-CLI tests in Step 1 already pin cwd, arguments and exit code.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add frontend/scripts/ng-test-lib.mjs frontend/scripts/ng-test-lib.test.mjs frontend/scripts/ng-test.mjs
git -C <wt> commit -m "feat(v199): cwd-free Angular test wrapper ng-test.mjs" -m "<attribution line passed by the controller>"
```

