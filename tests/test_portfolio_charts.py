# tests/test_portfolio_charts.py
import os

import matplotlib
matplotlib.use("Agg")


def _trades():
    return [{"ticker": "XOM", "sector": "Energy", "risk_pct": 2.0, "current_r": 0.4},
            {"ticker": "CVX", "sector": "Energy", "risk_pct": 1.0, "current_r": -0.2},
            {"ticker": "MSFT", "sector": "Tech", "risk_pct": 1.5, "current_r": 1.1}]


def test_heat_treemap_renders(tmp_path):
    from swingbot.core.charts.portfolio_charts import render_heat_map
    path = render_heat_map(_trades(), {"total": 6.0, "sector": 3.0}, str(tmp_path))
    assert os.path.exists(path) and os.path.getsize(path) > 5_000


def test_heat_treemap_empty_state(tmp_path):
    from swingbot.core.charts.portfolio_charts import render_heat_map
    path = render_heat_map([], {"total": 6.0, "sector": 3.0}, str(tmp_path))
    assert os.path.exists(path)     # renders "no open positions", never crashes


def test_corr_matrix_renders(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.charts.portfolio_charts import render_corr_matrix
    rng = np.random.default_rng(1)
    a = make_ohlcv(100 * np.cumprod(1 + rng.normal(0, 0.01, 200)))
    dfs = {"AAA": a, "BBB": a.copy(), "CCC": make_ohlcv(
        100 * np.cumprod(1 + np.random.default_rng(2).normal(0, 0.01, 200)))}
    trades = [{"ticker": t} for t in dfs]
    path = render_corr_matrix(trades, dfs, str(tmp_path))
    assert os.path.getsize(path) > 5_000
