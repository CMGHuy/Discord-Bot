import dataclasses
import datetime as dt

import pytest

from swingbot.core.gate import run_checklist
from swingbot.core.gate import registry
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan

EVENING = dt.datetime(2026, 7, 14, 23, 0, tzinfo=dt.timezone.utc)
QUIET_SNAP = {"built_at": "2026-07-14T22:00:00+00:00", "stale": False,
              "events": {"next_high_impact": None, "within_24h": [], "today": []}}


def _clean_run(strategy="Break & Retest"):
    df = uptrend_daily()
    plan = make_plan(strategy=strategy, created_at="2026-07-13",
                     trigger_price=float(df["Close"].iloc[-1]),
                     entry_price=None,
                     stop_loss=float(df["Close"].iloc[-1]) * 0.95,
                     tp1=float(df["Close"].iloc[-1]) * 1.10)
    return run_checklist(plan.ticker, strategy, plan, df,
                         macro_snap=QUIET_SNAP, now=EVENING)


def test_full_run_shape():
    result = _clean_run()
    assert {c.section for c in result.checks} == {"context", "setup", "redflag",
                                                  "risk", "timing"}
    assert 0 <= result.score <= 100
    assert result.hard_blocks == ()
    assert result.tier in ("A+", "A", "B", "C")
    assert result.as_of == str(uptrend_daily().index[-1].date())
    assert result.macro_stale is False


def test_raising_check_becomes_unknown(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("detector bug")
    spec = registry.CHECKS["atr_normal"]
    monkeypatch.setitem(registry.CHECKS, "atr_normal",
                        dataclasses.replace(spec, func=boom))
    result = _clean_run()
    by_id = {c.check_id: c for c in result.checks}
    assert by_id["atr_normal"].status == "unknown"        # never a scan crash
    assert by_id["htf_alignment"].status != "unknown"     # others unaffected


def test_strategy_filtering():
    breakout_ids = {c.check_id for c in _clean_run("Break & Retest").checks}
    vwap_ids = {c.check_id for c in _clean_run("VWAP").checks}
    assert "rf_fake_breakout" in breakout_ids
    assert "rf_fake_breakout" not in vwap_ids


def test_deterministic():
    a, b = _clean_run(), _clean_run()
    assert a.score == b.score and a.tier == b.tier
