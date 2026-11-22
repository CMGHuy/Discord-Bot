"""v238: the replication ladder's rules (v230 spec Part B)."""
from dataclasses import asdict
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import ladder
from swingbot.core.backtesting.screen.ideas import IDEAS

FAST = {"n_resamples": 300, "seed": 42}
H, F, U = ladder.HOLD, ladder.FAIL, ladder.UNDERPOWERED


def _events(rs, *, ticker="AAA", r_null=None):
    """One event per business day from 2017-03-01 (many ISO weeks)."""
    days = pd.bdate_range("2017-03-01", periods=len(rs) + 1).strftime("%Y-%m-%d")
    return [ladder.LadderEvent(ticker, days[i], days[i + 1], days[i + 1], float(r),
                               float(r), "target", r_null=r_null)
            for i, r in enumerate(rs)]


def _row(row_id, verdict, instrument="ladder-v1"):
    return {"id": row_id, "verdict": verdict, "instrument": instrument}


def test_vocabulary_windows_and_ids():
    assert ladder.LADDER_INSTRUMENT in stats.INSTRUMENTS
    assert all(label in stats.VERDICTS for label in (H, F, U))
    assert ladder.UNAVAILABLE == "LADDER-UNAVAILABLE" not in stats.VERDICTS
    assert ladder.INPUT_INSTRUMENTS == ("screen-v1", "screen-v2")
    assert ladder.NULL_VERSION == "v1" and "v230 placebo" in ladder.BIASED_NULL_NOTE
    assert (ladder.STORE_START, ladder.EVENT_START, ladder.READ_END) == (
        "2016-01-04", "2017-03-01", "2020-12-31")
    assert ladder.RUNGS == (1, 2, 3, 4) and set(ladder.RUNG_NAMES) == set(ladder.RUNGS)
    assert ladder.ladder_id("turtle_soup", 3) == "ladder-turtle_soup-r3"
    for bad in (("turtle_soup", 5), (" ", 1)):
        with pytest.raises(ValueError):
            ladder.ladder_id(*bad)
    event = _events([0.5])[0]
    assert ladder.LadderEvent(**asdict(event)) == event and event.key == ("AAA", event.signal_date)


@pytest.mark.parametrize("n, lo, rung, delta, expected", [
    (299, 0.5, 2, None, U), (300, 0.5, 2, None, H), (300, 0.0, 2, None, F),
    (300, 1e-12, 2, None, H), (300, None, 2, None, F), (300, 0.5, 1, 0.01, H),
    (300, 0.5, 1, 0.0, F), (300, 0.5, 1, None, F), (299, -1.0, 1, None, U),
])
def test_hold_verdict_boundaries(n, lo, rung, delta, expected):
    assert ladder.hold_verdict(n, lo, rung=rung, delta=delta) == expected


def test_hold_at_299_and_300_events():
    assert ladder.hold(_events([0.5] * 299), rung=2, **FAST).verdict == U
    result = ladder.hold(_events([0.5] * 300), rung=2, **FAST)
    assert (result.verdict, result.n, result.p, result.delta_null) == (H, 300, 0.0, None)
    assert result.mean == pytest.approx(0.5) and result.lo == pytest.approx(0.5)


def test_hold_fails_when_the_interval_straddles_zero_and_is_seeded():
    events = _events([1.0, -1.0] * 200)
    result = ladder.hold(events, rung=3, **FAST)
    assert result.verdict == F and result.lo < 0.0 < result.hi and 0.0 < result.p < 1.0
    assert ladder.hold(events, rung=3, **FAST) == result
    assert ladder.hold([], rung=2, **FAST) == ladder.HoldResult(U, 0, None, None, None, None, None)


def test_rung_one_needs_a_positive_delta_against_the_null():
    beats = ladder.hold(_events([0.5] * 300, r_null=0.2), rung=1, **FAST)
    assert beats.verdict == H and beats.delta_null == pytest.approx(0.3)
    loses = ladder.hold(_events([0.5] * 300, r_null=0.6), rung=1, **FAST)
    assert loses.verdict == F and loses.delta_null == pytest.approx(-0.1)
    missing = ladder.hold(_events([0.5] * 300), rung=1, **FAST)
    assert missing.verdict == F and missing.delta_null is None


def test_paired_difference_on_shared_events_only():
    upper = _events([0.5] * 50)
    lower = [ladder.LadderEvent(e.ticker, e.signal_date, e.entry_date, e.exit_date,
                                e.r - 0.2, e.gross_r, e.outcome) for e in upper[:40]]
    diff = ladder.paired_difference(upper, lower, **FAST)
    assert diff.n == 40 and diff.mean == pytest.approx(-0.2) and diff.wholly_below_zero
    same = ladder.paired_difference(upper, upper, **FAST)
    assert same.mean == 0.0 and not same.wholly_below_zero
    none = ladder.paired_difference(upper, _events([0.5], ticker="BBB"), **FAST)
    assert (none.n, none.mean, none.wholly_below_zero) == (0, None, False)
    with pytest.raises(ValueError, match="duplicate"):
        ladder.paired_difference(upper + upper, lower, **FAST)


def test_input_rows():
    v1 = [_row("screen-demo", "SCREEN-PASS", "screen-v1")]
    assert ladder.input_refusal("demo", v1) is None
    assert ladder.input_row("demo", v1)["instrument"] == "screen-v1"
    assert ladder.input_refusal("demo", [_row("screen2-demo", "SCREEN-PASS", "screen-v2")]) is None
    assert "no governing SCREEN-PASS" in ladder.input_refusal("demo", [])
    assert ladder.input_refusal("demo", [_row("screen-demo", "SCREEN-FAIL", "screen-v1")])
    assert ladder.input_refusal("demo", [_row("screen-demo", "SCREEN-PASS", "v1")])
    superseded = v1 + [_row("screen2-demo", "SCREEN-FAIL", "screen-v2")]
    assert ladder.input_row("demo", superseded) is None


def test_rung_order_and_one_shot_per_id():
    assert ladder.rung_refusal("demo", 1, []) is None
    assert "needs LADDER-HOLD" in ladder.rung_refusal("demo", 2, [])
    held = [_row("ladder-demo-r1", H)]
    assert ladder.rung_refusal("demo", 2, held) is None
    assert ladder.rung_refusal("demo", 3, held) is not None
    assert "LADDER-FAIL" in ladder.rung_refusal("demo", 2, [_row("ladder-demo-r1", F)])
    assert "one shot per id" in ladder.rung_refusal("demo", 1, held)
    assert "not one of" in ladder.rung_refusal("demo", 7, held)


def test_shape_refusal_for_rungs_two_to_four():
    assert all(ladder.shape_refusal(IDEAS["uptrend_pullback"], r) is None for r in ladder.RUNGS)
    level = IDEAS["range_breakdown_stop"]
    assert ladder.shape_refusal(level, 1) is None
    assert ladder.shape_refusal(level, 2).startswith(
        "LADDER-UNAVAILABLE: rung 2 needs the fixed next-open shape")
    assert ladder.shape_refusal(SimpleNamespace(name="t", race_shape="trail", entry="next_open"), 3)


def test_context_refusal_and_membership_coverage(tmp_path):
    for name in ("SPY", "TLT", "AAA"):
        (tmp_path / f"{name}.csv").write_text("Date,Open,High,Low,Close,Volume\n", encoding="utf-8")
    refusal = ladder.context_refusal(IDEAS["dollar_drop"], tmp_path)
    assert refusal.startswith("LADDER-UNAVAILABLE") and "UUP" in refusal
    assert ladder.context_refusal(IDEAS["bond_spike_rebound"], tmp_path) is None
    assert ladder.context_refusal(IDEAS["uptrend_pullback"], tmp_path) is None
    assert ladder.membership_coverage(["CCC", "AAA", "SPY", "AAA"], tmp_path) == {
        "members": 3, "in_store": 2, "missing_count": 1, "missing": ["CCC"]}


OK = ladder.PairedDiff(400, -0.05, -0.12, 0.02, False)
BAD = ladder.PairedDiff(400, -0.20, -0.30, -0.10, True)


@pytest.mark.parametrize("holds, diff, expected", [
    ({}, None, "pending"), ({1: F}, None, "non_replication"), ({1: U}, None, "non_replication"),
    ({1: H}, None, "pending"), ({1: H, 2: F}, None, "partner_open"),
    ({1: H, 2: H}, None, "pending"), ({1: H, 2: H, 3: F}, None, "orderable_shape"),
    ({1: H, 2: H, 3: H}, None, "pending"), ({1: H, 2: H, 3: H, 4: U}, None, "orderable_shape"),
    ({1: H, 2: H, 3: H, 4: H}, BAD, "orderable_shape"), ({1: H, 2: H, 3: H, 4: H}, OK, "bot_shape"),
])
def test_next_step_table(holds, diff, expected):
    assert ladder.next_step(holds, diff) == expected and expected in ladder.NEXT_STEPS


def test_next_step_needs_the_rung_four_difference_and_known_labels():
    with pytest.raises(ValueError, match="paired difference"):
        ladder.next_step({1: H, 2: H, 3: H, 4: H}, None)
    for bad in ({1: "SCREEN-PASS"}, {5: H}):
        with pytest.raises(ValueError):
            ladder.next_step(bad, None)
