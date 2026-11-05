"""v205 V205-9: the read memo is on for exactly six GET views, never a write.

Spec L1-c: a scope is opened only by an explicit @read_scope on GET routes; a
request context alone never opens one. The route enumeration below fails any
POST/PUT/PATCH/DELETE view that carries the marker, and the behavioural tests
write and then re-read in the same request (trade_commands._plan_row /
_trade_row) to prove a write route sees its own write."""
import pytest

from swingbot.admin.api_v1 import read_scope as rs
from swingbot.core.infra import read_memo
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.admin_perf import golden_book as gb
from tests.admin_perf.test_budgets import _cost
from tests.store_seed import seed_store

NAMES = list(gb.ENDPOINTS)
SCOPED = {"api_v1.dashboard", "api_v1.list_trades", "api_v1.get_live", "api_v1.calendar_pnl",
          "api_v1.calendar_pnl_day", "api_v1.calendar_pnl_day_sparklines"}
_WRITES = {"POST", "PUT", "PATCH", "DELETE"}
_PLAN_ID = "55555555-5555-4555-8555-555555555555"
_TRADE_ID = "bbbbbbbbbbbbbbbb"


def _api_rules():
    from swingbot.admin import app as admin_module
    flask_app = admin_module.app
    return [(rule, flask_app.view_functions[rule.endpoint])
            for rule in flask_app.url_map.iter_rules() if rule.rule.startswith("/api/v1")]


# --- the decorator ---------------------------------------------------------

def test_the_view_runs_inside_a_scope_and_the_scope_ends_with_it():
    seen = []

    @rs.read_scope
    def view(x):
        seen.append(read_memo.active())
        return x * 2

    assert view(21) == 42
    assert seen == [True]
    assert read_memo.active() is False
    assert view.__name__ == "view"
    assert getattr(view, rs.READ_SCOPE_ATTR) is True


def test_an_exception_still_ends_the_scope():
    @rs.read_scope
    def view():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        view()
    assert read_memo.active() is False


def test_the_marker_survives_require_auth(admin_app):
    from swingbot.admin.api_v1.auth import require_auth

    @require_auth
    @rs.read_scope
    def view():
        return "ok"

    assert getattr(view, rs.READ_SCOPE_ATTR, False) is True


# --- which routes carry it -------------------------------------------------

def test_exactly_the_six_read_views_carry_it(admin_app):
    marked = {rule.endpoint for rule, view in _api_rules() if getattr(view, rs.READ_SCOPE_ATTR, False)}
    assert marked == SCOPED
    for rule, _view in _api_rules():
        if rule.endpoint in SCOPED:
            assert not (rule.methods & _WRITES), (rule.rule, rule.methods)


def test_no_mutating_route_carries_it(admin_app):
    writes = [(rule, view) for rule, view in _api_rules() if rule.methods & _WRITES]
    assert len(writes) >= 20, "the enumeration found too few write routes to mean anything"
    offenders = [f"{sorted(rule.methods & _WRITES)} {rule.rule}" for rule, view in writes
                 if getattr(view, rs.READ_SCOPE_ATTR, False)]
    assert offenders == []


# --- what a scoped request does ---------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_each_store_loads_once_per_scoped_request(name, golden_seed, frozen_clock, sql_counted,
                                                  logged_in, monkeypatch):
    _, calls = _cost(logged_in, name, monkeypatch)
    assert calls.count("PlanRepository") <= 1, calls
    # TradeLog._all (read_memo.TRADES) and account._sum_realized_pnl (TRADE_ROWS) are two loads.
    assert calls.count("TradeRepository") <= 2, calls


def test_every_store_read_of_a_scoped_view_is_inside_the_scope(golden_seed, frozen_clock, logged_in,
                                                               monkeypatch):
    from swingbot.core.db.repositories.base import Repository
    seen = []
    real = Repository.list_all

    def spying(self, *args, **kwargs):
        seen.append((type(self).__name__, read_memo.active()))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Repository, "list_all", spying)
    assert logged_in.get(gb.ENDPOINTS["dashboard"]).status_code == 200
    store_reads = [active for cls, active in seen if cls in ("TradeRepository", "PlanRepository")]
    assert store_reads and all(store_reads), seen


def test_the_scope_ends_with_the_request(golden_seed, frozen_clock, logged_in):
    assert logged_in.get(gb.ENDPOINTS["trades"]).status_code == 200
    assert read_memo.active() is False
    assert read_memo.peek(read_memo.TRADES) is None


def test_a_second_request_sees_a_write_made_after_the_first(admin_app, logged_in):
    seed_store("plans", [])
    seed_store("trades", [_trade(_TRADE_ID, plan_id=None, status="open")])
    first = logged_in.get("/api/v1/trades?status=open").get_json()
    seed_store("trades", [_trade(_TRADE_ID, plan_id=None, status="closed")])   # seed_store upserts
    second = logged_in.get("/api/v1/trades?status=open").get_json()
    assert _TRADE_ID in str(first)
    assert _TRADE_ID not in str(second)


# --- write routes, then re-read in the same request -------------------------

@pytest.fixture
def scopes_by_method(monkeypatch):
    """The HTTP method of every request that opened a read scope."""
    import flask
    opened: list[str] = []
    real = read_memo.scope

    def recording():
        opened.append(flask.request.method if flask.has_request_context() else "-")
        return real()

    monkeypatch.setattr(read_memo, "scope", recording)
    return opened


@pytest.fixture
def no_live_quote(monkeypatch):
    """As tests/admin/test_api_v1_trade_commands.py: closes never reach yfinance."""
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price_detail", lambda *a, **k: None)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)


def test_closing_a_plan_returns_the_fresh_row(admin_app, logged_in, no_live_quote, scopes_by_method):
    seed_store("plans", [_plan(_PLAN_ID, status="ACTIVE")])
    seed_store("trades", [_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    assert logged_in.get("/api/v1/trades").status_code == 200       # a scoped read first
    response = logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close")
    assert response.status_code == 200
    assert response.get_json()["status"] == "CLOSED"                 # _plan_row re-read
    rows = logged_in.get("/api/v1/trades").get_json()
    assert "CLOSED" in str(rows) and _PLAN_ID in str(rows)
    assert "POST" not in scopes_by_method and "GET" in scopes_by_method


def test_cancelling_a_plan_returns_the_fresh_row(admin_app, logged_in, no_live_quote, scopes_by_method):
    seed_store("plans", [_plan(_PLAN_ID, status="PENDING")])
    seed_store("trades", [])
    response = logged_in.post(f"/api/v1/trades/{_PLAN_ID}/cancel")
    assert response.status_code == 200
    assert response.get_json()["status"] == "CANCELLED"
    assert "POST" not in scopes_by_method


def test_closing_a_legacy_trade_returns_the_fresh_row(admin_app, logged_in, no_live_quote,
                                                      scopes_by_method):
    seed_store("plans", [])
    seed_store("trades", [_trade(_TRADE_ID, plan_id=None, status="open")])
    response = logged_in.post(f"/api/v1/trades/{_TRADE_ID}/close")
    assert response.status_code == 200
    assert response.get_json()["status"] == "CLOSED"                 # _trade_row re-read
    assert "POST" not in scopes_by_method
