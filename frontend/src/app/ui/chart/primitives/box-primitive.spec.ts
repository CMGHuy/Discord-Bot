import { describe, expect, it, vi } from 'vitest';

import { BoxPrimitive, BoxSpec } from './box-primitive';

/* SR34 — the risk gate.
 *
 * These tests cover the parts that can be checked without a layout engine:
 * the primitive's contract with the library, and the coordinate handling that
 * decides whether a shape stays anchored. Whether it actually PAINTS is a
 * browser question and is recorded in
 * docs/superpowers/results/2026-08-13-chart-primitive-spike.md.
 */

const SPEC: BoxSpec = {
  time1: 1_700_000_000 as never,
  time2: 1_700_086_400 as never,
  price1: 100,
  price2: 110,
  fill: 'rgba(0,0,0,0.2)',
  border: '#fff',
};

function attach(primitive: BoxPrimitive, coords: Record<string, number | null>) {
  const chart = {
    timeScale: () => ({
      timeToCoordinate: vi.fn((t: unknown) =>
        t === SPEC.time1 ? coords['x1'] : coords['x2'],
      ),
    }),
  };
  const series = {
    priceToCoordinate: vi.fn((p: number) => (p === SPEC.price1 ? coords['y1'] : coords['y2'])),
  };
  primitive.attached({ chart, series } as never);
  return { chart, series };
}

/** A stand-in for the library's bitmap-space helper. */
function drawTarget() {
  const context = {
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 0,
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
  };
  return {
    context,
    target: {
      useBitmapCoordinateSpace: (cb: (scope: unknown) => void) =>
        cb({ context, horizontalPixelRatio: 2, verticalPixelRatio: 2 }),
    },
  };
}

describe('BoxPrimitive', () => {
  it('exposes exactly one pane view', () => {
    expect(new BoxPrimitive(SPEC).paneViews()).toHaveLength(1);
  });

  it('draws behind the candles by default', () => {
    // A zone is context. In front of the candles it hides the thing being
    // read.
    const view = new BoxPrimitive(SPEC).paneViews()[0] as { zOrder(): string };
    expect(view.zOrder()).toBe('bottom');
  });

  it('draws in front when asked', () => {
    const view = new BoxPrimitive({ ...SPEC, background: false })
      .paneViews()[0] as { zOrder(): string };
    expect(view.zOrder()).toBe('normal');
  });

  it('converts price and time on every draw, not once at construction', () => {
    // The whole reason a shape stays anchored while panning: the mapping
    // changes with the viewport, so a cached coordinate is right exactly
    // until the user touches the chart.
    const primitive = new BoxPrimitive(SPEC);
    const { series } = attach(primitive, { x1: 10, x2: 50, y1: 20, y2: 60 });
    const renderer = primitive.paneViews()[0].renderer() as { draw(t: unknown): void };

    const first = drawTarget();
    renderer.draw(first.target);
    const callsAfterFirst = series.priceToCoordinate.mock.calls.length;

    const second = drawTarget();
    renderer.draw(second.target);
    expect(series.priceToCoordinate.mock.calls.length).toBeGreaterThan(callsAfterFirst);
  });

  it('scales to the device pixel ratio', () => {
    // Without this everything renders at half size on a HiDPI screen, which
    // is the classic symptom of drawing in CSS pixels on a bitmap canvas.
    const primitive = new BoxPrimitive(SPEC);
    attach(primitive, { x1: 10, x2: 50, y1: 20, y2: 60 });
    const { context, target } = drawTarget();

    (primitive.paneViews()[0].renderer() as { draw(t: unknown): void }).draw(target);

    // ratio 2 => left 20, top 40, width 80, height 80
    expect(context.fillRect).toHaveBeenCalledWith(20, 40, 80, 80);
  });

  it('normalises the corners, so the order of the inputs does not matter', () => {
    const primitive = new BoxPrimitive(SPEC);
    attach(primitive, { x1: 50, x2: 10, y1: 60, y2: 20 });
    const { context, target } = drawTarget();

    (primitive.paneViews()[0].renderer() as { draw(t: unknown): void }).draw(target);

    expect(context.fillRect).toHaveBeenCalledWith(20, 40, 80, 80);
  });

  it('skips the frame when the shape is off screen', () => {
    // timeToCoordinate returns null outside the visible range. That is the
    // ordinary state of a scrolled-away shape, not an error -- drawing at
    // NaN would blank the canvas.
    const primitive = new BoxPrimitive(SPEC);
    attach(primitive, { x1: null, x2: 50, y1: 20, y2: 60 });
    const { context, target } = drawTarget();

    (primitive.paneViews()[0].renderer() as { draw(t: unknown): void }).draw(target);

    expect(context.fillRect).not.toHaveBeenCalled();
  });

  it('draws nothing once detached', () => {
    const primitive = new BoxPrimitive(SPEC);
    attach(primitive, { x1: 10, x2: 50, y1: 20, y2: 60 });
    primitive.detached();
    const { context, target } = drawTarget();

    (primitive.paneViews()[0].renderer() as { draw(t: unknown): void }).draw(target);

    expect(context.fillRect).not.toHaveBeenCalled();
  });
});
