# v195 — Graphite: the whole frontend redesigned

**Version:** ui 1.36.1 · bot 2.15.3
**Bump:** ui minor, bot patch — every workspace is rebuilt on a new look, shell and page template, so someone who used the app yesterday has to look at it anew (the v21 SPA-refresh precedent); the bot line moves only because the Discord alert chart images change colour.
**Edge:** none (integrity) — no signal, gate, stop, size, badge or API change. The partner reads these screens to place real orders; a calmer, denser, consistent surface lowers the chance of misreading a plan, but it buys no measurable expectancy.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor

**Status:** designed with the partner in brainstorm, 2026-10-25, section by section (visual mockups in `.superpowers/brainstorm/1939-1792961696/content/`). Replaces the "spec C (visual consistency and reorganisation)" that v194 names as its follow-up: every item on v194's spec-C list is in scope here.

**Precondition:** v194 (`2026-10-25-v194-ui-tooltips-and-data-truth.md`) is implemented and merged first. This spec builds on its top-layer `sb-hint` (Popover API) and its `title`→hint conversions, and never re-does them.

## Why

The admin UI has been refreshed piecemeal: Arctic Navy tokens (v167), motion and ambient glow (v168), saturated valence hues (v181), mobile consistency (v179), each correct in isolation. The result reads as decorated rather than professional. An ambient glow, hover lift and route-entrance animations compete with the figures; panel headings, pagers, filter bars and destructive actions differ from page to page. v194's root cause (a hover-lift transform breaking every tooltip) is a symptom of that decoration.

The partner asked for "a better, more professional and clean design" of the whole frontend, delivered as one program.

## Decisions taken in the brainstorm

| Question | Decision |
|---|---|
| Scope | Everything in one program: tokens, primitives, shell, every workspace, charts |
| Visual direction | **A · Graphite terminal**: neutral near-black, muted green/red, one steel-blue accent, no glow, no lift, minimal motion |
| Navigation | **C · Icon rail + ⌘K palette**: always-collapsed 48px rail, breadcrumb top bar, command palette; phone bottom tab bar |
| Density | Toggle, **compact default** (28px rows) with comfortable (44px) in the profile menu, stored per device. Named `dense` in code; applies at desktop only after panel review (§1.4) |
| Depth | Re-skin + re-layout on a shared page template + regroup (spec C's list). No API or data change |
| Discord chart images | Same Graphite palette (`chart_style.THEME` + `STYLE_VERSION`) |
| Light theme | No. Dark only; the token layer stays theme-ready |
| Delivery | One branch, phased plan, green at every phase |

## Scope

**In:** palette and tokens, density, motion reduction, every `frontend/src/app/ui/` primitive's look, the shell (rail, top bar, ⌘K, phone tab bar, More sheet), a shared page template, every workspace route re-laid out on it, nav regrouping, the Risk→System panel move, in-app and SVG chart theming, the Discord chart theme, a three-width layout audit.

**Out:** any backend API, schema or data change; light theme; merging, splitting or retiring a workspace; route path changes; anything the bot computes for trading; the login page beyond re-skin.

**Frontend changes beyond the look, named so they are not surprises:** a root `SearchIndexStore` for the palette, reading existing endpoints (§3.1); the Scan-health and Data-source computeds move from `RiskStore` to `SystemStore` (§5.1); one new System tab query value `?tab=providers` (§5.1); the server-stored `shell.sidebar` preference stops being read (§3); a new `ui.density` per-device key (§1.4); one new layout-audit check (Phase 7).

# Phase 1 — Visual system

## 1.1 Palette

`frontend/src/styles/palette.css` (tier 1, the only file with hued literals) is rewritten from Arctic Navy to a graphite ramp. Tier-2 semantic tokens in `tokens.css` (`--bg`, `--surface`, `--surface-raised`, `--surface-overlay`, `--text*`, `--accent`, `--pos`, `--neg`, …) **keep their names** and are repointed, so components that already read only tier 2 change no code.

| Role | Value |
|---|---|
| ground (`--bg`) | `#0d0f12` |
| surface | `#15181d` |
| raised / hover | `#1c2128` |
| overlay / popover | `#1f242b` |
| border (hairline) | `#23272e` |
| border strong | `#2d333b` |
| text | `#e6e8eb` |
| text secondary | `#c9d1d9` |
| text muted | `#9aa4b2` |
| text faint | `#6b7280` |
| accent (interactive only) | `#6ea8fe` |
| pos | `#3fb68b` |
| neg | `#e5534b` |
| warn | `#d29922` |
| category / violet | `#b392f0` |

The alpha tints (`-aNN`) are re-derived from the new hues, as plain `rgba()` literals in `palette.css` (v167 amendment 2 still holds: no `color-mix()`, so jsdom and lightweight-charts get plain strings). `--chart-1..6` and `--quality-4`, the named literal exceptions in `tokens.css`, are re-derived for the graphite ground. `frontend/src/index.html` and `frontend/public/manifest.webmanifest` carry the new `--bg` for the cold load.

Every text/surface and valence/surface pair is checked to WCAG AA in `contrast.spec.ts`; any value above that fails AA is darkened or lightened until it passes, and the spec table is amended in the same commit.

**Colour is never the only cue.** Every P&L, R and return figure carries an explicit sign (`+1.84R`, `−$212`, with a true minus sign), and direction cells keep their arrow glyph (`direction-arrow.ts`), so a loss can never read as a gain to a red/green colour-blind reader or on a poorly calibrated screen. `format.spec.ts` / `unit-format.spec.ts` pin the sign.

## 1.2 Decoration removed

Deleted: the shell's ambient glow (`.ambient`), `.sb-lift` hover lift (v194 deliberately keeps it; it goes here), route-entrance animation (`.sb-entering`, `ui/motion/route-entrance.ts`), depth shadows on panels and cards, and gradients used as surfaces. Depth comes only from surface steps and 1px borders. The overlay surfaces (palette, dialogs, menus, popovers) keep one shadow token.

`motion.css` shrinks to: colour/opacity/border transitions at ~120ms, the price-flash cue (it carries information), dialog/sheet open/close, and the `[data-motion=reduced|off]` guards. The `data-motion` attribute and `motion.service.ts` stay; the `on` state now means only those transitions.

## 1.3 Type

Inter for words, JetBrains Mono for figures (unchanged families, `fonts.css` unchanged). Scale tightened to 12 / 13 / 14 / 16 / 20 / 28 (micro and chip at 12, table 13, body 14, subhead 16, title 20, metric 28); the hero figure stays one step larger. Every figure is `tabular-nums`, right-aligned in tables, sign-coloured by `--pos`/`--neg`. Headings are sentence case; uppercase is kept only for micro labels (KPI captions, table column headers). The rail's group dividers carry no text.

## 1.4 Density

`<html data-density="dense|comfortable">` switches a token set: row height (28 / 44px), cell padding, table and body type step, panel padding. The values are `dense`/`comfortable`, not "compact", because "Compact" already means `isNarrow()` in `ui-design.md`. **Dense is the default.** The choice is a per-device preference (`ui.density` in `localStorage`, read and written in try/catch, defaulting to dense), set from the profile menu and from ⌘K.

**Dense applies at desktop (`md`, ≥ 1024px) only.** At `max-width: 1023px` (tablet and phone) the touch rules in `ui-design.md` win regardless of the setting: 44px targets, 16px control text, the existing `tap` audit check unchanged. The gate is never lowered for density.

**Order figures never shrink.** On every screen that shows a trade plan or position (Dashboard open positions, trade drawer, `trades/:id`, `plans/:id`, `watchlist/:symbol`), the entry, stop, target, size and risk-$ figures render at the 14px body step or larger in both densities.

## 1.5 Radius

6px panels and cards, 4px controls and chips, 2px cells, bars and swatches, full round only for status dots.

# Phase 2 — Primitives

Every primitive under `frontend/src/app/ui/` reads tier-2 tokens only and is re-skinned to Phase 1. Behaviour, inputs and outputs do not change except where named.

- **Panel (`sb-panel`, `layout.ts`)**: surface + hairline border, no lift class. **Panel header** (`panel-header.ts`): 13px semibold sentence-case title, the `?` hint next to it, quiet meta (count, as-of) right-aligned, optional actions slot. No uppercase banners.
- **Tables (`data-table/`, `pagination.ts`, `table-per-page.ts`)**: hairline row dividers, header row in faint micro type, density-driven row height. **One pager per table, at the bottom only.** On tablet (`sm`, 640–1023px) columns below the cut in `priority.ts` collapse into an expandable row detail instead of horizontal scroll; on phone rows render as cards (the existing v179 card mode, re-skinned). **Never collapsed:** ticker, side, stop, risk $, R/P&L and the strategy badge tier stay in the priority columns of every trade, plan and position table, so a WEAK strategy never reads as validated and a stop is never one tap away.
- **Buttons, chips, segmented, form controls, filter bar, control bar, toolbar**: flat, 4px radius, accent only on primary and selected states. Two danger variants: `danger` (solid neg fill, for the killswitch only, the one safety control) and `danger-quiet` (neg-tinted border and text, for housekeeping: restart bot, clear log, discard settings, deletes), so a halt never looks like housekeeping.
- **Stat strip / stat tile / metric card**: one KPI-strip look (cells split by hairlines inside one bordered surface).
- **Empty, loading, error states** (`empty-state.ts`, `spinner.ts`, `panel-error.ts`, `async.ts`): one style each, rendered inside the panel body.
- **Dialogs, confirm dialog, drawer, toasts**: overlay surface with the one shadow token.

# Phase 3 — Shell

`frontend/src/app/shell/` is rebuilt.

- **Icon rail (≥ `sm`)**: 48px wide, always collapsed. Brand mark, then the four nav groups (§5.1) separated by thin dividers, profile and connection status at the foot. Each entry has an `aria-label` and shows its label in an `sb-hint` on hover **and** keyboard focus. The active entry carries a 2px accent bar on its left edge (the existing `sb-nav-indicator`, restyled). The expand/collapse state, `railed`/`overlay` signals, the hamburger and the overlay sidebar are deleted. The server-stored `shell.sidebar` preference (`shell.ts`) is no longer read or written; the key is left in place (harmless, and a rollback reads it again) and listed in the results doc as orphaned.
- **Top bar (40px)**: breadcrumb left (`Group / Page / Detail`, e.g. `Review / Trades / NVDA #812`, the detail segment supplied by detail routes), the ⌘K trigger ("Search or jump…  ⌘K") centred, right cluster: killswitch state, scan progress, freshness, clock, profile menu. The profile menu gains the density toggle.
- **Killswitch state** (armed / halted) is a status chip in the top bar on every device, phone included, and links to Risk, where the killswitch control lives in the page header. On phone, Risk is a bottom-bar tab, so the halt is two taps from anywhere.
- **Freshness** (data age, last scan) stays visible in the top bar on every device, phone included, because Scan health leaves the Risk page (§5.1).
- **Ticker tape**: behaviour unchanged. It shows when `tape-prefs` holds flagged symbols, as today, restyled as a strip under the top bar. No new on/off preference.
- **Phone (< `sm`)**: the top bar collapses to the page title, the killswitch and freshness chips, and a search icon; a bottom tab bar (56px plus safe-area inset) holds Dashboard · Watchlist · Trades · Risk · More. More opens a sheet with the remaining pages and the search field.
- **Unchanged**: routes, `auth.guard.ts`, `route-focus.ts` (focus still lands on the page heading after navigation), toast service.

## 3.1 Command palette

Opened by Ctrl+K / ⌘K, `/` (when focus is not in a text field), or the top-bar trigger; a centred overlay on desktop/tablet, a full-screen sheet on phone. Focus is trapped (`focus-trap.ts`), Esc closes, ↑/↓ moves, Enter opens.

Sources come from a new root-provided `SearchIndexStore`. The existing `TradesStore`, `WatchlistStore` and `TradeDetailStore` are route-scoped (`trades.routes.ts`, `watchlist.routes.ts`, `plan-detail.routes.ts`), so the shell cannot read them. The index store calls the **existing** watchlist and trades list endpoints lazily on the palette's first open, caches for the session, and refreshes on reopen after 60s. There is no new backend endpoint. If a fetch fails, the palette still serves Pages and Preferences and shows a one-line "tickers unavailable" row.

| Group | Items | Target |
|---|---|---|
| Tickers | watchlist symbols and names | `/watchlist/:symbol` |
| Trades & plans | open and recent trades and plans, matched by ticker or id | `/trades/:id`, `/plans/:id` |
| Pages | every rail entry and workspace tab | its route |
| Preferences | density dense/comfortable | applies in place |

Ranking: exact prefix on ticker or id first, then prefix on name, then substring; ties keep the group order above. Empty query shows Pages and the five most recent trades. **Navigation and preferences only**: no scan trigger, restart, killswitch or any destructive or money-moving action is ever reachable from the palette.

# Phase 4 — Page template

A shared `sb-page` component with five slots, used by every workspace route:

1. **Header**: title (20px), one-line description, an **actions slot** on the right.
2. **Scope bar**: filters and scope only (horizon, side, date range, tabs). Never a destructive action.
3. **KPI strip**: 2–6 headline figures (Phase 2 strip).
4. **Primary panel**: full width.
5. **Secondary grid**: 2 columns at `lg` and up, 1 column below.

Any slot may be empty and then takes no space. **Destructive actions** (killswitch, restart bot, clear log, discard settings, any delete) live only in the header actions slot and always open `confirm-dialog`: the killswitch as `danger`, everything else as `danger-quiet` (§2).

# Phase 5 — Workspaces

## 5.1 Regrouping

| Rail group | Pages | Change |
|---|---|---|
| Monitor | Dashboard · Watchlist · Risk | Risk drops *Scan health* and *Data source* |
| Review | Trades · Calendar · Cancels | the trade book and its history |
| Insights (new) | Analytics · Research · Reports | split out of Review, which had six entries |
| System | System · Versions | gains *Scan health* and *Data source* beside *Data providers* |

System's tabs become **Scan · Providers · Settings · Logs**: Providers holds *Data providers*, *Data source*, *Scan health* and *Swallowed errors*. The Scan-health and Data-source computeds (`risk.store.ts`, today read by `risk.ts`) move into `SystemStore`; `RiskStore` keeps only risk. `SYSTEM_TABS` (`system.store.ts`) gains `providers`, adding the URL `?tab=providers`, and the layout audit's `ROUTES` gains that entry. Route paths do not change. `?tab=scan` still opens Scan, so a bookmark that expected Swallowed errors there now finds it one tab over. Nothing is merged or retired.

Concentration (top sector, max cluster) is shown on Risk only, as today; Dashboard links to it from the open-risk KPI. The UI gallery (`/ui`) stays off the rail and is re-laid out as the reference page for every primitive.

## 5.2 Per-workspace layout

Each workspace is rebuilt on `sb-page` with its existing panels, mapped to slots. The plan assigns each panel; the rules are:

- The figure the partner acts on goes in the KPI strip (e.g. Risk: open risk, cap headroom, top sector, max cluster; Dashboard: open risk, month ExpR, month R, win rate, open positions).
- **Risk figures carry their units together**: open risk and cap headroom show dollars and % of account side by side (`$1,420 · 1.42%`), against the dollar-risk cap; R is added where the source figure is in R. Never an R-only or %-only risk tile.
- **Performance strips lead with expectancy**: ExpR comes first and win rate after it, never in the lead slot. Every performance KPI shows its sample size (`N=37`), marks a small sample with the existing small-N cue, and states its basis (paper, pre-cost, pre-tax) in its hint, using v194's metric-basis wording.
- The page's main table or chart is the primary panel (Dashboard: open positions; Trades: the trade table; Risk: portfolio heat; Watchlist: the watchlist table).
- Detail routes (`trades/:id`, `plans/:id`, `watchlist/:symbol`, calendar day) use the same template with the breadcrumb detail segment and no scope bar.
- Every panel keeps its v194 hint text; no explanatory text is dropped.

# Phase 6 — Charts

- **In-app (lightweight-charts and `chart/`)**: grid, axes, crosshair, candles, volume, and entry/target/stop lines are read from tokens through the chart palette helper. Candles and P&L share `--pos`/`--neg`; entry uses `--accent`; target and stop are dashed pos/neg.
- **SVG primitives** (sparkline, histogram, heat grid, gauge, waterfall, donut, dot/strip plot, matrix, small multiples, timeline): no chart-local colour; every fill reads a token.
- **Discord alert images**: `swingbot/core/charts/chart_style.py` `THEME` moves to the Graphite values and `STYLE_VERSION` is bumped in the same commit. `THEME` gains `accent`, and `ENTRY_COLOR` reads it (today it reads `chart-1`), so the entry line is the same colour in an alert image and in the app. `python scripts/dev/dump_tokens.py` regenerates `tests/charts/resolved_tokens.json`. Its other readers, `frontend/src/test-setup.ts` and `ui/testing/resolve-token.ts`, pick up the new values. `tests/charts/test_chart_theme.py` gets a new row appended to `STYLE_PINS` (append-only: never edit an old row). A before/after rendered alert image is recorded in the results doc.

# Phase 7 — Verification and release

- **Layout audit**: `frontend/scripts/layout-audit-lib.mjs` (Playwright) runs every route, including the new `?tab=providers`, at 390 / 768 / 1440 against a local instance built from `.env` credentials. All existing `CHECKS` stay, unchanged (overflow, `tap` 44px up to 1023px, v194's `hint` visibility, …). One new check, `rail-label`, is appended after v194's `hint`: every rail entry has an accessible name, and its hint is visible when the entry has keyboard focus. After deploy, the audit runs once more against production (bomeo-capital.com), as v194 does. Results to `docs/superpowers/results/2026-10-25-v195-layout-audit.md`.
- **Release**: ui minor and bot patch resolved from `VERSION.json` at close-out, version history regenerated, full suite once as the plan's final task.

## Testing

Every phase ships its own unit tests, test-first:

- Tokens: `tokens.spec.ts`, `contrast.spec.ts`, `spacing.spec.ts`, `elevation.spec.ts`, `motion-css.spec.ts`, `text-styles.spec.ts` updated to the new values (updated, never deleted); a density spec (attribute switch, default dense, storage failure falls back to dense, touch rules win at ≤ 1023px, order figures ≥ 14px in both densities); a sign spec (every signed figure carries +/−).
- **Retired with the feature they test**, the only specs deleted: `ui/motion/route-entrance.spec.ts` and `no-replay.spec.ts` (route entrance removed, §1.2), and the shell's expand/collapse and overlay cases in `shell.spec.ts`. Each one is named in the commit that removes its feature.
- Shell: rail (labels on focus, active indicator, no expand state), breadcrumb (static and detail segments), phone tab bar and More sheet, profile density toggle.
- Palette: ranking (prefix ticker > prefix name > substring), empty query, no matches, a ticker absent from stores, focus trap and Esc, `/` ignored inside a text field, and an assertion that no destructive action is registered.
- `sb-page`: each slot present/absent, actions slot, destructive actions open the confirm dialog.
- Workspaces: each rebuilt route's existing spec kept green; the regrouping (panels present on System, absent on Risk); `workspace-consistency.spec.ts` extended to assert every route uses `sb-page`.
- Charts: chart palette spec, `test_chart_theme.py` with the new THEME.
- Every function stays under complexity 15 (`complexity_gate.py`).

## Risks

- **Colour tests churn**: many specs pin token values. They move with Phase 1 in the same commits; a spec that pinned a palette name rather than a role is repointed to the role.
- **Icon recognition**: an always-collapsed rail relies on icons. Mitigated by hover/focus labels, the breadcrumb, and ⌘K; the audit checks every rail entry has a label.
- **Concurrent plans touching the frontend** (v194 first, then anything else in flight) will conflict. v194 must be merged before this branch is cut; any other UI plan merged meanwhile is rebased onto the phase it touches.

## Rollback

The UI ships as one image. Rolling back means redeploying the previous image tag; no data migrates. The orphaned `shell.sidebar` key is read again by the old shell. The new `ui.density` (localStorage) and `?tab=providers` (unknown tab: falls back to Scan) are ignored by it. Discord chart images return to the old palette with the bot image; `STYLE_VERSION` rows are append-only, so a rollback never needs a test edit. There is no chart cache to purge: alert images are rendered per alert.

## Parallelisation

Phases are sequential: 1 (tokens) → 2 (primitives read the tokens) → 3 (shell uses primitives) → 4 (template uses primitives) → 5 (workspaces use the template and shell groups). Phase 6 (charts) needs only Phase 1 and may run beside Phases 3–5. Within Phase 5 the three groups (Monitor; Review; Insights + System) are independent of one another once Phase 4 lands. Phase 7 is last.

## Panel review

Run 2026-10-25 on `0889f13f` (staff-engineer on opus, financial-advisor on sonnet, serially). No staff-engineer finding hit a BLOCKING red flag; financial-advisor raised two BLOCKING.

**BLOCKING**
- financial-advisor 1: risk KPIs did not require dollars and % of account together (the 2% cap is a dollar cap) -- applied (§5.2, units rule).
- financial-advisor 2: Dashboard strip put win rate in a headline slot, no ExpR, no N, no pre-cost/pre-tax basis -- applied (§5.2: ExpR leads, N + small-N cue, basis in hint).

**ADVISORY**
- staff-engineer 1: palette's stores are route-scoped, so "no new API/store" was false -- applied (root `SearchIndexStore` on existing endpoints, §3.1; Out line and named-changes list amended).
- staff-engineer 2: Scan health / Data source read `RiskStore` computeds -- applied (computeds move to `SystemStore`, §5.1).
- staff-engineer 3: Providers tab adds `?tab=providers` -- applied (named in §5.1, audit ROUTES entry, bookmark note).
- staff-engineer 4: compact rows at 768 would fail the 44px `tap` check up to 1023px -- applied (dense at ≥ 1024px only; touch rules win below, §1.4).
- staff-engineer 5: `tape-prefs` has no on/off state -- applied (tape behaviour unchanged, no "off by default", §3).
- staff-engineer 6: orphaned `shell.sidebar` pref, no rollback section -- applied (§3 note, new `## Rollback`).
- staff-engineer 7: route-entrance specs are deleted with the feature -- applied (retired specs named in Testing).
- staff-engineer 8: `STYLE_PINS` is append-only; other readers of `resolved_tokens.json` -- applied (§6).
- staff-engineer 9: Discord `ENTRY_COLOR` on chart-1 vs in-app accent -- applied (`THEME` gains `accent`, entry reads it, §6).
- staff-engineer 10: `md` is desktop, not tablet; "compact" collides with `isNarrow()` naming -- applied (`sm` for tablet; density value renamed `dense`).
- staff-engineer 11: rail-label is a new check; v194 also audits production -- applied (new `rail-label` CHECK after `hint`; post-deploy production audit, Phase 7).
- staff-engineer 12: manifest path is `frontend/public/` -- applied (§1.1).
- financial-advisor 3: colour-only valence -- applied (explicit +/− sign and arrows required, §1.1).
- financial-advisor 4: dense rows on order screens -- applied (entry/stop/target/size/risk $ at ≥ 14px in both densities, §1.4).
- financial-advisor 5: tablet column collapse could hide stop/risk/badge -- applied (never-collapsed columns, §2).
- financial-advisor 6: killswitch looks like housekeeping; phone reach; state -- applied (`danger` vs `danger-quiet`, killswitch state chip in top bar on all devices, §2/§3/§4).
- financial-advisor 7: staleness leaves Risk -- applied (freshness chip always visible, phone included, §3).
- financial-advisor 8: concentration on Risk only -- applied (stated in §5.1, Dashboard links to it).
