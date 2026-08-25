import { describe, expect, it } from 'vitest';

import {
  deriveClosedVisible,
  deriveOpenVisible,
  expectedPnlPct,
  expectedR,
  expectedSlPct,
  liveUnrealizedAmount,
  livePnlPct,
  reconcileReorder,
} from './dashboard.helpers';

describe('deriveClosedVisible', () => {
  it('drops "now" and inserts "hold" immediately before "opened_at"', () => {
    const base = ['ticker', 'now', 'plan', 'opened_at', 'closed_at'];
    expect(deriveClosedVisible(base)).toEqual([
      'ticker', 'plan', 'hold', 'opened_at', 'closed_at',
    ]);
  });

  it('appends "hold" at the end when "opened_at" is itself hidden', () => {
    const base = ['ticker', 'plan', 'now'];
    expect(deriveClosedVisible(base)).toEqual(['ticker', 'plan', 'hold']);
  });

  it('does not duplicate "hold" if it is already in the base list', () => {
    // Can happen after reconcileReorder round-trips a shared list that a
    // prior derivation already touched.
    const base = ['ticker', 'hold', 'opened_at'];
    expect(deriveClosedVisible(base)).toEqual(['ticker', 'hold', 'opened_at']);
  });

  it('leaves a list with neither "now" nor "opened_at" only gaining "hold"', () => {
    expect(deriveClosedVisible(['ticker', 'plan'])).toEqual(['ticker', 'plan', 'hold']);
  });

  it('drops "direction" -- it folds into the Confidence cell instead', () => {
    const base = ['direction', 'confidence_level', 'opened_at'];
    expect(deriveClosedVisible(base)).toEqual(['confidence_level', 'hold', 'opened_at']);
  });

  it('drops "num" and "status" -- every row here is closed, and # is empty', () => {
    // The group heading already says CLOSED, and the Dashboard attaches no
    // cell to 'num', so both columns spent width saying nothing.
    const base = ['num', 'status', 'ticker', 'pnl_pct', 'opened_at'];
    expect(deriveClosedVisible(base)).toEqual(['ticker', 'pnl_pct', 'hold', 'opened_at']);
  });

  it('drops "held" so it cannot sit beside "hold" at a coarser precision', () => {
    // 'held' ships in the default column set; both measure the same duration.
    const base = ['ticker', 'held', 'opened_at'];
    expect(deriveClosedVisible(base)).toEqual(['ticker', 'hold', 'opened_at']);
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

  it('restores "num", "status" and "held" after a drag inside the Closed table', () => {
    // Closed drops all three (see CLOSED_DROPS). Without this a drag there
    // would delete them from the OTHER three groups' tables too.
    const order = ['ticker', 'pnl_pct', 'hold'];
    const base = ['num', 'status', 'ticker', 'pnl_pct', 'held'];
    expect(reconcileReorder(order, base)).toEqual([
      'ticker', 'pnl_pct', 'held', 'num', 'status',
    ]);
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

describe('liveUnrealizedAmount', () => {
  it('is the full price move times shares before any leg has realized', () => {
    // (105-100) * 10 = 50.
    expect(
      liveUnrealizedAmount({ entry: 100, current_price: 105, open_shares: 10, direction: 'bullish' }),
    ).toBeCloseTo(50);
  });

  it('is HALVED for a PARTIAL row whose open_shares reflects a realized TP1 leg', () => {
    // Same price move, same percentage -- but only half the shares are
    // still exposed, so the dollar figure is half of the full-size case
    // above: (105-100) * 5 = 25, not 50.
    expect(
      liveUnrealizedAmount({ entry: 100, current_price: 105, open_shares: 5, direction: 'bullish' }),
    ).toBeCloseTo(25);
  });

  it('is negative for a bearish row trading against direction', () => {
    expect(
      liveUnrealizedAmount({ entry: 100, current_price: 105, open_shares: 10, direction: 'bearish' }),
    ).toBeCloseTo(-50);
  });

  it('is null for a PENDING row -- no fill means no shares bought yet', () => {
    // Unlike livePnlPct, this does NOT fall back to trigger_price: a
    // percentage can be projected before a fill, a dollar figure cannot.
    expect(
      liveUnrealizedAmount({ entry: null, current_price: 105, open_shares: null, direction: 'bullish' }),
    ).toBeNull();
  });

  it('is null once current_price is unknown', () => {
    expect(
      liveUnrealizedAmount({ entry: 100, current_price: null, open_shares: 10, direction: 'bullish' }),
    ).toBeNull();
  });
});
