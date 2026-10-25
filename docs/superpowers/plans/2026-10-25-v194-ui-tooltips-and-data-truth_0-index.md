# v194 — UI integrity: tooltips that open, figures that are true: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V194-7:" -A 400 docs/superpowers/plans/2026-10-25-v194-ui-tooltips-and-data-truth_3-risk-format-and-sectors.md`.

**Bump:** ui patch, bot patch
**Edge:** none (integrity) — no signal, gate, stop, size or badge changes; the partner reads these screens to place real orders, so a hidden definition or a wrong figure is an integrity defect.
**Screen:** exempt (integrity)
**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md)
**Brief:** `.superpowers/briefs/2026-10-25-v194-ui-tooltips-and-data-truth.md` (gitignored; tasks cite repo files, never the brief)
**Worktree:** every task runs in `.claude/worktrees/2026-10-25-v194-ui-tooltips-and-data-truth` (branch of the same name, created in V194-1's first step; `docs/claude/document-lifecycle.md`). The merge to `main` is V194-17's last step.

## Goal

The admin UI is where the partner reads a trade plan before placing a real
resting order, and two kinds of defect make it say less, or something
different, from what the bot knows. First, the explanations are hidden: a
production probe (2026-10-25, ui 1.36.0) found that 19 of 20 `sb-hint`
popovers at 1440px, and every one at 390px, open off-position and clipped,
because `sb-panel`'s hover lift (`transform`) and the route-entrance
`will-change` turn the panel into the containing block of the popover's
`position: fixed`. On top of that, about a hundred native `title`
attributes carry definitions that never show on a phone, a tablet or by
keyboard. Second, eight figures and labels are wrong or misleading: tab
counts that read "Open 0" over eight open rows, "All" rows that render
ten, partial-exit legs that look like duplicate trades, fractional shares
rounded to whole, tiny risk percentages shown as zero, a sector-heat panel
that says "No sector exposure" because the sector map is empty, a `$`/`€`
unit label that has to be checked against what the money actually is, and
two Sharpe/drawdown pairs with the same names and different populations.

Once this ships, every hint renders in the browser's top layer (Popover
API), clamped to the viewport, so no ancestor transform, clip or stacking
context can hide it; the layout audit gains a `hint` check that opens every
trigger at 390, 768 and 1440 and fails when the popover is not visible and
topmost, and that check becomes the standing probe. Explanation hidden in
`title` moves into `sb-hint` or visible text, and a source-scanning spec
stops new explanation landing in `title` again. Each figure in section B
reads what the API returns: counts follow the lifecycle payload, "All"
asks for the 200-row cap, leg rows say "Leg N of M" plus the exit reason
and that win rate counts plans, shares and risk percentages keep their
precision with totals summed unrounded, a missing sector map shows a
banner instead of a reassuring zero, and Sharpe/drawdown tiles name their
basis, population, N and the paper / gross / pre-tax caveat.

In idea: fix the primitive once (`sb-hint`), make the audit prove it on a
real browser, then correct each figure at the point it is formatted or
labelled, adding one backend field where the data exists but the response
does not carry it (`unmapped_count`, `leg_exit_reason`,
`max_drawdown_amount`). Nothing the bot computes for trading changes:
`universe.sector_map` and the universe data stay as they are because the
walk-forward replay and the weekly retrospective read them too.

Left alone (spec C, next): panel-heading style, pagers, compact tables,
Risk/System regrouping, phone tab labels; every other overlay component.

Success is measured by the layout audit, `hint` check included, exiting 0
at all three widths against a local replica before merge and against
production after deploy; by the A4 audit table (one verdict per hint) in
V194-16's notes; and by each B item's acceptance tests.

## Architecture

- **`sb-hint` top layer (V194-1, V194-2).** `frontend/src/app/ui/hint.ts`
  gives its `.pop` element `popover="manual"` and drives
  `showPopover()`/`hidePopover()` from the existing `open` computed through
  guarded calls; `supportsPopover()` keeps today's `position: fixed` path
  where the API is absent. Placement is a pure exported function,
  `clampPopover`, so jsdom can test the arithmetic even though it cannot
  measure layout. A hint inside a `<dialog>` host hides on the host's
  `DIALOG_CLOSING_EVENT`, dispatched by `sb-drawer.requestClose()` and
  `sb-confirm-dialog`'s close path before their exit animations. A global
  `installPopoverPolyfill()` in `frontend/src/test-setup.ts` makes every
  page spec that renders an `sb-panel` heading safe.
- **Audit `hint` check (V194-3).** `frontend/scripts/layout-audit-lib.mjs`
  gains the pure `hintVerdict` (geometry in, verdict out) and `'hint'` as
  the eighth `CHECKS` entry; `frontend/scripts/layout-audit.mjs` hovers
  (1440) or taps (390, 768) each visible trigger Playwright-side, measures
  the popover and the elements at its sample points in the page, and turns
  them into findings.
- **Figures (V194-4..V194-13).** Formatting lives in
  `frontend/src/app/ui/format.ts` (`shareCount`, `riskPct`); the leg label
  in `frontend/src/app/workspaces/trades/leg-label.ts` (`legLabel`,
  `LEG_HINT_TEXT`), shared by Trades, Dashboard and Calendar. Backend
  additions are response fields only: `unmapped_count` on `GET /api/v1/risk`
  (from `collect_portfolio_state`, through extracted helpers since that
  function is complexity 22), `metrics.max_drawdown_amount` on the same
  endpoint, and `leg_exit_reason` on trade leg rows.
- **Titles (V194-14, V194-15).** `frontend/src/app/ui/title-usage.spec.ts`
  scans the source with the counting rule below and fails on any binding
  not listed in `frontend/src/app/ui/title-usage.allow.ts`.
- **Content audit (V194-16).** One verdict per `sb-hint` text and chart
  tooltip, recorded as a table in that task's notes.

## Global Constraints

- Frontend: Angular, zoneless, Vitest 4 through `@angular/build:unit-test`
  on jsdom. Narrow run: `npm --prefix "$WT/frontend" test -- --watch=false --include <spec path relative to frontend/>`;
  before each frontend commit also `npm --prefix "$WT/frontend" test -- --watch=false`
  (whole frontend) and `npm --prefix "$WT/frontend" run lint`. **Never `cd`
  in a Bash call** (it breaks the guardrail hooks): use `--prefix`, `-C` or
  absolute paths. `WT` is the worktree's absolute path.
- New fields on `TradeRow`, `Risk`, `RiskMetrics` in
  `frontend/src/app/api/models.ts` are **optional** (`?:`): several specs
  build full literals of these interfaces.
- Every UI change is designed for, and checked at, 390, 768 and 1440
  (`docs/claude/ui-design.md` § Checklist). The layout audit runs once for
  the plan, in V194-17, against the local replica; tasks rely on unit
  tests and, where a task says so, a Playwright screenshot.
- Browsers are driven by Playwright only. Local instances log in with
  `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD`, loaded inside the script and
  never printed, echoed or logged.
- Database-backed tests: `/replicate-prod-db` into the shared `swing-db`
  container runs once, in the first task that needs it (V194-4's diagnosis
  step, or V194-8 if it starts first); later tasks reuse it.
- Production is read-only for this plan: V194-6 and V194-8 open with a
  `prod-inspector` check through `scripts/ops/ssh-hetzner.sh`; nothing on
  the VM is changed.
- Every function written or changed ends at cyclomatic complexity **< 15**
  (`scripts/dev/complexity_gate.py`). `collect_portfolio_state`
  (`swingbot/core/edge/portfolio_state.py`, CC 22) never gets worse: new
  logic goes into extracted helpers.
- `universe.sector_map`, `universe.load` and the universe data files are
  **not changed** (they feed `swingbot/core/backtesting/backtest_wf.py` and
  `swingbot/core/tracking/retrospective.py`). If V194-8's inspection finds
  the cause is missing universe data, V194-8 ships only the warning log
  and `unmapped_count`, and the commit records the cause.
- Hint copy rules: a win-rate hint always names ExpR and N beside it; no
  hint reads as a recommendation ("take", "safe", "buy"); a performance
  figure states paper (simulated fills), gross or net of commissions and
  slippage, and pre-tax.
- Existing behaviour is otherwise preserved: `sb-hint`'s inputs (`text`,
  `label`, `glyph`, `wide`, `xl`, `align`), open reasons and their phone
  tap ordering, Escape / outside-pointer close, `aria-expanded`,
  `role="tooltip"`, `aria-describedby`, the 44px coarse-pointer `@media`
  block (its literal shape: `hint.spec.ts` regex-reads it), `.sb-lift`'s
  hover lift, the analytics unit value key `'money'`.
- **A3 counting rule** (fixes the brief's 123-vs-spec's-110 mismatch): a
  title site is an occurrence of `title="`, `[title]="` or `[attr.title]="`
  preceded by whitespace, or a host-metadata key `'[attr.title]':`, in
  `frontend/src/app/**/*.ts` excluding `*.spec.ts` and
  `frontend/src/app/testing/**`, **minus** bindings on elements whose
  `title` is a component input that renders visible heading text
  (`TITLE_INPUT_ELEMENTS`: `sb-panel-header`, `sb-empty-state`,
  `sb-confirm-dialog`). Occurrences are counted, not lines. V194-14 states
  the measured count in its commit.
- Commits: frontend and backend changes go in separate commits; no
  `VERSION.json` edit in any task (the bump is `/close-out`'s, from the
  `Bump:` line).

### Standard task close

Every task ends with `Close: standard (test: <path>)`, meaning these steps,
in order, and spells out only its deviations:

1. `git rev-parse --show-toplevel` prints the v194 worktree, and
   `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows
   nothing this task wrote into the main tree.
2. The narrow run of `<path>` is green (`0 failed`, `0 xfailed`):
   `.py` → `python scripts/dev/testrun.py file <path>`;
   `.spec.ts` → `npm --prefix "$WT/frontend" test -- --watch=false --include <path without the frontend/ prefix>`,
   then the whole frontend run and `npm --prefix "$WT/frontend" run lint`;
   `.mjs` → `node --test <path>`.
3. `python scripts/dev/complexity_gate.py` → exit 0.
4. `git add` the task's files by name and commit
   `<feat|fix|test|docs|chore>(v194): <summary> (V194-<n>)`, ending with
   the `Co-Authored-By:` trailer from the session's attribution reminder.
   A task touching both `swingbot/` and `frontend/` makes two commits.

## Handoff

Decisions the part writers inherit (from the brief and the index writer's
code reading, 2026-10-25):

- **Path fix.** The spec's `testing/dialog-polyfill.ts` is
  `frontend/src/app/testing/dialog-polyfill.ts`; the new polyfill sits
  beside it as `frontend/src/app/testing/popover-polyfill.ts` and is
  installed from `frontend/src/test-setup.ts` (patching prototypes there is
  safe; importing singletons is not — see that file's comment). The
  polyfill reflects the open state as the attribute `data-popover-open`,
  because jsdom cannot match `:popover-open`; `hint.spec.ts`'s `isOpen()`
  moves from `!pop().hidden` to that attribute.
- **B1 root cause is not established.** V194-4 starts with a diagnosis step
  on the local replica (Playwright at 1440, 768 and 390: the network log
  for `/api/v1/dashboard?…today…`, the store's `todayData`/`todayLoading`,
  the console). Known suspects to confirm or rule out: `loadToday`'s error
  branch leaves `todayData` null (counts `[]` → "Open 0") and only clears
  `todayLoading`; `resolve()` only patches `todayData` when the selection's
  mode is `today`. The fix follows the finding; the commit states it.
- **B2 root cause is known.** `frontend/src/app/workspaces/trades/trades.routes.ts`
  `queryFor`: `Number('0') || DEFAULT_PER_PAGE` turns "All" (`ALL_PER_PAGE
  = 0`) into 10, and the resolver ignores the saved per-page preference;
  `runGuardsAndResolvers: 'always'` reruns it on every navigate.
- **B7 finding (code).** No FX conversion exists anywhere in `swingbot/`:
  leg `realized_pnl_amount` is `shares * (exit_price - entry)` in the
  instruments' quote currency (`swingbot/admin/api_v1/trades.py:529`),
  and `CURRENCY_SYMBOL` only picks a symbol. V194-6 confirms on production
  (`prod-inspector`: the distinct quote currencies of closed-trade tickers)
  and then, as the spec allows, **keeps an honest `$`** on the Analytics
  toggle through `QUOTE_CURRENCY_SYMBOL` instead of relabelling to `€`;
  the spec's "€, $, £" toggle test becomes "the label is
  `QUOTE_CURRENCY_SYMBOL` whatever the account currency is € / $ / £, and
  the value key stays `'money'`". Only if the inspection finds a
  conversion does V194-6 use `connection.currency()` instead. Calendar's
  `€` toggle (`calendar.ts:489-497`) and every other `money(value,
  currency)` display over these same sums are recorded as V194-16 audit
  rows (`fixed text` only where the item is a hint or chart tooltip); an
  app-wide relabel or a real conversion is a follow-up spec, not this one.
- **B8 money drawdown.** `GET /risk` metrics carry R only. V194-10 adds
  `metrics.max_drawdown_amount` (`{value, n}` like the other metrics): the
  peak-to-trough decline of the cumulative realised P&L amount over all
  closed trades, in the quote currency (B7 finding), so Risk's tile shows
  it with `QUOTE_CURRENCY_SYMBOL`, and Analytics' existing money line uses
  the same symbol. A conversion to the account currency is not well
  defined without FX data; V194-10's commit records that.
- **B3 data.** `TradeRow` has no per-leg exit reason; stored legs carry
  `reason` (and `stop_source`, read by `_runner_exit_reason`). V194-12 adds
  `leg_exit_reason` to leg rows in `swingbot/admin/api_v1/trades.py`
  (`_row_from_leg`; `None` on non-leg rows) and to `TradeRow`. "Leg N of M"
  exists only as Calendar's `legLabel(trade: CalendarTrade)`
  (`frontend/src/app/workspaces/calendar/day/day-trade-card.ts:15-17`);
  V194-12 creates the shared `legLabel` in
  `frontend/src/app/workspaces/trades/leg-label.ts` (beside
  `exit-reasons.ts`, whose `reasonLabel` it uses), and Calendar switches to
  it. V194-13 states and tests whether the Trades row total counts legs or
  plans.
- **B6.** `prod-inspector` first. Hypothesis to test, not assume:
  `universe.load()` returns `[]` for a missing universe file, so a
  `SCAN_UNIVERSE` without a universe JSON gives an empty map with no
  exception. `tests/admin/test_api_v1_risk.py:129` asserts the exact
  top-level key set of `/risk`; V194-8 adds `unmapped_count` to it.
  `!growth` (`swingbot/commands/growth.py` `portfolio_report`) reads
  `state["sector_heat"]` as a dict, which stays a dict.
- **B8 tile hint.** `sb-stat-tile`'s `hint` input is plain text under the
  value; V194-11 adds an `about` input that renders an `sb-hint` beside the
  label, leaving `hint` as it is.
- **A3 batches.** V194-14 creates the scanner and the allow-list, and
  converts every site outside `frontend/src/app/workspaces/analytics/`;
  sites inside it that are still explanation are listed in
  `TITLE_PENDING` so the spec passes. V194-15 converts them and adds the
  assertion that `TITLE_PENDING` is empty.

## Parallelisation

- **V194-1 → V194-1b → V194-2 → V194-2b first, alone and sequential** (both edit
  `frontend/src/app/ui/hint.ts` and `hint.spec.ts`; every later task adds
  or checks hints).
- **Then parallel lanes, file-disjoint:**
  - V194-3 (A2): `frontend/scripts/` only.
  - V194-4 (B1): `dashboard.store.ts`, `dashboard.ts`, the trading
    performance panel.
  - V194-5 (B2): `trades.routes.ts` and its spec.
  - V194-6 (B7): `analytics/scope-bar.ts`, `ui/unit-format.ts`.
  - **Backend lane** V194-8 → V194-10: sequential, both edit
    `swingbot/admin/api_v1/risk.py` and `tests/admin/test_api_v1_risk.py`.
  - **Risk / models lane** V194-7 → V194-9 → V194-11 → V194-12 → V194-13:
    sequential. V194-7, V194-9 and V194-11 all edit
    `workspaces/risk/risk.ts` and `risk.spec.ts`; V194-9, V194-11 and
    V194-12 all edit `api/models.ts`; V194-7 and V194-13 both edit
    `trades.columns.ts`.
- Cross-lane contract edges: V194-9 starts after V194-8 (consumes
  `unmapped_count`); V194-11 after V194-10 (`max_drawdown_amount`) and
  V194-6 (`QUOTE_CURRENCY_SYMBOL`, and both touch Analytics); V194-13 after
  V194-4 (both edit `dashboard.ts`).
- **V194-14 after every B task** (it sweeps `title` sites in files B tasks
  edit, and B3/B8 add hints the allow-list must not list); V194-15 after
  V194-14 (same allow-list file); V194-16 after V194-15 (it audits every
  hint, including those added by A3, B3 and B8); V194-17 last.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-25-v194-ui-tooltips-and-data-truth_1-hint-top-layer-and-audit.md` | V194-1..V194-3 | worktree; popover polyfill; `sb-hint` top layer, clamp, dialog host close; layout-audit `hint` check |
| 2 | `2026-10-25-v194-ui-tooltips-and-data-truth_2-dashboard-trades-unit.md` | V194-4..V194-6 | B1 lifecycle counts (diagnose first); B2 "All" rows; B7 money unit label |
| 3 | `2026-10-25-v194-ui-tooltips-and-data-truth_3-risk-format-and-sectors.md` | V194-7..V194-9 | B4/B5 formatters; B6 backend `unmapped_count`; B6 banner |
| 4 | `2026-10-25-v194-ui-tooltips-and-data-truth_4-metric-basis-and-legs.md` | V194-10..V194-12 | B8 backend money drawdown; B8 tiles; B3 leg label and `leg_exit_reason` |
| 5 | `2026-10-25-v194-ui-tooltips-and-data-truth_5-leg-surfaces-and-titles.md` | V194-13..V194-15 | B3 Trades/Dashboard surfaces; A3 scanner, allow-list, conversions |
| 6 | `2026-10-25-v194-ui-tooltips-and-data-truth_6-content-audit-and-release.md` | V194-16..V194-17 | A4 content audit; full suite, replica layout audit, merge |

## Task ledger

| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |
|---|---|---|---|---|---|---|---|
| V194-1 | Worktree; global popover polyfill for the unit-test DOM | 1 | sonnet | A1 | C `frontend/src/app/testing/popover-polyfill.ts`; M `frontend/src/test-setup.ts`, `frontend/src/app/ui/hint.spec.ts` | worktree branch `2026-10-25-v194-ui-tooltips-and-data-truth`; `installPopoverPolyfill(): void` (idempotent; patches `HTMLElement.prototype.showPopover/hidePopover/togglePopover` when absent, reflects state as attribute `data-popover-open`, throws `InvalidStateError` like engines do on double show/hide); `POPOVER_OPEN_ATTR = 'data-popover-open'` | `installDialogPolyfill` |
| V194-1b | `sb-hint` shows in the top layer, with feature detection and guarded calls | 1 | sonnet | A1 | M `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/hint.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` | `supportsPopover(): boolean` (exported from `hint.ts`); `.pop` carries `popover="manual"`, `[hidden]` binding removed | `Hint`, `installPopoverPolyfill`, `POPOVER_OPEN_ATTR` |
| V194-2 | `sb-hint` viewport clamp (flip above, shift sideways, 8px) | 1 | sonnet | A1 | M `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/hint.spec.ts` | `clampPopover(trigger: { top: number; bottom: number; left: number; right: number; width: number }, pop: { width: number; height: number }, viewport: { width: number; height: number }, align: 'center' \| 'left', margin = 8): { top: number; left: number; above: boolean }` (exported from `hint.ts`) | `supportsPopover` |
| V194-2b | `sb-hint` closes when its `<dialog>` host starts closing | 1 | sonnet | A1 | M `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/hint.spec.ts`, `frontend/src/app/ui/layout.ts`, `frontend/src/app/ui/confirm-dialog.ts` | `DIALOG_CLOSING_EVENT = 'sb-dialog-closing'` (exported from `hint.ts`, a bubbling-free `Event` dispatched on the `<dialog>` element) | `requestClose`, `installDialogPolyfill`, `provideMotion` |
| V194-3 | Layout audit `hint` check: pure `hintVerdict`, eighth `CHECKS` entry, Playwright hover/tap | 1 | sonnet | A2 | M `frontend/scripts/layout-audit-lib.mjs`, `frontend/scripts/layout-audit-lib.test.mjs`, `frontend/scripts/layout-audit.mjs` | `hintVerdict(rect: { left, top, width, height }, viewport: { width, height }, hits: { center: boolean, corner: boolean }) -> { ok: boolean, reason: 'zero-size' \| 'off-screen' \| 'covered-center' \| 'covered-corner' \| null }`; `CHECKS` gains `'hint'` (eighth, last); finding shape `{ route, width, check: 'hint', selector, text, detail }` with the trigger `aria-label` in `detail` | `CHECKS`, `vcenterGeometry`, `auditPage`, `auditWidth` |
| V194-4 | B1: diagnose on the replica, then fix lifecycle tab counts and the stuck Trading performance skeleton | 2 | opus | B1 | M `frontend/src/app/stores/dashboard.store.ts`, `frontend/src/app/stores/dashboard.store.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` | — | `todayLifecycle`, `loadToday`, `lifecycleOf`, `lifecycleCounts`, `todayBusy` |
| V194-5 | B2: "All" rows asks for `per_page=200`, fresh and restored from prefs | 2 | sonnet | B2 | M `frontend/src/app/workspaces/trades/trades.routes.ts`; C `frontend/src/app/workspaces/trades/trades.routes.spec.ts` | — | `queryFor`, `ALL_PER_PAGE`, `perPageForApi`, `readTablePerPage`, `DEFAULT_PER_PAGE` |
| V194-6 | B7: verify the money unit on production, then label the Analytics money toggle honestly | 2 | sonnet | B7 | M `frontend/src/app/ui/unit-format.ts`, `frontend/src/app/workspaces/analytics/scope-bar.ts`, `frontend/src/app/workspaces/analytics/scope-bar.spec.ts` | `QUOTE_CURRENCY_SYMBOL = '$'` (exported from `ui/unit-format.ts`; the symbol of the instruments' quote currency, used wherever a figure is shares × price difference) | `unitLabel`, `unitOptions`, `currency` |
| V194-7 | B4/B5: `shareCount` and `riskPct` formatters; unrounded totals; Risk, trade detail and row drawer use them | 3 | sonnet | B4; B5 | M `frontend/src/app/ui/format.ts`, `frontend/src/app/ui/format.spec.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/risk/risk.spec.ts`, `frontend/src/app/workspaces/trades/position-card.ts`, `frontend/src/app/workspaces/trades/why/sizing-panel.ts`, `frontend/src/app/workspaces/trades/trades.columns.ts` | `shareCount(value: number \| null \| undefined): string` (up to 2 decimals, trailing zeros dropped, null → `ABSENT`); `riskPct(value: number \| null \| undefined): string` (`"0.00%"` for exact zero, `"<0.01%"` for 0 < \|v\| < 0.01 with the sign kept, else 2 decimals + `%`, null → `ABSENT`) | `num`, `ABSENT`, `riskCell` |
| V194-8 | B6 backend: `prod-inspector` cause check; warning logs; `unmapped_count` through extracted helpers; `/risk` field and docstring | 3 | opus | B6 | M `swingbot/core/edge/portfolio_state.py`, `swingbot/admin/api_v1/risk.py`, `tests/admin/test_api_v1_risk.py`; C `tests/edge/test_portfolio_state_sectors.py` | `_load_sector_map() -> dict` and `_unmapped_count(open_trades: list, sectors: dict) -> int` (in `portfolio_state.py`); `state["unmapped_count"]`; `/api/v1/risk` response key `unmapped_count: int` | `collect_portfolio_state`, `sector_heat`, `sector_map`, `get_risk`, `_cached`, `portfolio_report` |
| V194-9 | B6 frontend: "Sector concentration cannot be assessed" banner vs true-zero state | 3 | sonnet | B6 | M `frontend/src/app/api/models.ts`, `frontend/src/app/stores/risk.store.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/risk/risk.spec.ts` | `Risk.unmapped_count?: number`; `RiskStore.unmappedCount` (computed, `data()?.unmapped_count ?? 0`) | `unmapped_count`, `sectorHeat`, `positions` |
| V194-10 | B8 backend: `metrics.max_drawdown_amount` on `/risk` over all closed trades | 4 | sonnet | B8 | M `swingbot/admin/api_v1/risk.py`, `tests/admin/test_api_v1_risk.py` | `/api/v1/risk` `metrics.max_drawdown_amount: {value: float \| None, n: int}`; `_pnl_amounts(closed: list) -> list[float]` (in `risk.py`) | `max_drawdown_r`, `_metric`, `r_multiples` |
| V194-11 | B8 frontend: `sb-stat-tile` `about` hint; basis-named Sharpe / Max drawdown tiles on Risk and Analytics; money drawdown on Risk; footnote removed | 4 | sonnet | B8 | M `frontend/src/app/ui/stat-tile.ts`, `frontend/src/app/ui/stat-tile.spec.ts`, `frontend/src/app/api/models.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/risk/risk.spec.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts` | `StatTile.about` (`input<string \| undefined>(undefined)`, renders `<sb-hint [text]="about()" [label]="'About ' + label()">` beside the label); `RiskMetrics.max_drawdown_amount?: RiskMetric` | `max_drawdown_amount`, `QUOTE_CURRENCY_SYMBOL`, `metricTiles`, `kpiTiles`, `Hint` |
| V194-12 | B3 data and helper: `leg_exit_reason` on leg rows; shared `legLabel` and `LEG_HINT_TEXT`; Calendar uses them | 4 | sonnet | B3 | M `swingbot/admin/api_v1/trades.py`, `tests/admin/test_api_v1_trades.py`, `frontend/src/app/api/models.ts`, `frontend/src/app/workspaces/calendar/day/day-trade-card.ts`, `frontend/src/app/workspaces/calendar/calendar.ts`; C `frontend/src/app/workspaces/trades/leg-label.ts`, `frontend/src/app/workspaces/trades/leg-label.spec.ts` | leg-row field `leg_exit_reason: str \| None`; `TradeRow.leg_exit_reason?: string \| null`; `interface LegLike { leg_index: number; leg_total: number; leg_exit_reason?: string \| null; exit_reason?: string \| null }`; `legLabel(row: LegLike): string \| null` (`"Leg N of M"`, `" · <reasonLabel>"` appended when a reason is present, `null` for single-leg); `LEG_HINT_TEXT` (one plan, each row its part's share, win rate and N count plans, not legs) | `_row_from_leg`, `_runner_exit_reason`, `reasonLabel`, `CalendarTrade` |
| V194-13 | B3 surfaces: leg label and hint on Trades (table, compact rows, drawer) and the Dashboard positions table; Trades total counts legs or plans, stated | 5 | sonnet | B3 | M `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/trades/trades.spec.ts`, `frontend/src/app/workspaces/trades/trades.columns.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, `frontend/src/app/workspaces/dashboard/trade-drawer.ts` | — | `legLabel`, `LEG_HINT_TEXT`, `leg_exit_reason`, `isPartialLeg`, `partialOpenTitle`, `rangeLabel` |
| V194-14 | A3 part 1: `title-usage.spec.ts` scanner, allow-list, conversions outside Analytics | 5 | sonnet | A3 | C `frontend/src/app/ui/title-usage.spec.ts`, `frontend/src/app/ui/title-usage.allow.ts`; M `frontend/src/app/ui/layout.ts`, `frontend/src/app/ui/stat-tile.ts`, `frontend/src/app/ui/status-cell.ts`, `frontend/src/app/ui/plan-cell.ts`, `frontend/src/app/workspaces/calendar/day/calendar-day.ts`, `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/trades/trade-detail.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/gallery/gallery.ts`, `frontend/src/app/workspaces/system/settings-tab.ts`, `frontend/src/app/workspaces/versions/versions.ts` (and every other non-Analytics file the scan lists, named in the task) | `TitleSite`; `interface TitleSite { file: string; binding: string; kind: 'echo' \| 'control-name' \| 'explanation-pending'; note: string }`; `TITLE_ALLOW: readonly TitleSite[]`; `TITLE_PENDING` (the `explanation-pending` subset, Analytics only); `TITLE_INPUT_ELEMENTS` | `Hint`, `StatTile.about` |
| V194-15 | A3 part 2: convert the Analytics explanation sites; `TITLE_PENDING` empty | 5 | sonnet | A3 | M `frontend/src/app/ui/title-usage.allow.ts`, `frontend/src/app/ui/title-usage.spec.ts`, `frontend/src/app/workspaces/analytics/tabs/partials.ts`, `frontend/src/app/workspaces/analytics/tabs/attribution.ts`, `frontend/src/app/workspaces/analytics/tabs/tuning.ts`, `frontend/src/app/workspaces/analytics/tabs/pipeline.ts`, `frontend/src/app/workspaces/analytics/tabs/edge.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.ts`, `frontend/src/app/workspaces/analytics/tabs/execution.ts`, `frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts`, `frontend/src/app/workspaces/analytics/tabs/variance-band-panel.ts` | — | `TITLE_ALLOW`, `TITLE_PENDING`, `TitleSite` |
| V194-16 | A4 content audit: every `sb-hint` text and chart tooltip against the code that computes it; fixes; audit table in the task notes | 6 | opus | A4 | M the hint and chart-tooltip sites the audit marks `caveat added` / `fixed text` / `fixed figure` (named per row in the task; candidates `frontend/src/app/ui/chart-tooltip.ts` consumers `bar-list.ts`, `dot-plot.ts`, `heat-grid.ts`, `histogram.ts`, `share-bar.ts`, `strip-plot.ts`, `waterfall.ts`, and `analytics/tabs/*.ts`) | the A4 audit table (route, label, verdict) in the task notes | `LEG_HINT_TEXT`, `StatTile.about`, `QUOTE_CURRENCY_SYMBOL`, `TITLE_ALLOW` |
| V194-17 | Full suite; replica layout audit (`hint` included) at 390/768/1440; merge to `main`; post-deploy check recorded | 6 | haiku | Verification | — | — | `hintVerdict`, `CHECKS` |
