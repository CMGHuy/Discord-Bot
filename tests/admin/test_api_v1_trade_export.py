"""NG9 — GET /api/v1/trades/export.csv.

Spec v11 keeps this as CSV rather than making the SPA build it: rebuilding
the file client-side would mean shipping every row to the browser purely to
serialise it back, and a browser download is what the user actually wants.

The output must stay byte-identical to the Jinja route's for the same data.
Sub-project 6's acceptance walk lists a CSV byte-compare, and that only has
meaning if the two are the same today.
"""
import json

import pytest

from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trades import _trade

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=()):
        (tmp_path / "plans.json").write_text("[]", encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def test_requires_auth(client):
    assert_error(client.get("/api/v1/trades/export.csv"), "auth", 401)


def test_is_a_csv_attachment(seed, logged_in):
    seed(trades=[_trade("aaaaaaaaaaaaaaaa", plan_id=None, status="win")])
    r = logged_in.get("/api/v1/trades/export.csv")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert "attachment" in r.headers["Content-Disposition"]
    assert "trades.csv" in r.headers["Content-Disposition"]


def test_header_row_is_present_when_there_are_no_trades(seed, logged_in):
    """An empty export must still be a valid CSV with its columns, not a
    zero-byte file -- a spreadsheet opening it should show the schema."""
    seed()
    body = logged_in.get("/api/v1/trades/export.csv").data.decode()
    assert body.startswith("id,ticker,strategy,horizon_key,direction")
