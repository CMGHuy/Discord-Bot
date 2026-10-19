# v173 Execution fidelity, part 5: three-width check, full suite, release, deploy with both revisions, VM report, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-18:" -A 220 docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_5-check-release.md`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §2 (the retag on production), §4 (the verdict table and the daily trigger), §5 (checks at three widths, the VM run), § Testing, § Risks, `## Plan panel review`, `**Panel:**` line
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work`, § Pinned bulk-clear ids, the task ledger and § Revision 2026-10-19 (this part's six tasks were rewritten in place on 2026-10-19 to the Postgres verdict store, the daily evaluator and the second revision). Every task below implicitly includes those Global Constraints.

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`, branch `2026-10-18-v173-execution-fidelity-overrides`. `$SCRATCH` is the implementing session's scratchpad (absolute path): browser and VM scripts live there and nothing in it is committed. Never `cd`; use absolute paths and `git -C`. Production is reached only through `bash $R/scripts/ops/ssh-hetzner.sh "<cmd>"` (stdin for a script: `... "cd /opt/swing-bot && docker compose exec -T bot python -" < $SCRATCH/x.py`); any live change made there is mirrored into this repo and committed before its task counts as done (`mirror-prod` skill). A browser is driven with Playwright only, and every login loads `ADMIN_USERNAME`/`ADMIN_PASSWORD` from `.env` inside the script: never printed, echoed, passed on a command line or written to another file.

Tasks: V173-15..V173-20. **A push to `main` deploys** (`.github/workflows/deploy.yml` runs on every push to `main`, and `deploy/deploy.sh` runs `alembic upgrade head`), so both revisions run on production at the push: the data revision `v173_001` (re-tags the 15 pinned rows) and then the additive `v173_002` (creates the empty `preregistration_verdicts` table). That is why V173-17 merges and bumps on `main` **without pushing**, and V173-18 pushes only after the `schema-evolution.md` § Before running a data revision on production checks pass. Run V173-17 and V173-18 back to back in one sitting: `$R` is shared, and another session's push of `main` would carry the unpushed merge out with it.

**Names this part relies on, from other parts** (all final in the index ledger): the CLI `scripts/reports/execution_fidelity_report.py` with `--production`, `--json PATH` and `--mirror-row` (V173-11; banner `DEV DATABASE: fixture data, not the real book. This report never writes a verdict.`); the panel `sb-override-fidelity-panel` with cards `<li class="card">` in `<ul class="cards">` and caption element `.caption` (V173-14); the table `preregistration_verdicts` and revision `v173_002` (V173-24); the loop `override_verdict_check` and its log line `override_verdict_check: <result>` with `<result>` one of `recorded`, `already recorded`, `waiting` (V173-26, V173-27); `override_verdict.mirror_ledger_row` and `RESULTS_RECORD = "docs/superpowers/results/v173-override-fidelity.md"` (V173-10).

# Phase 5: Check, verify, release, run, close out (V173-15..V173-20)

### Task V173-15: Three-width Playwright check of the panel and the "Bulk close" label

**Model:** sonnet — run the app and judge layout at three widths

**Files:**
- Create (session scratchpad only, never the repo): `$SCRATCH/v173-widths.cjs`
- Modify, only if a check fails: the V173-14 files `frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts` (styles, template), `frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts` (copy) and their specs `override-fidelity-panel.spec.ts`, `override-fidelity.model.spec.ts`

**Interfaces:**
- Consumes: V173-14's `OverrideFidelityPanel` (selector `sb-override-fidelity-panel`; cards `<li class="card">` in `<ul class="cards">`; caption element `.caption`) mounted in `execution.ts`; V173-13's store slice, which calls `GET /api/v1/analytics/override-fidelity`; the payload contract of Global Constraints (keys `rows, summary, verdict, engine_flags, asof, currency_symbol`; the 20 row keys with `delta_r_gross`; the 13 summary keys with `sum_delta_r_gross`; the 17 verdict keys with `waiting_on`, `mean_delta_r_gross`, `sum_delta_r`, `sum_delta_usd`, `bar_close_n`); the UI copy of Global Constraints, verbatim; V173-2's label `manual_bulk: 'Bulk close'` in `exit-reasons.ts`, which `outcome-tiles.ts` shows from the last `status_history` reason when no leg has a reason.
- Produces: the measurement lines and the screenshot verdict, recorded in the task report (V173-20 copies the summary into § Progress).

The override endpoint is stubbed in the browser with four fixture payloads, so the check covers every badge state without the local database holding overrides: `waiting` (2 counted, under the floor), `waitingOn` (31 counted, not evaluable: the "waiting on other conditions" line), `cost` (a recorded COST verdict: the recorded line and the "live, may have moved" hint) and `empty`. Five rows, so the pager (hidden at five rows or fewer) never hides a card. The trade-page check rewrites one real local response so its last transition reads `manual_bulk`. Everything else is the real local admin.

Two checks are new on 2026-10-19 (financial-advisor, plan panel): **the caption** at 390px must be visible, unclipped (`scrollWidth <= clientWidth` and `scrollHeight <= clientHeight`), inside the viewport, at a font size no smaller than the panel's body text and coloured `var(--text-secondary)`; **the net-effect tile is not tinted while WAITING**: its background, border and value colour equal those of the neutral `Overrides counted` tile.

- [ ] **Step 1: Pick one local plan for the label check**

The local admin reads the working database named in `.env`. Find a CLOSED plan with no realised legs (the trade page then falls back to the last transition's reason):

```bash
PYTHONPATH=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides python -c "from swingbot.core.planning.plan_store import PlanStore; print(next((p.plan_id for p in PlanStore().all() if p.status == 'CLOSED' and not p.legs_realized and p.status_history), 'NONE'))"
```

Expected: one plan id (not a secret; it goes on the Step 4 command line). `NONE` means the local book has no such plan: pass `NONE` in Step 4 (the label half is skipped) and V173-18 Step 8 checks the label on production instead. Say which in the task report.

- [ ] **Step 2: Start the local admin and the dev server**

Start both in the background (Bash `run_in_background: true`, one call each):

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/admin_ui.py
```

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng serve --port 4123
```

`$WT` has no `.env` of its own and none is copied there (credentials are never written to another file): `swingbot/config.py` tries `$WT/.env`, then falls back to `load_dotenv()`, which walks up from the module to `$R/.env`. Read the admin's first output lines: the warning that the admin runs on the default `admin`/`admin` credentials (`config.py:1590`) means it did **not** load `.env`; stop both servers and report it rather than checking against the default. Wait until `curl -s -o /dev/null -w "%{http_code}" http://localhost:4123/app/` prints `200`. If the admin cannot reach its database and exits, stop, say so in the task report, and leave the check to V173-19 Step 6 (production); never skip it silently.

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
  actual_r: 0, engine_r: 0, delta_r: 0, delta_r_gross: 0, actual_usd: 0, engine_usd: 0, delta_usd: 0,
  engine_exit_reason: 'runner_tp2', outcome: 'neutral', source: 'manual', ...o,
});

const ROWS = [
  row({ plan_id: 'p1', ticker: 'AAPL', actual_r: 0.42, engine_r: 1.1, delta_r: -0.68, delta_r_gross: -0.66,
        actual_usd: 84, engine_usd: 220, delta_usd: -136, outcome: 'hurt' }),
  row({ plan_id: 'p2', ticker: 'MSFT', horizon: '2w', state_at_close: 'PARTIAL', close_date: '2026-10-14',
        actual_r: 1.21, engine_r: 0.9, delta_r: 0.31, delta_r_gross: 0.33,
        actual_usd: null, engine_usd: null, delta_usd: null, engine_exit_reason: 'runner_trail', outcome: 'helped' }),
  row({ plan_id: 'p3', ticker: 'NVDA', close_date: '2026-09-22', approx: true, price_source: 'session_close',
        actual_r: -0.3, engine_r: -0.18, delta_r: -0.12, delta_r_gross: -0.11,
        actual_usd: -60, engine_usd: -36, delta_usd: -24, engine_exit_reason: 'timeout', outcome: 'hurt' }),
  row({ plan_id: 'p4', ticker: 'XLE', close_date: '2026-09-30', bulk: true, approx: true,
        price_source: 'session_close', actual_r: 0.1, engine_r: 0.6, delta_r: -0.5, delta_r_gross: -0.49,
        actual_usd: 20, engine_usd: 120, delta_usd: -100, outcome: 'hurt' }),
  row({ plan_id: 'p5', ticker: 'TSLA', close_date: '2026-10-08', status: 'ambiguous',
        actual_r: 0.2, engine_r: null, delta_r: null, delta_r_gross: null,
        actual_usd: 40, engine_usd: null, delta_usd: null, engine_exit_reason: null, outcome: null }),
];

const split = (n, r, usd) => ({ n, sum_delta_r: r, sum_delta_usd: usd });
const SUMMARY = {
  n_by_status: { resolved: 2, ambiguous: 1 }, bulk_n: 1, bulk_dates: { '2026-09-30': 1 },
  approx_n: 1, counted_n: 2, sum_delta_r: -0.37, sum_delta_r_gross: -0.33, sum_delta_usd: -136,
  usd_missing_n: 1, helped: 1, hurt: 1, neutral: 0,
  splits: {
    state_at_close: { ACTIVE: split(1, -0.68, -136), PARTIAL: split(1, 0.31, null) },
    horizon: { '4w': split(1, -0.68, -136), '2w': split(1, 0.31, null) },
    direction: { bullish: split(2, -0.37, -136) },
  },
};
const NOT_RECORDED = { recorded: false, recorded_on: null, mean_delta_r: null, mean_delta_r_gross: null,
  ci: null, sum_delta_r: null, sum_delta_usd: null };
const WAITING = { state: 'WAITING', n: 2, needed: 30, weeks: 2, week_floor: 10, open_n: 0,
  excluded_share: 0.333, evaluable: false, waiting_on: ['count', 'weeks', 'excluded'], bar_close_n: 0,
  ...NOT_RECORDED };
const WAITING_ON = { ...WAITING, n: 31, weeks: 7, excluded_share: 0.25, waiting_on: ['weeks', 'excluded'] };
const COST = { state: 'COST', n: 34, needed: 30, weeks: 12, week_floor: 10, open_n: 0,
  excluded_share: 0.1, evaluable: true, waiting_on: [], recorded: true, recorded_on: '2027-03-01',
  mean_delta_r: -0.08, mean_delta_r_gross: -0.05, ci: [-0.15, -0.01], sum_delta_r: -2.72,
  sum_delta_usd: -544, bar_close_n: 2 };
const base = { engine_flags: { stall_exit_enabled: true, runner_structure_exit: 'off' },
  asof: '2026-10-19', currency_symbol: '$' };
const PAYLOADS = {
  waiting: { ...base, rows: ROWS, summary: SUMMARY, verdict: WAITING },
  waitingOn: { ...base, rows: ROWS, summary: { ...SUMMARY, counted_n: 31 }, verdict: WAITING_ON },
  cost: { ...base, rows: ROWS,
          summary: { ...SUMMARY, counted_n: 36, sum_delta_r: -2.9, sum_delta_usd: -580 }, verdict: COST },
  empty: { ...base, rows: [],
           summary: { ...SUMMARY, n_by_status: {}, bulk_n: 0, bulk_dates: {}, approx_n: 0, counted_n: 0,
                      sum_delta_r: 0, sum_delta_r_gross: 0, sum_delta_usd: 0, usd_missing_n: 0,
                      helped: 0, hurt: 0, neutral: 0, splits: { state_at_close: {}, horizon: {}, direction: {} } },
           verdict: { ...WAITING, n: 0, weeks: 0, excluded_share: 0, waiting_on: ['count', 'weeks'] } },
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
  const tiles = grid ? [...grid.children] : [];
  const tileRows = grid ? new Set(tiles.map((c) => Math.round(c.getBoundingClientRect().top))).size : null;
  // A tile's tone: its background, its border and the colour of its largest text.
  const tone = (t) => {
    if (!t) return null;
    const big = [...t.querySelectorAll('*')].filter((e) => e.children.length === 0 && e.textContent.trim())
      .sort((a, b) => parseFloat(getComputedStyle(b).fontSize) - parseFloat(getComputedStyle(a).fontSize))[0] ?? t;
    const s = getComputedStyle(t);
    return [s.backgroundColor, s.borderTopColor, getComputedStyle(big).color].join(' | ');
  };
  const netTone = tone(tiles[0]);              // tile order: net effect first
  const countedTone = tone(tile);
  const badge = leaf('No conclusion yet') ?? leaf('vs the engine');
  const touch = [...host.querySelectorAll('button, a, [role=button], summary')].filter(visible)
    .map((e) => Math.round(e.getBoundingClientRect().height));
  const table = host.querySelector('table');
  const cards = [...host.querySelectorAll('ul.cards > li.card')].filter(visible);
  const cap = host.querySelector('.caption');
  const probe = document.createElement('span');
  probe.style.color = 'var(--text-secondary)';
  host.appendChild(probe);
  const secondary = getComputedStyle(probe).color;
  probe.remove();
  const capRect = cap?.getBoundingClientRect();
  const caption = cap ? {
    visible: visible(cap) && getComputedStyle(cap).visibility !== 'hidden',
    unclipped: cap.scrollWidth <= cap.clientWidth && cap.scrollHeight <= cap.clientHeight,
    inViewport: capRect.left >= 0 && capRect.right <= window.innerWidth,
    fontPx: parseFloat(getComputedStyle(cap).fontSize),
    bodyPx: parseFloat(getComputedStyle(host).fontSize),
    secondaryColour: getComputedStyle(cap).color === secondary,
  } : null;
  return {
    panel: true,
    pageOverflowPx: Math.max(doc.scrollWidth - doc.clientWidth, document.body.scrollWidth - document.body.clientWidth),
    tileRows,
    netToneEqualsNeutral: netTone !== null && netTone === countedTone,
    badgeText: badge?.textContent.trim() ?? null,
    badgeTruncated: badge ? badge.scrollWidth > badge.clientWidth + 1 || getComputedStyle(badge).textOverflow === 'ellipsis' : null,
    tableVisible: visible(table),
    cardCount: cards.length,
    firstCard: cards[0]?.innerText.split('\n').map((s) => s.trim()).filter(Boolean).slice(0, 4) ?? null,
    smallestTouchPx: touch.length ? Math.min(...touch) : null,
    caption,
    text: host.innerText,
  };
}

const CAPTION = "Compares the overrides you made with what the engine would have done. Past closes only, not advice on future ones. A close for a reason the engine cannot see (a gap, earnings, needing the cash) can still be right. Figures are after modelled costs and before tax. Dollars use the plan's modelled position size. Closing early can also change the tax holding period. There is no target number of overrides.";
const COPY = ['Overrides vs engine', 'Overrides counted', 'Helped / hurt / neutral', 'counts ignore size', CAPTION,
  '1 close from one bulk clear on 2026-09-30 is not a decision, so it is left out',
  '1 estimated row is shown but not counted', 'estimated exit: daily close, not your fill'];
const EXPECT = {
  waiting: [...COPY, '2 of 30 needed. No conclusion yet.'],
  waitingOn: [...COPY, '31 of 30 counted. Waiting on other conditions. No conclusion yet.',
    'Waiting on: at least 10 distinct weeks (now 7); left-out rows at most 20% (now 25%)'],
  cost: [...COPY, 'Your overrides cost $', 'R) vs the engine',
    'Recorded on 2027-03-01 from 34 overrides over 12 weeks: mean', 'R per override, 95% CI',
    'Before costs:', '2 overrides priced from a bar close, not a quote.',
    'live, may have moved since recorded on 2027-03-01'],
  empty: ['Overrides vs engine', 'No manual overrides in scope.'],
};
const AMBIGUOUS_NOTE = /1 .+ row is left out/;   // the TSLA row, under its STATUS_LABEL

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  let variant = 'waiting';
  await page.route('**/api/v1/analytics/override-fidelity**', (route) => route.fulfill({ json: PAYLOADS[variant] }));
  await login(page);
  for (const v of ['waiting', 'waitingOn', 'cost', 'empty']) {
    variant = v;
    for (const width of [1280, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`${BASE}/app/analytics?tab=execution`, { waitUntil: 'load' });
      await page.waitForSelector('sb-override-fidelity-panel', { timeout: 60000 });
      await page.waitForTimeout(1200);
      const m = await page.evaluate(measure);
      const flat = (m.text ?? '').replace(/\s+/g, ' ');
      const missing = EXPECT[v].filter((s) => !flat.includes(s));
      if (v !== 'empty' && !AMBIGUOUS_NOTE.test(flat)) missing.push('1 <ambiguous label> row is left out');
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

The `.env` path is a path, not a secret; the script reads the two values itself and never prints them. Expected, one line per variant and width (twelve panel lines, plus three `label` lines unless `NONE`):
- Every panel line: `panel` true, `pageOverflowPx` 0, `missing` `[]`.
- Every `waiting`, `waitingOn` and `empty` line: `netToneEqualsNeutral` true (the net-effect tile is neutral-toned while WAITING). The `cost` lines may read either value; record it.
- Every line at 390 (and at 768 and 1280, recorded the same way): `caption.visible`, `caption.unclipped`, `caption.inViewport` and `caption.secondaryColour` true, and `caption.fontPx >= caption.bodyPx`. The `empty` variant may render no caption (`caption` `null`) only if V173-14's empty state omits it; record which.
- `waiting`, `waitingOn` and `cost` at 390: `tileRows` 2 (four tiles, two per row), `badgeTruncated` false, `tableVisible` false, `cardCount` 5, and `firstCard` leads with `AAPL`, then the close date `2026-10-20` (in whatever display form the panel uses), then the Δ in `$` and `R` (`-136` dollars and `-0.68 R` in the form `signedUsd`/`signedR` print).
- The same variants at 768 and 1280: `tileRows` ≤ 2, `badgeTruncated` false, `tableVisible` true.
- `smallestTouchPx` ≥ 44 at 390 wherever it is not `null` (with five rows the pager is hidden; the retry button only shows on an error).
- `label` lines: `bulkClose` true at every width.

If `cardCount` is 0 at 390 or `caption` is `null` on a non-empty variant, V173-14 drifted from the ledger contract (`<li class="card">` in `<ul class="cards">`, caption `.caption`): read the class from `override-fidelity-panel.ts`, report the drift, and change the selector in the scratch script only; never rename the component's class to suit the script.

- [ ] **Step 5: Look at the screenshots**

Open with the Read tool: `waiting-390.png`, `waiting-768.png`, `waiting-1280.png`, `waitingOn-390.png`, `cost-390.png`, `cost-1280.png`, `empty-390.png`, and `trade-390.png` when it exists (all under `$SCRATCH/v173-widths/`). Confirm by eye: the net-effect tile leads (`±$X · ±Y R`) and carries no green or red while WAITING; the badge sits whole at 390, with the `Waiting on:` line under it in `waitingOn`; the recorded line and the `live, may have moved since recorded on 2027-03-01` hint show in `cost`; each card shows ticker, close date and Δ on top with engine exit, status and the estimate label on the lines below; the NVDA row carries `estimated exit: daily close, not your fill`; the MSFT row shows `—` for its dollars; the exclusion notes read in the singular; the caption reads at the body-text size, in the secondary colour, not cut off; the trade page's Exit tile reads `Bulk close`.

- [ ] **Step 6: Fix, re-check, stop the servers**

A failed expectation is fixed in `override-fidelity-panel.ts` (styles or template; media queries only at 639/640/1023/1024/1439/1440/1919/1920) or, for copy, in `override-fidelity.model.ts`, with an assertion added to the matching spec for the fixed behaviour wherever a unit test can see it (copy, card structure, the neutral tone while WAITING). Never edit `EXPECT` or `CAPTION` to match the page: they are the spec's verbatim copy. Then:

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts --include src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts --include src/app/workspaces/analytics/tabs/execution.spec.ts
```

Expected: PASS. Re-run Step 4 until every line meets its expectation. Stop both background servers afterwards. Record the measurement lines in the task report.

- [ ] **Step 7: Commit (only if Step 6 changed a file)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "fix(ui): override panel at <width> -- <what was wrong> (v173 three-width check)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: one commit on the branch, or none when every check passed first time; `$R`'s status shows no change from this task (the scratch script and the screenshots stay in `$SCRATCH`).

### Task V173-16: Full suite (Python + frontend)

**Model:** haiku — run and record, no judgement

**Files:** none (a failure is fixed in the file that broke, as its own scoped commit, then re-run alone)

**Interfaces:**
- Consumes: every commit of V173-1..V173-15 and V173-21..V173-27 on the branch (revised 2026-10-19: the `indicator_df` keyword, data admission, bar-state ambiguity, the `preregistration_verdicts` table and `v173_002`, the repository, `override_io` and the `override_verdict_check` loop).
- Produces: the recorded green counts V173-20 writes into the index's `## Progress`.

- [ ] **Step 1: Check the branch is complete and clean**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides status --short
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides log --oneline main..HEAD
```

Expected: no uncommitted change; at least one commit for each code task V173-1..V173-3, V173-5..V173-14 and V173-21..V173-27 (V173-4 committed on `main`; V173-15 has a commit only if it fixed something). A missing task is reported, not written here.

- [ ] **Step 2: Confirm the exit engine's existing tests are untouched**

The Review Focus for V173-6 and V173-21 is zero behaviour change in `walk_v2`/`simulate_exit_v2`, proven by every existing exit test passing **unchanged**:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides diff --stat main...HEAD -- tests/planning tests/backtesting "tests/test_exit_sim*"
```

Expected: the only files listed are the ones the ledger creates or modifies (`tests/planning/test_record_transition_extra.py`, `tests/planning/test_exit_sim_v2_replay_hooks.py`, `tests/planning/test_exit_sim_v2_indicator_frame.py`, `tests/backtesting/test_instrument_stats_ledger.py`); no existing `test_exit_sim*` file, and not the scale-out witness `tests/test_exit_sim_scaleout_witness.py`. Anything else listed is reported as a finding, not fixed here.

- [ ] **Step 3: Run the Python full suite once, with the test database up**

CLAUDE.md: a task that runs tests against the database runs `/replicate-prod-db` first, so run it (it syncs the local replica; the suite itself never reads the replica). Five v173 test files open the disposable test database: `tests/db/test_v173_002_preregistration_verdicts.py` (`db_engine_empty`), `tests/db/test_preregistration_verdicts_repository.py` (`db_conn`), `tests/commands/test_override_verdict_loop.py` (the root autouse `_store_database`, for `scheduled_jobs`), plus the existing `tests/db/test_migrations.py` and `tests/db/test_v172_tables.py`, which now upgrade and downgrade through `v173_001` and `v173_002`. Start it first:

```bash
docker compose -f E:/Documents/Private/Projects/Discord-Bot/docker-compose.yml --profile test up -d db-test
```

Then dispatch the `test-runner` subagent (so none of the output lands in this context) with: run `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py full` with `db-test` up; report the pass/fail/xfail/skip counts, the node ids of any skip naming `db-test`, and the first failure's node id and assertion only.

Expected: `0 failed` and `0 xfailed`, and no skip naming `db-test` (a DB-skipped run does not count: start `db-test` and re-run). A changed pass count against the last baseline is not a failure (`testing-cost.md`).

- [ ] **Step 4: Run the frontend suite and the production build once**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend run build
```

Expected: Vitest `0 failed`; the build ends without errors (CI runs the same two commands).

- [ ] **Step 5: Complexity of every Python function the plan wrote or changed**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/planning/plan_types.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/admin/api_v1/trade_commands.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/tracking/performance.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/partials.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/planning/exit_sim.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/planning/exit_sim_v2.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_verdict.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_io.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/backtesting/instrument/stats.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/db/repositories/preregistration_verdicts.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/commands/scanning/loops.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/reports/execution_fidelity_report.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/admin/api_v1/analytics.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/db/migrations/versions/v173_002_preregistration_verdicts.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/complexity_gate.py
```

Expected: nothing listed from `override_fidelity.py`, `override_verdict.py`, `override_io.py`, `preregistration_verdicts.py`, `execution_fidelity_report.py`, `v173_001_manual_bulk_retag.py` or `v173_002_preregistration_verdicts.py`; any other line names a legacy function this plan did not touch (compare with `git -C $WT show main:<path>` run through the same radon command: the score is unchanged); `_close_plan`, `close_open`, `close_trade`, `close_trade_manual`, `record_transition`, `walk_v2`, `_runner_v2`, `override_verdict_check` and `analytics_override_fidelity` do not appear (all below C); the gate passes.

- [ ] **Step 6: Fix any failure alone, then record**

A failing test is fixed in its own scoped commit on the branch (`fix(<area>): ... (v173)`) and re-run alone (`python $WT/scripts/dev/testrun.py file <test>` or the one `ng test --include <spec>`), never by re-running the whole suite. Record in the task report: the Python counts (passed / skipped / 0 failed / 0 xfailed), the Vitest count, the build result and the gate result.

- [ ] **Step 7: Commit**

Nothing to commit when the suite was green on the first run. Otherwise the fix commits of Step 6 are this task's commits, each ending with `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`; `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows no change from this task.

### Task V173-17: `/panel`, merge to `main`, release bump (bot minor, ui minor), push

**Model:** sonnet — panel findings and merge need judgement

**Files:**
- Modify: `VERSION.json` (two release lines: `bot` minor, then `ui` minor)
- Modify: `swingbot/admin/version_history.json` (regenerated after each release commit)
- Modify, only if `main` gained an Alembic revision since V173-5: `swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py` (`down_revision`, its docstring `Revises:` line, and the `== "v172_001"` assertion in `tests/db/test_v173_manual_bulk_retag.py::test_it_chains_onto_an_existing_revision`)

**Interfaces:**
- Consumes: V173-16's green run on the branch; V173-5's `revision = "v173_001"` with `down_revision = "v172_001"`; V173-24's `revision = "v173_002"` with `down_revision = "v173_001"`.
- Produces: local `main` carrying the merge and four release commits, **not yet pushed**. The push is V173-18 Step 3, after the data-revision checks: a push to `main` deploys, and the deploy runs `v173_001` and `v173_002` on production. The ledger title keeps "push" because the push belongs to this release; it is made in V173-18.

- [ ] **Step 1: Run the panel over the full diff**

The spec carries `**Panel:** quant-researcher, quant-engineer, financial-advisor`. Run:

```
/panel quant-researcher,quant-engineer,financial-advisor main...2026-10-18-v173-execution-fidelity-overrides
```

with V173-16's recorded results and V173-15's measurement lines as context. Point the reviewers at the index's `## Review Focus` list: the stamp never blocks a close; one quote for stamp and trade; the retag refuses before any write and reads with `FOR UPDATE`; no lookahead (bars trimmed to `asof`, the clamped engine frame walked with real-frame indicators, parity and ambiguity on the real frame, the truncation test); one `costs.book` call per arm; breakeven arming or a stop move on the override bar is `ambiguous`; `v173_002` equals `schema.py`; **the verdict is evaluated only by `override_io.run_daily_check`, called only by the `override_verdict_check` loop, and the `preregistration_verdicts` primary key makes it one evaluation ever; the script and the API only read**; copy verbatim; cards below 640px; the caption legible at 390px. A `BLOCKING` finding stops this task: fix it on the branch as its own scoped commit (`fix(<area>): ... (v173 panel)`), re-run only the tests of the files it touched (`testrun.py file ...` / `ng test --include ...`), and re-run the panel for that role. Each `ADVISORY` finding is applied the same way or recorded with a one-line reason in the task report. A finding that would change a frozen constant (`DEAD_BAND`, `VERDICT_FLOOR`, `WEEK_FLOOR`, `EXCLUDED_CAP`, `SPLIT_TOLERANCE`, `LEDGER_ID`) is never applied here: it is a new spec, recorded as such. Expected: no unresolved `BLOCKING` finding.

- [ ] **Step 2: Bring `main` into the branch, then check the migration chain**

Follow the `worktree-lifecycle` skill (other sessions share `$R`). These steps run database tests (the disposable test DB, `docker compose --profile test up -d db-test`): run `/replicate-prod-db` first if this task has not yet (once per task).

```bash
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides merge main -m "merge: main into v173 execution fidelity before release" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_migrations.py
```

Expected: `$R` has no pending change to this plan's files; the merge is clean or its conflicts are resolved file by file; `test_migrations.py` passes, which asserts one Alembic head (the test, not a bare `alembic heads` from another directory, is the check: `alembic.ini`'s `script_location` is cwd-relative).

**If `main` gained a revision after V173-5** (`test_exactly_one_head` fails with two heads: `v173_002` and `main`'s new one): re-chain **only `v173_001`**. Set its `down_revision` and docstring `Revises:` line to `main`'s new head (`schema-evolution.md` § Revision ids) and the `== "v172_001"` assertion in `test_it_chains_onto_an_existing_revision` to match; `v173_002.down_revision` stays `"v173_001"` and its file is not touched, so the chain reads `<main's head> -> v173_001 -> v173_002`. Commit it on the branch (`fix(db): rebase v173_001 onto <rev>`), then re-run alone:

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_migrations.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_v173_manual_bulk_retag.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_v173_002_preregistration_verdicts.py
```

Expected: all three PASS with no skip naming `db-test`; `v173_002` is still the single head. Re-run alone the tests of any other file the merge conflicted in. No full suite here: it ran in V173-16.

- [ ] **Step 3: Before running a data revision on production: the read-only checks**

`schema-evolution.md` § Before running a data revision on production: confirm the last PITR drill passed (`docs/deploy/DB_RESTORE.md`); the rollback is `scripts/ops/rollback_to.sh` to the second before the revisions run. The deploy runs **two** revisions in one `alembic upgrade head`: `v173_001` (data: re-tags the 15 pinned `status_history` entries; its downgrade reverts exactly them) and `v173_002` (additive: creates the empty `preregistration_verdicts` table; its downgrade drops it). These checks come **before** the merge into `main`, so nothing that would deploy either revision lands on `main` until they pass. All four are read-only:

```bash
grep -n "^### Drill\|^VERDICT" E:/Documents/Private/Projects/Discord-Bot/docs/deploy/DB_RESTORE.md
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && grep VERDICT logs/pitr_verify.log | tail -3"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T -u postgres db pgbackrest --stanza=swingbot info </dev/null"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash scripts/ops/rollback_to.sh '<UTC second>' --dry-run"
```

`<UTC second>` is a literal typed into the command, two minutes before now: print it locally first with `date -u -d '-2 minutes' '+%Y-%m-%d %H:%M:%S'` (never a `$(...)` inside the ssh string: the wrapper would expand it on this machine). Also confirm production's current head is the one `v173_001` chains on:

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current </dev/null"
```

Expected:
1. `DB_RESTORE.md`: the last `### Drill` heading is followed by `VERDICT: PASS` (2026-10-01, v116 V116-10, when this plan was written).
2. `pitr_verify.log`: the newest `VERDICT <date> PASS` line, dated this month or last (the cron runs on the 1st).
3. `pgbackrest info`: status `ok`, a full or differential backup dated within the last 24 hours (nightly at 02:30 UTC), and a WAL archive range ending within the last few minutes.
4. The rollback dry run prints `Target ... resolves to:` with the code, bot image, db image, `.env` and market lines, then `Dry run: nothing changed.` (exit 0). A `REFUSE` line or a non-zero exit is a failed check.
5. `alembic current` prints `v172_001 (head)`, or the revision Step 2 re-chained `v173_001` onto. Anything else means production and the chain disagree: a failed check.

Any failed check stops the task before Step 4: report it to the partner with `AskUserQuestion`, one question, recommended option first: "Fix the backup first (run the PITR drill or the failing backup), then release", then "Release anyway; `v173_001` touches only the 15 pinned rows and its downgrade reverts exactly them, and `v173_002` only adds an empty table". Never proceed past a failed check without that answer. Record the five results in the task report; V173-18 Step 1 re-confirms them only if more than a day has passed.

- [ ] **Step 4: Merge the branch into `main` (local only)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot switch main
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-10-18-v173-execution-fidelity-overrides -m "merge: v173 execution fidelity (override stamp, manual_bulk retag, override replay, verdict table and daily evaluator, report, API, Overrides vs engine panel)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
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
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "release(bot): <bot version> -- manual closes stamp their exit price, bulk clears tagged manual_bulk (v173_001), override-fidelity report and API, verdict table (v173_002) with a daily one-time evaluation (v173)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/build_version_matrix.py
git -C E:/Documents/Private/Projects/Discord-Bot add swingbot/admin/version_history.json
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "chore(bot): <bot version> -- manual closes stamp their exit price, bulk clears tagged manual_bulk (v173_001), override-fidelity report and API, verdict table (v173_002) with a daily one-time evaluation (v173)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
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

The commits of Steps 2 and 4-6 are this task's commits (merge of `main` into the branch, the optional `v173_001` re-chain, the merge into `main`, `release(bot)`, `chore(bot)`, `release(ui)`, `chore(ui)`). `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows nothing from this task.

### Task V173-18: Deploy with both revisions on production; verify the 15 re-tags and the table

**Model:** opus — a data revision run against production rows

**Files:**
- Create (session scratchpad only): `$SCRATCH/v173-verify-deploy.py`
- None in the repo (VM only). Any live fix made on the VM is mirrored into this repo and committed on `main` before the task counts as done (`mirror-prod` skill).

**Interfaces:**
- Consumes: V173-17's unpushed `main` (merge plus four release commits) and its Step 3 check results; V173-5's `PINNED_PLAN_IDS: tuple[str, ...]` and `revision = "v173_001"` in `swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py`; V173-24's `revision = "v173_002"` and table `preregistration_verdicts`; V173-27's loop `override_verdict_check` in `_always_on_loops()`; § Pinned bulk-clear ids in the index (the 15 ids and their `at`, from V173-4); `swingbot.core.db.engine.get_engine() -> Engine`.
- Produces: production at `v173_002` with exactly the 15 pinned plans' last transition reading `manual_bulk`, an empty `preregistration_verdicts` table and the `override_verdict_check` loop running (consumed by V173-19); the recorded rollback second `T0`.

Invoke the `mirror-prod` skill before Step 3: this task changes production (a deploy, a data revision and a new table). `swingbot/core/db/migrations/env.py` runs the whole `alembic upgrade head` in one `context.begin_transaction()`, so `v173_001` and `v173_002` commit together or not at all: a refusal in either leaves production at `v172_001`, untouched.

- [ ] **Step 1: Re-confirm the release state**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch origin
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline main..origin/main
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the `log` prints nothing (nobody pushed `main` since V173-17); `status` shows nothing of this plan's. If `origin/main` moved, merge it into `main` (`git -C $R merge origin/main -m "merge: origin/main before the v173 push"`, ending with the attribution `-m` line) and run `python $R/scripts/dev/testrun.py file tests/db/test_migrations.py` alone: a new revision on `origin/main` means only `v173_001.down_revision` is re-chained onto it on `main` as its own commit (`fix(db): rebase v173_001 onto <rev>`, exactly as V173-17 Step 2), then `tests/db/test_migrations.py`, `tests/db/test_v173_manual_bulk_retag.py` and `tests/db/test_v173_002_preregistration_verdicts.py` re-run alone. If more than a day has passed since V173-17 Step 3, re-run its five checks now and stop on any failure as described there.

- [ ] **Step 2: Record the rollback second**

```bash
date -u '+%Y-%m-%d %H:%M:%S'
```

Write the printed value into the task report as `T0` (the second before the revisions can run; the rollback target if Step 9 needs one). Nothing has deployed yet.

- [ ] **Step 3: Push and watch the deploy**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot push origin main
gh run list --branch main --limit 1
gh run watch <run id from the line above> --exit-status
```

Expected: every suite job, the frontend "Unit tests" and "Production build", and the deploy job succeed. A red test or build job means nothing deployed: fix it on `main` as its own scoped commit, push again, and watch again; never re-run blindly. A red **deploy** job goes to Step 9.

- [ ] **Step 4: Read what the revisions did**

```bash
gh run view <run id> --log | grep -n "v173_00\|manual_bulk\|RuntimeError\|Running upgrade" | head -20
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current </dev/null"
```

Expected, in this order: `Running upgrade v172_001 -> v173_001` (or the re-chained parent), the revision's own line `v173_001: re-tagged 15 plans manual -> manual_bulk`, then `Running upgrade v173_001 -> v173_002`. The line `v173_001: none of the 15 pinned plans exist here ...` is a production no-op (production holds them) and goes to Step 9. `alembic current` prints `v173_002 (head)`.

- [ ] **Step 5: Verify the 15 re-tags and the empty table (read-only; the step fails on any miss)**

Write `$SCRATCH/v173-verify-deploy.py`:

```python
"""v173 V173-18: verify the deploy on production. Read-only. Exit 1 on any miss."""
import collections
import datetime as dt
import importlib.util
import pathlib
import sys

import sqlalchemy as sa

from swingbot.core.db.engine import get_engine
from swingbot.core.planning.plan_store import PlanStore

T0 = sys.argv[1] if len(sys.argv) > 1 else None   # "YYYY-MM-DD HH:MM:SS" UTC, from Step 2

path = pathlib.Path("swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py")
spec = importlib.util.spec_from_file_location("v173_001_check", path)
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)
pinned = set(mig.PINNED_PLAN_IDS)

plans = {p.plan_id: p for p in PlanStore().all()}
last = {pid: (p.status_history[-1] if p.status_history else {})
        for pid, p in plans.items() if p.status == "CLOSED"}
reasons = collections.Counter(entry.get("reason") for entry in last.values())
pinned_bulk = {pid for pid in pinned if last.get(pid, {}).get("reason") == "manual_bulk"}
other_bulk = {pid: last[pid].get("at") for pid in last
              if pid not in pinned and last[pid].get("reason") == "manual_bulk"}

engine = get_engine()
has_table = sa.inspect(engine).has_table("preregistration_verdicts")
with engine.connect() as conn:
    verdict_rows = conn.execute(sa.text("SELECT count(*) FROM preregistration_verdicts")).scalar() if has_table else None

print("pinned ids:", len(pinned))
print("pinned rows reading manual_bulk:", len(pinned_bulk))
print("pinned missing from the book:", sorted(pinned - set(plans)))
print("other manual_bulk rows (bulk clears after the deploy):", other_bulk)
print("manual rows:", reasons.get("manual", 0), "| CLOSED plans:", len(last))
print("preregistration_verdicts exists:", has_table, "| rows:", verdict_rows)
for pid in sorted(pinned):
    entry = last.get(pid, {})
    print(" ", pid, entry.get("reason"), entry.get("at"))
label_id = next((pid for pid in sorted(pinned) if pid in plans and not plans[pid].legs_realized), None)
print("label check id:", label_id)


def _after_t0(at):
    if T0 is None or at is None:
        return False
    t0 = dt.datetime.strptime(T0, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
    return dt.datetime.fromisoformat(at) >= t0


misses = []
if len(pinned) != 15 or len(pinned_bulk) != 15:
    misses.append("exactly 15 pinned rows must read manual_bulk")
if not all(_after_t0(at) for at in other_bulk.values()):
    misses.append("a non-pinned manual_bulk row predates the deploy")
if not has_table or verdict_rows != 0:
    misses.append("preregistration_verdicts must exist and be empty")
print("VERIFY:", "PASS" if not misses else "FAIL " + "; ".join(misses))
sys.exit(1 if misses else 0)
```

Pipe it in, with `T0` from Step 2 as the one argument (`python - '<T0>'` reads the script from stdin):

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - '<T0>'" < "$SCRATCH/v173-verify-deploy.py"
echo "exit: $?"
```

Expected: `VERIFY: PASS` and `exit: 0`; `pinned ids: 15`; `pinned rows reading manual_bulk: 15`; `pinned missing from the book: []`; `other manual_bulk rows` empty (or only bulk clears made after `T0`, which are real new bulk clears); the 15 listed lines read `manual_bulk` with `at` values matching § Pinned bulk-clear ids (2026-09-30 20:54–20:55 UTC); `manual rows` equals the individual manual closes (21 on 2026-10-17 per the Goal, plus any manual close made since; never fewer than 21: record a lower count as a miss); `preregistration_verdicts exists: True | rows: 0`; `label check id` is a plan id (needed by Step 8). **Any `FAIL` or a non-zero exit fails this step: go straight to Step 9 (the rollback path); Steps 6-8 do not run.**

- [ ] **Step 6: Check the bot and admin came up clean**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --since 20m bot admin 2>&1 | grep -iE 'Traceback|override|v173|Logged in as' | tail -20"
```

Expected: `bot`, `admin` and `db` up (healthy where a health check exists); a `Logged in as` line after the deploy (the bot's `on_ready` ran, and it calls `_start_background_loops()`); no traceback and no `override_verdict_check: daily check failed`. A traceback is reported with its lines; production is never patched by hand.

- [ ] **Step 7: The loop started**

The scheduler logs nothing when a loop starts, and `override_verdict_check` logs only at its weekday slot (`SESSION_END_HOUR`:50 Europe/Berlin). So the start is shown by the deployed code plus a clean `on_ready` (Step 6):

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot grep -n -A 6 'def _always_on_loops' swingbot/commands/scanning/loops.py </dev/null"
```

Expected: the tuple ends with `next_session_wrapup, override_verdict_check)`. If the deploy happened after that day's slot, the loop's first line appears at the next weekday slot; V173-19 Step 1 reads it (`override_verdict_check: waiting` on a first run). Record which slot is the first.

- [ ] **Step 8: The "Bulk close" label on production at three widths**

```bash
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/browse.mjs shots --out "$SCRATCH/v173-prod-label" --path "trades/<label check id>" --widths 1280,768,390
```

`browse.mjs` signs in from `.env` itself (one attempt; it never prints the values) and falls back to a manual sign-in in the window. Expected: each `*.txt` starts with `page-scroll-x: 0` and contains `Bulk close`; open `trades_<id>@390.png` with the Read tool and confirm the Exit tile reads `Bulk close`. This is the label check of record when V173-15 Step 1 found no local plan.

- [ ] **Step 9: Only if a check failed: stop, then ask**

Never edit production rows by hand. Report what failed with its lines, then ask the partner with `AskUserQuestion`, one question, recommended option first:
- **The deploy job failed on a revision** (a `RuntimeError` refusal or an error in `v173_002` in the log): the whole upgrade is one transaction, so production is still at `v172_001` and the rows are as they were. Options: "Leave production as it is and investigate on a fresh replica (`/replicate-prod-db`)" (recommended), then "Roll the whole bot back to `T0` with `rollback_to.sh`".
- **The revisions ran but Step 5 failed** (pinned `manual_bulk` count not 15, a pre-deploy non-pinned `manual_bulk` row, a `manual` count below 21, the table missing or not empty): options: "Downgrade both revisions: `bash $R/scripts/ops/ssh-hetzner.sh \"cd /opt/swing-bot && docker compose exec -T bot alembic downgrade v172_001 </dev/null\"` (drops the empty table, then reverts exactly the pinned entries; `v173_001`'s downgrade refuses unless all 15 read `manual_bulk`, and the refusal rolls the drop back too)" (recommended), then "Roll the whole bot back to `T0`: dry run first (`bash scripts/ops/rollback_to.sh '<T0>' --dry-run` on the VM through `ssh-hetzner.sh`), then the real run" (whole-bot: Postgres, `market_data/`, `.env` and images return to `T0`; scanning starts paused). Use the re-chained parent instead of `v172_001` if V173-17 re-chained.
- **A no-op line ("none of the 15 pinned plans exist here")**: production is missing the pinned ids, so V173-4's pin was wrong. Ask before anything else; the fix is a new revision with corrected ids, never an edit to `v173_001` after it ran.
- **The loop is missing from `_always_on_loops()`, or Step 6 shows a traceback**: the deployed image is not the merged build. Options: "Redeploy from `main` (`gh run rerun <run id>`) and repeat Steps 4-8" (recommended), then "Roll back to `T0`".

Act only on the partner's answer. Any change that results is mirrored into the repo and committed on `main` as its own scoped commit (`fix(<area>): ... (v173, mirrored from production)`) before this task counts as done.

- [ ] **Step 10: Commit**

Nothing to commit when every check passed: this task changes production only. Record in the task report: `T0`, the CI run id, the `alembic current` line, Step 5's `VERIFY` line and counts, Step 7's first slot and Step 8's verdict. `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows nothing from this task.

### Task V173-19: First real report run on the VM (read-only) and the mirror check

**Model:** sonnet — reads the real book's output and decides whether a stored verdict must be mirrored

**Files:**
- Create (session scratchpad only): `$SCRATCH/v173-verdict-table.py`, `$SCRATCH/v173-check-report.py`, `$SCRATCH/v173-report.json`, `$SCRATCH/v173-api.json`, `$SCRATCH/v173-mirror-row.txt`
- Modify: `docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md` (§ Progress, on `main`)
- Modify, only if `preregistration_verdicts` holds a row: `docs/superpowers/results/preregistration-ledger.jsonl` (the mirrored row, on `main`, by the standing procedure)

**Interfaces:**
- Consumes: V173-18's deployed build at `v173_002`, with the retag applied and the loop running; V173-11's read-only script `scripts/reports/execution_fidelity_report.py` (`--production` drops the banner `DEV DATABASE: fixture data, not the real book. This report never writes a verdict.`; `--json PATH` writes the payload; `--mirror-row` prints `mirror_ledger_row(<stored record>)` as one JSON line, or `no verdict recorded` with exit code 0; it never evaluates and never writes) and the results doc `docs/superpowers/results/v173-override-fidelity.md` with § Standing procedure; V173-12's `GET /api/v1/analytics/override-fidelity`; V173-24's table `preregistration_verdicts` (`ledger_id`, `verdict`, `recorded_on`, `doc`); V173-26/V173-27's log line `override_verdict_check: <result>`; V173-10's `LEDGER_ID = "v173-override-fidelity"` and `RESULTS_RECORD`; the payload contract of Global Constraints; V173-18 Step 5's `manual rows` count; `stats.load_ledger(path)`, `stats.append_ledger_row(row, path)` (`swingbot/core/backtesting/instrument/stats.py:193`, `:204`).
- Produces: the recorded first production output in § Progress; the mirrored ledger row if the table holds one.

Nothing in this task evaluates the verdict: only the bot's `override_verdict_check` loop does (Global Constraints, "The one evaluator"). Invoke the `pooled-numbers` skill before writing any figure from this run into § Progress or a commit: every figure is quoted with its N, window and source (this run, on the live book), and the ΣΔ figures are descriptive, not a verdict.

- [ ] **Step 1: Run the report on the VM with `--production --json`, and read the loop's log**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/execution_fidelity_report.py --production --json /tmp/v173-report.json </dev/null"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot cat /tmp/v173-report.json </dev/null" > "$SCRATCH/v173-report.json"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --since 72h bot 2>&1 | grep 'override_verdict_check' | tail -5"
```

Expected: the printed output does **not** start with `DEV DATABASE: fixture data, not the real book. This report never writes a verdict.` (that banner on the VM means `--production` did not reach the script: stop and report); it prints the row table, the summary with its splits and the verdict state. The JSON file is non-empty. The log shows `override_verdict_check: waiting` for each weekday slot since the deploy (none yet if no slot has passed: record that), never `daily check failed`. Keep the printed output in the task report.

- [ ] **Step 2: Read the verdict table (read-only)**

Write `$SCRATCH/v173-verdict-table.py`:

```python
"""v173 V173-19: what the verdict table holds. Read-only."""
import sqlalchemy as sa

from swingbot.core.db.engine import get_engine

with get_engine().connect() as conn:
    rows = conn.execute(sa.text(
        "SELECT ledger_id, verdict, recorded_on FROM preregistration_verdicts ORDER BY ledger_id")).fetchall()
print("verdict rows:", len(rows))
for row in rows:
    print(" ", row.ledger_id, row.verdict, row.recorded_on.isoformat())
```

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < "$SCRATCH/v173-verdict-table.py"
```

Expected on a first run: `verdict rows: 0` (the floors cannot hold yet). A row reads `v173-override-fidelity <COST|SAVED|INCONCLUSIVE> <YYYY-MM-DD>`; any other `ledger_id` or `verdict` is a finding.

- [ ] **Step 3: Fetch the same payload through the API**

```bash
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/browse.mjs api --path "api/v1/analytics/override-fidelity" > "$SCRATCH/v173-api.json"
```

`browse.mjs` signs in from `.env` itself and never prints the values; its status lines go to stderr, so the file holds only the JSON body.

- [ ] **Step 4: Check the output**

Write `$SCRATCH/v173-check-report.py`:

```python
"""v173 V173-19: check the first production report run and the API payload. Reads two JSON files."""
import collections
import json
import sys

STATUSES = {"resolved", "open", "stale", "ambiguous", "parity_mismatch", "split_affected",
            "unreplayable", "unstamped"}
PAYLOAD_KEYS = ["asof", "currency_symbol", "engine_flags", "rows", "summary", "verdict"]
ROW_KEYS = sorted(["plan_id", "ticker", "horizon", "direction", "state_at_close", "close_date", "bulk",
                   "approx", "price_source", "status", "actual_r", "engine_r", "delta_r", "delta_r_gross",
                   "actual_usd", "engine_usd", "delta_usd", "engine_exit_reason", "outcome", "source"])
SUMMARY_KEYS = sorted(["n_by_status", "bulk_n", "bulk_dates", "approx_n", "counted_n", "sum_delta_r",
                       "sum_delta_r_gross", "sum_delta_usd", "usd_missing_n", "helped", "hurt", "neutral",
                       "splits"])
VERDICT_KEYS = sorted(["state", "n", "needed", "weeks", "week_floor", "open_n", "excluded_share",
                       "evaluable", "waiting_on", "recorded", "recorded_on", "mean_delta_r",
                       "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n"])

report = json.load(open(sys.argv[1], encoding="utf-8"))
api = json.load(open(sys.argv[2], encoding="utf-8"))
rows = report["rows"]
summary, verdict = report["summary"], report["verdict"]

print("payload keys ok:", sorted(report) == PAYLOAD_KEYS, "| api keys ok:", sorted(api) == PAYLOAD_KEYS)
print("row keys ok:", all(sorted(r) == ROW_KEYS for r in rows),
      "| summary keys ok:", sorted(summary) == SUMMARY_KEYS, "| verdict keys ok:", sorted(verdict) == VERDICT_KEYS)
print("rows:", len(rows), "| bulk:", sum(r["bulk"] for r in rows), "| individual:", sum(not r["bulk"] for r in rows))
print("statuses:", dict(collections.Counter(r["status"] for r in rows)))
print("rows with an unknown status:", [r["plan_id"] for r in rows if r["status"] not in STATUSES])
print("individual approx:", sum(r["approx"] and not r["bulk"] for r in rows),
      "| individual not approx:", sum(not r["approx"] and not r["bulk"] for r in rows))
print("price_source:", dict(collections.Counter(r["price_source"] for r in rows)))
print("rows without dollars:", sum(r["delta_usd"] is None for r in rows))
print("summary:", {k: summary[k] for k in ("bulk_n", "bulk_dates", "approx_n", "counted_n", "sum_delta_r",
                                           "sum_delta_r_gross", "sum_delta_usd", "usd_missing_n",
                                           "helped", "hurt", "neutral")})
print("verdict:", verdict)
print("engine_flags:", report["engine_flags"], "| asof:", report["asof"], "| currency:", report["currency_symbol"])
print("api rows:", len(api["rows"]), "| api summary equal:", api["summary"] == summary,
      "| api verdict equal:", api["verdict"] == verdict)
```

```bash
python "$SCRATCH/v173-check-report.py" "$SCRATCH/v173-report.json" "$SCRATCH/v173-api.json"
```

Expected:
- `payload keys ok: True | api keys ok: True`, and `row keys ok`, `summary keys ok`, `verdict keys ok` all `True`.
- `bulk` 15 and `summary.bulk_dates` `{"2026-09-30": 15}`; `individual` equals V173-18 Step 5's `manual rows`; so every override in the book has a row.
- `rows with an unknown status: []` (each row carries exactly one of the eight statuses).
- Every individual close made before the deploy has no `override` stamp (stamp kind `missing`), so it is `approx` (`price_source` `session_open` or `session_close`); `individual not approx` counts only manual closes made after the V173-18 deploy (usually 0 on the first run), and among those an `unstamped` row means a stamp failed on production: report it.
- `counted_n` equals the number of individual non-approx `resolved` rows; the verdict `recorded` flag matches Step 2 (`false` with `verdict rows: 0`). Not recorded: `state` `WAITING`, `n` = `counted_n`, `needed` 30, `week_floor` 10, `evaluable` false on a first run, `waiting_on` lists the failing items in the order `count, weeks, open, excluded`, and `recorded_on`, `mean_delta_r`, `mean_delta_r_gross`, `ci`, `sum_delta_r`, `sum_delta_usd` are `null`. Recorded: `state`, `n`, `weeks`, `recorded_on`, the mean, CI and sums equal the stored record (Step 2's verdict and date).
- `api rows` equals `rows`, and both `equal` flags are `True` (the API calls the same `build_report` with the same stored record; an `asof` change between the two calls is the only acceptable difference: re-run Steps 1 and 3 once if it happened across a session close).
- `engine_flags` echoes production's `STALL_EXIT_ENABLED` and `RUNNER_STRUCTURE_EXIT`; record them.

A row count, a status or a flag that misses its expectation is reported as a finding with the printed lines; it is never patched on the VM.

- [ ] **Step 5: The mirror check (standing procedure)**

Print the mirror line on the VM; the script reads the table and never writes:

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/execution_fidelity_report.py --production --mirror-row </dev/null" > "$SCRATCH/v173-mirror-row.txt"
echo "exit: $?"
cat "$SCRATCH/v173-mirror-row.txt"
```

**No verdict recorded** (the expected first-run result): the file reads `no verdict recorded` and `exit: 0`. Nothing is mirrored; Step 7 records "no verdict yet".

**A verdict recorded** (the file holds one JSON line with `"id": "v173-override-fidelity"`): apply the standing procedure from `docs/superpowers/results/v173-override-fidelity.md` (`mirror-prod`). First check the jsonl on `main` does not already carry the id, then append the line and commit:

```bash
python -c "import json, pathlib; from swingbot.core.backtesting.instrument import stats; p = pathlib.Path(r'E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/preregistration-ledger.jsonl'); assert 'v173-override-fidelity' not in {r['id'] for r in stats.load_ledger(p)}, 'already mirrored'; row = json.loads(pathlib.Path(r'$SCRATCH/v173-mirror-row.txt').read_text(encoding='utf-8').strip()); stats.append_ledger_row(row, p); last = stats.load_ledger(p)[-1]; print(last['id'], last['verdict'], last['n'], last['record'])"
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/results/preregistration-ledger.jsonl
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v173): mirror the recorded override-fidelity verdict into the ledger" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot push origin main
```

(`$SCRATCH` is written out as the absolute scratchpad path in the command.) Expected: `already mirrored` is not raised (if it is, the row is in the jsonl already: nothing to do; `append_ledger_row` would also refuse the duplicate id); the print reads `v173-override-fidelity <COST|SAVED|INCONCLUSIVE> <n> docs/superpowers/results/v173-override-fidelity.md`, matching Step 2; the ledger-file test passes (the `record` path exists). The push deploys the mirrored file. The verdict is never recomputed: the table's row is the authority, and every later report returns it as stored.

- [ ] **Step 6: The panel on production at three widths**

```bash
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/browse.mjs shots --out "$SCRATCH/v173-prod-panel" --path "analytics?tab=execution" --widths 1280,768,390
```

Expected: each `*.txt` starts with `page-scroll-x: 0` and contains `Overrides vs engine`, the badge for Step 4's state (first run: `<counted_n> of 30 needed. No conclusion yet.`), `15 closes from one bulk clear on 2026-09-30 are not decisions, so they are left out`, and the estimated-rows note with Step 4's `approx_n` (`<approx_n> estimated rows are shown but not counted`, or `1 estimated row is shown but not counted`), plus the full caption. Open `analytics_tab_execution@390.png` and `analytics_tab_execution@1280.png` with the Read tool and confirm cards at 390, the table at 1280, the estimate label on the approx rows, the caption whole and legible at 390, and the net-effect tile not tinted while WAITING. If V173-15 could not run locally, this step is that check: record the measurements by eye in the task report.

- [ ] **Step 7: Record the run in § Progress and commit on `main`**

Replace the `## Progress` block's `Not started. Update this block when a phase closes.` line in `$R/docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md` with:

```markdown
First production report run <YYYY-MM-DD HH:MM UTC> (V173-19, `--production`, read-only, live book, bars as of <asof>): <rows> overrides = 15 bulk (2026-09-30) + <individual> individual (<approx> estimated, <not approx> stamped). Statuses: <statuses dict>. Counted <counted_n>; verdict WAITING (<counted_n> of 30, <weeks> of 10 weeks; waiting on <waiting_on>); `preregistration_verdicts` empty, no verdict yet, nothing mirrored. Loop `override_verdict_check`: <first slot line, or "no slot yet">. Engine flags: <engine_flags>. API payload identical to the script's.
```

filled from Steps 1-5 (add `ΣΔ <sum_delta_r> R / <sum_delta_usd> over the <counted_n> counted rows, net of modelled costs (<sum_delta_r_gross> R before costs), descriptive only` only when `counted_n` > 0; if Step 5 mirrored a row, replace the verdict clause with the recorded verdict, `n`, `recorded_on` and the mirror commit). Then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v173): first production override-fidelity report run recorded" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: one commit on `main` touching only the index (plus Step 5's commit if it applied); no push needed here (V173-20 pushes); `git status` shows nothing of this task's.

### Task V173-20: Close-out: move plan and spec to `implemented/`, remove worktree

**Model:** haiku — the close-out checklist

**Files:**
- Modify: `docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md` (`## Progress` block), then `git mv` all ten plan files into `docs/superpowers/plans/implemented/`:
  - `2026-10-18-v173-execution-fidelity-overrides_0-index.md`
  - `2026-10-18-v173-execution-fidelity-overrides_1-stamp-retag.md`
  - `2026-10-18-v173-execution-fidelity-overrides_2-replay-core.md`
  - `2026-10-18-v173-execution-fidelity-overrides_2b-engine-arms.md`
  - `2026-10-18-v173-execution-fidelity-overrides_3-statuses-verdict.md`
  - `2026-10-18-v173-execution-fidelity-overrides_3b-verdict.md`
  - `2026-10-18-v173-execution-fidelity-overrides_3c-verdict-store.md`
  - `2026-10-18-v173-execution-fidelity-overrides_4-report-api-ui.md`
  - `2026-10-18-v173-execution-fidelity-overrides_4b-panel.md`
  - `2026-10-18-v173-execution-fidelity-overrides_5-check-release.md`
- Move: `docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md` → `docs/superpowers/specs/implemented/`
- Stays put: `docs/superpowers/results/v173-override-fidelity.md` (the mirror row's `record` path; `test_preregistration_ledger_file.py` requires it to exist) and `docs/superpowers/results/preregistration-ledger.jsonl`.

**Interfaces:**
- Consumes: V173-15's measurement lines, V173-16's recorded counts, V173-17's panel result and release commits, V173-18's `T0`, CI run id, `VERIFY` line and first loop slot, V173-19's § Progress line.
- Produces: nothing; the plan leaves the live set and the SessionStart `PLAN WIP` line stops naming it. The `override_verdict_check` loop keeps running on production after close-out: the evaluation happens on the first weekday the floors hold, and the standing procedure in the results doc covers its mirror.

- [ ] **Step 1: Run the `close-out` skill, with three of its steps already done**

Invoke `/close-out`. Its panel step ran in V173-17 Step 1, and its bump and regeneration steps ran in V173-17 Steps 5-6: confirm them from the log rather than repeating them:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -8 -- VERSION.json swingbot/admin/version_history.json
python -c "import json; print(json.load(open(r'E:/Documents/Private/Projects/Discord-Bot/VERSION.json')))"
```

Expected: `release(bot)`, `chore(bot)`, `release(ui)`, `chore(ui)` commits naming v173, and `VERSION.json` showing both lines one minor above the values before V173-17. Do not bump again. The header said `Bump: bot minor; ui minor` and `Edge: none (integrity)`; both held, so nothing is amended (if one did not, amend the index header and say why in one clause in Step 4's commit). The plan is integrity work, so it goes to `implemented/`, never `no-lift/`, whatever the eventual verdict reads: the verdict is a result of the pre-registration, recorded in the results doc and the ledger, not of this plan.

- [ ] **Step 2: Record the results in the index**

In `$R/docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md`, put this line at the top of the `## Progress` block, above V173-19's first-run line (which stays):

```markdown
Done <YYYY-MM-DD>. V173-1..V173-27 complete. Three-width check (V173-15): <local | production only>, every line met (caption legible at 390px, net-effect tile neutral while WAITING). Full suite (V173-16): Python <passed> passed, <skipped> skipped, 0 failed, 0 xfailed; Vitest <n> passed; production build green; complexity gate green. Panel (V173-17): <n> BLOCKING resolved, <n> ADVISORY (<applied>/<recorded>). Released bot <version>, ui <version>. Deploy (V173-18): CI run <id>, rollback second T0 <T0>, Alembic at v173_002, 15 pinned plans read manual_bulk, preregistration_verdicts created empty, override_verdict_check in the always-on loops (first slot <date>), "Bulk close" shown at three widths. Verdict: <no verdict yet | VERDICT recorded on <date>, mirrored in <commit>>; the loop evaluates once, on the first weekday the floors hold.
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
for f in 0-index 1-stamp-retag 2-replay-core 2b-engine-arms 3-statuses-verdict 3b-verdict 3c-verdict-store 4-report-api-ui 4b-panel 5-check-release; do git -C E:/Documents/Private/Projects/Discord-Bot mv "docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_$f.md" docs/superpowers/plans/implemented/; done
git -C E:/Documents/Private/Projects/Discord-Bot mv docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md docs/superpowers/specs/implemented/
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/plans/implemented/2026-10-18-v173-execution-fidelity-overrides_0-index.md
ls E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_*.md 2>/dev/null | wc -l
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v173): close out -- plan and spec to implemented/, results recorded" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot push origin main
```

The § Progress edit from Step 2 rides in this commit (staged by the `git add` after the move). Expected: the first `ls` lists exactly the ten files above (a missing or an extra file is checked before moving: an extra `_N` file means a part was added after this task was written, and it moves too); each `git mv` succeeds; the second `ls` count is `0`; one commit that moves the ten plan files and the spec and changes the index's Progress block; `git status` clean for these paths; `docs/superpowers/results/v173-override-fidelity.md` is untouched; the push carries V173-19's commit too. No full suite after this (CLAUDE.md: it ran once, in V173-16).
