"""NG8 — PUT /api/v1/trades/{id}/note.

Spec v11 maps the legacy `POST /api/journal/<trade_id>/note` here. It is a
PUT rather than a POST because setting a note is idempotent replacement of
a single field, not creation of a new resource.

**A real limitation, preserved rather than papered over.** `set_note`
attaches to an EXISTING journal entry and returns False if there is none.
Journal entries are written when a trade closes, so an open position is
typically not journaled and cannot be noted. The legacy route 404s in that
case and so does this one.

Creating the missing entry here was considered and rejected: journal
records feed the analytics snapshot and `_resolve_outcome` expects a
closed trade, so a half-populated entry for a still-running position could
corrupt the numbers. That is a bigger change than a note endpoint should
make. **Sub-project 5's Notes tab must therefore treat "not journaled yet"
as a state to render, not an error to report** -- see the plan.
"""
import json

import pytest

from tests.admin.api_v1_contract import assert_error, assert_shape
from tests.admin.test_api_v1_trades import _trade

_LOGIN = {"username": "admin", "password": "admin"}
_TRADE_ID = "dddddddddddddddd"


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=(), journal=()):
        (tmp_path / "plans.json").write_text("[]", encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
        (tmp_path / "journal.json").write_text(json.dumps(list(journal)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _entry(trade_id, note=""):
    return {"trade_id": trade_id, "ticker": "AAPL", "strategy": "RSI Divergence",
            "outcome": "win", "note": note, "tags": []}


def test_requires_auth(client):
    assert_error(client.put(f"/api/v1/trades/{_TRADE_ID}/note", json={"note": "x"}), "auth", 401)


def test_set_a_note_on_a_journaled_trade(seed, logged_in):
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")],
         journal=[_entry(_TRADE_ID)])
    r = logged_in.put(f"/api/v1/trades/{_TRADE_ID}/note", json={"note": "took it early"})
    assert r.status_code == 200
    assert_shape(r.get_json(), {"id": str, "note": str})
    assert r.get_json() == {"id": _TRADE_ID, "note": "took it early"}


def test_the_note_persists(seed, logged_in):
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")],
         journal=[_entry(_TRADE_ID)])
    logged_in.put(f"/api/v1/trades/{_TRADE_ID}/note", json={"note": "kept"})
    assert logged_in.get(f"/api/v1/trades/{_TRADE_ID}").get_json()["has_note"] is True


def test_replacing_a_note_overwrites_it(seed, logged_in):
    """PUT, so the second write replaces rather than appends."""
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")],
         journal=[_entry(_TRADE_ID, note="first")])
    logged_in.put(f"/api/v1/trades/{_TRADE_ID}/note", json={"note": "second"})
    assert logged_in.put(
        f"/api/v1/trades/{_TRADE_ID}/note", json={"note": "second"}
    ).get_json()["note"] == "second"


def test_an_empty_note_clears_it(seed, logged_in):
    """Clearing must not 404 or be refused -- deleting a note is a normal
    edit, and `has_note` has to go back to False."""
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")],
         journal=[_entry(_TRADE_ID, note="remove me")])
    r = logged_in.put(f"/api/v1/trades/{_TRADE_ID}/note", json={"note": ""})
    assert r.status_code == 200
    assert logged_in.get(f"/api/v1/trades/{_TRADE_ID}").get_json()["has_note"] is False


def test_a_missing_note_field_is_rejected(seed, logged_in):
    """An absent `note` is a malformed request, not an instruction to clear.
    Treating it as a clear would let a client bug silently destroy text."""
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")],
         journal=[_entry(_TRADE_ID, note="precious")])
    assert_error(logged_in.put(f"/api/v1/trades/{_TRADE_ID}/note", json={}), "invalid", 400)
    assert logged_in.get(f"/api/v1/trades/{_TRADE_ID}").get_json()["has_note"] is True


def test_unknown_trade_is_404(seed, logged_in):
    seed()
    assert_error(
        logged_in.put(f"/api/v1/trades/{_TRADE_ID}/note", json={"note": "x"}),
        "not_found", 404,
    )


def test_a_trade_with_no_journal_entry_is_404(seed, logged_in):
    """The documented limitation: notes attach to journal entries, and those
    are written on close. An open position has none."""
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="open")], journal=[])
    assert_error(
        logged_in.put(f"/api/v1/trades/{_TRADE_ID}/note", json={"note": "x"}),
        "not_found", 404,
    )
