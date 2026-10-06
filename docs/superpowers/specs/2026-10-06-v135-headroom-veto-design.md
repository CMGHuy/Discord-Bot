# v135 — Headroom veto: skip plans whose path to TP1 is blocked

**Version:** ui 1.21.1 · bot 2.0.2 (at writing)
**Bump:** none (gate ships inert, defaults off; amended at close-out if a scope passes VALIDATION)
**Edge:** expectancy
**Status:** spec written 2026-10-06; no plan yet.

## Why

The partner shared eight "Daiken/BigWhale" price-action pages on 2026-10-06.
Most of what they teach is already built, queued or measured here (structure
v121/v130, reaction v88/v90/v127, pullback volume v122, location v125,
liquidity v133). One page is not: "90% trader bỏ qua bước này" — a clean
lower-timeframe setup taken directly under a higher-timeframe resistance,
with "còn bao nhiêu room?" and "RR còn đủ tốt không?" as the two checks that
would have skipped it.

The engine does the opposite of that check today.
`planning/targets.py:select_structural_target` takes the **nearest level
that pays at least `MIN_RISK_REWARD_RATIO`** and ignores every level nearer
than that floor. A confirmed resistance at 0.8R is stepped over and TP1 is
placed at the next level beyond it. `levels.build_scenarios` applies the
same floor on the confluence path. Nothing between entry and TP1 is ever
looked at.

**What was already tried, and why this is not a re-run.** v17 P1
("level-lifecycle targets") pulled TP1 **back inside** a gatekeeper level and
was measured inert (rejected 248/248); its flag, branch and lookup helper
were deleted in v31. That changed the target's geometry. v135 leaves every
target and stop where it is and removes the **trade**, which makes it a
subset feature with a mechanism clause (v72 clause 6) the v17 arm never had.
v84's `min_level_touches` gated on the significance of the level being
*traded*; v135 gates on a level standing in the *path*. Neither closed row
is reopened.

## Hypothesis

**Pre-registered claim:** removing plans that have a multi-source opposing
level nearer than `h` × their own risk raises win rate without costing
expectancy, under the standard v72 funnel.

This is a binary filter, not a score weight (blended-confidence weights
regressed in v32 and v33).

## The predicate

One pure function in `swingbot/core/edge/gates.py`:

`headroom_rejects(entry, stop, direction, levels, min_r) -> bool`

- `risk = abs(entry - stop)`; `risk <= 0` or `min_r <= 0` returns `False`.
- A **blocker** is a `levels.Level` that is
  1. strictly beyond `entry` on the target side (above for bullish, below
     for bearish), **and**
  2. nearer than `min_r × risk`: `abs(level.price - entry) < min_r × risk`
     (strict; a level exactly at the bound does not block), **and**
  3. confirmed by at least `HEADROOM_MIN_FAMILIES = 2` distinct detector
     families: `len({levels.strategy_family(s) for s in level.sources}) >= 2`.
- Returns `True` iff at least one blocker exists.
- `levels` empty or `None` returns `False`. The gate removes only what it
  can positively identify; the share of plans judged with no level map is
  reported per arm.

`HEADROOM_MIN_FAMILIES` is a **frozen module constant, not a knob and not a
grid axis**. Two families is the smallest value that excludes a lone
Bollinger band or floor pivot, and it is the bot's own definition of a
confirmed level (`levels.py`: "the more independent methods agree a price
matters, the stronger that level is"). Changing it is a new pre-registration.

Because every grid value of `h` is at most 1.0 and the target floor is
`MIN_RISK_REWARD_RATIO = 1.5`, the plan's own TP1 can never be its blocker.

**Which entry and stop.** The planned prices at the decision point, never a
fill:

| Scope | `entry`, `stop` | `levels` |
|---|---|---|
| `confluence` | `Scenario.entry`, `Scenario.stop_loss` | the same supports/resistances that were handed to `levels.build_scenarios` for that bar |
| `strategy` | the built plan's `entry`, `stop` | `levels.build_level_map` on the completed frame the plan was built from |

## Scope — two independent components

| Component | Population |
|---|---|
| `confluence` | every confluence-scan scenario, both directions |
| `strategy` | strategy-sourced plans for the frozen list: EMA Crossover, VWAP, Fibonacci, Support/Resistance, RSI, Elliott Wave, MA Ribbon, Break & Retest, RSI Divergence |

Excluded by design: MACD and Volume Profile (the only `VALIDATED` badges —
not diluted by an unrelated filter) and every name in
`strategy_types.SHORT_STRATEGIES` (own plan shapes, own budgets). The list is
frozen here as `HEADROOM_STRATEGIES`; adding a name is a new
pre-registration.

The two components are **separate pre-registrations with separate budgets**.
Each is measured, selected and validated alone; neither can be rescued by
pooling with the other. Per-direction results and top-2 horizon share are
disclosed, and an arm whose effect is more than 80% one direction says so.

## Knobs

- `HEADROOM_SCOPE` — `off | strategy | confluence`, default `off`,
  `search_class = searchable`.
- `HEADROOM_MIN_R` — float, default `0.0` meaning off,
  `search_class = searchable`.

Both live in `swingbot/config.py`'s schema and hot-reload like every other
field. The gate is inert unless `HEADROOM_SCOPE != off` **and**
`HEADROOM_MIN_R > 0`. `backtesting/arms/reachability.py` classifies both
before compute.

## Frozen grid and selection rule

`h ∈ {0.5, 0.75, 1.0}` per component. Frozen **now**, before v125's
descriptive report (`room_atr`) or v133's exists; no bucket table from
either may move it.

The funnel in `backtest-methodology.md`, verbatim:

1. **Stage −1 reachability** (pilot) — refuse on zero changed outcomes.
2. **Stage 0 MDE** (fold-train, paired bootstrap; arms share keys) — refuse
   the shot if the TRAIN effect is below the MDE.
3. **Stage 1 selection** (fold-train only) — eligible cells pass clauses 2–4
   and 6; `plateau_report()` is mandatory and the chosen `h` needs an
   eligible grid neighbour. Among eligible plateau cells pick the largest
   ΔWR; tie → smaller `h` (smaller cut).
4. **Stage 2 walk-forward** — `gate_win_rate`: ≥ 2 of 3 folds improving, no
   fold worse than −1.0pp, per-fold N ≥ 30.
5. **Stage 3 VALIDATION** 2024-01-01..2025-12-31 — one shot per component,
   all six clauses, missing permutation p = FAIL.

**Clause 6 reading (frozen, same as v122).** A rejected entry frees the
one-position slot (strategy) or the 5-bar cooldown (confluence), so the
component arm is not a strict subset of baseline. The mechanism clause is
scored on the **baseline** arm: in-scope trades the predicate flags at `h`
("removed") vs in-scope trades it does not flag ("retained"); pass iff
removed WR < retained WR **and** removed ExpR ≤ 0. Replacement trades count
fully in clauses 1–5 and their count is disclosed.

**Clause 5 instrument.** `scripts/backtest/permutation_test.py` in the
arm-pair mode v122 added (stamped pair, ΔWR, n = 200, fixed seed). No new
instrument and no change to that script's null.

Arms come from `scripts/backtest/measure_arms.py` and are judged by
`scripts/backtest/validate_component.py`. No bespoke measurement script. The
pre-registration record is committed under `docs/superpowers/results/`
before any outcome is read. `backtest-gate` is invoked before every run.

**Order.** `confluence` first (the level map is already in hand, and it is
the larger population), then `strategy`. Serial, never concurrent.

## Live / replay parity

One predicate, four call sites, the same ones v122's gate uses:

| | Live | Replay |
|---|---|---|
| `confluence` | `scanning/analyze.py`, beside `_apply_pullback_dryup` | `backtesting/backtest_scenarios.py`, beside `_dryup_kept` |
| `strategy` | `scanning/strategy_pass.py` | `backtesting/arms/strategy_engine.py:_gated_plan`, after `build_strategy_plan` returns |

- Each call site checks `HEADROOM_SCOPE` and, for `strategy`, membership of
  `HEADROOM_STRATEGIES`.
- **Confluence map.** Both paths pass the gate the very lists the scenario
  was built from (`analyze.py`'s scan map live, `levels_asof` re-split in
  replay). The gate adds no map build and no new live/replay difference on
  this scope.
- **Strategy map.** Neither path has a unified map at this point today:
  `strategy_pass.py` holds none, and `strategy_engine` builds one only when
  a plan wants TP2, cached per 5-bar bucket. With the gate active for
  `strategy`, live builds the map on its `completed_frame` (the frame v122's
  `_dryup_blocked` already uses) and replay builds the same bucketed as-of
  map for every in-scope signal. The replay bucket can lag live by up to
  four bars; that is the engine's existing convention and is disclosed in
  the results, not tuned. With the gate off neither path builds anything
  extra, so baseline arms stay byte-identical.
- Rejections are logged in the scan funnel with reason `headroom`.

Out of scope: moving any target or stop, any score weight, alert or chart
text, a "caution" badge instead of a veto, and any use of lifecycle state or
touch counts to qualify a blocker.

## Ship rule

A component flips default-on only after its own VALIDATION passes all six
clauses; shipping sets the two defaults in the schema (if both pass, the
scope type becomes a set — decided then). A failure at any stage closes that
component in the closed-pre-registrations table with its numbers, and the
code stays merged and inert. Reopening needs a mechanism other than
"an opposing level with ≥ 2 source families nearer than
`h ∈ {0.5, 0.75, 1.0}` × risk".

## Testing

- Predicate: no levels → `False`; a single-family level inside the bound →
  `False`; a two-family level inside → `True`; exactly at `min_r × risk` →
  `False`; behind entry → `False`; bearish mirror; `min_r = 0` and
  `risk = 0` → `False`; two labels of one family (`EMA20`, `EMA50`) count
  as one.
- Scope: `strategy` never touches confluence scenarios and vice versa; MACD,
  Volume Profile and a `SHORT_STRATEGIES` name are never gated.
- Parity: one fixture through the live and the replay call site of each
  scope gives the same accept/reject.
- Defaults-off witness: with both knobs at default, a replay fixture's
  trades are byte-identical to before the change, and the strategy engine
  builds no extra level map.
- No-lookahead: the strategy call site's map at bar `t` is unchanged by
  truncating the frame after `t`.
- Reachability registry classifies both knobs; the Stage −1 command is
  documented.

## Parallelisation

- **Sequential spine:** knobs + predicate first (every call site consumes
  them) → call sites → parity test (consumes both sides) → reachability →
  pre-registration commit → measurement.
- **Group (parallel):** the live call sites (`analyze.py`,
  `strategy_pass.py`) and the replay call sites (`backtest_scenarios.py`,
  `strategy_engine.py`) — disjoint files, both consume only the predicate.
- **Serial:** the two components' measurements — one shot at a time, no edit
  while a shot runs.
- **Shared files:** `config.py` and `arms/reachability.py` are also edited
  by other live plans (v128 and v129 name them); tasks touching them must
  not run concurrently with those.
- Full suite once, as the plan's final task.
