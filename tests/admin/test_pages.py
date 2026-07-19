"""Route-level smoke tests for the admin Flask app. Every test in this file
(and every other tests/admin/*.py file in this plan) uses the `client`/`auth`
fixtures from conftest.py rather than talking to a real running server."""


def test_index_requires_auth(client):
    assert client.get("/").status_code == 401


def test_index_renders(client, auth):
    r = client.get("/", headers=auth)
    assert r.status_code == 200 and b"Dashboard" in r.data
