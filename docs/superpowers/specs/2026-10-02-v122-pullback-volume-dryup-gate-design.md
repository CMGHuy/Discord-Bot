# v122 — Pullback volume dry-up gate

**Version:** ui 1.21.0 · bot 2.0.0 (at writing)
**Bump:** bot patch (only if a scope passes VALIDATION and ships default-on; alert volume drops, no new surface)
**Edge:** expectancy

## Hypothesis

Lesson 5 of `docs/strategy/volume-in-context.md`: a pullback on **falling**
volume is a healthy, low-conviction counter-move, while a pullback on volume
as heavy as the impulse that preceded it carries real counter-trend
participation. The bot never distinguishes the two. Its only pullback-volume
rule (RSI Divergence `min_volume_ratio`, closed 2026-07) required volume
*expansion* at entry — the opposite sign — and `planning/quality.py:
component_volume` rewards high entry-bar volume for every setup type.

**Pre-registered claim:** removing pullback entries whose pullback leg
averaged more than `d` × the impulse leg's volume raises win rate without
costing expectancy, under the standard v72 funnel.

This is a **filter**, not a score weight. Blended-confidence score changes
regressed twice (v32, v33); a binary gate is measured by the v72 clauses
directly and has a mechanism clause (removed vs retained) a weight does not.

## Instrument (consumed from v121, not redefined)

`pullback_vol_ratio` from `swingbot/core/market/structure.py` (v121): mean
volume of bars `SH+1..t` ÷ mean volume of bars `SL0..SH`, on confirmed `k=3`
pivots (bullish; mirror for bearish). v121 must be merged first. The gate
calls the same function the snapshot uses; it never re-derives legs.

**Gate rule.** Reject the entry iff `pullback_vol_ratio is not None` **and**
`pullback_vol_ratio > d`. `None` (no defined pullback: too few pivots, price
already past the swing extreme, zero volume) **passes** — the gate removes
only populations it can positively identify, so clause 6 measures a defined
subset rather than a missing-data artefact. The share of `None` is reported.

## Scope — two independent components

| Component | Population the gate applies to |
|---|---|
| `strategy` | strategy-sourced entries for the frozen pullback list: Fibonacci, EMA Crossover (pullback mode only), Break & Retest, RSI, RSI Divergence, MA Ribbon, VWAP |
| `confluence` | confluence-sourced entries (level-touch entries; the bulk of the live book) |

Excluded by design: Support/Resistance and the short-only strategies
(breakout-style; lesson 5 says a spike is *wanted* there), MACD and Volume
Profile (the only `VALIDATED` badges — not diluted by an unrelated filter),
Elliott Wave (unclear entry style, N=0 on recent replays). The list is frozen
here; adding a strategy is a new pre-registration.

The two components are **separate pre-registrations with separate budgets**:
each is measured, selected and validated alone, and neither can be rescued by
pooling with the other. Both directions are inside each component; per-
direction results and horizon concentration (top-2 horizon share) are
disclosed, and an arm whose effect is > 80% one direction says so.

## Knobs

- `PULLBACK_DRYUP_SCOPE` — `off | strategy | confluence`, default `off`,
  `search_class = searchable` (one value per pre-registered component).
- `PULLBACK_DRYUP_MAX_RATIO` — float, default `0.0` meaning off,
  `search_class = searchable`.

Both live in `swingbot/config.py`'s schema, hot-reloadable like every other
field. The reachability registry (`backtesting/arms/reachability.py`)
classifies both before compute; Stage −1 must show changed outcomes on the
pilot for each scope, or the component is refused with budget intact.

## Frozen grid and selection rule

`d ∈ {0.60, 0.75, 0.90}` per component. Frozen **now**, before v121's
descriptive report exists; no bucket table from that report may move it.
Selection follows the funnel in `backtest-methodology.md` verbatim:

1. **Stage −1 reachability** (pilot) — refuse if zero changed outcomes.
2. **Stage 0 MDE** (fold-train, paired bootstrap since arms share keys) —
   refuse the shot if the TRAIN effect is below MDE.
3. **Stage 1 selection** (fold-train only) — eligible cells pass clauses 2–4
   and 6 on fold-train; `plateau_report()` mandatory: the chosen `d` needs an
   eligible grid neighbour. Among eligible plateau cells pick the largest
   ΔWR; tie → larger `d` (smaller cut).
4. **Stage 2 walk-forward** — `gate_win_rate`: ≥ 2 of 3 folds improving, no
   fold worse than −1.0pp, per-fold N ≥ 30.
5. **Stage 3 VALIDATION** 2024-01-01..2025-12-31 — one shot per component,
   all six v72 clauses, missing permutation p = FAIL.

**Clause 6 reading (frozen amendment).** A rejected entry frees the
one-position slot (strategy) or the 5-bar cooldown (confluence), so the
component arm is not a strict subset of baseline and `acceptance.py`
reports the mechanism clause `SKIPPED`. For v122 the mechanism clause is
scored on the **baseline** arm: trades the predicate flags at `d` (the
"removed" population) vs the **in-scope** baseline trades it does not flag
("retained" — trades outside the component's scope are in neither group); pass iff removed WR < retained WR **and** removed ExpR ≤ 0.
Replacement trades the freed slots admit are part of the component arm and
count fully in clauses 1–5; the replacement count is disclosed.

**Clause 5 instrument (partner decision, 2026-10-02).** Today's
`scripts/backtest/permutation_test.py` shifts strategy entries through
`backtest_wf.run_folds` on TRAIN folds and reports ExpR; it cannot score
stamped VALIDATION arms or confluence entries. v122 **extends that script**
(not a new instrument) to read a stamped arm pair, cover confluence as well as
strategy entries, and report a p-value on ΔWR (n = 200, fixed seed). The
extension gets its own reviewed task and a witness test proving the script's
existing output is unchanged, and it is frozen in the pre-registration
before any VALIDATION arm exists.
The arm-pair null shifts removal labels only. It refuses a pair with changed
outcomes on surviving keyed trades, which that null cannot model; a stamped
pair must also pass the producer, validation-window, universe, horizon and
engine checks before a p-value is computed. These are fail-closed instrument
requirements, frozen before either component's pre-registration.

Arms are produced with `scripts/backtest/measure_arms.py` (live
constructor via the arm engines) and judged by
`scripts/backtest/validate_component.py`. No bespoke measurement script. The
pre-registration record is committed under `docs/superpowers/results/`
before any outcome is read; `backtest-gate` is invoked before every run.

## Live / replay parity

One predicate, `pullback_dryup_rejects(df, direction, max_ratio) -> bool`,
in `swingbot/core/edge/gates.py`, called at the **same decision point** in
both paths: after the entry signal is known and before plan stamping —
`scanning/strategy_pass.py` and the confluence path in `scanning/analyze.py`
live; `backtesting/arms/strategy_engine.py` and the confluence arm engine in
replay. Each call site checks `PULLBACK_DRYUP_SCOPE` and, for `strategy`,
membership of the frozen list. The predicate is always evaluated on
**completed daily bars only**: a live call site drops today's still-forming
bar before calling it (as v119 does), so a pivot's `k` confirming bars are
never an unfinished candle and live matches replay. A parity test feeds one fixture through the
live and replay call sites and asserts the same accept/reject. Rejections are
logged with reason `pullback_volume` (scan funnel) so production shows what
the gate removed.

Out of scope: changing `component_volume`, any breakout volume rule, any
score weight, alert or chart text.

## Ship rule

A component flips default-on only after its own VALIDATION passes all six
clauses. Shipping sets `PULLBACK_DRYUP_SCOPE` and `PULLBACK_DRYUP_MAX_RATIO`
defaults in the schema (if both pass, the scope type becomes a set — decided
then, not now). A failure at any stage closes that component in the
closed-pre-registrations table with its numbers; the code ships merged and
inert (defaults off). Reopening needs a mechanism other than "pullback-leg
over impulse-leg mean volume above `d ∈ {0.60, 0.75, 0.90}`".

## Testing

- Predicate: `None` passes; ratio exactly `d` passes; `d + ε` rejects;
  bearish mirror; `max_ratio = 0` never rejects.
- Scope: `strategy` never touches confluence entries and vice versa; a
  strategy outside the frozen list is never gated; EMA Crossover in
  crossover (non-pullback) mode is never gated.
- Parity: same fixture, live call site and replay call site agree.
- Defaults-off witness: with both knobs at default, a replay fixture's trades
  are byte-identical to before the change.
- Reachability registry classifies both knobs; Stage −1 command documented.

## Parallelisation

Sequential spine: v121 merged → knobs + predicate → live call sites and
replay call sites (these two can be written in parallel: disjoint files, both
consume only the predicate) → parity test (consumes both) → reachability →
pre-registration commit → measurement. The two components' measurements are
**serial**, never concurrent: one shot at a time, no edit while a shot runs.
`config.py` and `reachability.py` are also touched by v123 — v122 and v123
tasks editing those two files must not run concurrently. Full suite once,
as the plan's final task.
