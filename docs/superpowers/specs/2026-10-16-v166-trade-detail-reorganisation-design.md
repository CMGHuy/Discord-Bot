# v166 — Trade detail reorganisation: outcome header, four tabs, gap-free responsive grid

**Version:** ui 1.24.1 · bot 2.5.2 (at writing)
**Bump:** ui minor; bot none — every admin user gets a different trade page (new header, four tabs instead of five, new fields shown). The API and the Discord bot are untouched.
**Edge:** none (integrity) — a clearer view of one trade. It changes no signal, threshold, plan, sizing or badge.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, veteran-trader
**Status:** spec written 2026-10-16 from a brainstorm with the partner (structure and design approved in chat), after a Playwright pass over production trade `f48c80e2` (SPCX, closed, two legs) at 1440 / 820 / 390 px.

## Why

The partner opened a closed trade on bomeo-capital.com and asked for the page to be reorganised and to show more of the trade. The pass over all five tabs (`frontend/src/app/workspaces/trades/trade-detail.ts`) found:

1. **The outcome is missing.** On a closed trade the header says only `CLOSED`. The trade's R (`r_multiple`, 1.83 for SPCX), its exit price and its exit reason appear nowhere. The P&L % sits in a card called "Opened", and the $ amount sits on the Live tab.
2. **The Live tab mislabels a closed trade.** It shows `Price —` and calls the realised +3.20 % "Unrealised" (`trade-detail.ts:327`). Its only action, Delete, sits alone in a card, which takes a whole row at 390 px.
3. **The levels are shown three times.** Entry, stop and targets appear in Plan → Levels, Plan → Levels & methods (its number row) and Live → Stop to target. "If it gets there" repeats the `🔀` line of "Why this trade". "Opened" repeats the timeline's dates.
4. **Two tabs are nearly empty.** For SPCX, Strategy is one sentence ("The registry has no entry for Volume Profile HVN.") and Notes is only a textarea.
5. **The layout leaves holes.** `.panels` is `repeat(auto-fit, minmax(220px, 1fr))` with `align-items: start` (`trade-detail.ts:659`). Short cards (Per share, If it gets there) sit next to tall ones, and at 820 px the last row is two cards and an empty slot.
6. **The API sends fields the page never shows:** `badge`, `confidence_score`, `quality_score`, `detail.expires_on`, `detail.time_exit_on`, `detail.hold_cap_bars` and `detail.trail_atr_mult` (for SPCX: badge WEAK, confidence 90, quality 56).

## Design

### 1. Header — identity line + outcome strip (every tab)

**Identity line:** back link, ticker, direction arrow (↑ bullish / ↓ bearish, replacing the Per share "Direction" row), status indicator, then the existing chips (horizon, strategy, tier, Lv, cohort) plus **the badge chip** (new; `trade.badge`, no chip when null). The trade id stays as small mono text. **The action buttons move to the right end of this line** (`availableActions(status)`, same confirm dialog, Delete keeps `variant="danger"`). The Actions card is gone. On a narrow screen the buttons wrap under the chips and never take a row of their own.

**Outcome strip:** one row of KPI tiles. Which tiles appear depends on the status group:

| Status group | Tiles (label: value) |
|---|---|
| Closed (`CLOSED`, and any status with `exit_price` set) | **Result:** `r_multiple` as R, signed and tinted · **P&L:** `realized_pnl_amount` + `pnl_pct` · **Entry → exit:** entry → average exit · **Held:** `held_hours` · **Exit:** exit-reason label |
| Open (`ACTIVE`, `PARTIAL`) | **Price:** `current_price` + the "delayed" flag · **Unrealised:** `pnl_pct` + amount · **Progress:** the existing stop→target `sb-status-indicator` · **Held** · for PARTIAL, **Banked:** fraction @ price, R |
| Pending (`PENDING`) | **Trigger:** `trigger_price` · **Distance:** `distance_to_trigger_r` as R · **Expires:** `detail.expires_on` (or bars left) · **Created:** `created_at` |
| Cancelled / expired | **Status:** cancelled or expired · **Created** · **Trigger** · **Never filled** (plain text) |

- **Average exit** = Σ `fraction × exit_price` over `detail.legs` when there are legs, else `exit_price`. For SPCX: 0.5 × 147.54 + 0.5 × 145.56 = 146.55. `r_multiple` is already the fraction-weighted blend (0.5 × 2.23 + 0.5 × 1.43 = 1.83, matching the API), so the Result tile shows it directly and never re-derives it.
- **Exit-reason label:** the last leg's `reason`, else the last `status_history` reason, mapped through one frontend table: `tp1` → "TP1", `tp1_runner_be`/`runner_be` → "Runner at breakeven", `tp1_runner_tp2`/`runner_tp2` → "Runner at T2", `runner_trail` → "Runner trailed", `stop`/`loss` → "Stop", `scratch` → "Scratch", `timeout`/`time_exit`/`auto (near-tp stall)` → "Time exit", `reversed` → "Reversed". Anything else shows the raw text. A two-leg close reads "TP1 + Runner at breakeven". The table mirrors `metrics.EXIT_REASONS` and `_EXIT_REASON_ALIASES` (`swingbot/core/analytics/metrics.py:27-49`), and a spec test pins one example per key.
- **Layout:** `display: flex; flex-wrap: wrap` with tiles at `flex: 1 1 120px`. Flex (not grid `auto-fit`) is what makes a short last row stretch instead of leaving a gap: 5 across on desktop, 3 + 2 on a tablet, 2 + 2 + 1 on a phone, with the last tile full width.
- The arrival banner (v151) stays above the identity line, unchanged.

### 2. Tabs

`Overview · Why · Chart · Journal` (ids `overview`, `why`, `chart`, `journal`). **Old `?tab=` values keep working:** `plan` and `live` → `overview`, `notes` → `journal`, `strategy` → `why`. Unknown values still fall back to the default, `overview`, which drops the query parameter, as `plan` does today. `chart` keeps its id, because the v165 day page links to `?tab=chart`.

### 3. Overview tab (replaces Plan and Live)

Three cards:

- **Plan:** one table with columns level · price · % from entry. Rows: Order (at market / limit / stop, from `entry_type`), Trigger (when it differs from entry), Entry, Stop (or "Trailing stop" on PARTIAL, using today's `stopLabel()` rule), Target 1, Target 2, Acceptance. Under it, one line: `R:R 2.18 · risk 2.49 / reward 5.42 per share`. The stop is tinted negative and the targets positive, as now. This replaces Levels, Per share, Stop to target and the number row of Levels & methods. The "Paper plan — this page places no orders" footnote stays.
- **Position:** shares, deployed (`position_value`), sizing mode, gap risk p90 with the fragile chip, working stop, TP1 closes %, breakeven at, trail ATR × (`detail.trail_atr_mult`, new), expires on / time exit on / hold cap (new; each row hidden when null). The "Position size is snapshotted…" sentence shows only when the sizing snapshot is absent (`sizing_mode` null), not on every trade.
- **Outcome:** the scale-out legs (fraction, exit price, R, reason label) above the timeline (`sb-outcome-path`, unchanged inputs). An open trade shows the timeline so far.

**Dropped:** If it gets there (the Why tab's explanation already carries the continue/reverse line), Opened (dates are on the timeline, P&L is in the strip), and Origin (it moves to the identity line as a muted `origin` tag, but only when it is not `plan`).

### 4. Why tab (the reasoning, unchanged in substance)

Cards, in reading order:

- **Why this trade:** the explanation.
- **Scores (new):** Confidence `confidence_score` · Lv and Quality `quality_score`, each with its 0–100 bar. For SPCX: 90 · Lv5 and 56. The badge stays a header chip only, not repeated here.
- **Level sources:** Target / Stop / Target 2 / Confirmed by, as lists only (the numbers live on Overview).
- **Confidence & quality breakdown:** today's panel, unchanged.
- **Gate margins.**
- **Calendar + Strategy record:** today's calendar rows, then today's Strategy-tab `dl` (OOS/live sample, win rate, expectancy, delta, window, decayed warning) or its one-line "no registry entry" / "no strategy recorded" state.

**How it reuses `sb-why-panel` without changing the plan page:** each `WhyPanel` section is already its own `sb-panel` (`why-panel.ts:29-117`), selected by the `sections` input. The Why tab therefore renders one `<sb-why-panel [sections]="['x']">` per grid cell. One **additive** input, `showLevelNumbers` (default `true`, today's output), lets the trade page hide the number row of the levels section. The plan page passes nothing and renders byte-identically. The registry is fetched on first arrival at the Why tab (today's lazy effect, retargeted from `strategy` to `why`). The legacy no-detail note and `ABSENT_SECTIONS` behave as now.

### 5. Chart tab

Unchanged.

### 6. Journal tab (was Notes)

Excursions (MFE/MAE chips), tags and auto-lesson, then the note field with today's autosave and its states. The "not journaled yet" note for open positions stays.

### 7. Responsive card grid (every tab)

One grid rule replaces `.panels`:

- The grid is a **container** (`container-type: inline-size`), so it responds to the width actually available (sidebar open or closed), not to device detection. Dragging the window narrower reflows it live.
- Columns: **3 at ≥ 1100 px, 2 at 700–1099 px, 1 below 700 px** of container width.
- Each tab places its cards with `grid-template-areas` per breakpoint, chosen so that no row ends holding one narrow card:
  - **Overview:** three columns `plan position outcome`. Two columns `plan position` / `outcome outcome`. One column, stacked.
  - **Why:** three columns `why why scores` / `sources sources sources` / `breakdown breakdown breakdown` / `gates gates context`. Two columns `why why` / `scores context` / `sources sources` / `breakdown breakdown` / `gates gates`. One column in reading order. (`context` = Calendar + Strategy record.) A card whose section is absent (e.g. no explanation on a legacy record) leaves its area empty, so the area map for that case widens its neighbour: `scores` spans the row when `why` is absent.
- `align-items: stretch` within a row, so paired cards end level. Long content grows its card, and its neighbour stretches to match rather than leaving a hole.
- Inside a card, label/value lists (`dl`) flow into two columns when the card is ≥ 520 px wide (a container query on the card), so a full-width card on a tablet does not become one tall thin list.

**Acceptance (the partner's rule):** at 1440, 1024, 768 and 390 px, on a closed two-leg trade, an open/partial trade and a pending plan, no row contains a single card narrower than the full row while empty space sits beside it, and no page scrolls sideways.

## Edge cases

- **Legacy record without detail:** the strip still renders from the trade row; the Position rows that need detail are hidden; Why shows today's no-detail note plus gates/calendar (`ABSENT_SECTIONS`).
- **Closed with no legs:** average exit = `exit_price`; the exit label comes from `status_history`, else "—".
- **`r_multiple` null on a closed trade:** the Result tile shows "—", never a computed stand-in.
- **Stale price:** the "delayed" flag moves with the Price tile.
- **Single leg:** the Outcome card shows one leg row; the exit label has no "+".

## Testing

- `trade-detail.spec.ts`: the four tabs; the legacy `?tab=` mapping (each old id); strip tiles per status group; actions in the header (and no Actions card); badge chip; dropped cards absent; Scores card values; Strategy record under Why; registry lazy-load fires on `why`; `WhyPanel` with `showLevelNumbers=false` omits the number row, and by default keeps it.
- A pure-function spec for `averageExit(legs, exitPrice)` and `exitReasonLabel(legs, history)`, with the SPCX numbers (146.55; "TP1 + Runner at breakeven").
- The existing `why/*.spec.ts` and `plan-detail.spec.ts` stay green. `levels-block`, `if-it-gets-there` and `sizing-panel` are **kept**: the plan page imports all three (`plan-detail.ts:17-21`). The trade page simply stops using `if-it-gets-there`, and the new Plan and Position cards are new trade-page components.
- **Visual pass:** `node frontend/scripts/browse.mjs shots` at 1440, 1024, 768 and 390 px over a closed two-leg trade, an open or partial trade, and a pending plan, against a local `ng serve --port 4123`, with screenshots checked against the acceptance rule above. Production is re-shot after deploy.

## Out of scope

API or store changes (every field used is already in `/api/v1/trades/<id>`), the chart itself, the Trades list, and the plan detail page (`workspaces/plans/plan-detail.ts`), which imports `IfItGetsThere`, `LevelsBlock`, `OutcomePath`, `PlanChart`, `SizingPanel` and `WhyPanel` from `trades/why/` and must render exactly as before. The only shared change is `WhyPanel`'s additive `showLevelNumbers` input (default `true`), with a spec asserting that the default output is unchanged.
