# V21 — Direction & survivorship audit (plan v8, Phase V4)

**Status:** pre-registration written 2026-08-05 **before the grid was run** —
everything below the "Result" heading was empty when this file was first
committed. Harness: `scripts/direction_survivorship.py`.

## What this measures

`STRATEGY_GATES` (`swingbot/core/strategy_types.py:250-263`) restricts **seven
of eleven** strategies to `directions=("bullish",)`. Those masks were fitted on
the **2020-2023** TRAIN window — four bull years — and the module's own comment
already flags that they are "still carrying a bull-heavy 4-year fit". V21 asks
the two questions that fit cannot answer about itself:

- **Step 1:** long vs short expectancy **per regime**.
- **Step 2:** does the bullish-only premise survive on a subsample that is
  **not survivor-biased**? If the long-side edge is an artifact of running 25
  years of backtest over a watchlist of today's winners, **say so and
  re-derive the gates.**

**Why V21 is startable when most of Phase V4 is not.** V17 and V52 both
terminated with an **empty adopted set**, which blocks V18/V22/V24 — every one
of those needs a *candidate* config to measure. V21, like V20, interrogates the
**shipped** configuration, so it needs no candidate.

**What a result here licenses: nothing, by itself.** This is an audit. A
failure obliges a re-derivation of the gates (a follow-up task); a
non-failure adopts nothing and clears nothing. See "The one-directional
limitation" below — it is the most important paragraph in this file.

## The gates are run OFF, and that is the point

A bullish-only strategy emits **zero** bearish signals by construction, so a
gated run cannot compare the two arms — the short side would be an empty set,
and "long beats an empty set" is not a measurement. The pre-registered run is
therefore `--gates off`, which patches `entry_filters.STRATEGY_GATES` to `{}`
(the one binding `entries_for` reads; `backtest.py` imports the name but never
uses it — checked 2026-08-05).

This also restores the **horizon** halves of four gates (VWAP, Support/
Resistance, MACD, Volume Profile). Horizon masks are **out of scope** for
V21's decision rules — the rules read direction only. The extra horizons are
present in the sample and are not separately adjudicated here.

## Config under test — production, pinned

Identical to V20's, so the two are comparable:

| Setting | Value |
|---|---|
| `MIN_TARGET_PCT` / `TARGET_FLOOR_ENABLED` | 2.5% / true |
| `MAX_LOSS_PCT` / `MAX_LOSS_CAP_ENABLED` | 1.75% / true |
| Exit model | **v2 + scale-out**, TP2 `levels`, frictions **on** |
| `STRATEGY_GATES` | **OFF** (the object under test) |
| Window | TRAIN `1999-01-01 .. 2023-12-31` + V20's seven regimes |

No validation budget is spent: every window sits inside TRAIN.

## Windows

Step 1 uses **V20's seven regimes, imported from `regime_slices.py` rather
than copied** so the two harnesses cannot drift. Full TRAIN is reported beside
them for reference. All seven are drawdowns by construction — the same caveat
V20 carries applies here, and for this task it is a *feature*: a bullish-only
mask is most exposed exactly where the market fell.

## The three probes, and their decision rules

Sufficiency bar throughout: **N ≥ 30 per arm** (`MIN_N`, imported from V20).
Wilson lower bounds are reported everywhere per V6 Step 5; point estimates are
never read alone.

### Test A — does each gated strategy's bullish-only premise hold in drawdowns?

Per strategy, pooled over all seven windows: long ExpR vs short ExpR.

> **FAILS** if `long ExpR − short ExpR < 0` with both arms at N ≥ 30.
> **SURVIVES** if the difference is ≥ 0 at N ≥ 30. Otherwise **INSUFFICIENT**.

Any gated strategy that FAILS has its premise contradicted in the regimes
where it matters most, and must be re-derived.

### Test B — is the long-side edge a survivorship artifact?

Tickers are ranked by **CAGR of the adjusted close over their own
TRAIN-overlapping history** (the cache is built `auto_adjust=True`, so this is
total return) and cut into **equal-count terciles**. Equal count, not equal
width: the CAGR distribution is heavily right-skewed and equal-width bins put
~70 tickers in one bucket.

**Two arms, and B2 carries the rule.** Found while computing the ranking,
before any backtest ran: raw tercile membership is confounded by **history
length** — the naive top tercile is mostly short-history late listers (CEG 490
bars, PLTR 818, DDOG 1078) whose "TRAIN CAGR" is really a 2021-2023 regime
reading, not a 24-year one.

- **B2 (rule-bearing):** re-rank inside the **full-history subsample only**
  (≥ 5000 TRAIN bars, 40 tickers). Every member spans the same window, so
  tercile varies with eventual performance and nothing else.
- **B1 (reported beside it):** the same cut over all 67 ranked tickers.
  Confounded as above; reported so the confound is visible rather than hidden.

> **Rule, read on B2:** the long-side edge is declared a **survivorship
> artifact** if bottom-tercile long ExpR ≤ 0 while top-tercile long ExpR > 0,
> both at N ≥ 30.

**B2 membership, fixed before the run** (CAGR range in brackets):

| Tercile | n | CAGR range | Members |
|---|---:|---|---|
| top | 13 | +32.50% … +13.40% | AXON NFLX NVDA AAPL ISRG UNH SBUX ADBE AMZN NKE INTU STX ASML |
| middle | 13 | +12.67% … +8.04% | GD WDC SNPS MSFT BA AMD HD CVX PEP ILMN JPM AMAT EBAY |
| bottom | 14 | +7.98% … −2.07% | JNJ GS EA MRVL ORCL WMT IBM QCOM HPQ MU PFE INTC GLW MSTR |

### Test C — controls

- **Survivorship-free control: unavailable, and the reason is recorded rather
  than worked around.** The only two watchlist members that *cannot* be
  survivor-selected — `GC=F` and `SI=F`, a commodity future cannot be delisted
  for performance — are **both dropped by the universe's liquidity screen**
  before any backtest runs: "avg dollar vol $3.1M < $20M floor" for gold,
  $0.1M for silver. That is a **units mismatch, not illiquidity**: yfinance
  reports *contract count* for `=F` symbols and a gold contract is 100 oz, so
  `close × volume` is off by orders of magnitude. Gold futures are among the
  most liquid instruments in existence. **This probe has zero members before
  the run**; it is reported as empty, not repaired here (changing the
  liquidity screen would change the universe of every backtest in the repo).
- **Listing cohort:** `listed_at_cache_open` vs `late_lister`, split at
  2001-01-01. Note the cutoff is 2001, not 1999: TRAIN nominally opens
  1999-01-01 but **the deepest cached series starts 2000-01-03**, so no ticker
  has a 1999 bar and a 2000-01-01 cutoff would classify the entire universe as
  "late". Measured 2026-08-05, before the run.

Test C is **descriptive**. No adoption or rejection rule reads it.

## The one-directional limitation — read this before citing any result

**A genuinely survivorship-free sample cannot be constructed here, by anyone,
with the data on disk.** The universe is the live watchlist: 78 tickers chosen
in 2025-2026, every one of which survived to be chosen. There is no
delisted-security data in the cache, and yfinance does not serve delisted
tickers, so the names that would correct the bias — the ones that went to zero
between 1999 and 2023 — are unobtainable offline.

Test B therefore measures the **gradient** of the bias *within* an
already-truncated sample. That makes its evidence asymmetric, and the
asymmetry is pre-registered so it cannot be quietly dropped later:

> **Test B firing CONFIRMS the artifact. Test B not firing CANNOT CLEAR it.**

A flat long-side edge across terciles is consistent with "not much
winner-dependence *among survivors*" and equally consistent with "the whole
survivor sample is lifted together". Nothing in this task can distinguish
those. Any later citation of a non-firing Test B as evidence the gates are
sound is a misreading of this file.

## Why the rules read differences, not levels

Every absolute ExpR here inherits V51's measured bias: daily bars overstate
expectancy by **+0.318R per trade** (`2026-08-02-v51-hourly-fidelity.md`),
which is larger than any margin this task will produce. A **difference**
between two arms measured on the same bars is far more robust to that bias
than either level, so Tests A and B are written as differences.

**This assumes the bias is roughly direction-symmetric, and that is an
assumption, not a measurement** — the hourly run was never sliced by
direction. Recorded here so a later reader does not mistake it for something
that was checked.

## Harness

`scripts/direction_survivorship.py`. Runs the ticker × horizon × strategy grid
**once** and takes every slice off that single pass — the V50/V20
recomputation trap: `run_backtest` is essentially all of the runtime and is
identical no matter how its trades are later bucketed, so slicing by
re-invoking a range script per bucket would recompute it tens of times.

Everything statistical (`pool`, `pooled_max_dd_pct`, `wilson_lower_bound`,
`window_trades`) is imported from `run_backtest_range`, and `REGIMES`/`MIN_N`
from `regime_slices`, so these numbers cannot drift from the harnesses that
produced V16/V17/V20/V52.

**Verified against the real harness before being trusted**, following V20's
precedent: an RSI-only run with `--gates on` reproduces `regime_slices.py
--strategy RSI` exactly, regime by regime. Recorded under Result.

Universe: 78 watchlist tickers, of which **67** clear the liquidity/data
screens (excluded — illiquid: GC=F, SI=F; bad data: ASTS, BKNG, CRWV, HIMS,
HOOD, QBTS, SHOP, SOFI; no data: SPCX), and **40** have the ≥5000 TRAIN bars
that Test B2 requires.

---

# Result

*(empty at pre-registration time — filled in after the grid finished)*
