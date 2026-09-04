"""The veto TRAIN measures is the veto that ships.

entry_filters.py enforces this for entry logic by construction -- one
function, both worlds. v68's veto has two call sites, so it needs a test.
"""
import numpy as np
import pytest

from tests.conftest import make_ohlcv
from swingbot import config
from swingbot.core.market.chart_patterns import dead_cat_bounce, params_from_config
# engine must be imported before analyze: analyze.py's `from .engine import
# state, trade_log` and engine.py's `from .analyze import ScanItem, ...` are
# mutually dependent, and analyze.py resolves this only when engine is
# already partway initialized first (see tests/scanning/conftest.py, which
# does the same for every test under tests/scanning/). Pre-existing
# fragility, not introduced by v68 -- this module is just the first place
# outside tests/scanning/ to import analyze directly.
from swingbot.core.scanning import engine as _engine  # noqa: F401
from swingbot.core.scanning import analyze


def _frames():
    peak, trough = 100.0, 70.0
    dcb = make_ohlcv([peak] * 30 + list(np.linspace(peak, trough, 8))[1:]
                     + [72.0, 74.0, 75.0])
    recovery = make_ohlcv([peak] * 30 + list(np.linspace(peak, trough, 8))[1:]
                          + [85.0, 92.0, 96.0])
    calm = make_ohlcv([100.0] * 45)
    return {"dcb": dcb, "recovery": recovery, "calm": calm}


@pytest.mark.parametrize("name", ["dcb", "recovery", "calm"])
def test_both_call_sites_reach_the_same_verdict(name, monkeypatch):
    monkeypatch.setattr(config, "DEAD_CAT_BOUNCE_VETO", True)
    frame = _frames()[name]

    live = analyze.veto_bullish_for(frame)
    replay = dead_cat_bounce(frame, params_from_config())["detected"]

    assert live == replay, f"{name}: live={live} replay={replay}"


def test_the_live_seam_uses_the_shared_params_builder():
    """A second params dict anywhere is how the two worlds drift apart."""
    import inspect
    source = inspect.getsource(analyze.veto_bullish_for)
    assert "params_from_config()" in source
