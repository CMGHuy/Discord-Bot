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
