# V16 — Full-history baseline (plan v8, Phase V4)

**Run date:** 2026-08-02
**Command:** `python scripts/run_backtest_range.py --from 1999-01-01 --to 2023-12-31`
**Params:** current frozen config, no overrides. Exit model **v1** (the script
default), frictions **on**, TP2 **levels**.
**JSON:** `docs/superpowers/results/2026-08-02-v16-full-history.json`

## What this run is for

V16 establishes what today's config does across the full available history
rather than the bull-heavy 2020–2023 window that produced it. The plan's own
expectation is on the record: *"Expect it to look far worse than the 2020–2023
numbers; that is the point."* This file is written to be read against that
expectation, so a bad number here is a result, not a failure.

## Read this before quoting the window as "25 years"

Measured directly from `data/backtest_cache/` on the run date (first data row of
each of the 94 cached CSVs), not inherited from an earlier note:

| | |
|---|---|
| Tickers cached | 94 |
| Earliest bar anywhere | **2000-01-03** |
| Median ticker's first bar | **2009-11-18** |
| Latest first bar | 2025-03-28 |
| Start before 2000-01-01 | **0 / 94** |
| Start before 2005-01-01 | 45 / 94 |
| Start before 2010-01-01 | 48 / 94 |
| Start before 2015-01-01 | 53 / 94 |

So `--from 1999-01-01` buys nothing before 2000, the run is **~24 years at best
and ~14 for the median name**, and the first decade is carried by ~45 tickers
that are in the cache *because they still exist today*. That is survivorship
bias in the part of the window doing the most work to make this a "full history"
test. Treat pre-2010 sub-results as indicative, not decisive, and do not report
per-year numbers from the early window without the ticker count beside them.

Note also the 45 → 48 step between 2005 and 2010: almost nothing in this
universe *starts* in that window, so the early cohort is close to constant and
then jumps. Regime slices (V20) should cut on that boundary rather than on
round years.

## Exit-model caveat

The plan's V16 line is the bare command, which defaults to **exit model v1**.
Production runs the v2 intraday manager (`INTRADAY_MANAGER_V2=true`,
`PLAN_ENGINE_V2` on), so this baseline is *not* a like-for-like model of the
live system's exits. It is the correct baseline for comparing against the
existing v1-era numbers, which is what "what today's config does across 25
years" needs in order to mean anything. A v2 + `--scale-out` companion run is
the honest complement and belongs with V17's grid, where the exit parameters
are actually being chosen.

## Target-floor caveat (V48)

`TARGET_FLOOR_ENABLED=true` and `MIN_TARGET_PCT=2.5` are in force (config
default; the latter pinned explicitly in the deployed `.env` on 2026-08-02).
V10's standing note applies: **no post-floor result is comparable to a
pre-floor one.** Every number below is a post-floor number. The floor makes
small wins unreachable by construction, so a lower win rate and a higher
timeout share are the *designed* behaviour here, not a regression — V11's
reachability screen exists to bound exactly that trade.

## Universe actually evaluated

78 watchlist tickers attempted; **10 excluded, 68 evaluated**:

- **Illiquid (E12), 2:** `GC=F` ($3.1M avg dollar vol), `SI=F` ($0.1M) — both
  under the $20M floor. Note these are the same two metals whose *hourly*
  archive V43 was protecting; they are liquid enough to hold history and not
  liquid enough to trade in this universe.
- **Bad data (E16), 8:** `ASTS`, `BKNG`, `HIMS`, `QBTS` (frozen feed, >5
  identical consecutive closes); `CRWV`, `HOOD`, `QBTS`, `SHOP`, `SOFI` (>40%
  bar with no volume spike — bad split adjustment).

Note the report's `Excl%` column is **not** a ticker-exclusion rate, despite the
name: `run_backtest_range.py:53` defines `excluded_share` as
`(scratches + timeouts) / closed` — the share of *closed trades* that resolved
as neither a win nor a loss. It is the same quantity as the last column of the
table below, and it is the criterion V6's gate calls "scratches + timeouts
<= 50% of closed". At 23–36% every strategy is comfortably inside that bar,
and the level is expected under the floor: V10's own note predicts timeouts
rise once small wins are unreachable by construction. The column name is
misleading enough to have caused one misreading already while writing this
file; renaming it is folded into V49.

## Headline

**Summed N 14,951 across 11 strategies; N-weighted expectancy +0.0206 R.**

The plan predicted this would look far worse than 2020–2023, and it does: the
system is approximately **flat after frictions across ~24 years**. Seven of
eleven strategies sit between +0.000 and +0.044 R — indistinguishable from zero
for practical purposes — and the one clearly positive number does not survive
scrutiny (below).

| Strategy | N | WR | Wilson LB | ExpR | MaxDD | scr+TO / closed |
|---|---:|---:|---:|---:|---:|---:|
| RSI | 122 | 80.3% | 72.4% | +0.180 | −9.9% | 24.7% |
| Elliott Wave | 434 | 78.6% | 74.5% | +0.006 | −11.4% | 31.1% |
| Support/Resistance | 1386 | 77.8% | 75.6% | **+0.000** | −39.9% | 36.2% |
| Fibonacci | 1133 | 74.8% | 72.2% | +0.044 | −20.4% | 33.3% |
| Volume Profile | 409 | 69.9% | 65.3% | +0.057 | −12.7% | 30.6% |
| MACD | 763 | 68.3% | 64.9% | +0.008 | −18.9% | 31.2% |
| RSI Divergence | 6922 | 67.4% | 66.3% | +0.012 | **−97.7%** | 27.7% |
| VWAP | 692 | 67.1% | 63.5% | +0.026 | −23.5% | 31.4% |
| MA Ribbon | 1291 | 66.8% | 64.2% | +0.039 | −21.0% | 28.6% |
| Break & Retest | 1581 | 66.4% | 64.0% | +0.036 | −36.0% | 31.4% |
| EMA Crossover | 218 | 65.1% | 58.6% | −0.001 | −15.1% | 22.7% |

`RSI Divergence`'s **−97.7% max drawdown** on the largest sample in the run is
the single most alarming cell in the table and should be treated as a
disqualifier pending V20's regime slices, not as a tail curiosity.

## Two defects in how this run scores itself

**1. The script's PASS column tests a gate V6 voided.**
`run_backtest_range.py:84,142,345` still computes and prints
`pass: WR>=80, ExpR>0, N>=min_n, excl<=50%`. V6 Step 3 explicitly retired
`win_rate >= 80` ("void under a 2.5% floor") and pre-registered a replacement.
The printed report therefore says **RSI PASS, everything else FAIL**, which is
not the plan's rule. Re-scored against V6's actual pre-registered gate
(`expectancy_r > 0`, `scratches + timeouts <= 50% of closed`, objective =
maximise WR), **10 of 11 pass and only EMA Crossover fails** — on expectancy,
by 0.001R. Neither scoring is informative on its own; the gate needs
reconciling in the script before V17 quotes it. Logged as **V49**.

**2. Aggregate N double-counts signals reused across horizons.**
Strategy-level N is the *sum* over ten horizons, which is honest only when the
entries actually differ per horizon. **Five of eleven strategies reuse
signals.** Measured over the full universe by V49's instrumentation, comparing
distinct `(entry_date, entry, direction)` signatures against the summed count:

| Strategy | horizons | distinct signals | overcount | reported N → independent | Wilson LB reported → real |
|---|---:|---:|---:|---|---|
| RSI | 10 | 17 | **9.5×** | 122 → **~13** | 72.4% → **49.7%** |
| RSI Divergence | 10 | 983 | **9.7×** | 6922 → ~711 | 66.3% → 63.8% |
| Support/Resistance | 2 | 1161 | 1.9× | 1386 → ~740 | 75.6% → 74.7% |
| MACD | 5 | 626 | 1.8× | 763 → ~431 | 64.9% → 63.7% |
| MA Ribbon | 10 | 1105 | 1.6× | 1291 → ~789 | 64.2% → 63.4% |

Two distinct patterns, and they need reading differently. RSI and RSI
Divergence are **near-total reuse** (~10×) — the horizon is essentially ignored,
so the summed N is a tenfold overstatement. The other three are **partial**
(1.6–1.9×) — entries genuinely differ per horizon but overlap substantially, so
their bounds move only slightly and no conclusion changes.

An earlier, narrower probe in this file's first draft (3 tickers, 2m vs 9m,
exact set equality) found only the two ~10× cases and reported the other nine as
horizon-specific. That was too strict on both axes: exact equality misses
partial reuse, and it also **false-negatived RSI itself**, because a 9m hold
resolves a few window-edge trades differently from a 2m one. The table above is
the corrected, full-universe measurement.

The consequence for the run's only positive finding is unchanged and decisive:

**RSI's apparent win — the only strategy to clear even the stale gate — rests
on ~13 independent trades counted 9.5 times.** Its honest lower bound is
**49.7%**, not 72.4% — i.e. the data cannot rule out a coin flip. V6 Step 5
already pre-registered the standard that kills it: *"A high-WR config on N=12 is
a hypothesis, not a finding"*, and proving WR > 90% needs N ≥ 59. RSI does not
have the sample to support any claim here.

## Verdict against V6's pre-registered rule

The objective is *maximise win rate* with a **stretch of 90%** and V6 Step 4's
honesty clause: if the frontier tops out below 90%, **record the achieved
number and stop**.

**The frontier tops out at ~78% headline WR — best defensible lower bound
74.7% (Support/Resistance, on ~740 independent trades) — at essentially zero
expectancy (+0.000R).** Nothing in this universe approaches 90% at a 2.5%
target floor over 24 years. Recording that and stopping, per Step 4 — no cohort
re-cutting, no floor relaxation, no dropping losers from the denominator.

The uncomfortable reading, stated plainly: **high win rate and positive
expectancy are anti-correlated here.** The three highest-WR strategies
(S/R 77.8%, Elliott 78.6%, RSI-ex-artifact) carry expectancy of +0.000 and
+0.006 R, while the better-expectancy names sit in the 66–70% WR band. A
selection rule that maximises WR subject only to `ExpR > 0` will therefore
select for strategies that are indistinguishable from break-even. V17 should
expect its optimum to land on that boundary, and V6's rule may need a minimum
expectancy, not just a positive one — that is a **human-partner decision**, not
one to make inside V17.

## Carried into the next tasks

- **V17:** do not quote the script's PASS column until V49 lands. Grid on the
  V6 rule directly.
- **V18:** fold N must use `n_independent` from the JSON, not summed `n_eval`,
  or RSI clears `N >= 30/fold` on ~3 real setups. Five strategies are affected,
  two of them ~10×.
- **V20:** cut regimes on the 2005/2010 cohort boundary (see coverage above),
  and pull `RSI Divergence`'s −97.7% drawdown apart by regime.
- **V21:** the 10 dropped tickers (2 illiquid, 8 bad-data) belong in the
  survivorship audit — not the `Excl%` column, which measures something else.
- **V22:** the permutation test is the right instrument for a +0.02R edge —
  that is exactly the magnitude that a null shuffle should be able to produce.
