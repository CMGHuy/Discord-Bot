# V20 — Regime slices (plan v8, Phase V4)

**Status:** pre-registration written 2026-08-04 **before the harness was run**
(everything below the "Result" heading was empty when this file was first
committed, `f7427ab`); result filled in 2026-08-04 after the grid finished.
**Verdict: NOT REJECTED — and "not rejected" is not a pass.**

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

Run 2026-08-04, ~50 min, 78 tickers × 10 horizons × 11 strategies in one pass.
Raw output: `2026-08-04-v20-regime-slices.json`.

| # | Regime | Window | N | Win% | ExpR | Pooled max DD | Verdict |
|---|---|---|---:|---:|---:|---:|---|
| 1 | Dot-com bust | 2000-03-10..2001-12-31 | 396 | 34.6 | **−0.171** | −75.9% | non-pos |
| 2 | 2002 bear | 2002-01-01..2002-10-09 | 421 | 42.3 | **−0.139** | −54.0% | non-pos |
| 3 | GFC | 2007-10-09..2009-03-09 | 794 | 45.8 | **+0.027** | −55.1% | pos |
| 4 | 2011 | 2011-05-02..2011-10-03 | 266 | 32.0 | **−0.247** | −59.2% | non-pos |
| 5 | 2015-16 | 2015-05-21..2016-02-11 | 565 | 38.1 | **−0.094** | −56.7% | non-pos |
| 6 | COVID crash | 2020-02-19..2020-03-23 | 6 | 16.7 | +1.689 | −3.0% | INSUFFICIENT |
| 7 | 2022 bear | 2022-01-03..2022-10-12 | 384 | 45.6 | **+0.097** | −41.6% | pos |

### The pre-registered rule, applied mechanically

**NOT REJECTED.** Sufficient pre-2020 windows: all five of 1-5. Sufficient
post-2020: `bear_2022` only — COVID's N=6 lands far under the N≥30 threshold,
exactly the case Rule 1 exists for (its +1.689R is one or two lucky trades over
23 trading days and carries nothing).

Rejection required post-2020 `> 0` **and** *every* sufficient pre-2020 window
`<= 0`. The second clause fails on a single window: **GFC at +0.027R**. Four of
the five pre-2020 windows are negative; the config escapes the
"only works post-2020" verdict by 0.027R in one window out of seven.

That is the rule as written, applied without adjustment. Per Rule 3 **no pass
threshold was pre-registered, so "not rejected" is not a pass** and licenses
adoption of nothing.

### What the numbers say beyond the rule

- **Both positive windows are inside the known error bar, and it points down.**
  V51 measured daily bars *overstating* expectancy by **+0.318R** at a 30.3%
  outcome-disagreement rate (`2026-08-02-v51-hourly-fidelity.md`). GFC's
  +0.027R and 2022's +0.097R are a fraction of that correction. Applying it in
  the direction V51 measured puts **every** window in this table negative. The
  pre-registration said this in advance — "only sign and rough magnitude should
  be read" — and here it is the sign itself that does not survive.
- **Win rates straddle break-even without clearing it.** Break-even at
  2.5%/1.75% is 41.2%. Three windows sit below it (34.6, 32.0, 38.1) and the
  other three barely above (42.3, 45.8, 45.6) — and 2002 manages 42.3% *with*
  −0.139R expectancy, i.e. above the nominal break-even win rate and still
  losing, because realized R per win is well under the 1.43R the payoff
  assumes (scale-out, timeouts and stop-side fills all cut it).
- **Drawdowns are severe everywhere**, −41.6% to −75.9% pooled.

### The limit that governs how much of this counts

**All seven windows are drawdowns by construction** — that is what the task
asked for. This is therefore *not* a measurement of the config's overall
expectancy; it is the config's behaviour in seven bear regimes. The
`STRATEGY_GATES` are bullish-only (`strategy_types.py:246-263`), so a long-
biased system posting negative expectancy through seven bear markets is close
to the expected result, not a surprise finding. **Nothing here says the config
loses money in general, and this file must not be cited for that.** What it
does answer is the question actually pre-registered: the weakness is *not* a
post-2020 artifact — 2022 is one of the two least-bad windows in the table.

Survivorship still runs the same direction in every early window (the universe
is today's 78 tickers), so the pre-2020 numbers are measured on an
already-survived subset and, per the pre-registration, a bad number there is
the *strong* reading. **V21 Step 2** remains the task that audits this.

### One correction to the harness, made before these numbers existed

`post_positive` was `all(...)` over a filtered sequence, and `all([])` is
`True`. Had **both** post-2020 windows come back INSUFFICIENT, the rule would
have satisfied "expectancy > 0 in the post-2020 windows" vacuously and could
have fired a regime-fragile rejection on no post-2020 evidence at all — a
reachable case, since the RSI-only pre-check had both post-2020 windows under
N=30. It now requires at least one sufficient post-2020 window, mirroring the
`bool(suff_pre)` guard already on the pre-2020 side.

**This changed nothing for this run** — `bear_2022` cleared N≥30, so the old
and corrected rules both evaluate `post_positive = True` and both return
`REJECTED = False`. Recorded because the fix landed *before* the grid's numbers
existed, which is the only time a pre-registered rule may be touched.
