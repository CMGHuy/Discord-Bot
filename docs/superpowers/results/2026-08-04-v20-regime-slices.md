# V20 — Regime slices (plan v8, Phase V4)

**Status:** pre-registration written 2026-08-04 **before the harness was run.**
Everything below the "Result" heading was empty when this file was committed.

## What this measures, and why it survives V52

V17 (sizing) and V52 (selectivity) both terminated with an empty adopted set,
which blocks V18/V22/V24 — they all need a *candidate* config. V20 does not.
It asks a different question about the config we already ship:

> Does today's configuration work across market regimes, or only in the
> post-2020 bull window that produced it?

That is answerable with no adopted candidate, and the plan already
pre-registers the decision rule: **"A config that only works post-2020 is
rejected."**

## Config under test — production, pinned

Read off the live deployment on the run date, not assumed:

| Setting | Value |
|---|---|
| `PLAN_ENGINE_V2` | on |
| `INTRADAY_MANAGER_V2` | true |
| `MIN_TARGET_PCT` / `TARGET_FLOOR_ENABLED` | 2.5% / true |
| `MAX_LOSS_PCT` / `MAX_LOSS_CAP_ENABLED` | 1.75% / true |
| Exit model | **v2 + scale-out**, TP2 `levels`, frictions **on** |

**This differs from V16's baseline**, which ran exit model **v1** and finished
at 17:28 on 2026-08-02 — before V51's 1.75% cap landed at 22:01 the same day.
V16's numbers are therefore **not** a valid comparator for these slices. All
comparison here is *between regimes under one config*, never against V16.

At 2.5%/1.75% the payoff is 1.43R and break-even is **41.2%**, against a
measured no-skill rate of **43.4%** (`2026-08-02-v52-barrier-base-rate.md`).

## The seven windows, fixed before running

Chosen from the regimes the task names. Dates are peak-to-trough for the
drawdowns; all sit inside TRAIN (1999-01-01 .. 2023-12-31), so **no validation
budget is spent.**

| # | Regime | From | To |
|---|---|---|---|
| 1 | Dot-com bust | 2000-03-10 | 2001-12-31 |
| 2 | 2002 bear | 2002-01-01 | 2002-10-09 |
| 3 | GFC | 2007-10-09 | 2009-03-09 |
| 4 | 2011 (downgrade / euro) | 2011-05-02 | 2011-10-03 |
| 5 | 2015-16 | 2015-05-21 | 2016-02-11 |
| 6 | COVID crash | 2020-02-19 | 2020-03-23 |
| 7 | 2022 bear | 2022-01-03 | 2022-10-12 |

**Slicing is by `entry_date`** (`run_backtest_range.window_trades`), so a trade
entering inside a window resolves on the full price history and is *not*
truncated at the window edge. Short windows therefore produce a small N, not a
pile of artificial timeouts.

## The decision rule, pre-registered

1. **Minimum N.** A window with **N < 30** closed trades is reported but marked
   `INSUFFICIENT` and is **excluded from the rejection test**. It is not
   evidence either way.
2. **Rejection.** The config is **rejected as regime-fragile** if N-weighted
   expectancy is `> 0` in the post-2020 windows (COVID, 2022) **and** `<= 0` in
   *every* sufficient pre-2020 window.
3. **No pass threshold is pre-registered.** Consistent with V6 Step 4, no
   expectation is invented after the fact. Anything other than rejection is
   reported as measured, and does not by itself license adoption of anything.

## Known limits, stated before the numbers exist

- **Survivorship is the dominant confound and it runs the same direction in
  every early window.** The universe is today's 78-ticker watchlist. Names that
  did not trade in 2000 (ASTS, CRWV, HOOD, IREN, PLTR, RKLB, SOFI, …) simply
  contribute nothing, so early regimes are measured on a small, *already
  survived* subset. A good early number is therefore weak evidence, and a bad
  one is strong. This is exactly what **V21 Step 2** exists to audit; V20 does
  not resolve it.
- **N will be small in the short windows** (COVID is ~23 trading days). Rule 1
  above exists so those cannot quietly drive a conclusion.
- **Daily bars overstate expectancy by ~0.318R** with a 30.3% outcome
  disagreement rate (`2026-08-02-v51-hourly-fidelity.md`). That error bar is
  wider than most differences this grid can produce, so cross-regime *rankings*
  should not be read as real; only sign and rough magnitude should.

## Reproduce

```bash
python scripts/regime_slices.py --json docs/superpowers/results/2026-08-04-v20-regime-slices.json
```

One pass over the ticker × horizon × strategy grid, sliced seven ways —
`run_backtest` is the expensive call and is identical for every window, so
running the seven windows as seven separate `run_backtest_range.py` invocations
would recompute it 7×. Same recomputation trap V50 found in the sizing grid.

## Result

*Not yet run — this section is intentionally empty until the harness finishes.*
