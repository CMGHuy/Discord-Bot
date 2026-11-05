"""v202 V202-1: the dock's heat is the Risk page's heat, in dollars and percent."""
import pytest

from tests.store_seed import seed_store


def _trade(trade_id, ticker, entry, stop, shares, plan_id=None):
    return {"id": trade_id, "plan_id": plan_id, "ticker": ticker, "status": "open",
            "direction": "bullish", "strategy": "VWAP", "horizon_key": "1m",
            "entry": entry, "stop_loss": stop, "take_profit": entry * 1.2,
            "shares": shares, "opened_at": "2026-10-28T12:00:00+00:00"}


#: 200 at risk each on the conftest's 10,000 balance: 2% + 2% = 4% open heat.
#: t2 is a resting order: its plan is still PENDING, but the trade row exists
#: from alert time, so heat counts it (spec section 5, "incl. resting orders").
BOOK = [_trade("t1", "AAPL", 100.0, 95.0, 40),
        _trade("t2", "MSFT", 50.0, 48.0, 100, plan_id="p-resting")]
NULLED = ("open_pct", "cap_pct", "utilisation_pct", "open_amount", "cap_amount",
          "headroom_pct", "headroom_amount", "balance")


@pytest.fixture(autouse=True)
def cap_six(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)


def _live_heat(client):
    response = client.get("/api/v1/live")
    assert response.status_code == 200
    return response.get_json()["heat"]


def test_open_heat_state_is_the_collector_figure(admin_app):
    from swingbot.core.edge.portfolio_state import collect_portfolio_state, open_heat_state
    seed_store("trades", BOOK)
    shared, full = open_heat_state(), collect_portfolio_state()

    assert shared["open_heat"] == pytest.approx(4.0)
    assert shared["open_heat"] == full["open_heat"]
    assert shared["heat_cap"] == full["heat_cap"] == 6.0
    assert shared["balance"] == full["balance"] == 10000.0
    assert shared["availability"]["state"] == "ok"
    assert full["availability"]["heat"] == shared["availability"] | {
        "checked_at": full["availability"]["heat"]["checked_at"]}
    assert sorted(t["id"] for t in shared["open_trades"]) == ["t1", "t2"]


def test_heat_equals_risk_page_for_same_book(logged_in, fresh_risk_cache):
    seed_store("trades", BOOK)
    risk = logged_in.get("/api/v1/risk").get_json()["heat"]
    live = _live_heat(logged_in)
    for key in ("open_pct", "cap_pct", "utilisation_pct"):
        assert live[key] == risk[key], key


def test_heat_in_dollars_and_percent(logged_in):
    seed_store("trades", BOOK)
    heat = _live_heat(logged_in)

    assert (heat["availability"], heat["reason"]) == ("ok", None)
    assert heat["open_pct"] == pytest.approx(4.0)
    assert heat["cap_pct"] == 6.0
    assert heat["utilisation_pct"] == 66.7
    assert (heat["open_amount"], heat["cap_amount"]) == (400.0, 600.0)
    assert (heat["headroom_pct"], heat["headroom_amount"]) == (2.0, 200.0)
    assert heat["balance"] == 10000.0
    assert heat["includes_resting"] is True


def test_heat_is_not_clamped_over_the_cap(logged_in):
    seed_store("trades", [_trade("t9", "NVDA", 100.0, 90.0, 80)])   # 800 at risk: 8%
    heat = _live_heat(logged_in)
    assert heat["utilisation_pct"] == 133.3
    assert (heat["headroom_pct"], heat["headroom_amount"]) == (-2.0, -200.0)


def test_an_empty_book_is_zero_heat_not_unavailable(logged_in):
    heat = _live_heat(logged_in)
    assert heat["availability"] == "ok"
    assert heat["open_pct"] == heat["utilisation_pct"] == heat["open_amount"] == 0.0


def test_unavailable_heat_keeps_every_key_null(logged_in, monkeypatch):
    from swingbot.core.edge import portfolio_state

    def broken(cfg):
        raise ValueError("invalid balance")
    monkeypatch.setattr(portfolio_state, "_balance", broken)
    heat = _live_heat(logged_in)

    assert (heat["availability"], heat["reason"]) == ("unavailable", "invalid_balance")
    assert all(heat[key] is None for key in NULLED)
    assert heat["includes_resting"] is True
