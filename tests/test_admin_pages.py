"""Render smoke tests: every admin page returns 200 and carries the marker
classes the redesign relies on. Auth is satisfied by pointing config at
known credentials for the duration of each test.

NG19 TRIAGE — **HTML-structure · DELETE at cutover.** Spec v15 Decision 4
names this file as being in the same position as tests/admin/'s render tests
despite living a directory up. It asserts marker classes on pages that are
being deleted; no domain behaviour is pinned here that /api/v1 does not
already cover.

**Its `client` fixture is imported by other test modules** (see
tests/test_admin_api_ohlcv.py) -- move the fixture before deleting the file,
or those go red for an unrelated reason at the least convenient moment."""
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


def test_tokens_and_font_are_linked(client):
    html = client.get("/dashboard").get_data(as_text=True)
    assert "tokens.css" in html and "vendor/inter/inter.css" in html
    assert "googleapis" not in html  # no-CDN constraint


def test_stats_page_has_tiles(client):
    html = client.get("/performance").get_data(as_text=True)
    assert 'class="tile' in html or "tiles" in html


def test_settings_page_has_cards(client):
    assert 'class="card' in client.get("/settings").get_data(as_text=True)
