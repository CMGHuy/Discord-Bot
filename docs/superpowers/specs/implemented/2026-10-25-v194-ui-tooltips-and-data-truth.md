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

Robustness rules (panel, staff-engineer):

- **Feature detection.** When `HTMLElement.prototype.showPopover` is absent, the hint keeps today's `position: fixed` path, so an old browser loses only the clipped cases, never every hint.
- **Guarded calls.** `showPopover()` is called only when the element is connected and not already open; `hidePopover()` only when open (both throw `InvalidStateError` otherwise on some engines).
- **Host close.** A hint inside a modal `<dialog>` host (`sb-drawer`, `layout.ts:464`; `sb-confirm-dialog`, `confirm-dialog.ts`) hides when that dialog starts closing, not when it is removed — a pinned manual popover is not hidden by its ancestor dialog closing, so without this it would stay painted through the drawer's exit animation. B3 and B5 put hints in the drawer, so this case is real.
- The `[hidden]` binding on `.pop` (`hint.ts:61`) is removed; the popover's own UA display rule replaces it.

**Test environment.** jsdom (the unit-test DOM, `frontend/package.json`) has no Popover API and no layout. A popover polyfill (`showPopover` / `hidePopover` / `togglePopover` and the `:popover-open` state as a toggled attribute) goes into the **global** test setup (`src/test-setup.ts`), not per spec as `testing/dialog-polyfill.ts` is, because every `sb-panel` heading renders an `sb-hint` and any page spec that hovers it would otherwise throw.

**Tests (`hint.spec.ts`, behaviour only):** opens on hover, focus and tap; pin survives mouseleave; Escape and outside pointer close; the popover element carries `popover` and is shown/hidden through the API when open changes; no double show or hide; the fallback path when the API is absent; a hint in a closing dialog host hides. **Geometry** (the ancestor-transform regression and viewport clamping) cannot be measured in jsdom and is proven by A2's browser check, not asserted in unit tests.

## A2. Layout audit: `hint` check

`frontend/scripts/layout-audit-lib.mjs` gains an eighth check, `hint`, added to `CHECKS`. On every route and tab, at every width, the audit opens each visible `sb-hint` trigger (hover at 1440; tap at 390 and 768) and fails when the opened popover is not (a) inside the viewport and (b) the topmost element at both its centre and its top-left + 8px. Findings name the route, width and trigger `aria-label`. Allow-list rules are unchanged (a `hint` finding is fixed, never allowed). The ad-hoc probe that produced this spec's evidence was never committed; **from this spec on, the `hint` check is the probe** — the post-deploy check below runs it, nothing else.

**Tests:** `layout-audit-lib.test.mjs` is the pure, browser-free half (`node --test`). The decision is a pure function, geometry in and verdict out, the way `vcenterGeometry` already is: popover rect, viewport size and the elements found at the sample points → pass or fail with a reason. Its cases: visible, clipped by an ancestor (topmost element not inside the popover), off-screen, zero-size. The existing `CHECKS` assertion grows to eight in the same task. The browser half is proven by the replica audit run under Verification.

## A3. Explanatory `title` → `sb-hint`

Every `title=` / `[title]=` in `frontend/src/app` is classified once, in the plan, into:

- **Explanation** (a definition, a caveat, why a value is absent): becomes an `sb-hint` beside the thing it explains, or visible text where it is short enough to sit inline.
- **Echo** (repeats a truncated cell value or a full name that the row drawer or detail view also shows): stays `title`.
- **Control name** (an icon-only button): becomes `aria-label` plus `title` kept for desktop hover, since the name is not explanation.

A new spec test (`frontend/src/app/ui/title-usage.spec.ts`) scans the source and fails on any `title` binding not in an allow-list of echo and control-name sites, so new explanation cannot be hidden in a `title` again. The allow-list lives beside the test with one line per site saying which class it is.

Copy rules for converted text (panel, financial-advisor): a win-rate hint never stands alone — it names ExpR and N beside it (`edge-priorities.md`); no hint reads as a recommendation ("take", "safe", "buy").

## A4. Content audit: every hint and chart tooltip says what the number is

For each `sb-hint` text and each chart tooltip (`chart-tooltip.ts` consumers), the plan records the claim it makes and the code that computes the figure, then fixes whichever is wrong. Known findings going in (B7, B8 below) are fixed under B; A4 covers the rest. Specifically checked:

- the population (all closed, range-scoped, open book; plans vs legs);
- the sample size it names;
- the unit (R, %, account currency), and for money that the values are **actually in the account currency**, not USD relabelled (instruments are USD-quoted);
- that an "all-time" hint is not on a range-scoped figure or vice versa;
- whether the figure is gross or net of commissions and slippage, pre-tax, and paper (simulated fills) — a performance figure states all three.

The audit's record is a table in the plan's final task notes, one row per hint: route, label, verdict (`correct` / `caveat added` — figure right but a population, N or cost caveat was missing / `fixed text` / `fixed figure`).

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

**Acceptance.** A leg row shows **"Leg N of M"** beside its id — the vocabulary Calendar already uses (`calendar.ts:291`, `day-trade-card.ts:17`), so one trade is never named two ways. Not "TP1"/"Runner": `leg_index` follows the order legs realised (`dashboard.ts:983-987`), so leg 1 may be a stop-out and the last leg may exit at the stop or by timeout. Where the leg's recorded exit reason is available, it follows the label ("Leg 1 of 2 · target", "Leg 2 of 2 · stop"); where it is not, the label stands alone.

The existing icon on the leg row becomes an `sb-hint` that says: these rows are parts of **one plan**, each row's P&L is that part's share, and win rate and N count **plans, not legs**. The plan states, and tests, whether the Trades page's row total counts legs or plans, and the range label says which.

Applies wherever leg rows render: Trades (table, compact rows, drawer), the Dashboard positions table (`dashboard.ts:708`, `:990-992`), and Calendar (already "Leg N of M"; it gets the same hint).

**Tests.** Label for 1, 2 and 3 legs, with and without an exit reason; a single-leg trade shows no label; the hint text names plans-not-legs.

## B4. Fractional shares rounded to whole

**Symptom.** `/api/v1/risk` `positions[].shares` = 2.72; Exposure by position shows 3.

**Acceptance.** Shares render with up to 2 decimals, trailing zeros dropped (2.72, 3, 0.5), via one shared formatter used on Risk, trade detail and the row drawer. The column total is the **sum of the unrounded values**, then formatted. The shares column's hint says the count is the paper book's size, computed unrounded under the 2% dollar-risk cap; a broker may fill whole shares or another fraction.

**Tests.** Formatter cases: integer, one and two decimals, rounding at the third decimal, zero, null → em dash.

## B5. Tiny risk percentages read as zero; total has no unit

**Symptom.** Per-row `risk_pct` 0.002 renders "0.00%"; the column total renders "0.02" with no unit.

**Acceptance.** One percentage formatter for heat, rows and totals: a non-zero value below 0.01 renders "<0.01%" with the exact value available in an `sb-hint` or the drawer; totals carry "%". Exact zero renders "0.00%". A total is the sum of unrounded values, then formatted, so rows and total reconcile; when rounded rows visibly do not add up to the total, the total's hint says totals use unrounded values.

**Tests.** Formatter: 0, 0.002, 0.01, 1.234, negative, null.

## B6. Sector heat empty with eight open positions

**Symptom.** `/api/v1/risk` `sector_heat: []` while 8 positions are open. `swingbot/core/edge/portfolio_state.py` builds it from `universe.sector_map(SCAN_UNIVERSE)` and swallows every exception into `{}`, so a missing map and a real zero are indistinguishable, and the page says "No sector exposure".

**Acceptance.**

1. The cause is established read-only on production (`prod-inspector`) before any change.
2. The swallowed exceptions log at warning with the exception text.
3. **The fix stays on the read side.** `universe.sector_map(SCAN_UNIVERSE)` and the universe data behind it also feed the walk-forward replay's sector cap (`swingbot/core/backtesting/backtest_wf.py:427,545`) and the weekly risk report (`swingbot/core/tracking/retrospective.py:305,762`). Changing that data changes backtest results, which this spec excludes. If the cause is missing universe data, this spec ships only (2) and (4) and records the cause; the data fix becomes its own spec, reviewed by quant-engineer.
4. The API distinguishes "no sector data for N open positions" from "no exposure" through an added `unmapped_count` field. This is a response-shape change, not a stored record, so `schema-evolution.md` does not apply. It is recorded in the endpoint docstring (`swingbot/admin/api_v1/risk.py`, around 359–405) and the TypeScript interface (`frontend/src/app/api/models.ts`). The value is cached with `collect_portfolio_state` (`risk.py` `_cached`). Its other consumer, `!growth` (`swingbot/commands/growth.py`), is checked to still render.
5. When sector data is missing, the panel shows a visible banner — "Sector concentration cannot be assessed: no sector data for N of M open positions" — never a reassuring zero, a blank grid or "No sector exposure".

**Tests.** Backend: sector heat with a populated map, an empty map, and a map missing some tickers; the endpoint reports the unmapped count; `!growth` output is unchanged for a populated map. Frontend: the banner and the true-zero state render their own text.

## B7. Unit toggle shows "$" on a € account

**Symptom.** Analytics' R / % / $ toggle shows "$"; the account currency is €.

**Finding (plan, 2026-10-25).** No FX conversion exists anywhere in `swingbot/`: `realized_pnl_amount` is `shares × (exit − entry)` in each instrument's quote currency (settled in `swingbot/core/tracking/performance.py`, leg rows recomputed in `swingbot/admin/api_v1/trades.py`), and `CURRENCY_SYMBOL` only picks the symbol. Every money figure on a € account is therefore USD labelled €.

**Decision (partner, 2026-10-25, after the finding).** Add the FX conversion in v194, rather than keep an honest "$".

**Acceptance.**

- **Rate source.** yfinance FX pairs (e.g. `EURUSD=X`) daily close, fetched through the shared daily-bar path so they land in the existing OHLCV cache (`known-traps.md`: no third cache). No paid service.
- **Point in time.** Each leg converts at the rate on its own exit date; when that day has no bar, the last prior trading day's close.
- **Per instrument.** The quote currency is the ticker's own (a Euronext ticker is already EUR); same currency as the account → identity, no fetch. A USD account converts nothing.
- **Once, server-side.** Every money figure the admin API serves — trade and leg rows, dashboard P&L, Analytics sums and equity, Calendar, Risk's max-drawdown money equivalent (B8) — is in the account currency. The frontend keeps `connection.currency()` as the symbol everywhere, the Analytics money toggle included (matching Calendar, `calendar.ts:494`); its value key is unchanged, so saved preferences survive.
- **A missing rate is visible.** A row without a rate carries no converted amount and a flag; sums report how many rows were left out; the page shows a caveat naming the count. Never a silent 1.0.
- **Trading unchanged.** The stored `realized_pnl_amount` stays in quote currency: it also feeds the account balance (`swingbot/core/planning/account.py`), hence 2% sizing, the kill-switch drawdown and the growth path, which this spec excludes. The conversion is read-side only, so no stored record changes and `schema-evolution.md` does not apply. Discord commands keep today's figures (follow-up). *Partner confirmed display-only, 2026-10-25.*

**Tests.** Rate lookup: same currency → 1.0 with no fetch, exit-date close, prior-day fallback, missing → `None`. Conversion: a USD leg on a € account converts at its exit date's rate; a EUR-quoted leg is unchanged; a missing rate yields a flagged row and a counted sum, never 1.0. Toggle renders €, $ and £ for the three currencies; the stored value is the same key; the caveat renders when rows were left out.

## B8. Risk vs Analytics: same names, different figures

**Symptom.** Risk shows Sharpe (R) −0.07 and Max drawdown (R) −123.17R; Analytics shows Sharpe −1.62 and Max drawdown −120.66R. Both are correct for different populations; only a 10px footnote says so.

**Acceptance.**

- **Basis in the label, mandatory on both pages.** Every Sharpe and max-drawdown tile on Risk (`risk.ts:755-756`, today "Sharpe (R)" / "Max drawdown (R)") and on Analytics names its basis in the label: "Sharpe · per-trade R, all closed" and "Sharpe · annualised, selected range". The two never read as the same quantity.
- **Hint per tile.** Each tile carries an `sb-hint` stating the definition, the population, the closed-trade N (the tile's existing `sample`), and that the figure is **paper, gross of commissions and slippage, and pre-tax**, unless A4 finds the computation nets any of them.
- **Max drawdown in money too.** Max drawdown shows an account-currency equivalent next to the R figure on both pages. Analytics already shows one under its tile; Risk gains it. If the plan finds the R-to-currency conversion not well defined for the all-closed population, it records why and shows the percent of account instead.
- The footnote is removed once the labels carry it.

**Tests.** Tile labels, the money equivalent, and hint text (including the paper / gross / pre-tax caveat) present on both pages.

## Verification

- `testrun.py changed` while iterating; the plan's final task runs the full suite once.
- The layout audit, including the new `hint` check, exits 0 at 390, 768 and 1440 against a local replica (`/replicate-prod-db`, built bundle, `.env` credentials) before merge.
- After deploy, the layout audit's `hint` check is run against production at all three widths: 0 findings.

## Parallelisation

Grouped by the files they edit, not only by topic (panel, staff-engineer):

- **A1 first, alone.** Every later item either adds hints or checks them.
- **Then in parallel, file-disjoint:**
  - A2 (`frontend/scripts/` only);
  - B1 (dashboard store and tabs);
  - B2 (pagination and Trades store);
  - B7 (FX rate provider, then the read-side conversion seam, then the Analytics toggle and caveat; sequential within the group);
  - **Risk group** — B4+B5 (the shared formatter), the B6 frontend banner and B8's tiles, sequential within the group because all three edit `workspaces/risk/risk.ts`;
  - the B6 backend (`swingbot/`, independent of the frontend).
- **B3 after B1.** Both touch `dashboard.ts`.
- **A3 after B3, B8 and the Risk group.** A3 sweeps `title` sites across `frontend/src/app`. B3 converts the leg-row `partialOpenTitle` site (`dashboard.ts:988` and its twin in `trades.ts`), and B8 adds hints to the same tiles. Running A3 alongside them would make every branch edit its allow-list file at once.
- **A4 last before the full suite.** It audits hint text, including the hints A3, B3 and B8 add.

## Panel review

Run 2026-10-25 on `2a0cc8bd`: staff-engineer (opus), financial-advisor (sonnet).

**BLOCKING**

- financial-advisor 1: B8 left pre-cost/pre-tax unlabelled and drawdown only in R -- applied (B8: paper/gross/pre-tax caveat in each hint; max drawdown in account currency, or percent of account with the reason recorded).

**ADVISORY**

- staff-engineer 1: jsdom has no Popover API and no layout -- applied (global polyfill in test-setup; geometry proven by A2, not unit tests).
- staff-engineer 2: pinned popover outlives a closing dialog host; unguarded `showPopover`; `[hidden]` conflict -- applied (A1 robustness rules).
- staff-engineer 3: the parallel group shares files (`risk.ts`, `dashboard.ts`, A3's allow-list) -- applied (file-grouped Parallelisation; A3 serialised).
- staff-engineer 4: the B6 fix point feeds the backtest and retrospective -- applied (read-side only; a data fix becomes its own spec).
- staff-engineer 5: B6 shape record unnamed; cache and `!growth` consumer -- applied (docstring + `models.ts` named, `!growth` checked).
- staff-engineer 6: A2 test plan does not fit the pure `node --test` file -- applied (pure geometry decision function; `CHECKS` assertion updated).
- staff-engineer 7: the probe is not committed -- applied (the `hint` check is the probe from now on).
- staff-engineer 8: B3 misses the Dashboard and Calendar leg surfaces; TP1 assumption -- applied (all three surfaces; "Leg N of M" vocabulary).
- staff-engineer 9: no fallback without the Popover API -- applied (feature detection keeps today's path).
- financial-advisor 2: basis labels mandatory on both pages, N named -- applied (B8).
- financial-advisor 3: TP1/Runner by `leg_index` is unsafe -- applied (B3: "Leg N of M" plus exit reason where recorded).
- financial-advisor 4: leg hint must say plans-not-legs for win rate and N -- applied (B3).
- financial-advisor 5: totals must reconcile with rounded rows -- applied (B4, B5: sum of unrounded values; shares hint).
- financial-advisor 6: missing sector data must show a banner, not a reassuring zero -- applied (B6 item 5).
- financial-advisor 7: verify money is truly in the account currency before relabelling -- applied (B7 verification first; A4 unit check).
- financial-advisor 8: A4 needs gross/net/pre-tax/paper and a "caveat added" verdict -- applied (A4).
- financial-advisor 9: win-rate hints never alone; no recommendation wording -- applied (A3 copy rules).
