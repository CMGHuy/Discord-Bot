import { describe, expect, it } from 'vitest';
import type { TradeRow } from '../../api/models';
import { ABSENT } from '../../ui/format';
import { outcomeTiles, StripContext } from './outcome-tiles';

function context(status = 'CLOSED', overrides: Partial<TradeRow> = {}): StripContext {
  return {
    trade: { status, entry: 100, exit_price: 110, shares: 10, current_price: 105,
      stop_loss: 95, target: 110, r_multiple: 2, pnl_pct: 10,
      realized_pnl_amount: 100, held_hours: 30, trigger_price: 101,
      bars_to_expiry: 3, distance_to_trigger_r: 0.2, ...overrides } as TradeRow,
    legs: [], history: [], riskPerShare: 5, banked: null, bankedStats: null,
    expiresOn: '2026-10-20', timeExitOn: '2026-10-21', now: new Date('2026-10-17'),
  };
}

describe('outcomeTiles', () => {
  it('summarises a closed result with original risk and weighted exits', () => {
    const ctx = context();
    ctx.legs = [
      { fraction: 0.5, exitPrice: 110, r: 2, reason: 'tp1' },
      { fraction: 0.5, exitPrice: 100, r: 0, reason: 'runner_be' },
    ];
    const tiles = outcomeTiles(ctx);
    expect(tiles.map(t => t.id)).toEqual(['result', 'pnl', 'entry-exit', 'held', 'exit']);
    expect(tiles[0]).toMatchObject({ value: '+2.00R', sub: '1R = $50.00 · +2.00R / 0.00R', tone: 'pos' });
    expect(tiles[1]).toMatchObject({ value: '+100.00', sub: '+10.00% on position', costCaption: true });
    expect(tiles[2].value).toBe('100.00 → 105.00');
    expect(tiles[4].value).toBe('TP1 + Runner at breakeven');
  });

  it.each(['ACTIVE', 'PARTIAL'])('keeps %s open even with a settled exit field', status => {
    const tiles = outcomeTiles(context(status, { current_price_stale: true }));
    expect(tiles.map(t => t.id)).toEqual(['price', 'unrealised', 'progress', 'held']);
    expect(tiles[0]).toMatchObject({ value: '105.00', stale: true, tone: null });
    expect(tiles[1].stale).toBe(true);
    expect(tiles[1].sub).toContain(status === 'PARTIAL' ? 'on open shares' : 'on position');
    expect(tiles[2].indicator).toMatchObject({ current: 105, stop: 95, target: 110 });
    expect(tiles[3].sub).toBe('time exit in 4d');
  });

  it('appends the banked leg independently of the remaining position', () => {
    const ctx = context('PARTIAL', { r_multiple: -1 });
    ctx.banked = { fraction: 0.5, exitPrice: 110, r: 2, reason: 'tp1' };
    ctx.bankedStats = { pct: 10, amount: 50 };
    expect(outcomeTiles(ctx).at(-1)).toMatchObject({ id: 'banked', value: '50% @ 110.00',
      sub: '+2.00R · +10.00% · +50.00', tone: 'pos', costCaption: true });
  });

  it('uses pending status before an exit price', () => {
    const tiles = outcomeTiles(context('PENDING'));
    expect(tiles.map(t => t.id)).toEqual(['trigger', 'distance', 'expires', 'created']);
    expect(tiles[0]).toMatchObject({ value: '101.00', sub: 'now 105.00 · -3.81% to trigger' });
    expect(tiles[1].value).toBe('0.20R');
    expect(tiles[2].sub).toBe('3 bars left');
  });

  it('shows an unfilled status and its real history reason', () => {
    const ctx = context('CANCELLED', { exit_price: null });
    ctx.history = [{ status: 'CANCELLED', reason: 'manually cancelled', at: null }];
    const tiles = outcomeTiles(ctx);
    expect(tiles.map(t => t.id)).toEqual(['status', 'created', 'trigger', 'fill']);
    expect(tiles[0]).toMatchObject({ value: 'Cancelled', sub: 'manually cancelled' });
    expect(tiles[3].value).toBe('Never filled');
  });

  it.each([0, 0.099, -0.099, null, undefined])('keeps near-zero or absent R %s neutral', r => {
    const tiles = outcomeTiles(context('CLOSED', { r_multiple: r }));
    expect(tiles.every(t => t.tone === null)).toBe(true);
  });

  it.each(['CLOSED', 'ACTIVE', 'PENDING', 'CANCELLED'])('handles omitted fixture values in %s', status => {
    const ctx = context();
    ctx.trade = { status } as TradeRow;
    const tiles = outcomeTiles(ctx);
    expect(JSON.stringify(tiles)).not.toMatch(/undefined|NaN/);
    expect(tiles[0].value).toBe(status === 'CANCELLED' ? 'Cancelled' : ABSENT);
  });
});
