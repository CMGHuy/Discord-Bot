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

Grid completed **2026-08-05 10:03 UTC**: 67 tickers × 10 horizons × 11
strategies, `--gates off`, one pass, every slice below taken off it. Raw
output: `2026-08-05-v21-direction-survivorship.json`.

Headline, stated before the tables: **five of the seven gated strategies FAIL
Test A** — their bullish-only premise is contradicted in the drawdowns. **Test
B did not fire**, and per the pre-registered asymmetry that clears nothing.

## Harness verification, as pre-registered

`--strategy RSI --gates on` reproduces `regime_slices.py --strategy RSI`
**exactly** — identical `n_eval`, wins, losses and expectancy in all seven
windows (`y2011` N=10 ExpR +0.758, `bear_2022` N=10 ExpR +0.714, the other
five empty). Run 2026-08-05 after the grid; both JSONs compared field by
field, not eyeballed.

Reproduce (the host `python3` has **no pandas** — these scripts only run
inside the `swing-bot:latest` image):

```bash
docker run --rm -v /root/Discord-Bot:/app -w /app swing-bot:latest \
  python scripts/direction_survivorship.py --gates off \
  --json docs/superpowers/results/2026-08-05-v21-direction-survivorship.json
# parity check:
docker run --rm -v /root/Discord-Bot:/app -w /app swing-bot:latest \
  python scripts/direction_survivorship.py --strategy RSI --gates on --json /tmp/a.json
docker run --rm -v /root/Discord-Bot:/app -w /app swing-bot:latest \
  python scripts/regime_slices.py --strategy RSI --json /tmp/b.json
```

That same run also **demonstrates** the argument the pre-registration could
only assert: with gates ON, RSI's short arm is **N=0 in every one of the seven
windows**. A gated run genuinely cannot compare the two arms, so `--gates off`
was the only way to ask the question.

**Why the N here dwarfs V20's.** V20's dot-com row is N=396 for the whole
system; V21's is 707 long + 552 short. Gates off restores the four horizon
masks as well as the direction masks (`## The gates are run OFF` above). The
two files are not in conflict — they measure different signal sets, and only
V21's is direction-complete.

## Step 1 — long vs short expectancy per regime

| Regime | Window | N long | Win% | ExpR long | N short | Win% | ExpR short | long − short |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Dot-com bust | 2000-03-10..2001-12-31 | 707 | 31.1 | −0.208 | 552 | 38.9 | +0.080 | **−0.288** |
| 2002 bear | 2002-01-01..2002-10-09 | 636 | 40.6 | −0.078 | 920 | 37.5 | −0.035 | **−0.043** |
| GFC | 2007-10-09..2009-03-09 | 1115 | 39.1 | −0.108 | 1546 | 42.8 | +0.075 | **−0.183** |
| 2011 | 2011-05-02..2011-10-03 | 602 | 33.4 | −0.222 | 47 | 59.6 | +0.900 | **−1.123** |
| 2015-16 | 2015-05-21..2016-02-11 | 1190 | 39.1 | −0.027 | 572 | 33.2 | −0.138 | **+0.110** |
| COVID crash | 2020-02-19..2020-03-23 | 7 | 0.0 | −0.875 | 18 | 33.3 | +2.484 | *INSUFFICIENT* |
| 2022 bear | 2022-01-03..2022-10-12 | 392 | 34.4 | −0.230 | 977 | 52.1 | +0.320 | **−0.550** |
| *full TRAIN (reference)* | 1999-01-01..2023-12-31 | 37395 | 46.3 | **+0.196** | 10860 | 39.1 | **−0.041** | **+0.237** |

**The long arm is negative in all seven windows. The short arm beats it in
five of the six that are sufficient.** The single exception, 2015-16 (+0.110),
is a window where *both* arms lose. COVID is N=7/18 — under `MIN_N` and
carrying nothing, exactly as V20 found for the same window.

And the reference row is the whole finding in one line: pooled over all of
TRAIN the long side wins by **+0.237R**, and inside the drawdowns it loses.
`STRATEGY_GATES` was fitted 2020-2023 and encodes the TRAIN-wide sign as if it
were universal. The module's own comment — "still carrying a bull-heavy 4-year
fit" — is confirmed, not refuted, and it understates the case: the fit is
bull-heavy against **25** years, not four.

## Step 2 / Test A — per gated strategy, seven drawdowns pooled

| Strategy | Gated | N long | ExpR long | N short | ExpR short | long − short | Verdict |
|---|:-:|---:|---:|---:|---:|---:|---|
| MA Ribbon | **✓** | 212 | −0.310 | 146 | +0.834 | −1.145 | **FAILS** |
| Fibonacci | **✓** | 218 | −0.237 | 276 | +0.369 | −0.606 | **FAILS** |
| VWAP | **✓** | 238 | −0.172 | 209 | +0.094 | −0.266 | **FAILS** |
| MACD | **✓** | 582 | −0.150 | 776 | +0.116 | −0.266 | **FAILS** |
| Volume Profile | **✓** | 1502 | −0.142 | 1197 | +0.056 | −0.198 | **FAILS** |
| Support/Resistance | **✓** | 844 | −0.054 | 1191 | −0.068 | +0.014 | SURVIVES |
| RSI | **✓** | 20 | +0.736 | 10 | +0.714 | +0.022 | *INSUFFICIENT* |
| Break & Retest | — | 168 | −0.338 | 61 | +0.505 | −0.843 | FAILS |
| EMA Crossover | — | 30 | −0.370 | 31 | +0.212 | −0.583 | FAILS |
| Elliott Wave | — | 40 | −0.483 | 113 | +0.042 | −0.525 | FAILS |
| RSI Divergence | — | 795 | +0.007 | 622 | +0.089 | −0.082 | FAILS |

**The rule, applied mechanically: 5 FAIL, 1 SURVIVES, 1 INSUFFICIENT.**
Fibonacci, MA Ribbon, MACD, VWAP and Volume Profile have their premise
contradicted in the regimes where a bullish-only mask is most exposed, and
per the pre-registration **must be re-derived**. Every one of the five has
both arms over N≥30, and the margins (−0.198R to −1.145R) are not marginal —
four of the five exceed V51's +0.318R daily-bar bias in size, and the bias
would have to be strongly *anti*-symmetric by direction to manufacture a sign
flip this large.

Two verdicts that must not be over-read:

- **Support/Resistance "SURVIVES" on +0.014R, and both arms are negative.**
  That margin is ~20× smaller than V51's measured bias and well inside noise.
  The correct reading is "not distinguishable", not "vindicated" — the rule
  says SURVIVES because it was written to read the sign of the difference and
  it must be applied as written, but nothing about this strategy's gate is
  established by it. It loses on both sides.
- **RSI is INSUFFICIENT at N=20/10** — the least-firing gate in the
  drawdowns. Its gate comment advertises `N=608 WR=85.2 ExpR=+0.140` from the
  TRAIN fit; across seven bear markets it produces twenty long trades. The
  100% win rate in both arms is two 10-trade clusters (`y2011`, `bear_2022`)
  and is not a result.

The four ungated strategies are shown for completeness and no rule reads them.
That all four also fail is consistent with the Step 1 picture being a
system-wide regime effect rather than seven separate strategy defects.

## Test B — is the long-side edge a survivorship artifact?

**B2 (rule-bearing, full-history subsample, 40 tickers, full TRAIN):**

| Tercile | N long | Win% | Wilson LB | ExpR long | N short | ExpR short |
|---|---:|---:|---:|---:|---:|---:|
| top | 10024 | 47.4 | 46.4 | **+0.267** | 1952 | −0.019 |
| middle | 11511 | 45.4 | 44.5 | **+0.147** | 2924 | −0.028 |
| bottom | 9844 | 45.9 | 44.9 | **+0.160** | 4489 | −0.095 |
| *excluded from B2* | 6016 | 47.0 | 45.7 | +0.239 | 1495 | +0.077 |

**B1 (all 67, confounded by history length, reported so the confound is
visible):** top +0.280 (N=9594), middle +0.174 (N=17089), bottom +0.159
(N=10712).

> **ARTIFACT = false.** The rule required bottom-tercile long ExpR ≤ 0 while
> top > 0. Bottom is **+0.160**, comfortably positive at N=9844. The rule does
> not fire.

**Read the asymmetry before citing this.** Per the pre-registration — and this
is the paragraph that governs the whole file — *Test B firing CONFIRMS the
artifact; Test B not firing CANNOT CLEAR it.* Every ticker in this universe
survived to be watchlisted in 2025-2026. A flat long edge across terciles is
equally consistent with "the whole survivor sample is lifted together", and
nothing on disk can separate those. **This result does not license the claim
that the gates are survivorship-clean.**

What is visible is a **gradient in the direction the bias predicts**: the top
tercile's long edge (+0.267R) is ~67% larger than the bottom's (+0.160R), and
B1 shows the same ordering (+0.280 vs +0.159). Non-monotonic in the middle
(B2 middle sits *below* bottom), so it is a top-tercile effect rather than a
clean ranking — suggestive, and short of the pre-registered bar by design.

## Test C — controls (descriptive; no rule reads this)

- **Survivorship-free control: empty, as pre-registered.** The only asset
  class present is `equity` (N=37395 long / 10860 short). `GC=F` and `SI=F`
  were dropped by the liquidity screen before the run — the `=F` contract-count
  units mismatch documented above, not genuine illiquidity. The one probe that
  could have broken the one-directional limitation had **zero members before
  the grid started**, and it is recorded as empty rather than repaired.
- **Listing cohort:** `late_lister` long +0.275 / short **+0.132** (N=7616 /
  1902) vs `listed_at_cache_open` long +0.177 / short −0.076 (N=29779 / 8958).
  Late listers are the tickers whose TRAIN history is mostly 2021-2023, and
  both arms are positive there — consistent with a regime reading rather than
  a 24-year one, which is precisely why B2 re-ranks inside the full-history
  subsample.

## What this licenses

**Nothing is adopted and nothing is cleared.** V21 is an audit; per its own
pre-registration a non-failure clears nothing, and Test B's non-firing is the
weakest possible form of non-failure.

One obligation is created, by the rule as written:

> **Fibonacci, MA Ribbon, MACD, VWAP and Volume Profile must have their
> direction gates re-derived.** Their bullish-only masks are contradicted in
> the drawdowns at N≥30 per arm, with margins mostly larger than the known
> daily-bar bias.

Scoping notes for whoever takes that on, so it is not mis-sized:

- **The gates are not simply backwards.** Long beats short by +0.237R across
  full TRAIN and loses in the drawdowns. A re-derivation that flips the masks
  to bearish-only would fit the seven bear windows and break everything else.
  What the evidence supports is that **a static direction mask is the wrong
  shape**, not that its sign is wrong.
- **Horizon masks were not adjudicated here** (`## The gates are run OFF`).
  Gates-off restored them, so they are present in every number above and
  separately measured in none.
- **Direction-symmetry of V51's bias is still an assumption.** The hourly run
  was never sliced by direction. A re-derivation that reads *levels* rather
  than differences inherits that unmeasured assumption; this file's rules
  read differences specifically to avoid it.
- **Everything above is TRAIN.** No validation budget was spent, and none
  should be spent on a re-derivation until it has a candidate worth testing.
