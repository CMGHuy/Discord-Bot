import { describe, expect, it, vi } from 'vitest';

import { LegendPrimitive, legendLayout } from './legend-primitive';

const PALETTE = { text: '#fff', textMuted: '#999', surface: '#111' } as never;

describe('legendLayout', () => {
  it('measures a block from its longest line', () => {
    const box = legendLayout(['AAPL · 2w', 'EMA20 support since 2026-06-02'], 11);
    expect(box.width).toBeGreaterThan(box.lineHeight);
    expect(box.height).toBeGreaterThan(box.lineHeight);
  });

  it('clamps its width so it cannot cover the candles', () => {
    const box = legendLayout(['x'.repeat(400)], 11, 320);
    expect(box.width).toBeLessThanOrEqual(320 * 0.4);
  });

  it('renders nothing for no lines', () => {
    expect(legendLayout([], 11).height).toBe(0);
  });
});

/** A canvas context that records every fill and stroke colour it is handed. */
function recordingContext() {
  const fills: string[] = [];
  const strokes: string[] = [];
  const context = {
    save() {}, restore() {}, fillRect() {}, strokeRect() {}, fillText() {},
    globalAlpha: 1, lineWidth: 1, font: '', textBaseline: '',
    set fillStyle(value: string) { fills.push(value); },
    get fillStyle(): string { return fills.at(-1) ?? ''; },
    set strokeStyle(value: string) { strokes.push(value); },
    get strokeStyle(): string { return strokes.at(-1) ?? ''; },
  };
  return { context, fills, strokes };
}

function draw(legend: LegendPrimitive) {
  const recorded = recordingContext();
  legend.paneViews()[0].renderer()!.draw({
    useMediaCoordinateSpace: (cb: (scope: unknown) => void) =>
      cb({ context: recorded.context, mediaSize: { width: 800, height: 400 } }),
  } as never);
  return recorded;
}

describe('LegendPrimitive.setPalette (v225)', () => {
  const GRAPHITE = { text: '#e6e8eb', textMuted: '#9aa4b2', tooltipSurface: '#1f242b', tooltipBorder: '#2d333b' } as never;
  const NAVY = { text: '#e6ecf5', textMuted: '#9fb0c8', tooltipSurface: '#172440', tooltipBorder: '#233453' } as never;

  it('draws the box and the lines in the palette it was last given', () => {
    const legend = new LegendPrimitive(GRAPHITE, ['AAPL · 2w', 'EMA20']);
    expect(draw(legend).fills).toEqual(['#1f242b', '#e6e8eb', '#9aa4b2']);
    legend.setPalette(NAVY);
    const { fills, strokes } = draw(legend);
    expect(fills).toEqual(['#172440', '#e6ecf5', '#9fb0c8']);
    expect(strokes).toEqual(['#233453']);
  });

  it('asks the chart for a redraw when the palette changes, and is quiet before it is attached', () => {
    const legend = new LegendPrimitive(GRAPHITE, ['AAPL']);
    expect(() => legend.setPalette(NAVY)).not.toThrow();
    const requestUpdate = vi.fn();
    legend.attached({ requestUpdate } as never);
    legend.setPalette(GRAPHITE);
    expect(requestUpdate).toHaveBeenCalledTimes(1);
  });
});
