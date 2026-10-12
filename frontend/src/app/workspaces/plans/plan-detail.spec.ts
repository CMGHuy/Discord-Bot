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
import { PlanDetail, looksLikePlanId, redirectFor, timingLines } from './plan-detail';

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
