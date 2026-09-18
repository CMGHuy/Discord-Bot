from types import SimpleNamespace as Trade

from swingbot.core.backtesting import arm_rule as ar
from swingbot.core.market.strategy_types import HORIZONS


def _trades(wins, losses, scratches=0, timeouts=0):
    return ([Trade(outcome="win", r_multiple=1.0)] * wins + [Trade(outcome="loss", r_multiple=-1.0)] * losses
            + [Trade(outcome="scratch", r_multiple=0.0)] * scratches + [Trade(outcome="timeout", r_multiple=0.05)] * timeouts)


def _folds(*ns, exp=0.2):
    return [{"test_year": str(2021 + index), "stats": {"n": n, "expectancy_r": exp}} for index, n in enumerate(ns)]


def test_pooled_stats_and_empty():
    stats = ar.pooled_stats(_trades(6, 4, scratches=2))
    assert stats == {"n": 10, "wins": 6, "losses": 4, "win_rate": 60.0,
                     "expectancy_r": (6 - 4) / 12, "scratch_timeout_share": 2 / 12}
    assert ar.pooled_stats([]) == {"n": 0, "wins": 0, "losses": 0, "win_rate": None,
                                   "expectancy_r": None, "scratch_timeout_share": None}


def test_stage_one_clauses_and_zero_scratch_share():
    pooled = ar.pooled_stats(_trades(18, 14))
    verdict = ar.stage1_verdict(pooled, _folds(16, 15, 9))
    assert verdict["clears"] is True
    assert verdict["clauses"] == {"wr": True, "exp_r": True, "n": True, "scratch_share": True, "folds": True}
    assert ar.stage1_verdict({**pooled, "win_rate": 49.9}, _folds(16, 15))["clauses"]["wr"] is False
    assert ar.stage1_verdict({**pooled, "scratch_timeout_share": .51}, _folds(16, 15))["clauses"]["scratch_share"] is False


def test_stage_two_and_plateau_helpers():
    assert ar.stage2_allowed({"win_rate": 46.0, "expectancy_r": .3}) is True
    assert ar.stage2_allowed({"win_rate": 52.0, "expectancy_r": .3}) is False
    neighbours = ar.neighbour_subsets(("2m", "3m", "4m"), tuple(HORIZONS))
    assert ("3m", "4m") in neighbours and ("4w", "2m", "3m", "4m") in neighbours
    good = {"win_rate": 53.0, "n": 40}
    assert ar.plateau_ok(good, [good] * 4) is True
    assert ar.plateau_ok(good, [good] * 3) is False
