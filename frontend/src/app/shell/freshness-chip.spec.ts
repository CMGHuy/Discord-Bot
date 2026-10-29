import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { FreshnessChip, scanAge } from './freshness-chip';

const NOW = Date.parse('2026-10-27T12:00:00Z');

describe('scanAge (v195 Phase 3)', () => {
  it.each([
    ['2026-10-27T11:59:40Z', 'just now'],
    ['2026-10-27T11:59:00Z', '1m ago'],
    ['2026-10-27T11:48:00Z', '12m ago'],
    ['2026-10-27T11:00:00Z', '1h ago'],
    ['2026-10-27T09:00:00Z', '3h ago'],
    ['2026-10-25T12:00:00Z', '2d ago'],
  ])('%s reads %s', (at, text) => {
    expect(scanAge(at, NOW)).toBe(text);
  });

  it('is null for a missing or unreadable time', () => {
    expect(scanAge(null, NOW)).toBeNull();
    expect(scanAge('', NOW)).toBeNull();
    expect(scanAge('not a date', NOW)).toBeNull();
  });

  it('never reads a time from the future as negative', () => {
    expect(scanAge('2026-10-27T12:05:00Z', NOW)).toBe('just now');
  });
});

describe('FreshnessChip (v195 Phase 3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(at: string | null, now = NOW): HTMLElement {
    const fixture = TestBed.createComponent(FreshnessChip);
    fixture.componentRef.setInput('at', at);
    fixture.componentRef.setInput('now', now);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  const text = (el: HTMLElement) => el.textContent!.replace(/\s+/g, ' ').trim();

  it('reads the age of the last scan tick', () => {
    const el = render('2026-10-27T11:48:00Z');
    expect(text(el)).toBe('Scan 12m ago');
    expect(el.querySelector('time')!.getAttribute('datetime')).toBe('2026-10-27T11:48:00Z');
  });

  it('says so when the bot has never reported a tick', () => {
    const el = render(null);
    expect(text(el)).toBe('No scan yet');
    expect(el.querySelector('time')).toBeNull();
    expect(el.querySelector('.chip')!.classList).toContain('unknown');
  });

  it('ages as the clock moves, with no timer of its own', () => {
    const fixture = TestBed.createComponent(FreshnessChip);
    fixture.componentRef.setInput('at', '2026-10-27T11:48:00Z');
    fixture.componentRef.setInput('now', NOW);
    fixture.detectChanges();
    fixture.componentRef.setInput('now', NOW + 60 * 60_000);
    fixture.detectChanges();
    expect(text(fixture.nativeElement as HTMLElement)).toBe('Scan 1h ago');
  });

  it('carries no title', () => {
    expect(render('2026-10-27T11:48:00Z').querySelector('[title]')).toBeNull();
  });
});
