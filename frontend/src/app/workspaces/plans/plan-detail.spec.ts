import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import {
  Signal,
  WritableSignal,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { type MockInstance, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { ChartStore } from '../../stores/chart.store';
import { TradeDetailStore } from '../../stores/trade-detail.store';
import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { RouteTitleService } from '../../routing/route-title.service';
import { PlanDetail, looksLikePlanId, redirectFor, shortOrderNotes, timingLines } from './plan-detail';

// The page renders sb-plan-chart, whose TradeChart asks for matchMedia.
installMatchMediaPolyfill();

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();

  changes(name: string): Signal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter.asReadonly();
  }
}

const PLAN_ID = '44444444-4444-4444-8444-444444444444';
const LEGACY_ID = 'aaaaaaaaaaaaaaaa';

const DETAIL = {
  trade_id: 'ffffffffffffffff',
  note: null,
  created_at: '2026-10-05T14:00:00+00:00',
  plan_source: 'scan',
  entry_type: 'stop_entry',
  trigger_price: 101.5,
  expiry_bars: 5,
  tp1_fraction: 0.5,
  breakeven_trigger_fraction: 0.6,
  explanation: 'Price reclaimed the 50-day after a three-week base.',
  confirmed_by: [{ strategy: 'VWAP', horizon_key: '2w' }],
  target_sources: ['Fib 1.618'],
  stop_sources: ['Swing low'],
  target2_sources: [],
  confidence_breakdown: { 'Trend alignment': 'above the 200-day' },
  quality_breakdown: [['Badge', 15]],
  status_history: [],
  legs: [],
  legs_realized: [],
  sizing_mode: 'risk_pct',
  working_stop: null,
  entry_context: { rs_pctile: 62, gap_p90_pct: 1.85, gap_fragile: false },
  risk_features: { days_to_earnings: null },
  cohort_label: 'COHORT_TYPICAL',
  confidence_points: null,
  confidence_unevaluated: [],
  gates: [{
    key: 'rs', label: 'Relative strength', value: 62, threshold: 0,
    margin: null, applies: false, parts: [], note: 'bullish arm disabled',
  }],
  sessions_since_created: 2,
  expires_on: '2026-10-12',
  time_exit_on: null,
  calendar: [{ date: '2026-10-16', kind: 'opex_monthly', label: 'Monthly OPEX' }],
  hold_cap_bars: null,
  acceptance_level: null,
};

function planResponse(status: string, overrides: object = {}, detail: object = {}) {
  return {
    id: PLAN_ID,
    origin: 'plan',
    status,
    ticker: 'AAPL',
    direction: 'bullish',
    strategy: 'RSI Divergence',
    horizon: '4w',
    tier: 'A',
    badge: 'VALIDATED',
    confidence_level: 4,
    confidence_score: 78,
    quality_score: 80,
    entry: status === 'PENDING' ? null : 101.5,
    stop_loss: 95,
    target: 110,
    target2: 118,
    risk_reward: 2,
    shares: 10,
    open_shares: 10,
    position_value: 1015,
    current_price: 103,
    current_price_stale: false,
    exit_price: null,
    realized_pnl_amount: null,
    pnl_pct: 1.5,
    r_multiple: null,
    held_hours: 30,
    opened_at: '2026-10-06T14:05:00Z',
    closed_at: null,
    has_note: false,
    progress_pct: 40,
    entry_pct: 33,
    progress_band: 'toward_target',
    blink_seconds: null,
    status_label: 'Moving toward target',
    bars_to_expiry: status === 'PENDING' ? 3 : null,
    detail: { ...DETAIL, ...detail },
    ...overrides,
  };
}

const NOTICE = [
  '⚠ SQUEEZE RISK · Short interest 18.2% of float · 4.1 days to cover · float 45.3M (as of 2026-11-13)',
  'Earnings in hold: 2026-11-30 (in 5 sessions)',
  'Ex-div in hold: 2026-11-24 · ~$0.42/sh owed',
  'CHECK BORROW AVAILABILITY',
];
const GAP = {
  rule: 'gap_p99', up_gap_p99_pct: 4, shares: 25, risk_amount: 50, gap_risk_amount: 100,
  gap_sized: true, line: 'Risk $50 at stop · $100 on a p99 gap (4.0%) · size cut for gap risk',
};

describe('shortOrderNotes', () => {
  it('is null without either key (longs, unstamped, pre-v183)', () => {
    expect(shortOrderNotes(null)).toBeNull();
    expect(shortOrderNotes({ risk_notice_lines: null, gap_sizing: null })).toBeNull();
    expect(shortOrderNotes({})).toBeNull();
  });

  it('carries the size, the gap line verbatim and the notice lines', () => {
    expect(shortOrderNotes({ risk_notice_lines: NOTICE, gap_sizing: GAP })).toEqual({
      size: 'Suggested size 25 sh', gapLine: GAP.line, cut: true, lines: NOTICE,
    });
  });

  it('formats fractional shares and survives a rule-stop short', () => {
    const notes = shortOrderNotes({ risk_notice_lines: null,
      gap_sizing: { ...GAP, rule: 'stop', shares: 1234.567, gap_sized: false, line: null } });
    expect(notes).toEqual({ size: 'Suggested size 1,234.57 sh', gapLine: null, cut: false, lines: [] });
  });
});

describe('PlanDetail', () => {
  let backend: HttpTestingController;
  let navigate: MockInstance<Router['navigate']>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  });

  function mount(id: string) {
    const fixture = TestBed.createComponent(PlanDetail);
    fixture.componentRef.setInput('id', id);
    fixture.detectChanges();
    return fixture;
  }

  function render(status: string, overrides: object = {}, detail: object = {}): HTMLElement {
    const fixture = mount(PLAN_ID);
    backend.expectOne(`/api/v1/trades/${PLAN_ID}`).flush(planResponse(status, overrides, detail));
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders an ACTIVE plan: header, levels, Why panel, chart, outcome path, record link', () => {
    const el = render('ACTIVE');
    const text = el.textContent ?? '';
    expect(text).toContain('AAPL');
    expect(text).toContain('RSI Divergence · 4w');
    expect(text).toContain('VALIDATED');
    expect(text).toContain('Lv4');
    expect(el.querySelector('sb-levels-block')).toBeTruthy();
    expect(el.querySelector('sb-why-panel')).toBeTruthy();
    expect(el.querySelector('sb-plan-chart')).toBeTruthy();
    expect(el.querySelector('sb-outcome-path')).toBeTruthy();
    expect(text).toContain("Gate margins (vs today's thresholds)");
    expect(text).toContain('Monthly OPEX');
    expect(text).toContain('Paper plan — this page places no orders.');
    const link = el.querySelector<HTMLAnchorElement>('a.record-link');
    expect(link?.textContent).toContain('Open the full trade record');
    expect(link?.getAttribute('href')).toBe(`/trades/${PLAN_ID}`);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('keeps the gap and sizing panels on the trade record for a filled plan', () => {
    const el = render('ACTIVE');
    expect(el.querySelector('sb-if-it-gets-there')).toBeNull();
    expect(el.querySelector('sb-sizing-panel')).toBeNull();
  });

  it('shows the expiry line, If-it-gets-there and Sizing for a PENDING plan', () => {
    const el = render('PENDING');
    const text = el.textContent ?? '';
    expect(text).toContain('Expires 2026-10-12 at the close (ET) (3 bars left)');
    expect(el.querySelector('sb-if-it-gets-there')).toBeTruthy();
    expect(el.querySelector('sb-sizing-panel')).toBeTruthy();
    expect(text).not.toContain('Scale-out');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('puts the size, gap cut and squeeze notice inside the order block of a short', () => {
    const el = render('PENDING', { direction: 'bearish' },
      { risk_notice_lines: NOTICE, gap_sizing: GAP });
    const block = el.querySelector('.order-block');
    expect(block?.querySelector('sb-levels-block')).toBeTruthy();
    const notes = block?.querySelector('.order-notes');
    expect(notes?.textContent).toContain('Suggested size 25 sh');
    expect(notes?.querySelector('.gap.cut')?.textContent).toContain('size cut for gap risk');
    const items = [...(notes?.querySelectorAll('li') ?? [])].map((li) => li.textContent?.trim());
    expect(items).toEqual(NOTICE);
    expect(notes?.querySelectorAll('li.warn').length).toBe(1);
  });

  it('keeps the notice on a filled short too', () => {
    const el = render('ACTIVE', { direction: 'bearish' }, { risk_notice_lines: NOTICE, gap_sizing: null });
    expect(el.querySelector('.order-notes')?.textContent).toContain('Earnings in hold: 2026-11-30');
  });

  it('renders no order notes for a long or a pre-v183 plan', () => {
    expect(render('PENDING').querySelector('.order-notes')).toBeNull();
  });

  it('shows the time-exit line once a hold cap is set', () => {
    const text = render('ACTIVE', {}, { hold_cap_bars: 10, time_exit_on: '2026-10-19' })
      .textContent ?? '';
    expect(text).toContain('Time exit after 10 sessions — 2026-10-19 at the close (ET)');
  });

  for (const [status, overrides] of [
    ['CLOSED', {}],
    ['CANCELLED', {}],
    ['PENDING', { bars_to_expiry: 0 }],
  ] as const) {
    it(`redirects a ${status}${'bars_to_expiry' in overrides ? ' (expired)' : ''} plan to its trade record with the banner state`, () => {
      render(status, overrides);
      expect(navigate).toHaveBeenCalledWith(
        ['/trades', PLAN_ID],
        { replaceUrl: true, state: { from: 'plan' } },
      );
    });
  }

  it('redirects a legacy trade id without the banner state and without fetching', () => {
    mount(LEGACY_ID);
    expect(navigate).toHaveBeenCalledWith(['/trades', LEGACY_ID], { replaceUrl: true });
    backend.expectNone(`/api/v1/trades/${LEGACY_ID}`);
  });

  it('shows the error state on a 404 rather than redirecting', () => {
    const fixture = mount(PLAN_ID);
    backend.expectOne(`/api/v1/trades/${PLAN_ID}`).flush(
      { error: { code: 'not_found', message: `No trade with id '${PLAN_ID}'` } },
      { status: 404, statusText: 'Not Found' },
    );
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.failed')).toBeTruthy();
    expect(navigate).not.toHaveBeenCalled();
  });
});

describe('looksLikePlanId', () => {
  it('accepts a dashed uuid4 and rejects a trade id', () => {
    expect(looksLikePlanId(PLAN_ID)).toBe(true);
    expect(looksLikePlanId(LEGACY_ID)).toBe(false);
    expect(looksLikePlanId('')).toBe(false);
    expect(looksLikePlanId('4444444444444444444444444444444444-4')).toBe(false);
  });
});

describe('redirectFor', () => {
  it('sends the terminal cases to the trade record with the banner', () => {
    expect(redirectFor('CLOSED', null)).toBe('banner');
    expect(redirectFor('CANCELLED', null)).toBe('banner');
    expect(redirectFor('PENDING', 0)).toBe('banner');
  });

  it('keeps an open plan on the page', () => {
    expect(redirectFor('PENDING', 3)).toBeNull();
    expect(redirectFor('PENDING', null)).toBeNull();
    expect(redirectFor('ACTIVE', null)).toBeNull();
    expect(redirectFor('PARTIAL', null)).toBeNull();
    expect(redirectFor(null, null)).toBeNull();
  });
});

describe('timingLines', () => {
  const base = { status: 'ACTIVE', expiresOn: null, barsToExpiry: null, holdCapBars: null, timeExitOn: null };

  it('says nothing for a filled plan with no hold cap', () => {
    expect(timingLines(base)).toEqual([]);
  });

  it('words a pending expiry, with a dash for a date outside the calendar', () => {
    expect(timingLines({ ...base, status: 'PENDING', expiresOn: '2026-10-12', barsToExpiry: 3 }))
      .toEqual(['Expires 2026-10-12 at the close (ET) (3 bars left)']);
    expect(timingLines({ ...base, status: 'PENDING', barsToExpiry: 3 }))
      .toEqual(['Expires — at the close (ET) (3 bars left)']);
  });

  it('words the time exit before and after the fill', () => {
    expect(timingLines({ ...base, holdCapBars: 10 })).toEqual(['Time exit after 10 sessions']);
    expect(timingLines({ ...base, holdCapBars: 10, timeExitOn: '2026-10-19' }))
      .toEqual(['Time exit after 10 sessions — 2026-10-19 at the close (ET)']);
  });
});

describe('plan-detail title on one baseline (v179 layout audit)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/plans/plan-detail.ts'), 'utf8');
  const rule = (selector: string) => src.match(
    new RegExp(`${selector.replaceAll('.', '\\.')} \\{[^}]*\\}`),
  )?.[0] ?? '';

  it('sets the 20px ticker and its 12px direction chip on the text baseline, the status glyph centred', () => {
    expect(rule('.plan-title')).toMatch(/align-items:\s*baseline/);
    expect(rule('.tags')).toMatch(/align-items:\s*baseline/);
  });
});

/* -- v195 Phase 4, §5.2, §1.4 -- plan detail on sb-page --------------------- */

describe('PlanDetail on sb-page (v195 Phase 4, §5.2, §1.4)', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    TestBed.inject(RouteTitleService).set('Plan detail', 'Why this plan, and how it is going');
  });

  function mount(status = 'ACTIVE') {
    const fixture = TestBed.createComponent(PlanDetail);
    fixture.componentRef.setInput('id', PLAN_ID);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${PLAN_ID}`).flush(planResponse(status));
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('renders the route title as the one h1, from sb-page', () => {
    const { el } = mount();
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Plan detail');
  });

  it('names the plan as the breadcrumb detail segment, with the short id the Trades list shows', () => {
    mount();
    expect(TestBed.inject(RouteTitleService).detail()).toBe('AAPL #444444');
  });

  it('puts the crumb back after a title update clears it while the page is open', () => {
    const { fixture } = mount('PENDING');
    const titles = TestBed.inject(RouteTitleService);
    titles.set('Plan detail', null, '/somewhere-else');
    fixture.detectChanges();
    expect(titles.detail()).toBe('AAPL #444444');
  });

  it('stays read-only: no header actions, no scope bar, no in-page back link', () => {
    const { el } = mount();
    expect(el.querySelector('[page-actions]')).toBeNull();
    expect(el.querySelector('[page-scope]')).toBeNull();
    expect(el.querySelector('a.back')).toBeNull();
    expect(el.querySelector('sb-page button.danger, sb-page button.danger-quiet')).toBeNull();
  });

  it('keeps the plan header as the summary and the plan body as the primary panel', () => {
    const { el } = mount('PENDING');
    const summary = el.querySelector('sb-page [page-kpis]')!;
    expect(summary.querySelector('header.plan-head .plan-title .ticker')!.textContent).toBe('AAPL');
    expect(summary.textContent).toContain('Expires 2026-10-12 at the close (ET) (3 bars left)');
    const primary = el.querySelector('sb-page [page-primary]')!;
    expect(primary.tagName.toLowerCase()).toBe('sb-async');
    expect(primary.querySelector('sb-levels-block')).toBeTruthy();
    expect(primary.querySelector('sb-sizing-panel')).toBeTruthy();
    expect(primary.querySelector('a.record-link')!.getAttribute('href')).toBe(`/trades/${PLAN_ID}`);
  });

  it('sets its order figures on the 14px body step, in both densities', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/plans/plan-detail.ts'), 'utf8');
    expect(src).toMatch(/:host \{[^}]*--text-table: var\(--text-body\);/);
  });
});
