"""v146 I2: attach_plan_v2 stamps risk_features.days_to_earnings from the
live earnings calendar, as of the decision bar, and never blocks a plan."""
import datetime as dt
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot.core.market import earnings_calendar
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.scanning import analyze
from tests.helpers import make_ohlcv


class _StubSource:
    def __init__(self, reports):
        self._reports = list(reports)
        self.calls = []

    def reports(self, ticker):
        self.calls.append(ticker)
        return list(self._reports)


class _RaisingSource:
    def reports(self, ticker):
        raise RuntimeError("earnings fetch failed")


def _plan():
    return TradePlanV2(plan_id="p", ticker="AAPL", created_at="2026-09-16", source="confluence",
                       strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
                       trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=98.0, tp1=110.0,
                       tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
                       quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                       status=PlanStatus.PENDING)


def _attach(monkeypatch, source, *, issued_at=None):
    import swingbot.config as config
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *args, **kwargs: _plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    monkeypatch.setattr(analyze, "stamp_entry_context", lambda plan, df, asof: None)
    monkeypatch.setattr(analyze, "_earnings_source", lambda: source)
    df = make_ohlcv([100.0] * 300, start="2025-06-02")
    item = SimpleNamespace(rs_combined=None, sector_rs_percentile=None, conf=None,
                           htf_bias=None, target_confluence=None)
    scenario = SimpleNamespace(direction="bullish", entry=100.0)
    analyze.attach_plan_v2(item, scenario, df, "AAPL", "3m", rs_percentile=50.0,
                           regime2_state="bull_quiet", issued_at=issued_at)
    return item, df


def test_stamp_equals_sessions_to_reaction_as_of_the_decision_bar(monkeypatch):
    last = make_ohlcv([100.0] * 300, start="2025-06-02").index[-1].date()
    source = _StubSource([earnings_calendar.Report(last + dt.timedelta(days=14), "after_close")])
    item, _ = _attach(monkeypatch, source)
    expected = earnings_calendar.sessions_to_reaction("AAPL", last, source=source)
    assert expected is not None and expected > 0
    assert item.plan_v2.risk_features["days_to_earnings"] == expected
    assert source.calls and set(source.calls) == {"AAPL"}


def test_a_raising_source_stamps_none_and_the_plan_still_posts(monkeypatch):
    item, _ = _attach(monkeypatch, _RaisingSource())
    assert item.plan_v2 is not None
    rf = item.plan_v2.risk_features
    assert rf["days_to_earnings"] is None
    assert rf["regime2_state"] == "bull_quiet"     # the rest of the stamp survived


def test_an_empty_calendar_stamps_none(monkeypatch):
    item, _ = _attach(monkeypatch, _StubSource([]))
    assert item.plan_v2.risk_features["days_to_earnings"] is None


def test_a_historical_replay_never_asks_the_live_calendar(monkeypatch):
    source = _StubSource([earnings_calendar.Report(dt.date(2026, 7, 30), "after_close")])
    item, _ = _attach(monkeypatch, source, issued_at="2025-01-02T21:00:00+00:00")
    assert item.plan_v2.risk_features["days_to_earnings"] is None
    assert source.calls == []


def test_decision_session_date_is_the_et_date_of_the_last_bar():
    naive = make_ohlcv([100.0] * 3, start="2026-07-20")
    assert analyze._decision_session_date(naive) == dt.date(2026, 7, 22)
    aware = pd.DataFrame({"Close": [1.0]},
                         index=pd.DatetimeIndex([pd.Timestamp("2026-07-24 03:00", tz="UTC")]))
    assert analyze._decision_session_date(aware) == dt.date(2026, 7, 23)   # 23:00 ET the day before


def test_days_to_earnings_swallows_a_bad_frame(monkeypatch):
    monkeypatch.setattr(analyze, "_earnings_source", lambda: _StubSource([]))
    assert analyze._days_to_earnings("AAPL", pd.DataFrame()) is None


# --- Panel fix: the stamp reads only already-warmed data, never the network --

_REAL_EARNINGS_SOURCE = analyze._earnings_source   # captured before conftest's autouse stub


@pytest.fixture
def cold_caches(monkeypatch, tmp_path):
    """The real cache-only source over an empty data dir and an empty
    in-process earnings cache. Every Yahoo entry point records its call: the
    stamp swallows exceptions, so a raising fetcher alone would prove nothing."""
    from swingbot import config
    from swingbot.core.market import events
    monkeypatch.setattr(analyze, "_earnings_source", _REAL_EARNINGS_SOURCE)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(events, "_earnings_datetimes_cache", {})
    fetched = []

    def _no_fetch(*args, **kwargs):
        fetched.append(args)
        raise AssertionError("the days_to_earnings stamp must never fetch")

    monkeypatch.setattr(events.yf, "Ticker", _no_fetch)
    monkeypatch.setattr(events, "get_earnings_datetimes", _no_fetch)
    return tmp_path, fetched


def _ledger(tmp_path, symbols):
    from swingbot.core.infra.jsonio import atomic_write_json
    atomic_write_json(str(tmp_path / "earnings_history.json"),
                      {"updated_at": "2025-07-01T00:00:00+00:00", "symbols": symbols})


def _frame_and_report():
    df = make_ohlcv([100.0] * 300, start="2025-06-02")
    last = df.index[-1].date()
    report_ts = dt.datetime.combine(last + dt.timedelta(days=14), dt.time(20, 30),
                                    tzinfo=dt.timezone.utc)                # 16:30 ET: after close
    return df, last, report_ts


def test_a_cold_cache_stamps_none_without_fetching(cold_caches):
    _, fetched = cold_caches
    df, _, _ = _frame_and_report()
    assert analyze._days_to_earnings("AAPL", df) is None
    assert fetched == []


def test_a_ticker_missing_from_a_warm_ledger_stamps_none_without_fetching(cold_caches):
    tmp_path, fetched = cold_caches
    df, _, report_ts = _frame_and_report()
    _ledger(tmp_path, {"MSFT": {"next": report_ts.isoformat(), "past": []}})
    assert analyze._days_to_earnings("AAPL", df) is None
    assert fetched == []


def test_the_weekly_ledger_yields_the_session_count(cold_caches):
    tmp_path, fetched = cold_caches
    df, last, report_ts = _frame_and_report()
    _ledger(tmp_path, {"AAPL": {"next": report_ts.isoformat(), "past": []}})
    expected = earnings_calendar.sessions_to_reaction(
        "AAPL", last, source=_StubSource([earnings_calendar.report_from_timestamp(report_ts)]))
    assert expected is not None and expected > 0
    assert analyze._days_to_earnings("aapl", df) == expected
    assert fetched == []


def test_a_fresh_in_process_cache_yields_the_session_count(cold_caches, monkeypatch):
    import time
    from swingbot.core.market import events
    _, fetched = cold_caches
    df, last, report_ts = _frame_and_report()
    events._earnings_datetimes_cache["AAPL"] = ([report_ts], time.monotonic())
    expected = earnings_calendar.sessions_to_reaction(
        "AAPL", last, source=_StubSource([earnings_calendar.report_from_timestamp(report_ts)]))
    assert analyze._days_to_earnings("AAPL", df) == expected
    assert fetched == []


def test_an_expired_or_empty_in_process_entry_is_not_trusted(cold_caches):
    """A cached [] may be a failed fetch (events caches it for 6h), and an
    expired entry is stale: neither is read as an answer."""
    import time
    from swingbot.core.market import events
    _, fetched = cold_caches
    df, _, report_ts = _frame_and_report()
    events._earnings_datetimes_cache["AAPL"] = ([report_ts], time.monotonic() - 7 * 3600)
    events._earnings_datetimes_cache["MSFT"] = ([], time.monotonic())
    assert analyze._days_to_earnings("AAPL", df) is None
    assert analyze._days_to_earnings("MSFT", df) is None
    assert fetched == []
