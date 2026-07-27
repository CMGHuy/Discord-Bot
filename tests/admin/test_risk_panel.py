"""Flask test-client tests for the admin risk panel (Task E54).

Uses the existing tests/admin/conftest.py fixtures: `client` is an
UNAUTHENTICATED Flask test client (routes are guarded by @require_auth,
HTTP Basic Auth), so every request here passes the separate `auth` fixture
(a Basic Auth header dict) explicitly via `headers=auth`.
"""


def test_risk_page_renders(client, auth):
    resp = client.get("/risk", headers=auth)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Portfolio heat" in body and "Kill switch" in body


def test_killswitch_toggle_roundtrip(client, auth, tmp_path, monkeypatch):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "ks.json"))
    resp = client.post("/risk/killswitch", data={"action": "on"}, headers=auth)
    assert resp.status_code in (200, 302)
    assert throttle.kill_state()["on"] is True
    client.post("/risk/killswitch", data={"action": "off"}, headers=auth)
    assert throttle.kill_state()["on"] is False


def test_risk_page_shows_scan_health_sparkline(client, auth, tmp_path, monkeypatch):
    """Task E82: recent_telemetry(50)'s durations render as an inline SVG
    sparkline; patching engine.TELEMETRY_PATH directly (rather than relying
    on module-reload order) keeps this isolated regardless of when
    swingbot.core.scanning.engine first got imported this test session."""
    from swingbot.core.scanning import engine
    telemetry_path = str(tmp_path / "scan_telemetry.jsonl")
    monkeypatch.setattr(engine, "TELEMETRY_PATH", telemetry_path)
    for d in [60] * 20:
        engine.log_scan_telemetry({"duration_s": d, "tickers": 150})
    engine.log_scan_telemetry({"duration_s": 150, "tickers": 150})   # slowdown trigger

    resp = client.get("/risk", headers=auth)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Scan health" in body
    assert "<svg" in body and "<polyline" in body
    assert "150.0s" in body   # latest duration surfaced
    assert "more than 2x the median" in body


def test_risk_page_scan_health_empty_before_first_scan(client, auth, tmp_path, monkeypatch):
    from swingbot.core.scanning import engine
    monkeypatch.setattr(engine, "TELEMETRY_PATH", str(tmp_path / "scan_telemetry.jsonl"))
    resp = client.get("/risk", headers=auth)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "No scan telemetry yet" in body
    assert "<svg" not in body
