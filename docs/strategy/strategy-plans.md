# Strategy — building the trade plan

Entry, target, stop, the confidence score, what an alert contains, and how trades are monitored and tracked.

Part of the strategy documentation — index at [strategy.md](strategy.md).

## Entry is always today's current price

Unlike a crossover strategy that chases a specific indicator level, this
model reacts to *where price is right now*: entry = current price,
target = the next real support/resistance from here. There's no
pullback/retest logic to wait for — either a qualifying level exists
within reach today, or it doesn't (and no alert fires).

## The target must pay for the risk, or there's no plan

"The next real level" isn't automatically the target — it also has to be
far enough out to be worth the trade. Every plan's target is the *nearest*
real level beyond entry that pays at least `MIN_RISK_REWARD_RATIO` (1.5x
the plan's own stop distance), capped at `MAX_RISK_REWARD_RATIO` (2.5x): a
level sitting farther out than the cap doesn't get skipped, it becomes
target 2 instead, and the plan's actual target 1 is priced at exactly the
cap. Nearest-qualifying, not farthest-qualifying — a closer target inside
the band is reached more often than a distant one, and the band already
guarantees the payoff is worth it.

**When nothing clears the floor, there's no plan for that ticker/horizon —
same as no level existing at all.** This applies to every strategy that
posts a trade plan, not just the confluence scenarios above: a
Fibonacci-sourced plan targets a real retracement or extension of the fib
swing, an Elliott Wave plan targets a real wave-3 projection, a
Support/Resistance plan targets the real rolling structural high/low, and
the strategies with no price structure of their own (EMA Crossover, VWAP,
RSI, MACD, MA Ribbon, Break & Retest, RSI Divergence, Volume Profile) treat
the ticker's own volatility as the structure — but every one of them is
bound by the same real-level-or-nothing rule, never a fallback to a fixed
fraction of risk.

## Minimum stop distance: hard filter, not just a warning

A scenario is dropped entirely (`MIN_STOP_DISTANCE_PCT`, default **2%**)
if its stop sits closer than that to the entry — too exposed to
ordinary daily noise to be worth showing at all, regardless of how good
the target side looks. This is separate from, and on top of, the softer
ATR-based check below.

## Tight-stop warning

Even above that 2% floor, sometimes the nearest level on the opposite
side of the target sits closer than this horizon's own normal
volatility would suggest — a 3-4% stop on a stock that typically swings
8% is still tight relative to its own behavior, even though it clears
the hard minimum. Every qualifying scenario compares its actual stop
distance against this horizon's own ATR-based volatility cushion (the
same `atr_stop_multiple` the horizon settings define) and flags it with
⚠️ **tight stop** if it's noticeably tighter than that. The stop itself
is never silently widened — that would misrepresent the real technical
level — it's just flagged honestly so you know the reward:risk number
alone might be optimistic about how often this particular stop survives
normal noise.

## Quality over quantity, for real

Neither `MIN_REWARD_PCT` nor `MIN_STOP_DISTANCE_PCT` gets loosened if a
scan comes back empty. If there's no real support/resistance level on
the opposite side of a potential target, the bot does **not** invent an
estimated one just to produce a trade plan — that scenario simply isn't
built. Finding zero qualifying setups on a given scan, or on a given
ticker entirely, is a completely normal and expected outcome, not a
failure to fix.

## Live monitoring: near-close warnings and closed-trade results

Every scan (default every `SCAN_INTERVAL_MINUTES` = **5** minutes) does
two jobs in the same pass, at no extra API cost:

1. **Looks for new qualifying scenarios** (the normal alert flow).
2. **Checks every currently open trade** against today's price. If price
   has moved within `NEAR_CLOSE_THRESHOLD_PCT` (default 2%) of either the
   stop-loss or the take-profit, a ⚠️ near-close warning posts to
   `CLOSED_TRADES_CHANNEL_ID` (or the main channel if that's not set).

When a trade's stop-loss or take-profit actually gets hit, a ✅ WIN / ❌
LOSS result posts to the same channel — separate from the main alert
channel so results don't get lost among new signals.

## Market-wide events, not just this ticker's earnings

`events.py` checks each ticker's own next earnings date; `market_events.py`
separately tracks scheduled events that can move **every** ticker at
once: FOMC rate decisions (from the Fed's own published calendar), the
US jobs report (always the first Friday of the month), and US CPI
releases (approximate, flagged as such). Both are logged for every
trade's holding window (see Logging below); the earnings check also
surfaces directly in the alert if one falls inside the holding window.

## Logging

The bot logs its scanning progress, not just final alerts: per-ticker
fetch steps, the signal funnel (how many ticker/horizon combos were
checked vs. had no qualifying 5%+ move vs. got filtered by confidence or
confirmation), every scenario built (entry/stop/target1/target2, and
whether the stop came back tight), any macro events inside a trade's
holding window, and total scan duration. Default level is INFO; set
`LOG_LEVEL=DEBUG` in `.env` for full confidence-score breakdowns on
every scenario checked.

**This isn't just server-side logging** — `!check`'s live progress
message and its final funnel summary (see above) surface the same
information directly in Discord, so you don't need server/log access to
see what a scan actually did.

## Confidence is built from real confluence, and it's honest

Confidence is scored 1-5 directly from the *quality of the level*, not
generic technical noise:
- **Target level confluence** (0-35 pts) — how many independent methods
  (EMA, VWAP, Fibonacci, rolling structure, pivots, Bollinger Bands,
  Donchian Channel, floor pivots) agree on the target.
- **Stop level confluence** (0-15 pts) — same idea for the invalidation
  level on the other side.
- **Target distance quality** (0-15 pts) — how many multiples of
  `MIN_REWARD_PCT` the actual target distance is.
- **Market regime alignment** (0-15 pts) — does the scenario's direction
  agree with the broader market trend?
- **Volatility squeeze + volume breakout** (0-20 pts) — was this ticker
  recently in a Bollinger Band squeeze, and did it just break out of it
  on 1.5x+ average volume in this scenario's own direction? See "Three
  extra filters" above.

**Honesty gate:** Level 5 needs 3+ independent methods agreeing on the
target, Level 4 needs 2+. A scenario can't reach "high confidence" on
distance and regime alignment alone if only one method actually
confirms the level — that's a much weaker claim than "everything lines
up", so it gets capped down instead of rounded up. This is *emergent*
arithmetic, not a literal cap check in the code: the base level is
`min(5, method count)`, and the quality/expectancy adjustments below can
each move it at most ±1, so one confirming method can reach at best
Level 3 (1 base + 2) and two methods at best Level 4 -- the numbers above
are the accurate, worked-out consequence of that arithmetic, not a rule
written down anywhere as its own check.

A 2026-08 spec (v32) explored replacing this with one merged score --
folding in relative strength, multi-timeframe alignment and market
breadth as real gating inputs, plus a genuine explicit honesty cap and a
6th ("Elite") level -- but its one-shot validation run showed a small
win-rate *regression* against the scoring described here, not an
improvement, so it never shipped (stays off by default; this section
remains the accurate, live description).

Confidence is also **visually highlighted**: each alert's embed color is
a red-to-green gradient by confidence level (🔴 Lv1 → 🟠 Lv2 → 🟡 Lv3 →
🟢 Lv4 → 🟢 Lv5), plus a matching colored dot next to the confidence
text, so you can tell strength of signal at a glance.

## What's in every alert

- **Swing type** (horizon) and confidence, color-highlighted red (Lv1) →
  green (Lv5), with the full factor breakdown available.
- **One "🎯 Trade plan" field**: entry (today's current price), stop
  (with the method(s) that placed it, flagged ⚠️ tight if it's closer
  than this horizon's normal ATR cushion), target 1 (with its % distance
  and confirming method(s)), target 2 if a second level exists further
  out, and the reward:risk ratio to target 1.
- **A "🔀 If it gets there" field**: what happens if target 1 continues
  (next stop is target 2) vs. reverses (pulls back toward the stop-loss
  level on the other side) — both branches, not just the hoped-for one.
- **A chart image** — candlestick chart zoomed to the **last ~2 weeks**
  of trading (not the horizon's full lookback) so the current price
  action is big and legible, with entry/stop/target1/target2 lines,
  shaded zones for each, and a % stats box (no euro amounts). Two arrows
  are drawn directly from target 1: one continuing on to target 2 (if
  there is one), one reversing back to the stop — the same two branches
  described in the text, shown where they'd actually happen. Labels are
  spread out with a small leader line back to the real price whenever
  levels sit close enough together that they'd otherwise overlap and
  become unreadable.
- **A short explanation** — which level is being targeted, how many
  independent methods confirm it, both branch outcomes in prose, a tight-
  stop warning if relevant, and an earnings-date heads up if one falls in
  the holding window.

## Tracking trades: open, closed, and unrealized P/L

- **`!trades`** / **`!trade ID`** — list or inspect logged trades
  (`!trade ID` also shows target 2 if the original scenario had one).
- **`!trade delete ID`** — remove a single trade record.
- **`!trades clear`** — wipe every trade record.
- **`!pnl`** — current **unrealized % profit/loss** for every open
  trade, fetched against today's live price, and how far price is from
  the stop-loss/target.
- **`!performance`** — realized win rate per confidence level, once
  trades have actually closed.
- **Closed-trade notifications** — when a trade's stop-loss or target is
  hit, a WIN/LOSS result posts automatically to `CLOSED_TRADES_CHANNEL_ID`.
