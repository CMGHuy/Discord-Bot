import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LiveAwaiting, LiveEvent, LiveEventsMeta, LiveHeat, LiveKillswitch } from '../../api/models';
import { ConnectionState, ConnectionStore } from '../../stores/connection.store';
import { LiveStore } from '../../stores/live.store';
import { CLOCK } from '../../ui/clock';
import { LiveDock } from './live-dock';

const NOW = new Date('2026-10-29T13:00:00Z');
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const HEAT: LiveHeat = {
  availability: 'ok', as_of: ago(1), reason: null, open_pct: 5, cap_pct: 6, utilisation_pct: 85, open_amount: 2400,
  cap_amount: 2893, headroom_pct: 1, headroom_amount: 493, balance: 48210, includes_resting: true,
};

describe('LiveDock (v203)', () => {
  const live = {
    heat: signal<LiveHeat | null>(HEAT),
    awaiting: signal<LiveAwaiting | null>({ availability: 'ok', as_of: ago(1), reason: null, count: 3, next_expiry: null }),
    killswitch: signal<LiveKillswitch | null>({ availability: 'ok', as_of: ago(1), reason: null, engaged: true, since: '2026-10-29T08:31:00Z', detail: null }),
    events: signal<readonly LiveEvent[]>([]),
    eventsMeta: signal<LiveEventsMeta | null>({ availability: 'ok', as_of: ago(1), missing: [] }),
    loading: signal(false),
    failed: signal(false),
    retry: vi.fn(),
  };
  const connection = {
    botAlive: signal<boolean | null>(false), botHealthy: signal<boolean | null>(true), scanRunning: signal(false),
    botLastSuccess: signal<string | null>(ago(2)), botLastSeen: signal<string | null>(ago(1)),
    state: signal<ConnectionState>('live'), marketActive: signal<boolean | null>(true), currency: signal('$'),
  };

  beforeEach(() => {
    live.retry.mockClear();
    live.heat.set(HEAT);
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(), provideRouter([]), provideHttpClient(), provideHttpClientTesting(),
        { provide: LiveStore, useValue: live },
        { provide: ConnectionStore, useValue: connection },
        { provide: CLOCK, useValue: signal(NOW.getTime()) },
      ],
    });
  });

  function mount(variant: 'docked' | 'sheet') {
    const fixture = TestBed.createComponent(LiveDock);
    fixture.componentRef.setInput('variant', variant);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('holds the four sections in order under a Live head', () => {
    const { el } = mount('docked');
    expect(el.querySelector('.dock-head .dock-title')!.textContent!.trim()).toBe('Live');
    expect([...el.querySelectorAll('.dock > *:not(.dock-head)')].map((node) => node.tagName.toLowerCase()))
      .toEqual(['sb-live-bot', 'sb-live-awaiting', 'sb-live-heat', 'sb-live-activity']);
  });

  it('feeds the sections from LiveStore and ConnectionStore, money in the account currency', () => {
    const { el } = mount('docked');
    const text = (selector: string) => el.querySelector(selector)!.textContent!.replace(/\s+/g, ' ').trim();
    expect(text('sb-live-bot dl > div.row dd')).toBe('Down');
    expect(text('sb-live-bot dl > div.row:last-child dd')).toBe('Active: new alerts paused since 09:31');
    expect(text('sb-live-awaiting .figure')).toBe('3 awaiting order');
    expect(text('sb-live-heat .at-risk')).toBe('2,400 $ at risk · 5% of 48,210 $ · cap 6% (2,893 $)');
    expect(el.querySelector('sb-live-heat .at-risk')!.classList).toContain('warn');
    expect(text('sb-live-activity .quiet')).toBe('Nothing yet today');
  });

  it('routes a section retry to LiveStore.retry', () => {
    live.heat.set({ ...HEAT, availability: 'unavailable', open_pct: null });
    const { el } = mount('docked');
    el.querySelector<HTMLButtonElement>('sb-live-heat button.retry')!.click();
    expect(live.retry).toHaveBeenCalledTimes(1);
  });

  it('collapses from an icon button when docked, and closes from a text button in the sheet', () => {
    const docked = mount('docked');
    let closed = 0;
    docked.fixture.componentInstance.close.subscribe(() => closed++);
    const collapse = docked.el.querySelector<HTMLButtonElement>('.dock-head button')!;
    expect(collapse.getAttribute('aria-label')).toBe('Collapse the live dock');
    expect(collapse.classList).toContain('sb-hit');
    collapse.click();
    expect(closed).toBe(1);
    const sheet = mount('sheet');
    expect(sheet.el.querySelector('.dock-head button')!.textContent!.trim()).toBe('Close');
  });

  it('never touches RiskStore or /risk (spec v202 §4 "Data source")', () => {
    mount('docked');                                        // no RiskStore provider: injecting it would throw
    expect(TestBed.inject(HttpTestingController).match(() => true)).toEqual([]);
    const dir = join(process.cwd(), 'src/app/shell/live');
    const sources = readdirSync(dir).filter((name) => name.endsWith('.ts') && !name.endsWith('.spec.ts'))
      .map((name) => [name, readFileSync(join(dir, name), 'utf8')] as const);
    expect(sources.length).toBeGreaterThan(5);
    expect(sources.filter(([, source]) => /RiskStore|workspaces\/risk|api\.risk\(/.test(source)).map(([name]) => name)).toEqual([]);
  });
});
