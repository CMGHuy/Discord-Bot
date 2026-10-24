# v183 Part 3 — Squeeze and event notice: cache, daily refresh, snapshot, one wording, plan page

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md](../specs/2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md)
**Index:** [2026-10-21-v183-short-gap-sizing-and-squeeze-notice_0-index.md](2026-10-21-v183-short-gap-sizing-and-squeeze-notice_0-index.md) — Goal, Architecture, Global Constraints, Contracts, Review Focus, Parallelisation and the task ledger live there; every task here implicitly includes the index's Global Constraints.

**Worktree:** every command below runs from `.claude/worktrees/2026-10-21-v183-short-gap-sizing-and-squeeze-notice` (created in V183-1 Step 1). Never edit the main tree; never touch v182 plan files.

**Scope of this part:** V183-10..V183-15. Spec sections: Part B (applies to, lines 1–4, data, coverage and misses, snapshot, never used by a decision), panel additions "Never stops a scan or an alert", "Off switch", "Earnings line carries the distance", "Refresh owner", Storage (snapshot is its own plan field, never `entry_context`), and the tests "Notice: …" and "One channel-parity test".

**Decisions this part fixes (within the spec's "left to the builder"):**
- **Cache:** a file, `data/short_interest.json`, plus a miss queue `data/short_interest_queue.json`, both written with `atomic_write_json`. No table, so no Alembic revision.
- **Refresh:** a new bot loop `daily_short_interest_refresh`, Mon–Fri 23:40 Berlin (always after the 16:00 ET close, including the DST-mismatch weeks; clear of `daily_recap` at 23:15). It is skipped while `SHORT_RISK_NOTICE` is off.
- **Snapshot extras:** beyond the index's shape, `short_interest` also carries `"squeeze": bool`, decided at snapshot time from the thresholds in force then. So a later threshold change never makes the plan page disagree with the alert. `squeeze_tripped(si)` reads that key when it is present.
- **Earnings source:** `earnings_calendar.CachedSource` only, so it never goes to the network. A ticker the cache does not know prints `Earnings: not checked`; that is the spec's honest miss, not a bug.

# Phase 1 — Short-interest data off the scan path

### Task V183-10: Short-interest cache: parse, fetch, refresh, cached read

**Model:** sonnet — a new self-contained module with fixed field conversions and a file-cache pattern copied from `earnings_history.py`.

**Files:**
- Create: `swingbot/core/market/short_interest.py`
- Create: `tests/market/test_short_interest.py` (existing directory, suite `marketdata`; `tests/suites.toml` is not edited)

**Interfaces:**
- Consumes: `config.DATA_DIR`; `swingbot.core.infra.jsonio.atomic_write_json(path, obj)` / `read_json(path, default)`; `swingbot.core.marketdata.watchlist.load_watchlist()`; `swingbot.core.marketdata.universe.short_snapshot(day, live=True)` (`.symbols`); `PlanStore().open_plans()`; `TradeLog().get_trades(status="open", limit=None)`.
- Produces (index Contracts, exact):
  - `CACHE_NAME = "short_interest.json"`, `QUEUE_NAME = "short_interest_queue.json"`, `STALE_DAYS = 21`
  - `class ShortInterestCacheError(Exception)`
  - `parse_info(info: dict, *, today: dt.date) -> dict` with the keys `short_pct_float`, `days_to_cover`, `float_shares`, `si_date`, `ex_div_date`, `div_per_share`, `div_estimated`, `fetched_at`
  - `fetch_short_interest(ticker) -> dict`, `refresh_short_interest(symbols, *, now=None, fetch=None) -> {"updated": int, "failed": list[str]}`
  - `cached_short_interest(ticker) -> dict | None` (disk only; raises `ShortInterestCacheError` on an unreadable file)
  - `request_refresh(ticker) -> None` (never raises), `refresh_symbols() -> list[str]`
  - V183-11 calls `refresh_symbols` and `refresh_short_interest`. V183-12 calls `cached_short_interest` and `request_refresh`.

**Field mapping (yfinance `.info`; Step 5 verifies the names against a live `.info` once at build time, Review Focus 3):**

| Output key | Source | Conversion |
|---|---|---|
| `short_pct_float` | `shortPercentOfFloat`, else `sharesShort / floatShares` | fraction × 100, rounded to 1 dp (0.182 → 18.2) |
| `days_to_cover` | `shortRatio` | float, 1 dp |
| `float_shares` | `floatShares` | float |
| `si_date` | `dateShortInterest` | epoch seconds → UTC date, ISO |
| `ex_div_date` | `exDividendDate` | epoch seconds → UTC date, ISO |
| `div_per_share` | `lastDividendValue` | float |
| `div_estimated` | — | `True` when `ex_div_date ≥ today` and `lastDividendDate` (epoch → date) ≠ `ex_div_date`: the amount is the last payment's, not the announced one |

A value that is absent, not a number (a `bool` counts as not a number), NaN, or `≤ 0` maps to `None`. Nothing defaults to 0 (spec anti-goal).

- [ ] **Step 1: Write the failing test** — `tests/market/test_short_interest.py`

```python
"""V183-10: the short-interest cache -- parse yfinance .info, refresh off the
scan path, read disk only, never fabricate a value."""
import datetime as dt
import json

import pytest

from swingbot import config
from swingbot.core.market import short_interest as si

TODAY = dt.date(2026, 10, 21)
NOW = dt.datetime(2026, 10, 21, 21, 40, tzinfo=dt.timezone.utc)


def _epoch(day: str) -> int:
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())


INFO = {"shortPercentOfFloat": 0.182, "shortRatio": 4.08, "floatShares": 45_300_000,
        "sharesShort": 8_244_600, "dateShortInterest": _epoch("2026-10-15"),
        "exDividendDate": _epoch("2026-10-24"), "lastDividendValue": 0.42,
        "lastDividendDate": _epoch("2026-07-24")}


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def _parsed(ticker):
    return si.parse_info(INFO, today=TODAY)


def test_parse_info_converts_fraction_and_epoch_fields():
    out = si.parse_info(INFO, today=TODAY)
    assert out["short_pct_float"] == 18.2                 # never 0.2
    assert out["days_to_cover"] == 4.1
    assert out["float_shares"] == 45_300_000.0
    assert out["si_date"] == "2026-10-15"                  # never a raw integer
    assert out["ex_div_date"] == "2026-10-24"
    assert out["div_per_share"] == 0.42 and out["div_estimated"] is True
    assert dt.datetime.fromisoformat(out["fetched_at"]).tzinfo is not None


def test_parse_info_falls_back_to_shares_short_over_float():
    out = si.parse_info({**INFO, "shortPercentOfFloat": None}, today=TODAY)
    assert out["short_pct_float"] == 18.2


def test_announced_dividend_is_not_an_estimate():
    out = si.parse_info({**INFO, "lastDividendDate": INFO["exDividendDate"]}, today=TODAY)
    assert out["div_estimated"] is False


@pytest.mark.parametrize("bad", [None, "n/a", float("nan"), 0, -1, True])
def test_every_missing_or_unusable_field_is_none_never_zero(bad):
    out = si.parse_info({key: bad for key in INFO}, today=TODAY)
    for key in ("short_pct_float", "days_to_cover", "float_shares", "si_date",
                "ex_div_date", "div_per_share"):
        assert out[key] is None, key
    assert out["div_estimated"] is False


def test_refresh_writes_the_cache_and_keeps_old_entries_on_failure():
    def fetch(ticker):
        if ticker == "BAD":
            raise RuntimeError("yahoo 429")
        return _parsed(ticker)

    assert si.refresh_short_interest(["gme", "BAD"], now=NOW, fetch=fetch) == {"updated": 1, "failed": ["BAD"]}
    assert si.cached_short_interest("GME")["short_pct_float"] == 18.2
    assert si.cached_short_interest("BAD") is None

    assert si.refresh_short_interest(["GME"], now=NOW, fetch=lambda t: 1 / 0) == {"updated": 0, "failed": ["GME"]}
    assert si.cached_short_interest("gme")["short_pct_float"] == 18.2        # kept, case-insensitive


def test_cached_read_is_none_on_a_miss_and_raises_on_a_corrupt_file(_data_dir):
    assert si.cached_short_interest("GME") is None                          # no file yet
    (_data_dir / si.CACHE_NAME).write_text("{half-written", encoding="utf-8")
    with pytest.raises(si.ShortInterestCacheError):
        si.cached_short_interest("GME")


def test_a_corrupt_cache_does_not_stop_the_refresh(_data_dir):
    (_data_dir / si.CACHE_NAME).write_text("[]", encoding="utf-8")         # wrong shape
    assert si.refresh_short_interest(["GME"], now=NOW, fetch=_parsed)["updated"] == 1
    assert si.cached_short_interest("GME") is not None


def test_cached_read_never_fetches(monkeypatch):
    monkeypatch.setattr(si, "fetch_short_interest", lambda t: pytest.fail("network on the alert path"))
    assert si.cached_short_interest("GME") is None


def test_a_miss_is_queued_and_cleared_by_the_next_refresh(_data_dir, monkeypatch):
    monkeypatch.setattr(si, "_watchlist", lambda: ["AAPL"])
    monkeypatch.setattr(si, "_short_universe", lambda today: ["XOM"])
    monkeypatch.setattr(si, "_open_short_tickers", lambda: ["TSLA", "AAPL"])
    si.request_refresh("rivn")
    assert si.refresh_symbols() == ["AAPL", "RIVN", "TSLA", "XOM"]
    si.refresh_short_interest(["RIVN"], now=NOW, fetch=_parsed)
    assert "RIVN" not in json.loads((_data_dir / si.QUEUE_NAME).read_text(encoding="utf-8"))


def test_request_refresh_never_raises(monkeypatch):
    def boom(*args):
        raise OSError("disk full")
    monkeypatch.setattr(si, "atomic_write_json", boom)
    si.request_refresh("GME")                                               # no exception


def test_refresh_symbols_survives_a_failing_source(monkeypatch):
    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(si, "_watchlist", boom)
    monkeypatch.setattr(si, "_short_universe", lambda today: ["XOM"])
    monkeypatch.setattr(si, "_open_short_tickers", lambda: [])
    assert si.refresh_symbols() == ["XOM"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_short_interest.py`
Expected: FAIL — `ImportError: cannot import name 'short_interest' from 'swingbot.core.market'`.

- [ ] **Step 3: Create `swingbot/core/market/short_interest.py`**

The module docstring says three things. This is the v183 squeeze-notice cache. The alert path only ever calls `cached_short_interest` and `request_refresh`, and only the daily loop calls `fetch_short_interest`. Nothing here feeds a filter, a score or a backtest.

Import `atomic_write_json` and `read_json` by name at module level, so the test can patch `si.atomic_write_json`. Module-level `log`, `_QUEUE_LOCK = threading.Lock()` and `_path(name) -> os.path.join(config.DATA_DIR, name)`.

- `_num(value) -> float | None`: `None` unless the value is an `int`/`float` that is not a `bool`, is finite, and is `> 0`.
- `_epoch_date(value) -> str | None`: `_num` first, then `dt.datetime.fromtimestamp(v, dt.timezone.utc).date().isoformat()`. `None` on `OverflowError`/`OSError`/`ValueError`.
- `_short_pct(info) -> float | None`: `shortPercentOfFloat × 100`, else `sharesShort / floatShares × 100`, rounded to 1 dp.
- `_div_estimated(ex_div: str | None, last_div: str | None, today: dt.date) -> bool`.
- `parse_info(info, *, today)`: builds the dict per the table above, with `fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()`.
- `fetch_short_interest(ticker)`: `import yfinance as yf` inside the function, then `parse_info(yf.Ticker(ticker).info or {}, today=dt.date.today())`. Exceptions propagate; the refresh counts them.
- `_read_cache() -> dict`:
  - `open` + `json.load`. `FileNotFoundError` → `{}`.
  - Any other `OSError`/`ValueError`/`UnicodeDecodeError`, or a body that is not a dict → `raise ShortInterestCacheError(str(exc))`.
  - Do not use `read_json` here. It swallows corruption, and Review Focus 4 needs the error to reach V183-12's degrade path.
- `refresh_short_interest(symbols, *, now=None, fetch=None)`:
  - `fetch = fetch or fetch_short_interest`. Upper-case, strip, dedupe and sort the symbols.
  - Start from `_read_cache().get("symbols", {})`. On `ShortInterestCacheError`, start from `{}` and log one warning.
  - Fetch with `ThreadPoolExecutor(max_workers=4)`. Yahoo rate-limits `.info`, so stay at 4.
  - A failure keeps the old entry and appends the symbol to `failed`, which is sorted.
  - Write `{"updated_at": now.isoformat(), "symbols": {...}}` with `atomic_write_json`. Then, under `_QUEUE_LOCK`, drop the updated symbols from the queue file.
- `cached_short_interest(ticker)`: `_read_cache().get("symbols", {}).get(ticker.upper().strip())`, or `None` unless that is a dict.
- `request_refresh(ticker)`: under `_QUEUE_LOCK`, read the queue list with `read_json(path, [])`, add the upper-cased ticker, and write it back. The whole body sits in `try/except Exception` with `swallowed(log, "short_interest.queue", exc, level=logging.DEBUG)`; it never raises.
- One source each: `_watchlist()`, `_short_universe(today: dt.date)`, `_open_short_tickers()`, `_queued()`.
  - `_short_universe` returns `universe.short_snapshot(today.isoformat(), live=True).symbols`, or `[]` when the snapshot is `None` (the lane is skipped that day).
  - `_open_short_tickers` returns the `"bearish"` tickers of `PlanStore().open_plans()` and of `TradeLog().get_trades(status="open", limit=None)`. Import both inside the function, so `market` does not import `planning`/`tracking` at load.
- `refresh_symbols()`: the sorted, upper-cased union of the four sources. Each source call sits in its own `try/except` that logs one warning and contributes `[]`.

Every function stays below complexity 15.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/market/test_short_interest.py`
Expected: PASS (16 tests).

- [ ] **Step 5: Verify the live field names once (read-only, network)**

Run: `python -c "import yfinance as yf; i = yf.Ticker('GME').info; print({k: i.get(k) for k in ('shortPercentOfFloat','shortRatio','floatShares','sharesShort','dateShortInterest','exDividendDate','lastDividendValue','lastDividendDate')})"`
Expected: the keys exist, `shortPercentOfFloat` is a fraction below 1, and the dates are epoch integers. If a name or unit differs, fix `parse_info` and its test, and record the real name in the commit message.

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/short_interest.py tests/market/test_short_interest.py
git commit -m "feat(v183): short-interest cache -- parse yfinance info, refresh, disk-only read (V183-10)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V183-11: Daily short-interest refresh loop

**Model:** sonnet — one scheduled loop copied from `weekly_earnings_refresh`, plus registration and a restart-safety test.

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (module global beside `_earnings_refresh_fired_date` :732; the new loop directly below `weekly_earnings_refresh` :965-987; `_always_on_loops` :1229)
- Modify: `swingbot/commands/scanning/__init__.py` (the `from .loops import (...)` block :11-21 and `__all__` :24-30)
- Modify: `tests/commands/test_scheduled_jobs.py` (append tests)

**Interfaces:**
- Consumes (V183-10): `short_interest.refresh_symbols() -> list[str]`, `short_interest.refresh_short_interest(symbols, *, now=None, fetch=None) -> {"updated": int, "failed": list[str]}`. Consumes (V183-1): `config.SHORT_RISK_NOTICE`. Existing: `_scheduled_job_already_fired(job, today)`, `_mark_scheduled_job_fired(job, today)`, `SESSION_TZ` (Berlin).
- Produces: `loops.daily_short_interest_refresh` (a `tasks.loop(minutes=1)`), re-exported from `swingbot.commands.scanning`; the module global `_short_interest_refresh_fired_date: dt.date | None`; the scheduler job name `"daily_short_interest_refresh"`.

**Schedule (decided here, spec "Refresh owner"):** Monday to Friday at 23:40 Berlin. The US close is 22:00 Berlin, or 21:00 during the DST-mismatch weeks, so 23:40 is always after it. It also stays clear of `daily_recap` at 23:15. It runs in `asyncio.to_thread`, so the refresh never blocks the event loop or the scan. While `SHORT_RISK_NOTICE` is off it marks the day fired, logs one line and fetches nothing. The loop lives as long as Part B does and is removed with it.

- [ ] **Step 1: Write the failing tests** — append to `tests/commands/test_scheduled_jobs.py`

```python
def _fixed(now):
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)
    return FixedDateTime


def _short_interest_stubs(monkeypatch, calls):
    from swingbot.core.market import short_interest
    monkeypatch.setattr(short_interest, "refresh_symbols", lambda: ["GME", "TSLA"])
    monkeypatch.setattr(short_interest, "refresh_short_interest",
                        lambda symbols: calls.append(symbols) or {"updated": 2, "failed": []})
    monkeypatch.setattr(loops_mod, "_short_interest_refresh_fired_date", None)


def test_daily_short_interest_refresh_runs_once_after_the_close(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", True)
    monkeypatch.setattr(loops_mod.dt, "datetime", _fixed(dt.datetime(2026, 10, 21, 23, 40)))  # Wednesday
    _short_interest_stubs(monkeypatch, calls)

    asyncio.run(scanning_mod.daily_short_interest_refresh.coro())
    monkeypatch.setattr(loops_mod, "_short_interest_refresh_fired_date", None)   # simulated restart
    asyncio.run(scanning_mod.daily_short_interest_refresh.coro())

    assert calls == [["GME", "TSLA"]]
    assert scheduled_repo().fired_on("daily_short_interest_refresh") == "2026-10-21"


def test_daily_short_interest_refresh_skips_weekends_and_other_minutes(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", True)
    _short_interest_stubs(monkeypatch, calls)
    for now in (dt.datetime(2026, 10, 24, 23, 40),      # Saturday
                dt.datetime(2026, 10, 21, 23, 39),
                dt.datetime(2026, 10, 21, 22, 40)):
        monkeypatch.setattr(loops_mod.dt, "datetime", _fixed(now))
        asyncio.run(scanning_mod.daily_short_interest_refresh.coro())
    assert calls == []


def test_daily_short_interest_refresh_fetches_nothing_while_the_notice_is_off(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", False)
    monkeypatch.setattr(loops_mod.dt, "datetime", _fixed(dt.datetime(2026, 10, 22, 23, 40)))
    _short_interest_stubs(monkeypatch, calls)
    asyncio.run(scanning_mod.daily_short_interest_refresh.coro())
    assert calls == []


def test_a_failed_short_interest_refresh_is_logged_not_raised(monkeypatch, caplog):
    from swingbot.core.market import short_interest
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", True)
    monkeypatch.setattr(loops_mod.dt, "datetime", _fixed(dt.datetime(2026, 10, 23, 23, 40)))
    monkeypatch.setattr(loops_mod, "_short_interest_refresh_fired_date", None)
    monkeypatch.setattr(short_interest, "refresh_symbols", lambda: ["GME"])

    def boom(symbols):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(short_interest, "refresh_short_interest", boom)
    asyncio.run(scanning_mod.daily_short_interest_refresh.coro())      # no exception
    assert "daily_short_interest_refresh: refresh failed" in caplog.text


def test_daily_short_interest_refresh_is_always_on_and_tape_feed_stays_last():
    loops = loops_mod._always_on_loops()
    assert loops.index(loops_mod.daily_short_interest_refresh) == loops.index(loops_mod.weekly_earnings_refresh) + 1
    assert loops[-1] is loops_mod.tape_feed
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_scheduled_jobs.py`
Expected: FAIL — `AttributeError: module 'swingbot.commands.scanning' has no attribute 'daily_short_interest_refresh'`. The two existing tests still pass.

- [ ] **Step 3: Add the loop to `swingbot/commands/scanning/loops.py`**

Beside `_earnings_refresh_fired_date: dt.date | None = None` (:732), add `_short_interest_refresh_fired_date: dt.date | None = None`. Directly below `weekly_earnings_refresh`, add:

```python
_SHORT_INTEREST_REFRESH_AT = (23, 40)   # Berlin; always after the 16:00 ET close


@tasks.loop(minutes=1)
async def daily_short_interest_refresh():
    """v183 Part B: refresh the short-interest / float / ex-div cache once per
    weekday after the US close, off the scan path. The alert only reads the
    cache (short_interest.cached_short_interest); a failure here leaves the
    old entries and every short's notice degrades to "not checked"."""
    global _short_interest_refresh_fired_date
    now = dt.datetime.now(SESSION_TZ)
    if now.weekday() >= 5 or (now.hour, now.minute) != _SHORT_INTEREST_REFRESH_AT:
        return
    today = now.date()
    if (_short_interest_refresh_fired_date == today
            or _scheduled_job_already_fired('daily_short_interest_refresh', today)):
        return
    _short_interest_refresh_fired_date = today
    _mark_scheduled_job_fired('daily_short_interest_refresh', today)
    if not config.SHORT_RISK_NOTICE:
        log.info("daily_short_interest_refresh: SHORT_RISK_NOTICE is off -- skipped")
        return
    try:
        from swingbot.core.market import short_interest
        symbols = await asyncio.to_thread(short_interest.refresh_symbols)
        result = await asyncio.to_thread(short_interest.refresh_short_interest, symbols)
        log.info("daily_short_interest_refresh: %d updated, %d failed of %d symbols",
                 result["updated"], len(result["failed"]), len(symbols))
    except Exception:
        log.exception("daily_short_interest_refresh: refresh failed")
```

In `_always_on_loops()`, insert `daily_short_interest_refresh` directly after `weekly_earnings_refresh`; `tape_feed` stays last.

- [ ] **Step 4: Re-export it from `swingbot/commands/scanning/__init__.py`**

Add `daily_short_interest_refresh,` to the `from .loops import (...)` block, in alphabetical position after `daily_recap,`. Add `"daily_short_interest_refresh"` to `__all__`, after `"daily_recap"`.

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/commands/test_scheduled_jobs.py`
Expected: PASS (7 tests).

Run, one at a time: `python scripts/dev/testrun.py file tests/commands/test_tape_feed_loop.py`, `... file tests/commands/test_daily_reanchor_loop.py`, `... file tests/commands/test_outlook_loops.py`
Expected: PASS (the loop-order assertions still hold).

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`daily_short_interest_refresh` scores about 8).

- [ ] **Step 7: Commit**

```bash
git add swingbot/commands/scanning/loops.py swingbot/commands/scanning/__init__.py tests/commands/test_scheduled_jobs.py
git commit -m "feat(v183): daily short-interest refresh loop after the close, off the scan path (V183-11)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 2 — The notice snapshot and its one wording

### Task V183-12: Notice snapshot at plan creation, degrade on failure

**Model:** opus — it defines the snapshot every channel and the plan page read. It runs inside plan creation, where it must never stop a scan. It carries the "no decision reads it" pin.

**Files:**
- Create: `swingbot/core/scanning/risk_notice.py`
- Create: `tests/scanning/test_risk_notice_snapshot.py`
- Modify: `swingbot/core/planning/plan_types.py` (new last field of `TradePlanV2`, after `gap_sizing`; `_OMIT_WHEN_NONE` becomes `("gap_sizing", "risk_notice")`)
- Modify: `swingbot/core/scanning/analyze.py` (import; new `_stamp_risk_notice_live` directly below `_stamp_gap_sizing_live`; one call in `attach_plan_v2` directly after `_stamp_gap_sizing_live(plan, df, now)`)
- Modify: `swingbot/core/scanning/strategy_pass.py` (import; one call in `build_strategy_plan_at` directly after `stamp_gap_sizing(plan, df_completed)`)

**Interfaces:**
- Consumes (V183-10): `short_interest.cached_short_interest(ticker)`, `short_interest.request_refresh(ticker)`, `short_interest.STALE_DAYS`, `short_interest.ShortInterestCacheError`. Consumes (V183-1): `config.SHORT_RISK_NOTICE`, `config.SHORT_SQUEEZE_SI_PCT`, `config.SHORT_SQUEEZE_DTC`. Consumes (V183-4): `_OMIT_WHEN_NONE`, `_stamp_gap_sizing_live`, and from `tests/planning/test_gap_sizing.py` the helpers `_plan`, `_signed_gaps`, `_attach`, `PRE_V183_PLAN_KEYS`. Existing: `earnings_calendar.CachedSource`, `next_report(ticker, asof, *, source, calendar=None)`, `nyse_calendar()`, `SessionCalendar.session_after/sessions_between`, `now_et`, `HORIZONS[h]["max_holding_days"]`, `strategy_pass.completed_frame(df, now)`.
- Produces (index Contracts):
  - `hold_window(plan, signal_date) -> (start, end)`
  - `build_risk_notice(plan, signal_date, *, now=None, source=None) -> dict`
  - `degraded_notice(plan, signal_date) -> dict`
  - `stamp_risk_notice(plan, df) -> None`
  - `TradePlanV2.risk_notice: dict | None = None`
  - V183-13 words the snapshot. V183-14 copies it onto the trade record and the plan-page API.

**Snapshot shape (version 1, exact):**

```python
{"version": 1, "built_at": "<iso utc>", "window": ["2026-11-20", "2026-12-18"],
 "si_status": "ok" | "not_checked",
 "short_interest": {**parse_info fields, "stale": bool, "squeeze": bool} | None,
 "earnings": {"status": "in_hold" | "none_in_hold" | "not_checked" | "etf",
              "date": "YYYY-MM-DD" | None, "sessions": int | None},
 "ex_div": {"date": "YYYY-MM-DD", "per_share": float | None, "estimated": bool} | None}
```

**Rules:**
- **Window.** It runs from the signal bar (the last completed bar) to `session_after(signal, expiry_bars + HORIZONS[h]["max_holding_days"])`. When that passes the calendar's end, the window ends at `calendar.last`. Counted in NYSE sessions (Review Focus 5).
- **`stale`.** True when `si_date` is missing or older than `STALE_DAYS` calendar days at build time.
- **`squeeze`.** True when `short_pct_float ≥ SHORT_SQUEEZE_SI_PCT` or `days_to_cover ≥ SHORT_SQUEEZE_DTC`, using the thresholds in force at build time. A `None` never trips.
- **Earnings.**
  - A fund or spot metal gets `etf`.
  - `CachedSource().reports(ticker) == []` gets `not_checked`.
  - Otherwise the next report from `next_report(ticker, start, …)` gets `in_hold` when `start ≤ report.date ≤ end`, with `sessions = sessions_between(start, report.date)`. An after-close report on the last held day therefore counts as in hold. Anything else gets `none_in_hold`.
- **Ex-div.** It comes from the same cache entry and is kept only when `start ≤ ex_div_date ≤ end`.
- **Cache miss or read error.** `si_status` becomes `not_checked`, `short_interest` is `None`, and a miss calls `request_refresh`. The earnings and window parts are still built, each in its own `try`.
- **Any other exception** in `build_risk_notice` makes `stamp_risk_notice` store `degraded_notice` and log `"%s: risk notice degraded (%s)"` at INFO. It never raises (spec "Never stops a scan or an alert", Review Focus 4).
- **Who gets a snapshot.** It is stamped only when `plan.direction == "bearish"` and `config.SHORT_RISK_NOTICE` is on. Otherwise `plan.risk_notice` stays `None`, so long plan docs and switch-off shorts stay byte-identical (`_OMIT_WHEN_NONE`).

- [ ] **Step 1: Write the failing test** — `tests/scanning/test_risk_notice_snapshot.py`

```python
"""V183-12: the squeeze/event snapshot stamped on a short at creation."""
import datetime as dt
import logging
import pathlib
import re

import pytest

from swingbot import config
from swingbot.core.market import short_interest as si_mod
from swingbot.core.market.earnings_calendar import AFTER_CLOSE, BEFORE_OPEN, Report
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from swingbot.core.scanning import risk_notice as rn
from tests.planning.test_gap_sizing import PRE_V183_PLAN_KEYS, _attach, _plan, _signed_gaps

SIGNAL = dt.date(2026, 11, 20)                      # Friday before Thanksgiving week
NOW = dt.datetime(2026, 11, 23, 14, 0, tzinfo=dt.timezone.utc)
SI = {"short_pct_float": 18.2, "days_to_cover": 4.1, "float_shares": 45_300_000.0,
      "si_date": "2026-11-13", "ex_div_date": "2026-11-24", "div_per_share": 0.42,
      "div_estimated": True, "fetched_at": "2026-11-20T22:40:00+00:00"}


class Source:
    def __init__(self, *reports):
        self._reports = list(reports)

    def reports(self, ticker):
        return list(self._reports)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", True)
    monkeypatch.setattr(config, "SHORT_SQUEEZE_SI_PCT", 10.0)
    monkeypatch.setattr(config, "SHORT_SQUEEZE_DTC", 5.0)
    monkeypatch.setattr(rn, "_never_reports", lambda ticker: False)
    monkeypatch.setattr(rn, "_earnings_source", lambda: Source())     # never the real data/ ledger
    monkeypatch.setattr(si_mod, "cached_short_interest", lambda ticker: dict(SI))
    monkeypatch.setattr(si_mod, "request_refresh", lambda ticker: None)


def _short(**kw):
    return _plan(horizon_key="2w", expiry_bars=5, **kw)


def _build(source=None, **kw):
    return rn.build_risk_notice(_short(**kw), SIGNAL, now=NOW, source=source or Source())


def test_hold_window_counts_nyse_sessions_across_thanksgiving():
    assert rn.hold_window(_short(), SIGNAL) == (SIGNAL, dt.date(2026, 12, 18))   # 5 + 14 sessions


def test_hold_window_past_the_calendar_ends_at_its_last_session():
    start, end = rn.hold_window(_plan(horizon_key="9m", expiry_bars=5), dt.date(2030, 11, 1))
    assert (start, end) == (dt.date(2030, 11, 1), rn.nyse_calendar().last)


def test_snapshot_shape_and_squeeze_on_short_interest():
    snap = _build(Source(Report(dt.date(2026, 11, 30), BEFORE_OPEN)))
    assert snap["version"] == 1 and snap["window"] == ["2026-11-20", "2026-12-18"]
    assert snap["si_status"] == "ok"
    assert snap["short_interest"]["squeeze"] is True and snap["short_interest"]["stale"] is False
    assert snap["earnings"] == {"status": "in_hold", "date": "2026-11-30", "sessions": 5}
    assert snap["ex_div"] == {"date": "2026-11-24", "per_share": 0.42, "estimated": True}


@pytest.mark.parametrize("si,squeeze", [
    ({"short_pct_float": 4.0, "days_to_cover": 6.0}, True),       # days to cover alone
    ({"short_pct_float": 10.0, "days_to_cover": 1.0}, True),      # at the SI threshold
    ({"short_pct_float": 9.9, "days_to_cover": 4.9}, False),      # below both
    ({"short_pct_float": None, "days_to_cover": None}, False),    # missing never trips
])
def test_squeeze_thresholds(monkeypatch, si, squeeze):
    monkeypatch.setattr(si_mod, "cached_short_interest", lambda ticker: {**SI, **si})
    assert _build()["short_interest"]["squeeze"] is squeeze


def test_short_interest_older_than_21_days_or_undated_is_stale(monkeypatch):
    monkeypatch.setattr(si_mod, "cached_short_interest", lambda t: {**SI, "si_date": "2026-11-01"})
    assert _build()["short_interest"]["stale"] is True
    monkeypatch.setattr(si_mod, "cached_short_interest", lambda t: {**SI, "si_date": "2026-11-02"})
    assert _build()["short_interest"]["stale"] is False
    monkeypatch.setattr(si_mod, "cached_short_interest", lambda t: {**SI, "si_date": None})
    assert _build()["short_interest"]["stale"] is True


def test_a_cache_miss_is_not_checked_and_queued(monkeypatch):
    queued = []
    monkeypatch.setattr(si_mod, "cached_short_interest", lambda t: None)
    monkeypatch.setattr(si_mod, "request_refresh", queued.append)
    snap = _build()
    assert (snap["si_status"], snap["short_interest"], snap["ex_div"]) == ("not_checked", None, None)
    assert queued == ["ZZZ"]


@pytest.mark.parametrize("reports,expected", [
    ((Report(dt.date(2026, 12, 18), AFTER_CLOSE),), ("in_hold", "2026-12-18", 19)),   # last held day
    ((Report(dt.date(2026, 12, 21), BEFORE_OPEN),), ("none_in_hold", None, None)),    # after the window
    ((), ("not_checked", None, None)),                                                # calendar has no data
])
def test_earnings_inside_outside_and_unknown(reports, expected):
    e = _build(Source(*reports))["earnings"]
    assert (e["status"], e["date"], e["sessions"]) == expected


def test_a_fund_is_marked_etf_never_none_in_hold(monkeypatch):
    monkeypatch.setattr(rn, "_never_reports", lambda ticker: True)
    assert _build()["earnings"]["status"] == "etf"


def test_ex_div_outside_the_window_is_omitted(monkeypatch):
    monkeypatch.setattr(si_mod, "cached_short_interest", lambda t: {**SI, "ex_div_date": "2026-12-22"})
    assert _build()["ex_div"] is None


def test_a_corrupt_cache_degrades_the_line_and_the_scan_carries_on(monkeypatch):
    def corrupt(ticker):
        raise si_mod.ShortInterestCacheError("Expecting value: line 1")
    monkeypatch.setattr(si_mod, "cached_short_interest", corrupt)
    plan = _attach(monkeypatch, _plan(stop_loss=101.5), _signed_gaps())
    assert plan is not None and plan.risk_notice["si_status"] == "not_checked"


def test_any_other_failure_stores_the_degraded_snapshot_and_never_raises(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="swingbot.core.scanning.risk_notice")
    monkeypatch.setattr(rn, "build_risk_notice", lambda *a, **k: 1 / 0)
    plan = _short()
    rn.stamp_risk_notice(plan, _signed_gaps(end="2026-11-20"))
    assert plan.risk_notice == rn.degraded_notice(plan, SIGNAL) | {"built_at": plan.risk_notice["built_at"]}
    assert plan.risk_notice["si_status"] == "not_checked"
    assert plan.risk_notice["earnings"]["status"] == "not_checked"
    assert "ZZZ: risk notice degraded (division by zero)" in caplog.text


def test_longs_and_switch_off_shorts_get_no_snapshot_and_keep_their_plan_doc(monkeypatch):
    long_ = _plan("bullish")
    rn.stamp_risk_notice(long_, _signed_gaps())
    assert long_.risk_notice is None and list(plan_to_dict(long_)) == PRE_V183_PLAN_KEYS
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", False)
    short = _short()
    rn.stamp_risk_notice(short, _signed_gaps())
    assert short.risk_notice is None and "risk_notice" not in plan_to_dict(short)


def test_snapshot_round_trips_as_its_own_plan_field_never_entry_context():
    plan = _short()
    rn.stamp_risk_notice(plan, _signed_gaps(end="2026-11-20"))
    doc = plan_to_dict(plan)
    assert list(doc)[-1] == "risk_notice" and "risk_notice" not in doc["entry_context"]
    assert plan_from_dict(doc).risk_notice == plan.risk_notice


def test_both_live_sites_stamp_from_the_completed_frame(monkeypatch):
    from swingbot.core.scanning import strategy_pass as sp
    plan = _attach(monkeypatch, _plan(stop_loss=101.5), _signed_gaps(end="2026-11-20"))
    assert plan.risk_notice["window"][0] == "2026-11-20"
    monkeypatch.setattr(sp, "build_strategy_plan", lambda *a, **k: _plan(source="strategy"))
    monkeypatch.setattr(sp, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(sp, "stamp_cohort", lambda plan, state: None)
    monkeypatch.setattr(sp, "stamp_entry_context", lambda plan, df, asof: None)
    built = sp.build_strategy_plan_at(_signed_gaps(end="2026-11-20"), ticker="ZZZ", strategy="MACD",
                                      horizon_key="3m", direction="bearish", regime2_state="bear_quiet")
    assert built.risk_notice["si_status"] == "ok"


def test_no_scan_decision_changes_when_the_notice_data_changes(monkeypatch):
    """Same plan and item whether the cache says squeeze, calm or nothing."""
    outcomes = []
    for stub in ({**SI, "short_pct_float": 40.0}, {**SI, "short_pct_float": 1.0}, None):
        monkeypatch.setattr(si_mod, "cached_short_interest", lambda t, s=stub: s)
        plan = _attach(monkeypatch, _plan(stop_loss=101.5), _signed_gaps())
        doc = plan_to_dict(plan)
        doc.pop("risk_notice")
        doc.pop("issued_at")                       # wall-clock stamp, differs per call
        outcomes.append(doc)
    assert outcomes[0] == outcomes[1] == outcomes[2]


ALLOWED_READERS = {
    "swingbot/core/scanning/risk_notice.py", "swingbot/core/scanning/analyze.py",
    "swingbot/core/scanning/strategy_pass.py", "swingbot/core/planning/plan_types.py",
    "swingbot/core/presentation/short_notice.py", "swingbot/core/infra/notifier.py",
    "swingbot/core/tracking/performance.py", "swingbot/core/scanning/scan_run.py",
    "swingbot/core/scanning/short_run.py", "swingbot/core/planning/plan_manager.py",
    "swingbot/admin/api_v1/trades.py",
}


def test_only_display_and_plumbing_modules_touch_the_notice():
    """Never a filter, score, confidence or backtest input (spec Part B)."""
    root = pathlib.Path(__file__).resolve().parents[2]
    readers = {p.relative_to(root).as_posix() for p in (root / "swingbot").rglob("*.py")
               if re.search(r"risk_notice|short_interest", p.read_text(encoding="utf-8"))}
    readers.discard("swingbot/core/market/short_interest.py")
    readers.discard("swingbot/commands/scanning/loops.py")
    readers.discard("swingbot/config.py")
    assert readers <= ALLOWED_READERS, sorted(readers - ALLOWED_READERS)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_risk_notice_snapshot.py`
Expected: FAIL — `ImportError: cannot import name 'risk_notice' from 'swingbot.core.scanning'`.

- [ ] **Step 3: Create `swingbot/core/scanning/risk_notice.py`**

The module docstring says that this builds the v183 Part B snapshot at live plan creation, reads caches only (never the network), and is never read by a filter, score, confidence or backtest.

Import the module (`from swingbot.core.market import short_interest as si_mod`) and call `si_mod.cached_short_interest` / `si_mod.request_refresh` through it, so tests patch one place. Import `nyse_calendar`, `now_et` from `swingbot.core.market.session`. Import `CachedSource`, `next_report` from `earnings_calendar`, and `HORIZONS` from `strategy_types`.

| Function | Body (the decisions; each stays under complexity 15) |
|---|---|
| `_never_reports(ticker) -> bool` | `universe.is_etf(ticker) or spot_metals.is_spot_metal(ticker)`, the same rule `events._never_reports` uses |
| `_earnings_source()` | `CachedSource()` |
| `hold_window(plan, signal_date)` | `cal = nyse_calendar()`; `n = int(plan.expiry_bars or 0) + int(HORIZONS[plan.horizon_key]["max_holding_days"])`; `end = cal.session_after(signal_date, n) or cal.last`; return `(signal_date, end)` |
| `_short_interest_part(ticker, today) -> (status, dict \| None)` | the cache read in `try`: `ShortInterestCacheError` or any `Exception` → `("not_checked", None)`; a miss → `request_refresh(ticker)` then `("not_checked", None)`; a hit → `("ok", {**entry, "stale": …, "squeeze": …})` |
| `_is_stale(si_date, today) -> bool` | `True` for `None` or an unparsable date; else `(today - date).days > si_mod.STALE_DAYS` |
| `_squeeze(entry) -> bool` | the threshold rule, with `None` never tripping |
| `_earnings_part(ticker, start, end, source) -> dict` | the rule above; `{"status": …, "date": iso \| None, "sessions": int \| None}` |
| `_ex_div_part(entry, start, end) -> dict \| None` | the window rule above |
| `build_risk_notice(plan, signal_date, *, now=None, source=None)` | `now = now or datetime.now(timezone.utc)`; `today = now_et(now).date()`; window; the short-interest part; the earnings part in its own `try` (→ `not_checked` on exception); the ex-div part from the short-interest entry; assembled into the version-1 shape |
| `degraded_notice(plan, signal_date)` | the version-1 shape with `window [signal_date.isoformat(), None]`, `si_status "not_checked"`, `short_interest None`, earnings `not_checked`, `ex_div None`, `built_at` now. It uses nothing that can raise. |
| `_signal_date(plan, df) -> date` | `df.index[-1].date()` when `df` has rows, else `date.fromisoformat(str(plan.created_at)[:10])`, else today ET |
| `stamp_risk_notice(plan, df)` | returns at once unless bearish and `config.SHORT_RISK_NOTICE`; else `try: plan.risk_notice = build_risk_notice(plan, signal)`, `except Exception as exc: log.info("%s: risk notice degraded (%s)", plan.ticker, exc); plan.risk_notice = degraded_notice(plan, signal)` |

- [ ] **Step 4: Add the field and the omission to `swingbot/core/planning/plan_types.py`**

As the last field of `TradePlanV2`, after `gap_sizing`:

```python
    # v183 Part B (scanning/risk_notice.py): the squeeze / earnings / ex-div
    # snapshot shown on the alert and the plan page, stamped at LIVE creation
    # for shorts while SHORT_RISK_NOTICE is on. Live-only data, so never an
    # entry_context key; never read by a filter, score or backtest.
    # Omitted from plan_to_dict while None (_OMIT_WHEN_NONE).
    risk_notice: dict | None = None
```

Change `_OMIT_WHEN_NONE = ("gap_sizing",)` to `_OMIT_WHEN_NONE = ("gap_sizing", "risk_notice")`.

- [ ] **Step 5: Stamp at the two live creation sites**

In `swingbot/core/scanning/analyze.py`, import `from swingbot.core.scanning.risk_notice import stamp_risk_notice` beside the `stamp_gap_sizing` import. Directly below `_stamp_gap_sizing_live`, add `_stamp_risk_notice_live(plan, df, now) -> None`. It mirrors that helper: `completed_frame(df, now or datetime.now(timezone.utc))` in a `try` (→ `None`), then `stamp_risk_notice(plan, frame)`. In `attach_plan_v2`, directly after `_stamp_gap_sizing_live(plan, df, now)`, add `_stamp_risk_notice_live(plan, df, now)`.

In `swingbot/core/scanning/strategy_pass.py`, import `stamp_risk_notice` the same way. In `build_strategy_plan_at`, directly after `stamp_gap_sizing(plan, df_completed)`, add `stamp_risk_notice(plan, df_completed)`.

Do not touch `params.stamp_entry_context`, `edge/context.py` or `backtest_scenarios.py`.

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_risk_notice_snapshot.py`
Expected: PASS (21 tests).
Run, one at a time: `python scripts/dev/testrun.py file tests/planning/test_gap_sizing.py`, `... file tests/planning/test_plan_serialization.py`, `... file tests/scanning/test_live_context_stamp.py`, `... file tests/scanning/test_strategy_pass_emit.py`
Expected: PASS. `test_long_plan_doc_keeps_exactly_its_pre_v183_keys` still holds, because a long has no snapshot.

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `attach_plan_v2` gains one plain call (no branch), and `build_strategy_plan_at` stays at 3.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/scanning/risk_notice.py swingbot/core/planning/plan_types.py swingbot/core/scanning/analyze.py swingbot/core/scanning/strategy_pass.py tests/scanning/test_risk_notice_snapshot.py
git commit -m "feat(v183): squeeze/earnings/ex-div snapshot stamped on shorts at creation, degrades never raises (V183-12)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V183-13: One wording module: notice lines on every short alert

**Model:** opus — it fixes copy that four channels must reproduce exactly. It widens a gate that today leaves base-lane shorts without a notice, while longs and switch-off shorts must stay byte-identical.

**Files:**
- Modify: `swingbot/core/presentation/short_notice.py` (new constants and functions below `FIELD_NAME`; `alert_notice`)
- Modify: `swingbot/core/infra/notifier.py` (`_short_notice` :113-124, the gate only)
- Verify, no edit expected: `swingbot/core/scanning/alert_embeds.py`. `_short_notice_text` (:91) has no gate of its own; it passes everything to `alert_notice`, so the full embed (:193) and the simple mirror (:364) pick up the lines through it. If the implementer finds a gate there, widen it with `has_risk_notice` exactly as in `notifier`.
- Create: `tests/presentation/test_risk_notice_lines.py`
- Modify: `tests/scanning/test_short_alert_parity.py` (append tests)

**Interfaces:**
- Consumes (V183-12): the version-1 snapshot shape and `TradePlanV2.risk_notice`. Consumes (V183-1): nothing at render time. The squeeze decision is the snapshot's `short_interest["squeeze"]`, fixed when the alert went out.
- Produces (index Contracts):
  - `SQUEEZE_PREFIX = "⚠ SQUEEZE RISK · "`, `SQUEEZE_NOT_CHECKED = "⚠ Squeeze data not checked — verify short interest at your broker"`, `EARNINGS_NOT_CHECKED = "Earnings: not checked"`
  - `squeeze_tripped(si: dict) -> bool`
  - `risk_notice_lines(snapshot: dict | None, *, currency: str = "$") -> list[str]`
  - `has_risk_notice(plan_v2) -> bool`
  - `alert_notice(...)`, which now appends the lines.
  - V183-14 builds the plan-page `risk_notice_lines` with `risk_notice_lines`, and nothing else words the notice (index § Channel parity).

**The copy (spec Part B lines 1–4, panel "Earnings line carries the distance"; exact):**

| Snapshot | Line |
|---|---|
| `si_status "ok"`, squeeze, fresh | `⚠ SQUEEZE RISK · Short interest 18.2% of float · 4.1 days to cover · float 45.3M (as of 2026-11-13)` |
| `si_status "ok"`, no squeeze, stale | `Short interest 3.0% of float · 1.2 days to cover · float 1.2B (as of 2026-09-30 · STALE)` |
| every short-interest field `None` | `Short interest n/a of float · n/a days to cover · float n/a (as of n/a · STALE)` |
| `si_status "not_checked"` | `⚠ Squeeze data not checked — verify short interest at your broker` |
| earnings `in_hold`, sessions 5 / 1 / 0 | `Earnings in hold: 2026-11-30 (in 5 sessions)` / `(in 1 session)` / `(on the signal bar)` |
| earnings `none_in_hold` | `No earnings in hold` |
| earnings `not_checked` | `Earnings: not checked` |
| earnings `etf` | `Earnings: n/a (ETF)` |
| ex-div with amount / estimated / no amount | `Ex-div in hold: 2026-11-24 · ~$0.42/sh owed` / `… owed (est.)` / `Ex-div in hold: 2026-11-24 · amount n/a` |
| `ex_div None` | (no line) |

The lines come in the order short interest, earnings, ex-div. Float formatting is `B` at 1e9 or more, `M` at 1e6 or more, and `K` at 1e3 or more, each with one decimal; below that it uses thousands separators. `alert_notice` returns, in this order: the existing text (the compression block, or the extra-lane notice, or nothing for a base alert), then the lines, then `CHECK BORROW AVAILABILITY`. That last line is added only when the existing text does not already contain it. The parts are joined with `"\n"`.

- [ ] **Step 1: Write the failing test** — `tests/presentation/test_risk_notice_lines.py`

```python
"""V183-13: the one wording of the squeeze/event notice."""
from types import SimpleNamespace

import pytest

from swingbot.core.presentation import short_notice as sn

SI = {"short_pct_float": 18.2, "days_to_cover": 4.1, "float_shares": 45_300_000.0,
      "si_date": "2026-11-13", "stale": False, "squeeze": True}
SNAP = {"version": 1, "built_at": "2026-11-23T14:00:00+00:00", "window": ["2026-11-20", "2026-12-18"],
        "si_status": "ok", "short_interest": SI,
        "earnings": {"status": "in_hold", "date": "2026-11-30", "sessions": 5},
        "ex_div": {"date": "2026-11-24", "per_share": 0.42, "estimated": False}}
LINES = ["⚠ SQUEEZE RISK · Short interest 18.2% of float · 4.1 days to cover · float 45.3M (as of 2026-11-13)",
         "Earnings in hold: 2026-11-30 (in 5 sessions)",
         "Ex-div in hold: 2026-11-24 · ~$0.42/sh owed"]


def _snap(**kw):
    return {**SNAP, **kw}


def test_copy_constants():
    assert sn.SQUEEZE_PREFIX == "⚠ SQUEEZE RISK · "
    assert sn.SQUEEZE_NOT_CHECKED == "⚠ Squeeze data not checked — verify short interest at your broker"
    assert sn.EARNINGS_NOT_CHECKED == "Earnings: not checked"


def test_full_snapshot_lines():
    assert sn.risk_notice_lines(SNAP) == LINES


def test_below_both_thresholds_and_stale():
    si = {**SI, "short_pct_float": 3.0, "days_to_cover": 1.2, "float_shares": 1.2e9,
          "si_date": "2026-09-30", "stale": True, "squeeze": False}
    assert sn.risk_notice_lines(_snap(short_interest=si))[0] == (
        "Short interest 3.0% of float · 1.2 days to cover · float 1.2B (as of 2026-09-30 · STALE)")


@pytest.mark.parametrize("si,tripped", [
    ({"squeeze": True}, True), ({"squeeze": False, "short_pct_float": 50.0}, False),   # the stamp wins
])
def test_squeeze_tripped_reads_the_stamped_decision(si, tripped):
    assert sn.squeeze_tripped(si) is tripped


def test_every_short_interest_field_missing_prints_n_a():
    si = {key: None for key in ("short_pct_float", "days_to_cover", "float_shares", "si_date")}
    line = sn.risk_notice_lines(_snap(short_interest={**si, "stale": True, "squeeze": False}))[0]
    assert line == "Short interest n/a of float · n/a days to cover · float n/a (as of n/a · STALE)"
    assert "0.0" not in line


def test_cache_miss_never_reads_as_comfort():
    assert sn.risk_notice_lines(_snap(si_status="not_checked", short_interest=None))[0] == sn.SQUEEZE_NOT_CHECKED


@pytest.mark.parametrize("earnings,line", [
    ({"status": "in_hold", "date": "2026-11-30", "sessions": 1}, "Earnings in hold: 2026-11-30 (in 1 session)"),
    ({"status": "in_hold", "date": "2026-11-20", "sessions": 0}, "Earnings in hold: 2026-11-20 (on the signal bar)"),
    ({"status": "none_in_hold", "date": None, "sessions": None}, "No earnings in hold"),
    ({"status": "not_checked", "date": None, "sessions": None}, "Earnings: not checked"),
    ({"status": "etf", "date": None, "sessions": None}, "Earnings: n/a (ETF)"),
])
def test_earnings_line(earnings, line):
    assert sn.risk_notice_lines(_snap(earnings=earnings))[1] == line


@pytest.mark.parametrize("ex_div,line", [
    ({"date": "2026-11-24", "per_share": 0.42, "estimated": True}, "Ex-div in hold: 2026-11-24 · ~$0.42/sh owed (est.)"),
    ({"date": "2026-11-24", "per_share": None, "estimated": False}, "Ex-div in hold: 2026-11-24 · amount n/a"),
])
def test_ex_div_line(ex_div, line):
    assert sn.risk_notice_lines(_snap(ex_div=ex_div))[2] == line


def test_no_ex_div_means_no_line_and_currency_is_passed():
    assert len(sn.risk_notice_lines(_snap(ex_div=None))) == 2
    assert sn.risk_notice_lines(SNAP, currency="€")[2] == "Ex-div in hold: 2026-11-24 · ~€0.42/sh owed"


def test_no_snapshot_no_lines():
    assert sn.risk_notice_lines(None) == []
    assert sn.has_risk_notice(None) is False
    assert sn.has_risk_notice(SimpleNamespace(risk_notice=None)) is False
    assert sn.has_risk_notice(SimpleNamespace()) is False
    assert sn.has_risk_notice(SimpleNamespace(risk_notice=SNAP)) is True


NUMS = {"entry": 100.0, "stop_loss": 102.0, "take_profit": 95.0}


def test_base_lane_short_gets_lines_then_the_borrow_check():
    plan = SimpleNamespace(risk_notice=SNAP, strategy="MACD", expiry_bars=5)
    assert sn.alert_notice(plan, None, NUMS) == "\n".join([*LINES, sn.BORROW_TEXT])


def test_extra_lane_short_keeps_its_notice_first_and_one_borrow_check(monkeypatch):
    monkeypatch.setattr(sn, "completed_session_date", lambda: "2026-11-20")
    context = {"mode": "isolated", "decision_bar_date": "2026-11-20"}
    plan = SimpleNamespace(risk_notice=SNAP, strategy="MACD", expiry_bars=5)
    text = sn.alert_notice(plan, context, NUMS)
    assert text.startswith(sn.short_lane_notice(context, NUMS, 5))
    assert text.endswith("\n".join(LINES)) and text.count(sn.BORROW_TEXT) == 1


def test_without_a_snapshot_alert_notice_is_unchanged():
    plan = SimpleNamespace(risk_notice=None, strategy="MACD", expiry_bars=5)
    assert sn.alert_notice(plan, None, NUMS) == ""
```

- [ ] **Step 2: Append the channel tests** — `tests/scanning/test_short_alert_parity.py`

```python
from tests.presentation.test_risk_notice_lines import LINES, SNAP  # noqa: E402


def _noticed_item(context=None, snapshot=SNAP):
    item = _short_item(context=context)
    item.plan_v2 = dataclasses.replace(item.plan_v2, risk_notice=snapshot)
    return item


def test_a_base_lane_short_carries_the_notice_on_every_surface():
    for name, text in _renderings(_noticed_item()).items():
        for line in LINES:
            assert line in text, (name, line)
        assert text.count("CHECK BORROW AVAILABILITY") == 1, name


def test_an_extra_lane_short_carries_both_notices_and_one_borrow_check():
    for name, text in _renderings(_noticed_item(context=CONTEXT)).items():
        assert "isolated" in text.lower() and LINES[1] in text, name
        assert text.count("CHECK BORROW AVAILABILITY") == 1, name


def test_switch_off_short_and_long_never_reach_the_wording(monkeypatch):
    before = {"short": _renderings(_short_item(context=None)),
              "long": _renderings(make_item(plan_v2=make_plan_v2(direction="bullish")))}
    monkeypatch.setattr(short_notice, "risk_notice_lines",
                        lambda *a, **k: pytest.fail("a plan without a snapshot was worded"))
    assert _renderings(_short_item(context=None)) == before["short"]
    assert _renderings(make_item(plan_v2=make_plan_v2(direction="bullish"))) == before["long"]
```

- [ ] **Step 3: Run both to verify they fail**

Run: `python scripts/dev/testrun.py file tests/presentation/test_risk_notice_lines.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.presentation.short_notice' has no attribute 'SQUEEZE_PREFIX'`.
Run: `python scripts/dev/testrun.py file tests/scanning/test_short_alert_parity.py`
Expected: the two new notice tests FAIL (the lines are absent); every existing test still passes.

- [ ] **Step 4: Implement the wording in `swingbot/core/presentation/short_notice.py`**

Extend the module docstring by one paragraph. It says that v183 adds the squeeze/event lines, that `risk_notice_lines` is their only wording, and that Discord full, simple, email, push and the plan page all take them from here.

Add the three constants, then the helpers below. Each stays under complexity 15 and is table-driven where it branches on a status:
- `_fmt_float_shares(v) -> str`
- `_si_line(si: dict) -> str`
- `_sessions_text(n: int | None) -> str` (`None` → no parenthesis)
- `_EARNINGS_FIXED = {"none_in_hold": "No earnings in hold", "not_checked": EARNINGS_NOT_CHECKED, "etf": "Earnings: n/a (ETF)"}`
- `_earnings_line(e: dict | None) -> str` (a missing dict reads as `not_checked`)
- `_ex_div_line(x: dict | None, currency) -> str | None`

Then the four public functions:
- `squeeze_tripped(si)` returns `bool(si.get("squeeze"))`. The stamp is the decision; this module never reads the live thresholds, so the page cannot drift from the alert.
- `risk_notice_lines(snapshot, *, currency="$")`: `[]` for `None`. The first line is `SQUEEZE_NOT_CHECKED` unless `si_status == "ok"` and `short_interest` is a dict.
- `has_risk_notice(plan_v2)`: `getattr(plan_v2, "risk_notice", None) is not None`.
- `alert_notice`: compute the existing text exactly as today into `base`, and `return base` unless `has_risk_notice(plan_v2)`. Otherwise assemble it as stated above in a `_with_risk_lines(base, snapshot, currency) -> str` helper.

- [ ] **Step 5: Widen the gate in `swingbot/core/infra/notifier.py`**

In `_short_notice`, import `has_risk_notice` with `alert_notice, is_compression`. Change the early return to:

```python
    if not context and not is_compression(plan_v2) and not has_risk_notice(plan_v2):
        return ""
```

The docstring now reads: "The short notice (extra-lane, compression, or the v183 squeeze/event lines); "" for a long or an unstamped base alert."

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/presentation/test_risk_notice_lines.py`
Expected: PASS (19 tests).
Run: `python scripts/dev/testrun.py file tests/scanning/test_short_alert_parity.py`
Expected: PASS (9 tests).
Run, one at a time: `python scripts/dev/testrun.py file tests/scanning/test_compression_instructions.py`, `... file tests/scanning/test_embeds_v3.py`, `... file tests/presentation/test_gap_risk_line.py`
Expected: PASS.

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `alert_embeds.build_embed` is unchanged at 33, and `_short_notice` gains one boolean operand.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/presentation/short_notice.py swingbot/core/infra/notifier.py tests/presentation/test_risk_notice_lines.py tests/scanning/test_short_alert_parity.py
git commit -m "feat(v183): one wording of the squeeze/earnings/ex-div lines on every short alert channel (V183-13)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 3 — The paper record and the plan page

### Task V183-14: Paper-record snapshot, plan-page API, five-channel parity

**Model:** opus — it threads a new keyword through the legacy `log_trade` and four lanes, and it adds the plan-page API keys that the spec's channel-parity test pins across five surfaces.

**Files:**
- Modify: `swingbot/core/tracking/performance.py` (new `_risk_notice_field` beside `_gap_sizing_field`; `TradeLog.log_trade` signature and one `record.update(...)` line)
- Modify: `swingbot/core/scanning/scan_run.py`, `swingbot/core/scanning/short_run.py`, `swingbot/core/scanning/strategy_pass.py`, `swingbot/core/planning/plan_manager.py` (the same four `log_trade(` calls V183-6 edited, one keyword each)
- Modify: `swingbot/admin/api_v1/trades.py` (imports; new `_risk_notice_detail_lines`, `_gap_sizing_detail`, `_recorded_sizing_view`; one key pair each in `_plan_detail` :781 and `_legacy_detail` :829)
- Create: `tests/admin/test_api_v1_trade_risk_notice.py`
- Not modified, unlike the ledger row: `tests/scanning/test_short_alert_parity.py`. The five-channel test needs the admin app fixtures, so it lives in the new admin file and imports the three Discord/email renderers from the parity file.

**Interfaces:**
- Consumes:
  - V183-6: `_gap_sizing_field`, `log_trade(..., gap_sizing=None)`, and the four call sites.
  - V183-12: `TradePlanV2.risk_notice` and the snapshot shape.
  - V183-13: `short_notice.risk_notice_lines(snapshot, *, currency="$")`, plus `LINES`, `SNAP` from `tests/presentation/test_risk_notice_lines.py` and `_renderings`, `_noticed_item`, `_setup` from `tests/scanning/test_short_alert_parity.py`.
  - V183-4: `gap_sizing.size_for(...)` and `gap_sizing.gap_risk_amount_for(...)`. V183-8: `gap_risk.gap_risk_line(sizing, *, currency="$")`.
- Produces:
  - `TradeLog.log_trade(..., gap_sizing=None, risk_notice: dict | None = None)`.
  - The trade key `risk_notice`, written only when it is not `None`.
  - Two new keys in the detail from both `_plan_detail` and `_legacy_detail`:
    - `"risk_notice_lines": list[str] | None`
    - `"gap_sizing": {"rule", "up_gap_p99_pct", "shares", "risk_amount", "gap_risk_amount", "gap_sized", "line"} | None`
  - V183-15 renders both keys.

**Rules:**
- **The snapshot.** It is read from the plan doc first, then from the trade record. The plan page never rebuilds it, so it always shows what the alert said (spec "Snapshot").
- **`gap_sizing` detail.** It is `None` unless the row is `"bearish"` and carries a stamp.
  - `entry` is the trade's `entry`, else the plan's `trigger_price`, else its `entry_price`.
  - `shares` is the trade record's `shares` when present, because that is the paper book's fixed count. Otherwise it is `size_for(...)["shares"]`, the same call the alert made.
  - `risk_amount`, `gap_risk_amount` and the line are recomputed on those shares with `gap_risk_amount_for`.
  - A rule-`"stop"` stamp has no `gap_sized` key from `size_for`, so `line` is `None` and `gap_sized` is `False`, exactly as its alert printed no gap line.

- [ ] **Step 1: Write the failing test** — `tests/admin/test_api_v1_trade_risk_notice.py`

```python
"""V183-14: the paper record keeps the alert's notice snapshot, and the plan
page API words it with the same function as Discord full, simple, email and push."""
import ast
import pathlib

import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.tracking.performance import TradeLog
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.presentation.test_risk_notice_lines import LINES, SNAP
from tests.scanning.test_embeds_v3 import _isolated_scan_snapshots  # noqa: F401
from tests.scanning.test_short_alert_parity import _noticed_item, _renderings, _setup  # noqa: F401
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
_PLAN_ID = "66666666-6666-4666-8666-666666666666"
_TRADE_ID = "cccccccccccccccc"
STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}
REPO = pathlib.Path(__file__).resolve().parents[2]
SHORT_PLAN = {**_plan(_PLAN_ID), "direction": "bearish", "trigger_price": 100.0, "entry_price": None,
              "stop_loss": 102.0, "tp1": 96.0, "tp2": 92.0}
CUT_LINE = "Risk $50 at stop · $100 on a p99 gap (4.0%) · size cut for gap risk"


@pytest.fixture(autouse=True)
def _account(monkeypatch):
    monkeypatch.setattr(config, "MAX_POSITION_VALUE_ABSOLUTE", 0.0)
    monkeypatch.setattr(config, "MAX_RISK_AMOUNT_ABSOLUTE", 0.0)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)


@pytest.fixture
def seed(admin_app):
    def _seed(plans=(), trades=()):
        seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 100.0,
                               "sizing_mode": "risk_pct", "balance_history": []})
        seed_store("plans", list(plans))
        seed_store("trades", list(trades))
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _detail(client, row_id):
    return client.get(f"/api/v1/trades/{row_id}").get_json()["detail"]


# --- the paper record ----------------------------------------------------------

def _log(risk_notice, direction="bearish"):
    log = TradeLog()
    log.log_trade(ticker="TSLA", strategy="Bear Flag", horizon_key="4w", direction=direction,
                  confidence_level=3, confidence_label="Medium", entry=100.0,
                  stop_loss=102.0 if direction == "bearish" else 98.0,
                  take_profit=96.0 if direction == "bearish" else 104.0,
                  plan_id="p-rn", risk_notice=risk_notice)
    return log.trade_for_plan("p-rn")


def test_log_trade_copies_the_snapshot_and_a_long_record_has_no_key(seed):
    seed()
    assert _log(SNAP)["risk_notice"] == SNAP
    seed()
    assert "risk_notice" not in _log(None, direction="bullish")


@pytest.mark.parametrize("path", [
    "swingbot/core/scanning/scan_run.py", "swingbot/core/scanning/short_run.py",
    "swingbot/core/scanning/strategy_pass.py", "swingbot/core/planning/plan_manager.py",
])
def test_every_log_trade_call_site_passes_risk_notice(path):
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "log_trade"]
    assert calls, path
    for call in calls:
        assert "risk_notice" in {kw.arg for kw in call.keywords}, (path, call.lineno)


# --- the plan-page API ---------------------------------------------------------

def test_plan_page_lines_come_from_the_plan_snapshot(seed, logged_in):
    seed(plans=[{**SHORT_PLAN, "risk_notice": SNAP}])
    assert _detail(logged_in, _PLAN_ID)["risk_notice_lines"] == LINES


def test_a_trade_record_snapshot_is_used_when_the_plan_doc_has_none(seed, logged_in):
    seed(plans=[{**SHORT_PLAN, "status": "ACTIVE"}],
         trades=[{**_trade(_TRADE_ID, plan_id=_PLAN_ID), "direction": "bearish", "risk_notice": SNAP}])
    assert _detail(logged_in, _PLAN_ID)["risk_notice_lines"] == LINES
    seed(trades=[{**_trade(_TRADE_ID), "direction": "bearish", "risk_notice": SNAP}])
    assert _detail(logged_in, _TRADE_ID)["risk_notice_lines"] == LINES


def test_pre_v183_and_long_rows_carry_none(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID)], trades=[_trade(_TRADE_ID)])
    for row_id in (_PLAN_ID, _TRADE_ID):
        detail = _detail(logged_in, row_id)
        assert detail["risk_notice_lines"] is None and detail["gap_sizing"] is None


def test_gap_sizing_block_for_a_pending_gap_cut_short(seed, logged_in):
    seed(plans=[{**SHORT_PLAN, "gap_sizing": STAMP}])
    assert _detail(logged_in, _PLAN_ID)["gap_sizing"] == {
        "rule": "gap_p99", "up_gap_p99_pct": 4.0, "shares": 25.0, "risk_amount": 50.0,
        "gap_risk_amount": 100.0, "gap_sized": True, "line": CUT_LINE}


def test_gap_sizing_block_reads_the_paper_books_shares(seed, logged_in):
    trade = {**_trade(_TRADE_ID), "direction": "bearish", "entry": 100.0, "stop_loss": 102.0,
             "shares": 20, "gap_sizing": STAMP}
    seed(trades=[trade])
    block = _detail(logged_in, _TRADE_ID)["gap_sizing"]
    assert (block["shares"], block["risk_amount"], block["gap_risk_amount"]) == (20, 40.0, 80.0)


def test_a_rule_stop_short_shows_no_gap_line(seed, logged_in):
    seed(plans=[{**SHORT_PLAN, "gap_sizing": {**STAMP, "rule": "stop"}}])
    block = _detail(logged_in, _PLAN_ID)["gap_sizing"]
    assert (block["rule"], block["line"], block["gap_sized"]) == ("stop", None, False)


# --- five-channel parity (spec "One channel-parity test") ---------------------------

def test_discord_full_simple_email_push_and_the_plan_page_carry_the_same_notice(seed, logged_in):
    seed(plans=[{**SHORT_PLAN, "risk_notice": SNAP}])
    page = _detail(logged_in, _PLAN_ID)["risk_notice_lines"]
    assert page == LINES
    renderings = _renderings(_noticed_item())          # discord, simple, email/push
    for name, text in renderings.items():
        for line in page:
            assert line in text, (name, line)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_risk_notice.py`
Expected: FAIL — `TypeError: log_trade() got an unexpected keyword argument 'risk_notice'`, `KeyError: 'risk_notice_lines'`, and the AST test fails on all four files.

- [ ] **Step 3: Thread the snapshot onto the paper record**

In `swingbot/core/tracking/performance.py`, add beside `_gap_sizing_field`:

```python
def _risk_notice_field(risk_notice: dict | None) -> dict:
    """{"risk_notice": snapshot} for a short alerted with the v183 notice, else
    {} -- the key stays absent on longs and pre-v183 trades."""
    return {"risk_notice": dict(risk_notice)} if risk_notice is not None else {}
```

In `log_trade`, add `risk_notice=None` as the last keyword, after `gap_sizing=None`. Directly after `record.update(_gap_sizing_field(gap_sizing))`, add `record.update(_risk_notice_field(risk_notice))`. Add one docstring sentence: "`risk_notice` is the alert's v183 squeeze/event snapshot, copied so the trade page shows what the alert said." No branch is added, so `log_trade` stays at or below its baseline.

At the four call sites, directly after the `gap_sizing=...` keyword V183-6 added, add:
- `scan_run.py`: `risk_notice=getattr(plan_v2, "risk_notice", None),`
- `short_run._log_trade`: `risk_notice=getattr(plan_v2, "risk_notice", None),`
- `strategy_pass._open_trade`: `risk_notice=plan.risk_notice,`
- `plan_manager._on_event` fallback: `risk_notice=plan.risk_notice,`

- [ ] **Step 4: Add the plan-page keys in `swingbot/admin/api_v1/trades.py`**

Imports: `from swingbot import config` (if not already imported), `from swingbot.core.planning.gap_sizing import gap_risk_amount_for, size_for`, `from swingbot.core.presentation.gap_risk import gap_risk_line`, `from swingbot.core.presentation.short_notice import risk_notice_lines`.

```python
def _risk_notice_detail_lines(plan: dict | None, trade: dict | None) -> list[str] | None:
    """v183: the alert's squeeze/event lines, from the snapshot saved when it went
    out (plan doc first, then the paper record) -- never rebuilt, so the page
    matches the alert. None for longs and pre-v183 rows."""
    snapshot = (plan or {}).get("risk_notice") or (trade or {}).get("risk_notice")
    return risk_notice_lines(snapshot, currency=config.CURRENCY_SYMBOL) if snapshot else None


def _recorded_sizing_view(sizing: dict, shares, entry, stop, stamp) -> dict:
    """The size_for result re-expressed on the shares actually shown."""
    if shares is None or "gap_sized" not in sizing:
        return dict(sizing)
    return {**sizing, "risk_amount": round(float(shares) * abs(float(entry) - float(stop)), 2),
            "gap_risk_amount": gap_risk_amount_for(shares, entry, stop, stamp)}


def _gap_sizing_detail(plan: dict | None, trade: dict | None) -> dict | None:
    """v183: the order block's share count and gap-risk line for a stamped short."""
    p, t = plan or {}, trade or {}
    stamp = p.get("gap_sizing") or t.get("gap_sizing")
    if (p or t).get("direction") != "bearish" or not stamp:
        return None
    entry = t.get("entry") or p.get("trigger_price") or p.get("entry_price")
    stop = t.get("stop_loss") or p.get("stop_loss")
    sizing = size_for(entry, stop, direction="bearish", gap_sizing=stamp) or {}
    shares = t["shares"] if t.get("shares") is not None else sizing.get("shares")
    view = _recorded_sizing_view(sizing, shares, entry, stop, stamp)
    return {"rule": stamp.get("rule"), "up_gap_p99_pct": stamp.get("up_gap_p99_pct"),
            "shares": shares, "risk_amount": view.get("risk_amount"),
            "gap_risk_amount": view.get("gap_risk_amount"), "gap_sized": bool(view.get("gap_sized")),
            "line": gap_risk_line(view, currency=config.CURRENCY_SYMBOL)}
```

In `_plan_detail`, after `"quote": _quote_stamp(plan, trade),` add `"risk_notice_lines": _risk_notice_detail_lines(plan, trade),` and `"gap_sizing": _gap_sizing_detail(plan, trade),`. In `_legacy_detail`, after `"quote": _quote_stamp(None, t),` add the same pair with `(None, t)`. A rule-`stop` stamp gets `risk_amount` from the plain `size_for` result, which is that function's own stop risk.

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_risk_notice.py`
Expected: PASS (12 tests).
Run, one at a time: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py`, `... file tests/admin/test_api_quote_fields.py`, `... file tests/tracking/test_gap_sized_paper_book.py`, `... file tests/tracking/test_record_plan_fill.py`, `... file tests/scanning/test_short_alert_parity.py`
Expected: PASS. `test_detail_row_fields_match_the_list_exactly` compares only the row fields, so the detail additions do not touch it.

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `_plan_detail` stays at 11, `log_trade` does not rise, and the three helpers are below 15.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/tracking/performance.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py swingbot/core/scanning/strategy_pass.py swingbot/core/planning/plan_manager.py swingbot/admin/api_v1/trades.py tests/admin/test_api_v1_trade_risk_notice.py
git commit -m "feat(v183): paper record keeps the notice snapshot; plan-page API words it like every channel (V183-14)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V183-15: Plan page: notice lines and gap cut in the order block, three widths

**Model:** sonnet — one presentational block in an existing component, with a pure helper, specs, and a three-width browser check.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`TradeDetailFields` :240-292, plus a new `GapSizingDetail` interface directly above it). This file is not in the ledger row. It is the hand-written `/api/v1` contract, and the two new detail keys must be declared there. **V183-9 also edits `models.ts`, so V183-15 must never run alongside V183-9.** Run it after V183-9 has committed.
- Modify: `frontend/src/app/workspaces/plans/plan-detail.ts`
- Modify: `frontend/src/app/workspaces/plans/plan-detail.spec.ts`

**Interfaces:**
- Consumes (V183-14): `detail.risk_notice_lines: string[] | null` and `detail.gap_sizing: {rule, up_gap_p99_pct, shares, risk_amount, gap_risk_amount, gap_sized, line} | null`, from `GET /api/v1/trades/<plan id>`.
- Produces:
  - `export interface GapSizingDetail`, plus `TradeDetailFields.risk_notice_lines?` and `TradeDetailFields.gap_sizing?`.
  - `export interface ShortOrderNotes { size: string | null; gapLine: string | null; cut: boolean; lines: string[] }`.
  - `export function shortOrderNotes(detail: Pick<TradeDetailFields, 'risk_notice_lines' | 'gap_sizing'> | null): ShortOrderNotes | null`.

**Design (spec "Shown where the order is", "Snapshot"; `docs/claude/ui-design.md`):**
- **Placement.** The plan page wraps `<sb-levels-block>` and a new `.order-notes` block in one `.order-block` grid cell, so the size, the gap line and the notice sit directly under entry, stop and targets.
- **Status.** It is shown for every status, not only PENDING, because the snapshot is what the alert said.
- **Content, top to bottom.**
  - `Suggested size 25 sh`, with shares formatted to at most 2 decimals with en-US grouping.
  - The gap line, verbatim from the API.
  - Then the notice lines as a plain list. A line starting with `⚠` gets class `warn` (`color: var(--warn); font-weight: 600`). The gap line gets class `cut` when `gap_sized` is true.
- **Text is never re-worded in the SPA.** Every string comes from the API, which took it from `risk_notice_lines` / `gap_risk_line` (index § Channel parity).
- **A long, an unstamped short or a pre-v183 plan** gets `shortOrderNotes(...) === null`, so no `.order-notes` element renders and the page is unchanged.
- **Three widths.** At 375 the `.panels` grid is one column. The block takes the full width and long lines wrap (`overflow-wrap: anywhere`, `min-width: 0`) without horizontal page scroll. At 768 and 1280 the order block shares the auto-fit grid with the sizing panel. There are no controls, so touch targets do not apply.

- [ ] **Step 1: Write the failing specs** — append to `frontend/src/app/workspaces/plans/plan-detail.spec.ts`

Add `shortOrderNotes` to the import from `./plan-detail`. Then:

```ts
const NOTICE = [
  '⚠ SQUEEZE RISK · Short interest 18.2% of float · 4.1 days to cover · float 45.3M (as of 2026-11-13)',
  'Earnings in hold: 2026-11-30 (in 5 sessions)',
  'Ex-div in hold: 2026-11-24 · ~$0.42/sh owed',
  'CHECK BORROW AVAILABILITY',
];
const GAP = {
  rule: 'gap_p99', up_gap_p99_pct: 4, shares: 25, risk_amount: 50, gap_risk_amount: 100,
  gap_sized: true, line: 'Risk $50 at stop · $100 on a p99 gap (4.0%) · size cut for gap risk',
};

describe('shortOrderNotes', () => {
  it('is null without either key (longs, unstamped, pre-v183)', () => {
    expect(shortOrderNotes(null)).toBeNull();
    expect(shortOrderNotes({ risk_notice_lines: null, gap_sizing: null })).toBeNull();
    expect(shortOrderNotes({})).toBeNull();
  });

  it('carries the size, the gap line verbatim and the notice lines', () => {
    expect(shortOrderNotes({ risk_notice_lines: NOTICE, gap_sizing: GAP })).toEqual({
      size: 'Suggested size 25 sh', gapLine: GAP.line, cut: true, lines: NOTICE,
    });
  });

  it('formats fractional shares and survives a rule-stop short', () => {
    const notes = shortOrderNotes({ risk_notice_lines: null,
      gap_sizing: { ...GAP, rule: 'stop', shares: 1234.567, gap_sized: false, line: null } });
    expect(notes).toEqual({ size: 'Suggested size 1,234.57 sh', gapLine: null, cut: false, lines: [] });
  });
});
```

Inside the existing `describe('PlanDetail', …)`, after the PENDING test:

```ts
  it('puts the size, gap cut and squeeze notice inside the order block of a short', () => {
    const el = render('PENDING', { direction: 'bearish' },
      { risk_notice_lines: NOTICE, gap_sizing: GAP });
    const block = el.querySelector('.order-block');
    expect(block?.querySelector('sb-levels-block')).toBeTruthy();
    const notes = block?.querySelector('.order-notes');
    expect(notes?.textContent).toContain('Suggested size 25 sh');
    expect(notes?.querySelector('.gap.cut')?.textContent).toContain('size cut for gap risk');
    const items = [...(notes?.querySelectorAll('li') ?? [])].map((li) => li.textContent?.trim());
    expect(items).toEqual(NOTICE);
    expect(notes?.querySelectorAll('li.warn').length).toBe(1);
  });

  it('keeps the notice on a filled short too', () => {
    const el = render('ACTIVE', { direction: 'bearish' }, { risk_notice_lines: NOTICE, gap_sizing: null });
    expect(el.querySelector('.order-notes')?.textContent).toContain('Earnings in hold: 2026-11-30');
  });

  it('renders no order notes for a long or a pre-v183 plan', () => {
    expect(render('PENDING').querySelector('.order-notes')).toBeNull();
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include=src/app/workspaces/plans/plan-detail.spec.ts`
Expected: FAIL — `shortOrderNotes` is not exported, and `.order-block` is not found.

- [ ] **Step 3: Declare the contract in `frontend/src/app/api/models.ts`**

Directly above `TradeDetailFields`:

```ts
/** v183: a stamped short's order-block sizing (`_gap_sizing_detail`,
 *  swingbot/admin/api_v1/trades.py). `line` is the alert's own gap-risk
 *  wording; null for a rule-stop short. */
export interface GapSizingDetail {
  rule: string;
  up_gap_p99_pct: number | null;
  shares: number | null;
  risk_amount: number | null;
  gap_risk_amount: number | null;
  gap_sized: boolean;
  line: string | null;
}
```

At the end of `TradeDetailFields`, after `quote?`:

```ts
  /** v183: the alert's squeeze/earnings/ex-div lines, from the snapshot saved
   *  when it went out; null for longs and pre-v183 plans. Optional so older
   *  fixtures stay valid. */
  risk_notice_lines?: string[] | null;
  /** v183: see GapSizingDetail; null for longs and unstamped shorts. */
  gap_sizing?: GapSizingDetail | null;
```

- [ ] **Step 4: Implement in `frontend/src/app/workspaces/plans/plan-detail.ts`**

Next to `timingLines`, export `ShortOrderNotes` and the pure function `shortOrderNotes(detail)`:
- It returns `null` when `detail` is null, or when neither `risk_notice_lines?.length` nor `gap_sizing` is present.
- `size` is `null` when `gap_sizing?.shares` is null, else `` `Suggested size ${shares.toLocaleString('en-US', { maximumFractionDigits: 2 })} sh` ``.
- `gapLine` is `gap_sizing?.line ?? null`, `cut` is `gap_sizing?.gap_sized === true`, and `lines` is `risk_notice_lines ?? []`.

Import the `TradeDetailFields` type from `../../api/models`.

In the class, add `protected readonly orderNotes = computed(() => shortOrderNotes(this.store.detail()));`.

In the template, replace the bare `<sb-levels-block …/>` with:

```html
            <div class="order-block">
              <sb-levels-block
                …the existing bindings, unchanged…
              />
              @if (orderNotes(); as notes) {
                <div class="order-notes" role="group" aria-label="Short order checks">
                  @if (notes.size) {
                    <p class="size">{{ notes.size }}</p>
                  }
                  @if (notes.gapLine) {
                    <p class="gap" [class.cut]="notes.cut">{{ notes.gapLine }}</p>
                  }
                  @if (notes.lines.length) {
                    <ul class="risk-notice">
                      @for (line of notes.lines; track $index) {
                        <li [class.warn]="line.startsWith('⚠')">{{ line }}</li>
                      }
                    </ul>
                  }
                </div>
              }
            </div>
```

Add to `styles`:

```css
    .order-block {
      display: grid;
      gap: var(--space-8);
      min-width: 0;
    }
    .order-notes {
      display: grid;
      gap: var(--space-6);
      color: var(--text-secondary);
      font-size: var(--text-table);
      overflow-wrap: anywhere;
    }
    .order-notes p, .risk-notice {
      margin: 0;
    }
    .risk-notice {
      display: grid;
      gap: var(--space-6);
      padding: 0;
      list-style: none;
    }
    .gap.cut, .risk-notice .warn {
      color: var(--warn);
      font-weight: 600;
    }
```

- [ ] **Step 5: Run the specs**

Run: `cd frontend && npx ng test --watch=false --include=src/app/workspaces/plans/plan-detail.spec.ts`
Expected: PASS, including every pre-existing spec in the file.
Run: `cd frontend && npx ng test --watch=false --include=src/app/workspaces/trades/why/sizing-panel.spec.ts`
Expected: PASS (untouched component, guard run).
Run: `cd frontend && npx ng build`
Expected: build succeeds with no new warnings.

- [ ] **Step 6: Check at phone, tablet and desktop widths**

Seed one stamped short plan into the **local** replica only. Write the script to the session scratchpad, not the repo. It:
- loads `.env` through `swingbot.config`, never printing a value;
- exits with `not a local database` unless `urllib.parse.urlparse(config.DATABASE_URL).hostname in ("localhost", "127.0.0.1")`;
- builds `tests.planning.test_gap_sizing._plan(plan_id="77777777-7777-4777-8777-777777777777", ticker="ZZZ", created_at=<today ISO>, gap_sizing=<the GAP stamp shape {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}>, risk_notice=tests.presentation.test_risk_notice_lines.SNAP)`;
- runs `PlanStore().add(plan)`.

Start `python admin_ui.py` (port 1234) in a background shell, then:

```bash
node frontend/scripts/browse.mjs shots --base http://localhost:1234 --path "/plans/77777777-7777-4777-8777-777777777777" --widths 1280,768,375 --out "<session scratchpad>/v183-plan-page"
```

If port 1234 does not serve the built SPA, use `cd frontend && npx ng serve --port 4123` instead. Enter at `--base http://localhost:4123 --path "app/trades"` and add `--click 'a[href*="77777777-7777"]'`, because a cold `/app/<route>` bounces by design.

`browse.mjs` signs in with `ADMIN_USERNAME`/`ADMIN_PASSWORD`, which it loads from `.env` inside its own process. Never print, echo or pass them.

Expected:
- Each `<slug>@<width>.txt` starts with `page-scroll-x: 0` and contains `Suggested size`, `size cut for gap risk`, `⚠ SQUEEZE RISK` and `CHECK BORROW AVAILABILITY`.
- In each PNG the block sits directly under the levels block. At 375 the lines wrap with no clipped text. At 768 and 1280 the order block and the sizing panel sit side by side.

Afterwards, mark the seeded plan `CANCELLED` with `PlanStore().update(...)` (a legal PENDING → CANCELLED transition; PlanStore has no delete). Stop the servers. The next `/replicate-prod-db` replaces the local data. Report the three widths in the task report.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/workspaces/plans/plan-detail.ts frontend/src/app/workspaces/plans/plan-detail.spec.ts
git commit -m "feat(v183): plan page shows the short's size, gap cut and squeeze/event notice in the order block (V183-15)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
