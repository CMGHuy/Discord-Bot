# Strategy — finding setups

How levels are found, filtered and merged, and which horizons they are scanned on.

Part of the strategy documentation — index at [strategy.md](strategy.md).

## The core idea: next support/resistance, not indicator crossovers

Given a stock at price **X**, the bot asks two questions every scan:
- What's the **next resistance** above X? Is it at least 5% away? If so,
  that's a **bullish scenario**: X could rally to it.
- What's the **next support** below X? Is it at least 5% away? If so,
  that's a **bearish scenario**: X could pull back to it.

Both can qualify at once — you get both scenarios, not a forced pick.
Once a scenario qualifies, the bot finds the **second** support/resistance
beyond the first one too, and describes what happens in **both**
directions from the first level, not just the hoped-for one:
- **Continues:** breaks through level 1 and keeps going → level 2 is the
  next stop (the stretch target).
- **Reverses:** rejects at level 1 instead → pulls back toward the
  nearest level on the *other* side (which is also this scenario's
  stop-loss/invalidation level).

Every chart shows all four prices — entry, stop, target 1, target 2 —
with labels spaced out so they stay legible even when the actual levels
sit close together.

**There's no euro-based position sizing.** No flat stake, no max-loss
band, no €-per-trade target. The focus is entirely on whether a genuine
setup exists — how much money to put behind it is left to you.

## Levels come from EVERY method at once, not one indicator

A "support" or "resistance" level isn't just one line from one
indicator. Every scan gathers candidate levels from:
- **EMA** (both the fast and slow moving average for the horizon)
- **Rolling VWAP**
- **Fibonacci retracements** (all 5 standard ratios, plus the swing
  high/low that anchors them)
- **Rolling structural support/resistance** (highest high / lowest low
  over the horizon's lookback)
- **Zigzag/Elliott-style pivot highs and lows** (recent swing points)
- **Bollinger Bands** (upper/lower, 20-period, 2 std dev)
- **Donchian Channel** (20-bar highest high / lowest low — the classic
  Turtle Trader breakout channel)
- **Classic floor trader pivot points** (PP/R1/S1/R2/S2, projected off
  the prior session's range)
- **Anchored VWAP** (volume-weighted average price run from a specific
  bar, not a rolling window) — anchored to the bars that actually mean
  something: up to 2 recent swing lows, up to 2 recent swing highs, the
  single highest-volume bar in the lookback (a capitulation/breakout day
  the market remembers), and the 52-week high/low. Each anchor is
  labelled by the event it represents — "Anchored VWAP (swing low)",
  "Anchored VWAP (52w high)", etc. — not by a bar index, so an alert says
  what the level actually is.

Levels from different methods that land close together (within 1.5% of
each other) get merged into one, more-confirmed level — a Fibonacci
61.8% retracement sitting right on top of the 50-day EMA is a much
stronger level than either alone. **Confidence is built directly from
this**: how many independent methods agree on the target is the single
biggest factor in how confident an alert is (see below).

**All anchored-VWAP anchors count as one family.** A ticker can easily
carry 4-6 AVWAP anchors at once (two swing lows, two swing highs, a
volume spike, both 52-week extremes), and several of them landing near
the same price is common, not rare. If each labelled anchor counted as
its own confirming method, confluence would inflate for free — a ticker
with a busy pivot history would look more confirmed than one with a
quiet one, for reasons that have nothing to do with the level itself.
So every "Anchored VWAP (...)" label folds back to the single "AVWAP"
strategy family for confluence-counting purposes: however many anchors
cluster on a level, it contributes at most one method to that level's
count, the same as EMA or Fibonacci contributes one regardless of how
many of their own lines land there.

Anchored VWAP is on by default (`AVWAP_LEVELS_ENABLED`) as of 2026-08,
but — like the Bollinger squeeze breakout above — it only ever adds
candidate levels and feeds confluence/confidence; it gates nothing on
its own. It shipped on a **non-inferiority** basis, not a demonstrated
edge: a pre-registered one-shot VALIDATION run moved pooled win rate by
-0.084pp with heavily overlapping Wilson confidence intervals — measured
to not hurt the win rate, not proven to help it. Full measurement:
`docs/superpowers/plans/implemented/v35-avwap-preregistration.md`.

## Three extra filters for genuine 5%+ move candidates

On top of the level-confluence engine, three additional, purely
mathematical checks (`swingbot/core/market/volatility.py`) target whether a
stock is even *capable* of a fast move right now:

- **Filter 1 — Historical volatility floor** (ticker-level, hard
  filter): annualized historical volatility from daily log returns
  (the same calculation portfolio-analytics tools like Riskfolio-Lib
  report). A low-volatility utility/staples name structurally can't
  produce a fast 5%+ move the way a high-beta name can, so tickers
  below `MIN_ANNUALIZED_VOLATILITY_PCT` (default **35%**) are skipped
  entirely before any scenario is even built for them. Set it to `0` to
  disable this filter.
- **Filter 2 — Bollinger Band squeeze**: band width (upper − lower, as
  % of the middle band) at or near a ~6-month low signals compression/
  indecision that tends to resolve in a sharp move.
- **Filter 3 — Volume realignment**: a genuine breakout out of that
  compression needs volume at least 1.5x the 20-day average, on a day
  that actually closes outside the prior day's bands in the scenario's
  own direction.

Filters 2+3 combine into one "squeeze breakout" confirmation used as an
extra confidence factor (Factor E, see below) and, when it fires, shows
up as its own named confirming method ("Bollinger Squeeze Breakout")
right alongside EMA/VWAP/Fibonacci/etc. — a real, independent technical
confirmation, not just a distance number.

These are implemented natively in pandas/numpy rather than pulling in
`ta-lib` (needs a C library compiled on the host — exactly the kind of
deployment friction a "just deploy this container anywhere" bot should
avoid) or `pandas-ta` (an extra dependency for a handful of formulas
that are a few lines of pandas each). The formulas are the same
standard ones those libraries implement.

## Quality over quantity

Only **Level 4 (High)** and above confidence scenarios are shown as
alerts (`MIN_ALERT_CONFIDENCE_LEVEL`, default 4 -- `config.py:174`, not 3),
with Level 5 (⭐) prioritized. Lower levels are still computed internally,
just not surfaced — quality over quantity.

## Duplicate scenarios get merged

If two horizons on the same ticker/direction produce entry/stop/target
all within `DEDUP_TOLERANCE_PCT` (default 2%) of each other, they're
combined into **one** alert instead of several near-identical ones. The
alert shows the highest-confidence version and lists which other
horizons agree (e.g. "Confirmed by: S/R Confluence (4w), S/R Confluence (3m)").

## `!check` is a live snapshot, not just new alerts

`!check [horizon]` shows **every currently qualifying scenario right
now** — not only freshly-changed ones. Run it any time to see the full
picture of what's live in the market at that moment, filtered to
`MIN_ALERT_CONFIDENCE_LEVEL`+ confidence and deduplicated. The automatic
background scan (every `SCAN_INTERVAL_MINUTES` during the session) still
uses a confirmation debounce to avoid alerting on intraday flicker;
`!check` skips that debounce entirely since it's an on-demand look. A
given ticker+horizon+direction is never logged as more than one open
paper trade at a time — re-running `!check` on an unchanged setup shows
it again without creating a duplicate trade record. `!check` also shows
**live progress** while it runs, with detail beyond just a percentage:
`Scanning (all)… 42% (14/33) — currently: NVDA, 3 qualifying so far`,
then `Scanning done (3 qualifying found) — building alerts… 2/3` while
charts render, then a final funnel summary before the alerts post:
`Scan complete (all) — 33 ticker(s), 165 ticker/horizon combo(s) checked
→ 140 had no 5%+ move, 18 below Lv3 confidence, 4 awaiting confirmation
→ 3 alert(s)`.

## Swing horizons

`swingbot/core/market/strategy_types.py:HORIZONS` is authoritative if this
table ever drifts again -- it did (both the horizon count and the EMA pairs
below were wrong until v32's documentation pass found it independently of
that plan's own scope).

| Horizon | Meaning | EMA pair |
|---|---|---|
| `2w` | ~2 week swing | EMA8 / EMA13 |
| `4w` | ~4 week swing | EMA9 / EMA21 |
| `2m` | ~2 month swing | EMA14 / EMA35 |
| `3m` | ~3 month swing | EMA20 / EMA50 |
| `4m` | ~4 month swing | EMA30 / EMA100 |
| `5m` | ~5 month swing | EMA40 / EMA150 |
| `6m` | ~6 month swing | EMA50 / EMA200 |
| `7m` | ~7 month swing | EMA60 / EMA250 |
| `8m` | ~8 month swing | EMA70 / EMA300 |
| `9m` | ~9 month swing | EMA80 / EMA350 |

Capped at 9 months max -- further out, a mechanically-detected level
starts meaning less and less. Each horizon uses its own EMA pair, VWAP
window, Fibonacci lookback, structural lookback, and pivot granularity —
a `2w` scenario is built from short, fast-reacting windows; a `9m`
scenario from long, slow-reacting ones. Every ticker is checked across
all ten horizons.
