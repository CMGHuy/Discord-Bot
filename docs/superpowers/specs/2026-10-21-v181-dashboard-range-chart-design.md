# v181 — Dashboard range chart: zoom and pan re-scope the trading performance panel

**Version:** ui 1.33.0 · bot 2.14.1 (at writing)
**Bump:** ui minor — the Dashboard's equity chart pages history, changes timeframe on zoom and drives the KPI scope, and every P&L figure changes colour; bot patch — two additive query parameters (`before` on `/equity/candles`, `mode=range` on `/dashboard`) that no existing caller sends.
**Edge:** none (integrity) — a display and analysis tool; no alert, plan, stop or fill changes.
**Screen:** exempt (integrity)
**Panel:** financial-advisor, senior-engineer, quant-engineer
**Status:** spec written 2026-10-21 from a brainstorm with the partner; revised the same day after the panel (see `## Panel review`). Scope (all four range behaviours plus colour), the two-way scope link, the full TradingView preset set with a phone dropdown, and all four colour treatments were the partner's choices in chat.

## Why

The Trading performance panel's equity chart (`sb-equity-candles`) is already
a lightweight-charts candlestick chart, so zoom and drag work — but nothing
responds to them:

- The API returns only the newest 120 candles (`DEFAULT_LIMIT`, max 500), so
  dragging left hits a wall.
- The readout describes one candle (hovered, or latest), never the window in
  view.
- The eight KPI cards follow only the Today / All days toggle.
- The timeframe is fixed while zooming: zoomed out on 1H the candles become
  unreadable slivers.

The partner wants it to behave like TradingView: the window on screen *is*
the question being asked, and every figure on the panel answers it. Separately,
most P&L figures are uncoloured (win rate, payoff, risk used, the readout), so
the panel does not scan at a glance.

## Design

### 1. Scope control and the two-way link

- The panel header's scope control becomes **1D · 5D · 1M · 3M · 6M · YTD ·
  1Y · All**, plus a live **Range** chip showing the visible dates
  (`3 Sep – 18 Oct`) that appears and is pressed whenever the partner zooms
  or drags by hand.
- **Phone (< 640px)**: the same entries as a single native dropdown (`<select>`),
  44px target. Tablet and desktop: chips, wrapping if needed, never a
  horizontal page scroll.
- **Preset → chart**: choosing a preset sets the scope and moves the chart to
  that window (paging in older history first if the window needs it).
- **Chart → scope**: a user-initiated zoom or pan switches the scope to Range.
  A programmatic viewport change (preset click, timeframe step, data refresh)
  is flagged and never flips the scope. This guard is what keeps the link from
  looping.
- The scope stays **page-wide**: the Closed tab below follows Range like it
  follows Today / All today (v85 D10, unchanged).
- The chosen preset persists in server-backed preferences, like the
  timeframe. An ad-hoc Range is not persisted; a reload returns to the last
  preset.

### 2. Older history on pan

When the visible logical range comes within 20 candles of the oldest loaded
candle and the last response said `has_more`, fetch
`GET /equity/candles?tf=&basis=&before=<oldest candle time>&limit=200` and
prepend the page without moving the viewport. One page in flight at a time; a
page from a superseded timeframe/basis is dropped. Recording-start seam and
hollow approx candles behave as today across pages.

### 3. Auto timeframe on zoom

- More than **250** bars visible → step up one timeframe (1H→4H→1D→1W).
- Fewer than **15** bars visible → step down one.
- No bounce, by construction: a step up at 250 bars lands at about
  `250 / ratio` bars on the coarser timeframe, and the largest adjacent ratio
  (4H→1D at 6, 1D→1W at up to 7 sampled days) still leaves ≥ 35 bars, well
  above the 15 that would step back down. The invariant `250 / ratio > 15`
  is tested over every adjacent pair, with bars counted as candles actually
  present (weekends and empty buckets produce none).
- The **centre time** of the view is preserved across the switch; the visible
  time span is preserved as closely as the new candle width allows.
- The timeframe control follows (and its preference is written, as a manual
  pick would be).
- At the edge of history (a step down would leave fewer than 15 bars because
  data runs out), it stays put.
- A manual timeframe pick still works and simply sets the starting point.
- Changing timeframe changes the candles only: the scope's time window is
  unchanged, so the KPIs do not move.

### 4. Readout

- Hovering a candle: that candle, as today.
- No hover: a summary of the visible range, each coloured per §5:
  - **Equity change**: from the first in-window candle's `o` to the last
    in-window candle's `c`, in % and money. "In-window" means every candle
    whose bucket intersects the visible logical range (a partly visible edge
    candle counts whole), so the readout, the baseline (§5) and the KPI
    window (§6) all use the same whole buckets.
  - **High / Low**: the extremes of `h` / `l` over in-window candles.
  - **Max drawdown within range**: peak-to-trough of candle closes inside the
    window, as % of the running peak; null (shown "—") when the peak is ≤ 0.
    It ignores intra-candle lows by definition, so it can be smaller than
    High→Low; the label says "within range".
- On the mark-to-market basis the equity change includes unrealised drift,
  while the "Realised in range" card counts closes only. The two differ by
  design and are labelled differently ("Equity change" vs "Realised").
- The existing `ACCOUNT_LABEL` caption ("Paper account · before tax and
  costs", already under the chart) is repeated directly under the readout
  and on the KPI grid. Every range figure is a simulated, pre-friction,
  pre-tax number, and a green card must not read as money banked. Reusing
  the constant keeps one wording.

### 5. Profit/loss colour

One rule: `--pos` = good for the account, `--neg` = bad, `--text-secondary`
= neutral or no data. An em dash is never coloured.

| Figure | Rule |
|---|---|
| Readout change, range change, Open P&L, Realised, Expectancy | sign |
| Max drawdown | `--neg` when non-zero |
| Win rate **and** payoff ratio, as a pair | `--pos` when win rate > `1 / (1 + payoff)` + 0.5 pp, `--neg` when below it − 0.5 pp, neutral inside that band; neutral when either is null, payoff ≤ 0, or fewer than **5** closes in scope |
| Risk used | neutral < 75% of cap, warning token 75–100%, `--neg` at/over cap |
| Avg confidence, Open trades | neutral |

Win rate and payoff are judged as a pair on purpose: alone, a 0.8 payoff on a
65% win rate would read red on a profitable book. Payoff is mean winning R
over |mean losing R|, as `payoff_ratio_from_rs` defines it. The breakeven
ignores friction, so a thin edge can read green while losing after costs;
the panel caption (§4) says the figures are pre-cost. Below 5 closes the
colour would be noise, so the pair stays neutral and the cards show `N=`.
The rule lives once, in a frontend colour helper; the API sends no colour.

In Range or any preset other than 1D, the point-in-time cards (Open P&L,
Open trades, Risk used) carry the sub-label **"now"**, so a tinted card in a
past window is never read as that window's exposure.

- **KPI cards**: the card background takes `--pos-soft` / `--neg-soft` with
  its figure's colour; neutral cards stay plain. The phone summary rows take
  the same tint.
- **Stronger candle palette** (ripples beyond the CSS: `ui/tokens.spec.ts`
  pins the current hex and soft values; `swingbot/core/charts/chart_style.py`
  `THEME` mirrors them for the server-rendered Discord charts and bumps
  `STYLE_VERSION`; `tests/charts/resolved_tokens.json` is regenerated with
  `dump_tokens.py`; the gates are `ui/contrast.spec.ts` and
  `ui/chart-palette.spec.ts`). New, more saturated palette primitives
  (TradingView teal/red direction) wired through `--pos` / `--neg`, so all
  colour stays on two tokens and never disagrees. Every pairing (light, dark,
  figure on its soft tint) must pass `tokens.css`'s existing contrast and ΔE
  gates; a failing value is adjusted, never exempted.
- **Above/below-water tint**: a dashed baseline at the visible range's
  opening equity (starting balance in All), with a faint `--pos-soft` wash
  above and `--neg-soft` below, drawn by a series primitive behind the
  candles. It moves with the range, answering the same question as the
  readout.

### 6. API

**One clock.** Equity candles are bucketed on the New York wall clock
(`equity_candles.py:3-6`). Every `mode=range` window is therefore a run of
**whole New York buckets**: Range uses the in-window candles' bucket edges
(§4), and presets 5D…1Y snap `from` to the New York day start that the
preset reaches back to and `to` to the end of the current bucket. So the KPI
window, the readout and the baseline always cover the same buckets. **1D is
the one exception:** it stays `mode=today`, the Berlin day, exactly as the
Today toggle behaves now. Its KPI window and the New York day candles under
it are offset by the six-hour gap between the zones, which the spec accepts
rather than changing Today's long-standing meaning.

**`GET /equity/candles`** gains `before` and the response gains
`has_more: bool`.
- `before` accepts exactly the `t` format the endpoint emits for that `tf`:
  an ISO date for 1D/1W (read as that New York bucket's start), an ISO
  datetime with offset for 1H/4H. Any other shape is a 400. The client sends
  its oldest candle's `t` back unchanged, so the cursor always round-trips.
- Exclusive: candles whose bucket start is strictly before the cursor's
  instant. Comparison is on aware instants, so the repeated 01:00 hour on
  the November fall-back day (kept distinct by `fold`) and the skipped hour
  in March page correctly.
- The server builds the full series as today and slices it. `o`, `change`
  and `change_pct` therefore come from the full history (a realised page's
  first `o` is the true prior balance), and `has_more` is computed on the
  series before slicing.
- Without `before`, behaviour is unchanged (newest `limit`). Both bases.
  Paging at the database is out of scope.

**`GET /dashboard?mode=range&from=<ISO>&to=<ISO>`**: a fourth mode beside
`active` / `today` / `all`.
- Both bounds required, timezone-aware, `from ≤ to`; anything else is a 400,
  like an unknown `mode`.
- **One window object threads through every place `mode` is read today**
  (`dashboard.py`: `_scope()`/`_SCOPES`, the `scoped_raw` predicate,
  `_lifecycle_counts`, `_realized_parts` for both the main and the weak
  ledger). Each gets `window: (from, to) | None` alongside or in place of
  the `mode` string, and none of them may fall through to the "today"
  branch for `range`. A test asserts each path honours the window.
- **Extracted, not inlined:** range parsing and validation go into a helper
  (`_parse_range_window`), trade selection into `_scope_trades(window)`.
  `dashboard()` is a legacy function already at complexity 21 (baselined in
  `scripts/dev/complexity_baseline.json`); it must not rise, and the
  extraction is expected to lower it. Every new helper is < 15. The plan
  records the figure before and after and shrinks the baseline with
  `--update`.
- Closes count when `from ≤ closed_at < to`, comparing aware instants;
  stored `closed_at` values are normalised to UTC first, as
  `is_today_berlin` already does.
- Win rate, expectancy, payoff, realised P&L and lifecycle counts use those
  closes. Point-in-time figures (balance, Open P&L, open trades, risk used)
  stay "now". The Realised card label becomes "Realised in range".
- **The Closed tab** does not read `/dashboard`. It queries `/trades`
  through `TradesStore.setQuery` with a boolean `today` filter (the row's
  `today` comes from `_in_today_scope`, `trades.py:189`). `/trades` gains
  `closed_from` / `closed_to` (aware ISO, same `[from, to)` rule and
  validation as `mode=range`), and the Closed tab sends them in Range and
  the 5D…1Y presets in place of `today`. This is Part 2 only; Part 1 touches
  neither `dashboard.py` nor `trades.py`.

**Scope → request mapping (client):** 1D → `mode=today`; All → `mode=all`;
5D / 1M / 3M / 6M / YTD / 1Y / Range → `mode=range` with New York
bucket-edge bounds as above. Rolling presets recompute on each scan refresh,
but because `to` snaps to the current bucket's end, the window changes only
when a new bucket opens. KPIs don't flicker between refreshes inside one
bucket.

### 7. Where the logic lives

The chart components only wire events to pure functions, so each piece is
unit-testable without a chart and stays well under complexity 15. The
functions live in a new `equity-range.model.ts` beside
`equity-candles.model.ts`:

| Function | Does |
|---|---|
| `inWindowCandles(logicalRange, candles)` | the whole buckets in view (§4) |
| `windowBounds(candles)` | `{from, to}` instants from those buckets |
| `rangeStats(candles)` | equity change, high, low, max drawdown (§4) |
| `presetBounds(preset, now)` | New York bucket-edge bounds per preset (§6) |
| `scopeToRequest(scope)` | `mode`, `from`, `to` query params |
| `nextTimeframe(barCount, tf)` | step up, step down, or stay (§3) |
| `pnlTone(...)` helpers | the §5 colour rules |

State ownership:
- **`DashboardStore`**: scope (preset or Range plus window), the KPI
  `stale` flag, and the debounced refetch with its latest-request guard.
- **`EquityCandlesStore`**: loaded pages, `has_more`, the page-error note,
  and `atLiveEdge` for the "↦ Latest" control.
- **`sb-equity-candles`** keeps only the chart handle and the
  programmatic-move flag, a boolean set around its own `setVisibleRange` /
  timeframe calls and checked in the range-change handler.

### 8. Data flow

- Pan → visible logical range → time window → `DashboardStore.setRange`,
  debounced ~300ms after the gesture settles → refetch KPIs and Closed tab.
  A stale response is dropped by the latest-request guard (same pattern as
  `EquityCandlesStore`).
- Preset → store sets scope → chart pages in history if needed →
  `setVisibleRange` under the programmatic flag.

### 9. Errors and edge cases

- **History page fails**: loaded candles stay; a small "Couldn't load earlier
  history · Retry" note at the left edge; the next pan retries. Never blanks
  the chart.
- **Range refetch fails**: KPIs keep their last values, dimmed, with a stale
  hint; the Range chip stays. First-load error flow unchanged.
- **No closes in range**: cards show "—" with "none closed in range" (the
  existing "none closed today" hint, generalised).
- **Scan refresh while viewing the past**: the viewport is not snapped to
  now; a "↦ Latest" control returns to the live edge.

## Testing

**Backend (pytest)**, in the suites that already own these endpoints:
- `/equity/candles`:
  - `before` exclusivity and boundaries, empty page, `has_more` true/false
    (computed before slicing), both bases.
  - The cursor round-trips for every `tf` (date and offset forms); any other
    `before` shape is a 400.
  - DST: paging across the November fall-back (repeated hour) and the March
    spring-forward (skipped hour) on 1H/4H loses or duplicates no candle.
  - A realised page's first `o` equals the previous page's last `c`.
- `/dashboard?mode=range`:
  - 400s: missing bound, naive timestamp, `from > to`.
  - A close exactly at `from` counts; one exactly at `to` does not.
  - Each `mode` consumer (`scoped_raw`, `_lifecycle_counts`, both
    `_realized_parts` calls) honours the window: one test each, so none can
    fall through to "today".
  - Parity: a window of Berlin local midnight to the next local midnight
    (built from local midnights, not +24h, so the 23h and 25h DST days hold)
    gives figures identical to `mode=today`. A window covering all history
    gives figures identical to `mode=all`.
  - The Closed tab filter agrees with the KPIs.
  - `dashboard()`'s complexity is recorded before and after; it does not
    rise above its baseline of 21.
- `/trades?closed_from=&closed_to=`: the same boundary and 400 cases, and
  agreement with `/dashboard?mode=range` over one window.

**Frontend (spec files)**, as plain unit tests of the §7 functions where
possible:
- `inWindowCandles` / `windowBounds`: partly visible edge candles count
  whole; bounds sit on bucket edges.
- `rangeStats`: change from first `o` to last `c`; drawdown null on a peak
  ≤ 0; a flat window gives 0 drawdown.
- `presetBounds`: every preset snaps to New York bucket edges, including
  across DST changeovers and YTD on 1 Jan; `to` is stable within a bucket.
- `nextTimeframe`: the `250 / ratio > 15` invariant over every adjacent
  pair; centre preserved; edge-of-history hold.
- Breakeven pair: the ±0.5 pp band, payoff ≤ 0, fewer than 5 closes.
- Programmatic-move guard: a preset click or timeframe step never yields
  Range.
- History paging: request shape, prepend merge, superseded page dropped,
  failure note.
- Colour rules: sign, breakeven pair, risk thresholds, dash uncoloured.
- Dropdown below 640px, chips above.

**Visual:** Playwright against a local instance at 375 / 768 / 1280px, light
and dark, per `ui-design.md`; every new colour pairing passes the token
contrast gate.

## Decomposition

One spec, one plan in two parts:

1. **Chart and colour**: `before`/`has_more`, history paging, auto
   timeframe, readout range stats and caption, palette, baseline tint, card
   tints. It touches `equity.py` but not `dashboard.py`, and ships alone.
2. **Range scope**: `mode=range` with the window threaded through
   `dashboard.py`, the Closed tab window, the preset control and phone
   dropdown, the "now" sub-labels, and the two-way link.

## Out of scope

- Database-level paging of equity samples.
- Scoping point-in-time figures (balance, open P&L, risk used) to a past
  window.
- Drawing tools, indicators or compare overlays on the equity chart.
- Retiring the unused `equity_30d` series (already a separate change, v172 § 4).

## Panel review

Run 2026-10-21 against the spec as first committed. Roles:
financial-advisor, senior-engineer, quant-engineer.

**Blocking findings**
- financial-advisor 1: range figures not labelled paper, pre-cost, pre-tax.
  -- applied: "Paper trades · before costs and tax" caption (§4).
- senior-engineer 1: `mode` is read in `scoped_raw`, `_lifecycle_counts`,
  the weak-ledger `_realized_parts` and `_scope()`, not only the main
  `_realized_parts`, so a range could fall through to "today". -- applied:
  one window object through every consumer, one test each (§6, Testing).
- senior-engineer 2: `dashboard()` would cross complexity 15. -- applied:
  `_parse_range_window` and `_scope_trades` extracted; complexity recorded
  before and after (§6).
- senior-engineer 3: the guard and paging logic had no testable home. --
  applied: pure functions in `equity-range.model.ts`; store ownership named
  (§7).
- quant-engineer 1: candles use the New York clock while presets used
  Berlin midnight. -- applied: range windows are whole New York buckets;
  1D keeps the Berlin day as Today does, with the offset stated (§6).
- quant-engineer 2: start/end of "change" and partly visible candles were
  undefined; mark-to-market change and realised P&L were conflated. --
  applied: first `o` to last `c` over whole in-window buckets; the two
  figures are labelled apart (§4).
- quant-engineer 3: 1D/1W `t` is a date, so the paging cursor would have
  hit the naive-timestamp 400; also DST, `has_more` before slicing, and
  realised `o` on a page. -- applied: `before` accepts the emitted `t` form
  per `tf`, with aware comparison, full-series slicing and DST tests (§6).

**Advisory findings**
- financial-advisor 2: breakeven ignores friction; tiny N makes colour
  noise. -- applied: neutral below 5 closes; friction stated in the caption
  (§5).
- financial-advisor 3: make Expectancy the visually primary card. --
  rejected: card order and weight are v85 D9's deliberate triple and
  outside this spec's scope. Expectancy keeps its sign colour.
- financial-advisor 4: label drawdown "within range". -- applied (§4).
- financial-advisor 5: point-in-time cards inside a past range need a "now"
  label. -- applied (§5).
- financial-advisor 6: tax drag of turnover next to YTD/1Y Realised. --
  applied via the §4 caption ("before costs and tax").
- senior-engineer 4 and quant-engineer 8: hysteresis rule ambiguous. --
  applied: the `250 / ratio > 15` invariant, tested over every adjacent
  pair (§3).
- senior-engineer 5: tie-break and seam across pages. -- applied, merged
  with quant-engineer 3.
- senior-engineer 6: 1D uses `mode=today` while other presets use `<` on
  `to`. -- applied: 1D's Berlin-day exception is stated; presets snap `to`
  to a bucket end (§6).
- senior-engineer 7: which store owns `stale` and `atLiveEdge`. -- applied
  (§7).
- senior-engineer 8 and quant-engineer 5: breakeven-pair duplication and
  edge cases. -- applied: one frontend helper, a ±0.5 pp neutral band,
  payoff ≤ 0 neutral (§5).
- senior-engineer 9: keep Part 1 shippable. -- applied (Decomposition).
- quant-engineer 4: drawdown misses intra-candle lows and can divide by a
  zero peak. -- applied: % of the running peak on closes, null on a peak
  ≤ 0, and the difference from High/Low stated (§4).
- quant-engineer 6: `closed_at` normalisation and DST-safe today parity. --
  applied (§6, Testing).
- quant-engineer 7: rolling presets flicker. -- applied: `to` snaps to the
  current bucket end (§6).
