# v207 — Viewer accounts: read-only users beside the global admin

**Version:** ui 1.39.0 · bot 2.16.4
**Bump:** ui minor, bot minor (new user-visible capability: viewer logins and a Users page)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, senior-engineer

## Why

The admin UI (bomeo-capital.com) has exactly one login: `ADMIN_USERNAME` /
`ADMIN_PASSWORD` from `.env`, checked by `swingbot/admin/app.py:credentials_match`
and by both `require_auth` decorators (`app.py`, `api_v1/auth.py`). Anyone who
can log in can change Settings, cancel or delete trades, edit the watchlist,
trigger scans and restart the bot. The partner wants to give other people a
login that can **look at** the book and the setups but **change nothing** and
never reach Settings.

## Decisions (agreed 2026-11-05 brainstorm)

1. **Two roles only.** The `.env` account is the **global admin** — unchanged,
   never stored in the database, so it can never be disabled or locked out.
   Every database user is a **viewer**. A `role` column exists so another role
   can be added later without a migration of data; a CHECK constraint allows
   only `viewer` today.
2. **Viewers are managed in the admin UI** — a Users page, visible only to the
   global admin. No CLI, no `.env` list, no self-signup.
3. **Viewers see everything except the System area.** Dashboard, Trades
   (incl. calendar, cancels, trade and plan detail), Watchlist, Risk and
   Insights are readable. `/system/**` (Settings, ops health, jobs, logs,
   versions, the new Users page) is admin-only, in the SPA and in the API.
   The Insights → Analytics **Tuning tab** is an admin tool (it runs tune jobs
   and saves proposals) and is hidden for viewers like the System area.
4. **Write controls are hidden for viewers**, not shown disabled. The server is
   the security boundary; hiding is presentation.
5. **Preferences:** viewers load the admin's shared preferences record
   read-only. Layout changes they make last for the browser session only and
   are never saved. No per-user preferences.
6. **Enforcement is default-deny in the shared auth layer** (approach A), not
   per-route decorators: a route someone adds later is closed to viewers until
   it is classified, and a test fails while it is unclassified.
7. **Viewers log in through the web session only.** HTTP Basic auth stays an
   admin-only path (scripts, the test `auth` fixture); Basic credentials that
   are not the `.env` admin's are rejected without a table lookup. This keeps
   scrypt off every scripted request and leaves `login_limiter.attempt` and
   `credentials_match` with their current bool shape for Basic.

## Design

### Data — `admin_users` (Alembic revision `v207_001_admin_users`)

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | |
| `username` | text, unique on `lower(username)` | 3–64 chars, `[A-Za-z0-9._-]` |
| `password_hash` | text | werkzeug `generate_password_hash` (scrypt default) |
| `role` | text, CHECK `role IN ('viewer')` | |
| `disabled` | bool, default false | |
| `credential_version` | int, default 1 | bumped on password reset and on disable |
| `created_at` | timestamptz | |
| `last_login_at` | timestamptz null | |

Starts empty; no data migration. The table is declared in
`swingbot/core/db/schema.py` beside the other tables; the revision's
`down_revision` is whatever `python -m alembic heads` prints at implementation
time (`v205_001` today). The store is
`swingbot/core/db/repositories/admin_users.py`, built on `repositories/base.py`
like its neighbours (Postgres-only per `schema-evolution.md`), exposing
`list_users`, `get_by_username`, `get_by_id`, `create_user`, `set_disabled`,
`reset_password`, `delete_user`, `touch_last_login`.

**Before the migration has run** (the containers start before
`alembic upgrade head` in `deploy/deploy.sh`), a lookup that raises
`UndefinedTable` is treated as "no such user": logged once as a warning,
answered as invalid credentials, never a 500. The `.env` admin is checked
first and never touches the table, so the admin is unaffected in that window.

### Auth — principals

- **Login** (`POST /api/v1/session`) tries the `.env` admin first (existing
  constant-time `credentials_match`), then the table. Unknown username still
  runs one dummy `check_password_hash` so timing does not reveal account
  existence. Disabled users and wrong passwords get the identical "invalid
  credentials" answer. Every attempt still goes through `login_limiter`; the
  session route gets a principal-returning check, Basic keeps the bool one
  (Decision 7).
- A username equal to `ADMIN_USERNAME` (case-insensitive) cannot be created.
- **Session payload:** admin keeps today's `admin_authed` + `pw_hash`, plus
  `role="admin"`. A viewer session stores `role="viewer"`, `user_id`,
  `credential_version`. On every request a viewer session is re-checked
  against the row: missing row, `disabled`, or a different
  `credential_version` ⇒ unauthenticated. Disable, delete and password reset
  therefore end live sessions immediately — the same property `_password_hash`
  gives the admin today.
- `GET /api/v1/session` additionally returns `role` (`admin` | `viewer`) and
  the username for either.
- **One resolver.** `_session_authenticated()` (`app.py`) becomes
  `resolve_principal()` returning `{role, username, user_id|None}` or `None`;
  `_session_authenticated()` remains as `resolve_principal() is not None` for
  existing callers. `_identity()` (`api_v1/session.py`), both `require_auth`
  decorators, the access hook and `/api/v1/events` all go through it, so they
  cannot drift.
- `credential_version` is bumped on **disable** as well as on password reset,
  so re-enabling a user does not revive sessions issued before the disable.

### Access check — default-deny

A new module `swingbot/admin/access.py` holds one pure function
`check_access(principal, method, path) -> bool` and its tables. It is enforced
by a single **`api_v1.before_request` hook**, not inside the decorators, so a
v1 route added without `@require_auth` is still covered. (Non-v1 rules are only
the SPA shell and static assets; `app.require_auth` wraps no route today and
gets no 403 variant.)

- No principal ⇒ the hook does nothing; `require_auth` answers 401 as today.
  `/api/v1/session` (GET/POST/DELETE) is exempt.
- `role == "admin"` ⇒ allow.
- `role == "viewer"` ⇒ allow only if the method is `GET`/`HEAD` **and** either
  the path is on the viewer GET allowlist, or it is under no admin-only prefix.
  - Admin-only prefixes, matched on **segment boundaries**
    (`path == p or path.startswith(p + "/")`): `/api/v1/system`,
    `/api/v1/users`, `/api/v1/jobs`, `/api/v1/analytics/tuning`,
    `/api/v1/versions`.
  - Viewer GET allowlist (System reads the shell makes on every page):
    `/api/v1/system/scan` (freshness chip, scan strip, live bot section) and
    `/api/v1/system/preferences` (Decision 5).
- Denied ⇒ `403 {"error": {"code": "forbidden", "message": "Read-only account."}}`.

`PUT /api/v1/system/preferences` stays 403 for viewers (method rule), so
Decision 5 is enforced server-side, not only in the SPA.

**Complexity.** The resolver, `check_access` and the hook are separate small
functions; prefixes and the allowlist are data tables. The legacy
`app.require_auth` (already 5+ branches) gains no branch. Plan acceptance: no
new or changed auth function above complexity 12.

**Classification contract test:** walks `app.url_map`; every rule must appear
in a **checked-in expectation table** (`tests/admin/access_expectations.py`:
rule + method → `public` / `viewer` / `admin`), and `check_access` must agree
with the table. A rule missing from the table fails the test, forcing the
author to decide. The table is the source of truth, not the prefix function.

### Users API (admin-only)

| Method | Path | Body | Result |
|---|---|---|---|
| GET | `/api/v1/users` | — | list: id, username, role, disabled, created_at, last_login_at (never hashes) |
| POST | `/api/v1/users` | `{username, password}` | 201 user; 409 `conflict` on duplicate or admin name; 400 `invalid` on bad username / password < 12 chars |
| PATCH | `/api/v1/users/<id>` | `{disabled: bool}` | 200 user; disabling bumps `credential_version` |
| POST | `/api/v1/users/<id>/password` | `{password}` | 204; bumps `credential_version` |
| DELETE | `/api/v1/users/<id>` | — | 204; 404 if absent |

Errors use the existing v1 envelope `error(code, message)`; for `invalid` the
message names the offending field, as other v1 modules do. Each mutation logs
`users: <action> <username> by admin` — never a password or hash.

### SPA

- **Session store** exposes `role` and `isAdmin` signals from `GET /session`.
- **`adminGuard`** (beside `shell/auth.guard.ts`) on every `system/**` route;
  a viewer is redirected to `/dashboard`.
- **Nav:** the System entry is hidden for viewers, in every nav layout
  (desktop rail, tablet, mobile).
- **`*ifAdmin` structural directive** wraps every write control on viewer-
  readable pages. Known controls (the plan's brief completes this list by
  tracing every mutating `api-client.ts` method to its callers):

  | Where | Control | API |
  |---|---|---|
  | trades workspace, trade detail | close / cancel / delete / note edit | `/trades/<id>/close`, `/cancel`, `DELETE /trades/<id>`, `/note` |
  | trades workspace | clear-open / clear-history / close-open | `/trades/clear-open`, `/clear-history`, `/close-open` |
  | watchlist workspace | add / remove ticker | `/watchlist/tickers` |
  | shell `KillswitchChip` (`shell/shell.ts`) and Risk tab | killswitch toggle | `/risk/killswitch` |
  | callers of `live-values`, `system`, `risk` stores | market refresh; scan trigger/stop/pause/resume rendered outside System | `/market/refresh`, `/system/scan/*` |
  | Insights → Analytics | Tuning tab (whole tab hidden, Decision 3) | `/jobs/tune`, `/analytics/tuning/proposals` |

  The inventory lives as a checked-in list (`frontend/src/app/auth/write-calls.ts`:
  api-client method → gating); a spec fails when a mutating `api-client.ts`
  method is not on it.
- **Preferences store:** when `isAdmin()` is false it loads the record but
  never calls `savePreferences`; in-session edits stay in memory. Any other
  persistence path for column pickers or data tables follows the same rule and
  is covered by the same spec.
- **Read-only badge** in the shell header for viewers: "Read-only · <username>".
- **Users page** at `/system/users`, a tab in the System workspace following
  its existing tab pattern: table on desktop/tablet, stacked cards on mobile,
  touch-sized row actions (disable/enable, reset password, delete with a
  confirm step), create-user and reset-password dialogs, and an empty state
  ("No viewer accounts yet"). Designed and checked at mobile, tablet and
  desktop widths per `ui-design.md`.
- **403 interceptor:** a `forbidden` response shows a toast "Read-only
  account"; with controls hidden this is a fallback, not a normal path. It is
  suppressed for `/system/preferences`, so a viewer's layout tweak never toasts.

### Live stream

The SSE endpoint `GET /api/v1/events` (`swingbot/admin/events/stream.py`) is
outside `/system`, so viewers receive it. Today it authenticates once at
connect. It changes to re-run `resolve_principal()` on each loop iteration
(heartbeat cadence) and close the stream when the principal is gone, so a
disabled, deleted or password-reset viewer is cut off within one heartbeat and
gets a 401 on reconnect. The plan also verifies event payloads carry no
settings, secrets or System-only data; any event type that does is filtered
for viewers.

## Testing

Backend (suite `admin`, against the shared `swing-db` after `/replicate-prod-db`):

- url_map classification contract (above).
- Parametrized: every non-GET v1 route as a viewer ⇒ 403 `forbidden`; every
  viewer-readable GET ⇒ not 403; every `/system/*` and `/users` GET as a
  viewer ⇒ 403.
- Readable GETs assert 2xx with fixture data, not merely "not 403"; a 500 or
  404 does not pass.
- Login matrix: `.env` admin, viewer, disabled viewer, unknown user, wrong
  password — identical failure body; all counted by `login_limiter`.
- Viewer credentials over Basic auth ⇒ 401 (Decision 7); a viewer session
  never authenticates as admin.
- Disable, password reset and delete each invalidate an existing viewer
  session on its next request; disable → re-enable leaves the old session
  dead.
- `/api/v1/events` closes for a viewer disabled mid-stream.
- `UndefinedTable` (table not yet migrated) ⇒ viewer login is invalid
  credentials, not 500; admin login unaffected.
- Viewer payloads of `/dashboard`, `/live` and `/events` carry no Users or
  System-only fields.
- Users API: create, duplicate (case-insensitive), admin-name collision, short
  password, bad username, list never contains `password_hash`, patch, reset,
  delete, 404s; viewer calling any of them ⇒ 403.
- `GET /session` returns `role` for both principals.
- Alembic revision upgrades and downgrades cleanly.
- With an empty `admin_users` table, the existing admin test suite passes
  unchanged (the off state is today's behaviour).

Frontend: specs for `adminGuard`, `*ifAdmin` (renders for admin, not for
viewer), nav hiding, Tuning tab and `KillswitchChip` hidden, the write-calls
inventory (every mutating `api-client.ts` method listed), preferences store
no-save for viewers, no toast on a preferences 403, read-only badge,
and the Users page (empty, list, create, validation error, reset, delete
confirm, mobile card layout).

## Rollout

Additive. An empty `admin_users` table is exactly today's behaviour, so there
is no flag. Deploy = image build + `alembic upgrade head` on the VM (per
`docs/deploy/DEPLOY_HETZNER.md`). No `.env` change.

**Rollback**, written into `DEPLOY_HETZNER.md` as a v207 section shaped like
v205's: (1) redeploy the previous image (§ Rolling back). Old code never reads
`admin_users`, so the table can stay and viewer accounts survive a later
roll-forward. (2) Only to remove it, `alembic downgrade <the revision v207_001
revises>`. This **drops `admin_users` and every viewer account**, and also
rolls back any later revision stacked on it, so check `alembic history` first.

## Out of scope

Per-user preferences, more roles (operator, extra admins), viewer self-service
password change, self-signup, Discord command permissions, any change to the
`.env` admin, Basic auth for viewers.

## Panel review

Run 2026-11-05 on d0500efa.

- staff-engineer [BLOCKING]: rollout had no rollback / downgrade step -- applied (§ Rollout)
- staff-engineer: `/system` prefix 403s viewers on GET `/system/preferences`, contradicting Decision 5 -- applied (viewer GET allowlist)
- staff-engineer: shell reads GET `/system/scan` on every page -- applied (viewer GET allowlist)
- staff-engineer: `/api/v1/versions` matched no admin-only prefix -- applied
- staff-engineer: raw prefix `/api/v1/jobs/` misses `/api/v1/jobs` -- applied (segment-boundary matching)
- staff-engineer: a check inside the decorators misses undecorated routes; `app.require_auth` wraps nothing -- applied (`api_v1.before_request` hook, no non-v1 403 variant)
- staff-engineer: SSE `/events` authenticates once, so a disabled viewer keeps streaming; wrong file named -- applied (per-iteration re-check, `events/stream.py`)
- staff-engineer: containers start before `alembic upgrade`; a missing table must not 500 -- applied (§ Data)
- staff-engineer: Basic auth for viewers costs scrypt per request and changes `attempt`'s shape -- applied (Decision 7: viewers use the web session only)
- staff-engineer: name `_session_authenticated` as the single principal resolver -- applied (`resolve_principal`)
- senior-engineer [BLOCKING]: write-control inventory omitted the Analytics Tuning tab -- applied (tab hidden for viewers, Decision 3)
- senior-engineer [BLOCKING]: inventory missed `KillswitchChip` and store callers; needs a per-component list and a test -- applied (inventory table + `write-calls.ts` spec)
- senior-engineer: store belongs in `core/db/repositories/` on `base.py`, table in `schema.py` -- applied
- senior-engineer: complexity budget unaddressed in the auth path -- applied (separate helpers, data tables, <= 12 acceptance)
- senior-engineer: test gaps (viewer over Basic, disable -> re-enable, 2xx not just not-403, payload leakage, checked-in url_map table) -- applied
- senior-engineer: preferences 403 toast and other persistence paths -- applied (toast suppressed, same rule covers other paths)
- senior-engineer: Users API error envelope unspecified -- applied (v1 `error(code, message)`, field named in message)
