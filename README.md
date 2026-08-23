# Swing Trade Alert Bot (Discord)

A Discord bot that scans a list of stock/ETF tickers **live throughout the
trading session** (default 08:00-23:00 Europe/Berlin) across **ten
swing horizons** (capped at 9 months max), looking for a very specific
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

## Documentation

| Document | What's in it |
|---|---|
| [docs/strategy.md](docs/strategy.md) | How the bot decides — index over the three files below |
| [docs/strategy-signals.md](docs/strategy-signals.md) | Finding setups: levels from every method, filters, duplicate merging, horizons |
| [docs/strategy-plans.md](docs/strategy-plans.md) | Building the plan: entry, target, stop, confidence, alert contents, tracking |
| [docs/strategy-gates.md](docs/strategy-gates.md) | Gates: market regime, relative strength, trend alignment, symbol resolution |
| [docs/setup.md](docs/setup.md) | Creating the Discord bot, configuring `.env`, installing, running 24/7 |
| [docs/commands.md](docs/commands.md) | Every Discord command |
| [docs/features.md](docs/features.md) | Plan Engine v2, analytics, the admin cockpit and SPA |
| [DOCKER.md](docs/DOCKER.md) · [DEPLOY_HETZNER.md](docs/DEPLOY_HETZNER.md) | Container build and deployment |

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
- `scanning/engine.py` — the core scan/dedup/confidence-filter/alert-building logic, shared by the automatic scan and `!check`

**`swingbot/commands/` (Discord command handlers):**
- `scanning.py` — `!check`, `!session`, `!status`, the background scan loop
- `watchlist.py` — `!watchlist` and subcommands
- `info.py` — `!strategies`, `!confidence`, `!regime`, `!ticker`, `!commands`, `!ping`
- `trades.py` — `!trades`, `!trade`, `!tradecharts`, `!performance` (win rate + risk-adjusted stats), `!pnl`
- `backtest.py` — `!backtest`, `!backtestwatchlist`
- `account.py` — `!account` and subcommands
- `data.py` — `!charts`, `!scrapeall`, `!download`, `!cached`

**`swingbot/admin/`:**
- `app.py` — the admin web UI (see [DOCKER.md](docs/DOCKER.md)), three pages via a sidebar: **Dashboard** (open trades, auto-refreshing every 5s so trades logged by `!check` show up without a manual reload, click any for full detail with chart + confidence breakdown, clear all open trades), **Settings** (every `.env` variable as a compact input field, hot-reloads the bot on save), **Logs** (live-updating tail of the bot's log file).

**Data files (created on first run, under `data/`):** `watchlist.json`, `state.json`,
`trades.json`, `account.json`. Chart images go under `exports/`; the bot's rotating log file goes under `logs/`.

## Customizing

- `swingbot/core/market/levels.py` → `CLUSTER_TOLERANCE_PCT` (how close two levels must be to merge), `MAX_RECENT_PIVOTS`
- `swingbot/core/market/trendlines.py` → `MIN_TRENDLINE_STRENGTH`, `MAX_TRENDLINES_PER_SIDE`, fit method
- `swingbot/core/market/volatility.py` → Bollinger window/std-dev, squeeze lookback window, squeeze tolerance
- `swingbot/core/market/candlestick_patterns.py` → `BULLISH_PATTERNS`/`BEARISH_PATTERNS` lists, `CHECK_LAST_N_BARS`
- `swingbot/core/market/strategy.py` → `HORIZONS` (per-horizon EMA/VWAP/Fibonacci/structure settings, shared by both engines)
- `swingbot/core/scanning/confidence.py` → point weights for each of the 5+1 scoring factors, the honesty-gate thresholds
- `swingbot/core/tracking/risk_metrics.py` → `MIN_CLOSED_TRADES` (how many closed trades before Sharpe/Sortino/etc. are shown)
- `swingbot/config.py` (or the admin UI's Settings page) → `MIN_ALERT_CONFIDENCE_LEVEL`, `MIN_REWARD_PCT`, `MAX_STOP_LOSS_PCT`, `MIN_RISK_REWARD_RATIO`, `MAX_RISK_REWARD_RATIO`, `MIN_ANNUALIZED_VOLATILITY_PCT`, `DEDUP_TOLERANCE_PCT`, `DEFAULT_HISTORY_PERIOD`, session/scan timing
