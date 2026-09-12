# v84 — MA Ribbon rescue: TRAIN grid result

**Written 2026-09-10, Task R21.**

**Edge:** expectancy — attempted removal of whipsaw false-starts via an
alignment-persistence requirement.

## Pre-registered rule (spec §4.5, verbatim)

TRAIN sweep `confirm_bars ∈ {2, 3}`; qualify at WR>=50, ExpR>0, N>=30,
excl<=50%, plateau required. 0/2 qualifying => closes this axis too, no
VALIDATION spent.

Baseline to beat (K=1, current shipped behavior): **N=233, WR 48.1%,
ExpR +0.270**.

## Grid route

Env-var route (`MA_RIBBON_CONFIRM_BARS=<K> python scripts/backtest/run_backtest_range.py ...`),
same plumbing as R17 — `config._apply_env()` reads live `os.getenv` at
import, and this field has no `.env` entry to be overridden by
`load_dotenv(override=True)`.

## Results

| K (`confirm_bars`) | N | Win rate | ExpR | excl% | Clears WR>=50, ExpR>0, N>=30, excl<=50%? |
|---|---|---|---|---|---|
| 2 | 210 | 48.1% | +0.269 | 27% | no — WR 48.1 < 50 (misses by 1.9pp) |
| 3 | 194 | 49.0% | +0.289 | 28% | no — WR 49.0 < 50 (misses by 1.0pp) |

Both cells report distinct N (210, 194), both below the K=1 baseline's 233,
confirming the override took effect at each grid point.

**0/2 qualify.**

## Plateau check

A 2-point grid has only one neighbour each, so `plateau_report` is weak here
— stating that limitation explicitly rather than treating a 2-cell
comparison as a real plateau demonstration, per the task's own instruction.
For the record: K=2 (ExpR +0.269) and K=3 (ExpR +0.289) differ by 0.020,
inside `PLATEAU_TOLERANCE_R = 0.03` — the two cells agree closely with each
other. This is moot for the verdict below (neither clears the absolute WR
gate regardless of agreement), but is worth recording: unlike RSI
Divergence's K=3/K=4 collapse, MA Ribbon's persistence axis does not show a
dramatic negative reaction to more confirmation bars — it's a small, flat,
still-short-of-floor effect in both directions tried.

## Observations

Both K=2 and K=3 land within 2pp of the 50% floor (48.1%, 49.0%) with
slightly improved ExpR over baseline (+0.269/+0.289 vs +0.270 baseline —
essentially flat, not a real improvement either). Unlike RSI Divergence,
where persistence actively hurt, MA Ribbon's persistence axis is
directionally neutral-to-flat: it doesn't clean up the population
meaningfully in either direction at these two K values. N shrinks modestly
(233 -> 210 -> 194) as expected from a stricter filter, with no red flag in
the shrinkage pattern.

## Verdict

**0/2 qualify — this axis is closed.** MA Ribbon's `confirm_bars` gate stays
permanently at its default `1` (off, byte-identical to pre-R20 behavior).
Per the plan, **R22 (Stage 2 walkforward) and R23 (VALIDATION) do not run**
— both are gated on R21 qualifying. No VALIDATION spent; budget remains
available. Per Global Constraints ("Record failures as-is"), this closes the
MA Ribbon rescue line here.
