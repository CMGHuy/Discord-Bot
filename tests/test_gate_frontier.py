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
