"""autopsy.cells: cell vs complement, week-clustered bootstrap, BH over every cell."""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))

from autopsy import cells  # noqa: E402
from autopsy.cells import CellStats, Tally  # noqa: E402
from autopsy.rows import BookRow  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402

FAST = {"n_resamples": 200, "seed": 42}
MONDAYS = [(date(2026, 1, 5) + timedelta(weeks=i)).isoformat() for i in range(12)]


def _trade(day, net, gross=None, ticker="AAA"):
    return BookRow(row_kind="trade", ticker=ticker, entry_date=day, net_r=net,
                   gross_r=net if gross is None else gross)


def test_thin_by_n_or_by_weeks():
    assert cells.is_thin(29, 12)
    assert cells.is_thin(40, 7)
    assert not cells.is_thin(30, 8)


def test_a_cell_reports_its_own_numbers():
    members = [_trade(MONDAYS[0], 0.9, 1.0), _trade(MONDAYS[0], -1.1, -1.0, "BBB"),
               _trade(MONDAYS[1], 1.9, 2.0)]
    complement = [_trade(MONDAYS[0], -0.5), _trade(MONDAYS[1], 0.5)]
    cell = cells.cell_stats("strategy_horizon", "RSI|2w", members, complement, **FAST)
    assert (cell.id, cell.cut, cell.value) == ("strategy_horizon=RSI|2w", "strategy_horizon", "RSI|2w")
    assert (cell.n, cell.weeks) == (3, 2)
    assert cell.win_rate == pytest.approx(2 / 3)
    assert cell.net_expr == pytest.approx(1.7 / 3)
    assert cell.gross_expr == pytest.approx(2 / 3)
    assert cell.delta == pytest.approx(1.7 / 3 - 0.0)
    assert cell.ci is not None and cell.p is not None and cell.q is None
    assert cell.thin is True
    assert cell.extra == {"tickers": 2, "top_ticker_share": pytest.approx(0.6667)}


def test_the_bootstrap_gets_complement_then_cell_as_week_sums(monkeypatch):
    seen = {}

    def fake(baseline, component, statistic, *, n_resamples, seed):
        seen.update(baseline=baseline, component=component, statistic=statistic,
                    n_resamples=n_resamples, seed=seed)
        return np.array([0.1, 0.2, 0.3])

    monkeypatch.setattr(stats, "week_cluster_bootstrap", fake)
    members = [_trade(MONDAYS[0], 1.0), _trade(MONDAYS[0], 2.0), _trade(MONDAYS[1], 3.0)]
    complement = [_trade(MONDAYS[0], -1.0), _trade(MONDAYS[2], 0.0)]
    cell = cells.cell_stats("direction", "bullish", members, complement, **FAST)
    assert [(w.entry_date, w.total, w.n) for w in seen["component"]] == [
        (MONDAYS[0], 3.0, 2), (MONDAYS[1], 3.0, 1)]
    assert [(w.entry_date, w.total, w.n) for w in seen["baseline"]] == [
        (MONDAYS[0], -1.0, 1), (MONDAYS[2], 0.0, 1)]
    assert (seen["n_resamples"], seen["seed"]) == (200, 42)
    # the statistic is cell minus complement, on pooled means of the drawn weeks
    assert seen["statistic"](seen["baseline"], seen["component"]) == pytest.approx(2.0 - (-0.5))
    assert seen["statistic"]([], seen["component"]) is None
    assert cell.ci == pytest.approx((np.percentile([0.1, 0.2, 0.3], 2.5),
                                     np.percentile([0.1, 0.2, 0.3], 97.5)))


def test_a_clearly_better_cell_has_an_interval_above_zero():
    members = [_trade(d, 1.0 + 0.1 * (i % 3)) for d in MONDAYS for i in range(3)]
    complement = [_trade(d, -0.5 + 0.1 * (i % 3), ticker="ZZZ") for d in MONDAYS for i in range(3)]
    cell = cells.cell_stats("regime", "bull_quiet", members, complement, **FAST)
    assert cell.thin is False                      # 36 trades over 12 weeks
    assert cell.ci[0] > 0
    assert cell.p == pytest.approx(2 / 201)        # every draw positive: (0 + 1) x 2 / 201


def test_no_complement_means_no_delta_interval_or_p():
    cell = cells.cell_stats("direction", "bullish", [_trade(MONDAYS[0], 1.0)], [], **FAST)
    assert (cell.delta, cell.ci, cell.p) == (None, None, None)
    assert cell.n == 1 and cell.net_expr == 1.0


def test_the_same_seed_gives_the_same_interval():
    members = [_trade(d, 0.5 * (i - 1)) for i, d in enumerate(MONDAYS)]
    complement = [_trade(d, -0.2 * i) for i, d in enumerate(MONDAYS)]
    a = cells.cell_stats("weekday", "Mon", members, complement, **FAST)
    b = cells.cell_stats("weekday", "Mon", members, complement, **FAST)
    assert a.ci == b.ci and a.p == b.p


def test_a_missing_net_r_falls_back_to_gross_and_is_counted():
    member = BookRow(row_kind="trade", ticker="AAA", entry_date=MONDAYS[0], gross_r=1.0, net_r=None)
    cell = cells.cell_stats("direction", "bullish", [member], [], **FAST)
    assert cell.net_expr == 1.0
    assert cell.extra["net_modelled_missing"] == 1


def test_cut_cells_places_each_trade_once_and_counts_the_uncovered():
    trades = [_trade(MONDAYS[i], 1.0) for i in range(4)]
    trades += [_trade(MONDAYS[i], -1.0) for i in range(4)]
    trades += [_trade(MONDAYS[0], 100.0)]          # the key cannot place this one
    keys = {id(t): ("a" if t.net_r == 1.0 else "b" if t.net_r == -1.0 else None) for t in trades}
    out = cells.cut_cells("c", trades, lambda t: keys[id(t)], **FAST)
    assert [c.id for c in out] == ["c=a", "c=b"]
    assert [c.n for c in out] == [4, 4]
    assert all(c.extra["uncovered"] == 1 for c in out)
    # the unplaced 100 R trade is in neither arm: a's complement is exactly b
    assert out[0].delta == pytest.approx(2.0)
    assert out[1].delta == pytest.approx(-2.0)


def test_a_semicolon_in_a_value_cannot_break_the_cell_id():
    trades = [_trade(MONDAYS[0], 1.0), _trade(MONDAYS[1], -1.0)]
    out = cells.cut_cells("c", trades, lambda t: "x;y" if t.net_r > 0 else "z", **FAST)
    assert [c.id for c in out] == ["c=x,y", "c=z"]


def _bare(cell_id, p):
    cut, value = cell_id.split("=", 1)
    return CellStats(id=cell_id, cut=cut, value=value, n=1, weeks=1, win_rate=1.0,
                     net_expr=1.0, gross_expr=1.0, delta=None, ci=None, p=p, q=None, thin=True)


def test_bh_runs_once_over_every_tested_cell():
    pool = [_bare("a=1", 0.01), _bare("a=2", 0.04), _bare("b=1", 0.03), _bare("b=2", None)]
    tested = cells.apply_bh(pool)
    assert tested == 3
    assert [c.q for c in pool] == stats.bh_qvalues([0.01, 0.04, 0.03, None])
    assert pool[3].q is None


def test_cell_json_has_the_contract_keys_in_order():
    cell = _bare("a=1", 0.012345678)
    cell.ci, cell.delta, cell.bar_covered_n = (-0.123456, 0.654321), 0.3, 7
    out = cell.to_json()
    assert list(out) == ["id", "cut", "value", "n", "weeks", "win_rate", "net_expr",
                         "gross_expr", "delta", "ci", "p", "q", "thin", "bar_covered_n", "extra"]
    assert out["ci"] == [-0.1235, 0.6543] and out["p"] == 0.0123 and out["q"] is None
    assert _bare("a=2", None).to_json()["ci"] is None


def test_tally_json():
    assert Tally("fill_status=filled", "fill_status", "filled", 4).to_json() == {
        "id": "fill_status=filled", "cut": "fill_status", "value": "filled",
        "count": 4, "extra": {}}


def test_no_bootstrap_draw_means_all_comparison_fields_are_missing():
    cell = cells.cell_stats("c", "a", [_trade(MONDAYS[0], 1.0)],
                            [_trade(MONDAYS[1], -1.0)], n_resamples=0, seed=42)
    assert (cell.delta, cell.ci, cell.p) == (None, None, None)


def test_week_sums_group_iso_year_boundary_and_sort_weeks():
    trades = [_trade("2026-01-05", 4.0), _trade("2026-01-02", 2.0),
              _trade("2025-12-29", None, gross=1.0)]
    out = cells.week_sums(trades)
    assert [(w.entry_date, w.total, w.n) for w in out] == [
        ("2026-01-02", 3.0, 2), ("2026-01-05", 4.0, 1)]


def test_bootstrap_pools_trades_instead_of_averaging_week_means():
    # First week contributes three trades; second contributes only one.
    members = [_trade(MONDAYS[0], 0.0) for _ in range(3)]
    members.append(_trade(MONDAYS[1], 8.0))
    complement = [_trade(day, 0.0) for day in MONDAYS[:2]]
    cell = cells.cell_stats("c", "a", members, complement, n_resamples=1, seed=42)
    # Seed 42 draws week 0 and week 1 once each: pooled mean is 8/4.
    assert cell.delta == 2.0
    assert cell.ci == (2.0, 2.0)


def test_win_rate_uses_gross_returns_even_when_costs_erase_a_win():
    cell = cells.cell_stats("c", "a", [_trade(MONDAYS[0], -0.1, gross=0.1)], [], **FAST)
    assert cell.win_rate == 1.0
    assert cell.net_expr == -0.1


def test_empty_cell_has_zero_descriptives_and_no_comparison():
    cell = cells.cell_stats("c", "a", [], [_trade(MONDAYS[0], 1.0)], **FAST)
    assert (cell.n, cell.weeks, cell.win_rate, cell.net_expr, cell.gross_expr) == (0, 0, 0, 0, 0)
    assert (cell.delta, cell.ci, cell.p) == (None, None, None)
    assert cell.extra == {"tickers": 0, "top_ticker_share": 0.0}
    assert cells.cut_cells("c", [], lambda t: None, **FAST) == []
