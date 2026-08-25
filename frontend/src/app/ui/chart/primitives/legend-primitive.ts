import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts';

import { ChartPalette, token, tokenPx } from '../chart-theme';

/**
 * The pane's top-left legend (spec v23 Decision 8): the method's name and its
 * fit notes, drawn in the chart's corner rather than in the plot the way the
 * PNG does. `strategy-overlay.ts` explains why the rest of this module
 * deliberately draws no strings — this is the one place that does.
 *
 * **`legendLayout` is pure and canvas-free**, the same split `plan-lines.ts`
 * uses for `planLineSpecs`: the measuring rules (how tall a block of lines
 * is, how wide, when it has to clamp) are testable without a canvas or a
 * DOM, so a jsdom test can assert the numbers without faking
 * `measureText`. There is no real `CanvasRenderingContext2D` in this
 * project's test environment to measure against, so the width is an
 * estimate from character count rather than a per-glyph measurement — good
 * enough for a clamp decision, wrong for kerning-perfect layout, which this
 * primitive does not need.
 *
 * **DPR via `useMediaCoordinateSpace`, not `useBitmapCoordinateSpace`.** Every
 * other primitive in this directory draws in bitmap space and scales its own
 * strokes by the pixel ratio, because a one-pixel line has to land on an
 * exact device pixel to look crisp. Text has no such requirement — the canvas
 * already renders fonts at the bitmap's resolution inside media space — and
 * scaling a font size by hand the way `BoxRenderer` scales a line width would
 * only reintroduce the DPR bug this split avoids.
 */

/** The measured size of a legend block, in CSS pixels. */
export interface LegendBox {
  width: number;
  height: number;
  lineHeight: number;
}

/** Distance between the pane's corner and the legend's own edge. */
const MARGIN = 8;
/** Inside the legend's own border, between its edge and the text. */
const PADDING = 8;
/** Multiplier on font size. Typography convention, not a token: the type
 *  scale in `tokens.css` is font SIZE only, and no component in this app has
 *  needed to name a line-height as a design decision before this one. */
const LINE_SPACING = 1.4;
/** Estimated average glyph width as a fraction of font size, standing in for
 *  `context.measureText` — see the module comment for why there is no real
 *  canvas to measure against in this project's tests. Wide enough that the
 *  estimate over-measures proportional fonts rather than under-measuring
 *  them: a legend a few pixels wider than it needs to be is a cosmetic
 *  nit, a legend that clips its own longest line is a bug. */
const CHAR_WIDTH = 0.62;
/** A legend wider than this fraction of the pane starts covering candles
 *  instead of explaining them — the plan's "clamps rather than covering
 *  candles at the narrow breakpoints" acceptance criterion. */
const MAX_WIDTH_FRACTION = 0.4;

/**
 * The legend's size for a block of lines, measured from the longest one.
 *
 * `paneWidth` is optional so the pure geometry stays usable without a chart
 * at hand (as the spec above does); the renderer always has one and always
 * passes it, because an unclamped legend is the failure mode Decision 8's
 * acceptance test exists to catch.
 */
export function legendLayout(lines: string[], fontSize: number, paneWidth?: number): LegendBox {
  const lineHeight = fontSize * LINE_SPACING;
  // No lines is a chart with no plan, or a plan whose payload had no method
  // to name -- Decision 8's degraded state, not an error. An empty block
  // draws nothing rather than an empty box with a border around it.
  if (lines.length === 0) return { width: 0, height: 0, lineHeight };

  const longest = Math.max(...lines.map((line) => line.length));
  let width = longest * fontSize * CHAR_WIDTH + PADDING * 2;
  if (paneWidth !== undefined) {
    width = Math.min(width, paneWidth * MAX_WIDTH_FRACTION);
  }
  const height = lines.length * lineHeight + PADDING * 2;

  return { width, height, lineHeight };
}

class LegendRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly lines: () => readonly string[],
    private readonly palette: ChartPalette,
  ) {}

  draw(target: {
    useMediaCoordinateSpace: (
      cb: (scope: {
        context: CanvasRenderingContext2D;
        mediaSize: { width: number; height: number };
      }) => void,
    ) => void;
  }): void {
    const lines = this.lines();
    if (lines.length === 0) return;

    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      // `--text-table` (13px): the same size the tables around this chart
      // use for body text, so the legend reads as part of this app's type
      // scale rather than importing TradingView's own. v54 D5: was
      // `parseFloat(token(...))`, which is always NaN -> the 11px fallback --
      // `getComputedStyle().getPropertyValue()` never resolves a custom
      // property's own `calc()`, so this had silently ignored --text-scale
      // (and rendered a stale 11px, not this token's actual 13px) since the
      // "+2px across the scale" bump. `tokenPx()` resolves it for real.
      const fontSize = tokenPx('--text-table', 13);
      const family = token('--font-sans') || 'sans-serif';
      const box = legendLayout([...lines], fontSize, mediaSize.width);

      context.save();
      // v54 D5: the box reads as this chart's version of the other three
      // charts' `.tooltip` -- `chart-frame.ts`'s CHART_CHROME.tooltipSurface
      // / tooltipBorder, not the plain chart surface/grid border.
      context.fillStyle = this.palette.tooltipSurface;
      context.globalAlpha = 0.85;
      context.fillRect(MARGIN, MARGIN, box.width, box.height);
      context.globalAlpha = 1;
      context.strokeStyle = this.palette.tooltipBorder;
      context.lineWidth = 1;
      context.strokeRect(MARGIN + 0.5, MARGIN + 0.5, box.width - 1, box.height - 1);

      context.font = `${fontSize}px ${family}`;
      context.textBaseline = 'top';
      // The first line is the identity (ticker · horizon); the rest are
      // supporting detail, so only it takes the full-emphasis colour.
      lines.forEach((line, index) => {
        context.fillStyle = index === 0 ? this.palette.text : this.palette.textMuted;
        context.fillText(line, MARGIN + PADDING, MARGIN + PADDING + index * box.lineHeight);
      });
      context.restore();
    });
  }
}

class LegendPaneView implements IPrimitivePaneView {
  private readonly renderer_: LegendRenderer;

  constructor(lines: () => readonly string[], palette: ChartPalette) {
    this.renderer_ = new LegendRenderer(lines, palette);
  }

  /** In front of the candles: the legend is chrome, like the axis labels it
   *  sits beside, not a reading a candle should ever occlude. */
  zOrder(): 'top' {
    return 'top';
  }

  renderer(): IPrimitivePaneRenderer {
    return this.renderer_;
  }
}

/**
 * The legend primitive itself: no price/time anchoring, because the pane's
 * corner is a fixed pixel position, not a point on the chart. Task 11 attaches
 * one per chart and calls `setLines` whenever the trade, the crosshair, or the
 * theme changes.
 */
export class LegendPrimitive implements ISeriesPrimitive<Time> {
  private currentLines: readonly string[];
  private readonly views: LegendPaneView[];
  private requestUpdate: (() => void) | null = null;

  constructor(palette: ChartPalette, lines: string[]) {
    this.currentLines = lines;
    this.views = [new LegendPaneView(() => this.currentLines, palette)];
  }

  /** Replaces the drawn lines in place. Cheap enough to call on every
   *  crosshair move (Decision 8's OHLC readout) without debouncing. */
  setLines(lines: string[]): void {
    this.currentLines = lines;
    // `updateAllViews` only runs on a viewport change; new text with no pan
    // or zoom to trigger it would sit stale on the canvas until the next
    // one, so the primitive asks for a redraw itself.
    this.requestUpdate?.();
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.requestUpdate = null;
  }

  updateAllViews(): void {}

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }
}
