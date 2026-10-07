"""Instrument v1 stays byte-identical (v136 cross-cutting rule 1).

sha256 digests of every ticker-cluster verdict path, taken on main at
6485b8bb (2026-10-06), BEFORE the v138 cluster selector existed. The
selector's default (cluster="ticker") must reproduce them exactly. Never
re-pin to make a failure go away: a mismatch means v1 moved."""
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "backtest")]

import funnel  # noqa: E402
import harvest_select  # noqa: E402

from swingbot.core.backtesting import acceptance, acceptance_harvest  # noqa: E402
from swingbot.core.backtesting.arms import selection  # noqa: E402
from tests.backtesting._cluster_fixture import FAST, pinned_arms  # noqa: E402

PINNED = {
    "cluster_bootstrap": "5a65607553c5f4d9faf84fe9e2fb104c4f295e3dc0dabc7c83c173c1d25894bc",
    "evaluate": "4e6900f17ad39f1487623dd0873dba87506f1c844fe62a61030e8582ea33681c",
    "evaluate_harvest": "1f40f41dc0b2a71b327f7b6e8c7fb4f8b336efb4d9e559b4d5d8b8e0f27e0c2f",
    "mde_paired": "0.036552475366009286",
    "score_cell": "04018d1c1d19213593ef440edb989f046764ca0047550cc17fd0d0227d68f27d",
    "evaluate_cell": "588d69e2a1a5bbc5911cc1c5c9113f1973de29d0cda23cda9e15d31a04c6c915",
    "harvest_row": "d760a4d98d502f492e272895b6584f57a9c569611fb1fa4ba21e2b594534aa22",
}


def _digest(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def test_cluster_bootstrap_draws():
    b, c = pinned_arms()
    draws = acceptance.cluster_bootstrap(b, c, acceptance.delta_standardised_win_rate,
                                         **FAST)
    assert hashlib.sha256(draws.tobytes()).hexdigest() == PINNED["cluster_bootstrap"]


def test_evaluate_rendering():
    b, c = pinned_arms()
    result = acceptance.evaluate(b, c, stage="walkforward", **FAST)
    assert _digest(acceptance.render_json(result)) == PINNED["evaluate"]


def test_evaluate_harvest_rendering():
    b, c = pinned_arms()
    result = acceptance_harvest.evaluate_harvest(b, c, stage="walkforward", **FAST)
    assert _digest(acceptance.render_json(result)) == PINNED["evaluate_harvest"]


def test_mde_paired_value():
    b, c = pinned_arms()
    value = acceptance.mde_paired(b, c, acceptance.delta_expectancy_r,
                                  observed_n=len(c), target_n=1000, **FAST)
    assert repr(value) == PINNED["mde_paired"]


def test_funnel_score_cell():
    _, c = pinned_arms()
    rows = [dataclasses.asdict(t) for t in c]
    assert _digest(funnel.score_cell(rows, 30, **FAST)) == PINNED["score_cell"]


def test_selection_evaluate_cell():
    b, c = pinned_arms()
    cell = selection.evaluate_cell(0.1, b, c, resolvable=True, **FAST)
    assert _digest(dataclasses.asdict(cell)) == PINNED["evaluate_cell"]


def test_harvest_select_row():
    b, c = pinned_arms()
    assert _digest(harvest_select._row(0.1, b, c, set())) == PINNED["harvest_row"]
