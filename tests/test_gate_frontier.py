import pytest

from swingbot.core.gate.frontier import wr_by_decile


def synth_trades(n=200):
    """Deterministic monotone synthetic: score = i/2 (0..99.5); a trade
    wins iff score >= 40, so higher deciles have strictly higher WR."""
    trades = []
    for i in range(n):
        score = i / 2.0
        trades.append({"gate_score": score,
                       "outcome": "win" if score >= 40 else "loss",
                       "r_multiple": 1.5 if score >= 40 else -1.0})
    return trades


def test_deciles_monotone_and_golden():
    rows = wr_by_decile(synth_trades())
    assert len(rows) == 10
    assert [r["decile"] for r in rows] == list(range(10))
    assert rows[3]["wr"] == 0.0            # scores 30-40: all losses
    assert rows[4]["wr"] == 100.0          # scores 40-50: all wins
    wrs = [r["wr"] for r in rows]
    assert wrs == sorted(wrs)              # monotone by construction
    assert rows[9]["n"] == 20
    # The continuity-corrected Wilson bound (wr_math.py, frozen/golden per
    # its own docstring: 35/35 -> 0.877, 59/59 -> 0.924) gives 20/20 ->
    # 0.7995, not > 0.8 as a plain (uncorrected) Wilson interval would --
    # the correction is deliberately conservative at small n. Assert against
    # the real frozen function's output, not a hand-guessed round number.
    assert rows[9]["wilson_lb"] == pytest.approx(0.7995, abs=1e-4)
    assert rows[9]["expectancy_r"] == 1.5


def test_empty_trades():
    assert wr_by_decile([]) == []


from swingbot.core.gate.frontier import best_cut, frontier


def test_frontier_golden():
    rows = frontier(synth_trades(), cuts=range(0, 101, 20))
    by_cut = {r["cut"]: r for r in rows}
    assert by_cut[0]["n_kept"] == 200 and by_cut[0]["pct_kept"] == 100.0
    assert by_cut[0]["wr"] == 60.0                    # 120 of 200 win
    assert by_cut[40]["wr"] == 100.0                  # only winners survive
    assert by_cut[40]["pct_kept"] == 60.0
    assert by_cut[100]["n_kept"] == 0 and by_cut[100]["wr"] is None
    assert all("trades_per_month" in r and "wilson_lb" in r for r in rows)


def test_best_cut_constraints():
    rows = frontier(synth_trades(), cuts=range(0, 101, 20))
    chosen = best_cut(rows, min_n=30, max_signal_loss_pct=50.0)
    assert chosen["cut"] == 40                         # highest WR within loss budget
    # impossible constraints -> None is an allowed, reportable outcome
    assert best_cut(rows, min_n=500, max_signal_loss_pct=10.0) is None
