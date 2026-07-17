from swingbot.commands.info import format_signal_plan_line
from tests.test_plan_engine_model import _plan


def test_plan_line_validated_with_tp2():
    p = _plan(strategy="MACD", horizon_key="4w", badge="VALIDATED",
              badge_stats={"win_rate": 81.3, "n": 123},
              trigger_price=101.2, stop_loss=99.1, tp1=101.94, tp2=104.0)
    assert format_signal_plan_line(p) == \
        "MACD 4w ✅ 81.3% | entry 101.20 stop 99.10 tp1 101.94 tp2 104.00"


def test_plan_line_weak_no_tp2():
    p = _plan(strategy="RSI", horizon_key="2m", badge="WEAK",
              badge_stats={"win_rate": 68.4, "n": 414},
              trigger_price=50.0, stop_loss=48.0, tp1=50.8, tp2=None)
    assert format_signal_plan_line(p) == \
        "RSI 2m ⚠️ 68.4% | entry 50.00 stop 48.00 tp1 50.80"
