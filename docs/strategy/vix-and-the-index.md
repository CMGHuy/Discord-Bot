# VIX and the index: what volatility says about SPY / QQQ

Knowledge-base note (2026-11-07). How the VIX relates to SPY / the S&P 500
and QQQ, what it can and cannot tell you about a coming big move or its
direction, and how that maps onto this bot. **The figures below are from
published research and general market practice, not measured on this repo's
data.** Any rule taken from here is an idea, not an edge, until it passes the
Stage −2 screen (`docs/claude/backtest-methodology.md` § Funnel stages).

## 1. What VIX is

- The market's expected 30-day volatility of the S&P 500, implied from SPX
  option prices and quoted as an annualised percentage.
- QQQ / Nasdaq-100 has its own index, **VXN**, usually 3–6 points above VIX
  because tech is higher beta. **VVIX** is the volatility of VIX itself.
- **VIX3M** (formerly VXV) is the same measure over 3 months; the ratio
  VIX ÷ VIX3M describes the term structure (the "curve").

## 2. VIX predicts size, not direction

Convert VIX into an expected SPY move (one standard deviation):

| Horizon | Rule of thumb | VIX 16 | VIX 20 | VIX 32 |
|---|---|---|---|---|
| One day | VIX ÷ 16 (√252) | ±1.0 % | ±1.25 % | ±2.0 % |
| One month | VIX ÷ 3.5 (√12) | ±4.6 % | ±5.8 % | ±9.2 % |

This is the cleanest answer to "when will the market make a big move": the
bigger the VIX, the bigger the move the options market is pricing. It is
silent on direction.

## 3. The SPY–VIX relationship

- **Inverse and asymmetric.** Daily changes correlate around −0.7 to −0.8.
  Sell-offs lift VIX sharply (put demand, leverage effect); rallies bleed it
  slowly — "stairs up, elevator down".
- **Volatility clusters.** High VIX tends to stay high and low VIX low, so a
  level is a regime description more than a timing signal.
- **Mean reversion at extremes.** Spikes do not last; the decay after a spike
  is where most of VIX's directional information lives.

## 4. Signals with a track record

| Signal | Reading | Implication |
|---|---|---|
| **Term structure VIX ÷ VIX3M** | < 0.9 normal contango; > 1.0 inverted = acute stress; falling back under 1 often the all-clear | The most robust regime filter: no new longs while inverted |
| **VIX stretch then reversal** | VIX closes well above its 10-day average (+20–30 %), then closes down | Short-term (1–5 day) bullish for SPY/QQQ — capitulation bounce |
| **High level** (VIX > 30) | Fear | Forward 1–3 month SPX returns historically above average, path violent |
| **Low level + low realised vol** (VIX < 13) | Complacency / compression | Expansion likely, **direction unknown**; poor at timing tops, can persist for months |
| **Divergence, bullish** | SPY lower low, VIX lower high | Selling exhaustion |
| **Divergence, bearish** | SPY new high while VIX rises | Hedging demand into strength; warning |
| **VVIX** > ~110–120 | Demand for crash protection | Often precedes a VIX spike |
| **Implied < realised** (VIX below SPY's realised vol) | Options cheap vs actual movement | Stress regime |
| **VXN − VIX spread widening** | Tech-specific fear | QQQ / semis weaker than the broad index |

Rough level bands traders use: < 15 calm grind, 15–20 normal, 20–30
elevated, > 30 fear.

## 5. When the relationship breaks

- **SPY and VIX up together:** call buying in melt-ups (2017, 2021) or
  hedging ahead of an event; often precedes a vol event (Feb 2018).
- **Event premium and crush:** VIX inflates into FOMC / CPI / big earnings
  and collapses after, whatever the direction. Not a direction signal.
- **VIX expiration (Wednesdays) and monthly OPEX** distort readings.
- **"VIX low, so sell"** has historically lost money; low VIX is not a top.

## 6. What this bot already uses

| Use | Where |
|---|---|
| `^VIX` on the market tape (with `^GSPC`, `^NDX`, `^DJI`) | `swingbot/core/marketdata/shared/tape.py` (`TAPE_FIXED`) |
| Intraday VIX day change speeds SHOCK entry; VIX off its session high gates RECOVERY | v209 market-shock detector (`docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md`) |
| `^VIX` daily 2009–2019 as a screen context symbol | v209 plan |

**Not used yet:** daily VIX level regimes, the VIX ÷ VIX3M curve, VVIX, VXN,
VIX-stretch reversals, expected-move sizing.

## 7. Candidate screens (ranked by likely ExpR effect)

Each needs a `SCREEN-PASS` ledger row before a spec.

1. **Curve gate on longs** — no new longs while VIX ÷ VIX3M > 1.0, resume
   below ~0.95. Daily complement to v209's intraday detector; needs `^VIX3M`
   daily history (Yahoo, from about 2007). *Partner picked this first,
   2026-11-07.*
2. **VIX-stretch reversal long trigger** on SPY/QQQ and high-beta names — a
   new entry (expectancy and volume).
3. **Expected-move stops** — compare stop distance with VIX ÷ 16 × price.
   Caution: v191 ATR-band stops were NO-LIFT, so this needs a distinct
   argument.
4. **Direction-neutral "big move ahead" notice** — low VIX plus compressed
   realised vol; informational, `Edge: none`.
