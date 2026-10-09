"""v143 candidate rule on hand-built tables: one passing cell, then one table
failing each clause alone."""
import pytest

from swingbot.core.backtesting import fvg_diagnostic as fd
from tests.backtesting.fvg_diagnostic_rows import row, table


def cell(rows, key="gap_age", geometry="live"):
    return fd.feature_cell(rows, key, geometry, fd.medians(rows))


def test_a_cell_passing_every_clause_is_a_candidate():
    c = cell(table())                    # N 160, WR 60%, ExpR +0.20, unfav -0.5, 4/4 years
    assert c["favourable"] == {"n": 160, "win_rate": pytest.approx(60.0), "exp_r": pytest.approx(0.2)}
    assert c["unfavourable"]["n"] == 40 and c["years_positive"] == 4
    assert fd.candidate_failures(c) == []


@pytest.mark.parametrize("kwargs, failure", [
    (dict(fav_per_year=30, fav_wins=18), "N < 150"),
    (dict(unfav_r=0.15), "under +0.10R above the unfavourable side"),
])
def test_one_clause_fails_alone(kwargs, failure):
    assert fd.candidate_failures(cell(table(**kwargs))) == [failure]


def test_win_rate_clause_fails_alone():
    c = cell(table(fav_wins=19, win_r=2.0))           # 47.5% wins, ExpR +0.425
    assert c["favourable"]["exp_r"] == pytest.approx(0.425)
    assert fd.candidate_failures(c) == ["win rate < 50%"]


def test_expectancy_clause_fails_alone():
    c = cell(table(loss_r={"2023": -4.0}, unfav_r=-2.0))   # 60% wins, ExpR -0.10, 3 good years
    assert c["favourable"]["exp_r"] == pytest.approx(-0.1) and c["years_positive"] == 3
    assert fd.candidate_failures(c) == ["expectancy <= 0"]


def test_year_clause_fails_alone():
    wins = {"2020": 20, "2021": 20, "2022": 50, "2023": 50}
    c = cell(table(fav_per_year=50, fav_wins=wins))   # 70% wins, ExpR +0.40, 2 good years
    assert c["years_positive"] == 2
    assert fd.candidate_failures(c) == ["positive in fewer than 3 of 4 years"]


def test_under_the_computable_floor_is_not_tested_and_an_empty_side_fails_the_gap():
    rows = table() + [row(gap_age=None, role="unidentified") for _ in range(60)]
    c = cell(rows)                       # 200 of 260 computable = 76.9%
    assert (c["computable"], c["not_computable"]) == (200, 60)
    assert fd.candidate_failures(c) == [fd.NOT_TESTED]
    only_fav = [r for r in table() if r["features"]["gap_age"] == 5]
    assert fd.candidate_failures(cell(only_fav)) == ["under +0.10R above the unfavourable side"]


def test_medians_come_from_identified_rows_and_ties_are_favourable():
    rows = [row(quality=q) for q in (40, 60, 80)] + [row(quality=1000, role="unidentified")]
    med = fd.medians(rows)
    assert med["quality"] == 60
    assert [fd.side(r, "quality", med) for r in rows] == [False, True, True, True]
    assert fd.side(row(volatility=0.02), "volatility", {"volatility": 0.02}) is True
    assert fd.side(row(volatility=0.03), "volatility", {"volatility": 0.02}) is False
    assert fd.side(row(quality=None), "quality", med) is None
    assert fd.side(row(), "quality", {"quality": None}) is None


def test_stats_use_the_badge_definitions():
    rows = [row(outcome="win", r=1.0), row(outcome="loss", r=-1.0),
            row(outcome="timeout", r=0.4), row(outcome="scratch", r=0.0)]
    assert fd.stats(rows, "live") == {"n": 4, "win_rate": 50.0, "exp_r": pytest.approx(0.1)}
    assert fd.stats([], "live") == {"n": 0, "win_rate": None, "exp_r": None}


def test_population_tolerance_is_two_percent():
    assert fd.population_ok(1278) and fd.population_ok(1253) and fd.population_ok(1303)
    assert not fd.population_ok(1252) and not fd.population_ok(1304)
