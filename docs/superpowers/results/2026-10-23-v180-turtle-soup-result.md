# v180 result — Turtle Soup entry, structural arm: NO-LIFT

Spec: `docs/superpowers/specs/implemented/2026-10-21-v180-turtle-soup-entry-design.md`.
Pre-registration (frozen before any outcome; readings appended): `docs/superpowers/results/2026-10-21-v180-turtle-soup-preregistration.md`.
Plan: `2026-10-21-v180-turtle-soup-entry` (index `_0-index.md`, parts 1, 2a, 2b, 3).
Edge: expectancy. Screen: `screen-turtle_soup` SCREEN-PASS. Data source: `alpaca` (the screen ran on yfinance; disclosed, decides nothing).
Ledger: `v180-turtle-soup-structural`, verdict `NO-LIFT`.

## Verdict

NO-LIFT at Stage 0 by the frozen A3 rule. The A1 TRAIN point on fold-train (2018-06-01..2022-12-31) is -0.2145pp pooled ΔWR, below the paired MDE of 0.3132pp, so the shot was refused. VALIDATION was not spent and its budget is intact.

## The funnel

| Stage | Window | Reading | Gate |
|---|---|---|---|
| −1 reachability | 2018-06-01..2020-12-31 (pilot) | changed outcomes 12; split removed 0 changed 0 added 12 | REACHABLE |
| 0 MDE (A3) | 2018-06-01..2022-12-31 | A1 TRAIN -0.21pp vs paired MDE 0.31pp (observed decided N 9405 over 1675d) | REFUSED |
| 1 selection | — | not run: the funnel stopped at Stage 0 | — |
| 2 walk-forward | 2021 / 2022 / 2023 | not run: the funnel stopped at Stage 0 | not run |
| 3 VALIDATION | 2024-01-01..2025-12-31 | not run: the funnel stopped at Stage 0 | not run |

## Against the prediction

The spec predicted a positive but small ExpR on the added rows and a win rate below the book's, with a fail on the win-rate clause as the base case. Stage 0 measured the win-rate side: the pooled ΔWR is negative (-0.21pp) and the added rows' decided win rate is 27.1% (n = 210 trades), consistent with the base case. The added-row ExpR was not measured by a gate; the descriptive screen-style race of the traded population gives -0.046R, below the screen's +0.316R paired figure for the fixed 1.5/3 ATR bracket, so the base case holds and the structural plan shape did not rescue the trigger on this window.

## Descriptive blocks (never gating)

Stage 0 (fold-train), from `docs/superpowers/results/v180/selection.turtle_soup.json`:

- Drop and cancel shares of signals (855): trade 0.246, risk cap 0.480, no level in band 0.188, plan other 0.000, open through the stop 0.018, risk cap at the fill 0.062, not triggered 0.000, position open 0.007.
- Each population's screen-style outcome (ExpR, n): trade -0.046 (210), risk cap -0.018 (410), no level in band -0.068 (161), open through the stop -0.571 (15), risk cap at the fill -0.110 (53), position open +0.079 (6). None approaches the screen's +0.316R.
- Sweep depth `(L − Low[t]) / ATR14[t]`: kept median 0.149 (p25–p75 0.071–0.279), dropped median 0.188 (0.082–0.348).
- Early stops (within 2 sessions): 0.500.
- Exit mix: target 0.233, stop 0.629, gap 0.110, time cap 0.029; decided win rate 27.1%.
- Regime: SPY above its 200-day SMA ExpR -0.170, WR 28.8%; below ExpR -0.380, WR 22.8%.
- Signal clustering: max 15, p95 7.0 Turtle Soup signals per day.
- Universe: added-row share outside the S&P 500 0.210.

Stage −1 pilot (never gating): 53 signals, decided win rate 8.3% (n = 12), added-row share outside the S&P 500 0.25.

## Disclosures

- Costs on the added rows only: Turtle Soup rows net of 5 bps a side plus `commission_r()`, baseline rows gross. Clause 2 and the badge ExpR compare a net cohort with a gross book, a bias against the arm. Clause 1 and the badge win rate are unaffected.
- Hold-cap parity: the screen's `CAP = 10` and this plan's 10 sessions (fill = session 1) both close at the close of `t+10`.
- Two risk-cap readings, reported apart: `risk_cap` (builder, signal close) and `cancelled_risk_cap_fill` (fill).
- "No level in the band" read literally: no synthetic target.
- The first Stage 0 producer attempt (2026-10-22) died at 124/134 tickers and wrote no arm file; it was re-run once under the funnel's crashed-run rule. The written arm file is the only look.
- Multiple comparisons: two ideas were screened on 2026-10-21 (`turtle_soup` SCREEN-PASS, `sweep_reclaim_bos` SCREEN-FAIL), and one arm entered this funnel. The ledger's BH q for this row: n/a (no p-value), reported, never gating.

## What this licenses and what it closes

Turtle Soup is closed under this shape. It never re-enters the funnel with a retuned `channel`, `min_age`, stop buffer, R:R band or hold cap. Arm A (the screened 1.5/3 ATR shape) stays closed without a run. The screen pass stays in the ledger as measured. A different shape is a new idea and needs its own screen and spec. The masked code stays on `main`, inert (`STRATEGY_GATES` directions `()`, knob default `off`).
