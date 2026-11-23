import { readFileSync } from 'node:fs';
import { join } from 'node:path';
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
    expect(path.getAttribute('d')).toBe('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z');
  });

  it('falls back to the "opened" icon for an unrecognised status', () => {
    const el = render({ events: [
      { kind: 'opened', at: '2026-09-11T15:00:00Z', ticker: 'A', direction: null, status: 'WEIRD', detail: '', id: '1' },
    ]});
    const path = el.querySelector('sb-icon path')!;
    expect(path.getAttribute('d')).toBe(
      'M8.2 15.8a5.4 5.4 0 0 1 0-7.6 M15.8 8.2a5.4 5.4 0 0 1 0 7.6 M5.4 18.6a9.3 9.3 0 0 1 0-13.2 M18.6 5.4a9.3 9.3 0 0 1 0 13.2',
    );
  });

  it('gives the status icon a tooltip and accessible name', () => {
    const el = render({ events: [
      { kind: 'opened', at: '2026-09-11T15:00:00Z', ticker: 'A', direction: null, status: 'PARTIAL', detail: '', id: '1' },
    ]});
    const icon = el.querySelector('sb-icon')!;
    expect(icon.getAttribute('title')).toBe('Partial');
    expect(icon.getAttribute('aria-label')).toBe('Partial');
  });

  it('draws the status icon at 20px, the list size (v240 §4)', () => {
    const el = render({ events: [
      { kind: 'opened', at: '2026-09-11T15:00:00Z', ticker: 'A', direction: null, status: 'PARTIAL', detail: '', id: '1' },
    ]});
    // The direct child of the row button: the status icon, not the
    // direction arrow's own (16px) icon.
    const svg = el.querySelector('.event-hit > sb-icon svg')!;
    expect(svg.getAttribute('width')).toBe('20');
    expect(svg.getAttribute('height')).toBe('20');
  });

  it('says so when there is nothing yet rather than rendering an empty box', () => {
    const el = render({ events: [] });
    expect(el.textContent).toContain('No activity yet');
  });
});

const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/panels/recent-activity.ts'), 'utf8');
const rule = (selector: string) => SOURCE.match(
  new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\{[^}]*\\}`),
)?.[0] ?? '';

describe('recent activity rows open a trade (v179 section 3.2, section 6b.3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  const EVENTS = [
    { kind: 'opened', at: '2026-09-11T15:00:00Z', ticker: 'ASTS', direction: 'bullish', status: 'ACTIVE',
      detail: 'at 60.54', r: null, id: 't1:opened', tradeId: 't1' },
    { kind: 'closed', at: '2026-09-11T14:00:00Z', ticker: 'HOOD', direction: 'bearish', status: 'CLOSED',
      detail: 'Closed at +1.20R', r: 1.2, id: 't2:closed', tradeId: 't2' },
  ];

  function mount() {
    const f = TestBed.createComponent(RecentActivity);
    f.componentRef.setInput('events', EVENTS);
    f.detectChanges();
    return f;
  }

  it('renders each event as one native button inside its list item', () => {
    const el = mount().nativeElement as HTMLElement;
    const buttons = [...el.querySelectorAll<HTMLButtonElement>('li.event > button.event-hit')];
    expect(buttons).toHaveLength(2);
    expect(buttons.every((b) => b.type === 'button')).toBe(true);
    expect(buttons.every((b) => b.getAttribute('aria-haspopup') === 'dialog')).toBe(true);
    expect(buttons[0].textContent).toContain('ASTS');
    expect(buttons[0].querySelector('time.at')?.getAttribute('datetime')).toBe(EVENTS[0].at);
  });

  it('emits only the event that was activated', () => {
    const f = mount();
    const picked: unknown[] = [];
    f.componentInstance.eventActivate.subscribe((e: unknown) => picked.push(e));
    (f.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button.event-hit')[1].click();
    expect(picked).toEqual([EVENTS[1]]);
  });

  it('gives each row a touch-sized hit area and one text baseline', () => {
    const hit = rule('.event-hit');
    expect(hit).toContain('min-height: var(--control-h)');
    expect(hit).toContain('align-items: baseline');
    expect(hit).toContain('width: 100%');
    expect(rule('.event-hit sb-icon')).toContain('align-self: center');
    // The arrow is text-like and shares the baseline (5fc0efa6): no centring rule for it.
    expect(rule('.event-hit sb-direction-arrow')).toBe('');
    expect(SOURCE).not.toMatch(/\.event \{[^}]*display: grid/);
  });

  it('shows keyboard focus on the row button', () => {
    expect(rule('.event-hit:focus-visible')).toContain('outline');
  });
});

describe('recent activity row glyphs on the text baseline (v179 layout audit)', () => {
  it('lets the direction arrow, a text glyph, share the ticker baseline; only the svg icon centres', () => {
    expect(rule('.event-hit sb-direction-arrow')).toBe('');
    expect(rule('.event-hit sb-icon')).toContain('align-self: center');
  });
});
