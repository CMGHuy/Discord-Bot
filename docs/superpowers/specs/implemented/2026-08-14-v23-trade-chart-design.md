# The trade chart — one interactive chart, fully annotated (v23)

**Version:** ui 1.2.3 · bot 1.1.2
**Bump:** two lines, graded separately.
**`ui` minor** — the chart is the thing a user looks at every day, and after
this it is a different chart: it carries the trendline and its pivots, both
overlays, a legend, and indicator controls that persist. Someone who used it
yesterday has to look at it anew, which is the shape of a minor.
**`bot` patch** — a new persisted field and one changed input to
`generate_trade_chart()`. The alerts it posts look the same; only where the
trendline comes from changed.
**Date:** 2026-08-14
**Status:** approved, not yet implemented
**Upholds:** `2026-08-08-v15-jinja-cutover-design.md` Decision 3 — the PNG chart
routes stay deleted. This spec restores the *annotations*, not the image route.

---

## Why this exists

The Jinja trade detail page showed the **generated PNG** as its primary chart
(`trade_detail.html:19-24`, `url_for('trade_chart_image', …)`), with the
interactive chart demoted to a `<details>` disclosure below it. Release B
(`8bfd050`) deleted the templates and those image routes on 2026-08-14, and the
SPA kept only the interactive chart.

What was lost is not the image. It is what the image drew:

| Annotation | PNG | SPA today |
|---|---|---|
| Plan levels with right-axis price tags | yes | **yes** — `plan-lines.ts` |
| Risk / reward bands | yes | **yes** |
| The confirming method's geometry | yes | **yes** — `strategy-overlay.ts`, from the same `chart_geometry.py` |
| MACD / RSI / Keltner / volume profile | yes | **yes** |
| **The trendline** | yes | **no** — never sent |
| **Its swing pivots as diamonds** | yes | **no** |
| **Both sides' overlays** | yes | **no** — one, target preferred |
| **The legend block and fit notes** | yes | **no** |

The SPA chart is much closer to complete than "the chart is missing" suggests —
but the four gaps are the parts that say *why the trade exists*, and one of them
fails silently: a trade confirmed only by a trendline renders with **no overlay
at all**.

The trendline's absence is deliberate and reasoned. `market.py:316`:

> `trend_info` is deliberately left unset. `generate_trade_chart()` fits the
> trendline pair once, before it decides its display window (the window is then
> expanded to fit the line's own touches); re-fitting here would be a second
> source of truth for the same line.

That reasoning is correct and this spec does not overturn it. It removes the
condition that made it necessary.

---

## Decisions

### Decision 1 — enrich the interactive chart; no PNG in the SPA

The annotations come back inside `lightweight-charts`, not as a restored image
route. This upholds v15 Decision 3 rather than reversing it.

The PNG keeps its one real job — the image attached to a Discord alert, where
there is no canvas to be interactive on.

### Decision 2 — one chart component

`PriceChart` (`ui/price-chart.ts`, watchlist ticker detail) and `TradeChart`
(`ui/chart/trade-chart.ts`, trade detail) merge into a single component that
renders everything: candles, volume, the indicator panes, the volume profile,
plan levels, bands, overlays and the legend.

Two charts in one app that behave differently is the same inconsistency the
alignment work (`v22`) exists to remove. A ticker chart should not be a lesser
widget; it should be the same chart with no plan attached.

Plan levels, bands and overlays are simply absent when there is no trade —
`plan-lines.ts` already treats a null level as undrawn rather than drawn at
zero, and that rule extends to the whole plan layer.

### Decision 3 — one endpoint, keyed by ticker

```
GET /api/v1/market/chart/{ticker}?trade_id=<id>&window=<bars>
```

Returns the full payload always — bars, indicators, volume profile — and adds
`levels` plus `overlays` when `trade_id` is present and resolves.

This follows the precedent `/market/ohlcv/{ticker}` already set with its optional
`trade_id` for levels, and it is the shape a single component needs: keyed by
trade, an endpoint cannot serve a ticker that has no trade.

**One time type: epoch seconds.** Today `Candle.t` is a `YYYY-MM-DD` string and
`ChartBar.t` is an epoch — `models.ts:709` warns that mixing them is how an
overlay lands a year away from its candle. The merged payload uses epoch
seconds throughout, and `Candle` retires with the endpoint that produced it.

`/market/ohlcv/{ticker}` and `/market/chart/{trade_id}` are both replaced. No
deprecation window: the SPA is the only consumer, and it ships in the same
image.

`window` keeps its current contract — default 120, valid 20–500, out of range is
a 400 rather than a clamp.

### Decision 4 — the trendline fit is persisted on the trade

Fitted **once, when the plan is created**, and stored on the trade record:

```json
"trendline_fit": {
  "slope": -0.42, "intercept": 214.8,
  "points": [{"t": 1751500800, "price": 198.4},
             {"t": 1754784000, "price": 184.2}],
  "label": "descending resistance",
  "side": "target",
  "lookback": 120,
  "fit_at": "2026-08-14T18:22:04Z"
}
```

Both renderers read it. There is one fit, so there cannot be two answers.

**This is a stronger guarantee than the PNG has today.** A fit recomputed at
render time drifts as new bars arrive: open a six-week-old trade and you see the
line today's data supports, not the line the plan was made on. Persisting it
means the chart shows the reasoning the decision actually rested on — which is
the whole point of looking at an old trade — and it is consistent with the
NO-LOOKAHEAD rule the scan pipeline already holds itself to.

It is a data-model change to `data/*.json`, and by the rules in
`working-conventions.md` an *additive* one: absent on old records, and the code
must never require it. That is Decision 5.

### Decision 5 — legacy trades are fitted on read, then written back

A trade with no `trendline_fit` gets fitted once, when its chart is first
requested, and the result is persisted. Lazy backfill.

Every trade gets a line; old records converge on the new model without a
migration step; and each one is still fitted exactly once and never again. The
alternative — a one-off backfill script — fits every historical trade against
*today's* data, which is precisely the re-fit Decision 4 exists to avoid, and
needs a network fetch per ticker to do it.

The write happens on a GET, which is worth naming rather than hiding: it is a
cache fill, it is idempotent, and a failed write degrades to "fitted again next
time" rather than to an error.

### Decision 6 — the PNG reads the stored fit

`generate_trade_chart()` consumes `trendline_fit` instead of fitting its own.
The Discord image and the SPA chart draw the identical line, which is what
persisting it was for.

Its display-window logic is unchanged — it still expands the window to fit the
line's touches. It reads the line's endpoints from the record rather than from a
fit it performed, so the geometry is shared and the framing stays local.

This touches the alert path that posts on every scan, so it carries the heaviest
test coverage in the plan: an existing trade with a stored fit, one without
(backfill path), and one whose fit is unfittable.

### Decision 7 — both overlays, target emphasised

The endpoint returns `overlays: ChartOverlay[]` — the primary confirming method
per side rather than one for the whole chart. The target-side overlay draws at
full strength, the stop-side dimmed.

A trade's thesis has two halves: what it is aiming at, and what invalidates it.
Showing only the first is showing half the reasoning. The strength hierarchy is
what keeps two geometries on one pane readable.

`ChartOverlay` itself is unchanged — it already carries `side`, so this is a
count change, not a shape change.

### Decision 8 — an on-canvas legend, TradingView style

A legend block in the chart's top-left corner: the ticker and horizon, the
crosshair's OHLC readout, the drawn methods with their colour keys, and the fit
notes — which two dates a trendline connects, what range a fib was measured
between, the ADX trend strength. The same strings `_trendline_note_lines()` and
`_fib_note_lines()` compute for the PNG, shipped in the payload so the two
cannot disagree.

**This reverses a standing decision and the reversal is on the record.**
`strategy-overlay.ts` states "No text" as a rule, on the grounds that drawing
text on the canvas means re-solving font tokens, DPR scaling and label collision
inside a primitive — all of which remain true and are now costs this spec
accepts. The comment must be rewritten in the same commit that breaks it, not
left contradicting the code.

Consequences to build deliberately: font tokens read through `chart-theme.ts`'s
existing `token()` helper rather than hardcoded; DPR handled at the primitive
level as `box-primitive.ts` already does; and the block clamped so it never
covers candles at narrow widths.

### Decision 9 — TradingView conventions, this app's palette

`lightweight-charts` *is* TradingView's library, so the conventions come
naturally: the top-left legend that follows the crosshair, magnet crosshair
snapping to candles, price tags on the axis, panes with draggable separators.

The colours stay the app's own tokens. Adopting TradingView's `#26a69a`/`#ef5350`
would mean hex outside `tokens.css` — against a documented rule — and a chart
whose up/down colours disagree with the P&L colours in the table beside it. The
valence rule (a hue means a meaning) is worth more than palette familiarity.

### Decision 10 — indicators are on by default, toggleable, remembered

Every pane and overlay renders by default. A control hides individual panes
(MACD, RSI), overlays (Keltner, volume profile) and the plan layer, and the
choice persists.

The app already does exactly this for tables — `ui/table-prefs.ts` and
`ui/column-picker.ts` — so this is an established pattern reused, not new
machinery. Not remembering the choice makes the control useless: you re-hide the
same pane on every navigation until you stop using it.

---

## Architecture

**Python.** The trendline fit moves out of `generate_trade_chart()` into a
function both callers use; `chart_geometry.py` gains a shape built from a stored
fit rather than a computed one; `market.py`'s chart endpoint is re-keyed and
returns both overlays and the legend note strings; the trade record gains
`trendline_fit`, written at plan creation and on lazy backfill.

**Frontend.** One chart component under `ui/chart/`, with `price-chart.ts`
deleted; a legend primitive beside the existing box/marker/polyline primitives; a
prefs store following `table-prefs.ts`; `ticker-detail.ts` and `trade-detail.ts`
updated to the single component; `Candle`, `OhlcvResponse` and `TradeLevels`
retired from `api/models.ts` with `ChartBar` and `ChartLevels` as the survivors.

---

## Phases

**Phase 1 — the fit.** Extract the fit; persist it at plan creation; lazy
backfill on read; `generate_trade_chart()` reads it. Ends with the Discord PNG
drawing from stored geometry, SPA untouched.

**Phase 2 — the endpoint.** Re-key to ticker; merge the payloads onto epoch
seconds; both overlays; the trendline shape; legend note strings. Ends with the
old routes deleted.

**Phase 3 — one component.** Merge the two charts; delete `price-chart.ts`;
update both call sites.

**Phase 4 — legend and prefs.** The legend primitive and the TradingView
conventions; the indicator toggles and their persistence.

---

## Parallelisation

- **Sequential: Phase 1 → Phase 2 → Phase 3 → Phase 4.** This is a chain and
  saying so is worth as much as a wide group. Phase 2's payload carries the
  geometry Phase 1 persists; Phase 3 consumes Phase 2's payload shape; Phase 4
  draws what Phase 3's component owns. Nothing here is parallel across phases.
- **Within Phase 1 — parallel:** the fit extraction and the record-schema change
  are separate files (`swingbot/core/charts/`, the trade store) and neither
  consumes the other's symbols. **Sequential after both:** the plan-creation
  write, the backfill path, and `generate_trade_chart()`'s switch to reading —
  all three consume the extracted function *and* the new field.
- **Within Phase 2 — sequential.** Every task edits `market.py` and
  `api/models.ts`. Disjoint-files fails; do not dispatch these concurrently.
- **Within Phase 3 — sequential.** The merge, then the two call sites, then the
  deletion; the call sites consume the merged component's inputs.
- **Within Phase 4 — parallel:** the legend primitive
  (`ui/chart/primitives/`) and the prefs store (`ui/`) share no file and no
  symbol. **Sequential after both:** wiring them into the chart component.
- **Parallel with all of it: `v22`.** The two specs share no file. `v22` is
  frontend layout; the only frontend files this spec touches are under
  `ui/chart/` and the two workspace files' chart sections, neither of which
  `v22` converts.

---

## Testing

- **Python:** the extracted fit is deterministic for a fixed frame; a trade with
  a stored fit is not re-fitted; a trade without one is fitted and written back
  exactly once; an unfittable trade yields no trendline and no error; the PNG
  draws the stored line. `python scripts/testrun.py full` is the gate — the
  alert path is in scope.
- **Frontend:** the merged component renders without a plan (ticker case) and
  with one; both overlays draw with the target emphasised; an unknown shape kind
  still draws nothing and does not throw; prefs survive a remount; the legend
  clamps rather than covering candles at the narrow breakpoints.
- **Payload:** every `t` in a response is an epoch integer — the one assertion
  that would have caught the string/epoch mix at the source.

---

## Risks

- **The alert path.** Phase 1 changes where the Discord image gets its trendline.
  A regression here is user-visible on every scan. This is why Phase 1 lands
  alone, with the PNG reading stored geometry and nothing else changed.
- **The data-model change.** `trendline_fit` must stay optional in code forever;
  a reader that requires it breaks every trade written before today. Per
  `working-conventions.md` this is additive and therefore not a major bump — but
  only for as long as it is genuinely optional.
- **Writing on a GET.** Decision 5's backfill mutates on read. It must be
  idempotent and must degrade to a no-op on failure, never to a 500.
- **The legend reverses a documented rule.** If font/DPR/collision handling in a
  canvas primitive proves worse than expected, the fallback is a positioned HTML
  overlay — TradingView's own technique — which gets the same look without the
  canvas text machinery, and costs only the legend's positioning code.
