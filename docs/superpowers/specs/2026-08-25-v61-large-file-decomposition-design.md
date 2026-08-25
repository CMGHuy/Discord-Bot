# v61 — Large-file decomposition (move-only)

Version: ui 1.8.4 · bot 1.4.3
Bump: none
Edge: none (integrity)

## What this is

Three of this repo's largest source files are split into focused modules by
**relocating whole functions, never editing their bodies**. `Bump:` is `none`
because a move-only refactor produces no observable difference, and
`working-conventions.md` makes observable difference the test for a version
bump, not diff size.

`Edge: none (integrity)`, stated plainly: this adds no discriminator, harvests
no R, and qualifies no new setups. It buys the ability to work in the scan
pipeline without loading 2,347 lines to change 20 — which is a cost constraint
on edge work, not edge itself. It is ranked below any live expectancy plan and
should be scheduled accordingly.

Source: this spec covers three plans. A fourth candidate was measured and
deliberately dropped (see *Rejected*).

## The problem, measured

| File | Lines | Largest single unit |
|---|---|---|
| `core/scanning/engine.py` | 2347 | `_sync_run_scan` — ~800 lines |
| `commands/scanning.py` | 1824 | `_session_scan_tick` — ~160 lines |
| `core/planning/plan_engine.py` | 1419 | `build_strategy_plan` — ~135 lines |
| `core/scanning/embeds.py` | 1109 | `build_embed` — ~245 lines |

Each mixes several unrelated concerns, so any task touching one concern pays
for all of them. `engine.py` alone carries scan run-state flags, dedup,
telemetry, an LRU cache, four distinct data-acquisition paths, the per-ticker
analysis worker and the orchestrator.

## The invariant

> **A moved function's body is byte-identical across the move.** Only the
> module it lives in, and the import block at the top, change.

This is what makes the work reviewable. It converts "did this break
something" from judgement into a mechanical check, and it means a bug found
after the fact cannot have been introduced by a move — it was already there.

Function *decomposition* — breaking `_sync_run_scan` into named phases — is
explicitly **Phase B**, a later plan, deliberately not mixed in. Bugs can only
enter in Phase B, so it must be separable, deferrable and droppable.

## The facade convention

Each split file remains as a thin facade re-exporting the symbols external
callers actually use. Inside the package, modules import each other directly.

This is not a new pattern here: `engine.py` lines 95–110 already re-export ten
symbols from `embeds.py`, with a comment warning to check importers before
deleting one. This spec makes that accidental facade deliberate and bounded.

The payoff is diff size. The dominant import style across ~30 files is
`from swingbot.core.scanning import engine as scan_engine`, so call sites do
not change at all. `bot.py`, `admin/`, `commands/` and `scripts/` are
untouched by the moves.

Each facade declares `__all__`. A name absent from `__all__` is internal and
callers reach it at its real home.

## The rule this refactor lives or dies on

> When a function moves, every `monkeypatch.setattr(<facade>, "<name>", ...)`
> aimed at it moves to the new module **in the same commit**.

A facade re-export is a *different binding* than the callee's module global.
A test that keeps patching the facade patches nothing — and does so silently,
which is worse than failing. The test goes green while exercising the real
code path, including the real network.

Confirmed patch targets in the current suite that must migrate with their
functions:

| Patched name | Moves to |
|---|---|
| `ProcessPoolExecutor` | wherever the *call* lands — tests swap it for `_InlineProcessPool` to avoid spawning real processes. **Highest-risk single item in this spec.** |
| `get_daily_data`, `get_daily_data_batch` | `scanning/fetch.py` |
| `_load_cached_daily`, `_fetch_frames` | `scanning/fetch.py` |
| `is_stop_requested`, `_STOP_FILE`, `_RUNNING_FILE` | `scanning/runstate.py` |
| `TELEMETRY_PATH` | `scanning/telemetry.py` |

Two guard tests ship with plan `_2` to keep this class of mistake loud rather
than silent:

1. Every name in each facade's `__all__` resolves to a real object.
2. No module inside `core/scanning/` imports the facade — this kills import
   cycles before they form, and catches a moved module that "temporarily"
   reaches back through the facade.

## Plan _1 — `commands/scanning.py` → `commands/scanning/`

First, because its seams are the cleanest and it proves the package pattern on
the lower-risk of the two big files. No backtest coupling.

`runstate.py` (pause + heartbeat flags) · `alerts.py` (~250: ordering,
capping, routing, delivery) · `presence.py` (~200: presence text, session
transition, healthcheck) · `recap.py` (retrospective, digest, weekend scan) ·
`commands.py` (~330: the eight `!` handlers) · `loops.py` (~800: the
`@tasks.loop` scheduler layer)

**The specific risk here is registration.** `bot.py:39` does
`from swingbot.commands import scanning  # noqa: F401` purely for its side
effects — every `@tasks.loop` and `@bot.command` registers at import. The
package `__init__.py` must import all six submodules or handlers silently
vanish. A test asserting the expected command names are registered on the bot
object after import is part of this plan, not an afterthought.

`loops.py` at ~800 lines stays large. That is honest and expected: it is a
dense scheduler layer of many medium functions, and shrinking it is Phase B
work.

## Plan _2 — `core/scanning/` (engine.py + embeds.py)

Both together, because `engine.py` already re-exports from `embeds.py`;
splitting them in separate plans cuts the same seam twice. The main event.

**engine.py (2347) →** `scan_run.py` (the `_sync_run_scan` orchestrator) ·
`fetch.py` (crawl, live prices, cold frames, `LRUFrames`, sector ETFs) ·
`analyze.py` (`_scan_one`, the per-ticker worker) · `dedup.py` (`dedup_*`,
`_plans_similar`) · `runstate.py` (stop/running flags) · `telemetry.py`
(`log_scan_telemetry`, `recent_telemetry`, `scan_slowdown`), with `engine.py`
left as a facade.

The facade's `__all__` is the **verified** external surface, enumerated from
`git grep` over `swingbot/`, `bot.py`, `scripts/` and `tests/` rather than
assumed — attribute access (`scan_engine.X`) and direct
(`from ...engine import X`) both counted:

`run_scan` · `ScanProgress` · `ScanItem` · `request_stop` ·
`is_scan_running` · `get_regime` · `get_all_unrealized_pnl` · `map_tickers` ·
`LRUFrames` · `build_decision_context` · `dedup_sector_items` ·
`recent_telemetry` · `scan_slowdown` · `log_scan_telemetry` · `trade_log`,
plus the `embeds` re-exports already present (`CONFIDENCE_COLORS`,
`regenerate_chart_for_trade` and the rest of lines 104–110).

The plan re-runs that enumeration as its first task and treats the result as
authoritative. This list is evidence as of 2026-08-25, not a contract.

### The singleton hazard

`engine.py` holds two module-level instances — `state = StateStore()` and
`trade_log = TradeLog()` (lines 114–115) — and `trade_log` is reached
externally as `scan_engine.trade_log`.

If two split modules each construct their own, the scan silently runs against
two different trade logs and two different state stores. Nothing raises; writes
land in one and reads come from the other. **Both stay in exactly one module,
and every other module imports the instance rather than the class.** A test
asserting `engine.trade_log is <home>.trade_log` ships with this plan.

**embeds.py (1109) →** `snapshots.py` · `requirements.py` · `plan_table.py` ·
`alert_embeds.py` (`build_embed`, `build_simple_alert`) ·
`lifecycle_embeds.py` (closed-trade, near-close and plan-event embeds and
their notifiers), with `embeds.py` left as the facade `engine.py` imports
from.

`plan_numbers_for_display` goes to `plan_table.py`. `architecture.md` names it
THE cutover switch deciding whether alerts show legacy or v2 plan numbers, and
requires every new consumer of plan prices to route through it. It earns a
named home rather than sitting mid-file among formatting helpers.

## Plan _3 — `core/planning/plan_engine.py`

Last, and alone, because of correctness risk. `architecture.md` states the
exit simulator here is shared with `backtest.run_backtest(exit_model="v2",
scale_out=True)` so that "live behavior equals backtested behavior by
construction". A move-bug here is a money bug, and it is the one file where
the test suite alone is not sufficient evidence.

This file splits the best of the three — ~40 medium functions, no
mega-function:

`plan_types.py` (`PlanStatus`, `TradePlanV2`, `plan_to_dict`,
`plan_from_dict`, `effective_stop`, `record_transition`) · `targets.py` (the
five `*_target_candidates`, `select_structural_target`, `select_tp2`,
`_tp2_from_r`) · `builders.py` (`_atr_plan`, `_fibonacci_plan`, `_sr_plan`,
`_elliott_plan`, `build_strategy_plan`, `build_confluence_plan`,
`primary_strategy_for`, `scenario_is_breakout`, `entry_type_for`) ·
`lifecycle.py` (`apply_level_lifecycle`, `trigger_hit`, `fill_price`,
`pending_expired`, `pending_invalidated`) · `params.py` (`exit_params_for`,
the `_resolve_*` helpers, `_apply_quality`, badge stamping) · **`exit_sim.py`**
(`ExitResult`, both exit walks, `chandelier_stop`, `runner_floor`,
`simulate_exit`)

`exit_sim.py` is the real prize. The code that must stay in lockstep with the
backtest stops being buried in a 1419-line file and becomes the single module
to diff when parity is in question.

**Extra verification, this plan only:** a backtest run captured before the
split and re-run after, with the JSON output compared. The suite passing is
necessary but not sufficient for a file whose contract is "identical to the
backtest". Dispatch via the `backtest-runner` subagent.

## Rejected — `performance.py` and `trade_chart.py`

Both were in the original scope and were measured out of it. They are
**single-unit** problems, so move-only barely touches them:

- `charts/trade_chart.py` (1187): `generate_trade_chart` occupies lines
  207–1100 — one ~890-line function. Moving the note-helpers and
  `generate_all_strategy_charts` out leaves ~900 lines. Net ~25%.
- `tracking/performance.py` (1566): `class TradeLog` occupies lines 329–1566 —
  one ~1240-line class. Only ~280 lines of module-level helpers can move.
  Net ~18%.

Splitting ~300 lines off while leaving a 1240-line class behind spends a
plan's worth of review for a fifth of the win. Both files go to Phase B, where
the problem actually is.

## Verification

Per task: body-identity check on every moved function → `python -m py_compile`
over touched files → the narrow run,
`python scripts/dev/testrun.py file tests/test_<area>.py` (~7s).

Per plan, once, as the final task: `python scripts/dev/testrun.py full`,
dispatched to the `test-runner` subagent so ~1150 progress lines never reach
the controller's context. Green is `0 failed` **and** `0 xfailed`; a changed
pass count is not a failure, a new `xfailed` is.

Each plan executes in its own worktree named for the plan's file stem, per
`document-conventions.md`.

## Out of scope

- Any change to behaviour, signature, or call order. If a move reveals a real
  bug, it is recorded and fixed in a **separate** commit, never folded into a
  move.
- Phase B function decomposition (`_sync_run_scan`, `generate_trade_chart`,
  `TradeLog`), which is a later spec.
- The other seven `core/` packages, and `frontend/`.
