# Commands

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
