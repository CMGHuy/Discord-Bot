import pytest

from swingbot.core.edge.throttle import current_throttle, drawdown_pct


def _curve(dd_pct):
    return [100.0, 120.0, 120.0 * (1 - dd_pct / 100)]


def test_drawdown_from_peak():
    assert drawdown_pct(_curve(10.0)) == pytest.approx(10.0)
    assert drawdown_pct([100.0, 110.0, 120.0]) == 0.0


def test_ladder_rungs():
    assert current_throttle(_curve(5.0)) == (1.0, False)
    assert current_throttle(_curve(9.0)) == (0.75, False)
    assert current_throttle(_curve(13.0)) == (0.50, False)
    assert current_throttle(_curve(17.0)) == (0.25, False)
    assert current_throttle(_curve(21.0)) == (0.0, True)     # paused


def test_hysteresis_stays_paused_until_15():
    mult, paused = current_throttle(_curve(18.0), was_paused=True)
    assert (mult, paused) == (0.0, True)     # 18% still paused (came from >20%)
    mult, paused = current_throttle(_curve(14.0), was_paused=True)
    assert paused is False and mult == 0.50  # recovered below 15 -> back on the ladder


def test_streak_damper_kicks_in_at_4():
    from swingbot.core.edge.throttle import streak_multiplier
    assert streak_multiplier(["loss"] * 3) == 1.0
    assert streak_multiplier(["loss"] * 4) == 0.5
    assert streak_multiplier(["win", "loss", "loss", "scratch", "loss", "loss"]) == 0.5
    # scratches don't extend: 3 losses + scratch + loss is still 4 consecutive


def test_streak_recovers_after_two_wins():
    from swingbot.core.edge.throttle import streak_multiplier
    assert streak_multiplier(["loss"] * 4 + ["win"]) == 0.5      # one win: not yet
    assert streak_multiplier(["loss"] * 4 + ["win", "win"]) == 1.0


def test_combined_floor():
    from swingbot.core.edge.throttle import combined_throttle
    assert combined_throttle(0.75, 0.5) == pytest.approx(0.375)
    assert combined_throttle(0.25, 0.5) == 0.25       # floor
    assert combined_throttle(0.0, 1.0) == 0.0         # pause always wins


def test_kill_triggers():
    from swingbot.core.edge.throttle import check_kill_triggers
    assert check_kill_triggers(21.0, 0.0, 0.0) == "drawdown >20%"
    assert check_kill_triggers(0.0, -5.5, 0.0) == "SPY moved 5.5% in a day"
    assert check_kill_triggers(0.0, 0.0, 0.30) == "30% of universe failed data quality"
    assert check_kill_triggers(10.0, 2.0, 0.05) is None


def test_kill_state_roundtrip(tmp_path, monkeypatch):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "killswitch.json"))
    assert throttle.kill_state()["on"] is False              # default off
    throttle.set_kill(True, reason="manual")
    st = throttle.kill_state()
    assert st["on"] is True and st["reason"] == "manual" and st["at"]
    throttle.set_kill(False)
    assert throttle.kill_state()["on"] is False
