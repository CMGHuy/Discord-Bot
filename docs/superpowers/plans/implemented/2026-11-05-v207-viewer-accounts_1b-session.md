# v207 part 1b — viewer sign-in on `/api/v1/session`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v207 — Viewer accounts](../specs/2026-11-05-v207-viewer-accounts-design.md)
**Index:** [`2026-11-05-v207-viewer-accounts_0-index.md`](2026-11-05-v207-viewer-accounts_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Task V207-4b, the second half of the ledger's V207-4 (split at the 20 KB cap; V207-4 is in [`_1-data-and-login.md`](2026-11-05-v207-viewer-accounts_1-data-and-login.md)). It runs straight after V207-4, in index group B. `<wt>` is the implementation worktree, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v207-viewer-accounts`; every command runs with that path, never in the main tree. Python tests run narrow (`cd "<wt>" && python scripts/dev/testrun.py file <test>`); no task runs the full suite. The task reaches the local Postgres: `/replicate-prod-db` once per session before the first test run.

# Phase B — principals and login (continued)

### Task V207-4b: viewer sign-in on `/api/v1/session`, `role` in its body, `viewer_client`

**Model:** opus — continues V207-4's security boundary: the sign-in route decides which principal a cookie carries, and every refused sign-in must be indistinguishable.

**Files:**
- Modify: `swingbot/admin/api_v1/session.py` (`_identity` :29-35, `session_create` :52-71, `session_delete` :74-79)
- Modify: `tests/admin/test_api_v1_session.py` (exact-body asserts at :25-26, :39, :47-48, :71 gain `role`)
- Modify: `tests/admin/conftest.py` (`viewer_client` fixture)
- Modify: `tests/admin/test_viewer_login.py` (HTTP-level tests appended)

**Interfaces:**
- Consumes: `app.login_session_fields`, `app.resolve_principal`, `app.forget_principal`, `login_limiter.attempt_login` (V207-4); `principals.hash_password` (V207-3); `admin_users_repo().create_user` / `reset_password` (V207-2); fixture `admin_users_table_missing` (V207-3); helpers `VIEWER`, `FAIL_BODY`, `_make_viewer` already in `tests/admin/test_viewer_login.py` (V207-4).
- Produces:
  - `/api/v1/session` (GET/POST/DELETE) body: `{"authenticated": bool, "username": str | None, "role": "admin" | "viewer" | None}` (V207-9's `Identity` mirrors it).
  - Fixture `viewer_client(client) -> (client, row)`: viewer `viewer1` / `viewer-password-1` created through the repository and signed in through `POST /api/v1/session` (V207-5..V207-8 use it).

- [ ] **Step 1: Add the `viewer_client` fixture to `tests/admin/conftest.py`**

Append after `admin_users_table_missing`:

```python
VIEWER_USERNAME = "viewer1"
VIEWER_PASSWORD = "viewer-password-1"


@pytest.fixture
def viewer_client(client):
    """v207: `client` signed in through POST /api/v1/session as a viewer.

    Returns (client, row); `row` is the repository row as created (id,
    credential_version 1). An admin Basic header (`auth`) still works on the
    same client for setup calls."""
    from swingbot.admin import principals
    from swingbot.core.db.repositories.admin_users import admin_users_repo

    row = admin_users_repo().create_user(VIEWER_USERNAME,
                                         principals.hash_password(VIEWER_PASSWORD))
    response = client.post("/api/v1/session",
                           json={"username": VIEWER_USERNAME, "password": VIEWER_PASSWORD})
    assert response.status_code == 200, response.get_json()
    return client, row
```

- [ ] **Step 2: Update the exact-body asserts in `tests/admin/test_api_v1_session.py`**

The spec's one deliberate exception to "the admin suite passes unchanged". Add below `_LOGIN`:

```python
_SESSION_SHAPE = {"authenticated": bool, "username": (str, type(None)),
                  "role": (str, type(None))}
```

then:

- `test_session_get_reports_unauthenticated_without_a_cookie`: `assert_shape(r.get_json(), _SESSION_SHAPE)` and `assert r.get_json() == {"authenticated": False, "username": None, "role": None}`.
- `test_session_get_reports_authenticated_after_login`: `assert body == {"authenticated": True, "username": "admin", "role": "admin"}`.
- `test_login_sets_the_session_and_returns_identity`: `assert_shape(r.get_json(), _SESSION_SHAPE)` and `assert r.get_json() == {"authenticated": True, "username": "admin", "role": "admin"}`.
- `test_logout_clears_the_session`: `assert r.get_json() == {"authenticated": False, "username": None, "role": None}`.

Append after `test_logout_when_not_logged_in_is_not_an_error`:

```python
def test_an_admin_session_issued_before_v207_has_no_role_and_is_still_admin(client):
    """Sessions minted before the deploy carry admin_authed + pw_hash only."""
    import swingbot.admin.app as app_module

    with client.session_transaction() as s:
        s["admin_authed"] = True
        s["pw_hash"] = app_module._password_hash()
    assert client.get("/api/v1/session").get_json() == {
        "authenticated": True, "username": "admin", "role": "admin"}


def test_an_admin_login_stores_the_role(client):
    client.post("/api/v1/session", json=_LOGIN)
    with client.session_transaction() as s:
        assert s["role"] == "admin" and s["admin_authed"] is True
```

- [ ] **Step 3: Append the failing HTTP tests to `tests/admin/test_viewer_login.py`**

```python
# --- POST /api/v1/session as a viewer (V207-4b) ---------------------------------

def test_a_viewer_logs_in_and_the_session_says_viewer(client):
    row = _make_viewer()
    r = client.post("/api/v1/session", json=VIEWER)
    assert r.status_code == 200
    assert r.get_json() == {"authenticated": True, "username": "viewer1", "role": "viewer"}
    assert client.get("/api/v1/session").get_json()["role"] == "viewer"
    with client.session_transaction() as s:
        assert s["role"] == "viewer" and s["user_id"] == row["id"]
        assert s["credential_version"] == 1 and s["username"] == "viewer1"
        assert "admin_authed" not in s and "pw_hash" not in s


def test_viewer_login_is_case_insensitive_and_reports_the_stored_name(client):
    _make_viewer(name="Viewer1")
    r = client.post("/api/v1/session", json={**VIEWER, "username": "VIEWER1"})
    assert r.get_json()["username"] == "Viewer1"


def test_the_viewer_client_fixture_is_signed_in(viewer_client):
    client, _row = viewer_client
    assert client.get("/api/v1/session").get_json() == {
        "authenticated": True, "username": "viewer1", "role": "viewer"}
    assert client.get("/api/v1/health").status_code == 200


@pytest.mark.parametrize("case", ["admin-wrong-password", "viewer-wrong-password",
                                  "unknown-user", "disabled-viewer"])
def test_every_failure_is_the_same_401(client, case):
    _make_viewer()
    _make_viewer(name="viewer2", disabled=True)
    body = {"admin-wrong-password": {"username": "admin", "password": "nope-nope-nope"},
            "viewer-wrong-password": {**VIEWER, "password": "nope-nope-nope"},
            "unknown-user": {"username": "ghost", "password": "viewer-password-1"},
            "disabled-viewer": {"username": "viewer2", "password": "viewer-password-1"},
            }[case]
    r = client.post("/api/v1/session", json=body)
    assert r.status_code == 401 and r.get_json() == FAIL_BODY
    assert client.get("/api/v1/session").get_json()["authenticated"] is False


def test_every_failure_counts_toward_the_lockout(client):
    _make_viewer()
    _make_viewer(name="viewer2", disabled=True)
    for body in ({"username": "admin", "password": "nope-nope-nope"},
                 {**VIEWER, "password": "nope-nope-nope"},
                 {"username": "ghost", "password": "viewer-password-1"},
                 {"username": "viewer2", "password": "viewer-password-1"},
                 {**VIEWER, "password": "still-wrong-pw"}):
        assert client.post("/api/v1/session", json=body).status_code == 401
    locked = client.post("/api/v1/session", json=VIEWER)       # right password, too late
    assert_error(locked, "rate_limited", 429)
    assert int(locked.headers["Retry-After"]) >= 1


def test_a_missing_table_is_invalid_credentials_and_the_admin_is_unaffected(
        client, admin_users_table_missing):
    r = client.post("/api/v1/session", json=VIEWER)
    assert r.status_code == 401 and r.get_json() == FAIL_BODY
    ok = client.post("/api/v1/session", json={"username": "admin", "password": "admin"})
    assert ok.status_code == 200 and ok.get_json()["role"] == "admin"
    assert client.get("/api/v1/health").status_code == 200


def test_a_password_reset_ends_the_viewer_session_on_its_next_request(viewer_client):
    client, row = viewer_client
    admin_users_repo().reset_password(row["id"], principals.hash_password("a-new-password"))
    assert client.get("/api/v1/session").get_json() == {
        "authenticated": False, "username": None, "role": None}
    assert_error(client.get("/api/v1/health"), "auth", 401)


def test_logout_clears_a_viewer_session(viewer_client):
    client, _row = viewer_client
    assert client.delete("/api/v1/session").get_json() == {
        "authenticated": False, "username": None, "role": None}
    assert client.get("/api/v1/session").get_json()["authenticated"] is False


def test_switching_from_viewer_to_admin_leaves_no_viewer_fields(viewer_client):
    client, _row = viewer_client
    client.post("/api/v1/session", json={"username": "admin", "password": "admin"})
    with client.session_transaction() as s:
        assert s["role"] == "admin" and "user_id" not in s and "credential_version" not in s
```

- [ ] **Step 4: Run them to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_viewer_login.py`
Expected: FAIL — viewer sign-ins answer 401 (the route still calls `attempt(credentials_match)`), and the `viewer_client` fixture asserts on its 401.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_session.py`
Expected: FAIL on the four bodies that now expect `role` and on `test_an_admin_login_stores_the_role`.

- [ ] **Step 5: `api_v1/session.py` — the role in every body, the principal-returning sign-in**

Replace `_identity` (:29-35):

```python
def _identity() -> dict:
    """The one body all three /session methods return.

    Always the same shape, so the SPA's SessionStore has a single reducer
    for login, logout and the boot check rather than three. v207 adds `role`
    (`admin` | `viewer`, None when signed out)."""
    principal = _app.resolve_principal()
    if principal is None:
        return {"authenticated": False, "username": None, "role": None}
    return {"authenticated": True, "username": principal["username"],
            "role": principal["role"]}
```

Replace the body of `session_create` from the `# v148:` comment to the end:

```python
    # v148: gated by the login limiter all three credential checks share; a
    # locked client is refused before comparing. v207: the session route takes
    # the principal-returning check (admin first, then admin_users); Basic
    # keeps the bool one. Every refusal is the same 401 body.
    outcome = login_limiter.attempt_login(username, password, _app.login_session_fields)
    if outcome.retry_after is not None:
        return rate_limited(outcome.retry_after)
    if not outcome.ok:
        return error("auth", "Invalid username or password.", 401)
    # Clear first so a partially populated older session cannot survive; the
    # stored fields pin the admin's credential hash or the viewer's
    # credential_version, so a password change ends this session.
    session.clear()
    session.update(outcome.result)
    session.permanent = True
    _app.forget_principal()
    return jsonify(_identity())
```

In `session_delete`, add `_app.forget_principal()` between `session.clear()` and `return jsonify(_identity())`.

In the module docstring, change "JSON front door onto the same `session["admin_authed"]` + `pw_hash` mechanism `/login` and `/logout` already drive" to "JSON front door onto the signed session cookie: `admin_authed` + `pw_hash` for the `.env` admin, and since v207 `role` / `user_id` / `credential_version` for a viewer, all resolved through `_app.resolve_principal()`".

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_viewer_login.py`
Expected: PASS.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_session.py`
Expected: PASS.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_event_stream.py`
Expected: PASS (`/events` without a session is still the v1 401).

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_login_limiter.py`
Expected: PASS.

- [ ] **Step 7: Complexity gate**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: exit 0; `session_create` at most 6, `_identity` 2 (auth cap 12).

- [ ] **Step 8: Commit**

```bash
git -C "<wt>" add swingbot/admin/api_v1/session.py tests/admin/test_api_v1_session.py tests/admin/test_viewer_login.py tests/admin/conftest.py
git -C "<wt>" commit -m "feat(v207): viewer sign-in on /session, role in its body, viewer_client fixture (V207-4b)"
```

