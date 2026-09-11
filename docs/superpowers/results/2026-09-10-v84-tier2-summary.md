# v84 — Tier 2 results consolidation

**Written 2026-09-10, Task R28.**

Tier 2 covered three of the four strategies gated behind the shared
fold-arms emitter (R15): RSI Divergence, MA Ribbon, Support/Resistance.
(The fourth, Fibonacci, is Tier 3 — separate part.)

## Summary table

| Strategy | Adopted config | TRAIN verdict | Stage 2 verdict | VALIDATION verdict | Final badge |
|---|---|---|---|---|---|
| RSI Divergence | none | REJECTED-ON-TRAIN — 0/3 qualify (`min_consecutive_rsi_turn` grid {2,3,4}) | not run (gated on TRAIN qualifying) | not run (gated) | WEAK (unchanged) |
| MA Ribbon | none | 0/2 qualify (`confirm_bars` grid {2,3}) | not run (gated on TRAIN qualifying) | not run (gated) | WEAK (unchanged) |
| Support/Resistance | none | 0/3 qualify (`min_level_touches` grid {1,2,3}) | not run (gated on TRAIN qualifying) | not run (gated) | WEAK (unchanged) |

## Every strategy that died at a free stage

All three died at the same stage — TRAIN — none reached Stage 2 walkforward:

- **RSI Divergence** (Task R17): K=2 missed the WR floor by 1.0pp (49.0% vs
  50%) despite a slightly-improved ExpR; K=3/K=4 collapsed badly (WR
  28.6%/10.0%, ExpR -0.262/-0.326) — a real, monotonic, non-noisy negative
  effect (persistence delays entry past the strategy's early-turn window,
  per the reviewer's mechanism check). Plateau check on the best cell:
  `is_plateau: False` (spike, not stable) — independently disqualifying.
- **MA Ribbon** (Task R21): both grid cells (K=2, K=3) missed the WR floor
  narrowly (1.9pp, 1.0pp short) with roughly flat ExpR vs baseline —
  directionally neutral, not a collapse. 2-point-grid plateau weakness
  stated explicitly per the task's own instruction; the two cells do agree
  closely (0.020R apart) but this is moot since neither clears the
  absolute gate.
- **Support/Resistance** (Task R25): all three grid cells (K=1/2/3) missed
  the WR floor by 5.1-5.8pp with a genuinely stable plateau
  (`is_plateau: True`, 0.009R spread) — a real but too-weak filter, not a
  spike. Confirms the implementation task's (R24) own flagged prediction
  that most tested breakouts already clear a low touch-count bar.

An empty rescue column — no VALIDATION spent on any of the three — is the
finished answer here, not a stub. Every gate is documented in its own
results doc (`2026-09-10-v84-{rsidiv,maribbon,sr}-train.md`) with raw
numbers, independent arithmetic re-verification by a task reviewer, and the
exact pre-registered rule each verdict was scored against.

## VALIDATION-window look count spent by this part

**0 (of a possible 3).** No strategy in Tier 2 cleared its free TRAIN stage,
so R19/R23/R27 never ran and no VALIDATION window was looked at for RSI
Divergence, MA Ribbon, or Support/Resistance. All three VALIDATION shots
remain available (reopening any of these three specific badge questions
would need a genuinely new mechanism, not a re-run, per
`docs/claude/backtest-methodology.md`).

Combined with Tier 1 (0/3 spent — EMA Crossover, Break & Retest, VWAP all
closed at fold stability), the plan has spent **0 of its maximum 7
VALIDATION shots** through the end of Tier 2.

## Shared harness note

All three strategies' gates ship at their pre-existing/off default
(`min_consecutive_rsi_turn=1`, `confirm_bars=1`, `min_level_touches=0`) —
byte-identical to pre-v84 production behavior in every case, verified by
each task's own `test_gate_off_is_byte_identical` test. R15's shared
fold-arms emitter (`scripts/backtest/measure_strategy_arm.py`) was built but
never invoked in Tier 2, since no strategy reached the Stage 2 gate it
serves — it remains available for Tier 3 (R31-R35, Fibonacci) unchanged.
