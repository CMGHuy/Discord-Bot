# v172 Equity candlestick chart, part 2: recorder, candles API, backfill

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `grep -n "^### Task V172-5:" -A 300 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-17-v172-equity-candlestick-chart-design.md`](../specs/2026-10-17-v172-equity-candlestick-chart-design.md)
**Index:** [`2026-10-17-v172-equity-candlestick-chart_0-index.md`](2026-10-17-v172-equity-candlestick-chart_0-index.md): Global Constraints, Parallelisation, `$WT`/`$R` and the task ledger live there and bind every task below.

Tasks V172-4..V172-6 (V172-7, the backfill CLI, is in `_2b-backfill-cli.md` for the line cap). They consume part 1's contracts (ledger rows V172-1..V172-3), quoted in each task's **Interfaces** block:

- `swingbot.core.tracking.equity`: `parse_ts`, `main_book`, `RealizedLeg`, `realized_legs`, `realized_balance_at`, `starting_balance`, `load_plans_by_id`, `unrealized_decimal`, `EquitySnapshot`, `snapshot_at` (V172-1).
- `swingbot.core.db.repositories.equity_samples`: `EquitySampleRepository`, `equity_samples_repo`, row dict keys `at, realized_balance, unrealized_pnl, equity, open_n, skipped_n, source, kind, backfill_run` (V172-2).
- `swingbot.core.tracking.equity_candles`: `TIMEFRAMES`, `mtm_candles`, `realized_candles` (V172-3; both already call `add_change`).

# Phase 2: recorder, candles API, backfill

### Task V172-4: Record a live equity sample from `trade_monitor`

**Model:** opus — crosses `commands`, `core/tracking`, `core/db`, `core/market`; must never break the monitor

**Files:**
- Create: `swingbot/commands/scanning/equity_recorder.py`
- Modify: `swingbot/commands/scanning/loops.py` (package import line ~22; new helper directly above `trade_monitor` ~line 590; one call inside `trade_monitor` after the `_post_plan_events` block ~line 662)
- Test: `tests/commands/test_equity_recorder.py` (suite `discord`)

**Interfaces:**
- Consumes (V172-1, `swingbot.core.tracking.equity`): `snapshot_at(trades: list[dict], plans_by_id: dict, prices: dict[str, float], at: datetime, start: Decimal) -> EquitySnapshot`; `EquitySnapshot(realized_balance: Decimal, unrealized_pnl: Decimal, equity: Decimal, open_n: int, skipped_n: int)`; `load_plans_by_id() -> dict`; `starting_balance() -> Decimal`; `realized_legs(trades) -> list[RealizedLeg]`; `realized_balance_at(start, legs, at) -> Decimal`. `swingbot.admin.dashboard.unrealized_pnl_amount` stays importable (V172-1 re-import).
- Consumes (V172-2, `swingbot.core.db.repositories.equity_samples`): `EquitySampleRepository.insert_sample(row: dict, conn=None) -> int`, `.latest_at(source: str, conn=None) -> datetime | None` (tz-aware UTC), `.list_rows(*, sources=("live", "backfill"), since=None, conn=None) -> list[dict]`; `equity_samples_repo() -> EquitySampleRepository`. Money is written as `Decimal` and rounded once by the repository; it reads back as floats.
- Produces: `equity_recorder.SAMPLE_INTERVAL = timedelta(minutes=5)`; `equity_recorder.record_sample(live_prices: dict[str, float], *, now: datetime | None = None, repo: EquitySampleRepository | None = None) -> bool` (True when a row was written; never raises); `equity_recorder.load_trades() -> list[dict]` (test seam); `equity_recorder.reset_state() -> None` (test hook); `loops._record_equity_sample(live_prices: dict) -> None` (async).

Why this shape: `trade_monitor` runs every 60s around the clock and sits at cyclomatic complexity 13, so the hook is one awaited helper call. The sample is taken after `run_manager_tick` and `_post_plan_events`, because TP1 legs and plan stop/target closes land there (spec Correction 6): a trade closing this tick is realized in this sample and never also unrealized. The recorder re-reads trades itself (the monitor's `open_trades` list is stale after its closes) and uses only `live_prices`, so it adds no market-data call.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_equity_recorder.py`:

```python
"""v172: trade_monitor records one live equity sample per 5 minutes, in session.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
The DB is the per-worker test Postgres (autouse `_store_database`)."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from swingbot.admin import dashboard as dash
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import equity_recorder, loops
from swingbot.core.db.repositories.equity_samples import EquitySampleRepository
from swingbot.core.tracking import equity
from tests.store_seed import seed_store

# Wednesday 2026-10-14, 11:00 New York (EDT = UTC-4): inside the regular session.
IN_SESSION = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
# The same day, 17:00 New York: after the close.
AFTER_CLOSE = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)
BASE = 10000.0


@pytest.fixture(autouse=True)
def _fresh_state():
    equity_recorder.reset_state()
    yield
    equity_recorder.reset_state()


@pytest.fixture
def repo():
    return EquitySampleRepository()


@pytest.fixture
def account():
    seed_store("account", {"base_balance": BASE, "balance": BASE, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})


def _trade(tid, ticker, *, shares=10.0, entry=100.0, status="open", **extra):
    return {"id": tid, "ticker": ticker, "direction": "bullish", "status": status,
            "entry": entry, "stop_loss": round(entry * 0.95, 2), "shares": shares,
            "opened_at": "2026-10-13T14:00:00+00:00", "ledger": "main", **extra}


def _patch_book(monkeypatch, trades):
    monkeypatch.setattr(equity_recorder, "load_trades", lambda: list(trades))
    monkeypatch.setattr(equity, "load_plans_by_id", lambda: {})


def _fake_price_batch_aapl_110(tickers, **kw):
    """Module-level so it pickles through loops._run_bounded's worker process."""
    return {"AAPL": 110.0}


def _patch_monitor(monkeypatch, *, tick=lambda: []):
    monkeypatch.setattr(loops.trade_log, "get_trades",
                        lambda status=None, limit=None: [{"ticker": "AAPL", "id": "t1",
                                                          "status": "open"}])
    monkeypatch.setattr(loops, "get_current_price_batch", _fake_price_batch_aapl_110)
    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", lambda ticker, live: [])
    monkeypatch.setattr(loops.trade_log, "check_near_tp_timeout", lambda ticker, live: [])
    monkeypatch.setattr("swingbot.core.planning.plan_manager.run_manager_tick", tick)


def test_one_priced_one_unpriced_one_unsized_writes_one_row_with_two_skipped(
        monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL"), _trade("t2", "MSFT"),
                              _trade("t3", "NVDA", shares=None)])
    assert equity_recorder.record_sample({"AAPL": 110.0, "NVDA": 50.0},
                                         now=IN_SESSION, repo=repo) is True
    (row,) = repo.list_rows()
    assert (row["source"], row["kind"], row["open_n"], row["skipped_n"]) == ("live", "point", 1, 2)
    assert row["unrealized_pnl"] == 100.0
    assert row["realized_balance"] == BASE
    assert row["equity"] == BASE + 100.0
    assert row["at"] == IN_SESSION
    assert row["backfill_run"] is None


def test_a_zero_or_negative_price_is_unpriced_not_priced_at_zero(monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL"), _trade("t2", "MSFT")])
    equity_recorder.record_sample({"AAPL": 0.0, "MSFT": -1.0}, now=IN_SESSION, repo=repo)
    (row,) = repo.list_rows()
    assert (row["open_n"], row["skipped_n"], row["unrealized_pnl"]) == (0, 2, 0.0)


def test_outside_the_regular_session_nothing_is_written(monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL")])
    assert equity_recorder.record_sample({"AAPL": 110.0}, now=AFTER_CLOSE, repo=repo) is False
    assert repo.list_rows() == []


def test_two_ticks_under_five_minutes_apart_write_one_row(monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL")])
    record = equity_recorder.record_sample
    assert record({"AAPL": 110.0}, now=IN_SESSION, repo=repo) is True
    assert record({"AAPL": 111.0}, now=IN_SESSION + timedelta(minutes=4, seconds=59),
                  repo=repo) is False
    assert record({"AAPL": 112.0}, now=IN_SESSION + equity_recorder.SAMPLE_INTERVAL,
                  repo=repo) is True
    assert [r["unrealized_pnl"] for r in repo.list_rows()] == [100.0, 120.0]


def test_the_throttle_survives_a_restart_by_reading_the_last_live_row(
        monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL")])
    repo.insert_sample({"at": IN_SESSION - timedelta(minutes=2),
                        "realized_balance": Decimal("10000"), "unrealized_pnl": Decimal("0"),
                        "equity": Decimal("10000"), "open_n": 0, "skipped_n": 0,
                        "source": "live", "kind": "point", "backfill_run": None})
    assert equity_recorder.record_sample({"AAPL": 110.0}, now=IN_SESSION, repo=repo) is False
    assert len(repo.list_rows()) == 1


def test_parity_with_the_trades_page_and_the_realized_walk(monkeypatch, repo, account):
    trades = [
        _trade("t1", "AAPL", shares=7.5, entry=101.2),
        _trade("t2", "MSFT", status="loss", exit_price=95.0, realized_pnl_amount=-50.0,
               closed_at="2026-10-14T14:00:00+00:00"),
        _trade("t3", "NVDA", ledger="weak"),          # weak ledger: never in a sample
    ]
    _patch_book(monkeypatch, trades)
    equity_recorder.record_sample({"AAPL": 103.5, "NVDA": 500.0}, now=IN_SESSION, repo=repo)
    (row,) = repo.list_rows()
    assert row["open_n"] == 1
    assert row["unrealized_pnl"] == dash.unrealized_pnl_amount(101.2, "bullish", 7.5, 103.5)
    walk = equity.realized_balance_at(equity.starting_balance(),
                                      equity.realized_legs(trades), IN_SESSION)
    assert row["realized_balance"] == float(walk.quantize(Decimal("0.01")))
    assert row["realized_balance"] == BASE - 50.0


def test_a_trade_closed_in_the_same_tick_is_realized_not_unrealized(monkeypatch, repo, account):
    book = {"trades": [_trade("t1", "AAPL")]}
    closed = _trade("t1", "AAPL", status="win", exit_price=110.0, realized_pnl_amount=100.0,
                    closed_at=(datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat())

    def tick_closes_the_trade():
        book["trades"] = [closed]
        return []

    monkeypatch.setattr(equity_recorder, "load_trades", lambda: list(book["trades"]))
    monkeypatch.setattr(equity, "load_plans_by_id", lambda: {})
    monkeypatch.setattr(equity_recorder, "is_regular_session", lambda now=None: True)
    _patch_monitor(monkeypatch, tick=tick_closes_the_trade)

    asyncio.run(scanning_mod.trade_monitor.coro())

    (row,) = repo.list_rows()
    assert (row["open_n"], row["unrealized_pnl"]) == (0, 0.0)
    assert row["realized_balance"] == BASE + 100.0


def test_a_recording_failure_is_logged_once_per_type_and_never_raises(
        monkeypatch, repo, account, caplog):
    caplog.set_level(logging.DEBUG, logger=equity_recorder.__name__)

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(equity_recorder, "load_trades", boom)
    for minute in (0, 5, 10):
        assert equity_recorder.record_sample(
            {}, now=IN_SESSION + timedelta(minutes=minute), repo=repo) is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "RuntimeError" in warnings[0].getMessage()

    def other():
        raise KeyError("plan")

    monkeypatch.setattr(equity_recorder, "load_trades", other)
    equity_recorder.record_sample({}, now=IN_SESSION + timedelta(minutes=15), repo=repo)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2
    assert repo.list_rows() == []


def test_the_monitor_tick_completes_when_recording_raises(monkeypatch):
    calls = {"tick": 0}

    def tick():
        calls["tick"] += 1
        return []

    def explode(live_prices, **kw):
        raise RuntimeError("recorder bug")

    _patch_monitor(monkeypatch, tick=tick)
    monkeypatch.setattr(equity_recorder, "record_sample", explode)
    asyncio.run(scanning_mod.trade_monitor.coro())     # must not raise
    assert calls["tick"] == 1


def test_the_monitor_hands_its_own_prices_to_the_recorder(monkeypatch):
    seen = []
    _patch_monitor(monkeypatch)
    monkeypatch.setattr(equity_recorder, "record_sample",
                        lambda live_prices, **kw: seen.append(dict(live_prices)) or False)
    asyncio.run(scanning_mod.trade_monitor.coro())
    assert seen == [{"AAPL": 110.0}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_equity_recorder.py`
Expected: collection error, `ImportError: cannot import name 'equity_recorder' from 'swingbot.commands.scanning'`.

- [ ] **Step 3: Create the recorder module**

Create `swingbot/commands/scanning/equity_recorder.py`:

```python
"""v172: one live equity sample every 5 minutes, written from trade_monitor.

The trade monitor already prices the open book every 60 seconds. After this
tick's closes have landed (per-ticker hits and the plan-manager tick),
`record_sample` re-reads every trade, values the account through the one
equity definition (`swingbot.core.tracking.equity.snapshot_at`) at the
prices this tick fetched, and writes one `equity_samples` row
(`source="live"`, `kind="point"`).

Rules (spec v172 § 2, Corrections 3 and 6):
- regular US session only (`is_regular_session`): the monitor itself runs
  around the clock;
- at most one row per `SAMPLE_INTERVAL`: the first tick at least 5 minutes
  after the last written live row, seeded from the table after a restart;
- no market-data call of its own; an unpriced or unsized position is
  counted in `skipped_n`, never priced at 0;
- never raises: a failure is logged once per process per exception type
  (later ones at DEBUG) and the sample skipped. A missed sample is a gap,
  never an invented value.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from swingbot.core.db.repositories.equity_samples import (EquitySampleRepository,
                                                          equity_samples_repo)
from swingbot.core.market.session import is_regular_session
from swingbot.core.tracking import equity

log = logging.getLogger(__name__)

SAMPLE_INTERVAL = timedelta(minutes=5)

# Process-local, like loops._recap_fired_date: the table is the durable record.
_state: dict = {"last_at": None, "seeded": False}
_warned: set[str] = set()


def reset_state() -> None:
    """Test hook: forget the throttle and the exception types already warned about."""
    _state.update(last_at=None, seeded=False)
    _warned.clear()


def load_trades() -> list[dict]:
    """Every trade, read now: the monitor's own list is stale after its closes."""
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status=None, limit=None, sort_by="opened_at") or []


def _priced(live_prices: dict | None) -> dict[str, float]:
    """Only real prints: a missing, zero or negative price leaves the position unpriced."""
    return {ticker: price for ticker, price in (live_prices or {}).items()
            if price is not None and price > 0}


def _last_written(repo: EquitySampleRepository) -> datetime | None:
    if not _state["seeded"]:
        _state["last_at"] = repo.latest_at("live")
        _state["seeded"] = True
    return _state["last_at"]


def _due(now: datetime, repo: EquitySampleRepository) -> bool:
    last = _last_written(repo)
    return last is None or now - last >= SAMPLE_INTERVAL


def _row(snapshot: equity.EquitySnapshot, now: datetime) -> dict:
    return {"at": now, "realized_balance": snapshot.realized_balance,
            "unrealized_pnl": snapshot.unrealized_pnl, "equity": snapshot.equity,
            "open_n": snapshot.open_n, "skipped_n": snapshot.skipped_n,
            "source": "live", "kind": "point", "backfill_run": None}


def _record(live_prices: dict, now: datetime, repo: EquitySampleRepository) -> bool:
    if not is_regular_session(now) or not _due(now, repo):
        return False
    snapshot = equity.snapshot_at(load_trades(), equity.load_plans_by_id(),
                                  _priced(live_prices), now, equity.starting_balance())
    repo.insert_sample(_row(snapshot, now))
    _state["last_at"] = now
    return True


def _warn_once(exc: Exception) -> None:
    kind = type(exc).__name__
    if kind in _warned:
        log.debug("equity sample skipped: %s: %s", kind, exc)
        return
    _warned.add(kind)
    log.warning("equity sample skipped (%s; repeats of this error logged at DEBUG): %s",
                kind, exc, exc_info=True)


def record_sample(live_prices: dict[str, float], *, now: datetime | None = None,
                  repo: EquitySampleRepository | None = None) -> bool:
    """Write one live sample when due; True when a row was written. Never raises."""
    try:
        moment = now or datetime.now(timezone.utc)
        return _record(live_prices, moment, repo or equity_samples_repo())
    except Exception as exc:
        _warn_once(exc)
        return False
```

- [ ] **Step 4: Run the recorder-only tests**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_equity_recorder.py`
Expected: the seven `record_sample` tests PASS; `test_a_trade_closed_in_the_same_tick_is_realized_not_unrealized` and `test_the_monitor_hands_its_own_prices_to_the_recorder` FAIL (the monitor does not call the recorder yet); `test_the_monitor_tick_completes_when_recording_raises` already passes (nothing calls the stub yet) and becomes meaningful after Step 5.

- [ ] **Step 5: Wire the recorder into `trade_monitor`**

In `swingbot/commands/scanning/loops.py`, extend the package import (line ~22):

```python
from . import cooldown, equity_recorder, notices, ops_watch, outlook, presence, recap, runstate
```

Add this helper directly above `@tasks.loop(seconds=60)` / `async def trade_monitor():`:

```python
async def _record_equity_sample(live_prices: dict) -> None:
    """v172: one equity sample after this tick's closes (see equity_recorder).

    `record_sample` already swallows its own failures; this guard covers the
    thread hand-off itself, so recording can never break the monitor."""
    try:
        await asyncio.to_thread(equity_recorder.record_sample, live_prices)
    except Exception as exc:
        log.warning("trade_monitor: equity sample failed: %s", exc, exc_info=True)
```

Inside `trade_monitor`, after the plan-manager block, so the sequence reads:

```python
    if plan_events:
        await _post_plan_events(plan_events)
    await _record_equity_sample(live_prices)
    await _retry_notifications()
```

Append one sentence to `trade_monitor`'s docstring: `After the closes, one equity sample is recorded (v172, equity_recorder): it reuses this tick's prices and never raises.`

- [ ] **Step 6: Run the recorder and the existing monitor tests**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_equity_recorder.py`
Expected: all 10 PASS.
Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_trade_monitor_task.py`
Expected: PASS, same count as on `main` (in those tests the hook is a no-op outside the session, or a harmless empty-book write inside it).

- [ ] **Step 7: Check complexity**

Run: `python -m radon cc -s -n C $WT/swingbot/commands/scanning/equity_recorder.py`
Expected: no output (every function below C).
Run: `python -m radon cc -s $WT/swingbot/commands/scanning/loops.py | grep -E "trade_monitor|_record_equity_sample"`
Expected: `trade_monitor` still `C (13)` or lower (must stay ≤ 14), `_record_equity_sample` `A (2)`.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/commands/scanning/equity_recorder.py swingbot/commands/scanning/loops.py tests/commands/test_equity_recorder.py
git -C $WT commit -m "feat(bot): trade_monitor records a live equity sample every 5 minutes in session (v172)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

### Task V172-5: `GET /api/v1/equity/candles`

**Model:** sonnet — an admin endpoint over finished helpers

**Files:**
- Create: `swingbot/admin/api_v1/equity.py`
- Modify: `swingbot/admin/api_v1/__init__.py:208-210` (the route-module import tuple in `register()`)
- Test: `tests/admin/test_api_v1_equity.py` (suite `admin`)

**Interfaces:**
- Consumes (V172-1, `swingbot.core.tracking.equity`): `realized_legs(trades: list[dict]) -> list[RealizedLeg]` (main book applied inside); `starting_balance() -> Decimal`.
- Consumes (V172-2): `equity_samples_repo().list_rows(*, sources: tuple[str, ...], since=None, conn=None) -> list[dict]` (ordered by `at`, `at` tz-aware UTC, money floats); `.earliest_at(source: str, conn=None) -> datetime | None`; `EquitySampleRepository.upsert_many(rows: list[dict], conn=None) -> int` (tests seed through it).
- Consumes (V172-3, `swingbot.core.tracking.equity_candles`): `TIMEFRAMES = ("1H", "4H", "1D", "1W")`; `mtm_candles(rows: list[dict], tf: str) -> list[dict]`; `realized_candles(legs, start: Decimal, tf: str) -> list[dict]`. Both return candles with `change`/`change_pct` already filled by `add_change`, oldest first.
- Consumes (existing): `swingbot.admin.api_v1.ApiError(code, message, status)`, `api_v1` blueprint, `iso(value) -> str | None` (`__init__.py:109`), `require_auth` (`api_v1/auth.py`), `config.CURRENCY_SYMBOL` (`swingbot/config.py:510`), `TradeLog().get_trades(status=None, limit=None, sort_by="opened_at")` (`performance.py:1204`).
- Produces: route `equity_candles()` at `GET /api/v1/equity/candles`; module constants `DEFAULT_LIMIT = 120`, `MAX_LIMIT = 500`, `BASES = ("mtm", "realized")`. Response keys exactly `tf, basis, currency_symbol, candles, recording_since, as_of`; candle keys exactly `t, o, h, l, c, change, change_pct, samples, skipped, approx` (V172-8's `EquityCandlesResponse` mirrors this contract test).

Rules this task enforces (Global Constraints, API and Bucketing): `tf` default `1D`, `basis` default `mtm`, `limit` default 120 and any value outside 1..500 (or not an integer) is a 400 `invalid`; 1H/4H with `mtm` read `live` rows only, 1D/1W `mtm` read `live` and `backfill`; `realized` is built from the realized legs, never from samples; `limit` slices the most recent candles after `change` was computed over the whole series, so the first returned candle still compares with its true predecessor. `_equity_30d()` and `equity_30d` are not touched.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_api_v1_equity.py`:

```python
"""v172: GET /api/v1/equity/candles -- the contract the SPA's EquityCandlesResponse mirrors."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from swingbot import config
from swingbot.core.db.repositories.equity_samples import EquitySampleRepository
from tests.admin.api_v1_contract import (NULLABLE_NUMBER, NULLABLE_STR, NUMBER, assert_error,
                                         assert_shape)
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
URL = "/api/v1/equity/candles"
BASE = 10000.0

BODY = {"tf": str, "basis": str, "currency_symbol": str, "candles": list,
        "recording_since": NULLABLE_STR, "as_of": str}
CANDLE = {"t": str, "o": NUMBER, "h": NUMBER, "l": NUMBER, "c": NUMBER, "change": NUMBER,
          "change_pct": NULLABLE_NUMBER, "samples": int, "skipped": int, "approx": bool}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def account(admin_app):
    # base_balance stated outright: the conftest seeds only `balance`, and
    # load_account_config would then derive the base from realized P&L.
    seed_store("account", {"base_balance": BASE, "balance": BASE, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})


def _at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def _row(at, value, *, source="live", kind="point", skipped=0):
    return {"at": at, "realized_balance": Decimal(str(value)), "unrealized_pnl": Decimal("0"),
            "equity": Decimal(str(value)), "open_n": 0, "skipped_n": skipped,
            "source": source, "kind": kind,
            "backfill_run": "r1@bars-asof-2026-10-13" if source == "backfill" else None}


def _two_live_days():
    """Wed 2026-10-14 and Thu 2026-10-15, New York session hours (EDT = UTC-4)."""
    EquitySampleRepository().upsert_many([
        _row(_at(14, 13, 35), 10000), _row(_at(14, 15), 10100), _row(_at(14, 19, 55), 10050),
        _row(_at(15, 13, 35), 10080), _row(_at(15, 19, 55), 10200, skipped=2),
    ])


def _backfilled_tuesday():
    """Tue 2026-10-13 rebuilt from daily bars: open 09:30 NY, close 16:00 NY."""
    EquitySampleRepository().upsert_many([
        _row(_at(13, 13, 30), 9900, source="backfill"),
        _row(_at(13, 13, 30), 9950, source="backfill", kind="day_high"),
        _row(_at(13, 13, 30), 9880, source="backfill", kind="day_low"),
        _row(_at(13, 20), 9920, source="backfill"),
    ])


def _closed(tid, pnl, closed_at):
    return {"id": tid, "ticker": "AAPL", "direction": "bullish", "status": "win" if pnl > 0 else "loss",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 100.0 + pnl / 10, "shares": 10.0,
            "opened_at": "2026-10-13T14:00:00+00:00", "closed_at": closed_at,
            "realized_pnl_amount": pnl, "ledger": "main"}


def test_requires_auth(client):
    assert_error(client.get(URL), "auth", 401)


def test_an_empty_table_returns_the_defaults_and_no_candles(logged_in, account):
    body = logged_in.get(URL).get_json()
    assert_shape(body, BODY)
    assert (body["tf"], body["basis"], body["candles"]) == ("1D", "mtm", [])
    assert body["currency_symbol"] == config.CURRENCY_SYMBOL
    assert body["recording_since"] is None
    assert datetime.fromisoformat(body["as_of"]).tzinfo is not None


def test_daily_mtm_candles_from_live_samples(logged_in, account):
    _two_live_days()
    body = logged_in.get(URL).get_json()
    for candle in body["candles"]:
        assert_shape(candle, CANDLE, where="candle")
    first, second = body["candles"]
    assert (first["t"], first["o"], first["h"], first["l"], first["c"]) == (
        "2026-10-14", 10000.0, 10100.0, 10000.0, 10050.0)
    assert (first["change"], first["change_pct"], first["samples"]) == (50.0, 0.5, 3)
    assert (second["t"], second["o"], second["c"], second["change"]) == (
        "2026-10-15", 10080.0, 10200.0, 150.0)
    assert second["change_pct"] == 1.49                     # 150 / 10050 x 100
    assert (second["skipped"], second["approx"]) == (2, False)
    assert body["recording_since"] == "2026-10-14T13:35:00+00:00"


def test_limit_keeps_the_latest_candles_and_their_true_predecessor_change(logged_in, account):
    _two_live_days()
    (only,) = logged_in.get(URL + "?limit=1").get_json()["candles"]
    assert (only["t"], only["change"]) == ("2026-10-15", 150.0)


def test_daily_mtm_includes_backfill_rows_as_approx(logged_in, account):
    _backfilled_tuesday()
    _two_live_days()
    first = logged_in.get(URL + "?tf=1D").get_json()["candles"][0]
    assert (first["t"], first["o"], first["h"], first["l"], first["c"]) == (
        "2026-10-13", 9900.0, 9950.0, 9880.0, 9920.0)
    assert first["approx"] is True


def test_hourly_mtm_never_reads_backfill_rows(logged_in, account):
    _backfilled_tuesday()
    _two_live_days()
    body = logged_in.get(URL + "?tf=1H").get_json()
    assert body["tf"] == "1H"
    assert body["candles"][0]["t"] == "2026-10-14T09:00:00-04:00"
    assert not any(c["t"].startswith("2026-10-13") for c in body["candles"])
    assert not any(c["approx"] for c in body["candles"])
    four = logged_in.get(URL + "?tf=4H").get_json()["candles"]
    assert not any(c["t"].startswith("2026-10-13") for c in four)


def test_realized_basis_steps_through_closed_legs_not_samples(logged_in, account):
    seed_store("trades", [_closed("t1", 50.0, "2026-10-14T15:00:00+00:00"),
                          _closed("t2", -20.0, "2026-10-14T18:00:00+00:00")])
    body = logged_in.get(URL + "?basis=realized").get_json()
    assert body["basis"] == "realized"
    (day,) = body["candles"]
    assert (day["t"], day["o"], day["h"], day["l"], day["c"]) == (
        "2026-10-14", 10000.0, 10050.0, 10000.0, 10030.0)
    assert (day["samples"], day["skipped"], day["approx"]) == (2, 0, False)
    assert body["recording_since"] is None                  # no live rows yet


@pytest.mark.parametrize("query, name", [
    ("tf=1M", "tf"), ("tf=1d", "tf"), ("basis=gross", "basis"),
    ("limit=0", "limit"), ("limit=501", "limit"), ("limit=abc", "limit"),
])
def test_a_bad_parameter_is_a_400_naming_the_allowed_values(logged_in, account, query, name):
    response = logged_in.get(f"{URL}?{query}")
    assert_error(response, "invalid", 400)
    message = response.get_json()["error"]["message"]
    assert message.startswith(f"{name} must be one of")


def test_the_tf_error_lists_every_timeframe(logged_in, account):
    message = logged_in.get(URL + "?tf=2H").get_json()["error"]["message"]
    assert message == "tf must be one of 1H, 4H, 1D, 1W"


def test_the_limit_cap_itself_is_allowed(logged_in, account):
    assert logged_in.get(URL + "?limit=500").status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_equity.py`
Expected: `test_requires_auth` FAILS with 404 (no route yet; `assert_error` expected 401), and every other test FAILS on a 404 response.

- [ ] **Step 3: Create the route module**

Create `swingbot/admin/api_v1/equity.py`:

```python
"""v172: GET /api/v1/equity/candles -- the Dashboard's equity candlestick chart.

Candles are built on request from raw rows (spec v172, approach A):
- `basis=mtm` (default): `equity_samples` rows, live and backfill for 1D/1W,
  live only for 1H/4H (intraday history starts at deploy, by design);
- `basis=realized`: one step per realized leg of the main book
  (`swingbot.core.tracking.equity.realized_legs`), never the samples.
Bucketing and `change` live in `swingbot.core.tracking.equity_candles`.
`limit` keeps the most recent candles after `change` is computed over the
whole series, so the first returned candle still compares with its real
predecessor. `currency_symbol` is `config.CURRENCY_SYMBOL`, the symbol the
Dashboard already shows (no ISO code exists in config).
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import jsonify, request

from swingbot import config
from swingbot.core.db.repositories.equity_samples import equity_samples_repo
from swingbot.core.tracking import equity, equity_candles

from . import ApiError, api_v1, iso
from .auth import require_auth

DEFAULT_LIMIT = 120
MAX_LIMIT = 500
BASES = ("mtm", "realized")
_INTRADAY = ("1H", "4H")


def _choice(name: str, allowed: tuple[str, ...], default: str) -> str:
    raw = request.args.get(name)
    if raw is None:
        return default
    if raw not in allowed:
        raise ApiError("invalid", f"{name} must be one of {', '.join(allowed)}", 400)
    return raw


def _limit() -> int:
    raw = request.args.get("limit")
    if raw is None:
        return DEFAULT_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 0
    if not 1 <= value <= MAX_LIMIT:
        raise ApiError("invalid", f"limit must be one of 1..{MAX_LIMIT}", 400)
    return value


def _mtm(tf: str) -> list[dict]:
    sources = ("live",) if tf in _INTRADAY else ("live", "backfill")
    return equity_candles.mtm_candles(equity_samples_repo().list_rows(sources=sources), tf)


def _realized(tf: str) -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    trades = TradeLog().get_trades(status=None, limit=None, sort_by="opened_at") or []
    return equity_candles.realized_candles(equity.realized_legs(trades),
                                           equity.starting_balance(), tf)


@api_v1.route("/equity/candles", methods=["GET"])
@require_auth
def equity_candles_view():
    tf = _choice("tf", equity_candles.TIMEFRAMES, "1D")
    basis = _choice("basis", BASES, "mtm")
    limit = _limit()
    candles = _mtm(tf) if basis == "mtm" else _realized(tf)
    return jsonify({
        "tf": tf,
        "basis": basis,
        "currency_symbol": config.CURRENCY_SYMBOL,
        "candles": candles[-limit:],
        "recording_since": iso(equity_samples_repo().earliest_at("live")),
        "as_of": iso(datetime.now(timezone.utc)),
    })
```

Note: the view function is named `equity_candles_view`, not `equity_candles`, because `equity_candles` is the imported bucketing module in this file; the ledger's "route `equity_candles()`" means this route. Flask's endpoint name becomes `api_v1.equity_candles_view`; nothing references it by name.

- [ ] **Step 4: Register the module**

In `swingbot/admin/api_v1/__init__.py` `register()` (lines 208-210), add `equity` to the import tuple, keeping it alphabetical:

```python
    from . import (analytics, calendar, dashboard, equity, jobs, market,  # noqa: F401
                   ops_health, reports, research, risk, session, system,
                   trade_commands, trades, versions, watchlist)  # (register routes)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_equity.py`
Expected: PASS (15 tests: 9 plain + 6 parametrized).
Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py`
Expected: PASS, unchanged count (`equity_30d` untouched).

- [ ] **Step 6: Check complexity**

Run: `python -m radon cc -s -n C $WT/swingbot/admin/api_v1/equity.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/admin/api_v1/equity.py swingbot/admin/api_v1/__init__.py tests/admin/test_api_v1_equity.py
git -C $WT commit -m "feat(admin): GET /api/v1/equity/candles serves mtm and realized equity candles (v172)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

### Task V172-6: Backfill day-row builder (clamping, four rows a day)

**Model:** opus — no-lookahead territory (bar extremes vs holding window), crosses `core/tracking` and `core/market`

**Files:**
- Create: `scripts/data/backfill_equity_samples.py` (builder half; V172-7 adds the fetch and the CLI to the same file)
- Test: `tests/scripts/test_backfill_equity_samples.py` (suite `tooling`; V172-7 appends to it)

**Interfaces:**
- Consumes (V172-1, `swingbot.core.tracking.equity`): `parse_ts(value: str | datetime | None) -> datetime | None` (tz-aware UTC); `main_book(trades: list[dict]) -> list[dict]`; `RealizedLeg(at: datetime, amount: Decimal, trade_id)`; `realized_legs(trades: list[dict]) -> list[RealizedLeg]`; `realized_balance_at(start: Decimal, legs: Sequence[RealizedLeg], at: datetime) -> Decimal` (legs with `at <= t`); `unrealized_decimal(entry, direction: str, open_shares, price) -> Decimal | None` (unrounded; `None` without shares, entry or price).
- Consumes (existing): `swingbot.core.market.session.US_MARKET_TZ` (`session.py:12`); `swingbot.core.tracking.performance.expand_trade_legs(trade) -> list[dict]` (`performance.py:408`: one row per realized leg with leg-accurate `shares`, `exit_price`, `closed_at`, `status`, plus an `"open"` remainder row while the trade is open; `[trade]` when the trade has no legs).
- Produces (consumed by V172-7): `SESSION_OPEN = time(9, 30)`, `SESSION_CLOSE = time(16, 0)`, `GAP_REASONS = ("fetch failed", "no bar")`; `session_bounds(day: date) -> tuple[datetime, datetime]` (UTC); `ny_day(value) -> date | None`; `class Bar(NamedTuple): open: float; high: float; low: float; close: float`; `class Skip(NamedTuple): day: date; trade_id: object; ticker: str; reason: str`; `class CoverageGap(Exception)`; `filled_trades(trades: list[dict], plans_by_id: dict) -> list[dict]` (main book, PENDING placeholders dropped); `held_positions(trades: list[dict], day: date) -> list[dict]` (slice dicts with keys `trade_id, ticker, direction, entry, shares, entry_day, exit_day, exit_price`); `bar_for(frame: pd.DataFrame | None, day: date) -> Bar | None`; `position_day(pos: dict, bar: Bar, day: date) -> dict` (keys `open_u, high_u, low_u, close_u`, Decimals); `build_day_rows(day: date, positions: list[dict], bars: dict[str, pd.DataFrame], legs: Sequence[RealizedLeg], start: Decimal, run_tag: str, *, allow_gaps: bool) -> tuple[list[dict], list[Skip]]` (four rows, V172-2 row-dict shape).

**Design decisions this task fixes (read before coding):**

1. **A position is a slice.** `held_positions` expands each main-book trade through `expand_trade_legs`: every realized leg is its own slice (its shares, its exit day, its exit price) and an open trade's remainder is one more slice with no exit. A TP1 partial is therefore two slices: the banked half exits on its leg day, the runner carries on. This is what "shares = open size that day" means per slice, and it keeps the realized walk (V172-1's `realized_legs`, which counts the same legs) and the unrealized side from overlapping.
2. **Clamping (no lookahead).** The price path a slice was exposed to on day `D`: entry day `[entry, close]`; exit day `[open, exit_price]`; same-day round trip `[entry, exit_price]`; other days `[open, high, low, close]`. The bar's open, high and low are never read on an entry day, and its high, low and close never on an exit day. `open_u` is 0 on the entry day (entered during `D`), `close_u` is 0 on the exit day (the leg is realized).
3. **Exit-day extremes are measured net of the exit price.** The spec writes `day_high = realized(D) + Σ favourable extremes`; `realized(D)` already holds the exit leg. Adding the slice's full `pnl(p)` would count the banked leg twice, so an exit-day slice contributes `pnl(p) − pnl(exit_price)` over its path (≤ 0 at the high end, exactly 0 at the exit). With that, `day_high` is the true outer bound: the TP1 test below shows the double-counting version would read 10090 where the reachable maximum is 10060.
4. **Realized(D)** is the walk at the last instant of New York calendar day `D` (`_day_end(D)`), and `realized(D−1)` at the last instant of the day before, so a leg banked after the 16:00 close still belongs to its own day, exactly as its slice's exit day does.
5. **Gaps.** A slice with no bar for `D` is a gap: reason `"fetch failed"` when the ticker's frame is missing or empty, `"no bar"` when the frame lacks that date (or the bar holds a NaN). With `allow_gaps=False`, `build_day_rows` raises `CoverageGap` (V172-7's coverage gate refuses `--apply` before that can happen; the raise is the guard that no gap is ever written silently). With `allow_gaps=True` the slice is left out and counted in `skipped_n`. A slice with no size, no entry, or (on its exit day) no exit price is a non-gap skip (`"no size"`, `"no entry"`, `"no exit price"`), counted in `skipped_n` either way.
6. **PENDING placeholders.** `filled_trades` keeps the main book and drops an `open` trade whose plan exists with a status other than `ACTIVE`/`PARTIAL`, the filter `live_open_positions` applies (Global Constraints, Open positions). No-plan trades and closed trades are kept.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_backfill_equity_samples.py`:

```python
"""v172: the equity backfill -- clamped day rows (V172-6); the CLI tests follow (V172-7)."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from scripts.data import backfill_equity_samples as bes
from swingbot.core.tracking import equity

START = Decimal("10000")
MON, TUE, WED = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
TAG = "20261008T120000Z@bars-asof-2026-10-07"

# Long AAPL: entered Mon 10:00 NY, exited Wed 14:00 NY at 110 (+100).
AAPL = {"id": "a1", "ticker": "AAPL", "direction": "bullish", "status": "win",
        "entry": 100.0, "stop_loss": 95.0, "shares": 10.0, "exit_price": 110.0,
        "opened_at": "2026-10-05T14:00:00+00:00", "closed_at": "2026-10-07T18:00:00+00:00",
        "realized_pnl_amount": 100.0, "ledger": "main"}
# Short MSFT: entered Tue 11:00 NY, still open.
MSFT = {"id": "m1", "ticker": "MSFT", "direction": "bearish", "status": "open",
        "entry": 200.0, "stop_loss": 210.0, "shares": 5.0,
        "opened_at": "2026-10-06T15:00:00+00:00", "ledger": "main"}
TRADES = [AAPL, MSFT]


def _frame(bars):
    return pd.DataFrame([{"Open": o, "High": h, "Low": low, "Close": c}
                         for (o, h, low, c) in bars.values()],
                        index=pd.DatetimeIndex([pd.Timestamp(d) for d in bars]))


BARS = {
    "AAPL": _frame({MON: (99, 104, 98, 102), TUE: (102, 106, 101, 105), WED: (105, 112, 104, 111)}),
    "MSFT": _frame({TUE: (201, 203, 196, 198), WED: (198, 199, 194, 195)}),
}


def _rows(day, *, trades=TRADES, bars=BARS, allow_gaps=False):
    return bes.build_day_rows(day, bes.held_positions(trades, day), bars,
                              equity.realized_legs(trades), START, TAG, allow_gaps=allow_gaps)


def _kinds_and_equity(rows):
    return [(row["kind"], row["equity"]) for row in rows]


def test_session_bounds_are_new_york_open_and_close_in_utc():
    assert bes.session_bounds(MON) == (datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc),
                                       datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc))
    assert bes.session_bounds(date(2026, 12, 7)) == (       # EST, UTC-5
        datetime(2026, 12, 7, 14, 30, tzinfo=timezone.utc),
        datetime(2026, 12, 7, 21, 0, tzinfo=timezone.utc))


@pytest.mark.parametrize("day, expected", [
    # entry day of AAPL: path 100 -> 102; open contributes 0
    (MON, [("point", 10000), ("day_high", 10020), ("day_low", 10000), ("point", 10020)]),
    # AAPL full bar; MSFT entry day (short, path 200 -> 198)
    (TUE, [("point", 10020), ("day_high", 10070), ("day_low", 10010), ("point", 10060)]),
    # AAPL exit day (path 105 -> 110, net of the banked +100); MSFT full bar
    (WED, [("point", 10060), ("day_high", 10130), ("day_low", 10055), ("point", 10125)]),
])
def test_four_rows_a_day_with_clamped_extremes(day, expected):
    rows, skips = _rows(day)
    assert skips == []
    assert _kinds_and_equity(rows) == expected
    open_at, close_at = bes.session_bounds(day)
    assert [row["at"] for row in rows] == [open_at, open_at, open_at, close_at]
    assert {(row["source"], row["backfill_run"]) for row in rows} == {("backfill", TAG)}


def test_the_open_point_uses_yesterdays_realized_and_the_rest_todays():
    rows, _ = _rows(WED)
    assert [row["realized_balance"] for row in rows] == [10000, 10100, 10100, 10100]
    assert [row["unrealized_pnl"] for row in rows] == [60, 30, -45, 25]
    assert {(row["open_n"], row["skipped_n"]) for row in rows} == {(2, 0)}


def _pos(*, entry_day=MON, exit_day=None, exit_price=None, direction="bullish"):
    return {"trade_id": "x", "ticker": "X", "direction": direction, "entry": 100.0,
            "shares": 1.0, "entry_day": entry_day, "exit_day": exit_day, "exit_price": exit_price}


def test_entry_day_reads_no_bar_data_from_before_the_entry():
    bar = bes.Bar(open=50.0, high=999.0, low=1.0, close=101.0)
    assert bes.position_day(_pos(), bar, MON) == {
        "open_u": 0, "high_u": 1, "low_u": 0, "close_u": 1}


def test_exit_day_reads_no_bar_data_from_after_the_exit():
    bar = bes.Bar(open=102.0, high=999.0, low=1.0, close=50.0)
    assert bes.position_day(_pos(exit_day=WED, exit_price=105.0), bar, WED) == {
        "open_u": 2, "high_u": 0, "low_u": -3, "close_u": 0}


def test_a_same_day_round_trip_runs_entry_to_exit_only():
    bar = bes.Bar(open=90.0, high=999.0, low=1.0, close=80.0)
    assert bes.position_day(_pos(exit_day=MON, exit_price=103.0), bar, MON) == {
        "open_u": 0, "high_u": 0, "low_u": -3, "close_u": 0}


def test_a_short_on_a_full_day_favours_the_low():
    bar = bes.Bar(open=98.0, high=99.0, low=94.0, close=95.0)
    assert bes.position_day(_pos(entry_day=MON, direction="bearish"), bar, TUE) == {
        "open_u": 2, "high_u": 6, "low_u": 1, "close_u": 5}


def test_a_tp1_partial_is_two_slices_and_its_banked_leg_is_counted_once():
    leg = {"fraction": 0.5, "exit_price": 106.0, "r": 1.2, "reason": "tp1",
           "closed_at": "2026-10-06T16:00:00+00:00"}               # Tue 12:00 NY, at the bar high
    trade = {**AAPL, "id": "p1", "status": "open", "exit_price": None, "closed_at": None,
             "realized_pnl_amount": None, "legs": [leg]}
    held = bes.held_positions([trade], TUE)
    assert [(p["shares"], p["exit_day"], p["exit_price"]) for p in held] == [
        (5.0, TUE, 106.0), (5.0, None, None)]
    assert [(p["shares"], p["exit_day"]) for p in bes.held_positions([trade], WED)] == [(5.0, None)]
    rows, _ = _rows(TUE, trades=[trade])
    # Banked +30 at 106. Both halves at 106 is the reachable high: 10000 + 30 + 30 = 10060.
    # Adding the banked half's full pnl on top of realized(D) would read 10090.
    assert _kinds_and_equity(rows) == [
        ("point", 10020), ("day_high", 10060), ("day_low", 10015), ("point", 10055)]


def test_weak_and_outlook_trades_never_enter_a_day():
    weak = {**MSFT, "id": "w1", "ledger": "weak"}
    outlook = {**MSFT, "id": "o1", "origin": "next_session"}
    assert bes.held_positions([weak, outlook], TUE) == []


def test_filled_trades_drops_pending_placeholders_only():
    pending = {**MSFT, "id": "pp", "plan_id": "P1"}
    active = {**MSFT, "id": "pa", "plan_id": "P2"}
    closed = {**AAPL, "plan_id": "P3"}
    plans = {"P1": {"status": "PENDING"}, "P2": {"status": "ACTIVE"}, "P3": {"status": "CLOSED"}}
    kept = bes.filled_trades([pending, active, closed, MSFT], plans)
    assert [t["id"] for t in kept] == ["pa", "a1", "m1"]


def test_a_missing_bar_is_a_gap_refused_unless_allowed():
    bars = {"AAPL": BARS["AAPL"], "MSFT": _frame({TUE: (201, 203, 196, 198)})}
    with pytest.raises(bes.CoverageGap):
        _rows(WED, bars=bars)
    rows, skips = _rows(WED, bars=bars, allow_gaps=True)
    assert skips == [bes.Skip(WED, "m1", "MSFT", "no bar")]
    assert {(row["open_n"], row["skipped_n"]) for row in rows} == {(1, 1)}
    assert rows[-1]["equity"] == 10100                     # AAPL realized, MSFT left out


def test_a_ticker_with_no_frame_is_a_fetch_failure_gap():
    _, skips = _rows(WED, bars={"AAPL": BARS["AAPL"]}, allow_gaps=True)
    assert [s.reason for s in skips] == ["fetch failed"]


def test_an_unsized_position_is_skipped_but_is_not_a_gap():
    unsized = {**MSFT, "shares": None}
    rows, skips = _rows(WED, trades=[AAPL, unsized])          # allow_gaps=False: no raise
    assert skips == [bes.Skip(WED, "m1", "MSFT", "no size")]
    assert rows[0]["skipped_n"] == 1


def test_bar_for_matches_by_date_and_rejects_nan():
    frame = _frame({MON: (1, 2, 0.5, float("nan"))})
    assert bes.bar_for(frame, MON) is None
    assert bes.bar_for(BARS["AAPL"], MON) == bes.Bar(99.0, 104.0, 98.0, 102.0)
    assert bes.bar_for(BARS["AAPL"], date(2026, 10, 8)) is None
    assert bes.bar_for(None, MON) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_backfill_equity_samples.py`
Expected: collection error, `ImportError: cannot import name 'backfill_equity_samples' from 'scripts.data'`.

- [ ] **Step 3: Write the builder**

Create `scripts/data/backfill_equity_samples.py`:

```python
#!/usr/bin/env python3
"""v172: one-off backfill of daily equity samples from raw daily bars.

Rebuilds `equity_samples` rows (source="backfill") for every NYSE session
day from the first main-book trade to the session before the first live
sample, four rows a day (spec v172 § 3):

    point    @ 09:30 NY   realized(D-1) + sum of unrealized at the bar open
    day_high @ 09:30 NY   realized(D)   + sum of favourable extremes
    day_low  @ 09:30 NY   realized(D)   + sum of adverse extremes
    point    @ 16:00 NY   realized(D)   + sum of unrealized at the bar close

Each realized leg and each open remainder is one slice. Its extremes are
clamped to the time it was held: entry day = entry price .. bar close; exit
day = bar open .. exit price (realized at the close); a same-day round trip
= entry .. exit; other days = the bar's O/H/L/C. On an exit day the
extremes are measured net of the exit price, because realized(D) already
holds that leg. The high and low are outer bounds, never measured values:
every candle built from these rows is approx.

Bars are UNADJUSTED daily bars this script fetches itself (yfinance,
auto_adjust=False) for traded tickers only, saved under
data/backfill_equity_samples/<run_id>/<TICKER>.csv. Never read here:
backtest_cache.py (adjusted), market_data/, training_data.load_daily,
fetch_backtest_data.load_cached.

    python scripts/data/backfill_equity_samples.py                       # dry run: coverage report
    python scripts/data/backfill_equity_samples.py --apply               # write days with no backfill rows
    python scripts/data/backfill_equity_samples.py --apply --replace     # rewrite every backfill row
    python scripts/data/backfill_equity_samples.py --apply --allow-gaps  # write despite missing bars
    python scripts/data/backfill_equity_samples.py --recompute-realized [--apply]

Production (after the v172 deploy):
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py"
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py --apply"
"""
from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import NamedTuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.market.session import US_MARKET_TZ  # noqa: E402
from swingbot.core.tracking import equity  # noqa: E402
from swingbot.core.tracking.performance import expand_trade_legs  # noqa: E402

SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
GAP_REASONS = ("fetch failed", "no bar")
ZERO = Decimal("0")
_HELD_STATUSES = ("open", "win", "loss", "closed")
_LIVE_PLAN_STATUSES = ("ACTIVE", "PARTIAL")
_OHLC = ("Open", "High", "Low", "Close")


class Bar(NamedTuple):
    open: float
    high: float
    low: float
    close: float


class Skip(NamedTuple):
    day: date
    trade_id: object
    ticker: str
    reason: str


class CoverageGap(Exception):
    """A slice has no bar for a day and gaps were not allowed."""


def session_bounds(day: date) -> tuple[datetime, datetime]:
    """09:30 and 16:00 New York on `day`, in UTC."""
    def at(clock: time) -> datetime:
        return datetime.combine(day, clock, tzinfo=US_MARKET_TZ).astimezone(timezone.utc)
    return at(SESSION_OPEN), at(SESSION_CLOSE)


def _day_end(day: date) -> datetime:
    """The last instant of New York calendar day `day`, in UTC."""
    midnight = datetime.combine(day + timedelta(days=1), time(0), tzinfo=US_MARKET_TZ)
    return midnight.astimezone(timezone.utc) - timedelta(microseconds=1)


def ny_day(value) -> date | None:
    moment = equity.parse_ts(value)
    return None if moment is None else moment.astimezone(US_MARKET_TZ).date()


def filled_trades(trades: list[dict], plans_by_id: dict) -> list[dict]:
    """Main-book trades that were really filled: an open trade whose plan is
    neither ACTIVE nor PARTIAL is a PENDING placeholder and is dropped."""
    kept = []
    for trade in equity.main_book(trades):
        plan = plans_by_id.get(trade.get("plan_id"))
        if (trade.get("status") == "open" and plan is not None
                and plan.get("status") not in _LIVE_PLAN_STATUSES):
            continue
        kept.append(trade)
    return kept


def _slice(trade: dict, row: dict, entry_day: date) -> dict | None:
    status = row.get("status")
    if status not in _HELD_STATUSES:
        return None
    exit_day = None if status == "open" else ny_day(row.get("closed_at"))
    if status != "open" and exit_day is None:
        return None                       # a close with no time cannot be placed on a day
    return {"trade_id": trade.get("id"), "ticker": trade.get("ticker"),
            "direction": trade.get("direction"), "entry": trade.get("entry"),
            "shares": row.get("shares"), "entry_day": entry_day, "exit_day": exit_day,
            "exit_price": None if status == "open" else row.get("exit_price")}


def _slices(trade: dict) -> list[dict]:
    """One slice per realized leg plus the open remainder (expand_trade_legs)."""
    entry_day = ny_day(trade.get("opened_at"))
    if entry_day is None:
        return []
    slices = (_slice(trade, row, entry_day) for row in expand_trade_legs(trade))
    return [piece for piece in slices if piece is not None]


def _held_on(piece: dict, day: date) -> bool:
    return piece["entry_day"] <= day and (piece["exit_day"] is None or piece["exit_day"] >= day)


def held_positions(trades: list[dict], day: date) -> list[dict]:
    """Every main-book slice open at any point on `day` (pass `filled_trades` output)."""
    return [piece for trade in equity.main_book(trades) for piece in _slices(trade)
            if _held_on(piece, day)]


def bar_for(frame: pd.DataFrame | None, day: date) -> Bar | None:
    """The daily bar dated `day`, or None when absent or holding a NaN."""
    if frame is None or frame.empty:
        return None
    hit = frame[frame.index.date == day]
    if hit.empty:
        return None
    values = [hit.iloc[0].get(column) for column in _OHLC]
    if any(value is None or pd.isna(value) for value in values):
        return None
    return Bar(*(float(value) for value in values))


def _path(pos: dict, bar: Bar, day: date) -> tuple[list[float], float | None, float | None]:
    """(prices the slice was exposed to on `day`, its open price, its close price).

    No lookahead: the entry day never reads the bar's open/high/low, the exit
    day never its high/low/close."""
    entered, exited = pos["entry_day"] == day, pos["exit_day"] == day
    first = pos["entry"] if entered else bar.open
    last = pos["exit_price"] if exited else bar.close
    inner = [] if entered or exited else [bar.high, bar.low]
    return [first, *inner, last], (None if entered else bar.open), (None if exited else bar.close)


def position_day(pos: dict, bar: Bar, day: date) -> dict:
    """One slice's unrealized amounts on `day`: at the open, its favourable and
    adverse extremes, and at the close (Decimals, unrounded)."""
    def pnl(price: float) -> Decimal:
        return equity.unrealized_decimal(pos["entry"], pos["direction"], pos["shares"], price)

    path, open_price, close_price = _path(pos, bar, day)
    banked = pnl(pos["exit_price"]) if pos["exit_day"] == day else ZERO
    values = [pnl(price) - banked for price in path]
    return {"open_u": ZERO if open_price is None else pnl(open_price),
            "high_u": max(values), "low_u": min(values),
            "close_u": ZERO if close_price is None else pnl(close_price)}


def _unpriceable(pos: dict, day: date) -> str | None:
    if not pos["shares"]:
        return "no size"
    if pos["entry"] is None:
        return "no entry"
    if pos["exit_day"] == day and pos["exit_price"] is None:
        return "no exit price"
    return None


def _priceable(pos: dict, frame: pd.DataFrame | None, day: date) -> tuple[str | None, Bar | None]:
    reason = _unpriceable(pos, day)
    if reason:
        return reason, None
    bar = bar_for(frame, day)
    if bar is None:
        return ("fetch failed" if frame is None or frame.empty else "no bar"), None
    return None, bar


def _price_positions(day: date, positions: list[dict], bars: dict, *,
                     allow_gaps: bool) -> tuple[dict, int, list[Skip]]:
    totals = dict.fromkeys(("open_u", "high_u", "low_u", "close_u"), ZERO)
    counted, skips = 0, []
    for pos in positions:
        reason, bar = _priceable(pos, bars.get(pos["ticker"]), day)
        if reason in GAP_REASONS and not allow_gaps:
            raise CoverageGap(f"{pos['ticker']} on {day}: {reason}")
        if reason:
            skips.append(Skip(day, pos["trade_id"], pos["ticker"], reason))
            continue
        for key, value in position_day(pos, bar, day).items():
            totals[key] += value
        counted += 1
    return totals, counted, skips


def _row(at: datetime, kind: str, realized: Decimal, unrealized: Decimal, counted: int,
         skipped: int, run_tag: str) -> dict:
    return {"at": at, "realized_balance": realized, "unrealized_pnl": unrealized,
            "equity": realized + unrealized, "open_n": counted, "skipped_n": skipped,
            "source": "backfill", "kind": kind, "backfill_run": run_tag}


def build_day_rows(day: date, positions: list[dict], bars: dict[str, pd.DataFrame],
                   legs: Sequence[equity.RealizedLeg], start: Decimal, run_tag: str, *,
                   allow_gaps: bool) -> tuple[list[dict], list[Skip]]:
    """The four backfill rows for session `day`, and the slices left out."""
    totals, counted, skips = _price_positions(day, positions, bars, allow_gaps=allow_gaps)
    open_at, close_at = session_bounds(day)
    before = equity.realized_balance_at(start, legs, _day_end(day - timedelta(days=1)))
    after = equity.realized_balance_at(start, legs, _day_end(day))
    common = (counted, len(skips), run_tag)
    return [
        _row(open_at, "point", before, totals["open_u"], *common),
        _row(open_at, "day_high", after, totals["high_u"], *common),
        _row(open_at, "day_low", after, totals["low_u"], *common),
        _row(close_at, "point", after, totals["close_u"], *common),
    ], skips
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_backfill_equity_samples.py`
Expected: PASS (16 tests: 13 plain + 3 parametrized day cases).

- [ ] **Step 5: Check complexity**

Run: `python -m radon cc -s -n C $WT/scripts/data/backfill_equity_samples.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/data/backfill_equity_samples.py tests/scripts/test_backfill_equity_samples.py
git -C $WT commit -m "feat(scripts): equity backfill day-row builder with holding-window clamping (v172)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```
