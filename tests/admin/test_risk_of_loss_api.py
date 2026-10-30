"""v189 B4 on the wire: the Dashboard's risk-of-loss figure beside enforced
heat, the Risk page's per-row risk-of-loss column, and the golden trade's
realized parts on the Dashboard.

The book: the golden PARTIAL runner (stop at its floor, risk of loss $0,
enforced 100 x 5 = $500 = 5%), an ACTIVE long (100 sh, entry 50, stop 48:
$200 both ways = 2%) and a PENDING plan's placeholder (100 sh, entry 20,
stop 19: enforced 1%, no risk of loss -- nothing is held). Balance 10,000.
"""
import pytest

from swingbot.core.edge import heat
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.analytics.test_golden_partial_trade_metrics import (closed_case,
                                                               golden_closed_trade,
                                                               golden_open_trade,
                                                               load_golden, open_case)
from tests.store_seed import seed_store

G = load_golden()["trade"]
GOLDEN_PID = "11111111-1111-4111-8111-111111111111"
ACTIVE_PID = "22222222-2222-4222-8222-222222222222"
PENDING_PID = "33333333-3333-4333-8333-333333333333"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data",
                        lambda *a, **k: None, raising=False)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data_batch",
                        lambda *a, **k: {}, raising=False)


@pytest.fixture(autouse=True)
def fresh_risk_cache():
    import swingbot.admin.app  # noqa: F401 -- api_v1 imports resolve through the app
    from swingbot.admin.api_v1 import risk
    risk._invalidate_cache()
    yield
    risk._invalidate_cache()


@pytest.fixture
def logged_in(client):
    from swingbot.admin import app as admin_app

    response = client.post("/api/v1/session", json={
        "username": admin_app.ADMIN_USERNAME, "password": admin_app.ADMIN_PASSWORD})
    assert response.status_code == 200
    return client


def _pair(pid, tid, ticker, status, *, entry, stop, working_stop=None, legs=()):
    plan = _plan(pid, ticker=ticker, status=status)
    plan.update({"entry_price": entry, "trigger_price": entry, "stop_loss": stop,
                 "tp1": entry * 1.1, "tp2": entry * 1.2, "working_stop": working_stop,
                 "legs_realized": [dict(leg) for leg in legs]})
    trade = _trade(tid, plan_id=pid, ticker=ticker, status="open")
    trade.update({"entry": entry, "stop_loss": stop, "take_profit": entry * 1.1, "shares": 100})
    return plan, trade


@pytest.fixture
def book(admin_app):
    golden = _pair(GOLDEN_PID, "a" * 16, G["ticker"], "PARTIAL", entry=G["entry"],
                   stop=G["stop_loss"], working_stop=open_case("quote_113")["working_stop"],
                   legs=[G["tp1_leg"]])
    active = _pair(ACTIVE_PID, "b" * 16, "MSFT", "ACTIVE", entry=50.0, stop=48.0)
    pending = _pair(PENDING_PID, "c" * 16, "NVDA", "PENDING", entry=20.0, stop=19.0)
    seed_store("account", {"base_balance": 10000.0, "balance": 10000.0, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})
    seed_store("plans", [golden[0], active[0], pending[0]])
    seed_store("trades", [golden[1], active[1], pending[1]])
    return {"golden": golden, "active": active, "pending": pending}


def test_dashboard_shows_risk_of_loss_beside_enforced_heat(book, logged_in):
    body = logged_in.get("/api/v1/dashboard").get_json()
    assert "risk_used_pct" not in body
    # Enforced heat is unchanged: every open trade, placeholder and original size included.
    expected_heat = heat.open_heat([t for _, t in book.values()], 10000.0)
    assert body["heat_enforced_pct"] == pytest.approx(expected_heat)
    assert body["heat_enforced_pct"] == pytest.approx(8.0)            # 5 + 2 + 1
    # Risk of loss: the golden runner at its floor $0, the ACTIVE long $200, the placeholder none.
    assert body["risk_of_loss_amount"] == pytest.approx(200.0)
    assert body["risk_of_loss_pct"] == pytest.approx(2.0)
    assert body["risk_cap_pct"] is not None


def test_the_golden_runner_alone_has_no_risk_of_loss(admin_app, logged_in):
    plan, trade = _pair(GOLDEN_PID, "a" * 16, G["ticker"], "PARTIAL", entry=G["entry"],
                        stop=G["stop_loss"],
                        working_stop=open_case("quote_113")["working_stop"],
                        legs=[G["tp1_leg"]])
    seed_store("plans", [plan])
    seed_store("trades", [trade])
    body = logged_in.get("/api/v1/dashboard").get_json()
    assert body["risk_of_loss_amount"] == open_case("quote_113")["risk_of_loss_amount"]
    assert body["heat_enforced_pct"] > 0                       # enforced heat still counts it


def test_risk_page_rows_carry_risk_of_loss_and_still_sum_to_open_heat(book, logged_in):
    body = logged_in.get("/api/v1/risk").get_json()
    rows = {r["ticker"]: r for r in body["positions"]}
    assert (rows[G["ticker"]]["risk_of_loss_amount"], rows[G["ticker"]]["risk_of_loss_pct"]) == (0.0, 0.0)
    assert rows["MSFT"]["risk_of_loss_amount"] == pytest.approx(200.0)
    assert rows["MSFT"]["risk_of_loss_pct"] == pytest.approx(2.0)
    assert (rows["NVDA"]["risk_of_loss_amount"], rows["NVDA"]["risk_of_loss_pct"]) == (None, None)
    # The enforced rows keep their invariant and the gauge stays on enforced heat.
    assert sum(r["risk_pct"] for r in body["positions"]) == pytest.approx(
        body["heat"]["open_pct"], abs=0.01)


def test_golden_manual_close_is_two_realized_parts_on_the_dashboard(admin_app):   # admin_app pins FX to identity (v194 B7)
    """Spec § Testing: the Dashboard's realized parts for the golden trade
    closed by hand at 115 -- the TP1 leg ($500) and the runner ($750)."""
    import swingbot.admin.app  # noqa: F401
    from swingbot.admin.api_v1.dashboard import _realized, _realized_parts

    case = closed_case("manual")
    parts = _realized_parts([golden_closed_trade(case, closed_at="2026-08-05T15:00:00+00:00")], "all")
    assert len(parts) == 2
    realized = _realized(parts)
    assert realized["amount"] == pytest.approx(case["realized_pnl_amount"], abs=0.01)
    assert (realized["wins"], realized["losses"]) == (2, 0)


def test_golden_open_runner_has_its_banked_leg_as_one_realized_part(admin_app):   # admin_app pins FX to identity (v194 B7)
    import swingbot.admin.app  # noqa: F401
    from swingbot.admin.api_v1.dashboard import _realized, _realized_parts

    parts = _realized_parts([golden_open_trade()], "all")
    assert len(parts) == 1
    assert _realized(parts)["amount"] == pytest.approx(open_case("quote_113")["banked_amount"])
