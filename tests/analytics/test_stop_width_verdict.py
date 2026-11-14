"""v226: the pre-registered stop-width verdict -- every clause boundary, the
study's own BH family, and the three study verdicts. Clause boundaries are
driven through a stubbed ``_look`` so delta / bound / p are exact."""
from __future__ import annotations

import datetime as dt

import pytest

from swingbot.core.analytics import expectancy_attribution as ea

YEARS = ("2020", "2021", "2022", "2023")
NEG = {year: -0.5 for year in YEARS}
ZERO = {year: 0.0 for year in YEARS}
POS = {year: 0.2 for year in YEARS}
PASS = {"delta": -0.10, "ci_low": -0.2, "ci_high": -0.01, "p": 0.001}
FLAT = {"delta": 0.10, "ci_low": 0.0, "ci_high": 0.2, "p": 0.5}
LOOK_KEYS = ["n", "exp_r", "delta", "ci_low", "ci_high", "p", "q", "years",
             "years_negative", "clauses", "candidate"]


def _rows(n: int, tag: str, r_by_year: dict, years=YEARS) -> list[dict]:
    """``n`` rows tagged ``tag`` cycling over ``years``; r = r_by_year[year]."""
    out = []
    for i in range(n):
        year = years[i % len(years)]
        out.append({"r": r_by_year[year], "r_gross": r_by_year[year],
                    "week": f"{year}-03-02", "tag": tag, "stop_atr": 1.0})
    return out


def _groups(buckets: dict) -> dict:
    return {"buckets": dict(buckets),
            "known": [row for rows in buckets.values() for row in rows], "unknown": 0}


@pytest.fixture
def looks(monkeypatch):
    """tag -> the look ``_look`` returns for that bucket."""
    table = {}

    def fake_look(base, comp, seed):
        tag = comp[0]["tag"]
        assert all(row["tag"] != tag for row in base)        # rest never holds the bucket
        assert seed == 42
        return dict(table[tag])

    monkeypatch.setattr(ea, "_look", fake_look)
    return table


def _verdict(buckets: dict) -> dict:
    return ea.stop_width_verdict(_groups(buckets), seed=42)


def test_constants_are_the_pre_registered_values():
    assert (ea.VETO_DELTA, ea.VETO_MIN_N, ea.VETO_Q, ea.VETO_MIN_YEARS) == (-0.10, 300, 0.10, 3)
    assert ea.VETO_YEARS == YEARS
    assert ea.CLAUSE_KEYS == ("delta", "upper_bound", "negative_exp_r", "years", "n", "bh")
    assert ea.STUDY_VERDICTS == ("VETO-CANDIDATE", "UNDERPOWERED", "NO CANDIDATE")


def test_a_bucket_passing_all_six_clauses_is_a_candidate(looks):
    looks.update(A=PASS, B=FLAT)
    out = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})
    assert list(out) == ["verdict", "candidates", "family_size", "powered", "n_needed", "looks"]
    assert out["verdict"] == "VETO-CANDIDATE" and out["candidates"] == ["A"]
    assert (out["family_size"], out["powered"], out["n_needed"]) == (2, 2, 300)
    look = out["looks"]["A"]
    assert list(look) == LOOK_KEYS
    assert look["clauses"] == dict.fromkeys(ea.CLAUSE_KEYS, True) and look["candidate"] is True
    assert look["n"] == 300 and look["exp_r"] == -0.5
    assert look["years"] == {year: -0.5 for year in YEARS} and look["years_negative"] == 4
    assert look["q"] == pytest.approx(0.002)
    assert out["looks"]["B"]["candidate"] is False


@pytest.mark.parametrize("delta, passes", [(-0.10, True), (-0.099, False), (-0.5, True),
                                           (None, False)])
def test_clause_1_delta_boundary(looks, delta, passes):
    looks.update(A=dict(PASS, delta=delta), B=FLAT)
    look = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["clauses"]["delta"] is passes and look["candidate"] is passes


@pytest.mark.parametrize("ci_high, passes", [(-0.0001, True), (0.0, False), (0.01, False),
                                             (None, False)])
def test_clause_2_upper_bound_boundary(looks, ci_high, passes):
    looks.update(A=dict(PASS, ci_high=ci_high), B=FLAT)
    look = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["clauses"]["upper_bound"] is passes


def test_clause_3_bucket_exp_r_exactly_zero_fails(looks):
    looks.update(A=PASS, B=FLAT)
    # 304 rows in blocks of four (one per year), blocks alternating +0.5 / -0.5:
    # every year's mean is exactly 0, so the bucket ExpR is exactly 0.0.
    zero_mean = [dict(row, r=0.5 if (i // 4) % 2 == 0 else -0.5)
                 for i, row in enumerate(_rows(304, "A", ZERO))]
    look = _verdict({"A": zero_mean, "B": _rows(300, "B", POS)})["looks"]["A"]
    assert look["exp_r"] == 0.0
    assert look["clauses"] == dict(dict.fromkeys(ea.CLAUSE_KEYS, True), negative_exp_r=False)
    assert look["candidate"] is False


def test_clause_4_three_of_four_years_passes(looks):
    looks.update(A=PASS, B=FLAT)
    mixed = dict(NEG, **{"2023": 0.5})
    look = _verdict({"A": _rows(300, "A", mixed), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["years_negative"] == 3 and look["years"]["2023"] == 0.5
    assert look["clauses"]["years"] is True and look["candidate"] is True


def test_clause_4_two_of_four_years_fails(looks):
    looks.update(A=PASS, B=FLAT)
    mixed = dict(NEG, **{"2022": 0.2, "2023": 0.2})
    look = _verdict({"A": _rows(300, "A", mixed), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["exp_r"] < 0 and look["years_negative"] == 2
    assert look["clauses"]["years"] is False and look["candidate"] is False


def test_clause_4_a_year_without_bucket_rows_counts_against(looks):
    looks.update(A=PASS, B=FLAT)
    two_years = _rows(300, "A", NEG, years=("2020", "2021"))
    look = _verdict({"A": two_years, "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["years"] == {"2020": -0.5, "2021": -0.5, "2022": None, "2023": None}
    assert look["years_negative"] == 2 and look["clauses"]["years"] is False


def test_clause_4_a_year_without_rest_rows_is_none_too(looks):
    looks.update(A=PASS, B=FLAT)
    rest_three = _rows(300, "B", ZERO, years=("2020", "2021", "2022"))
    look = _verdict({"A": _rows(300, "A", NEG), "B": rest_three})["looks"]["A"]
    assert look["years"]["2023"] is None and look["years_negative"] == 3
    assert look["clauses"]["years"] is True


def test_clause_5_n_299_fails_and_300_passes(looks):
    looks.update(A=PASS, B=FLAT)
    short = _verdict({"A": _rows(299, "A", NEG), "B": _rows(300, "B", ZERO)})
    assert short["looks"]["A"]["clauses"]["n"] is False and short["candidates"] == []
    assert short["powered"] == 1 and short["verdict"] == "UNDERPOWERED"
    full = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})
    assert full["looks"]["A"]["clauses"]["n"] is True and full["verdict"] == "VETO-CANDIDATE"


def test_clause_6_q_exactly_0_10_fails(looks):
    looks.update(A=dict(PASS, p=0.05), B=FLAT)                # q_A = 0.05 * 2 / 1 = 0.10
    look = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["q"] == pytest.approx(0.10)
    assert look["clauses"]["bh"] is False and look["candidate"] is False


def test_clause_6_a_thin_look_has_no_q_and_fails(looks):
    looks.update(A=dict(PASS, ci_low=None, ci_high=None, p=None), B=FLAT)
    look = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["q"] is None and look["clauses"]["bh"] is False


def test_the_bh_family_is_this_studys_buckets_only(looks, monkeypatch):
    seen = []
    real = ea.stats.bh_qvalues

    def spy(pvalues):
        seen.append(list(pvalues))
        return real(pvalues)

    def refuse(*args, **kwargs):
        raise AssertionError("assign_qvalues is v146's family; the study never uses it")

    monkeypatch.setattr(ea.stats, "bh_qvalues", spy)
    monkeypatch.setattr(ea, "assign_qvalues", refuse)
    looks.update(A=dict(PASS, p=0.04), B=dict(FLAT, p=0.2), C=dict(FLAT, p=0.6))
    out = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO),
                    "C": _rows(300, "C", ZERO)})
    assert seen == [[0.04, 0.2, 0.6]]                          # one family, label order
    assert out["family_size"] == 3
    assert out["looks"]["A"]["q"] == pytest.approx(0.12)       # 0.04 * 3 / 1: m is 3, not 2
    assert out["looks"]["A"]["candidate"] is False


def test_a_candidate_wins_over_too_few_powered_buckets(looks):
    looks.update(A=PASS, B=FLAT)
    out = _verdict({"A": _rows(300, "A", NEG), "B": _rows(100, "B", ZERO)})
    assert out["powered"] == 1 and out["verdict"] == "VETO-CANDIDATE"


def test_no_candidate_with_two_powered_buckets_closes_the_question(looks):
    looks.update(A=dict(PASS, delta=-0.05), B=FLAT)
    out = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})
    assert out["verdict"] == "NO CANDIDATE" and out["candidates"] == []


def test_fewer_than_two_powered_buckets_is_underpowered(looks):
    looks.update(A=dict(PASS, delta=-0.05), B=FLAT)
    out = _verdict({"A": _rows(120, "A", NEG), "B": _rows(100, "B", ZERO)})
    assert out["verdict"] == "UNDERPOWERED" and out["powered"] == 0 and out["n_needed"] == 300


def test_an_empty_train_population_is_underpowered():
    out = ea.stop_width_verdict(ea.stop_width_groups([], [])["train"], seed=42)
    assert out["verdict"] == "UNDERPOWERED" and out["family_size"] == 1
    assert out["looks"]["Q1 (all)"]["exp_r"] is None
    assert out["looks"]["Q1 (all)"]["candidate"] is False


def test_end_to_end_on_real_looks_flags_the_losing_tight_bucket(monkeypatch):
    """Real ``_look`` (few resamples): tight stops lose, the rest earn."""
    monkeypatch.setattr(ea, "N_RESAMPLES", 200)
    rows = []
    for i in range(1600):
        stop_atr = 0.2 + (i % 8) * 0.1
        wobble = ((i * 37) % 11 - 5) / 50.0
        rows.append({"r": (-0.6 if stop_atr < 0.35 else 0.1) + wobble, "r_gross": 0.0,
                     "week": (dt.date(2020, 1, 6) + dt.timedelta(weeks=i % 200)).isoformat(),
                     "stop_atr": stop_atr})
    groups = ea.stop_width_groups(rows, [])
    out = ea.stop_width_verdict(groups["train"], seed=42)
    assert out["family_size"] == len(groups["labels"]) <= 4
    first = groups["labels"][0]
    assert out["looks"][first]["n"] == 400 and out["looks"][first]["delta"] < -0.5
    assert all(out["looks"][label]["p"] is not None for label in groups["labels"])
    assert out["candidates"] == [first] and out["verdict"] == "VETO-CANDIDATE"
