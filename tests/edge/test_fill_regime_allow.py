"""The pre-registered REGIME_ALLOW selection rule.

This rule was fixed in the spec before any fold ran, and its whole value is
that it cannot be reinterpreted after seeing results. These tests pin each
clause independently so a later "small tidy-up" of decide() cannot quietly
loosen it.
"""
import types

import pytest

from scripts.data.fill_regime_allow import decide, MIN_N_CELL, MIN_N_SUBFOLD, MIN_FOLD_AGREEMENT


def _trade(year, r, outcome="win"):
    return types.SimpleNamespace(entry_date=f"{year}-06-15", r_multiple=r, outcome=outcome)


def _cell(per_year):
    """{year: (count, r_multiple)} -> (pooled list, {year: list})."""
    pooled, by_fold = [], {}
    for year, (count, r) in per_year.items():
        trades = [_trade(year, r) for _ in range(count)]
        by_fold[year] = trades
        pooled.extend(trades)
    return pooled, by_fold


def _run(per_year, strategy="RSI", regime="bull_quiet"):
    pooled, by_fold = _cell(per_year)
    return decide({(strategy, regime): pooled},
                  {(strategy, regime): by_fold},
                  [strategy])


def _denied(allow, strategy, regime):
    return strategy in allow and regime not in allow[strategy]


# --- the three clauses, pinned independently --------------------------------

def test_denies_when_all_three_clauses_hold():
    allow, _rows = _run({"2020": (40, -0.5), "2021": (40, -0.5),
                         "2022": (40, -0.5), "2023": (40, +0.1)})
    assert _denied(allow, "RSI", "bull_quiet")


def test_does_not_deny_on_thin_pooled_sample():
    # negative and consistent, but under the pooled N floor
    n = (MIN_N_CELL - 1) // 4
    allow, _rows = _run({y: (n, -0.5) for y in ("2020", "2021", "2022", "2023")})
    assert allow == {}, "a cell under MIN_N_CELL must never be denied"


def test_does_not_deny_a_positive_expectancy_cell():
    allow, _rows = _run({y: (40, +0.5) for y in ("2020", "2021", "2022", "2023")})
    assert allow == {}


def test_does_not_deny_on_two_of_four_folds():
    allow, _rows = _run({"2020": (40, -0.5), "2021": (40, -0.5),
                         "2022": (40, +0.9), "2023": (40, +0.9)})
    # pooled expectancy is positive here AND only 2 folds negative
    assert allow == {}


def test_fold_agreement_needs_the_full_threshold():
    """Exactly MIN_FOLD_AGREEMENT-1 negative folds must not deny."""
    years = ["2020", "2021", "2022", "2023"]
    per_year = {y: (40, -0.5) for y in years[:MIN_FOLD_AGREEMENT - 1]}
    per_year.update({y: (40, -0.01) for y in years[MIN_FOLD_AGREEMENT - 1:]})
    # make the shortfall folds fail the N floor instead of the sign test
    for y in years[MIN_FOLD_AGREEMENT - 1:]:
        per_year[y] = (MIN_N_SUBFOLD - 1, -0.5)

    allow, rows = _run(per_year)
    row = rows[0]
    assert row["folds_negative"] == MIN_FOLD_AGREEMENT - 1
    assert allow == {}


def test_a_thin_subfold_counts_as_not_negative():
    """The clause that stops one populated year clearing '3 of 4'.

    Without it, a cell whose only real data is 2021 could be denied on a
    single year's evidence.
    """
    allow, rows = _run({"2020": (1, -0.9), "2021": (200, -0.9),
                        "2022": (1, -0.9), "2023": (1, -0.9)})

    assert rows[0]["folds_negative"] == 1, "thin folds must not count toward agreement"
    assert allow == {}


# --- table shape ------------------------------------------------------------

def test_a_strategy_with_no_denials_is_absent_from_the_table():
    """Absent means unrestricted; an empty tuple would mean silenced.

    apply_regime_gate treats a missing key as "no restriction" but an empty
    allow-tuple as "nothing permitted", which would mute the strategy
    entirely -- the opposite of the intended default-allow.
    """
    allow, _rows = _run({y: (40, +0.5) for y in ("2020", "2021", "2022", "2023")})
    assert "RSI" not in allow


def test_denied_strategy_lists_the_surviving_regimes():
    from swingbot.core.edge.regime2 import REGIMES

    allow, _rows = _run({y: (40, -0.5) for y in ("2020", "2021", "2022", "2023")},
                        regime="bear_volatile")

    assert allow["RSI"] == tuple(r for r in REGIMES if r != "bear_volatile")
    assert "bear_volatile" not in allow["RSI"]


def test_empty_evidence_denies_nothing():
    allow, rows = decide({}, {}, ["RSI"])
    assert allow == {}
    assert all(r["n"] == 0 and not r["deny"] for r in rows)


def test_every_strategy_regime_pair_is_reported():
    from swingbot.core.edge.regime2 import REGIMES

    _allow, rows = decide({}, {}, ["RSI", "MACD"])
    assert len(rows) == 2 * len(REGIMES)


# --- the guard that keeps the measurement honest ----------------------------

def test_the_run_refuses_to_measure_through_its_own_gate(monkeypatch, capsys):
    from scripts.data import fill_regime_allow

    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", True, raising=False)
    rc = fill_regime_allow.main([])

    assert rc == 2
    assert "REFUSING" in capsys.readouterr().out
