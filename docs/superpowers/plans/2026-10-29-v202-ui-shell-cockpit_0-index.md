# UI shell cockpit (v202 Phase 1) implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md)

**Goal:**

The admin shell has grown to eleven unlabelled rail glyphs. Their labels
appear only on hover, so a touch tablet never shows them. Related pages are
scattered: Calendar and Cancels are views of the trade book, and Analytics,
Research and Reports answer one question. Live state is spread over four
small top-bar chips. Portfolio heat, the one number a desk trading real
money from these alerts should always see, is a page away on Risk. The
two-tone BomeoCapital wordmark was dropped in v195. This plan is Phase 1 of
the partner's redesign (direction C, "cockpit + live dock"). It fixes the
structure first, so that Phases 2–4 design into the final navigation.

Once this ships, the rail carries **six labelled destinations**: Dashboard,
Watchlist, Trades, Risk and Insights, with System at the foot. Sub-pages
become section tabs drawn by the shell. Trades holds Book, Calendar and
Cancels, Insights holds Analytics, Research and Reports, and System holds
Health and Versions. Every old URL redirects with its query string and
fragment kept. The wordmark leads the top bar again. The top bar keeps only
the killswitch chip, plus an alarm chip that appears only while data is
stale, the stream is down or the bot is down. A right-hand **Live dock**
(320 px on desktop) shows four sections: Bot, Plans awaiting order,
Portfolio heat and Activity. Collapsed, it is a 40 px edge tab. On tablet
and phone a 40 px live strip under the tape opens the same dock as a sheet.
Each page has its own open/collapsed default, and the partner's choice is
remembered server-side per destination. A collapsed dock can never hide an
alarm: the edge tab and the strip take a warning tone.

The dock reads one new DB-only endpoint, `GET /api/v1/live`, plus the
root connection store. It never touches the slow, route-scoped `RiskStore`.
`/live` computes heat with the very same `heat.open_heat` path the Risk page
projects, through one shared `portfolio_state.open_heat_state()` so the two
figures cannot drift. It counts `PENDING` plans and gives an exact expiry
only for `valid_session` plans. It reports the killswitch state and builds an
activity feed from data the bot already persists: alerts, paper fills, TP1
legs, closed trades and the latest killswitch transition. Every P&L line
reads "(paper, pre-cost)". `trades.opened_at` never yields a fill line.

Left alone: page content and layout (each page moves under a new URL
unchanged), colours, type and component styling (Phase 2), the bot, Discord,
the scan pipeline and every stored record shape. No schema change: the dock
preference is a new key in the opaque `ui_preferences` blob. Stop moves, a
killswitch history and TP1 times the bot never wrote stay out (What
follows).

Success: the spec's §8 tests are green. Old paths redirect with query and
fragment, and no in-app link points at an old path. Heat from `/live` equals
the Risk page's for the same book. The layout audit at 390 / 768 / 1440 px
finds no overflow, no tap target under 44 px and no dock overlapping content
(V202-18). The full suite is green once (V202-19).

**Architecture:** Three seams. (1) **Server:** `swingbot/admin/api_v1/live.py`
serves `GET /api/v1/live` behind `require_auth`. Its heat, awaiting and
killswitch sections each catch their own failure. The activity feed comes
from `swingbot/admin/api_v1/live_events.py`: pure row builders, one per kind,
plus a table-driven `collect_events` that loads each source once, drops a
failed source's kinds into `missing`, and then merges, sorts and truncates.
`swingbot/core/edge/portfolio_state.py` gains `open_heat_state()`, which
both `collect_portfolio_state` and `/live` call. (2) **Navigation:**
`shell/nav.ts` becomes six `NavEntry`s with `sections`. It resolves URLs by
a second-segment rule, and `ALIASES` maps every old path. `app.routes.ts`
mounts the unchanged workspace modules under the new paths and redirects
the old ones, and `spa.py`/`smoke_spa.py` allow-list them. (3) **Shell:**
there is a labelled 80 px rail, `sb-section-tabs`, the wordmark top bar and
`sb-alarm-chip`. The root `LiveStore` (`/live`, debounced 2 s on `trades`,
`scan`, `bot` and `risk`) and the root `DockState` (destination, per-page
default, persisted toggle, sheet) feed `sb-live-dock` and its four section
components, `sb-live-edge-tab`, `sb-live-strip` and `sb-live-sheet`. The
warning and alarm rules live as pure functions in `shell/live/live-state.ts`.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy Core on Postgres, pytest;
Angular (standalone, zoneless, signals, `@ngrx/signals` `signalStore`),
vitest via `ng test`; the Node layout audit `frontend/scripts/layout-audit.mjs`
(Playwright).

## Global Constraints

- **`Bump: ui minor, bot patch`.** No task edits `VERSION.json`. `/close-out` resolves the bump and regenerates `swingbot/admin/version_history.json` (`document-conventions.md` § The header block).
- Implement in a worktree under `.claude/worktrees/` (name per `document-lifecycle.md`). Every command uses absolute paths or `git -C <wt>`. Stage explicit paths only, never `git add -A`. Never `cd` in Bash: use `npm --prefix <wt>/frontend …`.
- **Spec wins over the Figma mockups.** Dock wording is the spec's: "Paper fill", "(paper, pre-cost)", "incl. resting orders", "Active: new alerts paused since 09:31", "Clear", "Over cap", "Nothing yet today", "No scan since 09:00 (5h ago)".
- **No new colours, type scale, spacing or component styling** (Phase 2). Use today's tokens only (`--accent`, `--accent-soft`, `--text`, `--warn`/amber tone classes already in `styles`). Heat never turns red in Phase 1. Amber from 80 % of the cap, plus the words "Over cap" above 100 %.
- **No page's content or layout changes.** A workspace component, store or resolver never moves. Only the URL that reaches it changes.
- **`/api/v1/live` is Postgres-only.** It never calls a market-data provider, `collect_portfolio_state`, `get_daily_data*` or any network. A test pins this (V202-1). Heat comes only from `portfolio_state.open_heat_state()`, the function the Risk page's `collect_portfolio_state` also calls.
- `trades.opened_at` never yields a "fill" line. The only fill event is `paper_filled`, from the plan's first `status_history` entry with `status == "ACTIVE"`.
- The killswitch feed shows only the latest transition, worded by `on`/`engaged`. It never claims an engagement at a release time.
- **The dock never instantiates `RiskStore`** and never calls `/risk`. A spec pins it (V202-15).
- **No browser storage.** The dock toggle is stored only through `PreferencesStore`, under key `shell.dock`: a map from destination path to boolean, never keyed by a section or old path. A failed preference read falls back to the per-page default.
- All shell times are **Berlin local** via `timeInZone(iso, 'Europe/Berlin')` (`ui/format.ts:176`) with a relative age (`scanAge`, `shell/freshness-chip.ts`).
- **Stale rule = 900 s**, the `ui/freshness.ts` rule (V202-11 exports it as `STALE_AFTER_SEC`). The alarm chip, edge-tab/strip warning tone and the "No scan since" line all use it.
- Old route names stay in `spa.py` `WORKSPACES` and as SPA redirects **until Phase 4's close-out**, with a comment beside each list saying so (NG57 precedent, `spa.py:31-42`).
- **`insights` joins `spa.WORKSPACES` in the same commit as the route** (`tests/admin/test_spa_serving.py:277` parses `app.routes.ts`).
- **Tests:** `tests/admin/` is at about 1141 of 1200, so **add no test file there**. Edit existing ones only where behaviour changes (`test_spa_serving.py`). All `/live` tests go in the new `tests/live_api/` directory, registered as `[suites.live-api]` in `tests/suites.toml` by V202-1. SPA tests are co-located `*.spec.ts`. Every task ships tests for its empty, failure and edge cases.
- **DB tests:** a task whose tests hit Postgres runs `/replicate-prod-db` first, against the one shared `swing-db` container. No per-task container or database.
- **Per-task verification is the narrow run:** `python <wt>/scripts/dev/testrun.py file <test>`; SPA `npm --prefix <wt>/frontend test -- --watch=false --include <spec path relative to frontend/>`; lint `npm --prefix <wt>/frontend run lint`. The one full-suite run is V202-19.
- **Every UI task checks phone, tablet and desktop** (`ui-design.md`). It builds and serves the SPA locally with the `.env` admin credentials (loaded inside the script, never printed), then runs `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440`. It also states in its report that there is no horizontal scroll, that touch targets are 44 px and that nothing overlaps.
- Every function written or changed stays below cyclomatic complexity 15 (`python scripts/dev/complexity_gate.py`). Row builders and alarm rules are table-driven.
- **`shell.spec.ts` assertions that pin the old rail, cluster or brand are retired explicitly** in the task that changes that element, never silently. The task lists each one as "Retired" or "Moved" with its replacement (the v195 `fdf6b78a` precedent).
- Do not commit on `main`. The plan's tasks commit on the worktree branch, in scoped commits.

## Review Focus

- **Heat on the dock is lower than on Risk.** `/live` and `/risk` both read `open_heat_state()`. `tests/live_api/test_live_heat.py::test_heat_equals_risk_page_for_same_book` seeds one book with resting and filled trades and compares `open_pct` and `cap_pct` (V202-1).
- **A failed source looks like a quiet day.** If `plans` raises, the feed still answers 200. `events_meta.availability == "partial"` and `missing` names `plan_alerted`, `paper_filled` and `tp1_hit`, and the dock prints "Some sources unavailable: …". If all sources fail, the dock shows "Activity unavailable" plus a retry (V202-3, V202-14).
- **The bot stopped at 09:00 and nothing happened since.** The activity section reads "No scan since 09:00 (5h ago)" in warning tone, never "Nothing yet today". The edge tab and strip turn warning-toned, and the alarm chip shows "Data stale …" (V202-11, V202-14, V202-17).
- **A bookmark to `/analytics?tab=tuning#x`** lands on `/insights/analytics?tab=tuning#x`, and the rail lights Insights throughout (V202-4, V202-6).
- **`/trades/calendar`** is never read as trade id `calendar` (V202-4).

## Parallelisation

At most 2 implementers at once (`CLAUDE.md`). Sequential edges and why:

- **Server chain V202-1 → V202-2 → V202-3.** V202-1 creates `tests/live_api/` and its suite entry, which V202-2's tests need. V202-3 adds kinds to `live_events.py` (created by V202-2) and wires `collect_events` into `live.py` (created by V202-1).
- **The server chain runs beside the whole SPA chain.** The two share no file, and the SPA tests fake `/live` from the fixed payload shape below. They meet only at V202-18 (the audit runs against a live local instance), so **V202-3 → V202-18**.
- **V202-4 → V202-5:** the moved links and the no-old-path spec need the new routes to exist.
- **V202-4 → V202-6:** the label invariant looks up each section's route `title` in `app.routes.ts`. V202-5 ∥ V202-6 is allowed (disjoint files: links, calendar/analytics workspaces and `palette-items.ts` routes vs `nav.ts`/`breadcrumb.ts`).
- **V202-5 → V202-7:** both edit `shell/palette/palette-items.ts` (V202-5 the tab routes, V202-7 the grouping).
- **V202-6 → V202-7:** `more-sheet.ts`, `palette-items.ts` and `phone-tab-bar.ts` move onto `NAV_ENTRIES` and the new `navEntryFor` shape.
- **V202-6 → V202-8:** `sb-section-tabs` renders `NavSection`s.
- **V202-7, V202-8 → V202-9:** the rail rewrite deletes `NAV_GROUPS`/`NavGroup` once `shell.ts` is the last consumer (V202-7 removes the others). V202-8 and V202-9 both edit `shell.html`/`shell.ts`.
- **V202-10 runs beside V202-4..9.** It owns only `api/models.ts`, `api/api-client.ts` and `stores/live.store.ts`.
- **V202-6, V202-10 → V202-11:** `DockState` resolves the destination with the new `navEntryFor`. The warning rules read `LiveHeat`/`LiveKillswitch` types.
- **V202-11 → V202-12, V202-13, V202-14.** These three section components have disjoint files and may run in parallel, two at a time.
- **V202-9, V202-12, V202-13, V202-14 → V202-15:** the dock composes the sections, and the shell's desktop grid is the rail task's markup.
- **V202-15 → V202-16 → V202-17:** each edits `shell.html`, `shell.css`, `shell.ts` and `shell.spec.ts`.
- **V202-17, V202-3 → V202-18 → V202-19.**

## Task ledger

| ID | Title | Part | Model | Files | Cross-task contract |
|---|---|---|---|---|---|
| V202-1 | `GET /api/v1/live`: route, heat section, shared `open_heat_state`; `live-api` suite | 1 | opus | Create `swingbot/admin/api_v1/live.py`, `tests/live_api/__init__.py`, `tests/live_api/conftest.py`, `tests/live_api/test_live_endpoint.py`, `tests/live_api/test_live_heat.py`; modify `swingbot/admin/api_v1/__init__.py` (register import tuple), `swingbot/core/edge/portfolio_state.py`, `tests/suites.toml` | `portfolio_state.open_heat_state() -> dict`; `live.DEFAULT_LIMIT = 8`, `live.MAX_LIMIT = 50`, `live.parse_limit(raw: str \| None) -> int \| None`, `live.heat_section(now: datetime) -> dict`, `live.awaiting_section(now) -> dict`, `live.killswitch_section(now) -> dict`; route `GET /api/v1/live`. Payload: see "`/live` payload". `[suites.live-api]` paths `["tests/live_api/"]`. Until V202-3, `events` is `[]` with `events_meta.availability == "unavailable"`, `reason == "not wired"` |
| V202-1b | `/live` awaiting and killswitch sections; Postgres-only pin | 1 | sonnet | Modify `swingbot/admin/api_v1/live.py`, `tests/live_api/test_live_endpoint.py` | `live.awaiting_section(now) -> dict`, `live.killswitch_section(now) -> dict` (split out of V202-1; see part 1) |
| V202-2 | Activity row builders for plans: `plan_alerted`, `paper_filled`, `tp1_hit` | 1 | sonnet | Create `swingbot/admin/api_v1/live_events.py`, `tests/live_api/test_live_events_plans.py` | `live_events.plan_alerted_rows(plans: list[dict]) -> list[dict]`, `paper_filled_rows(plans) -> list[dict]`, `tp1_hit_rows(plans, shares_by_plan: Mapping[str, float]) -> list[dict]`, `live_events.direction_word(direction: str \| None) -> str`, `live_events.event_row(at, kind, text, tone, ref, pnl=None) -> dict`. Row shape: see "Event row" |
| V202-3 | Activity: `trade_closed`, `killswitch` builders; table-driven `collect_events`; wired into `/live` | 1 | sonnet | Modify `swingbot/admin/api_v1/live_events.py`, `swingbot/admin/api_v1/live.py`; create `tests/live_api/test_live_events_trades.py`, `tests/live_api/test_live_events_collect.py` | `trade_closed_rows(trades: list[dict]) -> list[dict]`, `killswitch_rows(state: Mapping) -> list[dict]`, `@dataclass(frozen=True) EventKind(kind: str, source: str, build: Callable[[dict], list[dict]])`, `EVENT_KINDS: tuple[EventKind, ...]`, `SOURCE_LOADERS: dict[str, Callable[[], Any]]` (`"plans"`, `"trades"`, `"killswitch"`, `"shares"`), `collect_events(limit: int, *, loaders: Mapping[str, Callable[[], Any]] \| None = None, now: datetime \| None = None) -> tuple[list[dict], dict]` |
| V202-4 | Routes and redirects; `insights` in `spa.WORKSPACES`; smoke lists | 1 | sonnet | Modify `frontend/src/app/app.routes.ts`, `frontend/src/app/app.routes.spec.ts`, `swingbot/admin/spa.py`, `scripts/dev/smoke_spa.py`, `tests/admin/test_spa_serving.py` | New routes `trades/calendar` (children incl. `:date`), `trades/cancels`, `insights` → `insights/analytics`, `insights/analytics`, `insights/research`, `insights/reports`, `system/versions`; titles `Calendar`, `Cancels`, `Analytics`, `Research`, `Reports`, `Versions` (subtitles unchanged). Old `calendar`, `calendar/:date`, `cancels`, `analytics`, `research`, `reports`, `versions` redirect, keeping query and fragment |
| V202-5 | Move every in-app link to the new paths; no-old-path spec | 2 | sonnet | Modify `workspaces/calendar/calendar.ts`, `workspaces/calendar/day/calendar-day.ts`, `workspaces/analytics/tabs/overview.ts`, `shell/palette/palette-items.ts` (routes only), `ui/hit-area.spec.ts`, `workspaces/calendar/calendar.spec.ts`, `workspaces/calendar/day/calendar-day.spec.ts`, `workspaces/calendar/day/month-context.spec.ts`, `routing/route-title.service.spec.ts`, `shell/palette/palette-items.spec.ts`; create `routing/old-paths.spec.ts` | `OLD_PATH_WORDS = ['calendar','cancels','analytics','research','reports','versions']` (local to the spec) |
| V202-6 | Nav model: six destinations, sections, second-segment rule, aliases, label invariant, breadcrumb | 2 | sonnet | Modify `shell/nav.ts`, `shell/nav.spec.ts`, `shell/breadcrumb.ts`, `shell/breadcrumb.spec.ts` | `NavSection`, `NavEntry.sections`, `NavEntry.foot`, `NAV_ENTRIES`, `SECTION_WORDS`, `SECTION_LABEL_OVERRIDES`, `DESTINATION_LABEL_OVERRIDES`, `ALIASES` (exported), `navEntryFor(url) -> { entry: NavEntry; section: NavSection \| null } \| null`, `destinationFor(url: string) -> string \| null`, `isSectionUrl(url: string) -> boolean`, `breadcrumbFor(url, detail) -> string[]`, `PHONE_TABS: readonly NavEntry[]`. `NAV_GROUPS`/`NavGroup` stay exported, unchanged and marked `@deprecated` (removed by V202-9). See "Nav model" |
| V202-7 | More sheet, palette and phone tab bar on `NAV_ENTRIES` | 2 | sonnet | Modify `shell/more-sheet.ts` (+spec), `shell/palette/palette-items.ts` (+spec), `shell/phone-tab-bar.ts` (+spec), `shell/nav.ts` (`PHONE_TABS` labels only) | `morePageGroups(entries: readonly NavEntry[], tabs: readonly NavEntry[]) -> MoreGroup[]` with `MoreGroup = { id: string; label: string; links: { label: string; path: string }[] }`; `pageItems(entries: readonly NavEntry[])`; `PHONE_TABS` Dashboard label `'Home'` |
| V202-8 | `sb-section-tabs` segmented control, drawn by the shell | 2 | sonnet | Create `shell/section-tabs.ts`, `shell/section-tabs.spec.ts`; modify `shell/shell.html`, `shell/shell.ts`, `shell/shell.css`, `shell/shell.spec.ts` | `SectionTabs` (`sb-section-tabs`), inputs `entry: NavEntry \| null`, `active: NavSection \| null`; `Shell.navHere: Signal<{ entry; section } \| null>` (computed from router URL; consumed by V202-9, V202-11 does its own) |
| V202-9 | Labelled 80 px rail, System at the foot; retire `sb-nav-indicator`, per-link hints and `NAV_GROUPS` | 3 | sonnet | Modify `shell/shell.html`, `shell/shell.css`, `shell/shell.ts`, `shell/shell.spec.ts`, `shell/nav.ts` (delete `NAV_GROUPS`, `NavGroup`), `shell/nav.spec.ts`, `frontend/scripts/layout-audit-lib.mjs` (`railLabelVerdict`), `frontend/scripts/layout-audit-lib.test.mjs`; delete `shell/nav-indicator.ts`, `shell/nav-indicator.spec.ts` | Rail markup: `nav.rail > a.rail-brand` then `ul.nav.rail-work > li > a.rail-link` ×5 then `ul.nav.rail-foot > li > a.rail-link` (System) then the version hint; each `a.rail-link` holds `sb-icon` + `span.rail-label`, active pill = `.rail-link.active .rail-pill`. CSS token `--rail-width: 80px` |
| V202-10 | `/live` client types, `ApiClient.live`, root `LiveStore` (debounced refresh) | 3 | sonnet | Modify `api/models.ts`, `api/api-client.ts`, `api/api-client.spec.ts`; create `stores/live.store.ts`, `stores/live.store.spec.ts` | Types in "SPA types". `ApiClient.live(limit?: number): Observable<LiveSnapshot>`. `LiveStore` (root): `snapshot()`, `loading()`, `failed()`, `heat()`, `awaiting()`, `killswitch()`, `events()`, `eventsMeta()`, `load(): void`, `retry(): void`; `LIVE_REFRESH_DEBOUNCE_MS = 2000`, `LIVE_REFRESH_EVENTS = ['trades','scan','bot','risk'] as const` |
| V202-11 | Live-state rules (warnings, alarm, heat tone, times) and `DockState` | 3 | sonnet | Create `shell/live/live-state.ts`, `shell/live/live-state.spec.ts`, `shell/live/dock-state.ts`, `shell/live/dock-state.spec.ts`; modify `ui/freshness.ts` (export `STALE_AFTER_SEC`) | See "Live-state rules" and "DockState" |
| V202-12 | Dock Bot section (scanner, last scan, freshness, stream, market, killswitch wording) | 3 | sonnet | Create `shell/live/live-bot-section.ts`, `shell/live/live-bot-section.spec.ts` | `LiveBotSection` (`sb-live-bot`), inputs: `botAlive: boolean \| null`, `botHealthy: boolean \| null`, `scanRunning: boolean`, `lastSuccess: string \| null`, `lastSeen: string \| null`, `streamState: ConnectionState`, `marketActive: boolean \| null`, `killswitch: LiveKillswitch \| null`, `now: Date` |
| V202-13 | Dock Plans-awaiting and Portfolio-heat sections | 4 | sonnet | Create `shell/live/live-awaiting-section.ts` (+spec), `shell/live/live-heat-section.ts` (+spec) | `LiveAwaitingSection` (`sb-live-awaiting`), inputs `awaiting: LiveAwaiting \| null`, `loading: boolean`, `now: Date`. `LiveHeatSection` (`sb-live-heat`), inputs `heat: LiveHeat \| null`, `loading: boolean`, `currency: string`, `now: Date`; output `retry: void` |
| V202-14 | Dock Activity section | 4 | sonnet | Create `shell/live/live-activity-section.ts` (+spec) | `LiveActivitySection` (`sb-live-activity`), inputs `events: readonly LiveEvent[]`, `meta: LiveEventsMeta \| null`, `loading: boolean`, `lastSuccess: string \| null`, `now: Date`; output `retry: void`; `activityLine(e: LiveEvent): string` exported |
| V202-15 | `sb-live-dock`, `sb-live-edge-tab`, desktop docking with persisted per-page toggle | 4 | sonnet | Create `shell/live/live-dock.ts` (+spec), `shell/live/live-edge-tab.ts` (+spec); modify `shell/shell.html`, `shell/shell.css`, `shell/shell.ts`, `shell/shell.spec.ts` | `LiveDock` (`sb-live-dock`), input `variant: 'docked' \| 'sheet'`, output `close: void`; `LiveEdgeTab` (`sb-live-edge-tab`), inputs `warnings: readonly LiveWarning[]`, `heatText: string`, `awaitingCount: number \| null`; output `expand: void`. Shell grid: `.workspace-row` = `main.workspace` + `aside.live-column` (320 px open / 40 px collapsed, only when `dock.docked()`) |
| V202-16 | `sb-live-strip` and `sb-live-sheet` for tablet and phone | 4 | sonnet | Create `shell/live/live-strip.ts` (+spec), `shell/live/live-sheet.ts` (+spec); modify `shell/shell.html`, `shell/shell.css`, `shell/shell.ts`, `shell/shell.spec.ts` | `LiveStrip` (`sb-live-strip`), inputs `warnings`, `heatText`, `awaitingCount`, `lastSuccess`, `now`; output `opened: void`. `LiveSheet` (`sb-live-sheet`), inputs `open: boolean`, `side: 'right' \| 'bottom'`; output `closed: void` |
| V202-17 | Top bar: wordmark, alarm chip, killswitch only; chips and clock leave the bar | 5 | sonnet | Create `shell/alarm-chip.ts` (+spec); modify `shell/shell.html`, `shell/shell.css`, `shell/shell.ts`, `shell/shell.spec.ts`, `ui/hit-area.spec.ts` | `AlarmChip` (`sb-alarm-chip`), input `alarm: Alarm \| null`; output `reveal: void`. Final top-bar order (desktop/tablet): `a.brand` (wordmark) · `span.topbar-divider` · `sb-breadcrumb` · flex · `div.status-cluster` (`sb-alarm-chip`, `sb-killswitch-chip`) · `button.search-trigger` · `sb-profile-menu`; phone: `a.brand` (diamond + wordmark) · flex · `div.status-cluster` · `button.search-trigger` · `sb-profile-menu` · `sb-scan-progress` |
| V202-18 | Layout audit at three widths: new routes, dock-overlap check, results | 5 | sonnet | Modify `frontend/scripts/layout-audit-lib.mjs`, `frontend/scripts/layout-audit-lib.test.mjs`, `frontend/scripts/layout-audit.mjs`; create `docs/superpowers/results/2026-10-29-v202-layout-audit.md` | `ROUTES` lists the new paths (old ones dropped); new check `dock`: `aside.live-column` intersects `main.workspace` content box at >= 1024 px, or the live sheet leaves the viewport; `CHECKS` gains `'dock'` |
| V202-19 | Full suite once (the bump is `/close-out`'s) | 5 | haiku | none (verification only) | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | [`2026-10-29-v202-ui-shell-cockpit_1-live-endpoint-and-routes.md`](2026-10-29-v202-ui-shell-cockpit_1-live-endpoint-and-routes.md) | V202-1..V202-3 | `/live` endpoint and activity feed |
| 1b | [`2026-10-29-v202-ui-shell-cockpit_1b-routes.md`](2026-10-29-v202-ui-shell-cockpit_1b-routes.md) | V202-4 | Routes, redirects and server allow-list |
| 2 | [`2026-10-29-v202-ui-shell-cockpit_2-nav-model.md`](2026-10-29-v202-ui-shell-cockpit_2-nav-model.md) | V202-5..V202-8 | Link moves, nav model, More/palette/tab bar, section tabs |
| 3 | [`2026-10-29-v202-ui-shell-cockpit_3-rail-and-live-state.md`](2026-10-29-v202-ui-shell-cockpit_3-rail-and-live-state.md) | V202-9..V202-12 | Labelled rail, `LiveStore`, live-state rules and `DockState`, Bot section |
| 4 | [`2026-10-29-v202-ui-shell-cockpit_4-dock.md`](2026-10-29-v202-ui-shell-cockpit_4-dock.md) | V202-13..V202-16 | Awaiting, heat and activity sections; dock, edge tab, strip, sheet |
| 5 | [`2026-10-29-v202-ui-shell-cockpit_5-topbar-audit-and-close.md`](2026-10-29-v202-ui-shell-cockpit_5-topbar-audit-and-close.md) | V202-17..V202-19 | Top bar and alarm chip, layout audit, full suite |

## Cross-task contracts

### `portfolio_state.open_heat_state()` (V202-1; `swingbot/core/edge/portfolio_state.py`)

```python
def open_heat_state() -> dict:
    """DB-only heat, the single definition both Risk and /live read.

    Returns {"open_trades": list[dict], "balance": float | None,
             "open_heat": float | None, "heat_cap": float,
             "availability": {"state": "ok" | "unavailable", "checked_at": str, "reason": str | None}}
    open_trades = _trades() (TradeLog().get_trades(status="open", limit=None)),
    balance = _balance(), open_heat = heat.open_heat(open_trades, balance) rounded exactly
    as collect_portfolio_state rounds it today, heat_cap = config.PORTFOLIO_HEAT_CAP_PCT.
    """
```

`collect_portfolio_state()` takes `open_trades`, `balance`, `open_heat` and `heat_cap` from it. This is a behaviour-preserving refactor: the existing Risk tests pin it.

### `/live` payload (V202-1, events from V202-3)

```json
{
  "heat": {"availability": "ok", "as_of": "2026-10-29T13:32:00+00:00", "reason": null,
           "open_pct": 4.2, "cap_pct": 6.0, "utilisation_pct": 70.0,
           "open_amount": 2010.0, "cap_amount": 2893.0,
           "headroom_pct": 1.8, "headroom_amount": 883.0,
           "balance": 48210.0, "includes_resting": true},
  "awaiting": {"availability": "ok", "as_of": "...", "reason": null,
               "count": 3, "next_expiry": "2026-10-30T20:00:00+00:00"},
  "killswitch": {"availability": "ok", "as_of": "...", "reason": null,
                 "engaged": true, "since": "2026-10-29T07:31:00+00:00", "detail": "daily loss"},
  "events": [{"at": "...", "kind": "trade_closed", "text": "NVDA closed · TP2", "tone": "positive",
              "ref": "812", "pnl": {"r": 2.1, "amount": 441.0}}],
  "events_meta": {"availability": "partial", "as_of": "...", "missing": ["tp1_hit"]}
}
```

- `availability` is `"ok" | "partial" | "unavailable"`. A failed section keeps its keys with `null` values, `availability: "unavailable"` and a short `reason`. Heat and awaiting are never `partial`.
- `utilisation_pct = round(open_pct / cap_pct * 100, 1)`, **unclamped**. `open_amount = open_pct / 100 * balance`, `cap_amount = cap_pct / 100 * balance`, `headroom_* = cap - open` (negative when over the cap). Money is rounded to 2 dp.
- `awaiting.count` = `plans` rows with `status == "PENDING"`. `next_expiry` is the soonest `session_close(valid_session)` among those PENDING plans that have `valid_session`, or `null`.
- `killswitch.since` is `state()["at"]` only when `on`, otherwise `null`. `detail` is `state()["reason"]`.
- `?limit=`: default 8, clamped to at most 50. A non-integer or a value < 1 gives HTTP 400 through `error()`.

### Event row (V202-2, V202-3; `live_events.event_row`)

`{"at": ISO-8601 UTC str, "kind": str, "text": str, "tone": str, "ref": str | None, "pnl": {"r": float, "amount": float | None} | None}`

- `kind` ∈ `plan_alerted`, `paper_filled`, `tp1_hit`, `trade_closed`, `killswitch`. `tone` ∈ `info`, `positive`, `negative`, `warning`, `neutral`.
- `text` is the line **without** the P&L figure. The SPA's `activityLine` appends `+1.0R ($210) (paper, pre-cost)` whenever `pnl` is set:
  - `plan_alerted`: `Alert · MSFT long · entry 418.50`, ref = plan id, tone `info`
  - `paper_filled`: `Paper fill · XLE short at 92.10`, ref = plan id, tone `info`
  - `tp1_hit`: `TP1 · NVDA`, pnl from the leg, ref = plan id, tone `positive`/`negative`/`neutral` by sign of `r`
  - `trade_closed`: `NVDA closed · TP2`, pnl `{r: closed_r_multiple(t), amount: realized_pnl_amount}`, ref = trade id, tone by sign of `r`
  - `killswitch`: `Killswitch engaged` (tone `warning`) / `Killswitch released` (tone `neutral`), ref `null`
- `collect_events` meta: `{"availability", "as_of", "missing": [kind, ...]}`. A source loader that raises drops every kind built from it into `missing`: `partial` when some kinds survive, `unavailable` when none do.

### Nav model (V202-6; `frontend/src/app/shell/nav.ts`)

```ts
export interface NavSection { path: string; label: string; }           // '/trades', 'Book'; '/trades/calendar', 'Calendar'
export interface NavEntry { path: string; label: string; icon: IconName; sections?: readonly NavSection[]; foot?: boolean; }
export const NAV_ENTRIES: readonly NavEntry[];   // Dashboard, Watchlist, Trades, Risk, Insights, System (foot: true)
export const SECTION_WORDS: ReadonlySet<string>;  // calendar, cancels, analytics, research, reports, versions
export const ALIASES: Readonly<Record<string, string>>;  // '/plans'→'/trades', '/universe'→'/watchlist', '/cockpit'→'/dashboard',
                                                         // '/calendar'→'/trades/calendar', '/cancels'→'/trades/cancels',
                                                         // '/analytics'|'/research'|'/reports'→'/insights/<w>', '/versions'→'/system/versions'
export const SECTION_LABEL_OVERRIDES: Readonly<Record<string, string>>;      // '/trades'→'Book', '/system'→'Health' (route titles stay 'Trades'/'System')
export const DESTINATION_LABEL_OVERRIDES: Readonly<Record<string, string>>;  // '/insights'→'Insights' (first section title is 'Analytics')
export function navEntryFor(url: string): { entry: NavEntry; section: NavSection | null } | null;
export function destinationFor(url: string): string | null;   // entry.path or null
export function isSectionUrl(url: string): boolean;           // second segment ∈ SECTION_WORDS, after ALIASES
export function breadcrumbFor(url: string, detail: string | null): string[];  // ['Trades', 'Calendar'] / ['Risk'] / [..., detail]
export const PHONE_TABS: readonly NavEntry[];                 // dashboard, watchlist, trades, risk (V202-7 labels dashboard 'Home')
export function detailCrumb(...): unchanged;
```

Icons: Dashboard `dashboard`, Watchlist `watchlist`, Trades `trades`, Risk `risk`, Insights `analytics`, System `system` (each distinct, all in `ICON_NAMES`). A URL whose second segment is not a section word (`/trades/812`) resolves to the first section.

### SPA types (V202-10; `frontend/src/app/api/models.ts`)

```ts
export type LiveAvailability = 'ok' | 'partial' | 'unavailable';
interface LiveSectionBase { availability: LiveAvailability; as_of: string; reason: string | null; }
export interface LiveHeat extends LiveSectionBase { open_pct: number | null; cap_pct: number | null; utilisation_pct: number | null;
  open_amount: number | null; cap_amount: number | null; headroom_pct: number | null; headroom_amount: number | null;
  balance: number | null; includes_resting: boolean; }
export interface LiveAwaiting extends LiveSectionBase { count: number | null; next_expiry: string | null; }
export interface LiveKillswitch extends LiveSectionBase { engaged: boolean | null; since: string | null; detail: string | null; }
export type LiveEventKind = 'plan_alerted' | 'paper_filled' | 'tp1_hit' | 'trade_closed' | 'killswitch';
export type LiveTone = 'info' | 'positive' | 'negative' | 'warning' | 'neutral';
export interface LiveEvent { at: string; kind: LiveEventKind; text: string; tone: LiveTone; ref: string | null;
  pnl: { r: number; amount: number | null } | null; }
export interface LiveEventsMeta { availability: LiveAvailability; as_of: string; missing: LiveEventKind[]; }
export interface LiveSnapshot { heat: LiveHeat; awaiting: LiveAwaiting; killswitch: LiveKillswitch;
  events: LiveEvent[]; events_meta: LiveEventsMeta; }
```

### Live-state rules (V202-11; `frontend/src/app/shell/live/live-state.ts`)

```ts
export type LiveWarning = 'heat-near-cap' | 'over-cap' | 'stale' | 'disconnected' | 'bot-down' | 'killswitch';
export interface LiveWarningInput { utilisationPct: number | null; lastSuccess: string | null; now: Date;
  streamState: ConnectionState; botAlive: boolean | null; killswitchOn: boolean | null; }
export function liveWarnings(input: LiveWarningInput): LiveWarning[];      // fixed order as the type lists
export function warningLabel(w: LiveWarning): string;                     // 'Heat near cap', 'Over cap', 'Data stale', 'Disconnected', 'Bot down', 'Killswitch active'
export type AlarmKind = 'bot-down' | 'disconnected' | 'stale';
export interface Alarm { kind: AlarmKind; text: string; }                  // 'Bot down' / 'Disconnected' / 'Data stale 12 min'
export function alarmFor(input: Omit<LiveWarningInput, 'utilisationPct' | 'killswitchOn'>): Alarm | null;  // priority bot-down > disconnected > stale
export function isStale(lastSuccess: string | null, now: Date, staleAfterSec?: number): boolean;  // null → true; default STALE_AFTER_SEC
export type HeatTone = 'unknown' | 'ok' | 'near' | 'over';
export function heatTone(utilisationPct: number | null): HeatTone;         // near >= 80, over > 100
export function heatStripText(heat: LiveHeat | null, currency: string): string;   // 'Heat $2,010 · 4.2% / 6%' | 'Heat $3,100 · 7.8% / 6% · Over cap' | 'Heat —'
export function liveTime(iso: string | null, now: Date): string;           // '14:32 · 6 min ago' (Berlin) | '—'
export const DOCK_PREF_KEY = 'shell.dock';
export const DOCK_DEFAULT_OPEN: ReadonlySet<string>;                       // '/dashboard', '/risk'
export function dockDefaultOpen(destination: string | null): boolean;
export function readDockOpen(prefs: Preferences, destination: string, fallback: boolean): boolean;  // non-boolean → fallback
export function writeDockOpen(prefs: Preferences, destination: string, open: boolean): Preferences; // new object
```

`ui/freshness.ts` exports `STALE_AFTER_SEC = 900` and uses it as the `staleAfterSec` input default. "Disconnected" means `streamState` is `'dead'` or `'degraded'`, "Bot down" means `botAlive === false`, and "stale" means `isStale(lastSuccess, now)` and is evaluated only once `/health` has answered (`botAlive !== null`).

### DockState (V202-11; `frontend/src/app/shell/live/dock-state.ts`)

```ts
@Injectable({ providedIn: 'root' })
export class DockState {
  readonly destination: Signal<string | null>;   // destinationFor(router url), updated on NavigationEnd
  readonly docked: Signal<boolean>;              // viewport is md or wider (>= 1024 px)
  readonly open: Signal<boolean>;                // readDockOpen(prefs, destination, dockDefaultOpen(destination)); a pre-load or failed read gives the default
  readonly sheetOpen: Signal<boolean>;
  toggle(): void;      // flips open for the current destination; preferences.update(p => writeDockOpen(p, dest, !open))
  reveal(): void;      // docked ? (open || toggle()) : openSheet()
  openSheet(): void;
  closeSheet(): void;  // also on NavigationEnd and when the viewport becomes docked
}
```
