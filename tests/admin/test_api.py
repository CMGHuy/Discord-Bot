"""Tests for the /api/* JSON blueprint."""
import json


def test_health_requires_auth_json(client):
    r = client.get("/api/health")
    assert r.status_code == 401
    assert r.get_json() == {"error": "auth"}


def test_health_ok(client, auth):
    r = client.get("/api/health", headers=auth)
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "versions" in body and "ui" in body["versions"]


def test_api_stats_returns_snapshot_verbatim(client, auth, monkeypatch):
    fake_snapshot = {"built_at": "2026-07-11T00:00:00+00:00", "by": {}, "calibration": {}}
    monkeypatch.setattr("swingbot.admin.api.load_snapshot", lambda max_age_seconds=3600: fake_snapshot)
    r = client.get("/api/stats", headers=auth)
    assert r.status_code == 200
    assert r.get_json() == fake_snapshot


def test_api_stats_self_heals_when_missing(client, auth, monkeypatch):
    calls = {"refresh": 0}

    def fake_refresh():
        calls["refresh"] += 1
        return {"built_at": "just-built", "by": {}, "calibration": {}}

    monkeypatch.setattr("swingbot.admin.api.load_snapshot", lambda max_age_seconds=3600: None)
    monkeypatch.setattr("swingbot.admin.api.refresh_snapshot", fake_refresh)
    r = client.get("/api/stats", headers=auth)
    assert r.get_json()["built_at"] == "just-built"
    assert calls["refresh"] == 1


def test_api_stats_fresh_query_forces_refresh(client, auth, monkeypatch):
    calls = {"refresh": 0}

    def fake_refresh():
        calls["refresh"] += 1
        return {"built_at": "forced", "by": {}, "calibration": {}}

    monkeypatch.setattr("swingbot.admin.api.load_snapshot", lambda max_age_seconds=3600: {"built_at": "stale"})
    monkeypatch.setattr("swingbot.admin.api.refresh_snapshot", fake_refresh)
    r = client.get("/api/stats?fresh=1", headers=auth)
    assert r.get_json()["built_at"] == "forced"
    assert calls["refresh"] == 1
