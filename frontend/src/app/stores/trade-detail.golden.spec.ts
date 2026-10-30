import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ApplicationRef, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { goldenOpenCase, loadGoldenPartialTrade } from '../ui/testing/golden-partial-trade';
import { TradeDetailStore } from './trade-detail.store';

/* v189 B1/B5 on the golden scaled-out trade: TP1 banked 50 of 100 shares at
 * 110 (entry 100), runner floor 106.67. Banked $500; risk of loss $0 (the
 * floor is above entry); open profit to stop at 113 = 50 x 6.33 = $316.67. */

const ID = 'golden0000000000';

describe('TradeDetailStore on the golden partial trade', () => {
  let store: InstanceType<typeof TradeDetailStore>;
  let backend: HttpTestingController;
  const golden = loadGoldenPartialTrade();
  const t = golden.trade;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting(), TradeDetailStore],
    });
    store = TestBed.inject(TradeDetailStore);
    backend = TestBed.inject(HttpTestingController);
  });

  function open(name: string): void {
    const c = goldenOpenCase(name);
    store.setId(ID);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush({
      id: ID, ticker: t.ticker, direction: t.direction, status: 'PARTIAL',
      entry: t.entry, stop_loss: c.working_stop, risk_stop: t.stop_loss, target: t.tp2,
      shares: c.shares, open_shares: c.shares, entry_shares: c.entry_shares,
      current_price: c.quote, r_multiple: c.r_multiple,
      banked_fraction: t.tp1_leg.fraction, banked_exit_price: t.tp1_leg.exit_price,
      banked_r: c.banked_r, banked_contribution_r: c.banked_contribution_r,
      detail: { trade_id: ID, note: null, working_stop: c.working_stop, legs_realized: [t.tp1_leg] },
    });
    backend.expectOne(`/api/v1/trades/${ID}/journal`).flush({ journaled: false, entry: null });
    backend.verify();
  }

  it.each(['quote_113', 'no_quote'])('banks $500 off the ORIGINAL shares (%s)', (name) => {
    open(name);
    expect(store.bankedStats()?.amount).toBeCloseTo(goldenOpenCase(name).banked_amount, 2);
    expect(store.bankedStats()?.pct).toBeCloseTo(10, 6);
  });

  it.each(['quote_113', 'no_quote'])('has no risk of loss once the runner floor sits above entry (%s)', (name) => {
    open(name);
    expect(store.riskOfLoss()).toBe(goldenOpenCase(name).risk_of_loss_amount);
  });

  it('shows the open profit to the stop only with a live quote', () => {
    open('quote_113');
    expect(store.openProfitToStop()).toBeCloseTo(goldenOpenCase('quote_113').open_profit_to_stop!, 2);
  });

  it('has no open profit to stop without a quote', () => {
    open('no_quote');
    expect(store.openProfitToStop()).toBeNull();
  });
});
