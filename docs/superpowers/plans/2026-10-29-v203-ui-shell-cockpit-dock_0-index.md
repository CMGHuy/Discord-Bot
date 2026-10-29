# UI shell cockpit (v202 Phase 1, plan B: rail, Live dock and top bar) implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md)
**Depends on:** [v202, plan A: `/live` and navigation](2026-10-29-v202-ui-shell-cockpit_0-index.md) merged on `main`. Branch this plan's worktree from a `main` that contains it.

No bot bump: this plan changes no Python and no backend route. It only reads v202's `GET /api/v1/live`.

**Goal:**

The spec behind this plan (v202, Phase 1 of the partner's "cockpit + live
dock" redesign) was too big for one plan under the 20-task cap, so it is
built in two. v202 shipped the data and the navigation: the `/live`
endpoint, the six-destination routes and redirects, the `NAV_ENTRIES`
model, section tabs, and the More sheet, palette and phone tab bar on that
model. **This plan builds the shell the partner actually looks at.** Today,
after v202, the rail still shows eleven unlabelled glyphs, live state is
four small top-bar chips, portfolio heat is a page away on Risk, and the
two-tone BomeoCapital wordmark that v195 dropped is still missing.

Once this ships, the rail is 80 px wide and carries **six labelled
destinations**, System at the foot. The top bar leads with the wordmark
again and keeps only the killswitch chip, plus an alarm chip that appears
only while data is stale, the stream is down or the bot is down. A
right-hand **Live dock** (320 px on desktop) shows four sections: Bot,
Plans awaiting order, Portfolio heat and Activity. Collapsed, it is a 40 px
edge tab. On tablet and phone a 40 px live strip under the tape opens the
same dock as a sheet. Each page has its own open/collapsed default, and the
partner's choice is remembered server-side per destination. A collapsed
dock can never hide an alarm: the edge tab and the strip take a warning
tone.

In idea: a root `LiveStore` reads `/live` (from v202, merged) and refreshes
it, debounced 2 s, on the `trades`, `scan`, `bot` and `risk` stream events.
A root `DockState` resolves the destination with v202's `destinationFor` and
holds the per-page default, the persisted toggle and the sheet. The warning,
alarm, heat-tone and time rules are pure functions in
`shell/live/live-state.ts`, so every surface (edge tab, strip, alarm chip,
sections) words a state the same way. The dock never touches `RiskStore`.

Left alone: page content and layout, colours, type and component styling
(Phase 2), the server and every stored record shape. Heat never turns red
in Phase 1: amber from 80 % of the cap, plus the words "Over cap" above
100 %.

Success: the spec's §8 shell, dock and top-bar tests are green. The bot
stopped at 09:00 reads "No scan since 09:00 (5h ago)" in warning tone, never
"Nothing yet today". The layout audit at 390 / 768 / 1440 px finds no
overflow, no tap target under 44 px and no dock overlapping content
(V203-10). The full suite is green once (V203-11).

**Architecture:** One seam, the **shell**, on top of v202's contracts.
There is a labelled 80 px rail, the wordmark top bar and `sb-alarm-chip`.
The root `LiveStore` (`/live`, debounced 2 s on `trades`, `scan`, `bot` and
`risk`) and the root `DockState` (destination, per-page default, persisted
toggle, sheet) feed `sb-live-dock` and its four section components,
`sb-live-edge-tab`, `sb-live-strip` and `sb-live-sheet`. The warning and
alarm rules live as pure functions in `shell/live/live-state.ts`. The
desktop grid gains `.workspace-row` = `main.workspace` + `aside.live-column`.

**Tech Stack:** Angular (standalone, zoneless, signals, `@ngrx/signals`
`signalStore`), vitest via `ng test`; the Node layout audit
`frontend/scripts/layout-audit.mjs` (Playwright).

**What follows:** the spec's What follows, unchanged: the Phase 2 foundations spec, a bot event log for stop moves (and TP1 times and killswitch transitions), `/health` market session state for the dock's Market row, a concentration row in the dock, and Phase 4's close-out removing the old route names with `cockpit` and `universe`.

## Global Constraints

- **`Bump: ui minor`.** No task edits `VERSION.json`. `/close-out` resolves the bump and regenerates `swingbot/admin/version_history.json` (`document-conventions.md` § The header block).
- **v202 is merged first.** `GET /api/v1/live`, `NAV_ENTRIES`, `navEntryFor`, `destinationFor`, `PHONE_TABS`, `SectionTabs` and `Shell.navHere` exist on `main` "from v202 (merged)". No task of this plan changes them or any file under `swingbot/` or `tests/` (Python).
- Implement in a worktree under `.claude/worktrees/` (name per `document-lifecycle.md`). Every command uses absolute paths or `git -C <wt>`. Stage explicit paths only, never `git add -A`. Never `cd` in Bash: use `npm --prefix <wt>/frontend …`.
- **Spec wins over the Figma mockups.** Dock wording is the spec's: "Paper fill", "(paper, pre-cost)", "incl. resting orders", "Active: new alerts paused since 09:31", "Clear", "Over cap", "Nothing yet today", "No scan since 09:00 (5h ago)".
- **No new colours, type scale, spacing or component styling** (Phase 2). Use today's tokens only (`--accent`, `--accent-soft`, `--text`, `--warn`/amber tone classes already in `styles`). Heat never turns red in Phase 1. Amber from 80 % of the cap, plus the words "Over cap" above 100 %.
- **No page's content or layout changes.** A workspace component, store or resolver never moves.
- **The dock never instantiates `RiskStore`** and never calls `/risk`. A spec pins it (V203-7).
- **No browser storage.** The dock toggle is stored only through `PreferencesStore`, under key `shell.dock`: a map from destination path to boolean, never keyed by a section or old path. A failed preference read falls back to the per-page default.
- All shell times are **Berlin local** via `timeInZone(iso, 'Europe/Berlin')` (`ui/format.ts:176`) with a relative age (`scanAge`, `shell/freshness-chip.ts`).
- **Stale rule = 900 s**, the `ui/freshness.ts` rule (V203-3 exports it as `STALE_AFTER_SEC`). The alarm chip, edge-tab/strip warning tone and the "No scan since" line all use it.
- **SPA tests fake `/live`** from the fixed payload shape below (`HttpTestingController` or a stub `ApiClient`), never a live server. SPA tests are co-located `*.spec.ts`. Every task ships tests for its empty, failure and edge cases.
- **DB:** only the layout audit (V203-10) and the full suite (V203-11) run against Postgres. Each runs `/replicate-prod-db` first if this session has not, against the one shared `swing-db` container. No per-task container or database.
- **Per-task verification is the narrow run:** SPA `npm --prefix <wt>/frontend test -- --watch=false --include <spec path relative to frontend/>`; lint `npm --prefix <wt>/frontend run lint`; audit lib `node --test <wt>/frontend/scripts/layout-audit-lib.test.mjs`. The one full-suite run is V203-11.
- **Every UI task checks phone, tablet and desktop** (`ui-design.md`). It builds and serves the SPA locally with the `.env` admin credentials (loaded inside the script, never printed), then runs `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440`. It also states in its report that there is no horizontal scroll, that touch targets are 44 px and that nothing overlaps.
- Every function written or changed stays below cyclomatic complexity 15 (`python scripts/dev/complexity_gate.py`). Alarm and warning rules are table-driven.
- **`shell.spec.ts` assertions that pin the old rail, cluster or brand are retired explicitly** in the task that changes that element, never silently. The task lists each one as "Retired" or "Moved" with its replacement (the v195 `fdf6b78a` precedent).
- Do not commit on `main`. The plan's tasks commit on the worktree branch, in scoped commits.

## Review Focus

- **The bot stopped at 09:00 and nothing happened since.** The activity section reads "No scan since 09:00 (5h ago)" in warning tone, never "Nothing yet today". The edge tab and strip turn warning-toned, and the alarm chip shows "Data stale …" (V203-3, V203-6, V203-9).
- **A failed source looks like a quiet day.** With `events_meta.availability == "partial"` the dock prints "Some sources unavailable: …". With `unavailable` it shows "Activity unavailable" plus a retry (V203-6; the server side is v202's V202-3).
- **A collapsed dock hides an alarm.** Every warning in `liveWarnings` reaches the edge tab and the strip as a warning tone (V203-7, V203-8).
- **The dock reads `RiskStore`.** It must not, and heat comes only from `/live` (V203-7).
- **The rail lights the wrong destination** on `/insights/analytics?tab=tuning#x` or `/trades/calendar` (V203-1, reading v202's `navEntryFor`).

## Parallelisation

At most 2 implementers at once (`CLAUDE.md`). Sequential edges and why:

- **V203-1 ∥ V203-2.** The rail rewrite owns `shell.html`/`shell.css`/`shell.ts`/`shell.spec.ts`, `nav.ts`/`nav.spec.ts` and the audit lib's `railLabelVerdict`. V203-2 owns only `api/models.ts`, `api/api-client.ts` (+spec) and `stores/live.store.ts` (+spec).
- **V203-1 → V203-1b:** the indicator and `NAV_GROUPS` go once the new rail no longer uses them; both edit `shell.spec.ts` consumers' expectations.
- **V203-3 → V203-3b:** `DockState` reads `dockDefaultOpen`/`readDockOpen`/`writeDockOpen` from `live-state.ts`.
- **V203-3b → V203-7:** the dock reads `DockState`.
- **V203-2 → V203-3:** the warning rules read `LiveHeat`/`LiveKillswitch` types. `DockState` resolves the destination with `destinationFor` from v202 (merged).
- **V203-3 → V203-4, V203-5, V203-6.** These three section components have disjoint files and may run in parallel, two at a time. V203-4 ∥ V203-1 is also allowed (disjoint files) once V203-3 is in.
- **V203-1, V203-4, V203-5, V203-6 → V203-7:** the dock composes the sections, and the shell's desktop grid is the rail task's markup.
- **V203-7 → V203-8 → V203-9:** each edits `shell.html`, `shell.css`, `shell.ts` and `shell.spec.ts`.
- **V203-9 → V203-10:** the audit checks the final top bar, the dock and the rail together; V203-1b and V203-10 both edit `layout-audit-lib.mjs` and its test.
- **V203-10 → V203-11.**

## Task ledger

| ID | Title | Part | Model | Files | Cross-task contract |
|---|---|---|---|---|---|
| V203-1 | Labelled 80 px rail, System at the foot; per-link hints retired | 1 | sonnet | Modify `shell/shell.html`, `shell/shell.css`, `shell/shell.ts`, `shell/shell.spec.ts`, `ui/hit-area.spec.ts` | Rail markup: `nav.rail > a.rail-brand` then `ul.nav.rail-work > li > a.rail-link` ×5 then `ul.nav.rail-foot > li > a.rail-link` (System) then the version hint; each `a.rail-link` holds `sb-icon` + `span.rail-label` (`--text-micro`), active pill = `.rail-link.active .rail-pill`. CSS token `--rail-width: 80px`. Reads `NAV_ENTRIES` and `Shell.navHere` from v202 (merged) |
| V203-1b | Retire `sb-nav-indicator` and `NAV_GROUPS`; rail-label audit on the visible label | 1 | sonnet | Modify `shell/nav.ts` (delete `NAV_GROUPS`, `NavGroup`), `shell/nav.spec.ts`, `styles/motion.css`, `ui/motion-css.spec.ts`, `frontend/scripts/layout-audit-lib.mjs` (`railLabelVerdict`), `frontend/scripts/layout-audit-lib.test.mjs`, `frontend/scripts/layout-audit.mjs` (`auditRailLabels`); delete `shell/nav-indicator.ts`, `shell/nav-indicator.spec.ts` | Audit `rail-label` measures `.rail-label`, not hints; three-width audit run covers V203-1 and V203-1b |
| V203-2 | `/live` client types, `ApiClient.live`, root `LiveStore` (debounced refresh) | 1 | sonnet | Modify `api/models.ts`, `api/api-client.ts`, `api/api-client.spec.ts`; create `stores/live.store.ts`, `stores/live.store.spec.ts` | Types in "SPA types". `ApiClient.live(limit?: number): Observable<LiveSnapshot>`. `LiveStore` (root): `snapshot()`, `loading()`, `failed()`, `heat()`, `awaiting()`, `killswitch()`, `events()`, `eventsMeta()`, `load(): void`, `retry(): void`; `LIVE_REFRESH_DEBOUNCE_MS = 2000`, `LIVE_REFRESH_EVENTS = ['trades','scan','bot','risk'] as const` |
| V203-3 | Live-state rules (warnings, alarm, heat tone, times) | 1 | sonnet | Create `shell/live/live-state.ts`, `shell/live/live-state.spec.ts`; modify `ui/freshness.ts` (export `STALE_AFTER_SEC`) | See "Live-state rules" |
| V203-3b | `DockState` | 1b | sonnet | Create `shell/live/dock-state.ts`, `shell/live/dock-state.spec.ts` | See "DockState" |
| V203-4 | Dock Bot section (scanner, last scan, freshness, stream, market, killswitch wording) | 1b | sonnet | Create `shell/live/live-bot-section.ts`, `shell/live/live-bot-section.spec.ts` | `LiveBotSection` (`sb-live-bot`), inputs: `botAlive: boolean \| null`, `botHealthy: boolean \| null`, `scanRunning: boolean`, `lastSuccess: string \| null`, `lastSeen: string \| null`, `streamState: ConnectionState`, `marketActive: boolean \| null`, `killswitch: LiveKillswitch \| null`, `now: Date` |
| V203-5 | Dock Plans-awaiting and Portfolio-heat sections | 2 | sonnet | Create `shell/live/live-awaiting-section.ts` (+spec), `shell/live/live-heat-section.ts` (+spec) | `LiveAwaitingSection` (`sb-live-awaiting`), inputs `awaiting: LiveAwaiting \| null`, `loading: boolean`, `now: Date`. `LiveHeatSection` (`sb-live-heat`), inputs `heat: LiveHeat \| null`, `loading: boolean`, `currency: string`, `now: Date`; output `retry: void` |
| V203-6 | Dock Activity section | 2 | sonnet | Create `shell/live/live-activity-section.ts` (+spec) | `LiveActivitySection` (`sb-live-activity`), inputs `events: readonly LiveEvent[]`, `meta: LiveEventsMeta \| null`, `loading: boolean`, `lastSuccess: string \| null`, `now: Date`; output `retry: void`; `activityLine(e: LiveEvent): string` exported |
| V203-7 | `sb-live-dock`, `sb-live-edge-tab`, desktop docking with persisted per-page toggle | 2 | sonnet | Create `shell/live/live-dock.ts` (+spec), `shell/live/live-edge-tab.ts` (+spec); modify `shell/shell.html`, `shell/shell.css`, `shell/shell.ts`, `shell/shell.spec.ts` | `LiveDock` (`sb-live-dock`), input `variant: 'docked' \| 'sheet'`, output `close: void`; `LiveEdgeTab` (`sb-live-edge-tab`), inputs `warnings: readonly LiveWarning[]`, `heatText: string`, `awaitingCount: number \| null`; output `expand: void`. Shell grid: `.workspace-row` = `main.workspace` + `aside.live-column` (320 px open / 40 px collapsed, only when `dock.docked()`) |
| V203-8 | `sb-live-strip` and `sb-live-sheet` for tablet and phone | 2 | sonnet | Create `shell/live/live-strip.ts` (+spec), `shell/live/live-sheet.ts` (+spec); modify `shell/shell.html`, `shell/shell.css`, `shell/shell.ts`, `shell/shell.spec.ts` | `LiveStrip` (`sb-live-strip`), inputs `warnings`, `heatText`, `awaitingCount`, `lastSuccess`, `now`; output `opened: void`. `LiveSheet` (`sb-live-sheet`), inputs `open: boolean`, `side: 'right' \| 'bottom'`; output `closed: void` |
| V203-9 | Top bar: wordmark, alarm chip, killswitch only; chips and clock leave the bar | 3 | sonnet | Create `shell/alarm-chip.ts` (+spec); modify `shell/shell.html`, `shell/shell.css`, `shell/shell.ts`, `shell/shell.spec.ts`, `ui/hit-area.spec.ts` | `AlarmChip` (`sb-alarm-chip`), input `alarm: Alarm \| null`; output `reveal: void`. Final top-bar order (desktop/tablet): `a.brand` (wordmark) · `span.topbar-divider` · `sb-breadcrumb` · flex · `div.status-cluster` (`sb-alarm-chip`, `sb-killswitch-chip`) · `button.search-trigger` · `sb-profile-menu`; phone: `a.brand` (diamond + wordmark) · flex · `div.status-cluster` · `button.search-trigger` · `sb-profile-menu` · `sb-scan-progress` |
| V203-10 | Layout audit at three widths: new routes, dock-overlap check, results | 3 | sonnet | Modify `frontend/scripts/layout-audit-lib.mjs`, `frontend/scripts/layout-audit-lib.test.mjs`, `frontend/scripts/layout-audit.mjs`; create `docs/superpowers/results/2026-10-29-v203-layout-audit.md` | `ROUTES` lists the new paths (old ones dropped); new check `dock`: `aside.live-column` intersects `main.workspace` content box at >= 1024 px, or the live sheet leaves the viewport; `CHECKS` gains `'dock'` |
| V203-11 | Full suite once (the bump is `/close-out`'s) | 3 | haiku | none (verification only) | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | [`2026-10-29-v203-ui-shell-cockpit-dock_1-rail-and-live-state.md`](2026-10-29-v203-ui-shell-cockpit-dock_1-rail-and-live-state.md) | V203-1..V203-3 | Labelled rail, `LiveStore`, live-state rules |
| 1b | [`2026-10-29-v203-ui-shell-cockpit-dock_1b-dock-state-and-bot.md`](2026-10-29-v203-ui-shell-cockpit-dock_1b-dock-state-and-bot.md) | V203-3b..V203-4 | `DockState`, Bot section |
| 2 | [`2026-10-29-v203-ui-shell-cockpit-dock_2-dock.md`](2026-10-29-v203-ui-shell-cockpit-dock_2-dock.md) | V203-5..V203-8 | Awaiting, heat and activity sections; dock, edge tab, strip, sheet |
| 3 | [`2026-10-29-v203-ui-shell-cockpit-dock_3-topbar-audit-and-close.md`](2026-10-29-v203-ui-shell-cockpit-dock_3-topbar-audit-and-close.md) | V203-9..V203-11 | Top bar and alarm chip, layout audit, full suite |

## Cross-task contracts

### Consumed from v202 (merged)

These exist on `main` before this plan starts. Their full definitions are in the [v202 index](2026-10-29-v202-ui-shell-cockpit_0-index.md) § Cross-task contracts; the parts below cite them as "from v202 (merged)".

- **`GET /api/v1/live`** (V202-1, V202-1b, V202-3): `{heat, awaiting, killswitch, events, events_meta}`. A failed section keeps its keys with `null` values, `availability: "unavailable"` and a short `reason`; heat and awaiting are never `partial`. `utilisation_pct` is **unclamped**; `headroom_*` is negative over the cap. `awaiting.next_expiry` is `null` when no PENDING plan has a `valid_session`. `killswitch.since` is set only when engaged. `?limit=` default 8, max 50.
- **Event row** (V202-2, V202-3): `{at, kind, text, tone, ref, pnl}`. `text` carries no P&L; `activityLine` (V203-6) appends `+1.0R ($210) (paper, pre-cost)` when `pnl` is set (`pnl.amount` may be `null`: then `+1.0R (paper, pre-cost)`). `events_meta.missing` lists the kinds of a failed source.
- **Nav model** (`frontend/src/app/shell/nav.ts`; V202-6, V202-6b, V202-7): `NavSection`, `NavEntry { path; label; icon; sections?; foot? }`, `NAV_ENTRIES` (Dashboard, Watchlist, Trades, Risk, Insights, System with `foot: true`), `navEntryFor(url) -> { entry; section } | null`, `destinationFor(url) -> string | null`, `isSectionUrl(url)`, `breadcrumbFor(url, detail)`, `PHONE_TABS` (Dashboard labelled `'Home'`). `NAV_GROUPS`/`NavGroup` are still exported and `@deprecated`; V203-1 deletes them and any lint suppression for them in `shell/shell.ts`.
- **`SectionTabs`** (`sb-section-tabs`, V202-8) and **`Shell.navHere: Signal<{ entry: NavEntry; section: NavSection | null } | null>`** (`protected readonly`, from the router URL on `NavigationEnd`). V203-1's rail reads `navHere`; V203-3's `DockState` derives its destination itself with `destinationFor`.

### `/live` payload (shape the SPA types mirror)

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

### SPA types (V203-2; `frontend/src/app/api/models.ts`)

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

### Live-state rules (V203-3; `frontend/src/app/shell/live/live-state.ts`)

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
export function heatStripText(heat: LiveHeat | null, currency: string): string;   // 'Heat 2,010 € · 4.2% / 6%' | 'Heat 3,100 € · 7.8% / 6% · Over cap' | 'Heat —' (money via ui/format.ts amount())
export function liveTime(iso: string | null, now: Date): string;           // '14:32 · 6 min ago' (Berlin) | '—'
export const DOCK_PREF_KEY = 'shell.dock';
export const DOCK_DEFAULT_OPEN: ReadonlySet<string>;                       // '/dashboard', '/risk'
export function dockDefaultOpen(destination: string | null): boolean;
export function readDockOpen(prefs: Preferences, destination: string, fallback: boolean): boolean;  // non-boolean → fallback
export function writeDockOpen(prefs: Preferences, destination: string, open: boolean): Preferences; // new object
```

`ui/freshness.ts` exports `STALE_AFTER_SEC = 900` and uses it as the `staleAfterSec` input default. "Disconnected" means `streamState` is `'dead'` or `'degraded'`, "Bot down" means `botAlive === false`, and "stale" means `isStale(lastSuccess, now)` and is evaluated only once `/health` has answered (`botAlive !== null`).

### DockState (V203-3; `frontend/src/app/shell/live/dock-state.ts`)

```ts
@Injectable({ providedIn: 'root' })
export class DockState {
  readonly destination: Signal<string | null>;   // destinationFor(router url) from v202 (merged), updated on NavigationEnd
  readonly docked: Signal<boolean>;              // viewport is md or wider (>= 1024 px)
  readonly open: Signal<boolean>;                // readDockOpen(prefs, destination, dockDefaultOpen(destination)); a pre-load or failed read gives the default
  readonly sheetOpen: Signal<boolean>;
  toggle(): void;      // flips open for the current destination; preferences.update(p => writeDockOpen(p, dest, !open))
  reveal(): void;      // docked ? (open || toggle()) : openSheet()
  openSheet(): void;
  closeSheet(): void;  // also on NavigationEnd and when the viewport becomes docked
}
```
