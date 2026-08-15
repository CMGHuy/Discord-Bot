# Chart harness

Draws a real `/api/v1/market/chart` payload with the real chart modules, in a
browser, with no admin server and no Angular. Built for SR40's walk against the
PNG and kept because that walk is the only check that catches a
coordinate-conversion error — unit tests cannot see one, and it found three.

## Running it

```bash
python scripts/dev/render_chart_fixtures.py --out /tmp/chart-png      # the PNG side
python scripts/dev/dump_chart_payloads.py frontend/chart-harness/payloads   # the browser side
cd frontend
npx esbuild chart-harness/main.ts --bundle --format=esm --outfile=chart-harness/bundle.js
python -m http.server 8899 --bind 127.0.0.1
```

Then open `http://127.0.0.1:8899/chart-harness/index.html?f=<fixture>` and put it
beside `/tmp/chart-png/<fixture>.png`. Fixture names are the keys of `FIXTURES`
in `scripts/dev/render_chart_fixtures.py`.

## What it does and does not prove

The payload comes from the **actual Flask route**, and every module that turns a
price or a time into a pixel is imported, not copied — including `price-pane.ts`,
which exists because the first version of this harness rebuilt the candle series
by hand and silently missed the price pane's autoscale provider. That is the
failure mode to watch for if you extend this: anything you reproduce here rather
than import can drift from the component and make a fix look like it did not
work.

It does not exercise `TradeChart` itself, the store, or the tab chrome —
bundling an Angular component needs the Angular compiler. Those are covered by
`ng build` and the unit tests.

**Three fixtures have no overlay by design.** `trendline`, `secondary_bollinger`
and `no_drawable_source` all resolve to a trendline, and the endpoint
deliberately does not fit trendlines (SR32's note: the fit happens before the
display window is chosen, so `overlay_geometry` returns `None` without a
`trend_info`). The PNG draws them; the browser does not. That is a known parity
gap, not a bug in this harness.
