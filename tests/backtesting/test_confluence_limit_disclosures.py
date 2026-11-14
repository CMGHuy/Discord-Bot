"""V212-14/14b: v212 disclosures -- each figure reads the right population;
nothing here gates."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import confluence_limit_disclosures as cld


def row(arm, n, r, *, filled=True, dropped=None, direction="bullish", **kw):
    day = f"2021-03-{n + 1:02d}"
    outcome = "dropped" if dropped else ("not_triggered" if not filled else
                                         ("win" if r > 0 else "loss"))
    base = {"key": f"T{n}|4w|{day}|{direction}", "arm": arm, "ticker": f"T{n}",
            "direction": direction, "entry_date": day, "fill_date": day,
            "exit_date": f"2021-03-{n + 3:02d}", "expiry_date": f"2021-03-{n + 4:02d}",
            "market": 100.0, "stop_loss": 97.0, "filled": filled and not dropped,
            "dropped": dropped, "outcome": outcome,
            "r_net": r if filled and not dropped else None, "gap_stopped": False,
            "gap_stop_r_from_limit": None, "early_stop": False, "wick_through": False,
            "atr14_pct": 2.5}
    return {**base, **kw}


def census(n, *, drop=None, state="filled"):
    return {"key": f"T{n}|4w|2021-03-{n + 1:02d}|bullish", "entry_date": f"2021-03-{n + 1:02d}",
            "d_pct": 2.0 + n, "drops": {"f0.5": drop},
            "fill_state": {"f0.5": None if drop else state}}


ARM = [row("f0.5", 0, 2.0), row("f0.5", 1, -1.0, early_stop=True, wick_through=True),
       row("f0.5", 2, -0.05, gap_stopped=True, gap_stop_r_from_limit=-1.4, atr14_pct=5.0),
       row("f0.5", 3, None, filled=False), row("f0.5", 4, None, dropped="limit_rr_fail")]
REF = [row("ref", n, r) for n, r in enumerate((1.0, -1.0, -1.0, 1.5, 0.5))]
CENSUS = [census(0), census(1), census(2, state="gap_stopped"), census(3, state="tp1_cancel"),
          census(4, drop="limit_rr_fail")]
SPY = {"2021-03-01": -1.5, "2021-03-02": 0.3}
EARNINGS = {"T1": ["2021-03-04"], "T0": ["2021-03-01"]}


@pytest.fixture(autouse=True)
def _risk(monkeypatch):
    monkeypatch.setattr(config, "RISK_PER_TRADE_PCT", 1.0, raising=False)


def test_paired_delta_scores_unfilled_and_dropped_alerts_as_zero():
    paired = cld.paired_delta(ARM, REF)
    assert paired["alerts"] == 5
    # arm 2, -1, -0.05, 0, 0 against ref 1, -1, -1, 1.5, 0.5
    assert paired["mean_delta_r"] == pytest.approx((1 + 0 + 0.95 - 1.5 - 0.5) / 5)
    assert paired["share_positive"] == pytest.approx(2 / 5)
    assert paired["dollar_per_alert_arm"] == pytest.approx(100 * 0.95 / 5)
    assert paired["dollar_per_alert_ref"] == pytest.approx(100 * 1.0 / 5)
    assert cld.filled_dollars(ARM) == {"fills": 3, "total": pytest.approx(95.0),
                                       "per_fill": pytest.approx(95.0 / 3)}


def test_scope_d_range_and_binding_shares_come_from_the_census():
    scope = cld.scope_counts(CENSUS, "f0.5")
    assert (scope["in_scope"], scope["kept"], scope["drops"]) == (5, 4, {"limit_rr_fail": 1})
    assert scope["d_range"] == [2.0, 5.0]
    assert (scope["tp1_cancel_share"], scope["expiry_share"]) == (0.25, 0.0)
    assert scope["fill_states"] == {"filled": 2, "gap_stopped": 1, "tp1_cancel": 1}


def test_adverse_gap_and_stop_run():
    adv = cld.adverse(ARM)
    assert adv["effective_stop_from_m_pct"] == pytest.approx(3.0)
    assert (adv["early_stop_share"], adv["wick_through_share"]) == (pytest.approx(1 / 3), 0.5)
    assert (adv["gap_stops"], adv["gap_stop_worst_r"], adv["gap_stop_worst_r_from_limit"]) == (
        1, -0.05, -1.4)
    assert adv["gap_stop_max_per_day"] == 1


def test_atr_buckets_count_non_dropped_alerts():
    assert [(b["bucket"], b["alerts"], b["fills"]) for b in cld.by_atr(ARM)] == [
        ("2-3%", 3, 2), (">=4.5%", 1, 1)]


def test_spy_down_days_and_distinct_fill_days():
    spy = cld.spy_days(ARM, SPY)
    assert (spy["down"]["n"], spy["other"]["n"], spy["distinct_fill_days"]) == (1, 2, 3)
    assert spy["down"]["expr"] == pytest.approx(2.0) and spy["spy_missing"] == 1


def test_earnings_inside_the_three_bar_window():
    # T1's report (03-04) falls after its signal (03-02) and by its expiry (03-05);
    # T0's report is on the signal date itself, so outside the window
    out = cld.earnings_share(ARM, EARNINGS)
    assert (out["with_earnings"], out["fills"]) == (1, 3)
    assert out["share"] == pytest.approx(1 / 3) and out["tickers_without_calendar"] == 1


def test_alert_volume_per_day_counts_weekdays_spanned():
    cen = [census(0), census(4)]                       # Mon 2021-03-01 .. Fri 03-05
    arm = [row("f0.5", n, 1.0) for n in range(4)] + [row("f0.5", 4, None, dropped="x")]
    assert cld.alert_volume_per_day(cen, arm) == pytest.approx(4 / 5)
    assert cld.alert_volume_per_day([], arm) == 0.0


def test_spy_changes():
    frame = pd.DataFrame({"Close": [100.0, 98.0, 99.0]},
                         index=pd.to_datetime(["2021-03-01", "2021-03-02", "2021-03-03"]))
    assert cld.spy_changes(frame) == {"2021-03-02": pytest.approx(-2.0),
                                      "2021-03-03": pytest.approx((99.0 / 98.0 - 1) * 100)}


def test_slim_rows_and_empty_inputs_do_not_crash():
    slim = [{"key": "k", "arm": "f0.5", "ticker": "T", "direction": "bullish",
             "entry_date": "2021-03-01", "fill_date": "2021-03-01", "exit_date": "2021-03-05",
             "filled": True, "dropped": None, "outcome": "loss", "r_net": -1.0}]
    assert cld.adverse(slim)["effective_stop_from_m_pct"] is None
    assert cld.earnings_share(slim, {"T": ["2021-03-02"]})["with_earnings"] == 0
    assert [b["bucket"] for b in cld.by_atr(slim)] == ["unknown"]
    assert cld.paired_delta([], [])["mean_delta_r"] is None
    assert cld.scope_counts([], None)["d_range"] is None
    assert cld.filled_dollars([])["per_fill"] is None


KEPT = {"arm": ARM[:3], "ref": REF,
        "arm_result": {"trades_taken": 3, "trades_skipped": 1, "max_dd_pct": 1.2,
                       "notional_capped": 1, "skip_reasons": {"heat": 1}},
        "ref_result": {"trades_taken": 5, "trades_skipped": 0, "max_dd_pct": 2.0,
                       "notional_capped": 0, "skip_reasons": {}}}


@pytest.fixture
def book():
    return cld.disclosures(ARM, REF, CENSUS, spy=SPY, earnings=EARNINGS, portfolio=KEPT)


def test_disclosures_assemble_every_section(book):
    assert book["cell"] == "f0.5"
    assert book["paired"] == cld.paired_delta(ARM, REF)
    assert book["scope"] == cld.scope_counts(CENSUS, "f0.5")
    assert book["adverse"] == cld.adverse(ARM) and book["atr"] == cld.by_atr(ARM)
    assert book["spy"] == cld.spy_days(ARM, SPY)
    assert book["earnings"] == cld.earnings_share(ARM, EARNINGS)
    assert book["alert_volume_per_day"] == cld.alert_volume_per_day(CENSUS, ARM)


def test_portfolio_skips_are_the_heat_at_fill_cancels(book):
    arm = book["portfolio"]["arm"]
    assert (arm["heat_at_fill"], arm["notional_capped_share"]) == (1, 0.25)
    assert (arm["submitted"], arm["taken"]) == (4, 3)
    assert book["portfolio"]["ref"]["heat_at_fill"] == 0
    reasons = {"heat": 1, "sector": 2, "cluster": 3, "max_open": 4, "one_per_ticker": 9}
    assert cld.cap_skips({"skip_reasons": reasons})["heat_at_fill"] == 10


def test_per_direction_and_risk(book):
    bull = book["per_direction"][0]
    assert (bull["direction"], bull["arm"]["n"], bull["ref"]["n"]) == ("bullish", 3, 5)
    assert bull["arm"]["wr"] == pytest.approx(100 / 3)
    assert book["per_direction"][1]["arm"] == {"n": 0, "expr": None, "wr": None}
    risk = book["risk"]["arm"]
    assert risk["worst_day_r"] == pytest.approx(-1.0)
    # 03-03: T0 (03-01..03-03), T1 (03-02..03-04) and T2 (03-03..03-05) all open
    assert (risk["max_open_positions"], risk["max_open_risk_pct"]) == (3, 3.0)
    assert risk["max_drawdown_r"] == pytest.approx(1.05)      # +2, then -1 and -0.05
    assert 0.0 <= risk["p_ruin"] <= 1.0


def test_empty_inputs_disclose_without_crashing():
    empty = {"arm": [], "ref": [], "arm_result": {}, "ref_result": {}}
    d = cld.disclosures([], [], [], spy={}, earnings={}, portfolio=empty)
    assert d["cell"] is None and d["paired"]["alerts"] == 0
    assert d["risk"]["arm"] == {"n": 0, "worst_day_r": None, "max_open_positions": 0,
                                "max_open_risk_pct": 0.0, "max_drawdown_r": None,
                                "p_ruin": None, "max_dd_p95": None}
    assert d["portfolio"]["arm"]["notional_capped_share"] is None
    assert "D range n/a" in cld.render_disclosures(d)


def test_render_prints_every_section_and_the_touch_sensitivity(book):
    text = cld.render_disclosures({"window": "train", "cells": [book],
                                   "touch": [{"cell": "f0.5", "n": 4, "ref_n": 5, "expr": 0.1,
                                              "ref_expr": 0.0, "wr": 50.0, "ref_wr": 60.0,
                                              "passes": False}]})
    for needle in ("## Disclosures (train", "### Cell f0.5", "D range 2.00%-5.00%",
                   "direction", "Paired per-alert", "Gap-through-stop", "Stop-run",
                   "ATR14%", "SPY down day", "Earnings", "Notional cap cut (arm)", "heat 1",
                   "Worst day R", "P(ruin)", "upper bound", "Touch-fill sensitivity", "n/a"):
        assert needle in text, needle
    assert "never gating" in text


def test_render_reads_a_json_round_trip(book):
    import json
    blob = json.loads(json.dumps({"window": "validation", "cells": [book], "touch": []}))
    assert cld.render_disclosures(blob) == cld.render_disclosures(
        {"window": "validation", "cells": [book]})
