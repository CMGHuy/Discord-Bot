import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';

/**
 * Above/below water — spec v181 §5. A dashed horizontal line at one price
 * (the visible range's opening equity) with a faint wash above it and below
 * it, painted behind the candles so it never hides one.
 *
 * At most one baseline: `setBaseline(null)` removes it. Which price and which
 * colours is the caller's choice; this class only draws.
 */
export interface BaselineSpec {
  value: number;
  line: string;
  above: string;
  below: string;
}

interface BitmapScope {
  context: CanvasRenderingContext2D;
  horizontalPixelRatio: number;
  verticalPixelRatio: number;
  bitmapSize: { width: number; height: number };
}

interface DrawTarget {
  useBitmapCoordinateSpace: (cb: (scope: BitmapScope) => void) => void;
}

/** Dash and gap, in CSS px. */
const DASH_PX = 4;

class BaselineRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly spec: () => BaselineSpec | null,
    private readonly series: () => ISeriesApi<SeriesType> | null,
  ) {}

  draw(target: DrawTarget): void {
    const spec = this.spec();
    const series = this.series();
    if (!spec || !series) return;
    const y = series.priceToCoordinate(spec.value);
    // No price scale yet (empty series).
    if (y === null) return;
    target.useBitmapCoordinateSpace((scope) => paint(scope, spec, y));
  }
}

function paint(scope: BitmapScope, spec: BaselineSpec, y: number): void {
  const { context, horizontalPixelRatio, verticalPixelRatio, bitmapSize } = scope;
  const py = Math.round(y * verticalPixelRatio);
  // Off the top: the whole pane is under water; off the bottom: all above.
  const split = Math.min(Math.max(py, 0), bitmapSize.height);
  context.save();
  context.fillStyle = spec.above;
  context.fillRect(0, 0, bitmapSize.width, split);
  context.fillStyle = spec.below;
  context.fillRect(0, split, bitmapSize.width, bitmapSize.height - split);
  if (py >= 0 && py <= bitmapSize.height) {
    context.strokeStyle = spec.line;
    context.lineWidth = Math.max(1, Math.floor(verticalPixelRatio));
    context.setLineDash([DASH_PX * horizontalPixelRatio, DASH_PX * horizontalPixelRatio]);
    context.beginPath();
    // +0.5 centres a 1px stroke on the pixel row instead of blurring two.
    context.moveTo(0, py + 0.5);
    context.lineTo(bitmapSize.width, py + 0.5);
    context.stroke();
  }
  context.restore();
}

class BaselinePaneView implements IPrimitivePaneView {
  constructor(private readonly renderer_: BaselineRenderer) {}

  zOrder(): 'bottom' {
    return 'bottom';
  }

  renderer(): IPrimitivePaneRenderer {
    return this.renderer_;
  }
}

export class BaselinePrimitive implements ISeriesPrimitive<Time> {
  private series: ISeriesApi<SeriesType> | null = null;
  private spec: BaselineSpec | null = null;
  private requestUpdate: (() => void) | null = null;
  private readonly views: BaselinePaneView[];

  constructor() {
    this.views = [new BaselinePaneView(new BaselineRenderer(() => this.spec, () => this.series))];
  }

  current(): BaselineSpec | null {
    return this.spec;
  }

  setBaseline(spec: BaselineSpec | null): void {
    this.spec = spec;
    this.requestUpdate?.();
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.series = param.series as ISeriesApi<SeriesType>;
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.series = null;
    this.requestUpdate = null;
  }

  updateAllViews(): void {}

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }
}
