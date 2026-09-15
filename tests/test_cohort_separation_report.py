import pytest

from scripts.reports.cohort_separation_report import (label_separation,
                                                      feature_separation,
                                                      MIN_N_PER_GROUP,
                                                      PASS_SEPARATION_R)


def _entry(label, r, created_at="2026-10-01", **feats):
    return {"cohort_label": label, "r_realized": r, "created_at": created_at,
            "cohort_run_date": "2026-09-14", "risk_features": feats}


def test_a_plan_created_before_the_freeze_is_excluded():
    entries = [_entry("COHORT_POOR", -1.0, created_at="2026-09-01")]
    assert label_separation(entries, "2026-09-14")["n_poor"] == 0


def test_unknown_plans_are_excluded_from_both_groups():
    entries = [_entry("COHORT_UNKNOWN", -1.0)] * 10
    out = label_separation(entries, "2026-09-14")
    assert out["n_poor"] == 0 and out["n_other"] == 0


def test_verdict_is_withheld_below_the_minimum_n():
    entries = [_entry("COHORT_POOR", -1.0)] * 5 + [_entry("COHORT_TYPICAL", 1.0)] * 5
    out = label_separation(entries, "2026-09-14")
    assert out["verdict"] == "INSUFFICIENT_N"


def test_clear_separation_at_full_n_passes():
    entries = ([_entry("COHORT_POOR", -1.0)] * MIN_N_PER_GROUP
               + [_entry("COHORT_TYPICAL", 1.0)] * MIN_N_PER_GROUP)
    out = label_separation(entries, "2026-09-14")
    assert out["separation_r"] == pytest.approx(-2.0)
    assert out["verdict"] == "PASS"


def test_no_separation_at_full_n_fails():
    entries = ([_entry("COHORT_POOR", 0.0)] * MIN_N_PER_GROUP
               + [_entry("COHORT_TYPICAL", 0.0)] * MIN_N_PER_GROUP)
    out = label_separation(entries, "2026-09-14")
    assert out["separation_r"] == pytest.approx(0.0)
    assert out["verdict"] == "FAIL"
    assert PASS_SEPARATION_R < 0


def test_feature_separation_groups_by_value():
    entries = [_entry("COHORT_POOR", -1.0, session_bucket="close"),
               _entry("COHORT_TYPICAL", 1.0, session_bucket="open"),
               _entry("COHORT_TYPICAL", 1.0, session_bucket="open")]
    rows = {r["value"]: r for r in feature_separation(entries, "session_bucket")}
    assert rows["open"]["n"] == 2 and rows["open"]["expectancy_r"] == pytest.approx(1.0)
    assert rows["close"]["n"] == 1 and rows["close"]["win_rate"] == 0.0
