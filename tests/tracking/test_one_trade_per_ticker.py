"""One open trade per ticker, and the reversal close.

The guard used to be scoped to direction + near-identical levels, so a second
position slipped through on a different strategy, horizon or entry -- and an
opposite-direction trade was never blocked at all. These pin the new rule and
the early close that is the only sanctioned way past it.
"""
import json

import pytest

from swingbot import config
from swingbot.core.tracking.performance import TradeLog


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    # close_trade_manual fetches a live price to settle with -- default it to
    # "no quote available" so every test not specifically about that price
    # fetch stays offline and deterministic; tests that care override this.
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")
    (tmp_path / "account.json").write_text(json.dumps({
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    }), encoding="utf-8")
    return TradeLog()


def _log(tl, *, direction="bullish", strategy="RSI", horizon="2w",
         entry=100.0, stop=95.0, target=110.0, score=60):
    return tl.log_trade(
        ticker="AAPL", strategy=strategy, horizon_key=horizon, direction=direction,
        confidence_level=3, confidence_label="Medium",
        entry=entry, stop_loss=stop, take_profit=target, confidence_score=score,
    )


# ── the guard ───────────────────────────────────────────────────────────────

def test_no_open_trade_returns_none(tlog):
    assert tlog.open_trade_for_ticker("AAPL") is None


def test_finds_the_open_trade(tlog):
    tid = _log(tlog)
    got = tlog.open_trade_for_ticker("AAPL")
    assert got is not None and got["id"] == tid


@pytest.mark.parametrize("kw", [
    {"strategy": "MACD"},                       # different strategy
    {"horizon": "9m"},                          # different horizon
    {"entry": 250.0, "stop": 240.0, "target": 300.0},   # far-apart levels
    {"direction": "bearish"},                   # opposite direction
])
def test_guard_catches_what_the_old_one_let_through(tlog, kw):
    """Each of these produced a SECOND open trade under the old
    has_open_trade/has_similar_open_trade pair."""
    _log(tlog)
    assert tlog.open_trade_for_ticker("AAPL") is not None, kw
    # the old direction-scoped checks disagree on exactly these cases
    if "direction" in kw or "entry" in kw:
        assert not tlog.has_similar_open_trade(
            "AAPL", kw.get("direction", "bullish"),
            kw.get("entry", 100.0), kw.get("stop", 95.0), kw.get("target", 110.0),
            tol_pct=1.0)


def test_other_tickers_are_unaffected(tlog):
    _log(tlog)
    assert tlog.open_trade_for_ticker("MSFT") is None


def test_a_closed_trade_frees_the_ticker(tlog):
    tid = _log(tlog)
    tlog.close_trade_manual(tid, reason="manual")
    assert tlog.open_trade_for_ticker("AAPL") is None


# ── the reversal close ──────────────────────────────────────────────────────

def test_reversed_close_records_exit_price_and_reason(tlog):
    tid = _log(tlog, entry=100.0)
    closed = tlog.close_trade_reversed(tid, 97.5)
    assert closed is not None
    assert closed["status"] == "closed"
    assert closed["exit_price"] == 97.5
    assert closed["close_reason"] == "reversed"
    assert closed["closed_at"]


def test_reversed_close_is_status_closed_not_win_or_loss(tlog):
    """A reversal books as a scratch: status "closed", never "win"/"loss".

    Note what this does NOT claim. get_stats()'s live win_rate is
    wins/closed, and its "losses" field is len(closed) - len(wins), so a
    scratch sits in that denominator and counts toward that "losses" number --
    pre-existing behaviour that manual admin closes already share (see the
    comment above `closed = ...` in get_stats). The backtest definition
    (win/(win+loss), scratches excluded) is the one a reversal leaves
    untouched. Both are asserted below so the distinction cannot silently
    change.
    """
    tid = _log(tlog)
    tlog.close_trade_reversed(tid, 97.5)
    t = tlog.get_trade_by_id(tid)
    assert t["status"] == "closed"

    stats = tlog.get_stats()
    assert stats["wins"] == 0
    assert stats["closed"] == 1
    # documents the live-dashboard quirk rather than pretending it isn't there
    assert stats["losses"] == 1


def test_reversed_close_is_excluded_from_expectancy_r(tlog):
    """The R-based metric skips anything that is not a win/loss, so a
    reversal cannot distort expectancy even though it dilutes win_rate."""
    tid = _log(tlog)
    tlog.close_trade_reversed(tid, 97.5)
    assert tlog.get_extended_stats()["expectancy_r"] is None


def test_reversed_close_settles_realized_pnl(tlog):
    """A reversal always exits at a real, caller-supplied price, so realized
    P&L must be filled in regardless of whether a live quote happens to be
    reachable for a manual close -- otherwise 'cut the loss sooner' is
    invisible in Trade History."""
    tid = _log(tlog, entry=100.0)
    closed = tlog.close_trade_reversed(tid, 97.5)
    if closed.get("shares"):          # only meaningful when sizing produced shares
        assert closed["realized_pnl_amount"] is not None
        assert closed["realized_pnl_amount"] < 0     # closed below entry on a long


def test_manual_close_without_a_live_quote_realizes_nothing(tlog):
    """A network hiccup on the price fetch must not block the close, and
    must not fabricate an exit price -- P&L stays blank exactly as it did
    before this trade had a real quote to settle against."""
    tid = _log(tlog)
    tlog.close_trade_manual(tid, reason="manual")
    t = tlog.get_trade_by_id(tid)
    assert t["exit_price"] is None
    assert t["realized_pnl_amount"] is None


def test_manual_close_with_a_live_quote_settles_realized_pnl(tlog, monkeypatch):
    """The admin UI's "Close" button is a human override of TIMING, not of
    price -- the position really did exit at whatever the market was doing,
    so once a live quote is available the close must settle exactly like
    any other (exit_price recorded, account balance updated), not leave
    P&L permanently blank the way the old no-price close did."""
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: 105.0)
    tid = _log(tlog, entry=100.0)
    tlog.close_trade_manual(tid, reason="manual")
    t = tlog.get_trade_by_id(tid)
    assert t["exit_price"] == 105.0
    if t.get("shares"):
        assert t["realized_pnl_amount"] is not None
        assert t["realized_pnl_amount"] > 0     # closed above entry on a long


def test_manual_close_settles_the_still_open_remainder_as_a_leg(tlog, monkeypatch):
    """A PARTIAL position (TP1 already banked as one leg) manually closed
    must realize the REMAINDER at the live quote too, not just the TP1
    leg -- otherwise the blended $ P&L silently ignores whatever size was
    still open when the human closed it."""
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: 108.0)
    tid = _log(tlog, entry=100.0, target=110.0)
    tl_trade = tlog.get_trade_by_id(tid)
    tl_trade["legs"].append({"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"})
    tlog._save()
    tlog.close_trade_manual(tid, reason="manual")
    t = tlog.get_trade_by_id(tid)
    assert t["exit_price"] == 108.0
    assert len(t["legs"]) == 2
    assert t["legs"][-1]["fraction"] == pytest.approx(0.5)
    assert t["legs"][-1]["exit_price"] == 108.0
    if t.get("shares"):
        assert t["realized_pnl_amount"] is not None


# ── backfill_exit_price: repairing a past no-price manual close ─────────────

def test_backfill_exit_price_fills_a_recorded_gap(tlog):
    """A trade closed by the OLD close_trade_manual has status='closed' and
    exit_price=None forever -- backfill_exit_price is how that gets repaired
    after the fact, from a price recovered elsewhere (e.g. the historical
    close on the day it closed)."""
    tid = _log(tlog, entry=100.0)
    tlog.close_trade_manual(tid, reason="manual")   # no quote mocked -> no exit_price
    assert tlog.get_trade_by_id(tid)["exit_price"] is None

    ok = tlog.backfill_exit_price(tid, 105.0)
    assert ok is True
    t = tlog.get_trade_by_id(tid)
    assert t["exit_price"] == 105.0
    if t.get("shares"):
        assert t["realized_pnl_amount"] is not None
        assert t["realized_pnl_amount"] > 0


def test_backfill_exit_price_never_overwrites_a_real_close(tlog, monkeypatch):
    """A trade that already settled at a real price must not have that
    replaced by a backfill guess -- this can only fill a gap, never
    second-guess a real close."""
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: 105.0)
    tid = _log(tlog, entry=100.0)
    tlog.close_trade_manual(tid, reason="manual")
    assert tlog.get_trade_by_id(tid)["exit_price"] == 105.0

    assert tlog.backfill_exit_price(tid, 999.0) is False
    assert tlog.get_trade_by_id(tid)["exit_price"] == 105.0


def test_backfill_exit_price_is_a_noop_on_a_still_open_trade(tlog):
    tid = _log(tlog)
    assert tlog.backfill_exit_price(tid, 105.0) is False
    assert tlog.get_trade_by_id(tid)["status"] == "open"


def test_reversing_an_already_closed_trade_is_a_noop(tlog):
    tid = _log(tlog)
    tlog.close_trade_manual(tid, reason="manual")
    assert tlog.close_trade_reversed(tid, 97.5) is None


def test_reversing_an_unknown_id_is_a_noop(tlog):
    assert tlog.close_trade_reversed("nope", 97.5) is None


def test_reversed_close_frees_the_ticker_for_the_inverse(tlog):
    tid = _log(tlog, direction="bullish")
    tlog.close_trade_reversed(tid, 97.5)
    assert tlog.open_trade_for_ticker("AAPL") is None
    new_id = _log(tlog, direction="bearish", entry=97.5, stop=102.0, target=90.0)
    got = tlog.open_trade_for_ticker("AAPL")
    assert got["id"] == new_id and got["direction"] == "bearish"


def test_reversed_close_settles_the_still_open_remainder_as_a_leg(tlog):
    """Same rule close_trade_manual follows: a PARTIAL position reversed after
    TP1 must realize the runner remainder at the reversal price as its own
    leg. Setting exit_price alone left settle_legs pricing only the TP1 leg,
    so the runner's P&L never reached the account."""
    tid = _log(tlog, entry=100.0, target=110.0)
    trade = tlog.get_trade_by_id(tid)
    trade["legs"].append({"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"})
    tlog._save()

    closed = tlog.close_trade_reversed(tid, 97.5)

    assert closed["exit_price"] == 97.5
    assert len(closed["legs"]) == 2
    assert closed["legs"][-1]["fraction"] == pytest.approx(0.5)
    assert closed["legs"][-1]["exit_price"] == 97.5
    assert closed["legs"][-1]["reason"] == "reversed"


def test_reversing_a_plan_linked_trade_closes_its_plan(tlog):
    """The trade row is only half a v2 position; plans.json holds the other
    half, and the plan manager acts on that. Closing only the row left the
    plan ACTIVE -- still stepped every minute, still able to post a close for
    a position already reversed -- next to the inverse's new plan."""
    from swingbot.core.planning.plan_engine import PlanStatus
    from swingbot.core.planning.plan_store import PlanStore
    from tests.planning.test_plan_manager_active import _active

    plan = _active()
    PlanStore().add(plan)
    tid = tlog.log_trade(
        ticker=plan.ticker, strategy="RSI", horizon_key="2w", direction="bullish",
        confidence_level=3, confidence_label="Medium", entry=100.0,
        stop_loss=95.0, take_profit=110.0, plan_id=plan.plan_id)

    tlog.close_trade_reversed(tid, 97.5)

    stored = PlanStore().get(plan.plan_id)
    assert stored.status == PlanStatus.CLOSED
    assert stored.status_history[-1]["reason"] == "reversed"


def test_reversing_a_pending_plans_placeholder_trade_cancels_the_plan(tlog):
    """A stop-entry plan's trade row is logged while the plan is still PENDING.
    PENDING -> CLOSED is not a legal transition, so the reversal cancels it."""
    from swingbot.core.planning.plan_engine import PlanStatus
    from swingbot.core.planning.plan_store import PlanStore
    from tests.planning.test_plan_engine_model import _plan

    plan = _plan(entry_type="stop_entry")          # PENDING by default
    PlanStore().add(plan)
    tid = tlog.log_trade(
        ticker=plan.ticker, strategy="RSI", horizon_key="2w", direction="bullish",
        confidence_level=3, confidence_label="Medium", entry=100.0,
        stop_loss=95.0, take_profit=110.0, plan_id=plan.plan_id)

    tlog.close_trade_reversed(tid, 97.5)

    assert PlanStore().get(plan.plan_id).status == PlanStatus.CANCELLED
