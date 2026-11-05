# v207 — Viewer accounts: read-only users beside the global admin (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v207 — Viewer accounts](../specs/2026-11-05-v207-viewer-accounts-design.md) (main @ 622f5327)

## Goal

The admin UI at bomeo-capital.com has exactly one login, the `.env`
`ADMIN_USERNAME` / `ADMIN_PASSWORD` pair, and that login can do everything:
change Settings, cancel or delete trades, edit the watchlist, trigger scans,
restart the bot. The partner wants to hand other people a login that can
**look at** the book and the setups but **change nothing** and never reach the
System area. Today the only way to show someone the book is to give them the
keys to it.

Once this ships, the global admin is unchanged (still `.env`, never stored, so
it cannot be locked out), and the admin can create **viewer** accounts from a
new Users tab under System. A viewer logs in through the normal web login and
sees Dashboard, Trades, Watchlist, Risk and Insights, with every write control
hidden, the System nav entry gone, the Analytics Tuning tab gone and a
"Read-only · <name>" badge in the header. Disabling, deleting or resetting the
password of a viewer ends their live session on the next request and their
live event stream within one heartbeat.

The idea: one database table (`admin_users`, Alembic `v207_001`), one principal
resolver in `app.py` that every auth path goes through, and one
**default-deny** access check enforced by a single `api_v1.before_request`
hook. A viewer may only `GET`/`HEAD`, and never under an admin-only prefix
(`/system`, `/users`, `/jobs`, `/analytics/tuning`, `/versions`) except two
shell reads (`/system/scan`, `/system/preferences`). A checked-in expectation
table classifies every Flask rule; a route someone adds later fails a test
until it is classified. The server is the security boundary; the SPA hides
controls as presentation only.

What it leaves alone: the `.env` admin and its session shape (it only gains
`role`), HTTP Basic auth (admin-only, no table lookup), Discord commands,
preferences (viewers read the admin's record, never save), every response body
except `/session` (adds `role`), and every non-v1 route. No `.env` change, no
flag: an empty `admin_users` table is exactly today's behaviour.

Success is measured by tests, not by a metric (`Edge: none (integrity)`): the
url_map classification contract, a parametrized viewer matrix (every non-GET
v1 route 403, every viewer-readable GET 2xx with fixture data), the login
matrix with identical failure bodies, session invalidation on disable / reset
/ delete (and disable → re-enable staying dead), the SSE cut-off, the
pre-migration `UndefinedTable` window answering "invalid credentials" not 500,
and the frontend specs (guard, directive, nav, inventory, preferences no-save,
403 toast suppression, Users page at three widths).

## Architecture

- **Data** (V207-1, V207-2): `admin_users` declared in
  `swingbot/core/db/schema.py` (promoted columns + standard `doc`/`updated_at`,
  `PROMOTION_REASONS` rows, functional unique index on `lower(username)`, CHECK
  `role IN ('viewer')`), Alembic `v207_001` revising the head at implementation
  time (`v205_001` today). `AdminUsersRepository` on `repositories/base.py`
  catches `UndefinedTable` (a `sqlalchemy.exc.ProgrammingError` whose `.orig`
  is `psycopg.errors.UndefinedTable`), logs one warning, answers "no such
  user".
- **Principals** (V207-3, V207-4): `swingbot/admin/principals.py` owns password
  hashing (werkzeug, `HASH_METHOD` module attribute so tests swap scrypt for a
  cheap method), username/password validation and the viewer lookups. It never
  imports `swingbot.admin.app`. `app.py` gains `login_session_fields()` (admin
  first via `credentials_match`, then the table), `principal_from_session()`
  and `resolve_principal()` (cached on `flask.g` per request);
  `_session_authenticated()` becomes `resolve_principal() is not None`.
  `login_limiter.attempt_login()` is the principal-returning variant for
  `POST /session`; `attempt()` keeps its bool shape for Basic.
- **Access** (V207-5): pure `swingbot/admin/access.py:check_access()` over data
  tables; enforced by `swingbot/admin/api_v1/access_hook.py` (a
  `@api_v1.before_request`), imported inside `api_v1.register()` because
  `api_v1/__init__.py` may import nothing from `swingbot.admin`.
- **Users API** (V207-6): `swingbot/admin/api_v1/users.py`, admin-only by
  prefix.
- **Stream** (V207-8): `events()` snapshots the session's principal fields at
  connect; `event_stream(..., still_valid=None)` re-checks on every loop pass
  and returns when it is false.
- **SPA** (V207-9..V207-17): new `frontend/src/app/auth/` folder (guard,
  `*ifAdmin` directive, 403 toast interceptor, write-call inventory);
  `SessionStore` gains `role`/`isAdmin`; nav consumers filter through
  `navEntriesFor()`; the Users page is a System tab (`/system?tab=users`).

**Tech stack:** Python 3.11, Flask, SQLAlchemy + psycopg 3, Alembic, werkzeug
security, pytest; Angular (standalone components, signals, `@ngrx/signals`),
Vitest via `frontend/scripts/ng-test.mjs`.

## Global Constraints

- **Two roles only:** `admin` (the `.env` account, never stored) and `viewer` (every `admin_users` row). CHECK `role IN ('viewer')`.
- Revision id `v207_001` (file `swingbot/core/db/migrations/versions/v207_001_admin_users.py`); `down_revision` = what `python -m alembic heads` prints at implementation time (`v205_001` today).
- Username `^[A-Za-z0-9._-]{3,64}$`, unique case-insensitively; a name equal to `ADMIN_USERNAME` (case-insensitive) is rejected with 409 `conflict`. Password minimum **12** characters.
- Password hashes: werkzeug `generate_password_hash(pw, method=principals.HASH_METHOD)` (default `"scrypt"`); unknown username still runs one `check_password_hash` against a dummy hash computed once per method. Never log, return or serialise a password or hash.
- Login failure body for every failing case (wrong password, unknown user, disabled user, pre-migration table): exactly `401 {"error": {"code": "auth", "message": "Invalid username or password."}}`. Every attempt goes through `login_limiter`.
- Basic auth stays admin-only: `api_v1/auth.py:require_auth` keeps calling `login_limiter.attempt(..., _app.credentials_match)`; Basic credentials never reach `admin_users`.
- Session fields — admin: `admin_authed=True`, `pw_hash`, `role="admin"`; viewer: `role="viewer"`, `user_id`, `credential_version`, `username`. A session with `admin_authed` + valid `pw_hash` and no `role` key (issued before deploy) is still the admin.
- Principal dict shape: `{"role": "admin" | "viewer", "username": str, "user_id": int | None}`.
- `credential_version` is bumped on **disable** and on **password reset**; re-enable does not bump. A viewer session is valid only while its row exists, is not disabled and has the same `credential_version`.
- Forbidden body: `403 {"error": {"code": "forbidden", "message": "Read-only account."}}`.
- Admin-only prefixes, segment-boundary match (`path == p or path.startswith(p + "/")`): `/api/v1/system`, `/api/v1/users`, `/api/v1/jobs`, `/api/v1/analytics/tuning`, `/api/v1/versions`. Viewer GET allowlist: `/api/v1/system/scan`, `/api/v1/system/preferences`. Exempt: `/api/v1/session`. Viewer methods: `GET`, `HEAD` only.
- Users mutations log `users: <action> <username> by admin` at INFO, nothing else about the user.
- `api_v1/__init__.py` imports nothing from `swingbot.admin`; v1 modules reach app functions through the module (`from swingbot.admin import app as _app`; `_app.resolve_principal()`), because `tests/admin/conftest.py` reloads `app` per test.
- Complexity: every new or changed auth function (principals, `access.py`, hook, resolver, login, limiter, stream) ≤ **12**; every touched function < 15 (`python scripts/dev/complexity_gate.py`). Legacy `app.require_auth` is not touched.
- Write controls are **hidden** for viewers (`*ifAdmin`), never shown disabled; the trade note renders as read-only text for viewers. The shell `KillswitchChip` is a read-only link and stays visible; the gated control is the Risk workspace Engage/Release buttons.
- Every UI change is checked at mobile 390 px, tablet 820 px and desktop 1440 px (`docs/claude/ui-design.md`); touch targets ≥ 44 px.
- Narrow test runs only: backend `python scripts/dev/testrun.py file <test>`; frontend `node <wt>/frontend/scripts/ng-test.mjs <wt>/frontend --include <spec>`. **No task runs the full suite**: CI does after the push. A task that touches the DB runs `/replicate-prod-db` first (shared `swing-db` container, port 56789).
- Implementation happens in the worktree `.claude/worktrees/2026-11-05-v207-viewer-accounts` (`<wt>` below); every command names `<wt>`. Commit per task on the branch; do not commit on `main`.

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| A data | V207-1 → V207-2 | `schema.py`, migration, `repositories/admin_users.py` | V207-2 builds on the table V207-1 declares |
| B auth core | V207-3 → V207-4 | `admin/principals.py` → `app.py`, `login_limiter.py`, `api_v1/session.py` | V207-4 calls V207-3's functions; needs Group A |
| C access + users | V207-5 → V207-5b → V207-6 → V207-7 | `access.py`, `api_v1/access_hook.py`, `api_v1/__init__.py`, `api_v1/users.py`, `tests/admin/access_expectations.py` | V207-6 adds its routes to V207-5's expectation table; V207-7 tests through both; all need V207-4's `resolve_principal` |
| D stream | V207-8 | `events/stream.py` | needs V207-4's `principal_from_session`; disjoint from C, may run beside it |
| E SPA auth | V207-9 → (V207-10 ‖ V207-11 ‖ V207-12) | `auth/`, `session.store.ts`, `models.ts`, `app.routes.ts` → nav/shell; interceptors/preferences; `write-calls.ts` | V207-10..12 consume `isAdmin` / `IfAdminDirective` |
| F SPA gating | V207-13 ‖ V207-14 ‖ V207-15 | trades + trade-detail; dashboard + row-actions + trade-drawer; watchlist + risk + analytics | each needs V207-9's `IfAdminDirective`; files disjoint |
| G Users page | V207-16 → V207-17 | `api-client.ts`, `models.ts`, `users.store.ts`, `write-calls.ts` → `system.store.ts`, `system.ts`, `users-tab.ts` | V207-16 needs V207-12's inventory (adds its rows) and V207-6's API shape; V207-17 consumes V207-16's store |
| H release | V207-18 | `docs/deploy/DEPLOY_HETZNER.md`, `VERSION.json`, `swingbot/admin/version_history.json` | needs every other task merged |

Groups A→B are strictly sequential. Backend (A–D) and SPA (E–G) share only the
HTTP contracts fixed in the ledger below (the `/session` body with `role`, the
`/users` shapes, the `forbidden` error code), so the SPA groups may start as
soon as the plan is approved. Inside F the three tasks touch disjoint files.
`models.ts` is touched by V207-9 (`Identity.role`) and V207-16 (`AdminUser`),
in that order. `write-calls.ts` is created by V207-12 and extended by V207-16.
`tests/admin/access_expectations.py` is created by V207-5b and extended by
V207-6. `tests/admin/conftest.py` is touched only by V207-3 (fast-hash fixture)
and V207-4 (viewer-login helper fixture), in that order.

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V207-1 | `admin_users` table + Alembic `v207_001` | 1 | opus | M `swingbot/core/db/schema.py`; C `swingbot/core/db/migrations/versions/v207_001_admin_users.py`; M `tests/db/test_unknown_field_round_trip.py` (V207-1: `admin_users` in `NOT_REPOSITORY_BACKED`; V207-2 moves it to `CASES`); C `tests/db/test_v207_admin_users.py` | `schema.admin_users` table: `id` BigInteger PK, `username` Text NOT NULL, `password_hash` Text NOT NULL, `role` Text NOT NULL default `'viewer'`, `disabled` Boolean NOT NULL default false, `credential_version` Integer NOT NULL default 1, `created_at` TIMESTAMPTZ NOT NULL default now(), `last_login_at` TIMESTAMPTZ NULL, + `doc`, `updated_at`; index `admin_users_username_lower_uq` on `lower(username)` unique; CHECK `admin_users_role_ck`; revision `v207_001` |
| V207-2 | `AdminUsersRepository` with the `UndefinedTable` guard | 1 | sonnet | C `swingbot/core/db/repositories/admin_users.py`; C `tests/db/test_admin_users_repository.py` | `admin_users_repo() -> AdminUsersRepository`; methods `list_users() -> list[dict]` (by id), `get_by_username(username) -> dict \| None` (case-insensitive), `get_by_id(user_id: int) -> dict \| None`, `create_user(username, password_hash, *, role="viewer") -> dict` (raises `UsernameTaken`), `set_disabled(user_id, disabled: bool) -> dict \| None` (bumps `credential_version` when disabling), `reset_password(user_id, password_hash) -> dict \| None` (bumps), `delete_user(user_id) -> bool`, `touch_last_login(user_id) -> None`; `class UsernameTaken(Exception)`; row dict keys `id, username, password_hash, role, disabled, credential_version, created_at, last_login_at` |
| V207-3 | `principals.py`: hashing, validation, viewer authentication | 1 | sonnet | C `swingbot/admin/principals.py`; C `tests/admin/test_principals.py`; M `tests/admin/conftest.py` (autouse `_fast_password_hash`) | `HASH_METHOD = "scrypt"`; `hash_password(pw) -> str`; `verify_password(pw_hash \| None, pw) -> bool` (dummy-hash check when None); `validate_username(name) -> str \| None` (error message naming `username`); `validate_password(pw) -> str \| None` (names `password`); `authenticate_viewer(username, password) -> dict \| None` (row on success, touches `last_login_at`; None for unknown/disabled/wrong/table missing); `viewer_principal(user_id, credential_version) -> dict \| None` (principal dict) |
| V207-4 | `resolve_principal`, principal login, `/session` role | 1 | opus | M `swingbot/admin/app.py`; M `swingbot/admin/login_limiter.py`; M `swingbot/admin/api_v1/session.py`; M `tests/admin/test_api_v1_session.py`; C `tests/admin/test_viewer_login.py`; M `tests/admin/conftest.py` (`viewer_client` fixture) | app: `login_session_fields(username, password) -> dict \| None`; `principal_from_session(data: Mapping) -> dict \| None`; `resolve_principal() -> dict \| None` (cached on `g`); `_session_authenticated()` = `resolve_principal() is not None`. limiter: `LoginAttempt(result, retry_after)` with `.ok`; `attempt_login(username, password, authenticate) -> LoginAttempt`. `/session` body `{"authenticated", "username", "role"}`. Fixture `viewer_client(client) -> (client, row)` logged in as viewer `viewer1` / `viewer-password-1` |
| V207-4b | `/api/v1/session` on principals: `role` in body, `viewer_client` fixture, HTTP sign-in tests | 1b | opus | M `swingbot/admin/api_v1/session.py`; M `tests/admin/test_api_v1_session.py`; M `tests/admin/conftest.py` (`viewer_client`); C `tests/admin/test_viewer_login.py` | `/session` body `{"authenticated", "username", "role"}`; fixture `viewer_client(client) -> (client, row)`. Later parts take `viewer_client` and the `role` body from here, not V207-4 |
| V207-5 | `check_access` + `api_v1` access hook | 2 | opus | C `swingbot/admin/access.py`; C `swingbot/admin/api_v1/access_hook.py`; M `swingbot/admin/api_v1/__init__.py` (import `access_hook` in `register()`); C `tests/admin/test_access.py` | `access.ADMIN_ONLY_PREFIXES: tuple[str, ...]`; `access.VIEWER_GET_ALLOWLIST: frozenset[str]`; `access.EXEMPT_PATHS`; `access.READ_METHODS`; `check_access(principal: dict \| None, method: str, path: str) -> bool` (None ⇒ True); `access_hook.enforce_access()` |
| V207-5b | url_map classification contract — `access_expectations.py` + contract test | 2 | sonnet | C `tests/admin/access_expectations.py`; C `tests/admin/test_access_contract.py` | `access_expectations.EXPECTATIONS: dict[tuple[str, str], str]` keyed `(rule, METHOD)` → `"public" \| "viewer" \| "admin"`; `access_expectations.SAMPLE_PATHS: dict[str, str]` (rule with converters → concrete path); `SPA_WORKSPACES`, `V1` |
| V207-6 | Users API + session invalidation | 2 | sonnet | C `swingbot/admin/api_v1/users.py`; M `swingbot/admin/api_v1/__init__.py` (import `users`); M `tests/admin/access_expectations.py` (5 rows); C `tests/admin/test_api_v1_users.py`; C `tests/admin/test_viewer_sessions.py` | `GET /api/v1/users` → `{"users": [UserOut]}`; `POST /api/v1/users` `{username, password}` → 201 UserOut; `PATCH /api/v1/users/<int:user_id>` `{disabled}` → 200 UserOut; `POST /api/v1/users/<int:user_id>/password` `{password}` → 204; `DELETE /api/v1/users/<int:user_id>` → 204; 404 `not_found`, 409 `conflict`, 400 `invalid`. UserOut = `{id: int, username: str, role: "viewer", disabled: bool, created_at: ISO str, last_login_at: ISO str \| null}` |
| V207-7 | Viewer route matrix, payload leakage, Basic-viewer 401, side-effect GET audit | 2 | sonnet | C `tests/admin/test_viewer_route_matrix.py`; M `swingbot/admin/access.py` + `tests/admin/access_expectations.py` (only if a GET with write side effects is reclassified `admin`) | — |
| V207-8 | SSE re-check: stream closes for a revoked viewer | 2 | sonnet | M `swingbot/admin/events/stream.py`; M `tests/admin/test_event_stream.py` | `event_stream(subscription, broker, *, ping_interval=PING_INTERVAL, still_valid: Callable[[], bool] \| None = None)`; `session_snapshot() -> dict` in stream.py |
| V207-9 | SPA: `role` on Identity/SessionStore, `adminGuard`, `*ifAdmin` | 3 | sonnet | M `frontend/src/app/api/models.ts`; M `frontend/src/app/stores/session.store.ts` (+ spec); C `frontend/src/app/auth/admin.guard.ts` (+ spec); C `frontend/src/app/auth/if-admin.directive.ts` (+ spec); M `frontend/src/app/app.routes.ts` (+ `app.routes.spec.ts`) | `type Role = 'admin' \| 'viewer'`; `Identity { authenticated: boolean; username: string \| null; role: Role \| null }`; `SessionStore.role: Signal<Role \| null>`, `.isAdmin: Signal<boolean>`, `.isViewer: Signal<boolean>`; `adminGuard: CanMatchFn` (true or UrlTree `/dashboard`); `IfAdminDirective` selector `[ifAdmin]` (use `*ifAdmin`), standalone |
| V207-10 | Nav hiding (rail, More sheet, palette) + read-only badge | 3 | sonnet | M `frontend/src/app/shell/nav.ts` (+ `nav.spec.ts`); M `frontend/src/app/shell/shell.ts`, `shell.html` (+ `shell.spec.ts`); M `frontend/src/app/shell/more-sheet.ts` (+ spec); M `frontend/src/app/shell/palette/palette-items.ts` and its caller (+ spec); C `frontend/src/app/shell/read-only-badge.ts` (+ spec) | `navEntriesFor(isAdmin: boolean, entries = NAV_ENTRIES): readonly NavEntry[]`; `ReadOnlyBadge` selector `sb-read-only-badge` |
| V207-11 | 403 toast interceptor + preferences no-save for viewers | 3 | sonnet | C `frontend/src/app/auth/forbidden.interceptor.ts` (+ spec); M `frontend/src/app/app.config.ts`; M `frontend/src/app/stores/preferences.store.ts` (+ spec) | `forbiddenInterceptor: HttpInterceptorFn` (array position before `errorInterceptor`); `FORBIDDEN_TOAST = 'Read-only account'` |
| V207-12 | Write-call inventory + completeness spec | 3 | sonnet | C `frontend/src/app/auth/write-calls.ts`; C `frontend/src/app/auth/write-calls.spec.ts` | `type WriteGate = 'public' \| 'admin-route' \| 'if-admin' \| 'hidden-tab' \| 'store-no-save'`; `WRITE_CALLS: Readonly<Record<string, WriteGate>>` keyed by `ApiClient` method name |
| V207-13 | Gate trades workspace + trade detail | 4 | sonnet | M `frontend/src/app/workspaces/trades/trades.ts` (+ spec); M `frontend/src/app/workspaces/trades/trade-detail.ts` (+ spec) | — |
| V207-14 | Gate dashboard: row actions, close-all, market refresh | 4 | sonnet | M `frontend/src/app/workspaces/dashboard/dashboard.ts` (+ spec); M `frontend/src/app/workspaces/dashboard/row-actions.ts` (+ spec); M `frontend/src/app/workspaces/dashboard/trade-drawer.ts` (+ spec) | — |
| V207-15 | Gate watchlist, Risk killswitch buttons, Analytics Tuning tab | 4 | sonnet | M `frontend/src/app/workspaces/watchlist/watchlist.ts` (+ spec); M `frontend/src/app/workspaces/risk/risk.ts` (+ spec); M `frontend/src/app/workspaces/analytics/analytics.ts` (+ `analytics.spec.ts`) | `visibleAnalyticsTabs(isAdmin)` local to `analytics.ts` |
| V207-16 | Users API client, models, `UsersStore` | 5 | sonnet | M `frontend/src/app/api/api-client.ts`; M `frontend/src/app/api/models.ts`; M `frontend/src/app/auth/write-calls.ts`; C `frontend/src/app/stores/users.store.ts` (+ spec) | `AdminUser` interface (= UserOut); `ApiClient.listUsers(): Observable<AdminUser[]>`, `.createUser(body: { username: string; password: string }): Observable<AdminUser>`, `.setUserDisabled(id: number, disabled: boolean): Observable<AdminUser>`, `.resetUserPassword(id: number, password: string): Observable<void>`, `.deleteUser(id: number): Observable<void>`; `UsersStore` (`users`, `status`, `error`, `load()`, `create()`, `setDisabled()`, `resetPassword()`, `remove()`) |
| V207-17 | Users tab: table / cards, dialogs, empty state, three widths | 5 | sonnet | M `frontend/src/app/stores/system.store.ts` (`SYSTEM_TABS` + `'users'`); M `frontend/src/app/workspaces/system/system.ts` (+ `system.spec.ts`); C `frontend/src/app/workspaces/system/users-tab.ts` (+ spec) | `UsersTab` selector `sb-users-tab` |
| V207-18 | DEPLOY_HETZNER v207 section, version bump, history | 5 | haiku | M `docs/deploy/DEPLOY_HETZNER.md`; M `VERSION.json`; M `swingbot/admin/version_history.json` (regenerated by `python scripts/dev/build_version_matrix.py`) | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-05-v207-viewer-accounts_1-data-and-login.md` | V207-1..V207-4 | table + migration, repository, principals, resolver + login + `/session` role |
| 1b | `2026-11-05-v207-viewer-accounts_1b-session.md` | V207-4b | `/session` role, `viewer_client` fixture, sign-in tests (split from V207-4 for size) |
| 2 | `2026-11-05-v207-viewer-accounts_2-access-users-stream.md` | V207-5, V207-5b, V207-6..V207-8 | default-deny access + contract, Users API + invalidation, viewer matrix, SSE re-check |
| 3 | `2026-11-05-v207-viewer-accounts_3-spa-auth.md` | V207-9..V207-12 | session role, guard, directive, nav + badge, 403 toast + preferences, write-call inventory |
| 4 | `2026-11-05-v207-viewer-accounts_4-spa-gating.md` | V207-13..V207-15 | hide write controls on trades, dashboard, watchlist, risk, analytics |
| 5 | `2026-11-05-v207-viewer-accounts_5-users-page-release.md` | V207-16..V207-18 | Users client + store, Users tab, deploy doc + release |

## Notes for part writers

- The spec's Testing line "Tuning tab and `KillswitchChip` hidden" predates the
  622f5327 correction: the chip stays; V207-15 tests the Risk Engage/Release
  buttons (`.kill-actions`, `data-action="killswitch"`) hidden for viewers and
  the chip still rendered.
- Scan controls render only inside System (`scan-tab.ts`), already behind
  `adminGuard`; no per-control gating outside System.
- `/api/v1/events` is classified `viewer` (GET, outside admin prefixes).
  `Event.data()` carries only `{"seq", "at"}`; V207-8 pins that with a test
  rather than adding a filter.
- V207-7 skims GET handlers under `/market/*` and `/live*` for write side
  effects; any found is reported in the task's result and, if real,
  reclassified `admin` in `access.py` and the expectation table in that task.
