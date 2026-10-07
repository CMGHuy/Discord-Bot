"""v136 §4: every bootstrap-reading verdict helper takes the cluster unit."""
import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "backtest")]

import funnel  # noqa: E402
import harvest_select  # noqa: E402

from swingbot.core.backtesting import acceptance  # noqa: E402
from swingbot.core.backtesting.arms import selection  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from tests.backtesting._cluster_fixture import FAST, pinned_arms  # noqa: E402


def _rows():
    _, c = pinned_arms()
    return [dataclasses.asdict(t) for t in c]


def test_expr_lower_bound_uses_the_week_bootstrap():
    rows = _rows()
    trades = [SimpleNamespace(**row) for row in rows]
    draws = stats.week_cluster_bootstrap(
        [], trades, lambda _b, comp: acceptance.expectancy_r(comp), **FAST)
    expected = float(np.percentile(draws, 100 * acceptance.ALPHA / 2))
    assert funnel.expr_lower_bound(rows, cluster="week", **FAST) == expected
    assert funnel.expr_lower_bound(rows, **FAST) != expected


def test_score_cell_threads_the_unit():
    rows = _rows()
    scored = funnel.score_cell(rows, funnel.MIN_N_TRAIN, cluster="week", **FAST)
    assert scored["lower_bound"] == funnel.expr_lower_bound(rows, cluster="week", **FAST)


def test_stage1_threads_the_unit():
    rows = _rows()
    grid = (0.1, 0.25, 0.5)
    rows_by_cell = {funnel.cell_key(value): rows for value in grid}
    out = funnel.stage1(rows_by_cell, "bullish", grid, cluster="week", **FAST)
    expected = funnel.score_cell(funnel.dir_rows(rows, "bullish"), funnel.MIN_N_TRAIN,
                                 cluster="week", **FAST)["lower_bound"]
    assert out["cells"]["0.1"]["lower_bound"] == expected


def test_evaluate_cell_passes_the_unit_to_the_gate(monkeypatch):
    seen = []
    real = acceptance.evaluate

    def spy(*args, **kwargs):
        seen.append(kwargs.get("cluster"))
        return real(*args, **kwargs)

    monkeypatch.setattr(selection.acceptance, "evaluate", spy)
    b, c = pinned_arms()
    selection.evaluate_cell(0.1, b, c, resolvable=True, **FAST)
    selection.evaluate_cell(0.1, b, c, resolvable=True, cluster="week", **FAST)
    assert seen == ["ticker", "week"]


def test_harvest_select_passes_the_unit_to_the_bootstrap(monkeypatch):
    seen = []

    def fake_delta(_baseline, _component, _statistic, **kwargs):
        seen.append(kwargs.get("cluster"))
        return acceptance.BootstrapResult(0.1, 0.05, 0.2, 0.01, 1, 42)

    monkeypatch.setattr(harvest_select, "bootstrap_delta", fake_delta)
    b, c = pinned_arms()
    harvest_select._row(0.1, b, c, set())
    harvest_select.select([(0.1, b, c), (0.25, b, c)], param="b",
                          less_aggressive="larger", cluster="week")
    assert seen == ["ticker", "week", "week"]
