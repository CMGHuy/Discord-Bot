"""NG33 — Flask serving the built SPA.

NG19 TRIAGE: KEEP unchanged. This tests `swingbot/admin/spa.py`, which
exists only for the Angular UI and outlives the cutover.

The bundle is absent in a source checkout (`static/app/` is gitignored and
produced by the Dockerfile's frontend stage), so these tests write a fake
one into it and remove it afterwards. That is the honest setup: it is the
same directory the container uses, and pointing the tests at a tmp_path
would test a path the deployment never takes.
"""
import os
import shutil

import pytest

from swingbot.admin import spa

# The four whose URL the Jinja UI does not already own. `/risk` and
# `/trades/<trade_id>` are still Jinja routes until NG57 -- see
# test_a_workspace_the_jinja_ui_still_owns_stays_jinja.
SPA_WORKSPACES = ("cockpit", "trades", "analytics", "universe", "system")


@pytest.fixture
def built():
    """A fake bundle in the real output directory, cleaned up after."""
    created = not os.path.isdir(spa.APP_DIR)
    os.makedirs(spa.APP_DIR, exist_ok=True)
    index = os.path.join(spa.APP_DIR, "index.html")
    asset = os.path.join(spa.APP_DIR, "main-ABCD1234.js")
    with open(index, "w", encoding="utf-8") as f:
        f.write("<!doctype html><sb-root></sb-root>")
    with open(asset, "w", encoding="utf-8") as f:
        f.write("console.log(1)")
    try:
        yield
    finally:
        # ignore_errors throughout: Werkzeug can still hold a sent file open
        # on Windows when the test client has not closed the response, and a
        # cleanup failure must not turn a passing test red.
        if created:
            shutil.rmtree(spa.APP_DIR, ignore_errors=True)
        else:
            for path in (index, asset):
                try:
                    os.remove(path)
                except OSError:
                    pass


# --------------------------------------------------------------------------
# The allow-list
# --------------------------------------------------------------------------

@pytest.mark.parametrize("workspace", SPA_WORKSPACES)
def test_each_workspace_serves_the_spa(client, workspace, built):
    response = client.get(f"/{workspace}")

    assert response.status_code == 200
    assert b"sb-root" in response.data


@pytest.mark.parametrize("path", ["/risk", "/trades/PLAN-1"])
def test_a_url_the_jinja_ui_still_owns_stays_jinja(client, path, built):
    """Both UIs are live until Phase 5, so a colliding URL keeps its
    existing owner rather than being taken over mid-migration.

    **This test is expected to fail at NG57** and that is its job: when the
    Jinja routes are deleted, these paths start serving the SPA, and the
    failure is the reminder to move them into SPA_WORKSPACES above.

    Two different mechanisms produce the same outcome. `/risk` is an exact
    duplicate rule and `spa.register` skips it. `/trades/PLAN-1` matches
    Jinja's `/trades/<trade_id>` rather than the SPA's
    `/trades/<path:_rest>`, because Werkzeug ranks the narrower converter
    first -- nothing skipped it.
    """
    response = client.get(path)

    assert response.status_code != 200 or b"sb-root" not in response.data


@pytest.mark.parametrize("path", ["/universe/AAPL"])
def test_a_detail_url_reloads_into_the_spa(client, path, built):
    """Refreshing on /trades/:id must not 404 -- the route only exists in
    the browser, so the server has to hand back the shell and let the
    router take it from there."""
    assert client.get(path).status_code == 200


def test_an_unknown_path_is_still_a_404(client, built):
    """The reason this is an allow-list and not a catch-all.

    A catch-all would swallow every Jinja URL, every typo and every future
    route into a 200 rendering the SPA's own "not found" -- and both UIs are
    live until cutover.
    """
    assert client.get("/definitely-not-a-workspace").status_code == 404


def test_an_api_typo_does_not_return_html(client, built):
    """The worst version of the catch-all failure: a JSON caller handed a
    200 with an HTML body."""
    response = client.get("/api/v1/tradez")

    assert response.status_code == 404
    assert response.mimetype == "application/json"


def test_the_jinja_ui_is_untouched(client, auth, built):
    """Both UIs are live until Phase 5. / is still the Jinja dashboard, and
    nothing here may change that."""
    response = client.get("/", headers=auth)

    assert response.status_code == 200
    assert b"sb-root" not in response.data


# --------------------------------------------------------------------------
# Caching
# --------------------------------------------------------------------------

def test_a_hashed_asset_is_cached_forever(client, built):
    """`main-ABCD1234.js` is immutable by construction: a changed file gets
    a different name, so it can never need revalidating."""
    response = client.get("/app/main-ABCD1234.js")

    assert response.status_code == 200
    assert "max-age=31536000" in response.headers["Cache-Control"]
    assert "immutable" in response.headers["Cache-Control"]


def test_index_is_never_cached(client, built):
    """It is the one file whose name never changes and the one that names
    all the others -- caching it is how a browser ends up asking for a
    bundle that no longer exists, after a deploy that otherwise worked."""
    for path in ("/cockpit", "/app/index.html"):
        cache = client.get(path).headers["Cache-Control"]
        assert "no-cache" in cache, path
        assert "immutable" not in cache, path


# --------------------------------------------------------------------------
# Before the bundle exists
# --------------------------------------------------------------------------

def test_an_unbuilt_spa_404s_rather_than_pretending(client):
    """A source checkout has no bundle. A friendly placeholder here would be
    indistinguishable from a broken deployment."""
    if spa.is_built():
        pytest.skip("a real bundle is present in static/app/")

    assert client.get("/cockpit").status_code == 404
    assert client.get("/app/main-ABCD1234.js").status_code == 404
