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
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { TradeDetail } from './trade-detail';

/* SR49 — the rendering half.
 *
 * `trade-detail.narrowing.spec.ts` pins the shapes coming out of the store.
 * This file pins the thing the parity audit actually found: that nine fields
 * were fetched on every load and appeared on screen nowhere. A store that
 * narrows them correctly and a template that never reads it would look exactly
 * like the bug being fixed here, so the assertions below are all on rendered
 * text.
 */

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

const ID = 'ffffffffffffffff';

const DETAIL = {
  trade_id: ID,
  note: null,
  created_at: '2026-08-01T09:30:00Z',
  plan_source: 'scan',
  entry_type: 'stop',
  trigger_price: 101.5,
  tp1_fraction: 0.5,
  breakeven_trigger_fraction: 0.6,
  explanation: 'Price reclaimed the 50-day after a three-week base.',
  confirmed_by: [{ strategy: 'VWAP', horizon_key: '2w' }],
  target_sources: ['Fib 1.618'],
  stop_sources: ['Swing low'],
  target2_sources: [],
  confidence_breakdown: { 'Trend alignment': 'above the 200-day' },
  quality_breakdown: [['Badge', 15]],
  status_history: [{ status: 'ACTIVE', reason: 'trigger filled', at: '2026-08-02T14:05:00Z' }],
  legs: [
    { fraction: 0.5, exit_price: 110, r: 1.2, reason: 'TP1' },
    { fraction: 0.5, exit_price: null, r: null, reason: null },
  ],
  legs_realized: [],
  sizing_mode: 'risk_pct',
  working_stop: 99,
};

function tradeResponse(detail: object, status = 'ACTIVE') {
  return {
    id: ID,
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
    entry: 100,
    stop_loss: 95,
    target: 110,
    target2: 118,
    risk_reward: 2,
    shares: 10,
    open_shares: 10,
    position_value: 1000,
    current_price: 105,
    exit_price: null,
    realized_pnl_amount: null,
    pnl_pct: 5,
    r_multiple: null,
    held_hours: 30,
    opened_at: '2026-08-02T14:05:00Z',
    closed_at: null,
    has_note: false,
    progress_pct: 66,
    entry_pct: 33,
    progress_band: 'toward_target',
    blink_seconds: null,
    status_label: 'Moving toward target',
    detail,
  };
}

describe('TradeDetail — the fields that rendered nowhere', () => {
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
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  /** Mount on a tab and settle the detail request. */
  function render(tab: string, detail: object = DETAIL, status = 'ACTIVE') {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail, status));
    fixture.detectChanges();
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('renders the explanation on the Plan tab', () => {
    expect(render('plan')).toContain(
      'Price reclaimed the 50-day after a three-week base.',
    );
  });

  it('renders what confirmed the setup', () => {
    const text = render('plan');
    expect(text).toContain('Confirmed by');
    expect(text).toContain('VWAP');
    expect(text).toContain('2w');
  });

  it('renders what justifies each level', () => {
    const text = render('plan');
    expect(text).toContain('Target confirmed by');
    expect(text).toContain('Fib 1.618');
    expect(text).toContain('Stop confirmed by');
    expect(text).toContain('Swing low');
  });

  it('renders both breakdowns', () => {
    const text = render('plan');
    expect(text).toContain('Confidence breakdown');
    expect(text).toContain('Trend alignment');
    expect(text).toContain('Quality breakdown');
    expect(text).toContain('Badge');
    // Signed: a factor that cost points is as informative as one that earned
    // them, and "15" alone reads as a credit either way.
    expect(text).toContain('+15');
  });

  it('renders the trigger price and the two fractions unsigned', () => {
    const text = render('plan');
    expect(text).toContain('Trigger');
    expect(text).toContain('101.50');
    // "TP1 closes +50%" would read as a gain. It means half the position.
    expect(text).toContain('50%');
    expect(text).not.toContain('+50%');
    expect(text).toContain('60%');
  });

  it('renders the timeline on the Live tab', () => {
    const text = render('live');
    expect(text).toContain('Timeline');
    // Creation is prepended -- status_history does not contain it.
    expect(text).toContain('CREATED');
    expect(text).toContain('ACTIVE');
    expect(text).toContain('trigger filled');
  });

  it('renders the scale-out legs, saying which is still open', () => {
    const text = render('live');
    expect(text).toContain('Scale-out');
    expect(text).toContain('110.00');
    expect(text).toContain('+1.20R');
    expect(text).toContain('still open');
  });

  it('shows the trade id in the header', () => {
    // Previously only visible (truncated) in the Trades list's # column --
    // reaching this page by clicking a row lost the one thing someone might
    // come here to copy (e.g. for `!trade ID`).
    const text = render('plan');
    expect(text).toContain(ID);
  });

  it('labels the stop "Trailing stop" once TP1 has banked (PARTIAL)', () => {
    // A PARTIAL short's stop legitimately sits BELOW entry (it protects the
    // profit TP1 already locked in, not the original risk), which reads as
    // backwards unless the label says why.
    const text = render('plan', DETAIL, 'PARTIAL');
    expect(text).toContain('Trailing stop');
  });

  it('labels the stop plain "Stop" before any TP1 (ACTIVE)', () => {
    const text = render('plan', DETAIL, 'ACTIVE');
    expect(text).toContain('Stop');
    expect(text).not.toContain('Trailing stop');
  });

  it('does not show a Scale-out panel for a position with one leg', () => {
    // One leg is not a scale-out, and a panel saying "First 100%" is noise on
    // every ordinary trade.
    const text = render('live', { ...DETAIL, legs: [{ fraction: 1, exit_price: null }] });
    expect(text).not.toContain('Scale-out');
  });

  it('says a legacy record has no detail rather than showing blank panels', () => {
    const text = render('plan', {
      trade_id: ID,
      note: null,
      created_at: null,
      plan_source: null,
      entry_type: null,
      trigger_price: null,
      tp1_fraction: null,
      breakeven_trigger_fraction: null,
      explanation: null,
      confirmed_by: [],
      target_sources: [],
      stop_sources: [],
      target2_sources: [],
      confidence_breakdown: null,
      quality_breakdown: [],
      status_history: [],
      legs: [],
      legs_realized: [],
      sizing_mode: null,
      working_stop: null,
    });

    expect(text).toContain('logged before the admin UI captured the full alert detail');
    expect(text).not.toContain('Why this trade');
    expect(text).not.toContain('Quality breakdown');
  });

  it('offers Close on a live position (SR48, through the real component)', () => {
    // SR48 fixed availableActions; this is the same fix seen from the screen,
    // which is where the absence was invisible for a whole phase.
    expect(render('live')).toContain('Close');
  });
});

describe('TradeDetail — partial position panel (v58)', () => {
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
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  function renderPartial(legsRealized: unknown[] = [
    { fraction: 0.5, exit_price: 110, r: 2.0, reason: 'tp1' },
  ]) {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', 'live');
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(
      tradeResponse({ ...DETAIL, legs_realized: legsRealized, working_stop: 101.33 },
                    'PARTIAL'),
    );
    fixture.detectChanges();
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('shows the runner as its own position once PARTIAL', () => {
    const text = renderPartial();
    expect(text).toContain('Partial position');
    expect(text).toContain('110.00');   // the TP1 leg's own fill, as "Entry"
    expect(text).toContain('50%');
    expect(text).toContain('+2.00R');
  });

  it('shows the pct and dollar figures for the banked leg', () => {
    const text = renderPartial();
    // tradeResponse() defaults entry=100, shares=10: (110-100)*0.5*10 = 50
    expect(text).toContain('+10.00%');
    expect(text).toContain('+50.00');
  });

  it('does not render the panel before anything has banked', () => {
    expect(renderPartial([])).not.toContain('Partial position');
  });

  it('does not render the panel outside PARTIAL', () => {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', 'live');
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(DETAIL, 'ACTIVE'));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Partial position');
  });
});

describe('TradeDetail states', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
  });

  it('shows a skeleton in the tab body while loading, before the first response', () => {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeTruthy();
  });

  it('shows the error state on a first-load failure', () => {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.detectChanges();
    TestBed.inject(HttpTestingController)
      .expectOne(`/api/v1/trades/${ID}`)
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.failed')).toBeTruthy();
  });
});
