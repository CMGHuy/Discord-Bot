import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveEvent, LiveEventsMeta } from '../../api/models';
import { LiveActivitySection, activityLine, activityView, missingText, pnlParts } from './live-activity-section';

const NOW = new Date('2026-10-29T13:00:00Z');               // 14:00 Berlin
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const event = (over: Partial<LiveEvent> = {}): LiveEvent => ({
  at: ago(6), kind: 'trade_closed', text: 'NVDA closed · TP2', tone: 'positive', ref: '812', pnl: { r: 2.1, amount: 441 }, ...over,
});
const ALERT = event({ kind: 'plan_alerted', text: 'AAPL plan alerted · long', tone: 'info', pnl: null, at: ago(20) });
const meta = (over: Partial<LiveEventsMeta> = {}): LiveEventsMeta => ({ availability: 'ok', as_of: ago(0), missing: [], ...over });

describe('activityLine (spec v202 §4.4)', () => {
  it('appends R, its amount and the paper label to a P&L row', () => {
    expect(activityLine(event())).toBe('NVDA closed · TP2 · +2.1R (441 €) (paper, pre-cost)');
    expect(activityLine(event(), '$')).toBe('NVDA closed · TP2 · +2.1R (441 $) (paper, pre-cost)');
  });
  it('signs a loss with a true minus and keeps the amount unsigned', () => {
    expect(activityLine(event({ pnl: { r: -1, amount: -210 }, tone: 'negative' }))).toBe('NVDA closed · TP2 · −1.0R (210 €) (paper, pre-cost)');
  });
  it('omits a missing amount, and leaves a row without P&L alone', () => {
    expect(activityLine(event({ pnl: { r: 1, amount: null } }))).toBe('NVDA closed · TP2 · +1.0R (paper, pre-cost)');
    expect(activityLine(ALERT)).toBe('AAPL plan alerted · long');
    expect(pnlParts(null, '€')).toBeNull();
  });
});

describe('missingText', () => {
  it('words the kinds of a failed source', () => {
    expect(missingText(meta({ availability: 'partial', missing: ['tp1_hit', 'paper_filled'] }))).toBe('Some sources unavailable: TP1 hits, paper fills');
    expect(missingText(meta({ availability: 'partial', missing: [] }))).toBe('Some sources unavailable');
    expect(missingText(meta())).toBeNull();
  });
});

describe('activityView (spec v202 §6)', () => {
  it('is loading, then unavailable when the first answer failed or the source is down', () => {
    expect(activityView([], null, true, ago(2), NOW, '€').state).toBe('loading');
    expect(activityView([], null, false, ago(2), NOW, '€').state).toBe('unavailable');
    expect(activityView([], meta({ availability: 'unavailable' }), false, ago(2), NOW, '€').state).toBe('unavailable');
  });
  it('reads Nothing yet today only with no rows and a recent scan', () => {
    expect(activityView([], meta(), false, ago(2), NOW, '€')).toMatchObject({ state: 'ok', quiet: true, scanWarning: null });
    expect(activityView([ALERT], meta(), false, ago(2), NOW, '€').quiet).toBe(false);
  });
  it('never reads a missed scan as a quiet day', () => {
    expect(activityView([], meta(), false, ago(300), NOW, '€')).toMatchObject({ quiet: false, scanWarning: 'No scan since 09:00 (5h ago)' });
    expect(activityView([ALERT], meta(), false, ago(300), NOW, '€').scanWarning).toBe('No scan since 09:00 (5h ago)');
    expect(activityView([], meta(), false, null, NOW, '€')).toMatchObject({ quiet: false, scanWarning: 'No scan yet' });
  });
  it('builds a row per event with its time, tone and P&L parts', () => {
    expect(activityView([event()], meta(), false, ago(2), NOW, '€').rows).toEqual([{
      key: `${ago(6)}|trade_closed|812`, time: '13:54 · 6m ago', text: 'NVDA closed · TP2', tone: 'positive',
      pnl: { r: '+2.1R', amount: '441 €' }, line: 'NVDA closed · TP2 · +2.1R (441 €) (paper, pre-cost)',
    }]);
  });
});

describe('LiveActivitySection', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] }));

  function mount(events: LiveEvent[], m: LiveEventsMeta | null, lastSuccess: string | null = ago(2), loading = false) {
    const fixture = TestBed.createComponent(LiveActivitySection);
    fixture.componentRef.setInput('events', events);
    fixture.componentRef.setInput('meta', m);
    fixture.componentRef.setInput('loading', loading);
    fixture.componentRef.setInput('lastSuccess', lastSuccess);
    fixture.componentRef.setInput('now', NOW);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }
  const text = (node: Element) => node.textContent!.replace(/\s+/g, ' ').trim();

  it('lists the events newest first as given, each line with its tone', () => {
    const { el } = mount([event(), ALERT], meta());
    expect(text(el.querySelector('h2.title')!)).toBe('Activity');
    const rows = [...el.querySelectorAll('ol.events > li')];
    expect(rows.map((row) => text(row.querySelector('.line')!))).toEqual([activityLine(event()), activityLine(ALERT)]);
    expect(rows.map((row) => text(row.querySelector('time')!))).toEqual(['13:54 · 6m ago', '13:40 · 20m ago']);
    expect(rows[0].classList).toContain('tone-positive');
    expect(rows[0].querySelector('.amt')!.classList).not.toContain('tone');
  });

  it('adds the faint partial line after the rows', () => {
    const { el } = mount([ALERT], meta({ availability: 'partial', missing: ['tp1_hit'] }));
    const faint = el.querySelector('ol.events + .faint')!;
    expect(text(faint)).toBe('Some sources unavailable: TP1 hits');
  });

  it('says Nothing yet today on a quiet, fresh day', () => {
    const { el } = mount([], meta());
    expect(text(el.querySelector('.quiet')!)).toBe('Nothing yet today');
    expect(el.querySelector('.scan-warning')).toBeNull();
  });

  it('warns No scan since 09:00 (5h ago) when the bot stopped, never Nothing yet today', () => {
    const { el } = mount([], meta(), ago(300));
    const warning = el.querySelector('.scan-warning')!;
    expect(text(warning)).toBe('No scan since 09:00 (5h ago)');
    expect(warning.classList).toContain('warn');
    expect(el.querySelector('.quiet')).toBeNull();
  });

  it('shows Activity unavailable with a retry, and still links the full log', () => {
    const { fixture, el } = mount([], meta({ availability: 'unavailable' }));
    let retried = 0;
    fixture.componentInstance.retry.subscribe(() => retried++);
    expect(text(el.querySelector('sb-panel-error')!)).toContain('Activity unavailable');
    el.querySelector<HTMLButtonElement>('sb-panel-error button.retry')!.click();
    expect(retried).toBe(1);
    const link = el.querySelector<HTMLAnchorElement>('a.link')!;
    expect(link.getAttribute('href')).toBe('/system?tab=logs');
    expect(link.textContent!.trim()).toBe('Full activity log →');
    expect(link.classList).toContain('sb-hit');
  });

  it('says loading before the first answer, with no link yet', () => {
    const { el } = mount([], null, ago(2), true);
    expect(text(el.querySelector('[role=status]')!)).toBe('Loading…');
    expect(el.querySelector('a.link')).toBeNull();
  });
});
