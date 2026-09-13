"""NG7 — the trade commands.

Spec v11 Decision 3: actions that are not CRUD get a verb sub-path, always
POST, rather than being modelled as a PATCH on a status field. "Close this
position" and "cancel this plan" have their own preconditions and their own
failure modes, and pretending they are field assignments hides that.

The domain rules are NOT reinvented here -- they are the ones the Jinja
handlers already enforce:

  cancel  only a PENDING plan            (pages.plan_cancel)
  close   only an ACTIVE/PARTIAL plan,   (pages.plan_close)
          or an `open` legacy trade      (app.close_trade)

Both existing paths also queue a Discord notification through
data/manual_close_notify.json, because the bot is a separate process and
that file is how it learns a human closed something. Dropping that would
silently stop the trade-history channel posting, so it is pinned here.
"""
import json

import pytest

from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trades import _plan, _trade

_LOGIN = {"username": "admin", "password": "admin"}
_PLAN_ID = "55555555-5555-4555-8555-555555555555"
_TRADE_ID = "bbbbbbbbbbbbbbbb"


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(plans=(), trades=()):
        (tmp_path / "plans.json").write_text(json.dumps(list(plans)), encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def notify_queue(tmp_path):
    """The bot's manual-close notification queue."""
    def _read():
        p = tmp_path / "manual_close_notify.json"
        return json.loads(p.read_text()) if p.exists() else []
    return _read


# --- auth ----------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("post", f"/api/v1/trades/{_TRADE_ID}/close"),
    ("post", f"/api/v1/trades/{_PLAN_ID}/cancel"),
    ("delete", f"/api/v1/trades/{_TRADE_ID}"),
    ("post", "/api/v1/trades/clear-open"),
    ("post", "/api/v1/trades/clear-history"),
])
def test_every_command_requires_auth(client, method, path):
    assert_error(getattr(client, method)(path), "auth", 401)


# --- close: plan ---------------------------------------------------------

def test_close_an_active_plan(seed, logged_in, notify_queue):
    seed(plans=[_plan(_PLAN_ID, status="ACTIVE")],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])

    r = logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close")
    assert r.status_code == 200
    assert r.get_json()["status"] == "CLOSED"

    # The linked trade closes too -- otherwise the position would read CLOSED
    # while still counting as open exposure everywhere trades.json is read.
    row = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()
    assert row["status"] == "CLOSED"
    assert row["closed_at"] is not None

    assert notify_queue(), "the bot learns about a manual close via the queue file"


def test_closing_a_plan_queues_a_notify_record_for_that_plan(seed, logged_in, notify_queue):
    """The bot is a separate process; this file is how it learns. A close that
    skips it silently stops the Discord trade-history channel."""
    seed(plans=[_plan(_PLAN_ID, status="ACTIVE")],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])

    logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close")

    assert any(r.get("plan_id") == _PLAN_ID for r in notify_queue())


def test_close_a_pending_plan_is_rejected(seed, logged_in):
    """Only ACTIVE/PARTIAL close. A PENDING plan never filled, so there is
    nothing to close -- it cancels instead."""
    seed(plans=[_plan(_PLAN_ID, status="PENDING")])
    assert_error(logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close"), "invalid", 422)


def test_close_an_already_closed_plan_is_rejected(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID, status="CLOSED")])
    assert_error(logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close"), "invalid", 422)


def test_close_records_a_status_transition(seed, logged_in):
    """status_history drives the lifecycle strip's 'today' counts, and an
    entry with no timestamp is invisible to it."""
    seed(plans=[_plan(_PLAN_ID, status="ACTIVE")])
    logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close")
    history = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()["detail"]["status_history"]
    assert history and history[-1]["status"] == "CLOSED"
    assert history[-1]["at"], "an entry without `at` never counts as closed today"


# --- close: legacy trade -------------------------------------------------

def test_close_an_open_legacy_trade(seed, logged_in, notify_queue):
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="open")])
    r = logged_in.post(f"/api/v1/trades/{_TRADE_ID}/close")
    assert r.status_code == 200
    assert r.get_json()["status"] == "CLOSED"
    assert notify_queue()


def test_close_an_already_closed_legacy_trade_is_rejected(seed, logged_in):
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")])
    assert_error(logged_in.post(f"/api/v1/trades/{_TRADE_ID}/close"), "invalid", 422)


def test_close_unknown_id_is_404(seed, logged_in):
    seed()
    assert_error(logged_in.post(f"/api/v1/trades/{_TRADE_ID}/close"), "not_found", 404)


# --- cancel --------------------------------------------------------------

def test_cancel_a_pending_plan(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID, status="PENDING")])
    r = logged_in.post(f"/api/v1/trades/{_PLAN_ID}/cancel")
    assert r.status_code == 200
    assert r.get_json()["status"] == "CANCELLED"


def test_cancel_an_active_plan_is_rejected(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID, status="ACTIVE")])
    assert_error(logged_in.post(f"/api/v1/trades/{_PLAN_ID}/cancel"), "invalid", 422)


def test_cancel_a_legacy_trade_is_rejected(seed, logged_in):
    """Legacy trades have no PENDING state, so cancelling one is meaningless
    rather than merely disallowed."""
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="open")])
    assert_error(logged_in.post(f"/api/v1/trades/{_TRADE_ID}/cancel"), "invalid", 422)


# --- delete --------------------------------------------------------------

def test_delete_a_legacy_trade(seed, logged_in):
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")])
    assert logged_in.delete(f"/api/v1/trades/{_TRADE_ID}").status_code == 200
    assert logged_in.get("/api/v1/trades").get_json()["total"] == 0


def test_deleting_a_plan_is_refused(seed, logged_in):
    """Plans are not deletable, and that is a deliberate parity decision.

    The Jinja UI has no plan-delete route -- only `/trades/<id>/delete`. A
    plan is a lifecycle record with a legal state machine, and CANCELLED /
    CLOSED are how it ends; erasing one would destroy the history those
    states exist to record. Deleting only the linked trade row would be
    worse still: the plan would survive as a position with no execution.

    Supporting it would need a `PlanStore.delete()` in core, which this
    plan's Global Constraints rule out. Left as an open question for
    sub-project 5.
    """
    seed(plans=[_plan(_PLAN_ID, status="CLOSED")],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID, status="win")])
    assert_error(logged_in.delete(f"/api/v1/trades/{_PLAN_ID}"), "invalid", 422)
    assert logged_in.get("/api/v1/trades").get_json()["total"] == 1, "nothing destroyed"


def test_delete_unknown_id_is_404(seed, logged_in):
    seed()
    assert_error(logged_in.delete(f"/api/v1/trades/{_TRADE_ID}"), "not_found", 404)


# --- bulk clears ---------------------------------------------------------

def test_clear_open_leaves_closed_history(seed, logged_in):
    seed(trades=[
        _trade("aaaaaaaaaaaaaaaa", plan_id=None, status="open"),
        _trade("cccccccccccccccc", plan_id=None, status="win"),
    ])
    r = logged_in.post("/api/v1/trades/clear-open")
    assert r.status_code == 200
    assert r.get_json() == {"removed": 1}
    remaining = logged_in.get("/api/v1/trades").get_json()["items"]
    assert [t["status"] for t in remaining] == ["CLOSED"]


def test_clear_history_leaves_open_trades(seed, logged_in):
    seed(trades=[
        _trade("aaaaaaaaaaaaaaaa", plan_id=None, status="open"),
        _trade("cccccccccccccccc", plan_id=None, status="win"),
    ])
    r = logged_in.post("/api/v1/trades/clear-history")
    assert r.get_json() == {"removed": 1}
    remaining = logged_in.get("/api/v1/trades").get_json()["items"]
    assert [t["status"] for t in remaining] == ["ACTIVE"]


def test_clear_open_on_an_empty_store_is_not_an_error(seed, logged_in):
    seed()
    assert logged_in.post("/api/v1/trades/clear-open").get_json() == {"removed": 0}


# --- close-open (bulk close, NOT clear-open -- see close_open's docstring) --

def test_close_open_closes_active_and_partial(seed, logged_in):
    active_id = "11111111-1111-4111-8111-111111111111"
    partial_id = "22222222-2222-4222-8222-222222222222"
    seed(plans=[
        _plan(active_id, ticker="AAPL", status="ACTIVE"),
        _plan(partial_id, ticker="MSFT", status="PARTIAL"),
    ])

    body = logged_in.post("/api/v1/trades/close-open").get_json()

    assert body["closed"] == 2
    assert body["failed"] == 0
    assert sorted(body["tickers"]) == ["AAPL", "MSFT"]


def test_close_open_leaves_pending_plans_alone(seed, logged_in):
    """A plan that never filled cannot be closed -- cancelling is the act that
    means something for one, and it is a different act."""
    seed(plans=[_plan(_PLAN_ID, status="PENDING")])

    body = logged_in.post("/api/v1/trades/close-open").get_json()

    assert body["closed"] == 0
    row = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()
    assert row["status"] == "PENDING"


def test_close_open_on_an_empty_book_is_a_no_op(seed, logged_in):
    seed()
    assert logged_in.post("/api/v1/trades/close-open").get_json() == \
        {"closed": 0, "failed": 0, "tickers": []}


def test_close_open_queues_one_notify_record_per_position(seed, logged_in, notify_queue):
    seed(plans=[
        _plan("11111111-1111-4111-8111-111111111111", status="ACTIVE"),
        _plan("22222222-2222-4222-8222-222222222222", status="ACTIVE"),
    ])

    logged_in.post("/api/v1/trades/close-open")

    queued = notify_queue()
    assert len([r for r in queued if r.get("kind") == "plan_transition"]) == 2


def test_close_open_scope_open_closes_only_active(seed, logged_in):
    active_id = "11111111-1111-4111-8111-111111111111"
    partial_id = "22222222-2222-4222-8222-222222222222"
    seed(plans=[
        _plan(active_id, ticker="AAPL", status="ACTIVE"),
        _plan(partial_id, ticker="MSFT", status="PARTIAL"),
    ])

    body = logged_in.post("/api/v1/trades/close-open?scope=open").get_json()

    assert body["closed"] == 1
    assert body["tickers"] == ["AAPL"]
    row = logged_in.get(f"/api/v1/trades/{partial_id}").get_json()
    assert row["status"] == "PARTIAL"


def test_close_open_scope_partial_closes_only_partial(seed, logged_in):
    active_id = "11111111-1111-4111-8111-111111111111"
    partial_id = "22222222-2222-4222-8222-222222222222"
    seed(plans=[
        _plan(active_id, ticker="AAPL", status="ACTIVE"),
        _plan(partial_id, ticker="MSFT", status="PARTIAL"),
    ])

    body = logged_in.post("/api/v1/trades/close-open?scope=partial").get_json()

    assert body["closed"] == 1
    assert body["tickers"] == ["MSFT"]
    row = logged_in.get(f"/api/v1/trades/{active_id}").get_json()
    assert row["status"] == "ACTIVE"


def test_close_open_scope_open_partial_matches_the_default(seed, logged_in):
    seed(plans=[
        _plan("11111111-1111-4111-8111-111111111111", ticker="AAPL", status="ACTIVE"),
        _plan("22222222-2222-4222-8222-222222222222", ticker="MSFT", status="PARTIAL"),
    ])

    body = logged_in.post("/api/v1/trades/close-open?scope=open_partial").get_json()

    assert body["closed"] == 2
    assert sorted(body["tickers"]) == ["AAPL", "MSFT"]


def test_close_open_unknown_scope_is_a_400_not_a_silent_fallback(seed, logged_in):
    seed()
    assert_error(
        logged_in.post("/api/v1/trades/close-open?scope=everything"), "invalid", 400,
    )


def test_close_open_reports_failures_without_aborting_the_rest(seed, logged_in, monkeypatch):
    """One bad position must not strand the others half-closed."""
    from swingbot.admin.api_v1 import trade_commands

    seed(plans=[
        _plan("11111111-1111-4111-8111-111111111111", status="ACTIVE"),
        _plan("22222222-2222-4222-8222-222222222222", status="ACTIVE"),
    ])

    calls = {"n": 0}
    real = trade_commands._close_plan

    def flaky(store, plan):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(store, plan)

    monkeypatch.setattr(trade_commands, "_close_plan", flaky)

    body = logged_in.post("/api/v1/trades/close-open").get_json()
    assert body["closed"] == 1
    assert body["failed"] == 1
