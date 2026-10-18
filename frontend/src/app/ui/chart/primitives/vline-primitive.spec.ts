import { describe, expect, it, vi } from 'vitest';

import { VLinePrimitive } from './vline-primitive';

function fakeContext() {
  return {
    save: vi.fn(), restore: vi.fn(), fillRect: vi.fn(), fillText: vi.fn(),
    fillStyle: '', font: '', textBaseline: '',
  };
}

function attach(coordinate: number | null) {
  const primitive = new VLinePrimitive();
  const requestUpdate = vi.fn();
  const chart = { timeScale: () => ({
    timeToCoordinate: () => coordinate,
    options: () => ({ barSpacing: 10 }),
  }) };
  primitive.attached({ chart, series: {}, requestUpdate } as never);
  return { primitive, requestUpdate };
}

function draw(primitive: VLinePrimitive) {
  const context = fakeContext();
  const target = { useBitmapCoordinateSpace: (cb: (scope: unknown) => void) => cb({
    context, horizontalPixelRatio: 2, verticalPixelRatio: 2, bitmapSize: { width: 400, height: 300 },
  }) };
  primitive.paneViews()[0].renderer()!.draw(target as never);
  return context;
}

const SPEC = { time: '2026-10-20', label: 'Recording started', color: 'LINE', textColor: 'TEXT' };

describe('VLinePrimitive', () => {
  it('draws one full-height line at the left edge of the bar, with its label', () => {
    const { primitive } = attach(100);
    primitive.setLine(SPEC as never);
    const context = draw(primitive);
    // centre 100 - half of barSpacing 10 = 95 CSS px = 190 bitmap px.
    expect(context.fillRect).toHaveBeenCalledWith(190, 0, 2, 300);
    expect(context.fillText).toHaveBeenCalledWith('Recording started', 198, 8);
  });

  it('draws nothing without a line or off screen', () => {
    const { primitive } = attach(100);
    expect(draw(primitive).fillRect).not.toHaveBeenCalled();
    const offscreen = attach(null).primitive;
    offscreen.setLine(SPEC as never);
    expect(draw(offscreen).fillRect).not.toHaveBeenCalled();
  });

  it('asks the chart to repaint when the line changes', () => {
    const { primitive, requestUpdate } = attach(100);
    primitive.setLine(SPEC as never);
    expect(requestUpdate).toHaveBeenCalledTimes(1);
    expect(primitive.current()).toEqual(SPEC);
    primitive.setLine(null);
    expect(primitive.current()).toBeNull();
  });
});
