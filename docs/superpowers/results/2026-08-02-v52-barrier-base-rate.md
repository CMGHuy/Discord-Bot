# V52 groundwork — the no-skill base rate under V6 Step 3b

**Measured 2026-08-02**, before any selectivity search, so the ladder has a floor
to be judged against rather than an intuition. Covers both the first directive
(2.5% / 2.0%, bar 85%) and the same-day revision (2.5% / **1.75%**, bar **80%**,
staged 60 -> 70 -> 80).

## What was measured

Under Step 3b every trade is a race between a **+2.5% target** and a **hard
percentage stop**. From an *arbitrary* daily bar — no strategy, no filter, no
entry skill — how often does the target land first?

- Substrate: `data/backtest_cache/`, 89–90 tickers with usable OHLC, TRAIN
  1999-01-01..2023-12-31 (daily; hourly cannot serve, see V51 Step 4).
- Entry at bar close, **long only**, resolution swept across the swing ladder
  (2w, 1m, 6w, 2m, 3m, 6m, 9m in trading days).
- 107,069 decided entries per cell (stride-3 subsample); the 30-bar single-cap
  first pass used all 334,290 and agrees to 0.2 pts.
- Daily bars cannot order two barriers touched inside one bar, so a
  pessimistic/optimistic pair is reported. The gap is the intrabar error bar
  V51 Step 4 requires — **3.5% of decided trades**.

## Result 1 — the floor, and what tightening the stop costs

| stop | payoff | break-even | **no-skill WR (pess / opt)** | ExpR at no skill | margin over b/e |
|---|---|---|---|---|---|
| −2.00% | 1.250R | 44.4% | **46.6% / 50.2%** | +0.049R | +2.2 pts |
| **−1.75%** | **1.4286R** | **41.2%** | **43.4% / 47.4%** | **+0.054R** | +2.2 pts |

Two things fall out, and they matter for the revision:

1. **Tightening 2.00% -> 1.75% costs 3.2 points of win rate** (46.6% -> 43.4%).
   The bar moved down 5 points (85 -> 80) but the floor moved down 3.2, so the
   revision's real gain in reachability is **about 1.8 points, not 5.**
2. **The margin over break-even is +2.2 pts at both stops** and expectancy is
   near-identical (+0.049R vs +0.054R). The stop choice is close to a wash for
   profitability; it trades win rate against payoff almost exactly evenly. It is
   *not* a wash for the win-rate constraint, which is the binding one here.

## Result 2 — holding period: this is swing, and the barriers don't care

| horizon | 2w | 1m | 6w | 2m | 3m | 6m | 9m |
|---|---|---|---|---|---|---|---|
| WR @ −1.75% | 42.8% | 43.3% | 43.4% | 43.4% | 43.4% | 43.4% | 43.4% |
| timeouts | 4.3% | 0.7% | 0.3% | 0.1% | 0.1% | 0.0% | 0.0% |

**The no-skill rate is flat from 1m to 9m, and 99.3% of entries resolve inside
one month.** Barrier distance sets the holding period, not the horizon label — a
9m-horizon trade with a 2.5% target is not a 9-month trade. This is the same
mechanism that produced the live book's ~1.2h median winning hold under 0.35R
targets, only less extreme.

**Consequence for the swing framing:** TP1 at 2.5% resolves fast on every
horizon, so the swing character has to come from the **uncapped runner** (V51
Step 2), not from TP1. A short median hold is not evidence the system is
day-trading; it is evidence TP1 is near. Any "this is swing-like" claim must be
evidenced by *runner* holds.

## Result 3 — what the 80% bar requires

The ladder spans **+16.6 pts (60%), +26.6 (70%), +36.6 (80%)** above the 43.4%
floor. Reaching 80% means a screen whose picks hit **1.84x the no-skill rate.**

Set against what this repo has demonstrated: **G100's permutation test put all
eleven strategies at p >= 0.05** (0.346–1.0), and
`2026-07-gate-decision.md:182-190` records "Config changes applied: none." No tier
cut here has demonstrated *any* edge surviving a permutation test.

Sample size is not the binding problem — 107k+ candidates means the N=29 needed
to prove 80% (at 95% observed) is a tiny top slice. A screen that selective is
findable; one that is selective *and* genuinely predictive rather than curve-fit
is what no measurement here supports. At that cut a permutation test is mandatory
before belief, which is why V52 Steps 3–4 require one.

**Pre-registered per V6 Step 4: Stage 1 (60%) is expected to clear, Stage 2 (70%)
is plausible, Stage 3 (80%) is not expected to clear at provable N.**

## The loss cap is a large win regardless of which rung is reached

| | old economics | **new (2.5% / 1.75%)** |
|---|---|---|
| payoff ratio | 0.58 | **1.4286** |
| break-even WR | 63.2% | **41.2%** |
| actual / no-skill WR | 55.6% live | 43.4% at random |
| margin | **−7.6 pts (loses money)** | **+2.2 pts (makes money)** |

The live book fails because it banks ~0.35R and risks 1R by construction. Capping
loss at 1.75% while letting winners run past 2.5% moves break-even *below* the
no-skill rate — **a coin flip becomes marginally profitable (+0.054R), where the
current system must be 7.6 points better than it is just to stop losing.**

Timeouts also collapse from the 22–29% "dead" share the V17 grid measures under
ATR stops to **0.7% at one month**: the tight cap resolves trades fast, so capital
turns over instead of sitting in scratches.

**Adopt the cap on its own merits, independent of which rung the ladder reaches.**
It repairs the structural defect; the 80% bar is a separate bet on an edge no
measurement in this repository supports.

> ### Correction 2026-08-02 (V51 Step 2): the table above assumes no scale-out
>
> The "+2.2 pts / makes money" row is right for a book that exits a win entirely
> at TP1. **Production does not.** `TP1_FRACTION = 0.5` is frozen by spec §5, so
> half the position exits at 2.5% and half becomes a trailing runner. A win
> therefore realises `0.5 × 1.4286 + 0.5 × r_runner`, and break-even moves with
> the runner:
>
> | runner outcome | blended R per win | break-even WR | vs 43.4% no-skill |
> |---|---|---|---|
> | stopped at breakeven (`r=0`) | 0.714R | **58.3%** | **−14.9 pts, loses** |
> | matches TP1 (`r=1.43`) | 1.4286R | **41.2%** | +2.2 pts, makes money |
> | rides to 3R | 2.214R | **31.1%** | +12.3 pts |
>
> **That straddles the no-skill rate**, so "a coin flip is now profitable" is
> true only without scale-out. Under production settings it needs runners
> averaging ≳1.43R, which is unmeasured. The caveat list below flagged this;
> V51 Step 2 quantified it. **V52 Step 1 must report the runner-leg R
> distribution as a first-class output** — a blended ExpR cannot tell these
> three worlds apart, and they disagree about whether the system makes money.

## Caveats, stated rather than buried

- **Longs only.** Shorts are not measured and nothing here claims symmetry.
- Entry at bar close from *every* bar (stride-3) — the unconditional base rate,
  which is the point, but real strategies enter at specific structures.
- Ignores scale-out: real exits bank half at TP1, so realised R differs from the
  clean 1.4286R the economics table assumes.
- Daily resolution — the 3.5% ambiguous share is the honest error bar, and it is
  why V51 Step 4 wants the hourly overlap as a fidelity check.
- Long-only drift over 1999–2023 is doing the +2.2 pt work; it is a property of
  the window, not a demonstrated edge.

## Reproduce

`scratchpad/barrier_baserate.py` (single 30-bar cap, all entries) and
`scratchpad/barrier_swing.py` (horizon ladder, both stops), session 9c9ca604.
Pure measurement over the daily cache; no plan-engine dependency, so unaffected
by V51's changes.
