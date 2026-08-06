"""live_cohort_report.py (plan v8 Task V8) -- the weekly live-cohort loop.

The invariant worth testing here is that the report re-derives no stat math
of its own: every number must come from analytics/metrics.py or
gate/wr_math.py, so the report, the admin UI and the gate surfaces can never
disagree about what "win rate" means.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import live_cohort_report as lcr  # noqa: E402


def _t(status, entry, exit_price, direction="bullish", stop=None, closed_at="2026-07-20T00:00:00+00:00", **kw):
    t = {"status": status, "entry": entry, "exit_price": exit_price,
         "direction": direction, "stop_loss": stop if stop is not None else entry * 0.95,
         "closed_at": closed_at}
    t.update(kw)
    return t


def test_pnl_pct_sign_flips_for_bearish():
    # A short that exits BELOW entry made money.
    assert lcr.pnl_pct(_t("win", 100.0, 97.0, "bearish")) == pytest.approx(3.0)
    assert lcr.pnl_pct(_t("loss", 100.0, 103.0, "bearish")) == pytest.approx(-3.0)
    assert lcr.pnl_pct(_t("win", 100.0, 103.0)) == pytest.approx(3.0)


def test_pnl_pct_none_when_unpriced():
    assert lcr.pnl_pct({"entry": 100.0, "direction": "bullish"}) is None
    assert lcr.pnl_pct({"exit_price": 100.0, "direction": "bullish"}) is None


def test_cohort_stats_golden():
    # 3 wins at +1%, 1 loss at -2%; stop is 5% away so 1R = 5%.
    trades = [_t("win", 100.0, 101.0)] * 3 + [_t("loss", 100.0, 98.0)]
    s = lcr.cohort_stats(trades)
    assert (s["n"], s["n_win"], s["n_loss"]) == (4, 3, 1)
    assert s["win_rate"] == pytest.approx(75.0)
    assert s["avg_win_pct"] == pytest.approx(1.0)
    assert s["avg_loss_pct"] == pytest.approx(-2.0)
    assert s["payoff"] == pytest.approx(0.5)
    assert s["total_pct"] == pytest.approx(1.0)          # 3(+1) + 1(-2)
    assert s["expectancy_r"] == pytest.approx((3 * 0.2 + (-0.4)) / 4)


def test_win_rate_excludes_manual_closes_like_the_ui_does():
    """A manual "closed" has no win/loss verdict -- it counts in n and in
    total%, but must not move the win rate. This is metrics.win_rate's rule
    and the report must not invent its own."""
    trades = [_t("win", 100.0, 101.0), _t("loss", 100.0, 98.0),
              _t("closed", 100.0, 100.5)]
    s = lcr.cohort_stats(trades)
    assert s["n"] == 3
    assert s["win_rate"] == pytest.approx(50.0)          # 1 of 2, not 1 of 3


def test_wilson_bound_is_below_the_point_estimate():
    """The methodology doc requires a Wilson lower bound beside every rate
    precisely because a small cohort's point estimate overstates itself."""
    small = lcr.cohort_stats([_t("win", 100.0, 101.0)] * 5)
    big = lcr.cohort_stats([_t("win", 100.0, 101.0)] * 60)
    assert small["win_rate"] == big["win_rate"] == 100.0
    assert small["wilson_lb"] < big["wilson_lb"] < 100.0
    assert small["wilson_lb"] < 60.0        # 5/5 proves very little


def test_empty_cohort_reports_none_not_zero():
    """"no data yet" and "0%" must never look the same."""
    s = lcr.cohort_stats([])
    assert s["n"] == 0
    assert s["win_rate"] is None and s["wilson_lb"] is None
    assert s["payoff"] is None and s["expectancy_r"] is None


def test_filter_since_uses_close_date_and_keeps_earlier_opens():
    trades = [
        _t("win", 100.0, 101.0, closed_at="2026-07-30T23:59:00+00:00"),
        _t("win", 100.0, 101.0, closed_at="2026-08-01T00:00:00+00:00"),
        {"status": "open", "entry": 100.0},          # no closed_at at all
    ]
    kept = lcr.filter_since(trades, "2026-08-01")
    assert len(kept) == 1
    assert kept[0]["closed_at"].startswith("2026-08-01")


def test_build_report_slices_every_dimension():
    trades = [_t("win", 100.0, 101.0, plan_id="p1", tier="A", badge="WEAK",
                 horizon_key="2w", source="confluence", strategy="FVG (bullish)"),
              _t("loss", 100.0, 98.0, strategy="S/R Confluence")]   # legacy: no plan_id
    rep = lcr.build_report(trades)
    assert rep["n_closed"] == 2
    assert set(rep["dimensions"]) == {"Engine path", "Strategy", "Tier", "Badge",
                                      "Horizon", "Direction", "Source", "Close source",
                                      "Legs"}
    assert rep["dimensions"]["Engine path"]["legacy"]["n"] == 1
    assert rep["dimensions"]["Engine path"]["v2"]["n"] == 1
    # Legacy trades carry no tier/badge/source -- rendered as a real "None"
    # cohort, never dropped: that absence is what separates the two paths.
    assert rep["dimensions"]["Tier"]["None"]["n"] == 1
    assert rep["dimensions"]["Source"]["None"]["n"] == 1


def test_open_trades_never_enter_a_cohort():
    trades = [_t("win", 100.0, 101.0), {"status": "open", "entry": 100.0}]
    rep = lcr.build_report(trades)
    assert (rep["n_records"], rep["n_closed"], rep["n_open"]) == (2, 1, 1)
    assert rep["overall"]["n"] == 1


def test_baseline_accepts_both_a_trades_json_and_a_snapshot(tmp_path):
    """--baseline must swallow the frozen archive directly (it is a plain
    trades.json) as well as a snapshot this script emitted, so the v8
    baseline needs no conversion step."""
    trades = [_t("win", 100.0, 101.0), _t("loss", 100.0, 98.0)]
    raw = tmp_path / "trades.json"
    raw.write_text(json.dumps(trades))
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps(lcr.build_report(trades)))

    from_raw = lcr.load_baseline(raw)
    from_snap = lcr.load_baseline(snap)
    assert from_raw["overall"]["n"] == from_snap["overall"]["n"] == 2
    assert from_raw["overall"]["win_rate"] == from_snap["overall"]["win_rate"]


def test_baseline_rejects_an_unrelated_json(tmp_path):
    p = tmp_path / "nope.json"
    p.write_text(json.dumps({"something": "else"}))
    with pytest.raises(SystemExit):
        lcr.load_baseline(p)


def test_diff_names_cohorts_that_appeared_or_vanished(capsys):
    """A cohort that shows up or disappears between two runs is usually the
    finding -- e.g. the legacy path going to zero after V13's cut."""
    base = lcr.build_report([_t("loss", 100.0, 98.0, strategy="S/R Confluence")] * 6)
    cur = lcr.build_report([_t("win", 100.0, 103.0, strategy="FVG (bullish)",
                               plan_id="p1")] * 6)
    lcr.render_diff(cur, base, min_n=5)
    out = capsys.readouterr().out
    assert "NEW in current" in out and "FVG (bullish)" in out
    assert "GONE from current" in out and "S/R Confluence" in out


# -- V29: the close-source split the rollback trigger depends on -------------
# A reconcile-booked close replays missed bars and resolves a bar spanning
# both levels as the stop, so it books the full gap move. Live measurement
# (2026-08-06): -1.041R reconciled (n=32) against -0.342R live-polled (n=30)
# over the same days. If the report pools them, an outage reads as strategy
# decay and V29's trigger fires on the wrong thing.

def test_close_source_is_its_own_dimension():
    trades = [_t("loss", 100.0, 90.0, plan_id="p1", close_source="reconcile"),
              _t("loss", 100.0, 98.0, plan_id="p2", close_source="live")]
    rep = lcr.build_report(trades)
    cs = rep["dimensions"]["Close source"]
    assert cs["reconcile"]["n"] == 1 and cs["live"]["n"] == 1
    # and it must not be conflated with `source` (which strategy found it)
    assert set(rep["dimensions"]["Source"]) != set(cs)


def test_unstamped_closes_are_not_assumed_live():
    """Every trade closed before 2026-08-06 has no stamp. Defaulting those to
    `live` would drop the Aug-4 outage's reconciled closes straight into the
    cohort the rollback trigger watches."""
    rep = lcr.build_report([_t("loss", 100.0, 90.0, plan_id="p1")])
    cs = rep["dimensions"]["Close source"]
    assert cs["unstamped"]["n"] == 1
    assert "live" not in cs


def test_legs_cohort_separates_scaled_out_wins():
    """V4 Step 3. A v2 win with no legs was closed by something other than the
    plan manager -- the failure is silent, so it needs a standing cohort."""
    trades = [_t("win", 100.0, 101.0, plan_id="p1",
                 legs=[{"fraction": 0.5}, {"fraction": 0.5}]),
              _t("win", 100.0, 101.0, plan_id="p2")]
    cohorts = lcr.build_report(trades)["dimensions"]["Legs"]
    assert cohorts["2+ legs"]["n"] == 1
    assert cohorts["0 legs"]["n"] == 1
