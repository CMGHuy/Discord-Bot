"""Registry classifications and outcome-level fixture observability (v100)."""
import pytest

from swingbot import config
from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.engine import run_arm

from .test_v74_fixture import load_v74_fixture

PERTURB = {bool: lambda value: not value, int: lambda value: max(1, value + 1),
           float: lambda value: value * 1.75 + 0.5}
HORIZONS_UNDER_TEST = ("4w", "3m")
WINDOW = ("1900-01-01", "2100-12-31")
_BASELINES: dict = {}


def _run(engines, delta):
    rows = []
    for ticker, frame in load_v74_fixture().items():
        for trade in run_arm(ticker, frame, engines, HORIZONS_UNDER_TEST, WINDOW, delta):
            r_multiple = None if trade.r_multiple is None else round(trade.r_multiple, 6)
            rows.append((trade.key, trade.outcome, r_multiple, trade.planned_rr))
    return sorted(rows, key=repr)


def _baseline(engines):
    if engines not in _BASELINES:
        _BASELINES[engines] = _run(engines, {})
    return _BASELINES[engines]


def test_every_searchable_knob_is_classified():
    assert set(reach.REGISTRY) == set(config.searchable_attrs())


@pytest.mark.slow
@pytest.mark.parametrize("attr", sorted(attr for attr, item in reach.REGISTRY.items() if item.fixture_observable))
def test_knob_is_observable(attr):
    engines = tuple(sorted(reach.REGISTRY[attr].observed_by))
    current = getattr(config, attr)
    changed = _run(engines, {attr: PERTURB[type(current)](current)})
    assert changed != _baseline(engines), (
        f"{attr} is classified fixture_observable but changed nothing on the fixture; "
        "set fixture_observable=False in reachability.py and explain why")
