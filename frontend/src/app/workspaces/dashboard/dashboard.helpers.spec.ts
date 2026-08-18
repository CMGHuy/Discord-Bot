import { describe, expect, it } from 'vitest';

import {
  deriveClosedVisible,
  deriveOpenVisible,
  expectedPnlPct,
  expectedR,
  expectedSlPct,
  livePnlPct,
  reconcileReorder,
} from './dashboard.helpers';

describe('deriveClosedVisible', () => {
  it('drops "now" and inserts "hold" immediately before "opened_at"', () => {
    const base = ['num', 'status', 'ticker', 'now', 'plan', 'opened_at', 'closed_at'];
    expect(deriveClosedVisible(base)).toEqual([
      'num', 'status', 'ticker', 'plan', 'hold', 'opened_at', 'closed_at',
    ]);
  });

  it('appends "hold" at the end when "opened_at" is itself hidden', () => {
    const base = ['num', 'status', 'ticker', 'now'];
    expect(deriveClosedVisible(base)).toEqual(['num', 'status', 'ticker', 'hold']);
  });

  it('does not duplicate "hold" if it is already in the base list', () => {
    // Can happen after reconcileReorder round-trips a shared list that a
    // prior derivation already touched.
    const base = ['num', 'hold', 'opened_at'];
    expect(deriveClosedVisible(base)).toEqual(['num', 'hold', 'opened_at']);
  });

  it('leaves a list with neither "now" nor "opened_at" only gaining "hold"', () => {
    expect(deriveClosedVisible(['num', 'status'])).toEqual(['num', 'status', 'hold']);
  });

  it('drops "direction" -- it folds into the Confidence cell instead', () => {
    const base = ['num', 'status', 'direction', 'confidence_level', 'opened_at'];
    expect(deriveClosedVisible(base)).toEqual([
      'num', 'status', 'confidence_level', 'hold', 'opened_at',
    ]);
  });
});

describe('deriveOpenVisible', () => {
  it('drops "closed_at" and leaves everything else in place', () => {
    const base = ['num', 'status', 'ticker', 'opened_at', 'closed_at', 'pnl_pct'];
    expect(deriveOpenVisible(base)).toEqual(['num', 'status', 'ticker', 'opened_at', 'pnl_pct']);
  });

  it('is a no-op when "closed_at" is not present', () => {
    const base = ['num', 'status', 'ticker'];
    expect(deriveOpenVisible(base)).toEqual(base);
  });

  it('drops "direction" -- it folds into the Confidence cell instead', () => {
    const base = ['num', 'direction', 'confidence_level', 'now'];
    expect(deriveOpenVisible(base)).toEqual(['num', 'confidence_level', 'now']);
  });
});

describe('reconcileReorder', () => {
  it('drops "hold" and restores "now" when the base list carried it', () => {
    // The Closed group's own rendered order: no 'now', 'hold' inserted.
    const order = ['num', 'hold', 'opened_at'];
    const base = ['num', 'now', 'opened_at'];
    expect(reconcileReorder(order, base)).toEqual(['num', 'opened_at', 'now']);
  });

  it('restores "closed_at" when an Active/Pending/Partial group reorders', () => {
    const order = ['num', 'ticker'];
    const base = ['num', 'ticker', 'closed_at'];
    expect(reconcileReorder(order, base)).toEqual(['num', 'ticker', 'closed_at']);
  });

  it('does not reintroduce "now"/"closed_at" the base list never had', () => {
    // The user's own picker choice hid these -- a drag inside one group must
    // not resurrect a column another part of the UI deliberately removed.
    const order = ['num', 'ticker'];
    const base = ['num', 'ticker'];
    expect(reconcileReorder(order, base)).toEqual(['num', 'ticker']);
  });

  it('leaves an order that already carries both columns untouched (besides dropping hold)', () => {
    const order = ['num', 'now', 'closed_at', 'hold'];
    const base = ['num', 'now', 'closed_at'];
    expect(reconcileReorder(order, base)).toEqual(['num', 'now', 'closed_at']);
  });

  it('restores "direction" when a drag drops it, since every group omits it', () => {
    const order = ['num', 'ticker'];
    const base = ['num', 'ticker', 'direction'];
    expect(reconcileReorder(order, base)).toEqual(['num', 'ticker', 'direction']);
  });
});

describe('expectedPnlPct', () => {
  it('is positive for a bullish row whose target sits above entry', () => {
    expect(expectedPnlPct({ entry: 100, trigger_price: null, target: 110, direction: 'bullish' }))
      .toBeCloseTo(10);
  });

  it('is positive for a bearish row whose target sits below entry', () => {
    expect(expectedPnlPct({ entry: 100, trigger_price: null, target: 90, direction: 'bearish' }))
      .toBeCloseTo(10);
  });

  it('is negative for a bearish row whose target sits above entry', () => {
    expect(expectedPnlPct({ entry: 100, trigger_price: null, target: 110, direction: 'bearish' }))
      .toBeCloseTo(-10);
  });

  it('falls back to trigger_price for a PENDING stop-entry row with no fill yet', () => {
    // Same fallback PlanCell uses for its own first-number display.
    expect(expectedPnlPct({ entry: null, trigger_price: 100, target: 110, direction: 'bullish' }))
      .toBeCloseTo(10);
  });

  it('is null once neither entry nor trigger_price, or no target, is known', () => {
    expect(expectedPnlPct({ entry: null, trigger_price: null, target: 110, direction: 'bullish' }))
      .toBeNull();
    expect(expectedPnlPct({ entry: 100, trigger_price: null, target: null, direction: 'bullish' }))
      .toBeNull();
    expect(expectedPnlPct({ entry: 0, trigger_price: null, target: 110, direction: 'bullish' }))
      .toBeNull();
  });
});

describe('expectedR', () => {
  it('is the reward:risk ratio for a bullish row', () => {
    // Risk = 100-90 = 10, reward = 120-100 = 20 -> 2R.
    expect(
      expectedR({ entry: 100, trigger_price: null, target: 120, stop_loss: 90, direction: 'bullish' }),
    ).toBeCloseTo(2);
  });

  it('is the reward:risk ratio for a bearish row', () => {
    // Risk = 110-100 = 10, reward = 100-80 = 20 -> 2R.
    expect(
      expectedR({ entry: 100, trigger_price: null, target: 80, stop_loss: 110, direction: 'bearish' }),
    ).toBeCloseTo(2);
  });

  it('falls back to trigger_price for a PENDING stop-entry row with no fill yet', () => {
    expect(
      expectedR({ entry: null, trigger_price: 100, target: 120, stop_loss: 90, direction: 'bullish' }),
    ).toBeCloseTo(2);
  });

  it('is null when the stop is missing or equals entry (zero risk)', () => {
    expect(
      expectedR({ entry: 100, trigger_price: null, target: 120, stop_loss: null, direction: 'bullish' }),
    ).toBeNull();
    expect(
      expectedR({ entry: 100, trigger_price: null, target: 120, stop_loss: 100, direction: 'bullish' }),
    ).toBeNull();
  });

  it('is null once neither entry nor trigger_price, or no target, is known', () => {
    expect(
      expectedR({ entry: null, trigger_price: null, target: 120, stop_loss: 90, direction: 'bullish' }),
    ).toBeNull();
    expect(
      expectedR({ entry: 100, trigger_price: null, target: null, stop_loss: 90, direction: 'bullish' }),
    ).toBeNull();
  });
});

describe('expectedSlPct', () => {
  it('is negative for a bullish row whose stop sits below entry', () => {
    expect(expectedSlPct({ entry: 100, trigger_price: null, stop_loss: 90, direction: 'bullish' }))
      .toBeCloseTo(-10);
  });

  it('is negative for a bearish row whose stop sits above entry', () => {
    expect(expectedSlPct({ entry: 100, trigger_price: null, stop_loss: 110, direction: 'bearish' }))
      .toBeCloseTo(-10);
  });

  it('falls back to trigger_price for a PENDING stop-entry row with no fill yet', () => {
    expect(expectedSlPct({ entry: null, trigger_price: 100, stop_loss: 90, direction: 'bullish' }))
      .toBeCloseTo(-10);
  });

  it('is null once neither entry nor trigger_price, or no stop, is known', () => {
    expect(expectedSlPct({ entry: null, trigger_price: null, stop_loss: 90, direction: 'bullish' }))
      .toBeNull();
    expect(expectedSlPct({ entry: 100, trigger_price: null, stop_loss: null, direction: 'bullish' }))
      .toBeNull();
  });
});

describe('livePnlPct', () => {
  it('is positive for a bullish row trading above entry', () => {
    expect(livePnlPct({ entry: 100, trigger_price: null, current_price: 105, direction: 'bullish' }))
      .toBeCloseTo(5);
  });

  it('is negative for a bullish row trading below entry', () => {
    expect(livePnlPct({ entry: 100, trigger_price: null, current_price: 95, direction: 'bullish' }))
      .toBeCloseTo(-5);
  });

  it('is positive for a bearish row trading below entry', () => {
    expect(livePnlPct({ entry: 100, trigger_price: null, current_price: 95, direction: 'bearish' }))
      .toBeCloseTo(5);
  });

  it('falls back to trigger_price for a PENDING stop-entry row with no fill yet', () => {
    expect(livePnlPct({ entry: null, trigger_price: 100, current_price: 110, direction: 'bullish' }))
      .toBeCloseTo(10);
  });

  it('is null once neither entry nor trigger_price, or no current_price, is known', () => {
    expect(livePnlPct({ entry: null, trigger_price: null, current_price: 105, direction: 'bullish' }))
      .toBeNull();
    expect(livePnlPct({ entry: 100, trigger_price: null, current_price: null, direction: 'bullish' }))
      .toBeNull();
  });
});
