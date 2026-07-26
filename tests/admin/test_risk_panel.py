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
