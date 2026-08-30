# v65 — Table pagination overhaul

**Version:** ui 1.9.2 · bot 1.4.5
**Bump:** ui minor (1.9.2 → 1.10.0) · bot none
**Edge:** none (integrity)

Every row-list table in the admin SPA gains a pager at the top *and* the
bottom, a consistent page height, and — on the Trades side — a `Held` column
that is correct to the minute rather than correct to the hour at whatever
moment the server last answered.

`Bump` is a minor on `ui` alone and nothing on `bot`: no Python changes, but
every table screen in the product looks and behaves differently afterwards.
`Edge` is `none (integrity)` — this buys no expectancy. It buys a table that
does not lie about how many rows exist and a duration that does not lie about
how long a position has been open.

## Goal

Four things, in one pass over the table layer:

1. **Pagination on every row-list table, top and bottom.** Three tables have
   none at all today; the rest have a bottom pager only.
2. **`Held` to minute precision, computed live.**
3. **A constant page height**, with the unfilled remainder painted in the page
   background rather than left as a collapsing table.
4. **The table improvements that fall out of doing the above**: sticky header,
   first/last/jump paging, screen-reader page announcements, sortable Risk and
   ticker-detail tables, and totals where a total can be stated honestly.

## Non-goals

- **The four fixed-shape grids stay untouched**: the Analytics heatmap
  (`analytics.ts:594`), the settings diff view (`settings-tab.ts:251`), the
  Calendar day-of-week header (`calendar.ts:160`) and the Gallery numerics demo
  (`gallery.ts:209`). These are matrices, not row lists; a pager over a
  seven-column day-of-week header is chrome with nothing to page.
- **A totals footer on the Trades table.** See Decision 12 — it needs a
  backend aggregate and belongs to its own spec.
- **No backend change of any kind.** Everything here is under `frontend/`.

## Decisions

### D1 — The top pager lives in `DataTable`, not in the call sites

`sb-data-table` already owns *when* the pager appears; its own header comment
records this as deliberate ("a caller cannot forget to render the pager"). The
top pager is therefore a second `<sb-pagination>` inside `DataTable`'s
template, rendered above `.scroller`, bound to the same `pagination()` input
and emitting the same `pageChange`/`perPageChange` outputs.

Both pagers carry identical controls, including the rows-per-page selector when
`showPerPage` is set. They need no synchronisation: both are stateless
projections of `pagination()`, so neither can disagree with the other.

Two call sites render `sb-pagination` directly rather than through the table —
`analytics.ts:876` (strategy proposals, a card list) and `gallery.ts:368` (a
component demo). Neither is a row-list table, both are out of `DataTable`'s
reach, and both keep the single bottom pager they have. The Gallery's *table*
demo (`gallery.ts:362`) goes through `DataTable` and so picks the top pager up
for free.

### D2 — The three unpaginated tables get `createClientPage`

Risk's "Exposure by position" (`risk.ts:222`), the Watchlist
(`watchlist.ts:224`) and a ticker's "Trades on X" (`ticker-detail.ts:89`) pass
no `pagination` input at all. Each gets a `createClientPage` over the rows it
already has in hand — the same helper the eight Analytics tables use.

Client-side, not server-side, because none of the three endpoints returns a
`Collection<T>` envelope. `PageSpec.total` stays honest: it is the length of
the full fetched array, not of the visible slice.

Watchlist pages over `sortedRows()`, not the raw rows, so sorting reorders the
whole list and paging then slices it — the ordering-then-slicing direction that
`DataTable`'s "server-side everything" property exists to protect.

### D3 — The Dashboard groups need no "only if overflow" logic

Each `sb-trade-group` already queries with `per_page: cap` (6) and already
holds the true pre-slice `total`. `PaginationComponent` already renders nothing
when there is one page. So binding `[pagination]="trades.pagination()"` and
`(pageChange)` produces exactly the requested behaviour — a cap of six, and a
pager that appears only when more than six exist — with no conditional.

`showPerPage` stays off for these four groups. The cap is the design, not a
preference; the "All N →" link is the escape hatch to Trades and stays.

`rows = trades.rows().slice(0, cap)` becomes redundant once the page size *is*
the cap, but stays as a defensive clamp against a server that over-returns.

This reverses `OPEN_POSITIONS_CAP`'s standing comment, which argued that a
pager here "would invite paging through a summary, which is the Trades
workspace wearing a disguise". The reversal is narrow and must be recorded in
that comment: the cap survives untouched, so the summary is still a summary;
what changes is that rows 7+ stop being *silently* invisible.

### D4 — `Held` is computed live for open positions, and `Hold` is deleted

`Held` renders in `heldPrecise` form (`3d 1h 22m`) everywhere.

For a **closed** row the source stays the server's `held_hours`, which is fixed
and correct. For an **open** row the duration is computed in the browser from
`opened_at` against a ticking clock.

The client computation is not a refinement, it is a correctness requirement.
`_held_hours` (`swingbot/admin/api_v1/trades.py:118`) measures an open position
to `datetime.now()` *at response time*, and this SPA refreshes on bot events
rather than on a timer — the Dashboard's own footnote says so. Rounding to the
hour hid that staleness. Minutes would display it: a table left open for twenty
minutes would read `1h 3m` when the truth is `1h 23m`.

**`heldPrecise` and the `hold` column are consequently redundant and go away.**
With `Held` at minute precision, `hold` (`trades.columns.ts:104`) is the same
column under a second name. `hold` is dropped from `tradeColumns()` and from
`dashboard.ts`'s `closedVisible()`; `heldPrecise` is folded into `held`.

### D5 — The clock is an injected signal, not a timer inside the formatter

A new `ui/clock.ts` exports a `CLOCK` `InjectionToken<Signal<number>>` whose
default implementation ticks every 30 seconds. This mirrors `CHART_PREFS_STORE`
(`ui/chart/chart-prefs.ts:35`), the pattern this repo already uses for an
ambient dependency that tests must be able to replace.

`tradeColumns()` takes the clock as a parameter:
`tradeColumns(now: Signal<number>)`. The column def **closes over the signal
and reads it inside `value()`**, rather than the caller passing `now()` and
rebuilding the array each tick. Reading a signal during template evaluation is
what makes the affected cells re-render; rebuilding the array would invalidate
the whole `computed`, re-run the column picker's mapping, and re-render every
table on the Dashboard every 30 seconds for two cells that changed.

Thirty seconds, not one: the number is minutes-precision, so a per-second tick
would re-render for a value that is identical 29 times out of 30.

Tests pass `signal(FIXED_MS)` and get a deterministic duration.

### D6 — Filler rows pad every page up to `perPage`

A short page pads to a constant height with blank `<tr>`s, so the last page is
the same height as the first.

The brief asked for this on "paginated tables" *and* on "all tables including
unpaginated". After D2 those are the same set: every row-list table in the app
is paginated once Risk, Watchlist and ticker-detail get `createClientPage`. So
there is one rule and no `minRows` escape hatch — the target is always
`pagination().perPage`, and a table with no `pagination` input is by then only
the four fixed-shape grids this spec does not touch.

The filler rows:

- carry `aria-hidden="true"` and no cell content — they are visual spacing, and
  a screen reader must not count them as rows;
- are painted `background: var(--bg)` (#0a0b10), one step darker than the
  panel's `--surface` (#10121a), so the remainder reads as *void beneath the
  table* rather than as rows that failed to load;
- carry no bottom border and are not hoverable or activatable;
- are **skipped in mobile card mode** — card mode renders a stack, not a grid,
  and a blank card is not spacing, it is a broken card;
- are **skipped when per-page is `All`** (`ALL_PER_PAGE`, 0) — there is no
  fixed page height to pad to.

### D7 — The row count always shows; only the buttons hide

`PaginationComponent` currently renders nothing at all when `pageCount() <= 1`,
which also hides `rangeLabel()`. A one-page table therefore cannot tell you how
many rows it has without counting them.

The range label becomes unconditional (`6 rows` in the single-page case,
`26–50 of 90` otherwise); the Previous/Next/first/last controls keep their
existing `pageCount() > 1` condition.

### D8 — First, last and jump-to-page

Previous/Next alone is twelve clicks to page thirteen. The pager gains ⏮ and ⏭
buttons flanking the existing pair, and the `N / M` indicator becomes a number
input that navigates on commit. Out-of-range input clamps rather than errors —
`goTo` already refuses a target outside `1..pageCount()`.

### D9 — Page changes are announced

An `aria-live="polite"` region in `PaginationComponent` announces
`Page 3 of 9, showing 51–75 of 214` on change.

`PaginationComponent` renders twice per table, so the region is gated behind a
new `announce` input (default `false`). `DataTable` sets it on the **top**
pager only — two live regions saying the same thing would announce every page
change twice, which is worse than not announcing it.

Follows the `announce()` input `sb-async` already uses rather than inventing a
second mechanism.

### D10 — `createClientPage` gains a reactive `perPage`, persisted per table

`createClientPage(rows, perPage = 25)` takes a fixed number today, so a
client-paged table cannot offer a rows-per-page control. The signature becomes
`createClientPage(rows, perPage: () => number)`, with the existing numeric form
accepted and wrapped so the eight Analytics call sites need no change beyond
opting in.

Persistence reuses `readTablePerPage`/`writeTablePerPage`
(`ui/table-prefs.ts:108`), which are already per-table-keyed and already
tolerant of a stale stored value. Only Trades uses them today; Risk, Watchlist,
ticker-detail and the Analytics tables each get a stable table id.

The clamp-on-read behaviour in `createClientPage` becomes load-bearing rather
than defensive: shrinking `perPage` from 50 to 10 while on page 4 must land on
a page that exists.

### D11 — Sticky header, with its scrollport trap named

`thead th { position: sticky; top: 0 }` **does not work as written here.**
`.scroller` is `overflow-x: auto`, and per CSS overflow rules a non-`visible`
value on one axis computes the other to `auto` — so `.scroller` is a scrollport
on both axes and the header sticks to a box that never scrolls vertically.

The header must therefore stick against the viewport, offset by the shell's own
sticky header (`shell/shell.css:93`). This is the one item in this spec with a
real chance of looking subtly wrong at some viewport, so it is its own task
with its own visual check at 375px, 768px and 1280px, and it is sequenced last
so a problem there cannot block anything else.

### D12 — Totals where a total can be stated honestly

**Risk's exposure table gets one, and it is the only one.** It holds the
complete set client-side, and its two summable columns — shares-at-risk and
risk % — are exactly the numbers "how exposed am I right now" is asking for, so
the sum is both correct and wanted. The other client-paged tables have no
column worth summing: Watchlist rows are tickers, and Analytics rows are
already aggregates.

**Trades gets no footer.** It is server-paged; a footer summing the visible
page would be the same defect as a pager counting visible rows, which
`PageSpec.total`'s own doc comment calls out as the anti-pattern the contract
exists to prevent. An honest Trades total needs a new aggregate on the
collection endpoint, with its own API contract and test surface. That is a
separate spec, and bolting it on here roughly doubles this plan.

The footer renders in `<tfoot>`, is excluded from the filler-row count, and is
suppressed when the table is empty — a total of zero over no rows is a claim,
not a measurement.

### D13 — Sorting on Risk and ticker-detail

Neither table has a single `sortable` column. Risk's exposure list cannot be
ordered by risk %, which is the one question that table exists to answer.

Both get client-side sorting, following the pattern Watchlist already uses
(`sort()` signal + `setSort()`, sorting the array before the client page slices
it). `held` becomes sortable on ticker-detail, matching Trades.

## Components

| File | Change |
|---|---|
| `ui/clock.ts` | **new** — `CLOCK` token, 30s ticking default |
| `ui/pagination.ts` | first/last/jump; unconditional count; `announce` input |
| `ui/data-table/data-table.ts` | second `<sb-pagination>`; filler rows; `<tfoot>`; sticky header |
| `ui/data-table/data-table.types.ts` | `ColumnDef.footer?`, for D12 |
| `ui/data-table/client-page.ts` | reactive `perPage` |
| `ui/table-prefs.ts` | no change — already sufficient |
| `ui/format.ts` | `held` absorbs `heldPrecise`; `heldPrecise` removed |
| `workspaces/trades/trades.columns.ts` | `tradeColumns(now)`; `hold` deleted |
| `workspaces/dashboard/trade-group.ts` | pager wiring; `OPEN_POSITIONS_CAP` comment reversal |
| `workspaces/dashboard/dashboard.ts` | `closedVisible()` drops `hold`; clock injection |
| `workspaces/trades/trades.ts` | clock injection |
| `workspaces/risk/risk.ts` | client page, sorting, totals footer |
| `workspaces/watchlist/watchlist.ts` | client page over `sortedRows()` |
| `workspaces/watchlist/ticker-detail.ts` | client page, sorting |
| `workspaces/analytics/analytics.ts` | eight tables opt into `showPerPage` |

## Data flow

Unchanged in shape. `DataTable` still never reorders or slices `rows` — the
client-paged call sites slice *before* handing rows in, exactly as Analytics
does today, and `PageSpec.total` remains the pre-slice count in every case.

The one new flow is the clock: `CLOCK` → injected in `trades.ts` /
`dashboard.ts` / `ticker-detail.ts` → passed to `tradeColumns(now)` → read
inside the `held` column's `value()` during template evaluation → Angular marks
the component dirty on tick.

## Error handling and edge cases

- **Page beyond the end.** `createClientPage` clamps on read; the server-paged
  stores already reset to page 1 on a filter change (`trades.ts:796`).
- **`opened_at` null or unparseable.** A `PENDING` row has no `opened_at`; the
  live path returns `ABSENT` (em dash), never `0m`. `format.ts`'s standing rule
  — a missing value is never rendered as zero — governs.
- **Clock in tests.** A real 30s interval must never run under Vitest; the
  `CLOCK` token is overridden with a fixed `signal()` per suite.
- **`perPage: All` with filler.** Filler off (D6); footer still renders.
- **Empty table.** Empty state renders, filler does not, footer does not.

## Testing

Per-task verification is `npm test -- --include <the one spec file>`; the plan
ends with one full `cd frontend && npm test`. No Python suite is touched.

New or extended specs: `pagination.spec.ts` (first/last/jump, unconditional
count, announcement text), `data-table.spec.ts` (filler count and background,
card-mode and `All` suppression, `tfoot`), `client-page.spec.ts` (reactive
`perPage`, clamp on shrink), `format.spec.ts` (`held` minute output, null),
`trades.columns.spec.ts` (`hold` gone, `held` reads the clock), plus each
touched workspace's own spec for the pager and sort wiring.

## Parallelisation

- **Sequential first:** `ui/clock.ts`, then `ui/pagination.ts`, then
  `ui/data-table/data-table.ts` — each consumes the previous one's symbols, and
  every workspace task consumes all three.
- **Group 1 (parallel):** `ui/format.ts` and `ui/data-table/client-page.ts` —
  disjoint files, no shared contract, both independent of the pager work.
- **Group 2 (parallel, after the sequential block and Group 1):** `risk.ts`,
  `watchlist.ts`, `ticker-detail.ts`, `analytics.ts` — one workspace file each.
- **Sequential:** `trades.columns.ts` before `trades.ts` and `dashboard.ts`
  (both consume `tradeColumns(now)`'s new signature); `trade-group.ts` before
  `dashboard.ts` (same file's group bindings). `trades.ts` and `dashboard.ts`
  are **not** parallel with each other — `dashboard.ts` reads
  `trades.columns.ts` and both drop `hold`.
- **Sequential last:** the sticky header (D11), then full-suite verification.

## Acceptance

1. Every row-list table shows a pager above and below, with identical controls.
2. A single-page table shows its row count and no navigation buttons.
3. Dashboard groups show six rows and a pager only when more than six exist.
4. `Held` shows minutes, ticks while watched on an open position, and is fixed
   on a closed one. No `Hold` column exists.
5. A short page is padded to full height in `--bg`, with no filler in card mode
   or under `All`, and screen readers count only the real rows.
6. Risk and ticker-detail sort; Risk shows honest totals; Trades shows none.
7. `cd frontend && npm test` is green.
