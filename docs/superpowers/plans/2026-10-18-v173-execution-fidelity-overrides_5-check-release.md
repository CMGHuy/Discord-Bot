# v173 Execution fidelity, part 5: three-width check, full suite, release, deploy with the data revision, VM report, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-18:" -A 220 docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_5-check-release.md`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §2 (the retag on production), §5 (checks at three widths, the VM run), § Testing, § Risks, `**Panel:**` line
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work`, § Pinned bulk-clear ids and the task ledger. Every task below implicitly includes those Global Constraints.

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`, branch `2026-10-18-v173-execution-fidelity-overrides`. `$SCRATCH` is the implementing session's scratchpad (absolute path): browser and VM scripts live there and nothing in it is committed. Never `cd`; use absolute paths and `git -C`. Production is reached only through `bash $R/scripts/ops/ssh-hetzner.sh "<cmd>"` (stdin for a script: `... "cd /opt/swing-bot && docker compose exec -T bot python -" < $SCRATCH/x.py`); any live change made there is mirrored into this repo and committed before its task counts as done (`mirror-prod` skill). A browser is driven with Playwright only, and every login loads `ADMIN_USERNAME`/`ADMIN_PASSWORD` from `.env` inside the script: never printed, echoed, passed on a command line or written to another file.

Tasks: V173-15..V173-20. **A push to `main` deploys** (`.github/workflows/deploy.yml` runs on every push to `main`, and `deploy/deploy.sh` runs `alembic upgrade head`), so the data revision `v173_001` runs on production at the push. That is why V173-17 merges and bumps on `main` **without pushing**, and V173-18 pushes only after the `schema-evolution.md` § Before running a data revision on production checks pass. Run V173-17 and V173-18 back to back in one sitting: `$R` is shared, and another session's push of `main` would carry the unpushed merge out with it.

# Phase 5: Check, verify, release, run, close out (V173-15..V173-20)

### Task V173-15: Three-width Playwright check of the panel and the "Bulk close" label

**Model:** sonnet — run the app and judge layout at three widths

**Files:**
- Create (session scratchpad only, never the repo): `$SCRATCH/v173-widths.cjs`
- Modify, only if a check fails: the V173-14 files `frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts` (styles, template) and its spec `frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts`

**Interfaces:**
- Consumes: V173-14's `OverrideFidelityPanel` (selector `sb-override-fidelity-panel`) mounted in `execution.ts`; V173-13's store slice, which calls `GET /api/v1/analytics/override-fidelity`; the payload contract of Global Constraints (keys `rows, summary, verdict, engine_flags, asof, currency_symbol`, the 19 row keys, the summary and verdict keys) and the Handoff value types (`bulk_dates` = `{iso_date: int}`, `engine_flags` = `{"stall_exit_enabled": bool, "runner_structure_exit": str}`); V173-2's label `manual_bulk: 'Bulk close'` in `exit-reasons.ts`, which `outcome-tiles.ts` shows from the last `status_history` reason when no leg has a reason.
- Produces: the measurement lines and the screenshot verdict, recorded in the task report (V173-20 copies the summary into § Progress).

The override endpoint is stubbed in the browser with three fixture payloads (WAITING with mixed rows, a recorded COST verdict, empty), so the check covers every layout state and does not depend on the local database holding overrides. The trade-page check rewrites one real local response so its last transition reads `manual_bulk`. Everything else is the real local admin.

- [ ] **Step 1: Pick one local plan for the label check**

The local admin reads the working database named in `.env`. Find a CLOSED plan with no realised legs (the trade page then falls back to the last transition's reason):

```bash
PYTHONPATH=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides python -c "from swingbot.core.planning.plan_store import PlanStore; print(next((p.plan_id for p in PlanStore().all() if p.status == 'CLOSED' and not p.legs_realized and p.status_history), 'NONE'))"
```

Expected: one plan id (not a secret; it goes on the Step 4 command line). `NONE` means the local book has no such plan: pass `NONE` in Step 4 (the label half is skipped) and V173-18 Step 7 checks the label on production instead. Say which in the task report.

- [ ] **Step 2: Start the local admin and the dev server**

Start both in the background (Bash `run_in_background: true`, one call each):

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/admin_ui.py
```

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng serve --port 4123
```

`$WT` has no `.env` of its own and none is copied there (credentials are never written to another file): `swingbot/config.py` tries `$WT/.env`, then falls back to `load_dotenv()`, which walks up from the module to `$R/.env`. Read the admin's first output lines: the warning that the admin runs on the default `admin`/`admin` credentials (`config.py:1590`) means it did **not** load `.env`; stop both servers and report it rather than checking against the default. Wait until `curl -s -o /dev/null -w "%{http_code}" http://localhost:4123/app/` prints `200`. If the admin cannot reach its database and exits, stop, say so in the task report, and leave the check to V173-19 Step 5 (production); never skip it silently.

- [ ] **Step 3: Write the check script**

Create `$SCRATCH/v173-widths.cjs`:

```js
// v173 three-width check: sb-override-fidelity-panel and the "Bulk close" label.
// Usage: node v173-widths.cjs <WT> <envFile> <outDir> <planId|NONE>
// Logs in with ADMIN_USERNAME/ADMIN_PASSWORD loaded from <envFile> into this
// process only -- never printed, logged or passed on a command line.
const { createRequire } = require('node:module');
const { mkdirSync } = require('node:fs');
const [wt, envFile, out, planId] = process.argv.slice(2);
const { chromium } = createRequire(`${wt}/frontend/package.json`)('playwright');
mkdirSync(out, { recursive: true });
process.loadEnvFile(envFile);
const BASE = 'http://localhost:4123';

const row = (o) => ({
  plan_id: 'p', ticker: 'T', horizon: '4w', direction: 'bullish', state_at_close: 'ACTIVE',
  close_date: '2026-10-20', bulk: false, approx: false, price_source: 'quote', status: 'resolved',
  actual_r: 0, engine_r: 0, delta_r: 0, actual_usd: 0, engine_usd: 0, delta_usd: 0,
  engine_exit_reason: 'runner_tp2', outcome: 'neutral', source: 'manual', ...o,
});

const ROWS = [
  row({ plan_id: 'p1', ticker: 'AAPL', actual_r: 0.42, engine_r: 1.1, delta_r: -0.68,
        actual_usd: 84, engine_usd: 220, delta_usd: -136, outcome: 'hurt' }),
  row({ plan_id: 'p2', ticker: 'MSFT', horizon: '2w', state_at_close: 'PARTIAL', close_date: '2026-10-14',
        actual_r: 1.21, engine_r: 0.9, delta_r: 0.31, actual_usd: null, engine_usd: null, delta_usd: null,
        engine_exit_reason: 'runner_trail', outcome: 'helped' }),
  row({ plan_id: 'p3', ticker: 'NVDA', close_date: '2026-09-22', approx: true, price_source: 'session_close',
        actual_r: -0.3, engine_r: -0.18, delta_r: -0.12, actual_usd: -60, engine_usd: -36, delta_usd: -24,
        engine_exit_reason: 'timeout', outcome: 'hurt' }),
  row({ plan_id: 'p4', ticker: 'XLE', close_date: '2026-09-30', bulk: true, approx: true,
        price_source: 'session_close', actual_r: 0.1, engine_r: 0.6, delta_r: -0.5,
        actual_usd: 20, engine_usd: 120, delta_usd: -100, outcome: 'hurt' }),
  row({ plan_id: 'p5', ticker: 'XLF', close_date: '2026-09-30', bulk: true, approx: true,
        price_source: 'session_close', direction: 'bearish', actual_r: -0.2, engine_r: -1.0, delta_r: 0.8,
        actual_usd: -40, engine_usd: -200, delta_usd: 160, engine_exit_reason: 'stop', outcome: 'helped' }),
  row({ plan_id: 'p6', ticker: 'TSLA', close_date: '2026-10-08', status: 'ambiguous',
        actual_r: 0.2, engine_r: null, delta_r: null, actual_usd: 40, engine_usd: null, delta_usd: null,
        engine_exit_reason: null, outcome: null }),
];

const split = (n, r, usd) => ({ n, sum_delta_r: r, sum_delta_usd: usd });
const SUMMARY = {
  n_by_status: { resolved: 2, ambiguous: 1 }, bulk_n: 2, bulk_dates: { '2026-09-30': 2 },
  approx_n: 1, counted_n: 2, sum_delta_r: -0.37, sum_delta_usd: -136, usd_missing_n: 1,
  helped: 1, hurt: 1, neutral: 0,
  splits: {
    state_at_close: { ACTIVE: split(1, -0.68, -136), PARTIAL: split(1, 0.31, null) },
    horizon: { '4w': split(1, -0.68, -136), '2w': split(1, 0.31, null) },
    direction: { bullish: split(2, -0.37, -136) },
  },
};
const WAITING = { state: 'WAITING', n: 2, needed: 30, weeks: 2, week_floor: 10, open_n: 0,
  excluded_share: 0.333, evaluable: false, recorded: false, recorded_on: null, mean_delta_r: null, ci: null };
const COST = { state: 'COST', n: 34, needed: 30, weeks: 12, week_floor: 10, open_n: 0,
  excluded_share: 0.1, evaluable: true, recorded: true, recorded_on: '2027-03-01',
  mean_delta_r: -0.08, ci: [-0.15, -0.01] };
const base = { engine_flags: { stall_exit_enabled: true, runner_structure_exit: 'off' },
  asof: '2026-10-19', currency_symbol: '$' };
const PAYLOADS = {
  waiting: { ...base, rows: ROWS, summary: SUMMARY, verdict: WAITING },
  cost: { ...base, rows: ROWS,
          summary: { ...SUMMARY, counted_n: 34, sum_delta_r: -2.72, sum_delta_usd: -544 }, verdict: COST },
  empty: { ...base, rows: [],
           summary: { ...SUMMARY, n_by_status: {}, bulk_n: 0, bulk_dates: {}, approx_n: 0, counted_n: 0,
                      sum_delta_r: 0, sum_delta_usd: 0, usd_missing_n: 0, helped: 0, hurt: 0, neutral: 0,
                      splits: { state_at_close: {}, horizon: {}, direction: {} } },
           verdict: { ...WAITING, n: 0, weeks: 0, excluded_share: 0 } },
};

async function login(page) {
  await page.goto(`${BASE}/app/`, { waitUntil: 'domcontentloaded' });
  const ok = await page.evaluate(async (body) => {
    const res = await fetch('/api/v1/session', { method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return res.ok;   // one attempt only: the login limiter counts failures
  }, { username: process.env.ADMIN_USERNAME, password: process.env.ADMIN_PASSWORD });
  if (!ok) throw new Error('login refused with the .env credentials (values not shown)');
}

function measure() {
  const host = document.querySelector('sb-override-fidelity-panel');
  if (!host) return { panel: false };
  const doc = document.documentElement;
  const leaf = (text) => [...host.querySelectorAll('*')]
    .filter((e) => e.textContent.includes(text))
    .sort((a, b) => a.textContent.length - b.textContent.length)[0] ?? null;
  const visible = (e) => !!e && e.getBoundingClientRect().width > 0 && getComputedStyle(e).display !== 'none';
  let tile = leaf('Overrides counted');
  while (tile && tile.parentElement && tile.parentElement !== host && tile.parentElement.children.length < 4) {
    tile = tile.parentElement;
  }
  const grid = tile?.parentElement ?? null;
  const tileRows = grid ? new Set([...grid.children].map((c) => Math.round(c.getBoundingClientRect().top))).size : null;
  const badge = leaf('of 30 needed') ?? leaf('vs the engine');
  const touch = [...host.querySelectorAll('button, a, [role=button], summary')].filter(visible)
    .map((e) => Math.round(e.getBoundingClientRect().height));
  const table = host.querySelector('table');
  const cards = [...host.querySelectorAll('li.card')].filter(visible);
  return {
    panel: true,
    pageOverflowPx: Math.max(doc.scrollWidth - doc.clientWidth, document.body.scrollWidth - document.body.clientWidth),
    tileRows,
    badgeText: badge?.textContent.trim() ?? null,
    badgeTruncated: badge ? badge.scrollWidth > badge.clientWidth + 1 || getComputedStyle(badge).textOverflow === 'ellipsis' : null,
    tableVisible: visible(table),
    cardCount: cards.length,
    firstCard: cards[0]?.innerText.split('\n').map((s) => s.trim()).filter(Boolean).slice(0, 4) ?? null,
    smallestTouchPx: touch.length ? Math.min(...touch) : null,
    text: host.innerText,
  };
}

const COPY = [
  'Overrides vs engine', 'Overrides counted', 'Helped / hurt / neutral', 'counts ignore size',
  'Compares the overrides you made with what the engine would have done. Past closes only, not advice on future ones. A close for a reason the engine cannot see (a gap, earnings, needing the cash) can still be right. Figures are after modelled costs and before tax. Closing early can also change the tax holding period. There is no target number of overrides.',
];
const EXPECT = {
  waiting: [...COPY, '2 of 30 needed. No conclusion yet.',
    '2 closes from one bulk clear on 2026-09-30 are not decisions, so they are left out',
    '1 estimated rows are shown but not counted', 'estimated exit: daily close, not your fill'],
  cost: [...COPY, 'Your overrides cost $', 'R) vs the engine'],
  empty: ['Overrides vs engine', 'No manual overrides in scope.'],
};

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  let variant = 'waiting';
  await page.route('**/api/v1/analytics/override-fidelity**', (route) => route.fulfill({ json: PAYLOADS[variant] }));
  await login(page);
  for (const v of ['waiting', 'cost', 'empty']) {
    variant = v;
    for (const width of [1280, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`${BASE}/app/analytics?tab=execution`, { waitUntil: 'load' });
      await page.waitForSelector('sb-override-fidelity-panel', { timeout: 60000 });
      await page.waitForTimeout(1200);
      const m = await page.evaluate(measure);
      const flat = (m.text ?? '').replace(/\s+/g, ' ');
      const missing = EXPECT[v].filter((s) => !flat.includes(s));
      if (v === 'waiting' && !/1 .+ rows are left out/.test(flat)) missing.push('1 <ambiguous label> rows are left out');
      delete m.text;
      console.log(v, width, JSON.stringify({ ...m, missing }));
      await page.locator('sb-override-fidelity-panel').screenshot({ path: `${out}/${v}-${width}.png` });
    }
  }
  if (planId && planId !== 'NONE') {
    await page.route(`**/api/v1/trades/${planId}`, async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      const history = body.detail?.status_history ?? [];
      if (history.length) history[history.length - 1].reason = 'manual_bulk';
      await route.fulfill({ response: res, json: body });
    });
    for (const width of [1280, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`${BASE}/app/trades/${planId}`, { waitUntil: 'load' });
      await page.waitForTimeout(2500);
      const text = await page.evaluate(() => document.body.innerText);
      console.log('label', width, JSON.stringify({ bulkClose: text.includes('Bulk close') }));
      await page.screenshot({ path: `${out}/trade-${width}.png`, fullPage: true });
    }
  }
  await browser.close();
})().catch((err) => { console.error(String(err.message ?? err)); process.exit(1); });
```

- [ ] **Step 4: Run it**

Install Chromium once per machine first if Playwright asks (`npm --prefix $WT/frontend exec -- playwright install chromium`). Then, with the plan id from Step 1 (or `NONE`):

```bash
node "$SCRATCH/v173-widths.cjs" "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides" "E:/Documents/Private/Projects/Discord-Bot/.env" "$SCRATCH/v173-widths" "<plan id or NONE>"
```

The `.env` path is a path, not a secret; the script reads the two values itself and never prints them. Expected, one line per variant and width (nine panel lines, plus three `label` lines unless `NONE`):
- Every panel line: `panel` true, `pageOverflowPx` 0, `missing` `[]`.
- `waiting` and `cost` at 390: `tileRows` 2 (four tiles, two per row), `badgeTruncated` false, `tableVisible` false, `cardCount` 6, and `firstCard` leads with `AAPL`, then the close date `2026-10-20` (in whatever display form the panel uses), then the Δ in `$` and `R` (`-136` dollars and `-0.68 R` in the form `signedUsd`/`signedR` print).
- `waiting` and `cost` at 768 and 1280: `tileRows` ≤ 2, `badgeTruncated` false, `tableVisible` true.
- `smallestTouchPx` ≥ 44 at 390 wherever it is not `null` (the panel may carry no control; the retry button only shows on an error).
- `label` lines: `bulkClose` true at every width.

If `cardCount` is 0 at 390 because V173-14 named its card class differently, read the class from `override-fidelity-panel.ts` and change the `li.card` selector in the scratch script only; never rename the component's class to suit the script.

- [ ] **Step 5: Look at the screenshots**

Open with the Read tool: `waiting-390.png`, `waiting-768.png`, `waiting-1280.png`, `cost-390.png`, `empty-390.png`, and `trade-390.png` when it exists (all under `$SCRATCH/v173-widths/`). Confirm by eye: the net-effect tile leads (`±$X · ±Y R`), the badge sits whole at 390, each card shows ticker, close date and Δ on top with engine exit, status and the estimate label on the lines below, the NVDA row carries `estimated exit: daily close, not your fill`, the MSFT row shows `—` for its dollars, the exclusion notes are present, and the trade page's Exit tile reads `Bulk close`.

- [ ] **Step 6: Fix, re-check, stop the servers**

A failed expectation is fixed in `override-fidelity-panel.ts` (styles or template; media queries only at 639/640/1023/1024/1439/1440/1919/1920), with an assertion added to `override-fidelity-panel.spec.ts` for the fixed behaviour wherever a unit test can see it (copy, card structure), then:

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts --include src/app/workspaces/analytics/tabs/execution.spec.ts
```

Expected: PASS. Re-run Step 4 until every line meets its expectation. Stop both background servers afterwards. Record the measurement lines in the task report.

- [ ] **Step 7: Commit (only if Step 6 changed a file)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "fix(ui): override panel layout at <width> -- <what was wrong> (v173 three-width check)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: one commit on the branch, or none when every check passed first time; `$R`'s status shows no change from this task (the scratch script and the screenshots stay in `$SCRATCH`).

### Task V173-16: Full suite (Python + frontend)

**Model:** haiku — run and record, no judgement

**Files:** none (a failure is fixed in the file that broke, as its own scoped commit, then re-run alone)

**Interfaces:**
- Consumes: every commit of V173-1..V173-15 on the branch.
- Produces: the recorded green counts V173-20 writes into the index's `## Progress`.

- [ ] **Step 1: Check the branch is complete and clean**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides status --short
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides log --oneline main..HEAD
```

Expected: no uncommitted change; at least one commit for each code task V173-1..V173-3 and V173-5..V173-14 (V173-4 committed on `main`; V173-15 has a commit only if it fixed a layout).

- [ ] **Step 2: Confirm the exit engine's existing tests are untouched**

The Review Focus for V173-6 is zero behaviour change in `walk_v2`/`simulate_exit_v2`, proven by every existing exit test passing **unchanged**:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides diff --stat main...HEAD -- tests/planning tests/backtesting
```

Expected: the only files listed are the ones the ledger creates or modifies (`tests/planning/test_record_transition_extra.py`, `tests/planning/test_exit_sim_v2_replay_hooks.py`, `tests/backtesting/test_instrument_stats_ledger.py`); no existing `test_exit_sim*` file, and not the scale-out witness `tests/planning/test_exit_sim_scaleout_witness.py`. Anything else listed is reported as a finding, not fixed here.

- [ ] **Step 3: Run the Python full suite once**

CLAUDE.md: a task that runs tests against the database runs `/replicate-prod-db` first, so run it (it syncs the local replica; the suite itself uses the per-worker test database, and no new v173 test opens a database except `tests/db/test_v173_manual_bulk_retag.py`, which uses the disposable test DB fixtures). Then dispatch the `test-runner` subagent (so none of the output lands in this context) with: run `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py full` with the local test Postgres (`db-test`) up; report the pass/fail/xfail/skip counts and the first failure's node id and assertion only.

Expected: `0 failed` and `0 xfailed`. A changed pass count against the last baseline is not a failure (`testing-cost.md`). A DB-skipped run (`db-test` down) does not count: start `db-test` and re-run.

- [ ] **Step 4: Run the frontend suite and the production build once**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend run build
```

Expected: Vitest `0 failed`; the build ends without errors (CI runs the same two commands).

- [ ] **Step 5: Complexity of every Python function the plan wrote or changed**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/planning/plan_types.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/admin/api_v1/trade_commands.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/tracking/performance.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/partials.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/planning/exit_sim.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/planning/exit_sim_v2.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_verdict.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/backtesting/instrument/stats.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/reports/execution_fidelity_report.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/admin/api_v1/analytics.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/complexity_gate.py
```

Expected: nothing listed from `override_fidelity.py`, `override_verdict.py`, `execution_fidelity_report.py` or `v173_001_manual_bulk_retag.py`; any other line names a legacy function this plan did not touch (compare with `git -C $WT show main:<path>` run through the same radon command: the score is unchanged); `_close_plan`, `close_open`, `close_trade`, `close_trade_manual`, `record_transition` and the new `analytics_override_fidelity` do not appear (all below C); the gate passes.

- [ ] **Step 6: Fix any failure alone, then record**

A failing test is fixed in its own scoped commit on the branch (`fix(<area>): ... (v173)`) and re-run alone (`python $WT/scripts/dev/testrun.py file <test>` or the one `ng test --include <spec>`), never by re-running the whole suite. Record in the task report: the Python counts (passed / skipped / 0 failed / 0 xfailed), the Vitest count, the build result and the gate result.

- [ ] **Step 7: Commit**

Nothing to commit when the suite was green on the first run. Otherwise the fix commits of Step 6 are this task's commits, each ending with `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`; `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows no change from this task.

### Task V173-17: `/panel`, merge to `main`, release bump (bot minor, ui minor), push

**Model:** sonnet — panel findings and merge need judgement

**Files:**
- Modify: `VERSION.json` (two release lines: `bot` minor, then `ui` minor)
- Modify: `swingbot/admin/version_history.json` (regenerated after each release commit)
- Modify, only if `main` gained an Alembic revision since V173-5: `swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py` (`down_revision`)

**Interfaces:**
- Consumes: V173-16's green run on the branch; V173-5's `revision = "v173_001"` and its `down_revision`.
- Produces: local `main` carrying the merge and four release commits, **not yet pushed**. The push is V173-18 Step 3, after the data-revision checks: a push to `main` deploys, and the deploy runs `v173_001` on production. The ledger title keeps "push" because the push belongs to this release; it is made in V173-18.

- [ ] **Step 1: Run the panel over the full diff**

The spec carries `**Panel:** quant-researcher, quant-engineer, financial-advisor`. Run:

```
/panel quant-researcher,quant-engineer,financial-advisor main...2026-10-18-v173-execution-fidelity-overrides
```

with V173-16's recorded results and V173-15's measurement lines as context. Point the reviewers at the index's `## Review Focus` list (stamp never blocks a close; one quote for stamp and trade; refusal before any write; no lookahead in the two frames; one `costs.book` call per arm; verdict evaluated only under `--production`, written once; copy verbatim; cards below 640px). A `BLOCKING` finding stops this task: fix it on the branch as its own scoped commit (`fix(<area>): ... (v173 panel)`), re-run only the tests of the files it touched (`testrun.py file ...` / `ng test --include ...`), and re-run the panel for that role. Each `ADVISORY` finding is applied the same way or recorded with a one-line reason in the task report. A finding that would change a frozen constant (`DEAD_BAND`, `VERDICT_FLOOR`, `WEEK_FLOOR`, `EXCLUDED_CAP`, `SPLIT_TOLERANCE`, `LEDGER_ID`) is never applied here: it is a new spec, recorded as such. Expected: no unresolved `BLOCKING` finding.

- [ ] **Step 2: Bring `main` into the branch, then check the migration chain**

Follow the `worktree-lifecycle` skill (other sessions share `$R`). These steps run database tests (the disposable test DB): run `/replicate-prod-db` first if this task has not yet (once per task).

```bash
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides merge main -m "merge: main into v173 execution fidelity before release" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_migrations.py
```

Expected: `$R` has no pending change to this plan's files; the merge is clean or its conflicts are resolved file by file; `test_migrations.py` passes, which asserts one Alembic head (the test, not a bare `alembic heads` from another directory, is the check: `alembic.ini`'s `script_location` is cwd-relative). If `main` gained a revision after V173-5, set `down_revision` in `swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py` to that revision (`schema-evolution.md` § Revision ids), commit it on the branch (`fix(db): rebase v173_001 onto <rev>`), and re-run `tests/db/test_migrations.py` and `tests/db/test_v173_manual_bulk_retag.py` alone. Re-run alone the tests of any file the merge conflicted in. No full suite here: it ran in V173-16.

- [ ] **Step 3: Before running a data revision on production: the read-only checks**

`schema-evolution.md` § Before running a data revision on production: confirm the last PITR drill passed (`docs/deploy/DB_RESTORE.md`); the rollback is `scripts/ops/rollback_to.sh` to the second before the revision runs. These checks come **before** the merge into `main`, so nothing that would deploy the revision lands on `main` until they pass. All four are read-only:

```bash
grep -n "^### Drill\|^VERDICT" E:/Documents/Private/Projects/Discord-Bot/docs/deploy/DB_RESTORE.md
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && grep VERDICT logs/pitr_verify.log | tail -3"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T -u postgres db pgbackrest --stanza=swingbot info </dev/null"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash scripts/ops/rollback_to.sh '<UTC second>' --dry-run"
```

`<UTC second>` is a literal typed into the command, two minutes before now: print it locally first with `date -u -d '-2 minutes' '+%Y-%m-%d %H:%M:%S'` (never a `$(...)` inside the ssh string: the wrapper would expand it on this machine).

Expected:
1. `DB_RESTORE.md`: the last `### Drill` heading is followed by `VERDICT: PASS` (2026-10-01, v116 V116-10, when this plan was written).
2. `pitr_verify.log`: the newest `VERDICT <date> PASS` line, dated this month or last (the cron runs on the 1st).
3. `pgbackrest info`: status `ok`, a full or differential backup dated within the last 24 hours (nightly at 02:30 UTC), and a WAL archive range ending within the last few minutes.
4. The rollback dry run prints `Target ... resolves to:` with the code, bot image, db image, `.env` and market lines, then `Dry run: nothing changed.` (exit 0). A `REFUSE` line or a non-zero exit is a failed check.

Any failed check stops the task before Step 4: report it to the partner with `AskUserQuestion`, one question, recommended option first: "Fix the backup first (run the PITR drill or the failing backup), then release", then "Release anyway; the data revision touches only the 15 pinned rows and its downgrade reverts exactly them". Never proceed past a failed check without that answer. Record the four results in the task report; V173-18 Step 1 re-confirms them only if more than a day has passed.

- [ ] **Step 4: Merge the branch into `main` (local only)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot switch main
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-10-18-v173-execution-fidelity-overrides -m "merge: v173 execution fidelity (override stamp, manual_bulk retag, override replay and frozen verdict, report, API, Overrides vs engine panel)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -3
```

Expected: a merge commit on `main`. **Do not push.** No full suite after this merge (CLAUDE.md).

- [ ] **Step 5: Release the bot line (minor)**

Read the current values from disk (never from this plan): `python -c "import json; print(json.load(open(r'E:/Documents/Private/Projects/Discord-Bot/VERSION.json')))"`. Then bump `bot` by one minor and stamp it:

```bash
python - <<'EOF'
import datetime
import json
import pathlib

path = pathlib.Path(r"E:/Documents/Private/Projects/Discord-Bot/VERSION.json")
version = json.loads(path.read_text(encoding="utf-8"))
major, minor, _patch = (int(part) for part in version["bot"].split("."))
version["bot"] = f"{major}.{minor + 1}.0"
version["bot_updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
path.write_text(json.dumps(version, indent=2) + "\n", encoding="utf-8")
print(version["bot"])
EOF
git -C E:/Documents/Private/Projects/Discord-Bot diff VERSION.json
```

Expected: only the `bot` and `bot_updated` lines change. Commit, regenerate, commit (two commits, in this order), replacing `<bot version>` with the printed value:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add VERSION.json
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "release(bot): <bot version> -- manual closes stamp their exit price, bulk clears tagged manual_bulk (data revision v173_001), override-fidelity report and API (v173)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/build_version_matrix.py
git -C E:/Documents/Private/Projects/Discord-Bot add swingbot/admin/version_history.json
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "chore(bot): <bot version> -- manual closes stamp their exit price, bulk clears tagged manual_bulk (data revision v173_001), override-fidelity report and API (v173)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Release the ui line (minor)**

The same with `ui`/`ui_updated`:

```bash
python - <<'EOF'
import datetime
import json
import pathlib

path = pathlib.Path(r"E:/Documents/Private/Projects/Discord-Bot/VERSION.json")
version = json.loads(path.read_text(encoding="utf-8"))
major, minor, _patch = (int(part) for part in version["ui"].split("."))
version["ui"] = f"{major}.{minor + 1}.0"
version["ui_updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
path.write_text(json.dumps(version, indent=2) + "\n", encoding="utf-8")
print(version["ui"])
EOF
git -C E:/Documents/Private/Projects/Discord-Bot diff VERSION.json
git -C E:/Documents/Private/Projects/Discord-Bot add VERSION.json
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "release(ui): <ui version> -- Overrides vs engine panel on Analytics Execution, Bulk close exit label (v173)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/build_version_matrix.py
git -C E:/Documents/Private/Projects/Discord-Bot add swingbot/admin/version_history.json
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "chore(ui): <ui version> -- Overrides vs engine panel on Analytics Execution, Bulk close exit label (v173)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
```

Expected: only the `ui` lines change in the diff; the version-matrix test passes (the one check the pre-bump suite cannot make).

- [ ] **Step 7: Hand over to V173-18 without a gap**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline origin/main..main
```

Expected: the merge commit, the branch's commits and the four release commits, nothing else. Start V173-18 now, in this sitting.

- [ ] **Step 8: Commit**

The commits of Steps 2 and 4-6 are this task's commits (merge of `main` into the branch, the optional `down_revision` fix, the merge into `main`, `release(bot)`, `chore(bot)`, `release(ui)`, `chore(ui)`). `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows nothing from this task.

### Task V173-18: Deploy with the data revision on production; verify the 15 re-tags

**Model:** opus — a data revision run against production rows

**Files:**
- Create (session scratchpad only): `$SCRATCH/v173-verify-retag.py`
- None in the repo (VM only). Any live fix made on the VM is mirrored into this repo and committed on `main` before the task counts as done (`mirror-prod` skill).

**Interfaces:**
- Consumes: V173-17's unpushed `main` (merge plus four release commits) and its Step 3 check results; V173-5's `PINNED_PLAN_IDS: tuple[str, ...]` and `revision = "v173_001"` in `swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py`; § Pinned bulk-clear ids in the index (the 15 ids and their `at`, from V173-4).
- Produces: production at `v173_001` with exactly the 15 pinned plans' last transition reading `manual_bulk` (consumed by V173-19's report run); the recorded rollback second `T0`.

Invoke the `mirror-prod` skill before Step 3: this task changes production (a deploy and a data revision).

- [ ] **Step 1: Re-confirm the release state**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch origin
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline main..origin/main
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the `log` prints nothing (nobody pushed `main` since V173-17); `status` shows nothing of this plan's. If `origin/main` moved, merge it into `main` (`git -C $R merge origin/main -m "merge: origin/main before the v173 push"`, ending with the attribution `-m` line) and run `python $R/scripts/dev/testrun.py file tests/db/test_migrations.py` alone: a new revision on `origin/main` means `v173_001`'s `down_revision` is rebased onto it on `main` as its own commit (`fix(db): rebase v173_001 onto <rev>`), then `tests/db/test_migrations.py` and `tests/db/test_v173_manual_bulk_retag.py` re-run alone. If more than a day has passed since V173-17 Step 3, re-run its four checks now and stop on any failure as described there.

- [ ] **Step 2: Record the rollback second**

```bash
date -u '+%Y-%m-%d %H:%M:%S'
```

Write the printed value into the task report as `T0` (the second before the revision can run; the rollback target if Step 8 needs one). Nothing has deployed yet.

- [ ] **Step 3: Push and watch the deploy**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot push origin main
gh run list --branch main --limit 1
gh run watch <run id from the line above> --exit-status
```

Expected: every suite job, the frontend "Unit tests" and "Production build", and the deploy job succeed. A red test or build job means nothing deployed: fix it on `main` as its own scoped commit, push again, and watch again; never re-run blindly. A red **deploy** job goes to Step 8.

- [ ] **Step 4: Read what the revision did**

```bash
gh run view <run id> --log | grep -n "v173_001\|manual_bulk\|RuntimeError\|Running upgrade" | head -20
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current </dev/null"
```

Expected: a `Running upgrade <down_revision> -> v173_001` line and the revision's own line `v173_001: re-tagged 15 plans manual -> manual_bulk` (never `v173_001: none of the 15 pinned plans exist here ...`: production holds them; that line means a no-op and goes to Step 8); `alembic current` prints `v173_001 (head)`, or a later head whose chain contains `v173_001` if another plan's revision merged first (check with `docker compose exec -T bot alembic history -r v173_001: </dev/null`).

- [ ] **Step 5: Verify the 15 re-tags (read-only)**

Write `$SCRATCH/v173-verify-retag.py`:

```python
"""v173 V173-18: verify the manual_bulk retag on production. Read-only."""
import collections
import importlib.util
import pathlib

from swingbot.core.planning.plan_store import PlanStore

path = pathlib.Path("swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py")
spec = importlib.util.spec_from_file_location("v173_001_check", path)
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)
pinned = set(mig.PINNED_PLAN_IDS)

plans = {p.plan_id: p for p in PlanStore().all()}
last = {pid: (p.status_history[-1] if p.status_history else {})
        for pid, p in plans.items() if p.status == "CLOSED"}
reasons = collections.Counter(entry.get("reason") for entry in last.values())
bulk = {pid for pid, entry in last.items() if entry.get("reason") == "manual_bulk"}

print("pinned ids:", len(pinned))
print("manual_bulk rows:", len(bulk), "| equal to the pinned set:", bulk == pinned)
print("pinned missing from the book:", sorted(pinned - set(plans)))
print("manual rows:", reasons.get("manual", 0), "| CLOSED plans:", len(last))
for pid in sorted(pinned):
    entry = last.get(pid, {})
    print(" ", pid, entry.get("reason"), entry.get("at"))
label_id = next((pid for pid in sorted(pinned) if pid in plans and not plans[pid].legs_realized), None)
print("label check id:", label_id)
```

Pipe it in:

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < "$SCRATCH/v173-verify-retag.py"
```

Expected: `pinned ids: 15`; `manual_bulk rows: 15 | equal to the pinned set: True`; `pinned missing from the book: []`; the 15 listed lines read `manual_bulk` with `at` values matching § Pinned bulk-clear ids (2026-09-30 20:54–20:55 UTC); `manual rows` equals the individual manual closes (21 on 2026-10-17 per the Goal, plus any manual close made since; never fewer than 21); `label check id` is a plan id (needed by Step 7). Any other result goes to Step 8.

- [ ] **Step 6: Check the bot and admin came up clean**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --since 20m bot admin 2>&1 | grep -iE 'Traceback|override|v173' | tail -20"
```

Expected: `bot`, `admin` and `db` up (healthy where a health check exists); no traceback. A traceback is reported with its lines; production is never patched by hand.

- [ ] **Step 7: The "Bulk close" label on production at three widths**

```bash
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/browse.mjs shots --out "$SCRATCH/v173-prod-label" --path "trades/<label check id>" --widths 1280,768,390
```

`browse.mjs` signs in from `.env` itself (one attempt; it never prints the values) and falls back to a manual sign-in in the window. Expected: each `*.txt` starts with `page-scroll-x: 0` and contains `Bulk close`; open `trades_<id>@390.png` with the Read tool and confirm the Exit tile reads `Bulk close`. This is the label check of record when V173-15 Step 1 found no local plan.

- [ ] **Step 8: Only if a check failed: stop, then ask**

Never edit production rows by hand. Report what failed with its lines, then ask the partner with `AskUserQuestion`, one question, recommended option first:
- **The deploy job failed on the revision** (a `RuntimeError` refusal in the log): the refusal fires before any write, so the rows are as they were. Options: "Leave production as it is and investigate on a fresh replica (`/replicate-prod-db`)" (recommended), then "Roll the whole bot back to `T0` with `rollback_to.sh`".
- **The revision ran but the rows are wrong** (`manual_bulk` count not 15, set not equal, a `manual` count below 21): options: "Downgrade only the revision: `bash $R/scripts/ops/ssh-hetzner.sh \"cd /opt/swing-bot && docker compose exec -T bot alembic downgrade <down_revision> </dev/null\"` (reverts exactly the pinned entries; it refuses unless all 15 read `manual_bulk`)" (recommended), then "Roll the whole bot back to `T0`: dry run first (`bash scripts/ops/rollback_to.sh '<T0>' --dry-run` on the VM through `ssh-hetzner.sh`), then the real run" (whole-bot: Postgres, `market_data/`, `.env` and images return to `T0`; scanning starts paused).
- **A zero count with an "ids absent" no-op line**: production is missing the pinned ids, so V173-4's pin was wrong. Ask before anything else; the fix is a new revision with corrected ids, never an edit to `v173_001` after it ran.

Act only on the partner's answer. Any change that results is mirrored into the repo and committed on `main` as its own scoped commit (`fix(<area>): ... (v173, mirrored from production)`) before this task counts as done.

- [ ] **Step 9: Commit**

Nothing to commit when every check passed: this task changes production only. Record in the task report: `T0`, the CI run id, the `alembic current` line, Step 5's counts and Step 7's verdict. `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows nothing from this task.

### Task V173-19: First real report run on the VM

**Model:** sonnet — reads the real book's output and decides whether a ledger row must be mirrored

**Files:**
- Create (session scratchpad only): `$SCRATCH/v173-check-report.py`, `$SCRATCH/v173-report.json`, `$SCRATCH/v173-api.json`
- Modify: `docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md` (§ Progress, on `main`)
- Modify, only if the run evaluated the verdict: `docs/superpowers/results/preregistration-ledger.jsonl` (the mirrored row, on `main`)

**Interfaces:**
- Consumes: V173-18's deployed build with `v173_001` applied; V173-11's script `scripts/reports/execution_fidelity_report.py` (`--production`, `--json PATH`; without `--production` it prints `DEV_BANNER` and never writes the ledger; on an evaluating run it appends the ledger row and prints it as one JSON line); V173-12's `GET /api/v1/analytics/override-fidelity`; the payload contract of Global Constraints; V173-10's `LEDGER_ID = "v173-override-fidelity"`; V173-18 Step 5's `manual rows` count.
- Produces: the recorded first production output in § Progress; the mirrored ledger row if one was written.

Invoke the `pooled-numbers` skill before writing any figure from this run into § Progress or a commit: every figure is quoted with its N, window and source (this run, on the live book), and the ΣΔ figures are descriptive, not a verdict.

- [ ] **Step 1: Run the report on the VM with `--production`**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/execution_fidelity_report.py --production --json /tmp/v173-report.json </dev/null"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot cat /tmp/v173-report.json </dev/null" > "$SCRATCH/v173-report.json"
```

Expected: the printed output does **not** start with `DEV DATABASE: fixture data, not the real book. The ledger is never written.` (that banner on the VM means `--production` did not reach the script: stop and report); it prints the row table, the summary with its splits and the verdict state. The JSON file is non-empty. Keep the printed output in the task report.

- [ ] **Step 2: Fetch the same payload through the API**

```bash
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/browse.mjs api --path "api/v1/analytics/override-fidelity" > "$SCRATCH/v173-api.json"
```

`browse.mjs` signs in from `.env` itself and never prints the values; its status lines go to stderr, so the file holds only the JSON body.

- [ ] **Step 3: Check the output**

Write `$SCRATCH/v173-check-report.py`:

```python
"""v173 V173-19: check the first production report run and the API payload. Reads two JSON files."""
import collections
import json
import sys

STATUSES = {"resolved", "open", "stale", "ambiguous", "parity_mismatch", "split_affected", "unreplayable"}
PAYLOAD_KEYS = ["asof", "currency_symbol", "engine_flags", "rows", "summary", "verdict"]

report = json.load(open(sys.argv[1], encoding="utf-8"))
api = json.load(open(sys.argv[2], encoding="utf-8"))
rows = report["rows"]
summary, verdict = report["summary"], report["verdict"]

print("payload keys ok:", sorted(report) == PAYLOAD_KEYS, "| api keys ok:", sorted(api) == PAYLOAD_KEYS)
print("rows:", len(rows), "| bulk:", sum(r["bulk"] for r in rows), "| individual:", sum(not r["bulk"] for r in rows))
print("statuses:", dict(collections.Counter(r["status"] for r in rows)))
print("rows with an unknown status:", [r["plan_id"] for r in rows if r["status"] not in STATUSES])
print("individual approx:", sum(r["approx"] and not r["bulk"] for r in rows),
      "| individual stamped:", sum(not r["approx"] and not r["bulk"] for r in rows))
print("price_source:", dict(collections.Counter(r["price_source"] for r in rows)))
print("rows without dollars:", sum(r["delta_usd"] is None for r in rows))
print("summary:", {k: summary[k] for k in ("bulk_n", "bulk_dates", "approx_n", "counted_n", "sum_delta_r",
                                           "sum_delta_usd", "usd_missing_n", "helped", "hurt", "neutral")})
print("verdict:", verdict)
print("engine_flags:", report["engine_flags"], "| asof:", report["asof"], "| currency:", report["currency_symbol"])
print("api rows:", len(api["rows"]), "| api summary equal:", api["summary"] == summary,
      "| api verdict equal:", api["verdict"] == verdict)
```

```bash
python "$SCRATCH/v173-check-report.py" "$SCRATCH/v173-report.json" "$SCRATCH/v173-api.json"
```

Expected:
- `payload keys ok: True | api keys ok: True`.
- `bulk` 15 and `summary.bulk_dates` `{"2026-09-30": 15}`; `individual` equals V173-18 Step 5's `manual rows`; so every override in the book has a row.
- `rows with an unknown status: []` (each row carries exactly one of the seven statuses).
- Every individual close made before this deploy has no `override` stamp, so it is `approx` (`price_source` `session_open` or `session_close`); `individual stamped` counts only manual closes made after the V173-18 deploy (usually 0 on the first run).
- `counted_n` equals the number of individual stamped `resolved` rows; the verdict is `WAITING` with `n` = `counted_n`, `needed` 30, `week_floor` 10, `evaluable` false, `recorded` false (the floors cannot hold on the first run).
- `api rows` equals `rows`, and both `equal` flags are `True` (the API calls the same `build_report`; an `asof` change between the two calls is the only acceptable difference: re-run Steps 1-2 once if it happened across a session close).
- `engine_flags` echoes production's `STALL_EXIT_ENABLED` and `RUNNER_STRUCTURE_EXIT`; record them.

A row count, a status or a flag that misses its expectation is reported as a finding with the printed lines; it is never patched on the VM.

- [ ] **Step 4: Only if the run evaluated: mirror the ledger row**

On a first run this step does not apply: the verdict is `WAITING` and nothing is written. If Step 1 printed a ledger row (one JSON line with `"id": "v173-override-fidelity"`), the container's `docs/superpowers/results/preregistration-ledger.jsonl` now holds a row the repo does not. Mirror it (`mirror-prod`): append that printed line, byte for byte, as the last line of `$R/docs/superpowers/results/preregistration-ledger.jsonl` on `main`, then:

```bash
python -c "import pathlib; from swingbot.core.backtesting.instrument import stats; rows = stats.load_ledger(pathlib.Path(r'E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/preregistration-ledger.jsonl')); print(rows[-1]['id'], rows[-1]['verdict'], rows[-1]['n'])"
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/results/preregistration-ledger.jsonl
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v173): mirror the override-fidelity verdict ledger row from production" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot push origin main
```

Expected: the check prints `v173-override-fidelity <COST|SAVED|INCONCLUSIVE> <n>`; the push deploys the mirrored file, so the next redeploy keeps the row. The verdict is never recomputed: a later run returns the recorded row as is.

- [ ] **Step 5: The panel on production at three widths**

```bash
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/browse.mjs shots --out "$SCRATCH/v173-prod-panel" --path "analytics?tab=execution" --widths 1280,768,390
```

Expected: each `*.txt` starts with `page-scroll-x: 0` and contains `Overrides vs engine`, the badge `<counted_n> of 30 needed. No conclusion yet.`, `15 closes from one bulk clear on 2026-09-30 are not decisions, so they are left out`, and `<approx_n> estimated rows are shown but not counted` (with Step 3's values). Open `analytics_tab_execution@390.png` and `analytics_tab_execution@1280.png` with the Read tool and confirm cards at 390, the table at 1280, and the estimate label on the approx rows. If V173-15 could not run locally, this step is that check: record the measurements by eye in the task report.

- [ ] **Step 6: Record the run in § Progress and commit on `main`**

Replace the `## Progress` block's `Not started. Update this block when a phase closes.` line in `$R/docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md` with:

```markdown
First production report run <YYYY-MM-DD HH:MM UTC> (V173-19, `--production`, live book, bars as of <asof>): <rows> overrides = 15 bulk (2026-09-30) + <individual> individual (<approx> estimated, <stamped> stamped). Statuses: <statuses dict>. Counted <counted_n>; verdict WAITING (<counted_n> of 30, <weeks> of 10 weeks), nothing written to the ledger. Engine flags: <engine_flags>. API payload identical to the script's.
```

filled from Step 3's lines (add `ΣΔ <sum_delta_r> R / <sum_delta_usd> over the <counted_n> counted rows, descriptive only` only when `counted_n` > 0; if Step 4 applied, replace the verdict clause with the recorded row's verdict, `n` and date). Then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v173): first production override-fidelity report run recorded" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: one commit on `main` touching only the index (plus Step 4's commit if it applied); no push needed here (V173-20 pushes); `git status` shows nothing of this task's.

### Task V173-20: Close-out: move plan and spec to `implemented/`, remove worktree

**Model:** haiku — the close-out checklist

**Files:**
- Modify: `docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md` (`## Progress` block), then `git mv` it and every part file into `docs/superpowers/plans/implemented/`: `_0-index`, `_1-stamp-retag`, `_2-replay-core`, `_3-statuses-verdict`, `_4-report-api-ui`, `_5-check-release` (the index's `## Parts` table lists them)
- Move: `docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md` → `docs/superpowers/specs/implemented/`

**Interfaces:**
- Consumes: V173-15's measurement lines, V173-16's recorded counts, V173-17's panel result and release commits, V173-18's `T0`, CI run id and re-tag counts, V173-19's § Progress line.
- Produces: nothing; the plan leaves the live set and the SessionStart `PLAN WIP` line stops naming it.

- [ ] **Step 1: Run the `close-out` skill, with three of its steps already done**

Invoke `/close-out`. Its panel step ran in V173-17 Step 1, and its bump and regeneration steps ran in V173-17 Steps 5-6: confirm them from the log rather than repeating them:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -8 -- VERSION.json swingbot/admin/version_history.json
python -c "import json; print(json.load(open(r'E:/Documents/Private/Projects/Discord-Bot/VERSION.json')))"
```

Expected: `release(bot)`, `chore(bot)`, `release(ui)`, `chore(ui)` commits naming v173, and `VERSION.json` showing both lines one minor above the values before V173-17. Do not bump again. The header said `Bump: bot minor; ui minor` and `Edge: none (integrity)`; both held, so nothing is amended (if one did not, amend the index header and say why in one clause in Step 4's commit). The plan is integrity work, so it goes to `implemented/`, never `no-lift/`.

- [ ] **Step 2: Record the results in the index**

In `$R/docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md`, put this line at the top of the `## Progress` block, above V173-19's first-run line (which stays):

```markdown
Done <YYYY-MM-DD>. V173-1..V173-20 complete. Three-width check (V173-15): <local | production only>, every line met. Full suite (V173-16): Python <passed> passed, <skipped> skipped, 0 failed, 0 xfailed; Vitest <n> passed; production build green; complexity gate green. Panel (V173-17): <n> BLOCKING resolved, <n> ADVISORY (<applied>/<recorded>). Released bot <version>, ui <version>. Deploy (V173-18): CI run <id>, rollback second T0 <T0>, Alembic at v173_001, 15 pinned plans read manual_bulk, "Bulk close" shown at three widths.
```

filled from the task reports.

- [ ] **Step 3: Remove the worktree and its branch**

The branch name contains no `backup` and is not `stable-*`. Check it is fully merged first; non-zero means stop and ask the partner:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot rev-list --count main..2026-10-18-v173-execution-fidelity-overrides
git -C E:/Documents/Private/Projects/Discord-Bot worktree remove .claude/worktrees/2026-10-18-v173-execution-fidelity-overrides
git -C E:/Documents/Private/Projects/Discord-Bot branch -d 2026-10-18-v173-execution-fidelity-overrides
git -C E:/Documents/Private/Projects/Discord-Bot worktree list
```

Expected: `0`; the worktree and branch are gone (`branch -d`, never `-D`); `worktree list` no longer shows it. A `worktree remove` that refuses because of untracked files means something was left uncommitted: look at it before deciding, never `--force` by default.

- [ ] **Step 4: Move the documents, commit and push on `main`**

```bash
ls E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_*.md
for f in E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_*.md; do git -C E:/Documents/Private/Projects/Discord-Bot mv "$f" E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/plans/implemented/; done
git -C E:/Documents/Private/Projects/Discord-Bot mv docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md docs/superpowers/specs/implemented/
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/plans/implemented/2026-10-18-v173-execution-fidelity-overrides_0-index.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v173): close out -- plan and spec to implemented/, results recorded" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot push origin main
```

The § Progress edit from Step 2 rides in this commit (staged by the final `git add` after the move). Expected: the `ls` lists exactly the six files of the index's `## Parts` table (a missing or an extra file is checked before moving); one commit that moves the six plan files and the spec and changes the index's Progress block; `git status` clean for these paths; the push carries V173-19's commit too. No full suite after this (CLAUDE.md: it ran once, in V173-16).
