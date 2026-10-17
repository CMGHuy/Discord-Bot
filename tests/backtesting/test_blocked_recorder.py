"""v147 V147-4: TRAIN gate-row recorder module."""
import json

import pytest

from swingbot.core.backtesting import blocked_recorder as br
from swingbot.core.planning.exit_sim import ExitResult, _not_triggered, _no_trade
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct


def _plan(trigger=100.0, stop=97.0, **kw) -> TradePlanV2:
    base = dict(plan_id="p1", ticker="MSFT", created_at="2021-03-01", source="confluence",
                strategy="Fibonacci", horizon_key="4w", direction="bullish", entry_type="stop_entry",
                trigger_price=trigger, entry_price=None, expiry_bars=3, stop_loss=stop, tp1=106.0,
                tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING, status_history=[])
    base.update(kw)
    return TradePlanV2(**base)


def _row(**kw) -> dict:
    base = dict(population="train", arm="blocked", source="confluence", ticker="MSFT",
                strategy="Fibonacci", horizon="4w", direction="bullish", signal_date="2021-03-01",
                gate="plan_rejected", reason="risk_cap", margin=1.0, cf_status="filled",
                cf_r=-1.0, win=False)
    base.update(kw)
    return br.gate_row(**base)


def _win(r=1.4) -> ExitResult:
    return ExitResult(outcome="win", runner_outcome="runner_be", entry_index=4, exit_index=7,
                      entry_price=100.0, r_total=r,
                      legs=[{"fraction": 0.5, "exit_price": 106.0, "r": 2.0, "reason": "tp1"}])


SHAPE = {"population", "arm", "source", "ticker", "strategy", "horizon", "direction",
         "signal_date", "entry_date", "gate", "reason", "margin", "cf_status", "cf_r", "win",
         "planned_loss_pct", "dollar_risk", "expiry_bars", "in_sample"}


def test_train_window_is_frozen():
    assert br.TRAIN_WINDOW == ("2020-01-01", "2023-12-31")


@pytest.mark.parametrize("kwargs", [
    {"date_from": "2020-01-01", "date_to": "2023-12-31", "validation": True},
    {"date_from": "2019-12-31", "date_to": "2023-12-31"},
    {"date_from": "2020-01-01", "date_to": "2024-01-02"},
])
def test_require_train_window_refuses_outside_train(kwargs, capsys):
    with pytest.raises(SystemExit) as exc:
        br.require_train_window(**kwargs)
    assert exc.value.code == 2
    assert "--record-blocked" in capsys.readouterr().err


@pytest.mark.parametrize("date_from,date_to", [
    ("2020-01-01", "2023-12-31"), ("2021-06-01", "2022-06-30"), (None, None)])
def test_require_train_window_accepts_train(date_from, date_to):
    assert br.require_train_window(date_from, date_to) is None


@pytest.mark.parametrize("trigger,stop", [(100.0, 97.0), (100.0, 98.0), (100.0, 98.5),
                                          (50.0, 48.9999), (200.0, 204.5)])
def test_over_cap_agrees_with_attach_plan_v2s_check(trigger, stop):
    direction = "bullish" if stop < trigger else "bearish"
    plan = _plan(trigger, stop, direction=direction)
    live = planned_loss_pct(plan.trigger_price, plan.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + 1e-9
    assert br.over_cap(plan) is live


def test_exactly_at_the_cap_is_not_over():
    assert br.over_cap(_plan(100.0, 98.0)) is False
    assert br.risk_cap_margin(_plan(100.0, 98.0)) == pytest.approx(0.0)


def test_risk_cap_margin_is_planned_loss_past_the_cap():
    assert br.risk_cap_margin(_plan(100.0, 97.0)) == pytest.approx(1.0)
    assert br.risk_cap_margin(_plan(100.0, 98.5)) == pytest.approx(-0.5)


def test_dollar_risk_scales_r_by_stop_width_over_the_cap():
    assert br.dollar_risk(-1.0, 3.0) == pytest.approx(-1.5)
    assert br.dollar_risk(2.0, 2.0) == pytest.approx(2.0)
    assert br.dollar_risk(None, 3.0) is None
    assert br.dollar_risk(1.0, None) is None
    assert br.dollar_risk(1.0, float("inf")) is None


def test_gate_row_has_the_shared_shape():
    row = _row(planned_loss_pct=3.0, expiry_bars=3)
    assert set(row) == SHAPE
    assert row["entry_date"] == row["signal_date"] == "2021-03-01"
    assert row["dollar_risk"] == pytest.approx(-1.5)
    assert row["in_sample"] is False
    json.dumps(row)


def test_non_filled_rows_carry_no_r_and_no_win():
    for status in ("no-fill", "no-plan", "no-data"):
        row = _row(cf_status=status, cf_r=0.0, win=False, planned_loss_pct=3.0)
        assert (row["cf_r"], row["win"], row["dollar_risk"]) == (None, None, None)


@pytest.mark.parametrize("field,value", [("population", "holdout"), ("arm", "both"),
                                         ("gate", "dryup"), ("cf_status", "pending"),
                                         ("source", "outlook")])
def test_gate_row_rejects_unknown_labels(field, value):
    with pytest.raises(ValueError):
        _row(**{field: value})


def test_row_from_exit_fills_from_the_plan():
    row = br.row_from_exit(_win(), _plan(), population="train", arm="taken", source="confluence",
                           signal_date="2021-03-01", gate="plan_rejected", reason=None,
                           margin=None, in_sample=False)
    assert (row["cf_status"], row["cf_r"], row["win"]) == ("filled", 1.4, True)
    assert (row["ticker"], row["strategy"], row["horizon"], row["direction"], row["expiry_bars"]) \
        == ("MSFT", "Fibonacci", "4w", "bullish", 3)


def test_row_from_exit_never_scores_a_no_fill_or_no_trade():
    kw = dict(population="train", arm="taken", source="strategy", signal_date="2021-03-01",
              gate="compression", reason=None, margin=None, in_sample=True)
    assert br.row_from_exit(_not_triggered("expired"), _plan(), **kw)["cf_status"] == "no-fill"
    assert br.row_from_exit(_no_trade(4, 100.0), _plan(), **kw)["cf_status"] == "no-plan"
    assert br.row_from_exit(_not_triggered(), _plan(), **kw)["cf_r"] is None


def test_write_gate_rows_round_trips(tmp_path):
    rows = [_row(), _row(ticker="AAPL", cf_status="no-fill", cf_r=None, win=None)]
    path = tmp_path / "logs" / "v147-blocked-confluence.jsonl"
    assert br.write_gate_rows(rows, path) == 2
    back = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert back == rows
    assert br.write_gate_rows([], path) == 0 and path.read_text(encoding="utf-8") == ""
