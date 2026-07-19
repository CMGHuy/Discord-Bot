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
