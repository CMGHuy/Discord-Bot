"""v229 statistics: per-alert ExpR, week-clustered deltas, path-class calibration."""
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

from deferred_entry import analysis  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402

FAST = dict(n_resamples=300, seed=42)
WEEKS = ("2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23")   # W45..W48, Mondays


def _leg(arm, r, *, taken=True, outcome="loss"):
    return {"arm": arm, "taken": taken, "fill": 100.0, "stop": 98.0, "tp1": 104.0,
            "outcome": outcome if taken else "skipped", "r_net": r if taken else 0.0,
            "r_gross": r + 0.05 if taken else 0.0, "exit_ts": None, "gap_stop": False}


def _pair(tid, entry_date, c, a, b, *, b_taken=True, c_outcome="loss", a_outcome="win",
          live_reason="loss", live_r=-1.0, above=True, event=False):
    return {"trade_id": tid, "entry_date": entry_date,
            "arms": {"C": _leg("C", c, outcome=c_outcome), "A": _leg("A", a, outcome=a_outcome),
                     "B": _leg("B", b, taken=b_taken, outcome=a_outcome)},
            "live": {"reason": live_reason, "outcome": live_reason, "r_realized": live_r},
            "tradeability": {"fill_above_entry": above, "event_day": event}}


@pytest.mark.parametrize("reason, expected", [
    ("tp1_partial", "win"), ("TP1_runner_be", "win"), ("tp1_runner_tp2", "win"), ("win", "win"),
    ("scratch", "scratch"), ("loss", "loss"), ("stop", "loss"), (" Loss ", "loss"),
    ("manual", None), ("reversed", None), ("stall_exit", None), ("time_exit", None), ("", None), (None, None),
])
def test_live_class_follows_the_live_writer(reason, expected):
    assert analysis.live_class(reason) == expected


@pytest.mark.parametrize("outcome, expected", [
    ("win", "win"), ("loss", "loss"), ("scratch", "scratch"),
    ("timeout", None), ("no_bars", None), ("skipped", None), (None, None),
])
def test_sim_class_maps_the_race_outcomes(outcome, expected):
    assert analysis.sim_class(outcome) == expected


def test_arm_summary_counts_a_skipped_plan_at_zero_r():
    pairs = [_pair("t-1", WEEKS[0], -1.0, 2.0, 2.0),
             _pair("t-2", WEEKS[0], -1.0, -1.0, 0.0, b_taken=False)]
    out = analysis.arm_summary(pairs, "B")
    assert out["n"] == 2 and out["taken"] == 1 and out["wins"] == 1
    assert out["win_rate"] == pytest.approx(1.0)             # over trades taken
    assert out["exp_r"] == pytest.approx(1.0)                # (2 + 0) / 2, per alert
    assert out["total_r"] == pytest.approx(2.0)
    assert out["exp_r_gross"] == pytest.approx(2.05 / 2)


def test_arm_summary_on_no_pairs_is_empty_not_zero():
    assert analysis.arm_summary([], "C") == {"n": 0, "taken": 0, "wins": 0, "win_rate": None,
                                             "exp_r": None, "total_r": 0.0, "exp_r_gross": None}


def test_delta_stats_defaults_are_the_pre_registered_ones():
    params = inspect.signature(analysis.delta_stats).parameters
    assert params["n_resamples"].default == 10_000
    assert params["seed"].default == stats.WEEK_BOOTSTRAP_SEED == 42


def test_a_uniform_lift_has_its_bound_at_the_lift_and_p_zero():
    pairs = [_pair(f"t-{i}", d, -1.0, 0.0, 0.0) for i, d in enumerate(WEEKS * 3)]
    out = analysis.delta_stats(pairs, "A", **FAST)
    assert out == {"arm": "A", "n": 12, "weeks": 4, "mean": pytest.approx(1.0),
                   "lower": pytest.approx(1.0), "p": 0.0}


def test_a_uniform_loss_has_p_one():
    pairs = [_pair(f"t-{i}", d, 1.0, 0.5, 0.5) for i, d in enumerate(WEEKS)]
    out = analysis.delta_stats(pairs, "B", **FAST)
    assert out["mean"] == pytest.approx(-0.5) and out["p"] == 1.0


def test_delta_stats_is_deterministic_under_the_seed_and_brackets_the_mean():
    pairs = [_pair(f"t-{i}", d, -1.0, r, r) for i, (d, r) in
             enumerate(zip(WEEKS * 2, (2.0, -1.0, 0.5, 3.0, -1.0, 1.0, 0.0, 2.0)))]
    first = analysis.delta_stats(pairs, "A", **FAST)
    assert first == analysis.delta_stats(pairs, "A", **FAST)
    assert first["lower"] < first["mean"] and 0.0 <= first["p"] <= 1.0


def test_a_skipped_b_plan_enters_the_delta_at_zero_r():
    pairs = [_pair("t-1", WEEKS[0], -1.0, -1.0, 0.0, b_taken=False),
             _pair("t-2", WEEKS[1], -1.0, -1.0, 0.0, b_taken=False)]
    assert analysis.delta_stats(pairs, "B", **FAST)["mean"] == pytest.approx(1.0)


def test_a_single_week_book_returns_no_interval(monkeypatch):
    monkeypatch.setattr(analysis, "week_cluster_bootstrap",
                        lambda *a, **k: pytest.fail("bootstrap called on one week"))
    pairs = [_pair("t-1", "2026-11-02", -1.0, 1.0, 1.0), _pair("t-2", "2026-11-06", -1.0, 0.0, 0.0)]
    out = analysis.delta_stats(pairs, "A", **FAST)
    assert out["weeks"] == 1 and out["mean"] == pytest.approx(1.5)
    assert out["lower"] is None and out["p"] is None


def test_no_pairs_returns_no_mean_and_no_interval():
    assert analysis.delta_stats([], "A", **FAST) == {"arm": "A", "n": 0, "weeks": 0,
                                                    "mean": None, "lower": None, "p": None}


def test_the_bootstrap_gets_objects_keyed_by_entry_date(monkeypatch):
    seen = {}

    def fake(baseline, component, statistic, *, n_resamples, seed):
        seen.update(b=baseline, c=component, n=n_resamples, seed=seed)
        return stats.week_cluster_bootstrap(baseline, component, statistic, n_resamples=n_resamples, seed=seed)

    monkeypatch.setattr(analysis, "week_cluster_bootstrap", fake)
    analysis.delta_stats([_pair("t-1", WEEKS[0], -1.0, 2.0, 0.0), _pair("t-2", WEEKS[1], 0.0, 1.0, 0.0)],
                         "A", **FAST)
    assert [item.entry_date for item in seen["b"]] == [WEEKS[0], WEEKS[1]]
    assert [item.r for item in seen["b"]] == [-1.0, 0.0] and [item.r for item in seen["c"]] == [2.0, 1.0]
    assert (seen["n"], seen["seed"]) == (300, 42)


def test_delta_over_taken_leaves_out_the_skipped_plans():
    pairs = [_pair("t-1", WEEKS[0], -1.0, 0.0, 0.0, b_taken=False), _pair("t-2", WEEKS[0], 1.0, 0.5, 0.5)]
    assert analysis.delta_over_taken(pairs, "B") == {"n": 1, "mean": pytest.approx(-0.5)}
    assert analysis.delta_over_taken([], "B") == {"n": 0, "mean": None}


def test_week_count_counts_distinct_iso_weeks():
    pairs = [_pair("t-1", "2026-11-02", 0, 0, 0), _pair("t-2", "2026-11-06", 0, 0, 0),
             _pair("t-3", "2026-11-09", 0, 0, 0)]
    assert analysis.week_count(pairs) == 2 and analysis.week_count([]) == 0
