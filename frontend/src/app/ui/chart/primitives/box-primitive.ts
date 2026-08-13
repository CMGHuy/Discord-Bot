import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';

/**
 * A filled, bordered rectangle between two times and two prices — the
 * `fvg_zone` shape, and the simplest of spec v18 Decision 10's five.
 *
 * **SR34 is a risk gate**, and this file is the evidence. `lightweight-charts`
 * has no shape support of its own; every overlay in SR37–SR39 depends on a
 * series primitive being able to draw arbitrary geometry anchored in
 * price/time space rather than in pixels. If that were not possible the phase
 * would need a different design — a positioned `<canvas>` overlay synchronised
 * by hand — and finding that out here is cheaper than finding it out four
 * tasks later.
 *
 * The mechanism, which SR37–SR39 copy:
 *
 *  - `paneViews()` returns view objects the library asks for on every frame;
 *  - each view's `renderer()` draws in **pixel** space, so the conversion from
 *    price/time to coordinates happens per frame, not once at construction.
 *    That is what keeps a shape anchored while panning and zooming — the
 *    alternative, converting up front, produces a rectangle that slides off
 *    its bars the moment the axis moves;
 *  - `updateAllViews()` marks them stale when the viewport changes.
 *
 * A coordinate can be `null` when its price or time is outside the visible
 * range. Those are not errors: they are the ordinary state of a shape scrolled
 * off screen, and the renderer simply skips the frame rather than drawing at
 * NaN.
 */

export interface BoxSpec {
  /** Left and right edges, in the series' own time domain. */
  time1: Time;
  time2: Time;
  /** Top and bottom edges, in price. Order does not matter. */
  price1: number;
  price2: number;
  fill: string;
  border: string;
  /** Drawn behind the candles. A zone is context, not a reading. */
  background?: boolean;
}

class BoxRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly box: BoxSpec,
    private readonly coords: () => {
      x1: number | null;
      x2: number | null;
      y1: number | null;
      y2: number | null;
    },
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
    const { x1, x2, y1, y2 } = this.coords();
    // Off-screen in either axis: nothing to draw this frame. Not a failure.
    if (x1 === null || x2 === null || y1 === null || y2 === null) return;

    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio, verticalPixelRatio }) => {
      // The canvas is a bitmap at device resolution; the coordinates the chart
      // hands back are CSS pixels. Skipping this scale draws everything at
      // half size on any HiDPI screen, which is the classic symptom.
      const left = Math.round(Math.min(x1, x2) * horizontalPixelRatio);
      const right = Math.round(Math.max(x1, x2) * horizontalPixelRatio);
      const top = Math.round(Math.min(y1, y2) * verticalPixelRatio);
      const bottom = Math.round(Math.max(y1, y2) * verticalPixelRatio);

      context.fillStyle = this.box.fill;
      context.fillRect(left, top, right - left, bottom - top);
      context.strokeStyle = this.box.border;
      context.lineWidth = 1 * horizontalPixelRatio;
      context.strokeRect(left, top, right - left, bottom - top);
    });
  }
}

class BoxPaneView implements IPrimitivePaneView {
  private readonly renderer_: BoxRenderer;

  constructor(
    private readonly box: BoxSpec,
    private readonly chart: () => IChartApi | null,
    private readonly series: () => ISeriesApi<SeriesType> | null,
  ) {
    this.renderer_ = new BoxRenderer(box, () => this.coordinates());
  }

  /** Behind the candles for a zone, in front for anything read precisely. */
  zOrder(): 'bottom' | 'normal' {
    return this.box.background === false ? 'normal' : 'bottom';
  }

  renderer(): IPrimitivePaneRenderer {
    return this.renderer_;
  }

  /**
   * Converted per frame, deliberately.
   *
   * Doing this once at construction is the obvious optimisation and it is
   * wrong: the mapping from price and time to pixels changes on every pan and
   * every zoom, so a cached coordinate is correct exactly until the user
   * touches the chart.
   */
  private coordinates() {
    const chart = this.chart();
    const series = this.series();
    if (!chart || !series) return { x1: null, x2: null, y1: null, y2: null };
    const scale = chart.timeScale();
    return {
      x1: scale.timeToCoordinate(this.box.time1),
      x2: scale.timeToCoordinate(this.box.time2),
      y1: series.priceToCoordinate(this.box.price1),
      y2: series.priceToCoordinate(this.box.price2),
    };
  }
}

export class BoxPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private readonly views: BoxPaneView[];

  /** Public because it IS the geometry — SR39's dispatcher is asserted against
   *  it, and SR40 compares these numbers with the PNG's. */
  get spec(): BoxSpec {
    return this.box;
  }

  constructor(private readonly box: BoxSpec) {
    this.views = [
      new BoxPaneView(
        box,
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

  /** The library calls this when the viewport changes; the views recompute
   *  their coordinates on the next draw, so there is nothing to invalidate
   *  by hand. */
  updateAllViews(): void {}

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }
}
