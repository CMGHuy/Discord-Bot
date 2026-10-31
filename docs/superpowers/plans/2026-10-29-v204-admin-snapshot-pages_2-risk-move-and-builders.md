# Admin snapshot pages: part 2, risk move and builders

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin snapshot pages](../specs/2026-10-29-v204-admin-snapshot-pages.md) (precedence: "Brief corrections", then "Panel amendments", then the earlier text)
**Index:** [`_0-index.md`](2026-10-29-v204-admin-snapshot-pages_0-index.md): Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and every cross-task contract ("Read-only bars", "Risk payload", "Snapshot builders"). Read its Global Constraints before any task here.

This part holds V204-5 … V204-8. It adds the core read-only daily-bar
reader, moves the risk maths from the Flask blueprint into
`swingbot/core/analytics` unchanged (parity against the frozen golden
payloads), records each snapshot's inputs and its `stale_inputs` flag, and
writes every snapshot builder the refresher's worker (part 3) will call.

`<wt>` is the implementation worktree's absolute path. Every DB-backed test
run is preceded once per session by `/replicate-prod-db` into the shared
`swing-db` container.

**Consumed from earlier work.** v201 (merged first): `admin_refresh.refresher_on()`,
`session.last_regular_close(now)`, `fx.quote_currency_code(t, *, fetch=False)`,
`fx.fx_rate(..., refresh=False)`, `fx_convert.to_account_currency(rows, *, account=None, fetch=True)`,
`fx_convert.missing_count(rows)`.
Part 1: `tests/admin_snapshots/golden_book.py` (`golden_book` → `GoldenBook(client,
tmp_path, network_calls)` with a logged-in client and `ADMIN_REFRESHER="off"`,
`golden_payload`, `assert_matches_golden`, `GOLDEN_NOW`, `GOLDEN_MONTH`,
`normalise`). A module that uses `golden_book` imports it together with
`admin_app`, `client` and `_clear_login_limiter` from that file; there is no
`tests/admin_snapshots/conftest.py`. Also from part 1: the `admin-snapshots` suite,
V204-2's verdicts in `docs/superpowers/results/2026-10-29-v204-measure-first.md`,
and V204-3's `admin_refresh` additions (`SNAPSHOT_RISK`, `SNAPSHOT_ANALYTICS`,
`performance_key`, `equity_curve_key`, `calendar_key`, `calendar_months`).

**Clock seams.** `risk_payload._now()` and `admin_snapshots._now()` return
`datetime.now(timezone.utc)`. Parity tests patch both to `GOLDEN_NOW`, so a
wall-clock `checked_at` can never make a frozen payload differ.

---

# Phase: read-only bars and the risk move (V204-5, V204-6)

### Task V204-5: Core read-only daily-bar reader; `page_daily(read_only=)`; `collect_portfolio_state(bars_reader=)`

**Model:** opus — the reader is the only thing standing between a snapshot and a silent network fetch or cache write, and its loud-failure rules were blocking panel findings.

**Files:**
- Create: `swingbot/core/marketdata/daily_readonly.py`, `tests/admin_snapshots/test_daily_readonly.py`
- Modify: `swingbot/admin/freshness.py` (`_PERIOD_DAYS` line 119, `_trim` 172-176, `page_daily` 179-189), `swingbot/core/edge/portfolio_state.py` (`_observed` 71-79, `_daily_frames` 131-142, `_clusters_state` 145-161, `collect_portfolio_state` 193)

**Interfaces:**
- Consumes: `data_store.DATA_DIR`, `timeframe_name`, `safe_symbol`, `load_normalized_file(path, label=)` (`data_store.py:378`), which is what `daily_delta.read_daily(T, basis=BASIS_YF)` calls on `cache_path(T, "daily")`; `spot_metals.is_spot_metal`.
- Produces (index "Read-only bars", exact): `DailyCacheUnavailable(RuntimeError)`; `PERIOD_DAYS`; `trim(df, period)`; `ReadOnlyBars(frames, missing, fingerprints)` (frozen); `read_cached_daily(tickers, *, period="2y", min_rows=1) -> ReadOnlyBars`; `RecordingReader(*, period="2y", min_rows=1)` with `__call__(symbols) -> dict[str, DataFrame]` and `.seen -> ReadOnlyBars`; `freshness.page_daily(tickers, *, period="2y", read_only=False)`; `collect_portfolio_state(*, bars_reader=None)`; `_daily_frames(trades, bars_reader=None)`.

**Behaviour fixed here:**
- **Never fetch, never write, never create.** `daily_readonly` imports nothing from `data`, `data_refresh`, `providers`, `fx` or `swingbot.admin`. It first checks that `d = os.path.join(data_store.DATA_DIR, data_store.timeframe_name("daily"))` is a directory, and raises `DailyCacheUnavailable(f"daily bar cache {os.path.abspath(d)} is not mounted")` when it is not. It reads `os.path.join(d, f"{safe_symbol(T)}.csv")` with `data_store.load_normalized_file(path, label=f"{T}/yfinance-auto_adjust")`. That is the file and loader `daily_delta.read_daily(T, basis=BASIS_YF)` uses (`cache_file` → `cache_path(T, "daily")`), minus `cache_path`'s `os.makedirs`. It reads `data_store.DATA_DIR` at call time, because `cache_path`'s `base_dir` default is bound at import and would ignore a test's patch. It never reads `data/backtest_cache/` or the Alpaca basis.
- **Per symbol**, after `T = str(t).upper().strip()` and de-duplication in first-seen order, the outcome falls through in this order:
  1. A spot metal → `missing[T] = "spot_metal"`, with no file touched.
  2. No file → `"no_file"`.
  3. A file of 0 bytes → `"empty"`.
  4. `load_normalized_file` returns `None` → `"unreadable"`.
  5. `trim(df, period)` has fewer than `min_rows` rows → `"short:<rows>/<min_rows>"`.
  6. Otherwise `frames[T] = trim(df, period)`.

  Every file that parsed (cases 5 and 6) gets `fingerprints[T] = {"path": abs path, "mtime": os.path.getmtime(path), "last_bar": df.index[-1].strftime("%Y-%m-%d"), "rows": len(df)}`, where `rows` is the untrimmed file's row count. A short frame is **never** returned as if it were whole.
- `RecordingReader.__call__` calls `read_cached_daily(symbols, period=self.period, min_rows=self.min_rows)`, merges the result into its running `frames`/`missing`/`fingerprints`, and returns that call's `frames`. `.seen` returns a `ReadOnlyBars` of copies of the merged dicts. `DailyCacheUnavailable` propagates.
- `freshness`: `_PERIOD_DAYS` and `_trim` become `from swingbot.core.marketdata.daily_readonly import PERIOD_DAYS as _PERIOD_DAYS, trim as _trim`. `page_daily` gains `read_only: bool = False`. Its first statement is `if read_only: return read_cached_daily(tickers, period=period).frames`. The rest is today's code.
- `portfolio_state`: `_observed` gains `except DailyCacheUnavailable: raise` ahead of its `except Exception`, so a missing volume escapes the collector instead of becoming `clusters_unavailable`. Today's reads never raise it, so the Discord path is unchanged. `_daily_frames(trades, bars_reader=None)` keeps today's loop when there is no reader. With a reader it calls `got = bars_reader(sorted({str(t).upper().strip() for t in tickers}))` once and keys the frames by each trade's own ticker string (`frames[t] = got[t.upper().strip()]` when that frame is present and non-empty), so the frames are keyed exactly as `get_daily_data` keyed them. It never calls `data.get_daily_data`, and `missing = len(tickers) - len(frames)`. The reader travels `collect_portfolio_state(*, bars_reader=None)` → `_clusters_state(..., bars_reader=None)` → `_daily_frames`. Discord's `commands/growth.py:178` calls with no argument and keeps today's behaviour.

- [ ] **Step 1: Write the failing tests** in `tests/admin_snapshots/test_daily_readonly.py`

```python
"""v204: snapshot bars come from the yfinance-basis daily file only; never fetched, never written."""
import os

import pandas as pd
import pytest

from swingbot.admin import freshness
from swingbot.core.edge import portfolio_state
from swingbot.core.marketdata import daily_readonly, data, data_refresh, data_store
from swingbot.core.marketdata.daily_readonly import (
    DailyCacheUnavailable, ReadOnlyBars, RecordingReader, read_cached_daily)


def frame(days=30, start="2026-08-03"):
    close = [100.0 + i for i in range(days)]
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": [1000.0] * days}, index=pd.bdate_range(start, periods=days))


@pytest.fixture
def disk(tmp_path, monkeypatch):
    root = tmp_path / "market_data"
    daily = root / data_store.timeframe_name("daily")
    daily.mkdir(parents=True)
    monkeypatch.setattr(data_store, "DATA_DIR", str(root))

    def boom(*a, **k):
        raise AssertionError("read-only bars reached a fetch or a cache write")
    for mod, name in ((data, "get_daily_data"), (data, "get_daily_data_batch"),
                      (data_refresh, "refresh_symbol"), (data_store, "update_cache"),
                      (data_store, "save_to_disk"), (freshness, "_daily_for")):
        monkeypatch.setattr(mod, name, boom, raising=False)

    def write(sym, df):
        df.to_csv(daily / f"{data_store.safe_symbol(sym)}.csv")
    return write, daily


def test_cached_symbols_are_read_and_absent_ones_listed_missing(disk):
    write, _ = disk
    write("AAPL", frame())
    got = read_cached_daily(["aapl", " MSFT ", "AAPL"])
    assert isinstance(got, ReadOnlyBars)
    assert list(got.frames) == ["AAPL"] and got.missing == {"MSFT": "no_file"}
    assert got.frames["AAPL"]["Close"].iloc[-1] == 129.0


def test_fingerprint_names_the_yfinance_basis_file(disk):
    write = disk[0]
    write("AAPL", frame(days=40))
    _, daily = disk
    fp = read_cached_daily(["AAPL"], period="6mo").fingerprints["AAPL"]
    assert os.path.normcase(fp["path"]) == os.path.normcase(
        os.path.abspath(daily / f"{data_store.safe_symbol('AAPL')}.csv"))
    assert fp["rows"] == 40 and fp["last_bar"] == "2026-09-25" and fp["mtime"] > 0


def test_period_trims_to_the_window_but_rows_count_the_file(disk):
    write, _ = disk
    write("AAPL", frame(days=600, start="2024-03-01"))
    got = read_cached_daily(["AAPL"], period="1y")
    kept = got.frames["AAPL"]
    assert (kept.index[-1] - kept.index[0]).days <= daily_readonly.PERIOD_DAYS["1y"]
    assert got.fingerprints["AAPL"]["rows"] == 600


def test_short_frame_is_missing_with_its_row_count_never_returned(disk):
    write, _ = disk
    write("AAPL", frame(days=12))
    got = read_cached_daily(["AAPL"], min_rows=21)
    assert got.frames == {} and got.missing == {"AAPL": "short:12/21"}
    assert got.fingerprints["AAPL"]["rows"] == 12


def test_empty_and_unreadable_files_are_missing_with_a_reason(disk):
    _, daily = disk
    (daily / f"{data_store.safe_symbol('AAA')}.csv").write_text("")
    (daily / f"{data_store.safe_symbol('BBB')}.csv").write_text("not,a,bar file\n1,2,3\n")
    got = read_cached_daily(["AAA", "BBB"])
    assert got.frames == {} and got.missing == {"AAA": "empty", "BBB": "unreadable"}


def test_spot_metal_is_missing_never_fetched(disk):
    got = read_cached_daily(["XAUUSD"])
    assert got.frames == {} and got.missing == {"XAUUSD": "spot_metal"} and got.fingerprints == {}


def test_unmounted_cache_dir_raises(tmp_path, monkeypatch):
    absent = tmp_path / "not-mounted"
    monkeypatch.setattr(data_store, "DATA_DIR", str(absent))
    with pytest.raises(DailyCacheUnavailable, match="not mounted"):
        read_cached_daily(["AAPL"])
    assert not absent.exists()


def test_recording_reader_returns_frames_and_remembers_every_call(disk):
    write, _ = disk
    write("AAPL", frame())
    reader = RecordingReader(min_rows=5)
    assert list(reader(["AAPL"])) == ["AAPL"]
    assert reader(["MSFT"]) == {}
    seen = reader.seen
    assert list(seen.frames) == ["AAPL"] and seen.missing == {"MSFT": "no_file"}
    assert set(seen.fingerprints) == {"AAPL"}


def test_page_daily_read_only_reads_disk_and_never_refreshes(disk):
    write, _ = disk
    write("AAPL", frame())
    assert set(freshness.page_daily(["AAPL", "MSFT", "XAUUSD"], read_only=True)) == {"AAPL"}


def test_cluster_bars_go_through_the_reader_keyed_by_trade_ticker(disk):
    frames, missing = portfolio_state._daily_frames(
        [{"ticker": "aapl"}, {"ticker": "MSFT"}], bars_reader=lambda syms: {"AAPL": frame()})
    assert list(frames) == ["aapl"] and missing == 1


def test_missing_volume_escapes_the_collector(monkeypatch):
    def unmounted(syms):
        raise DailyCacheUnavailable("daily bar cache /x is not mounted")
    trades = [{"ticker": "AAPL", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
               "shares": 10.0}]
    monkeypatch.setattr(portfolio_state, "_trades", lambda: trades)
    monkeypatch.setattr(portfolio_state, "_load_sector_map", lambda: {"AAPL": "Tech"})
    monkeypatch.setattr(portfolio_state.account_module, "load_account_config",
                        lambda: {"base_balance": 10_000.0})
    with pytest.raises(DailyCacheUnavailable):
        portfolio_state.collect_portfolio_state(bars_reader=unmounted)


def test_collector_without_a_reader_still_swallows_cluster_fetch_errors(monkeypatch):
    def down(ticker):
        raise RuntimeError("provider down")
    monkeypatch.setattr(data, "get_daily_data", down)
    frames, missing = portfolio_state._daily_frames([{"ticker": "AAPL"}])
    assert frames == {} and missing == 1
```

If `_balance(cfg)` in `portfolio_state` needs more account keys than `base_balance`, add them to the stub in `test_missing_volume_escapes_the_collector`. Do not change the assertion. What matters is that the raise reaches the caller.

- [ ] **Step 2: Run the file to verify it fails**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_daily_readonly.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'swingbot.core.marketdata.daily_readonly'`.

- [ ] **Step 3: Create `swingbot/core/marketdata/daily_readonly.py`**

The module docstring says this is v204's snapshot bars and that the module is read-only by construction. It names what the module never calls (providers, `data.get_daily_data*`, `data_refresh`, `freshness._daily_for`, `backtest_cache`) and states the loud-failure rule with its pointer (`known-traps.md` § The market_data cache never self-heals). Top-level imports are the standard library only, plus `pandas` under `TYPE_CHECKING`. Import `data_store` and `spot_metals` inside the functions, because `freshness` imports this module at load time. Do not import `daily_delta`: it pulls in the provider router.

```python
PERIOD_DAYS = {"6mo": 183, "1y": 366, "2y": 731, "5y": 1827}   # moved from freshness._PERIOD_DAYS


class DailyCacheUnavailable(RuntimeError):
    """The daily bar cache directory is absent (an unmounted volume)."""


@dataclass(frozen=True)
class ReadOnlyBars:
    frames: dict
    missing: dict
    fingerprints: dict
```

`trim(df, period)` is `freshness._trim`'s body, unchanged. Split `read_cached_daily` into `_daily_dir() -> str` (it raises when the directory is absent) and `_read_one(symbol, daily_dir, period, min_rows) -> tuple[frame | None, reason | None, fingerprint | None]`. Each function stays well under complexity 15.

- [ ] **Step 4: Wire `freshness` and `portfolio_state`**

Apply the `freshness` and `portfolio_state` edits per "Behaviour fixed here". `portfolio_state` imports `DailyCacheUnavailable` at module top (`from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable`). That is core importing core. The module's own top-level imports stay standard-library only, so this adds no cycle.

- [ ] **Step 5: Run the tests to verify they pass, plus today's readers**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_daily_readonly.py`
Expected: PASS, `0 failed`.
Run: `... file tests/admin/test_admin_freshness.py`, `... file tests/edge/test_edge_heat.py`, and each file `git -C <wt> grep -ln "parity_cases.growth\|_collect_portfolio_state" -- tests` names
Expected: PASS, assertions unchanged.
Run: `git -C <wt> grep -n "swingbot.admin\|get_daily_data\|data_refresh\|backtest_cache\|providers\|makedirs" -- swingbot/core/marketdata/daily_readonly.py`
Expected: matches only inside the docstring's "never calls" list.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add swingbot/core/marketdata/daily_readonly.py swingbot/admin/freshness.py swingbot/core/edge/portfolio_state.py tests/admin_snapshots/test_daily_readonly.py
git -C <wt> commit -m "feat(v204): core read-only daily-bar reader; page_daily and the collector take it"
```

### Task V204-6: Risk maths moves to core unchanged; strict mode; parity with golden

**Model:** opus — a behaviour-preserving move of the whole risk chain across the admin/core seam, pinned to frozen payloads; a drifted figure here is the spec's "forked copy of the risk maths" anti-goal.

**Files:**
- Create: `swingbot/core/analytics/risk_payload.py`, `tests/admin_snapshots/test_risk_payload.py`
- Move: `swingbot/admin/api_v1/risk_read_model.py` → `swingbot/core/analytics/risk_read_model.py` (`git mv`). Recreate the admin path as a re-export of its three public names.
- Modify: `swingbot/admin/api_v1/risk.py` (delete the moved definitions; `_risk_bars` 348-354; `get_risk` 455-510)
- Modify (retarget patch paths only, no assertion changes): `tests/admin/test_api_v1_risk.py` lines 758, 815, 995, 1031, 1041, 1078, 1099 (today's numbering); `tests/admin/test_risk_read_model.py` needs none (it imports through the re-export)

**Interfaces:**
- Consumes: V204-5 `daily_readonly.DailyCacheUnavailable`; v201 `admin_refresh.refresher_on()`, `fx_convert.to_account_currency(rows, *, account=None, fetch=True)`, `fx_convert.missing_count(rows)`; part 1 `golden_book`, `assert_matches_golden`, `GOLDEN_NOW`.
- Produces (index "Risk payload", exact): `RiskMetrics(metrics, correlation, availability, bars_as_of: dict[str, str], missing_bars: dict[str, str])` (frozen); `metrics_and_correlation(bars_reader, *, strict=False) -> RiskMetrics`; `market_body(state, result) -> dict`; `empty_body() -> dict`; seams `_open_trades() -> list | None`, `_now() -> datetime`. In `risk.py`: `_risk_metrics() -> RiskMetrics`, `_risk_metrics_and_correlation()`, `_distribution_metrics(open_trades, benchmark, checked)`.

**Behaviour fixed here:**
- **Moved unchanged, log tags included.** These move from `risk.py` to `risk_payload.py`: `_position_risk`, `_positions`, `_open_short_gap_risk`, `_heat_gap_block`, `_sector_rows`, `_metric`, `_pnl_amounts`, `_money_metric`, `_max_drawdown_amount`, `_closed_history`, `_population_status`, `_finite_metric`, `_r_metrics`, `_closed_metrics`, `_DISTRIBUTION_KEYS`, `_empty_distribution`, `_distribution_status`, `_asset_symbols`, `_asset_correlation`, `_market_values`, `_covered_distribution` and `_distribution_metrics`. Only five edits are allowed:
  1. `_money_metric` calls `fx_convert.to_account_currency(ordered, fetch=not admin_refresh.refresher_on())` and `fx_convert.missing_count(...)`, as module attributes looked up at call time.
  2. The read-model imports point at `swingbot.core.analytics.risk_read_model`.
  3. `_distribution_metrics(open_trades, benchmark, checked, bars_reader, *, strict=False)` calls `bars_reader(...)` where it called `_risk_bars(...)`. Its bar-read `try` gains `except DailyCacheUnavailable: raise` ahead of `except Exception`, and the generic branch re-raises when `strict`.
  4. `_asset_correlation(symbols, bars, *, strict=False)` re-raises in its `except` when `strict`.
  5. `metrics_and_correlation` uses the seams `_open_trades()` (today's inline `TradeLog().get_trades(status="open", limit=None)`, `None` on any error) and `_now()`.
- **`metrics_and_correlation(bars_reader, *, strict=False)`** is today's `_risk_metrics_and_correlation` body with `checked = _now().isoformat()`. Three things are added to it:
  - A private `_Recorder(bars_reader)` wraps the reader and remembers the symbols asked for and the frames returned. `bars_as_of = {SYM: frame.index[-1].strftime("%Y-%m-%d")}` covers every non-empty returned frame. `missing_bars = {SYM: reason}` covers every asked symbol without one. The reason is `bars_reader.seen.missing[SYM]` when the reader has `.seen` (V204-5's `RecordingReader`), else `"no_bars"`.
  - `_overlap_checked(correlation)`: with at least 2 labels, a list matrix, and every off-diagonal cell `None` (no pair reached `risk_metrics._MIN_BARS`), it returns `{"labels": labels, "values": None, "reason": "insufficient_overlap"}`. Otherwise it returns the input object unchanged.
  - When `metrics["beta_spy"]["value"] is None` and the benchmark frame has at least 2 returns with `math.isclose(var(ddof=1), 0.0, abs_tol=1e-18)`, it sets `availability["beta_spy"] = "zero_variance"`.

  `availability` is a fresh dict, so `market_body` and the caller never mutate a cached object (`test_distribution_availability_merges_without_mutating_cache` stays green). Neither guard fires on a book with enough overlapping, moving bars, so the golden payload is unaffected.
- **`market_body(state, result)`** returns `heat` (`open_pct`, `cap_pct`, the unclamped `utilisation_pct`, `**_heat_gap_block`), `availability` (`{**state["availability"], **result.availability}`), `positions`, `sector_heat`, `unmapped_count`, `clusters`, `throttle`, `metrics` and `correlation`. Each value is exactly the expression `get_risk` uses today. The "Utilisation is NOT clamped" comment moves with it. There is no `killswitch` and no `scan_health`. **`empty_body()`** returns the same keys: `heat` = `{"open_pct": None, "cap_pct": None, "utilisation_pct": None, **_heat_gap_block(None)}`, `availability: {}`, `positions: None`, `sector_heat: None`, `unmapped_count: 0`, `clusters: None`, `throttle: {"multiplier": None, "paused": None}`, `metrics: {**_empty_distribution(), **_closed_metrics(None, "")[0], "benchmark_symbol": <benchmark>}` and `correlation: {"labels": [], "values": []}`.
- **`risk.py` keeps** `_risk_bars`, now `freshness.page_daily(symbols, read_only=admin_refresh.refresher_on())` when the layer is on (the else-branch is today's), plus `_cached`, `_invalidate_cache`, `_fresh_kill`, `_kill_*`, `_scan_health`, `_data_sources_summary` and the killswitch routes. It adds these compat names:
  - `_risk_metrics()` returns `risk_payload.metrics_and_correlation(_risk_bars)`. `_risk_bars` is a module global looked up at call time, so existing patches of `risk._risk_bars` still bite.
  - `_risk_metrics_and_correlation()` returns `(r.metrics, r.correlation, r.availability)`.
  - `_distribution_metrics(open_trades, benchmark, checked)` passes `_risk_bars`.
  - The aliases `_closed_metrics`, `_closed_history`, `_max_drawdown_amount`, `_pnl_amounts` and `_DISTRIBUTION_KEYS` each equal `risk_payload.<same>`.

  `get_risk` reads `state = _cached("portfolio_state", collect_portfolio_state)` and `result = _cached("metrics", _risk_metrics)`. It returns `jsonify({**body, "availability": {**body["availability"], "killswitch": kill["availability"]}, "killswitch": kill, "scan_health": _scan_health()})` with `body = risk_payload.market_body(state, result)`. Flask sorts JSON keys, so the response bytes match today's.
- `risk_payload` imports nothing from `swingbot.admin`. Its module docstring carries over `risk.py`'s "Nothing is computed" paragraph and states that `GET /risk` and the refresher's snapshot both call `metrics_and_correlation` and `market_body`.

- [ ] **Step 1: Write the failing tests** in `tests/admin_snapshots/test_risk_payload.py`

```python
"""v204: the risk chain lives in core; GET /risk and the snapshot call the same functions."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.admin.api_v1 import risk
from swingbot.core.analytics import risk_payload
from swingbot.core.marketdata import fx
from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable, ReadOnlyBars
from tests.admin_snapshots.golden_book import (  # noqa: F401
    GOLDEN_NOW, _clear_login_limiter, admin_app, assert_matches_golden, client, golden_book)


def frame(days=60, flat=False):
    close = [100.0] * days if flat else [100.0 + i * (1 + (i % 3)) for i in range(days)]
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": [1000.0] * days},
                        index=pd.bdate_range("2026-07-01", periods=days))


def trade(ticker, tid, direction="bullish"):
    return {"id": tid, "ticker": ticker, "direction": direction, "entry": 100.0,
            "stop_loss": 95.0, "shares": 10.0, "status": "open", "strategy": "RSI"}


@pytest.fixture
def seams(monkeypatch):
    monkeypatch.setattr(fx, "account_currency_code", lambda: "USD")
    monkeypatch.setattr(fx, "quote_currency_code", lambda t, **k: "USD")
    monkeypatch.setattr(fx, "fx_rate", lambda *a, **k: 1.0)
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(risk_payload, "_now", lambda: GOLDEN_NOW)
    monkeypatch.setattr(risk_payload, "_closed_history", lambda: [])
    monkeypatch.setattr(risk_payload, "_open_trades",
                        lambda: [trade("AAPL", 1), trade("MSFT", 2)])


def test_off_path_risk_matches_the_golden_payload(golden_book, monkeypatch):
    monkeypatch.setattr(risk_payload, "_now", lambda: GOLDEN_NOW)
    risk._invalidate_cache()
    assert_matches_golden("risk", golden_book.client.get("/api/v1/risk").get_json())
    assert golden_book.network_calls == []


def test_metrics_record_bars_as_of_and_missing_symbols(seams):
    result = risk_payload.metrics_and_correlation(lambda syms: {"AAPL": frame(), "SPY": frame()})
    assert result.bars_as_of == {"AAPL": "2026-09-22", "SPY": "2026-09-22"}
    assert result.missing_bars == {"MSFT": "no_bars"}
    assert result.availability["distribution_metrics"]["reason"] == "incomplete_bars"
    assert result.metrics["benchmark_symbol"] == "SPY"


def test_missing_reasons_come_from_a_recording_reader(seams):
    class Reader:
        seen = ReadOnlyBars(frames={}, missing={"MSFT": "short:12/21"}, fingerprints={})

        def __call__(self, syms):
            return {"AAPL": frame(), "SPY": frame()}
    assert risk_payload.metrics_and_correlation(Reader()).missing_bars == {"MSFT": "short:12/21"}


def test_complete_bars_give_values_and_a_full_matrix(seams):
    result = risk_payload.metrics_and_correlation(lambda syms: {s: frame() for s in syms})
    assert result.missing_bars == {}
    assert result.metrics["annualised_vol"]["value"] is not None
    assert result.correlation["labels"] == ["AAPL", "MSFT"]
    assert result.correlation["values"][0][1] is not None


def test_no_overlapping_bars_gives_null_correlation_with_a_reason(seams):
    short = frame(days=5)
    result = risk_payload.metrics_and_correlation(
        lambda syms: {"AAPL": short, "MSFT": short, "SPY": frame()})
    assert result.correlation == {"labels": ["AAPL", "MSFT"], "values": None,
                                  "reason": "insufficient_overlap"}


def test_flat_benchmark_gives_null_beta_with_a_reason(seams):
    result = risk_payload.metrics_and_correlation(
        lambda syms: {**{s: frame() for s in syms}, "SPY": frame(flat=True)})
    assert result.metrics["beta_spy"]["value"] is None
    assert result.availability["beta_spy"] == "zero_variance"


def test_unavailable_bar_cache_is_raised_strict_or_not(seams):
    def reader(syms):
        raise DailyCacheUnavailable("daily bar cache /x is not mounted")
    for strict in (False, True):
        with pytest.raises(DailyCacheUnavailable):
            risk_payload.metrics_and_correlation(reader, strict=strict)


def test_other_reader_errors_degrade_as_today_and_raise_when_strict(seams):
    def reader(syms):
        raise RuntimeError("provider down")
    result = risk_payload.metrics_and_correlation(reader)
    assert result.availability["distribution_metrics"]["reason"] == "market_data_unavailable"
    with pytest.raises(RuntimeError, match="provider down"):
        risk_payload.metrics_and_correlation(reader, strict=True)


def test_correlation_errors_raise_only_when_strict(seams, monkeypatch):
    from swingbot.core.analytics import risk_metrics as rm

    def broken(symbols, bars):
        raise ValueError("bad matrix")
    monkeypatch.setattr(rm, "correlation_matrix", broken)
    bars = lambda syms: {s: frame() for s in syms}  # noqa: E731
    assert risk_payload.metrics_and_correlation(bars).correlation["values"] == []
    with pytest.raises(ValueError, match="bad matrix"):
        risk_payload.metrics_and_correlation(bars, strict=True)


STATE = {"open_trades": [trade("AAPL", 1)], "balance": 10_000.0, "open_heat": 0.5,
         "heat_cap": 6.0, "sector_heat": {"Tech": 0.5}, "unmapped_count": 0,
         "clusters": [], "throttle_mult": 1.0, "paused": False, "availability": {}}
BODY_KEYS = {"heat", "availability", "positions", "sector_heat", "unmapped_count",
             "clusters", "throttle", "metrics", "correlation"}


def test_market_body_carries_no_live_control_fields(seams):
    result = risk_payload.metrics_and_correlation(lambda syms: {s: frame() for s in syms})
    body = risk_payload.market_body(STATE, result)
    assert set(body) == BODY_KEYS and "killswitch" not in body["availability"]
    assert body["heat"]["utilisation_pct"] == round(0.5 / 6.0 * 100.0, 1)


def test_empty_body_has_every_key_and_no_figures():
    body = risk_payload.empty_body()
    assert set(body) == BODY_KEYS and body["positions"] is None
    assert body["correlation"] == {"labels": [], "values": []}
    assert body["metrics"]["var_95"] == {"value": None, "n": 0}


def test_compat_names_still_answer_from_risk_py():
    assert risk._closed_metrics is risk_payload._closed_metrics
    assert risk._DISTRIBUTION_KEYS == risk_payload._DISTRIBUTION_KEYS
    assert callable(risk._risk_metrics) and callable(risk._risk_metrics_and_correlation)


def test_core_risk_modules_never_import_admin():
    import inspect
    from swingbot.core.analytics import risk_read_model
    for module in (risk_payload, risk_read_model):
        assert "swingbot.admin" not in inspect.getsource(module)
```

- [ ] **Step 2: Run the file to verify it fails**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_risk_payload.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'swingbot.core.analytics.risk_payload'`.

- [ ] **Step 3: Move the read model**

```bash
git -C <wt> mv swingbot/admin/api_v1/risk_read_model.py swingbot/core/analytics/risk_read_model.py
```

Recreate `swingbot/admin/api_v1/risk_read_model.py` as a one-line docstring ("v204: moved to swingbot.core.analytics.risk_read_model; this path re-exports it") plus `from swingbot.core.analytics.risk_read_model import chronological_records, complete_bars, signed_weights  # noqa: F401`. V201-4's edits to the file move with it unchanged.

- [ ] **Step 4: Create `swingbot/core/analytics/risk_payload.py` and slim `risk.py`**

Build it per "Behaviour fixed here", with `_Recorder`, `_overlap_checked(correlation) -> dict` and `_zero_variance(frame) -> bool` as small helpers. That keeps `metrics_and_correlation` below complexity 15.

```python
@dataclass(frozen=True)
class RiskMetrics:
    metrics: dict
    correlation: dict
    availability: dict
    bars_as_of: dict[str, str]
    missing_bars: dict[str, str]
```

- [ ] **Step 5: Retarget the existing risk tests (patch paths only)**

In `tests/admin/test_api_v1_risk.py` (add `from swingbot.core.analytics import risk_payload` where a test needs it):
- line 758: `"swingbot.admin.api_v1.money.to_account_currency"` → `"swingbot.core.marketdata.fx_convert.to_account_currency"` (the stub already takes `**kwargs`);
- lines 995, 1031, 1078: `setattr(risk, "_money_metric", …)` → `setattr(risk_payload, "_money_metric", …)`;
- line 1099: `setattr(risk, "_market_values", …)` → `setattr(risk_payload, "_market_values", …)`;
- lines 815 and 1041: `setattr(risk, "_risk_metrics_and_correlation", lambda: (m, c, a))` → `setattr(risk, "_risk_metrics", lambda: risk_payload.RiskMetrics(m, c, a, {}, {}))`.

The `_risk_bars` patches at 946, 976, 996, 1091 and 1111 stay on `risk`. No assertion changes. One case may break: an existing route test pins a correlation matrix whose every pair is `null`. The spec's partial-book rule changes that shape. Update only that assertion to `{"labels": …, "values": None, "reason": "insufficient_overlap"}`, and name it in the commit body.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_risk_payload.py`
Expected: PASS, `0 failed`.
Run: `... file tests/admin/test_api_v1_risk.py`, `... file tests/admin/test_risk_read_model.py`, `... file tests/admin/test_admin_layer_readers.py`, `... file tests/analytics/test_risk_metrics.py`, `... file tests/admin_snapshots/test_golden_today.py`
Expected: PASS. The golden tests pass unchanged, which shows the move preserved the payload.
Run: `git -C <wt> grep -n "swingbot.admin" -- swingbot/core`
Expected: no output.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add swingbot/core/analytics/risk_payload.py swingbot/core/analytics/risk_read_model.py swingbot/admin/api_v1/risk_read_model.py swingbot/admin/api_v1/risk.py tests/admin/test_api_v1_risk.py tests/admin_snapshots/test_risk_payload.py
git -C <wt> commit -m "refactor(v204): risk maths into core unchanged; strict mode; golden parity"
```

# Phase: snapshot inputs and builders (V204-7, V204-8)

### Task V204-7: Snapshot inputs, `expected_bar_date`/`stale_inputs`, the risk builder

**Model:** opus — "last completed session" and the recorded inputs decide whether a stale risk picture can look current; both were blocking quant findings.

**Files:**
- Create: `swingbot/core/analytics/admin_snapshots.py`, `tests/admin_snapshots/test_snapshot_inputs.py`, `tests/admin_snapshots/test_build_risk.py`

**Interfaces:**
- Consumes: V204-5 `daily_readonly.RecordingReader`, `read_cached_daily`, `ReadOnlyBars`; V204-6 `risk_payload.metrics_and_correlation(reader, strict=True)`, `market_body`; v201 `session.last_regular_close(now)` (UTC-aware), `session.US_MARKET_TZ`, `fx.quote_currency_code(t, *, fetch=False)`, `fx.fx_rate(from, to, on, *, refresh=False)`; V204-3 config `ADMIN_STALE_SNAPSHOT_REGULAR_S`, `ADMIN_STALE_SNAPSHOT_EXTENDED_S` and v201's `ADMIN_STALE_PRICE_REGULAR_S`, `ADMIN_STALE_PRICE_EXTENDED_S`.
- Produces (index "Snapshot builders", V204-7 rows, exact): `SnapshotResult(doc, inputs, stale_inputs)` (frozen); `build_inputs(...)`, which returns the index's **inputs shape**; `expected_bar_date(now=None) -> date`; `stale_inputs_for(per_symbol, now=None) -> bool`; `build_risk() -> SnapshotResult`. Module-private, used again by V204-8: `_now()`, `_code_version()`, `_fx_inputs(tickers, *, on) -> tuple[dict, list[str]]`, `RISK_MIN_ROWS = 21`.

**Behaviour fixed here:**
- **The module stays light to import.** It imports `config`, `session`, `spot_metals`, `daily_readonly` and the standard library at top level. Pandas, the DB, `risk_payload`, `portfolio_state` and `fx` are imported inside the builders. It has no `swingbot.admin`, `swingbot.commands` or `discord` import (V204-10 guards this).
- **`build_inputs`** returns exactly the index's inputs shape:
  - `computed_at` is `computed_at.isoformat()`.
  - `quotes` and `fx` are copied as given. `oldest_quote_as_of` is the earliest `as_of`, compared with `datetime.fromisoformat` and returned as the original string. `oldest_fx_as_of` is the earliest FX `as_of` (ISO dates, so `min` over strings). Each is `None` when nothing has one.
  - `bars_as_of.per_symbol = {SYM: bars.fingerprints[SYM]["last_bar"] for SYM in bars.frames}`. `oldest`/`newest` are its min/max, else `None`.
  - `bar_files = dict(bars.fingerprints)`. It includes symbols whose short file was still fingerprinted, for audit.
  - `missing.quotes`/`missing.fx` are sorted unique lists. `missing.bars = dict(bars.missing)`.
  - `trade_ids` keeps its order.
  - `thresholds` reads the four config fields as floats.
  - `code_version = _code_version()`, which is `read_json(os.path.join(config._PROJECT_ROOT, "VERSION.json"), {}).get("bot")`.
- **`expected_bar_date(now)`**. Take `close = session.last_regular_close(now)` in `US_MARKET_TZ`. When `now` (in ET) falls on the same date as `close` and before 20:00 ET, the scan has not had its chance to update the daily file yet. The answer is then the previous session's close date, `session.last_regular_close(close - timedelta(seconds=1))`. Otherwise it is `close`'s ET date. Half days follow the same rule through `last_regular_close`. `now=None` means `_now()`.
- **`stale_inputs_for(per_symbol, now)`** drops spot metals (`spot_metals.is_spot_metal`). It is `False` when nothing is left. Otherwise it is `min(date.fromisoformat(d)) < expected_bar_date(now)`. A symbol under `missing.bars` never makes a snapshot stale; it is counted as missing instead.
- **`_fx_inputs(tickers, *, on)`**. For each unique upper-cased ticker, `code = fx.quote_currency_code(t, fetch=False)`. No code puts `t` in `missing`. A code whose major unit (`fx._major(code)[0]`) equals the account's records nothing, since no conversion happens. Otherwise the result gets `fx_map[src] = {"rate": fx.fx_rate(code, account, on, refresh=False), "as_of": <pair file last bar>}`. The last bar comes from `read_cached_daily([f"{src}{dst}=X"]).fingerprints.get(pair, {}).get("last_bar")`. A `None` rate also puts `t` in `missing`. It never fetches. `_fx_inputs` and `RecordingReader` both reach `read_cached_daily` as `daily_readonly.read_cached_daily`, looked up at call time, so one patch covers both.
- **`build_risk()`**:
  1. `now = _now()` and `reader = RecordingReader(min_rows=RISK_MIN_ROWS)`.
  2. `state = collect_portfolio_state(bars_reader=reader)`.
  3. `result = risk_payload.metrics_and_correlation(reader, strict=True)`.
  4. `doc = risk_payload.market_body(state, result)`.
  5. `inputs = build_inputs(computed_at=now, fx=fx_map, bars=reader.seen, missing_fx=missing_fx, trade_ids=[t.get("id") for t in open_trades])`, where `open_trades = state.get("open_trades") or []` and `fx_map, missing_fx = _fx_inputs([t.get("ticker") for t in open_trades], on=now.date())`. Per the brief correction, quotes are empty and `ledger` is `None`.
  6. `stale_inputs = stale_inputs_for(inputs["bars_as_of"]["per_symbol"], now)`.

  Every error propagates, including `DailyCacheUnavailable`, strict correlation and bar errors, and a DB error. `RISK_MIN_ROWS = 21`, because `risk_metrics._MIN_BARS` returns need `_MIN_BARS + 1` closes (a test pins the relation).

- [ ] **Step 1: Write the failing input tests** in `tests/admin_snapshots/test_snapshot_inputs.py`

```python
"""v204: what a snapshot records, and when its bars count as stale."""
from datetime import date, datetime, timezone

import pytest

from swingbot import config
from swingbot.core.analytics import admin_snapshots as snaps
from swingbot.core.market import session
from swingbot.core.marketdata.daily_readonly import ReadOnlyBars

NOW = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)          # Wed 11:00 ET
REAL_CODE_VERSION = snaps._code_version
FP = {"AAPL": {"path": "/m/daily/AAPL.csv", "mtime": 1.0, "last_bar": "2026-09-15", "rows": 500},
      "SPY": {"path": "/m/daily/SPY.csv", "mtime": 2.0, "last_bar": "2026-09-14", "rows": 500},
      "SAP.DE": {"path": "/m/daily/SAP.DE.csv", "mtime": 3.0, "last_bar": "2026-09-15", "rows": 9}}
BARS = ReadOnlyBars(frames={"AAPL": object(), "SPY": object()},
                    missing={"SAP.DE": "short:9/21", "XAUUSD": "spot_metal"}, fingerprints=FP)


@pytest.fixture(autouse=True)
def knobs(monkeypatch):
    for key, value in (("ADMIN_STALE_SNAPSHOT_REGULAR_S", 600), ("ADMIN_STALE_SNAPSHOT_EXTENDED_S", 1800),
                       ("ADMIN_STALE_PRICE_REGULAR_S", 120), ("ADMIN_STALE_PRICE_EXTENDED_S", 900)):
        monkeypatch.setattr(config, key, value)
    monkeypatch.setattr(snaps, "_code_version", lambda: "2.16.0")


def test_build_inputs_has_the_contract_shape():
    got = snaps.build_inputs(
        computed_at=NOW,
        quotes={"MSFT": {"price": 410.5, "as_of": "2026-09-16T14:58:30+00:00"},
                "AAPL": {"price": 230.1, "as_of": "2026-09-16T10:59:00-04:00"}},
        fx={"EUR": {"rate": 1.08, "as_of": "2026-09-15"}, "GBP": {"rate": 1.27, "as_of": "2026-09-14"}},
        bars=BARS, missing_quotes=["NEWX"], missing_fx=["SAP.DE", "SAP.DE"],
        ledger="main", trade_ids=[9, 7])
    assert got == {
        "computed_at": NOW.isoformat(),
        "oldest_quote_as_of": "2026-09-16T14:58:30+00:00",
        "quotes": {"MSFT": {"price": 410.5, "as_of": "2026-09-16T14:58:30+00:00"},
                   "AAPL": {"price": 230.1, "as_of": "2026-09-16T10:59:00-04:00"}},
        "fx": {"EUR": {"rate": 1.08, "as_of": "2026-09-15"}, "GBP": {"rate": 1.27, "as_of": "2026-09-14"}},
        "oldest_fx_as_of": "2026-09-14",
        "bars_as_of": {"per_symbol": {"AAPL": "2026-09-15", "SPY": "2026-09-14"},
                       "oldest": "2026-09-14", "newest": "2026-09-15"},
        "bar_files": FP,
        "missing": {"quotes": ["NEWX"], "fx": ["SAP.DE"],
                    "bars": {"SAP.DE": "short:9/21", "XAUUSD": "spot_metal"}},
        "ledger": "main", "trade_ids": [9, 7],
        "thresholds": {"stale_snapshot_regular_s": 600.0, "stale_snapshot_extended_s": 1800.0,
                       "stale_price_regular_s": 120.0, "stale_price_extended_s": 900.0},
        "code_version": "2.16.0"}


def test_build_inputs_with_nothing_recorded():
    got = snaps.build_inputs(computed_at=NOW)
    assert got["oldest_quote_as_of"] is None and got["oldest_fx_as_of"] is None
    assert got["bars_as_of"] == {"per_symbol": {}, "oldest": None, "newest": None}
    assert got["missing"] == {"quotes": [], "fx": [], "bars": {}} and got["bar_files"] == {}


def test_code_version_is_the_bot_line_of_version_json(monkeypatch, tmp_path):
    (tmp_path / "VERSION.json").write_text('{"ui": "1.0.0", "bot": "9.9.9"}')
    monkeypatch.setattr(snaps, "_code_version", REAL_CODE_VERSION)
    monkeypatch.setattr(config, "_PROJECT_ROOT", str(tmp_path))
    assert snaps._code_version() == "9.9.9"


def utc(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_expected_bar_date_monday_morning_after_a_holiday_friday():
    assert snaps.expected_bar_date(utc(2026, 4, 6, 13, 40)) == date(2026, 4, 2)    # Mon 09:40 ET


def test_expected_bar_date_saturday():
    assert snaps.expected_bar_date(utc(2026, 10, 31, 15, 0)) == date(2026, 10, 30)


def test_expected_bar_date_before_the_scan_updates_the_file():
    assert snaps.expected_bar_date(utc(2026, 10, 28, 21, 30)) == date(2026, 10, 27)  # Wed 17:30 ET


def test_expected_bar_date_after_20_et_is_today():
    assert snaps.expected_bar_date(utc(2026, 10, 29, 1, 0)) == date(2026, 10, 28)    # Wed 21:00 ET


def test_expected_bar_date_half_day_waits_like_a_full_day():
    assert snaps.expected_bar_date(utc(2026, 11, 27, 19, 0)) == date(2026, 11, 25)   # Fri 14:00 ET


def test_expected_bar_date_has_one_source(monkeypatch):
    seen = []
    monkeypatch.setattr(session, "last_regular_close",
                        lambda now=None: seen.append(now) or utc(2026, 9, 15, 20, 0))
    assert snaps.expected_bar_date(NOW) == date(2026, 9, 15) and seen == [NOW]


@pytest.mark.parametrize("per_symbol, stale", [
    ({"AAPL": "2026-09-15", "SPY": "2026-09-15"}, False),
    ({"AAPL": "2026-09-15", "SPY": "2026-09-14"}, True),
    ({"XAUUSD": "2026-09-01", "AAPL": "2026-09-15"}, False),   # spot metal never makes it stale
    ({"XAUUSD": "2026-09-01"}, False),
    ({}, False),
])
def test_stale_inputs_compare_with_the_last_completed_session(per_symbol, stale):
    assert snaps.stale_inputs_for(per_symbol, now=NOW) is stale


def test_monday_after_holiday_is_not_stale_on_thursday_bars():
    assert snaps.stale_inputs_for({"AAPL": "2026-04-02"}, now=utc(2026, 4, 6, 13, 40)) is False
```

- [ ] **Step 2: Write the failing builder tests** in `tests/admin_snapshots/test_build_risk.py`

```python
"""v204: the risk snapshot records its inputs, flags stale bars and fails loudly."""
from datetime import datetime, timezone

import pytest

from swingbot.core.analytics import admin_snapshots as snaps
from swingbot.core.analytics import risk_metrics, risk_payload
from swingbot.core.edge import portfolio_state
from swingbot.core.marketdata import daily_readonly, fx
from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable, ReadOnlyBars
from tests.admin_snapshots.golden_book import (  # noqa: F401
    GOLDEN_NOW, _clear_login_limiter, admin_app, assert_matches_golden, client, golden_book)

NOW = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)
RESULT = risk_payload.RiskMetrics(
    metrics={"benchmark_symbol": "SPY"}, correlation={"labels": [], "values": []},
    availability={}, bars_as_of={}, missing_bars={})
STATE = {"open_trades": [
    {"id": 7, "ticker": "AAPL", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0, "shares": 10.0},
    {"id": 9, "ticker": "SAP.DE", "direction": "bullish", "entry": 50.0, "stop_loss": 45.0, "shares": 4.0},
    {"id": 11, "ticker": "XAUUSD", "direction": "bullish", "entry": 2400.0, "stop_loss": 2350.0, "shares": 1.0}],
    "balance": 10_000.0, "open_heat": 0.7, "heat_cap": 6.0, "sector_heat": {}, "unmapped_count": 3,
    "clusters": [], "throttle_mult": 1.0, "paused": False, "availability": {}}


def bars(per):
    fps = {s: {"path": f"/m/{s}.csv", "mtime": 1.0, "last_bar": d, "rows": 500} for s, d in per.items()}
    return ReadOnlyBars(frames={s: object() for s in per},
                        missing={"SAP.DE": "no_file", "XAUUSD": "spot_metal"}, fingerprints=fps)


@pytest.fixture
def world(monkeypatch):
    calls = {}

    def collect(*, bars_reader=None):
        calls["collect_reader"] = bars_reader
        bars_reader(["AAPL", "SAP.DE", "XAUUSD"])
        return dict(STATE)

    def metrics(reader, *, strict=False):
        calls["strict"] = strict
        reader(["AAPL", "SPY"])
        return RESULT
    monkeypatch.setattr(portfolio_state, "collect_portfolio_state", collect)
    monkeypatch.setattr(risk_payload, "metrics_and_correlation", metrics)
    monkeypatch.setattr(fx, "account_currency_code", lambda: "USD")
    monkeypatch.setattr(fx, "quote_currency_code",
                        lambda t, **k: {"AAPL": "USD", "XAUUSD": "USD"}.get(t))
    monkeypatch.setattr(snaps, "_now", lambda: NOW)
    monkeypatch.setattr(snaps, "_code_version", lambda: "2.16.0")
    return calls


def test_risk_builder_records_inputs_and_flags_stale_bars(world, monkeypatch):
    monkeypatch.setattr(daily_readonly, "read_cached_daily",
                        lambda syms, **k: bars({"AAPL": "2026-09-15", "SPY": "2026-09-14"}))
    res = snaps.build_risk()
    assert res.doc == risk_payload.market_body(STATE, RESULT)
    assert world["strict"] is True
    assert isinstance(world["collect_reader"], daily_readonly.RecordingReader)
    assert res.inputs["missing"] == {"quotes": [], "fx": ["SAP.DE"],
                                     "bars": {"SAP.DE": "no_file", "XAUUSD": "spot_metal"}}
    assert res.inputs["quotes"] == {} and res.inputs["oldest_quote_as_of"] is None
    assert res.inputs["trade_ids"] == [7, 9, 11] and res.inputs["ledger"] is None
    assert res.stale_inputs is True                         # SPY is a session behind


def test_current_bars_are_not_stale_and_spot_metal_is_only_missing(world, monkeypatch):
    monkeypatch.setattr(daily_readonly, "read_cached_daily",
                        lambda syms, **k: bars({"AAPL": "2026-09-15", "SPY": "2026-09-15"}))
    res = snaps.build_risk()
    assert res.stale_inputs is False and res.inputs["missing"]["bars"]["XAUUSD"] == "spot_metal"


def test_non_usd_position_records_its_rate_and_pair_date(world, monkeypatch):
    monkeypatch.setattr(fx, "quote_currency_code", lambda t, **k: "EUR" if t == "SAP.DE" else "USD")
    monkeypatch.setattr(fx, "fx_rate", lambda src, dst, on, **k: 1.08 if k == {"refresh": False} else None)
    pair = ReadOnlyBars({}, {}, {"EURUSD=X": {"path": "p", "mtime": 1.0, "last_bar": "2026-09-15", "rows": 9}})
    monkeypatch.setattr(daily_readonly, "read_cached_daily", lambda syms, **k: (
        pair if list(syms) == ["EURUSD=X"] else bars({"AAPL": "2026-09-15", "SPY": "2026-09-15"})))
    res = snaps.build_risk()
    assert res.inputs["fx"] == {"EUR": {"rate": 1.08, "as_of": "2026-09-15"}}
    assert res.inputs["missing"]["fx"] == []


def test_missing_bar_cache_fails_the_risk_snapshot(world, monkeypatch):
    def unmounted(syms, **k):
        raise DailyCacheUnavailable("daily bar cache /app/market_data is not mounted")
    monkeypatch.setattr(daily_readonly, "read_cached_daily", unmounted)
    with pytest.raises(DailyCacheUnavailable, match="not mounted"):
        snaps.build_risk()


def test_min_rows_is_the_risk_metric_window():
    assert snaps.RISK_MIN_ROWS == risk_metrics._MIN_BARS + 1


def test_risk_snapshot_doc_matches_the_golden_payload(golden_book, monkeypatch):
    monkeypatch.setattr(risk_payload, "_now", lambda: GOLDEN_NOW)
    monkeypatch.setattr(snaps, "_now", lambda: GOLDEN_NOW)
    res = snaps.build_risk()
    assert set(res.doc) == set(risk_payload.empty_body())
    assert_matches_golden("risk", res.doc)       # normalise drops availability.killswitch
    assert golden_book.network_calls == []
    assert res.inputs["fx"] == {"EUR": {"rate": 1.1, "as_of": None}}   # no EURUSD=X file in the book
    assert res.stale_inputs is False                                   # bars end 2026-10-28
```

The golden test is the snapshot's half of the anti-fork rule. The off path was pinned to the same file in V204-6. `golden_book` serves `data.get_daily_data*` from the same yfinance-basis files `read_cached_daily` reads, under `chdir(tmp_path)`, so clusters and metrics see identical frames. Never edit the golden file.

- [ ] **Step 3: Run both files to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_snapshot_inputs.py`, then `... file tests/admin_snapshots/test_build_risk.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'swingbot.core.analytics.admin_snapshots'`.

- [ ] **Step 4: Create `swingbot/core/analytics/admin_snapshots.py`**

The module docstring says this is v204. It defines the admin page snapshots the refresher stores in `admin_snapshots` (the table), and names the inputs contract and the "last completed session" rule with its 20:00 ET window. It states that `analytics_snapshot.json` stays for Discord. Build it per "Behaviour fixed here", splitting `build_inputs` into `_oldest_iso(values)`, `_bars_block(bars)` and `_thresholds()`, so every function stays below complexity 15.

```python
@dataclass(frozen=True)
class SnapshotResult:
    doc: dict
    inputs: dict
    stale_inputs: bool


RISK_MIN_ROWS = 21     # risk_metrics._MIN_BARS returns need _MIN_BARS + 1 closes
_SCAN_GRACE_HOUR_ET = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_snapshot_inputs.py`, `... file tests/admin_snapshots/test_build_risk.py`
Expected: PASS, `0 failed`.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add swingbot/core/analytics/admin_snapshots.py tests/admin_snapshots/test_snapshot_inputs.py tests/admin_snapshots/test_build_risk.py
git -C <wt> commit -m "feat(v204): snapshot inputs, last-completed-session staleness, the risk builder"
```

### Task V204-8: Analytics, sparkline and Calendar builders; `compute_snapshot`; file-producer parity

**Model:** opus — moves route bodies into core under a parity rule, and is the one place where the Discord file and the admin table could start disagreeing about the same trades.

**Files:**
- Modify: `swingbot/core/analytics/admin_snapshots.py`, `swingbot/core/analytics/snapshots.py` (`refresh_snapshot` 108-131)
- Create: `tests/admin_snapshots/test_build_analytics.py`, `tests/admin_snapshots/test_file_producer_parity.py`
- Create **only if V204-2 marked at least one route `snapshot`**: `swingbot/core/analytics/page_bodies.py`. Then modify `swingbot/admin/api_v1/analytics.py` (`analytics_performance` 163-307 and/or `analytics_equity_curve` 310-399, plus helpers 84-161) and/or `swingbot/admin/api_v1/calendar.py` (`calendar_pnl` 71-107), only so they call the moved body functions.

**Interfaces:**
- Consumes: V204-7 `SnapshotResult`, `build_inputs`, `build_risk`, `_now`, `_fx_inputs`; V204-3 `admin_refresh.SNAPSHOT_RISK`, `SNAPSHOT_ANALYTICS`, `performance_key`, `equity_curve_key`, `calendar_key`, `calendar_months`; v201 `fx_convert.to_account_currency(rows, *, fetch=)`, `missing_count`, `admin_refresh.refresher_on()`; `scope.LEDGERS`, `parse_scope`, `closed_only`, `select`; part 1 `golden_book`, `golden_payload`, `assert_matches_golden`, `GOLDEN_MONTH`; V204-2's verdict lines.
- Produces (index "Snapshot builders", V204-8 rows, exact): `SNAPSHOT_ROUTES: frozenset[str]`; `build_analytics_snapshot()`; `build_performance(ledger)`, `build_equity_curve(ledger)` and `build_calendar(month)`, each `-> SnapshotResult` and each only for a route in `SNAPSHOT_ROUTES`; `builders(now=None) -> dict[str, Callable[[], SnapshotResult]]`; `snapshots.compute_snapshot(sources=None) -> dict` and `snapshots.gather_sources() -> SnapshotSources`; `page_bodies.performance_body(scope, *, all_raw=None)`, `equity_curve_body(scope, *, all_raw=None)`, `calendar_body(month, filters, *, rows=None)`, each `-> dict`. The keyword arguments are optional and default to today's reads, so the index signatures still hold.

**Behaviour fixed here:**
- **`SNAPSHOT_ROUTES`** is copied from V204-2's three verdict lines in `docs/superpowers/results/2026-10-29-v204-measure-first.md`. It holds every route whose verdict is `snapshot`. A test reads the doc and pins the two to each other.
- **`snapshots.gather_sources()`** is today's gather from `refresh_snapshot`: `all_trades`, `split_by_ledger`, `base_balance` and `registry.active_rows(...)`. It returns a frozen `SnapshotSources(closed, weak_closed, starting_balance, registry_entries)`. `compute_snapshot(sources=None)` takes `s = sources or gather_sources()` and returns `build_snapshot(s.closed, s.starting_balance, s.registry_entries, weak_closed=s.weak_closed)` (today's call form). It **raises** on any error. `refresh_snapshot()` becomes `save_snapshot(compute_snapshot())` inside today's `try/except` with today's warning, so the file and its Discord readers are unchanged.
- **`build_analytics_snapshot()`** is `src = snapshots.gather_sources()`, then `doc = snapshots.compute_snapshot(src)` and `inputs = build_inputs(computed_at=_now(), trade_ids=[t.get("id") for t in [*src.closed, *src.weak_closed]])`. Its `stale_inputs` is `False`, because the file's figures use neither bars, quotes nor FX. It never calls `save_snapshot`. This one key also feeds the dashboard sparkline (`doc["equity_curve"]["points"][-30:]`, V204-13).
- **`page_bodies.py`**, for the routes marked `snapshot` only. Each route body moves **unchanged** from `tl = TradeLog()` (or `everything = pc.load_rows(...)`) to the `jsonify(...)` argument, and returns that dict. There are four permitted differences:
  1. `closed_pnl` → `swingbot.core.tracking.performance.closed_pnl_pct`, the function `admin.dashboard.closed_pnl` delegates to.
  2. `money.to_account_currency`/`missing_count` → `fx_convert.to_account_currency(rows, fetch=not admin_refresh.refresher_on())`/`fx_convert.missing_count`, which is what V201-4's `money.py` passes.
  3. `all_raw`/`rows`, when given, replace the body's own first read.
  4. `scope`/`month`/`filters` arrive as arguments instead of `_scope()`, `_month_param()` and `_filter_args()`.

  The helpers the moved bodies use (`_all_trades`, `_index_benchmark`, `_weak_in_account_currency`, `_fx_missing_total`) move with them. `analytics.py` keeps each old name as an alias (`_all_trades = page_bodies._all_trades`, …), because other routes call `_all_trades`. A route then reads `return jsonify(page_bodies.performance_body(_scope()))` (equity curve likewise), or `return jsonify(page_bodies.calendar_body(_month_param(), _filter_args()))`. `_reject_unknown_params()` still runs first in `calendar_pnl`. `page_bodies` imports nothing from `swingbot.admin`.
- **The builders**, for routes in `SNAPSHOT_ROUTES` only:
  - `build_performance(ledger)` reads `all_raw = TradeLog().get_trades(status=None, limit=None, ledger=None) or []` once, takes `scope = parse_scope({"ledger": ledger})`, and builds `doc = performance_body(scope, all_raw=all_raw)`. Its `ids = [t.get("id") for t in select(closed_only(all_raw), scope)]`, it calls `_fx_inputs(<those trades' tickers>, on=_now().date())`, and it records `ledger=ledger`. `build_equity_curve(ledger)` works the same way.
  - `build_calendar(month)` reads `rows = pc.load_rows(convert=<the fetch-aware converter>)`, builds `doc = calendar_body(month, (None, None), rows=rows)`, and records the unique `trade_id`s of `rows` whose `day` starts with `month` (first-seen order) and their tickers' FX.

  Each builder's `stale_inputs` is `False`. Their staleness is age-based (V204-11), and they use no bars.
- **`builders(now=None)`** has keys in this order:
  1. `SNAPSHOT_RISK` → `build_risk`.
  2. `SNAPSHOT_ANALYTICS` → `build_analytics_snapshot`.
  3. For each `ledger` in `scope.LEDGERS`: `performance_key(ledger)` and then `equity_curve_key(ledger)`, each only when its route is in `SNAPSHOT_ROUTES`. The value is `functools.partial(build_..., ledger)`.
  4. When `"calendar.pnl"` is in `SNAPSHOT_ROUTES`: `calendar_key(m)` for each `m` in `calendar_months(now or _now())`.

- [ ] **Step 1: Read the verdicts**

Run: `grep -n "analytics.performance\|analytics.equity_curve\|calendar.pnl" <wt>/docs/superpowers/results/2026-10-29-v204-measure-first.md`
Expected: one verdict line per route, each naming `request` or `snapshot`. Write down the routes marked `snapshot`. A missing or ambiguous verdict line means `BLOCKED: V204-2 verdict for <route>`. Do not guess.

- [ ] **Step 2: Write the failing builder tests** in `tests/admin_snapshots/test_build_analytics.py`

```python
"""v204: analytics, sparkline and calendar builders; the file producer keeps its behaviour."""
import functools
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from swingbot.core.analytics import admin_snapshots as snaps
from swingbot.core.analytics import snapshots
from swingbot.core.marketdata.shared import admin_refresh as ar
from tests.admin_snapshots.golden_book import (  # noqa: F401
    GOLDEN_MONTH, _clear_login_limiter, admin_app, assert_matches_golden, client, golden_book,
    golden_payload)

ROUTES = ("analytics.performance", "analytics.equity_curve", "calendar.pnl")
RESULTS = Path(__file__).resolve().parents[2] / "docs/superpowers/results/2026-10-29-v204-measure-first.md"
NOW = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)


def test_snapshot_routes_follow_the_measured_verdicts():
    text = RESULTS.read_text(encoding="utf-8")
    verdicts = {}
    for route in ROUTES:
        found = re.findall(rf"{re.escape(route)}\W+(request|snapshot)\b", text)
        assert found, f"no verdict line for {route}"
        verdicts[route] = found[0]
    assert snaps.SNAPSHOT_ROUTES == frozenset(r for r, v in verdicts.items() if v == "snapshot")


def test_builders_order_with_every_route_snapshotted(monkeypatch):
    monkeypatch.setattr(snaps, "SNAPSHOT_ROUTES", frozenset(ROUTES))
    for name in ("build_performance", "build_equity_curve", "build_calendar"):
        monkeypatch.setattr(snaps, name, lambda *a: None, raising=False)
    keys = list(snaps.builders(NOW))
    assert keys == ["risk", "analytics.snapshot",
                    "analytics.performance:main", "analytics.equity_curve:main",
                    "analytics.performance:weak", "analytics.equity_curve:weak",
                    "analytics.performance:both", "analytics.equity_curve:both",
                    *[ar.calendar_key(m) for m in ar.calendar_months(NOW)]]


def test_builders_hold_only_the_routes_marked_snapshot():
    keys = set(snaps.builders(NOW))
    assert {"risk", "analytics.snapshot"} <= keys
    prefixes = {"analytics.performance": "analytics.performance:",
                "analytics.equity_curve": "analytics.equity_curve:", "calendar.pnl": "calendar.pnl:"}
    for route, prefix in prefixes.items():
        has = any(k.startswith(prefix) for k in keys)
        assert has is (route in snaps.SNAPSHOT_ROUTES)
    assert all(ar.is_snapshot_key(k) for k in keys)


def test_compute_snapshot_raises_and_refresh_snapshot_still_swallows(monkeypatch):
    def broken():
        raise RuntimeError("registry unreadable")
    monkeypatch.setattr(snapshots, "gather_sources", broken)
    with pytest.raises(RuntimeError, match="registry unreadable"):
        snapshots.compute_snapshot()
    assert snapshots.refresh_snapshot() is None


def test_refresh_snapshot_still_saves_the_computed_doc(monkeypatch):
    saved = []
    monkeypatch.setattr(snapshots, "compute_snapshot", lambda sources=None: {"a": 1})
    monkeypatch.setattr(snapshots, "save_snapshot", saved.append)
    snapshots.refresh_snapshot()
    assert saved == [{"a": 1}]


def test_analytics_builder_never_writes_the_file_and_records_trade_ids(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("analytics_snapshot.json written by the refresher")
    src = snapshots.SnapshotSources(closed=[{"id": 1}], weak_closed=[{"id": 2}],
                                    starting_balance=10_000.0, registry_entries=[])
    monkeypatch.setattr(snapshots, "save_snapshot", boom)
    monkeypatch.setattr(snapshots, "gather_sources", lambda: src)
    monkeypatch.setattr(snapshots, "build_snapshot",
                        lambda closed, bal, reg, *, weak_closed=(): {"n": len(closed)})
    res = snaps.build_analytics_snapshot()
    assert res.doc == {"n": 1} and res.stale_inputs is False
    assert res.inputs["trade_ids"] == [1, 2]


def test_analytics_snapshot_and_sparkline_match_golden(golden_book):
    doc = snaps.build_analytics_snapshot().doc
    assert_matches_golden("analytics_snapshot", doc)
    spark = [p["balance"] for p in doc["equity_curve"]["points"][-30:]]
    assert spark == golden_payload("sparkline")["points"]


@pytest.mark.parametrize("route, name, golden", [
    ("analytics.performance", "build_performance", "performance_main"),
    ("analytics.equity_curve", "build_equity_curve", "equity_curve_main"),
])
def test_ledger_builders_match_the_golden_route_body(golden_book, route, name, golden):
    if route not in snaps.SNAPSHOT_ROUTES:
        assert not hasattr(snaps, name)
        return
    res = getattr(snaps, name)("main")
    assert_matches_golden(golden, res.doc)
    assert res.inputs["ledger"] == "main" and res.stale_inputs is False


def test_calendar_builder_matches_the_golden_month(golden_book):
    if "calendar.pnl" not in snaps.SNAPSHOT_ROUTES:
        assert not hasattr(snaps, "build_calendar")
        return
    res = snaps.build_calendar(GOLDEN_MONTH)
    assert_matches_golden("calendar_pnl", res.doc)
    assert res.inputs["fx"] == {"EUR": {"rate": 1.1, "as_of": None}}
    assert res.inputs["trade_ids"] == list(dict.fromkeys(res.inputs["trade_ids"]))


def test_partial_builders_are_bound_to_their_scope(monkeypatch):
    monkeypatch.setattr(snaps, "SNAPSHOT_ROUTES", frozenset({"analytics.performance"}))
    monkeypatch.setattr(snaps, "build_performance", lambda ledger: ledger, raising=False)
    fn = snaps.builders(NOW)["analytics.performance:weak"]
    assert isinstance(fn, functools.partial) and fn() == "weak"
```

The regex expects the verdict line to put the route name and then its verdict word on one line, for example `analytics.performance: snapshot` or a table row `| analytics.performance | snapshot |`. If V204-2's doc words its lines differently, adjust **the regex** to that wording. Never adjust the verdict.

- [ ] **Step 3: Write the failing file-producer parity test** in `tests/admin_snapshots/test_file_producer_parity.py`

```python
"""v204: analytics_snapshot.json (Discord) and the admin routes agree on the same trades."""
import pytest

from swingbot import config
from swingbot.core.analytics import snapshots
from swingbot.core.marketdata import fx
from tests.admin_snapshots.golden_book import (  # noqa: F401
    _clear_login_limiter, admin_app, client, golden_book)


@pytest.fixture
def same_currency(golden_book, monkeypatch):
    """The file sums stored amounts and the routes convert; an identity rate makes both one sum."""
    account = fx.account_currency_code()
    monkeypatch.setattr(fx, "quote_currency_code", lambda t, **k: account)
    assert config.ADMIN_REFRESHER == "off"                     # golden_book: today's routes
    return golden_book.client


def get(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    return response.get_json()


def test_main_ledger_totals_and_equity_agree(same_currency):
    src = snapshots.gather_sources()
    file_doc = snapshots.compute_snapshot(src)
    perf = get(same_currency, "/api/v1/analytics/performance?ledger=main")
    curve = get(same_currency, "/api/v1/analytics/equity-curve?ledger=main")
    overall = file_doc["overall"]
    assert perf["totals"]["closed"] == overall["n"] == curve["points_n"]
    assert perf["win_rate"] == overall["win_rate"]
    assert perf["expectancy_r"] == overall["expectancy_r"]
    file_points = file_doc["equity_curve"]["points"]
    assert file_points, "the golden book must close at least one main-ledger trade"
    assert curve["points"][-1]["cum_pnl"] == pytest.approx(
        file_points[-1]["balance"] - src.starting_balance, abs=0.01)


def test_weak_ledger_totals_agree(same_currency):
    weak = snapshots.compute_snapshot()["weak"]
    perf = get(same_currency, "/api/v1/analytics/performance?ledger=weak")
    curve = get(same_currency, "/api/v1/analytics/equity-curve?ledger=weak")
    assert perf["totals"]["closed"] == weak["n"] == curve["points_n"]
    assert perf["win_rate"] == weak["win_rate"]
    final = curve["points"][-1]["cum_pnl"] if curve["points"] else 0.0
    assert final == pytest.approx(weak["total_pnl"], abs=0.01)
```

Each line of this file holds whichever way V204-2 went. Routes marked `request` serve today's body, and routes marked `snapshot` serve the moved one. Either way the file and the route must agree.

- [ ] **Step 4: Run both files to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_build_analytics.py`, then `... file tests/admin_snapshots/test_file_producer_parity.py`
Expected: FAIL with `AttributeError` on `snaps.SNAPSHOT_ROUTES`, `snapshots.gather_sources` and `snapshots.SnapshotSources`.

- [ ] **Step 5: Implement `snapshots.gather_sources`/`compute_snapshot`, the `page_bodies` moves and the builders**

Edit `snapshots.py` first, then `page_bodies.py` and the routes (only for `snapshot` routes), then extend `admin_snapshots.py`. Keep each builder small. Factor the shared "ids + tickers → `build_inputs`" step into `_ledger_inputs(trades, *, ledger) -> dict`. Then `builders` and each `build_*` stay below complexity 15. The moved route bodies keep their complexity exactly.

- [ ] **Step 6: Run the tests to verify they pass, plus today's route and file tests**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_build_analytics.py`, `... file tests/admin_snapshots/test_file_producer_parity.py`, `... file tests/admin_snapshots/test_golden_today.py`
Expected: PASS, `0 failed`.
Run: `... file tests/analytics/test_snapshots.py`, `... file tests/admin/test_api_v1_analytics.py`, `... file tests/admin/test_api_analytics.py`, `... file tests/admin/test_api_v1_calendar.py`, `... file tests/analytics/test_pnl_calendar.py`, and each file `git -C <wt> grep -ln "refresh_snapshot\|load_snapshot" -- tests` names
Expected: PASS, assertions unchanged. A test that patched a moved helper on `analytics_api`/`calendar` is retargeted to `page_bodies` (patch path only).
Run: `git -C <wt> grep -n "swingbot.admin" -- swingbot/core`
Expected: no output.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add swingbot/core/analytics/admin_snapshots.py swingbot/core/analytics/snapshots.py tests/admin_snapshots/test_build_analytics.py tests/admin_snapshots/test_file_producer_parity.py
# only when V204-2 marked a route `snapshot`:
git -C <wt> add swingbot/core/analytics/page_bodies.py swingbot/admin/api_v1/analytics.py swingbot/admin/api_v1/calendar.py
git -C <wt> commit -m "feat(v204): analytics, sparkline and calendar builders; compute_snapshot; file parity"
```

