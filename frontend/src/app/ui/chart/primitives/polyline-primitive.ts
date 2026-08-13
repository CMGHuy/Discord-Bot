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
 * A line through N points in price/time space — SR39's workhorse.
 *
 * Three of the six overlay shapes are this primitive with different points: a
 * `curve` is its own polyline, a `trendline` is the two-point case, a
 * `horizontal` is the two-point case at one price, and every ray of a `fib_fan`
 * is another. Writing three primitives that each drew a line would be three
 * places to get the pixel-ratio scaling wrong.
 *
 * It is not `LineSeries`, and the difference matters: a series is indexed by
 * the chart's own time scale and must have one value per bar, while these
 * shapes span arbitrary endpoints — a trendline is anchored to two pivots, not
 * to every bar between them, and a fib ray ends where its ratio says. A series
 * would need whitespace for every bar it does not touch and would still refuse
 * to end mid-frame.
 *
 * Follows SR34's mechanism exactly: convert in the renderer, once per frame, so
 * the shape stays pinned while the axes move.
 */

export interface PolylineSpec {
  /** `[epochSeconds, price]`, in the order they are joined. */
  points: [number, number][];
  color: string;
  lineWidth?: number;
  /** Dashed for the faint members of a fan — a shape drawn for context rather
   *  than as the reading. */
  dashed?: boolean;
}

const DASH = [4, 3];

class PolylineRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly spec: PolylineSpec,
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
    if (!chart || !series || this.spec.points.length < 2) return;

    const scale = chart.timeScale();
    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio, verticalPixelRatio }) => {
      context.save();
      context.strokeStyle = this.spec.color;
      context.lineWidth = (this.spec.lineWidth ?? 1) * horizontalPixelRatio;
      if (this.spec.dashed) context.setLineDash(DASH.map((d) => d * horizontalPixelRatio));
      context.beginPath();

      // A point outside the visible range converts to null. That BREAKS the
      // path rather than ending it: a curve whose middle is scrolled past
      // should resume on the far side, not stop at the edge and never come
      // back.
      let pen = false;
      for (const [time, price] of this.spec.points) {
        const x = scale.timeToCoordinate(time as UTCTimestamp);
        const y = series.priceToCoordinate(price);
        if (x === null || y === null) {
          pen = false;
          continue;
        }
        const px = x * horizontalPixelRatio;
        const py = y * verticalPixelRatio;
        if (pen) context.lineTo(px, py);
        else context.moveTo(px, py);
        pen = true;
      }

      context.stroke();
      context.restore();
    });
  }
}

class PolylinePaneView implements IPrimitivePaneView {
  private readonly renderer_: PolylineRenderer;

  constructor(
    spec: PolylineSpec,
    chart: () => IChartApi | null,
    series: () => ISeriesApi<SeriesType> | null,
  ) {
    this.renderer_ = new PolylineRenderer(spec, chart, series);
  }

  /** In front of the candles, unlike SR34's zones. This is the reading — the
   *  line the trade was confirmed against — and behind a candle body it would
   *  disappear exactly where it matters. */
  zOrder(): 'normal' {
    return 'normal';
  }

  renderer(): IPrimitivePaneRenderer {
    return this.renderer_;
  }
}

export class PolylinePrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private readonly views: PolylinePaneView[];

  /** Public because it IS the geometry: the dispatcher's choices are asserted
   *  against it, and SR40 compares these numbers with the PNG's. */
  constructor(readonly spec: PolylineSpec) {
    this.views = [
      new PolylinePaneView(
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
