# Angular shell, build, deploy and auth

**Date:** 2026-08-08
**Version:** ui 1.0.9 · bot 1.1.2
**Status:** design agreed, not implemented
**Scope:** design only — the frame the workspaces plug into. No workspace code.

## Why this exists

The admin UI is being rebuilt as an Angular SPA. That migration is too large for
one spec, so it is split into six sub-projects:

| # | Sub-project | Status |
|---|---|---|
| 1 | REST API for the whole admin surface | agreed (`2026-08-08-v11-admin-rest-api-design.md`) |
| 2 | Real-time event push (bot → admin) | agreed (`2026-08-08-v12-realtime-push-design.md`) |
| 3 | Design system | agreed (`2026-08-08-v20-admin-design-system-design.md`) |
| 4 | **Angular shell + build/deploy/auth** | **this document** |
| 5 | The workspace implementations | not started |
| 6 | Cutover, delete Jinja | not started |

This document covers **only** sub-project 4: the application frame — versions,
project layout, state architecture, HTTP and event plumbing, routing, auth, and
how a Node-built bundle reaches a Python container. It builds **no workspace**.
Its deliverable is an app that boots, authenticates, shows an empty shell with
working navigation, and proves the data path end to end with one trivial view.

## The problem being solved

There is no frontend project. No `package.json`, no `angular.json`, no
TypeScript anywhere in the repo. Meanwhile the repo has hard-won properties that
a default `ng new` would casually break:

- **Zero runtime CDN calls.** Inter and `lightweight-charts` are vendored under
  `static/vendor/` and self-hosted so the admin works fully offline. A default
  Angular app happily pulls Google Fonts.
- **One Docker image, python:3.11-slim, two services.** Adding Node to the
  runtime image would roughly triple it and put a JavaScript toolchain on the
  production host for no reason.
- **A layer-cached Dockerfile** that was deliberately tuned (`uv`, cache mounts,
  requirements copied before source). A careless `COPY . .` for the frontend
  would invalidate it on every source edit.

## Decision 1 — Angular 21, not 22

**Pin `@angular/core@~21.2` and `@ngrx/signals@~21.1`.**

Angular 22.1.1 is the current release, so this is deliberately one major behind.
The reason is checked, not assumed: `@ngrx/signals@21.1.1` declares
`peerDependencies: {"@angular/core": "^21.0.0"}`, and `@ngrx/signals@22` has
shipped only `22.0.0-rc.0`. Angular 22 plus NgRx 21 means installing against a
violated peer range; Angular 22 plus NgRx 22-rc means a release candidate in the
foundation of a UI that has not been written yet.

Angular 21.2.19 is stable and current within its major. **Upgrade to 22 once
`@ngrx/signals@22` is stable** — that is a mechanical bump, and it should happen
after sub-project 5, never during it.

This is the first thing to re-verify at implementation time; if NgRx 22 has
released by then, take 22 for both and delete this decision.

## Decision 2 — Standalone, signals, native control flow

No `NgModule` anywhere. Every component `standalone: true`, `ChangeDetectionStrategy.OnPush`
without exception, `@if`/`@for`/`@switch` rather than the structural directives,
`input()`/`output()`/`model()` rather than the decorators, and `inject()` rather
than constructor parameters.

This is not fashion. It is that the whole application is being written at once
by one author: there is no legacy to accommodate, and picking one idiom per
concern means a reviewer never has to ask which of two equivalent forms a file
uses. Any file mixing idioms is a review defect.

**Zoneless** (`provideZonelessChangeDetection()`). With signals throughout and
`OnPush` everywhere, Zone.js is a 40 KB patch of every browser async primitive
buying nothing. The constraint it imposes — state changes must go through
signals — is one this design wants enforced anyway.

## Decision 3 — NgRx SignalStore, with the boundary drawn

**State lives in `@ngrx/signals` SignalStores.** One per workspace, plus two
application-wide.

An honest note, because the alternative was close: **a single-user tool with
server-owned state does not obviously need a state library.** Nearly all of this
application's data is a projection of what the server has; plain services
holding `signal()`s would work. The structure the store buys, and the reason to
take it, is uniformity — `withState` / `withComputed` / `withMethods` gives
every workspace the same three-part shape, so the Trades store and the Analytics
store are navigable by the same reading habit. On an application with six
workspaces written over a long stretch, that consistency is worth more than the
indirection costs.

What it must **not** become is a place where server data is cached, merged and
gradually diverges from the server's version. That is the failure mode of a
store in front of a REST API, and sub-project 2's thin-event design is what
prevents it: an event means refetch, not patch.

### The stores

| Store | Scope | Holds |
|---|---|---|
| `SessionStore` | root | auth state, current user, login/logout |
| `ConnectionStore` | root | SSE state (`live` / `degraded` / `dead`), last event `seq`, bot liveness |
| `CockpitStore` | route | the nine metrics + equity series |
| `TradesStore` | route | list query (filters, sort, page), rows, selected trade detail |
| `AnalyticsStore` | route | performance, strategies, calibration, tuning proposals |
| `UniverseStore` | route | ticker list, per-ticker detail |
| `RiskStore` | route | exposure, killswitch state |
| `SystemStore` | route | settings schema+values, logs, scan state, jobs |

Root stores are `providedIn: 'root'`. Workspace stores are **provided on the
route**, so they are created on entry and destroyed on exit — a workspace should
not hold stale state while you are looking at another one. `TradesStore` is the
exception worth watching: returning to a list should restore filters, which
argues for hoisting *just the query* to a root-level preference store rather
than keeping the whole store alive.

### Column-picker and filter persistence

Sub-project 3 requires the column picker to persist "per user". With one user
that is a server-side blob, exposed by sub-project 1 as a System setting — not
`localStorage`. Reason: the same person on the same tool from a laptop and a
desktop should see the same columns, and `localStorage` silently fails that. A
`PreferencesStore` at root owns it, reads once at boot, and writes debounced.

## Decision 4 — HTTP and events

**One generated-by-hand typed client**, `ApiClient`, in `src/app/api/`. Its
interfaces mirror sub-project 1's contract test file-for-file, per that spec's
Decision 6. Components never call `HttpClient` directly; stores call `ApiClient`.

Three functional interceptors, in order:

1. **`authInterceptor`** — sets `withCredentials: true` so the session cookie
   rides along, and on `401` routes to the login view and clears `SessionStore`.
   It must not retry: a 401 here means the session is gone, and a retry loop
   against a login-gated API is a self-inflicted outage.
2. **`errorInterceptor`** — maps sub-project 1's `{error: {code, message}}` body
   onto a typed `ApiError`, so every store handles one shape. Non-JSON failures
   (network down, proxy 502) become `ApiError` with code `unavailable`.
3. **`loadingInterceptor`** — counts in-flight requests per workspace for the
   shell's activity indicator.

**Events land in one place.** An `EventStream` service owns the single
`EventSource` to `/api/v1/events`, exposes the parsed event as a signal, and
implements the reconnect/fallback policy from sub-project 2 (three reconnects in
a minute → degrade to 5-second polling, surface it on `ConnectionStore`).

Stores subscribe by declaring which event types concern them; the service does
not know what a store is. A store's reaction is always **refetch**, never patch —
this is the rule that keeps client state from drifting from the server, and it
is the single most important convention in this document.

## Decision 5 — Routing

Six lazy routes, one per workspace, matching sub-project 3's IA exactly:

```
/cockpit          /trades   /trades/:id     /analytics
/universe         /universe/:symbol         /risk        /system
```

`/` redirects to `/cockpit`. Every workspace route is `loadComponent`, so a
workspace's code and its store arrive together and only when visited.

A single `authGuard` (a `CanMatchFn` reading `SessionStore`) protects all six.
Login is not a route inside the shell — it is rendered *instead of* the shell,
so an unauthenticated user never downloads or mounts workspace code.

`withComponentInputBinding()` so `:id` and `:symbol` arrive as `input()`s, and
**query parameters are the source of truth for the Trades list state** — filters,
sort, page. Not store-only. A filtered view has to survive a reload and be
pasteable, and routing it through the URL is what makes the store's query slice
a projection of something durable rather than a fourth copy of the truth.

## Decision 6 — Build and deploy

**The SPA is served by Flask, same-origin, from `swingbot/admin/static/app/`.**

Same-origin matters beyond convenience: it is what lets sub-project 1 keep
cookie auth with `SameSite=Strict` and no CORS, and what lets `EventSource` —
which cannot send headers — authenticate at all. **A cross-origin deployment
would invalidate decisions in three of these specs**, so it is ruled out here
rather than left open.

### Layout

```
frontend/                     the Angular project — NOT inside swingbot/
  package.json  angular.json  tsconfig.json
  src/app/{shell,api,stores,workspaces,ui}/
swingbot/admin/static/app/    build output — gitignored, produced by CI/Docker
```

`frontend/` sits at the repo root, outside the Python package, so `pip install`,
`py_compile` and pytest collection never see TypeScript. The build output is
**gitignored**: a committed bundle is a merge-conflict generator and a lie about
what the source produces.

### Docker

A **multi-stage build**, so Node never reaches the runtime image:

```dockerfile
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./       # deps layer, cached across source edits
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim                # unchanged from here down
…
COPY --from=frontend /build/dist/browser /app/swingbot/admin/static/app
```

`package*.json` is copied before the source for exactly the reason
`requirements.txt` already is — the existing Dockerfile documents that
reasoning at length, and this mirrors it. The final image gains only static
files.

**The bot service shares this image and does not need the frontend.** It costs a
few hundred KB of static assets in a shared layer; splitting into two images to
avoid that would cost the shared build cache, which the Dockerfile's comments
show was deliberately engineered. Not worth it.

### Serving

Flask serves `index.html` for any unmatched non-`/api` path so client-side
routing survives a refresh — with an explicit **allow-list of the six workspace
prefixes** rather than a blanket catch-all. A catch-all that swallows typos into
`index.html` turns "this endpoint does not exist" into a blank page, which is a
miserable thing to debug.

Hashed filenames get a long `Cache-Control`; `index.html` gets `no-cache`.

### Dev workflow

`ng serve` on 4200 with `proxy.conf.json` forwarding `/api` to `localhost:1234`,
so the SPA runs against the real Flask process with real data. **`ng serve` must
never be the production path**, and the Angular dev server is never added to
`docker-compose.yml`.

### Zero CDN, still

`@font-face` for **Inter and JetBrains Mono** points at
`swingbot/admin/static/vendor/`, reusing the existing vendored Inter rather than
adding a duplicate copy under `frontend/`. Sub-project 3 requires JetBrains Mono
to be vendored the same way — that is a task in this sub-project, since it is
the one that owns asset plumbing.

`lightweight-charts` is the one library that arrives through npm rather than the
`static/vendor/` copy, because the Angular wrapper needs its types. **Note the
version gap: the repo vendors 4.2.3, npm's current is 5.2.0, and v5 has breaking
API changes.** Take 5.x in the frontend and let the Jinja UI keep its vendored
4.2.3 until cutover — they are separate consumers and need not agree. Sub-project
5 owns the wrapper and inherits this.

## Decision 7 — Auth

Unchanged from the server's side; sub-project 1 fixed the contract:

- `POST /api/v1/session` on login; the response sets the existing signed session
  cookie. `SessionStore` records authenticated state.
- `GET /api/v1/session` at boot answers "is my cookie still good", before the
  shell renders. This is what stops the app flashing a dashboard and then
  bouncing to login.
- `DELETE /api/v1/session` on logout, then a full reload — cheapest reliable way
  to guarantee no store retains data across an identity change.
- HTTP Basic still works for scripted access and the SPA does nothing about it.

**No token in `localStorage`, no JWT, no refresh.** The cookie is `HttpOnly`,
which a token in JS storage is not.

**Password changes invalidate sessions** via the existing `pw_hash` check —
the SPA must treat the resulting `401` as a normal logout, not an error state.

## Definition of done

Sub-project 4 is complete when:

1. `npm run build` produces a bundle Flask serves at `/`, and `docker compose
   up --build` yields a working image with no Node in it.
2. Logging in, reloading, and logging out work against the real Flask session.
3. The shell renders sub-project 3's frame — sidebar with six entries, workspace
   header, connection status, toast host — using the agreed tokens, with
   JetBrains Mono and Inter both loading from `static/vendor/`.
4. All six routes resolve to placeholder components, lazily.
5. `/api/v1/events` is connected: killing the endpoint flips `ConnectionStore`
   to degraded and the indicator changes.
6. **One real view exists end to end** — the Cockpit's three primary metric
   cards, fed by `/api/v1/cockpit` through `ApiClient` and `CockpitStore`,
   refetching on an `account` event. This is the tracer bullet; everything else
   in sub-project 5 repeats its shape.
7. The Jinja UI still works, untouched.

## Explicitly out of scope

- Any of the six workspaces beyond the tracer-bullet metric cards (sub-project 5)
- The data table component — sub-project 5 owns it and it is that plan's first task
- Endpoint implementations (sub-project 1) and the event stream server
  (sub-project 2); this consumes both and can be built against stubs
- Deleting anything (sub-project 6)
- Replacing the Werkzeug dev server, SSR, service workers, i18n, e2e tooling
- Mobile layouts — sub-project 3 rules out below ~1100px

## Risks

**The NgRx/Angular version pin is a moving target.** It is correct on 2026-08-08
and verified against npm; it may be stale by the time anyone implements this.
Re-check `npm view @ngrx/signals peerDependencies` before `ng new` and follow
what it says over what this document says.

**A frontend build in the Dockerfile lengthens every image build**, including
the bot's, since they share the image. `npm ci` on a cold cache is not fast.
Mitigated by the deps-before-source layer split, but the first build after a
dependency bump will be noticeably slower and that is worth knowing before
blaming it on something else.

**`lightweight-charts` 4.2.3 and 5.2.0 coexisting** during the migration means
two chart APIs in the repo at once. Bounded — the Jinja copy is deleted at
cutover — but a v5 example pasted into the old UI will not work, and the
confusion will happen at least once.

**SignalStore may prove to be ceremony.** If, three workspaces in, every store
is `withState` plus a fetch method and nothing more, that is evidence the
library is not earning its place. Say so then rather than adding structure to
justify it retroactively.

**"Refetch, never patch" will be tempting to violate** the first time a refetch
feels wasteful — a single trade's price ticking, say. Violating it is how the
client's state starts diverging from the server's. If it must be violated, it
should be a documented exception in one place, not a habit.

## Open questions

None blocking. Two to settle during implementation:

1. Whether `TradesStore` hoists its query slice to a root preference store, or
   relies on the URL alone to restore filters. The URL may be enough; decide
   once the Trades workspace exists.
2. Whether the shell needs a global command palette. Sub-project 3's component
   inventory does not include one, so the default is no — revisit only if
   navigating six workspaces proves slow in practice.
