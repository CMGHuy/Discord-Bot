"""Isolated HTTP contract tests for the benchmark endpoint; no stores are opened."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, jsonify

from swingbot import admin
from swingbot.admin.api_v1 import ApiError, api_v1
from swingbot.admin.api_v1 import benchmark


@pytest.fixture
def endpoint(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(api_v1)
    app.register_error_handler(ApiError, lambda exc: (jsonify(error={"code": exc.code, "message": exc.message}), exc.status))
    monkeypatch.setattr(admin, "app", SimpleNamespace(_session_authenticated=lambda: True), raising=False)
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)
    load = Mock(return_value=object())
    build = Mock(return_value={"daily": [{"date": "2026-10-16"}, {"date": "2026-10-15"}, {"date": "2026-10-14"}]})
    monkeypatch.setattr(benchmark, "_now", lambda: now)
    monkeypatch.setattr(benchmark, "_load_inputs", load)
    monkeypatch.setattr(benchmark, "build_benchmark", build)
    return app.test_client(), load, build, now


def test_authentication_is_required(endpoint, monkeypatch):
    client, load, _, _ = endpoint
    monkeypatch.setattr(admin, "app", SimpleNamespace(_session_authenticated=lambda: False))
    response = client.get("/api/v1/analytics/benchmark")
    assert response.status_code == 401
    assert response.json["error"]["code"] == "auth"
    load.assert_not_called()


@pytest.mark.parametrize("query, message", [
    ("?z=1&ledger=main", "unknown parameter 'ledger'"),
    ("?from=2026-13-01", "from must be a YYYY-MM-DD date"),
    ("?before=yesterday", "before must be a YYYY-MM-DD date"),
    ("?from=2026-10-16&to=2026-10-15", "from must be on or before to"),
    ("?capture=DIA", "capture must be one of"),
    ("?limit=0", "limit must be one of 1..500"),
    ("?limit=501", "limit must be one of 1..500"),
])
def test_invalid_parameters_rejected_before_loading(endpoint, query, message):
    client, load, _, _ = endpoint
    response = client.get("/api/v1/analytics/benchmark" + query)
    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid"
    assert message in response.json["error"]["message"]
    load.assert_not_called()


def test_range_capture_and_paging_are_forwarded(endpoint):
    client, load, build, now = endpoint
    response = client.get("/api/v1/analytics/benchmark?from=2026-10-01&to=2026-10-16&capture=QQQ&before=2026-10-16&limit=1")
    assert response.status_code == 200
    assert response.json == {"daily": [{"date": "2026-10-15"}], "daily_has_more": True}
    load.assert_called_once_with(now, date(2026, 10, 1))
    build.assert_called_once_with(load.return_value, start=date(2026, 10, 1), end=date(2026, 10, 16), capture="QQQ")


def test_default_request_uses_spy_and_returns_all_available_rows(endpoint):
    client, load, build, now = endpoint
    response = client.get("/api/v1/analytics/benchmark")
    assert response.status_code == 200
    assert len(response.json["daily"]) == 3
    assert response.json["daily_has_more"] is False
    load.assert_called_once_with(now, None)
    build.assert_called_once_with(load.return_value, start=None, end=None, capture="SPY")
