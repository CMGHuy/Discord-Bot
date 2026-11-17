"""v229 results doc and JSON payload."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

from deferred_entry import report, verdict  # noqa: E402


def _leg(arm, r, *, taken=True, outcome="loss", gap=False):
    return {"arm": arm, "taken": taken, "fill": 100.0, "stop": 98.0, "tp1": 104.0, "outcome": outcome,
            "r_net": r, "r_gross": r + 0.05, "exit_ts": None, "gap_stop": gap}


def _pair(tid, day, *, c=-1.0, a=1.0, b_taken=True, bucket="open", expired=False, event=False):
    return {"trade_id": tid, "entry_date": day, "bucket": bucket, "direction": "bullish",
            "arms": {"C": _leg("C", c), "A": _leg("A", a, outcome="win", gap=True),
                     "B": _leg("B", a if b_taken else 0.0, taken=b_taken, outcome="win")},
            "live": {"reason": "loss", "outcome": "loss", "r_realized": -1.0},
            "tradeability": {"fill_vs_entry_r": 0.5, "fill_above_entry": True, "shifted_stop_above_day_low": True,
                             "day_low": 98.5, "day_low_vs_stop_r": 0.25, "price_1530_vs_entry_r": 0.5,
                             "first_gap_r": {"C": -0.2, "A": 0.1, "B": None},
                             "bar_1530": {"volume": 1000.0, "range_r": 0.3, "open_vs_last_close_r": 0.0},
                             "plan_expired": expired, "sessions_since_plan": 1, "entry_bar_stopout": False,
                             "earnings_after_close": None, "monthly_opex": False, "fomc": event, "event_day": event}}


def _payload(pairs, phase="exploratory", **kw):
    args = dict(phase=phase, t0="2026-11-19T15:00:00+00:00", pairs=pairs,
                bearish=[_pair("s-1", "2026-11-03")], funnel={"eligible": len(pairs), "no_coverage": 0},
                close_bucket={"n": 35, "exp_r": 0.672}, archive_last_bar="2026-11-18T20:55:00+00:00",
                git_sha="abc1234")
    args.update(kw)
    return report.build_payload(**args)


PAIRS = [_pair("t-1", "2026-11-02"), _pair("t-2", "2026-11-09", b_taken=False, bucket="midday", expired=True),
         _pair("t-3", "2026-11-10", c=0.5, a=-1.0, event=True)]


def test_payload_is_json_serialisable_and_records_its_provenance():
    payload = _payload(PAIRS)
    json.dumps(payload, allow_nan=False)
    assert payload["rule_hash"] == verdict.rule_hash() and payload["frozen"] == verdict.FROZEN
    assert payload["archive_last_bar"] == "2026-11-18T20:55:00+00:00" and payload["git_sha"] == "abc1234"
    assert payload["buckets"] == {"open": 2, "midday": 1} and payload["verdict"] is None
    assert payload["arms"]["B"]["taken"] == 2 and payload["skips"]["skipped"] == 1
    assert payload["deltas"]["A"]["weeks"] == 2 and payload["b_over_taken"]["n"] == 2
    assert payload["close_bucket"] == {"n": 35, "exp_r": 0.672}
    assert any("no runner" in line for line in payload["disclosures"])


def test_a_missing_git_sha_is_recorded_as_unknown():
    assert _payload(PAIRS, git_sha=None)["git_sha"] == "unknown"


def test_tradeability_summary_counts_and_means():
    out = report.tradeability_summary(PAIRS)
    assert out["count_plan_expired"] == 1 and out["count_event_day"] == 1
    assert out["count_shifted_stop_above_day_low"] == 3 and out["count_earnings_after_close"] == 0
    assert out["mean_fill_vs_entry_r"] == pytest.approx(0.5)
    assert out["first_gap_r"] == {"C": pytest.approx(-0.2), "A": pytest.approx(0.1), "B": None}
    assert out["gap_through_stop"] == {"C": 0, "A": 3, "B": 0}
    assert out["bar_1530_median"]["volume"] == pytest.approx(1000.0)


def test_bearish_pairs_are_a_disclosure_with_their_own_summary():
    bearish = _payload(PAIRS)["bearish"]
    assert bearish["n"] == 1 and bearish["d_a"] == pytest.approx(2.0)
    assert bearish["arms"]["C"]["n"] == 1


@pytest.mark.parametrize("phase, calibrated, study, expected", [
    ("exploratory", True, None, "EXPLORATORY (no verdict)"),
    ("exploratory", False, None, "EXPLORATORY (no verdict) -- UNCALIBRATED: the forward read is not started"),
    ("forward", True, "PASS", "VERDICT: PASS"),
    ("forward", False, "UNDERPOWERED", "VERDICT: UNDERPOWERED"),
    ("forward", False, None, "UNCALIBRATED (no verdict)"),
    ("forward", True, None, "FORWARD (no verdict yet)"),
])
def test_label(phase, calibrated, study, expected):
    payload = {"phase": phase, "calibration": {"calibrated": calibrated},
               "verdict": {"study": study} if study else None}
    assert report.label(payload) == expected


def test_markdown_carries_every_section_and_the_disclosures():
    text = report.render_markdown(_payload(PAIRS))
    for needle in ("# v229 deferred-entry counterfactual: exploratory read", "EXPLORATORY (no verdict)",
                   "abc1234", verdict.rule_hash(), "no runner", "## Population funnel", "## Arms",
                   "| C |", "## Deltas", "d_B over the plans B took", "## Calibration",
                   "| sim \\ live | loss | scratch | win |", "## Per week", "2026-W45", "## Splits",
                   "## Arm B skips", "## Tradeability", "## Context", "+0.672", "## Bearish disclosure"):
        assert needle in text, needle


def test_markdown_renders_a_verdict_and_missing_values():
    payload = _payload(PAIRS[:1], phase="forward")
    payload["verdict"] = {"study": "UNDERPOWERED", "arms": {"A": "UNDERPOWERED", "B": "UNDERPOWERED"},
                          "ledger": {"verdict": "NO-LIFT", "n": 1, "exp_r": None, "p": None}}
    text = report.render_markdown(payload)
    assert "VERDICT: UNDERPOWERED" in text and "## Verdict" in text and "NO-LIFT" in text
    assert "n/a" in text                                   # one week: no bound, no p


def test_an_empty_read_still_renders():
    text = report.render_markdown(_payload([], bearish=[]))
    assert "## Arms" in text and "n/a" in text
