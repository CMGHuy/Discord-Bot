"""v214: the golden capture serialises an edge-mode Verdict over its original
nine fields (so the v182 long golden stays byte-identical) but never hides
avoid-mode data: an avoid Verdict, or one carrying a non-default v214 field,
serialises all twelve."""
from swingbot.core.backtesting.screen import verdict
from tests.backtesting.screen import long_golden

NINE = ("verdict", "n", "delta_exp_r", "ci_low", "ci_high", "p", "years_positive",
        "per_year", "clauses")
TWELVE = NINE + ("mode", "years_negative", "control")


def _verdict(**extra):
    return verdict.Verdict("SCREEN-FAIL", 412, 0.03, -0.01, 0.07, 0.2, 6, {}, {}, **extra)


def test_an_edge_verdict_serialises_over_its_original_nine_fields():
    assert tuple(long_golden._exact(_verdict())) == NINE


def test_an_avoid_verdict_serialises_all_twelve_fields():
    arm = verdict.ControlArm(300, -0.25, -0.3, -0.2, {})
    out = long_golden._exact(_verdict(mode="avoid", years_negative=8, control=arm))
    assert set(out) == set(TWELVE)
    assert out["mode"] == "avoid" and out["years_negative"] == 8
    assert out["control"]["n"] == 300


def test_an_edge_verdict_with_a_non_default_v214_field_is_not_trimmed():
    assert set(long_golden._exact(_verdict(years_negative=3))) == set(TWELVE)
