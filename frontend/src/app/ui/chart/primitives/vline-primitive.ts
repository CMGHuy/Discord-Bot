import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts';

import { token } from '../chart-theme';

/**
 * One labelled vertical line at a bar's left edge — v172's "Recording
 * started" seam between candles rebuilt from daily bars and candles built
 * from recorded samples.
 *
 * At most one line at a time: `setLine(null)` removes it. The line sits at
 * the bar's LEFT edge (centre minus half the bar spacing) because the seam is
 * where recording began, not the middle of the first recorded candle.
 */
export interface VLineSpec {
  time: Time;
  label: string;
  color: string;
  textColor: string;
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

const LABEL_PX = 11;
const LABEL_INSET_PX = 4;

class VLineRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly line: () => VLineSpec | null,
    private readonly chart: () => IChartApi | null,
  ) {}

  draw(target: DrawTarget): void {
    const spec = this.line();
    const chart = this.chart();
    if (!spec || !chart) return;
    const scale = chart.timeScale();
    const centre = scale.timeToCoordinate(spec.time);
    // Scrolled off screen.
    if (centre === null) return;
    const x = centre - scale.options().barSpacing / 2;

    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio, verticalPixelRatio, bitmapSize }) => {
      const px = Math.round(x * horizontalPixelRatio);
      context.save();
      context.fillStyle = spec.color;
      context.fillRect(px, 0, Math.max(1, Math.floor(horizontalPixelRatio)), bitmapSize.height);
      context.fillStyle = spec.textColor;
      const family = token('--font-sans') || 'sans-serif';
      context.font = `${Math.round(LABEL_PX * verticalPixelRatio)}px ${family}`;
      context.textBaseline = 'top';
      context.fillText(
        spec.label,
        px + Math.round(LABEL_INSET_PX * horizontalPixelRatio),
        Math.round(LABEL_INSET_PX * verticalPixelRatio),
      );
      context.restore();
    });
  }
}

class VLinePaneView implements IPrimitivePaneView {
  constructor(private readonly renderer_: VLineRenderer) {}

  zOrder(): 'top' {
    return 'top';
  }

  renderer(): IPrimitivePaneRenderer {
    return this.renderer_;
  }
}

export class VLinePrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private spec: VLineSpec | null = null;
  private requestUpdate: (() => void) | null = null;
  private readonly views: VLinePaneView[];

  constructor() {
    this.views = [new VLinePaneView(new VLineRenderer(() => this.spec, () => this.chart))];
  }

  current(): VLineSpec | null {
    return this.spec;
  }

  setLine(spec: VLineSpec | null): void {
    this.spec = spec;
    this.requestUpdate?.();
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart;
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.chart = null;
    this.requestUpdate = null;
  }

  updateAllViews(): void {}

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }
}
