# v177 — Plan cell for trailing runners and closed partial trades: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V177-2:" -A 400 docs/superpowers/plans/2026-10-19-v177-runner-plan-cell_1-row-and-cell.md`.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-10-19-v177-runner-plan-cell-design.md](../specs/2026-10-19-v177-runner-plan-cell-design.md)
**Brief:** `.superpowers/briefs/2026-10-19-v177-runner-plan-cell.md`
**Worktree:** implement in `.claude/worktrees/2026-10-19-v177-runner-plan-cell` (branch of the same name, created in V177-1; `docs/claude/document-lifecycle.md`) for V177-1..V177-5 (the merge is V177-5's last steps); V177-6 and V177-7 run on `main` in the main tree.

## Goal

The Plan cell on the admin UI is the one place the partner reads a trade's
levels at a glance. Once TP1 is banked and the runner trails with no TP2, the
cell today reads `original entry → TP1 fill ✓ / current trailing stop`: the
plan's original TP1 and stop are gone, and nothing says what the trailing stop
locks in if price turns. On the live RKLB short (entry 60.67, TP1 58.33, stop
61.85, best 49.94, trailing stop 52.44) the partner could not see it. On the
Closed tab a partial trade's two leg rows both show the plan's TP1 as the
target, so the runner's real outcome appears nowhere in the cell.

Once this ships, a PARTIAL runner with a trailing stop shows two lines:
`60.67 → 58.33 / 61.85 (3.9% - 1.9%)` (the original plan, unsigned distances
from the entry, as today's shape) and `Trail 49.94 → 52.44 (+17.7% / +13.6%)`
(best price since TP1 → the price the trailing stop exits at, both as signed
per-share profit from the original entry). A closed partial trade shows the
runner's actual exit price in the target slot with its signed profit, and the
tooltip names what closed the runner (trailing stop, give-back stop, floor
stop, TP2, manual close, …). The cell prints numbers; each tooltip says what
they are and that the peak is unrealised and the exit figure is per share,
before costs and tax, and that broker orders are not synced.

How it works: the trades list row (`swingbot/admin/api_v1/trades.py`) gains
three derived fields (`tp1`, `runner_exit_price`, `runner_exit_reason`) and
always carries the two existing percentages (`best_pnl_pct`, `stop_pnl_pct`),
now computed in the row builder by the same helper the status bar uses, so
they survive a dead price feed. Nothing is stored; every value is derived from
fields the plan already holds. The frontend `PlanCell` gains optional inputs
that switch it into the two-line or the closed-runner form; the Dashboard's
positions table and the Trades page pass them through one pure gate function
keyed on `row.status`, so a TP1-leg row of a still-open plan keeps today's
cell.

It leaves alone: every signal, gate, stop, size and badge; `plan_view.py` and
every Discord surface (the v73 surface-agreement invariant holds because the
row's `stop_loss`/`target` do not change); PENDING and ACTIVE rows; a PARTIAL
plan with a TP2; the Gallery; the trade-detail panel; the P&L %, R and status
columns; legacy trades without a `plan_id`.

Success is measured by tests and by eye: the RKLB fixture produces exactly
`tp1 = 58.33`, `best_pnl_pct = 17.69`, `stop_pnl_pct = 13.57`; the exact-key
API contract and the detail-equals-list test stay green; the cell renders the
two RKLB lines verbatim; the three-width browser check (390/768/1440) shows no
wrapped line and no horizontal page scroll; and after deploy the production
RKLB row carries the new fields.

## Architecture

- **Backend row fields** (V177-1, `swingbot/admin/api_v1/trades.py`).
  `_row_from_plan` (cyclomatic complexity 15 at baseline, must not grow)
  builds its dict as today, then `row.update(_runner_cell_fields(plan, trade,
  row))` — one call, no new branch. The new helpers carry every condition.
  `_trailing_status_fields`' priced path swaps its direct
  `_trailing_pnl_ends(row, stop, best, is_bull)` call for
  `_runner_pnl_fields(row)` so the status bar and the Plan cell share one
  entry point (`_trailing_pnl_ends` stays the one formula). `_row_from_leg`
  clears `tp1`, `best_pnl_pct`, `stop_pnl_pct` on every leg row (leg rows are
  always `status: "CLOSED"`), keeping `bar_kind` and the runner-exit fields.
  `_row_from_trade` (legacy) emits all five keys as `None`. The exact-key
  `TRADE_ROW` contract gains the five keys.
- **PlanCell** (V177-2, `frontend/src/app/ui/plan-cell.ts`). New optional
  inputs; with none set, the template, text and tooltip are byte-identical to
  today. Runner mode (`planTp1` set) renders two block lines, each `nowrap`,
  each with its own `title`; closed-runner mode (`runnerExit` set) keeps the
  one-line shape with the runner exit in the target slot and a signed percent.
- **Template wiring** (V177-3). A pure `runnerCellInputs(row: TradeRow)` in
  a new `frontend/src/app/ui/runner-cell.ts` holds the status gate; the
  identical `#planCell` templates in `dashboard.ts` and `trades.ts` bind
  `@let rc = runnerCellInputs(row);` and pass `rc.*` to the cell.
- **Ship** (V177-4..V177-7): three-width browser check against a local
  instance on the production replica, the plan's one full suite, merge with
  both patch bumps, gated push (the push is the deploy), read-only production
  verification, `/panel`, `/close-out`.

**Tech Stack:** Python 3.11, Flask (`swingbot/admin/api_v1`), pytest (suite
`admin`, Postgres-backed `seed_store` fixtures), Angular 21 standalone/OnPush
components with signal inputs, Vitest 4 through `npx ng test`, ESLint,
Playwright via `frontend/scripts/browse.mjs`, GitHub Actions `deploy.yml`.

## Global Constraints

- Display only: no signal, gate, stop, size, badge or stored record changes. No schema change, no stored `runner_exit_*` field, no read-time upcasting (`schema-evolution.md`).
- `plan_view.py` is not edited. The row's `stop_loss`, `target`, `banked_exit_price` keep today's values (`tests/presentation/test_surface_agreement.py` stays green).
- Every function written or changed stays at cyclomatic complexity < 15; `_row_from_plan` (15 at baseline) must not get worse: new logic only in named helpers (`scripts/dev/complexity_gate.py`).
- Row contract is exact-key: every new key is emitted by `_row_from_plan` **and** `_row_from_trade` (as `None`), added to `TRADE_ROW` in `tests/admin/test_api_v1_trades.py`; `test_detail_row_fields_match_the_list_exactly` stays green.
- Percent formula (unchanged, `_trailing_pnl_ends`): `round((price − entry) × sign / entry × 100, 2)`, `sign = +1` long, `−1` short.
- Line-2 best price = `runner_best` (`runner_high_close`), falling back to the TP1 fill `banked_exit_price` when `None`; the backend percentages and the frontend best price use the same fallback.
- Runner exit: `len(legs) >= 2 and legs[-1].get("reason") != "tp1"` → last leg's `exit_price`; reason = `"giveback"` when that leg's `stop_source == "giveback"`, else the leg's `reason`. Manual close: `status == "CLOSED"`, exactly one leg with `.get("reason") == "tp1"`, `status_history[-1].reason == "manual"` → `trade["exit_price"]` (read in `_row_from_plan`, before `_row_from_leg` overwrites `exit_price`), reason `"manual"`; `None`/`None` when that price is `None`. Every leg read uses `.get` (legacy TP1 legs have no `reason`).
- Frontend: new `TradeRow` fields optional and nullable; no colour literals, no `.pos`/`.neg`/`.muted` selectors (`primitives.spec.ts`); colours via `var(--pos)`, `var(--neg)`, `var(--text-faint)`, `var(--text-secondary)`; spacing is literal text inside `.sep`, not margins; `npm run lint` clean (no new `eslint-suppressions.json` entries).
- Each cell line is its own block with `white-space: nowrap`; the 375px no-wrap constraint (`dashboard.ts:540-560`) applies per line; column widths and `inlineFrom` unchanged (`trades.columns.ts`).
- Copy: the cell never prints "TP2"; tooltips state "per share from the original entry", the peak is "unrealised", "before costs and tax", and that broker orders are not synced (exact strings in § PlanCell contract).
- Browser: Playwright only (`frontend/scripts/browse.mjs`), never claude-in-chrome; credentials only from `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD`, loaded inside the script, never printed; if either is missing the task stops and asks the partner (`AskUserQuestion`), never `admin`/`admin`, never a workaround.
- Production: only through `bash scripts/ops/ssh-hetzner.sh`, read-only; `git push origin main` (the deploy) only after the partner says yes through `AskUserQuestion`.
- Never `cd` in Bash: `git -C <tree>`, absolute paths; frontend commands from PowerShell with `Push-Location <tree>/frontend` … `Pop-Location`.
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`, `npx ng test --watch=false --include <spec>`); one full suite (V177-5) plus one full frontend run, both before the merge. No full suite after the merge.
- Tests that seed the store use the disposable Postgres test database: run `/replicate-prod-db` once in the session before the first DB-backed test run (CLAUDE.md); `docker compose --profile test up -d db-test` if it is down.

## Backend contract (V177-1, consumed by V177-2..V177-6)

New and changed helpers in `swingbot/admin/api_v1/trades.py`:

| Symbol | Signature | Returns |
|---|---|---|
| `_runner_cell_fields` | `(plan: dict, trade: dict \| None, row: dict) -> dict` | exactly the keys `tp1`, `best_pnl_pct`, `stop_pnl_pct`, `runner_exit_price`, `runner_exit_reason` |
| `_runner_best_or_fill` | `(row: dict) -> float \| None` | `row["runner_best"]` if a number, else `row["banked_exit_price"]` if a number, else `None` |
| `_runner_pnl_fields` | `(row: dict) -> dict` | `{"stop_pnl_pct", "best_pnl_pct"}`: `_trailing_pnl_ends(row, row["stop_loss"], _runner_best_or_fill(row), row["direction"] != "bearish")` when `row["status"] == "PARTIAL"`, `row["bar_kind"] == "trailing"` and stop/best are numbers; both `None` otherwise |
| `_runner_exit_fields` | `(plan: dict, trade: dict \| None) -> dict` | `{"runner_exit_price", "runner_exit_reason"}` per Global Constraints; both `None` unless `plan["status"] == "CLOSED"` |
| `_runner_exit_reason` | `(leg: dict) -> str \| None` | `"giveback"` if `leg.get("stop_source") == "giveback"`, else `leg.get("reason")` |
| `_closed_manually_after_tp1` | `(plan: dict, legs: list) -> bool` | the manual-close test in Global Constraints |
| `_RUNNER_CELL_CLEARED` | module dict `{"tp1": None, "best_pnl_pct": None, "stop_pnl_pct": None}` | merged into `_row_from_leg`'s `row.update` |

`tp1` = `plan.get("tp1")` when the row is a PARTIAL trailing row (same
condition as `_runner_pnl_fields`), else `None` — so a PARTIAL plan with a
`tp2`, ACTIVE, PENDING and CLOSED rows carry `tp1: None`.

Wire fields on every trades row (list, detail, close/cancel response):
`tp1: number | null`, `best_pnl_pct: number | null`, `stop_pnl_pct: number | null`,
`runner_exit_price: number | null`, `runner_exit_reason: string | null`.
`runner_exit_reason` values: `tp1_runner_trail`, `tp1_runner_be`,
`tp1_runner_tp2`, `tp1_runner_progress_stall`, `time_exit`, `giveback`,
`manual`, or any other leg reason string (passed through).

## PlanCell contract (V177-2, consumed by V177-3 and V177-4)

New inputs on `PlanCell` (`frontend/src/app/ui/plan-cell.ts`), all
`input<… | null>(null)`:

| Input | Mode | Meaning |
|---|---|---|
| `planTp1: number \| null` | runner (two-line) — non-null switches it on | line 1 target (original TP1) |
| `planStop: number \| null` | runner | line 1 stop (original stop, `risk_stop`) |
| `trailBest: number \| null` | runner | line 2 best price since TP1 |
| `trailBestPct: number \| null` | runner | line 2 max % gain (signed) |
| `trailExitPct: number \| null` | runner | line 2 % gain at exit (signed) |
| `runnerExit: number \| null` | closed-runner — non-null switches it on | target slot price |
| `runnerExitPct: number \| null` | closed-runner | signed % in the rise slot |
| `runnerExitReason: string \| null` | closed-runner | tooltip reason key |

Line 2's exit price is the existing `stop` input; line 1's entry is the
existing `entry` input. Line 2 renders only when `entry`, `stop`, `trailBest`,
`trailBestPct` and `trailExitPct` are all non-null; otherwise runner mode shows
line 1 alone. Direction for the tooltip sentence is inferred: short when
`planTp1 < entry`.

Exported from `plan-cell.ts`: `runnerExitLabel(reason: string | null): string`
mapping `tp1_runner_trail → 'trailing stop'`, `giveback → 'give-back stop'`,
`tp1_runner_be → 'floor stop'`, `tp1_runner_tp2 → 'TP2'`,
`manual → 'manual close'`, `tp1_runner_progress_stall → 'progress stall'`,
`time_exit → 'time exit'`, anything else → `'runner exit'`.

DOM in runner mode: root `<span class="plan runner">` (no `title`), children
`<span class="line l1" [title]>` and `<span class="line l2" [title]>`; line 2
starts with `<span class="trail">Trail</span>`. Closed-runner mode keeps the
legacy single `.plan` root with its `title`. Text (whitespace-collapsed):

- RKLB runner, line 1: `60.67 → 58.33 / 61.85 (3.9% - 1.9%)`
- RKLB runner, line 2: `Trail 49.94 → 52.44 (+17.7% / +13.6%)` (inputs `trailBestPct 17.69`, `trailExitPct 13.57`, `stop 52.437`; percents via `pct(v, 1)`)
- RKLB closed runner: `60.67 → 52.44 / 61.85 (+13.6% - 1.9%)` (`runnerExit 52.44`, `runnerExitPct` from `bankedLegPct(60.67, 52.44, 'bearish')`)

Tooltips (exact, `{…}` substituted, numbers via `num`/`pct(v, 1)`):

- line 1: `Original plan (TP1 already filled): entry → TP1 / original stop. Percentages are the distance from the entry to each level.`
- line 2 (`stopKind` `trailing`; `derived_floor` replaces `Trailing stop` with `Locked-in floor` and `the trailing stop` with `the locked-in floor`): `Trailing stop. Best price so far → price the trailing stop would exit at. {bestPct} is the peak since TP1 (unrealised); {exitPct} is the profit if the stop fills at {exit}, per share from the original entry, before costs and tax. {A short gains when price falls.|A long gains when price rises.} The bot's paper level: your broker's resting orders are not synced, update your stop yourself.`
- closed-runner: `Entry {entry} · Runner exit ({runnerExitLabel(reason)}): {runnerExit}, {pct} per share from the original entry · Stop {stop}`

## Gate contract (V177-3)

`frontend/src/app/ui/runner-cell.ts` exports:

```ts
export interface RunnerCellInputs {
  planTp1: number | null; planStop: number | null;
  trailBest: number | null; trailBestPct: number | null; trailExitPct: number | null;
  runnerExit: number | null; runnerExitPct: number | null; runnerExitReason: string | null;
}
export const NO_RUNNER_CELL: RunnerCellInputs; // every field null
export function runnerCellInputs(row: TradeRow): RunnerCellInputs;
```

`status === 'PARTIAL' && bar_kind === 'trailing' && tp1 != null` → runner
fields (`trailBest = runner_best ?? banked_exit_price`); `status === 'CLOSED'
&& runner_exit_price != null` → closed fields (`runnerExitPct =
bankedLegPct(entry, runner_exit_price, direction)`); otherwise
`NO_RUNNER_CELL`. Both components expose it as
`protected readonly runnerCellInputs = runnerCellInputs;`.

## Parallelisation

At most 2 implementers at once; disjoint files and no contract dependency are required for a pair.

- **V177-1 first, alone:** it creates the worktree, and its wire fields are the contract V177-3 consumes.
- **V177-2 parallel with V177-1:** frontend `plan-cell.ts`/`plan-cell.spec.ts`/`models.ts` only, disjoint from the backend; it consumes only the field names fixed in § Backend contract, not V177-1's code. It must start after V177-1's Step 1 (the worktree exists).
- **V177-2 → V177-3 sequential:** V177-3 binds the PlanCell inputs V177-2 creates and imports `runnerExitLabel`/`bankedLegPct` beside them; its specs render the real cell.
- **V177-1 → V177-3 sequential:** V177-3's fixtures use the exact wire field names and the backend's gating (fields `None` on leg rows) that V177-1 pins in tests.
- **V177-3 → V177-4 sequential:** the browser check needs the whole stack (backend fields + cell + wiring) running.
- **V177-4 → V177-5 sequential:** the full suite runs once, on the final code; a layout fix from the browser check must land before it.
- **V177-5 → V177-6 → V177-7 strictly sequential:** merge before push (the push is the deploy); production verification needs the deployed image; `/panel` reviews the shipped diff and `/close-out` needs every task merged.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-19-v177-runner-plan-cell_1-row-and-cell.md` | V177-1..V177-3 | backend row fields + contract tests, PlanCell inputs/template/tooltips/styles, Dashboard and Trades template wiring |
| 2 | `2026-10-19-v177-runner-plan-cell_2-ship.md` | V177-4..V177-7 | three-width browser check, full suite + merge + patch bumps, gated deploy + production verification, `/panel` + `/close-out` |

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V177-1 | Backend row fields: `tp1`, price-free percentages, runner exit, leg clearing, contract | 1 | opus | M `swingbot/admin/api_v1/trades.py`, M `tests/admin/test_trades_partial_row.py`, M `tests/admin/test_api_v1_trades.py` | worktree `.claude/worktrees/2026-10-19-v177-runner-plan-cell`; helpers and wire fields in § Backend contract (`_runner_cell_fields(plan, trade, row) -> dict`, `_runner_best_or_fill(row)`, `_runner_pnl_fields(row) -> dict`, `_runner_exit_fields(plan, trade) -> dict`, `_runner_exit_reason(leg) -> str \| None`, `_closed_manually_after_tp1(plan, legs) -> bool`, `_RUNNER_CELL_CLEARED`); `TRADE_ROW` gains `tp1`, `best_pnl_pct`, `stop_pnl_pct`, `runner_exit_price` (`NULLABLE_NUMBER`), `runner_exit_reason` (`NULLABLE_STR`) |
| V177-2 | PlanCell runner and closed-runner forms + `TradeRow` fields | 1 | sonnet | M `frontend/src/app/ui/plan-cell.ts`, M `frontend/src/app/ui/plan-cell.spec.ts`, M `frontend/src/app/api/models.ts` | PlanCell inputs `planTp1`, `planStop`, `trailBest`, `trailBestPct`, `trailExitPct`, `runnerExit`, `runnerExitPct`, `runnerExitReason`; `runnerExitLabel(reason: string \| null): string`; classes `.plan.runner`, `.line.l1`, `.line.l2`, `.trail`; `TradeRow` optional `tp1?: number \| null`, `runner_exit_price?: number \| null`, `runner_exit_reason?: string \| null` |
| V177-3 | Wire Dashboard and Trades templates through the status gate | 1 | opus | C `frontend/src/app/ui/runner-cell.ts`, C `frontend/src/app/ui/runner-cell.spec.ts`, M `frontend/src/app/workspaces/dashboard/dashboard.ts`, M `frontend/src/app/workspaces/trades/trades.ts`, M `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, M `frontend/src/app/workspaces/trades/trades.spec.ts`, M `frontend/src/app/workspaces/dashboard/positions-table.spec.ts` | `RunnerCellInputs`, `NO_RUNNER_CELL`, `runnerCellInputs(row: TradeRow): RunnerCellInputs` (§ Gate contract); `#planCell` binds `@let rc = runnerCellInputs(row);` in both components |
| V177-4 | Three-width browser check (PARTIAL tab, Closed tab, Trades page) | 2 | sonnet | C `$SCRATCH/v177-shots/` (screenshots, not committed); M (only on a layout defect) `frontend/src/app/ui/plan-cell.ts` | a recorded pass at 390/768/1440 (findings in the V177-5 merge message), or a stop with the partner's answer if `.env` lacks the credentials |
| V177-5 | Full suite + frontend run, merge to `main`, ui patch + bot patch, version history | 2 | sonnet | M `VERSION.json`, M `swingbot/admin/version_history.json` | merged `main` (not pushed); bump resolved from `VERSION.json` on disk at merge time; `/close-out` in V177-7 skips its bump steps |
| V177-6 | Gated push (deploy), workflow watch, read-only production check of RKLB's row | 2 | sonnet | C `$SCRATCH/v177_prod_row.py` (not committed) | deployed image; production RKLB row shows `tp1`, `best_pnl_pct`, `stop_pnl_pct`, `runner_exit_price`, `runner_exit_reason` |
| V177-7 | `/panel` pre-close-out and `/close-out` (bump skipped) | 2 | sonnet | M plan files (moved to `implemented/` by `/close-out`), M spec (`## Panel review` addendum if the panel adds findings) | — |
