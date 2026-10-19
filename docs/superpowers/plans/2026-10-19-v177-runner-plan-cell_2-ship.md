# v177 — Plan cell for trailing runners and closed partial trades, part 2: browser check, full suite, merge, deploy, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V177-5:" -A 260 docs/superpowers/plans/2026-10-19-v177-runner-plan-cell_2-ship.md`.

**Spec:** [`2026-10-19-v177-runner-plan-cell-design.md`](../specs/2026-10-19-v177-runner-plan-cell-design.md) (§ Layout, § Testing, `**Panel:**` line, § Panel review)
**Index:** [`2026-10-19-v177-runner-plan-cell_0-index.md`](2026-10-19-v177-runner-plan-cell_0-index.md) — Global Constraints, § Backend contract, § PlanCell contract, § Gate contract, Parallelisation and the Task ledger live there and bind every task below.

Names used in every task:

- `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree, branch `main`).
- `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell` (created by V177-1), branch `2026-10-19-v177-runner-plan-cell`.
- `$SCRATCH` = the implementing session's scratchpad (an absolute path). Commit messages are written there and passed with `git commit -F`; the check script, its screenshots and the VM script live there; nothing in it is committed.

Never `cd` in Bash: `git -C <tree>`, `npm --prefix <dir>`, absolute paths. Frontend commands that must run from `frontend/` run in PowerShell between `Push-Location <tree>/frontend` and `Pop-Location`. Production is reached only through `bash $R/scripts/ops/ssh-hetzner.sh "<cmd>"`, read-only; any live fix made there is mirrored into this repo and committed before its task counts as done (`mirror-prod` skill). `ADMIN_USERNAME`/`ADMIN_PASSWORD` are read only inside a Node process (`process.loadEnvFile`), never printed, echoed, grepped, passed on a command line or written to another file.

# Phase B: Ship (V177-4..V177-7)

### Task V177-4: Three-width browser check (PARTIAL tab, Closed tab, Trades page)

**Model:** sonnet — runs the app and judges layout at three widths; a layout fix is a small style edit.

**Files:**
- Create (session scratchpad only, never the repo): `$SCRATCH/v177-admin-replica.py` (admin launcher pointed at the replica), `$SCRATCH/v177-widths.cjs` (Playwright check), `$SCRATCH/v177-shots/` (screenshots and the measurement JSON)
- Modify, only on a layout defect found here: `frontend/src/app/ui/plan-cell.ts` (styles only) and `frontend/src/app/ui/plan-cell.spec.ts` (a regression case for the defect), on the branch in `$WT`

**Interfaces:**
- Consumes: V177-1's wire fields on every trades row (`tp1`, `best_pnl_pct`, `stop_pnl_pct`, `runner_exit_price`, `runner_exit_reason`; index § Backend contract); V177-2's DOM (`sb-plan-cell` → `<span class="plan runner">` with children `.line.l1`, `.line.l2` (line 2 starting with `<span class="trail">Trail</span>`), each with its own `title`; closed-runner mode keeps the single `.plan` root whose `title` contains `Runner exit (`; index § PlanCell contract); V177-3's wiring of that cell on the Dashboard positions table (tabs `[role="tab"]` labelled `Partial <n>` / `Closed <n>`, from `POSITION_TABS` in `positions-table.ts`) and on the Trades page (`/app/trades?status=open`, `/app/trades?status=CLOSED`).
- Produces: the measurement verdict at 390/768/1440 for the three surfaces, recorded in the task report; V177-5 copies its one-line summary into the merge message. Or, if `.env` lacks the credentials, the partner's answer from Step 1 and what it decided.

This is the spec's § Testing browser check ("Browser check at 390/768/1440 on the PARTIAL tab, the Closed tab and the Trades page") and § Layout's per-line no-wrap rule. The local data is the production replica, so the real RKLB short (or whatever runner the book holds today) is what renders; nothing is seeded and nothing is stubbed.

- [ ] **Step 1: Check that `.env` carries the admin credentials (without reading them out)**

```bash
node -e "process.loadEnvFile('E:/Documents/Private/Projects/Discord-Bot/.env'); const ok = ['ADMIN_USERNAME', 'ADMIN_PASSWORD'].every((k) => Boolean(process.env[k])); console.log(ok ? 'credentials: present' : 'credentials: missing');"
```

The command prints one of two fixed strings and never a value. Do not `cat`, `grep`, `sed`, `type` or `Read` `.env`, and do not echo either variable to check it.

Expected: `credentials: present`. On `credentials: missing` (or a `loadEnvFile` error: `.env` absent), **stop here** and ask the partner with `AskUserQuestion`, one question, recommended option first:

> "`.env` has no `ADMIN_USERNAME`/`ADMIN_PASSWORD`, which the local three-width check of the v177 Plan cell signs in with (never `admin`/`admin`). How should I go on?"
> 1. "I'll add both to `.env` now — re-run the check when I say so" (recommended)
> 2. "Skip the local check; after the deploy, look at three widths on production with `browse.mjs`, where I sign in by hand in its window (V177-6 Step 5)"

Do not improvise around it: no default credentials, no manual sign-in in a headed window unless the partner chose answer 2 (and then only the partner types), no second `.env`, no copy of the values anywhere. On answer 1, wait for the partner's go-ahead and repeat this step. On answer 2, record "local browser check skipped (no credentials in `.env`; partner chose the production look)" in the task report, skip Steps 2-6, and end the task (V177-6 Step 5 becomes required).

- [ ] **Step 2: Sync the production replica**

Run the `replicate-prod-db` skill (`/replicate-prod-db`): CLAUDE.md requires it before a task's first database-backed run, and this check renders production's own runners from it.

Expected: a verdict line `replicate_prod_db: MATCH|DRIFT target=swingbot_prod_replica tables=… alembic=…`. `MISMATCH` or `FAIL`: stop, report the printed lines in full, and ask the partner (`AskUserQuestion`) whether to run the check on the working local database instead (fixture data: probably no runner row) or on production after the deploy. v177 adds no Alembic revision, so the replica's `alembic=` revision is the one this branch expects; if `python -m alembic heads` (run with `PYTHONPATH=$WT`) names a newer head, report it rather than migrating anything.

- [ ] **Step 3: Start the local admin on the replica, and the dev server**

The working local database holds fixture data; the admin must read `swingbot_prod_replica` instead. `swingbot/config.py` loads `.env` with `override=True`, so an environment variable cannot redirect it; the launcher sets `config.DATABASE_URL` in-process after `.env` has loaded, swapping only the database name (user, password, host and port stay what `.env` says, never printed). Create `$SCRATCH/v177-admin-replica.py`:

```python
"""v177 browser check: run the worktree's admin UI against the production replica.

The working local database holds fixture data; the check needs the production
book's real runners. swingbot.config loads .env with override=True, so the
redirect happens here, in-process, after .env has loaded. Only the database
name changes; the URL (which carries the password) is never printed.
"""
import runpy
import sys

WT = r"E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell"
REPLICA = "swingbot_prod_replica"

sys.path.insert(0, WT)

from sqlalchemy.engine import make_url  # noqa: E402

from swingbot import config  # noqa: E402

if not config.DATABASE_URL:
    sys.exit("v177 launcher: DATABASE_URL is not set in .env; stopping")
config.DATABASE_URL = make_url(config.DATABASE_URL).set(database=REPLICA).render_as_string(hide_password=False)
print(f"v177 launcher: admin UI on database {REPLICA}", flush=True)
sys.argv = [f"{WT}/admin_ui.py"]
runpy.run_path(f"{WT}/admin_ui.py", run_name="__main__")
```

Make sure the worktree's frontend has its dependencies (V177-2/V177-3 normally installed them):

```bash
test -d $WT/frontend/node_modules || npm --prefix $WT/frontend ci
```

Start both servers in the background (Bash `run_in_background: true`, one call each):

```bash
python $SCRATCH/v177-admin-replica.py
```

```bash
npm --prefix $WT/frontend exec -- ng serve --port 4123
```

`$WT` has no `.env` of its own and none is copied there: `config.py` tries `$WT/.env`, then `load_dotenv()` walks up to `$R/.env`, so the admin runs on `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD`. Read the admin's first output lines:

- `v177 launcher: admin UI on database swingbot_prod_replica` must be there.
- A line starting `SECURITY: the admin UI is using the DEFAULT credentials (admin/admin)` (`config.py:1611`) means `.env` did **not** load: stop both servers and report it; never run the check on the default credentials.
- A database connection error means the replica (or `swing-db`) is down: `make up`, re-run Step 2, restart the admin.

Wait until the dev server answers (port 4123, never 4200; its proxy forwards `/api` and `/static` to the admin on `:1234`):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:4123/app/
```

Expected: `200`.

- [ ] **Step 4: Write the check script**

Create `$SCRATCH/v177-widths.cjs`:

```js
// v177 three-width check of the runner Plan cell.
// Usage: node v177-widths.cjs <WT> <envFile> <outDir>
// Signs in with ADMIN_USERNAME/ADMIN_PASSWORD loaded from <envFile> into this
// process only -- never printed, logged or passed on a command line.
const { createRequire } = require('node:module');
const { mkdirSync, writeFileSync } = require('node:fs');
const [wt, envFile, out] = process.argv.slice(2);
const { chromium } = createRequire(`${wt}/frontend/package.json`)('playwright');
mkdirSync(out, { recursive: true });
process.loadEnvFile(envFile);
const BASE = 'http://localhost:4123';
const WIDTHS = [390, 768, 1440];

// Shapes from the index's PlanCell contract (whitespace-collapsed text).
const LINE1 = /^\S+ → \S+ \/ \S+ \(\d+(\.\d+)?% - \d+(\.\d+)?%\)$/;
const LINE2 = /^Trail \S+ → \S+ \([+-]\d+\.\d% \/ [+-]\d+\.\d%\)$/;
const RKLB_LINE1 = '60.67 → 58.33 / 61.85 (3.9% - 1.9%)';
const RKLB_LINE2 = 'Trail 49.94 → 52.44 (+17.7% / +13.6%)';

const SURFACES = [
  { name: 'dashboard-partial', path: '/app/dashboard', tab: 'Partial', expect: 'runner' },
  { name: 'dashboard-closed', path: '/app/dashboard', tab: 'Closed', allDays: true, expect: 'closed' },
  { name: 'trades-open', path: '/app/trades?status=open', expect: 'runner' },
  { name: 'trades-closed', path: '/app/trades?status=CLOSED', expect: 'closed' },
];

async function login(page) {
  await page.goto(`${BASE}/app/`, { waitUntil: 'domcontentloaded' });
  const ok = await page.evaluate(async (body) => {
    const res = await fetch('/api/v1/session', { method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return res.ok; // one attempt only: the login limiter counts failures
  }, { username: process.env.ADMIN_USERNAME, password: process.env.ADMIN_PASSWORD });
  if (!ok) throw new Error('sign-in refused (credentials not shown)');
}

// Which rows the API says should render a new form: tickers and prices only, no secrets.
async function apiCandidates(page) {
  return page.evaluate(async () => {
    const all = async (status) => {
      const rows = [];
      for (let p = 1; p < 50; p += 1) {
        const res = await fetch(`/api/v1/trades?status=${status}&per_page=100&page=${p}`, { credentials: 'include' });
        const body = await res.json();
        rows.push(...body.items);
        if (rows.length >= body.total || body.items.length === 0) break;
      }
      return rows;
    };
    const pick = (r) => ({ ticker: r.ticker, status: r.status, direction: r.direction, entry: r.entry,
      stop_loss: r.stop_loss, tp1: r.tp1, runner_best: r.runner_best, banked_exit_price: r.banked_exit_price,
      best_pnl_pct: r.best_pnl_pct, stop_pnl_pct: r.stop_pnl_pct, bar_kind: r.bar_kind,
      runner_exit_price: r.runner_exit_price, runner_exit_reason: r.runner_exit_reason, leg_index: r.leg_index });
    const partial = (await all('PARTIAL')).map(pick);
    const closed = (await all('CLOSED')).map(pick);
    return {
      runners: partial.filter((r) => r.tp1 != null),
      partialWithoutTp1: partial.filter((r) => r.tp1 == null).length,
      closedRunners: closed.filter((r) => r.runner_exit_price != null),
      closedTotal: closed.length,
    };
  });
}

async function measure(page) {
  return page.evaluate(() => {
    const doc = document.documentElement;
    const text = (el) => el.textContent.replace(/\s+/g, ' ').trim();
    const overflow = (el) => {
      const cell = el.closest('td, [role="cell"], [role="gridcell"]') ?? el.parentElement;
      return Math.round(el.getBoundingClientRect().right - cell.getBoundingClientRect().right);
    };
    const lines = [...document.querySelectorAll('sb-plan-cell .plan.runner .line')].map((el) => ({
      cls: el.classList.contains('l1') ? 'l1' : 'l2',
      text: text(el),
      title: el.getAttribute('title'),
      whiteSpace: getComputedStyle(el).whiteSpace,
      display: getComputedStyle(el).display,
      lineBoxes: el.getClientRects().length,
      height: Math.round(el.getBoundingClientRect().height),
      lineHeight: parseFloat(getComputedStyle(el).lineHeight) || null,
      overflowPx: overflow(el),
    }));
    const closedRunner = [...document.querySelectorAll('sb-plan-cell .plan:not(.runner)')]
      .filter((el) => (el.getAttribute('title') ?? '').includes('Runner exit ('))
      .map((el) => ({ text: text(el), title: el.getAttribute('title'), overflowPx: overflow(el),
        height: Math.round(el.getBoundingClientRect().height) }));
    const allCells = [...document.querySelectorAll('sb-plan-cell')].map(text);
    return {
      pageScrollX: doc.scrollWidth - doc.clientWidth,
      runnerLines: lines,
      closedRunner,
      cellCount: allCells.length,
      cellsSayingTp2: allCells.filter((t) => /\bTP2\b/.test(t)).length,
    };
  });
}

async function open(page, surface) {
  await page.goto(`${BASE}${surface.path}`, { waitUntil: 'networkidle' });
  if (surface.tab) {
    await page.locator('[role="tab"]', { hasText: surface.tab }).first().click();
    await page.waitForLoadState('networkidle');
  }
  if (surface.allDays) {
    const all = page.getByText('All days', { exact: true });
    if (await all.count()) {
      await all.first().click();
      await page.waitForLoadState('networkidle');
    }
  }
  await page.waitForTimeout(1200);
}

function problemsOf(surface, m) {
  const problems = [];
  if (m.pageScrollX > 0) problems.push(`page scrolls horizontally by ${m.pageScrollX}px`);
  if (m.cellsSayingTp2 > 0) problems.push(`${m.cellsSayingTp2} plan cell(s) print "TP2"`);
  for (const l of m.runnerLines) {
    if (l.whiteSpace !== 'nowrap') problems.push(`${l.cls} white-space is ${l.whiteSpace}`);
    if (l.display === 'inline') problems.push(`${l.cls} is inline, not its own block`);
    if (l.lineBoxes > 1 || (l.lineHeight && l.height > 1.5 * l.lineHeight)) problems.push(`${l.cls} wraps: "${l.text}"`);
    if (l.overflowPx > 0) problems.push(`${l.cls} overflows its cell by ${l.overflowPx}px: "${l.text}"`);
    if (!l.title) problems.push(`${l.cls} has no title`);
    if (l.cls === 'l1' && !LINE1.test(l.text)) problems.push(`line 1 shape: "${l.text}"`);
    if (l.cls === 'l2' && !LINE2.test(l.text)) problems.push(`line 2 shape: "${l.text}"`);
  }
  for (const c of m.closedRunner) if (c.overflowPx > 0) problems.push(`closed runner overflows by ${c.overflowPx}px: "${c.text}"`);
  if (surface.expect === 'closed' && m.runnerLines.length > 0) problems.push('two-line runner form on a CLOSED surface');
  return problems;
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await login(page);
  const report = { candidates: await apiCandidates(page), surfaces: [] };
  for (const surface of SURFACES) {
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await open(page, surface);
      const m = await measure(page);
      await page.screenshot({ path: `${out}/${surface.name}@${width}.png`, fullPage: true });
      const l1 = m.runnerLines.filter((l) => l.cls === 'l1').map((l) => l.text);
      const l2 = m.runnerLines.filter((l) => l.cls === 'l2').map((l) => l.text);
      report.surfaces.push({
        surface: surface.name, width, pageScrollX: m.pageScrollX, cells: m.cellCount, line1: l1, line2: l2,
        rklbLine1: l1.includes(RKLB_LINE1), rklbLine2: l2.includes(RKLB_LINE2),
        closedRunner: m.closedRunner.map((c) => c.text),
        titles: [...new Set(m.runnerLines.map((l) => l.title).concat(m.closedRunner.map((c) => c.title)))],
        problems: problemsOf(surface, m),
      });
    }
  }
  await browser.close();
  writeFileSync(`${out}/v177-widths.json`, JSON.stringify(report, null, 2));
  for (const s of report.surfaces) {
    console.log(`${s.surface}@${s.width}: scrollX=${s.pageScrollX} cells=${s.cells} l1=${s.line1.length} `
      + `l2=${s.line2.length} closedRunner=${s.closedRunner.length} `
      + `${s.problems.length ? 'PROBLEMS: ' + s.problems.join('; ') : 'ok'}`);
  }
  console.log(`api: runners=${report.candidates.runners.length} closedRunners=${report.candidates.closedRunners.length}`
    + ` (of ${report.candidates.closedTotal} closed rows)`);
})().catch((err) => { console.error(err.message); process.exit(1); });
```

- [ ] **Step 5: Run it and read the result**

```bash
node $SCRATCH/v177-widths.cjs "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell" "E:/Documents/Private/Projects/Discord-Bot/.env" "$SCRATCH/v177-shots"
```

(`playwright` resolves from `$WT/frontend/node_modules`; Chromium lives in `%LOCALAPPDATA%\ms-playwright` — run `npm --prefix $WT/frontend exec -- playwright install chromium` once if the launch says it is missing.)

Expected, on every one of the 12 `surface@width` lines:

- `scrollX=0` (no horizontal page scroll at 390, 768 and 1440; a wide table scrolls inside its own box, which does not move `scrollX`) and `ok` (no `PROBLEMS:`).
- `dashboard-partial` and `trades-open`: `l1` equals the number of runner rows on that page (`api: runners=` when they fit one page). `l2` equals `l1` unless a runner has no stop or best price, in which case that row shows line 1 only (§ Edge cases) — the JSON's `candidates.runners` entries show which.
- `dashboard-closed` and `trades-closed`: `l1=0 l2=0`; `closedRunner` counts the closed runner rows on the page (`api: closedRunners=`; the Dashboard's Closed tab shows only what its Today/All days scope and pager hold, so the Trades page is the authoritative count).

Then open `$SCRATCH/v177-shots/v177-widths.json` (Read tool) and check by value:

- If the RKLB short is still PARTIAL with the spec's numbers, `rklbLine1` and `rklbLine2` are `true` on both runner surfaces. If the book has moved on (RKLB closed, or a new best price), compare each runner's `line2` text with its `candidates.runners` entry instead: best price = `runner_best` (else `banked_exit_price`), exit price = `stop_loss`, percents = `best_pnl_pct`/`stop_pnl_pct` to one decimal with their sign. A closed RKLB shows in `closedRunner` as `60.67 → <exit> / 61.85 (<signed %> - 1.9%)`.
- Every `titles` entry is one of the index's § PlanCell contract tooltip strings with its numbers filled: line 1 starts `Original plan (TP1 already filled)`; line 2 starts `Trailing stop.` (or `Locked-in floor.`) and contains `(unrealised)`, `per share from the original entry, before costs and tax` and `your broker's resting orders are not synced`; a closed-runner title starts `Entry ` and contains `Runner exit (` followed by one of `runnerExitLabel`'s labels.

Open the screenshots with the Read tool — at least `dashboard-partial@390.png`, `dashboard-partial@1440.png`, `trades-closed@390.png` and `trades-closed@768.png` — and confirm by eye: the two runner lines stack in the Plan cell with no wrapping or clipping, the `Trail` label is muted, the row grew in height rather than the column in width, and the TP1-leg row of a still-PARTIAL plan on the Closed surfaces shows the one-line cell as before.

An empty result is a measured answer, not a pass: `api: runners=0` means the replica holds no trailing runner and the two-line form was not seen in a browser; `closedRunners=0` means the closed form was not seen. Say which in the task report; V177-6 Step 5 then looks at that form on production (which holds the same rows, so this only happens when the book has none at all — then say so).

- [ ] **Step 6: Fix a layout defect, if one showed (otherwise skip)**

A `PROBLEMS:` entry for a line that wraps, overflows its cell, or makes the page scroll is fixed in `$WT/frontend/src/app/ui/plan-cell.ts`'s `styles` only, inside the Global Constraints: each line its own block with `white-space: nowrap`; no margins for spacing (literal text inside `.sep`); colours only through `var(--pos)`/`var(--neg)`/`var(--text-faint)`/`var(--text-secondary)`; no `.pos`/`.neg`/`.muted` selectors; no colour literal; column widths and `inlineFrom` in `trades.columns.ts` unchanged. Add a case to `$WT/frontend/src/app/ui/plan-cell.spec.ts` pinning the corrected style, for example:

```ts
it('keeps each runner line a nowrap block (v177 browser check)', () => {
  const fixture = TestBed.createComponent(PlanCell);
  fixture.componentRef.setInput('entry', 60.67);
  fixture.componentRef.setInput('stop', 52.437);
  fixture.componentRef.setInput('planTp1', 58.33);
  fixture.componentRef.setInput('planStop', 61.85);
  fixture.componentRef.setInput('trailBest', 49.94);
  fixture.componentRef.setInput('trailBestPct', 17.69);
  fixture.componentRef.setInput('trailExitPct', 13.57);
  fixture.detectChanges();
  const lines = [...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('.plan.runner .line')];
  expect(lines).toHaveLength(2);
  for (const line of lines) {
    expect(getComputedStyle(line).whiteSpace).toBe('nowrap');
    expect(getComputedStyle(line).display).toBe('block');
  }
});
```

(match the spec file's existing setup — V177-2 added its runner cases there; reuse its fixture helper if it has one rather than repeating the inputs). A copy or number defect (wrong text, wrong tooltip, a `TP2`) is not a layout fix: report it, add the failing case to the spec of the file V177-2 or V177-3 owns, then fix that file.

Verify in PowerShell (never `cd` in Bash):

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npx ng test --watch=false --include src/app/ui/plan-cell.spec.ts
npm run lint
Pop-Location
```

Expected: the spec passes; lint reports nothing new (no new `eslint-suppressions.json` entry). Re-run Step 5: no `PROBLEMS:` entry. A 60 s "Timeout waiting for worker … no tests" from `ng test` is machine load: re-run the same command once (`testing-cost.md`).

- [ ] **Step 7: Stop the servers, commit a fix if there was one, record**

Stop the background admin and `ng serve` processes, so V177-5's full suite does not share the machine with them.

Nothing to commit when Step 5 passed first time: the scripts and screenshots stay in `$SCRATCH`. If Step 6 changed a file, write `$SCRATCH/v177-4-msg.txt`:

```text
fix(ui): plan cell runner lines stay on one line at <width> (v177 browser check)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $WT add frontend/src/app/ui/plan-cell.ts frontend/src/app/ui/plan-cell.spec.ts
git -C $WT commit -F "$SCRATCH/v177-4-msg.txt"
git -C $WT status --short
```

Record in the task report, for V177-5's merge message, one line: `Browser check (replica, 390/768/1440): <12/12 ok | n problems fixed in <sha>>; runners seen <n>, closed runners seen <n>; RKLB <verbatim | moved on, compared by value>` — or `Browser check: skipped, <reason>` from Step 1 or Step 2.

### Task V177-5: Full suite + frontend run, merge to `main`, ui patch + bot patch, version history

**Model:** sonnet — runs the gates and merges; judgement only on a failure or a merge conflict.

**Files:**
- Modify: `VERSION.json` (two release commits: `ui` patch, then `bot` patch)
- Modify: `swingbot/admin/version_history.json` (regenerated after each release commit by `scripts/dev/build_version_matrix.py`)
- Modify, only on a failure: the file that broke, as its own scoped commit on the branch

**Interfaces:**
- Consumes: every commit of V177-1..V177-4 on branch `2026-10-19-v177-runner-plan-cell`; V177-4's one-line browser-check summary from its task report.
- Produces: `main` carrying the merge commit and four release commits (`release(ui)`, `chore(ui)`, `release(bot)`, `chore(bot)`), **not pushed** (V177-6 asks the partner first; the push is the deploy). Both bumps are done here, resolved from `VERSION.json` on disk at merge time, so V177-7's `/close-out` skips its bump and regeneration steps.

This is the plan's one full suite and one full frontend run, both on the final branch code and both before the merge (Global Constraints; CLAUDE.md: no full suite after the merge). **The frontend gates matter here as much as the Python suite: the previous deploy was blocked in CI by a frontend gate** — `frontend/src/app/ui/primitives.spec.ts` failed on a raw `<button>` without `sb-button` — so `npm run lint`, the full `npx ng test --watch=false` and `npm run build` must all run green locally, from `frontend/` through PowerShell `Push-Location`, before the merge. CI's `frontend-test` job runs exactly these three commands (`.github/workflows/deploy.yml`), and a red one there blocks the deploy.

- [ ] **Step 1: Check the branch is complete and clean**

```bash
git -C $WT status --short
git -C $WT log --oneline main..HEAD
git -C $WT diff --stat main...HEAD
```

Expected: no uncommitted change; at least one commit each for V177-1, V177-2 and V177-3 (V177-4 has one only if it fixed a style). The diff stat names only the files in the index's Task ledger rows V177-1..V177-4: `swingbot/admin/api_v1/trades.py`, `tests/admin/test_trades_partial_row.py`, `tests/admin/test_api_v1_trades.py`, `frontend/src/app/ui/plan-cell.ts`, `frontend/src/app/ui/plan-cell.spec.ts`, `frontend/src/app/api/models.ts`, `frontend/src/app/ui/runner-cell.ts`, `frontend/src/app/ui/runner-cell.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, `frontend/src/app/workspaces/trades/trades.spec.ts`, `frontend/src/app/workspaces/dashboard/positions-table.spec.ts`. In particular `swingbot/core/presentation/plan_view.py` and `trades.columns.ts` are absent (Global Constraints). Any other file is explained in the task report or reverted.

- [ ] **Step 2: Run the Python full suite once**

The suite's database-backed tests use the disposable test Postgres. If `/replicate-prod-db` has not run in this session yet (V177-4 Step 2 runs it), run it now (CLAUDE.md). Make sure `db-test` is up:

```bash
docker compose -f E:/Documents/Private/Projects/Discord-Bot/docker-compose.yml --profile test up -d db-test
```

Then dispatch the `test-runner` subagent (so none of the output lands in this context) with: run `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/scripts/dev/testrun.py full` (it includes the complexity gate); report the passed/failed/xfailed/skipped counts and, for a failure, only the first failing node id and its assertion line.

Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`testing-cost.md`). A run with the database tests skipped (`db-test` down) does not count: start `db-test` and re-run. `tests/presentation/test_surface_agreement.py` and `tests/presentation/test_plan_view_partial.py` are among the green ones, unchanged by this plan (`git -C $WT diff --stat main...HEAD -- tests/presentation/` prints nothing).

- [ ] **Step 3: Run the frontend gates once (lint, full unit run, production build)**

In PowerShell (never `cd` in Bash):

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npm run lint
npx ng test --watch=false
npm run build
Pop-Location
```

Expected: lint exits 0 with no new `eslint-suppressions.json` entry (`git -C $WT diff --stat main...HEAD -- frontend/eslint-suppressions.json` prints nothing); Vitest reports `0 failed`, and `src/app/ui/primitives.spec.ts` is among the passing files (no raw `<button>`/`<input>`/`<select>`, no `.pos`/`.neg`/`.muted` selector, no colour literal in the files V177-2/V177-3/V177-4 touched); the build ends without errors. A 60 s "Timeout waiting for worker … no tests" is machine load: re-run once. A `primitives.spec.ts` failure is fixed in the file it names (use `sb-button`, a token colour, a non-reserved class name), never by an allowlist entry without a comment.

- [ ] **Step 4: Complexity of every Python function the plan wrote or changed**

```bash
python -m radon cc -s E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/swingbot/admin/api_v1/trades.py | grep -E "_row_from_plan|_row_from_leg|_row_from_trade|_runner_|_closed_manually_after_tp1|_trailing_status_fields|_trailing_pnl_ends"
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/scripts/dev/complexity_gate.py
```

Expected: `_row_from_plan` reads `C (15)` or lower (its baseline is 15, `complexity_baseline.json`; it must not grow); every other listed function — `_runner_cell_fields`, `_runner_best_or_fill`, `_runner_pnl_fields`, `_runner_exit_fields`, `_runner_exit_reason`, `_closed_manually_after_tp1`, `_row_from_leg`, `_row_from_trade`, `_trailing_status_fields` — reads below 15; the gate passes.

- [ ] **Step 5: Fix any failure alone (otherwise skip)**

A failing test or gate is fixed in its own scoped commit on the branch (`fix(<area>): ... (v177)`, message in `$SCRATCH/v177-5-fix-<n>-msg.txt` ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, `git -C $WT commit -F`) and re-run alone — `python $WT/scripts/dev/testrun.py file <test>` or `npx ng test --watch=false --include <spec>` from `$WT/frontend` — never by re-running the whole suite. Record in the task report: Python counts (passed / skipped / 0 failed / 0 xfailed), the Vitest count, lint and build results, and the `_row_from_plan` radon line.

- [ ] **Step 6: Bring `main` into the branch**

Follow the `worktree-lifecycle` skill (other sessions share `$R` and may have committed to `main` since V177-1):

```bash
git -C $R fetch origin
git -C $R status --short
git -C $R log --oneline -1 origin/main
git -C $R log --oneline -1 main
git -C $WT merge main -m "merge: main into v177 runner plan cell before release"
```

Expected: `$R` shows no pending change to this plan's files; local `main` is not behind `origin/main` (if it is, `git -C $R pull --ff-only origin main` first — never a force or a rebase of `main`); the merge is clean or its conflicts are resolved file by file. v177 adds no Alembic revision. Re-run alone the tests of any file that conflicted (for `trades.py`: `python $WT/scripts/dev/testrun.py file tests/admin/test_trades_partial_row.py` and `... file tests/admin/test_api_v1_trades.py`; for a frontend file: its spec with `--include`), plus `python $WT/scripts/dev/complexity_gate.py` if `trades.py` conflicted. No full suite here: it ran in Step 2.

- [ ] **Step 7: Merge the branch into `main`**

Write `$SCRATCH/v177-5-merge-msg.txt`, with V177-4's recorded browser-check line in place of the placeholder line:

```text
merge: v177 runner plan cell -- original plan plus trail line for trailing runners, runner exit on closed partial trades

Row fields tp1, best_pnl_pct, stop_pnl_pct (price-free), runner_exit_price,
runner_exit_reason; PlanCell runner and closed-runner forms; Dashboard and
Trades page wired through runnerCellInputs.
<V177-4 browser-check line, verbatim from its task report>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R switch main
git -C $R merge --no-ff 2026-10-19-v177-runner-plan-cell -F "$SCRATCH/v177-5-merge-msg.txt"
git -C $R log --oneline -3
```

Expected: a merge commit on `main`. No full suite after this merge (CLAUDE.md).

- [ ] **Step 8: Release the ui line (patch)**

Read the current values from disk (never from this plan or the spec's "at writing" line), bump `ui` by one patch and stamp it:

```bash
python - <<'EOF'
import datetime
import json
import pathlib

path = pathlib.Path(r"E:/Documents/Private/Projects/Discord-Bot/VERSION.json")
version = json.loads(path.read_text(encoding="utf-8"))
major, minor, patch = (int(part) for part in version["ui"].split("."))
version["ui"] = f"{major}.{minor}.{patch + 1}"
version["ui_updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
path.write_text(json.dumps(version, indent=2) + "\n", encoding="utf-8")
print(version["ui"])
EOF
git -C $R diff VERSION.json
```

Expected: only `ui` and `ui_updated` change. Write `$SCRATCH/v177-5-ui-release.txt` and `$SCRATCH/v177-5-ui-chore.txt`, identical except the first word (`release(ui):` / `chore(ui):`), with the printed value in place of `<ui version>`:

```text
release(ui): <ui version> -- Plan cell shows the original plan and a trail line for trailing runners, and the runner's exit on closed partial trades (v177)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R add VERSION.json
git -C $R commit -F "$SCRATCH/v177-5-ui-release.txt"
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/build_version_matrix.py
git -C $R add swingbot/admin/version_history.json
git -C $R commit -F "$SCRATCH/v177-5-ui-chore.txt"
```

- [ ] **Step 9: Release the bot line (patch)**

The same with `bot`/`bot_updated`:

```bash
python - <<'EOF'
import datetime
import json
import pathlib

path = pathlib.Path(r"E:/Documents/Private/Projects/Discord-Bot/VERSION.json")
version = json.loads(path.read_text(encoding="utf-8"))
major, minor, patch = (int(part) for part in version["bot"].split("."))
version["bot"] = f"{major}.{minor}.{patch + 1}"
version["bot_updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
path.write_text(json.dumps(version, indent=2) + "\n", encoding="utf-8")
print(version["bot"])
EOF
git -C $R diff VERSION.json
```

Write `$SCRATCH/v177-5-bot-release.txt` and `$SCRATCH/v177-5-bot-chore.txt` (`release(bot):` / `chore(bot):`):

```text
release(bot): <bot version> -- trades rows carry tp1, price-free runner percentages and the runner's exit price and reason (v177)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R add VERSION.json
git -C $R commit -F "$SCRATCH/v177-5-bot-release.txt"
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/build_version_matrix.py
git -C $R add swingbot/admin/version_history.json
git -C $R commit -F "$SCRATCH/v177-5-bot-chore.txt"
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
```

Expected: only the `bot` lines change in the diff; the version-matrix test passes (the one check the pre-bump suite cannot make). Do **not** push: V177-6 asks the partner first.

- [ ] **Step 10: Commit**

The commits of Steps 7-9 are this task's commits (merge, `release(ui)`, `chore(ui)`, `release(bot)`, `chore(bot)`), plus any Step 5 fix commits on the branch. Check:

```bash
git -C $R log --oneline -6
git -C $R status --short
git -C $R log --oneline origin/main..main
```

Expected: the five commits on top of `main`; `git status` shows nothing from this task; `origin/main..main` lists this plan's commits (still unpushed). Record both new version numbers in the task report for V177-6 and V177-7.

### Task V177-6: Gated push (deploy), workflow watch, read-only production check of RKLB's row

**Model:** sonnet — a gated push and reading production output against the contract.

**Files:**
- Create (session scratchpad only, never the repo): `$SCRATCH/v177_prod_row.py`, `$SCRATCH/v177-prod/` (production screenshots, Step 5)
- VM: read-only. Nothing is changed on production; if a live fix ever became necessary it is mirrored into this repo and committed on `main` before the task counts as done (`mirror-prod` skill) — none is planned.

**Interfaces:**
- Consumes: V177-5's unpushed `main` (merge plus the four release commits) and its two recorded version numbers; V177-1's helpers `_runner_cell_fields(plan, trade, row) -> dict`, `_runner_pnl_fields(row) -> dict`, `_runner_exit_fields(plan, trade) -> dict` in `swingbot/admin/api_v1/trades.py` (index § Backend contract), used only as a presence check; existing `build_rows(trades: list[dict] | None = None) -> list[dict]` (`trades.py:599`), which runs `_row_from_plan`/`_expand_plan_row` over the whole book with no request context and no price fetch.
- Produces: the deployed image; the production check's output (RKLB's row with `tp1`, `best_pnl_pct`, `stop_pnl_pct`, `runner_exit_price`, `runner_exit_reason`) recorded in the task report, which V177-7 copies into the index.

**The push is the deploy:** `.github/workflows/deploy.yml` runs on every push to `main` and deploys to the Hetzner VM when its gates pass. Nothing is pushed until the partner says yes.

- [ ] **Step 1: Ask the partner before pushing**

```bash
git -C $R log --oneline origin/main..main
git -C $R status --short
```

Then ask with `AskUserQuestion`, one question, recommended option first:

> "v177 is merged on `main` (ui <ui version>, bot <bot version>; full suite and frontend gates green; browser check: <V177-4 line>). `git push origin main` deploys it to production. Push now?"
> 1. "Push now and watch the deploy" (recommended)
> 2. "Hold — leave `main` unpushed for now"

On answer 2, stop the task here and report that `main` is ahead of `origin/main` by the listed commits; V177-7 waits until the partner asks for the push.

- [ ] **Step 2: Push**

```bash
git -C $R push origin main
gh run list --branch main --limit 1
```

Expected: the push is accepted and a workflow run for the new `main` head is listed. A rejected push (another session pushed first) is resolved with `git -C $R pull --no-rebase origin main`, never a force push; because that pull brings other sessions' commits into the same deploy, show them (`git -C $R log --oneline HEAD@{1}..HEAD`) and ask the partner again (`AskUserQuestion`, same two options) before re-pushing.

- [ ] **Step 3: Watch the workflow**

```bash
gh run watch <run id from Step 2's list> --exit-status
```

Expected: every `backend-test` suite leg, `backend-lint-gate` (complexity gate), `frontend-test` (Lint, Unit tests — `primitives.spec.ts` among them —, Production build, the base-href check), the image and health-check jobs and the deploy job all succeed. A red job: read its log (`gh run view <id> --log-failed`), fix the cause on `main` as its own scoped commit (`fix(<area>): ... (v177, CI)`), re-run that one test or spec alone locally, then ask the partner before pushing the fix (Step 1's question). Never re-run a red workflow blindly.

- [ ] **Step 4: Check the rows the production admin serves (read-only)**

Write `$SCRATCH/v177_prod_row.py`:

```python
"""v177 deploy check (read-only): trades rows on production carry the runner fields.

Runs inside the admin container. build_rows() reads the plan and trade stores
and builds every row; it fetches no price and writes nothing.
"""
import json
import pathlib

from swingbot.admin.api_v1 import trades

KEYS = ("tp1", "best_pnl_pct", "stop_pnl_pct", "runner_exit_price", "runner_exit_reason")
SHOWN = ("ticker", "plan_id", "status", "direction", "entry", "stop_loss", "risk_stop", "tp1",
         "runner_best", "banked_exit_price", "best_pnl_pct", "stop_pnl_pct", "bar_kind",
         "runner_exit_price", "runner_exit_reason", "leg_index", "leg_total")


def _pct(price, entry, bearish):
    if not isinstance(price, (int, float)) or not isinstance(entry, (int, float)) or not entry:
        return None
    sign = -1 if bearish else 1
    return round((price - entry) * sign / entry * 100, 2)


def _formula_holds(row):
    best = row.get("runner_best")
    if not isinstance(best, (int, float)):
        best = row.get("banked_exit_price")
    bearish = row.get("direction") == "bearish"
    return (_pct(best, row.get("entry"), bearish) == row.get("best_pnl_pct")
            and _pct(row.get("stop_loss"), row.get("entry"), bearish) == row.get("stop_pnl_pct"))


version_file = pathlib.Path(trades.__file__).resolve().parents[3] / "VERSION.json"
rows = trades.build_rows()
runners = [r for r in rows if r.get("tp1") is not None]
closed_runners = [r for r in rows if r.get("runner_exit_price") is not None]
print(json.dumps({
    "version": json.loads(version_file.read_text()) if version_file.exists() else "VERSION.json not found",
    "new_code": all(hasattr(trades, n) for n in ("_runner_cell_fields", "_runner_pnl_fields", "_runner_exit_fields")),
    "rows": len(rows),
    "rows_missing_a_key": sum(1 for r in rows if not all(k in r for k in KEYS)),
    "runners": len(runners),
    "runners_formula_holds": sum(1 for r in runners if _formula_holds(r)),
    "runners_not_partial_trailing": sum(1 for r in runners
                                        if r.get("status") != "PARTIAL" or r.get("bar_kind") != "trailing"),
    "closed_runners": len(closed_runners),
    "closed_runner_reasons": sorted({str(r.get("runner_exit_reason")) for r in closed_runners}),
    "closed_runners_not_closed": sum(1 for r in closed_runners if r.get("status") != "CLOSED"),
    "rklb": [{k: r.get(k) for k in SHOWN} for r in rows if r.get("ticker") == "RKLB"],
}, indent=2, default=str))
```

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -" < "$SCRATCH/v177_prod_row.py"
```

Expected:
- `docker compose ps`: `bot` and `admin` up and healthy, started after the deploy finished.
- `version` shows the ui and bot versions V177-5 released; `new_code` is `true`.
- `rows_missing_a_key` is `0` (the exact-key contract holds on production data, legacy trades included).
- `runners_formula_holds` equals `runners`, and `runners_not_partial_trailing` is `0` (index § Backend contract: `tp1` only on PARTIAL trailing rows; percentages by `_trailing_pnl_ends`'s formula with the `runner_best` → `banked_exit_price` fallback).
- `closed_runners_not_closed` is `0`; each `closed_runner_reasons` entry is one of `tp1_runner_trail`, `tp1_runner_be`, `tp1_runner_tp2`, `tp1_runner_progress_stall`, `time_exit`, `giveback`, `manual` or another leg reason passed through (name any such in the report).
- `rklb`: if the short is still PARTIAL, its row carries `tp1` `58.33`, `risk_stop` `61.85`, `entry` `60.67`, and `best_pnl_pct`/`stop_pnl_pct` that match its current `runner_best`/`stop_loss` (`17.69`/`13.57` while best is 49.94 and the stop 52.437; a newer best price moves both, which is the formula working, not a defect). Its TP1-leg row (status `CLOSED`, leg index 0) carries `tp1`, `best_pnl_pct`, `stop_pnl_pct` all `None`. If RKLB has closed since, both of its leg rows carry the same `runner_exit_price` and `runner_exit_reason`, and `tp1` is `None` on both.

A mismatch is a defect: report the row (it holds prices and tickers, no secrets) and fix it in this repo on `main` with a failing test first, then ask before pushing (Step 1). Never patch production by hand.

- [ ] **Step 5: Look at the cell on production at three widths**

Required if V177-4 did not run its local check (credentials or replica) or saw no runner or no closed runner; otherwise a short confirmation that the deployed bundle matches what V177-4 measured. `browse.mjs` signs in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` inside its own process (one attempt); without them it waits for the partner to sign in in its window — only when the partner chose that in V177-4 Step 1 (answer 2); otherwise ask first (`AskUserQuestion`). Paths go without a leading slash (Git Bash rewrites `/app/...`):

```bash
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/browse.mjs shots --out "$SCRATCH/v177-prod/partial" --path "app/dashboard" --click '[role="tab"]:has-text("Partial")' --widths 1440,768,390
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/browse.mjs shots --out "$SCRATCH/v177-prod/closed" --path "app/trades?status=CLOSED" --widths 1440,768,390
```

Read each `*.txt` and open each `*.png` with the Read tool. Expected: every `.txt` starts `page-scroll-x: 0`; the Partial tab's text holds, per trailing runner, a line in the shape `<entry> → <tp1> / <stop> (<d1>% - <d2>%)` followed by `Trail <best> → <exit> (+<a>% / +<b>%)` (for RKLB at the spec's numbers: `60.67 → 58.33 / 61.85 (3.9% - 1.9%)` and `Trail 49.94 → 52.44 (+17.7% / +13.6%)`); the Closed page shows each closed runner's exit price in the target slot with a signed percent, and no Plan cell anywhere prints `TP2`. In the screenshots, the two runner lines stack without wrapping at 390, 768 and 1440. Record what was seen in the task report.

- [ ] **Step 6: Commit**

Nothing to commit: the push of Step 2 is this task's change, and the scripts and screenshots stay in `$SCRATCH`. A CI or production fix from Steps 3-4 is its own scoped commit on `main`, made in that step. Check:

```bash
git -C $R status --short
git -C $R log --oneline origin/main..main
```

Expected: no change from this task; `origin/main..main` is empty (everything pushed). Record in the task report, for V177-7: the run id and its result, Step 4's JSON summary line by line (versions, counts, RKLB rows), and Step 5's verdict.

### Task V177-7: `/panel` pre-close-out and `/close-out` (bump skipped)

**Model:** sonnet — weighs panel findings and runs the close-out checklist.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-19-v177-runner-plan-cell_0-index.md` (a `## Results` section appended), then `git mv` all three plan files (`_0-index`, `_1-row-and-cell`, `_2-ship`) into `docs/superpowers/plans/implemented/`
- Move: `docs/superpowers/specs/2026-10-19-v177-runner-plan-cell-design.md` → `docs/superpowers/specs/implemented/` (with an `### Implementation review` addendum under its `## Panel review` if the panel returns findings)
- Modify, only on a `BLOCKING` finding: the file it names, on the branch in `$WT`

**Interfaces:**
- Consumes: V177-5's merge commit on `main` and its recorded results (Python counts, Vitest count, lint/build, `_row_from_plan` radon line, both new versions); V177-4's browser-check line; V177-6's run id, production JSON summary and production look.
- Produces: nothing for a later task; the plan leaves the live set and the SessionStart `PLAN WIP` line stops naming it.

CLAUDE.md gives standing permission to run `/close-out` once every task is merged; the spec's `**Panel:** staff-engineer, financial-advisor` line makes `/panel` its first gate.

- [ ] **Step 1: Run the panel over the merged diff**

Find the merge commit and run the panel over the plan's full diff:

```bash
git -C $R log --oneline --merges -1 --grep="merge: v177 runner plan cell"
```

```
/panel staff-engineer,financial-advisor <merge sha>^1...2026-10-19-v177-runner-plan-cell
```

Give the reviewers V177-5's recorded results, V177-4's browser-check line and V177-6's production summary as context, and point each at the spec's own `## Panel review`: the staff-engineer checks the manual-close fallback, the leg-row clearing (`_RUNNER_CELL_CLEARED`, `bar_kind` kept), the exact-key contract with the legacy `None`s, that `plan_view.py` and the row's `stop_loss`/`target`/`banked_exit_price` are untouched, and that `_row_from_plan` did not grow; the financial-advisor checks the copy — the `Trail` label, "unrealised", "per share from the original entry, before costs and tax", "your broker's resting orders are not synced", no `TP2` in the cell, signed runner-exit percentages with an explicit `-` on the loss side, and the line-1 tooltip "Original plan (TP1 already filled)".

Expected: no unresolved `BLOCKING` finding. A `BLOCKING` finding is fixed on the branch in `$WT` as its own scoped commit (`fix(<area>): ... (v177 panel)`, message via `$SCRATCH` and `git -C $WT commit -F`), its tests re-run alone (`python $WT/scripts/dev/testrun.py file <test>` or `npx ng test --watch=false --include <spec>` from `$WT/frontend` in PowerShell `Push-Location`), the panel re-run for that role, and the branch merged into `main` again (`git -C $R merge --no-ff 2026-10-19-v177-runner-plan-cell`); that fix reaches production only through V177-6 Step 1's question and push. Or it is rejected with a reason, recorded as `rejected: <why>` in `.superpowers/sdd/progress.md` (append; never `cat` that file). Each `ADVISORY` finding is applied the same way or recorded with a one-line reason.

If the panel returned any finding, append to the spec `$R/docs/superpowers/specs/2026-10-19-v177-runner-plan-cell-design.md`, under its `## Panel review` section:

```markdown

### Implementation review, <YYYY-MM-DD> (staff-engineer, financial-advisor)

- <role> <n>: <one line> -- applied (<sha>) | rejected: <why>
```

one line per finding; a role that returned `CLEAN` gets the line `- <role>: clean`.

- [ ] **Step 2: Run `/close-out`, with its bump steps already done**

Invoke `/close-out`. Its Step 2 (panel) is Step 1 above. Its Steps 3-4 (bump and regeneration) ran in V177-5 Steps 8-9: confirm them from the log rather than repeating them:

```bash
git -C $R log --oneline -6 -- VERSION.json swingbot/admin/version_history.json
python -c "import json; print(json.load(open(r'E:/Documents/Private/Projects/Discord-Bot/VERSION.json')))"
```

Expected: `release(ui)`, `chore(ui)`, `release(bot)`, `chore(bot)` commits naming v177, and both lines one patch above their values before V177-5. Do not bump again. The header predicted `Bump: ui patch, bot patch` and `Edge: none (integrity)`; both held (the cell shows different content on existing screens, the endpoint gained additive fields, no signal or stored record changed), so nothing is amended. If one did not hold, amend the index header and say why in one clause in Step 5's commit (close-out Step 5).

- [ ] **Step 3: Record the results in the index**

Append to `$R/docs/superpowers/plans/2026-10-19-v177-runner-plan-cell_0-index.md`, filled from the task reports:

```markdown

## Results

Done <YYYY-MM-DD>. V177-1..V177-7 complete. Full suite (V177-5): Python <passed> passed, <skipped> skipped, 0 failed, 0 xfailed; Vitest <n> passed; lint clean; production build green; `_row_from_plan` <radon grade (n)>. Browser check (V177-4): <line>. Released ui <version>, bot <version>; deploy run <id> green. Production (V177-6): <rows> rows, 0 missing a key; <n> runners, formula holds on <n>; <n> closed runners (reasons <list>); RKLB <tp1 58.33, best_pnl_pct x, stop_pnl_pct y | closed: runner exit p, reason r>. Panel (V177-7): <n> BLOCKING resolved, <n> ADVISORY (<applied>/<recorded>), or clean.
```

- [ ] **Step 4: Remove the worktree and its branch**

The branch name contains no `backup` and is not `stable-*`. Check it is fully merged first; a non-zero count means stop and ask the partner (`git-safety.md`):

```bash
git -C $R rev-list --count main..2026-10-19-v177-runner-plan-cell
git -C $WT status --short
git -C $R worktree remove .claude/worktrees/2026-10-19-v177-runner-plan-cell
git -C $R branch -d 2026-10-19-v177-runner-plan-cell
git -C $R worktree list
```

Expected: `0`; `$WT` clean; the worktree and branch are gone (`branch -d`, never `-D`); `worktree list` no longer shows it. A `worktree remove` that refuses because of untracked or modified files means something was left behind: look at it before deciding, never `--force` by default (`frontend/node_modules` and build output are ignored files and do not block the removal).

- [ ] **Step 5: Move the documents and commit on `main`**

```bash
ls E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/plans/2026-10-19-v177-runner-plan-cell_*.md
git -C $R mv docs/superpowers/plans/2026-10-19-v177-runner-plan-cell_0-index.md docs/superpowers/plans/implemented/
git -C $R mv docs/superpowers/plans/2026-10-19-v177-runner-plan-cell_1-row-and-cell.md docs/superpowers/plans/implemented/
git -C $R mv docs/superpowers/plans/2026-10-19-v177-runner-plan-cell_2-ship.md docs/superpowers/plans/implemented/
git -C $R mv docs/superpowers/specs/2026-10-19-v177-runner-plan-cell-design.md docs/superpowers/specs/implemented/
git -C $R add docs/superpowers/plans/implemented/2026-10-19-v177-runner-plan-cell_0-index.md docs/superpowers/specs/implemented/2026-10-19-v177-runner-plan-cell-design.md
git -C $R status --short
```

Expected: `ls` lists exactly the three plan files (a missing or extra file is checked before moving); `git status` shows three renames into `plans/implemented/`, one into `specs/implemented/`, and the index/spec edits of Steps 1 and 3 — nothing else of this plan's. The spec moves only if nothing else live builds from it: before the `git mv` of the spec, `git -C $R grep -l "2026-10-19-v177-runner-plan-cell-design" -- docs/superpowers/plans docs/superpowers/specs` must list only this plan's three files and the spec itself; any other live plan or spec citing it keeps the spec where it is (skip its `git mv`, and say why in the commit message).

Write `$SCRATCH/v177-7-msg.txt`:

```text
docs(v177): close out -- plan and spec to implemented/, results recorded

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R commit -F "$SCRATCH/v177-7-msg.txt"
git -C $R status --short
git -C $R log --oneline origin/main..main
```

Expected: one commit moving the plan files and the spec and carrying the index's Results and any spec addendum; no full suite after this (CLAUDE.md: it ran once, in V177-5).

- [ ] **Step 6: Push the close-out, with the partner's yes**

Every push to `main` runs the deploy workflow, even a docs-only one (it redeploys the same code). Ask with `AskUserQuestion`, one question, recommended option first:

> "v177 is closed out on `main` (docs only: plan and spec moved to `implemented/`, results recorded). Pushing re-runs the deploy workflow with unchanged code. Push now?"
> 1. "Push now" (recommended)
> 2. "Leave it unpushed — it goes out with the next push"

On answer 1:

```bash
git -C $R push origin main
gh run list --branch main --limit 1
```

Expected: the push is accepted (a rejection is resolved with `git -C $R pull --no-rebase origin main` and a re-push, never a force push); the listed run is for the close-out commit. On answer 2, report that `main` is ahead of `origin/main` by the close-out commit.

