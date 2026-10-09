# v147 — Gate counterfactual: what the blocked candidates would have done

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** bot patch (new internal store + nightly resolver; nothing a user sees)
**Edge:** none (integrity) — measurement only; admission evidence for a later expectancy screen that loosens or tightens a gate
**Screen:** exempt (descriptive; registers nothing and spends no budget)
**Panel:** quant-researcher, quant-engineer, risk-manager
**Status:** spec written 2026-10-09; no plan yet.

## Why

Every gate in the scan pipeline throws candidates away, and none of them
records what the thrown-away candidate would have done. Today a block is a
counter and, at most, a debug line:

- **RS gate.** Three call sites, all count-only:
  `swingbot/core/scanning/strategy_pass.py:237-239` (strategy path, bearish
  only, `result.rs_blocked += 1`), `swingbot/core/scanning/scan_run.py:664-673`
  (confluence path, `rs_blocked += 1` plus a funnel tally) and
  `swingbot/core/scanning/qualify.py:125-126` (short lane, `Rejected(item, "rs", "rs_blocked")`).
- **Plan rejected.** `analyze.py:123-126` (`_reject_plan`) stamps
  `plan_v2_rejected` with `no_qualifying_target` (`analyze.py:379`) or
  `risk_cap` (`analyze.py:388`); the item is then dropped at
  `scan_run.py:694-698` or `qualify.py:127-129` (`_revoke` logs it,
  `qualify.py:101-106`).
- **Compression / earnings rejects.** `strategy_pass.py:243-246` counts a
  `decide_compression_entry` reject (`_count_compression_reject`,
  `strategy_pass.py:155-162`; reasons starting `earnings_` feed
  `earnings_excluded_by_mode`). Only the *masked* cells' raw signals are
  written to `data/compression_shadow.jsonl`
  (`scan_run.py:157-166` → `shadow_log.append_compression`,
  `swingbot/core/backtesting/shadow_log.py:63-71`), with no outcome.

`short_funnel.ShortFunnel` (`swingbot/core/scanning/short_funnel.py:33-60`)
counts stage × reason tuples; it holds no candidate and no outcome. No table
or file anywhere pairs a blocked candidate with the trade it would have been.

So the question "is this gate paying for itself?" has only ever been answered
once per gate, on the pre-registration replay that admitted it, and never on
the live book. This spec builds the instrument: a shared counterfactual
simulator, a TRAIN recorder, a live store with a nightly resolver, and one
report with a pre-registered three-way verdict per gate. It changes no gate.

## Scope

**In:** the RS gate (live only, see below), plan rejections (with reason)
and compression/earnings rejects, on both the strategy and confluence paths
and the short lane. Task 1 enumerates every block point from code (the list
above is the starting point, not the contract) and the report covers each
one it finds that falls under these three gates.

**Out:** changing any gate, threshold or default; any VALIDATION-window
replay; any TRAIN evaluation of the RS gate; the pullback dry-up gate
(`strategy_pass.py:240-242`, `analyze.py:615-624`) — inactive since v122
closed NO-LIFT (`PULLBACK_DRYUP_SCOPE` defaults to `off`,
`swingbot/config.py:227-229`, `.env.example:251`, which makes
`filter_pullback_dryup` a no-op, `edge/gates.py:103-108`), so it blocks
nothing to measure; the confluence/confidence/geometry requirement rejects
(`short_funnel._REQUIREMENT_STAGE`), dedup and cooldown skips (those are
"already have this trade", not a quality gate); any UI (v150 renders the
JSON this spec emits).

## Gates covered and their margin

`margin` is the signed distance of the deciding value past the gate's line,
so the report can split blocked rows into near-misses and clear rejects.
It is `null` where the gate decides on a category, not a number.

| `gate` | `reason` values | `margin` |
|---|---|---|
| `rs` | `rs_blocked` | `rs_combined − RS_LAGGARD_PERCENTILE` (`rs_gate.rs_verdict`, `swingbot/core/edge/rs_gate.py:28`) |
| `plan_rejected` | `no_qualifying_target`, `risk_cap` | `risk_cap`: planned loss % − `HARD_MAX_PLANNED_LOSS_PCT` (`swingbot/core/risk_limits.py:9`); `no_qualifying_target`: `null` |
| `compression` | the `decide_compression_entry` reason string, `earnings_*` included | `null` |

**`no_qualifying_target` has no plan to simulate.** `build_confluence_plan`
returned `None` — no level in the RR band exists (`analyze.py:370-379`).
Such rows are stored and counted with `cf_status = no-plan`; they never
enter an ExpR.

**The RS gate is live-only.** Its only pre-registration, v34 (ledger id
`v34-rs-gate-bearish`; closed-table row in `backtest-methodology.md`), is
closed and stays closed. This spec evaluates the RS rule on no historical
window, re-runs nothing from v34 and spends no budget: RS rows come only
from the live `gate_rejections` store, and the RS verdict is printed only
once that store holds N ≥ 30 filled RS rows. There is no TRAIN RS row in the
report.

## The counterfactual simulator

One function, `simulate_blocked(candidate, bars)`, in a new module
`swingbot/core/backtesting/gate_counterfactual.py`, used unchanged by the
TRAIN recorder and the live resolver.

- **Plan.** If the candidate already carries a plan (`risk_cap`, compression
  shadow plans), that plan is used as stored. Otherwise the plan is built by
  the live constructor on the frame truncated at the signal bar:
  `build_strategy_plan` (`swingbot/core/planning/builders.py:398`) for a
  strategy candidate, `build_confluence_plan` (`builders.py:556`) for a
  confluence scenario. A `None` plan is `no-plan`.
- **Walk.** `exit_sim.simulate_exit(df, signal_index, plan, scale_out=True)`
  (`swingbot/core/planning/exit_sim.py:625`) — the v2 exit model with
  scale-out that the live book and every current backtest use, with the
  horizon's `max_holding_days` (`strategy_types.HORIZONS`).
- **Status.** `ExitResult.outcome == "not_triggered"` (pending expired or
  invalidated before the trigger, `exit_sim.py:693-696`) maps to
  `cf_status = no-fill`. That result carries `r_total = 0.0`
  (`exit_sim.py:76-86`); the counterfactual **must not** read it as a 0R
  trade. `no-fill` rows count toward fill rate and are excluded from ExpR and
  win rate. Anything else is `filled`, `cf_r = r_total`, win = TP1 touched
  (the badge definition in `backtest-methodology.md`).

### No lookahead

The entry decision — plan levels, trigger, stop, targets — reads only bars
up to and including the signal bar; the outcome reads only bars strictly
after it (`simulate_exit`'s stop-entry scan starts at `signal_index + 1`,
`exit_sim.py:682`). Two tests pin it: building the plan from
`full.iloc[:signal+1]` and from the full frame yields the same plan
(the architecture NO-LOOKAHEAD truncation test), and appending bars after the
horizon's expiry changes no `cf_r`.

## TRAIN side

`scripts/backtest/run_backtest_range.py` gains `--record-blocked PATH`
(sibling of the existing `--trades-jsonl`, `run_backtest_range.py:375`),
writing one JSONL row per blocked candidate: `ticker`, `strategy`,
`horizon`, `direction`, `signal_date`, `gate`, `reason`, `margin`,
`cf_status`, `cf_r`, `win`. Windows: TRAIN only (2020-01-01..2023-12-31);
the flag refuses `--validation` and any `--to` past 2023-12-31.

TRAIN mirrors the **live configuration at writing**, because the replay
does not apply every live gate:

| Gate | Replay applies it? | TRAIN recording |
|---|---|---|
| compression | yes, `arms/strategy_engine.py:170` | real block, simulated from the signal bar |
| `no_qualifying_target` | yes, `backtest_scenarios.py:160` / `backtest.py:454` | real block, `no-plan` |
| `risk_cap` | **no** (no `HARD_MAX_PLANNED_LOSS_PCT` check in either replay) | shadow: the cap's rule evaluated on each replayed plan; a would-block trade moves from *taken* to *blocked*, its outcome already simulated |
| RS | no | **not recorded** — live-only (above) |

**The `risk_cap` shadow touches no closed pre-registration.** None of the 61
ids in `docs/superpowers/results/preregistration-ledger.jsonl` tests the
`HARD_MAX_PLANNED_LOSS_PCT` plan rejection as a knob. v101 and v104 mention
the 2% cap only as fixed context for other mechanisms, and v129's disaster
stop "lands on the 2% cap" without testing it. The cap is also the partner's
dollar-risk rule rather than a tuned threshold, so a `GATE COSTS` reading on
it is reported, never a licence to loosen the cap without the partner. The
compression rows record blocks the replay already makes. They re-score
nothing in `v119-compression-short`.

Runs: one `--exit-model v2 --scale-out --record-blocked` TRAIN run per
strategy plus one `--scenarios` run for the confluence book, each dispatched
to `backtest-runner` with flushed progress (and a percent file past 15
minutes). Rows land in `logs/v147-blocked-<strategy>.jsonl` (gitignored).

## Live side

### Store

A new append-only table `gate_rejections`, one Alembic revision
`v147_001` (`down_revision` = the head at implementation time; at writing
`v116_002`, `swingbot/core/db/migrations/versions/v116_002_dropped_doc_fields.py:10`),
following `docs/claude/schema-evolution.md`:

| Column | Promoted because |
|---|---|
| `id BIGINT PK` | primary key |
| `ticker`, `gate`, `strategy`, `horizon`, `signal_date` — `UNIQUE` together | the dedupe key; the insert is `ON CONFLICT DO NOTHING` |
| `cf_status TEXT NOT NULL` (`pending`/`filled`/`no-fill`/`no-plan`/`no-data`), indexed | the resolver's `WHERE cf_status = 'pending'` |
| `created_at`, `resolved_at` | resolver due-date and report window filters |
| `doc JSONB`, `updated_at` | standard; `doc` holds `reason`, `margin`, `direction`, `source` (strategy / confluence / short lane), the plan snapshot (`plan_to_dict`) or the scenario inputs needed to build it, `entry_context`, `cf_r`, `win`, `exit_index` |

Each promoted column gets its line in `schema.PROMOTION_REASONS`
(`swingbot/core/db/schema.py:215`), the table is `register(...)`ed
(`schema.py:28`), and a repository joins `swingbot/core/db/repositories/`.
`strategy` for a confluence candidate is its `primary_strategy_for` label
(`builders.py:520`). Rows are never updated except by the resolver filling
the outcome fields once; never deleted.

### Write path

Each block point calls one helper, `record_rejection(...)`, that builds the
snapshot and inserts it. It is **fail-open for the scan**: a write failure
logs a warning and the scan carries on exactly as today (the gate's own
decision never depends on the write). The helper is called from the scan
runner's serial merge, never from `map_tickers()` workers
(`short_funnel.py` thread rule, lines 8-10).

### Nightly resolver

A `tasks.loop(minutes=1)` poll in `swingbot/commands/scanning/loops.py`,
same shape as `weekly_earnings_refresh` (`loops.py:726-727`), firing once per
weekday after the session close. It selects `pending` rows whose horizon has
expired — signal date + the plan's pending window + `max_holding_days`
trading bars — loads daily bars through `get_daily_data_batch`
(`swingbot/core/marketdata/data.py:85`), runs `simulate_blocked`, and writes
`cf_status`, `cf_r`, `win`, `resolved_at`. A ticker with too few bars after
the signal stays `pending` up to five more sessions, then `no-data`.
Batches are capped so one night never blocks the scan loop.

## The report

The logic lives in an importable module,
`swingbot/core/analytics/gate_counterfactual_report.py`. `build_report()`
reads the TRAIN JSONL files and the live table, persists its latest result to
`data/reports/gate-counterfactual.json` (`data/` is mounted into both the
bot and admin containers), and returns it; `load_report()` returns that
file's content as a JSON-serialisable dict (or `None` before the first run),
so v150 serves it without importing anything else here.
`scripts/reports/gate_counterfactual_report.py` stays a thin wrapper: it
calls `build_report()` and prints the table. One row per gate × reason ×
population, **live and TRAIN side by side, never pooled**:

- blocked N, `no-plan` N, fill rate (`filled / (filled + no-fill)`),
- blocked ExpR and win rate over `filled` rows,
- taken ExpR and win rate: the trades that reached the same gate and passed
  it, in the same scope (direction, source, window),
- margin split: near-miss (|margin| in the gate's first quintile) vs rest,
  reported only.

On the live side, taken trades are re-walked through the same
`simulate_exit` call from their stored plan, so both arms use one
instrument; the realised live ExpR of the taken trades is printed beside it
as context, never compared.

### Pre-registered verdict

Fixed here, before any row exists:

- Blocked-ExpR 95% interval from a ticker-cluster bootstrap
  (`acceptance.cluster_bootstrap`, `swingbot/core/backtesting/acceptance.py:239`,
  `BOOTSTRAP_RESAMPLES = 10_000`, seed 42) over the blocked `filled` rows.
- **GATE EARNS** — the interval lies entirely below taken ExpR.
- **GATE COSTS** — the interval lies entirely above taken ExpR.
- **INCONCLUSIVE** — otherwise.
- **WAITING** — fewer than 30 `filled` blocked rows for that gate in that
  population. The live verdict is never printed below N = 30.

Per population and per gate; the two populations are never combined into
one verdict. The RS gate has a live verdict only (no TRAIN population).

**What a verdict buys.** Nothing changes automatically. `GATE COSTS` licenses
exactly one thing: a Stage −2 idea screen (`backtest-methodology.md`) for
loosening that gate, under a new idea name. For `risk_cap` that screen also
needs the partner, whose dollar-risk rule the cap is. `GATE EARNS` is
evidence for a later tightening screen. Neither reopens a closed row: the RS
gate (v34) and earnings blackout (v82) rows in the closed table stay closed, and a follow-on is a new pre-registration with its own shot. This
report itself spends no budget and appends no ledger row.

## Production progress cron

The live verdict needs weeks. Per the repo rule that far-off work runs on the
Hetzner VM, `scripts/ops/gate_counterfactual_progress.py` (read-only: counts
per gate × `cf_status`, filled N against 30) plus an idempotent
`scripts/ops/install_gate_counterfactual_cron.sh` (pattern:
`install_intraday_coverage_cron.sh`) run weekly on the VM and append to
`logs/gate-counterfactual.log` there. When every covered gate has left
`WAITING`, the next Claude session runs the report and records it; the cron
removes nothing and decides nothing.

## Testing

- `simulate_blocked`: a synthetic frame per outcome (win, loss, scratch,
  timeout, `no-fill` via expiry and via invalidation, `no-plan`); a
  `no-fill` never reaches an ExpR.
- No lookahead: the truncation test and the appended-bars test above.
- Each block point writes exactly one row with the right `gate`/`reason`/
  `margin`, and a failing write leaves the scan result identical.
- Dedupe: a second insert for the same key is a no-op; the same ticker, gate, strategy and day on two horizons is two rows.
- Migration: up/down via `tests/db/test_migrations.py`; the table passes
  `tests/db/test_schema_contract.py` and `test_unknown_field_round_trip.py`.
- Resolver: only expired `pending` rows are touched; `no-data` after the
  grace window.
- `--record-blocked` refuses VALIDATION dates, writes no `rs` row, and its
  `risk_cap` shadow agrees with `analyze.py:381`'s check on fixed plans.
- Verdict rule on hand-built populations: one each for EARNS, COSTS,
  INCONCLUSIVE and WAITING (N = 29).
- `build_report()` writes the file `load_report()` reads back unchanged, and
  `json.dumps(load_report())` succeeds; `load_report()` is `None` with no file.

## What follows

- **v146 (sibling, attribution).** Attribution explains the trades that were
  taken; this spec measures the ones that were not. They share no code
  beyond `simulate_exit`, and either can land first.
- **v150 (Reports workspace)** renders `data/reports/gate-counterfactual.json`
  as a page through `load_report()`; this spec fixes the JSON shape and the
  loader, v150 owns everything visual.
- A `GATE COSTS` or `GATE EARNS` verdict feeds a Stage −2 screen spec for
  that gate, with its own `Screen:` line; nothing else follows from it.

## Parallelisation

- **Sequential first:** Task 1 (enumerate block points) before everything —
  every later task's hook list comes from it. Then `simulate_blocked` and its
  tests, which every other part consumes.
- **Group A (parallel, after the simulator):** the TRAIN recorder
  (`run_backtest_range.py`, `arms/strategy_engine.py`,
  `backtest_scenarios.py`, the `risk_cap` shadow) and the store (Alembic
  revision, `schema.py`, new repository). Disjoint files, no shared symbol.
- **Sequential after the store:** the live write hooks (`strategy_pass.py`,
  `scan_run.py`, `qualify.py`, `analyze.py` — one task, these files share
  the merge path), then the resolver in `loops.py`.
- **Group B (parallel, after both sides exist):** the report module with its
  thin script wrapper, and the ops cron scripts — disjoint files; the cron
  reads only the table.
- The TRAIN runs (`backtest-runner`, one per strategy plus confluence) need
  the recorder only and can run while the live hooks are built. The full
  suite runs once, as the plan's final task.
