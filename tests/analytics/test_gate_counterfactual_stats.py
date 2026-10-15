"""v147 V147-13: the gate-counterfactual verdict statistics."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from swingbot.core.analytics import gate_counterfactual_report as gcr

REPO = Path(__file__).resolve().parents[2]


def gate_row(**fields) -> dict:
    """The shared gate-row shape (index), built locally so V147-13 does not wait on V147-4."""
    row = {"planned_loss_pct": None, "dollar_risk": None, "in_sample": False, **fields}
    row["entry_date"] = row["signal_date"]
    return row


@pytest.fixture(autouse=True)
def _fast_bootstrap(monkeypatch):
    monkeypatch.setattr(gcr, "BOOTSTRAP_RESAMPLES", 600)


def _row(arm="blocked", *, gate="rs", reason="rs_blocked", ticker="AAPL", day="2024-01-08",
         status="filled", r=0.5, win=True, horizon="2w", population="live", margin=None,
         expiry_bars=5, strategy="Fibonacci", direction="bearish", source="strategy"):
    filled = status == "filled"
    return gate_row(population=population, arm=arm, source=source, ticker=ticker, strategy=strategy,
                    horizon=horizon, direction=direction, signal_date=day, gate=gate,
                    reason=reason if arm == "blocked" else None, margin=margin, cf_status=status,
                    cf_r=r if filled else None, win=win if filled else None, expiry_bars=expiry_bars)


def _weekly(arm, rs, *, start="2024-01-08"):
    """One filled row per ISO week (distinct tickers, so nothing collapses)."""
    first = dt.date.fromisoformat(start)
    return [_row(arm, ticker=f"T{i}", day=(first + dt.timedelta(weeks=i)).isoformat(), r=r, win=r > 0)
            for i, r in enumerate(rs)]


def test_frozen_constants():
    assert (gcr.VERDICT_FLOOR, gcr.Q_MAX, gcr.BOOTSTRAP_SEED) == (30, 0.10, 42)
    assert gcr.NEAR_MISS_BANDS == {"rs": 5.0, "risk_cap": 0.5}
    assert gcr.CELLS == (("rs", "live"), ("risk_cap", "live"), ("compression", "live"),
                         ("risk_cap", "train"), ("compression", "train"))
    assert gcr.VERDICTS == ("GATE EARNS", "GATE COSTS", "INCONCLUSIVE", "WAITING")


def test_the_pre_registered_resample_count_is_ten_thousand():
    # the autouse fixture patches the attribute down; the source keeps the frozen value
    import inspect
    assert "BOOTSTRAP_RESAMPLES = 10_000" in inspect.getsource(gcr)


@pytest.mark.parametrize("draws, expected", [
    ([-1.0, 1.0, 2.0, 3.0], 0.8),            # tail = min(1, 3) + 1 = 2 -> 2 * 2 / 5
    ([0.5] * 9, 0.2),                         # tail = 0 + 1 -> 2 / 10
    ([0.0, 0.0, 0.0], 1.0),                   # zeros count on both sides; capped at 1
])
def test_two_sided_p_is_v146s_plus_one_corrected_formula(draws, expected):
    assert gcr.two_sided_bootstrap_p(draws) == pytest.approx(expected)


def test_p_refuses_an_empty_draw_set():
    with pytest.raises(ValueError):
        gcr.two_sided_bootstrap_p([])


def test_one_copy_of_the_p_formula():
    hits = [p for p in (REPO / "swingbot").rglob("*.py") if "2.0 * tail" in p.read_text(encoding="utf-8")]
    assert len(hits) == 1, hits


@pytest.mark.parametrize("gate, reason, expected", [
    ("rs", "rs_blocked", "rs"), ("compression", "earnings_unknown", "compression"),
    ("plan_rejected", "risk_cap", "risk_cap"), ("plan_rejected", "no_qualifying_target", "no_qualifying_target"),
    ("plan_rejected", None, "risk_cap"),     # a taken confluence row belongs to the risk_cap cell
    ("plan_rejected", "headroom", "other"),  # v135's gate: never pooled into risk_cap
    ("plan_rejected", "stop_beyond_confluence_ceiling", "other"),   # v139
    ("plan_rejected", "risk_sizing", "other"),                      # v139
])
def test_cell_key(gate, reason, expected):
    assert gcr.cell_key({"gate": gate, "reason": reason}) == expected


def test_consecutive_day_blocks_of_one_setup_collapse_to_the_earliest_row():
    rows = [_row(day=d, r=r) for d, r in (("2024-01-10", -1.0), ("2024-01-08", 0.4), ("2024-01-09", 2.0))]
    (setup,) = gcr.distinct_setups(rows)
    assert setup["signal_date"] == "2024-01-08" and setup["cf_r"] == 0.4


def test_a_block_past_the_pending_window_is_a_new_setup():
    rows = [_row(day="2024-01-08", expiry_bars=3), _row(day="2024-01-11", expiry_bars=3),   # 3 sessions: same
            _row(day="2024-01-12", expiry_bars=3)]                                           # 4 sessions: new
    assert [r["signal_date"] for r in gcr.distinct_setups(rows)] == ["2024-01-08", "2024-01-12"]


def test_the_window_counts_nyse_sessions_not_calendar_days():
    # 2024-01-12 (Fri) -> 2024-01-19 (Fri) spans the MLK holiday: 4 sessions, inside a 5-bar window
    rows = [_row(day="2024-01-12"), _row(day="2024-01-19")]
    assert len(gcr.distinct_setups(rows)) == 1


def test_an_unknown_window_uses_the_default_expiry():
    rows = [_row(day="2024-02-05", expiry_bars=None), _row(day="2024-02-12", expiry_bars=None)]   # 5 sessions
    assert len(gcr.distinct_setups(rows)) == 1


@pytest.mark.parametrize("change", [{"horizon": "4w"}, {"ticker": "MSFT"}, {"strategy": "RSI"},
                                    {"population": "train", "gate": "plan_rejected", "reason": "risk_cap"},
                                    {"arm": "taken"}, {"direction": "bullish"}])
def test_different_setup_keys_never_collapse(change):
    assert len(gcr.distinct_setups([_row(), _row(**change)])) == 2


def test_arm_stats_apply_the_one_population_rule():
    rows = [_row(r=1.0, win=True), _row(r=-1.0, win=False), _row(status="no-fill"),
            _row(status="no-plan"), _row(status="no-data")]
    stats = gcr.arm_stats(rows)
    assert stats == {"n": 5, "filled_n": 2, "no_fill_n": 1, "no_plan_n": 1, "no_data_n": 1,
                     "fill_rate": pytest.approx(2 / 3), "exp_r": pytest.approx(0.0),
                     "win_rate": pytest.approx(0.5)}


def test_arm_stats_of_an_arm_with_nothing_filled():
    stats = gcr.arm_stats([_row(status="no-fill")])
    assert (stats["exp_r"], stats["win_rate"], stats["fill_rate"]) == (None, None, 0.0)
    assert gcr.arm_stats([])["fill_rate"] is None


def test_a_reading_needs_a_filled_row_in_both_arms():
    assert gcr.difference_reading(_weekly("blocked", [1.0] * 3), []) is None
    assert gcr.difference_reading([_row(status="no-fill")], _weekly("taken", [1.0])) is None


def test_the_reading_is_the_seeded_blocked_minus_taken_difference():
    blocked, taken = _weekly("blocked", [0.5, -0.2, 1.0, 0.1]), _weekly("taken", [0.1, 0.3, -0.4, 0.2])
    first = gcr.difference_reading(blocked, taken)
    assert first == gcr.difference_reading(blocked, taken)
    assert first["difference"] == pytest.approx(0.35 - 0.05)
    assert first["ci_low"] <= first["difference"] <= first["ci_high"]
    assert 0.0 < first["p"] <= 1.0


def test_no_fill_rows_never_reach_the_reading():
    blocked, taken = _weekly("blocked", [0.5, 0.7]), _weekly("taken", [0.1, 0.3])
    padded = blocked + [_row(status="no-fill", ticker="X", day="2024-01-08")]
    assert gcr.difference_reading(padded, taken) == gcr.difference_reading(blocked, taken)


def _verdict(blocked_rs, taken_rs, *, n=None):
    blocked, taken = _weekly("blocked", blocked_rs), _weekly("taken", taken_rs)
    reading = gcr.difference_reading(blocked, taken)
    return gcr.classify(reading, reading["p"], len(blocked) if n is None else n)


def test_gate_earns_when_blocked_setups_lose_against_taken():
    assert _verdict([-1.0, -0.5] * 20, [1.0, 0.5] * 20) == "GATE EARNS"


def test_gate_costs_when_blocked_setups_beat_taken():
    assert _verdict([1.0, 0.5] * 20, [-1.0, -0.5] * 20) == "GATE COSTS"


def test_inconclusive_when_the_interval_spans_zero():
    assert _verdict([1.0, -1.0] * 20, [-1.0, 1.0] * 20) == "INCONCLUSIVE"


def test_waiting_below_thirty_distinct_filled_setups():
    assert _verdict([-1.0, -0.5] * 20, [1.0, 0.5] * 20, n=29) == "WAITING"
    assert gcr.classify(None, None, 40) == "WAITING"


def test_an_interval_off_zero_still_needs_q_below_ten_percent():
    reading = {"difference": -0.5, "ci_low": -0.9, "ci_high": -0.1, "p": 0.04}
    assert gcr.classify(reading, 0.10, 40) == "INCONCLUSIVE"
    assert gcr.classify(reading, None, 40) == "INCONCLUSIVE"
    assert gcr.classify(reading, 0.0999, 40) == "GATE EARNS"


def test_bh_runs_over_the_fixed_five_cell_family():
    # m stays 5: a cell without a reading enters as p = 1.0, never drops out of the family
    q = gcr.family_qvalues([0.01, None, 0.04, None, None])
    assert q == pytest.approx([0.05, 1.0, 0.1, 1.0, 1.0])


def test_bh_family_refuses_a_family_of_the_wrong_size():
    with pytest.raises(ValueError):
        gcr.family_qvalues([0.01, 0.02])
