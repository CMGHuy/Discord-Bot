"""v104 §3.4: a plan's hold_cap_bars shortens the timeout, nothing else."""
from swingbot.core.planning.exit_sim import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan


def _flat():
    return make_ohlcv([100.0] * 80, start="2024-01-02")


def _short(**kw):
    return _plan(direction="bearish", entry_type="market", trigger_price=100.0,
                 stop_loss=110.0, tp1=80.0, tp2=None, horizon_key="4w", **kw)


def test_hold_cap_times_out_early():
    capped = simulate_exit(_flat(), 30, _short(hold_cap_bars=3))
    free = simulate_exit(_flat(), 30, _short())
    assert capped.outcome == "timeout" and free.outcome == "timeout"
    assert capped.exit_index < free.exit_index
    assert capped.exit_index - capped.entry_index <= 3


def test_hold_cap_never_lengthens_the_horizon_default():
    capped = simulate_exit(_flat(), 30, _short(hold_cap_bars=999))
    free = simulate_exit(_flat(), 30, _short())
    assert capped.exit_index == free.exit_index
