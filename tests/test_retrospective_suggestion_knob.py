"""Plan v8 Task V5: the daily retrospective's low-RR suggestion must name
the knob that actually governs v2 TP1.

`_analyse` has always detected the payoff problem correctly, but it used to
suggest raising `MIN_RISK_REWARD_RATIO`, which only gates the LEGACY scenario
path in scanning/engine.py -- under PLAN_ENGINE_V2=on it cannot move TP1 at
all. So the bot diagnosed a real structural defect every day and recommended
a no-op. The floor (`MIN_TARGET_PCT`, Task V9) is the knob that moves it.
"""
import datetime as dt

from swingbot.core import retrospective


def _trade(status, exit_price):
    """entry 100 / stop 95 -> 1R = 5.00. A win at 101.75 is +0.35R, a loss
    at 95 is -1.00R: the live book's actual shape (payoff ratio 0.58)."""
    return {"status": status, "direction": "bullish", "entry": 100.0,
            "stop_loss": 95.0, "exit_price": exit_price,
            "confidence_level": 3, "horizon_key": "2w"}


def _analyse_low_rr():
    closed = ([_trade("win", 101.75)] * 6) + ([_trade("loss", 95.0)] * 4)
    return retrospective._analyse(closed, [], [], dt.date(2026, 7, 31), [])


def test_low_rr_suggests_the_target_floor_not_the_legacy_gate():
    _, suggestions, issues = _analyse_low_rr()
    assert issues.get("low_rr") is True
    [s] = [s for s in suggestions if "MIN_TARGET_PCT" in s]
    assert "MIN_RISK_REWARD_RATIO" not in s


def test_no_suggestion_still_points_at_the_legacy_gate():
    """Nothing anywhere in a daily retrospective may recommend
    MIN_RISK_REWARD_RATIO for a payoff problem -- it is the wrong lever
    under the v2 engine, and this is what made the nag a no-op."""
    _, suggestions, _ = _analyse_low_rr()
    assert not any("MIN_RISK_REWARD_RATIO" in s for s in suggestions)


def test_floor_is_snapshotted_so_the_nag_can_stop():
    """The escalation ladder only stops nagging when it can see the config
    key it suggested actually change, which requires the key to be in the
    snapshot written into each day's history entry."""
    assert "MIN_TARGET_PCT" in retrospective._TUNABLE_KEYS
    assert retrospective._live_config_snapshot()["MIN_TARGET_PCT"] == 2.5
