# Swing Trade Alert Bot (Discord)

A Discord bot that scans a list of stock/ETF tickers **live throughout the
trading session** (default 08:00-23:00 Europe/Berlin) across **five
swing horizons** (capped at 6 months max), looking for a very specific
thing: **is there a real, multi-method-confirmed support or resistance
level within reach of today's price?** If the next support or resistance
is at least `MIN_REWARD_PCT` (default **5%**, configurable) away from
the current price, that's a qualifying trade plan. It tracks every
recommendation as a paper trade, reports current unrealized P/L, warns
when an open trade
is nearing its stop-loss or take-profit, posts win/loss results to a
dedicated channel when a trade closes, and lets you backtest the
underlying technical patterns against real historical data. It only
sends alerts — it never places trades.

Run `!commands` (or `!help`) in Discord any time for the full command list.

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

Levels from different methods that land close together (within 1.5% of
each other) get merged into one, more-confirmed level — a Fibonacci
61.8% retracement sitting right on top of the 50-day EMA is a much
stronger level than either alone. **Confidence is built directly from
this**: how many independent methods agree on the target is the single
biggest factor in how confident an alert is (see below).

## Three extra filters for genuine 5%+ move candidates

On top of the level-confluence engine, three additional, purely
mathematical checks (`swingbot/core/volatility.py`) target whether a
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

Only **Level 3 (Medium)** and above confidence scenarios are shown as
alerts (`MIN_ALERT_CONFIDENCE_LEVEL`, default 3), with Level 4-5 (⭐)
prioritized. Lower levels are still computed internally, just not
surfaced — quality over quantity.

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

| Horizon | Meaning | EMA pair |
|---|---|---|
| `2w` | ~1-2 week swing | EMA5 / EMA10 |
| `4w` | ~4 week swing | EMA9 / EMA21 |
| `2m` | ~2 month swing | EMA14 / EMA35 |
| `3m` | ~3 month swing | EMA20 / EMA50 |
| `6m` | ~6 month swing | EMA50 / EMA200 |

Capped at 6 months max -- further out, a mechanically-detected level
starts meaning less and less. Each horizon uses its own EMA pair, VWAP
window, Fibonacci lookback, structural lookback, and pivot granularity —
a `2w` scenario is built from short, fast-reacting windows; a `6m`
scenario from long, slow-reacting ones. Every ticker is checked across
all five horizons.

## Entry is always today's current price

Unlike a crossover strategy that chases a specific indicator level, this
model reacts to *where price is right now*: entry = current price,
target = the next real support/resistance from here. There's no
pullback/retest logic to wait for — either a qualifying level exists
within reach today, or it doesn't (and no alert fires).

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
up", so it gets capped down instead of rounded up.

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

## Market regime filter

Checks a benchmark index (default SPY) against its 200-day EMA to
classify the broad market as bullish/bearish (`!regime` anytime). Feeds
into confidence scoring for alignment.

## Ticker symbol resolution

Common aliases (`SPX`→`^GSPC`, `XAUUSD`→`GC=F`, `EURUSD`→`EURUSD=X`, etc.)
resolve automatically. `!watchlist add` validates immediately and warns
if a symbol can't be resolved.

## Command hints

Mistype a command and the bot suggests the closest match. Get an argument
wrong and it shows correct usage instead of a raw error.

## 1. Create the Discord bot

1. Go to https://discord.com/developers/applications → **New Application**.
2. Go to **Bot** → **Add Bot**. Copy the **token**.
3. Under **Privileged Gateway Intents**, enable **Message Content Intent**.
4. **OAuth2 → URL Generator**: check `bot`, then `Send Messages`,
   `Embed Links`, `Attach Files`. Open the generated URL to invite the bot.
5. Right-click your alert channel → **Copy Channel ID** (enable Developer
   Mode in Discord settings first). Do the same for a second channel if
   you want closed-trade notifications separated out.

## 2. Configure

```bash
cp .env.example .env
```

Key settings in `.env` (see the file for the full list with comments):
```
DISCORD_TOKEN=<your bot token>
DISCORD_CHANNEL_ID=<main alert channel id>
CLOSED_TRADES_CHANNEL_ID=<closed-trade notifications channel id>
MIN_ALERT_CONFIDENCE_LEVEL=3
MIN_REWARD_PCT=5.0
DEDUP_TOLERANCE_PCT=2.0
DEFAULT_HISTORY_PERIOD=5y
```

## 3. Install & run

```bash
pip install -r requirements.txt
python bot.py
```

## 4. Commands

Run `!commands` for the live, categorized list. Summary:

| Command | Description |
|---|---|
| `!check [horizon]` | Snapshot of ALL current qualifying scenarios right now (shows live progress %) |
| `!session` / `!status` | Session window info / bot status |
| `!watchlist` / `add` / `remove` / `clear` | Manage the watchlist |
| `!strategies` / `!confidence` / `!regime` | Reference info |
| `!ticker TICKER` | Full technical snapshot for one ticker (legacy per-indicator view) |
| `!trades [open\|closed\|all] [n]` | List recent trades |
| `!trades clear` | Delete ALL trade records |
| `!trade ID` | Full detail + chart on one trade |
| `!trade delete ID` | Delete a single trade record |
| `!tradecharts [status] [n]` | Chart images for multiple trades |
| `!pnl` | Current unrealized P/L for every open trade |
| `!performance [level]` | Realized win-rate stats |
| `!backtest TICKER [horizon] [strategy]` | Backtest one ticker (legacy indicator-crossover engine) |
| `!backtestwatchlist [horizon] [strategy]` | Backtest & rank the whole watchlist |
| `!account` / `balance` / `risk` / `maxpositions` | Account settings (informational only, not used for sizing) |
| `!charts` | Full daily history + candlestick charts, posted per-ticker to the channel |
| `!scrapeall [force]` | Bulk-scrape full ("all time") history for the whole watchlist at once, concurrently, cached to disk (see below) |
| `!download INTERVAL [TICKER]` | Cache intraday data to disk |
| `!cached` | List what's cached on disk |
| `!ping` / `!commands` | Latency check / full command list |

Default watchlist on first run: `AAPL`, `MSFT`, `SPY`.

**`!scrapeall` vs `!charts`:** both fetch full ("all time", `period="max"`)
daily history for every watchlist ticker, but they're for different
purposes. `!charts` is interactive -- it posts each ticker's CSV and two
chart images directly into the channel, which is great for a handful of
tickers but impractical for a large watchlist (dozens of file uploads).
`!scrapeall` is the bulk/background version: it fetches every ticker
*concurrently* (a bounded thread pool, not one-by-one), skips any ticker
already scraped in roughly the last day unless you pass `force`, saves
everything as CSV under `exports/full_history/` on disk, and posts a
single summary table (or a summary file, if the watchlist is too big for
one Discord message) instead of flooding the channel. Inspired by
[gunjannandy/stock-market-scraper](https://github.com/gunjannandy/stock-market-scraper)'s
approach to bulk-downloading full history with multithreading and
skip-if-already-fetched caching -- see `export_data.py`'s docstring for
specifics on what was adapted from it.

**Note on `!backtest`/`!ticker`:** these still run the original
per-indicator crossover strategies (EMA Crossover, VWAP, Fibonacci,
Support/Resistance, RSI, Elliott Wave) from `strategy.py`, kept for
historical reference and quick per-ticker technical reads. The live
alert engine (`!check` and the background scan) uses the newer
support/resistance confluence model in `levels.py` instead — the two
are related (both pull from the same indicators) but not identical, so
don't expect `!backtest`'s numbers to describe live alert performance.
Use `!performance` for that.

## 5. Running it 24/7

Host this somewhere always-on. The included Docker setup ([DOCKER.md](DOCKER.md))
runs the bot plus an authenticated admin web UI as two containers
sharing one project directory — works on any VPS, a Raspberry Pi, or a
cloud VM. For a push-to-deploy pipeline on a Hetzner Cloud server
specifically (GitHub Actions deploys automatically on every push to
`main`), see [DEPLOY_HETZNER.md](DEPLOY_HETZNER.md). Without Docker, a
`systemd` service or `screen`/`tmux` session running `python bot.py`
works fine too.

## Event loop responsiveness

All the heavy work — Yahoo Finance fetches, pandas/indicator computation,
matplotlib chart rendering, backtesting — runs in a background thread via
`asyncio.to_thread()`, never directly on Discord's event loop. Without
this, a scan or backtest that takes more than ~10 seconds blocks the
gateway heartbeat and Discord can flag the bot as unresponsive
(`discord.gateway Shard ID None heartbeat blocked`). A scan lock
(`asyncio.Lock`) also ensures the automatic session scan and a manual
`!check` can't run their file-writing work at the same time. This applies
to every command that fetches data or renders a chart: `!check`,
`!ticker`, `!backtest`, `!backtestwatchlist`, `!charts`, `!scrapeall`,
`!download`, `!pnl`, `!trade`, `!tradecharts`, `!watchlist add`.

## Plan Engine v2: validated trade plans with badges and scale-out

Every trade plan the bot emits can be produced by one shared engine
(`swingbot/core/plan_engine.py`) whose exit behavior was backtested under a
train/validation split — so live behavior equals backtested behavior by
construction. Rollout is gated by three flags (all in `.env` / the admin
UI's "Plan Engine v2" section, hot-reloadable):

| Flag | Values | Meaning |
|---|---|---|
| `PLAN_ENGINE_V2` | `off` / `shadow` / `on` | `off` = legacy behavior. `shadow` = v2 plans are computed and logged to `data/shadow_plans.jsonl` during scans but not posted (parity evidence for the cutover — compare with `python scripts/shadow_parity_report.py`). `on` = alerts price and emit v2 plans. |
| `SCALE_OUT_ENABLED` | `true`/`false` | At TP1, close 50% and move the stop to break-even; the runner rides toward TP2 with a chandelier ATR trail. Enable only after `PLAN_ENGINE_V2=on` has run cleanly. |
| `INTRADAY_MANAGER_V2` | `true`/`false` | The 60s monitor manages the full plan lifecycle (PENDING → ACTIVE → PARTIAL → CLOSED): entry triggers, break-even moves, TP1 partials, runner trail, invalidation — with a Discord alert per transition. `!plans` shows the live board. |

**Defaults ship fully live** (`PLAN_ENGINE_V2=on`, `SCALE_OUT_ENABLED=true`,
`INTRADAY_MANAGER_V2=true`) so a fresh deployment runs the validated engine
immediately with no staged rollout required. If you'd rather stage it
yourself: `shadow` for ≥5 scan sessions (compare against legacy numbers via
`python scripts/shadow_parity_report.py`) → `on` for ≥5 clean sessions →
enable scale-out + manager.

**Badges: what they legally claim.** Every v2 plan is stamped from
`swingbot/core/validation_registry.json`:

- ✅ **VALIDATED** — this plan's signal source cleared `win_rate ≥ 80%,
  expectancy > 0, N ≥ 15, scratches+timeouts ≤ 50%` on the **held-out
  2024–2025 window it was never tuned on** (tuning used 2020–2023 only,
  and each source got exactly one validation shot). The badge line shows
  the actual N / win-rate / expectancy behind the claim.
- ⚠️ **WEAK** — the source did not clear that bar out-of-sample. Weak
  plans are **never suppressed**; they carry a caution block with the real
  numbers instead. A win rate printed on a badge is always an
  out-of-sample number, never a train number.

The registry regenerates only from validation runs
(`python scripts/run_backtest_range.py --validation --exit-model v2
--scale-out --emit-registry swingbot/core/validation_registry.json
--run-date <date>`), never by hand.

**Rescue outcomes.** Round 1 validated 6 of 11 strategies out-of-sample;
each of the other 5 got one pre-registered rescue attempt (a new opt-in
gate, TRAIN-only tuning, then a single validation-window look, no
retuning after). Only **RSI** cleared the bar (range-regime gate,
100% WR / N=30), bringing the total to **7 of 11 VALIDATED**. RSI
Divergence and MA Ribbon's gates never qualified on TRAIN; Elliott Wave
and EMA Crossover both passed TRAIN comfortably but missed the 80%
out-of-sample floor by a few points and stay WEAK. Full scoreboard and
pooled numbers: `docs/superpowers/results/2026-07-v2-final-report.md`.

## Files

The project is laid out as a proper package:

```
bot.py                 entry point: python bot.py
admin_ui.py             entry point: python admin_ui.py (admin web UI)
data/                   runtime state -- trades.json, state.json, account.json, watchlist.json
logs/                   bot.log (rotating), read by the admin UI's Logs page
exports/                generated chart images
deploy/                 hetzner-setup.sh (one-time server bootstrap), deploy.sh (pull + restart, used by CI and manually)
.github/workflows/       deploy.yml -- GitHub Actions: sanity-check then deploy over SSH on push to main
swingbot/
  config.py              all environment-driven settings (single schema for hot-reload + admin UI)
  bot_core.py             shared bot instance, session window, error handling, hot-reload signal handler
  core/                   business logic, no Discord dependency
  commands/               Discord command handlers, one module per area
  admin/                  the admin web UI (Flask)
```

**`swingbot/core/` (no Discord dependency):**
- `levels.py` — the live engine: multi-method support/resistance detection, level clustering, dual-scenario (bullish/bearish) builder with target 1 + target 2
- `trendlines.py` — diagonal trendline support/resistance (trendln library), one more independent confluence source alongside the horizontal methods in `levels.py`
- `volatility.py` — the three extra 5%-move filters: annualized volatility floor, Bollinger Band squeeze detection, volume breakout confirmation
- `candlestick_patterns.py` — classic candlestick pattern recognition (engulfing, hammer, morning star, etc. via pandas-ta-classic), used as a small confidence bonus when a pattern confirms the scenario's direction
- `strategy.py` — legacy per-indicator crossover strategies (EMA, VWAP, Fibonacci, Support/Resistance, RSI, Elliott Wave), still used by `!backtest`/`!ticker`
- `indicators.py` — EMA / RSI / rolling VWAP / Fibonacci levels / ATR / zigzag pivots
- `confidence.py` — 5-factor (+1 bonus factor), 5-level confidence scoring from level confluence
- `performance.py` — paper-trade log (log/update/clear/clear-open/delete/stats)
- `risk_metrics.py` — Sharpe/Sortino/max-drawdown/Calmar/profit-factor on the closed-trade track record (via QuantStats), feeding `!performance`
- `backtest.py` — vectorized historical backtesting engine (legacy indicator strategies)
- `account.py` — account config storage (informational only) + unrealized % P/L
- `events.py` — per-ticker earnings-date awareness
- `market_events.py` — broad market-wide events (FOMC, US jobs report, US CPI release)
- `regime.py` — broad market regime detection
- `explain.py` — short per-alert "why this trade" text
- `export_data.py` — full daily-history CSV + candlestick chart generation (single-ticker via `!charts`) and bulk concurrent/cached "all time" watchlist scraping (`!scrapeall`)
- `trade_chart.py` — per-alert annotated chart image (entry/stop/target1/target2)
- `data_store.py` — local intraday data cache
- `ticker_utils.py` — ticker alias resolution
- `data.py` — Yahoo Finance daily-bar fetch + per-ticker currency detection
- `watchlist.py` / `state.py` — watchlist storage / signal confirmation debounce
- `scan_engine.py` — the core scan/dedup/confidence-filter/alert-building logic, shared by the automatic scan and `!check`

**`swingbot/commands/` (Discord command handlers):**
- `scanning.py` — `!check`, `!session`, `!status`, the background scan loop
- `watchlist.py` — `!watchlist` and subcommands
- `info.py` — `!strategies`, `!confidence`, `!regime`, `!ticker`, `!commands`, `!ping`
- `trades.py` — `!trades`, `!trade`, `!tradecharts`, `!performance` (win rate + risk-adjusted stats), `!pnl`
- `backtest.py` — `!backtest`, `!backtestwatchlist`
- `account.py` — `!account` and subcommands
- `data.py` — `!charts`, `!scrapeall`, `!download`, `!cached`

**`swingbot/admin/`:**
- `app.py` — the admin web UI (see [DOCKER.md](DOCKER.md)), three pages via a sidebar: **Dashboard** (open trades, auto-refreshing every 5s so trades logged by `!check` show up without a manual reload, click any for full detail with chart + confidence breakdown, clear all open trades), **Settings** (every `.env` variable as a compact input field, hot-reloads the bot on save), **Logs** (live-updating tail of the bot's log file).

**Data files (created on first run, under `data/`):** `watchlist.json`, `state.json`,
`trades.json`, `account.json`. Chart images go under `exports/`; the bot's rotating log file goes under `logs/`.

## Customizing

- `swingbot/core/levels.py` → `CLUSTER_TOLERANCE_PCT` (how close two levels must be to merge), `MAX_RECENT_PIVOTS`
- `swingbot/core/trendlines.py` → `MIN_TRENDLINE_STRENGTH`, `MAX_TRENDLINES_PER_SIDE`, fit method
- `swingbot/core/volatility.py` → Bollinger window/std-dev, squeeze lookback window, squeeze tolerance
- `swingbot/core/candlestick_patterns.py` → `BULLISH_PATTERNS`/`BEARISH_PATTERNS` lists, `CHECK_LAST_N_BARS`
- `swingbot/core/strategy.py` → `HORIZONS` (per-horizon EMA/VWAP/Fibonacci/structure settings, shared by both engines)
- `swingbot/core/confidence.py` → point weights for each of the 5+1 scoring factors, the honesty-gate thresholds
- `swingbot/core/risk_metrics.py` → `MIN_CLOSED_TRADES` (how many closed trades before Sharpe/Sortino/etc. are shown)
- `swingbot/config.py` (or the admin UI's Settings page) → `MIN_ALERT_CONFIDENCE_LEVEL`, `MIN_REWARD_PCT`, `MAX_STOP_LOSS_PCT`, `MIN_RISK_REWARD_RATIO`, `MIN_ANNUALIZED_VOLATILITY_PCT`, `DEDUP_TOLERANCE_PCT`, `DEFAULT_HISTORY_PERIOD`, session/scan timing

