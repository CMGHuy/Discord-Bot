"""Lifecycle partial-position lines render the v73 projection."""
from swingbot.core.scanning.plan_table import partial_position_line


class FakePlan:
    def __init__(self, **kw):
        defaults = dict(status="PARTIAL", direction="bullish", entry_price=100.0,
                        trigger_price=100.0, stop_loss=90.0, tp1=120.0, tp2=None,
                        working_stop=113.3333333,
                        legs_realized=[{"fraction": 0.5, "exit_price": 121.0,
                                        "r": 2.1, "reason": "tp1"}],
                        tp1_fraction=0.5, expiry_bars=5, created_at="2026-09-01")
        defaults.update(kw)
        for key, value in defaults.items():
            setattr(self, key, value)


def test_no_tp2_line_names_trail_not_target():
    line = partial_position_line(FakePlan())
    assert "121.00" in line and "113.33" in line
    assert "no tp2" not in line.lower()


def test_tp2_line_keeps_entry_target_stop_shape():
    line = partial_position_line(FakePlan(tp2=140.0))
    assert "121.00" in line and "140.00" in line and "113.33" in line


def test_legacy_runner_uses_floor_not_original_stop():
    line = partial_position_line(FakePlan(working_stop=None))
    assert "113.33" in line and "90.00" not in line


def test_bearish_floor_is_below_entry():
    plan = FakePlan(direction="bearish", entry_price=100.0, stop_loss=110.0,
                    tp1=80.0, working_stop=None,
                    legs_realized=[{"fraction": 0.5, "exit_price": 79.0, "r": 2.1}])
    assert "86.67" in partial_position_line(plan)
