"""v218 V218-13: exactly the audited views answer 304, and how their ETag behaves (v206 P3-c).

The allow-list is the union of the route audits (V218-10..12, v206
`### Plan 3 route audits (V218-10..12)`): /trades in its closed-only shape.
Every other view keeps Cache-Control: no-store. The behaviour tests run the
admitted shape on the golden book, snapshot vouched for, refresher on."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.admin import build_identity
from swingbot.admin.api_v1 import conditional as cond
from swingbot.admin.api_v1.read_scope import READ_SCOPE_ATTR
from swingbot.core.infra import store_generation
from tests.admin_perf import golden_book as gb
from tests.admin_perf.test_read_scope_routes import _WRITES, _api_rules
from tests.admin_perf.test_trades_conditional_audit import (  # noqa: F401  (fixtures)
    CLOSED, UTC, closed_page, refresher_on)
from tests.store_seed import seed_store

CONDITIONAL = {"api_v1.list_trades"}
ROUTE_KEYS = {"api_v1.list_trades": "trades"}
EXCLUDED = ("api_v1.dashboard", "api_v1.get_live", "api_v1.calendar_pnl", "api_v1.calendar_pnl_day",
            "api_v1.calendar_pnl_day_sparklines")
_REAL_AUTO_RELOAD = config.auto_reload_if_changed


def _tag(response) -> str:
    assert response.status_code == 200, response.get_data(as_text=True)
    tag = response.headers.get("ETag")
    assert tag and tag.startswith('W/"'), dict(response.headers)
    return tag


def _again(client, tag: str, path: str = CLOSED, **headers):
    return client.get(path, headers={"If-None-Match": tag, **headers})


# --- which views carry it ----------------------------------------------------

def test_exactly_the_audited_views_are_conditional(admin_app):
    marked = {rule.endpoint: getattr(view, cond.CONDITIONAL_ATTR)
              for rule, view in _api_rules() if hasattr(view, cond.CONDITIONAL_ATTR)}
    assert marked == ROUTE_KEYS
    assert set(marked) == CONDITIONAL
    assert len(set(marked.values())) == len(marked), "two views share a route key"


def test_a_conditional_view_is_a_read_scoped_get(admin_app):
    for rule, view in _api_rules():
        if rule.endpoint in CONDITIONAL:
            assert not (rule.methods & _WRITES), (rule.rule, rule.methods)
            assert getattr(view, READ_SCOPE_ATTR, False) is True, rule.rule


@pytest.mark.parametrize("endpoint", EXCLUDED)
def test_the_spec_and_audit_exclusions_stay_off(admin_app, endpoint):
    assert not hasattr(admin_app.view_functions[endpoint], cond.CONDITIONAL_ATTR)


# --- the admitted shape: 304 only while nothing changed ----------------------

def test_a_repeat_is_a_bodiless_304(closed_page):
    tag = _tag(closed_page.get(CLOSED))
    response = _again(closed_page, tag)
    assert response.status_code == 304 and response.get_data() == b""
    assert response.headers["ETag"] == tag
    assert response.headers["Cache-Control"] == cond.CACHE_CONTROL
    assert response.headers["Server-Timing"].endswith("snap;desc=hit")


def test_a_trade_write_gives_a_200_with_the_new_row(closed_page):
    tag = _tag(closed_page.get(CLOSED))
    seed_store("trades", [gb._trade("golden-t7-v218", "AAPL", status="win", entry=100.0, shares=1,
                                    closed_at="2026-11-04T10:00:00+00:00", exit_price=101.0, pnl=1.0)])
    response = _again(closed_page, tag)
    assert _tag(response) != tag
    assert "golden-t7-v218" in {row["id"] for row in response.get_json()["items"]}


def test_a_journal_note_gives_a_200_with_has_note(closed_page):
    tag = _tag(closed_page.get(CLOSED))
    seed_store("journal", [{"created_at": "2026-11-04T10:00:00+00:00", "trade_id": "golden-t1-sap-win",
                            "ticker": "SAP.DE", "strategy": "S/R Confluence", "outcome": "win",
                            "note": "v218 lesson", "tags": []}])
    response = _again(closed_page, tag)
    assert _tag(response) != tag
    rows = {row["id"]: row for row in response.get_json()["items"]}
    assert rows["golden-t1-sap-win"]["has_note"] is True


@pytest.mark.parametrize("concern", ["trades", "journal"])
def test_a_notify_with_unchanged_versions_still_gives_a_200(closed_page, concern):
    tag = _tag(closed_page.get(CLOSED))
    store_generation.bump(concern)                 # what the snapshot listener does on a NOTIFY
    assert _tag(_again(closed_page, tag)) != tag


def test_a_berlin_midnight_crossing_gives_a_200_with_today_recomputed(closed_page, monkeypatch):
    monkeypatch.setattr(gb, "FROZEN_NOW", dt.datetime(2026, 11, 3, 22, 30, tzinfo=UTC))
    before = closed_page.get(CLOSED)
    tag = _tag(before)
    assert {r["id"] for r in before.get_json()["items"] if r["today"]} == {
        "golden-t1-sap-win", "golden-t2-usd-win", "golden-t3-usd-midnight"}
    monkeypatch.setattr(gb, "FROZEN_NOW", dt.datetime(2026, 11, 3, 23, 30, tzinfo=UTC))
    after = _again(closed_page, tag)
    assert after.status_code == 200
    assert "ETag" not in after.headers             # 00:30 Berlin, still 3 Nov in ET: not admitted
    assert not any(row["today"] for row in after.get_json()["items"])


def test_the_next_admitted_berlin_day_gets_a_new_tag(closed_page, monkeypatch):
    monkeypatch.setattr(gb, "FROZEN_NOW", dt.datetime(2026, 11, 4, 22, 30, tzinfo=UTC))
    tag = _tag(closed_page.get(CLOSED))
    monkeypatch.setattr(gb, "FROZEN_NOW", dt.datetime(2026, 11, 5, 5, 30, tzinfo=UTC))
    assert _tag(_again(closed_page, tag)) != tag


def test_a_new_build_gives_a_200(closed_page, monkeypatch):
    tag = _tag(closed_page.get(CLOSED))
    monkeypatch.setattr(build_identity, "build_version", lambda: "ffffffffffffffff|swing-bot:next")
    assert _tag(_again(closed_page, tag)) != tag


def test_an_env_change_picked_up_by_auto_reload_gives_a_200(closed_page, monkeypatch):
    tag = _tag(closed_page.get(CLOSED))
    # reload() reassigns these module globals with `global`; register them for restore.
    for name in ("_DOTENV_LOADED", "_DOTENV_FROM_CANONICAL_PATH", "_ENV_MTIME"):
        monkeypatch.setattr(config, name, getattr(config, name))
    monkeypatch.setattr(config, "auto_reload_if_changed", _REAL_AUTO_RELOAD)  # undo refresher_on's no-op
    monkeypatch.setattr(config, "_env_signature", lambda: ("v218-edited", 1))
    monkeypatch.setattr(config, "_load_dotenv_file", lambda: (True, False))
    monkeypatch.setattr(config, "_apply_env", lambda: {"ADMIN_SLOW_REQUEST_MS": (2000, 2500)})
    settings_before = store_generation.generation("settings")
    response = _again(closed_page, tag)
    assert store_generation.generation("settings") == settings_before + 1
    assert _tag(response) != tag


# --- no tag at all --------------------------------------------------------------

@pytest.mark.parametrize("setup", ["switch_off", "disconnected", "fresh"])
def test_a_bypassed_request_carries_no_tag(closed_page, monkeypatch, setup):
    headers = {"If-None-Match": "*"}
    if setup == "switch_off":
        monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "off")
    elif setup == "disconnected":
        store_generation.set_connected(False)
    else:
        headers["X-Swingbot-Fresh"] = "1"
    response = closed_page.get(CLOSED, headers=headers)
    assert response.status_code == 200             # '*' would have been a 304 had a tag been computed
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"


def test_an_unauthenticated_request_gets_a_401_without_a_tag(closed_page, admin_app):
    response = admin_app.test_client().get(CLOSED, headers={"If-None-Match": "*"})
    assert response.status_code == 401
    assert "ETag" not in response.headers


@pytest.mark.parametrize("path", ["/api/v1/trades", "/api/v1/trades?status=open", "/api/v1/dashboard"])
def test_excluded_shapes_and_routes_carry_no_tag(closed_page, path):
    response = closed_page.get(path, headers={"If-None-Match": "*"})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"


def test_a_viewer_and_the_admin_get_different_tags(closed_page):
    from swingbot.admin import principals
    from swingbot.core.db.repositories.admin_users import admin_users_repo
    from tests.admin.conftest import VIEWER_PASSWORD, VIEWER_USERNAME
    admin_tag = _tag(closed_page.get(CLOSED))
    admin_users_repo().create_user(VIEWER_USERNAME, principals.hash_password(VIEWER_PASSWORD))
    login = closed_page.post("/api/v1/session",
                             json={"username": VIEWER_USERNAME, "password": VIEWER_PASSWORD})
    assert login.status_code == 200, login.get_json()
    viewer = _again(closed_page, admin_tag)
    assert _tag(viewer) != admin_tag               # the admin's tag never answers a viewer with 304
