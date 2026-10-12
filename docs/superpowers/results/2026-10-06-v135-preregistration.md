# v135 pre-registration — headroom veto

**Committed before any v135 outcome is read and before any arm file exists.** Spec: `docs/superpowers/specs/implemented/2026-10-06-v135-headroom-veto-design.md`. Plan: `docs/superpowers/plans/implemented/2026-10-06-v135-headroom-veto_0-index.md` (parts `_1`, `_2`).

## Claim
Removing plans that have a multi-source opposing level nearer than `h` x their own risk raises win rate without costing expectancy, under the standard v72 funnel. A binary filter, not a score weight.

## Instrument
`gates.headroom_rejects(entry, stop, direction, levels, min_r)`. A blocker is a `levels.Level` strictly beyond entry on the target side, with `abs(level.price - entry) < h x abs(entry - stop)` (strict), confirmed by at least `HEADROOM_MIN_FAMILIES = 2` distinct `levels.strategy_family` families. No levels, zero risk or `h = 0` never reject. `HEADROOM_MIN_FAMILIES` is a frozen constant, not a grid axis. Planned prices only, never a fill: `Scenario.entry` / `Scenario.stop_loss` for confluence; the built plan's entry (filled price if set, else trigger) and `stop_loss` for strategy. Call sites: `analyze._apply_headroom` / `backtest_scenarios._headroom_kept` (confluence, on the lists the scenario was built from) and `strategy_pass._headroom_blocked` / `StrategyEngine._gated_plan` (strategy, after the plan is built). Parity is pinned by `tests/backtesting/test_headroom_parity.py`. The strategy veto reads a level map built at the signal bar itself in both paths (live: on the pass's completed frame; replay: on the frame truncated at the signal bar), never the engine's 5-bar TP2 map, so live, replay and the clause-6 reading judge a plan against the same map.

Instrument: v1 (the only one; `--instrument` not present at pre-registration).

## Components (separate budgets, never pooled)
| Component | Knob delta | Population |
|---|---|---|
| confluence | `HEADROOM_SCOPE=confluence`, `HEADROOM_MIN_R=h` | every confluence-scan scenario, both directions |
| strategy | `HEADROOM_SCOPE=strategy`, `HEADROOM_MIN_R=h` | EMA Crossover, VWAP, Fibonacci, Support/Resistance, RSI, Elliott Wave, MA Ribbon, Break & Retest, RSI Divergence |

MACD, Volume Profile and every `strategy_types.SHORT_STRATEGIES` name are never gated. Arms come from `scripts/backtest/measure_arms.py` with both default engines, so each component is judged against the whole replayed book it would ship into. Order: confluence fully through its funnel first, then strategy. One shot at a time.

## Frozen grid and selection rule (verbatim from the spec)
`h ∈ {0.5, 0.75, 1.0}` per component. No bucket table from v125 (`room_atr`) or v133 may move it.
1. **Stage −1 reachability** (pilot, `h = 1.0`, the widest cut): refuse on zero changed outcomes.
2. **Stage 0 MDE** (fold-train `selection` arms, paired bootstrap; arms share keys): run per cell with `--train-effect-pp` set to that cell's fold-train standardised ΔWR. A refused cell is ineligible at Stage 1. If all three are refused, the shot is refused with the budget intact.
3. **Stage 1 selection** (fold-train only): eligible cells pass clauses 2–4 and 6 (SKIPPED is not a pass); `plateau_report()` is mandatory and the chosen `h` needs an eligible grid neighbour. Among eligible plateau cells pick the largest ΔWR; tie → smaller `h` (smaller cut). Judge: `validate_component.py --stage selection --headroom-mechanism`.
4. **Stage 2 walk-forward**: `gate_win_rate`: ≥ 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N ≥ 30.
5. **Stage 3 VALIDATION** 2024-01-01..2025-12-31: one shot per component, all six clauses, missing permutation p = FAIL. Judge: `validate_component.py --stage validation --headroom-mechanism --permutation-p <p>`.

## Clause 6 reading (frozen, same as v122)
A rejected entry frees the one-position slot (strategy) or the 5-bar cooldown (confluence), so the component arm is not a strict subset of baseline. The mechanism clause is scored on the **baseline** arm: in-scope trades the predicate flags at `h` ("removed") vs in-scope trades it does not flag ("retained"); pass iff removed WR < retained WR **and** removed ExpR ≤ 0. Out-of-scope trades are in neither group. Replacement trades count fully in clauses 1–5 and their count is disclosed.

**How a baseline trade is read** (`swingbot/core/backtesting/arms/headroom_clauses.py`). An arm row carries no entry or stop, so the reading replays the baseline with both knobs forced off. Strategy: each in-scope `(ticker, strategy, horizon)` cell is replayed through `StrategyEngine.iter_trades`, giving the baseline's own plans; the level map is built at each trade's own signal bar, identical to the map the replay gate and the live gate read. Confluence: each trade's scenario and support/resistance lists are rebuilt with `backtest_scenarios.scenarios_at` after priming the level bucket, reproducing the replay bar for bar. Flags use `gates.blocker_inside`, the gate's own comparison. A trade the replay does not reproduce is never flagged and is disclosed as `unreadable`.

## Clause 5 instrument
`python scripts/backtest/permutation_test.py --arms <the stamped VALIDATION arm file> --n 200 --seed 42`, the arm-pair mode v122 added. No change to the script or its null. Its `p_value` is passed as `--permutation-p`; a null p is a FAIL.

## Disclosure (every stage reached)
Removed / added (replacements) / changed counts; per-direction ΔWR and ΔExpR; the top-2 horizon share of the removed trades; a statement when more than 80% of the removed trades are one direction; the `no_map` and `unreadable` shares of the scoped baseline population (the judge's JSON line); and the baseline-reading flagged WR, retained WR and flagged ExpR.

## Stop rules
A refusal or failure at any stage closes that component in `docs/claude/backtest-methodology.md`'s closed-pre-registrations table with its numbers; later stages are not run and an unspent VALIDATION budget stays unspent. The code stays merged and inert (defaults off). A component flips default-on only after its own VALIDATION passes all six clauses. Reopening needs a mechanism other than "an opposing level with ≥ 2 source families nearer than `h ∈ {0.5, 0.75, 1.0}` × risk".
