import { describe, expect, it, vi } from 'vitest';

import { BaselinePrimitive } from './baseline-primitive';

function fakeContext() {
  return {
    save: vi.fn(), restore: vi.fn(), fillRect: vi.fn(), beginPath: vi.fn(),
    moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), setLineDash: vi.fn(),
    fillStyle: '', strokeStyle: '', lineWidth: 0,
    // fillStyle is overwritten between the two washes; record each fill's colour.
    fills: [] as string[],
  };
}

function attach(coordinate: number | null) {
  const primitive = new BaselinePrimitive();
  const requestUpdate = vi.fn();
  const series = { priceToCoordinate: vi.fn(() => coordinate) };
  primitive.attached({ chart: {}, series, requestUpdate } as never);
  return { primitive, requestUpdate, series };
}

function draw(primitive: BaselinePrimitive) {
  const context = fakeContext();
  context.fillRect.mockImplementation(() => context.fills.push(context.fillStyle));
  const target = { useBitmapCoordinateSpace: (cb: (scope: unknown) => void) => cb({
    context, horizontalPixelRatio: 2, verticalPixelRatio: 2, bitmapSize: { width: 400, height: 300 },
  }) };
  primitive.paneViews()[0].renderer()!.draw(target as never);
  return context;
}

const SPEC = { value: 1000, line: 'LINE', above: 'ABOVE', below: 'BELOW' };

describe('BaselinePrimitive', () => {
  it('washes above and below the baseline and dashes the line across the pane', () => {
    const { primitive, series } = attach(50);
    primitive.setBaseline(SPEC);
    const context = draw(primitive);
    expect(series.priceToCoordinate).toHaveBeenCalledWith(1000);
    // y 50 CSS px = 100 bitmap px.
    expect(context.fillRect).toHaveBeenNthCalledWith(1, 0, 0, 400, 100);
    expect(context.fillRect).toHaveBeenNthCalledWith(2, 0, 100, 400, 200);
    expect(context.fills).toEqual(['ABOVE', 'BELOW']);
    expect(context.setLineDash).toHaveBeenCalledWith([8, 8]);
    expect(context.moveTo).toHaveBeenCalledWith(0, 100.5);
    expect(context.lineTo).toHaveBeenCalledWith(400, 100.5);
    expect(context.strokeStyle).toBe('LINE');
  });

  it('puts the whole pane under water when the baseline sits above the top', () => {
    const { primitive } = attach(-20);
    primitive.setBaseline(SPEC);
    const context = draw(primitive);
    expect(context.fillRect).toHaveBeenNthCalledWith(1, 0, 0, 400, 0);
    expect(context.fillRect).toHaveBeenNthCalledWith(2, 0, 0, 400, 300);
    expect(context.stroke).not.toHaveBeenCalled();
  });

  it('puts the whole pane above water when the baseline sits below the bottom', () => {
    const { primitive } = attach(200);
    primitive.setBaseline(SPEC);
    const context = draw(primitive);
    expect(context.fillRect).toHaveBeenNthCalledWith(1, 0, 0, 400, 300);
    expect(context.fillRect).toHaveBeenNthCalledWith(2, 0, 300, 400, 0);
    expect(context.stroke).not.toHaveBeenCalled();
  });

  it('draws nothing without a baseline or before the scale has a coordinate', () => {
    const { primitive } = attach(null);
    expect(draw(primitive).fillRect).not.toHaveBeenCalled();
    primitive.setBaseline(SPEC);
    expect(draw(primitive).fillRect).not.toHaveBeenCalled();
  });

  it('asks the chart to repaint when the baseline changes, and reports it', () => {
    const { primitive, requestUpdate } = attach(50);
    primitive.setBaseline(SPEC);
    expect(requestUpdate).toHaveBeenCalledTimes(1);
    expect(primitive.current()).toEqual(SPEC);
    primitive.setBaseline(null);
    expect(primitive.current()).toBeNull();
  });

  it('paints behind the candles', () => {
    expect(new BaselinePrimitive().paneViews()[0].zOrder?.()).toBe('bottom');
  });
});
