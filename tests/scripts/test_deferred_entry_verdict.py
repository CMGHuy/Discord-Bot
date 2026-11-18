"""v229 frozen rule, forward window and verdict guard."""
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

from deferred_entry import verdict  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402

T0 = pd.Timestamp("2026-11-19T15:00:00+00:00")             # a Thursday
CAL = {"calibrated": True}
UNCAL = {"calibrated": False}


def _delta(arm, mean, lower, p):
    return {"arm": arm, "n": 400, "weeks": 12, "mean": mean, "lower": lower, "p": p}


def test_frozen_is_the_pre_registered_rule():
    assert verdict.FROZEN == {"defer_et": "15:30", "hold_sessions": 5, "window_weeks": 12,
                              "floor_r": 0.10, "lower_pct": 2.5, "calibration_min": 0.80,
                              "min_pairs": 300, "min_weeks": 10, "resamples": 10000, "seed": 42,
                              "be_fraction": 0.5, "deferred_entry_bps_mult": 2}
    assert verdict.LEDGER_ID == "v229-deferred-entry"


def test_rule_hash_is_sha256_of_the_sorted_rule(monkeypatch):
    expected = hashlib.sha256(json.dumps(verdict.FROZEN, sort_keys=True).encode()).hexdigest()[:16]
    assert verdict.rule_hash() == expected and len(expected) == 16
    monkeypatch.setitem(verdict.FROZEN, "floor_r", 0.2)
    assert verdict.rule_hash() != expected


@pytest.mark.parametrize("t0, start", [
    ("2026-11-19T15:00:00+00:00", dt.date(2026, 11, 23)),   # Thursday -> next Monday
    ("2026-11-23T14:00:00+00:00", dt.date(2026, 11, 30)),   # Monday 09:00 ET: its week is not complete
    ("2026-11-23T03:00:00+00:00", dt.date(2026, 11, 23)),   # Sunday 22:00 ET: ET date decides
])
def test_forward_window_is_twelve_complete_iso_weeks(t0, start):
    first, last = verdict.forward_window(pd.Timestamp(t0))
    assert first == start and first.weekday() == 0
    assert last == start + dt.timedelta(days=83) and last.weekday() == 6


def test_a_naive_t0_is_refused():
    with pytest.raises(ValueError, match="UTC"):
        verdict.forward_window(pd.Timestamp("2026-11-19T15:00:00"))


@pytest.mark.parametrize("day, expected", [
    (dt.date(2026, 11, 18), "exploratory"), (dt.date(2026, 11, 19), "after"),
    (dt.date(2026, 11, 20), "after"), (dt.date(2026, 11, 23), "forward"),
    (dt.date(2027, 2, 14), "forward"), (dt.date(2027, 2, 15), "after"),
])
def test_phase_by_entry_date(day, expected):
    assert verdict.phase(day, T0) == expected


def test_verdict_opens_the_day_after_the_fifth_session_past_the_window():
    # window ends Sun 2027-02-14; last session Fri 02-12; 02-15 is Presidents' Day;
    # sessions 02-16, 17, 18, 19, 22 -> the fifth is 02-22
    assert verdict.verdict_open_date(T0) == dt.date(2027, 2, 23)


def _pair(h=None):
    return {"trade_id": "t-1", "rule_hash": h or verdict.rule_hash()}


def test_guard_refuses_before_the_open_date_and_passes_on_it():
    with pytest.raises(verdict.VerdictRefused, match="2027-02-23"):
        verdict.guard(today=dt.date(2027, 2, 22), t0=T0, ledger_rows=[], pairs=[_pair()])
    verdict.guard(today=dt.date(2027, 2, 23), t0=T0, ledger_rows=[], pairs=[_pair()])


def test_guard_refuses_a_second_verdict():
    rows = [{"id": "v226-stop-width"}, {"id": verdict.LEDGER_ID}]
    with pytest.raises(verdict.VerdictRefused, match="already"):
        verdict.guard(today=dt.date(2027, 3, 1), t0=T0, ledger_rows=rows, pairs=[])


def test_guard_refuses_a_log_written_under_another_rule():
    with pytest.raises(verdict.VerdictRefused, match="rule"):
        verdict.guard(today=dt.date(2027, 3, 1), t0=T0, ledger_rows=[],
                      pairs=[_pair(), _pair("ffffffffffffffff")])
    verdict.assert_one_rule([])                              # an empty log carries no other rule


@pytest.mark.parametrize("mean, lower, calibrated, expected", [
    (0.10, 0.01, True, "PASS"), (0.0999, 0.01, True, "NO-LIFT"), (0.30, 0.0, True, "NO-LIFT"),
    (0.30, None, True, "NO-LIFT"), (None, None, True, "NO-LIFT"), (0.50, 0.20, False, "UNCALIBRATED"),
])
def test_arm_verdict(mean, lower, calibrated, expected):
    assert verdict.arm_verdict(_delta("A", mean, lower, 0.01), calibrated) == expected


def test_one_passing_arm_passes_the_study_with_a_doubled_p():
    out = verdict.study_verdict(deltas={"A": _delta("A", 0.31234, 0.05, 0.004),
                                        "B": _delta("B", 0.08, -0.02, 0.2)},
                                calibration=CAL, n_pairs=812, weeks=12)
    assert out == {"study": "PASS", "arms": {"A": "PASS", "B": "NO-LIFT"},
                   "ledger": {"verdict": "PASS", "n": 812, "exp_r": 0.3123, "p": 0.008}}


def test_the_doubled_p_is_capped_at_one():
    out = verdict.study_verdict(deltas={"A": _delta("A", -0.1, -0.3, 0.7), "B": _delta("B", -0.2, -0.4, 0.9)},
                                calibration=CAL, n_pairs=400, weeks=12)
    assert out["study"] == "NO-LIFT" and out["ledger"]["p"] == 1.0 and out["ledger"]["exp_r"] == -0.1


@pytest.mark.parametrize("n_pairs, weeks", [(299, 12), (400, 9)])
def test_underpowered_closes_like_a_fail_and_precedes_calibration(n_pairs, weeks):
    deltas = {"A": _delta("A", 0.5, 0.2, 0.001), "B": _delta("B", 0.4, 0.1, 0.01)}
    out = verdict.study_verdict(deltas=deltas, calibration=UNCAL, n_pairs=n_pairs, weeks=weeks)
    assert out["study"] == "UNDERPOWERED" and out["arms"] == {"A": "UNDERPOWERED", "B": "UNDERPOWERED"}
    assert out["ledger"]["verdict"] == "NO-LIFT" and out["ledger"]["p"] == 0.002


def test_uncalibrated_is_inconclusive_with_no_estimate():
    deltas = {"A": _delta("A", 0.5, 0.2, 0.001), "B": _delta("B", 0.4, 0.1, 0.01)}
    out = verdict.study_verdict(deltas=deltas, calibration=UNCAL, n_pairs=400, weeks=12)
    assert out == {"study": "UNCALIBRATED", "arms": {"A": "UNCALIBRATED", "B": "UNCALIBRATED"},
                   "ledger": {"verdict": "INCONCLUSIVE", "n": 400, "exp_r": None, "p": None}}


def test_no_p_on_either_arm_leaves_the_ledger_p_null():
    deltas = {"A": _delta("A", None, None, None), "B": _delta("B", None, None, None)}
    out = verdict.study_verdict(deltas=deltas, calibration=CAL, n_pairs=0, weeks=0)
    assert out["ledger"] == {"verdict": "NO-LIFT", "n": 0, "exp_r": None, "p": None}


def test_exploratory_close_only_when_uncalibrated():
    assert verdict.exploratory_close(CAL, 350) is None
    assert verdict.exploratory_close(UNCAL, 350) == {
        "study": "UNCALIBRATED", "arms": {"A": "UNCALIBRATED", "B": "UNCALIBRATED"},
        "ledger": {"verdict": "INCONCLUSIVE", "n": 350, "exp_r": None, "p": None}}


@pytest.mark.parametrize("ledger", [
    {"verdict": "PASS", "n": 812, "exp_r": 0.3123, "p": 0.008},
    {"verdict": "NO-LIFT", "n": 0, "exp_r": None, "p": None},
    {"verdict": "INCONCLUSIVE", "n": 350, "exp_r": None, "p": None},
])
def test_every_ledger_mapping_is_a_valid_ledger_row(ledger):
    stats.validate_ledger_row({"id": verdict.LEDGER_ID, "date": "2027-02-23", "hypothesis": "h",
                               "instrument": "v1", "record": "docs/x.md", **ledger})


STAMP = {"slippage_bps": 5.0, "commission_r": 0.01, "be_fraction": 0.5}


def test_assert_same_frictions_accepts_one_stamp_and_ignores_unstamped_rows():
    verdict.assert_same_frictions([{"frictions": STAMP}, {"frictions": dict(reversed(list(STAMP.items())))}, {}])
    verdict.assert_same_frictions([{}, {"frictions": None}], STAMP)
    verdict.assert_same_frictions([{"frictions": STAMP}], STAMP)


def test_assert_same_frictions_refuses_a_mixed_log_or_a_changed_current_stamp():
    other = {**STAMP, "slippage_bps": 9.0}
    with pytest.raises(verdict.VerdictRefused, match="frictions"):
        verdict.assert_same_frictions([{"frictions": STAMP}, {"frictions": other}])
    with pytest.raises(verdict.VerdictRefused, match="frictions"):
        verdict.assert_same_frictions([{"frictions": STAMP}], other)


def test_assert_one_rule_also_refuses_mixed_frictions():
    other = {**STAMP, "commission_r": 0.02}
    with pytest.raises(verdict.VerdictRefused, match="frictions"):
        verdict.assert_one_rule([{"rule_hash": verdict.rule_hash(), "frictions": STAMP},
                                 {"rule_hash": verdict.rule_hash(), "frictions": other}])


def test_the_frozen_rule_hash_is_unchanged_by_the_frictions_stamp():
    assert verdict.rule_hash() == "8bbaaa9781535813"
