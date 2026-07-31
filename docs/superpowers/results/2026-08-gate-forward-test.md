# A+ Forward Gate — 4-week paper test (pre-registered)

**Status:** template — runs only after enforce-mode promotion (G105/G106).
**Window:** 4 calendar weeks from the first A+ alert after promotion.
Start date: ____  End date: ____

## Pre-registered pass criteria (ALL must hold — written before the data)

- [ ] >= 10 A+ signals occurred in the window (else: extend 2 weeks, once)
- [ ] A+ cohort live WR Wilson LB >= B-tier cohort live WR (point estimate)
- [ ] A+ cohort expectancy (R) >= B-tier cohort expectancy
- [ ] zero gate-attributable incidents (crashes, wrong holds)

## Data (filled during the window — source: shadow/journal joins, !tierwr)

| week | A+ signals | A+ W-L | A+ WR (LB) | B WR | notes |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |

## On pass
Enforce may move from min-tier B to the chosen-tier ladder (G207).

## On fail (pre-registered — no renegotiation after seeing data)
Tier cuts revert to proposal state; gate stays enforce at min-tier B;
next attempt requires a fresh G98 frontier run and a new 4-week window.
