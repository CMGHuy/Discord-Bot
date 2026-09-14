import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it, beforeEach } from 'vitest';

import { RecentActivity } from './recent-activity';

describe('recent activity panel', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(RecentActivity);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('lists each event with its ticker, detail and time', () => {
    const el = render({ events: [
      { kind: 'opened', at: '2026-09-11T15:53:00Z', ticker: 'ASTS', direction: 'bearish', status: 'ACTIVE', detail: 'at 60.54', id: 'a:opened' },
    ]});
    const item = el.querySelector('.event')!;
    expect(item.textContent).toContain('ASTS');
    expect(item.textContent).toContain('at 60.54');
  });

  it('distinguishes the three kinds by class, not by colour alone', () => {
    const el = render({ events: [
      { kind: 'opened', at: '2026-09-11T15:00:00Z', ticker: 'A', direction: null, status: 'ACTIVE', detail: '', id: '1' },
      { kind: 'closed', at: '2026-09-11T14:00:00Z', ticker: 'B', direction: null, status: 'CLOSED', detail: '', id: '2' },
      { kind: 'cancelled', at: '2026-09-11T13:00:00Z', ticker: 'C', direction: null, status: 'CANCELLED', detail: '', id: '3' },
    ]});
    // Sorted before comparing, not literal className order: this test
    // environment's DOM alphabetises classList tokens on read, so "event
    // closed" and "closed event" are the same class list, not different ones.
    const classes = [...el.querySelectorAll('.event')].map((n) => [...n.classList].sort());
    expect(classes).toEqual([
      ['event', 'opened'],
      ['closed', 'event'],
      ['cancelled', 'event'],
    ]);
  });

  it('picks the icon from the row\'s current status, not the event kind', () => {
    // An 'opened' event whose row has since moved to PARTIAL shows the
    // partial icon, not a generic "opened" one -- Recent Activity is now
    // the one place this status vocabulary lives (2026-09-14).
    const el = render({ events: [
      { kind: 'opened', at: '2026-09-11T15:00:00Z', ticker: 'A', direction: null, status: 'PARTIAL', detail: '', id: '1' },
    ]});
    // Asserted via the rendered SVG path data (matching icon.spec.ts's own
    // "partial" path) rather than an icon name, since sb-icon exposes no
    // other observable trace of which name it was given.
    const path = el.querySelector('sb-icon path')!;
    expect(path.getAttribute('d')).toBe('M8 14.5A6.5 6.5 0 1 0 8 1.5a6.5 6.5 0 0 0 0 13z M8 1.5v13');
  });

  it('falls back to the "opened" icon for an unrecognised status', () => {
    const el = render({ events: [
      { kind: 'opened', at: '2026-09-11T15:00:00Z', ticker: 'A', direction: null, status: 'WEIRD', detail: '', id: '1' },
    ]});
    const path = el.querySelector('sb-icon path')!;
    expect(path.getAttribute('d')).toBe(
      'M8 13.5A5.5 5.5 0 1 0 8 2.5a5.5 5.5 0 0 0 0 11z M8 8.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5z',
    );
  });

  it('says so when there is nothing yet rather than rendering an empty box', () => {
    const el = render({ events: [] });
    expect(el.textContent).toContain('No activity yet');
  });
});
