# v194 — UI integrity: tooltips that open, figures that are true

**Version:** ui 1.36.1 · bot 2.15.3
**Bump:** ui patch, bot patch — every change fixes something that is shown wrong or not shown at all; the bot line moves only for the sector-map fix (B6).
**Edge:** none (integrity) — no signal, gate, stop, size or badge changes; the partner reads these screens to place real orders, so a hidden definition or a wrong figure is an integrity defect.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor

**Status:** approved by the partner in brainstorm, 2026-10-25 (sections A and B). Sequencing: this spec first; a follow-up spec C (visual consistency and reorganisation) builds on the fixed primitives.

## Why

The partner reported that the Plan lifecycle help icon on the Dashboard shows nothing on hover. A Playwright probe of production (bomeo-capital.com, 2026-10-25, ui 1.36.0) hovered every `sb-hint` trigger on 20 routes and tested whether the popover was the topmost element at its own centre:

| Width | `sb-hint` triggers | Not visible when opened |
|---|---|---|
| 1440 | 20 | 19 |
| 768 | 24 | 23 |
| 390 | 24 | 24 |

Every failure has the same signature: the popover is open (`hidden` false) and its `top` is roughly twice the trigger's (e.g. trigger 441px, popover 880px).

**Root cause.** `sb-panel` renders `<section class="panel sb-panel sb-lift">` (`frontend/src/app/ui/layout.ts:43`) with `overflow: hidden`. Under `[data-motion=on]`, `.sb-lift:hover` sets `transform: translateY(-2px)` (`frontend/src/styles/motion.css`, "#5 hover and press"). A transformed ancestor becomes the containing block for `position: fixed` descendants, so `sb-hint`'s popover (`frontend/src/app/ui/hint.ts`, `.pop { position: fixed }`, top/left from the trigger's *viewport* rect) is offset by the panel's own page position and then clipped by the panel. Hovering the trigger always hovers the panel, so the popover fails exactly when it is wanted. `.sb-entering` (`will-change: transform, opacity, filter`, ~1s after every route change) produces the same failure. Real touch devices (`hover: none`) do not apply the lift, but still hit the entrance window.

The same probe found 17–94 native `title` attributes per route (110 in source). A `title` opens only on mouse hover after a delay: never on a phone or tablet, never by keyboard. Where it carries explanation, that explanation is invisible on two of the three device classes `ui-design.md` requires.

API checks against production (2026-10-25) separated real data defects from display defects; section B lists only confirmed ones.

## Scope

**In:** A — tooltip rendering, a visibility check in the layout audit, `title`→hint conversion, a content audit of every hint and chart tooltip. B — eight confirmed wrong or misleading figures and labels.

**Out (spec C, next):** panel-heading style, one pager per table, compact tablet tables, destructive actions out of filter bars, Risk/System regrouping, phone tab labels. Out entirely: any change to what the bot computes for trading.

# Phase A — Tooltips

## A1. `sb-hint` renders in the top layer

`sb-hint`'s popover element takes the native Popover API (`popover="manual"`) and is shown with `showPopover()` / hidden with `hidePopover()` driven by the existing `open` computed signal. The top layer is outside every ancestor's containing block, `overflow` clip and stacking context, so no transform, filter, `will-change`, `contain` or `z-index` anywhere above it can hide or misplace it.

Kept unchanged: the three open reasons (hover, focus, pin) and their phone tap ordering; Escape and outside-pointer close; `aria-expanded`, `role="tooltip"`, `aria-describedby`; `text` vs projected content; `wide` / `xl` / `align`; the trigger's 44px hit area under `(pointer: coarse), (max-width: 1023px)`. Positioning still comes from the trigger's viewport rect, now correct because the top layer's containing block *is* the viewport.

Added: the popover is clamped inside the viewport with an 8px margin (it flips above the trigger when there is no room below, and shifts horizontally rather than run off either edge), so `align="left"` workarounds become unnecessary; the input is kept for compatibility. The UA popover styles (`inset`, `margin`, border, background) are reset so the existing `.pop` / `.elev-overlay` look is unchanged.

`.sb-lift` keeps its hover lift. No other overlay component changes in this spec.

**Tests (`hint.spec.ts`):** opens on hover, focus and tap; pin survives mouseleave; Escape and outside pointer close; the popover element carries `popover` and is `:popover-open` when open; with a `transform` on an ancestor the popover's rect stays at trigger-bottom + 4px (the regression); viewport clamping at the right, left and bottom edges; empty projected content still renders a trigger with its label.

## A2. Layout audit: `hint` check

`frontend/scripts/layout-audit-lib.mjs` gains an eighth check, `hint`, added to `CHECKS`. On every route and tab, at every width, the audit opens each visible `sb-hint` trigger (hover at 1440; tap at 390 and 768) and fails when the opened popover is not (a) inside the viewport and (b) the topmost element at both its centre and its top-left + 8px. Findings name the route, width and trigger `aria-label`. Allow-list rules are unchanged (a `hint` finding is fixed, never allowed). The probe used for this spec's evidence is the reference behaviour.

**Tests:** the audit library's unit tests cover the new check's pass and fail decisions on a fixture page (one clipped popover, one visible).

## A3. Explanatory `title` → `sb-hint`

Every `title=` / `[title]=` in `frontend/src/app` is classified once, in the plan, into:

- **Explanation** (a definition, a caveat, why a value is absent): becomes an `sb-hint` beside the thing it explains, or visible text where it is short enough to sit inline.
- **Echo** (repeats a truncated cell value or a full name that the row drawer or detail view also shows): stays `title`.
- **Control name** (an icon-only button): becomes `aria-label` plus `title` kept for desktop hover, since the name is not explanation.

A new spec test (`frontend/src/app/ui/title-usage.spec.ts`) scans the source and fails on any `title` binding not in an allow-list of echo and control-name sites, so new explanation cannot be hidden in a `title` again. The allow-list lives beside the test with one line per site saying which class it is.

## A4. Content audit: every hint and chart tooltip says what the number is

For each `sb-hint` text and each chart tooltip (`chart-tooltip.ts` consumers), the plan records the claim it makes and the code that computes the figure, then fixes whichever is wrong. Known findings going in (B7, B8 below) are fixed under B; A4 covers the rest. Specifically checked: the population (all closed, range-scoped, open book), the sample size it names, the unit (R, %, account currency), and that an "all-time" hint is not on a range-scoped figure or vice versa. The audit's record is a table in the plan's final task notes, one row per hint: route, label, verdict (`correct` / `fixed text` / `fixed figure`).

# Phase B — Figures and labels

Each item: the confirmed symptom, the acceptance rule, the test.

## B1. Dashboard lifecycle tab counts and stuck Trading performance

**Symptom.** `/api/v1/dashboard` returns `lifecycle: {ACTIVE: 8, ...}`; at 1440 and 768 the Open positions tabs read "Open 0" while 8 rows render, and the Trading performance panel shows its skeleton after 6s. At 390 both are correct. The tab counts come from `store.todayLifecycle()` (`dashboard.ts` `lifecycleCounts`), so the today-scoped request is the first suspect.

**Acceptance.** Root cause found and stated in the commit. Tab counts equal the API's lifecycle counts at all three widths after load; Trading performance renders data or `sb-async`'s error with Retry, never an indefinite skeleton.

**Tests.** Store spec for the today request's lifecycle; component spec that the tab counts follow the store at desktop and compact viewports.

## B2. Trades "All" rows renders 10

**Symptom.** Rows = All, label "1–10 of 1272 (capped)". `ui-design.md` § Tables and pagers: "All" asks the API for its 200-row cap.

**Acceptance.** "All" requests `per_page=200` and renders up to 200 rows with the `(capped)` label when the total is larger; a saved "All" restored from prefs behaves the same.

**Tests.** Pagination/store spec: choice "All" → request `per_page=200`; restored pref "All" → same.

## B3. Partial-exit legs look like duplicate trades

**Symptom.** A partially exited trade lists as two rows with the same id prefix and different P&L (API: same `id`, `leg_index` 0 and 1). Data is correct; the table does not say which row is which.

**Acceptance.** A leg row shows a leg label beside its id: `leg_index` 0 → "TP1", the last leg → "Runner" (intermediate legs "TP2", …). The existing icon on the leg row becomes an `sb-hint` explaining that one plan exited in parts. Applies wherever leg rows render (Trades table, its compact rows and drawer).

**Tests.** Label mapping for 1, 2 and 3 legs; a single-leg trade shows no label.

## B4. Fractional shares rounded to whole

**Symptom.** `/api/v1/risk` `positions[].shares` = 2.72; Exposure by position shows 3.

**Acceptance.** Shares render with up to 2 decimals, trailing zeros dropped (2.72, 3, 0.5), via one shared formatter used on Risk, trade detail and the row drawer. The column total uses the same formatter.

**Tests.** Formatter cases: integer, one and two decimals, rounding at the third decimal, zero, null → em dash.

## B5. Tiny risk percentages read as zero; total has no unit

**Symptom.** Per-row `risk_pct` 0.002 renders "0.00%"; the column total renders "0.02" with no unit.

**Acceptance.** One percentage formatter for heat, rows and totals: a non-zero value below 0.01 renders "<0.01%" with the exact value available in an `sb-hint` or the drawer; totals carry "%". Exact zero renders "0.00%".

**Tests.** Formatter: 0, 0.002, 0.01, 1.234, negative, null.

## B6. Sector heat empty with eight open positions

**Symptom.** `/api/v1/risk` `sector_heat: []` while 8 positions are open. `swingbot/core/edge/portfolio_state.py` builds it from `universe.sector_map(SCAN_UNIVERSE)` and swallows every exception into `{}`, so a missing map and a real zero are indistinguishable, and the page says "No sector exposure".

**Acceptance.** (1) The cause is established read-only on production (`prod-inspector`) before any change. (2) The swallowed exceptions log at warning with the exception text. (3) The open tickers resolve to a sector, or the plan records why they cannot. (4) The API distinguishes "no sector data for N open positions" from "no exposure" (an added field, documented in the endpoint's response shape), and the panel renders the two differently.

**Tests.** Backend: sector heat with a populated map, an empty map, and a map missing some tickers; the endpoint reports the unmapped count. Frontend: both empty states render their own text.

## B7. Unit toggle shows "$" on a € account

**Symptom.** Analytics' R / % / $ toggle shows "$"; the account currency is €.

**Acceptance.** The money option's label is the account currency symbol from `connection.currency()` everywhere the toggle appears; its value key is unchanged so saved preferences survive.

**Tests.** Toggle renders €, $ and £ for the three currencies; the stored value is the same key.

## B8. Risk vs Analytics: same names, different figures

**Symptom.** Risk shows Sharpe (R) −0.07 and Max drawdown (R) −123.17R; Analytics shows Sharpe −1.62 and Max drawdown −120.66R. Both are correct for different populations; only a 10px footnote says so.

**Acceptance.** Each such tile's label names its basis (e.g. "Sharpe · per-trade R, all closed", "Sharpe · annualised, selected range") and carries an `sb-hint` with the definition, population and N. The footnote is removed once the labels carry it.

**Tests.** Tile labels and hint text present on both pages.

## Verification

- `testrun.py changed` while iterating; the plan's final task runs the full suite once.
- The layout audit, including the new `hint` check, exits 0 at 390, 768 and 1440 against a local replica (`/replicate-prod-db`, built bundle, `.env` credentials) before merge.
- After deploy, the probe is re-run against production: 0 hints not visible at all three widths.

## Parallelisation

- **A1 first, alone** — A2's check and A3's conversions both depend on a hint that can actually be seen.
- **Then in parallel:** A2 (audit script) · A3 (title sweep) · B1 · B2 · B3 · B4+B5 (one shared formatter module, one group) · B6 (backend, independent of the frontend) · B7.
- **B8 after A1** (it adds hints) and may run beside the group above.
- **A4 last before the full suite** — it audits hint text, including those A3 and B8 add.
