# Admin REST API

**Date:** 2026-08-08
**Version:** ui 1.0.9 · bot 1.1.2
**Status:** design agreed, not implemented
**Scope:** design only — endpoint contract, no Angular, no implementation

## Why this exists

The admin UI is being rebuilt as an Angular SPA. That migration is too large for
one spec, so it is split into six sub-projects:

| # | Sub-project | Status |
|---|---|---|
| 1 | **REST API for the whole admin surface** | **this document** |
| 2 | Real-time event push (bot → admin) | not started |
| 3 | Design system | agreed (`2026-08-08-admin-design-system-design.md`) |
| 4 | Angular shell + build/deploy/auth | not started |
| 5 | The workspace implementations | not started |
| 6 | Cutover, delete Jinja | not started |

This document covers **only** sub-project 1: what the SPA is allowed to ask the
server for, and in what shape. It specifies no Angular, no transport for pushed
events (sub-project 2), and no build tooling (sub-project 4).

## The problem being solved

Today the admin server has **58 routes**. Ten of them return JSON. The other
forty-eight return HTML, HTML fragments, redirects, PNGs or CSV. An SPA can use
none of that.

The ten JSON routes were added ad hoc for the pages that needed AJAX (the Plans
board's polling, job progress, journal note edits, trade-history paging). They
are not wrong, but they are not a system: `/api/stats` forwards a snapshot
verbatim, `/api/trade-history` has its own paging convention, `/api/plans` takes
three filter params invented for one board. Nothing agrees on error shape,
nothing agrees on how a collection is paged, and roughly half the admin's
actual capability — settings, watchlist, scan control, killswitch, logs — has
no JSON path at all.

**The constraint carried forward from sub-project 3:** *UI renders, analytics
computes.* No calculation moves into the API layer that does not already live
behind it. Endpoints project and filter; they do not derive.

## Decision 1 — `/api/v1/` as a parallel surface

The new API lives under **`/api/v1/`**. The existing `/api/*` routes stay
exactly where they are and keep working.

This is not future-proofing, which would not be worth the prefix on a
single-client private tool. It is what makes a big-bang cutover survivable:
during sub-projects 4 and 5 the Jinja UI must stay fully working — it is the
only UI there is — and it consumes `/api/plans`, `/api/jobs/*`,
`/api/trade-history` and `/api/ohlcv/*` today. Two namespaces let the new API be
designed properly instead of being bent around what `dashboard.js` currently
expects. Sub-project 6 deletes the old ten.

**Rejected:** evolving `/api/*` in place. It forces every design decision here
to be backward-compatible with a shape that exists only because one board
needed it, and it makes every commit a potential break of the live UI.

**The v1 is not a promise of v2.** There is one client. If the contract needs to
change during sub-project 5, it changes — the version segment is a migration
seam, not a compatibility guarantee.

## Decision 2 — Resource model

Nine resource groups. The grouping follows sub-project 3's six workspaces, not
the current page structure, so that a workspace maps to a small set of
endpoints rather than a scatter.

| Group | Base | Serves workspace |
|---|---|---|
| Session | `/api/v1/session` | shell |
| System health | `/api/v1/health` | shell |
| Cockpit | `/api/v1/cockpit` | Cockpit |
| Trades | `/api/v1/trades` | Trades |
| Analytics | `/api/v1/analytics/*` | Analytics |
| Universe | `/api/v1/universe/*` | Universe |
| Risk | `/api/v1/risk` | Risk |
| System | `/api/v1/system/*` | System |
| Market data | `/api/v1/market/*` | Trades, Universe (charts) |

`/api/v1/events` is reserved for sub-project 2's SSE stream and is not specified
here.

### The big one: trades and plans unify

Today a *plan* (`data/plans.json`, Plan Engine v2) and a *trade*
(`data/trades.json`) are separate stores with separate pages — the Plans board
and the Dashboard's two tables. Sub-project 3 abolished that split in the UI:
one Trades list, with `PENDING` / `ACTIVE` / `PARTIAL` / `CLOSED` / `CANCELLED`
as a **filter**.

The API must therefore present one collection. **`GET /api/v1/trades` returns
the union of both stores, projected onto one row shape, with `status`
distinguishing them.** The stores themselves are not merged — that is a data
migration with real risk and no UI payoff, and it is explicitly out of scope.

This is the one place the API layer does work the current code does not. It is
allowed because a union of two already-serialised row sets is a projection, not
a computation: `_plan_rows()` (`pages.py:111` region) and
`_query_closed_trades()` (`app.py:740` region) already produce the rows; the new
endpoint chooses between and concatenates them. If a field exists on one side
and not the other it is `null` — the API does not invent it.

Consequence: **`id` must be unambiguous across both stores.** Plan IDs and trade
IDs are allocated independently today. The implementation must either confirm
they cannot collide or prefix them (`plan:<id>` / `trade:<id>`). This is the
first thing sub-project 1's implementation should check, before any endpoint is
written — a collision discovered later invalidates every trade route.

## Decision 3 — Conventions

### Collections

```
GET /api/v1/trades?status=ACTIVE&ticker=AAPL&page=1&per_page=25&sort=-opened_at
```

```json
{ "items": [ … ], "total": 137, "page": 1, "per_page": 25 }
```

`total` is the count **after filtering, before slicing** — this is exactly the
contract `_query_closed_trades()` already implements and documents, and it is
generalised rather than reinvented. `per_page` caps at 200. `sort` takes one
field, `-` for descending; the set of sortable fields is per-endpoint and closed.

Filters are `AND`-ed, absent means unfiltered, and an unrecognised filter
parameter is a **400**, not a silent ignore. Silent ignores are how a filter
that quietly stops working survives to production.

### Single resources

Returned bare, with no envelope:

```json
{ "id": "…", "ticker": "AAPL", … }
```

**Rejected:** wrapping everything in `{"data": …}`. It costs a `.data` at every
call site in the SPA and buys nothing when the error shape is already
distinguished by status code.

### Errors

Every non-2xx returns:

```json
{ "error": { "code": "not_found", "message": "No trade with id 'abc'" } }
```

`code` is a stable snake_case string the SPA may branch on; `message` is for
humans and may change. Codes in use: `auth`, `forbidden`, `not_found`,
`invalid`, `conflict`, `busy`, `unavailable`, `internal`.

Status codes: `400` invalid input · `401` unauthenticated · `404` unknown
resource · `409` conflicting state (a job already running — the existing
`/api/jobs/tune` already returns this) · `422` well-formed but rejected by
domain rules · `503` a dependency is down (Docker socket absent for bot
restart).

**`401` always returns this JSON body, never an HTML challenge or a redirect.**
`require_auth_json` already establishes this and every v1 route uses it.

### Commands

Actions that are not CRUD get a verb sub-path under their resource, always
`POST`, always returning the affected resource or `{"ok": true}`:

```
POST /api/v1/trades/{id}/close
POST /api/v1/risk/killswitch
POST /api/v1/system/scan/pause
```

**Rejected:** modelling these as `PATCH` on a status field. "Close this trade at
this price" and "pause the scan loop" are operations with their own inputs and
their own failure modes, and pretending they are field assignments hides that.

### Timestamps and numbers

All timestamps are **ISO-8601 UTC with offset**, as `/scan/status` already
emits. No epoch seconds, no naive local strings. Money and percentages are
JSON numbers, never pre-formatted strings — sub-project 3 owns formatting, and a
server that ships `"+2.4%"` has taken that decision away from it.

## Decision 4 — Route mapping

Every one of the 58 current routes, and where it goes. `→ (drop)` means it has
no v1 successor and dies at cutover.

### Session and shell

| Today | v1 |
|---|---|
| `GET /login` | → (drop) — the SPA renders its own login view |
| `POST /login` | `POST /api/v1/session` |
| `POST /logout` | `DELETE /api/v1/session` |
| — | `GET /api/v1/session` — new: who am I, is the cookie still good |
| `GET /api/health` | `GET /api/v1/health` |

### Cockpit

| Today | v1 |
|---|---|
| `GET /` | `GET /api/v1/cockpit` |
| `GET /dashboard/fragment` | → (drop) — the fragment exists only because Jinja polls HTML |
| `GET /api/stats` | `GET /api/v1/analytics/snapshot` |

`GET /api/v1/cockpit` returns exactly the nine metrics sub-project 3 specifies
(3 primary + 6 chips) plus the 30-day equity series for the sparkline — nothing
more. The six metrics that spec moved to Analytics are **not** in this response;
they are served by `/api/v1/analytics/*`. The existing `dashboard.py` view-model
builders are the source; this endpoint is a thin projection over them.

### Trades

| Today | v1 |
|---|---|
| `GET /api/trade-history` | `GET /api/v1/trades?status=CLOSED` |
| `GET /plans`, `GET /plans/fragment` | `GET /api/v1/trades?status=PENDING` |
| `GET /trades/{id}` | `GET /api/v1/trades/{id}` |
| `GET /plans/{id}` | `GET /api/v1/trades/{id}` (same endpoint — see Decision 2) |
| `POST /trades/{id}/close` | `POST /api/v1/trades/{id}/close` |
| `POST /plans/{id}/close` | `POST /api/v1/trades/{id}/close` |
| `POST /plans/{id}/cancel` | `POST /api/v1/trades/{id}/cancel` |
| `POST /trades/{id}/delete` | `DELETE /api/v1/trades/{id}` |
| `POST /trades/clear-open` | `POST /api/v1/trades/clear-open` |
| `POST /trades/history/clear` | `POST /api/v1/trades/clear-history` |
| `GET /trades/export.csv` | `GET /api/v1/trades/export.csv` — stays CSV |
| `GET /journal` | `GET /api/v1/trades?has_note=1` |
| `GET /api/journal` | → absorbed by the above |
| `POST /api/journal/{id}/note` | `PUT /api/v1/trades/{id}/note` |
| `GET /trades/{id}/chart.png` | → (drop) — see sub-project 6 |
| `GET /plans/{id}/chart.png` | → (drop) — see sub-project 6 |
| `GET /api/plans` | → absorbed by `GET /api/v1/trades` |

The two CSV/PNG exceptions are deliberate: **CSV export stays a browser download,
not JSON.** Rebuilding it client-side would mean shipping every row to the SPA
to serialise it back.

The PNG chart routes are marked `(drop)` here rather than decided — they still
serve Discord embeds through a different path, and sub-project 6 owns the
question of whether the *admin's* copies of them are still needed once every
chart in the UI is `lightweight-charts`.

### Analytics

| Today | v1 |
|---|---|
| `GET /performance` | `GET /api/v1/analytics/performance` |
| `GET /strategies` | `GET /api/v1/analytics/strategies` |
| `GET /calibration` | `GET /api/v1/analytics/calibration` |
| `GET /api/calibration` | → absorbed by the above |
| `GET /api/registry` | `GET /api/v1/analytics/registry` |
| `GET /tuning` | `GET /api/v1/analytics/tuning/proposals` |
| `POST /tuning/propose` | `POST /api/v1/analytics/tuning/proposals` |
| `POST /tuning/proposals/{f}/delete` | `DELETE /api/v1/analytics/tuning/proposals/{f}` |
| `POST /api/jobs/tune` | `POST /api/v1/jobs/tune` |
| `GET /api/jobs` | `GET /api/v1/jobs` |
| `GET /api/jobs/{id}` | `GET /api/v1/jobs/{id}` |

`/api/v1/analytics/performance` also carries the six metrics sub-project 3
relocated here from the Cockpit header (wins, losses, avg realised P&L, best,
worst, avg holding period).

Jobs sit at the top level rather than under `analytics/` because a job is
infrastructure — tuning happens to be the only kind today, but the resource is
about async work, not about analysis.

### Universe

| Today | v1 |
|---|---|
| `GET /watchlist` | `GET /api/v1/universe/tickers` |
| `POST /watchlist/add` | `POST /api/v1/universe/tickers` |
| `POST /watchlist/bulk_add` | `POST /api/v1/universe/tickers` with an array body |
| `POST /watchlist/remove` | `DELETE /api/v1/universe/tickers/{symbol}` |
| `GET /watchlist/suggest` | `GET /api/v1/universe/suggest?q=` |

One endpoint takes both the single add and the bulk add: the body is always a
list. `bulk_add` exists today only because an HTML form cannot post an array.

### Risk

| Today | v1 |
|---|---|
| `GET /risk` | `GET /api/v1/risk` |
| `POST /risk/killswitch` | `POST /api/v1/risk/killswitch` |

### System

| Today | v1 |
|---|---|
| `GET /settings` | `GET /api/v1/system/settings` |
| `POST /settings/preview` | `POST /api/v1/system/settings/preview` |
| `POST /settings/save` | `PUT /api/v1/system/settings` |
| `GET /settings/export` | `GET /api/v1/system/settings/export` — stays a file download |
| `POST /settings/import` | `POST /api/v1/system/settings/import` |
| `GET /logs` | `GET /api/v1/system/logs` |
| `GET /logs/raw` | `GET /api/v1/system/logs/raw` — stays text/plain |
| `POST /logs/clear` | `DELETE /api/v1/system/logs` |
| `POST /bot/restart` | `POST /api/v1/system/bot/restart` |
| `GET /scan/status` | `GET /api/v1/system/scan` |
| `POST /scan/trigger` | `POST /api/v1/system/scan/trigger` |
| `POST /scan/stop` | `POST /api/v1/system/scan/stop` |
| `POST /scan/pause` | `POST /api/v1/system/scan/pause` |
| `POST /scan/resume` | `POST /api/v1/system/scan/resume` |

`GET /api/v1/system/settings` returns the schema **and** the current values in
one response, driven by `swingbot/config.py`'s `Field` entries — the same single
source the current Settings page renders from. The SPA must not hardcode the
field list; a new setting appearing in `config.py` must appear in the UI with no
frontend change. **Sensitive fields stay masked (`•••`) exactly as today**, and
the export endpoint keeps omitting them entirely rather than masking them.

### Market data

| Today | v1 |
|---|---|
| `GET /api/ohlcv/{ticker}` | `GET /api/v1/market/ohlcv/{ticker}` |

Unchanged in substance: `bars` defaults to 260, caps at 1000, falls back to the
local CSV cache on a failed live fetch, and an optional `trade_id` adds that
trade's levels.

### Coverage check

58 routes in · 5 dropped (`GET /login`, `/dashboard/fragment`, two `chart.png`,
plus `/api/plans` absorbed) · the rest mapped. Any route added to `app.py` or
`pages.py` after this date must be added to this table or consciously excluded.

## Decision 5 — Auth

The v1 API uses the **existing session cookie**, unchanged: `session["admin_authed"]`
plus `session["pw_hash"]`, signed with the key persisted at
`data/admin_session_secret` so sessions survive a restart. `POST /api/v1/session`
sets it, `DELETE` clears it.

**HTTP Basic stays supported** on every v1 route, because it is how the API is
scripted against today and dropping it would break that for no gain.

No JWT, no token endpoint, no refresh flow. This is a single-user tool behind a
password on a private network; a token scheme would add three moving parts to
protect against threats that the deployment does not have.

**CSRF:** the SPA and the API are same-origin (Decision 6 of sub-project 4
places the built app under the Flask server), so a `SameSite=Strict` session
cookie is the protection. If sub-project 4 later chooses to serve the SPA from a
different origin, this decision must be revisited — that is the trigger, and it
should be checked there rather than assumed here.

## Decision 6 — The contract is tested, not generated

There is no OpenAPI document. Instead:

1. **`tests/admin/test_api_v1_contract.py`** asserts, per endpoint, the exact
   top-level key set of a successful response and the error shape of each
   failure path. A field that disappears fails a test.
2. The Angular client's TypeScript interfaces are **hand-written**, in one file,
   mirroring that test.

**Rejected:** hand-writing OpenAPI and generating the TS client. It is the
correct answer for an API with consumers you do not control. Here it adds a
codegen step to the build, a schema file that drifts from the code exactly as
easily as the TS interfaces would, and a second place to change every endpoint —
for one client, in one repo, written by the same person.

The honest risk is stated in Risks below.

## Explicitly out of scope

- Real-time push and the `/api/v1/events` endpoint (sub-project 2)
- Any Angular code, including the typed client (sub-project 4)
- Merging `plans.json` and `trades.json` into one store
- Deleting the old routes and templates (sub-project 6)
- Multi-user auth, roles, or per-user persistence beyond what the session
  already holds — note that sub-project 3's column picker "persists per user",
  which with one user means a single server-side blob; that is a System setting,
  not a user system
- Rate limiting, API keys, CORS — same-origin, single user, private network

## Risks

**The trade/plan union is the load-bearing decision and the easiest to get
wrong.** If plan IDs and trade IDs can collide, or if the two row shapes differ
more than expected, every Trades endpoint changes. Check this first; do not
design the row shape from the spec, design it from both stores.

**Hand-written TS interfaces will drift from the Python.** The contract test
catches removed and renamed fields but not a type change from `float` to
`str`. Mitigation: the contract test should assert types, not only key presence.

**Forty-eight routes is a lot of surface to port.** The realistic failure is not
a wrong design, it is an endpoint quietly not built because no workspace needed
it yet, discovered at cutover. The mapping table above is the checklist;
sub-project 6's acceptance list should re-derive it from `grep -rn "\.route("`
rather than trusting this document.

**Two API namespaces coexist for the whole migration.** Anyone editing admin
code during sub-projects 4 and 5 has to know which one they are in. Mitigation:
v1 lives in its own module (`swingbot/admin/api_v1/`), not alongside the old
blueprint.

## Open questions

None blocking. Two to settle during implementation:

1. Whether `GET /api/v1/trades` needs a separate lightweight "list" projection
   from the detail response, or whether one row shape serves both. Depends on
   how heavy the plan rows turn out to be.
2. Whether `/api/v1/analytics/performance` should accept a date range, or keep
   the snapshot's fixed windows. The snapshot is what exists; a range means
   computing on request, which the "UI renders, analytics computes" constraint
   pushes back on.
