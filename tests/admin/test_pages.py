"""Route-level smoke tests for the admin Flask app. Every test in this file
(and every other tests/admin/*.py file in this plan) uses the `client`/`auth`
fixtures from conftest.py rather than talking to a real running server."""


def test_index_requires_auth(client):
    assert client.get("/").status_code == 401


def test_index_renders(client, auth):
    r = client.get("/", headers=auth)
    assert r.status_code == 200 and b"Dashboard" in r.data


import pytest

NEW_PATHS = ["/plans", "/strategies", "/calibration", "/journal", "/tuning"]


@pytest.mark.parametrize("path", NEW_PATHS)
def test_new_pages_200_authed(client, auth, path):
    r = client.get(path, headers=auth)
    assert r.status_code == 200


@pytest.mark.parametrize("path", NEW_PATHS)
def test_new_pages_401_unauthed(client, path):
    assert client.get(path).status_code == 401


def test_new_nav_items_in_sidebar(client, auth):
    r = client.get("/", headers=auth)
    html = r.data.decode("utf-8")
    for label in ("Plans", "Strategies", "Calibration", "Journal", "Tuning"):
        assert label in html
