"""NG33 — Flask serving the built SPA.

NG19 TRIAGE: KEEP unchanged. This tests `swingbot/admin/spa.py`, which
exists only for the Angular UI and outlives the cutover.

The bundle is absent in a source checkout (`static/app/` is gitignored and
produced by the Dockerfile's frontend stage), so these tests build a fake one
**in a tmp_path** and point `spa.APP_DIR` at it.

An earlier version wrote into the real `static/app/` instead, arguing that a
tmp_path "would test a path the deployment never takes". That argument was
wrong twice over. `send_from_directory` behaves identically whichever
directory it is given, so nothing about the serving logic was being proved by
using the real one -- and the real one is *shared mutable state*: under
`-n 4` two workers create and delete it underneath each other, and a
developer who had actually built the SPA had their bundle deleted by running
the suite.

What the real path genuinely needs is one assertion that it points where the
Dockerfile puts the bundle, which is
`test_app_dir_points_where_the_dockerfile_copies_the_bundle` below. That is
the part a tmp_path cannot cover, and it is one test rather than a
filesystem-wide side effect.
"""
import os

import pytest

from swingbot.admin import spa

# The four whose URL the Jinja UI does not already own. `/risk` and
# `/trades/<trade_id>` are still Jinja routes until NG57 -- see
# test_a_workspace_the_jinja_ui_still_owns_stays_jinja.
SPA_WORKSPACES = ("cockpit", "trades", "analytics", "universe", "system")


@pytest.fixture
def built(tmp_path, monkeypatch):
    """A fake bundle, in a directory belonging to this test alone."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "index.html").write_text(
        "<!doctype html><sb-root></sb-root>", encoding="utf-8")
    (app_dir / "main-ABCD1234.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(spa, "APP_DIR", str(app_dir))
    return app_dir


def test_app_dir_points_where_the_dockerfile_copies_the_bundle():
    """The one thing a tmp_path cannot check.

    `COPY --from=frontend /build/dist/frontend/browser
    /app/swingbot/admin/static/app` in the Dockerfile, and docker-compose
    keeps that path alive past its bind mount with an anonymous volume at the
    same string. Three places have to agree; this asserts the one in Python.
    """
    expected = os.path.join(
        os.path.dirname(os.path.abspath(spa.__file__)), "static", "app")
    assert spa.APP_DIR == expected
    assert spa.APP_DIR.replace("\\", "/").endswith("swingbot/admin/static/app")


# --------------------------------------------------------------------------
# The allow-list
# --------------------------------------------------------------------------

@pytest.mark.parametrize("workspace", SPA_WORKSPACES)
def test_each_workspace_serves_the_spa(client, workspace, built):
    response = client.get(f"/{workspace}")

    assert response.status_code == 200
    assert b"sb-root" in response.data


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

def test_an_unbuilt_spa_404s_rather_than_pretending(client, tmp_path, monkeypatch):
    """A source checkout has no bundle. A friendly placeholder here would be
    indistinguishable from a broken deployment.

    Points APP_DIR at a directory that does not exist, rather than skipping
    when the real one happens to be populated. The skip meant this ran on a
    clean checkout and silently did not run on any machine where someone had
    built the SPA -- so the assertion was weakest exactly where a person was
    most likely to be changing this code.
    """
    monkeypatch.setattr(spa, "APP_DIR", str(tmp_path / "never-built"))
    assert not spa.is_built()

    assert client.get("/cockpit").status_code == 404
    assert client.get("/app/main-ABCD1234.js").status_code == 404


# --------------------------------------------------------------------------
# The build's base href, which is not a unit-testable thing but breaks
# everything when it is wrong
# --------------------------------------------------------------------------

def test_the_build_base_href_matches_where_flask_serves_the_bundle():
    """NG54. The one failure that no other test in this repo could see.

    `asset()` above serves the bundle from `/app/`, deliberately, so it
    cannot collide with the Jinja UI's `/static/`. But index.html's asset
    URLs are relative and resolve against whatever `<base href>` the build
    stamped in. Angular's default is `/`, so the default build produces a
    page that asks for `/main-<hash>.js` while Flask only answers at
    `/app/main-<hash>.js`: every asset 404s and the SPA is a black screen.

    Nothing caught it. The Python tests write a FAKE index.html, so they
    never see the real one; the Angular tests never load index.html at all;
    and both suites passed on a bundle that could not boot. It took opening
    the page in a browser, which is exactly the argument for spec v15's
    Decision 2b existing.

    So this test reads the two values that must agree and compares them --
    the closest a test can get to the browser check without a browser.
    `APP_BASE_HREF` in app.config.ts then puts the ROUTER back at `/`; that
    half is covered by app.routes.spec.ts, which routes to /cockpit.
    """
    import json

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    angular_json = os.path.join(here, "frontend", "angular.json")
    if not os.path.isfile(angular_json):
        pytest.skip("no frontend/ in this checkout")

    with open(angular_json, encoding="utf-8") as fh:
        config = json.load(fh)
    project = next(iter(config["projects"].values()))
    base_href = project["architect"]["build"]["options"].get("baseHref")

    assert base_href == "/app/", (
        f"angular.json baseHref is {base_href!r}, but spa.py serves the bundle "
        f"from /app/. A mismatch means every asset 404s and the SPA renders a "
        f"black screen -- with both test suites still green."
    )


def test_logged_out_front_door_does_not_500(client):
    """Release B shipped a 500 here, and every test in this suite missed it.

    `require_auth` redirected an unauthenticated browser to
    `url_for("login_page")` — a Jinja endpoint the cutover deleted — so `/`
    raised `BuildError` for anyone not already logged in. The deploy's
    healthcheck caught it; the test suite did not, because every other test
    authenticates first and `test_login.py` (which was the only thing
    exercising the logged-out path) was deleted in the same commit.

    The SPA renders its own login form, so the logged-out front door is
    supposed to hand over to the SPA and let it ask `/api/v1/session`.
    """
    response = client.get("/")

    assert response.status_code < 500, (
        f"logged-out GET / returned {response.status_code}; it must reach the "
        f"SPA, which renders the login form itself"
    )
    assert response.status_code in (302, 200)
    if response.status_code == 302:
        assert "/dashboard" in response.headers["Location"]


def test_logged_out_api_is_still_guarded(client):
    """The counterpart, so the fix above cannot become "nothing is guarded".

    Serving the SPA shell to anyone is fine — it is static assets. What must
    stay closed is the data.
    """
    assert client.get("/api/v1/dashboard").status_code == 401
