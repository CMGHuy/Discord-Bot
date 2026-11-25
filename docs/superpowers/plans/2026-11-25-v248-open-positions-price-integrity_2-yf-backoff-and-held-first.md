# v248 — Open-positions price integrity — Part 2: yfinance backoff and held-first

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V248-5" -A 400 <this file>`); never read a part whole.

**Spec:** [2026-11-25-v248-open-positions-price-integrity-design.md](../specs/2026-11-25-v248-open-positions-price-integrity-design.md) § 3 (held tickers first), § 4 (yfinance per-ticker backoff), the config line of § 5 and the § Testing rows 3 and 4.
**Index:** [2026-11-25-v248-open-positions-price-integrity_0-index.md](2026-11-25-v248-open-positions-price-integrity_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and the binding "Decisions the spec left open" live there; every task below implicitly includes them.
**Brief:** `.superpowers/briefs/2026-11-25-v248-open-positions-price-integrity.md` §3k, §3l, §4 (refresher and marketdata test patterns), §7 traps.

Tasks: V248-4 (config field + `yf_backoff` module), V248-5 (backoff wired at `data._yf_quote_details`), V248-6 (refresher held-first batch).

Order: V248-4 → V248-5 (V248-5 calls `yf_backoff.partition` / `record`). V248-6 runs after **V248-1** (both edit `swingbot/admin/market_values.py` and `tests/admin_market/test_market_values.py`; V248-1 adds `MarketQuote.error_at`, a trailing field with a default, so V248-6 builds `MarketQuote` by keyword). V248-4 may run beside V248-1.

Decisions made in this part (within the ledger):
- **The backoff touches the shared store only when `config.MARKETDATA_LAYER == "on"`** (production runs `on`), the same gate as `shared/budget.py:47` and `shared/tape.py:106`. `off` / `count` keep the exact pre-v248 yfinance path; `tests/conftest.py` pins `off`, so no existing test meets the store by accident.
- `BackoffBatch` gains a fourth field with a default, `known: bool = True`, set False when the state read failed open, so `record` never overwrites counts it could not read. Additive; only V248-5 consumes `BackoffBatch`.
- "A live price this session" (§ 3) is a priced quote whose `as_of` falls on the **session day**: the ET date of `now` when it is an NYSE trading day at or after 04:00 ET, otherwise the ET date of `session.last_regular_close(now)`. So a weekend reads Friday's trades as this session's, and a pre-market trade today counts.
- The refresher's per-cycle yfinance budget stays `ADMIN_REFRESH_YF_FALLBACK_CAP` in total: the priority batch gets the full cap, the rest gets `cap - len(priority)` and keeps today's scan split.

---

# Phase 2 — yfinance backoff and held-first

### Task V248-4: `HELD_PRICE_STALE_ALERT_MIN` config + `yf_backoff` policy and shared-store state (fail open)

**Model:** sonnet — a pure policy module with spec-fixed numbers plus one read and one write through an existing repository, every rule pinned by the tests below.

**Files:**
- Create: `swingbot/core/marketdata/yf_backoff.py`
- Create: `tests/marketdata/test_yf_backoff.py` (suite `market-data`, existing directory: no `suites.toml` edit)
- Modify: `swingbot/config.py` (one `Field` right after `EMPTY_SYMBOLS_ALERT_PCT`, ~l.1036)
- Modify: `.env.example` (after `EMPTY_SYMBOLS_ALERT_PCT=5`, ~l.540)
- Modify: `tests/infra/test_config_ops_alerts.py`

**Interfaces:**
- Consumes: `market_shared_repo().read_entries(keys, *, conn) -> {key: record}` and `.write_entries(rows, *, conn)` (`swingbot/core/db/repositories/market_shared.py:45, 56`; a record carries `key, kind, symbol, fetched_at, source, value`); `side_connection()` (`swingbot/core/db/side_engine.py:86`); `session.session_state(now)` / `session.SESSION_REGULAR` (`swingbot/core/market/session.py:246-258`); `trades_repo().open_trades()` (`swingbot/core/db/repositories/trades.py:18, 82`, rows carry `ticker`); `swallowed(log, tag, exc, msg="", *args, level=...)`.
- Produces (V248-5, V248-7, V248-8): `config.HELD_PRICE_STALE_ALERT_MIN` (int, default 10, min 1, max 120, hot-reload); in `swingbot/core/marketdata/yf_backoff.py`: `KIND = "yf_backoff"`, `MISSES_TO_SKIP = 3`, `FIRST_PAUSE = timedelta(minutes=30)`, `MAX_PAUSE = timedelta(hours=4)`, `entry_key(symbol: str) -> str` (`"yf_backoff:SYM"`), `@dataclass(frozen=True) BackoffState(misses: int = 0, skip_until: datetime | None = None, written_at: datetime | None = None)`, `after_miss(state: BackoffState, now: datetime) -> BackoffState`, `is_skipped(state, now, *, held_in_session: bool, held_cap: timedelta) -> bool`, `@dataclass(frozen=True) BackoffBatch(fetch: list[str], skipped: list[str], states: dict[str, BackoffState], known: bool = True)`, `partition(tickers: list[str], now: datetime | None = None) -> BackoffBatch`, `record(batch: BackoffBatch, got: Iterable[str], now: datetime | None = None) -> None`, `held_symbols(now: datetime | None = None) -> frozenset[str]` (60 s TTL), `_reset_for_tests() -> None`.

**Why.** Spec § 4: a ticker yfinance cannot serve (DOCU) is retried every cycle. After 3 consecutive misses its yfinance fallback pauses 30 min, each further miss after a pause doubles that up to 4 h, and one success resets it; a held ticker in the regular session is never paused longer than `HELD_PRICE_STALE_ALERT_MIN` (index Decision 7: effective `skip_until = min(skip_until, written_at + cap)`, `written_at` = the entry's `fetched_at`). State lives in `market_cache` rows of kind `yf_backoff`, value `{"misses", "skip_until"}`, so the bot and the refresher share it and it survives a restart; no table, no Alembic revision. A busy or down side pool never stops yfinance.

- [ ] **Step 1: Write the failing config tests**

In `tests/infra/test_config_ops_alerts.py` add `"HELD_PRICE_STALE_ALERT_MIN"` to `_KEYS` (the section/attr and `.env.example` tests then cover it), and append:

```python
def test_held_price_threshold_is_hot_whole_minutes():
    f = _fields()["HELD_PRICE_STALE_ALERT_MIN"]
    assert (f.type, f.default, f.min, f.max) == ("number", "10", 1, 120)
    assert f.hot_reloadable is True and f.sensitive is False
    assert config._cast(f, "15") == 15
    assert config.HELD_PRICE_STALE_ALERT_MIN == 10


def test_held_price_help_names_both_stale_thresholds():
    # spec 1c: the panel's red (ADMIN_STALE_PRICE_REGULAR_S) comes first, Discord after this one.
    text = _fields()["HELD_PRICE_STALE_ALERT_MIN"].help
    assert "ADMIN_STALE_PRICE_REGULAR_S" in text and "backoff" in text
```

- [ ] **Step 2: Write the failing backoff tests**

Create `tests/marketdata/test_yf_backoff.py`:

```python
"""v248 § 4: yfinance per-ticker backoff, shared through market_cache rows of kind yf_backoff."""
import contextlib
import logging
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.db.engine import DatabaseUnavailable
from swingbot.core.db.repositories import trades as trades_mod
from swingbot.core.db.repositories.market_shared import MarketSharedRepository
from swingbot.core.marketdata import yf_backoff as bo
from swingbot.core.marketdata.yf_backoff import BackoffState

UTC = timezone.utc
T0 = datetime(2026, 11, 24, 15, 0, tzinfo=UTC)        # Tue 10:00 ET, regular session
CAP = timedelta(minutes=10)


@pytest.fixture(autouse=True)
def _fresh():
    bo._reset_for_tests()
    yield
    bo._reset_for_tests()


def _misses(n, now=T0):
    state = BackoffState()
    for _ in range(n):
        state = bo.after_miss(state, now)
    return state


# -- pure policy -------------------------------------------------------------------

def test_entry_key_is_upper_case_per_symbol():
    assert bo.KIND == "yf_backoff" and bo.entry_key("docu") == "yf_backoff:DOCU"


def test_two_misses_never_skip():
    state = _misses(2)
    assert (state.misses, state.skip_until) == (2, None)
    assert not bo.is_skipped(state, T0, held_in_session=False, held_cap=CAP)


def test_third_miss_skips_for_30_minutes():
    state = _misses(3)
    assert state.skip_until == T0 + timedelta(minutes=30) and state.written_at == T0
    assert bo.is_skipped(state, T0 + timedelta(minutes=29), held_in_session=False, held_cap=CAP)
    assert not bo.is_skipped(state, T0 + timedelta(minutes=30), held_in_session=False, held_cap=CAP)


@pytest.mark.parametrize("n, pause_min", [(4, 60), (5, 120), (6, 240), (7, 240), (400, 240)])
def test_each_further_miss_doubles_the_pause_capped_at_4h(n, pause_min):
    assert _misses(n).skip_until == T0 + timedelta(minutes=pause_min)


def test_held_ticker_in_session_is_capped_at_the_alert_threshold():
    state = _misses(6)                                   # 4 h pause written at T0
    assert bo.is_skipped(state, T0 + timedelta(minutes=9), held_in_session=True, held_cap=CAP)
    assert not bo.is_skipped(state, T0 + timedelta(minutes=10), held_in_session=True, held_cap=CAP)
    assert bo.is_skipped(state, T0 + timedelta(minutes=10), held_in_session=False, held_cap=CAP)


# -- shared store ------------------------------------------------------------------

@pytest.fixture
def store(db_committed, db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(bo, "held_symbols", lambda now=None: frozenset())
    side_engine.reset()
    yield db_committed
    side_engine.reset()


def _miss_n(symbols, n, now=T0):
    for _ in range(n):
        bo.record(bo.partition(symbols, now), [], now)


def test_unknown_tickers_are_all_fetched(store):
    batch = bo.partition(["AAPL", "DOCU"], T0)
    assert (batch.fetch, batch.skipped, batch.known) == (["AAPL", "DOCU"], [], True)


def test_three_misses_skip_and_the_row_is_shared(store):
    _miss_n(["DOCU"], 3)
    side_engine.reset()                                  # a second client: no in-process state
    batch = bo.partition(["AAPL", "DOCU"], T0 + timedelta(minutes=5))
    assert (batch.fetch, batch.skipped) == (["AAPL"], ["DOCU"])
    row = MarketSharedRepository().read_entries(["yf_backoff:DOCU"], conn=store)["yf_backoff:DOCU"]
    assert (row["kind"], row["symbol"], row["fetched_at"]) == ("yf_backoff", "DOCU", T0)
    assert row["value"] == {"misses": 3, "skip_until": (T0 + timedelta(minutes=30)).isoformat()}


def test_a_success_resets_and_a_clean_success_writes_nothing(store, monkeypatch):
    _miss_n(["DOCU"], 3)
    later = T0 + timedelta(minutes=31)
    bo.record(bo.partition(["DOCU"], later), ["DOCU"], later)
    assert bo.partition(["DOCU"], later).states["DOCU"].misses == 0
    writes = []
    monkeypatch.setattr(bo, "_write_rows", writes.append)
    bo.record(bo.partition(["AAPL"], later), ["AAPL"], later)
    assert writes == []


def test_held_ticker_in_regular_session_returns_after_the_cap(store, monkeypatch):
    _miss_n(["DOCU", "MSFT"], 3)
    monkeypatch.setattr(bo, "held_symbols", lambda now=None: frozenset({"DOCU"}))
    batch = bo.partition(["DOCU", "MSFT"], T0 + timedelta(minutes=11))
    assert (batch.fetch, batch.skipped) == (["DOCU"], ["MSFT"])


def test_held_set_is_not_read_when_nothing_is_in_backoff(store, monkeypatch):
    def boom(now=None):
        raise AssertionError("held_symbols read without need")
    monkeypatch.setattr(bo, "held_symbols", boom)
    assert bo.partition(["AAPL"], T0).fetch == ["AAPL"]


def test_enter_and_leave_log_one_info_line_each(store, caplog):
    caplog.set_level(logging.INFO, logger=bo.__name__)
    _miss_n(["DOCU"], 3, T0)                             # enters at the 3rd miss
    _miss_n(["DOCU"], 1, T0 + timedelta(minutes=31))     # the 4th, after the pause, only doubles
    assert sum("DOCU enters" in r.getMessage() for r in caplog.records) == 1
    later = T0 + timedelta(hours=2)
    bo.record(bo.partition(["DOCU"], later), ["DOCU"], later)
    assert sum("DOCU leaves" in r.getMessage() for r in caplog.records) == 1


# -- fail open ---------------------------------------------------------------------

@pytest.mark.parametrize("exc", [DatabaseUnavailable("side engine backing off"),
                                 sa.exc.TimeoutError("QueuePool limit reached")])
def test_busy_or_down_side_pool_fails_open(monkeypatch, exc):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")

    @contextlib.contextmanager
    def busy():
        raise exc
        yield
    monkeypatch.setattr(bo, "side_connection", busy)
    batch = bo.partition(["DOCU"], T0)
    assert (batch.fetch, batch.skipped, batch.known) == (["DOCU"], [], False)
    bo.record(batch, [], T0)                             # never raises, never writes blind


def test_layer_off_never_touches_the_store(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    touched = []

    def forbidden():
        touched.append(1)                                # the helpers fail open, so count calls
        raise AssertionError("store touched with the layer off")
    monkeypatch.setattr(bo, "side_connection", forbidden)
    batch = bo.partition(["DOCU"], T0)
    bo.record(batch, [], T0)
    assert batch.fetch == ["DOCU"] and touched == []


# -- held set ----------------------------------------------------------------------

def test_held_symbols_reads_open_trades_once_a_minute_and_keeps_the_last_good(monkeypatch):
    calls = []

    class Repo:
        def open_trades(self, *, conn=None):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("db down")
            return [{"ticker": "docu"}, {"ticker": "AAPL"}, {"ticker": None}]
    monkeypatch.setattr(trades_mod, "trades_repo", lambda: Repo())
    assert bo.held_symbols(T0) == frozenset({"DOCU", "AAPL"})
    assert bo.held_symbols(T0 + timedelta(seconds=59)) == frozenset({"DOCU", "AAPL"})
    assert len(calls) == 1
    assert bo.held_symbols(T0 + timedelta(seconds=61)) == frozenset({"DOCU", "AAPL"})   # read failed
    assert bo.held_symbols(T0 + timedelta(seconds=62)) == frozenset({"DOCU", "AAPL"})   # retried
    assert len(calls) == 3
```

- [ ] **Step 3: Run the tests to verify they fail**

Run `/replicate-prod-db` first (the store tests reach the shared `swing-db`).
Run: `python scripts/dev/testrun.py file tests/marketdata/test_yf_backoff.py` and `python scripts/dev/testrun.py file tests/infra/test_config_ops_alerts.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.marketdata.yf_backoff'`; `KeyError: 'HELD_PRICE_STALE_ALERT_MIN'`.

- [ ] **Step 4: Add the config field and its `.env.example` line**

In `swingbot/config.py`, after the `EMPTY_SYMBOLS_ALERT_PCT` field:

```python
    # v248: held-position price watch (spec § 4, § 5).
    Field("HELD_PRICE_STALE_ALERT_MIN", "HELD_PRICE_STALE_ALERT_MIN", "Data Sources",
          "Ops alert: held price stale after (min)", type="number", default="10",
          min=1, max=120, step=1,
          help="v248. During the regular session, an open trade whose last trade price is "
               "older than this, or that has no price at all, posts one ops-channel notice "
               "per ticker per session day, plus one recovery line. It also caps the "
               "yfinance per-ticker backoff for a held ticker in the regular session. "
               "Deliberately longer than ADMIN_STALE_PRICE_REGULAR_S (the panel's stale "
               "colour): the panel turns red first, Discord is paged only if it stays stale."),
```

In `.env.example`, after `EMPTY_SYMBOLS_ALERT_PCT=5`:

```
# v248: minutes a held ticker's price may be stale in the regular session before the
# ops channel is paged; also caps a held ticker's yfinance backoff in the session.
HELD_PRICE_STALE_ALERT_MIN=10
```

- [ ] **Step 5: Implement `swingbot/core/marketdata/yf_backoff.py`**

Module docstring: v248 § 4, the rule, the store kind, "fails open; Alpaca is never touched here; only `MARKETDATA_LAYER == "on"` touches the store". Imports: `from swingbot.core.db.repositories.market_shared import market_shared_repo`, `from swingbot.core.db.side_engine import side_connection` (module-level names: the tests patch `bo.side_connection`), `from swingbot.core.market import session`, `config`, `swallowed`. Import trades **inside** `held_symbols` (`from swingbot.core.db.repositories import trades as trades_mod; trades_mod.trades_repo().open_trades()`), so the test's module patch applies and `data.py` gains no import cycle.

The policy (the numbers are the spec's; the exponent is clamped so a symbol missed for weeks never overflows a `timedelta`):

```python
def after_miss(state: BackoffState, now: datetime) -> BackoffState:
    misses = state.misses + 1
    if misses < MISSES_TO_SKIP:
        return BackoffState(misses, None, now)
    pause = min(FIRST_PAUSE * (2 ** min(misses - MISSES_TO_SKIP, 4)), MAX_PAUSE)
    return BackoffState(misses, now + pause, now)


def is_skipped(state: BackoffState, now: datetime, *, held_in_session: bool,
               held_cap: timedelta) -> bool:
    until = state.skip_until
    if until is None:
        return False
    if held_in_session and state.written_at is not None:
        until = min(until, state.written_at + held_cap)
    return now < until
```

Store helpers, each its own short side connection, both fail open with `swallowed(log, "marketdata.yf_backoff.read" | "marketdata.yf_backoff.write", exc, level=logging.DEBUG)` on any `Exception` (`DatabaseUnavailable`, `sa.exc.TimeoutError`, statement errors; the `# noqa: BLE001` comment as in `shared/layer.py:_read_keys`):
- `_store_on() -> bool`: `config.MARKETDATA_LAYER == "on"`.
- `_read_states(tickers) -> dict[str, BackoffState] | None` (None = the read failed): one `read_entries([entry_key(t) ...])`; a row's `value` `{"misses": int, "skip_until": iso | None}` and its `fetched_at` give `BackoffState(misses, skip_until, written_at=fetched_at)`; a malformed value reads as `BackoffState()`; keyed by the ticker as passed.
- `_write_rows(rows: list[dict]) -> None`: one `write_entries(rows)`; each row `{"key": entry_key(t), "kind": KIND, "symbol": t.upper(), "fetched_at": now, "source": "yfinance", "value": {"misses": s.misses, "skip_until": s.skip_until.isoformat() if s.skip_until else None}}`.

`partition(tickers, now=None)`: `now = now or datetime.now(timezone.utc)`; store off or no tickers → `BackoffBatch(list(tickers), [], {})`; read failed → `BackoffBatch(list(tickers), [], {}, known=False)`. Otherwise call `held_symbols(now)` **only** when some state has `skip_until > now` and `session.session_state(now) == session.SESSION_REGULAR` (else `frozenset()`); `cap = timedelta(minutes=int(config.HELD_PRICE_STALE_ALERT_MIN))`; split in input order with `is_skipped(state, now, held_in_session=t.upper() in held, held_cap=cap)`; `states` holds every read state.

`record(batch, got, now=None)`: no-op when the store is off or `batch.known` is False. For each ticker in `batch.fetch` (skipped tickers were not asked, so never recorded): in `got` → a reset `BackoffState()` row only when its prior `misses > 0`, logging `INFO "yfinance backoff: %s leaves after a fetch"` when the prior misses were `>= MISSES_TO_SKIP`; not in `got` → an `after_miss(prior, now)` row, logging `INFO "yfinance backoff: %s enters after %d misses, skipped until %s"` only when the new misses equal `MISSES_TO_SKIP` (a doubling logs nothing). One `_write_rows` call for all rows, none when empty. Put the per-ticker decision in `_next_state(prior: BackoffState, hit: bool, now: datetime) -> BackoffState | None` so `record` stays well under 15.

`held_symbols(now=None)`: module cache `_held: tuple[datetime, frozenset[str]] | None`; re-read when absent, older than 60 s, or `now` is before its stamp; the set is `frozenset(str(r["ticker"]).upper() for r in rows if r.get("ticker"))`. On a read error, `swallowed(..., level=logging.DEBUG)` and return the last good set (or `frozenset()`) **without restamping**, so the next call retries. `_reset_for_tests()` sets `_held = None`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_yf_backoff.py`, then `python scripts/dev/testrun.py file tests/infra/test_config_ops_alerts.py`, then `python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: no new offender.

- [ ] **Step 7: Commit**

```bash
git add swingbot/config.py .env.example tests/infra/test_config_ops_alerts.py
git commit -m "feat(v248): HELD_PRICE_STALE_ALERT_MIN config field"
git add swingbot/core/marketdata/yf_backoff.py tests/marketdata/test_yf_backoff.py
git commit -m "feat(v248): yfinance per-ticker backoff policy and shared-store state"
```

### Task V248-5: Backoff at the shared yfinance seam `_yf_quote_details`; both callers honour it; INFO on enter/leave

**Model:** sonnet — one seam function split in two and wrapped by an existing module's two calls; the outcomes per download result are fixed by the tests.

**Files:**
- Modify: `swingbot/core/marketdata/data.py` (import line l.18; `_yf_quote_details` l.399-420)
- Modify: `tests/marketdata/test_data.py` (new tests appended)
- Modify: `tests/marketdata/test_refresh_quote_batch.py` (one fixture and three tests appended)

**Interfaces:**
- Consumes (V248-4): `yf_backoff.partition(tickers, now=None) -> BackoffBatch(fetch, skipped, states, known=True)`, `yf_backoff.record(batch, got, now=None) -> None`, `yf_backoff.held_symbols`, `yf_backoff._reset_for_tests()`. The INFO enter/leave lines are V248-4's (`record`); this task only routes every yfinance quote download through it.
- Produces: `data._yf_download_quotes(tickers: list) -> dict | None` (private: the old body; `None` = the download raised, `{}` = an empty frame). `_yf_quote_details(tickers)` keeps its signature and its return shape, so `_YfCap.__call__` (l.204), `_marked_quotes` (l.249, l.254) and `router.latest_quotes(..., yf_fetch)` (`providers/router.py:531`) need no change.

**Why.** Spec § 4 puts the backoff at `_yf_quote_details` so it covers every caller: the refresher's `refresh_quote_batch` (through `_YfCap`) and the bot's quote reads (`get_quote_batch` → `_marked_quotes` → `router.latest_quotes(..., _yf_quote_details)`), which also feed the stop monitor and lifecycle. Alpaca is asked before yfinance inside `latest_quotes` and is never skipped. Index Decision 7: a download **exception** (`DownloadBusy`, any other error) records nothing, `BudgetDeferred` still propagates and records nothing, and an **empty frame** counts as a miss for every asked ticker. A ticker absent from the returned dict is a miss (yfinance logs `YFPricesMissingError` and returns no column or an all-NaN one; nothing in `swingbot/` sees the exception itself).

- [ ] **Step 1: Write the failing seam tests**

Append to `tests/marketdata/test_data.py`:

```python
# -- v248 § 4: the yfinance backoff at the shared quote seam ------------------------

from swingbot.core.marketdata.yf_backoff import BackoffBatch


@pytest.fixture
def backoff(monkeypatch):
    """A fake yf_backoff: `skip` holds the backed-off tickers; calls are recorded."""
    seen = {"partition": [], "record": [], "skip": set()}

    def partition(tickers, now=None):
        tickers = list(tickers)
        seen["partition"].append(tickers)
        return BackoffBatch([t for t in tickers if t not in seen["skip"]],
                            [t for t in tickers if t in seen["skip"]], {})

    def record(batch, got, now=None):
        seen["record"].append((list(batch.fetch), sorted(got)))
    monkeypatch.setattr(data_mod.yf_backoff, "partition", partition)
    monkeypatch.setattr(data_mod.yf_backoff, "record", record)
    return seen


def _minute_frame(prices: dict) -> pd.DataFrame:
    idx = pd.DatetimeIndex(["2026-11-24 10:59"]).tz_localize("America/New_York")
    cols = pd.MultiIndex.from_product([list(prices), ["Close"]])
    return pd.DataFrame([list(prices.values())], index=idx, columns=cols)


def test_yf_quote_details_never_downloads_a_backed_off_ticker(monkeypatch, backoff):
    backoff["skip"].add("DOCU")
    asked = []
    monkeypatch.setattr(data_mod.yf_safe, "download",
                        lambda symbols, **kw: asked.append(symbols) or _minute_frame({"AAPL": 190.5}))
    got = data_mod._yf_quote_details(["AAPL", "DOCU", "MSFT"])
    assert asked == ["AAPL MSFT"] and set(got) == {"AAPL"}
    assert backoff["record"] == [(["AAPL", "MSFT"], ["AAPL"])]          # MSFT absent: a miss


def test_yf_quote_details_with_every_ticker_backed_off_makes_no_call(monkeypatch, backoff):
    backoff["skip"].add("DOCU")
    asked = []
    monkeypatch.setattr(data_mod.yf_safe, "download", lambda symbols, **kw: asked.append(symbols))
    assert data_mod._yf_quote_details(["DOCU"]) == {}
    assert asked == [] and backoff["record"] == []


def test_an_empty_frame_is_a_miss_for_every_asked_ticker(monkeypatch, backoff):
    monkeypatch.setattr(data_mod.yf_safe, "download", lambda *a, **k: pd.DataFrame())
    assert data_mod._yf_quote_details(["DOCU", "MSFT"]) == {}
    assert backoff["record"] == [(["DOCU", "MSFT"], [])]


@pytest.mark.parametrize("exc", [RuntimeError("yahoo 500"), "busy"])
def test_a_failed_download_records_nothing(monkeypatch, backoff, exc):
    err = data_mod.yf_safe.DownloadBusy("lock") if exc == "busy" else exc

    def boom(*a, **k):
        raise err
    monkeypatch.setattr(data_mod.yf_safe, "download", boom)
    assert data_mod._yf_quote_details(["DOCU"]) == {}
    assert backoff["record"] == []


def test_budget_deferred_still_propagates_and_records_nothing(monkeypatch, backoff):
    def deferred(*a, **k):
        raise data_mod.yf_safe.BudgetDeferred("tier 5")
    monkeypatch.setattr(data_mod.yf_safe, "download", deferred)
    with pytest.raises(data_mod.yf_safe.BudgetDeferred):
        data_mod._yf_quote_details(["DOCU"])
    assert backoff["record"] == []
```

(Move the new import up to the file's import block when you add them; it is shown here for completeness.)

- [ ] **Step 2: Write the failing caller tests (Postgres)**

Append to `tests/marketdata/test_refresh_quote_batch.py` (add `import pandas as pd` and `from swingbot.core.marketdata import yf_backoff` to its imports):

```python
# -- v248 § 4: both callers honour one shared backoff -------------------------------

@pytest.fixture
def yahoo(monkeypatch):
    """Alpaca answers only ALP; every other symbol reaches the real _yf_quote_details,
    whose download comes back empty (DOCU before the open). Returns the calls."""
    calls = {"latest": [], "download": []}

    def latest(tickers, yf_fetch):
        tickers = list(tickers)
        calls["latest"].append(tickers)
        out = {t: _q(t) for t in tickers if t == "ALP"}
        out.update(yf_fetch([t for t in tickers if t != "ALP"]) or {})
        return out

    def download(symbols, *a, **k):
        calls["download"].append(symbols)
        return pd.DataFrame()
    monkeypatch.setattr(data.router, "latest_quotes", latest)
    monkeypatch.setattr(data.yf_safe, "download", download)
    monkeypatch.setattr(yf_backoff, "held_symbols", lambda now=None: frozenset())
    yf_backoff._reset_for_tests()
    return calls


def test_refresher_batch_stops_asking_yahoo_after_three_misses(shared, yahoo):
    for _ in range(3):
        assert data.refresh_quote_batch(["DOCU"], yf_limit=5) == {}
    assert yahoo["download"] == ["DOCU"] * 3
    assert data.refresh_quote_batch(["DOCU"], yf_limit=5) == {}
    assert yahoo["download"] == ["DOCU"] * 3                      # 4th cycle: skipped


def test_bot_quote_read_honours_the_refresher_backoff(shared, yahoo):
    for _ in range(3):
        data.refresh_quote_batch(["DOCU"], yf_limit=5)
    side_engine.reset()                                           # the bot is another client
    got = data.get_quote_batch(["DOCU"], asker=Asker.STOP_MONITOR, max_age_s=0)
    assert ["DOCU"] in yahoo["latest"][3:]                        # the bot path did ask
    assert got == {} and yahoo["download"] == ["DOCU"] * 3        # ...but never reached Yahoo


def test_alpaca_is_never_skipped_by_the_yahoo_backoff(shared, yahoo):
    for _ in range(3):
        yf_backoff.record(yf_backoff.partition(["ALP"]), [])
    assert yf_backoff.partition(["ALP"]).skipped == ["ALP"]
    got = data.refresh_quote_batch(["ALP"], yf_limit=5)
    assert got["ALP"].price == 10.0 and yahoo["download"] == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run `/replicate-prod-db` first if this session has not (the `shared` fixture reaches the shared `swing-db`).
Run: `python scripts/dev/testrun.py file tests/marketdata/test_data.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.marketdata.data' has no attribute 'yf_backoff'`.
Run: `python scripts/dev/testrun.py file tests/marketdata/test_refresh_quote_batch.py`
Expected: FAIL — the 4th refresher call downloads again (`['DOCU', 'DOCU', 'DOCU', 'DOCU']`).

- [ ] **Step 4: Wire the backoff into the seam**

In `swingbot/core/marketdata/data.py`: change l.18 to `from swingbot.core.marketdata import spot_metals, yf_backoff, yf_safe`. Rename the current body of `_yf_quote_details` to `_yf_download_quotes(tickers: list) -> dict | None`, unchanged except that the `DownloadBusy` and the generic `Exception` branches return `None` instead of `{}` (`BudgetDeferred` still re-raises; an empty or `None` frame still returns `{}`). Then:

```python
def _yf_quote_details(tickers: list) -> dict:
    """v171: _yf_batch_prices with each price's own bar timestamp (D5: a
    delayed yfinance value counts only if its own timestamp passes 60 s).
    v248 § 4: a ticker in yfinance backoff is not asked; an answered ticker
    resets its backoff, an unanswered one counts a miss; a failed download
    records nothing."""
    batch = yf_backoff.partition(list(tickers))
    if not batch.fetch:
        return {}
    got = _yf_download_quotes(batch.fetch)
    if got is None:
        return {}
    yf_backoff.record(batch, got)
    return got
```

Do not touch `_yf_batch_prices` (l.422, the legacy `get_current_price_batch` path with `MARKETDATA_LAYER` off): the spec names the timestamped seam only, and the store is never read with the layer off anyway.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_data.py`, `python scripts/dev/testrun.py file tests/marketdata/test_refresh_quote_batch.py`, `python scripts/dev/testrun.py file tests/marketdata/test_provider_router.py` (the existing `_yf_quote_details` tests at l.244-272 keep passing: the layer is off there, so `partition` passes every ticker through), `python scripts/dev/testrun.py file tests/marketdata/test_quote_layer.py` and `python scripts/dev/testrun.py file tests/commands/test_trade_monitor_shared_quote.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: no new offender.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/marketdata/data.py tests/marketdata/test_data.py tests/marketdata/test_refresh_quote_batch.py
git commit -m "feat(v248): yfinance quote seam honours the per-ticker backoff"
```

### Task V248-6: Refresher: held tickers first (first cycle all held; later, held without a live price this session) with the full yfinance cap

**Model:** sonnet — a priority batch in front of the existing two-batch split plus one small session-day predicate; the batch lists and caps are spelled out by the tests.

**Files:**
- Modify: `swingbot/admin/market_values.py` (two functions added after `quote_fields`, ~l.133)
- Modify: `swingbot/refresher/quotes.py` (module docstring, imports, `_fetch_batches` l.88-101, one global and one helper added)
- Modify: `tests/admin_market/test_market_values.py` (tests appended)
- Modify: `tests/refresher/test_quote_cycle.py` (fixture `cycle` gains two patches; tests appended)

**Interfaces:**
- Consumes: `MarketQuote` (`market_values.py:24`; build it **by keyword** — V248-1 appends `error_at: Optional[str] = None`); `market_values.read_quotes(symbols, *, kind=DataKind.QUOTE, enqueue=True, now=None)` (l.110); `session.now_et`, `session.last_regular_close`, `session.NYSE_HOLIDAYS`, `session.TAPE_OPEN` (`swingbot/core/market/session.py:30, 261, 126, 26`); `ctx.symbols.held`, `ctx.scan_running`, `ctx.now` (`refresher/loop.py` `CycleContext`); `data.refresh_quote_batch(tickers, *, yf_limit)`.
- Produces: `market_values.session_priced(quote: MarketQuote | None, now: datetime) -> bool`; `market_values._session_day(now: datetime) -> date`; `quotes._held_primed: bool` (module global, `False` at import, tests reset it); `quotes._priority(ctx, wanted: list[str]) -> list[str]`; `quotes._ordered_batches(ctx, wanted: list[str], cap: int) -> dict` (today's `_fetch_batches` body with `cap` passed in).

**Why.** Spec § 3: after a restart the refresher fetched held names in watchlist order, and a new fill or a name still on prev close waited behind the watchlist; during a scan only the held split kept yfinance. Now `quote_step` fetches a batch of its own first, with the full `ADMIN_REFRESH_YF_FALLBACK_CAP` whatever `ctx.scan_running` says: on the first cycle after process start every held ticker; on every later (full) cycle each held ticker with no live price this session. The rest keeps today's ordering (during a scan its held part still gets yfinance, its watchlist part none) with what is left of the cap, so one cycle never asks yfinance for more than the cap. "This session" is the part decision above: the session day is the ET date of `now` on an NYSE trading day from 04:00 ET, else the ET date of the last regular close. A bid/ask-only quote (DOCU before the open: `price` None) is never session-priced. The read is `read_quotes(..., enqueue=False)`: it never queues work. Held tickers are present only on full cycles (`loop._context` gives `SymbolSet((), ())` between them), so queued-only cycles are unchanged.

- [ ] **Step 1: Write the failing `session_priced` tests**

Append to `tests/admin_market/test_market_values.py`:

```python
# -- v248 § 3: a live price this session ---------------------------------------------

from datetime import datetime, timezone

UTC = timezone.utc
TUE_1000_ET = datetime(2026, 11, 24, 15, 0, tzinfo=UTC)


def _mq(price, as_of):
    return mv.MarketQuote(symbol="DOCU", price=price, as_of=as_of.isoformat() if as_of else None,
                          age_s=None, refreshing=False, error=None)


@pytest.mark.parametrize("now, price, as_of, expected", [
    (TUE_1000_ET, 71.2, datetime(2026, 11, 24, 14, 45, tzinfo=UTC), True),    # today 09:45 ET
    (TUE_1000_ET, 71.2, datetime(2026, 11, 24, 10, 0, tzinfo=UTC), True),     # today 05:00 ET pre-market
    (TUE_1000_ET, 71.2, datetime(2026, 11, 24, 0, 0, tzinfo=UTC), False),     # Mon 19:00 ET after hours
    (TUE_1000_ET, None, datetime(2026, 11, 24, 14, 59, tzinfo=UTC), False),   # bid/ask only, no trade
    (TUE_1000_ET, 71.2, None, False),
    (datetime(2026, 11, 24, 7, 0, tzinfo=UTC), 71.2,                          # Tue 02:00 ET: tape shut,
     datetime(2026, 11, 24, 0, 0, tzinfo=UTC), True),                         # Monday is the session
    (datetime(2026, 11, 28, 15, 0, tzinfo=UTC), 71.2,                         # Saturday: Friday's
     datetime(2026, 11, 27, 17, 30, tzinfo=UTC), True),                       # half-day trade counts
    (datetime(2026, 11, 26, 15, 0, tzinfo=UTC), 71.2,                         # Thanksgiving: Wednesday
     datetime(2026, 11, 26, 0, 0, tzinfo=UTC), True),                         # 19:00 ET counts
    (datetime(2026, 11, 26, 15, 0, tzinfo=UTC), 71.2,
     datetime(2026, 11, 24, 20, 0, tzinfo=UTC), False),                       # ...Tuesday does not
])
def test_session_priced(now, price, as_of, expected):
    assert mv.session_priced(_mq(price, as_of), now) is expected


def test_no_quote_is_never_session_priced():
    assert mv.session_priced(None, TUE_1000_ET) is False
```

(Move the `datetime` import up to the file's import block.)

- [ ] **Step 2: Write the failing refresher tests**

In `tests/refresher/test_quote_cycle.py`, inside the `cycle` fixture before `return`, add:

```python
    monkeypatch.setattr(quotes, "_held_primed", False)
    monkeypatch.setattr(quotes.market_values, "read_quotes", lambda symbols, **kw: {})
```

Then append (add `from datetime import timedelta` and `from swingbot.admin.market_values import MarketQuote` to the imports):

```python
# -- v248 § 3: held tickers first ---------------------------------------------------

HELD = SymbolSet(("AAPL", "BAD", "YF"), ("^GSPC",), ("AAPL", "YF"))


def _door(sym, price, minutes_ago):
    as_of = REGULAR - timedelta(minutes=minutes_ago)
    return MarketQuote(symbol=sym, price=price, as_of=as_of.isoformat(),
                       age_s=minutes_ago * 60.0, refreshing=False, error=None)


def _next_full_cycle(monkeypatch):
    monkeypatch.setattr(loop, "_last_full", None)     # same clock, but a full cycle again
    loop.run_cycle(REGULAR)


def test_first_cycle_fetches_every_held_ticker_first_with_the_full_cap(cycle, monkeypatch):
    _marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)
    loop.run_cycle(REGULAR)
    assert batches == [(["AAPL", "YF"], 150), (["BAD"], 148)]
    assert quotes._held_primed is True


def test_first_cycle_held_batch_keeps_the_full_cap_during_a_scan(cycle, monkeypatch):
    marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)
    monkeypatch.setattr(loop, "_scan_running", lambda: True)
    loop.run_cycle(REGULAR)
    assert batches == [(["AAPL", "YF"], 150), (["BAD"], 0)]
    assert ("clear", ("quote:BAD",), quotes.NO_QUOTE_DURING_SCAN) in marks.events


def test_later_cycle_puts_only_held_without_a_session_price_first(cycle, monkeypatch):
    _marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)
    loop.run_cycle(REGULAR)
    batches.clear()
    asked = []

    def door(symbols, **kw):
        asked.append((list(symbols), kw.get("enqueue")))
        return {"AAPL": _door("AAPL", 190.5, 1), "YF": _door("YF", None, 1)}   # YF: bid/ask only
    monkeypatch.setattr(quotes.market_values, "read_quotes", door)
    _next_full_cycle(monkeypatch)
    assert asked == [(["AAPL", "YF"], False)]                 # never enqueues
    assert batches == [(["YF"], 150), (["AAPL", "BAD"], 149)]


def test_later_cycle_with_every_held_priced_keeps_todays_ordering(cycle, monkeypatch):
    _marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)
    loop.run_cycle(REGULAR)
    monkeypatch.setattr(quotes.market_values, "read_quotes",
                        lambda symbols, **kw: {s: _door(s, 10.0, 2) for s in symbols})
    batches.clear()
    _next_full_cycle(monkeypatch)
    assert batches == [(["AAPL", "BAD", "YF"], 150)]
    monkeypatch.setattr(loop, "_scan_running", lambda: True)
    batches.clear()
    _next_full_cycle(monkeypatch)
    assert batches == [(["AAPL", "YF"], 150), (["BAD"], 0)]   # today's scan split


def test_unreadable_door_puts_every_held_ticker_first(cycle, monkeypatch):
    _marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)
    loop.run_cycle(REGULAR)

    def down(symbols, **kw):
        raise RuntimeError("side pool busy")
    monkeypatch.setattr(quotes.market_values, "read_quotes", down)
    batches.clear()
    _next_full_cycle(monkeypatch)
    assert batches[0] == (["AAPL", "YF"], 150)


def test_a_failed_first_fetch_keeps_the_first_cycle_rule(cycle, monkeypatch):
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)

    def down(tickers, *, yf_limit):
        raise RuntimeError("alpaca 503")
    monkeypatch.setattr(quotes.data, "refresh_quote_batch", down)
    loop.run_cycle(REGULAR)
    assert quotes._held_primed is False
```

The existing `test_scan_running_keeps_yfinance_for_held_symbols_only` keeps its exact assertion (`[(["BAD", "YF"], 150), (["AAPL"], 0)]`): on a first cycle the held batch is the priority batch.

- [ ] **Step 3: Run the tests to verify they fail**

Run `/replicate-prod-db` first if this session has not (the `market` fixture's suite reaches Postgres).
Run: `python scripts/dev/testrun.py file tests/admin_market/test_market_values.py`
Expected: FAIL — `AttributeError: module 'swingbot.admin.market_values' has no attribute 'session_priced'`.
Run: `python scripts/dev/testrun.py file tests/refresher/test_quote_cycle.py`
Expected: FAIL — `AttributeError: ... 'quotes' has no attribute 'market_values'` (fixture), then the batch-list assertions.

- [ ] **Step 4: Implement `session_priced` in `swingbot/admin/market_values.py`**

Add `from datetime import date` to the imports. After `quote_fields`:

```python
def _session_day(now: datetime) -> date:
    """v248 § 3: the ET date whose trades count as this session's -- today on an
    NYSE trading day from the 04:00 ET tape open, else the last regular close's day."""
    et = session.now_et(now)
    if et.weekday() < 5 and et.date() not in session.NYSE_HOLIDAYS and et.time() >= session.TAPE_OPEN:
        return et.date()
    return session.now_et(session.last_regular_close(now)).date()


def session_priced(quote: Optional[MarketQuote], now: datetime) -> bool:
    """A live trade price stamped on this session's day. A bid/ask-only quote
    (no trade, `price` None) is not; the midpoint is never a price."""
```

Body: False when `quote` is None, `quote.price` is None or `quote.as_of` is falsy or unparsable (`datetime.fromisoformat` → `ValueError` / `TypeError`); else `session.now_et(as_of).date() == _session_day(now)`.

- [ ] **Step 5: Implement the priority batch in `swingbot/refresher/quotes.py`**

Imports: `from swingbot.admin import market_values` (the module, so tests patch `quotes.market_values.read_quotes`; it imports only `swingbot.core` modules). Module global after `NO_QUOTE_DURING_SCAN`:

```python
#: v248 § 3: False until the first held-first fetch of this process returned.
_held_primed = False
```

Add to the module docstring one paragraph: "v248: held tickers go first in a batch of their own with the full yfinance cap whatever a scan says -- all of them on the first cycle after start, later only those without a live price this session (`market_values.session_priced`); the rest keeps the split below with what is left of the cap."

```python
def _priority(ctx: "CycleContext", wanted: list[str]) -> list[str]:
    held_set = set(ctx.symbols.held)
    held = [s for s in wanted if s in held_set]
    if not held or not _held_primed:
        return held
    try:
        door = market_values.read_quotes(held, enqueue=False, now=ctx.now)
    except Exception as exc:  # noqa: BLE001 - unreadable: every held ticker goes first
        swallowed(log, "ops.refresher.held_quotes", exc, level=logging.DEBUG)
        return held
    return [s for s in held if not market_values.session_priced(door.get(s), ctx.now)]


def _fetch_batches(ctx: "CycleContext", wanted: list[str]) -> dict:
    """v248: the held-first batch with the whole yfinance budget, then the rest in
    today's order with what is left of it."""
    global _held_primed
    cap = int(config.ADMIN_REFRESH_YF_FALLBACK_CAP)
    first = _priority(ctx, wanted)
    got = data.refresh_quote_batch(first, yf_limit=cap) if first else {}
    _held_primed = True
    rest = [s for s in wanted if s not in set(first)]
    if rest:
        got.update(_ordered_batches(ctx, rest, max(0, cap - len(first))))
    return got
```

`_ordered_batches(ctx, wanted, cap) -> dict` is the old `_fetch_batches` body with its docstring, reading `cap` from the parameter instead of `config` (outside a scan one batch with `cap`; during a scan held with `cap`, the rest with 0). `_refresh_quotes`, `_settle` and the report fields stay as they are: `ok`/`missed` are computed from `wanted` and `got`, so the priority batch needs nothing extra.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin_market/test_market_values.py`, `python scripts/dev/testrun.py file tests/refresher/test_quote_cycle.py`, `python scripts/dev/testrun.py file tests/refresher/test_loop.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: no new offender.

- [ ] **Step 7: Commit**

```bash
git add swingbot/admin/market_values.py tests/admin_market/test_market_values.py
git commit -m "feat(v248): market_values.session_priced -- a live trade on this session's day"
git add swingbot/refresher/quotes.py tests/refresher/test_quote_cycle.py
git commit -m "feat(v248): refresher fetches held tickers first with the full yfinance cap"
```

