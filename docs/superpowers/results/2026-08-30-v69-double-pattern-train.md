# v69 Double Pattern — TRAIN grid

Plan v69 Task DB6. The standard strategy harness replayed the cached TRAIN
window (2020-01-01 through 2023-12-31) for three cached symbols. No fetch
failed and the smoke run had non-zero activity before the grid started.

## Pre-registered rule

> Per (direction, horizon) cell include iff win_rate >= 50 and expectancy_r >
> 0 and N >= 30 and excluded <= 50%; adopt the parameter set with the best
> pooled ExpR among sets having at least two qualifying cells. If no set has
> two qualifying cells, none is adopted and VALIDATION is not spent.

## Twelve-cell table

| equality tol % | separation % | volume multiple | N | WR % | ExpR | excluded % | qualifies |
|---:|---:|---:|---:|---:|---:|---:|---|
| 2 | 5 | off | 8 | 37.5 | +0.195 | 38 | no |
| 2 | 5 | 1.5 | 0 | n/a | +0.862 | 100 | no |
| 2 | 10 | off | 4 | 0.0 | -1.030 | 0 | no |
| 2 | 10 | 1.5 | 0 | n/a | n/a | 0 | no |
| 3 | 5 | off | 10 | 40.0 | +0.203 | 38 | no |
| 3 | 5 | 1.5 | 0 | n/a | +0.862 | 100 | no |
| 3 | 10 | off | 5 | 0.0 | -0.865 | 17 | no |
| 3 | 10 | 1.5 | 0 | n/a | n/a | 0 | no |
| 5 | 5 | off | 18 | 33.3 | +0.059 | 28 | no |
| 5 | 5 | 1.5 | 2 | 50.0 | +0.619 | 50 | no |
| 5 | 10 | off | 5 | 0.0 | -0.865 | 17 | no |
| 5 | 10 | 1.5 | 0 | n/a | n/a | 0 | no |

## Decision

No configuration qualified: the closest row (`equality_tol_pct=5`,
`separation_pct=5`, volume arm off) has only N=18 and 33.3% WR. Every row is
under-populated relative to N>=30, and no parameter set has even one qualifying
cell, let alone the required two. No values are adopted, `STRATEGY_GATES`
remains absent, and the VALIDATION budget is deliberately not spent.

## Observations

This repeats the relevant part of Elliott Wave's fate: geometry built from
`zigzag_pivots` fires too rarely in this cached TRAIN universe to earn an alert
scope. The volume-confirmation arm reduced already-small samples to zero (or
two trades); a positive expectancy with zero evaluated trades is not evidence.
The feature is therefore no-lift rather than an inert strategy to ship.
