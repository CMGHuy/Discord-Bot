import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { TradeRow } from '../../api/models';
import { ChartStore } from '../../stores/chart.store';
import { TradesStore } from '../../stores/trades.store';
import { TickerDetail } from './ticker-detail';

function row(overrides: Partial<TradeRow>): TradeRow {
  return {
    id: 't1', origin: 'plan', status: 'CLOSED', ticker: 'AAPL',
    direction: 'bullish', strategy: null, horizon: null, tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 100, stop_loss: 95, target: 110, target2: null,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: null, shares: 5, open_shares: null, position_value: null,
    current_price: null, current_price_stale: false, exit_price: 110, realized_pnl_amount: 50,
    pnl_pct: 10, r_multiple: 2, held_hours: 1, opened_at: null, closed_at: null,
    has_note: false, today: true, created_at: null, trigger_price: null,
    follow_score: null, progress_pct: null, entry_pct: null, progress_band: null,
    blink_seconds: null, status_label: 'CLOSED', target_is_banked_tp1: false,
    stop_kind: 'risk', bar_kind: 'none', floor_r: null, price_r: null,
    headroom_r: null, distance_to_trigger_r: null, bars_to_expiry: null,
    leg_index: 0, leg_total: 1,
    ...overrides,
  } as TradeRow;
}

describe('TickerDetail rowKey', () => {
  it('is unique for two leg-rows sharing one id', () => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(), provideRouter([]),
        provideHttpClient(), provideHttpClientTesting(),
        TradesStore, ChartStore,
      ],
    });
    const f = TestBed.createComponent(TickerDetail);
    const rowKey = (f.componentInstance as unknown as {
      rowKey: (r: TradeRow) => string;
    }).rowKey;

    // This view renders rows from the same leg-expanding /api/v1/trades the
    // Trades table reads, so a scaled-out position arrives as two rows that
    // share one plan id -- `row.id` alone is not a key.
    const tp1 = row({ leg_index: 0, leg_total: 2 });
    const runner = row({ leg_index: 1, leg_total: 2 });
    expect(rowKey(tp1)).not.toBe(rowKey(runner));
  });
});
