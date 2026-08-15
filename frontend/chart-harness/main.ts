/* SR40 step 4 — the browser half of the comparison against the PNG.
 *
 * Throwaway. Loads a payload dumped from the REAL /api/v1/market/chart route
 * (scratchpad/dump_chart_payloads.py) and draws it with the REAL chart modules,
 * so the numbers on screen are the numbers the endpoint serves.
 *
 * It repeats `TradeChart`'s ~15 lines of composition rather than mounting the
 * component: bundling an Angular component needs the Angular compiler, and
 * esbuild alone cannot. Everything that CONVERTS a price or a time to a pixel —
 * which is what this walk exists to check — is imported, not copied.
 */
import { UTCTimestamp, createChart } from 'lightweight-charts';

import { ChartResponse } from '../src/app/api/models';
import { chartOptions, chartPalette } from '../src/app/ui/chart/chart-theme';
import { IndicatorPanes } from '../src/app/ui/chart/indicator-panes';
import { BasicOverlays } from '../src/app/ui/chart/overlays-basic';
import { PlanLines } from '../src/app/ui/chart/plan-lines';
import { createPricePane } from '../src/app/ui/chart/price-pane';
import { StrategyOverlay } from '../src/app/ui/chart/strategy-overlay';

const name = new URLSearchParams(location.search).get('f') ?? 'curve_ema';

async function main(): Promise<void> {
  const data: ChartResponse = await (await fetch(`./payloads/${name}.json`)).json();
  const host = document.getElementById('chart') as HTMLElement;

  const palette = chartPalette();
  const chart = createChart(host, chartOptions(palette));

  // The same factory the component uses. The first version of this harness
  // rebuilt these two series by hand and silently missed the price pane's
  // autoscale provider — which is how a fix looked like it had not worked.
  const { candles, volume } = createPricePane(chart, palette, () => data.levels);

  candles.setData(
    data.ohlcv.map((bar) => ({
      time: bar.t as UTCTimestamp,
      open: bar.o,
      high: bar.h,
      low: bar.l,
      close: bar.c,
    })),
  );
  volume.setData(data.ohlcv.map((bar) => ({ time: bar.t as UTCTimestamp, value: bar.v })));

  new IndicatorPanes(chart).render(data.indicators, data.ohlcv, palette);
  new BasicOverlays(chart, candles).render(data, palette);
  new StrategyOverlay(candles).render(data.overlays, palette);
  new PlanLines(candles).render(
    data.levels,
    palette,
    data.ohlcv[0].t as UTCTimestamp,
    data.ohlcv[data.ohlcv.length - 1].t as UTCTimestamp,
  );

  chart.timeScale().fitContent();

  const caption = document.getElementById('caption') as HTMLElement;
  caption.textContent =
    `${name} · ${data.ohlcv.length} bars · overlays: ` +
    (data.overlays.length
      ? data.overlays.map((o) => `${o.side} ${o.shape.kind} (${o.source})`).join(', ')
      : 'none') +
    ` · entry ${data.levels?.entry?.toFixed(2)} stop ${data.levels?.stop?.toFixed(2)}` +
    ` t1 ${data.levels?.target1?.toFixed(2)} t2 ${data.levels?.target2?.toFixed(2)}`;

  // Polled by the screenshot driver: a canvas that has not painted yet
  // screenshots as an empty box, which looks exactly like a broken chart.
  requestAnimationFrame(() => requestAnimationFrame(() => (document.body.dataset['ready'] = 'yes')));
}

void main();
