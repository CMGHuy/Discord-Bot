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
that says "No sector exposure" because the sector map is empty, money in
the instruments' quote currency (USD) shown as if it were the account's
(€) with no conversion anywhere, and two Sharpe/drawdown pairs with the
same names and different populations.

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
banner instead of a reassuring zero, every money figure the admin API
serves is converted into the account currency at each leg's exit-date FX
rate (a missing rate shown as a caveat, never assumed 1.0), and
Sharpe/drawdown tiles name their basis, population, N and the paper /
gross / pre-tax caveat.

In idea: fix the primitive once (`sb-hint`), make the audit prove it on a
real browser, then correct each figure at the point it is formatted or
labelled, adding one backend field where the data exists but the response
does not carry it (`unmapped_count`, `leg_exit_reason`,
`max_drawdown_amount`), plus one read-side FX conversion seam for admin
money (partner decision, 2026-10-25). Nothing the bot computes for trading
changes: `universe.sector_map` and the universe data stay as they are
because the walk-forward replay and the weekly retrospective read them
too, and the stored `realized_pnl_amount` (which feeds the account
balance, hence sizing and the kill-switch) stays in quote currency.

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
- **FX conversion (V194-6..V194-6c).** `swingbot/core/marketdata/fx.py`
  (`fx_rate`, `quote_currency_code`, `account_currency_code`) reads FX
  pairs through the shared daily-bar cache;
  `swingbot/admin/api_v1/money.py` `to_account_currency` converts closed
  trade and leg rows once, where the admin read paths load them, before
  any sum; rows without a rate carry `fx_missing` and payloads
  `fx_missing_count`, which the frontend turns into a caveat.
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
- **B7 -- partner decision (2026-10-25, AskUserQuestion): add FX
  conversion in v194**, replacing the honest-`$` relabel. Found by the
  brief and the index writer: no FX conversion exists anywhere in
  `swingbot/`; `realized_pnl_amount` is `shares * (exit_price - entry)` in
  each instrument's quote currency (settled at
  `swingbot/core/tracking/performance.py:960-972`, leg split at `:511-517`,
  leg rows recomputed at `swingbot/admin/api_v1/trades.py:529`), and
  `CURRENCY_SYMBOL` (`swingbot/config.py:510`) only picks a symbol.
  Defaults set by the controller (no paid services):
  - **Rate source:** yfinance FX pairs (`EURUSD=X` style,
    `{QUOTE}{ACCOUNT}=X`) daily close, fetched through the shared daily-bar
    path (`swingbot/core/marketdata/providers/router.py`
    `daily_bars_between`) so it lands in the existing OHLCV cache
    (`docs/claude/known-traps.md`: two caches; never add a third).
  - **Point in time:** the rate on each leg's exit date (`closed_at`; a leg
    row's own close); fallback the last prior trading day's close.
  - **Per instrument:** the quote currency comes from the ticker
    (`swingbot/core/marketdata/data.py` `_provider_currency_code`; a
    Euronext ticker is already EUR). The account currency's ISO code is
    derived from `CURRENCY_SYMBOL` through the inverse of
    `CURRENCY_SYMBOLS`. Same currency -> identity, no fetch (a USD account
    converts nothing).
  - **One conversion, server-side:** every money figure the admin API
    serves (trade and leg rows, dashboard P&L, analytics sums and equity
    `cum_pnl`, calendar, risk `max_drawdown_amount`) is in the account
    currency, and the frontend keeps `connection.currency()` as the symbol
    everywhere, the Analytics toggle included (the spec's "€, $, £" test
    stands). V194-6b's first step maps every admin money path to the loader
    it reads and wraps the shared loader(s), not each sum.
  - **A missing rate is visible, never 1.0:** the row keeps
    `realized_pnl_amount: null` plus `fx_missing: true`, sums report
    `fx_missing_count`, and the UI shows a caveat naming the count.
  - **Stored data and trading stay as they are (partner confirmed
    display-only, 2026-10-25):** the stored
    `realized_pnl_amount` stays in quote currency because it also feeds the
    account balance (`swingbot/core/planning/account.py`
    `_sum_realized_pnl`), hence 2% sizing, the kill-switch drawdown and the
    growth path, which this spec excludes. Conversion is read-side at the
    admin API seam: no schema change, no `schema-evolution.md` step.
    Discord commands (`!trades`, `!pnl`) keep today's figures and are
    recorded as a follow-up.
- **B8 money drawdown.** `GET /risk` metrics carry R only. V194-10 adds
  `metrics.max_drawdown_amount` (`{value, n, fx_missing_count}`): the
  peak-to-trough decline of the cumulative realised P&L **converted to the
  account currency** (`to_account_currency`, V194-6b) over all closed
  trades; Risk's tile shows it with `connection.currency()`. Trades with a
  missing rate are excluded and counted.
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
  - V194-4 → V194-4b (B1): `dashboard.store.ts`, `dashboard.ts`, the trading
    performance panel.
  - V194-5 (B2): `trades.routes.ts` and its spec.
  - **FX lane** V194-6 → V194-6a → V194-6b → V194-6c (B7): sequential; V194-6b
    consumes V194-6's `fx_rate`, V194-6c the response fields V194-6b
    adds. Files: `swingbot/core/marketdata/fx.py`,
    `swingbot/admin/api_v1/money.py`, the admin `trades.py` /
    `analytics.py` / `dashboard.py` and `core/analytics/pnl_calendar.py`
    read paths, then `analytics/scope-bar.ts` and `calendar.ts`.
  - **Backend lane** V194-8 → V194-10: sequential, both edit
    `swingbot/admin/api_v1/risk.py` and `tests/admin/test_api_v1_risk.py`.
  - **Risk / models lane** V194-7 → V194-9 → V194-11 → V194-12 → V194-13:
    sequential. V194-7, V194-9 and V194-11 all edit
    `workspaces/risk/risk.ts` and `risk.spec.ts`; V194-9, V194-11 and
    V194-12 all edit `api/models.ts`; V194-7 and V194-13 both edit
    `trades.columns.ts`.
- Cross-lane contract edges: V194-9 starts after V194-8 (consumes
  `unmapped_count`); V194-11 after V194-10 (`max_drawdown_amount`) and
  V194-6c (`fx_missing_count`, both touch Analytics and `models.ts`);
  V194-10 after V194-6b (consumes `to_account_currency`); V194-12 after
  V194-6b (both edit `swingbot/admin/api_v1/trades.py`) and V194-6c
  (both edit `calendar.ts`); V194-9 after V194-6c (both edit
  `models.ts`); V194-13 after V194-4b (both edit `dashboard.ts`).
- **V194-14 after every B task** (it sweeps `title` sites in files B tasks
  edit, and B3/B8 add hints the allow-list must not list); V194-15 after
  V194-14 (same allow-list file); V194-16 after V194-15 (it audits every
  hint, including those added by A3, B3 and B8); V194-16b (docs only)
  after V194-3, parallel to everything else; V194-17 last.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-25-v194-ui-tooltips-and-data-truth_1-hint-top-layer-and-audit.md` | V194-1..V194-3 | worktree; popover polyfill; `sb-hint` top layer, clamp, dialog host close; layout-audit `hint` check |
| 2 | `2026-10-25-v194-ui-tooltips-and-data-truth_2-dashboard-trades-unit.md` | V194-4..V194-6a | B1 lifecycle counts (diagnose first); B2 "All" rows; B7 FX rate provider |
| 2b | `2026-10-25-v194-ui-tooltips-and-data-truth_2b-fx-conversion.md` | V194-6b..V194-6c | B7 server-side conversion seam; currency label and missing-rate caveat |
| 3 | `2026-10-25-v194-ui-tooltips-and-data-truth_3-risk-format-and-sectors.md` | V194-7..V194-9 | B4/B5 formatters; B6 backend `unmapped_count`; B6 banner |
| 4 | `2026-10-25-v194-ui-tooltips-and-data-truth_4-metric-basis-and-legs.md` | V194-10..V194-12 | B8 backend money drawdown; B8 tiles; B3 leg label and `leg_exit_reason` |
| 5 | `2026-10-25-v194-ui-tooltips-and-data-truth_5-leg-surfaces-and-titles.md` | V194-13..V194-15 | B3 Trades/Dashboard surfaces; A3 scanner, allow-list, conversions |
| 6 | `2026-10-25-v194-ui-tooltips-and-data-truth_6-content-audit-and-release.md` | V194-16..V194-17 | A4 content audit; ui-design checklist names the `hint` check; full suite, replica layout audit, merge |

## Task ledger

| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |
|---|---|---|---|---|---|---|---|
| V194-1 | Worktree; global popover polyfill for the unit-test DOM | 1 | sonnet | A1 | C `frontend/src/app/testing/popover-polyfill.ts`; M `frontend/src/test-setup.ts`, `frontend/src/app/ui/hint.spec.ts` | worktree branch `2026-10-25-v194-ui-tooltips-and-data-truth`; `installPopoverPolyfill(): void` (idempotent; patches `HTMLElement.prototype.showPopover/hidePopover/togglePopover` when absent, reflects state as attribute `data-popover-open`, throws `InvalidStateError` like engines do on double show/hide); `POPOVER_OPEN_ATTR = 'data-popover-open'` | `installDialogPolyfill` |
| V194-1b | `sb-hint` shows in the top layer, with feature detection and guarded calls | 1 | sonnet | A1 | M `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/hint.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` | `supportsPopover(): boolean` (exported from `hint.ts`); `.pop` carries `popover="manual"`, `[hidden]` binding removed | `Hint`, `installPopoverPolyfill`, `POPOVER_OPEN_ATTR` |
| V194-2 | `sb-hint` viewport clamp (flip above, shift sideways, 8px) | 1 | sonnet | A1 | M `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/hint.spec.ts` | `clampPopover(trigger: { top: number; bottom: number; left: number; right: number; width: number }, pop: { width: number; height: number }, viewport: { width: number; height: number }, align: 'center' \| 'left', margin = 8): { top: number; left: number; above: boolean }` (exported from `hint.ts`) | `supportsPopover` |
| V194-2b | `sb-hint` closes when its `<dialog>` host starts closing | 1 | sonnet | A1 | M `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/hint.spec.ts`, `frontend/src/app/ui/layout.ts`, `frontend/src/app/ui/confirm-dialog.ts` | `DIALOG_CLOSING_EVENT = 'sb-dialog-closing'` (exported from `hint.ts`, a bubbling-free `Event` dispatched on the `<dialog>` element) | `requestClose`, `installDialogPolyfill`, `provideMotion` |
| V194-3 | Layout audit `hint` check: pure `hintVerdict`, eighth `CHECKS` entry, Playwright hover/tap | 1 | sonnet | A2 | M `frontend/scripts/layout-audit-lib.mjs`, `frontend/scripts/layout-audit-lib.test.mjs`, `frontend/scripts/layout-audit.mjs` | `hintVerdict(rect: { left, top, width, height }, viewport: { width, height }, hits: { center: boolean, corner: boolean }) -> { ok: boolean, reason: 'zero-size' \| 'off-screen' \| 'covered-center' \| 'covered-corner' \| null }`; `CHECKS` gains `'hint'` (eighth, last); finding shape `{ route, width, check: 'hint', selector, text, detail }` with the trigger `aria-label` in `detail` | `CHECKS`, `vcenterGeometry`, `auditPage`, `auditWidth` |
| V194-4 | B1: diagnose on the replica (F1 superseded / F2 failed / F3 cancelled / F4 stop), then fix the dashboard store's today load | 2 | opus | B1 | M `frontend/src/app/stores/dashboard.store.ts`, `frontend/src/app/stores/dashboard.store.spec.ts` | store state `todayError: string \| null` | `todayLifecycle`, `loadToday`, `lifecycleOf`, `lifecycleCounts`, `todayBusy` |
| V194-4b | B1: tab counts fall back to the scoped open counts; Realised today says when today failed; replica confirmed at 390/768/1440 | 2 | sonnet | B1 | M `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` | `TradingPerformance.todayError` (`input<string \| null>(null)`); `ALL_TIME_STATUSES` | `todayError`, `todayLifecycle`, `lifecycle`, `lifecycleCounts`, `todaySub` |
| V194-5 | B2: "All" rows asks for `per_page=200`, fresh and restored from prefs | 2 | sonnet | B2 | M `frontend/src/app/workspaces/trades/trades.routes.ts`; C `frontend/src/app/workspaces/trades/trades.routes.spec.ts` | — | `queryFor`, `ALL_PER_PAGE`, `perPageForApi`, `readTablePerPage`, `DEFAULT_PER_PAGE` |
| V194-6 | B7 FX: `prod-inspector` check (distinct quote currencies of closed-trade tickers, the account symbol); `fx_rate` over the yfinance daily cache (`data_refresh.refresh_symbol` + `data_store.load_normalized`; `daily_bars_between` is Alpaca-only) | 2 | sonnet | B7 | C `swingbot/core/marketdata/fx.py`, `tests/marketdata/test_fx.py` | `fx_rate(from_code: str, to_code: str, on: date) -> float \| None` (1.0 when equal; `{FROM}{TO}=X` daily close on `on`, else the last prior close within `FALLBACK_DAYS` = 7, else `None`; minor units via `MINOR_UNITS` -- `GBp`, `ZAc`, `ILA` scale by 0.01); `FALLBACK_DAYS`; `MINOR_UNITS` | `refresh_symbol`, `load_normalized`, `CURRENCY_SYMBOLS` |
| V194-6a | B7 FX: `account_currency_code` and `quote_currency_code` (Yahoo code returned unnormalised; `GBp` resolved only in `fx_rate`) | 2 | sonnet | B7 | M `swingbot/core/marketdata/fx.py`, `tests/marketdata/test_fx.py` | `account_currency_code() -> str` (ISO code from `CURRENCY_SYMBOL` via the inverse of `CURRENCY_SYMBOLS`, `EUR` when unknown); `quote_currency_code(ticker: str) -> str \| None` | `fx_rate`, `CURRENCY_SYMBOLS`, `_provider_currency_code` |
| V194-6b | B7 FX: one server-side conversion seam for admin money (trade and leg rows, dashboard, analytics sums and equity, calendar); `fx_missing` flags | 2b | opus | B7 | C `swingbot/admin/api_v1/money.py`, `tests/admin/test_api_v1_money.py`; M `swingbot/admin/api_v1/trades.py`, `swingbot/admin/api_v1/analytics.py`, `swingbot/admin/api_v1/dashboard.py`, `swingbot/core/analytics/pnl_calendar.py`, `tests/admin/test_api_v1_trades.py`, `tests/admin/test_api_v1_analytics.py` | `to_account_currency(rows: list[dict], *, account: str \| None = None) -> list[dict]` (copies; converts `realized_pnl_amount` by `fx_rate(quote_currency_code(row['ticker']), account, closed date)`; sets `fx_missing: bool`, and `realized_pnl_amount: None` when the rate is missing); `MONEY_FIELDS`; response field `fx_missing_count: int` on analytics, dashboard and calendar payloads; row field `fx_missing: bool` | `fx_rate`, `quote_currency_code`, `account_currency_code`, `_row_from_leg`, `realized_pnl_amount` |
| V194-6c | B7 frontend: Analytics money toggle labelled `connection.currency()`; missing-rate caveat where `fx_missing_count > 0` | 2b | sonnet | B7 | M `frontend/src/app/api/models.ts`, `frontend/src/app/workspaces/analytics/scope-bar.ts`, `frontend/src/app/workspaces/analytics/scope-bar.spec.ts`, `frontend/src/app/workspaces/calendar/calendar.ts`, `frontend/src/app/workspaces/calendar/calendar.spec.ts` | `fx_missing_count?: number` on the analytics, dashboard and calendar interfaces; `TradeRow.fx_missing?: boolean`; `fxMissingText(n: number): string` (exported from `scope-bar.ts`) | `fx_missing_count`, `fx_missing`, `currency`, `unitOptions` |
| V194-7 | B4/B5: `shareCount` and `riskPct` formatters; unrounded totals; Risk, trade detail and row drawer use them | 3 | sonnet | B4; B5 | M `frontend/src/app/ui/format.ts`, `frontend/src/app/ui/format.spec.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/risk/risk.spec.ts`, `frontend/src/app/workspaces/trades/position-card.ts`, `frontend/src/app/workspaces/trades/why/sizing-panel.ts`, `frontend/src/app/workspaces/trades/trades.columns.ts` | `shareCount(value: number \| null \| undefined): string` (up to 2 decimals, trailing zeros dropped, null → `ABSENT`); `riskPct(value: number \| null \| undefined): string` (`"0.00%"` for exact zero, `"<0.01%"` for 0 < \|v\| < 0.01 with the sign kept, else 2 decimals + `%`, null → `ABSENT`) | `num`, `ABSENT`, `riskCell` |
| V194-8 | B6 backend: `prod-inspector` cause check; warning logs; `unmapped_count` through extracted helpers; `/risk` field and docstring | 3 | opus | B6 | M `swingbot/core/edge/portfolio_state.py`, `swingbot/admin/api_v1/risk.py`, `tests/admin/test_api_v1_risk.py`; C `tests/edge/test_portfolio_state_sectors.py` | `_load_sector_map() -> dict` and `_unmapped_count(open_trades: list, sectors: dict) -> int` (in `portfolio_state.py`); `state["unmapped_count"]`; `/api/v1/risk` response key `unmapped_count: int` | `collect_portfolio_state`, `sector_heat`, `sector_map`, `get_risk`, `_cached`, `portfolio_report` |
| V194-9 | B6 frontend: "Sector concentration cannot be assessed" banner vs true-zero state | 3 | sonnet | B6 | M `frontend/src/app/api/models.ts`, `frontend/src/app/stores/risk.store.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/risk/risk.spec.ts` | `Risk.unmapped_count?: number`; `RiskStore.unmappedCount` (computed, `data()?.unmapped_count ?? 0`) | `unmapped_count`, `sectorHeat`, `positions` |
| V194-10 | B8 backend: `metrics.max_drawdown_amount` on `/risk` over all closed trades, converted to the account currency | 4 | sonnet | B8 | M `swingbot/admin/api_v1/risk.py`, `tests/admin/test_api_v1_risk.py` | `/api/v1/risk` `metrics.max_drawdown_amount: {value: float \| None, n: int, fx_missing_count: int}`; `_pnl_amounts(closed: list) -> list[float]` (in `risk.py`) | `max_drawdown_r`, `_metric`, `r_multiples`, `to_account_currency` |
| V194-11 | B8 frontend: `sb-stat-tile` `about` hint; basis-named Sharpe / Max drawdown tiles on Risk and Analytics; money drawdown on Risk; footnote removed | 4 | sonnet | B8 | M `frontend/src/app/ui/stat-tile.ts`, `frontend/src/app/ui/stat-tile.spec.ts`, `frontend/src/app/api/models.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/risk/risk.spec.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts` | `StatTile.about` (`input<string \| undefined>(undefined)`, renders `<sb-hint [text]="about()" [label]="'About ' + label()">` beside the label); `RiskMetrics.max_drawdown_amount?: RiskMetric` | `max_drawdown_amount`, `fx_missing_count`, `metricTiles`, `kpiTiles`, `Hint` |
| V194-12 | B3 data and helper: `leg_exit_reason` on leg rows; shared `legLabel` and `LEG_HINT_TEXT`; Calendar uses them | 4 | sonnet | B3 | M `swingbot/admin/api_v1/trades.py`, `tests/admin/test_api_v1_trades.py`, `frontend/src/app/api/models.ts`, `frontend/src/app/workspaces/calendar/day/day-trade-card.ts`, `frontend/src/app/workspaces/calendar/calendar.ts`; C `frontend/src/app/workspaces/trades/leg-label.ts`, `frontend/src/app/workspaces/trades/leg-label.spec.ts` | leg-row field `leg_exit_reason: str \| None`; `TradeRow.leg_exit_reason?: string \| null`; `interface LegLike { leg_index: number; leg_total: number; leg_exit_reason?: string \| null; exit_reason?: string \| null }`; `legLabel(row: LegLike): string \| null` (`"Leg N of M"`, `" · <reasonLabel>"` appended when a reason is present, `null` for single-leg); `LEG_HINT_TEXT` (one plan, each row its part's share, win rate and N count plans, not legs) | `_row_from_leg`, `_runner_exit_reason`, `reasonLabel`, `CalendarTrade` |
| V194-13 | B3 surfaces: leg label and hint on Trades (table, compact rows, drawer) and the Dashboard positions table; Trades total counts legs or plans, stated; missing-FX-rate caveat on Trades and Dashboard (`fx_missing_count`, `fx_missing` rows, `fxMissingText`) | 5 | sonnet | B3 | M `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/trades/trades.spec.ts`, `frontend/src/app/workspaces/trades/trades.columns.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, `frontend/src/app/workspaces/dashboard/trade-drawer.ts` | — | `legLabel`, `LEG_HINT_TEXT`, `leg_exit_reason`, `isPartialLeg`, `partialOpenTitle`, `rangeLabel`, `fx_missing_count`, `fxMissingText` |
| V194-14 | A3 part 1: `title-usage.spec.ts` scanner, allow-list, conversions outside Analytics | 5 | sonnet | A3 | C `frontend/src/app/ui/title-usage.spec.ts`, `frontend/src/app/ui/title-usage.allow.ts`; M `frontend/src/app/ui/layout.ts`, `frontend/src/app/ui/stat-tile.ts`, `frontend/src/app/ui/status-cell.ts`, `frontend/src/app/ui/plan-cell.ts`, `frontend/src/app/workspaces/calendar/day/calendar-day.ts`, `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/trades/trade-detail.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/gallery/gallery.ts`, `frontend/src/app/workspaces/system/settings-tab.ts`, `frontend/src/app/workspaces/versions/versions.ts` (and every other non-Analytics file the scan lists, named in the task) | `TitleSite`; `interface TitleSite { file: string; binding: string; kind: 'echo' \| 'control-name' \| 'explanation-pending'; note: string }`; `TITLE_ALLOW: readonly TitleSite[]`; `TITLE_PENDING` (the `explanation-pending` subset, Analytics only); `TITLE_INPUT_ELEMENTS` | `Hint`, `StatTile.about` |
| V194-15 | A3 part 2: convert the Analytics explanation sites; `TITLE_PENDING` empty | 5 | sonnet | A3 | M `frontend/src/app/ui/title-usage.allow.ts`, `frontend/src/app/ui/title-usage.spec.ts`, `frontend/src/app/workspaces/analytics/tabs/partials.ts`, `frontend/src/app/workspaces/analytics/tabs/attribution.ts`, `frontend/src/app/workspaces/analytics/tabs/tuning.ts`, `frontend/src/app/workspaces/analytics/tabs/pipeline.ts`, `frontend/src/app/workspaces/analytics/tabs/edge.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.ts`, `frontend/src/app/workspaces/analytics/tabs/execution.ts`, `frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts`, `frontend/src/app/workspaces/analytics/tabs/variance-band-panel.ts` | — | `TITLE_ALLOW`, `TITLE_PENDING`, `TitleSite` |
| V194-16 | A4 content audit: every `sb-hint` text and chart tooltip against the code that computes it; fixes; audit table in the task notes | 6 | opus | A4 | M the hint and chart-tooltip sites the audit marks `caveat added` / `fixed text` / `fixed figure` (named per row in the task; candidates `frontend/src/app/ui/chart-tooltip.ts` consumers `bar-list.ts`, `dot-plot.ts`, `heat-grid.ts`, `histogram.ts`, `share-bar.ts`, `strip-plot.ts`, `waterfall.ts`, and `analytics/tabs/*.ts`) | the A4 audit table (route, label, verdict) in the task notes | `LEG_HINT_TEXT`, `StatTile.about`, `fx_missing_count`, `TITLE_ALLOW` |
| V194-16b | `docs/claude/ui-design.md` § Checklist names the layout audit's `hint` check; `AGENTS.md` mirror | 6 | haiku | A2 | M `docs/claude/ui-design.md`, `AGENTS.md` | — | `hintVerdict`, `CHECKS` |
| V194-17 | Full suite; replica layout audit (`hint` included) at 390/768/1440; merge to `main`; post-deploy check recorded | 6 | haiku | Verification | — | — | `hintVerdict`, `CHECKS` |
