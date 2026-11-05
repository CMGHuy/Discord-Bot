import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveHeat } from '../../api/models';
import { LiveHeatSection, atRiskText, heatView, roomText, utilisationText } from './live-heat-section';

const NOW = new Date('2026-10-29T13:00:00Z');
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const heat = (over: Partial<LiveHeat> = {}): LiveHeat => ({
  availability: 'ok', as_of: ago(6), reason: null, open_pct: 4.2, cap_pct: 6, utilisation_pct: 70, open_amount: 2010,
  cap_amount: 2893, headroom_pct: 1.8, headroom_amount: 883, balance: 48210, includes_resting: true, ...over,
});
const OVER: Partial<LiveHeat> = { open_pct: 7.8, utilisation_pct: 130, open_amount: 3760, headroom_pct: -1.8, headroom_amount: -867 };

describe('heat words (spec v202 §4.3)', () => {
  it('reads dollars and percent against the balance and the cap', () => {
    expect(atRiskText(heat(), '€')).toBe('2,010 € at risk · 4.2% of 48,210 € · cap 6% (2,893 €)');
  });
  it('drops only the words a missing figure would print', () => {
    expect(atRiskText(heat({ open_amount: null, balance: null, cap_amount: null }), '€')).toBe('At risk · 4.2% · cap 6%');
    expect(atRiskText(heat({ open_pct: null }), '€')).toBe('—');
  });
  it('reads the room left, or how far over the cap', () => {
    expect(roomText(heat(), '€')).toBe('Room 883 € · 1.8% under the cap');
    expect(roomText(heat(OVER), '€')).toBe('Over cap by 867 € · 1.8%');
    expect(roomText(heat({ headroom_amount: null }), '€')).toBe('Room 1.8% under the cap');
    expect(roomText(heat({ headroom_pct: null }), '€')).toBe('—');
  });
  it.each<[number | null, string]>([[70, '70% of the cap'], [80, '80% of the cap'], [100, '100% of the cap'],
    [130, '130% of the cap · Over cap'], [null, '—']])('never clamps: %s reads %s', (pct, words) => expect(utilisationText(pct)).toBe(words));
});

describe('heatView', () => {
  it('is loading, then unavailable when the first answer failed', () => {
    expect(heatView(null, true, '€', NOW).state).toBe('loading');
    expect(heatView(null, false, '€', NOW)).toMatchObject({ state: 'unavailable', message: 'Heat unavailable' });
  });
  it.each<[Partial<LiveHeat>, string]>([
    [{ availability: 'unavailable', reason: 'no balance' }, 'Heat unavailable (no balance)'],
    [{ open_pct: null }, 'Heat unavailable'],
    [{ cap_pct: null }, 'Heat unavailable'],
  ])('is unavailable for %o', (change, message) => {
    expect(heatView(heat(change), false, '€', NOW)).toMatchObject({ state: 'unavailable', message });
  });
  it.each<[number, string, number]>([[70, 'ok', 70], [80, 'near', 80], [130, 'over', 100], [-5, 'ok', 0]])(
    'tones utilisation %s as %s and fills the meter to %s', (pct, tone, width) => {
      expect(heatView(heat({ utilisation_pct: pct }), false, '€', NOW)).toMatchObject({ state: 'ok', tone, meterWidth: width, utilisationPct: pct });
    });
  it('marks resting orders and a stale snapshot', () => {
    expect(heatView(heat(), false, '€', NOW)).toMatchObject({ resting: true, asOf: '13:54 · 6m ago', stale: false });
    expect(heatView(heat({ includes_resting: false, as_of: ago(20) }), false, '€', NOW)).toMatchObject({ resting: false, stale: true });
  });
});

describe('LiveHeatSection', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function mount(value: LiveHeat | null, loading = false) {
    const fixture = TestBed.createComponent(LiveHeatSection);
    fixture.componentRef.setInput('heat', value);
    fixture.componentRef.setInput('loading', loading);
    fixture.componentRef.setInput('currency', '€');
    fixture.componentRef.setInput('now', NOW);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }
  const text = (node: Element) => node.textContent!.replace(/\s+/g, ' ').trim();

  it('renders the figure, an unclamped meter, the room and the resting note', () => {
    const { el } = mount(heat());
    expect(text(el.querySelector('h2.title')!)).toBe('Portfolio heat');
    expect(text(el.querySelector('.at-risk')!)).toBe('2,010 € at risk · 4.2% of 48,210 € · cap 6% (2,893 €)');
    const meter = el.querySelector('[role=meter]')!;
    expect(meter.getAttribute('aria-valuenow')).toBe('70');
    expect(meter.getAttribute('aria-label')).toBe('Portfolio heat against the cap');
    expect(el.querySelector<HTMLElement>('.fill')!.style.width).toBe('70%');
    expect(text(el.querySelector('.room')!)).toBe('Room 883 € · 1.8% under the cap');
    expect(text(el.querySelector('.aside-note')!)).toBe('incl. resting orders');
    expect(el.querySelectorAll('.warn').length).toBe(0);
  });

  it('turns amber at 80 % and says Over cap above 100 %, the meter value unclamped', () => {
    expect(mount(heat({ utilisation_pct: 80 })).el.querySelector('.at-risk')!.classList).toContain('warn');
    const { el } = mount(heat(OVER));
    expect(text(el.querySelector('.util')!)).toBe('130% of the cap · Over cap');
    expect(el.querySelector('[role=meter]')!.getAttribute('aria-valuenow')).toBe('130');
    expect(el.querySelector<HTMLElement>('.fill')!.style.width).toBe('100%');
    expect(el.querySelector('.fill')!.classList).toContain('warn');
  });

  it('shows the panel error with a retry when heat is unavailable', () => {
    const { fixture, el } = mount(heat({ availability: 'unavailable', open_pct: null, reason: 'db down' }));
    let retried = 0;
    fixture.componentInstance.retry.subscribe(() => retried++);
    expect(text(el.querySelector('sb-panel-error')!)).toContain('Heat unavailable (db down)');
    el.querySelector<HTMLButtonElement>('sb-panel-error button.retry')!.click();
    expect(retried).toBe(1);
    expect(el.querySelector('[role=meter]')).toBeNull();
  });

  it('says loading before the first answer', () => {
    expect(text(mount(null, true).el.querySelector('[role=status]')!)).toBe('Loading…');
  });
});
