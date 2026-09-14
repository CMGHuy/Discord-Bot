import datetime as dt

import pytest

from swingbot.core.tracking.performance import TradeLog, closed_r_multiple, expand_trade_legs
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_pending import _pending


def test_full_lifecycle_writes_two_leg_win(tmp_path):
    feed = FakePriceFeed()
    feed.set_series("AAPL", [
        106.0,    # fill (trigger 105)
        116.0,    # tp1 partial (tp1 110 -> touched; entry 106, stop 104)
        140.0,    # runner ratchets trail well above entry
        118.0,    # pierces trail -> tp1_runner_trail close
    ])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    log = TradeLog(path=str(tmp_path / "trades.json"))
    store.add(_pending(stop_loss=104.0, tp1=110.0, tp2=None))
    mgr = PlanManager(store, feed.get_price, atr_fn=lambda t: 2.0,
                      trade_log=log)

    transitions = []
    for day in range(27, 31):
        now = dt.datetime(2026, 8, day, 12, 0, tzinfo=US_MARKET_TZ)
        transitions.extend(e.transition for e in mgr.poll(now=now))
    assert transitions == ["filled", "tp1_partial", "closed"] or \
           transitions == ["filled", "tp1_partial", "be_moved", "closed"]

    log.refresh()
    [t] = [t for t in log.get_trades(limit=10) if t.get("plan_id") == "p1"]
    assert t["status"] == "win"
    assert len(t["legs"]) == 2
    assert t["legs"][0]["reason"] == "tp1"
    assert t["legs"][1]["reason"].startswith("tp1_runner")
    assert t["realized_pnl_amount"] is not None or t["shares"] is None


def test_extended_stats_uses_leg_aware_closed_r_multiple(tmp_path):
    trade = {
        "status": "win",
        "direction": "bullish",
        "entry": 100.0,
        "stop_loss": 95.0,
        "exit_price": 100.25,
        "legs": [
            {"fraction": 0.5, "r": 2.0, "exit_price": 110.0},
            {"fraction": 0.5, "r": 0.05, "exit_price": 100.25},
        ],
    }
    log = TradeLog(path=str(tmp_path / "trades.json"))

    # With leg expansion, each leg is counted as its own outcome, so expectancy_r
    # becomes the average of individual leg R-multiples (2.0 and 0.05), which is 1.025.
    # This equals the fraction-weighted sum (0.5*2.0 + 0.5*0.05 = 1.025) by coincidence
    # of equal weighting -- the difference from closed_r_multiple(trade) (1.02) is only
    # rounding: the original rounds the blended sum, but expanded legs average pre-rounded values.
    assert log.get_extended_stats(trades=[trade])["expectancy_r"] == pytest.approx(1.025)


def _closed(r_target: float, status: str) -> dict:
    """A single-leg closed trade whose closed_r_multiple works out to
    r_target exactly, via the plain entry/stop/exit formula (risk = 5)."""
    return {
        "status": status,
        "direction": "bullish",
        "entry": 100.0,
        "stop_loss": 95.0,
        "exit_price": 100.0 + r_target * 5.0,
        "legs": [],
    }


def test_extended_stats_reports_payoff_ratio_over_the_same_legs_as_expectancy(tmp_path):
    log = TradeLog(path=str(tmp_path / "trades.json"))
    # Two wins at +2R and +4R, two losses at -1R and -1R.
    # expectancy_r = (2 + 4 - 1 - 1) / 4 = 1.0
    # payoff_ratio = mean(2, 4) / |mean(-1, -1)| = 3.0
    trades = [
        _closed(2.0, "win"),
        _closed(4.0, "win"),
        _closed(-1.0, "loss"),
        _closed(-1.0, "loss"),
    ]

    stats = log.get_extended_stats(trades=trades)
    assert stats["expectancy_r"] == pytest.approx(1.0)
    assert stats["payoff_ratio"] == pytest.approx(3.0)


def test_extended_stats_payoff_ratio_is_none_with_no_losses(tmp_path):
    log = TradeLog(path=str(tmp_path / "trades.json"))
    assert log.get_extended_stats(trades=[_closed(2.0, "win")])["payoff_ratio"] is None


def test_close_plan_trade_journals_and_refreshes_snapshot(tmp_path, monkeypatch):
    log = TradeLog(path=str(tmp_path / "trades.json"))
    log._trades = [{
        "id": "t-close", "plan_id": "p-close", "ticker": "AAPL",
        "status": "open", "direction": "bullish", "entry": 100.0,
        "stop_loss": 95.0, "shares": None, "legs": [],
    }]
    journaled = []
    refreshed = []
    monkeypatch.setattr("swingbot.core.tracking.performance._journal_close_safely", journaled.append)
    monkeypatch.setattr("swingbot.core.tracking.performance._refresh_snapshot_safely", lambda: refreshed.append(True))

    log.close_plan_trade("p-close", {"fraction": 1.0, "exit_price": 105.0, "r": 1.0}, "win")

    assert [trade["id"] for trade in journaled] == ["t-close"]
    assert refreshed == [True]

def test_expand_trade_legs_passes_through_a_trade_with_no_legs():
    trade = {"status": "win", "shares": 10, "entry": 100.0,
             "direction": "bullish", "stop_loss": 95.0, "exit_price": 110.0}
    assert expand_trade_legs(trade) == [trade]


def test_expand_trade_legs_splits_a_fully_closed_scaled_out_trade():
    trade = {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 118.0,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 118.0, "r": 3.6, "reason": "tp1_runner_tp2"},
        ],
    }
    rows = expand_trade_legs(trade)
    assert len(rows) == 2
    assert [r["shares"] for r in rows] == [5.0, 5.0]
    assert [r["exit_price"] for r in rows] == [110.0, 118.0]
    assert [r["status"] for r in rows] == ["win", "win"]


def test_expand_trade_legs_adds_the_open_remainder():
    trade = {
        "status": "open", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": None,
        "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}],
    }
    rows = expand_trade_legs(trade)
    assert len(rows) == 2
    assert rows[0]["status"] == "win" and rows[0]["shares"] == 5.0
    assert rows[1]["status"] == "open" and rows[1]["shares"] == 5.0
    assert rows[1]["exit_price"] is None


def test_expand_trade_legs_classifies_a_negative_r_leg_as_loss():
    trade = {
        "status": "closed", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 98.0,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 98.0, "r": -0.4, "reason": "manual"},
        ],
    }
    rows = expand_trade_legs(trade)
    assert [r["status"] for r in rows] == ["win", "loss"]


def test_get_extended_stats_counts_each_leg_as_its_own_outcome(tmp_path):
    trade = {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 118.0, "confidence_level": None,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 90.0, "r": -0.5, "reason": "manual"},
        ],
    }
    log = TradeLog(path=str(tmp_path / "trades.json"))
    stats = log.get_stats(trades=[trade])
    assert stats["total"] == 2 and stats["wins"] == 1 and stats["losses"] == 1


def test_expand_trade_legs_falls_back_to_the_price_sign_when_a_leg_has_no_r():
    """A leg appended without an `r` (plan_manager's stop-out mirror path
    writes some legs that shape) must NOT read as a win just because a
    missing r folds to 0. Same rule the admin API's `_leg_outcome` already
    applies: the sign of the realized move, direction-adjusted."""
    trade = {
        "status": "loss", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 95.0,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": None, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 95.0, "reason": "stop"},
        ],
    }
    assert [r["status"] for r in expand_trade_legs(trade)] == ["win", "loss"]


def test_expand_trade_legs_price_sign_fallback_is_direction_adjusted():
    """On a bearish position an exit BELOW entry is the win."""
    trade = {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bearish",
        "stop_loss": 105.0, "exit_price": 90.0,
        "legs": [
            {"fraction": 0.5, "exit_price": 90.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 104.0, "reason": "stop"},
        ],
    }
    assert [r["status"] for r in expand_trade_legs(trade)] == ["win", "loss"]


def test_expand_trade_legs_keeps_a_zero_r_leg_a_win():
    """A leg that really did record r == 0 (scratched at breakeven) stays a
    win -- the plan's Global Constraint is `r >= 0`. Only a MISSING r falls
    through to the price-sign rule."""
    trade = {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 100.0,
        "legs": [{"fraction": 1.0, "exit_price": 100.0, "r": 0.0, "reason": "be"}],
    }
    assert [r["status"] for r in expand_trade_legs(trade)] == ["win"]


def _scaled_out_win_then_loss_trade() -> dict:
    """One scaled-out position: a +2R TP1 leg and a -0.5R runner leg, whose
    blended whole-position outcome is a single `win`. The fixture the
    expand/no-expand contrast is measured on."""
    return {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 118.0, "confidence_level": 3,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 90.0, "r": -0.5, "reason": "manual"},
        ],
    }


def test_get_stats_expand_false_keeps_the_pre_v79_blended_outcome(tmp_path):
    """`expand=False` is what live confidence scoring reads (analyze.py's
    `track_record`). It must see exactly what it saw before v79: ONE closed
    outcome per position, at the blended 100% win rate -- not two legs at
    50%. The confidence formula pays every counted win the scenario's full
    reward:risk, which a ~1R TP1 leg does not earn."""
    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade = _scaled_out_win_then_loss_trade()

    unexpanded = log.get_stats(trades=[trade], expand=False)
    assert unexpanded["total"] == 1
    assert unexpanded["closed"] == 1
    assert unexpanded["wins"] == 1
    assert unexpanded["losses"] == 0
    assert unexpanded["win_rate"] == 100.0

    # ...while the default (dashboards, stat cards) still gets v79's legs.
    expanded = log.get_stats(trades=[trade])
    assert (expanded["total"], expanded["wins"], expanded["losses"]) == (2, 1, 1)
    assert expanded["win_rate"] == 50.0


def test_get_stats_expand_false_honours_the_confidence_filter(tmp_path):
    """The live call site passes a base level positionally; `expand=False`
    must not disturb that filter."""
    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade = _scaled_out_win_then_loss_trade()

    assert log.get_stats(3, trades=[trade], expand=False)["closed"] == 1
    assert log.get_stats(4, trades=[trade], expand=False)["closed"] == 0


def test_get_extended_stats_expand_false_uses_the_blended_r(tmp_path):
    """Unexpanded, expectancy is the position's own fraction-weighted R
    (0.5*2.0 + 0.5*-0.5 = 0.75), one value -- not one per leg."""
    log = TradeLog(path=str(tmp_path / "trades.json"))
    stats = log.get_extended_stats(trades=[_scaled_out_win_then_loss_trade()], expand=False)
    assert stats["r_multiples_count"] == 1
    assert stats["expectancy_r"] == pytest.approx(0.75)


def test_get_extended_stats_avg_holding_days_position_accurate_not_leg_doubled(tmp_path):
    # Scaled-out trade with 2 legs should contribute ONE duration value to avg_holding_days,
    # not TWO (one per leg). Without the fix, both legs would share the same closed_at/opened_at
    # and silently double the position's weight in the average.
    trade = {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 118.0, "confidence_level": None,
        "opened_at": "2026-09-01T09:30:00+00:00",
        "closed_at": "2026-09-05T16:00:00+00:00",  # 4 days 6.5 hours
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 118.0, "r": 3.6, "reason": "tp1_runner_tp2"},
        ],
    }
    log = TradeLog(path=str(tmp_path / "trades.json"))
    stats = log.get_extended_stats(trades=[trade])
    # The position was open for 4 days + 6.5 hours = ~4.27 days
    # avg_holding_days should be ~4.27, not ~8.54 (which would result from each leg contributing ~4.27)
    # This verifies that holding_days is position-accurate, not leg-doubled
    assert stats["avg_holding_days"] == pytest.approx(4.270833333333333)


@pytest.fixture(autouse=True)
def _rth_gate_off(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
