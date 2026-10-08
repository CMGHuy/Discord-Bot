# v128 — Fair value gap lift audit: all vs off vs displacement-only

**Version:** ui 1.21.1 · bot 2.0.0 (at writing)
**Bump:** bot patch (inert flag at default; a non-default mode ships only if it clears VALIDATION under both gates)
**Edge:** expectancy

## Why

`swingbot/core/market/fvg.py` contributes every unfilled 3-candle gap from
the last 100 bars (max 3 per side) to `levels.collect_candidate_levels`.
That makes FVG a source in two places at once:

1. **A confluence vote.** `"FVG"` is one of the 12 price families counted by
   `levels.count_confirming_strategies`. That count feeds the
   `MIN_CONFLUENCE` gate and the confidence score.
2. **A candidate price.** A gap midpoint can become an entry, stop or target level.

The gap has no minimum size and no condition on the candle that created it, so a
few-cent gap left by an ordinary bar casts a full vote. FVG predates the
validation registry and has **never been lift-tested**: v49 measured it only
as a redundancy count, and it is absent from the closed-pre-registrations table
in `docs/claude/backtest-methodology.md`. Nothing here reopens a closed row.

The idea came from a price-action handbook the partner shared (2026-10-02):
an FVG matters only in the sequence liquidity → **displacement** → structure →
FVG → reaction. The displacement half of that sequence can be computed on daily
bars without lookahead. The sweep and structure halves need v121's pivots and
belong to the follow-on spec (chop + sweep features).

**Pre-registered claim:** removing FVG levels entirely (`off`), or keeping only
gaps whose middle candle is a displacement candle (`displacement`), improves
the scan under **both** the v72 win-rate gate and the v92 harvest gate.

## Knobs

- `FVG_LEVELS_MODE`: `all | displacement | off`, default `all`
  (production byte-identical), `search_class = searchable`.
- `FVG_DISPLACEMENT_ATR_K`: float, default `1.5`, read only when mode is
  `displacement`, `search_class = searchable`.

Both are fields in `swingbot/config.py`'s schema (hot-reloadable), threaded
through `ScanParams` as `fvg_levels_mode` / `fvg_displacement_atr_k`, the same
way `avwap_levels_enabled` is. The mode check in `levels.py` sits **outside** the
`try`, as AVWAP's does, so a renamed field fails loudly instead of silently
dropping the source. Both are registered in `backtesting/arms/reachability.py`
as reachable. Replay calls `collect_candidate_levels`, the same function live
calls, so live and replay share one code point and need no separate parity
wiring.

**Scope of removal (partner decision):** a gap filtered out by the mode
disappears from **both** roles, the confluence vote and the candidate price.
Charts (`chart_geometry.py`, `/strategycharts`) keep drawing every unfilled
gap whatever the mode; that is display, not signal.

## Displacement rule (causal)

A gap formed at third-candle index `i` (`bar_index` in
`find_fair_value_gaps_detailed`) is a displacement gap iff its middle candle
`m = i − 1` satisfies all of:

- `|Close[m] − Open[m]| ≥ k × ATR14[m]`, using `indicators.atr(df, 14)`, which is
  computed only from bars `≤ m`.
- **Bullish gap:** `Close[m] ≥ Low[m] + (2/3)·(High[m] − Low[m])`.
  **Bearish gap:** `Close[m] ≤ Low[m] + (1/3)·(High[m] − Low[m])`.
- `ATR14[m]` is finite and > 0 (otherwise the gap is **not** a displacement gap).

The gap only exists once bar `i` has closed, so the rule never reads a bar the
gap's own existence did not already need. The existing fill check reads bars
`i+1 … n−1` of the frame it is handed; replay already truncates that frame at
the decision bar. A test asserts that appending future bars cannot change
whether an already-formed gap counts as displacement.

## Frozen grid and selection

Arms: baseline `all`; candidates `off`, `displacement@k ∈ {1.0, 1.5, 2.0}`.
The grid is frozen **now**, before any arm is produced, and no table from any
stage may move it.

Funnel per `backtest-methodology.md`, with each stage scored **twice** by
`scripts/backtest/validate_component.py`, once `--gate win_rate` (v72) and once
`--gate harvest` (v92). A cell advances only if **both** pass at that stage.

1. **Stage −1 reachability** (pilot, 10 tickers): each candidate must show
   changed outcomes or it is refused with the budget intact.
2. **Stage 0 MDE** (fold-train, paired bootstrap, since the arms share keys): a
   candidate below MDE under either gate is refused with the budget intact.
3. **Stage 1 selection** (fold-train only). Eligible cells pass every
   fold-train-applicable clause of both gates. `plateau_report()` is
   mandatory for the `k` grid: a chosen `k` needs an eligible neighbour.
   `off` is a boolean arm with no neighbour; it is eligible on its clauses
   alone, as AVWAP's on/off was in v35. If `plateau_report()` cannot accept a
   single-point arm, the plan's first measurement task records how it was
   scored *before* any arm is read. **At most one winner across all four
   candidates.** Pick the largest ΔExpR (Edge: expectancy). On a tie, prefer
   the smaller alert cut, then `displacement` over `off` (smaller change).
4. **Stage 2 walk-forward** (folds 2021/2022/2023): `gate_win_rate` (≥ 2 of 3
   folds improving, none worse than −1.0pp, per-fold N ≥ 30) and the harvest
   gate's walk-forward rule. Both must hold.
5. **Stage 3 VALIDATION**, 2024-01-01..2025-12-31: **one shot, total**, for the
   single Stage-1 winner. All six v72 clauses plus every v92 clause. A
   missing permutation p is a FAIL.

**Clause 6 reading (frozen amendment, same shape as v122's).** A mode change
both drops setups (a lost confluence vote) and moves the stops and targets of
setups that survive, so the arm is not a strict subset of baseline. The mechanism clause
is scored on the **baseline** arm. "Removed" means baseline trades whose
confluence families include `FVG` from a gap the mode filters out, **or** whose
entry/stop/target level came from such a gap. "Retained" means every other
baseline trade. Pass iff removed WR < retained WR **and** removed ExpR ≤ 0.

**Clause 5 dependency.** The permutation p on stamped VALIDATION arms needs
the `permutation_test.py` extension v122 specifies (stamped arm pair,
confluence plus strategy entries, ΔWR p, n = 200, fixed seed). v128 reuses it
and does not build a second one. If it has not landed on `main` when v128
reaches Stage 3, the plan **stops before VALIDATION** and leaves a resume
point, with the budget unspent. Stages −1 to 2 do not need it.

Arms come from `scripts/backtest/measure_arms.py` (the standard producer), not
a bespoke instrument. The pre-registration record is committed under
`docs/superpowers/results/` **before** any arm is produced. The
`backtest-gate` skill is invoked before every run. Every run longer than about 2
minutes goes to `backtest-runner`, one arm per chunk.

## Reporting (every stage)

- One stage result file under `docs/superpowers/results/`.
- **Attribution table (diagnostic, never a gate):** per candidate, the number of
  baseline trades changed by vote loss only, by price change only, or by both;
  removed-vs-retained WR/ExpR for each bucket; per-direction split and top-2
  horizon share (if over 80%, say so explicitly).
- **Context slice (diagnostic, Stage 1 report only):** baseline `all`-arm trades
  sliced by whether `FVG` is among their confluence families. Labelled
  confounded (FVG-tagged setups carry more families by construction); it
  explains, it never selects.
- Whatever the outcome, add a row to the closed-pre-registrations table in
  `docs/claude/backtest-methodology.md` and mirror it in `AGENTS.md` if that table is
  mirrored there.

A PASS flips `FVG_LEVELS_MODE`'s default to the winner, and to the winning `k` for
displacement, in its own reviewed commit and `bot patch` release. Any other
outcome leaves the default `all` and the code merged inert.

## Code changes

- `fvg.py`: `is_displacement_gap(df, gap, k, atr_series=None) -> bool`; a
  `mode`/`k` parameter on `find_fair_value_gaps` (default `all` = today's
  output). `find_fair_value_gaps_detailed` is unchanged; charts keep using it.
- `levels.py`: `collect_candidate_levels` reads `params.fvg_levels_mode` and
  `params.fvg_displacement_atr_k` outside the `try`; `off` emits no FVG
  candidates.
- `config.py`, `scan_params.py`: the two fields, validated (the enum, and
  `k > 0`).
- `backtesting/arms/reachability.py`: both knobs classified as reachable.
- A small attribution helper for the report, in the report/measurement script
  layer and not in the scan path.

Every function written or changed stays below cyclomatic complexity 15. The
`no-lookahead` skill applies to the displacement rule.

## Testing

- `is_displacement_gap` on hand-built frames: strong body in the right third → True;
  body below `k·ATR` → False; wrong third → False; NaN/zero ATR → False;
  bearish mirror; appending future bars does not change the verdict.
- `find_fair_value_gaps(mode="all")` equals today's output on a fixture
  (characterisation, captured before the change); `off` returns `[]`;
  `displacement` returns a subset of `all`.
- `collect_candidate_levels` / `count_confirming_strategies`: the `FVG` family
  disappears in `off`, is unchanged in `all`, and follows the filter in
  `displacement`.
- Config: invalid mode or `k ≤ 0` rejected; defaults leave scan output
  identical (the existing scan/level tests stay green unchanged).
- Reachability: both knobs classify as reachable.
- One full-suite run, as the plan's final task.

## Out of scope

The chop (flat/intertwined EMA) and liquidity-sweep features, which are a
separate follow-on spec built on v121; FVG zone width/edges instead of the
midpoint; minimum gap size; FVG age; order blocks; any chart or alert-text
change; the strategy-path entry trigger.

## Parallelisation

The code tasks (fvg filter → levels wiring → config/reachability) form one
sequential chain: each consumes the previous one's interface. The
pre-registration record can be written in parallel with the code, but must be
committed before Stage −1. Stages −1 → 0 → 1 → 2 → 3 are strictly sequential,
because each stage's refusal stops the next. Stage 3 also waits on v122's
permutation extension. The full suite is the last task.
