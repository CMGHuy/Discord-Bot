import inspect

import numpy as np
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.edge import correlation
from swingbot.core.edge.correlation import cluster_exposure, returns_corr


def _walk(seed, n=200):
    rng = np.random.default_rng(seed)
    return make_ohlcv(100 * np.cumprod(1 + rng.normal(0, 0.01, n)))


def test_clone_correlates_near_one():
    a = _walk(1)
    assert returns_corr(a, a.copy()) == pytest.approx(1.0)


def test_independent_walks_do_not():
    c = returns_corr(_walk(1), _walk(2))
    assert abs(c) < 0.5


def test_too_little_overlap_returns_none():
    a, b = _walk(1, n=200), _walk(2, n=10)
    assert returns_corr(a, b) is None


def test_cluster_exposure_counts_correlated_heat():
    a = _walk(1)
    dfs = {"AAA": a, "BBB": a.copy(), "CCC": _walk(2), "CAND": a.copy()}
    open_trades = [
        {"ticker": "AAA", "risk_pct": 2.0},
        {"ticker": "BBB", "risk_pct": 1.0},
        {"ticker": "CCC", "risk_pct": 2.0},
    ]
    exp = cluster_exposure(open_trades, "CAND", dfs, balance=10_000.0)
    assert exp["cluster"] == ["AAA", "BBB"]          # CCC uncorrelated
    assert exp["correlated_heat"] == pytest.approx(3.0)
    assert exp["max_corr"] == pytest.approx(1.0)


def test_sector_fallback_when_data_thin():
    dfs = {"AAA": _walk(1, n=10), "CAND": _walk(3, n=10)}   # too short to correlate
    exp = cluster_exposure([{"ticker": "AAA", "risk_pct": 2.0}], "CAND", dfs,
                           balance=10_000.0,
                           sectors={"AAA": "Information Technology",
                                    "CAND": "Information Technology"})
    assert exp["cluster"] == ["AAA"]                 # same sector counted


def test_default_window_is_a_named_constant_of_ninety():
    assert correlation.DEFAULT_WINDOW == 90


def test_both_signatures_default_to_the_constant():
    rc = inspect.signature(correlation.returns_corr).parameters["window"].default
    ce = inspect.signature(correlation.cluster_exposure).parameters["window"].default
    assert rc == correlation.DEFAULT_WINDOW
    assert ce == correlation.DEFAULT_WINDOW


def test_default_window_matches_the_explicit_ninety():
    a, b = _walk(1, n=300), _walk(2, n=300)
    assert correlation.returns_corr(a, b) == correlation.returns_corr(a, b, window=90)


def test_window_change_through_the_constant_is_read_at_definition_only(monkeypatch):
    # The default is bound when the function is defined: patching the constant
    # later does not change a call that omits `window` (same as a literal 90).
    a, b = _walk(1, n=300), _walk(2, n=300)
    before = correlation.returns_corr(a, b)
    monkeypatch.setattr(correlation, "DEFAULT_WINDOW", 40)
    assert correlation.returns_corr(a, b) == before
