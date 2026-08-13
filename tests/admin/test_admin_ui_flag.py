"""NG53 — the `ADMIN_UI` flag.

NG19 TRIAGE: DELETE at NG57. The flag exists to make Release A reversible;
once Jinja is gone there is nothing to flip back to and the flag goes with
it.

What matters here is the property the whole two-release cutover rests on:
**flipping the value swaps what `/` serves and changes nothing else.** Every
Jinja route stays mounted in both modes, so a rollback is a restart rather
than a rebuild or a redeploy.

**`is_built` is monkeypatched here rather than faked on disk**, unlike
`test_spa_serving.py`, which needs real files to serve. `static/app/` is
shared process-wide, and since this task `/` reads it — so a file written by
one xdist worker changes what `/` answers for every other worker's test at
the same moment. That is exactly the cross-worker flake this file would
otherwise have introduced into the dashboard tests.
"""
import pytest

from swingbot import config
from swingbot.admin import spa


@pytest.fixture
def built(monkeypatch):
    """The bundle exists, without touching the filesystem."""
    monkeypatch.setattr(spa, "is_built", lambda: True)


@pytest.fixture
def spa_mode(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_UI", "spa", raising=False)


@pytest.fixture
def jinja_mode(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_UI", "jinja", raising=False)


# --------------------------------------------------------------------------
# The flag
# --------------------------------------------------------------------------

def test_spa_mode_sends_the_root_to_the_spa(client, auth, built, spa_mode):
    response = client.get("/", headers=auth)

    assert response.status_code in (301, 302, 308)
    assert response.headers["Location"].endswith("/dashboard")


def test_jinja_mode_serves_the_dashboard_at_the_root(client, auth, built, jinja_mode):
    response = client.get("/", headers=auth)

    assert response.status_code == 200
    assert b"sb-root" not in response.data


def test_the_default_is_spa():
    """`spa` and not `jinja`: the flag's value is the rollback, not the
    opt-in (spec v15's open question 1, decided)."""
    field = next(f for f in config.FIELDS if f.key == "ADMIN_UI")

    assert field.default == "spa"
    assert [value for value, _ in field.options] == ["spa", "jinja"]


def test_the_flag_is_not_hot_reloadable():
    """It is read per request, but the honest answer for the operator is
    'restart the admin container' -- the same answer every other Admin UI
    field gives, and the one the two-release plan assumes."""
    field = next(f for f in config.FIELDS if f.key == "ADMIN_UI")

    assert field.hot_reloadable is False


# --------------------------------------------------------------------------
# What the flag must NOT change
# --------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["spa", "jinja"])
def test_every_jinja_page_stays_reachable_in_both_modes(
    client, auth, built, monkeypatch, mode,
):
    """The property that makes the cutover reversible.

    If any of these 404'd under `spa`, rolling back would mean redeploying
    rather than restarting -- and the two-week watch in NG56 would be
    protecting nothing.
    """
    monkeypatch.setattr(config, "ADMIN_UI", mode, raising=False)

    # `/jinja/dashboard` and `/jinja/watchlist` are the only two that carry a
    # prefix: SR4 and SR5 moved them there because the SPA's renamed
    # Dashboard and Watchlist workspaces needed the clean URLs, and
    # spa.register() skips any rule Jinja owns. The point of this test is
    # unchanged -- every Jinja page still answers 200 in BOTH modes, which is
    # what keeps rollback a restart rather than a redeploy.
    for path in ("/jinja/dashboard", "/plans", "/journal", "/performance",
                 "/strategies", "/calibration", "/tuning", "/jinja/watchlist",
                 "/risk", "/settings", "/logs"):
        response = client.get(path, headers=auth)
        assert response.status_code == 200, f"{path} under ADMIN_UI={mode}"


def test_the_spa_routes_stay_mounted_in_jinja_mode(client, jinja_mode):
    """The flag decides what `/` answers with and nothing else.

    The SPA's own six prefixes are registered at import time and the flag
    never touches them, which is what makes flipping forward as cheap as
    flipping back. Asserted on the URL map rather than by fetching, because
    fetching would need a real bundle on disk — `test_spa_serving.py` owns
    that half.
    """
    rules = {rule.rule for rule in client.application.url_map.iter_rules()}

    assert "/cockpit" in rules
    assert "/analytics" in rules


def test_an_unbuilt_bundle_falls_back_to_jinja(client, auth, spa_mode, monkeypatch):
    """The one place an unbuilt SPA does not 404.

    Elsewhere it must, so a missing bundle cannot be mistaken for a working
    deploy. Here the alternative is a front door redirecting into a 404
    while a perfectly good UI sits behind it -- so it falls back, loudly
    (WARNING), rather than breaking `/`.
    """
    monkeypatch.setattr(spa, "is_built", lambda: False)

    response = client.get("/", headers=auth)

    assert response.status_code == 200
    assert b"sb-root" not in response.data
