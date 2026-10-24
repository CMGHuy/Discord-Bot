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
