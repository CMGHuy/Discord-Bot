# v72 acceptance funnel — timing smoke run

Not a component decision. This times the machinery and proves the stages
wire together; no pre-registration is opened, spent or affected.

## Gate cost (bootstrap)

| Population | Resamples | Wall clock |
|---|---|---|
| v68 fixture (1159 baseline vs 1139 component trades) | 10,000 | 17.1s |

## Replay cost (one fold-test year, full width)

| Tickers | Horizons | Window | Trades | Wall clock |
|---|---|---|---|---|
| 72 | 10 | 2021-01-01..2021-12-31 | 2144 baseline / 2039 component | 6465.5s (~108 min) |

Run via a standalone script mirroring `make_v68_fixture.py`'s logic
(`load_frames` → `replay_scenarios` → `simulate_exit`, DCB veto as a
post-hoc filter over `dead_cat_bounce()`), with `SAMPLE_EVERY=1` and all 10
horizon keys. Watchlist scope is 77 tickers; 72 had a cached CSV on this
machine and were replayed — 5 short of the 89-ticker cache-wide universe the
spec's extrapolation assumed. **Because this component (DCB veto) is a pure
post-hoc filter, baseline and component trades come out of the *same*
replay/`simulate_exit` pass** — this 6465.5s figure already covers both arms
for a component of this shape. A component that instead needs its own
`gates=` (a different signal definition, not just a filter on the baseline's
signals) would need an independent `replay_scenarios` pass per arm, roughly
doubling this cost.

## Projected full funnel

Stage 2 is three fold-test years, two arms each. Stage 3 is one two-year
window, two arms. Using the measured 6465.5s/year-at-full-width as the
per-arm-pass cost (the plan's own costing assumption), and scaling Stage 3
linearly by window length (2 years ≈ 2× a 1-year pass):

- Stage 2 (2021 / 2022 / 2023, 2 arms each): 3 × 2 × 6465.5s ≈ 10.8h
- Stage 3 (2024-01-01..2025-12-31, 2 arms): 2 × 2 × 6465.5s ≈ 7.2h
- Gate (bootstrap, both stages): 2 × 17.1s ≈ negligible

**Projected total ≈ 18h for a two-gate-config component — well past the
spec's 2-5h estimate.** Replay dominates by roughly three orders of
magnitude over the bootstrap gate (17.1s vs. hours), so the estimate's gap
is entirely in the replay stage, not the statistics. The 2-5h estimate holds
only for a post-hoc-filter component (DCB-veto shape), where both arms share
one pass and the true cost is closer to Stage 2 ≈ 5.4h + Stage 3 ≈ 3.6h ≈
9h — still above the top of the spec's range. Either the spec's estimate
needs revising upward, or Stage 2/3 need a narrower ticker/horizon sample
than full width to stay inside a practical session.
