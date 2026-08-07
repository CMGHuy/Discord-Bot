"""One open trade per ticker, and the reversal close.

The guard used to be scoped to direction + near-identical levels, so a second
position slipped through on a different strategy, horizon or entry -- and an
opposite-direction trade was never blocked at all. These pin the new rule and
the early close that is the only sanctioned way past it.
"""
import json

import pytest

from swingbot import config
from swingbot.core.performance import TradeLog


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
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
    """close_trade_manual leaves P&L blank because it records no exit price.
    A reversal exits at a real price, so realized P&L must be filled in --
    otherwise 'cut the loss sooner' is invisible in Trade History."""
    tid = _log(tlog, entry=100.0)
    closed = tlog.close_trade_reversed(tid, 97.5)
    if closed.get("shares"):          # only meaningful when sizing produced shares
        assert closed["realized_pnl_amount"] is not None
        assert closed["realized_pnl_amount"] < 0     # closed below entry on a long


def test_manual_close_still_realizes_nothing(tlog):
    """The settle change must not start realizing P&L for admin-UI closes,
    which record no exit price."""
    tid = _log(tlog)
    tlog.close_trade_manual(tid, reason="manual")
    t = tlog.get_trade_by_id(tid)
    assert t["exit_price"] is None
    assert t["realized_pnl_amount"] is None


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
