# v142 — Partials analytics tab: TP1→TP2 conversion and runner counterfactuals

**Version:** ui 1.21.1 · bot 2.2.2 (at writing)
**Bump:** ui minor (a new Analytics tab the partner uses) · bot patch (plans gain an internal `runner_path` stamp at runner close; nothing a user sees changes in Discord)
**Edge:** none (integrity) — measurement only. It points at an exit change (harvest) but sets no threshold and changes no exit; any change it suggests goes through its own TRAIN/VALIDATION pre-registration.
**Screen:** exempt (descriptive; registers nothing and spends no budget)
**Status:** spec written 2026-10-08.

## Why

Every live plan scales out: `tp1_fraction` (0.5 by default, `planning/params.py:TP1_FRACTION`)
closes at TP1, the plan goes `PARTIAL`, and the runner rides to TP2, a chandelier
trail, the runner floor (`entry + 2/3·(tp1−entry)`), or a progress stall. Nothing
on the live book answers the partner's questions:

1. Of trades that hit TP1, what share go on to TP2?
2. What share of partial trades are *successful* — and does holding the runner pay at all?
3. How long does each stage of a partial trade hold?

Today the only view is one exit-reason share-bar on the Execution tab
(`metrics.exit_reason_split`), and runner counts exist only for backtests
(`run_backtest_range.py`). The purpose of this page is **exit tuning**: show
whether the runner earns its keep and where a different TP2 distance or split
would have landed, so the partner knows which exit pre-registration is worth
spending budget on. The page is never itself a gate — the live book is a small,
non-pre-registered sample.

## Decisions taken in the brainstorm

| Question | Decision |
|---|---|
| Purpose | Tune the exit — counterfactuals, not just descriptive rates |
| Counterfactuals | All four: all-out at TP1, runner MFE/giveback, closer-TP2 ladder, different TP1 fraction |
| Placement | New 7th tab **Partials** in the existing Analytics workspace, inheriting its scope bar and URL state |
| Breakdowns | Strategy, horizon, side, month |
| Headline "success" | Runner beat all-out: blended R > R had 100% closed at TP1 |
| Post-TP1 price path | Stamped onto the plan at runner close; one-off backfill for closed history; the API reads only the DB |

## Data — the `runner_path` stamp

The ladder and MFE need the price path between the TP1 fill and the runner exit.
`runner_high_close` is close-based and only the best value, so it cannot answer
"was 2.5R touched?". A new field on the plan doc (`plans.doc`, JSONB; no promoted
column, so no Alembic revision — but it follows `schema-evolution.md`: readers
never infer a missing stamp, the backfill writes it):

```
runner_path = {
  "mfe_r":            float,   # best R on intraday highs (lows for shorts), TP1 session .. exit session
  "mae_r":            float,   # worst R over the same window
  "ladder":           {"1.5": "YYYY-MM-DD" | null, "2.0": ..., "2.5": ..., "3.0": ..., "4.0": ...},
  "sessions_after_tp1": int,   # trading sessions from TP1 to runner exit
  "source":           "live" | "backfill",
}
```

`ladder` maps each R level (`LADDER_R = (1.5, 2.0, 2.5, 3.0, 4.0)`) to the
session it was first touched, or null. R is measured against the plan's
**initial** risk (`entry − stop_loss` at fill), the same basis as
`metrics.r_multiple`.

**One pure helper computes it:** `compute_runner_path(plan, bars) -> dict | None`
in `swingbot/core/analytics/runner_path.py`. Inputs: the plan and the daily OHLCV
bars covering the TP1 session through the exit session. It returns `None` when
the bars do not cover the window. Rules:

- Direction-aware: longs use highs for MFE / ladder touches and lows for MAE; shorts the mirror.
- **TP1 session:** only the part of the bar after TP1 can count, and a daily bar
  cannot order intrabar events — so on the TP1 session a level counts as touched
  only if it lies beyond TP1 **and** the bar's extreme reached it; on the exit
  session, if the exit was a stop/floor/trail, the conservative rule assumes the
  exit came first and that session's extreme is **not** counted.
- A gap through a level counts as touched.
- MFE is floored at the TP1 R (the runner was at least there).

**Live stamping:** `plan_manager` calls the helper wherever a runner leg closes —
`tp1_runner_tp2`, `tp1_runner_trail`, `tp1_runner_be`, `tp1_runner_progress_stall`,
and a time or manual exit of a plan already `PARTIAL`. Bars come from the
already-loaded daily data on that scan; the stamp never triggers a network fetch
and never blocks the close. Missing bars → `runner_path: null` and one log line.

**Backfill:** `scripts/data/backfill_runner_path.py`, dry-run by default,
`--apply` to write. It walks closed plans whose `status_history` contains
`PARTIAL`, skips any already stamped (idempotent), reads daily bars from the
local OHLCV cache only (**no network** — the known 18.5s cold-fetch blocker),
stamps `source: "backfill"`, and prints `stamped / skipped / unavailable`
counts. It is run once on production via `scripts/ops/ssh-hetzner.sh`; which
cache production actually holds for the full history is verified first, in the
plan, not assumed.

## Metrics — `swingbot/core/analytics/partials.py`

Pure functions over plan records; no I/O. All R via `metrics.r_multiple`.

**Population.** *Filled* = plans that reached `ACTIVE` (excludes PENDING and
CANCELLED-before-fill). *Partial* = filled plans whose `status_history` holds a
`PARTIAL` entry. The scope bar's date range filters on **fill date**.

**Runner outcome buckets** (each partial trade in exactly one):
`tp2`, `trail`, `floor` (`tp1_runner_be`), `stall`, `time`, `manual`, `no_tp2`
(plan has `tp2 is None`, whatever its exit), `open` (runner still live).

**KPIs**

| KPI | Definition |
|---|---|
| TP1 rate | partial ÷ filled-and-closed (open pre-TP1 trades excluded from the denominator) |
| TP1→TP2 rate | `tp2` ÷ closed runners, excluding `no_tp2` and `open` |
| **Runner beat all-out** (hero) | share of closed runners with blended R > all-out R |
| Mean runner ΔR | mean(blended R − all-out R) over closed runners |
| Hold times | trading sessions entry→TP1, TP1→runner exit, entry→final exit — median and p25/p75 |

**Counterfactuals** (closed runners only)

| What-if | Per trade |
|---|---|
| All-out at TP1 | R of the TP1 leg × 1.0 |
| Giveback | `runner_path.mfe_r` − runner leg R |
| TP2 ladder at L | `tp1_fraction·R_tp1 + (1−tp1_fraction)·(L if touched else actual runner R)` — pooled into touch rate and counterfactual ExpR per L, with the actual setup marked |
| TP1 split f ∈ {0.33, 0.5, 0.67} | `f·R_tp1 + (1−f)·R_runner` from the trade's own two legs |

Trades with `runner_path: null` are excluded from giveback and ladder only, and
counted in a visible `path_unavailable` figure — never silently dropped.

**Breakdowns:** the KPI set plus N, grouped by strategy, horizon, side, and
month of TP1 hit. A row with N < 10 is flagged `thin: true` (values still shown).

## API

`GET /api/v1/analytics/partials` in `swingbot/admin/api_v1/analytics.py`,
taking the same scope parameters as its siblings. Response:

```
{ "kpis":        {...},
  "funnel":      [{"stage": "filled|tp1|runner_closed|tp2", "n": int}],
  "outcomes":    [{"bucket", "n", "share", "avg_runner_r"}],
  "counterfactuals": {
      "actual_exp_r", "all_out_exp_r",
      "giveback":   [float],                       # per trade, for the histogram
      "ladder":     [{"level_r", "touch_rate", "cf_exp_r", "n"}],
      "split":      [{"fraction", "exp_r", "n"}],
      "path_unavailable": int },
  "holds":       {"entry_tp1"|"tp1_exit"|"entry_exit": {"p25","median","p75","points":[int]}},
  "breakdowns":  {"strategy"|"horizon"|"side"|"month": [{"key", "n", "thin", ...kpis}]} }
```

## Frontend — `tabs/partials.ts`

Registered as the seventh entry in the `tabs` array (`analytics.ts`), routed by
the existing `?tab=` query state; data through a new `partials` slice in
`stores/analytics.store.ts`, types in `api/models.ts`. Built only from the
existing SVG components in `frontend/src/app/ui/`; no new chart library.

Top to bottom:

1. **KPI row** — TP1 rate · TP1→TP2 rate · **Runner beat all-out %** (hero) · mean runner ΔR · median TP1→exit sessions; each with N.
2. **Funnel** (bar-list) — filled → TP1 → closed runner → TP2.
3. **Runner outcome mix** (share-bar) — buckets with average runner R.
4. **Does the runner pay?** (waterfall) — all-out ExpR → runner contribution → actual ExpR.
5. **TP2 ladder** (line chart) — touch rate and counterfactual ExpR per R level; actual setup marked.
6. **Split what-if** (bar-list) — ExpR at 33/50/67% taken at TP1.
7. **Giveback** (histogram) — MFE R − banked runner R.
8. **Hold times** (strip plot) — three stages, median + IQR.
9. **Breakdown table** — dimension switcher (strategy/horizon/side/month), KPI columns, thin rows dimmed; month view adds a trend line.

Footer: population, `path_unavailable` count, "live book only — not a gate".
Empty state when the scope holds zero partial trades.

## Edge cases

| Case | Handling |
|---|---|
| TP1 and runner exit on the same session | `sessions_after_tp1 = 0`; conservative intrabar rule above |
| Gap through a ladder level | touched |
| `tp2 is None` | `no_tp2` bucket, out of the TP1→TP2 denominator, still in the ladder |
| `tp1_fraction ≠ 0.5` | every counterfactual uses the trade's own fraction |
| Runner still open | funnel and `open` bucket only; out of counterfactuals and hold times for the exit stages |
| Manual close after TP1 | `manual` bucket; counts as a closed runner |
| Missing bars | `runner_path: null`, counted in `path_unavailable` |

## Testing

- `compute_runner_path`: long, short, gap through a level, same-session TP1+exit, exit-session conservatism, missing bars → `None`.
- `partials.py`: each KPI and counterfactual against hand-built plan fixtures; pooled actual ExpR ties out to `metrics.r_multiple`.
- Endpoint: scope filtering, empty scope, response shape.
- Live stamp: each runner-close path writes `runner_path` with `source: "live"`; missing bars still closes the plan.
- Backfill: dry run writes nothing; `--apply` twice stamps once.
- Frontend: tab renders from a fixture; empty state; thin rows dimmed.
- Every new or changed function under cyclomatic complexity 15.

## Parallelisation

- **Sequential first:** `runner_path.py` helper (the stamp's contract) before live stamping, the backfill and `partials.py` — all three consume its output shape.
- **Group A (parallel, after the helper):** live stamping in `plan_manager.py`; backfill script; `partials.py` metrics — disjoint files, each consumes only the helper.
- **Sequential:** API endpoint after `partials.py` (it serialises that module's output). Frontend models + store after the endpoint (they mirror its response). The tab component after the store.
- **Last:** full Python suite and full `npm test`, once.
- **Production:** backfill `--apply` on the VM only after the branch is merged and deployed, so the live stamp and the backfill write the same shape.

## Out of scope

- Changing any exit parameter (TP2 distance, split, floor, trail). That is a separate pre-registration the page may motivate.
- Backtest-side partial analytics — `run_backtest_range.py` already prints runner counts.
- A per-trade drill-down table (not chosen in the brainstorm).
