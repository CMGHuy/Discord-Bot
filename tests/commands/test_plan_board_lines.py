"""Discord board lines share the v73 plan projection."""
from swingbot.commands.plans import _partial_tail, _plan_line


class FakePlan:
    def __init__(self, **kw):
        defaults = dict(plan_id="p1", ticker="AAPL", status="PARTIAL",
                        direction="bullish", strategy="MACD", horizon_key="3m",
                        entry_price=100.0, trigger_price=100.0, stop_loss=90.0,
                        tp1=120.0, tp2=None, working_stop=113.3333333,
                        legs_realized=[{"fraction": 0.5, "exit_price": 121.0,
                                        "r": 2.1, "reason": "tp1"}],
                        tp1_fraction=0.5, expiry_bars=5, created_at="2026-09-01",
                        badge="WEAK", confidence_level=3, quality_score=3)
        defaults.update(kw)
        for key, value in defaults.items():
            setattr(self, key, value)


def test_no_tp2_runner_says_trailing_not_a_target():
    tail = _partial_tail(FakePlan())
    assert "trailing" in tail.lower()
    assert "TP2" not in tail


def test_no_tp2_runner_names_tp1_leg_as_banked():
    assert "banked" in _partial_tail(FakePlan()).lower()


def test_legacy_runner_still_shows_derived_floor():
    assert "113.33" in _partial_tail(FakePlan(working_stop=None))


def test_tp2_runner_shows_real_target():
    assert "140.00" in _partial_tail(FakePlan(tp2=140.0))


def test_pending_line_shows_distance_and_expiry():
    plan = FakePlan(status="PENDING", entry_price=None, working_stop=None,
                    legs_realized=[])
    line = _plan_line(plan, price=95.0, bars_since_created=2)
    assert "0.5R" in line
    assert "3 bars left" in line


def test_pending_line_omits_unknown_numbers():
    plan = FakePlan(status="PENDING", entry_price=None, working_stop=None,
                    legs_realized=[])
    line = _plan_line(plan)
    assert "R away" not in line
    assert "AAPL" in line
