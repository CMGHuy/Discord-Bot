# Chart primitive spike — SR34, the risk gate

**Verdict: PASS. Proceed to SR35. SR37–SR39 use `box-primitive.ts` as their
template.**

`lightweight-charts` 5.2.1 has no shape support of its own, so every overlay in
Phase 3 depends on the v5 series-primitive API being able to draw arbitrary
geometry anchored in price/time space. This spike answers that question before
SR32 refactors code the bot depends on — the plan puts SR34 third, but it is
blocked only by Phase 2, and running it first is the whole point of calling it
a gate.

## The API

`ISeriesPrimitive`, attached with `series.attachPrimitive(p)`:

| Member | Role |
|---|---|
| `attached({ chart, series })` | hands over the two objects every coordinate conversion needs |
| `paneViews()` | returns view objects the library asks for each frame |
| `view.zOrder()` | `'bottom'` draws behind the candles — right for a zone |
| `view.renderer().draw(target)` | the actual painting, in **bitmap** space |
| `detached()` | drop the references |

Coordinates come from `chart.timeScale().timeToCoordinate(time)` and
`series.priceToCoordinate(price)`, **converted inside `draw`, once per frame.**
Converting at construction is the obvious optimisation and it is wrong: the
mapping changes on every pan and zoom, so a cached coordinate is correct
exactly until the user touches the chart.

Both converters return `null` for a value outside the visible range. That is
the ordinary state of a shape scrolled off screen, not an error — the renderer
skips the frame. Drawing at `NaN` blanks the canvas.

## Measured

200 synthetic daily bars, a box spanning bars 40–80 and prices 96–108,
Chromium at 1100×700.

| Question | Result |
|---|---|
| Draws on attach | **yes** |
| At the right coordinates | **yes** — drawn CSS x/y `170, 106`, expected `170, 106`, exact |
| Stays anchored while panning | **yes** — moved, and matched `timeToCoordinate` after the pan |
| Rescales on zoom | **yes** — width changed with the range |
| Survives `series.setData` | **yes** |
| Redraw cost, 500 bars | 60 frames in 998 ms — **16.63 ms/frame** |
| Console errors | none |

The 16.63 ms is one vsync interval at 60 Hz, so the measurement is bounded by
`requestAnimationFrame` and not by the drawing: the primitive's own cost is
below what this method can resolve. A 500-bar chart with a shape on it is not
near a frame budget.

## The trap worth knowing

**`window.devicePixelRatio` is not the ratio to draw with.** In this run DPR
was `1.0` while the library handed the renderer `horizontalPixelRatio: 1.5` and
`verticalPixelRatio: 1.5012…`. They are different numbers, and the library's is
the authoritative one — it accounts for the canvas's own bitmap sizing, which
is not always the display's.

Using DPR instead would draw every shape at two thirds scale on this
configuration, and correctly on a machine where the two happen to agree —
which is the worst kind of bug, since it looks fine wherever it was written.
`useBitmapCoordinateSpace` supplies both ratios; use them and nothing else.

Note the vertical and horizontal ratios are not equal (`1.5` vs `1.5012…`), so
they cannot be collapsed into a single scale factor either.

## Consequences for SR37–SR39

- The template is `paneViews()` → `renderer()` → convert-then-draw, per frame.
- Multi-segment shapes (`trendline`, `fib_fan`, `curve`) are the same shape of
  problem: convert each point inside `draw`, skip the frame if any conversion
  is `null`, scale by the supplied ratios.
- `zOrder: 'bottom'` for zones, `'normal'` for anything read precisely against
  a candle.
- The fallback design named in step 4 — a positioned `<canvas>` synchronised by
  hand — is **not needed** and should not be built.
