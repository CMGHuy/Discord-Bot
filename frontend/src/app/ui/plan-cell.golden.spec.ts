import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { PlanCell, bankedLegAmount } from './plan-cell';
import { goldenOpenCase, loadGoldenPartialTrade } from './testing/golden-partial-trade';

/* v189 B1/B3: the golden scaled-out trade (100 sh, f 0.5, entry 100, stop 95,
 * TP1 110) on the Trades row. Banked TP1 = 50 sh x 10 = $500, contributing
 * +1.00R (TP1 +2.00R on 50%). */

describe('PlanCell on the golden partial trade', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  const golden = loadGoldenPartialTrade();
  const t = golden.trade;

  it.each(['quote_113', 'no_quote'])('banks $500 off the ORIGINAL shares (%s)', (name) => {
    const c = goldenOpenCase(name);
    const amount = bankedLegAmount(t.entry, t.tp1_leg.exit_price, t.tp1_leg.fraction, c.entry_shares, t.direction);
    expect(amount).toBeCloseTo(c.banked_amount, 2);
  });

  it('would halve the banked dollars if fed the remaining shares (the bug B1 fixes)', () => {
    const c = goldenOpenCase('quote_113');
    expect(bankedLegAmount(t.entry, t.tp1_leg.exit_price, t.tp1_leg.fraction, c.shares, t.direction))
      .toBeCloseTo(c.banked_amount / 2, 2);
  });

  it('labels the banked part by its contribution, naming the TP1 leg beside it', () => {
    const c = goldenOpenCase('quote_113');
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', t.entry);
    f.componentRef.setInput('target', t.tp2);
    f.componentRef.setInput('stop', c.working_stop);
    f.componentRef.setInput('stopKind', 'trailing');
    f.componentRef.setInput('bankedFraction', t.tp1_leg.fraction);
    f.componentRef.setInput('bankedR', c.banked_r);
    f.componentRef.setInput('bankedContributionR', c.banked_contribution_r);
    f.componentRef.setInput('bankedPct', 10);
    f.componentRef.setInput('bankedAmount', c.banked_amount);
    f.componentRef.setInput('bankedEntry', t.tp1_leg.exit_price);
    f.componentRef.setInput('currency', '$');
    f.detectChanges();
    const title = (f.nativeElement as HTMLElement).querySelector('[title]')!.getAttribute('title')!;
    expect(title).toContain('banked +1.00R (TP1 +2.00R on 50%), +10.00%, +500.00 $ @ 110.00');
    expect(title).not.toContain('banked +2.00R');
  });

  it('reads the fixture from the repo, the same file pytest reads', () => {
    expect(golden.tolerance).toBe(0.005);
    expect(golden.open_cases.map((c) => c.name)).toEqual(['quote_113', 'no_quote']);
  });
});
