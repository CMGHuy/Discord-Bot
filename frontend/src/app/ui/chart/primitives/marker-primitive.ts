import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';

/**
 * A diamond at one point in price/time space.
 *
 * Two shapes need it: a `marker` (a zigzag pivot, which the PNG draws as a lone
 * diamond) and each pivot of a `trendline`, which shows which touches produced
 * the fit. Both are single points rather than levels — a pivot does not extend
 * anywhere, which is exactly why SR32 gave it its own `kind` instead of folding
 * it into a zero-length `horizontal`.
 *
 * A diamond rather than a dot, because the chart already uses round crosshair
 * markers and a pivot must not be mistaken for one.
 *
 * The marker is NOT `createSeriesMarkers`: the library's markers attach to a
 * bar of the series, and a pivot's price is its own — a marker snapped to a
 * bar's high or low would move it, quietly, to a price the server never sent.
 */

export interface MarkerSpec {
  /** Epoch seconds — the one time type in this payload. */
  time: number;
  price: number;
  color: string;
  /** Half-diagonal, in CSS pixels. */
  size?: number;
}

const DEFAULT_SIZE = 4;

class MarkerRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly spec: MarkerSpec,
    private readonly chart: () => IChartApi | null,
    private readonly series: () => ISeriesApi<SeriesType> | null,
  ) {}

  draw(target: {
    useBitmapCoordinateSpace: (
      cb: (scope: {
        context: CanvasRenderingContext2D;
        horizontalPixelRatio: number;
        verticalPixelRatio: number;
      }) => void,
    ) => void;
  }): void {
    const chart = this.chart();
    const series = this.series();
    if (!chart || !series) return;

    const x = chart.timeScale().timeToCoordinate(this.spec.time as UTCTimestamp);
    const y = series.priceToCoordinate(this.spec.price);
    // Scrolled off screen. The ordinary state of a pivot outside the window.
    if (x === null || y === null) return;

    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio, verticalPixelRatio }) => {
      const size = this.spec.size ?? DEFAULT_SIZE;
      const cx = x * horizontalPixelRatio;
      const cy = y * verticalPixelRatio;
      // Scaled per axis, not by one ratio: SR34 measured the two differing on
      // this machine, and using either alone skews the diamond.
      const dx = size * horizontalPixelRatio;
      const dy = size * verticalPixelRatio;

      context.save();
      context.fillStyle = this.spec.color;
      context.beginPath();
      context.moveTo(cx, cy - dy);
      context.lineTo(cx + dx, cy);
      context.lineTo(cx, cy + dy);
      context.lineTo(cx - dx, cy);
      context.closePath();
      context.fill();
      context.restore();
    });
  }
}

class MarkerPaneView implements IPrimitivePaneView {
  private readonly renderer_: MarkerRenderer;

  constructor(
    spec: MarkerSpec,
    chart: () => IChartApi | null,
    series: () => ISeriesApi<SeriesType> | null,
  ) {
    this.renderer_ = new MarkerRenderer(spec, chart, series);
  }

  /** In front: a pivot marks a specific bar, and behind the candle it marks it
   *  would be invisible. */
  zOrder(): 'top' {
    return 'top';
  }

  renderer(): IPrimitivePaneRenderer {
    return this.renderer_;
  }
}

export class MarkerPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private readonly views: MarkerPaneView[];

  constructor(readonly spec: MarkerSpec) {
    this.views = [
      new MarkerPaneView(
        spec,
        () => this.chart,
        () => this.series,
      ),
    ];
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart;
    this.series = param.series as ISeriesApi<SeriesType>;
  }

  detached(): void {
    this.chart = null;
    this.series = null;
  }

  updateAllViews(): void {}

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }
}
