"""v142: partials.py -- KPIs and counterfactuals over hand-built partial plans."""
import pytest

from swingbot.core.analytics import metrics as m
from swingbot.core.analytics import partials as pa
from swingbot.core.analytics.scope import BookScope
from swingbot.core.planning.plan_engine import PlanStatus
from tests.planning.test_plan_engine_model import _plan

FILL, TP1, EXIT = "2026-10-01T14:00:00+00:00", "2026-10-05T15:00:00+00:00", "2026-10-07T18:00:00+00:00"


def _path(mfe, top):
    """A runner_path whose ladder is touched up to and including `top` R."""
    return {"mfe_r": mfe, "mae_r": 1.5, "sessions_after_tp1": 2, "source": "live",
            "ladder": {key: ("2026-10-06" if float(key) <= top else None)
                       for key in ("1.5", "2.0", "2.5", "3.0", "4.0")}}


def _trade(plan_id, *, status=PlanStatus.CLOSED, reason=None, runner_r=None, tp2=120.0,
           strategy="RSI", direction="bullish", path=None, fill=FILL, tp1_hit=True,
           exit_at=EXIT, ledger="main"):
    """Entry 100, risk 5 (bullish: stop 95), TP1 leg at exactly 2.0R."""
    stop = 95.0 if direction == "bullish" else 105.0
    sign = 1 if direction == "bullish" else -1
    history = [{"status": "ACTIVE", "reason": "filled", "at": fill}]
    legs = []
    if tp1_hit:
        history.append({"status": "PARTIAL", "reason": "tp1_partial", "at": TP1})
        legs.append({"fraction": 0.5, "exit_price": 100.0 + 10.0 * sign, "r": 2.0, "reason": "tp1"})
    if runner_r is not None:
        legs.append({"fraction": 0.5, "exit_price": 100.0 + 5.0 * runner_r * sign,
                     "r": runner_r, "reason": reason})
    if status == PlanStatus.CLOSED:
        history.append({"status": "CLOSED", "reason": reason, "at": exit_at})
    return _plan(plan_id=plan_id, strategy=strategy, direction=direction, entry_price=100.0,
                 stop_loss=stop, tp1=100.0 + 10.0 * sign, tp2=tp2, status=status,
                 status_history=history, legs_realized=legs, runner_path=path, ledger=ledger)


def _book():
    return [
        _trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0),
               exit_at="2026-10-09T18:00:00+00:00"),
        _trade("B", reason="tp1_runner_be", runner_r=1.34, path=_path(2.6, 2.5)),
        _trade("C", reason="tp1_runner_trail", runner_r=3.0, path=_path(3.6, 3.0), strategy="MACD"),
        _trade("D", reason="manual"),                                   # runner leg only on the trade
        _trade("E", status=PlanStatus.PARTIAL),                         # runner still open
        _trade("F", reason="tp1_runner_trail", runner_r=2.4, tp2=None, path=_path(2.8, 2.5),
               strategy="MACD"),
        _trade("G", status=PlanStatus.ACTIVE, tp1_hit=False),           # open pre-TP1
        _trade("H", reason="loss", tp1_hit=False, direction="bearish"),  # stopped pre-TP1
    ]


MANUAL = {"D": 112.5}        # the linked trade's manual exit -> 2.5R


@pytest.fixture
def report():
    return pa.build_report(_book(), manual_exits=MANUAL)


def test_funnel(report):
    assert report["funnel"] == [{"stage": "filled", "n": 8}, {"stage": "tp1", "n": 6},
                                {"stage": "runner_closed", "n": 5}, {"stage": "tp2", "n": 1}]


def test_kpis(report):
    k = report["kpis"]
    assert (k["tp1_rate"], k["tp1_rate_n"]) == (85.7, 7)         # 6 / 7, G excluded
    assert (k["tp1_tp2_rate"], k["tp1_tp2_n"]) == (25.0, 4)      # A of A,B,C,D; F is no_tp2
    assert (k["beat_all_out"], k["beat_all_out_n"]) == (80.0, 5)  # B lost to all-out
    assert k["mean_runner_delta_r"] == pytest.approx(0.324)
    assert (k["median_tp1_exit_sessions"], k["tp1_exit_n"]) == (2.0, 5)


def test_outcome_buckets_cover_every_partial_once(report):
    rows = {row["bucket"]: row for row in report["outcomes"]}
    assert list(rows) == list(pa.OUTCOME_BUCKETS)               # no "other" row when empty
    assert {b: rows[b]["n"] for b in rows} == {"tp2": 1, "trail": 1, "floor": 1, "stall": 0,
                                               "time": 0, "manual": 1, "no_tp2": 1, "open": 1}
    assert rows["floor"]["avg_runner_r"] == 1.34 and rows["open"]["avg_runner_r"] is None
    assert rows["manual"]["avg_runner_r"] == 2.5 and rows["tp2"]["share"] == 16.7


def test_an_unknown_close_reason_is_reported_not_dropped():
    rows = pa.outcomes([pa.partial_trade(_trade("X", reason="acceptance", runner_r=1.0))])
    assert rows[-1] == {"bucket": "other", "n": 1, "share": 100.0, "avg_runner_r": 1.0}


def test_actual_exp_r_ties_out_to_r_multiple(report):
    measured = [p for p in _book() if p.plan_id in "ABCF"]
    blended = [m.r_multiple({"entry": 100.0, "stop_loss": 95.0, "direction": "bullish",
                             "legs": p.legs_realized}) for p in measured]
    blended.append(m.r_multiple({"entry": 100.0, "stop_loss": 95.0, "direction": "bullish",
                                 "legs": [{"fraction": 0.5, "r": 2.0},
                                          {"fraction": 0.5, "exit_price": 112.5}]}))
    cf = report["counterfactuals"]
    assert cf["actual_exp_r"] == pytest.approx(sum(blended) / 5) == pytest.approx(2.324)
    assert cf["all_out_exp_r"] == 2.0


def test_ladder_uses_each_trades_own_path(report):
    ladder = {row["level_r"]: row for row in report["counterfactuals"]["ladder"]}
    assert [row["n"] for row in ladder.values()] == [4] * 5      # D has no path
    assert ladder[1.5]["touch_rate"] == 100.0 and ladder[1.5]["cf_exp_r"] == 1.75
    assert ladder[3.0]["touch_rate"] == 50.0
    assert ladder[3.0]["cf_exp_r"] == pytest.approx(2.2175)
    assert ladder[4.0]["touch_rate"] == 25.0
    assert ladder[4.0]["cf_exp_r"] == pytest.approx(2.3425)


def test_split_what_if(report):
    split = {row["fraction"]: row for row in report["counterfactuals"]["split"]}
    assert split[0.5]["exp_r"] == pytest.approx(2.324)
    assert split[0.33]["exp_r"] == pytest.approx(2.4342)
    assert split[0.67]["exp_r"] == pytest.approx(2.2138)
    assert {row["n"] for row in split.values()} == {5}


def test_giveback_and_visible_exclusions(report):
    cf = report["counterfactuals"]
    assert cf["giveback"] == pytest.approx([0.2, 1.26, 0.6, 0.4])
    assert cf["path_unavailable"] == 1 and cf["runner_r_unavailable"] == 0


def test_a_manual_close_without_a_trade_price_is_counted_not_dropped():
    report = pa.build_report(_book(), manual_exits={})
    cf = report["counterfactuals"]
    assert cf["runner_r_unavailable"] == 1
    assert report["kpis"]["beat_all_out_n"] == 4
    assert report["funnel"][2] == {"stage": "runner_closed", "n": 5}


def test_counterfactuals_use_the_trades_own_fraction():
    plan = _trade("Q", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.0, 4.0))
    plan.tp1_fraction = 0.25
    plan.legs_realized[0]["fraction"], plan.legs_realized[1]["fraction"] = 0.25, 0.75
    cf = pa.counterfactuals([pa.partial_trade(plan)])
    assert cf["actual_exp_r"] == pytest.approx(0.25 * 2.0 + 0.75 * 4.0)
    assert cf["ladder"][0]["cf_exp_r"] == pytest.approx(0.25 * 2.0 + 0.75 * 1.5)


def test_holds_in_trading_sessions(report):
    h = report["holds"]
    assert h["entry_tp1"]["points"] == [2] * 6                   # Thu -> Mon, open runner included
    assert h["tp1_exit"]["points"] == [2, 2, 2, 2, 4]            # A exits Fri; E is open
    assert h["entry_exit"]["median"] == 4.0


def test_breakdowns(report):
    by_strategy = {row["key"]: row for row in report["breakdowns"]["strategy"]}
    assert (by_strategy["RSI"]["n"], by_strategy["RSI"]["tp1_rate"]) == (4, 80.0)
    assert (by_strategy["MACD"]["n"], by_strategy["MACD"]["tp1_tp2_rate"]) == (2, 0.0)
    assert all(row["thin"] for row in by_strategy.values())
    by_side = {row["key"]: row for row in report["breakdowns"]["side"]}
    assert (by_side["bearish"]["n"], by_side["bearish"]["tp1_rate"]) == (0, 0.0)
    [month] = report["breakdowns"]["month"]
    assert (month["key"], month["n"], month["tp1_rate"]) == ("2026-10", 6, None)


def test_a_row_of_ten_is_not_thin():
    plans = [_trade(f"T{i}", reason="tp1_runner_tp2", runner_r=4.0) for i in range(10)]
    [row] = pa.build_report(plans)["breakdowns"]["strategy"]
    assert (row["n"], row["thin"]) == (10, False)


def test_empty_scope_is_all_zeros_and_nones():
    report = pa.build_report([])
    assert [row["n"] for row in report["funnel"]] == [0, 0, 0, 0]
    assert report["kpis"]["tp1_rate"] is None and report["kpis"]["beat_all_out"] is None
    assert report["counterfactuals"]["actual_exp_r"] is None
    assert report["holds"]["tp1_exit"] == {"p25": None, "median": None, "p75": None, "points": []}


def test_select_plans_filters_on_fill_date_and_plan_fields():
    plans = [_trade("early", reason="tp1_runner_tp2", runner_r=4.0, fill="2026-09-30T14:00:00+00:00"),
             _trade("late", reason="tp1_runner_tp2", runner_r=4.0),
             _trade("weak", reason="tp1_runner_tp2", runner_r=4.0, ledger="weak"),
             _trade("short", reason="loss", tp1_hit=False, direction="bearish"),
             _plan(plan_id="pending", status=PlanStatus.PENDING)]
    ids = lambda scope: [p.plan_id for p in pa.select_plans(plans, scope)]
    assert ids(BookScope()) == ["early", "late", "short"]
    assert ids(BookScope(start="2026-10-01")) == ["late", "short"]
    assert ids(BookScope(ledger="both", direction="bullish")) == ["early", "late", "weak"]
    assert ids(BookScope(strategy="MACD")) == []


def test_a_stamp_without_ladder_or_mfe_is_path_unavailable_not_a_crash():
    plan = _trade("S", reason="tp1_runner_tp2", runner_r=4.0, path={"source": "live"})
    cf = pa.counterfactuals([pa.partial_trade(plan)])
    assert cf["giveback"] == [] and cf["path_unavailable"] == 1
    assert [row["n"] for row in cf["ladder"]] == [0] * 5
