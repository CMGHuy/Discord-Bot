# v208 — Benchmark tab, part 2: benchmark bars, refresher step, pure stats

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v208 — Benchmark tab](../specs/2026-11-05-v208-benchmark-tab.md) (its *Amendment after the code brief* overrides earlier spec text)
**Index:** [2026-11-05-v208-benchmark-tab_0-index.md](2026-11-05-v208-benchmark-tab_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks V208-5..V208-7. V208-5 → V208-6 are sequential (6 calls 5's builders
and V208-2's repositories); V208-7 is pure and may start at once.

Conventions used in this part:

- **Stored returns are fractions** (`0.0123` = +1.23%). `benchmark_bars.day_pct`
  and every value `benchmark.py` returns are fractions; only V208-10 converts
  to the API's percentages.
- Drawdowns are returned **≤ 0** (`-0.10` = a 10% drop; `money_drawdown`
  `-250.0` = $250 below the peak).
- Session dates are NYSE sessions from `swingbot.core.market.session.nyse_calendar()`,
  never the weekday-only `is_regular_session`.

# Phase B — benchmark bars

### Task V208-5: `BENCHMARK_PROXY_SYMBOLS` + `marketdata/benchmarks.py` bar builders

**Model:** sonnet — new module on known yfinance/config patterns, pure row builders with clear tests.

**Files:**
- Modify: `swingbot/config.py` (new `Field` directly after `TAPE_PROXY_SYMBOLS`, ~:941)
- Modify: `.env.example` (two lines directly after `TAPE_PROXY_SYMBOLS=...`, ~:513)
- Create: `tests/test_config_v208_keys.py` (suite `config`, matches `tests/test_*.py`)
- Create: `swingbot/core/marketdata/benchmarks.py`
- Create: `tests/marketdata/test_benchmarks.py` (suite `market-data`)

**Interfaces:**
- Consumes: `swingbot.core.marketdata.yf_safe.download(*args, lock_timeout=None, **kwargs)` (raises `DownloadBusy` / `BudgetDeferred`); `swingbot.core.marketdata.data.get_current_price_batch(tickers, *, allow_stale=True) -> dict[str, float]`; `swingbot.core.market.session.nyse_calendar() -> SessionCalendar` (`.sessions(start, end) -> list[date]`).
- Produces (V208-6, V208-10, V208-11 rely on these exact names):
  - `BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "^IXIC", "^DJI")`
  - `TOTAL_RETURN: frozenset[str] = frozenset({"SPY", "QQQ"})`
  - `benchmark_proxy_map() -> dict[str, str]`
  - `fetch_history(symbols: Sequence[str], start: date) -> dict[str, pd.DataFrame]` — per-symbol frames with `Close` (and `Adj Close` when Yahoo sends it), NaN closes dropped, blank symbols omitted; download errors propagate to the caller.
  - `history_rows(symbol: str, frame: pd.DataFrame, *, source_symbol: str, sessions: Sequence[date], final_through: date, now: datetime) -> list[dict]`
  - `history_with_fallback(symbol: str, start: date, *, sessions: Sequence[date], final_through: date, now: datetime, fetch=fetch_history) -> list[dict]`
  - `latest_benchmark_prices(symbols: Sequence[str]) -> dict[str, float]`
  - `intraday_row(symbol: str, prev: dict | None, price: float | None, session: date, now: datetime) -> dict | None`
  - Every row dict has exactly the keys `symbol, session, close, adj_close, day_pct, source_symbol, final, as_of` (the V208-2 `upsert_bars` shape). `day_pct` is a **fraction**.

Rules this task pins (Global Constraints + Review Focus 4):

- `day_pct` = level / previous-session level − 1, where level is `Adj Close` for
  `TOTAL_RETURN` symbols sourced from themselves, `Close` otherwise (^IXIC, ^DJI
  and every proxy). The previous level must belong to the **previous NYSE
  session**; if that session has no valid row, `day_pct` is `None` (never a
  two-session return).
- A proxy row (`source_symbol != symbol`) stores `close = adj_close = None`.
- `history_rows` emits rows only for dates in `sessions` and `<= final_through`;
  every emitted row is `final = True`. A total-return symbol without an
  `Adj Close` column yields `[]` (blank, so the caller falls back or retries),
  never a silent price-only series.
- `intraday_row` reads the previous session's stored **raw `close`**. It returns
  `None` when the price is missing or ≤ 0, or `prev` is missing, not `final`, a
  proxy row (`close` NULL, `source_symbol != symbol`), or not the previous NYSE
  session. Intraday rows are `final = False`, `close = price`, `adj_close = None`,
  `source_symbol = symbol` (the Today card is their only reader).

- [ ] **Step 1: Write the failing config test**

`tests/test_config_v208_keys.py`:

```python
"""v208 V208-5: the Benchmark tab's proxy key (index "Global Constraints")."""
import pathlib

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]
ATTR = "BENCHMARK_PROXY_SYMBOLS"
DEFAULT = "^IXIC=ONEQ,^DJI=DIA"


def _field(attr=ATTR):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_is_a_hot_reloadable_data_sources_text_key():
    field = _field()
    assert (field.key, field.section, field.type, field.default) == (ATTR, "Data Sources", "text", DEFAULT)
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "v208" in field.help


def test_sits_right_after_the_tape_proxy_key():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index(ATTR) == attrs.index("TAPE_PROXY_SYMBOLS") + 1


def test_default_casts_to_itself():
    assert config._cast(_field(), _field().default) == DEFAULT


def test_env_example_lists_it_with_its_default():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{ATTR}={DEFAULT}\n" in text


def test_the_tape_key_is_untouched():
    assert _field("TAPE_PROXY_SYMBOLS").default == "^GSPC=SPY,^NDX=QQQ,^DJI=DIA,^VIX=VIXY,SI=F=SLV"
```

- [ ] **Step 2: Write the failing builder tests**

`tests/marketdata/test_benchmarks.py`:

```python
"""v208 V208-5: benchmark bar rows -- day_pct only, proxies change-% only, no lookahead."""
import math
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import benchmarks

NOW = datetime(2026, 11, 4, 22, 0, tzinfo=timezone.utc)
OCT30, NOV2, NOV3, NOV4 = date(2026, 10, 30), date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)
SESSIONS = [NOV2, NOV3]


def _frame(rows):
    """rows: [(date, close, adj_close)] -> a yfinance-shaped daily frame."""
    index = pd.DatetimeIndex([pd.Timestamp(d) for d, _, _ in rows])
    return pd.DataFrame({"Close": [c for _, c, _ in rows], "Adj Close": [a for _, _, a in rows]},
                        index=index)


SPY = _frame([(OCT30, 100.0, 98.0), (NOV2, 101.0, 99.96), (NOV3, 102.0, 100.5)])


def _rows(symbol, frame, source=None, sessions=SESSIONS, final_through=NOV3):
    return benchmarks.history_rows(symbol, frame, source_symbol=source or symbol,
                                   sessions=sessions, final_through=final_through, now=NOW)


def test_the_symbol_set_and_total_return_pair():
    assert benchmarks.BENCHMARK_SYMBOLS == ("SPY", "QQQ", "^IXIC", "^DJI")
    assert benchmarks.TOTAL_RETURN == frozenset({"SPY", "QQQ"})


def test_total_return_symbols_take_day_pct_from_adj_close():
    rows = _rows("SPY", SPY)
    assert [r["session"] for r in rows] == [NOV2, NOV3]
    first = rows[0]
    assert set(first) == {"symbol", "session", "close", "adj_close", "day_pct",
                          "source_symbol", "final", "as_of"}
    assert first["day_pct"] == pytest.approx(99.96 / 98.0 - 1)
    assert (first["close"], first["adj_close"]) == (101.0, 99.96)
    assert (first["source_symbol"], first["final"], first["as_of"]) == ("SPY", True, NOW)


def test_price_indexes_take_day_pct_from_close():
    rows = _rows("^DJI", SPY)
    assert rows[0]["day_pct"] == pytest.approx(0.01)


def test_a_proxy_row_stores_only_the_proxys_own_day_pct():
    dia = _frame([(OCT30, 400.0, 390.0), (NOV2, 404.0, 393.0), (NOV3, 402.0, 391.0)])
    rows = _rows("^DJI", dia, source="DIA")
    assert rows[0]["day_pct"] == pytest.approx(0.01)
    assert rows[1]["day_pct"] == pytest.approx(402.0 / 404.0 - 1)
    assert all(r["close"] is None and r["adj_close"] is None for r in rows)
    assert all(r["source_symbol"] == "DIA" and r["symbol"] == "^DJI" for r in rows)


def test_a_row_after_final_through_is_never_written():
    with_today = _frame([(OCT30, 100.0, 98.0), (NOV2, 101.0, 99.96), (NOV3, 102.0, 100.5),
                         (NOV4, 103.0, 101.0)])
    rows = _rows("SPY", with_today, sessions=[NOV2, NOV3, NOV4], final_through=NOV3)
    assert [r["session"] for r in rows] == [NOV2, NOV3]


def test_a_missing_previous_session_leaves_day_pct_none_not_a_two_day_return():
    gap = _frame([(OCT30, 100.0, 98.0), (NOV2, math.nan, math.nan), (NOV3, 102.0, 100.5)])
    rows = _rows("SPY", gap)
    assert [r["session"] for r in rows] == [NOV3]
    assert rows[0]["day_pct"] is None


def test_a_total_return_symbol_without_adj_close_is_blank():
    assert _rows("SPY", SPY.drop(columns=["Adj Close"])) == []


def test_proxy_map_parses_on_the_last_equals(monkeypatch):
    monkeypatch.setattr(config, "BENCHMARK_PROXY_SYMBOLS", " ^ixic=oneq , ^DJI=DIA,bad,=X", raising=False)
    assert benchmarks.benchmark_proxy_map() == {"^IXIC": "ONEQ", "^DJI": "DIA"}


def test_fallback_uses_the_proxy_only_when_yahoo_is_blank(monkeypatch):
    monkeypatch.setattr(config, "BENCHMARK_PROXY_SYMBOLS", "^DJI=DIA", raising=False)
    calls = []

    def fetch(symbols, start):
        calls.append(list(symbols))
        return {"DIA": SPY} if list(symbols) == ["DIA"] else {}

    rows = benchmarks.history_with_fallback("^DJI", OCT30, sessions=SESSIONS, final_through=NOV3,
                                            now=NOW, fetch=fetch)
    assert calls == [["^DJI"], ["DIA"]]
    assert {r["source_symbol"] for r in rows} == {"DIA"}

    calls.clear()
    rows = benchmarks.history_with_fallback(
        "SPY", OCT30, sessions=SESSIONS, final_through=NOV3, now=NOW,
        fetch=lambda symbols, start: calls.append(list(symbols)) or {"SPY": SPY})
    assert calls == [["SPY"]]
    assert {r["source_symbol"] for r in rows} == {"SPY"}


def test_fallback_without_a_proxy_is_empty(monkeypatch):
    monkeypatch.setattr(config, "BENCHMARK_PROXY_SYMBOLS", "", raising=False)
    assert benchmarks.history_with_fallback("^IXIC", OCT30, sessions=SESSIONS, final_through=NOV3,
                                            now=NOW, fetch=lambda symbols, start: {}) == []


@pytest.mark.parametrize("multi", [True, False])
def test_fetch_history_downloads_raw_and_adjusted(monkeypatch, multi):
    seen = {}

    def download(tickers, **kwargs):
        seen.update(kwargs, tickers=tickers)
        if not multi:
            return SPY
        blank = pd.DataFrame({"Close": [math.nan], "Adj Close": [math.nan]},
                             index=pd.DatetimeIndex([pd.Timestamp(NOV2)]))
        return pd.concat({"SPY": SPY, "^DJI": blank}, axis=1)

    monkeypatch.setattr(benchmarks.yf_safe, "download", download)
    symbols = ["SPY", "^DJI"] if multi else ["SPY"]
    got = benchmarks.fetch_history(symbols, OCT30)
    assert seen["auto_adjust"] is False and seen["interval"] == "1d"
    assert seen["start"] == "2026-10-30" and seen["tickers"] == " ".join(symbols)
    assert list(got) == ["SPY"]
    assert list(got["SPY"]["Adj Close"]) == [98.0, 99.96, 100.5]


PREV = {"symbol": "SPY", "session": NOV3, "close": 102.0, "adj_close": 100.5, "day_pct": 0.01,
        "source_symbol": "SPY", "final": True, "as_of": NOW}


def test_intraday_row_is_not_final_and_uses_the_raw_previous_close():
    row = benchmarks.intraday_row("SPY", PREV, 103.02, NOV4, NOW)
    assert row["day_pct"] == pytest.approx(0.01)
    assert (row["final"], row["close"], row["adj_close"], row["source_symbol"]) == (False, 103.02, None, "SPY")
    assert row["session"] == NOV4


@pytest.mark.parametrize("prev, price", [
    (None, 103.0),
    (PREV, None),
    (PREV, 0.0),
    ({**PREV, "final": False}, 103.0),
    ({**PREV, "close": None, "source_symbol": "DIA"}, 103.0),
    ({**PREV, "session": NOV2}, 103.0),
])
def test_intraday_row_is_skipped_rather_than_computed_from_nothing(prev, price):
    assert benchmarks.intraday_row("SPY", prev, price, NOV4, NOW) is None


def test_latest_prices_never_take_a_stale_price(monkeypatch):
    seen = {}

    def batch(tickers, *, allow_stale=True):
        seen.update(tickers=tickers, allow_stale=allow_stale)
        return {"SPY": 680.5, "^DJI": 0.0, "QQQ": None}

    monkeypatch.setattr(benchmarks.data, "get_current_price_batch", batch)
    assert benchmarks.latest_benchmark_prices(["SPY", "QQQ", "^DJI"]) == {"SPY": 680.5}
    assert seen == {"tickers": ["SPY", "QQQ", "^DJI"], "allow_stale": False}
```

- [ ] **Step 3: Run both files and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/test_config_v208_keys.py`, then `python scripts/dev/testrun.py file tests/marketdata/test_benchmarks.py`
Expected: FAIL — `StopIteration` (no such field) and `ImportError: cannot import name 'benchmarks'`.

- [ ] **Step 4: Add the config key and the `.env.example` lines**

In `swingbot/config.py`, directly after the `TAPE_PROXY_SYMBOLS` `Field(...)`:

```python
    Field("BENCHMARK_PROXY_SYMBOLS", "BENCHMARK_PROXY_SYMBOLS", "Data Sources",
          "Benchmark ETF proxies (index=ETF,...)", default="^IXIC=ONEQ,^DJI=DIA",
          help="v208. Analytics Benchmark tab only: when Yahoo has no daily bars for an index, "
               "its day % comes from this ETF, stored as change % only and flagged as a proxy. "
               "The last '=' separates the ETF. The tape keeps TAPE_PROXY_SYMBOLS."),
```

In `.env.example`, directly after the `TAPE_PROXY_SYMBOLS=...` line:

```
# v208: Benchmark tab ETF proxies, day % only; the last '=' separates the ETF
BENCHMARK_PROXY_SYMBOLS=^IXIC=ONEQ,^DJI=DIA
```

- [ ] **Step 5: Create `swingbot/core/marketdata/benchmarks.py`**

Module docstring: v208; what a row is; returns are read from `day_pct` only;
proxies are change-% only (the v171 rule); intraday rows feed the Today card only.
Imports: `math`, `date`/`datetime`/`timedelta`, `Sequence`, `pandas as pd`,
`from swingbot import config`, `from swingbot.core.market.session import nyse_calendar`,
`from swingbot.core.marketdata import data, yf_safe` (module attributes, so the
tests' `monkeypatch.setattr(benchmarks.yf_safe, ...)` and `benchmarks.data` work).

Signatures as in the Interfaces block. The bodies the tests leave open:

```python
def benchmark_proxy_map() -> dict[str, str]:
    """``BENCHMARK_PROXY_SYMBOLS`` as ``{index: proxy}``; each item splits on its last ``=``
    (the same parse as ``tape.proxy_map``; a separate key so the tape is untouched)."""
    out: dict[str, str] = {}
    for item in str(getattr(config, "BENCHMARK_PROXY_SYMBOLS", "") or "").split(","):
        symbol, sep, proxy = item.strip().rpartition("=")
        if sep and symbol.strip() and proxy.strip():
            out[symbol.strip().upper()] = proxy.strip().upper()
    return out


def fetch_history(symbols: Sequence[str], start: date) -> dict[str, pd.DataFrame]:
    syms = list(dict.fromkeys(symbols))
    raw = yf_safe.download(" ".join(syms), start=start.isoformat(), interval="1d",
                           group_by="ticker", auto_adjust=False, progress=False)
    return {s: frame for s in syms if (frame := _symbol_frame(raw, s)) is not None}


def _symbol_frame(raw, symbol: str) -> pd.DataFrame | None:
    """One symbol's frame from a grouped (MultiIndex) or flat download; None when blank."""
    columns = getattr(raw, "columns", None)
    if columns is None or raw.empty:
        return None
    if getattr(columns, "nlevels", 1) > 1:
        if symbol not in columns.get_level_values(0):
            return None
        raw = raw[symbol]
    if "Close" not in raw.columns:
        return None
    frame = raw.dropna(subset=["Close"])
    return None if frame.empty else frame


def _previous_session(day: date) -> date | None:
    earlier = nyse_calendar().sessions(day - timedelta(days=10), day - timedelta(days=1))
    return earlier[-1] if earlier else None


def _level_column(symbol: str, source_symbol: str, frame: pd.DataFrame) -> str | None:
    if source_symbol == symbol and symbol in TOTAL_RETURN:
        return "Adj Close" if "Adj Close" in frame.columns else None
    return "Close"
```

`_by_day(frame, column) -> dict[date, float]`: positive, finite values of
`column` keyed by `ts.date()`; `{}` when the column is absent.

`history_rows`: `column = _level_column(...)`, `None` → `[]`. `levels = _by_day(frame, column)`,
`closes = _by_day(frame, "Close")`, `adjs = _by_day(frame, "Adj Close")`. For each
`day in sessions` with `day <= final_through and day in levels`:
`prev = _previous_session(day)`; `day_pct = levels[day] / levels[prev] - 1 if prev in levels else None`;
`own = source_symbol == symbol`; row `{"symbol": symbol, "session": day,
"close": closes.get(day) if own else None, "adj_close": adjs.get(day) if own else None,
"day_pct": day_pct, "source_symbol": source_symbol, "final": True, "as_of": now}`.
Put the row in a `_bar(...)` helper so every function stays well under complexity 15.

`history_with_fallback`:

```python
def history_with_fallback(symbol, start, *, sessions, final_through, now, fetch=fetch_history):
    window = {"sessions": sessions, "final_through": final_through, "now": now}
    own = fetch([symbol], start).get(symbol)
    rows = history_rows(symbol, own, source_symbol=symbol, **window) if own is not None else []
    proxy = benchmark_proxy_map().get(symbol)
    if rows or not proxy:
        return rows
    frame = fetch([proxy], start).get(proxy)
    return history_rows(symbol, frame, source_symbol=proxy, **window) if frame is not None else []
```

`latest_benchmark_prices`: `data.get_current_price_batch(list(symbols), allow_stale=False) or {}`,
keep only `p is not None and float(p) > 0`, values as `float`.

`intraday_row`: the skip rules listed above, then
`{"symbol": symbol, "session": session, "close": float(price), "adj_close": None,
"day_pct": float(price) / float(prev["close"]) - 1, "source_symbol": symbol, "final": False,
"as_of": now}`. Docstring: the raw previous close is used for every symbol, so an
ex-dividend morning reads price-only; the post-close final row replaces it.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/test_config_v208_keys.py`, `python scripts/dev/testrun.py file tests/marketdata/test_benchmarks.py`, `python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py`
Expected: each `0 failed`.

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; nothing in `swingbot/core/marketdata/benchmarks.py` reported.

- [ ] **Step 8: Commit**

```bash
git add swingbot/config.py .env.example tests/test_config_v208_keys.py swingbot/core/marketdata/benchmarks.py tests/marketdata/test_benchmarks.py
git commit -m "feat(v208): BENCHMARK_PROXY_SYMBOLS and benchmark bar builders (V208-5)"
```

### Task V208-6: Refresher step `benchmarks` + DEPLOY_HETZNER step line

**Model:** sonnet — one never-fails refresher step on the `fx_snap_step` template; the scheduling rules are fully pinned by tests.

**Files:**
- Create: `swingbot/refresher/benchmarks.py`
- Modify: `swingbot/refresher/loop.py` (import + `STEPS`, module docstring line on `STEPS`)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (one bullet in `## The refresher service (v201)`)
- Create: `tests/refresher/test_benchmarks_step.py` (suite `refresher`)

**Interfaces:**
- Consumes: V208-5 `swingbot.core.marketdata.benchmarks` — `BENCHMARK_SYMBOLS`, `history_with_fallback(symbol, start, *, sessions, final_through, now, fetch=...) -> list[dict]`, `latest_benchmark_prices(symbols) -> dict[str, float]`, `intraday_row(symbol, prev, price, session, now) -> dict | None`. V208-2 `swingbot.core.db.repositories.benchmark_bars` — `benchmark_bars_repo()` (`upsert_bars(rows) -> int`, `list_range(symbols, start, end) -> list[dict]`) and `benchmark_refresh_repo()` (`full_refreshed_on(symbol) -> date | None`, `mark_full_refresh(symbol, day) -> None`). Existing: `equity_samples_repo().earliest_at(source) -> datetime | None`; `session.last_regular_close(now) -> datetime` (UTC, half-day aware), `session.market_today(now)`, `session.nyse_calendar()`, `session.SESSION_REGULAR`, `session.US_MARKET_TZ`; `router.asker_scope(Asker.ADMIN_REFRESH)`; `swallowed(log, tag, exc, msg, *args, level=...)`.
- Produces:
  - `benchmarks_step(ctx: CycleContext) -> None` — never raises; failures are swallowed under `ops.refresher.benchmarks` and leave `ctx.report.error` alone.
  - `INTRADAY_EVERY_S = 300`, `FULL_RETRY_S = 900`
  - `live_since() -> date | None` — NY date of the earliest `equity_samples` row of any source (V208-11 reuses it for the range clamp).
  - `last_completed_session(now: datetime) -> date` — NY date of `last_regular_close(now)`.
  - `reset_state() -> None` — clears the process-memory throttles (tests only).
  - `loop.STEPS == [quotes.quote_step, quotes.fx_step, quotes.fx_snap_step, benchmarks.benchmarks_step]`.

Scheduling rules (spec § Benchmark series; Review Focus 1 and 3):

1. **Skip the whole step while a scan runs** (`ctx.scan_running`): both
   fetches use the yfinance lock, like `_refresh_index`. Skip when
   `live_since()` is `None` (nothing to compare against yet).
2. **Full refresh, per symbol, once per session day.** `last = last_completed_session(now)`.
   A symbol is due when `full_refreshed_on(symbol)` is `None` or `< last`, and
   it was not tried in this process within `FULL_RETRY_S`. A due symbol gets
   one `history_with_fallback(symbol, live_since - 10 days, sessions=nyse_calendar().sessions(live_since, last), final_through=last, now=now)`:
   every session since `live_since` in **one** call and one `upsert_bars`, so a
   refresher down for days catches up in a single cycle. It is marked
   (`mark_full_refresh(symbol, last)`) **only when the rows include `last`**;
   otherwise (Yahoo has not published the close yet, or blank everywhere) it
   is retried after `FULL_RETRY_S`, never every 30-second cycle. Skipped when
   `last < live_since`.
3. **Intraday**, only when `ctx.session == session.SESSION_REGULAR` and today
   (`market_today(now)`) is an NYSE session, at most once per
   `INTRADAY_EVERY_S`: previous rows = `list_range(BENCHMARK_SYMBOLS, last, last)`
   (in session, `last` is the previous session), prices =
   `latest_benchmark_prices(BENCHMARK_SYMBOLS)`, rows = every non-`None`
   `intraday_row(...)`, one `upsert_bars`. The full refresh runs first in the
   same cycle, so the previous final row exists after a restart.
4. Both run inside `router.asker_scope(Asker.ADMIN_REFRESH)`.
5. Half days come from `last_regular_close` (13:00 ET close): at 13:30 ET on
   2026-11-27 the last completed session is 2026-11-27; at 12:30 ET it is 2026-11-25.

- [ ] **Step 1: Write the failing tests**

`tests/refresher/test_benchmarks_step.py`:

```python
"""v208 V208-6: the benchmarks refresher step -- once-a-day full refresh, 5-minute intraday, never fails."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared.kinds import Asker
from swingbot.refresher import benchmarks as step
from swingbot.refresher import loop, quotes
from swingbot.refresher.symbols import SymbolSet

UTC = timezone.utc
SYMBOLS = ("SPY", "QQQ", "^IXIC", "^DJI")
SINCE = date(2026, 10, 28)
AFTER_CLOSE = datetime(2026, 11, 4, 22, 0, tzinfo=UTC)    # Wed 17:00 ET
IN_SESSION = datetime(2026, 11, 4, 15, 0, tzinfo=UTC)     # Wed 10:00 ET
ALL_SESSIONS = [date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30),
                date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)]


class FakeBars:
    def __init__(self):
        self.rows = {}
        self.upserts = 0

    def upsert_bars(self, rows, conn=None):
        self.upserts += 1
        for row in rows:
            self.rows[(row["symbol"], row["session"])] = dict(row)
        return len(rows)

    def list_range(self, symbols, start, end, conn=None):
        return [r for (s, d), r in sorted(self.rows.items()) if s in symbols and start <= d <= end]


class FakeRefresh:
    def __init__(self, done=None):
        self.done = dict(done or {})

    def full_refreshed_on(self, symbol, conn=None):
        return self.done.get(symbol)

    def mark_full_refresh(self, symbol, day, conn=None):
        self.done[symbol] = day


def _bar(symbol, day, *, final=True, close=100.0):
    return {"symbol": symbol, "session": day, "close": close, "adj_close": close, "day_pct": 0.01,
            "source_symbol": symbol, "final": final, "as_of": AFTER_CLOSE}


@pytest.fixture
def env(monkeypatch):
    step.reset_state()
    state = {"bars": FakeBars(), "refresh": FakeRefresh(), "history": [], "prices": [],
             "through": None, "asker": []}

    def history(symbol, start, *, sessions, final_through, now, fetch=None):
        state["history"].append((symbol, start, list(sessions), final_through))
        state["asker"].append(router.current_asker())
        through = state["through"] or final_through
        return [_bar(symbol, d) for d in sessions if d <= through]

    def prices(symbols):
        state["prices"].append(tuple(symbols))
        return {s: 101.0 for s in symbols}

    monkeypatch.setattr(step, "benchmark_bars_repo", lambda: state["bars"])
    monkeypatch.setattr(step, "benchmark_refresh_repo", lambda: state["refresh"])
    monkeypatch.setattr(step, "live_since", lambda: SINCE)
    monkeypatch.setattr(step.mb, "history_with_fallback", history)
    monkeypatch.setattr(step.mb, "latest_benchmark_prices", prices)
    yield state
    step.reset_state()


def _ctx(now, state="closed", scan_running=False):
    return loop.CycleContext(now, state, SymbolSet((), ()), [], [], scan_running,
                             loop.CycleReport(state, 30.0))


def test_the_step_runs_last_right_after_the_fx_snap():
    assert loop.STEPS[-1] is step.benchmarks_step
    assert loop.STEPS.index(step.benchmarks_step) == loop.STEPS.index(quotes.fx_snap_step) + 1


def test_a_running_scan_skips_the_step(env):
    step.benchmarks_step(_ctx(AFTER_CLOSE, scan_running=True))
    assert env["history"] == [] and env["bars"].rows == {}


def test_no_equity_yet_writes_nothing(env, monkeypatch):
    monkeypatch.setattr(step, "live_since", lambda: None)
    step.benchmarks_step(_ctx(AFTER_CLOSE))
    assert env["history"] == []


def test_a_restart_after_days_down_catches_up_every_session_in_one_refresh(env):
    env["refresh"].done = {s: date(2026, 10, 29) for s in SYMBOLS}
    step.benchmarks_step(_ctx(AFTER_CLOSE))
    assert [h[0] for h in env["history"]] == list(SYMBOLS)
    for _, start, sessions, through in env["history"]:
        assert start < SINCE and sessions == ALL_SESSIONS and through == date(2026, 11, 4)
    assert env["bars"].upserts == 4 and len(env["bars"].rows) == 4 * len(ALL_SESSIONS)
    assert all(r["final"] for r in env["bars"].rows.values())
    assert env["refresh"].done == {s: date(2026, 11, 4) for s in SYMBOLS}
    assert set(env["asker"]) == {Asker.ADMIN_REFRESH}


def test_the_next_cycle_never_refetches_a_refreshed_day(env):
    step.benchmarks_step(_ctx(AFTER_CLOSE))
    env["history"].clear()
    step.reset_state()   # even a restarted process reads the stored guard
    step.benchmarks_step(_ctx(AFTER_CLOSE + timedelta(seconds=30)))
    assert env["history"] == []


def test_a_refresh_without_the_last_close_is_retried_later_not_marked(env):
    env["through"] = date(2026, 11, 3)
    step.benchmarks_step(_ctx(AFTER_CLOSE))
    assert env["refresh"].done == {}
    env["history"].clear()
    step.benchmarks_step(_ctx(AFTER_CLOSE + timedelta(seconds=60)))
    assert env["history"] == []
    env["through"] = None
    step.benchmarks_step(_ctx(AFTER_CLOSE + timedelta(seconds=step.FULL_RETRY_S)))
    assert len(env["history"]) == 4
    assert env["refresh"].done == {s: date(2026, 11, 4) for s in SYMBOLS}


@pytest.mark.parametrize("now, last", [
    (datetime(2026, 11, 27, 18, 30, tzinfo=UTC), date(2026, 11, 27)),   # 13:30 ET, half day closed
    (datetime(2026, 11, 27, 17, 30, tzinfo=UTC), date(2026, 11, 25)),   # 12:30 ET, still open
])
def test_a_half_day_close_gates_the_final_bar(now, last):
    assert step.last_completed_session(now) == last


def test_in_session_today_is_upserted_not_final_at_most_every_five_minutes(env):
    env["refresh"].done = {s: date(2026, 11, 3) for s in SYMBOLS}
    env["bars"].rows = {(s, date(2026, 11, 3)): _bar(s, date(2026, 11, 3)) for s in SYMBOLS}
    step.benchmarks_step(_ctx(IN_SESSION, "regular"))
    today = {s: env["bars"].rows[(s, date(2026, 11, 4))] for s in SYMBOLS}
    assert all(r["final"] is False and r["as_of"] == IN_SESSION for r in today.values())
    assert today["SPY"]["day_pct"] == pytest.approx(0.01)
    assert env["history"] == []          # yesterday already refreshed
    step.benchmarks_step(_ctx(IN_SESSION + timedelta(seconds=60), "regular"))
    assert len(env["prices"]) == 1
    step.benchmarks_step(_ctx(IN_SESSION + timedelta(seconds=step.INTRADAY_EVERY_S), "regular"))
    assert len(env["prices"]) == 2


@pytest.mark.parametrize("state", ["extended", "closed"])
def test_no_intraday_row_outside_the_regular_session(env, state):
    env["refresh"].done = {s: date(2026, 11, 4) for s in SYMBOLS}
    step.benchmarks_step(_ctx(AFTER_CLOSE, state))
    assert env["prices"] == []


def test_a_failure_is_swallowed_and_leaves_the_cycle_error_alone(env, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('relation "benchmark_bars" does not exist')
    monkeypatch.setattr(step.mb, "history_with_fallback", boom)
    before = sw.snapshot().get("ops.refresher.benchmarks", {}).get("count", 0)
    ctx = _ctx(AFTER_CLOSE)
    step.benchmarks_step(ctx)
    assert ctx.report.error is None
    assert sw.snapshot()["ops.refresher.benchmarks"]["count"] == before + 1


class FakeEquity:
    def __init__(self, live, backfill):
        self.edges = {"live": live, "backfill": backfill}

    def earliest_at(self, source, conn=None):
        return self.edges[source]


@pytest.mark.parametrize("live, backfill, expected", [
    (datetime(2026, 10, 1, 14, 0, tzinfo=UTC), datetime(2026, 8, 8, 2, 0, tzinfo=UTC), date(2026, 8, 7)),
    (datetime(2026, 10, 1, 14, 0, tzinfo=UTC), None, date(2026, 10, 1)),
    (None, None, None),
])
def test_live_since_is_the_earliest_sample_of_any_source_as_an_ny_date(monkeypatch, live, backfill, expected):
    monkeypatch.setattr(step, "equity_samples_repo", lambda: FakeEquity(live, backfill))
    assert step.live_since() == expected
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python scripts/dev/testrun.py file tests/refresher/test_benchmarks_step.py`
Expected: FAIL — `ImportError: cannot import name 'benchmarks' from 'swingbot.refresher'`.

- [ ] **Step 3: Create `swingbot/refresher/benchmarks.py`**

Module docstring: v208; the three rules above in one paragraph each; "the
stored `benchmark_refresh` date is the once-per-session-day guard; the two
process-memory throttles only space out retries".

Imports, at module level so the tests can patch them:
`from swingbot.core.db.repositories.benchmark_bars import benchmark_bars_repo, benchmark_refresh_repo`,
`from swingbot.core.db.repositories.equity_samples import equity_samples_repo`,
`from swingbot.core.market import session`,
`from swingbot.core.marketdata import benchmarks as mb`,
`from swingbot.core.marketdata.providers import router`,
`from swingbot.core.marketdata.shared.kinds import Asker`,
`from swingbot.core.infra.swallowed import swallowed`; `CycleContext` under
`TYPE_CHECKING` only (as in `quotes.py`; `loop` imports this module).

```python
INTRADAY_EVERY_S = 300
FULL_RETRY_S = 900
_FETCH_LEAD = timedelta(days=10)   # the bar before live_since gives its first day_pct

_last_intraday: datetime | None = None
_last_try: dict[str, datetime] = {}


def benchmarks_step(ctx: "CycleContext") -> None:
    try:
        _run(ctx)
    except Exception as exc:  # noqa: BLE001 - a missed benchmark write never fails the cycle
        swallowed(log, "ops.refresher.benchmarks", exc, "benchmarks step failed: %s", exc,
                  level=logging.WARNING)


def _run(ctx: "CycleContext") -> None:
    if ctx.scan_running:
        return
    since = live_since()
    if since is None:
        return
    with router.asker_scope(Asker.ADMIN_REFRESH):
        _full_refresh(ctx.now, since)
        if ctx.session == session.SESSION_REGULAR:
            _intraday(ctx.now)
```

The rest, by signature (bodies follow rules 2 and 3 above):

- `live_since() -> date | None`: `min` of the non-`None` `earliest_at("live")` /
  `earliest_at("backfill")`, `.astimezone(session.US_MARKET_TZ).date()`.
- `last_completed_session(now: datetime) -> date`: `session.last_regular_close(now).astimezone(session.US_MARKET_TZ).date()`.
- `_full_refresh(now: datetime, since: date) -> None`: compute `last`, return when
  `last < since`, build `sessions` once, call `_refresh_symbol` for each due symbol.
- `_full_due(symbol: str, last: date, now: datetime) -> bool`: stored date first, then `_last_try`.
- `_refresh_symbol(symbol, since, sessions, last, now) -> None`: stamp `_last_try[symbol] = now`
  **before** the fetch (a raising fetch is throttled too), fetch, upsert when non-empty,
  mark only when `any(r["session"] == last for r in rows)`.
- `_intraday(now: datetime) -> None`: throttle on `_last_intraday`, return when
  `not session.nyse_calendar().is_session(session.market_today(now))`, stamp
  `_last_intraday = now`, then the rows of rule 3.
- `reset_state() -> None`: `_last_intraday = None`, `_last_try.clear()`.

- [ ] **Step 4: Wire it into `swingbot/refresher/loop.py`**

`from swingbot.refresher import benchmarks, lock, quotes`, then

```python
STEPS: list[Callable[[CycleContext], None]] = [quotes.quote_step, quotes.fx_step,
                                               quotes.fx_snap_step, benchmarks.benchmarks_step]
```

and extend the docstring sentence on `STEPS`: "…and the v205 FX snap (`quotes`),
then the v208 `benchmarks` step (index daily bars for the Analytics Benchmark tab)".

- [ ] **Step 5: List the step in `docs/deploy/DEPLOY_HETZNER.md`**

In `## The refresher service (v201)`, directly after the `- Logs: ...` bullet:

```markdown
- Steps, in order: quotes, FX pairs, the v205 FX snap, and the v208
  `benchmarks` step. `benchmarks` writes SPY, QQQ, ^IXIC and ^DJI daily bars
  into `benchmark_bars` for the Analytics Benchmark tab: today's row every
  5 minutes in session (`final = false`), and once per session day after the
  close a full adjusted-history rewrite since the first equity sample
  (`final = true`, guarded by `benchmark_refresh`, so a refresher that was
  down catches up in one cycle). It skips while a scan runs, falls back to the
  `BENCHMARK_PROXY_SYMBOLS` ETFs when Yahoo is blank, and logs
  `benchmarks step failed` (swallowed) until `v208_001` is applied. With the
  refresher off nothing is written and the tab says "Benchmarks not updating".
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/refresher/test_benchmarks_step.py`, `python scripts/dev/testrun.py file tests/refresher/test_fx_snap_step.py`, `python scripts/dev/testrun.py file tests/refresher/test_loop.py`, `python scripts/dev/testrun.py file tests/scripts/test_rollback_to_shape.py`
Expected: each `0 failed` (`test_loop.py` patches `loop.STEPS = []`, so the new step never runs there).

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; nothing in `swingbot/refresher/benchmarks.py` reported.

- [ ] **Step 8: Commit**

```bash
git add swingbot/refresher/benchmarks.py swingbot/refresher/loop.py docs/deploy/DEPLOY_HETZNER.md tests/refresher/test_benchmarks_step.py
git commit -m "feat(v208): refresher benchmarks step -- daily bars, 5-minute intraday, once-a-day rewrite (V208-6)"
```

# Phase C — pure stats

### Task V208-7: `core/analytics/benchmark.py` — formulas + small-sample guards

**Model:** sonnet — pure numeric functions with reference values fixed in the tests; no I/O, no shared state.

**Files:**
- Create: `swingbot/core/analytics/benchmark.py`
- Create: `tests/analytics/test_benchmark_stats.py` (suite `analytics`)

**Interfaces:**
- Consumes: nothing from earlier tasks (standard library `math`, `statistics`, `dataclasses`).
- Produces (V208-10 builds every stat tile from these; names and fields are final):
  - Constants `TRADING_DAYS = 252`, `MIN_BETA_N = 20`, `MIN_SHARPE_N = 20`, `MIN_ALPHA_N = 60`, `MIN_CAPTURE_SIDE_N = 10`.
  - `needs(k: int) -> str` → `f"needs ≥ {k} sessions"` (the Global Constraints copy); `CAPTURE_REASON = "needs ≥ 10 index-up and ≥ 10 index-down sessions"`; `NO_VARIANCE = "no variance"`; `INDEX_FLAT = "index flat"`.
  - `@dataclass(frozen=True) Estimate(value: float | None, se: float | None, t: float | None, n: int, reason: str | None)`
  - `@dataclass(frozen=True) Capture(up: float | None, down: float | None, ratio: float | None, up_n: int, down_n: int, reason: str | None)`
  - `@dataclass(frozen=True) BeatCount(up_days: int, up_beat: int, down_days: int, down_beat: int)`
  - `total_return(r: Sequence[float]) -> float | None`
  - `cumulative(r: Sequence[float]) -> list[float]`
  - `max_drawdown(r: Sequence[float]) -> float | None` (≤ 0)
  - `money_drawdown(closes: Sequence[float]) -> float | None` (≤ 0, money units)
  - `losing_streak(r: Sequence[float]) -> int`
  - `sharpe(r: Sequence[float]) -> Estimate`
  - `beta(bot: Sequence[float], idx: Sequence[float]) -> Estimate`
  - `alpha(bot: Sequence[float], idx: Sequence[float]) -> Estimate` (annualised)
  - `capture(bot: Sequence[float], idx: Sequence[float]) -> Capture`
  - `beat_count(bot: Sequence[float], idx: Sequence[float]) -> BeatCount`
  - Every return in and out is a **fraction**; the caller (V208-10) passes only
    the returns it means to count (spanning pairs and `base_balance` sessions
    already removed for beta/alpha/Sharpe/capture/Beat?), never `None`.

Definitions (spec § Stats; Global Constraints):

| Function | Definition |
|---|---|
| `total_return` | `Π(1+r) − 1`; `None` for an empty input |
| `cumulative` | running `Π(1+r) − 1`, one value per input, `[]` for empty |
| `max_drawdown` | largest drop of the curve `1, Π(1+r)…` from its running peak, `trough/peak − 1`; the base 1.0 counts as a peak; `0.0` when it never falls; `None` for empty |
| `money_drawdown` | largest `close − running peak` over the closes; `0.0` for one close; `None` for none |
| `losing_streak` | longest run of consecutive `r < 0` (a `0.0` ends a run) |
| `sharpe` | `mean / stdev(ddof=1) × √252`, rf = 0; `n < 20` → `needs(20)`; stdev 0 → `NO_VARIANCE`; `se = t = None` |
| `beta` | OLS slope of `bot` on `idx`; `se` = slope standard error `√(s²/Sxx)`, `s² = SSE/(n−2)`; `t = value/se` (`None` when `se == 0`); `n < 20` → `needs(20)`; `Sxx == 0` → `INDEX_FLAT` |
| `alpha` | OLS intercept × 252; `se` = intercept SE `√(s²(1/n + x̄²/Sxx))` × 252; `t` = intercept / intercept SE (`None` when SE is 0); `n < 60` → `needs(60)`; `Sxx == 0` → `INDEX_FLAT` |
| `capture` | up days = `idx > 0`, down days = `idx < 0`, flat days excluded; `up = Σ bot_up / Σ idx_up`, `down = Σ bot_down / Σ idx_down`, `ratio = up / down` (`None` when `down` is 0); fewer than 10 on either side → all three `None`, `CAPTURE_REASON`, counts still set |
| `beat_count` | per side, sessions with `bot > idx`; flat days excluded |

Every function taking `bot, idx` raises `ValueError` when the lengths differ.
A guarded result keeps its `n` (the tiles show `N` even when the value is `—`).

- [ ] **Step 1: Write the failing tests**

`tests/analytics/test_benchmark_stats.py` (the reference values were computed
with `scipy.stats.linregress` and `statistics.stdev`; scipy is not a test
dependency, so they are literals):

```python
"""v208 V208-7: benchmark stats -- known values, empty inputs and the N guards."""
import math

import pytest

from swingbot.core.analytics import benchmark as bm


def _fixture(n=60):
    idx = [0.01 * math.sin(1.7 * i) + 0.002 * ((i % 5) - 2) for i in range(n)]
    bot = [0.0004 + 0.6 * x + 0.003 * math.cos(2.3 * i) for i, x in enumerate(idx)]
    return bot, idx


BOT, IDX = _fixture()


def test_constants_and_reasons():
    assert (bm.TRADING_DAYS, bm.MIN_BETA_N, bm.MIN_SHARPE_N, bm.MIN_ALPHA_N, bm.MIN_CAPTURE_SIDE_N) == \
        (252, 20, 20, 60, 10)
    assert bm.needs(20) == "needs ≥ 20 sessions"


def test_total_and_cumulative():
    assert bm.total_return([0.1, -0.1]) == pytest.approx(-0.01)
    assert bm.cumulative([0.1, 0.1]) == pytest.approx([0.1, 0.21])
    assert bm.total_return(BOT) == pytest.approx(0.02280255021326738)
    assert bm.cumulative(BOT)[-1] == pytest.approx(bm.total_return(BOT))


def test_empty_and_single_session_inputs():
    assert bm.total_return([]) is None
    assert bm.cumulative([]) == []
    assert bm.max_drawdown([]) is None
    assert bm.money_drawdown([]) is None
    assert bm.losing_streak([]) == 0
    assert bm.total_return([0.02]) == pytest.approx(0.02)
    assert bm.max_drawdown([0.02]) == 0.0
    assert bm.money_drawdown([10_000.0]) == 0.0
    empty = bm.sharpe([])
    assert (empty.value, empty.n, empty.reason) == (None, 0, "needs ≥ 20 sessions")


@pytest.mark.parametrize("returns, expected", [
    ([0.1, -0.5, 0.2], -0.5),
    ([-0.1], -0.1),            # the base close is the first peak
    ([0.05, 0.05], 0.0),
])
def test_max_drawdown_is_a_non_positive_fraction(returns, expected):
    assert bm.max_drawdown(returns) == pytest.approx(expected)


def test_money_drawdown_and_losing_streak():
    assert bm.money_drawdown([10_000.0, 10_500.0, 9_800.0, 10_200.0, 9_700.0]) == pytest.approx(-800.0)
    assert bm.losing_streak([0.01, -0.01, -0.02, 0.0, -0.01, -0.01, -0.01, 0.02]) == 3


def test_sharpe_known_value_ddof_1():
    est = bm.sharpe(BOT)
    assert est.value == pytest.approx(1.2465510910232496)
    assert (est.n, est.reason, est.se, est.t) == (60, None, None, None)


def test_sharpe_guards():
    short = bm.sharpe(BOT[:19])
    assert (short.value, short.n, short.reason) == (None, 19, "needs ≥ 20 sessions")
    flat = bm.sharpe([0.001] * 25)
    assert (flat.value, flat.n, flat.reason) == (None, 25, bm.NO_VARIANCE)


def test_beta_with_standard_error_at_the_threshold():
    est = bm.beta(BOT[:20], IDX[:20])
    assert est.value == pytest.approx(0.5987039626951823)
    assert est.se == pytest.approx(0.06907751418848224)
    assert est.t == pytest.approx(0.5987039626951823 / 0.06907751418848224)
    assert (est.n, est.reason) == (20, None)


def test_beta_guards():
    short = bm.beta(BOT[:19], IDX[:19])
    assert (short.value, short.se, short.n, short.reason) == (None, None, 19, "needs ≥ 20 sessions")
    flat = bm.beta(BOT[:25], [0.0] * 25)
    assert (flat.value, flat.reason) == (None, bm.INDEX_FLAT)


def test_alpha_is_annualised_jensen_with_t_stat():
    est = bm.alpha(BOT, IDX)
    assert est.value == pytest.approx(0.1002628883975672)
    assert est.se == pytest.approx(0.07025359431166461)
    assert est.t == pytest.approx(1.4271567082073118)
    assert (est.n, est.reason) == (60, None)
    assert bm.beta(BOT, IDX).value == pytest.approx(0.5860686561580911)
    assert bm.beta(BOT, IDX).se == pytest.approx(0.03702029864741104)


def test_alpha_needs_sixty_sessions():
    est = bm.alpha(BOT[:59], IDX[:59])
    assert (est.value, est.se, est.t, est.n, est.reason) == (None, None, None, 59, "needs ≥ 60 sessions")


def test_an_exact_linear_fit_has_zero_error():
    idx = IDX
    bot = [0.002 + 0.5 * x for x in idx]
    assert bm.beta(bot, idx).value == pytest.approx(0.5)
    assert bm.beta(bot, idx).se == pytest.approx(0.0, abs=1e-9)
    assert bm.alpha(bot, idx).value == pytest.approx(0.504)


def test_capture_sum_ratio_and_beat_count():
    cap = bm.capture(BOT, IDX)
    assert (cap.up_n, cap.down_n, cap.reason) == (31, 29, None)
    assert cap.up == pytest.approx(0.6186249784112493)
    assert cap.down == pytest.approx(0.4932598706459592)
    assert cap.ratio == pytest.approx(1.2541563083190115)
    assert bm.beat_count(BOT, IDX) == bm.BeatCount(up_days=31, up_beat=7, down_days=29, down_beat=26)


def test_flat_index_days_are_excluded_from_capture_and_beat():
    bot, idx = BOT + [0.05, -0.05], IDX + [0.0, 0.0]
    assert bm.capture(bot, idx) == bm.capture(BOT, IDX)
    assert bm.beat_count(bot, idx) == bm.beat_count(BOT, IDX)


def test_capture_needs_ten_sessions_each_side():
    cap = bm.capture([0.01] * 19, [0.01] * 10 + [-0.01] * 9)
    assert (cap.up, cap.down, cap.ratio, cap.up_n, cap.down_n) == (None, None, None, 10, 9)
    assert cap.reason == bm.CAPTURE_REASON == "needs ≥ 10 index-up and ≥ 10 index-down sessions"


def test_an_all_flat_index_has_no_capture():
    cap = bm.capture([0.01] * 30, [0.0] * 30)
    assert (cap.up, cap.ratio, cap.up_n, cap.down_n, cap.reason) == (None, None, 0, 0, bm.CAPTURE_REASON)


@pytest.mark.parametrize("fn", [bm.beta, bm.alpha, bm.capture, bm.beat_count])
def test_paired_functions_reject_mismatched_lengths(fn):
    with pytest.raises(ValueError):
        fn([0.01, 0.02], [0.01])
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_benchmark_stats.py`
Expected: FAIL — `ImportError: cannot import name 'benchmark' from 'swingbot.core.analytics'`.

- [ ] **Step 3: Create `swingbot/core/analytics/benchmark.py`**

Module docstring: v208; pure, no I/O; fractions in and out; rf = 0; the
guards and why (spec § Small-sample guard); "alpha is descriptive, never
edge". Names and definitions as in the Interfaces block and the table.

The one algorithm the table leaves open is the shared OLS helper; both
`beta` and `alpha` call it after their own `n` guard:

```python
_EPS = 1e-15


def _ols(y: Sequence[float], x: Sequence[float]) -> tuple[float, float, float, float] | None:
    """(slope, intercept, slope_se, intercept_se) of y on x; None when x has no variance."""
    n = len(x)
    mx, my = math.fsum(x) / n, math.fsum(y) / n
    sxx = math.fsum((a - mx) ** 2 for a in x)
    if sxx <= _EPS:
        return None
    slope = math.fsum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx
    intercept = my - slope * mx
    s2 = math.fsum((b - intercept - slope * a) ** 2 for a, b in zip(x, y)) / (n - 2)
    return slope, intercept, math.sqrt(s2 / sxx), math.sqrt(s2 * (1 / n + mx * mx / sxx))
```

`_t(value, se) -> float | None` returns `value / se` when `se > _EPS`, else
`None`. `_paired(bot, idx)` raises `ValueError("bot and idx differ in length")`
and is the first line of every paired function. `_sides(bot, idx)` splits the
pairs into up and down lists once, for `capture` and `beat_count`. Sharpe uses
`statistics.mean` / `statistics.stdev` (ddof = 1). Every function stays far
below complexity 15.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_benchmark_stats.py`
Expected: `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; nothing in `swingbot/core/analytics/benchmark.py` reported.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/benchmark.py tests/analytics/test_benchmark_stats.py
git commit -m "feat(v208): benchmark stats -- total, drawdowns, Sharpe, beta/alpha with SE, capture, guards (V208-7)"
```
