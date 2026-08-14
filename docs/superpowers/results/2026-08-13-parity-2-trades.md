# Jinja → SPA parity audit, group 2: Trades, Journal and the detail views

Task SR42 of `2026-08-13-v21-spa-refresh.md`. Templates audited:
`journal.html`, `trade_detail.html`, `_trade_history_rows.html`,
`plan_detail.html`, together with the routes that build their context
(`pages.py:journal_page`, `pages.py:plan_detail_page`, `app.py:trade_detail`,
`dashboard.py` for the row partial's callables).

Three statuses only — `migrated`, `dropped on purpose`, `missing`. Nothing is
left unclassified.

**The finding that dominates this group.** Nine fields on `TradeDetailFields`
(`frontend/src/app/api/models.ts:101-139`) are typed, fetched and then rendered
by nothing: `explanation`, `confirmed_by`, `target_sources`, `stop_sources`,
`target2_sources`, `confidence_breakdown`, `quality_breakdown`,
`status_history`, `legs` / `legs_realized`, plus `trigger_price`, `expiry_bars`
and `created_at`. `grep` over `frontend/src` finds each one exactly once — in
`models.ts` itself. The data is already on the wire, so every row below that
points at one of them is a rendering gap, not a backend gap. That is the
cheapest class of `missing` row in this whole audit.

---

## `_trade_history_rows.html` — the closed-trade row partial

Rendered by both the dashboard's first paint and `/api/trade-history`. The
table *chrome* around it was audited in SR41; this is the row content.

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Continuous row numbering across pages (`row_offset`) | `_trade_history_rows.html:26` | dropped on purpose | SR16 replaced the ordinal with the trade's short id (`trades.ts:214-216`) — a number that changes when you sort is not an identifier |
| Outcome glyph W / L / CLOSED + per-outcome tooltip | `:27-31` | migrated | Status chips filter on it (`outcome`), `sb-status-cell` renders `status_label` |
| Ticker link to the detail page | `:32-34` | migrated | `ticker` / `num` cells are anchors to `/trades/:id` |
| Inline direction glyph at compact density | `:35` | migrated | `sb-direction-arrow` as its own column (SR9) |
| Tier chip + "A ≥75 / B 50-74 / C below 50" tooltip | `:36` | migrated (narrowed) | `tier` column + `sb-quality-chip`; the threshold tooltip is gone |
| VALIDATED/WEAK deliberately omitted from this table | `:38-41` | dropped on purpose | Same decision holds — `badge` is row-expansion and detail only |
| Strategy cell + "Sources: …" tooltip | `:43-44` | migrated (narrowed) | `strategy` column. The sources tooltip has no equivalent — see the `target_sources` row below |
| Horizon pill + "~N months swing horizon" tooltip | `:45` | migrated (narrowed) | `horizon` column, raw key only |
| Direction cell | `:46-50` | migrated | `sb-direction-arrow` |
| Confidence Lv1-5, colour-coded | `:51` | migrated | `sb-confidence-cell` (SR10) |
| Entry price | `:52` | migrated | `entry` column |
| Exit price, with "no exit price recorded" tooltip | `:53-57` | migrated (narrowed) | `exit_price` column; `num()` renders null as a dash without saying why |
| Realized P&L %, direction-adjusted | `:58-63`, `dashboard.py:closed_pnl` | migrated | `pnl_pct` column |
| Realized gain/loss in account currency | `:64-71` | migrated | `realized_pnl_amount` column ("Realised") |
| That cell's tooltip: position size at open, or "no sizing snapshot" | `:67` | **missing** | — `position_value` is a picker-addable column, but the "logged before this feature existed" distinction is gone |
| Realized R-multiple + its explanation tooltip | `:72-77`, `dashboard.py:closed_r` | migrated (narrowed) | `r_multiple` column via `rMultiple()`; no tooltip |
| Held / holding period | `:78-79`, `dashboard.py:closed_days` | migrated | `held` column via `held(row.held_hours)` |
| Opened / Closed timestamps, Berlin, UTC in the tooltip | `:80-81` | migrated (narrowed) | `opened_at` / `closed_at` via `dateTime()`; no second timezone |
| Row action: open detail in a new tab | `:83-84` | dropped on purpose | The id cell is a real anchor, so the browser provides this |
| Row action: delete this trade record | `:85-88` | migrated | `availableActions()` returns `delete` in every branch, so this is the one row action that does render (`trades.ts:247-255`) |
| Scale-out leg rows under the trade | `:91-101` | **missing** | `legs` is on the wire (`models.ts:130`); nothing renders it. Recorded once here and once in SR41 |

---

## `trade_detail.html` — one trade

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| "Back to dashboard" link | `trade_detail.html:3` | migrated | "← Trades", `trade-detail.ts:74` — back to the list the row came from |
| Visualization card: LONG/SHORT + ticker heading | `:8-13` | migrated | The header's ticker, `sb-status-indicator` and the direction/strategy tags (`trade-detail.ts:76-103`) |
| Server-rendered PNG chart | `:19-24` | dropped on purpose | Phase 3 replaced it with the live `sb-trade-chart` on the Chart tab; SR40 walked the two against each other |
| Chart loading spinner and its "price data may be unavailable" failure copy | `:15-24` | migrated | `sb-chart-container` `[loading]` / `[error]` / `[canRetry]`, `trade-detail.ts:278-288` |
| `<details>` "Interactive chart" | `:25-27` | migrated | The Chart tab *is* the interactive chart; it is no longer folded away |
| Chart lightbox: pinch-zoom, drag-pan, double-tap reset, orientation lock | `:182-431` | dropped on purpose | A lightbox is what a static raster needs. The Chart tab's chart zooms and pans natively |
| Trade facts: strategy + horizon pill | `:34` | migrated | Header tags, `trade-detail.ts:88-93` |
| VALIDATED / WEAK badge pill + its two tooltips | `:35-37` | migrated (narrowed) | The Strategy tab shows the registry's own `status`, `n`, win rate, expectancy and window (`trade-detail.ts:346-383`), which is the same judgement with its evidence. The pill and its copy are gone |
| Status pill (WIN / LOSS / other) | `:38-40` | migrated | `sb-status-indicator` in the header |
| Entry / Stop / Target 1 / Target 2 / R:R | `:44-52` | migrated | Plan tab → Levels panel, `trade-detail.ts:117-140` |
| Realized amount | `:53-55` | migrated | Live tab → Now → Amount, `trade-detail.ts:220-225` |
| "Close trade" button on an open trade | `:58-63` | **missing** | Live tab → Actions renders `actionsFor(trade.status)`, and `availableActions()` matches `'open'` while the endpoint emits `ACTIVE` / `PARTIAL` — so only Delete appears. Same defect as SR41's row |
| Trade plan panel (duplicate of Trade facts, plus sources) | `:76-94` | migrated | Plan tab → Levels |
| "Target confirmed by" / "Stop confirmed by" sources | `:88-93` | **missing** | `target_sources` / `stop_sources` are on the wire (`models.ts:134-136`); no component reads them |
| "If it gets there" projection (next level up, pullback on reversal) | `:96-104` | **missing** | — no equivalent panel; it is derived from `target2` and `stop_loss`, both of which the Levels panel already has |
| Support/resistance wording (`level_word` / `opposite_word`, direction-aware) | `:46, 99, 103`, computed in `app.py:trade_detail` | dropped on purpose | The SPA labels them "Target 1" / "Target 2" / "Stop" regardless of direction — one vocabulary rather than two |
| "Why this trade" — the recorded explanation | `:107-114` | **missing** | `explanation` is on the wire (`models.ts:132`); nothing renders it. The single largest piece of per-trade prose in the old UI |
| Setup: strategy, direction, confidence label + Lv + score | `:126-134` | migrated | Header tags + Plan tab (`direction`, `origin`); confidence as a chip |
| "Confirmed by" — the other strategies that agreed | `:135-139` | **missing** | `confirmed_by` on the wire (`models.ts:133`), rendered nowhere |
| Opened / Closed timestamps with fill prices | `:151-154` | migrated (narrowed) | Plan tab → Opened (At / Closed); the fill price is not paired with the timestamp |
| Realized gain/loss | `:155-159` | migrated | Live tab → Amount |
| Confidence score breakdown table (8-10 factors) | `:163-173` | **missing** | `confidence_breakdown` on the wire (`models.ts:131`), rendered nowhere |
| "Logged before the admin UI captured full detail" notice | `:177-181` | **missing** | — the SPA renders missing detail fields as dashes with no explanation of why they are empty |
| Per-share risk / reward | — | n/a | New in the SPA (`trade-detail.ts:142-161`) |
| Working stop, sizing mode, entry type | — | n/a | New on the Plan tab; `working_stop` / `sizing_mode` / `entry_type` are the three detail fields that *are* rendered |

---

## `plan_detail.html` — one plan

Nothing on this page has its own destination in the SPA: a plan and its trade
are one entity there, so `/trades/:id` is the successor to both detail pages.
What follows classifies the contents.

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Heading: ticker — strategy (horizon) | `plan_detail.html:7` | migrated | Detail header + tags |
| Tier chip, badge chip, status pill | `:9-11` | migrated (narrowed) | Tier chip and status indicator are there; the badge chip is not (see the badge row above) |
| Direction | `:14` | migrated | Plan tab → Per share → Direction |
| Entry type | `:15` | migrated | Plan tab → Opened → Entry type |
| Trigger / Entry pair | `:16-17` | **missing** | `trigger_price` on the wire (`models.ts:118`), rendered nowhere. For a PENDING plan this is the only actionable price |
| Stop loss | `:18` | migrated | Plan tab → Levels → Stop |
| TP1 with its fraction ("TP1 (50%)") | `:19-20` | migrated (narrowed) | "Target 1"; `tp1_fraction` is on the wire and not rendered, so the split is not shown |
| TP2 (runner) | `:21` | migrated | Plan tab → Levels → Target 2 |
| Break-even trigger, as % of TP1 distance | `:22` | **missing** | `breakeven_trigger_fraction` on the wire (`models.ts:121`), rendered nowhere |
| Quality score | `:23` | migrated | Trades row expansion → Quality (`trades.ts:287`) |
| Plan chart PNG + lightbox | `:26-46` | dropped on purpose | Same decision as the trade chart — the Chart tab replaces both |
| Lifecycle timeline (created, then every status transition with reason and time) | `:48-58` | **missing** | `status_history` and `created_at` are on the wire (`models.ts:115, 128`), rendered nowhere. This is the plan's whole audit trail |
| Quality breakdown table (factor → points) | `:60-74` | **missing** | `quality_breakdown` on the wire (`models.ts:126`), rendered nowhere — the score shows without its reasons |
| Badge stats: status, N, win rate, expectancy, window | `:76-87` | migrated | Strategy tab renders the registry's equivalents, and adds the live-vs-OOS comparison (`trade-detail.ts:346-383`) |
| Follow-score breakdown | `:89-98` | **missing** | — follow score itself is not on the wire at all (SR41), so neither is its breakdown |
| Linked trade: id, status, legs | `:100-114` | dropped on purpose | Plan and trade are one row and one page in the SPA, so there is nothing to link to. The legs half is recorded as missing above |
| Empty state: "No trade has been linked to this plan yet" | `:115-120` | dropped on purpose | Same reason — a PENDING row simply has null execution fields |

---

## `journal.html` — the journal

The Journal is `dropped on purpose` **as a page** (spec v14 Decision 4 folds it
into Trades, and the Notes tab is where a note is written). Its analytical
content is a different question, and most of it did not come with it.

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Journal as its own destination | `journal.html` | dropped on purpose | Spec v14 Decision 4 |
| Entries / Weekly digest view switch | `:3-6` | dropped on purpose | Only the entries half has a successor; the digest is recorded below |
| Filter: strategy | `:28-29` | **missing** | Same gap as SR41's strategy filter — accepted by `api_v1/trades.py:FILTERS`, no control |
| Filter: tag | `:30-35` | **missing** | — journal tags are not on `TradeRow` at all |
| Filter: outcome (win / loss / scratch / timeout) | `:36-42` | migrated (narrowed) | Status chips cover `win` and `loss`; `scratch` and `timeout` have no chip |
| Filter: has note / no note | `:43-47` | **missing** | `has_note` is on `TradeRow` (`models.ts:84`) *and* in `FILTERS` (`trades.py:59`) — client-only work |
| Clear filters | `:48-49` | migrated | `sb-filter-bar (cleared)` |
| Empty state | `:52-56` | migrated | `data-table` empty state |
| Per-entry outcome chip, ticker, strategy | `:60-65` | migrated | The Trades row carries all three |
| Realized R per entry | `:66-68` | migrated | `r_multiple` column |
| Link to the trade | `:69` | migrated | Row and id cell both link |
| MFE (max favourable excursion), in R | `:72` | **missing** | — not on `TradeRow`, not on `TradeDetailFields`, nowhere in the API |
| MAE (max adverse excursion), in R | `:73` | **missing** | — likewise absent from the wire |
| Exit efficiency % | `:74` | **missing** | — likewise |
| Entry tags | `:76-80` | **missing** | — likewise |
| Auto-generated lesson per entry | `:81-83` | **missing** | — likewise |
| Note display | `:84-86` | migrated | Notes tab, `detail.note` |
| Inline note editing, saved per entry | `:87-94, 100-121` | migrated | Notes tab textarea with `saving` / `unsaved` / `error` states (`trade-detail.ts:303-333`) — a better version of the same control, one trade at a time |
| Weekly digest messages | `:8-15`, `pages.py:346` (`weekly_digest`) | **missing** | — no endpoint and no view |
| Top lessons list | `:16-25`, `pages.py:347` (`top_lessons`) | **missing** | — likewise |

---

## Tally for this group

| Status | Count |
|---|---|
| migrated (incl. narrowed) | 39 |
| dropped on purpose | 12 |
| **missing** | 25 |
| new in the SPA (not a parity row) | 2 |

The `missing` rows fall into three groups, which is what SR46 will rank:

1. **Fetched but never rendered** — explanation, confirmed_by, target/stop
   sources, confidence breakdown, quality breakdown, status history, legs,
   trigger price, break-even fraction, TP1 fraction. Twelve fields, all
   already on the wire, all needing only a component. This is the largest and
   cheapest cluster in the audit.
2. **Never on the wire** — MFE, MAE, exit efficiency, tags, auto-lessons, the
   weekly digest, top lessons, follow score. These need an endpoint before
   they need a view, so they are the expensive half. Note that the journal
   analytics are a coherent set: they either come back together or not at all.
3. **The Close action**, again — recorded in SR41 and repeated here because it
   is absent from the detail view's Actions panel for the same reason.
