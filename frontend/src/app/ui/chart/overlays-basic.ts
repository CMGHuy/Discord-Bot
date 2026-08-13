import {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  LineData,
  LineSeries,
  SeriesAttachedParameter,
  SeriesType,
  Time,
  UTCTimestamp,
  WhitespaceData,
} from 'lightweight-charts';

import { ChartBar, ChartResponse, ChartSeries, VolumeProfileBin } from '../../api/models';
import { ChartPalette } from './chart-theme';
import { PANE_PRICE } from './trade-chart';

/**
 * The two overlays that are context rather than readings (SR38): the Keltner
 * envelope, and the volume profile down the left edge.
 *
 * Neither is a number anyone takes off an axis — the envelope says where price
 * has been calm, the profile says where it has traded — so both are drawn
 * faintly, neither gets a price line, and neither contributes a legend entry
 * worth reading. That is the whole reason they can share a file: they are the
 * same kind of thing, drawn two different ways because one is a time series and
 * one is emphatically not.
 *
 * **The profile is a primitive because no built-in series can express it.**
 * Every series type in the library maps one value per time; the profile maps a
 * volume per PRICE, along an axis the time scale knows nothing about. SR34's
 * spike is what makes drawing it possible at all, and this file uses the same
 * mechanism: convert in the renderer, per frame, so the bars stay pinned to
 * their prices while the axis moves.
 */

/** One bar of the profile: where it sits, how long it is relative to the
 *  fattest bin, and how much price it covers. */
export interface ProfileBar {
  price: number;
  /** 0–1 against the widest bin. */
  ratio: number;
  /** The bin's height in price, so the bars tile instead of overlapping. */
  span: number;
}

/** How much of the pane's width the fattest bin may occupy. A profile that
 *  reaches the candles stops being a margin annotation and starts hiding the
 *  thing it annotates. */
const MAX_WIDTH_FRACTION = 0.18;

/** Fallback height for a lone bin, which has no neighbour to measure against.
 *  A share of its own price rather than a fixed number of dollars: a $4 stock
 *  and a $400 one would otherwise get bars three orders of magnitude apart in
 *  visual weight. */
const LONE_BIN_SPAN = 0.01;

/**
 * Pair an indicator series with the bars it was computed over.
 *
 * **A `null` becomes whitespace — `{ time }` with no `value` — and never zero.**
 * A 20-bar envelope has no value on bar one, and a zero there does not merely
 * draw a wrong point: it pulls the price scale down to include 0 and flattens
 * every candle on the pane into a band at the top.
 *
 * Zipped to the shorter of the two. The server aligns both to the visible
 * window, so a mismatch means something upstream is wrong, and drawing a value
 * at an undefined time puts a point at epoch zero rather than raising.
 */
export function keltnerPoints(
  bars: ChartBar[],
  values: ChartSeries,
): (LineData<Time> | WhitespaceData<Time>)[] {
  const length = Math.min(bars.length, values.length);
  const points: (LineData<Time> | WhitespaceData<Time>)[] = [];

  for (let index = 0; index < length; index++) {
    const time = bars[index].t as UTCTimestamp;
    const value = values[index];
    points.push(value === null || !Number.isFinite(value) ? { time } : { time, value });
  }
  return points;
}

/**
 * The profile's bins, normalised against the fattest one.
 *
 * **Relative, never absolute.** The profile has no axis and never gets one, so
 * the only information in a bar's length is how it compares with its
 * neighbours; scaling to a constant volume would make the same distribution
 * look different on every ticker.
 *
 * An empty list in, an empty list out — "not enough history" arrives as an
 * empty array rather than an absent key, because unlike an indicator this is an
 * overlay on the price pane and there is no pane to omit.
 */
export function profileBars(bins: VolumeProfileBin[]): ProfileBar[] {
  const usable = bins.filter(
    (bin) => Number.isFinite(bin.price) && Number.isFinite(bin.volume) && bin.volume > 0,
  );
  if (usable.length === 0) return [];

  const widest = Math.max(...usable.map((bin) => bin.volume));
  // Every bin empty is the one input that would divide by zero. It is also
  // indistinguishable from no profile at all, so it degrades to the same thing.
  if (!(widest > 0)) return [];

  const span =
    usable.length > 1
      ? Math.abs(usable[1].price - usable[0].price)
      : Math.abs(usable[0].price) * LONE_BIN_SPAN;

  return usable.map((bin) => ({
    price: bin.price,
    ratio: bin.volume / widest,
    span: span > 0 ? span : LONE_BIN_SPAN,
  }));
}

class ProfileRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly bars: ProfileBar[],
    private readonly color: string,
    private readonly series: () => ISeriesApi<SeriesType> | null,
  ) {}

  draw(target: {
    useBitmapCoordinateSpace: (
      cb: (scope: {
        context: CanvasRenderingContext2D;
        mediaSize: { width: number; height: number };
        horizontalPixelRatio: number;
        verticalPixelRatio: number;
      }) => void,
    ) => void;
  }): void {
    const series = this.series();
    if (!series || this.bars.length === 0) return;

    target.useBitmapCoordinateSpace(
      ({ context, mediaSize, horizontalPixelRatio, verticalPixelRatio }) => {
        const maxWidth = mediaSize.width * MAX_WIDTH_FRACTION * horizontalPixelRatio;
        context.fillStyle = this.color;

        for (const bar of this.bars) {
          const top = series.priceToCoordinate(bar.price + bar.span / 2);
          const bottom = series.priceToCoordinate(bar.price - bar.span / 2);
          // Off screen in price. Ordinary for a profile whose range is wider
          // than the visible window, not an error.
          if (top === null || bottom === null) continue;

          const y = Math.round(Math.min(top, bottom) * verticalPixelRatio);
          // At least one pixel: a hundred-bin profile on a short pane rounds
          // several bins to zero height, which silently drops them.
          const height = Math.max(1, Math.round(Math.abs(bottom - top) * verticalPixelRatio) - 1);
          context.fillRect(0, y, Math.round(bar.ratio * maxWidth), height);
        }
      },
    );
  }
}

class ProfilePaneView implements IPrimitivePaneView {
  private readonly renderer_: ProfileRenderer;

  constructor(bars: ProfileBar[], color: string, series: () => ISeriesApi<SeriesType> | null) {
    this.renderer_ = new ProfileRenderer(bars, color, series);
  }

  /** Behind the candles. It is a backdrop describing where trade happened, and
   *  in front it would veil the left quarter of the frame. */
  zOrder(): 'bottom' {
    return 'bottom';
  }

  renderer(): IPrimitivePaneRenderer {
    return this.renderer_;
  }
}

/**
 * The volume profile, hung off the left edge of the price pane.
 *
 * The left edge is the one strip of the pane no series occupies — the price
 * scale is on the right, and the candles fill from the left only once the
 * window is full.
 */
export class VolumeProfilePrimitive implements ISeriesPrimitive<Time> {
  private series: ISeriesApi<SeriesType> | null = null;
  private readonly views: ProfilePaneView[];

  constructor(bars: ProfileBar[], color: string) {
    this.views = [new ProfilePaneView(bars, color, () => this.series)];
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.series = param.series as ISeriesApi<SeriesType>;
  }

  detached(): void {
    this.series = null;
  }

  updateAllViews(): void {}

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }
}

/**
 * Both overlays on the price pane, owned together so they clear together.
 *
 * Removed and rebuilt on every render, like `PlanLines`: the presence of each
 * overlay is a property of the payload — a short frame has no envelope, a
 * shorter one has no profile — so there is no stable set of objects to
 * reconcile against.
 */
export class BasicOverlays {
  private lines: ISeriesApi<'Line'>[] = [];
  private profile: VolumeProfilePrimitive | null = null;

  constructor(
    private readonly chart: IChartApi,
    private readonly priceSeries: ISeriesApi<SeriesType>,
  ) {}

  render(data: ChartResponse, palette: ChartPalette): void {
    this.detach();

    const kc = data.indicators.kc;
    if (kc) {
      // `--info-soft` is `--info` at 12%: the tokens' own vocabulary for "this
      // hue, reduced". Inventing a fourth opacity here would be inventing a
      // fourth palette, which is what SR3's audit existed to stop.
      for (const values of [kc.upper, kc.lower]) {
        const line = this.chart.addSeries(
          LineSeries,
          {
            color: palette.infoSoft,
            lineWidth: 1,
            // No axis tag, no last-value label, no crosshair marker: an
            // envelope is read as a shape, and three more numbers on the price
            // scale would crowd out the plan levels that are read as numbers.
            lastValueVisible: false,
            priceLineVisible: false,
            crosshairMarkerVisible: false,
          },
          PANE_PRICE,
        );
        line.setData(keltnerPoints(data.ohlcv, values));
        this.lines.push(line);
      }
    }

    const bars = profileBars(data.volume_profile);
    if (bars.length > 0) {
      // Greyscale, like the volume histogram and for the same reason: under the
      // token palette a hue is a valence, and volume has none.
      this.profile = new VolumeProfilePrimitive(bars, palette.volume);
      this.priceSeries.attachPrimitive(this.profile);
    }
  }

  detach(): void {
    for (const line of this.lines) this.chart.removeSeries(line);
    this.lines = [];
    if (this.profile) this.priceSeries.detachPrimitive(this.profile);
    this.profile = null;
  }
}
