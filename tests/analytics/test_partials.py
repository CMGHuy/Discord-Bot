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
    assert cf["giveback"] == pytest.approx([0.2, 1.26, 0.6])     # A, B, C; F has no TP2, D is manual
    assert cf["giveback_excluded"] == 2
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
    assert cf["giveback_excluded"] == 1
    assert [row["n"] for row in cf["ladder"]] == [0] * 5


# -- v173: a bulk clear is a manual close for the outcome buckets ------------

def test_a_bulk_cleared_runner_lands_in_the_manual_bucket():
    plan = _trade("Z", reason="manual_bulk")
    assert pa.outcome_bucket(plan) == "manual"


def test_bulk_and_single_manual_closes_share_one_bucket_row():
    book = [*_book(), _trade("Z", reason="manual_bulk")]
    rows = {row["bucket"]: row for row in pa.build_report(book, manual_exits={**MANUAL, "Z": 107.5})["outcomes"]}
    assert rows["manual"]["n"] == 2
    assert "other" not in rows
    assert rows["manual"]["avg_runner_r"] == pytest.approx((2.5 + 1.5) / 2)


# -- v219: tp2_r, typed pathed, decidable, progress --------------------------

def _one(plan, manual_exits=None):
    return pa.partial_trade(plan, manual_exits)


def test_tp2_r_is_the_plans_tp2_on_the_initial_risk_basis():
    assert _one(_trade("A", reason="tp1_runner_tp2", runner_r=4.0)).tp2_r == 4.0
    assert _one(_trade("S", reason="tp1_runner_tp2", runner_r=4.0, direction="bearish",
                       tp2=80.0)).tp2_r == 4.0
    assert _one(_trade("F", reason="tp1_runner_trail", runner_r=2.4, tp2=None)).tp2_r is None


def test_a_well_formed_stamp_is_pathed():
    assert _one(_trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0))).pathed
    whole = {**_path(4.0, 4.0), "mfe_r": 4}                     # an int is a real number
    assert _one(_trade("I", reason="tp1_runner_tp2", runner_r=4.0, path=whole)).pathed


@pytest.mark.parametrize("stamp", [
    None,
    {},
    "garbage",
    ["mfe_r", "ladder"],
    {"mfe_r": 3.1},
    {"ladder": {}},
    {"mfe_r": None, "ladder": {}},
    {"mfe_r": "3.1", "ladder": {}},
    {"mfe_r": True, "ladder": {}},
    {"mfe_r": float("nan"), "ladder": {}},
    {"mfe_r": float("inf"), "ladder": {}},
    {"mfe_r": 3.1, "ladder": None},
    {"mfe_r": 3.1, "ladder": ["2026-10-06"]},
])
def test_a_malformed_stamp_is_unpathed_and_never_raises(stamp):
    trade = _one(_trade("X", reason="tp1_runner_trail", runner_r=3.0, path=stamp))
    assert trade.pathed is False and trade.decidable is False and trade.progress is None
    cf = pa.counterfactuals([trade])
    assert cf["giveback"] == [] and cf["giveback_excluded"] == 1


def test_decidable_needs_every_condition():
    assert _one(_trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0))).decidable
    unpriced = _trade("N", reason="tp1_runner_trail", path=_path(3.0, 3.0))
    flat = _trade("Q", reason="tp1_runner_trail", runner_r=3.0, tp2=110.0, path=_path(3.0, 3.0))
    below = _trade("R", reason="tp1_runner_trail", runner_r=3.0, tp2=105.0, path=_path(3.0, 3.0))
    no_tp2 = _trade("F", reason="tp1_runner_trail", runner_r=2.4, tp2=None, path=_path(2.8, 2.5))
    assert not _one(unpriced).decidable                           # runner R unknown
    assert _one(flat).tp2_r == 2.0 and not _one(flat).decidable   # tp2_r == r_tp1: no distance
    assert not _one(below).decidable                              # tp2_r < r_tp1
    assert not _one(no_tp2).decidable


def test_a_priced_manual_close_with_a_stamp_is_still_not_decidable():
    plan = _trade("M", reason="manual", path=_path(3.0, 2.5))
    trade = _one(plan, {"M": 107.5})                              # priced from its trade: 1.5R
    assert trade.bucket == "manual" and trade.r_runner == 1.5 and trade.pathed
    assert trade.decidable is False and trade.progress is None
    cf = pa.counterfactuals([trade])
    assert cf["giveback"] == [] and cf["giveback_excluded"] == 1


@pytest.mark.parametrize("mfe, expected", [
    (4.2, 1.0),      # past TP2: clamped at 1
    (4.0, 1.0),
    (3.0, 0.5),      # exactly halfway
    (2.0, 0.0),      # at TP1
    (1.5, 0.0),      # below TP1 (a hand-built stamp): clamped at 0
])
def test_progress_to_tp2_is_clamped(mfe, expected):
    trade = _one(_trade("P", reason="tp1_runner_trail", runner_r=2.0, path=_path(mfe, 2.0)))
    assert trade.progress == pytest.approx(expected)
    assert 0.0 <= trade.progress <= 1.0


def test_progress_is_none_unless_decidable():
    assert _one(_trade("N", reason="tp1_runner_trail", path=_path(3.0, 3.0))).progress is None


def test_the_giveback_threshold_is_half_way():
    assert pa.GIVEBACK_PROGRESS == 0.5


# -- v219: runner endings -- rows and path exclusions --------------------------

def _runners(plans, manual_exits=MANUAL):
    trades = [t for plan in plans if (t := pa.partial_trade(plan, manual_exits)) is not None]
    return pa._section(trades)


def _rows(plans, manual_exits=MANUAL):
    return {row["ending"]: row for row in pa.ending_rows(_runners(plans, manual_exits))}


def test_the_section_is_closed_runners_with_a_tp2():
    assert [t.plan_id for t in _runners(_book())] == ["A", "B", "C", "D"]  # E open, F no TP2


@pytest.mark.parametrize("reason, ending", [
    ("tp1_runner_tp2", "tp2"), ("tp1_runner_trail", "trail"), ("tp1_runner_be", "floor"),
    ("tp1_runner_progress_stall", "other"), ("time_exit", "other"), ("manual", "other"),
    ("manual_bulk", "other"), ("acceptance", "other"),
])
def test_every_close_reason_has_one_ending(reason, ending):
    trade = pa.partial_trade(_trade("X", reason=reason, runner_r=1.0))
    assert pa.ending_of(trade) == ending


def test_share_carries_a_wilson_interval_in_percent():
    assert pa._share(1, 4) == {"share": 25.0, "lo": 4.6, "hi": 69.9}
    assert pa._share(0, 3) == {"share": 0.0, "lo": 0.0, "hi": 56.2}
    assert pa._share(0, 0) == {"share": None, "lo": None, "hi": None}


def test_ending_rows_on_the_book():
    rows = _rows(_book())
    assert list(rows) == ["tp2", "trail", "floor", "other", "giveback"]
    assert rows["tp2"] == {
        "ending": "tp2", "n": 1, "denominator": 4, "share": 25.0, "lo": 4.6, "hi": 69.9,
        "thin": True, "r_n": 1, "avg_r": 4.0, "median_r": 4.0, "total_r": 2.0,
        "vs_all_out": 1.0, "path_n": 1, "best_r": 4.2, "progress": 100.0, "gave_back": 0.2,
        "sessions": 4.0}
    cols = ("n", "denominator", "share", "r_n", "avg_r", "median_r", "total_r", "vs_all_out",
            "path_n", "best_r", "progress", "gave_back", "sessions")
    pick = lambda row: tuple(row[c] for c in cols)
    assert pick(rows["trail"]) == (1, 4, 25.0, 1, 3.0, 3.0, 1.5, 0.5, 1, 3.6, 80.0, 0.6, 2.0)
    assert pick(rows["floor"]) == (1, 4, 25.0, 1, 1.34, 1.34, 0.67, -0.33, 1, 2.6, 30.0, 1.26, 2.0)
    assert pick(rows["other"]) == (1, 4, 25.0, 1, 2.5, 2.5, 1.25, 0.25, 0, None, None, None, 2.0)
    assert pick(rows["giveback"]) == (0, 3, 0.0, 0, None, None, None, None, 0, None, None, None, None)
    assert (rows["giveback"]["lo"], rows["giveback"]["hi"]) == (0.0, 56.2)


def test_the_four_ending_rows_make_the_whole_section():
    book = [*_book(), _trade("S1", reason="tp1_runner_progress_stall", runner_r=1.5),
            _trade("T1", reason="time_exit", runner_r=0.8)]
    rows = pa.ending_rows(_runners(book))
    endings = [row for row in rows if row["ending"] in pa.ENDING_ROWS]
    assert sum(row["n"] for row in endings) == 6 == endings[0]["denominator"]
    assert sum(row["share"] for row in endings) == pytest.approx(100.0, abs=0.2)
    assert {row["ending"]: row["n"] for row in endings} == {"tp2": 1, "trail": 1, "floor": 1, "other": 3}


def _giveback_case(plan_id, *, reason="tp1_runner_trail", runner_r, mfe):
    return _trade(plan_id, reason=reason, runner_r=runner_r, path=_path(mfe, 2.5))


@pytest.mark.parametrize("runner_r, mfe, expected", [
    (1.98, 3.0, True),      # exactly halfway to TP2, closed just below TP1
    (2.0, 3.0, False),      # closed exactly at TP1: not a giveback
    (1.0, 2.98, False),     # 49% of the way: not far enough
    (1.0, 4.2, True),       # past TP2 (progress clamped to 1), closed well below TP1
])
def test_giveback_definition(runner_r, mfe, expected):
    trade = pa.partial_trade(_giveback_case("G", runner_r=runner_r, mfe=mfe))
    assert pa.is_giveback(trade) is expected


def test_giveback_spans_endings_and_has_its_own_denominator():
    book = [*_book(),
            _giveback_case("G1", runner_r=1.98, mfe=3.0),                        # trail
            _giveback_case("G2", reason="tp1_runner_be", runner_r=1.34, mfe=3.2),  # floor
            _trade("M1", reason="manual", path=_path(3.5, 3.0))]                 # priced below TP1
    rows = _rows(book, {**MANUAL, "M1": 105.0})
    give = rows["giveback"]
    assert (give["n"], give["denominator"]) == (2, 5)     # A, B, C, G1, G2 decidable; D, M1 manual
    assert (give["share"], give["lo"], give["hi"]) == (40.0, 11.8, 76.9)
    assert give["r_n"] == give["path_n"] == 2
    assert rows["trail"]["n"] == 2 and rows["floor"]["n"] == 2 and rows["other"]["n"] == 2
    assert rows["tp2"]["denominator"] == 7


def test_a_runner_without_runner_r_counts_in_n_and_share_only():
    rows = _rows([_trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0)),
                  _trade("U", reason="tp1_runner_trail", path=_path(3.0, 3.0))], manual_exits={})
    trail = rows["trail"]
    assert (trail["n"], trail["share"], trail["r_n"], trail["path_n"]) == (1, 50.0, 0, 0)
    assert trail["avg_r"] is None and trail["total_r"] is None
    assert trail["vs_all_out"] is None and trail["sessions"] is None


def test_a_row_of_ten_is_not_thin_and_an_empty_one_is():
    plans = [_trade(f"T{i}", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0))
             for i in range(10)]
    rows = _rows(plans)
    assert (rows["tp2"]["n"], rows["tp2"]["thin"]) == (10, False)
    assert (rows["trail"]["n"], rows["trail"]["thin"]) == (0, True)


def test_an_empty_section_is_measured_zeros_and_nones():
    rows = pa.ending_rows([])
    assert [row["ending"] for row in rows] == ["tp2", "trail", "floor", "other", "giveback"]
    for row in rows:
        assert (row["n"], row["denominator"], row["r_n"], row["path_n"], row["thin"]) == (0, 0, 0, 0, True)
        assert all(row[key] is None for key in ("share", "lo", "hi", "avg_r", "median_r",
                                                "total_r", "vs_all_out", "best_r", "progress",
                                                "gave_back", "sessions"))
    assert pa.path_exclusions([]) == {"runner_r_unavailable": 0, "manual_close": 0,
                                      "unpathed": 0, "no_tp2_distance": 0}


def test_path_exclusions_on_the_book():
    assert pa.path_exclusions(_runners(_book())) == {
        "runner_r_unavailable": 0, "manual_close": 1, "unpathed": 0, "no_tp2_distance": 0}


def test_path_exclusions_count_the_first_failing_reason():
    plans = [
        _trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0)),   # decidable
        _trade("M0", reason="manual", path=_path(3.0, 3.0)),                        # no price
        _trade("M1", reason="manual", path=_path(3.0, 3.0)),                        # priced
        _trade("U", reason="tp1_runner_trail", runner_r=3.0),                       # no stamp
        _trade("Q", reason="tp1_runner_trail", runner_r=3.0, tp2=110.0, path=_path(3.0, 3.0)),
        _trade("W", reason="tp1_runner_trail", runner_r=3.0, tp2=105.0,
               path={"mfe_r": "x", "ladder": {}}),                                  # both: unpathed first
    ]
    runners = _runners(plans, {"M1": 107.5})
    counts = pa.path_exclusions(runners)
    assert counts == {"runner_r_unavailable": 1, "manual_close": 1, "unpathed": 2,
                      "no_tp2_distance": 1}
    assert sum(counts.values()) == len(runners) - sum(t.decidable for t in runners)
