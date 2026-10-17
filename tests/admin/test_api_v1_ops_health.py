"""v148: GET /api/v1/system/health -- provider rows and swallowed-error counts.

The System -> Scan panels render exactly this payload, so the shape is pinned
with types (api_v1_contract.assert_shape), not key presence: a rate that
turned into a string would render as "NaN%" without failing anything else.
"""
import json
import logging

import pytest

from tests.admin.api_v1_contract import (NULLABLE_NUMBER, NULLABLE_STR, NUMBER,
                                         assert_error, assert_shape)

_LOGIN = {"username": "admin", "password": "admin"}
_PROVIDER_ROW = {
    "at": str,
    "tickers": NUMBER,
    "provider_fallback_rate": NULLABLE_NUMBER,
    "stale_symbols": NULLABLE_NUMBER,
    "empty_symbols": NULLABLE_NUMBER,
    "empty_rate": NULLABLE_NUMBER,
}
_SWALLOWED_ROW = {
    "process": str,
    "tag": str,
    "count": NUMBER,
    "first_at": NULLABLE_STR,
    "last_at": NULLABLE_STR,
    "last_error": NULLABLE_STR,
}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def _clean_counts():
    """The admin's counter is module-level and this test process is the
    admin: clear it so another test's swallowed errors never show up here."""
    from swingbot.core.infra import swallowed as swallowed_mod
    swallowed_mod.reset()
    yield
    swallowed_mod.reset()


@pytest.fixture
def telemetry_rows(tmp_path, monkeypatch):
    from swingbot.core.scanning import telemetry
    path = tmp_path / "scan_telemetry.jsonl"
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", str(path))

    def write(*rows):
        with path.open("a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
    return write


def _scan_row(minute, **fields):
    return {"at": f"2026-10-09T14:{minute:02d}:00+00:00", "duration_s": 60.0,
            "tickers": 150, **fields}


def _health(client):
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def _beat(**fields):
    from swingbot.core.db.repositories.heartbeat import heartbeat_repo
    heartbeat_repo().beat(fields)


def test_requires_auth(client):
    assert_error(client.get("/api/v1/system/health"), "auth", 401)


def test_nothing_recorded_yet_is_empty_not_an_error(logged_in, telemetry_rows):
    body = _health(logged_in)
    assert_shape(body, {"providers": list, "thresholds": dict, "swallowed": list,
                        "bot_counts_since": NULLABLE_STR})
    assert_shape(body["thresholds"], {"fallback_pct": NUMBER, "empty_pct": NUMBER},
                 where="thresholds")
    assert body["providers"] == []
    assert body["swallowed"] == []
    assert body["bot_counts_since"] is None


def test_provider_rows_are_newest_first_and_capped_at_20(logged_in, telemetry_rows):
    telemetry_rows(*[_scan_row(m, provider_fallback_rate=m / 100, stale_symbols=0,
                               empty_symbols=m, empty_rate=m / 150) for m in range(25)])

    rows = _health(logged_in)["providers"]

    assert len(rows) == 20
    assert rows[0]["at"] == "2026-10-09T14:24:00+00:00"
    assert rows[-1]["at"] == "2026-10-09T14:05:00+00:00"
    assert rows[0]["empty_symbols"] == 24
    for row in rows:
        assert_shape(row, _PROVIDER_ROW, where="provider row")


def test_a_pre_v148_row_reads_as_null_and_deploy_markers_are_skipped(logged_in, telemetry_rows):
    telemetry_rows(
        _scan_row(1),                                          # pre-v148: no provider keys
        {"type": "deploy", "at": "2026-10-09T14:02:00+00:00"},  # not a scan row
        _scan_row(3, provider_fallback_rate=None, stale_symbols=None,
                  empty_symbols=0, empty_rate=0.0),
    )

    rows = _health(logged_in)["providers"]

    assert [r["at"] for r in rows] == ["2026-10-09T14:03:00+00:00",
                                       "2026-10-09T14:01:00+00:00"]
    assert rows[1] == {"at": "2026-10-09T14:01:00+00:00", "tickers": 150,
                       "provider_fallback_rate": None, "stale_symbols": None,
                       "empty_symbols": None, "empty_rate": None}
    assert rows[0]["empty_symbols"] == 0 and rows[0]["provider_fallback_rate"] is None


def test_thresholds_follow_the_live_config(logged_in, telemetry_rows, monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "PROVIDER_FALLBACK_ALERT_PCT", 35)
    monkeypatch.setattr(config, "EMPTY_SYMBOLS_ALERT_PCT", 8)

    assert _health(logged_in)["thresholds"] == {"fallback_pct": 35, "empty_pct": 8}


def test_bot_counts_come_from_the_heartbeat_and_admin_counts_from_memory(
        logged_in, telemetry_rows):
    from swingbot.core.infra import swallowed as swallowed_mod
    _beat(timestamp="2026-10-10T12:00:00+00:00", swallowed={
        "since": "2026-10-10T06:00:00+00:00",
        "counts": {
            "scan.run_bounded": {"count": 7, "first_at": "2026-10-10T06:05:00+00:00",
                                 "last_at": "2026-10-10T11:55:00+00:00",
                                 "last_error": "TimeoutError: cold-fetch chunk 3"},
            "marketdata.price_batch": {"count": 2, "first_at": "2026-10-10T07:00:00+00:00",
                                       "last_at": "2026-10-10T09:00:00+00:00",
                                       "last_error": "KeyError: 'AAPL'"},
        },
    })
    swallowed_mod.swallowed(logging.getLogger("tests.ops_health"), "ops.test_admin_site",
                            ValueError("boom"), "test site failed")

    body = _health(logged_in)

    assert body["bot_counts_since"] == "2026-10-10T06:00:00+00:00"
    ours = {"scan.run_bounded", "marketdata.price_batch", "ops.test_admin_site"}
    got = [(r["process"], r["tag"], r["count"]) for r in body["swallowed"] if r["tag"] in ours]
    assert got == [("bot", "scan.run_bounded", 7),
                   ("bot", "marketdata.price_batch", 2),
                   ("admin", "ops.test_admin_site", 1)]
    for row in body["swallowed"]:
        assert_shape(row, _SWALLOWED_ROW, where="swallowed row")
    admin = next(r for r in body["swallowed"] if r["tag"] == "ops.test_admin_site")
    assert admin["last_error"] == "ValueError: boom"
    counts = [r["count"] for r in body["swallowed"]]
    assert counts == sorted(counts, reverse=True)


def test_a_garbled_heartbeat_block_reads_as_no_bot_rows(logged_in, telemetry_rows):
    _beat(timestamp="2026-10-10T12:00:00+00:00", swallowed="garbled")

    body = _health(logged_in)

    assert [r for r in body["swallowed"] if r["process"] == "bot"] == []
    assert body["bot_counts_since"] is None
