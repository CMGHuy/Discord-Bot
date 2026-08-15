import { describe, expect, it } from 'vitest';

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
