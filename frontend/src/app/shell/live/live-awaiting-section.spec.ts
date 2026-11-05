import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveAwaiting } from '../../api/models';
import { LiveAwaitingSection, awaitingView, expiryDay } from './live-awaiting-section';

const NOW = new Date('2026-10-29T13:00:00Z');              // 14:00 Berlin
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const awaiting = (over: Partial<LiveAwaiting> = {}): LiveAwaiting => ({
  availability: 'ok', as_of: ago(6), reason: null, count: 3, next_expiry: '2026-10-30T20:00:00+00:00', ...over,
});

describe('expiryDay', () => {
  it('prints the Berlin calendar day', () => expect(expiryDay('2026-10-30T20:00:00+00:00')).toBe('30 Oct'));
  it('crosses midnight in Berlin, not in UTC', () => expect(expiryDay('2026-10-30T23:30:00Z')).toBe('31 Oct'));
  it.each([[null], [''], ['garbage']])('is null for %s', (iso) => expect(expiryDay(iso)).toBeNull());
});

describe('awaitingView (spec v202 §4.2, §6)', () => {
  it('is loading before the first answer, and unavailable when that answer failed', () => {
    expect(awaitingView(null, true, NOW).state).toBe('loading');
    expect(awaitingView(null, false, NOW).state).toBe('unavailable');
  });
  it.each<[Partial<LiveAwaiting>]>([[{ availability: 'unavailable', count: null, reason: 'db down' }], [{ count: null }]])(
    'is unavailable for %o', (change) => expect(awaitingView(awaiting(change), false, NOW).state).toBe('unavailable'));
  it('is empty at zero, and ok above it', () => {
    expect(awaitingView(awaiting({ count: 0, next_expiry: null }), false, NOW).state).toBe('empty');
    expect(awaitingView(awaiting(), false, NOW)).toEqual({
      state: 'ok', count: 3, expiry: '30 Oct', reason: null, asOf: '13:54 · 6m ago', stale: false,
    });
  });
  it('guesses no expiry for bar-count plans', () => expect(awaitingView(awaiting({ next_expiry: null }), false, NOW).expiry).toBeNull());
  it('marks a snapshot older than 900 s as stale', () => {
    expect(awaitingView(awaiting({ as_of: ago(16) }), false, NOW).stale).toBe(true);
    expect(awaitingView(awaiting({ as_of: ago(14) }), false, NOW).stale).toBe(false);
  });
});

describe('LiveAwaitingSection', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] }));

  function mount(value: LiveAwaiting | null, loading = false) {
    const fixture = TestBed.createComponent(LiveAwaitingSection);
    fixture.componentRef.setInput('awaiting', value);
    fixture.componentRef.setInput('loading', loading);
    fixture.componentRef.setInput('now', NOW);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }
  const text = (node: Element) => node.textContent!.replace(/\s+/g, ' ').trim();

  it('titles the section', () => {
    const section = mount(awaiting()).querySelector('section[aria-labelledby]')!;
    expect(section.querySelector(`#${section.getAttribute('aria-labelledby')}`)!.textContent!.trim()).toBe('Plans awaiting order');
  });

  it('shows the count, the next expiry and a link to the pending plans in the Book', () => {
    const el = mount(awaiting());
    expect(text(el.querySelector('.figure')!)).toBe('3 awaiting order');
    expect(text(el.querySelector('.aside-note')!)).toBe('Next expires 30 Oct');
    const link = el.querySelector<HTMLAnchorElement>('a.link')!;
    expect(link.getAttribute('href')).toBe('/trades?status=PENDING');
    expect(link.textContent!.trim()).toBe('Show in Book ›');
    expect(link.classList).toContain('sb-hit');
    expect(text(el.querySelector('.as-of')!)).toBe('As of 13:54 · 6m ago');
  });

  it('shows zero without a link or an expiry', () => {
    const el = mount(awaiting({ count: 0, next_expiry: null }));
    expect(text(el.querySelector('.figure')!)).toBe('0 awaiting order');
    expect(el.querySelector('a.link')).toBeNull();
    expect(el.querySelector('.aside-note')).toBeNull();
  });

  it('says loading, and says unavailable with the reason', () => {
    expect(text(mount(null, true).querySelector('[role=status]')!)).toBe('Loading…');
    const el = mount(awaiting({ availability: 'unavailable', count: null, reason: 'db down' }));
    expect(text(el.querySelector('.muted')!)).toBe('Plans unavailable · db down');
    expect(el.querySelector('.as-of')).toBeNull();
  });

  it('tones a stale as-of line', () => {
    expect(mount(awaiting({ as_of: ago(30) })).querySelector('.as-of')!.classList).toContain('warn');
  });
});
