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
    readers.discard("swingbot/commands/scanning/__init__.py")   # re-exports the V183-11 loop
    readers.discard("swingbot/config.py")
    assert readers <= ALLOWED_READERS, sorted(readers - ALLOWED_READERS)
