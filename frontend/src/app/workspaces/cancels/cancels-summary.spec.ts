import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { CancelPrecision, CancelOutcome } from '../../api/models';
import { CancelCardKey, CancelFilter, CancelSplit, NO_FILTER } from '../../stores/cancels.store';
import { CANCEL_PAYLOAD, EMPTY_CANCEL_PAYLOAD, fig } from '../../testing/cancel-fixtures';
import { CancelsSummary } from './cancels-summary';

const CAPTION = 'Hypothetical replay, before commissions, slippage and tax';

function create(data: CancelPrecision = CANCEL_PAYLOAD, filter: CancelFilter = NO_FILTER): ComponentFixture<CancelsSummary> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(CancelsSummary);
  fixture.componentRef.setInput('data', data);
  fixture.componentRef.setInput('filter', filter);
  fixture.detectChanges();
  return fixture;
}

const host = (f: ComponentFixture<CancelsSummary>): HTMLElement => f.nativeElement;
const q = (f: ComponentFixture<CancelsSummary>, sel: string): HTMLElement | null => host(f).querySelector(sel);
const text = (el: Element | null): string => el?.textContent?.replace(/\s+/g, ' ').trim() ?? '';

describe('CancelsSummary', () => {
  it('puts precision and net R side by side at equal prominence, N beside both', () => {
    const f = create();
    const precision = q(f, '[data-figure="precision"]')!;
    const net = q(f, '[data-figure="net-r"]')!;
    expect(text(precision)).toContain('62% of 37');
    expect(text(precision)).toContain('N 37');
    expect(text(net)).toContain('-3.40R');
    expect(text(net)).toContain('N 37');
    expect(precision.querySelector('.value')!.className).toBe(net.querySelector('.value')!.className);
  });

  it('shows R avoided, R missed and both intervals', () => {
    const f = create();
    expect(text(q(f, '[data-figure="net-r"]'))).toContain('R avoided +23.00R · R missed -26.40R');
    expect(text(q(f, '[data-figure="precision"]'))).toContain('95% CI 45–78%');
    expect(text(q(f, '[data-figure="net-r"]'))).toContain('95% CI [-9.10R, +2.30R]');
  });

  it('carries the hypothetical-replay caption on the headline and on the cards', () => {
    const f = create();
    expect(text(q(f, '.headline-block .caption'))).toBe(CAPTION);
    expect(text(q(f, '.cards-block .caption'))).toBe(CAPTION);
  });

  it('says how many cancels reach the precision N, and how many verdicts were ties', () => {
    const f = create();
    expect(text(q(f, '.survival'))).toBe(
      '37 of 52 cancels reach the precision N: 9 unresolved (MTM +1.35R), 4 untriggered after cancel, 2 excluded.');
    expect(text(q(f, '.ties'))).toBe('3 verdicts decided by a same-bar stop and TP1 touch, counted as the stop.');
  });

  it('marks every figure under N 10, and only those', () => {
    const f = create();
    expect(text(q(f, '[data-card="expired"] .small-n'))).toBe('N < 10');
    expect(q(f, '[data-card="invalidated"] .small-n')).not.toBeNull();
    expect(q(f, '[data-card="other"] .small-n')).not.toBeNull();
    expect(q(f, '.without-risk-cap .small-n')).not.toBeNull();
    expect(q(f, '[data-split="origin:next_session"] .small-n')).not.toBeNull();
    expect(q(f, '[data-split="direction:short"] .small-n')).not.toBeNull();
    expect(q(f, '[data-card="risk_cap"] .small-n')).toBeNull();
    expect(q(f, '[data-card="risk_cap_fill"] .small-n')).toBeNull();
    expect(q(f, '[data-figure="precision"] .small-n')).toBeNull();
    expect(q(f, '.baseline .small-n')).toBeNull();
    expect(q(f, '[data-split="origin:regular"] .small-n')).toBeNull();
  });

  it('labels risk_cap a skipped setup and keeps both entry models together', () => {
    const f = create();
    const pair = q(f, '.pair')!;
    expect(pair.querySelector('[data-card="risk_cap"]')).not.toBeNull();
    expect(pair.querySelector('[data-card="risk_cap_fill"]')).not.toBeNull();
    expect(text(pair)).toContain('Outcome of the skipped setup, unaffordable at the cap');
    expect(text(pair)).not.toMatch(/wrong cancel/i);
    expect(text(q(f, '[data-card="risk_cap_fill"]'))).toContain('recorded 0 · estimated 1');
  });

  it('shows the baseline stop-first rate of filled plans', () => {
    const f = create();
    const baseline = text(q(f, '.baseline'));
    expect(baseline).toContain('Filled plans, same window, strategy and horizon');
    expect(baseline).toContain('stop first 58% of 120');
    expect(baseline).toContain('95% CI 50–66%');
  });

  it('stamps the data date, the window, the rule changes and the manual count', () => {
    const f = create();
    expect(text(q(f, '.as-of'))).toBe('Bars as of 2026-10-22 · cancels 2026-07-27 to 2026-10-22');
    const changes = host(f).querySelectorAll('.rule-changes li');
    expect(changes.length).toBe(1);
    expect(text(changes[0])).toBe('2026-09-28 v104 structural stops and stop-ceiling scope');
    expect(text(q(f, '.manual'))).toBe('Manual cancels are your decisions and stay out of every figure: 1.');
  });

  it('emits the card, outcome or split that was clicked', () => {
    const f = create();
    const cards: (CancelCardKey | null)[] = [];
    const outcomes: (CancelOutcome | null)[] = [];
    const splits: (CancelSplit | null)[] = [];
    f.componentInstance.card.subscribe((v) => cards.push(v));
    f.componentInstance.outcome.subscribe((v) => outcomes.push(v));
    f.componentInstance.split.subscribe((v) => splits.push(v));
    q(f, '[data-card="risk_cap"]')!.click();
    q(f, '[data-outcome="wrong"]')!.click();
    q(f, '[data-split="origin:next_session"]')!.click();
    expect(cards).toEqual(['risk_cap']);
    expect(outcomes).toEqual(['wrong']);
    expect(splits).toEqual([{ dim: 'origin', value: 'next_session' }]);
  });

  it('reads the headline counts with no card, in cancel words', () => {
    const f = create();
    expect(text(q(f, '.counts-head'))).toBe('All three reasons, trigger entry');
    expect(text(q(f, '[data-outcome="right"]'))).toBe('Right cancels 23 +23.00R avoided');
    expect(text(q(f, '[data-outcome="wrong"]'))).toBe('Wrong cancels 14 -26.40R missed');
    expect(text(q(f, '[data-outcome="unresolved"]'))).toBe('Unresolved 9 MTM +1.35R');
    expect(text(q(f, '[data-outcome="untriggered_after_cancel"]'))).toBe('Untriggered after cancel 4 no R');
  });

  it("switches the counts to the picked card's figure and words, and presses that card", () => {
    const f = create(CANCEL_PAYLOAD, { ...NO_FILTER, card: 'risk_cap', outcome: 'right' });
    expect(text(q(f, '.counts-head'))).toBe('risk_cap · from the trigger');
    expect(text(q(f, '[data-outcome="right"]'))).toBe('Setup lost 17 +17.00R avoided');
    expect(text(q(f, '[data-outcome="wrong"]'))).toBe('Setup reached TP1 12 -22.20R missed');
    expect(q(f, '[data-card="risk_cap"]')!.getAttribute('aria-pressed')).toBe('true');
    expect(q(f, '[data-card="invalidated"]')!.getAttribute('aria-pressed')).toBe('false');
    expect(q(f, '[data-outcome="right"]')!.getAttribute('aria-pressed')).toBe('true');
    expect(q(f, '.counts .small-n')).toBeNull();
  });

  it('presses the picked split row', () => {
    const f = create(CANCEL_PAYLOAD, { ...NO_FILTER, split: { dim: 'horizon', value: '2m' } });
    expect(q(f, '[data-split="horizon:2m"]')!.getAttribute('aria-pressed')).toBe('true');
    expect(q(f, '[data-split="horizon:4w"]')!.getAttribute('aria-pressed')).toBe('false');
  });

  it('states that cards pool both origins, and the full-target TP1 rule', () => {
    const f = create();
    expect(text(host(f))).toContain('Cards pool regular and next-session plans.');
    expect(text(q(f, '.tp1-note'))).toBe(CANCEL_PAYLOAD.tp1_note);
  });

  it('renders an empty book as — of 0 with the small-N marker, never an error', () => {
    const f = create(EMPTY_CANCEL_PAYLOAD);
    expect(text(q(f, '[data-figure="precision"]'))).toContain('— of 0');
    expect(q(f, '[data-figure="precision"] .small-n')).not.toBeNull();
    expect(text(q(f, '[data-figure="precision"]'))).toContain('95% CI —');
    expect(text(q(f, '.as-of'))).toBe('Bars as of — · no scored cancels');
    expect(text(q(f, '[data-outcome="right"]'))).toBe('Right cancels 0 0.00R avoided');
    expect(q(f, '.rule-changes')).toBeNull();
    expect(host(f).querySelectorAll('.split-empty').length).toBe(3);
    expect(host(f).querySelector('[role="alert"]')).toBeNull();
  });

  it('renders a book where every plan is unresolved', () => {
    const all = fig({ total: 5, counts: { right: 0, wrong: 0, unresolved: 5, untriggered_after_cancel: 0 }, unresolved_r: 0.8 });
    const f = create({ ...EMPTY_CANCEL_PAYLOAD, headline: { all, without_risk_cap: all } });
    expect(text(q(f, '[data-figure="precision"]'))).toContain('— of 0');
    expect(text(q(f, '[data-outcome="unresolved"]'))).toBe('Unresolved 5 MTM +0.80R');
    expect(text(q(f, '.survival'))).toBe(
      '0 of 5 cancels reach the precision N: 5 unresolved (MTM +0.80R), 0 untriggered after cancel, 0 excluded.');
  });
});
