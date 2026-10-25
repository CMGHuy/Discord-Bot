"""v188: figures, intervals, baseline and payload (pure)."""
from datetime import date, timedelta

import pytest

from swingbot.core.analytics import cancel_precision as cp
from swingbot.core.analytics.cancel_replay import Replay
from swingbot.core.analytics.cancel_rows import CancelRow
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

DAY = date(2026, 8, 3)
FIGURE_KEYS = {"n", "total", "excluded", "precision", "precision_ci", "r_avoided",
               "r_missed", "net_r", "net_r_ci", "counts", "unresolved_r", "ties", "small_n"}
ROW_KEYS = {"plan_id", "ticker", "strategy", "horizon_key", "direction", "origin", "reason",
            "raw_reason", "cancel_date", "entry_model", "entry_source", "entry", "stop", "tp1",
            "badge", "stop_ceiling_pct", "cap_size_pct", "outcome", "r", "tie", "exit_date",
            "excluded"}


def _row(outcome="right", r=-1.0, *, day=DAY, tie=False, excluded=None, **kw):
    base = dict(plan_id="p1", ticker="AAPL", strategy="Fibonacci", horizon_key="2w",
                direction="long", origin="regular", reason="invalidated",
                raw_reason="invalidated", cancel_day=day, entry_model="trigger",
                entry_source=None, entry=105.0, stop=95.0, tp1=120.0, badge="WEAK",
                stop_ceiling_pct=2.0, cap_size_pct=None, excluded=excluded,
                replay=None if excluded else Replay(outcome, r, tie, day, None,
                                                     day + timedelta(days=14), True))
    base.update(kw)
    return CancelRow(**base)


# -- figure --------------------------------------------------------------------

def test_an_empty_figure_is_n_zero_never_an_error():
    """Review Focus 4."""
    fig = cp.figure([])
    assert set(fig) == FIGURE_KEYS
    assert (fig["n"], fig["total"], fig["precision"], fig["precision_ci"], fig["net_r_ci"]) == \
        (0, 0, None, None, None)
    assert fig["small_n"] is True and fig["net_r"] == 0.0
    assert fig["counts"] == {"right": 0, "wrong": 0, "unresolved": 0,
                             "untriggered_after_cancel": 0}


def test_counts_precision_and_r():
    rows = [_row(), _row(), _row(tie=True), _row("wrong", 1.5), _row("unresolved", 0.2),
            _row("unresolved", None), _row("untriggered_after_cancel", None),
            _row(excluded="split_guard")]
    fig = cp.figure(rows, with_interval=False)
    assert (fig["n"], fig["total"], fig["excluded"]) == (4, 8, 1)
    assert fig["precision"] == 0.75
    assert (fig["r_avoided"], fig["r_missed"], fig["net_r"]) == (3.0, 1.5, 1.5)
    assert fig["counts"] == {"right": 3, "wrong": 1, "unresolved": 2,
                             "untriggered_after_cancel": 1}
    assert (fig["unresolved_r"], fig["ties"], fig["small_n"]) == (0.2, 1, True)
    assert fig["precision_ci"] is None and fig["net_r_ci"] is None


def test_net_r_can_be_negative_while_precision_is_above_half():
    fig = cp.figure([_row(), _row(), _row("wrong", 3.0)], with_interval=False)
    assert fig["precision"] == pytest.approx(0.6667)
    assert fig["net_r"] == -1.0


def test_all_unresolved_is_n_zero():
    fig = cp.figure([_row("unresolved", 0.4), _row("unresolved", None)])
    assert (fig["n"], fig["precision"], fig["precision_ci"], fig["small_n"]) == (0, None, None, True)
    assert fig["unresolved_r"] == 0.4


def test_the_small_n_marker_clears_at_ten():
    assert cp.figure([_row()] * 9, with_interval=False)["small_n"] is True
    assert cp.figure([_row()] * 10, with_interval=False)["small_n"] is False


def test_the_interval_brackets_the_point_and_is_reproducible():
    rows = [_row(day=DAY + timedelta(weeks=w)) for w in range(6)]
    rows += [_row("wrong", 1.5, day=DAY + timedelta(weeks=w)) for w in range(0, 6, 2)]
    first, second = cp.figure(rows), cp.figure(rows)
    lo, hi = first["precision_ci"]
    assert 0.0 <= lo <= first["precision"] <= hi <= 1.0
    assert first["net_r_ci"][0] <= first["net_r"] <= first["net_r_ci"][1]
    assert first == second                                    # seed 42


def test_one_week_gives_a_degenerate_interval():
    fig = cp.figure([_row(), _row("wrong", 1.5)])
    assert fig["precision_ci"] == [0.5, 0.5]


# -- baseline population -------------------------------------------------------

def test_the_baseline_keeps_the_window_and_the_strategy_horizon_pairs():
    scored = [_row(day=DAY), _row(day=DAY + timedelta(days=10))]
    inside = _row(reason="filled", day=DAY + timedelta(days=5), plan_id="f1")
    early = _row(reason="filled", day=DAY - timedelta(days=1), plan_id="f2")
    other_pair = _row(reason="filled", day=DAY, horizon_key="4w", plan_id="f3")
    kept = cp.baseline_population([inside, early, other_pair], scored)
    assert [r.plan_id for r in kept] == ["f1"]


def test_no_scored_cancels_means_no_baseline():
    assert cp.baseline_population([_row(reason="filled")], []) == []


# -- payload -------------------------------------------------------------------

FLAT = (100.0, 100.5, 99.5, 100.0)
STOP_HIT = (100.0, 101.0, 94.0, 95.0)
TP1_HIT = (104.0, 121.0, 104.0, 120.0)
LONG = dict(entry_type="stop_entry", trigger_price=105.0, stop_loss=95.0, tp1=120.0,
            horizon_key="2w", source="strategy", strategy="Fibonacci", stop_ceiling_pct=2.0)


def _frame(*walked):
    bars = [FLAT, FLAT, (108.0, 108.5, 99.5, 100.0)] + list(walked)
    return make_ohlcv(bars + [FLAT] * (14 - len(bars)), start="2026-07-30")


def _with(status, reason, plan_id, at="2026-08-03T15:00:00+00:00", **kw):
    plan = _plan(plan_id=plan_id, ticker=plan_id.upper(), **{**LONG, **kw})
    record_transition(plan, status, reason=reason, at=at)
    return plan


def _book():
    frames = {"INV": _frame((104, 106, 104, 105), STOP_HIT),      # invalidated, right
              "EXP": _frame((104, 106, 104, 105), TP1_HIT),       # expired, wrong 1.5R
              "CAP": _frame(),                                     # risk_cap, untriggered
              "OTH": _frame(), "MAN": _frame(),
              "FIL": _frame(STOP_HIT)}                             # baseline, right
    plans = [_with(PlanStatus.CANCELLED, "invalidated", "inv"),
             _with(PlanStatus.CANCELLED, "expired", "exp", at="2026-08-04T15:00:00+00:00"),
             _with(PlanStatus.CANCELLED, "risk_cap", "cap"),
             _with(PlanStatus.CANCELLED, "never_triggered", "oth"),
             _with(PlanStatus.CANCELLED, "manual", "man"),
             _with(PlanStatus.ACTIVE, "stop_entry_fill", "fil")]
    return plans, frames.get


def test_the_payload_shape_and_copy():
    plans, loader = _book()
    body = cp.precision_payload(plans, loader, generated_at="2026-10-23T12:00:00+00:00")
    assert body["caption"] == "Hypothetical replay, before commissions, slippage and tax"
    assert body["risk_cap_label"] == "Outcome of the skipped setup, unaffordable at the cap"
    assert body["tp1_note"] == ("A TP1 hit counts the full target R with no partial exit; "
                                "the bot does not bank winners in full.")
    assert body["small_n_threshold"] == 10
    assert set(body["cards"]) == {"risk_cap", "risk_cap_fill", "invalidated", "expired", "other"}
    assert set(body["headline"]) == {"all", "without_risk_cap"}
    assert all(set(r) == ROW_KEYS for r in body["rows"])
    assert set(body["baseline"]) == FIGURE_KEYS


def test_the_payload_figures():
    plans, loader = _book()
    body = cp.precision_payload(plans, loader, generated_at="x")
    head = body["headline"]["all"]
    assert (head["n"], head["total"], head["precision"]) == (2, 3, 0.5)
    assert head["counts"]["untriggered_after_cancel"] == 1
    assert body["headline"]["without_risk_cap"]["total"] == 2
    assert body["cards"]["risk_cap_fill"]["total"] == 1
    assert body["cards"]["other"]["total"] == 1
    assert body["out_of_scope"] == {"manual": 1}
    assert (body["baseline"]["n"], body["baseline"]["precision"]) == (1, 1.0)
    assert body["window"] == {"first": "2026-08-03", "last": "2026-08-04"}
    assert body["rule_changes"] == []
    assert body["data_as_of"] == "2026-08-18"


def test_rows_are_newest_first_with_both_risk_cap_models_and_no_baseline_or_manual():
    plans, loader = _book()
    rows = cp.precision_payload(plans, loader, generated_at="x")["rows"]
    assert [(r["plan_id"], r["entry_model"]) for r in rows] == [
        ("exp", "trigger"), ("cap", "trigger"), ("cap", "cancel_fill"),
        ("inv", "trigger"), ("oth", "trigger")]
    fill = rows[2]
    assert (fill["entry"], fill["entry_source"]) == (108.0, "estimated")
    assert rows[0]["r"] == 1.5 and rows[0]["exit_date"] == "2026-08-05"


def test_splits_list_only_present_keys():
    plans, loader = _book()
    splits = cp.precision_payload(plans, loader, generated_at="x")["splits"]
    assert list(splits["origin"]) == ["regular"]
    assert list(splits["direction"]) == ["long"]
    assert list(splits["horizon"]) == ["2w"]


def test_an_excluded_row_has_null_outcome_r_and_exit():
    plans, _ = _book()
    rows = cp.precision_payload(plans[:1], lambda _t: None, generated_at="x")["rows"]
    assert (rows[0]["excluded"], rows[0]["outcome"], rows[0]["r"], rows[0]["exit_date"]) == \
        ("no_bars", None, None, None)


def test_a_rule_change_inside_the_window_is_listed():
    plan = _with(PlanStatus.CANCELLED, "invalidated", "inv", at="2026-09-28T15:00:00+00:00")
    body = cp.precision_payload([plan], lambda _t: make_ohlcv([FLAT] * 5, start="2026-09-24"),
                                generated_at="x")
    assert body["rule_changes"] == [{"date": "2026-09-28",
                                     "label": "v104 structural stops and stop-ceiling scope"}]
    late = _with(PlanStatus.CANCELLED, "invalidated", "late", at="2026-10-23T15:00:00+00:00")
    body = cp.precision_payload([plan, late],
                                lambda _t: make_ohlcv([FLAT] * 25, start="2026-09-24"),
                                generated_at="x")
    assert body["window"] == {"first": "2026-09-28", "last": "2026-10-23"}
    assert body["rule_changes"] == [
        {"date": "2026-09-28", "label": "v104 structural stops and stop-ceiling scope"},
        {"date": "2026-10-14", "label": "v139 stored stop ceiling"},
        {"date": "2026-10-23", "label": "v183 gap-aware short sizing"}]


def test_the_loader_is_called_once_per_ticker():
    calls = []
    plans, loader = _book()
    cp.precision_payload(plans, lambda t: calls.append(t) or loader(t), generated_at="x")
    assert sorted(calls) == sorted(set(calls))


def test_an_empty_book():
    """Review Focus 4: an empty book is a payload with n = 0, never an error."""
    body = cp.precision_payload([], lambda _t: None, generated_at="x")
    assert body["headline"]["all"]["n"] == 0 and body["headline"]["all"]["precision"] is None
    assert body["headline"]["all"]["small_n"] is True
    assert (body["rows"], body["rule_changes"], body["data_as_of"]) == ([], [], None)
    assert body["window"] == {"first": None, "last": None}
    assert body["splits"] == {"origin": {}, "direction": {}, "horizon": {}}
