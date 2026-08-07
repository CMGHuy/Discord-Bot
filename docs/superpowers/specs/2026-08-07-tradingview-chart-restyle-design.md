# TradingView Chart Restyle — Design Spec

**Date:** 2026-08-07 · **Status:** Approved (brainstormed + user-approved in session)
**Implementation plan:** `docs/superpowers/plans/2026-08-07-tradingview-chart-restyle-v10.md`

## 1. Goal

Make the generated static trade-plan PNG (`swingbot/core/charts/trade_chart.py`,
mplfinance) read like the admin UI's interactive chart
(`swingbot/admin/static/chart-init.js`, lightweight-charts 4.x), while keeping
every indicator and annotation it renders today.

The palette is **not** the gap. `chart_style.py` already uses TradingView's dark
theme (`#131722` background, `#26a69a`/`#ef5350` candles) and
`test_chart_theme.py` pins it to `admin/static/tokens.css`. The gap is layout
and annotation convention — *where* information sits, not what is shown.

Success criteria:

1. No empty background band below the bottom pane.
2. Exactly one price ladder, on the right.
3. Volume and Volume Profile both render inside the price pane.
4. The centered title and the boxed matplotlib legend are replaced by one
   top-left legend block.
5. Level names/prices read off the line and the right axis, not floating pills.
6. Every indicator, overlay, chip and stat visible today is still visible.
7. Full suite green; no change to any scoring, level, or trading logic.

## 2. Baseline — the eight deviations

Measured against `exports/trade_charts/KLAC_84ab7e58.png` and `chart-init.js`:

| # | Static chart today | Interactive chart |
|---|---|---|
| 1 | ~20% of the image is empty below the RSI pane | panes fill the frame |
| 2 | Price ladder printed twice (left VP panel + right axis) | one right axis |
| 3 | VP is a detached left panel with its own ladder | overlaid in the price pane |
| 4 | Boxed matplotlib legend | compact top-left legend |
| 5 | Level names as large filled pills in the plot area | line title + right-axis tag |
| 6 | Volume is its own pane with a `Volume 10⁶` label | translucent overlay, bottom |
| 7 | Big centered bold title | top-left symbol line |
| 8 | Dashed grid on both axes | faint solid hairlines |

Items 1, 2 and 6 are defects rather than style choices: dead space wastes the
frame, and the duplicate ladder is a direct consequence of the VP panel owning
its own axis.

## 3. Panel architecture

Today (`trade_chart.py:396-421`), plus a manually-placed left panel:

```
panel 0  price   ratio 4      figsize=(13.5, 7.0 | 9.5 | 11.0)   <- fixed heights
panel 1  volume  ratio 0.9
panel 2  MACD    ratio 1.5
panel 3  RSI     ratio 1.2
left     VP panel, VOLUME_PROFILE_PANEL_WIDTH_FRAC = 0.15 of figure width
```

After:

```
panel 0  price + volume overlay + VP overlay   ratio 6
panel 1  MACD                                  ratio 1.5
panel 2  RSI                                   ratio 1.2
figure height DERIVED from sum(panel_ratios)
```

Volume moves in through mplfinance's `volume_panel=0`, on a secondary y-axis,
with scale margins putting it in the bottom ~18% — mirroring `chart-init.js:38`
(`scaleMargins {top: 0.82, bottom: 0}`). **Verified working** against the pinned
mplfinance `0.12.10b0`; `volume_panel` and `tight_layout` are both supported.

The three hardcoded `fig_height` constants are replaced by a height derived from
the panel ratios actually in use. That fixes the dead space at its cause: the
constants were tuned for a 4-panel layout and do not follow when a pane is
absent.

## 4. Annotation systems

**Top-left legend** (new) replaces both the centered title and the boxed legend
at `trade_chart.py:431`:

```
KLAC  2-month swing  SHORT
O 235.55  H 240.12  L 231.08  C 235.55   Vol 21.4M
EMA35   Fib 38.2%   KC (EMA20 ±1.5×ATR)   VP POC 247.06
```

Line 3 is what makes deleting the boxed legend safe — it names every overlay
drawn. The existing stat strip (`T1 / SL / R:R / T2 / RSI / ADX / MACD`) stays
as its own row: R:R and ADX have no TradingView counterpart and are genuinely
this bot's own output.

**Right-axis price tags** replace the pills. The matplotlib equivalent of
lightweight-charts' `createPriceLine`: `annotate` with
`xycoords=('axes fraction', 'data')` anchored at x=1.0, so the tag sits in the
axis gutter *outside* the plot area. The short name (`SL`, `Entry`, `TP1`,
`TP2`) anchors at the line's left end, matching `chart-init.js:8-12`, which
passes both a `title` and `axisLabelVisible: true`.

Tag font is set one step larger than TradingView's, deliberately: these PNGs are
read in Discord on a phone, where the image is downscaled.

The existing `MIN_LABEL_GAP_FRAC` collision-avoidance still applies — tags
overlap when two levels sit close, exactly as pills did.

**Volume Profile overlay** — `barh` on the price axes using a blended transform
(width in axes coordinates, y in data coordinates), bars growing leftward from
the right edge at low alpha, POC still highlighted.
`chart_volume_profile._draw_volume_profile_panel` keeps its binning maths
(`VOLUME_PROFILE_PANEL_BINS`, `VOLUME_PROFILE_PANEL_LOOKBACK_DAYS`); only its
draw target and geometry change. `VOLUME_PROFILE_PANEL_WIDTH_FRAC` and
`VOLUME_PROFILE_PANEL_GAP_FRAC` retire.

**Grid** — solid hairlines at `GRID_COLOR`, replacing `gridstyle="--"` in
`PRO_STYLE`, matching `chart-init.js:26`.

## 5. Code organisation

`trade_chart.py` is already 62 KB and three of the four systems above are
annotation code. Adding them there makes a file that is hard to hold in context
worse. The legend and the axis tags go in a new
`swingbot/core/charts/chart_annotations.py`, a sibling of the existing
`chart_drawing.py` / `chart_volume_profile.py` / `chart_strategy_overlay.py`.
`chart_style.py` gains the new sizing constants.

This is targeted at the work in hand. No unrelated decomposition of
`trade_chart.py` is in scope.

**The palette is untouched**, so `test_chart_theme.py`'s THEME ↔ module
constants ↔ `tokens.css` assertions stay green by construction.

## 6. Verification

`assert_rendered` (`tests/conftest.py:35`) counts distinct colours. It is
resolution-independent and correctly answers "did we draw something", but it
**cannot see layout** — every change in this spec would pass it unchanged. The
existing chart tests will not tell us this worked. Three additions:

1. **Structural assertions**, which are genuinely checkable from the figure:
   - `len(fig.axes)` drops by one (the VP panel is gone)
   - no y-tick labels on the left spine (the duplicate ladder is gone)
   - the bottom-most axes' bbox reaches within ~4% of the figure bottom.
     **This is the dead-space regression test, and it fails against today's
     output.**
2. **Render-and-look** at each milestone: generate from a fixture and read the
   PNG back. This is the only real check on "does it look like TradingView",
   and it is a human/agent judgement, not an assertion.
3. **Existing suite** as the guard that the other six chart modules
   (`decision_chart`, `analytics_charts`, `portfolio_charts`, cache, overlays,
   theme) still render.

## 7. Risks

- **Volume overlay vs. candles.** At `scaleMargins 0.82` the bars can collide
  with a low stop line. Volume gets its own hidden y-axis so it scales
  independently and can be pushed lower without touching price.
- **VP overlay vs. the newest candles.** The right edge is what traders read,
  and the profile now sits over it. Low alpha is the first mitigation; the
  fallback is anchoring the profile to the left edge instead, which was an
  explicitly considered option and is a geometry change, not a redesign.
- **Axis-tag legibility in Discord** cannot be fully verified from the repo. The
  rendered PNG can be checked; how Discord scales it on a phone cannot. This
  needs the operator to eyeball one real alert before the work is called done.

## 8. Out of scope

- Any change to scoring, level detection, confluence, or trade logic.
- The other six chart modules, except where they break.
- The interactive chart itself — it is the reference, not the target.
- Decomposing `trade_chart.py` beyond extracting the new annotation module.
