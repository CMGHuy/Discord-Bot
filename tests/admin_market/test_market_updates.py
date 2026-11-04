from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
import swingbot.admin.app  # noqa: F401  (app first: api_v1 modules import under it)
from swingbot.admin.api_v1 import market_updates
from swingbot.core.marketdata.shared.admin_refresh import PRIORITY_USER, QUEUE_KIND_QUOTE
from tests.admin_market.test_page_loads_never_fetch import network_forbidden  # noqa: F401

NOW = datetime.now(timezone.utc)


def _beat(age_s, cadence=30.0):
    return {"beat_at": NOW - timedelta(seconds=age_s), "cadence_s": cadence,
            "session": "regular", "cycle_ms": 900, "last_error": None}


@pytest.fixture
def changes(monkeypatch):
    rows: list[dict] = []
    monkeypatch.setattr(market_updates, "_cache_changes", lambda since: list(rows))
    return rows


def test_without_since_only_status_is_filled(on_client, market, changes):
    market.heartbeat.row = _beat(10)
    body = on_client.get("/api/v1/market/updates").get_json()
    assert body["quotes"] == [] and "snapshots" not in body
    datetime.fromisoformat(body["cursor"])
    status = body["status"]
    assert status["session"] == "regular" and status["stale_price_s"] == 120
    assert "stale_snapshot_s" not in status
    assert status["heartbeat"]["stalled"] is False and status["heartbeat"]["cadence_s"] == 30.0
    assert status["last_close_at"] is not None


def test_since_lists_changed_quotes_and_in_flight_marks(on_client, market, changes,
                                                        network_forbidden):
    market.quote("MSFT", 110.0, age_s=5)
    changes.append({"key": "quote:MSFT:", "symbol": "MSFT", "fetched_at": NOW,
                    "doc": {}, "updated_at": NOW})
    market.marks.in_flight.add("quote:NVDA")
    market.marks.changed.append({"key": "quote:NVDA", "in_flight": True, "error": None,
                                 "updated_at": NOW})
    since = (NOW - timedelta(minutes=1)).isoformat()
    body = on_client.get("/api/v1/market/updates", query_string={"since": since}).get_json()
    by_symbol = {q["symbol"]: q for q in body["quotes"]}
    assert by_symbol["MSFT"]["price"] == 110.0 and by_symbol["MSFT"]["refreshing"] is False
    assert by_symbol["NVDA"]["price"] is None and by_symbol["NVDA"]["refreshing"] is True
    assert set(by_symbol["MSFT"]) == {"symbol", "price", "as_of", "refreshing", "error"}
    assert market.queue.pending == {}                       # the updates read never enqueues
    assert network_forbidden == []


def test_malformed_since_is_400(on_client, market, changes):
    resp = on_client.get("/api/v1/market/updates?since=yesterday")
    assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "invalid"


def test_heartbeat_not_stalled_when_the_refresher_is_off(on_client, market, changes,
                                                         monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    body = on_client.get("/api/v1/market/updates").get_json()
    assert body["status"]["heartbeat"]["stalled"] is False


def test_refresh_enqueues_and_answers_202(on_client, market):
    resp = on_client.post("/api/v1/market/refresh",
                          json={"symbols": ["msft", "nvda"]})
    assert resp.status_code == 202 and resp.get_json() == {"queued": 2}
    assert market.queue.pending[(QUEUE_KIND_QUOTE, "MSFT")] == PRIORITY_USER


@pytest.mark.parametrize("body", [
    {},
    {"symbols": []},
    {"symbols": "MSFT"},
    {"symbols": [1]},
    {"symbols": [f"S{i}" for i in range(201)]},
])
def test_refresh_rejects_a_bad_body(on_client, market, body):
    resp = on_client.post("/api/v1/market/refresh", json=body)
    assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "invalid"
    assert market.queue.pending == {}


@pytest.mark.parametrize("age_s, expected", [(60, "ok"), (100, "stalled")])
def test_health_reports_refresher_stalled_after_three_cadences(on_client, market,
                                                               age_s, expected):
    market.heartbeat.row = _beat(age_s, cadence=30.0)
    block = on_client.get("/api/v1/system/health").get_json()["refresher"]
    assert block["status"] == expected and block["cadence_s"] == 30.0


def test_health_reports_off_when_the_flag_is_off(on_client, market, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    assert on_client.get("/api/v1/system/health").get_json()["refresher"] == {
        "status": "off", "beat_at": None, "cadence_s": None, "last_error": None}


def test_no_heartbeat_row_reads_stalled(on_client, market):
    assert on_client.get("/api/v1/system/health").get_json()["refresher"]["status"] == "stalled"
