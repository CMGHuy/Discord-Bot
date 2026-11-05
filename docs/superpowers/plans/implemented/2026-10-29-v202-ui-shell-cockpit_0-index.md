# UI shell cockpit (v202 Phase 1, plan A: `/live` and navigation) implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md)

The bump stays `ui minor, bot patch`: the partner sees new URLs, section tabs and a regrouped More sheet, palette and tab bar, and the bot gains a read-only admin endpoint.

**Goal:**

The admin shell has grown to eleven unlabelled rail glyphs. Their labels
appear only on hover, so a touch tablet never shows them. Related pages are
scattered: Calendar and Cancels are views of the trade book, and Analytics,
Research and Reports answer one question. Live state is spread over four
small top-bar chips. Portfolio heat, the one number a desk trading real
money from these alerts should always see, is a page away on Risk. This is
Phase 1 of the partner's redesign (direction C, "cockpit + live dock"). It
fixes the structure first, so that Phases 2–4 design into the final
navigation. The spec is built by two plans, because one would pass the
20-task cap: **this plan (v202) lays the data and the navigation**, and
**v203 builds the shell on top of it** (rail, Live dock, top bar, audit).

Once this plan ships, the information architecture is the final one. There
are six destinations: Dashboard, Watchlist, Trades, Risk and Insights, with
System at the foot. Trades holds Book, Calendar and Cancels, Insights holds
Analytics, Research and Reports, and System holds Health and Versions. Every
old URL redirects with its query string and fragment kept, and no in-app
link points at an old path. The shell draws section tabs above each
sectioned page. The More sheet, the command palette and the phone tab bar
all read the one `NAV_ENTRIES` model, and the breadcrumb reads
`Destination / Section`. The server answers `GET /api/v1/live`, which the
v203 dock will read: portfolio heat, plans awaiting an order, the killswitch
state and an activity feed. The rail itself still shows the old glyphs until
v203 replaces it.

`/live` is DB-only. It never touches the slow, route-scoped `RiskStore` or
any market-data provider. It computes heat with the very same
`heat.open_heat` path the Risk page projects, through one shared
`portfolio_state.open_heat_state()`, so the two figures cannot drift. It
counts `PENDING` plans and gives an exact expiry only for `valid_session`
plans. It reports the killswitch state and builds an activity feed from data
the bot already persists: alerts, paper fills, TP1 legs, closed trades and
the latest killswitch transition. `trades.opened_at` never yields a fill
line. Navigation resolves URLs by a per-destination second-segment rule, so
`/trades/calendar` is a section and `/trades/812` a trade.

Left alone: page content and layout (each page moves under a new URL
unchanged), colours, type and component styling (Phase 2), the bot,
Discord, the scan pipeline and every stored record shape. No schema change.
The rail, the dock, the top bar and the layout audit's new checks are v203's.

Success: the spec's §8 "`/live`", "Nav model" and "Routes" tests are green.
Old paths redirect with query and fragment, and no in-app link points at an
old path. Heat from `/live` equals the Risk page's for the same book. A
failed source answers 200 with `events_meta.availability == "partial"`. The
full suite is green once (V202-9).

**Architecture:** Two seams. (1) **Server:** `swingbot/admin/api_v1/live.py`
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
the old ones, and `spa.py`/`smoke_spa.py` allow-list them. The shell derives
`navHere` from the router URL and draws `sb-section-tabs`.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy Core on Postgres, pytest;
Angular (standalone, zoneless, signals, `@ngrx/signals` `signalStore`),
vitest via `ng test`; the Node layout audit `frontend/scripts/layout-audit.mjs`
(Playwright).

**What follows:** [v203, UI shell cockpit: rail, Live dock and top bar](2026-10-29-v203-ui-shell-cockpit-dock_0-index.md) builds the rest of the same spec (labelled rail, `LiveStore`, `DockState`, the dock and its sections, strip and sheet, top bar and alarm chip, three-width layout audit). It starts once this plan is merged. The spec's own What follows (Phase 2, the stop-move event log, market session state, a concentration row, Phase 4's removal of the old route names) is unchanged.

## Global Constraints

- **`Bump: ui minor, bot patch`.** No task edits `VERSION.json`. `/close-out` resolves the bump and regenerates `swingbot/admin/version_history.json` (`document-conventions.md` § The header block).
- Implement in a worktree under `.claude/worktrees/` (name per `document-lifecycle.md`). Every command uses absolute paths or `git -C <wt>`. Stage explicit paths only, never `git add -A`. Never `cd` in Bash: use `npm --prefix <wt>/frontend …`.
- **Spec wins over the Figma mockups.** Activity wording is the spec's: "Alert", "Paper fill", "TP1", "closed", "Killswitch engaged", "Killswitch released"; the SPA appends "(paper, pre-cost)" to every P&L line.
- **No new colours, type scale, spacing or component styling** (Phase 2). Use today's tokens only (`--accent`, `--accent-soft`, `--text`, `--warn`/amber tone classes already in `styles`). `sb-section-tabs` reuses `sb-segmented`'s tokens.
- **No page's content or layout changes.** A workspace component, store or resolver never moves. Only the URL that reaches it changes.
- **`/api/v1/live` is Postgres-only.** It never calls a market-data provider, `collect_portfolio_state`, `get_daily_data*` or any network. A test pins this (V202-1b). Heat comes only from `portfolio_state.open_heat_state()`, the function the Risk page's `collect_portfolio_state` also calls.
- `trades.opened_at` never yields a "fill" line. The only fill event is `paper_filled`, from the plan's first `status_history` entry with `status == "ACTIVE"`.
- The killswitch feed shows only the latest transition, worded by `on`/`engaged`. It never claims an engagement at a release time.
- Old route names stay in `spa.py` `WORKSPACES` and as SPA redirects **until Phase 4's close-out**, with a comment beside each list saying so (NG57 precedent, `spa.py:31-42`).
- **`insights` joins `spa.WORKSPACES` in the same commit as the route** (`tests/admin/test_spa_serving.py:277` parses `app.routes.ts`).
- **`NAV_GROUPS`/`NavGroup` stay exported and `@deprecated` at the end of this plan.** The old rail in `shell.ts` is their last reader; v203's V203-1 deletes them. Any lint suppression left for them names only `shell/shell.ts`.
- **Tests:** `tests/admin/` is at about 1141 of 1200, so **add no test file there**. Edit existing ones only where behaviour changes (`test_spa_serving.py`). All `/live` tests go in the new `tests/live_api/` directory, registered as `[suites.live-api]` in `tests/suites.toml` by V202-1. SPA tests are co-located `*.spec.ts`. Every task ships tests for its empty, failure and edge cases.
- **DB tests:** a task whose tests hit Postgres runs `/replicate-prod-db` first, against the one shared `swing-db` container. No per-task container or database.
- **Per-task verification is the narrow run:** `python <wt>/scripts/dev/testrun.py file <test>`; SPA `npm --prefix <wt>/frontend test -- --watch=false --include <spec path relative to frontend/>`; lint `npm --prefix <wt>/frontend run lint`. The one full-suite run is V202-9.
- **Every UI task checks phone, tablet and desktop** (`ui-design.md`). A task that changes markup (V202-8) builds and serves the SPA locally with the `.env` admin credentials (loaded inside the script, never printed), then runs `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440`, and states in its report that there is no horizontal scroll, that touch targets are 44 px and that nothing overlaps. A task that only moves a link target reports "no layout change"; v203's V203-10 audits the new paths.
- Every function written or changed stays below cyclomatic complexity 15 (`python scripts/dev/complexity_gate.py`). Row builders are table-driven.
- **`shell.spec.ts` assertions that pin the old shape are retired explicitly** in the task that changes it, never silently. The task lists each one as "Retired" or "Moved" with its replacement (the v195 `fdf6b78a` precedent).
- Do not commit on `main`. The plan's tasks commit on the worktree branch, in scoped commits.

## Review Focus

- **Heat on the dock is lower than on Risk.** `/live` and `/risk` both read `open_heat_state()`. `tests/live_api/test_live_heat.py::test_heat_equals_risk_page_for_same_book` seeds one book with resting and filled trades and compares `open_pct` and `cap_pct` (V202-1).
- **A failed source looks like a quiet day.** If `plans` raises, the feed still answers 200. `events_meta.availability == "partial"` and `missing` names `plan_alerted`, `paper_filled` and `tp1_hit` (V202-3). The dock's wording of it is v203's V203-6.
- **A bookmark to `/analytics?tab=tuning#x`** lands on `/insights/analytics?tab=tuning#x`, and navigation resolves it to Insights throughout (V202-4, V202-6b).
- **`/trades/calendar`** is never read as trade id `calendar`, and `/trades/analytics` is a trade id, not a section (V202-4, V202-6b).

## Parallelisation

At most 2 implementers at once (`CLAUDE.md`). Sequential edges and why:

- **Server chain V202-1 → V202-1b → V202-2 → V202-3.** V202-1 creates `live.py`, `tests/live_api/` and its suite entry. V202-1b adds the awaiting and killswitch sections to the same `live.py` and `test_live_endpoint.py`. V202-2's tests need the suite. V202-3 adds kinds to `live_events.py` (created by V202-2) and wires `collect_events` into `live.py`.
- **The server chain runs beside the whole SPA chain.** The two share no file. They meet only at the full suite, so **V202-3 → V202-9**.
- **V202-4 → V202-5:** the moved links and the no-old-path spec need the new routes to exist.
- **V202-4 → V202-6:** the label invariant looks up each section's route `title` in `app.routes.ts`, and the alias test reads each old path's `redirectTo`. V202-5 ∥ V202-6 is allowed (disjoint files: links, calendar/analytics workspaces and `palette-items.ts` routes vs `nav.ts`/`nav.spec.ts`).
- **V202-6 → V202-6b:** both edit `nav.ts` and `nav.spec.ts`; V202-6b's resolution functions read V202-6's `NAV_ENTRIES` and `ALIASES`.
- **V202-5 → V202-7:** both edit `shell/palette/palette-items.ts` (V202-5 the tab routes, V202-7 the grouping) and its spec.
- **V202-6b → V202-7:** `more-sheet.ts`, `palette-items.ts` and `phone-tab-bar.ts` move onto `NAV_ENTRIES` and the final `navEntryFor`/`PHONE_TABS`; both tasks edit `phone-tab-bar.spec.ts` and `shell.spec.ts`.
- **V202-6b → V202-8:** `sb-section-tabs` renders `NavSection`s, and `Shell.navHere` is computed with the final `navEntryFor`.
- **V202-7 → V202-8:** both edit `shell/shell.spec.ts` (V202-7 lines 733 and 801, V202-8 a new describe).
- **V202-3, V202-8 → V202-9.**

## Task ledger

| ID | Title | Part | Model | Files | Cross-task contract |
|---|---|---|---|---|---|
| V202-1 | `GET /api/v1/live`: route, heat section, shared `open_heat_state`; `live-api` suite | 1 | opus | Create `swingbot/admin/api_v1/live.py`, `tests/live_api/__init__.py`, `tests/live_api/conftest.py`, `tests/live_api/test_live_endpoint.py`, `tests/live_api/test_live_heat.py`; modify `swingbot/admin/api_v1/__init__.py` (register import tuple), `swingbot/core/edge/portfolio_state.py`, `tests/suites.toml` | `portfolio_state.open_heat_state() -> dict`; `live.DEFAULT_LIMIT = 8`, `live.MAX_LIMIT = 50`, `live.parse_limit(raw: str \| None) -> int \| None`, `live.heat_section(now: datetime) -> dict`; route `GET /api/v1/live`. Payload: see "`/live` payload". `[suites.live-api]` paths `["tests/live_api/"]`. Until V202-3, `events` is `[]` with `events_meta.availability == "unavailable"`, `reason == "not wired"` |
| V202-1b | `/live` awaiting and killswitch sections; Postgres-only pin | 1 | sonnet | Modify `swingbot/admin/api_v1/live.py`, `tests/live_api/test_live_endpoint.py` | `live.awaiting_section(now) -> dict`, `live.killswitch_section(now) -> dict` (split out of V202-1; see part 1) |
| V202-2 | Activity row builders for plans: `plan_alerted`, `paper_filled`, `tp1_hit` | 1 | sonnet | Create `swingbot/admin/api_v1/live_events.py`, `tests/live_api/test_live_events_plans.py` | `live_events.plan_alerted_rows(plans: list[dict]) -> list[dict]`, `paper_filled_rows(plans) -> list[dict]`, `tp1_hit_rows(plans, shares_by_plan: Mapping[str, float]) -> list[dict]`, `live_events.direction_word(direction: str \| None) -> str`, `live_events.event_row(at, kind, text, tone, ref, pnl=None) -> dict`. Row shape: see "Event row" |
| V202-3 | Activity: `trade_closed`, `killswitch` builders; table-driven `collect_events`; wired into `/live` | 1 | sonnet | Modify `swingbot/admin/api_v1/live_events.py`, `swingbot/admin/api_v1/live.py`; create `tests/live_api/test_live_events_trades.py`, `tests/live_api/test_live_events_collect.py` | `trade_closed_rows(trades: list[dict]) -> list[dict]`, `killswitch_rows(state: Mapping) -> list[dict]`, `@dataclass(frozen=True) EventKind(kind: str, source: str, build: Callable[[dict], list[dict]])`, `EVENT_KINDS: tuple[EventKind, ...]`, `SOURCE_LOADERS: dict[str, Callable[[], Any]]` (`"plans"`, `"trades"`, `"killswitch"`, `"shares"`), `collect_events(limit: int, *, loaders: Mapping[str, Callable[[], Any]] \| None = None, now: datetime \| None = None) -> tuple[list[dict], dict]` |
| V202-4 | Routes and redirects; `insights` in `spa.WORKSPACES`; smoke lists | 1b | sonnet | Modify `frontend/src/app/app.routes.ts`, `frontend/src/app/app.routes.spec.ts`, `swingbot/admin/spa.py`, `scripts/dev/smoke_spa.py`, `tests/admin/test_spa_serving.py` | New routes `trades/calendar` (children incl. `:date`), `trades/cancels`, `insights` → `insights/analytics`, `insights/analytics`, `insights/research`, `insights/reports`, `system/versions`; titles `Calendar`, `Cancels`, `Analytics`, `Research`, `Reports`, `Versions` (subtitles unchanged). Old `calendar`, `calendar/:date`, `cancels`, `analytics`, `research`, `reports`, `versions` redirect, keeping query and fragment |
| V202-5 | Move every in-app link to the new paths; no-old-path spec | 2 | sonnet | Modify `workspaces/calendar/calendar.ts`, `workspaces/calendar/day/calendar-day.ts`, `workspaces/analytics/tabs/overview.ts`, `shell/palette/palette-items.ts` (routes only), `ui/hit-area.spec.ts`, `workspaces/calendar/calendar.spec.ts`, `workspaces/calendar/day/calendar-day.spec.ts`, `workspaces/calendar/day/month-context.spec.ts`, `routing/route-title.service.spec.ts`, `shell/palette/palette-items.spec.ts`; create `routing/old-paths.spec.ts` | `OLD_PATH_WORDS = ['calendar','cancels','analytics','research','reports','versions']` (local to the spec) |
| V202-6 | Nav model data: six destinations, sections, overrides, aliases, label invariant | 2 | sonnet | Modify `shell/nav.ts`, `shell/nav.spec.ts` | `NavSection { path; label }`, `NavEntry.sections?: readonly NavSection[]`, `NavEntry.foot?: boolean`, `NAV_ENTRIES`, `SECTION_WORDS`, `SECTION_LABEL_OVERRIDES`, `DESTINATION_LABEL_OVERRIDES`, `ALIASES` (exported, the full nine-key map). `navEntryFor` keeps its old behaviour through `NAV_GROUPS` and a private `GROUP_ALIASES` until V202-6b. See "Nav model" |
| V202-6b | Nav resolution: second-segment rule, `destinationFor`, `isSectionUrl`, breadcrumb `Destination / Section` | 2 | sonnet | Modify `shell/nav.ts`, `shell/nav.spec.ts`, `shell/breadcrumb.ts`, `shell/breadcrumb.spec.ts`; one line each in `shell/shell.spec.ts:612` and `shell/phone-tab-bar.spec.ts:51` | `navEntryFor(url) -> { entry: NavEntry; section: NavSection \| null } \| null`, `destinationFor(url: string) -> string \| null`, `isSectionUrl(url: string) -> boolean` (per destination: a segment is a section only when it is one of that destination's section words), `breadcrumbFor(url, detail) -> string[]`, `PHONE_TABS: readonly NavEntry[]` (from `NAV_ENTRIES`), `detailCrumb` unchanged; `crumbsFor(url, detail, title)` keeps its signature and becomes section-aware (`depth()` → `detailDepth()`). `NAV_GROUPS`/`NavGroup` stay exported, unchanged and `@deprecated` (removed by v203's V203-1) |
| V202-7 | More sheet, palette and phone tab bar on `NAV_ENTRIES` | 2 | sonnet | Modify `shell/more-sheet.ts` (+spec), `shell/palette/palette-items.ts` (+spec), `shell/phone-tab-bar.ts` (+spec), `shell/nav.ts` (`PHONE_TABS` labels only); expectations only in `shell/palette/command-palette.spec.ts:123`, `shell/shell.spec.ts:733,801` | `morePageGroups(entries: readonly NavEntry[] = NAV_ENTRIES, tabs: readonly NavEntry[] = PHONE_TABS) -> MoreGroup[]` with `MoreGroup = { id: string; label: string; links: { label: string; path: string }[] }`; `pageItems(entries: readonly NavEntry[] = NAV_ENTRIES) -> PaletteItem[]`; `PHONE_TABS` Dashboard label `'Home'` |
| V202-8 | `sb-section-tabs` segmented control, drawn by the shell | 2 | sonnet | Create `shell/section-tabs.ts`, `shell/section-tabs.spec.ts`; modify `shell/shell.html`, `shell/shell.ts`, `shell/shell.css`, `shell/shell.spec.ts` | `SectionTabs` (`sb-section-tabs`), inputs `entry: NavEntry \| null`, `active: NavSection \| null`; renders nothing unless `entry` has sections. `Shell.navHere: Signal<{ entry: NavEntry; section: NavSection \| null } \| null>` (`protected readonly`, computed from the router URL on `NavigationEnd`; v203's V203-1 rail reads it, V203-3's `DockState` derives its own) |
| V202-9 | Full suite once (the bump is `/close-out`'s) | 3 | haiku | none (verification only) | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | [`2026-10-29-v202-ui-shell-cockpit_1-live-endpoint-and-routes.md`](2026-10-29-v202-ui-shell-cockpit_1-live-endpoint-and-routes.md) | V202-1, V202-1b, V202-2, V202-3 | `/live` endpoint and activity feed |
| 1b | [`2026-10-29-v202-ui-shell-cockpit_1b-routes.md`](2026-10-29-v202-ui-shell-cockpit_1b-routes.md) | V202-4 | Routes, redirects and server allow-list |
| 2 | [`2026-10-29-v202-ui-shell-cockpit_2-nav-model.md`](2026-10-29-v202-ui-shell-cockpit_2-nav-model.md) | V202-5, V202-6, V202-6b, V202-7, V202-8 | Link moves, nav model and resolution, More/palette/tab bar, section tabs |
| 3 | [`2026-10-29-v202-ui-shell-cockpit_3-full-suite.md`](2026-10-29-v202-ui-shell-cockpit_3-full-suite.md) | V202-9 | Full suite once |

## Cross-task contracts

These are final: v203 consumes `/live`, the event row and the nav model as "from v202 (merged)".

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

### `/live` payload (V202-1, V202-1b, events from V202-3)

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
- `text` is the line **without** the P&L figure. The SPA's `activityLine` (v203) appends `+1.0R ($210) (paper, pre-cost)` whenever `pnl` is set:
  - `plan_alerted`: `Alert · MSFT long · entry 418.50`, ref = plan id, tone `info`
  - `paper_filled`: `Paper fill · XLE short at 92.10`, ref = plan id, tone `info`
  - `tp1_hit`: `TP1 · NVDA`, pnl from the leg, ref = plan id, tone `positive`/`negative`/`neutral` by sign of `r`
  - `trade_closed`: `NVDA closed · TP2`, pnl `{r: closed_r_multiple(t), amount: realized_pnl_amount}`, ref = trade id, tone by sign of `r`
  - `killswitch`: `Killswitch engaged` (tone `warning`) / `Killswitch released` (tone `neutral`), ref `null`
- `collect_events` meta: `{"availability", "as_of", "missing": [kind, ...]}`. A source loader that raises drops every kind built from it into `missing`: `partial` when some kinds survive, `unavailable` when none do.

### Nav model (V202-6 data, V202-6b resolution, V202-7 labels; `frontend/src/app/shell/nav.ts`)

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
export function navEntryFor(url: string): { entry: NavEntry; section: NavSection | null } | null;   // V202-6b
export function destinationFor(url: string): string | null;   // entry.path or null (V202-6b)
export function isSectionUrl(url: string): boolean;           // second segment ∈ that destination's section words, after ALIASES (V202-6b)
export function breadcrumbFor(url: string, detail: string | null): string[];  // ['Trades', 'Calendar'] / ['Risk'] / [..., detail] (V202-6b)
export const PHONE_TABS: readonly NavEntry[];                 // dashboard, watchlist, trades, risk (V202-7 labels dashboard 'Home')
export function detailCrumb(...): unchanged;
/** @deprecated */ export interface NavGroup; /** @deprecated */ export const NAV_GROUPS;   // kept for the old rail; v203's V203-1 deletes them
```

Icons: Dashboard `dashboard`, Watchlist `watchlist`, Trades `trades`, Risk `risk`, Insights `analytics`, System `system` (each distinct, all in `ICON_NAMES`). A URL whose second segment is not one of its destination's section words (`/trades/812`, `/trades/analytics`) resolves to the first section.
