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
4. **Write controls are hidden for viewers**, not shown disabled. The server is
   the security boundary; hiding is presentation.
5. **Preferences:** viewers load the admin's shared preferences record
   read-only. Layout changes they make last for the browser session only and
   are never saved. No per-user preferences.
6. **Enforcement is default-deny in the shared auth layer** (approach A), not
   per-route decorators: a route someone adds later is closed to viewers until
   it is classified, and a test fails while it is unclassified.

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

Starts empty; no data migration. A store module under `swingbot/core/db/`
(following the existing store pattern, Postgres-only per `schema-evolution.md`)
exposes `list_users`, `get_by_username`, `get_by_id`, `create_user`,
`set_disabled`, `reset_password`, `delete_user`, `touch_last_login`.

### Auth — principals

- **Login** (`POST /api/v1/session` and Basic auth in both `require_auth`
  decorators) tries the `.env` admin first (existing constant-time
  `credentials_match`), then the table. Unknown username still runs one dummy
  `check_password_hash` so timing does not reveal account existence. Disabled
  users and wrong passwords get the identical "invalid credentials" answer.
  Every attempt still goes through `login_limiter`.
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
- A helper `current_principal()` returns `{role, username, user_id|None}` for
  the request, used by the access check and by audit logging.

### Access check — default-deny

One function, called inside both `require_auth` decorators after
authentication succeeds:

- `role == "admin"` ⇒ allow.
- `role == "viewer"` ⇒ allow only if the request method is `GET`/`HEAD` **and**
  the path is not under an admin-only prefix. Admin-only prefixes:
  `/api/v1/system/`, `/api/v1/users`, `/api/v1/jobs/`,
  `/api/v1/analytics/tuning/proposals`. The only non-GET routes a viewer may
  call are `POST /api/v1/session` and `DELETE /api/v1/session` (log in / out),
  which sit outside `require_auth`.
- Denied ⇒ `403 {"error": {"code": "forbidden", "message": "Read-only account."}}`
  for v1; plain-text 403 for the non-v1 `app.require_auth` path.

Consequence worth naming: `PUT /api/v1/system/preferences` is 403 for viewers
by the prefix rule — Decision 5 is enforced server-side, not only in the SPA.

**Classification contract test:** walks `app.url_map`, and every rule must be
exactly one of *public* (session, static, SPA shell), *viewer-readable* or
*admin-only* according to the same function. A new rule that the test's
explicit expectation table does not list fails the test, forcing the author to
decide.

### Users API (admin-only)

| Method | Path | Body | Result |
|---|---|---|---|
| GET | `/api/v1/users` | — | list: id, username, role, disabled, created_at, last_login_at (never hashes) |
| POST | `/api/v1/users` | `{username, password}` | 201 user; 409 `conflict` on duplicate or admin name; 400 `invalid` on bad username / password < 12 chars |
| PATCH | `/api/v1/users/<id>` | `{disabled: bool}` | 200 user; disabling bumps `credential_version` |
| POST | `/api/v1/users/<id>/password` | `{password}` | 204; bumps `credential_version` |
| DELETE | `/api/v1/users/<id>` | — | 204; 404 if absent |

Each mutation logs `users: <action> <username> by admin` — never a password or
hash.

### SPA

- **Session store** exposes `role` and `isAdmin` signals from `GET /session`.
- **`adminGuard`** (beside `shell/auth.guard.ts`) on every `system/**` route;
  a viewer is redirected to `/dashboard`.
- **Nav:** the System entry is hidden for viewers, in every nav layout
  (desktop rail, tablet, mobile).
- **`*ifAdmin` structural directive** wraps every write control on viewer-
  readable pages: trade close / cancel / delete / note edit, clear-open,
  clear-history, close-open, watchlist add / remove, the risk killswitch,
  market refresh, and any scan control rendered outside System.
- **Preferences store:** when `isAdmin()` is false it loads the record but
  never calls `savePreferences`; in-session edits stay in memory.
- **Read-only badge** in the shell header for viewers: "Read-only · <username>".
- **Users page** at `/system/users`, a tab in the System workspace following
  its existing tab pattern: table on desktop/tablet, stacked cards on mobile,
  touch-sized row actions (disable/enable, reset password, delete with a
  confirm step), create-user and reset-password dialogs, and an empty state
  ("No viewer accounts yet"). Designed and checked at mobile, tablet and
  desktop widths per `ui-design.md`.
- **403 interceptor:** a `forbidden` response shows a toast "Read-only
  account"; with controls hidden this is a fallback, not a normal path.

### Live stream

The SSE/live-events endpoint is a GET outside `/system`, so viewers receive it.
The plan verifies its payloads carry no settings, secrets or System-only data;
if any event type does, that type is filtered for viewers.

## Testing

Backend (suite `admin`, against the shared `swing-db` after `/replicate-prod-db`):

- url_map classification contract (above).
- Parametrized: every non-GET v1 route as a viewer ⇒ 403 `forbidden`; every
  viewer-readable GET ⇒ not 403; every `/system/*` and `/users` GET as a
  viewer ⇒ 403.
- Login matrix: `.env` admin, viewer, disabled viewer, unknown user, wrong
  password — identical failure body; all counted by `login_limiter`.
- Disable, password reset and delete each invalidate an existing viewer
  session on its next request.
- Users API: create, duplicate (case-insensitive), admin-name collision, short
  password, bad username, list never contains `password_hash`, patch, reset,
  delete, 404s; viewer calling any of them ⇒ 403.
- `GET /session` returns `role` for both principals.
- Alembic revision upgrades and downgrades cleanly.
- With an empty `admin_users` table, the existing admin test suite passes
  unchanged (the off state is today's behaviour).

Frontend: specs for `adminGuard`, `*ifAdmin` (renders for admin, not for
viewer), nav hiding, preferences store no-save for viewers, read-only badge,
and the Users page (empty, list, create, validation error, reset, delete
confirm, mobile card layout).

## Rollout

Additive. An empty `admin_users` table is exactly today's behaviour, so there
is no flag. Deploy = image build + `alembic upgrade head` on the VM (per
`docs/deploy/DEPLOY_HETZNER.md`). No `.env` change.

## Out of scope

Per-user preferences, more roles (operator, extra admins), viewer self-service
password change, self-signup, Discord command permissions, any change to the
`.env` admin.
