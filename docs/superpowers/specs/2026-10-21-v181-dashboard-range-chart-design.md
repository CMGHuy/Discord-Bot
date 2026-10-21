# v181 — Dashboard range chart: zoom and pan re-scope the trading performance panel

**Version:** ui 1.33.0 · bot 2.14.1 (at writing)
**Bump:** ui minor — the Dashboard's equity chart pages history, changes timeframe on zoom and drives the KPI scope, and every P&L figure changes colour; bot patch — two additive query parameters (`before` on `/equity/candles`, `mode=range` on `/dashboard`) that no existing caller sends.
**Edge:** none (integrity) — a display and analysis tool; no alert, plan, stop or fill changes.
**Screen:** exempt (integrity)
**Panel:** financial-advisor, senior-engineer, quant-engineer
**Status:** spec written 2026-10-21 from a brainstorm with the partner. Scope (all four range behaviours plus colour), the two-way scope link, the full TradingView preset set with a phone dropdown, and all four colour treatments were the partner's choices in chat.

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
- Hysteresis: after a step up, the step-down threshold for the new timeframe
  applies only once the visible bar count falls below 15 on *that* timeframe
  (the counts differ by the timeframe ratio, so a single zoom cannot bounce).
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
- No hover: a summary of the visible range — start→end change in % and money,
  high, low, max drawdown (peak-to-trough of candle closes inside the window),
  each coloured per §5.

### 5. Profit/loss colour

One rule: `--pos` = good for the account, `--neg` = bad, `--text-secondary`
= neutral or no data. An em dash is never coloured.

| Figure | Rule |
|---|---|
| Readout change, range change, Open P&L, Realised, Expectancy | sign |
| Max drawdown | `--neg` when non-zero |
| Win rate **and** payoff ratio, as a pair | `--pos` when win rate > `1 / (1 + payoff)` (they clear breakeven together), else `--neg`; neutral if either is null |
| Risk used | neutral < 75% of cap, warning token 75–100%, `--neg` at/over cap |
| Avg confidence, Open trades | neutral |

Win rate and payoff are judged as a pair on purpose: alone, a 0.8 payoff on a
65% win rate would read red on a profitable book.

- **KPI cards**: the card background takes `--pos-soft` / `--neg-soft` with
  its figure's colour; neutral cards stay plain. The phone summary rows take
  the same tint.
- **Stronger candle palette**: new, more saturated palette primitives
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

**`GET /equity/candles`** gains `before=<ISO timestamp>` (exclusive: candles
whose bucket starts before it) and the response gains `has_more: bool`.
Without `before`, behaviour is unchanged (newest `limit`). An unparseable or
naive `before` is a 400. Both bases. The server still builds the full series
and slices; at current data size that is fine, and paging at the database is
out of scope.

**`GET /dashboard?mode=range&from=<ISO>&to=<ISO>`** — a fourth mode beside
`active` / `today` / `all`. Both bounds required, timezone-aware, `from ≤ to`;
anything else is a 400, like an unknown `mode`. Win rate, expectancy, payoff,
realised P&L and the lifecycle counts use closes with `from ≤ closed_at < to`
— the same partial-close parts `_realized_parts` uses for `today`, generalised
from "Berlin today" to an explicit window. Point-in-time figures (balance,
Open P&L, open trades, risk used) stay "now". The Realised card label becomes
"Realised in range". The Closed tab's query takes the same window.

**Scope → request mapping (client):** 1D → `mode=today`; All → `mode=all`;
5D / 1M / 3M / 6M / YTD / 1Y / Range → `mode=range` with bounds computed
client-side from Berlin midnight (presets) or the visible candles (Range:
first visible candle's open to last visible candle's close). Presets anchored
on now roll forward on each scan refresh, as Today does.

### 7. Data flow

- Pan → visible logical range → time window → `DashboardStore.setRange`,
  debounced ~300ms after the gesture settles → refetch KPIs and Closed tab.
  A stale response is dropped by the latest-request guard (same pattern as
  `EquityCandlesStore`).
- Preset → store sets scope → chart pages in history if needed →
  `setVisibleRange` under the programmatic flag.

### 8. Errors and edge cases

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
- `/equity/candles`: `before` exclusivity and boundaries, empty page,
  `has_more` true/false, both bases, 400 on bad `before`.
- `/dashboard?mode=range`: 400s (missing bound, naive timestamp, `from > to`);
  a close exactly at `from` counts and exactly at `to` does not; a window
  equal to Berlin today gives figures identical to `mode=today`; a window
  covering all history equals `mode=all`; the Closed tab filter agrees.

**Frontend (spec files):**
- Visible logical range → time window.
- Preset → bounds, including the Berlin DST changeovers and YTD on 1 Jan.
- Auto-timeframe thresholds and hysteresis (no oscillation across a zoom
  sequence); centre preserved; edge-of-history hold.
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

1. **Chart and colour** — `before`/`has_more`, history paging, auto
   timeframe, readout range stats, palette, baseline tint, card tints.
   Shippable alone.
2. **Range scope** — `mode=range`, Closed tab window, preset control and
   phone dropdown, the two-way link.

## Out of scope

- Database-level paging of equity samples.
- Scoping point-in-time figures (balance, open P&L, risk used) to a past
  window.
- Drawing tools, indicators or compare overlays on the equity chart.
- Retiring the unused `equity_30d` series (already a separate change, v172 § 4).
