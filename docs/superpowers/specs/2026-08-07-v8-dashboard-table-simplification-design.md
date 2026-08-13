# Dashboard Table Simplification — Design Spec

**Date:** 2026-08-07 · **Status:** Approved (brainstormed + user-approved in session)
**Implementation plan:** to be written from this spec (writing-plans) once approved

## 1. Goal

The Dashboard's two tables have accumulated more columns than a monitoring
surface can carry: **Open Trades renders 18 columns, Trade History 16** (14 of
them sortable, plus the row-number and actions columns), on top of tier and
badge chips packed inside the ticker cell. The operator's stated job
for these tables is "both monitor and judge, but split" — a lean default for
monitoring, with the analytical columns still reachable rather than deleted.

Success criteria:

1. Open Trades defaults to **8 columns**, Trade History to **8**.
2. Every column available today is still reachable, in one click, per table.
3. Compact is the shipped default: a browser with no stored preference gets it.
4. Sorting, filtering, pagination and auto-refresh behave exactly as they do
   today in both densities.
5. Full suite green; no change to any route, trading logic, or stored data.

## 2. Why these columns are cuttable

The cuts follow four redundancy groups found in the current markup, not taste:

- **One judgement rendered twice.** `confidence` (Lv3) and `score` (60/100)
  are the same assessment at two resolutions.
- **One outcome expressed three ways.** `pnl%`, `gain/loss` and `R` differ only
  in scaling — `pnl%` and `gain/loss` are the same ratio times position size.
- **Two facts spread over three time columns.** `opened` + `closed` + `held`.
- **A static plan next to a live indicator of it.** `entry`/`stop`/`target`/`rr`
  are fixed at open, and the existing `status` cell already renders price's
  position between them (`0% = SL, 100% = TP`).

Separately, the **Performance page already aggregates by strategy, by horizon
and by confidence**, with win rate, expectancy, profit factor, tier calibration
and badge drift. Cross-trade analysis is served better there — with sample
sizes — than by eyeballing a wide table, so those columns leave the default
view without losing the capability they existed for.

**Deliberately kept, against the redundancy logic:** `Gain/Loss` *and* `R`.
Money says what happened; R says whether the trade was good relative to the
risk taken. `pnl%` is the one that goes, since it carries no information that
`gain/loss` doesn't.

## 3. Column sets

### Open Trades — 18 → 8

| # | Compact column | Built from |
|---|---|---|
| 1 | `#` | `rownum` |
| 2 | `Prog` | existing `status` cell (position between SL and TP) |
| 3 | `Ticker` | `ticker` + direction glyph + tier chip + badge chip, merged |
| 4 | `P&L` | `pnl` %, unrealised amount on hover |
| 5 | `Price` | `current_price`, live-refresh styling preserved |
| 6 | `Plan` | `entry` → `target` / `stop`, collapsed into one cell |
| 7 | `Held` | `days` |
| 8 | — | actions |

Full-only: `strategy`, `horizon`, `confidence`, `score`, `rr`, `size`,
`opened`, and `entry`/`stop`/`target` as separate columns.

### Trade History — 16 → 8

| # | Compact column | Built from |
|---|---|---|
| 1 | `#` | `rownum` |
| 2 | `W/L` | `outcome` |
| 3 | `Ticker` | `ticker` + direction + tier/badge chips, merged |
| 4 | `Gain/Loss` | money, `pnl%` on hover |
| 5 | `R` | realised R-multiple |
| 6 | `Held` | `days` |
| 7 | `Closed` | `closed_at` |
| 8 | — | actions |

Full-only: `strategy`, `horizon`, `conf`, `entry`, `exit`, `pnl%` as its own
column, `opened`.

## 4. Mechanism

A `[Compact | Full]` control sits beside each table's existing per-page
selector. State is **per table and independent** — `ot_density` and
`ct_density` in localStorage — each defaulting to `'compact'` when unset,
mirroring how `ct_per_page` already defaults to `'10'`.

**The server keeps rendering every column, always.** Density is a CSS class on
the table wrapper; full-only cells carry `col-full`, and the two new composite
cells carry `col-compact`. Toggling swaps the class — instant, no re-fetch.

This beats rendering different column sets server-side for three reasons:

1. **Sorting keeps working.** `ctColIndex()` and `colIndexById()` resolve a
   column by its position among `thead th`. Removing columns from the DOM
   shifts every index and silently breaks sort; CSS hiding leaves the DOM
   shape intact.
2. **Auto-refresh stays simple.** morphdom patches this fragment continuously.
   If markup varied by density, the server would need each client's toggle
   state. Instead the class is re-applied in the existing
   `refreshClosedTradesTable()` / `otRefreshRows()` hooks — one line each,
   because morphdom may revert a class it did not render.
3. It reuses the localStorage-persisted control pattern already in this file.

**Compact is not purely "hide some columns."** `Prog` and `Plan` are new
composite cells and the direction glyph moves inside the ticker cell, so both
tables need template work — this is not a CSS-only change. Scope stays inside
`dashboard_fragment.html` plus `static/style.css`.

## 5. Behaviour

- **Sort state survives toggling.** Sort column and direction are preserved
  across a density switch. A hidden column cannot be sorted while hidden;
  switch to Full to sort by it.
- **Pagination and filters are untouched.** Density is presentational and
  changes no row's visibility, so the paginator, filter dropdowns and the
  row-count line behave identically in both densities.
- **Free-text search still matches hidden cells.** Open Trades' filter reads
  `row.innerText`, which includes hidden columns, so typing `RSI` in Compact
  still finds those rows. Kept deliberately: a search that silently stops
  matching what you cannot see is the worse failure.
- **Leg rows are unaffected.** `.ot-leg-row` / `.ct-leg-row` continue to be
  excluded from pagination and shown with their parent trade in both densities.

## 6. Testing

Server-side, following `tests/admin/test_dashboard_v2.py`:

1. Every column still renders in the HTML in both densities (nothing is
   dropped server-side).
2. `col-full` / `col-compact` markers land on the correct cells in both tables.
3. The default density is compact — the wrapper ships with the compact class
   and no stored preference is required.
4. The existing leg-row regression tests continue to pass unchanged.

Not covered by these tests: the toggle's client-side behaviour, since the repo
has no JS test runner. The class-swap and its re-application after refresh
need manual verification in a browser.

## 7. Out of scope

- Any change to the Performance, Plans, or trade detail pages.
- Any change to Discord embeds, routes, or trading logic.
- Column reordering beyond what the compact set requires.
- Mobile-specific layout work.
