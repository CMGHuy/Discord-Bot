# v207 part 2 — default-deny access, Users API, viewer route matrix, SSE re-check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v207 — Viewer accounts](../specs/2026-11-05-v207-viewer-accounts-design.md)
**Index:** [`2026-11-05-v207-viewer-accounts_0-index.md`](2026-11-05-v207-viewer-accounts_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Tasks V207-5..V207-8 (index groups C and D). Group C (V207-5 → V207-6 → V207-7) is sequential; V207-8 may run beside it. All four need V207-4 / V207-4b merged: `_app.resolve_principal()`, `_app.principal_from_session()` and the `viewer_client` fixture (`tests/admin/conftest.py`, viewer `viewer1` / `viewer-password-1`). `<wt>` is the implementation worktree, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v207-viewer-accounts`; every command runs with that path, never in the main tree. Python tests run narrow (`cd "<wt>" && python scripts/dev/testrun.py file <test>`); no task runs the full suite. Every task here reaches the local Postgres: `/replicate-prod-db` once per session before the first test run.

**One fixture trap for every test below.** The access hook resolves the *session* principal before `require_auth` looks at a Basic header, so a client that carries a viewer cookie is a viewer whatever `Authorization` header it also sends. Admin calls in a test that also uses `viewer_client` go through a **second** client: `admin_app.test_client()` with the `auth` (Basic `admin:admin`) header. (V207-4b's `viewer_client` docstring says the Basic header "still works on the same client"; that stops being true for admin-only paths once V207-5 lands. The docstring is left as V207-4b wrote it, because the index gives `conftest.py` to V207-3 and V207-4 only; the tests in this part never rely on it.)

# Phase C — access, users, matrix

### Task V207-5: `check_access` + `api_v1` access hook (contract in V207-5b)

**Model:** opus — the security boundary itself: one default-deny rule every v1 request passes, plus the contract that keeps a future route from slipping past it.

**Files:**
- Create: `swingbot/admin/access.py`
- Create: `swingbot/admin/api_v1/access_hook.py`
- Modify: `swingbot/admin/api_v1/__init__.py` (`register()` import list, ~:202-204)
- Create: `tests/admin/test_access.py`

**Interfaces:**
- Consumes: `_app.resolve_principal() -> dict | None` (V207-4, through the module: `from swingbot.admin import app as _app`); fixture `viewer_client(client) -> (client, row)` (V207-4b); `api_v1`, `error()` (`api_v1/__init__.py:36`, `:89`).
- Produces:
  - `access.ADMIN_ONLY_PREFIXES: tuple[str, ...]`, `access.VIEWER_GET_ALLOWLIST: frozenset[str]`, `access.EXEMPT_PATHS: frozenset[str]`, `access.READ_METHODS: frozenset[str]`, `access.is_admin_only(path) -> bool`.
  - `access.check_access(principal: dict | None, method: str, path: str) -> bool` — `None` ⇒ True (the hook stays out; `require_auth` answers 401); exempt path ⇒ True; `admin` ⇒ True; `viewer` ⇒ read method and (allowlisted or under no admin-only prefix); any other role ⇒ False.
  - `access_hook.enforce_access()` — the `@api_v1.before_request` hook; returns `None` or `error("forbidden", "Read-only account.", 403)`.
  - The ledger's `tests/admin/access_expectations.py` (`EXPECTATIONS`, `SAMPLE_PATHS`) and the url_map contract test are written by **V207-5b**, split from this task at the 20 KB cap.

Why a blueprint hook and not the decorators: a v1 route added without `@require_auth` is still covered. Flask runs `api_v1.before_request` functions before the view and its decorators, and only for requests routed to a blueprint endpoint, so unmatched `/api/v1/...` URLs still get the v1 404. A Basic-only request has no session principal, so the hook stays out and `require_auth` decides (Basic is admin-only, Decision 7).

- [ ] **Step 1: Write the failing unit and hook tests**

Create `tests/admin/test_access.py`:

```python
"""v207: check_access (pure, data-driven) and the api_v1 before_request hook
that enforces it on every v1 request."""
import pytest
from tests.admin.api_v1_contract import assert_error

from swingbot.admin import access
from swingbot.admin import api_v1 as v1  # noqa: F401  (reload-safe import idiom)

VIEWER = {"role": "viewer", "username": "viewer1", "user_id": 1}
ADMIN = {"role": "admin", "username": "admin", "user_id": None}
FORBIDDEN_BODY = {"error": {"code": "forbidden", "message": "Read-only account."}}


@pytest.mark.parametrize("method,path,allowed", [
    ("GET", "/api/v1/dashboard", True),
    ("HEAD", "/api/v1/dashboard", True),
    ("get", "/api/v1/dashboard", True),
    ("POST", "/api/v1/trades/clear-open", False),
    ("PUT", "/api/v1/trades/t1/note", False),
    ("DELETE", "/api/v1/trades/t1", False),
    ("OPTIONS", "/api/v1/dashboard", False),
    ("GET", "/api/v1/system", False),
    ("GET", "/api/v1/system/settings", False),
    ("GET", "/api/v1/system/scan", True),
    ("GET", "/api/v1/system/preferences", True),
    ("PUT", "/api/v1/system/preferences", False),
    ("GET", "/api/v1/system/scan/trigger", False),
    ("GET", "/api/v1/jobs", False),
    ("GET", "/api/v1/jobs/j1/result", False),
    ("GET", "/api/v1/users", False),
    ("GET", "/api/v1/users/3", False),
    ("GET", "/api/v1/analytics/tuning", False),
    ("GET", "/api/v1/analytics/tuning/proposals", False),
    ("GET", "/api/v1/analytics/performance", True),
    ("GET", "/api/v1/versions", False),
    ("GET", "/api/v1/versionsx", True),
    ("GET", "/api/v1/systematic", True),
    ("GET", "/api/v1/not-yet-written", True),
    ("POST", "/api/v1/not-yet-written", False),
    ("POST", "/api/v1/session", True),
    ("DELETE", "/api/v1/session", True),
])
def test_viewer_rules(method, path, allowed):
    assert access.check_access(VIEWER, method, path) is allowed


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/v1/system/bot/restart"), ("GET", "/api/v1/users"),
    ("DELETE", "/api/v1/trades/t1"), ("PUT", "/api/v1/system/preferences"),
])
def test_admin_and_no_principal_are_always_let_through(method, path):
    assert access.check_access(ADMIN, method, path) is True
    assert access.check_access(None, method, path) is True


@pytest.mark.parametrize("principal", [{"role": "operator"}, {}, {"role": None}])
def test_an_unknown_role_is_denied_even_a_read(principal):
    assert access.check_access(principal, "GET", "/api/v1/dashboard") is False


def test_prefixes_match_on_segment_boundaries_only():
    assert access.is_admin_only("/api/v1/jobs")
    assert access.is_admin_only("/api/v1/jobs/tune/defaults")
    assert not access.is_admin_only("/api/v1/jobsite")


# --- the hook, through real requests -----------------------------------------

def test_the_hook_is_installed_on_the_blueprint(admin_app):
    from swingbot.admin.api_v1 import access_hook

    assert access_hook.enforce_access in admin_app.before_request_funcs["api_v1"]


def test_a_viewer_write_is_refused_before_the_handler_runs(viewer_client, monkeypatch):
    from swingbot.core.marketdata import watchlist

    client, _row = viewer_client
    calls = []
    monkeypatch.setattr(watchlist, "add_ticker", lambda ticker: calls.append(ticker))
    r = client.post("/api/v1/watchlist/tickers", json={"tickers": ["MSFT"]})
    assert_error(r, "forbidden", 403)
    assert r.get_json() == FORBIDDEN_BODY
    assert calls == []


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/system/settings"), ("HEAD", "/api/v1/system/settings"),
    ("PUT", "/api/v1/system/preferences"), ("GET", "/api/v1/versions"),
])
def test_a_viewer_is_refused_admin_paths_and_writes(viewer_client, method, path):
    client, _row = viewer_client
    r = client.open(path, method=method, json={} if method == "PUT" else None)
    assert r.status_code == 403


def test_a_viewer_reads_the_shell_allowlist(viewer_client):
    client, _row = viewer_client
    assert client.get("/api/v1/system/preferences").status_code == 200


def test_the_admin_session_is_not_filtered(client, monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.backtest_cache.ensure_cached_background",
                        lambda ticker: None)
    client.post("/api/v1/session", json={"username": "admin", "password": "admin"})
    r = client.post("/api/v1/watchlist/tickers", json={"tickers": ["MSFT"]})
    assert r.status_code == 200, r.get_json()


def test_no_principal_still_gets_the_v1_401(client):
    assert_error(client.get("/api/v1/dashboard"), "auth", 401)


def test_basic_admin_reaches_admin_paths(admin_app, auth):
    r = admin_app.test_client().get("/api/v1/system/settings", headers=auth)
    assert r.status_code == 200


def test_the_hook_denies_a_route_it_has_never_seen(admin_app, monkeypatch):
    """Default-deny: the hook reads the method and path, not a decorator, so a
    route added later without @require_auth is still closed to viewer writes."""
    from swingbot.admin import app as admin_module
    from swingbot.admin.api_v1 import access_hook

    monkeypatch.setattr(admin_module, "resolve_principal", lambda: VIEWER)
    with admin_app.test_request_context("/api/v1/not-yet-written", method="POST"):
        response, status = access_hook.enforce_access()
    assert status == 403
    assert response.get_json() == FORBIDDEN_BODY
```

`add_ticker` is patched on `swingbot.core.marketdata.watchlist` because `add_tickers` imports it from there inside the handler (`watchlist.py:171`), so the patch is what the handler would call.

- [ ] **Step 2: Run them to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_access.py`
Expected: FAIL at collection — `ImportError: cannot import name 'access' from 'swingbot.admin'`.

- [ ] **Step 3: Write `swingbot/admin/access.py`**

```python
"""v207: who may call which /api/v1 route -- one pure, default-deny rule.

Spec: docs/superpowers/specs/2026-11-05-v207-viewer-accounts-design.md
§ Access check. Enforced by api_v1/access_hook.py (an api_v1.before_request),
so a route added later without @require_auth is still covered. The tables are
data; tests/admin/access_expectations.py classifies every Flask rule and
test_access_contract.py fails when this module disagrees with it.

Imports nothing from swingbot.admin: it is pure, and the hook imports it.
"""
from __future__ import annotations

from typing import Callable, Mapping

#: A viewer may call nothing under these, matched on segment boundaries
#: (`/api/v1/jobs` and `/api/v1/jobs/...`, never `/api/v1/jobsite`).
ADMIN_ONLY_PREFIXES: tuple[str, ...] = (
    "/api/v1/system",
    "/api/v1/users",
    "/api/v1/jobs",
    "/api/v1/analytics/tuning",
    "/api/v1/versions",
)

#: System reads the shell makes on every page: the freshness chip, scan strip
#: and live bot section (/system/scan) and the shared layout record
#: (/system/preferences, spec Decision 5). GET/HEAD only, exact paths.
VIEWER_GET_ALLOWLIST: frozenset[str] = frozenset({
    "/api/v1/system/scan",
    "/api/v1/system/preferences",
})

#: The sign-in door: every principal (and none) may read, open and close it.
EXEMPT_PATHS: frozenset[str] = frozenset({"/api/v1/session"})

READ_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def is_admin_only(path: str) -> bool:
    return any(_under(path, prefix) for prefix in ADMIN_ONLY_PREFIXES)


def _viewer_may(method: str, path: str) -> bool:
    if method.upper() not in READ_METHODS:
        return False
    return path in VIEWER_GET_ALLOWLIST or not is_admin_only(path)


def _admin_may(method: str, path: str) -> bool:
    return True


_ROLE_RULES: Mapping[str, Callable[[str, str], bool]] = {
    "admin": _admin_may,
    "viewer": _viewer_may,
}


def check_access(principal: Mapping | None, method: str, path: str) -> bool:
    """True when `principal` may call `method path`.

    No principal is not a refusal: the hook steps aside and `require_auth`
    answers 401 (or lets a Basic admin through). A role this table does not
    know is refused -- default deny."""
    if principal is None or path in EXEMPT_PATHS:
        return True
    rule = _ROLE_RULES.get(principal.get("role"))
    return rule is not None and rule(method, path)
```

- [ ] **Step 4: Write `swingbot/admin/api_v1/access_hook.py` and register it**

```python
"""v207: enforce swingbot.admin.access on every /api/v1 request.

A blueprint before_request, not a check inside require_auth: it runs for every
route routed to api_v1 -- decorated or not -- before the view. It lives here,
not in api_v1/__init__.py, because that module may import nothing from
swingbot.admin; register() imports this module before register_blueprint().
"""
from __future__ import annotations

from flask import request

from swingbot.admin import access
from swingbot.admin import app as _app  # module, not names: tests reload app

from . import api_v1, error

FORBIDDEN_MESSAGE = "Read-only account."


@api_v1.before_request
def enforce_access():
    """None lets the request through; a viewer outside its rights gets 403."""
    if access.check_access(_app.resolve_principal(), request.method, request.path):
        return None
    return error("forbidden", FORBIDDEN_MESSAGE, 403)
```

In `swingbot/admin/api_v1/__init__.py` `register()`, add `access_hook` to the endpoint import list. It must stay above `app.register_blueprint(api_v1)`: Flask refuses a new `before_request` on a blueprint that has already been registered.

```python
    from . import (access_hook, analytics, calendar, cancel_precision, dashboard, equity,  # noqa: F401
                   jobs, live, market, market_updates, ops_health, reports, research, risk, session,
                   system, trade_commands, trades, versions, watchlist)  # (routes + the v207 access hook)
```

- [ ] **Step 5: Run the unit and hook tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_access.py`
Expected: PASS.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_session.py`
Expected: PASS (the session door is exempt).

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`
Expected: PASS (`:800` monkeypatches `_session_authenticated` with no session; the hook sees no principal and stays out).

- [ ] **Step 6: Complexity gate**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: exit 0; `check_access` ≤ 3, `_viewer_may` ≤ 3, `enforce_access` 2 (auth cap 12).

- [ ] **Step 7: Commit**

```bash
git -C "<wt>" add swingbot/admin/access.py swingbot/admin/api_v1/access_hook.py swingbot/admin/api_v1/__init__.py tests/admin/test_access.py
git -C "<wt>" commit -m "feat(v207): default-deny viewer access check and api_v1 hook (V207-5)"
```

### Task V207-5b: url_map classification contract — `access_expectations.py` + contract test

**Model:** sonnet — the table and the test are spelled out in full below; the classification judgement is already made here, the work is transcription plus one run.

Split from V207-5 at the 20 KB cap; runs straight after it (index group C).

**Files:**
- Create: `tests/admin/access_expectations.py`
- Create: `tests/admin/test_access_contract.py`

**Interfaces:**
- Consumes: `access.check_access`, `access.EXEMPT_PATHS` (V207-5); fixture `admin_app` (`tests/admin/conftest.py`).
- Produces: `tests/admin/access_expectations.py` — `EXPECTATIONS: dict[tuple[str, str], str]` keyed `(rule, METHOD)` (HEAD/OPTIONS never listed) → `"public" | "viewer" | "admin"`; `SAMPLE_PATHS: dict[str, str]` (every rule with a converter → a concrete path that routes to it); `SPA_WORKSPACES: tuple[str, ...]`; `V1 = "/api/v1"`. V207-6 adds its five rows and two sample paths; V207-7 reads both.

Meaning of the three kinds: **public** — the role check does not apply (the `/api/v1/session` door and every non-v1 rule: SPA shell, assets); **viewer** — a viewer may call it; **admin** — a viewer gets 403 `forbidden`. The table is the source of truth (spec § Access check); `check_access` must agree with every row. Rows were taken from the live `app.url_map` on 2026-11-05 (115 rules, 26 non-GET v1 methods).

The contract is written red-first in the sense that matters: Step 3's first run is the moment the table meets the real url_map. A failure there is information about the table, not about the test.

- [ ] **Step 1: Write the checked-in expectation table**

Create `tests/admin/access_expectations.py` (rule strings exactly as `rule.rule` prints them):

```python
"""v207: every Flask rule x method, classified for the viewer role.

The source of truth for who may call what (spec § Access check):
  "public" -- the role check does not apply: the /api/v1/session door and
              every non-v1 rule (SPA shell, assets).
  "viewer" -- a viewer may call it.
  "admin"  -- a viewer gets 403 forbidden.
test_access_contract.py fails when a served rule is missing here, when a row
names a rule that is gone, and when swingbot.admin.access disagrees with a
row. Adding a route means adding its row here: decide, don't default.
"""
V1 = "/api/v1"

#: The SPA shell serves /<workspace> and /<workspace>/<path:_rest> (spa.py).
SPA_WORKSPACES = ("analytics", "calendar", "cancels", "cockpit", "dashboard", "insights",
                  "plans", "reports", "research", "risk", "system", "trades", "ui",
                  "universe", "versions", "watchlist")

_PUBLIC = [
    ("/", "GET"), ("/<any('ngsw-worker.js', 'ngsw.json'):filename>", "GET"),
    ("/app/<path:filename>", "GET"), ("/static/<path:filename>", "GET"),
    (f"{V1}/session", "GET"), (f"{V1}/session", "POST"), (f"{V1}/session", "DELETE"),
    *[(f"/{w}", "GET") for w in SPA_WORKSPACES],
    *[(f"/{w}/<path:_rest>", "GET") for w in SPA_WORKSPACES],
]

#: Viewer-readable GETs. /market/chart backfills a trendline fit and
#: /market/tape records demand and refreshes stale quotes: idempotent cache
#: fills any reader triggers, never a change to the book (V207-7 audit).
_VIEWER_GET = [
    "/analytics/by-dimension", "/analytics/calibration", "/analytics/cohort",
    "/analytics/equity-curve", "/analytics/exit-quality", "/analytics/heat-grid",
    "/analytics/journal", "/analytics/override-fidelity", "/analytics/partials",
    "/analytics/performance", "/analytics/plans", "/analytics/registry",
    "/analytics/snapshot", "/analytics/soak", "/analytics/strategies",
    "/analytics/variance-band",
    "/calendar/pnl", "/calendar/pnl/day", "/calendar/pnl/day/sparklines",
    "/cancel-precision", "/dashboard", "/equity/candles", "/events", "/health", "/live",
    "/market/chart/<ticker>", "/market/tape", "/market/updates",
    "/reports/expectancy-attribution", "/reports/gate-counterfactual", "/research/ledger",
    "/risk", "/risk/killswitch", "/system/preferences", "/system/scan",
    "/trades", "/trades/<trade_id>", "/trades/<trade_id>/journal", "/trades/export.csv",
    "/watchlist/suggest", "/watchlist/tickers",
]

_ADMIN_GET = [
    "/analytics/tuning/proposals", "/jobs", "/jobs/<job_id>", "/jobs/<job_id>/result",
    "/jobs/tune/defaults", "/system/health", "/system/logs", "/system/logs/raw",
    "/system/settings", "/system/settings/export", "/versions",
]

#: Every v1 write except the session door.
_ADMIN_WRITES = [
    ("/analytics/tuning/proposals", "POST"), ("/analytics/tuning/proposals/<filename>", "DELETE"),
    ("/jobs/tune", "POST"), ("/market/refresh", "POST"), ("/risk/killswitch", "POST"),
    ("/system/bot/restart", "POST"), ("/system/logs", "DELETE"),
    ("/system/preferences", "PUT"), ("/system/scan/pause", "POST"),
    ("/system/scan/resume", "POST"), ("/system/scan/stop", "POST"),
    ("/system/scan/trigger", "POST"), ("/system/settings", "PUT"),
    ("/system/settings/import", "POST"), ("/system/settings/preview", "POST"),
    ("/trades/<trade_id>", "DELETE"), ("/trades/<trade_id>/cancel", "POST"),
    ("/trades/<trade_id>/close", "POST"), ("/trades/<trade_id>/note", "PUT"),
    ("/trades/clear-history", "POST"), ("/trades/clear-open", "POST"),
    ("/trades/close-open", "POST"), ("/watchlist/tickers", "POST"),
    ("/watchlist/tickers/<symbol>", "DELETE"),
]

EXPECTATIONS: dict[tuple[str, str], str] = {
    **{key: "public" for key in _PUBLIC},
    **{(V1 + rule, "GET"): "viewer" for rule in _VIEWER_GET},
    **{(V1 + rule, "GET"): "admin" for rule in _ADMIN_GET},
    **{(V1 + rule, method): "admin" for rule, method in _ADMIN_WRITES},
}

#: Rule with converters -> a concrete path that routes to it. "t1" and "AAPL"
#: are the ids V207-7's matrix seeds.
SAMPLE_PATHS: dict[str, str] = {
    "/<any('ngsw-worker.js', 'ngsw.json'):filename>": "/ngsw.json",
    "/app/<path:filename>": "/app/main.js",
    "/static/<path:filename>": "/static/app.css",
    **{f"/{w}/<path:_rest>": f"/{w}/x" for w in SPA_WORKSPACES},
    f"{V1}/analytics/tuning/proposals/<filename>": f"{V1}/analytics/tuning/proposals/p.json",
    f"{V1}/jobs/<job_id>": f"{V1}/jobs/j1",
    f"{V1}/jobs/<job_id>/result": f"{V1}/jobs/j1/result",
    f"{V1}/market/chart/<ticker>": f"{V1}/market/chart/AAPL",
    f"{V1}/trades/<trade_id>": f"{V1}/trades/t1",
    f"{V1}/trades/<trade_id>/cancel": f"{V1}/trades/t1/cancel",
    f"{V1}/trades/<trade_id>/close": f"{V1}/trades/t1/close",
    f"{V1}/trades/<trade_id>/journal": f"{V1}/trades/t1/journal",
    f"{V1}/trades/<trade_id>/note": f"{V1}/trades/t1/note",
    f"{V1}/watchlist/tickers/<symbol>": f"{V1}/watchlist/tickers/AAPL",
}
```

- [ ] **Step 2: Write the contract test**

Create `tests/admin/test_access_contract.py`:

```python
"""v207: the url_map classification contract (spec § Access check).

Every served rule x method must be in tests/admin/access_expectations.py, and
swingbot.admin.access must agree with every row. A new route fails here until
its author classifies it."""
import pytest
from tests.admin.access_expectations import EXPECTATIONS, SAMPLE_PATHS

from swingbot.admin import access

VIEWER = {"role": "viewer", "username": "viewer1", "user_id": 1}
ADMIN = {"role": "admin", "username": "admin", "user_id": None}
SKIPPED_METHODS = {"HEAD", "OPTIONS"}


def _served(app) -> dict[tuple[str, str], str]:
    return {(rule.rule, method): rule.endpoint
            for rule in app.url_map.iter_rules()
            for method in rule.methods - SKIPPED_METHODS}


def test_every_served_rule_is_classified(admin_app):
    missing = sorted(_served(admin_app).keys() - EXPECTATIONS.keys())
    assert not missing, f"classify in tests/admin/access_expectations.py: {missing}"


def test_no_row_names_a_rule_that_is_gone(admin_app):
    stale = sorted(EXPECTATIONS.keys() - _served(admin_app).keys())
    assert not stale, f"remove from tests/admin/access_expectations.py: {stale}"


def test_kinds_are_the_three_known_ones():
    assert set(EXPECTATIONS.values()) <= {"public", "viewer", "admin"}


def test_every_converter_rule_has_a_sample_path_that_routes_to_it(admin_app):
    served = _served(admin_app)
    adapter = admin_app.url_map.bind("localhost")
    for rule, method in EXPECTATIONS:
        if "<" not in rule:
            continue
        assert rule in SAMPLE_PATHS, f"SAMPLE_PATHS needs {rule!r}"
        endpoint, _args = adapter.match(SAMPLE_PATHS[rule], method=method)
        assert endpoint == served[(rule, method)], (rule, method)


@pytest.mark.parametrize("key", sorted(EXPECTATIONS), ids=lambda key: f"{key[1]} {key[0]}")
def test_check_access_agrees_with_the_table(key):
    rule, method = key
    kind = EXPECTATIONS[key]
    path = SAMPLE_PATHS.get(rule, rule)
    assert access.check_access(ADMIN, method, path) is True
    assert access.check_access(None, method, path) is True
    assert access.check_access(VIEWER, method, path) is (kind != "admin")
    outside_role_check = path in access.EXEMPT_PATHS or not path.startswith("/api/v1/")
    assert outside_role_check is (kind == "public")
```

- [ ] **Step 3: Run the contract**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_access_contract.py`
Expected: PASS. If `test_every_served_rule_is_classified` names a rule, the url_map gained a route after this plan was written (2026-11-05: 115 rules): classify it by the spec's rules (write → `admin`; GET under an admin-only prefix → `admin`; other GET → `viewer`; non-v1 → `public`) and name it in the task report. Never loosen the test.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_access.py`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git -C "<wt>" add tests/admin/access_expectations.py tests/admin/test_access_contract.py
git -C "<wt>" commit -m "test(v207): url_map classification contract for viewer access (V207-5b)"
```

### Task V207-6: Users API + session invalidation

**Model:** sonnet — CRUD over a repository and validators that already exist, behind the access hook V207-5 built; the shapes are fixed below.

**Files:**
- Create: `swingbot/admin/api_v1/users.py`
- Modify: `swingbot/admin/api_v1/__init__.py` (`register()` import list: add `users`)
- Modify: `tests/admin/access_expectations.py` (five Users rows, two sample paths)
- Create: `tests/admin/test_api_v1_users.py`
- Create: `tests/admin/test_viewer_sessions.py`

**Interfaces:**
- Consumes: `admin_users.admin_users_repo()` and its `list_users`, `get_by_id`, `create_user` (raises `UsernameTaken`), `set_disabled`, `reset_password`, `delete_user` (V207-2, through the module `swingbot.core.db.repositories.admin_users` so tests that swap `_repo` are honoured); `principals.hash_password`, `validate_username`, `validate_password`, `authenticate_viewer`, `USERNAME_RULE`, `PASSWORD_RULE` (V207-3); `_app.ADMIN_USERNAME` (read per request, never at import); fixture `viewer_client` (V207-4b); `EXPECTATIONS` / `SAMPLE_PATHS` (V207-5b); `api_v1`, `error`, `iso` (`api_v1/__init__.py`), `require_auth` (`api_v1/auth.py`).
- Produces (V207-16's `ApiClient` mirrors these):
  - `GET /api/v1/users` → 200 `{"users": [UserOut, ...]}` ordered by id.
  - `POST /api/v1/users` `{username, password}` → 201 UserOut; 400 `invalid` (message names `username` or `password`); 409 `conflict` (duplicate, case-insensitive, or the `.env` admin's name).
  - `PATCH /api/v1/users/<int:user_id>` `{disabled: bool}` → 200 UserOut; 400 `invalid` when `disabled` is not a bool; 404 `not_found`.
  - `POST /api/v1/users/<int:user_id>/password` `{password}` → 204 empty; 400 `invalid`; 404 `not_found`.
  - `DELETE /api/v1/users/<int:user_id>` → 204 empty; 404 `not_found`.
  - UserOut = `{"id": int, "username": str, "role": "viewer", "disabled": bool, "created_at": ISO str, "last_login_at": ISO str | null}` — never `password_hash` or `credential_version`.
  - `users.user_out(row: dict) -> dict`.
  - INFO log per mutation, exactly `users: <action> <username> by admin` with action `create` / `disable` / `enable` / `reset-password` / `delete`.

Viewers never reach these handlers: `/api/v1/users` is an admin-only prefix, so V207-5's hook answers 403 first. `@require_auth` stays on every route for the no-principal 401. Session invalidation needs no code here — V207-2 bumps `credential_version` on disable and reset, and V207-4's `principal_from_session` re-checks the row on every request; this task proves it end to end.

- [ ] **Step 1: Write the failing Users API tests**

Create `tests/admin/test_api_v1_users.py`:

```python
"""v207: /api/v1/users -- viewer accounts, managed by the .env admin only."""
import logging

import pytest
from tests.admin.api_v1_contract import NULLABLE_STR, assert_error, assert_shape

from swingbot.admin import api_v1 as v1  # noqa: F401  (reload-safe import idiom)
from swingbot.admin import principals
from swingbot.core.db.repositories.admin_users import admin_users_repo

USER_SHAPE = {"id": int, "username": str, "role": str, "disabled": bool,
              "created_at": str, "last_login_at": NULLABLE_STR}
NEW = {"username": "viewer1", "password": "viewer-password-1"}


@pytest.fixture
def api(client, auth):
    """Admin over Basic: no session cookie, so the access hook steps aside."""
    def call(method, path, **kwargs):
        return client.open(f"/api/v1{path}", method=method, headers=auth, **kwargs)
    return call


def _create(api, **overrides):
    return api("POST", "/users", json={**NEW, **overrides})


def test_the_list_starts_empty(api):
    r = api("GET", "/users")
    assert r.status_code == 200
    assert r.get_json() == {"users": []}


def test_create_returns_the_user_and_never_the_hash(api):
    r = _create(api)
    assert r.status_code == 201
    body = r.get_json()
    assert_shape(body, USER_SHAPE)
    assert body["username"] == "viewer1" and body["role"] == "viewer"
    assert body["disabled"] is False and body["last_login_at"] is None


def test_the_list_never_carries_a_hash(api):
    _create(api)
    r = api("GET", "/users")
    stored = admin_users_repo().get_by_username("viewer1")["password_hash"]
    text = r.get_data(as_text=True)
    assert "password_hash" not in text and stored not in text
    assert "credential_version" not in text
    [user] = r.get_json()["users"]
    assert_shape(user, USER_SHAPE)


def test_a_duplicate_is_a_conflict_whatever_its_case(api):
    _create(api)
    assert_error(_create(api, username="Viewer1"), "conflict", 409)


@pytest.mark.parametrize("name", ["admin", "ADMIN", "Admin"])
def test_the_env_admins_name_cannot_be_taken(api, name):
    assert_error(_create(api, username=name), "conflict", 409)
    assert admin_users_repo().list_users() == []


@pytest.mark.parametrize("body,field", [
    ({"username": "viewer1", "password": "x" * 11}, "password"),
    ({"username": "a b", "password": "viewer-password-1"}, "username"),
    ({"username": "ab", "password": "viewer-password-1"}, "username"),
    ({"password": "viewer-password-1"}, "username"),
    ({"username": "viewer1"}, "password"),
    ({}, "username"),
])
def test_bad_input_is_invalid_and_names_the_field(api, body, field):
    r = api("POST", "/users", json=body)
    assert_error(r, "invalid", 400)
    assert r.get_json()["error"]["message"].startswith(field)


def test_a_non_object_body_is_invalid(api):
    assert_error(api("POST", "/users", json=["viewer1"]), "invalid", 400)


def test_disable_bumps_the_credential_version_and_enable_does_not(api):
    user = _create(api).get_json()
    r = api("PATCH", f"/users/{user['id']}", json={"disabled": True})
    assert r.status_code == 200
    assert r.get_json()["disabled"] is True
    assert admin_users_repo().get_by_id(user["id"])["credential_version"] == 2
    r = api("PATCH", f"/users/{user['id']}", json={"disabled": False})
    assert r.get_json()["disabled"] is False
    assert admin_users_repo().get_by_id(user["id"])["credential_version"] == 2


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_disabled_must_be_a_bool(api, value):
    user = _create(api).get_json()
    assert_error(api("PATCH", f"/users/{user['id']}", json={"disabled": value}), "invalid", 400)


def test_reset_password_is_204_and_the_new_password_works(api):
    user = _create(api).get_json()
    r = api("POST", f"/users/{user['id']}/password", json={"password": "a-new-password-2"})
    assert r.status_code == 204
    assert r.get_data() == b""
    assert admin_users_repo().get_by_id(user["id"])["credential_version"] == 2
    assert principals.authenticate_viewer("viewer1", "a-new-password-2") is not None
    assert principals.authenticate_viewer("viewer1", "viewer-password-1") is None


def test_reset_with_a_short_password_is_invalid(api):
    user = _create(api).get_json()
    r = api("POST", f"/users/{user['id']}/password", json={"password": "short"})
    assert_error(r, "invalid", 400)
    assert r.get_json()["error"]["message"].startswith("password")


def test_delete_is_204_then_404(api):
    user = _create(api).get_json()
    r = api("DELETE", f"/users/{user['id']}")
    assert r.status_code == 204
    assert api("GET", "/users").get_json() == {"users": []}
    assert_error(api("DELETE", f"/users/{user['id']}"), "not_found", 404)


@pytest.mark.parametrize("method,path,body", [
    ("PATCH", "/users/999", {"disabled": True}),
    ("POST", "/users/999/password", {"password": "a-new-password-2"}),
    ("DELETE", "/users/999", None),
])
def test_an_unknown_id_is_404(api, method, path, body):
    assert_error(api(method, path, json=body), "not_found", 404)


def test_mutations_log_the_action_and_nothing_secret(api, caplog):
    caplog.set_level(logging.INFO, logger="swingbot.admin.api_v1.users")
    user = _create(api).get_json()
    api("PATCH", f"/users/{user['id']}", json={"disabled": True})
    api("PATCH", f"/users/{user['id']}", json={"disabled": False})
    api("POST", f"/users/{user['id']}/password", json={"password": "a-new-password-2"})
    api("DELETE", f"/users/{user['id']}")
    lines = [rec.getMessage() for rec in caplog.records if rec.name.endswith("users")]
    assert lines == ["users: create viewer1 by admin", "users: disable viewer1 by admin",
                     "users: enable viewer1 by admin", "users: reset-password viewer1 by admin",
                     "users: delete viewer1 by admin"]
    assert "viewer-password-1" not in caplog.text and "a-new-password-2" not in caplog.text


def test_without_a_principal_every_route_is_401(client):
    assert_error(client.get("/api/v1/users"), "auth", 401)
    assert_error(client.post("/api/v1/users", json=NEW), "auth", 401)


@pytest.mark.parametrize("method,suffix,body", [
    ("GET", "", None), ("POST", "", NEW), ("PATCH", "/{id}", {"disabled": True}),
    ("POST", "/{id}/password", {"password": "a-new-password-2"}), ("DELETE", "/{id}", None),
])
def test_a_viewer_is_refused_every_users_route(viewer_client, method, suffix, body):
    client, row = viewer_client
    path = "/api/v1/users" + suffix.format(id=row["id"])
    assert_error(client.open(path, method=method, json=body), "forbidden", 403)
    assert admin_users_repo().get_by_id(row["id"])["disabled"] is False
```

- [ ] **Step 2: Write the failing session-invalidation tests**

Create `tests/admin/test_viewer_sessions.py`:

```python
"""v207: disable, password reset and delete end a viewer's live session on its
next request; disable -> re-enable leaves it dead (credential_version)."""
import pytest
from tests.admin.api_v1_contract import assert_error

from swingbot.admin import api_v1 as v1  # noqa: F401  (reload-safe import idiom)

READ = "/api/v1/system/preferences"  # allowlisted viewer GET with no fixture data


@pytest.fixture
def admin(admin_app, auth):
    """A SECOND client for the admin: the viewer's client carries a viewer
    cookie, and the session principal wins over a Basic header."""
    other = admin_app.test_client()

    def call(method, path, **kwargs):
        return other.open(f"/api/v1{path}", method=method, headers=auth, **kwargs)
    return call


def _signed_in(client) -> bool:
    return client.get("/api/v1/session").get_json()["authenticated"]


def _assert_dead(client):
    assert_error(client.get(READ), "auth", 401)
    assert _signed_in(client) is False


def test_the_viewer_session_works_before_anything_changes(viewer_client, admin):
    client, _row = viewer_client
    assert admin("GET", "/users").status_code == 200
    assert client.get(READ).status_code == 200
    assert _signed_in(client) is True


def test_disable_ends_the_session(viewer_client, admin):
    client, row = viewer_client
    assert admin("PATCH", f"/users/{row['id']}", json={"disabled": True}).status_code == 200
    _assert_dead(client)


def test_disable_then_enable_leaves_the_old_session_dead(viewer_client, admin):
    client, row = viewer_client
    admin("PATCH", f"/users/{row['id']}", json={"disabled": True})
    admin("PATCH", f"/users/{row['id']}", json={"disabled": False})
    _assert_dead(client)


def test_enabling_an_enabled_user_keeps_the_session(viewer_client, admin):
    client, row = viewer_client
    admin("PATCH", f"/users/{row['id']}", json={"disabled": False})
    assert client.get(READ).status_code == 200


def test_password_reset_ends_the_session(viewer_client, admin):
    client, row = viewer_client
    r = admin("POST", f"/users/{row['id']}/password", json={"password": "a-new-password-2"})
    assert r.status_code == 204
    _assert_dead(client)


def test_after_a_reset_the_new_password_signs_in(viewer_client, admin):
    client, row = viewer_client
    admin("POST", f"/users/{row['id']}/password", json={"password": "a-new-password-2"})
    r = client.post("/api/v1/session",
                    json={"username": "viewer1", "password": "a-new-password-2"})
    assert r.status_code == 200
    assert r.get_json()["role"] == "viewer"
    assert client.get(READ).status_code == 200


def test_delete_ends_the_session(viewer_client, admin):
    client, row = viewer_client
    assert admin("DELETE", f"/users/{row['id']}").status_code == 204
    _assert_dead(client)
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_users.py`
Expected: FAIL — every case gets the v1 404 `not_found`: there is no `/api/v1/users` route yet, and an unmatched URL never reaches a blueprint `before_request`, so even the viewer cases 404 instead of 403.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_viewer_sessions.py`
Expected: FAIL — the admin's `/users` calls 404.

- [ ] **Step 4: Write `swingbot/admin/api_v1/users.py`**

```python
"""v207: /api/v1/users -- viewer accounts, managed by the .env admin.

Spec: docs/superpowers/specs/2026-11-05-v207-viewer-accounts-design.md
§ Users API. Admin-only by prefix (swingbot.admin.access): the api_v1 access
hook refuses every viewer before these handlers run; @require_auth still
answers 401 when there is no principal at all.

Never returns, logs or serialises a password, a hash or credential_version.
Disable and password reset bump credential_version in the repository, which
is what ends a viewer's live sessions (app.principal_from_session).
"""
from __future__ import annotations

import logging

from flask import jsonify, request

from swingbot.admin import app as _app  # module, not names: tests reload app
from swingbot.admin import principals
from swingbot.core.db.repositories import admin_users

from . import api_v1, error, iso
from .auth import require_auth

log = logging.getLogger(__name__)

TAKEN = "username is already taken."


def user_out(row: dict) -> dict:
    """The one public shape of a viewer row (UserOut)."""
    return {"id": row["id"], "username": row["username"], "role": row["role"],
            "disabled": row["disabled"], "created_at": iso(row["created_at"]),
            "last_login_at": iso(row["last_login_at"])}


def _body() -> dict:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _not_found(user_id: int):
    return error("not_found", f"No user with id {user_id}.", 404)


def _audit(action: str, username: str) -> None:
    log.info("users: %s %s by admin", action, username)


def _create_problem(username, password):
    """The 400/409 answer for a create request, or None when it may proceed."""
    message = principals.validate_username(username) or principals.validate_password(password)
    if message:
        return error("invalid", message, 400)
    if username.lower() == _app.ADMIN_USERNAME.lower():
        return error("conflict", TAKEN, 409)
    return None


@api_v1.route("/users", methods=["GET"])
@require_auth
def list_users():
    return jsonify({"users": [user_out(r) for r in admin_users.admin_users_repo().list_users()]})


@api_v1.route("/users", methods=["POST"])
@require_auth
def create_user():
    body = _body()
    username, password = body.get("username"), body.get("password")
    problem = _create_problem(username, password)
    if problem is not None:
        return problem
    try:
        row = admin_users.admin_users_repo().create_user(
            username, principals.hash_password(password))
    except admin_users.UsernameTaken:
        return error("conflict", TAKEN, 409)
    _audit("create", row["username"])
    return jsonify(user_out(row)), 201


@api_v1.route("/users/<int:user_id>", methods=["PATCH"])
@require_auth
def update_user(user_id: int):
    disabled = _body().get("disabled")
    if not isinstance(disabled, bool):
        return error("invalid", "disabled must be true or false.", 400)
    row = admin_users.admin_users_repo().set_disabled(user_id, disabled)
    if row is None:
        return _not_found(user_id)
    _audit("disable" if disabled else "enable", row["username"])
    return jsonify(user_out(row))


@api_v1.route("/users/<int:user_id>/password", methods=["POST"])
@require_auth
def reset_user_password(user_id: int):
    password = _body().get("password")
    message = principals.validate_password(password)
    if message:
        return error("invalid", message, 400)
    row = admin_users.admin_users_repo().reset_password(
        user_id, principals.hash_password(password))
    if row is None:
        return _not_found(user_id)
    _audit("reset-password", row["username"])
    return "", 204


@api_v1.route("/users/<int:user_id>", methods=["DELETE"])
@require_auth
def delete_user(user_id: int):
    repo = admin_users.admin_users_repo()
    row = repo.get_by_id(user_id)
    if row is None or not repo.delete_user(user_id):
        return _not_found(user_id)
    _audit("delete", row["username"])
    return "", 204
```

`validate_username` runs before the admin-name comparison, so `username.lower()` only ever sees a validated `str`.

In `swingbot/admin/api_v1/__init__.py` `register()`, add `users` to the import list (alphabetical, after `trades`):

```python
    from . import (access_hook, analytics, calendar, cancel_precision, dashboard, equity,  # noqa: F401
                   jobs, live, market, market_updates, ops_health, reports, research, risk, session,
                   system, trade_commands, trades, users, versions, watchlist)  # (routes + the v207 access hook)
```

- [ ] **Step 5: Classify the five new rules**

In `tests/admin/access_expectations.py`, below `_ADMIN_WRITES`:

```python
#: v207 Users API (V207-6): admin-only by prefix, reads and writes alike.
_USERS = [
    ("/users", "GET"), ("/users", "POST"), ("/users/<int:user_id>", "PATCH"),
    ("/users/<int:user_id>", "DELETE"), ("/users/<int:user_id>/password", "POST"),
]
```

add `**{(V1 + rule, method): "admin" for rule, method in _USERS},` as the last line of `EXPECTATIONS`, and these two entries at the end of `SAMPLE_PATHS`:

```python
    f"{V1}/users/<int:user_id>": f"{V1}/users/1",
    f"{V1}/users/<int:user_id>/password": f"{V1}/users/1/password",
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_users.py`
Expected: PASS.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_viewer_sessions.py`
Expected: PASS.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_access_contract.py`
Expected: PASS (the five `/users` rules are classified; without Step 5 `test_every_served_rule_is_classified` names them).

- [ ] **Step 7: Complexity gate**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: exit 0; every function in `users.py` ≤ 4 (auth cap 12).

- [ ] **Step 8: Commit**

```bash
git -C "<wt>" add swingbot/admin/api_v1/users.py swingbot/admin/api_v1/__init__.py tests/admin/access_expectations.py tests/admin/test_api_v1_users.py tests/admin/test_viewer_sessions.py
git -C "<wt>" commit -m "feat(v207): admin-only Users API; disable/reset/delete end viewer sessions (V207-6)"
```

### Task V207-7: Viewer route matrix, payload leakage, Basic-viewer 401, side-effect GET audit

**Model:** sonnet — a parametrized sweep over the table V207-5b and V207-6 built; the only judgement (the GET side-effect audit) is already recorded below.

**Files:**
- Create: `tests/admin/test_viewer_route_matrix.py`
- Modify (only if the run in Step 2 finds a GET that changes the book, settings or watchlist): `swingbot/admin/access.py` and `tests/admin/access_expectations.py`, reclassifying that GET `admin`.

**Interfaces:**
- Consumes: `EXPECTATIONS`, `SAMPLE_PATHS` (V207-5b, V207-6); fixture `viewer_client` (V207-4b); `seed_store` (`tests/store_seed.py`); `assert_error` (`tests/admin/api_v1_contract.py`).
- Produces: nothing later tasks import.

**GET side-effect audit (done while writing this plan, 2026-11-05).** `/market/chart/<ticker>` backfills a missing trendline fit (`market.py:215-265`: an idempotent cache fill; the store refuses to overwrite an existing fit). `/market/tape` records symbol demand and self-fetches stale quotes (`market.py:689-751`: cache warming). `/market/updates` reads with `enqueue=False` (`market_updates.py:82-84`). `/live` and the live-event rows only read. None of them changes the book, settings or the watchlist, and an admin opening the same page triggers the same fill, so all stay `viewer`; the test module's docstring records this. The implementer re-reads those four handlers and, if one has gained a real write since, reclassifies it `admin` in both files and says so in the task report.

The matrix asserts **2xx with fixture data**, not "not 403": each viewer-readable GET is fetched by the admin (Basic, second client) and by the viewer, and both must be 2xx with the same status. A route that is not 2xx for the admin either is a gap in this file's fixture (`_book`, `_offline`, `QUERIES`) — fix the fixture, never widen the accepted statuses.

- [ ] **Step 1: Write the matrix**

Create `tests/admin/test_viewer_route_matrix.py`:

```python
"""v207: the viewer route matrix (spec § Testing).

- Every viewer-classified GET answers a viewer 2xx with fixture data, and the
  same status the admin gets for the same URL.
- Every admin-classified rule x method answers a viewer 403 forbidden, and a
  sweep of viewer writes leaves the book untouched.
- /dashboard and /live: the viewer's payload has the admin's keys and none
  naming users or credentials.
- Viewer credentials over HTTP Basic are 401 (Decision 7); a viewer session
  plus an admin Basic header is still the viewer.

GET side-effect audit (2026-11-05, V207-7): /market/chart/<ticker> backfills a
stored trendline fit (idempotent cache fill), /market/tape records demand and
refreshes stale quotes (cache warming), /market/updates reads with
enqueue=False, /live only reads. None changes the book, settings or the
watchlist, so all stay "viewer" in tests/admin/access_expectations.py.
"""
import base64

import numpy as np
import pandas as pd
import pytest
from tests.admin.access_expectations import EXPECTATIONS, SAMPLE_PATHS
from tests.admin.api_v1_contract import assert_error
from tests.store_seed import seed_store

from swingbot.admin import api_v1 as v1  # noqa: F401  (reload-safe import idiom)

#: SSE never ends; V207-8 covers /events (tests/admin/test_event_stream.py).
STREAMING = {"/api/v1/events"}

#: Query strings a GET needs to answer 2xx (tests/admin/test_api_v1_*.py use the same).
QUERIES = {
    "/api/v1/analytics/by-dimension": "?dim=strategy",
    "/api/v1/calendar/pnl/day": "?date=2026-08-04",
    "/api/v1/calendar/pnl/day/sparklines": "?date=2026-08-04",
    "/api/v1/market/tape": "?symbols=AAPL",
    "/api/v1/watchlist/suggest": "?q=AA",
}

#: Keys that would mean a Users or session secret leaked into a read payload.
LEAK_KEYS = {"password_hash", "credential_version", "pw_hash", "admin_authed", "users", "user_id"}

VIEWER_GETS = sorted(rule for (rule, method), kind in EXPECTATIONS.items()
                     if kind == "viewer" and method == "GET" and rule not in STREAMING)
ADMIN_CASES = sorted(key for key, kind in EXPECTATIONS.items() if kind == "admin")
WRITE_METHODS = {"POST", "PUT", "PATCH"}


def _trade(trade_id: str) -> dict:
    """One closed AAPL trade -- the shape tests/admin/test_api_v1_trades.py seeds."""
    return {
        "id": trade_id, "plan_id": None, "ticker": "AAPL", "strategy": "RSI Divergence",
        "horizon_key": "1m", "direction": "bullish", "confidence_level": 4,
        "confidence_label": "High", "confidence_score": 81.0, "entry": 101.0,
        "stop_loss": 95.0, "take_profit": 110.0, "target2": None, "risk_reward_ratio": 1.8,
        "tier": "A", "badge": "VALIDATED", "quality_score": 72, "source": "strategy",
        "legs": [], "opened_at": "2026-08-01T10:00:00+00:00", "status": "win",
        "closed_at": "2026-08-04T15:00:00+00:00", "exit_price": 108.0,
        "realized_pnl_amount": 70.0, "shares": 10, "position_value": 1010.0,
        "target_sources": [], "stop_sources": [], "target2_sources": [],
        "confirmed_by": [], "explanation": None, "confidence_breakdown": None,
    }


def _frame(n: int = 300) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=n)
    close = pd.Series(50 + np.cumsum(np.random.default_rng(3).normal(0, .5, n)), index=idx)
    return pd.DataFrame({"Open": close, "High": close + .5, "Low": close - .5,
                         "Close": close, "Volume": 9_999}, index=idx)


@pytest.fixture
def _book(admin_app):
    """Trade "t1" and watchlist ticker "AAPL": the ids SAMPLE_PATHS names."""
    seed_store("trades", [_trade("t1")])
    seed_store("watchlist", ["AAPL"])


@pytest.fixture
def _offline(monkeypatch):
    """Every network edge the readable GETs touch, stubbed as their own tests do."""
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda ticker: _frame())
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data_batch", lambda syms: {})
    monkeypatch.setattr("swingbot.core.marketdata.data.get_company_name", lambda t: f"{t} Inc.")
    monkeypatch.setattr("swingbot.core.market.events.get_next_earnings_datetime", lambda t: None)
    monkeypatch.setattr("swingbot.admin.watchlist_rows.get_daily_data_batch",
                        lambda tickers, period="6mo": {})
    monkeypatch.setattr("swingbot.admin.watchlist_rows.is_us_market_active", lambda: False)
    monkeypatch.setattr("swingbot.core.marketdata.backtest_cache.ensure_cached_background",
                        lambda t: None)


@pytest.fixture
def admin_get(admin_app, auth):
    """The admin on a SECOND client: the viewer's cookie would win over Basic."""
    other = admin_app.test_client()
    return lambda url: other.get(url, headers=auth)


def _url(rule: str) -> str:
    return SAMPLE_PATHS.get(rule, rule) + QUERIES.get(rule, "")


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def _basic(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_the_matrix_is_not_empty():
    assert len(VIEWER_GETS) >= 40 and len(ADMIN_CASES) >= 40


@pytest.mark.parametrize("rule", VIEWER_GETS)
def test_a_viewer_reads_every_viewer_get_with_data(viewer_client, admin_get, _book, _offline, rule):
    client, _row = viewer_client
    url = _url(rule)
    theirs = admin_get(url)
    assert 200 <= theirs.status_code < 300, f"fixture gap for {url}: admin got {theirs.status_code}"
    mine = client.get(url)
    assert mine.status_code == theirs.status_code, (url, mine.get_data(as_text=True)[:200])


@pytest.mark.parametrize("rule,method", ADMIN_CASES)
def test_a_viewer_is_refused_every_admin_rule(viewer_client, rule, method):
    client, _row = viewer_client
    body = {} if method in WRITE_METHODS else None
    assert_error(client.open(SAMPLE_PATHS.get(rule, rule), method=method, json=body),
                 "forbidden", 403)


def test_a_sweep_of_viewer_writes_changes_nothing(viewer_client, admin_get, _book, _offline):
    client, _row = viewer_client
    for rule, method in ADMIN_CASES:
        if method != "GET":
            client.open(SAMPLE_PATHS.get(rule, rule), method=method,
                        json={} if method in WRITE_METHODS else None)
    assert admin_get("/api/v1/trades/t1").status_code == 200
    tickers = admin_get("/api/v1/watchlist/tickers").get_json()
    assert "AAPL" in str(tickers)


@pytest.mark.parametrize("path", ["/api/v1/dashboard", "/api/v1/live"])
def test_viewer_payloads_carry_the_admins_keys_and_no_secrets(viewer_client, admin_get,
                                                              _book, _offline, path):
    client, _row = viewer_client
    mine, theirs = client.get(path), admin_get(path)
    assert mine.status_code == theirs.status_code == 200
    assert _keys(mine.get_json()) == _keys(theirs.get_json())
    assert not _keys(mine.get_json()) & LEAK_KEYS


def test_viewer_credentials_over_basic_are_401(admin_app, viewer_client):
    fresh = admin_app.test_client()
    r = fresh.get("/api/v1/dashboard", headers=_basic("viewer1", "viewer-password-1"))
    assert_error(r, "auth", 401)


def test_a_viewer_session_with_an_admin_basic_header_is_still_the_viewer(viewer_client, auth):
    client, _row = viewer_client
    assert_error(client.get("/api/v1/system/settings", headers=auth), "forbidden", 403)
    assert client.get("/api/v1/session").get_json()["role"] == "viewer"
```

`ADMIN_CASES` runs every write with an empty JSON body: the hook answers before any handler parses it, so the body's content never matters.

- [ ] **Step 2: Run the matrix**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_viewer_route_matrix.py`
Expected: PASS. This file adds tests over code V207-5..V207-6 already shipped, so there is no red step; a failure is a finding:
- `fixture gap for <url>: admin got 4xx/5xx` — the URL needs data or a stub this fixture lacks. Read that route's own test file (`tests/admin/test_api_v1_<module>.py`) and copy its seed, stub or query into `_book`, `_offline` or `QUERIES`. Never accept a non-2xx status.
- a viewer status that differs from the admin's — a real defect in V207-4/V207-5: stop and report it.
- a non-empty `LEAK_KEYS` intersection — a real leak: stop and report it.

If the Step 1 audit note turned out wrong for a handler (a GET that writes the book, settings or watchlist), move that rule from `_VIEWER_GET` to `_ADMIN_GET` in `tests/admin/access_expectations.py`, add its exact path to `ADMIN_ONLY_PREFIXES` in `swingbot/admin/access.py` (segment-boundary match) with a `test_access.py::test_viewer_rules` case, rerun this file, `tests/admin/test_access.py` and `tests/admin/test_access_contract.py`, and record the change in the task report and the commit.

- [ ] **Step 3: Commit**

```bash
git -C "<wt>" add tests/admin/test_viewer_route_matrix.py
git -C "<wt>" commit -m "test(v207): viewer route matrix, payload keys, Basic-viewer 401 (V207-7)"
```

# Phase D — live stream

### Task V207-8: SSE re-check: stream closes for a revoked viewer

**Model:** sonnet — one optional callable threaded into an existing generator, with the request-context trap spelled out below.

**Files:**
- Modify: `swingbot/admin/events/stream.py` (`event_stream` :62-90, `events` :104-136, imports :31-45)
- Modify: `tests/admin/test_event_stream.py` (tests appended)

**Interfaces:**
- Consumes: `_app.principal_from_session(data: Mapping) -> dict | None` (no request context needed) and `_app.resolve_principal()` (V207-4, through the module); fixture `viewer_client` (V207-4b); `admin_users_repo().set_disabled` (V207-2).
- Produces:
  - `event_stream(subscription, broker, *, ping_interval: float = PING_INTERVAL, still_valid: Callable[[], bool] | None = None) -> Iterator[str]` — `None` keeps today's behaviour (existing direct-call tests pass unchanged); otherwise it is called after every `subscription.get()` (each ping interval, and after each event) and the generator returns, closing the subscription, the first time it is False.
  - `session_snapshot() -> dict` — the current session's principal fields (`admin_authed`, `pw_hash`, `role`, `user_id`, `credential_version`, `username`), copied while the request context exists.
  - `events()` passes `ping_interval=PING_INTERVAL` explicitly (read at call time, so a test can shorten it) and `still_valid` built from the snapshot when the connection was authenticated by session; a Basic-only connection (no session principal) gets `None`, as today.

Why a snapshot: the WSGI server consumes the generator after `events()` has returned, so `flask.session`, `request` and `g` are gone inside it (brief § events/stream.py). `principal_from_session` re-reads the `admin_users` row (viewer) or recomputes `_password_hash()` (admin) on every call, so disable, password reset and delete — and an admin password change — end the stream within one ping interval (20 s); the next connect is the v1 401. Event payloads already carry only `{"seq", "at"}` (`Event.data()`, `events/broker.py:74`); the event name is the table channel. Nothing System-only travels, so there is no viewer filter — a test pins the shape instead (index note).

- [ ] **Step 1: Write the failing tests**

In `tests/admin/test_event_stream.py`, add below `import pytest` (:18):

```python
from tests.admin.api_v1_contract import assert_error
```

then append at the end of the file:

```python
# --------------------------------------------------------------------------
# v207: the principal is re-checked on every loop pass
# --------------------------------------------------------------------------

class OneEventSubscription(SilentSubscription):
    """A subscription that always has an event waiting."""

    def get(self, timeout=None):
        self.timeouts.append(timeout)
        return b.Event(seq=7, event="trades", at="2026-11-05T00:00:00+00:00")


def test_the_stream_ends_when_still_valid_turns_false(broker):
    subscription = SilentSubscription()
    valid = {"ok": True}
    generator = s.event_stream(subscription, broker, ping_interval=0.01,
                               still_valid=lambda: valid["ok"])
    assert next(generator).startswith("event: resync")
    assert next(generator).startswith("event: ping")
    valid["ok"] = False
    with pytest.raises(StopIteration):
        next(generator)
    assert subscription.closed


def test_a_revoked_principal_is_not_sent_the_waiting_event(broker):
    subscription = OneEventSubscription()
    generator = s.event_stream(subscription, broker, ping_interval=0.01,
                               still_valid=lambda: False)
    assert next(generator).startswith("event: resync")
    with pytest.raises(StopIteration):
        next(generator)
    assert subscription.closed


def test_session_snapshot_copies_only_the_principal_fields(admin_app):
    from flask import session

    with admin_app.test_request_context("/api/v1/events"):
        session.update({"role": "viewer", "user_id": 4, "credential_version": 2,
                        "username": "viewer1", "unrelated": "x"})
        snapshot = s.session_snapshot()
    assert snapshot == {"role": "viewer", "user_id": 4, "credential_version": 2,
                        "username": "viewer1"}


def test_a_viewer_disabled_mid_stream_is_cut_off(viewer_client, broker, monkeypatch):
    from swingbot.core.db.repositories.admin_users import admin_users_repo

    monkeypatch.setattr(s, "PING_INTERVAL", 0.01)
    client, row = viewer_client
    response = client.get("/api/v1/events")
    assert response.status_code == 200
    iterator = iter(response.response)
    assert next(iterator).decode("utf-8").startswith("event: resync")
    assert next(iterator).decode("utf-8").startswith("event: ping")
    admin_users_repo().set_disabled(row["id"], True)
    with pytest.raises(StopIteration):
        next(iterator)
    response.response.close()
    assert_error(client.get("/api/v1/events"), "auth", 401)


def test_an_admin_session_stream_ends_when_the_admin_password_changes(client, broker,
                                                                      monkeypatch):
    from swingbot.admin import app as admin_module

    monkeypatch.setattr(s, "PING_INTERVAL", 0.01)
    client.post("/api/v1/session", json={"username": "admin", "password": "admin"})
    response = client.get("/api/v1/events")
    iterator = iter(response.response)
    assert next(iterator).decode("utf-8").startswith("event: resync")
    monkeypatch.setattr(admin_module, "ADMIN_PASSWORD", "changed-password")
    with pytest.raises(StopIteration):
        next(iterator)
    response.response.close()


def test_a_basic_admin_stream_is_not_rechecked(client, auth, broker, monkeypatch):
    """Basic carries no session principal: nothing to revoke mid-stream."""
    from swingbot.admin import app as admin_module

    monkeypatch.setattr(s, "PING_INTERVAL", 0.01)
    response = client.get("/api/v1/events", headers=auth)
    monkeypatch.setattr(admin_module, "principal_from_session",
                        lambda data: pytest.fail("Basic stream re-checked a session"))
    names = [frame["name"] for frame in take(response, 3)]
    assert names == ["resync", "ping", "ping"]


def test_a_viewer_stream_carries_only_seq_and_at(viewer_client, broker):
    client, _row = viewer_client
    response = client.get("/api/v1/events")
    broker.publish("settings")
    resync, event = take(response, 2)
    assert event["name"] == "settings"
    assert set(event["data"]) == {"seq", "at"}
    assert set(resync["data"]) == {"seq", "at"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_event_stream.py`
Expected: FAIL — `TypeError: event_stream() got an unexpected keyword argument 'still_valid'`, `AttributeError: module ... has no attribute 'session_snapshot'`, and the viewer-disabled / admin-password cases get another `ping` instead of `StopIteration`. The pre-v207 tests and `test_a_viewer_stream_carries_only_seq_and_at` pass.

- [ ] **Step 3: Implement the re-check in `swingbot/admin/events/stream.py`**

Imports (replace the `from typing import Iterator` and `from flask import Response, request` lines; add the `_app` import beside the other `swingbot.admin` imports):

```python
from typing import Callable, Iterator

from flask import Response, request, session

from swingbot.admin import app as _app  # module, not names: tests reload app
```

`stream.py` is imported from `api_v1.register()` at the bottom of `app.py`, the same point `api_v1/auth.py` already imports `app` as a module, so this adds no new import-order constraint.

Below `_now()`, add:

```python
#: Session keys app.principal_from_session reads.
_PRINCIPAL_KEYS = ("admin_authed", "pw_hash", "role", "user_id", "credential_version", "username")


def session_snapshot() -> dict:
    """The session's principal fields, copied while the request context exists.

    v207: the generator below runs after events() has returned, when
    flask.session is gone, so it re-checks a copy."""
    return {key: session[key] for key in _PRINCIPAL_KEYS if key in session}


def _revalidator(snapshot: dict) -> Callable[[], bool] | None:
    """A re-check for a session-authenticated stream; None for Basic auth,
    which has no session principal to revoke mid-stream."""
    if _app.resolve_principal() is None:
        return None
    return lambda: _app.principal_from_session(snapshot) is not None
```

Replace `event_stream` with:

```python
def event_stream(
    subscription: Subscription,
    broker: EventBroker,
    *,
    ping_interval: float = PING_INTERVAL,
    still_valid: Callable[[], bool] | None = None,
) -> Iterator[str]:
    """Frames for one connection, until the consumer closes the generator.

    Opens with a `resync`. Decision 4: recovery is a resync and not a
    replay, and that applies to the first connection exactly as it does to
    the thousandth reconnect -- the client has just arrived, whatever it is
    displaying is of unknown age, and one refetch fixes that regardless of
    how long it was away or how much it missed.

    v207: `still_valid`, when given, is asked after every wait -- each ping
    interval, and before each event is sent -- and the stream ends the first
    time it says no, so a disabled, reset or deleted viewer is cut off within
    one heartbeat and meets the 401 on reconnect.
    """
    try:
        # The current high-water mark, not a fresh number: see EventBroker.seq.
        yield _frame("resync", {"seq": broker.seq, "at": _now()}, event_id=broker.seq)
        while True:
            event = subscription.get(timeout=ping_interval)
            if still_valid is not None and not still_valid():
                return
            if event is None:
                # No `id:` -- a ping is not a change, and giving it one would
                # have the browser hand it back as Last-Event-ID, naming a
                # position at which nothing happened.
                yield _frame("ping", {"at": _now()})
            else:
                yield _frame(event.event, event.data(), event_id=event.seq)
    finally:
        # Reached on GeneratorExit when the client hangs up, which is how
        # every one of these connections ends -- and, since v207, when the
        # principal is revoked. Without it the slot is held until the process
        # restarts and the cap of 8 becomes a countdown.
        subscription.close()
```

In `events()`, replace the `Response(...)` construction with:

```python
    # v207: the generator outlives the request context, so the principal's
    # session fields are copied now and re-checked on every loop pass.
    still_valid = _revalidator(session_snapshot())
    response = Response(
        event_stream(subscription, broker, ping_interval=PING_INTERVAL, still_valid=still_valid),
        mimetype="text/event-stream",
    )
```

and add to its docstring: "v207: a session-authenticated stream re-checks its principal each ping interval and ends when it is revoked; Basic connections are not re-checked."

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_event_stream.py`
Expected: PASS, including every pre-v207 test unchanged (`test_the_ping_interval_is_twenty_seconds` still reads `s.PING_INTERVAL == 20.0`: the monkeypatches are per test).

- [ ] **Step 5: Complexity gate**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: exit 0; `event_stream` ≤ 6, `events` ≤ 3, `session_snapshot` / `_revalidator` ≤ 3 (auth cap 12).

- [ ] **Step 6: Commit**

```bash
git -C "<wt>" add swingbot/admin/events/stream.py tests/admin/test_event_stream.py
git -C "<wt>" commit -m "feat(v207): SSE stream re-checks its principal and closes for a revoked viewer (V207-8)"
```

