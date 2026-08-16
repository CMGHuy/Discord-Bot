# v31 — Structural targets: fixing the trade-plan risk/reward inversion

Version: ui 1.5.1 · bot 1.1.4
Bump: bot minor (1.1.4 → 1.2.0)

## The problem

Every trade plan the bot posts shows reward far below risk. The reported case:

```
AXON LONG  entry 617.38  ->  TP 621.85 / SL 604.59
reward = 621.85 - 617.38 =  4.47
risk   = 617.38 - 604.59 = 12.79      →  ~1 : 2.9, inverted
```

This is not an outlier. It is the arithmetic every plan goes through, so the
whole alert stream carries it.

## Root cause

`swingbot/core/planning/plan_engine.py` prices the **stop first**, from real
structure — an ATR multiple, a fib swing, a wave-2 pivot, or a support level —
and then derives the **target from that risk distance** times a small constant:

```python
# plan_engine.py:196-197  (_atr_plan, the default builder)
return entry - risk_distance, entry + risk_distance * rr

# plan_engine.py:665-666  (build_confluence_plan, the live Discord-alert path)
rr = STRATEGY_RR_OVERRIDE.get(primary_strategy, 0.35)
tp1 = entry + risk * rr if is_bull else entry - risk * rr
```

`rr` resolves through `_rr_for()` (`plan_engine.py:164-167`) to
`STRATEGY_RR_OVERRIDE` (`strategy_types.py:217-229`, every value 0.30–0.40) or
`HORIZONS[*]["reward_risk_ratio"]` (`strategy_types.py:45-198`, 0.40 at 2w
reaching only 1.25 at 9m), floored by `RR_FLOOR = 0.30`.

AXON reproduces to the cent: `12.79 × 0.35 = 4.4765 → 621.85`.

The stop can also be **widened** independently by `apply_level_lifecycle()`
(`plan_engine.py:233-311`, `LEVEL_LIFECYCLE_STOPS_ENABLED` defaults on) out to
a *tested* level, bounded only by `max_risk_pct` (3% at 2w to 11% at 9m). The
target is then re-derived from the wider risk at the same small `rr`
(line 289), so a structurally-justified wide stop mechanically produces a
proportionally wide-but-still-tiny target. That is almost certainly AXON's
path.

**This was a deliberate bet, not a defect.** `strategy_types.py:209-216`
argues it: break-even win rate at R:R 0.30 is `1/(1+0.30)` = 76.9%, so an 80%
win rate profits. The bet is being retired, not corrected.

**The wasteful part:** `swingbot/core/market/levels.py` already computes a
genuine structure-based target and already enforces `MIN_RISK_REWARD_RATIO`
(default 1.5) against it in `_check_constraints()` (`levels.py:568-608`). But
`build_confluence_plan()` throws that target away as `tp1`, demoting it to a
possible `tp2`. The one R:R guard in the codebase protects a number no user
ever sees.

## What already exists

Reading the code before designing changed the shape of this work. Four
findings, all of which shrink it:

1. **The band mechanism is already built.** `_fibonacci_plan()`
   (`plan_engine.py:314-339`) and `_sr_plan()` (`342-363`) each carry a correct
   structural-target path in their `else` branch. `_fibonacci_plan` even bounds
   its structural target between `HORIZONS[*]["min_structure_rr"]` and
   `["max_structure_rr"]` — exactly the min/max band this work needs.
   `STRATEGY_RR_OVERRIDE` short-circuits both: the lookup always finds a value,
   so the structural branch is unreachable today. Removing the override table
   revives it.

2. **`select_tp2()` already exists** (`plan_engine.py:388+`) and already does
   what tp2 needs — "first clustered level strictly beyond TP1 in the trade
   direction", with a `MAX_TARGET2_LEG_MULTIPLE` cap on disproportionate legs.
   No new tp2 work; only re-verification once tp1 moves outward.

3. **Only two builders truly lack a structural path** — `_atr_plan()` (the
   default, serving RSI/MACD/VWAP/EMA/MA Ribbon/Break & Retest and more) and
   `_elliott_plan()` (`366-380`). These are where a new selector is genuinely
   required.

4. **The existing band values are themselves sub-1.0** — `min_structure_rr` /
   `max_structure_rr` run 0.35/0.40 at 2w and 0.40/0.50 at 4w, topping out near
   1.25. Reviving the structural path is necessary but not sufficient; the band
   itself has to move.

Two corrections to earlier notes, recorded so they are not re-derived:
`HORIZONS` lives in **`strategy_types.py`, not `config.py`**; and
`STRATEGY_RR_OVERRIDE` has consumers outside the plan engine —
`swingbot/admin/queries.py:42,143` (surfaces `rr_override` to the admin UI),
`swingbot/core/backtesting/backtest.py:32,72`, and a docstring at
`swingbot/core/planning/plan_manager.py:64`.

## Goal

Tie every posted target to real chart structure, with reward landing in a
**1.5×–2.5× risk** band — meaningfully larger than risk, but near enough to be
realistically reachable so the high win rate the current design bought is not
simply thrown away. Where no structural level qualifies, **post nothing** for
that ticker/horizon rather than falling back to a bad ratio.

### Non-goals

- Re-pricing paper trades already open. Forward-only.
- R:R-aware quality scoring in `swingbot/core/planning/quality.py`. Once every
  posted plan is in-band by construction, R:R stops distinguishing them.
- Re-tuning per strategy or per horizon. One global band first; re-introduce
  finer tuning only if measurement demands it.

## Design

### The selector

One shared function in `plan_engine.py`, placed beside the sizing builders.
That placement is deliberate and already documented at `plan_engine.py:200-208`:
`backtest._trade_plan_at` and `build_strategy_plan` are two separate plan
paths, and edge-engine-v4's `DATA_DRIVEN_STOPS_ENABLED` scored 0.0000 — burning
its one pre-registered validation shot — precisely because it reached only one
of them. Anything touching stop or target must be shared by both or it is
unmeasurable by construction.

```python
def select_structural_target(entry, stop_loss, is_bull, candidate_levels,
                             min_rr, max_rr) -> float | None:
    """Nearest qualifying structural level, capped; None when none qualifies."""
```

- `risk = abs(entry - stop_loss)`.
- From `candidate_levels` — prices beyond entry on the trade-direction side —
  take the **nearest** whose distance from entry is `>= risk * min_rr`.
- If that level's distance exceeds `risk * max_rr`, return the capped price
  `entry ± risk * max_rr` (a synthetic price, deliberately not a real level).
- If nothing clears `min_rr`, return `None`.

**Nearest, not farthest.** The closest qualifying level is the one most likely
to actually be reached; reaching for a distant level to maximise reward would
give back the win rate this design is trying to protect.

**`None` means no valid setup.** The builder returns `None`, and the caller
skips posting for that ticker/horizon (`scanning/engine.py:516-542`,
`attach_plan_v2()`) or reports no qualifying setup on the `!info` path. There
is deliberately no fallback to the old formula — a fallback would quietly
reinstate the very ratios this work removes.

### Configuration

`MIN_RISK_REWARD_RATIO` already exists in `swingbot/config.py` (default 1.5);
keep it. Add `MAX_RISK_REWARD_RATIO` (default 2.5) as one `Field` beside it,
following the one-`Field`-per-setting convention so it reaches the admin
Settings page with no extra wiring.

These two fields become the single global band, replacing both the per-horizon
`min_structure_rr`/`max_structure_rr` pairs and the per-strategy override
table.

### Per-path wiring

| Path | Change |
|---|---|
| `build_confluence_plan()` (`654-666`) — live alerts | Selector against the unified multi-method level map |
| `apply_level_lifecycle()` (`233-311`) | Replace the line-289 recompute with the selector against the widened risk; **roll back the widening** if nothing qualifies |
| `_atr_plan()`, `_elliott_plan()` | New selector, from each strategy's own native levels |
| `_fibonacci_plan()`, `_sr_plan()` | Mostly *unblocked* by deleting the override; retarget the existing structural branch at the global band |

**Target sources differ by design.** The confluence path uses the unified level
map, as it already does for stops. The four strategy builders use **each
strategy's own native levels** — a Fibonacci plan targets fib levels, an
Elliott plan targets wave pivots — so each strategy keeps its identity rather
than every strategy converging on one merged level set.

**Roll back, don't skip, on a widening conflict.** If widening the stop to a
tested level leaves no qualifying target, the widening is the refinement and
the band is the guarantee; the guarantee wins.

**The ordered candidate list already exists.** `build_level_map()` returns
`(supports, resistances)` as `Level` lists sorted nearest-first — its docstring
at `levels.py:506` says so, and the sorts at `:508-509` prove it. Nothing about
`build_level_map` or `build_scenarios` needs to change; only *threading* the
map into the builders is new. (An earlier draft of this spec assumed the
opposite and was wrong.)

The one genuine unknown is elsewhere: **`_atr_plan` has no native levels at
all.** It is the fallback for eight of the eleven strategies — EMA Crossover,
VWAP, RSI, MACD, MA Ribbon, Break & Retest, RSI Divergence, Volume Profile —
and its only native scale is volatility. "Each strategy's own native levels"
has no obvious answer there. Returning `None` for all eight would empty
`!ticker`, empty the backtest for those strategies, and therefore empty the
badge registry that `stamp_badge` reads. The plan recommends an **ATR ladder**
(`entry ± k * atr_val`, `k ∈ 1…10`): at `atr_stop_multiple = 2.0` risk is 2
ATR, so the 1.5R floor lands at 3 ATR and the 2.5R cap at 5 ATR — the ladder
brackets the band exactly. This is the one decision to settle before
implementation starts.

### Removal

`STRATEGY_RR_OVERRIDE`, `HORIZONS[*]["reward_risk_ratio"]`, the
`min_structure_rr`/`max_structure_rr` pairs, `_rr_for()`, `RR_FLOOR`, and
`LEVEL_LIFECYCLE_TARGETS_ENABLED` with its pull-in branch
(`plan_engine.py:294-309`) all become dead once the selector lands. They are
deleted in the same change rather than left behind, so no later reader has to
work out whether they still apply. The targets flag is already documented as
measured inert — rejected 248 times out of 248 — and is fully superseded by the
selector's own capping.

Deletion must follow through to the out-of-engine consumers listed above;
`admin/queries.py` in particular returns `rr_override` to the UI.

## Risks

**The win rate falls further than the reward rises.** This is the real risk,
and it is the whole reason the old bet existed. Targets 1.5×–2.5× risk are hit
less often than targets at 0.35× risk. Expectancy must be measured, not
assumed — a new TRAIN-window pre-registration, before any VALIDATION run.

**Alert volume collapses.** If structural levels rarely clear 1.5× risk, the
skip path could silence most of the watchlist. The manual spot-check exists to
catch this early; skip volume should look sane, not all-or-nothing.

**The revived branches are effectively untested code.** `_fibonacci_plan` and
`_sr_plan`'s `else` branches have been unreachable for as long as
`STRATEGY_RR_OVERRIDE` has had full coverage. Switching them on is shipping new
code, not restoring known-good code, and should be reviewed that way.

**The existing acceptance gate is arithmetically incompatible with this
change.** `docs/claude/backtest-methodology.md:11` sets `win_rate >= 80`, and
`:15` lists `STRATEGY_RR_OVERRIDE` + the 0.30 floor under "Frozen constants" —
both deleted here. Break-even win rate at R:R = X is `1/(1+X)`: 76.9% at the old
0.30 floor, which is precisely *why* the gate was 80%. At a 1.5 floor it is 40%,
and at 2.5 it is 28.6%. Carrying the 80% gate over would demand an edge no
strategy in this repo has ever shown and produce a table of failures that says
nothing. Both bullets must be rewritten, with a new floor fixed in the
pre-registration *before* the run — never after seeing results.

**The sizing-parity harness will fail loudly, and that is correct.**
`tests/backtesting/test_sizing_parity.py` checks the live engine against
`tests/fixtures/legacy_trade_plan_at.py`, a deliberately frozen pre-extraction
copy that prices targets off the deleted tables. The fixture must **not** be
taught the new selector — being an independent witness is its whole value. The
harness narrows to stop-only parity instead, with the TP1 divergence documented
as intentional so a later session does not "repair" it.

## Parallelisation

**Sequential throughout the core work.** Tasks touching
`swingbot/core/planning/plan_engine.py` — the selector, all four builders,
`build_confluence_plan`, `apply_level_lifecycle`, and the `_rr_for`/`RR_FLOOR`
removal — are one file. This working tree is shared between concurrent
sessions, so two agents on that file overwrite rather than merge. They also
carry a contract dependency: every wiring task consumes
`select_structural_target()`, which does not exist until the selector task
lands, and the removal tasks must come last or they break callers still in use.

- **Group 1 (parallel):** the `MAX_RISK_REWARD_RATIO` config field
  (`swingbot/config.py`) alongside the level-map candidate-list work
  (`swingbot/core/market/levels.py`) — disjoint files, no shared symbol.
- **Sequential:** the selector before every wiring task (all consume it);
  wiring before removal (removal breaks live callers otherwise); backtest
  re-validation after all code lands (it measures the finished behaviour); the
  version bump last.

## Acceptance

- Unit tests for `select_structural_target()`: nearest-qualifying beats a
  farther level; overshoot caps; nothing qualifying returns `None`; long/short
  symmetry.
- `scripts/dev/testrun.py fast` while iterating, `full` as the pre-commit gate,
  against the `1686 passed, 66 skipped, 0 failed` baseline. Only `failed` — and
  any new `xfailed` — is red.
- Manual spot-check across real tickers including AXON: reward inside
  1.5×–2.5× risk, or the setup skipped, with plausible skip volume.
- A new TRAIN-window pre-registration per
  `docs/claude/backtest-methodology.md` comparing win rate, expectancy and
  realised R:R before and after. Expectancy must hold before VALIDATION.
- `bot` minor bump with `version_history.json` regenerated in the same change.
