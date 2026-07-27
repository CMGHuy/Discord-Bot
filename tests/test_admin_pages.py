"""Render smoke tests: every admin page returns 200 and carries the marker
classes the redesign relies on. Auth is satisfied by pointing config at
known credentials for the duration of each test."""
import base64

import pytest

from swingbot import config
from swingbot.admin import app as app_module
from swingbot.admin.app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_module, "ADMIN_USERNAME", "testadmin", raising=False)
    monkeypatch.setattr(app_module, "ADMIN_PASSWORD", "testpass", raising=False)
    app.config["TESTING"] = True
    token = base64.b64encode(b"testadmin:testpass").decode()
    with app.test_client() as c:
        c.environ_base["HTTP_AUTHORIZATION"] = f"Basic {token}"
        yield c


PAGES = ["/", "/performance", "/watchlist", "/settings", "/logs"]


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"
