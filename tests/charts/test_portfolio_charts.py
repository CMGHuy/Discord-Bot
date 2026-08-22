# tests/test_portfolio_charts.py
import os

import matplotlib
import pytest
from tests.conftest import assert_rendered

# ~85% of suite runtime lives in nine files like this one; excluded from
# the fast tier (scripts/dev/testrun.py fast). See docs/claude/testing-cost.md.
pytestmark = pytest.mark.slow
matplotlib.use("Agg")


def _trades():
    return [{"ticker": "XOM", "sector": "Energy", "risk_pct": 2.0, "current_r": 0.4},
            {"ticker": "CVX", "sector": "Energy", "risk_pct": 1.0, "current_r": -0.2},
            {"ticker": "MSFT", "sector": "Tech", "risk_pct": 1.5, "current_r": 1.1}]


def test_heat_treemap_renders(tmp_path):
    from swingbot.core.charts.portfolio_charts import render_heat_map
    path = render_heat_map(_trades(), {"total": 6.0, "sector": 3.0}, str(tmp_path))
    assert_rendered(path)


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
    assert_rendered(path)


def test_mc_fan_renders(tmp_path):
    from swingbot.core.edge.ruin import simulate
    from swingbot.core.charts.portfolio_charts import render_mc_fan
    sim = simulate([0.4] * 8 + [-1.0] * 2, risk_pct=1.0,
                   n_trades=300, n_paths=500, return_paths=True)
    path = render_mc_fan(sim, 10_000.0, str(tmp_path),
                         percentile_paths=sim["percentile_paths"])
    assert_rendered(path)


def test_growth_path_chart_renders(tmp_path):
    from swingbot.core.charts.portfolio_charts import render_growth_path
    curve = [(f"2026-{m:02d}-01", 10_000 * (1.02 ** m)) for m in range(1, 13)]
    path = render_growth_path(curve, str(tmp_path))
    assert_rendered(path)


def test_fold_evidence_renders(tmp_path):
    from swingbot.core.charts.portfolio_charts import render_fold_evidence
    results = [{"component": "rs_min_60", "folds": [0.03, 0.02, -0.01], "verdict": "PASS"},
               {"component": "mtf_min_2", "folds": [0.01, -0.06, 0.02], "verdict": "FAIL"}]
    path = render_fold_evidence(results, str(tmp_path))
    assert_rendered(path)


def test_save_closes_figure_even_if_savefig_raises(tmp_path, monkeypatch):
    """A savefig failure (disk full, bad path, encoder error) must not leak
    the matplotlib Figure in this long-running bot process."""
    import matplotlib.pyplot as plt
    from swingbot.core.charts.portfolio_charts import _save

    def _boom(*a, **kw):
        raise RuntimeError("disk full")

    fig, ax = plt.subplots()
    fignum = fig.number
    monkeypatch.setattr(fig, "savefig", _boom)

    with pytest.raises(RuntimeError):
        _save(fig, str(tmp_path), "test.png")

    assert fignum not in plt.get_fignums()


def test_every_renderer_saves_through_the_disclaimer_helper():
    """Task E97: _save() is the ONLY place DISCLAIMER_TEXT gets drawn onto a
    portfolio chart -- if any render_* function called fig.savefig directly
    instead of returning _save(...), that chart would silently ship without
    the risk disclosure. Source-grepped rather than pixel-checked because
    the disclaimer text is 6pt, near-invisible in a saved-PNG byte-size
    assertion, and this is a structural guarantee, not a rendering one."""
    import inspect
    from swingbot.core.charts import portfolio_charts as pc

    src = inspect.getsource(pc)
    # Exactly one real fig.savefig call in the whole module -- inside _save().
    assert src.count("fig.savefig(") == 1
    for name, fn in inspect.getmembers(pc, inspect.isfunction):
        if name.startswith("render_"):
            assert "return _save(" in inspect.getsource(fn), \
                f"{name} does not return through _save() -- would ship without the disclaimer"
