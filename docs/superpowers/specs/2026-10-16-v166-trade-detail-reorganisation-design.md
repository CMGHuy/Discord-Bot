# v166 — Trade detail reorganisation: outcome header, four tabs, gap-free responsive grid

**Version:** ui 1.24.1 · bot 2.5.2 (at writing)
**Bump:** ui minor; bot none — every admin user gets a different trade page (new header, four tabs instead of five, new fields shown). The one API change is an additive field read only by the admin UI. The Discord bot is untouched.
**Edge:** none (integrity) — a clearer view of one trade. It changes no signal, threshold, plan, sizing or badge.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, veteran-trader
**Status:** spec written 2026-10-16 from a brainstorm with the partner (structure and design approved in chat), after a Playwright pass over production trade `f48c80e2` (SPCX, closed, two legs) at 1440 / 820 / 390 px. Revised the same day after the panel (see `## Panel review`).

## Why

The partner opened a closed trade on bomeo-capital.com and asked for the page to be reorganised and to show more of the trade. The pass over all five tabs (`frontend/src/app/workspaces/trades/trade-detail.ts`) found:

1. **The outcome is missing.** On a closed trade the header says only `CLOSED`. The trade's R (`r_multiple`, 1.83 for SPCX), its exit price and its exit reason appear nowhere. The P&L % sits in a card called "Opened", and the $ amount sits on the Live tab.
2. **The Live tab mislabels a closed trade.** It shows `Price —` and calls the realised +3.20 % "Unrealised" (`trade-detail.ts:327`). Its only action, Delete, sits alone in a card, which takes a whole row at 390 px.
3. **The levels are shown three times.** Entry, stop and targets appear in Plan → Levels, Plan → Levels & methods (its number row) and Live → Stop to target. "Opened" repeats the timeline's dates.
4. **Two tabs are nearly empty.** For SPCX, Strategy is one sentence ("The registry has no entry for Volume Profile HVN.") and Notes is only a textarea.
5. **The layout leaves holes.** `.panels` is `repeat(auto-fit, minmax(220px, 1fr))` with `align-items: start` (`trade-detail.ts:659`). Short cards (Per share, If it gets there) sit next to tall ones, and at 820 px the last row is two cards and an empty slot.
6. **The API sends fields the page never shows:** `badge`, `confidence_score`, `quality_score`, `detail.expires_on`, `detail.time_exit_on`, `detail.hold_cap_bars` and `detail.trail_atr_mult` (for SPCX: badge WEAK, confidence 90, quality 56).

## Design

### 1. Header — identity line + outcome strip (every tab)

**Identity line:**
- Back link, ticker, then the side as text (**Long** / **Short**, replacing the Per share "Direction" row), then the status indicator.
- The existing chips (horizon, strategy, tier, Lv, cohort), plus **the badge chip** (new; `trade.badge`, no chip when null).
- An **earnings chip** for open and pending trades when the earnings gate recorded a numeric days-to-earnings (`store.gates()` key `earnings`, e.g. "Earnings in 19d"). No chip when it is "not recorded".
- `origin` as a muted tag, only when it is not `plan`.
- The trade id as small mono text.
- **The action buttons sit at the right end of this line** (`availableActions(status)`, same confirm dialog, Delete keeps `variant="danger"`). The Actions card is gone. On a narrow screen the buttons wrap under the chips and never take a row of their own.

**Outcome strip:** one row of KPI tiles. **Status decides the group first**; `exit_price` is consulted only for a terminal status that is not `CLOSED`.

| Status group | Tiles (label: value · subline) |
|---|---|
| Closed (`CLOSED`; any other terminal status with `exit_price` set) | **Result:** `r_multiple` as R · subline "1R = $<shares × risk per share>" and, with two or more legs, the leg Rs ("+2.23R / +1.43R") · **P&L:** `realized_pnl_amount` · subline "`pnl_pct` on position" · **Entry → exit:** entry → average exit · **Held:** `held()` (prints days, e.g. "5d 3h 0m") · **Exit:** exit-reason label |
| Open (`ACTIVE`, `PARTIAL`) | **Price:** `current_price` · subline "to stop −x% · to T1 +y%" from the current price · **Unrealised:** amount · subline "`pnl_pct` on position" (on PARTIAL, labelled for whatever the API's `pnl_pct` covers, verified in the plan) · **Progress:** the existing stop→target `sb-status-indicator` · **Held** · subline "time exit in Nd" when `time_exit_on` is set · on PARTIAL, **Banked:** fraction @ price, R |
| Pending (`PENDING`) | **Trigger:** `trigger_price` · subline current price and % to trigger · **Distance:** `distance_to_trigger_r` as R · **Expires:** `detail.expires_on` as a date (bars left as the subline) · **Created:** `created_at` |
| Cancelled / expired | **Status:** cancelled or expired · subline: the last `status_history` reason when present (e.g. invalidated before trigger) · **Created** · **Trigger** · **Never filled** |

- **Costs and basis are stated on the tiles.** Every $ / % tile carries the caption "before fees & tax". The strip ends with one muted line, "Paper fills at plan levels; real fills and slippage may differ." The `%` is always labelled "on position", never left bare. It is price move on the entry value, not a share of the account.
- **Stale price:** the "delayed" flag sits on both the Price tile and the Unrealised tile, which are both marks to the last price.
- **Tint:** Result and P&L are tinted only outside a neutral band (|R| < 0.1 → no tint). The sign and the text always carry the meaning, not the colour alone.
- **Average exit** = Σ `fraction × exit_price` over `store.legs()` (which already prefers `legs_realized` over `legs`, `trade-detail.store.ts:383-389`). Legs whose `exit_price` is null are skipped and the remaining fractions renormalised. With no usable leg, use `exit_price`. For SPCX: 0.5 × 147.54 + 0.5 × 145.56 = 146.55. `r_multiple` is already the fraction-weighted blend (0.5 × 2.23 + 0.5 × 1.43 = 1.83, matching the API, measured against the original stop), so the Result tile shows it directly and never re-derives it.
- **Exit-reason label:** the last leg's `reason`, else the last `status_history` reason, mapped through one table in its own file, `workspaces/trades/exit-reasons.ts`:

  | Reason text | Label |
  |---|---|
  | `tp1` | TP1 |
  | `tp1_runner_be`, `runner_be` | Runner at breakeven |
  | `tp1_runner_tp2`, `runner_tp2` | Runner at T2 |
  | `runner_trail` | Runner trailed |
  | `stop`, `loss` | Stop |
  | `scratch` | Scratch |
  | `timeout`, `time_exit` | Time exit |
  | `auto (near-tp stall)`, `stall_exit` | Stall exit |
  | `reversed` | Reversed |
  | anything else | the raw text |

  A two-leg close reads "TP1 + Runner at breakeven". A "Stop" exit with `r_multiple` < −1.05 gets the suffix "(gapped)".
- **Drift check:** a pytest (`tests/admin/test_exit_reason_labels.py`) reads `exit-reasons.ts` and fails when any `metrics.EXIT_REASONS` name or `_EXIT_REASON_ALIASES` key (`swingbot/core/analytics/metrics.py:27-49`) is missing from it. The backend vocabulary owns the keys; the frontend owns only the wording.
- **Layout:** `display: flex; flex-wrap: wrap` with tiles at `flex: 1 1 120px`. Flex (not grid `auto-fit`) is what makes a short last row stretch instead of leaving a gap: 5 across on desktop, 3 + 2 on a tablet, 2 + 2 + 1 on a phone, with the last tile full width.
- The arrival banner (v151) stays above the identity line, unchanged.

### 2. Tabs

`Overview · Why · Chart · Journal` (ids `overview`, `why`, `chart`, `journal`).
- **Old `?tab=` values are rewritten in place** (`router.navigate` with `replaceUrl: true`): `plan` and `live` → no parameter (`overview` is the default), `notes` → `journal`, `strategy` → `why`.
- An unknown value renders Overview and is left in the URL, as today (`trade-detail.ts:898-901`).
- `chart` keeps its id, because the v165 day page links to `?tab=chart`. Nothing in the frontend, `swingbot/` or Discord links to the other old ids; Discord links go to `/plans/<id>`.

### 3. Overview tab (replaces Plan and Live)

Three cards:

- **Plan:** one table with columns level · price · % from entry.
  - Rows: Order, Trigger (when it differs from entry), Entry, Stop, Target 1, Target 2, Acceptance.
  - Order names the side and type so it can be entered as written: "Buy stop 142.20", "Sell limit …", or "Market (long)". Where the trigger differs from entry, a note says a gap through the trigger fills at the open, not at entry.
  - **Stop row:** the original risk stop. When the working stop differs (after TP1, or trailing), a second row "**Working stop 145.62** (was 139.52)" follows. On an ACTIVE or PARTIAL trade the card also shows one highlighted line: "**Move your resting stop to 145.62**". The original stop comes from a new API field `risk_stop` (below), and the working stop from `detail.working_stop`.
  - Under the table, one line: `R:R 2.18 · risk 2.49 / reward 5.42 per share`.
  - The stop is tinted negative and the targets positive, as now. The "Paper plan — this page places no orders" footnote stays.
- **Position:** shares, deployed (`position_value`), **$ at risk** (shares × risk per share; $17.43 for SPCX), sizing mode, gap risk p90 with the fragile chip, TP1 closes %, breakeven at, trail ATR × (`detail.trail_atr_mult`, new), and expires on / time exit on / hold cap (new; each row hidden when null). The "Position size is snapshotted…" sentence shows only when `sizing_mode` is null.
- **Outcome:**
  - **ACTIVE, PARTIAL and PENDING:** first the "Next" block, which is the existing `sb-if-it-gets-there` (continues past T1 → next stop T2; reverses → stop), then the timeline so far.
  - **Closed:** the scale-out legs (fraction, exit price, R, reason label) above the timeline (`sb-outcome-path`, unchanged inputs).

**Dropped:** the Opened card (dates are on the timeline, P&L is in the strip) and the Per share card (its rows moved into the Plan line and the identity line).

**API addition:** `/api/v1/trades/<id>` and the list rows gain `risk_stop`, the plan's original stop. It is the value the row builders already set as the transient `_risk_stop` (`swingbot/admin/api_v1/trades.py:316`, `:518`), which is popped at `:1035`; it is now published under a public name. Additive; no reader changes.

### 4. Why tab (the reasoning, unchanged in substance)

Cards, in reading order:

- **Why this trade:** the explanation.
- **Scores (new):** Confidence `confidence_score` · Lv, Quality `quality_score`, and the badge. Bars use a neutral tint. One muted line: "Scores rank setups; they are not win probabilities." For SPCX: 90 · Lv5, 56, WEAK.
- **Level sources:** Target / Stop / Target 2 / Confirmed by, as lists. This is a new trade-page card fed straight from the store (`targetSources()`, `stopSources()`, `target2Sources()`, `confirmedBy()`). It is hidden when all four are empty. `WhyPanel`'s `levels` section is not used on this page, so the shared component gains no input at all.
- **Confidence & quality breakdown:** `<sb-why-panel [sections]="['confidence']">`, unchanged.
- **Gate margins:** `<sb-why-panel [sections]="['gates']">`.
- **Context:** two panels stacked in one grid cell. First `<sb-why-panel [sections]="['calendar']">`, then the Strategy record panel: today's Strategy-tab `dl` (OOS/live sample, win rate, expectancy, delta, window, decayed warning) or its one-line "no registry entry" / "no strategy recorded" state.

Each `WhyPanel` section is already its own `sb-panel` (`why-panel.ts:29-117`), selected by the `sections` input, so one instance per grid cell reuses it unchanged. A cell's section list is intersected with the record's allowed sections (`ABSENT_SECTIONS` on a legacy record, `trade-detail.ts:54`).

The registry is fetched on first arrival at the Why tab (today's lazy effect, retargeted from `strategy` to `why`).

### 5. Chart tab

Unchanged.

### 6. Journal tab (was Notes)

Excursions (MFE/MAE chips), tags and auto-lesson, then the note field with today's autosave and its states. The "not journaled yet" note for open positions stays.

### 7. Responsive card grid (every tab)

One grid rule replaces `.panels`:

- The grid is a trade-page wrapper element with `container-type: inline-size`, so it responds to the width actually available (sidebar open or closed), not to device detection. Dragging the window narrower reflows it live. **No container is set on the shared `sb-panel`**: each card's own container query sits on a trade-page wrapper `div` around it, so no other admin page changes.
- Columns: **3 at ≥ 1100 px, 2 at 700–1099 px, 1 below 700 px** of container width.
- Each tab places its cards with `grid-template-areas` per breakpoint, chosen so that no row ends holding one narrow card:
  - **Overview:** three columns `plan position outcome`. Two columns `plan position` / `outcome outcome`. One column, stacked.
  - **Why:** three columns `why why scores` / `sources sources sources` / `breakdown breakdown breakdown` / `gates gates context`. Two columns `why why` / `scores context` / `sources sources` / `breakdown breakdown` / `gates gates`. One column in reading order.
- **Absent cards.** The area map is computed (`whyAreas()`), not static CSS. A card whose content would render nothing is not mounted, and its area is removed from the map:
  - explanation null;
  - no confidence points or factors (`why-panel.ts:51`);
  - all level sources empty;
  - a section excluded by `ABSENT_SECTIONS`.

  Its row partner widens to fill the row (e.g. `scores` spans the row when `why` is absent; `gates` spans the row when `context` is absent). A removed row leaves no doubled gap.
- `align-items: stretch` within a row, so paired cards end level. Long content grows its card, and its neighbour stretches to match rather than leaving a hole.
- Inside a card, label/value lists (`dl`) flow into two columns when the card's wrapper is ≥ 520 px wide.

**Acceptance (the partner's rule):** at 1440, 1024, 768 and 390 px, on a closed two-leg trade, an open/partial trade and a pending plan, no row contains a single card narrower than the full row while empty space sits beside it, and no page scrolls sideways.

## Edge cases

- **Legacy record without detail:** the strip still renders from the trade row; the Position rows that need detail are hidden; Why shows today's no-detail note plus gates/calendar (`ABSENT_SECTIONS`), with the area map collapsing around the absent cards.
- **Closed with no legs:** average exit = `exit_price`; the exit label comes from `status_history`, else "—".
- **A leg with `exit_price: null`** (fixture at `trade-detail.spec.ts:254`): skipped by the average, still listed in the Outcome card with "—".
- **`r_multiple` null on a closed trade:** the Result tile shows "—", never a computed stand-in; the "(gapped)" suffix is then never added.
- **`risk_stop` null** (a row built before this field): only the stop as `stop_loss` shows, and the working-stop row and the "move your resting stop" line are omitted.
- **Single leg:** the Outcome card shows one leg row; the exit label has no "+"; the Result subline shows no leg Rs.

## Testing

- **Rewrite the existing trade-detail cases.** About 15 cases in `trade-detail.spec.ts` (around `:155-290`, `:425`, `:457`, `:535-588`) mount `'plan'` or `'live'` and assert Live or Plan content (Unrealised, the Actions card, the levels block, `sb-if-it-gets-there`). The plan schedules their rewrite to the new tabs explicitly; each keeps its intent (e.g. the PARTIAL trailing-stop label becomes the working-stop row).
- **New cases in `trade-detail.spec.ts`:**
  - four tabs, and the legacy `?tab=` rewrite (each old id, `replaceUrl`);
  - strip tiles per status group, with status taking precedence over `exit_price`;
  - the cost caption and the "on position" label;
  - the stale flag on both price tiles;
  - neutral tint inside ±0.1R;
  - actions in the header and no Actions card;
  - badge and earnings chips, and Long/Short text;
  - the working-stop row and the "move your resting stop" line;
  - the Next block only on ACTIVE/PARTIAL/PENDING;
  - dropped cards absent;
  - Scores card values and note;
  - Strategy record under Why, and the registry lazy-load firing on `why`;
  - `whyAreas()` collapsing for each absent card.
- **Pure-function specs** for `averageExit(legs, exitPrice)`, including a null leg and no legs, and `exitReasonLabel(legs, history, r)`, including "(gapped)" and `stall_exit`. Both use the SPCX numbers: 146.55, and "TP1 + Runner at breakeven".
- **Backend:** `tests/admin/test_exit_reason_labels.py` (the drift check above), and an API test that `risk_stop` is present and equals the plan stop on a PARTIAL row whose `stop_loss` is the trailing stop. Each joins its existing suite in `tests/suites.toml`.
- **Shared gates the new files must pass:**
  - `ui/primitives.spec.ts`: the `.head` allowance (`:62-68`) is keyed to `trade-detail.ts` by file name, so moving the identity line or strip into a new component moves that allowlist entry with its required comment (`:120-133`). New cards must not redefine `.pos`, `.neg`, `.muted` or `.note`, and must contain no hex literals.
  - `ui/async-coverage.spec.ts`: `trade-detail.ts` keeps its `<sb-async` and gains no `class="loading"` (`:14-17`, `:84-90`).
- `why/*.spec.ts` and `plan-detail.spec.ts` stay green unchanged. `WhyPanel`, `LevelsBlock`, `IfItGetsThere`, `SizingPanel` and `OutcomePath` are not edited; the plan page imports all of them (`plan-detail.ts:17-22`).
- **Visual pass:** `node frontend/scripts/browse.mjs shots` at 1440, 1024, 768 and 390 px over a closed two-leg trade, an open or partial trade, and a pending plan, against a local `ng serve --port 4123`. Screenshots are checked against the acceptance rule above. Production is re-shot after deploy.

## Out of scope

The chart itself, the Trades list, the plan detail page (`workspaces/plans/plan-detail.ts`), any store write path, and any change to a shared `why/` component. The only backend change is publishing `risk_stop`.

## Panel review

Staff-engineer (10 ADVISORY):
- card container must not go on shared `sb-panel` -- applied (§7: trade-page wrappers only).
- per-cell `WhyPanel` leaves empty cells, and `ABSENT_SECTIONS` intersection is unstated -- applied (§7 computed `whyAreas()`, §4 intersection).
- `showLevelNumbers` would still render a "Levels & methods" heading or an empty panel -- applied (the input is dropped; Level sources is a trade-page card fed from the store, hidden when empty).
- calendar + strategy cannot be one panel -- applied (two panels stacked in one cell).
- `averageExit` should use `store.legs()` and name the null-leg rule -- applied.
- closed/open precedence when `exit_price` is set -- applied (status first).
- `stall_exit` missing, and the hand-mirrored table drifts -- applied (label added; pytest drift check against `metrics.py`).
- the claim that unknown `?tab=` drops the parameter was wrong -- applied (legacy ids rewritten with `replaceUrl`; unknown left as today).
- ~15 existing spec cases break -- applied (rewrite scheduled in Testing).
- `primitives.spec.ts` and `async-coverage.spec.ts` gates -- applied (named in Testing).

Financial-advisor (2 BLOCKING, 8 ADVISORY):
- BLOCKING: P&L shown with no fees/tax qualifier -- applied ("before fees & tax" caption).
- BLOCKING: % basis unstated, no 1R $ -- applied ("on position" label; "1R = $" subline).
- blended R alone can mislead -- applied (leg Rs subline).
- average exit matches no fill -- no change needed (legs one tab away on Overview).
- stale flag on Unrealised, and the PARTIAL basis -- applied (flag on both tiles; basis verified and labelled in the plan).
- Confidence 90 beside a hidden WEAK badge -- applied (badge on Scores, neutral bars, "not win probabilities" note).
- tint near zero overstates -- applied (neutral band |R| < 0.1).
- paper disclaimer only in one footnote -- applied (one muted line under the strip).
- no $ risk -- applied (Position "$ at risk").
- holding period / tax -- applied (covered by the pre-tax caption; `held()` already prints days).

Veteran-trader (1 BLOCKING, 7 ADVISORY):
- BLOCKING: working stop vs original stop unclear, no follow-up cue -- applied (working-stop row "(was …)", "move your resting stop" line, new `risk_stop` field).
- no distance from the current price -- applied (Price subline "to stop / to T1"; pending current price and % to trigger).
- dropping If-it-gets-there removes "what next" -- applied (kept as the Next block in Outcome for ACTIVE/PARTIAL/PENDING).
- earnings buried in Why -- applied (earnings chip on the identity line from the earnings gate).
- stall vs time exit merged, gap exits hidden -- applied (separate "Stall exit"; "(gapped)" below −1.05R).
- expiry as bars, and "never filled" reason -- applied (date first; status_history reason as subline).
- arrow-only direction, order side unnamed -- applied (Long/Short text; Order row names side and type; gap-through-trigger note).
- `held_hours` unreadable -- no change needed (`held()` already prints days, `ui/format.ts:74-82`); time-exit days-left subline added.
