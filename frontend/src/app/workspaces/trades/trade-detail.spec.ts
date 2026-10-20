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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { ChartStore } from '../../stores/chart.store';
import { TradeDetailStore } from '../../stores/trade-detail.store';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { TradeDetail, arrivalBanner } from './trade-detail';

// The Chart tab now mounts the shared chart, which asks for matchMedia the
// moment a chart exists. See the polyfill for why.
installMatchMediaPolyfill();
installDialogPolyfill();

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

  /** The outcome strip's age hint reads ConnectionStore (v171), which opens the stream. */
  connect(): void {}

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

function tradeResponse(detail: object, status = 'ACTIVE', overrides: object = {}) {
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
    current_price_stale: false,
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
    ...overrides,
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
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  /** Mount on a tab and settle the detail request. */
  function render(tab: string, detail: object = DETAIL, status = 'ACTIVE', overrides: object = {}) {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail, status, overrides));
    fixture.detectChanges();
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('renders the explanation on the Why tab', () => {
    expect(render('why')).toContain(
      'Price reclaimed the 50-day after a three-week base.',
    );
  });

  it('renders what confirmed the setup', () => {
    const text = render('why');
    expect(text).toContain('Confirmed by');
    expect(text).toContain('VWAP');
    expect(text).toContain('2w');
  });

  it('renders what justifies each level', () => {
    const text = render('why');
    expect(text).toContain('Level sources');
    expect(text).toContain('Fib 1.618');
    expect(text).toContain('Stop');
    expect(text).toContain('Swing low');
  });

  it('renders both breakdowns', () => {
    const text = render('why');
    expect(text).toContain('Confidence breakdown');
    expect(text).toContain('Trend alignment');
    expect(text).toContain('Quality breakdown');
    expect(text).toContain('Badge');
    // Signed: a factor that cost points is as informative as one that earned
    // them, and "15" alone reads as a credit either way.
    expect(text).toContain('+15');
  });

  it('renders the trigger price and the two fractions unsigned', () => {
    const text = render('overview');
    expect(text).toContain('Trigger');
    expect(text).toContain('101.50');
    // "TP1 closes +50%" would read as a gain. It means half the position.
    expect(text).toContain('50%');
    expect(text).not.toContain('+50%');
    expect(text).toContain('60%');
  });

  it('renders the timeline on Overview', () => {
    const text = render('overview');
    expect(text).toContain('Timeline');
    // Creation is prepended -- status_history does not contain it.
    expect(text).toContain('CREATED');
    expect(text).toContain('ACTIVE');
    expect(text).toContain('trigger filled');
  });

  it('renders settled exit legs in the Outcome card', () => {
    const text = render('overview', DETAIL, 'CLOSED', { exit_price: 110 });
    expect(text).toContain('Exit legs');
    expect(text).toContain('110.00');
    expect(text).toContain('+1.20R');
  });

  it('shows the trade id in the header', () => {
    // Previously only visible (truncated) in the Trades list's # column --
    // reaching this page by clicking a row lost the one thing someone might
    // come here to copy (e.g. for `!trade ID`).
    const text = render('overview');
    expect(text).toContain(ID);
  });

  it('keeps the original Stop beside the Working stop once TP1 has banked', () => {
    // A PARTIAL short's stop legitimately sits BELOW entry (it protects the
    // profit TP1 already locked in, not the original risk), which reads as
    // backwards unless the label says why.
    const text = render('overview', DETAIL, 'PARTIAL', { risk_stop: 95, stop_loss: 99 });
    expect(text).toContain('Stop');
    expect(text).toContain('95.00');
    expect(text).toContain('Working stop');
    expect(text).toContain('(was 95.00)');
  });

  it('labels the stop plain "Stop" before any TP1 (ACTIVE)', () => {
    const text = render('overview', DETAIL, 'ACTIVE');
    expect(text).toContain('Stop');
    expect(text).not.toContain('Trailing stop');
  });

  it('does not show a Scale-out panel for a position with one leg', () => {
    // One leg is not a scale-out, and a panel saying "First 100%" is noise on
    // every ordinary trade.
    const text = render('overview', { ...DETAIL, legs: [{ fraction: 1, exit_price: null }] });
    expect(text).not.toContain('Scale-out');
  });

  it('says a legacy record has no detail rather than showing blank panels', () => {
    const text = render('why', {
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

});

describe('TradeDetail — identity line (v166 TD6)', () => {
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
  });

  function mount(status = 'ACTIVE', overrides: object = {}, days: number | null = 3, tab = 'overview') {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    const detail = { ...DETAIL, gates: [{ key: 'earnings', label: 'Earnings', value: days }] };
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail, status, overrides));
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it.each([['bullish', 'Long'], ['SHORT', 'Short']])('names the ACTIVE %s side beside its ticker and status', (direction, side) => {
    const { el } = mount('ACTIVE', { direction });
    const title = el.querySelector('header.head > .identity > .trade-title');
    expect(title?.querySelector('.ticker')?.textContent).toBe('AAPL');
    expect(title?.querySelector('.side')?.textContent).toBe(side);
    expect(title?.querySelector('sb-status-indicator')).toBeTruthy();
  });

  it('keeps the complete trade identity and badge together', () => {
    const tags = mount().el.querySelector('.identity > .tags');
    expect([...tags!.querySelectorAll('.tag')].map(tag => tag.textContent)).toEqual(['4w', 'RSI Divergence']);
    expect([...tags!.querySelectorAll('sb-quality-chip')].map(chip => chip.textContent?.trim())).toEqual(['Tier A', 'Lv4', 'VALIDATED']);
    expect(tags?.querySelector('.trade-id')?.textContent).toBe(ID);
    expect(tags?.querySelector('.origin')).toBeNull();
  });

  it('omits an absent badge while retaining tier and confidence', () => {
    const tags = mount('ACTIVE', { badge: null }).el.querySelector('.identity > .tags');
    const chips = [...tags!.querySelectorAll('sb-quality-chip')];
    expect(chips.map(chip => chip.textContent?.trim())).toEqual(['Tier A', 'Lv4']);
    expect(tags?.textContent).not.toContain('VALIDATED');
  });

  it('identifies a legacy record', () => {
    expect(mount('ACTIVE', { origin: 'legacy' }).el.querySelector('.identity .origin')?.textContent).toBe('legacy');
  });

  it.each(['ACTIVE', 'PARTIAL', 'PENDING'])('shows upcoming earnings for %s', status => {
    expect(mount(status).el.querySelector('.tags > .earnings > sb-chip')?.textContent).toContain('Earnings in 3d');
  });

  it.each(['CLOSED', 'CANCELLED', 'EXPIRED'])('omits earnings for %s', status => {
    expect(mount(status).el.querySelector('.earnings')).toBeNull();
  });

  it('omits an absent earnings gate value', () => {
    expect(mount('ACTIVE', {}, null).el.querySelector('.earnings')).toBeNull();
  });

  it('shows an earnings event today without treating zero as absent', () => {
    expect(mount('PENDING', {}, 0).el.querySelector('.earnings')?.textContent).toContain('Earnings in 0d');
  });

  it.each([
    ['ACTIVE', ['Close', 'Delete']], ['PARTIAL', ['Close', 'Delete']],
    ['PENDING', ['Cancel plan', 'Delete']], ['CLOSED', ['Delete']],
  ])('offers the %s commands in the header', (status, labels) => {
    const { el } = mount(status as string, {}, 3, 'live');
    const buttons = [...el.querySelectorAll<HTMLButtonElement>('.identity > .actions > button[sb-button]')];
    expect(buttons.map(button => button.textContent?.trim())).toEqual(labels);
    expect(buttons.at(-1)?.classList).toContain('danger');
    expect([...el.querySelectorAll('sb-panel')].some(panel => panel.getAttribute('heading') === 'Actions')).toBe(false);
  });

  it('offers Close on a live position (SR48, through the real component)', () => {
    const { fixture, el } = mount();
    const close = el.querySelector<HTMLButtonElement>('.identity .actions button');
    expect(close?.textContent).toContain('Close');
    close!.click();
    fixture.detectChanges();
    expect(el.querySelector('sb-confirm-dialog')?.textContent).toContain('Close trade');
    expect(el.querySelector('sb-confirm-dialog')?.textContent).toContain('AAPL');
  });
});

describe('TradeDetail — the cohort risk chip (v86 C8)', () => {
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
  });

  /** Mounts with a row response carrying the given cohort fields; returns
   *  the rendered header element for class/text assertions. Unlike `render`
   *  above (which returns plain text), tone lives on a class, so this needs
   *  the element itself. */
  function renderHeader(
    cohortLabel?: string,
    cohortStats?: Record<string, unknown>,
  ): HTMLElement {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush({
      ...tradeResponse(DETAIL),
      cohort_label: cohortLabel,
      cohort_stats: cohortStats,
    });
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders a danger-toned chip for COHORT_POOR', () => {
    const el = renderHeader('COHORT_POOR', {
      regime2_state: 'bear_volatile', win_rate: 41.2, expectancy_r: -0.38,
      n_live: 100, n_backtest: 500, run_date: '2026-09-14',
    });
    const chip = el.querySelector('.tags > sb-chip .chip');
    expect(chip).toBeTruthy();
    expect(chip!.classList).toContain('bad');
    expect(chip!.textContent).toContain('Poor cohort');
    // [title] binds to the sb-chip HOST element (Chip has no `title` input
    // to forward it onto the inner span), not the .chip span itself.
    const host = el.querySelector('.tags > sb-chip')!;
    expect(host.getAttribute('title')).toContain('41.2% WR');
    expect(host.getAttribute('title')).toContain('-0.38R');
  });

  it('renders a positive-toned chip for COHORT_STRONG', () => {
    const el = renderHeader('COHORT_STRONG', { win_rate: 71, expectancy_r: 0.6 });
    const chip = el.querySelector('.tags > sb-chip .chip');
    expect(chip!.classList).toContain('good');
    expect(chip!.textContent).toContain('Strong cohort');
  });

  it('renders a muted chip labelled unknown for COHORT_UNKNOWN', () => {
    // The API never omits cohort_label (the backend defaults a pre-v86
    // record to COHORT_UNKNOWN server-side, see test_cohort_api.py) -- this
    // is the shape a pre-v86 trade actually arrives in over the wire.
    const el = renderHeader('COHORT_UNKNOWN', {});
    const chip = el.querySelector('.tags > sb-chip .chip');
    expect(chip).toBeTruthy();
    expect(chip!.classList).toContain('muted');
    expect(chip!.textContent).toContain('Cohort unknown');
  });

  it('renders neutral n= text, not a fabricated 0.0% WR, when COHORT_UNKNOWN carries a real stamped (zeroed) cell', () => {
    // Final-review Fix 5: once a real registry exists, a COHORT_UNKNOWN cell
    // is still stamped with the full 8-key dict -- it just fell below the
    // registry's N floor -- rather than staying `{}`. Computing a WR/ExpR
    // line off those zeros would be the exact fabricated-zero bug already
    // fixed once server-side (commit 7d5d4d3a); the tooltip must not
    // reintroduce it on the frontend.
    const el = renderHeader('COHORT_UNKNOWN', {
      regime2_state: 'bear_volatile', win_rate: 0.0, expectancy_r: 0.0,
      n_live: 3, n_backtest: 0, run_date: '2026-09-14',
    });
    const host = el.querySelector('.tags > sb-chip')!;
    const title = host.getAttribute('title') ?? '';
    expect(title).toContain('Not enough closed trades');
    expect(title).toContain('n=3');
    expect(title).not.toContain('0.0% WR');
    expect(title).not.toContain('WR');
  });

  it('renders no chip when cohort_label is entirely absent from the response', () => {
    // Defensive: an old cached bundle hitting a pre-C8 backend response
    // shape must not crash or show a chip for a field that isn't there.
    const el = renderHeader(undefined, undefined);
    expect(el.querySelector('.tags > sb-chip')).toBeNull();
  });

  it('renders no chip at all for COHORT_TYPICAL', () => {
    const el = renderHeader('COHORT_TYPICAL', {});
    expect(el.querySelector('.tags > sb-chip')).toBeNull();
  });
});

describe('TradeDetail — banked leg and open runner', () => {
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
  });

  function renderPartial(legsRealized: unknown[] = [
    { fraction: 0.5, exit_price: 110, r: 2.0, reason: 'tp1' },
  ]) {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', 'overview');
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
    expect(text).toContain('Position');
    expect(text).toContain('Open shares');
    expect(text).toContain('110.00');   // banked TP1 fill in the strip
    expect(text).toContain('50%');
    expect(text).toContain('50% @ 110.00');
  });

  it('shows the pct and dollar figures for the banked leg', () => {
    const text = renderPartial();
    // tradeResponse() defaults entry=100, shares=10: (110-100)*0.5*10 = 50
    expect(text).toContain('+10.00%');
    expect(text).toContain('+50.00');
  });

  it('omits the Banked tile before anything has banked', () => {
    expect(renderPartial([])).not.toContain('Banked');
  });

  it('uses ordinary Shares outside PARTIAL', () => {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', 'overview');
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(DETAIL, 'ACTIVE'));
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[data-row="Open shares"]')).toBeNull();
    expect(el.querySelector('[data-row="Shares"]')).toBeTruthy();
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
        TradeDetailStore,
        ChartStore,
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

describe('TradeDetail — the shared Why components (v151)', () => {
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
  });

  function mount(tab: string, detail: object = DETAIL, status = 'ACTIVE', overrides: object = {}) {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail, status, overrides));
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it.each([
    ['CLOSED', ['result', 'pnl', 'entry-exit', 'held', 'exit']],
    ['ACTIVE', ['price', 'unrealised', 'progress', 'held']],
    ['PENDING', ['trigger', 'distance', 'expires', 'created']],
    ['CANCELLED', ['status', 'created', 'trigger', 'fill']],
  ])('renders the %s strip directly after the header on every tab', (status, ids) => {
    const el = mount('journal', DETAIL, status as string);
    const strip = el.querySelector('header.head + sb-outcome-strip');
    expect(strip).toBeTruthy();
    expect([...strip!.querySelectorAll('[data-tile]')].map(t => t.getAttribute('data-tile'))).toEqual(ids);
    expect(strip!.querySelectorAll('.strip-foot').length).toBe(1);
    expect(strip!.textContent).toContain('Paper fills at plan levels; real fills and slippage may differ.');
  });

  it.each(['ACTIVE', 'PARTIAL'])('renders the %s outcome progress bar between the working stop and target', status => {
    const el = mount('overview', DETAIL, status, { current_price: 105, stop_loss: 101, target: 109 });
    const bar = el.querySelector('[data-tile="progress"] [role="progressbar"]');
    expect(bar).toBeTruthy();
    expect(bar!.getAttribute('aria-valuenow')).toBe('50');
  });

  it('keeps a partial runner open and separates its banked result', () => {
    const el = mount('overview', { ...DETAIL, legs_realized: [
      { fraction: 0.5, exit_price: 110, r: 2, reason: 'tp1' },
    ] }, 'PARTIAL', { exit_price: 110, stop_loss: 101, target: 118, r_multiple: -0.5 });
    const strip = el.querySelector('sb-outcome-strip')!;
    expect(strip.querySelector('[data-tile="result"]')).toBeNull();
    expect(strip.querySelector('[data-tile="unrealised"]')?.textContent).toContain('on open shares');
    expect(strip.querySelector('[data-tile="banked"]')?.textContent).toContain('50% @ 110.00');
    expect(strip.querySelectorAll('.tile-caption').length).toBe(2);
    expect(strip.querySelector('[data-tile="progress"] sb-status-indicator')).toBeTruthy();
  });

  it('flags a stale current price and unrealised result in the outcome strip', () => {
    const el = mount('overview', DETAIL, 'ACTIVE', { current_price_stale: true });
    const strip = el.querySelector('sb-outcome-strip')!;
    expect(strip.querySelector('[data-tile="price"] .stale-flag')?.textContent).toContain('delayed');
    expect(strip.querySelector('[data-tile="unrealised"] .stale-flag')?.textContent).toContain('delayed');
  });

  it('does not flag a fresh current price in the outcome strip', () => {
    const el = mount('overview', DETAIL, 'ACTIVE', { current_price_stale: false });
    expect(el.querySelector('sb-outcome-strip .stale-flag')).toBeNull();
  });

  it('excludes synthetic created reasons from an unfilled strip', () => {
    const el = mount('overview', { ...DETAIL, status_history: [] }, 'CANCELLED');
    expect(el.querySelector('[data-tile="status"] .tile-sub')).toBeNull();
  });

  it('hosts all Overview cards in reading order and responsive grid areas', () => {
    const el = mount('overview');
    const grid = el.querySelector<HTMLElement>('div.grid-host > div.card-grid.overview-grid')!;
    expect(grid).toBeTruthy();
    expect([...grid.children].map(cell => cell.getAttribute('data-area'))).toEqual(['plan', 'position', 'outcome']);
    for (const cell of [...grid.children] as HTMLElement[]) expect(cell.style.gridArea).toBe(cell.dataset['area']);
    expect(grid.style.getPropertyValue('--areas-1')).toBe('"plan" "position" "outcome"');
    expect(grid.style.getPropertyValue('--areas-2')).toBe('"plan position" "outcome outcome"');
    expect(grid.style.getPropertyValue('--areas-3')).toBe('"plan position outcome"');
    expect(grid.querySelector('sb-trade-plan-card')).toBeTruthy();
    expect(grid.querySelector('sb-trade-position-card')).toBeTruthy();
    expect(grid.querySelector('sb-trade-outcome-card')).toBeTruthy();
    expect(el.querySelector('sb-why-panel')).toBeNull();
    expect(el.textContent).toContain('Paper plan — this page places no orders.');
  });

  it('uses the current stop in the Outcome next block and original risk in Position', () => {
    const el = mount('overview', { ...DETAIL, working_stop: 101 }, 'PARTIAL',
      { risk_stop: 95, stop_loss: 101, shares: 5, position_value: 500 });
    const position = el.querySelector('sb-trade-position-card')!;
    expect(position.querySelector('[data-row="Open shares"]')?.textContent).toContain('5');
    expect(position.querySelector('[data-row="$ at risk"]')?.textContent).toContain('25.00');
    expect(position.querySelector('[data-row="Deployed"]')?.textContent).toContain('500.00');
    expect(el.querySelector('sb-trade-outcome-card sb-if-it-gets-there')?.textContent).toContain('101.00');
  });

  it('omits a working stop change for a PARTIAL row without its original risk stop', () => {
    const el = mount('overview', { ...DETAIL, working_stop: 101 }, 'PARTIAL',
      { stop_loss: 101, shares: 5, position_value: 500 });
    const plan = el.querySelector('sb-trade-plan-card')!;
    expect(plan).toBeTruthy();
    expect(plan.querySelector('[data-level="Stop"]')?.textContent).toContain('101.00');
    expect(plan.querySelector('[data-level="Working stop"]')).toBeNull();
    expect(plan.textContent).not.toContain('Move your resting stop');
  });

  it('omits a working stop change when an ACTIVE row has equal original and working stops', () => {
    const el = mount('overview', { ...DETAIL, working_stop: 95 }, 'ACTIVE',
      { risk_stop: 95, stop_loss: 95 });
    const plan = el.querySelector('sb-trade-plan-card')!;
    expect(plan).toBeTruthy();
    expect(plan.querySelector('[data-level="Stop"]')?.textContent).toContain('95.00');
    expect(plan.querySelector('[data-level="Working stop"]')).toBeNull();
    expect(plan.textContent).not.toContain('Move your resting stop');
  });

  it('shows the final tab labels and preserves the Journal body', () => {
    const el = mount('journal');
    expect([...el.querySelectorAll('[role="tab"]')].map(tab => tab.textContent?.trim()))
      .toEqual(['Overview', 'Why', 'Chart', 'Journal']);
    expect(el.querySelector('.notes')).toBeTruthy();
    expect(el.querySelector('.note-field')).toBeTruthy();
  });

  it.each([
    ['plan', null, 'Overview'], ['live', null, 'Overview'],
    ['notes', 'journal', 'Journal'], ['strategy', 'why', 'Why'],
  ])('renders and replaces legacy tab %s immediately', (legacy, target, label) => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const el = mount(legacy!);
    expect(el.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(label);
    expect(navigate).toHaveBeenCalledWith([], {
      queryParams: { tab: target }, queryParamsHandling: 'merge', replaceUrl: true,
    });
  });

  it.each([undefined, 'unknown'])('falls back to Overview without rewriting tab %s', requested => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const el = mount(requested as string);
    expect(el.querySelector('.overview-grid')).toBeTruthy();
    expect(navigate).not.toHaveBeenCalled();
  });

  it('removes the tab parameter when Overview is selected', () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const el = mount('journal');
    const overview = [...el.querySelectorAll<HTMLButtonElement>('[role="tab"]')][0];
    overview.click();
    expect(navigate).toHaveBeenCalledWith([], {
      queryParams: { tab: null }, queryParamsHandling: 'merge', replaceUrl: true,
    });
  });

  it('renders Why cards in reading order with areas for all device classes', () => {
    const el = mount('why');
    const grid = el.querySelector<HTMLElement>('div.grid-host > div.card-grid.why-grid')!;
    expect(grid).toBeTruthy();
    expect([...grid.children].map(cell => cell.getAttribute('data-area')))
      .toEqual(['why', 'scores', 'sources', 'breakdown', 'gates', 'context']);
    for (const cell of [...grid.children] as HTMLElement[]) {
      expect(cell.style.gridArea).toBe(cell.dataset['area']);
    }
    expect(grid.style.getPropertyValue('--areas-1')).toBe('"why" "scores" "sources" "breakdown" "gates" "context"');
    expect(grid.style.getPropertyValue('--areas-2')).toBe('"why why" "scores context" "sources sources" "breakdown breakdown" "gates gates"');
    expect(grid.style.getPropertyValue('--areas-3')).toBe('"why why scores" "sources sources sources" "breakdown breakdown breakdown" "gates gates context"');
    expect(grid.querySelector('[data-area="context"] sb-trade-strategy-record')).toBeTruthy();
    expect(el.querySelectorAll('[role="tab"]')[1]?.textContent).toContain('Why');
  });

  it('uses a shrinkable single-column track for the initial Why layout', () => {
    const el = mount('why');
    const grid = el.querySelector<HTMLElement>('.why-grid')!;
    expect(getComputedStyle(grid).gridTemplateColumns).toBe('minmax(0, 1fr)');
    expect(getComputedStyle(grid.parentElement!).minWidth).toBe('0px');
    for (const cell of [...grid.children]) {
      expect(getComputedStyle(cell).minWidth).toBe('0px');
    }
  });

  it.each([
    ['why', { explanation: null }, {}],
    ['scores', {}, { confidence_score: null, confidence_level: null, quality_score: null, badge: null }],
    ['sources', { confirmed_by: [], target_sources: [], stop_sources: [], target2_sources: [] }, {}],
    ['breakdown', { confidence_points: null, confidence_breakdown: null, quality_breakdown: [] }, {}],
  ])('omits only the %s card when its own data is absent', (absent, detail, trade) => {
    const el = mount('why', { ...DETAIL, ...detail }, 'ACTIVE', trade);
    expect(el.querySelector(`[data-area="${absent}"]`)).toBeNull();
    expect(el.querySelectorAll('.why-grid > .cell').length).toBe(5);
    expect(el.querySelector('.no-detail')).toBeNull();
    expect(el.querySelector('[data-area="gates"]')).toBeTruthy();
    expect(el.querySelector('[data-area="context"]')).toBeTruthy();
  });

  it('keeps each WhyPanel cell restricted to its own section', () => {
    const el = mount('why');
    const sections = [
      ['why', 'Why this trade'],
      ['breakdown', 'Confidence breakdown'],
      ['gates', "Gate margins (vs today's thresholds)"],
      ['context', 'Calendar in the holding window'],
    ];
    for (const [area, heading] of sections) {
      const cell = el.querySelector(`[data-area="${area}"]`)!;
      expect(cell.querySelectorAll('sb-why-panel').length).toBe(1);
      expect([...cell.querySelectorAll('sb-why-panel h2')].map(node => node.textContent))
        .toEqual([heading]);
    }
    expect(el.textContent).not.toContain('Levels & methods');
    expect(el.querySelector('[data-area="scores"]')?.textContent)
      .toContain('Scores rank setups; they are not win probabilities.');
  });

  it('omits absent reasoning cards and compacts the area bindings', () => {
    const el = mount('why', { ...DETAIL, explanation: null, confirmed_by: [],
      target_sources: [], stop_sources: [], confidence_breakdown: null, quality_breakdown: [], status_history: [] },
      'ACTIVE', { confidence_score: null, confidence_level: null, quality_score: null, badge: null });
    const grid = el.querySelector<HTMLElement>('.why-grid')!;
    expect([...grid.children].map(cell => cell.getAttribute('data-area'))).toEqual(['gates', 'context']);
    expect(grid.style.getPropertyValue('--areas-3')).toBe('"gates gates context"');
    expect(el.querySelector('p.no-detail + div.grid-host')).toBeTruthy();
  });

  it('retains a zero score and a points-only breakdown', () => {
    const el = mount('why', { ...DETAIL, confidence_breakdown: null, quality_breakdown: [],
      confidence_points: { Trend: 0 } }, 'ACTIVE', { confidence_score: 0 });
    expect(el.querySelector('[data-area="scores"]')?.textContent).toContain('0');
    expect(el.querySelector('[data-area="breakdown"]')?.textContent).toContain('Trend');
  });

  it('loads the registry only on first arrival at Why', () => {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(DETAIL));
    fixture.detectChanges();
    backend.expectNone('/api/v1/analytics/strategies');
    fixture.componentRef.setInput('tab', 'why');
    fixture.detectChanges();
    backend.expectOne('/api/v1/analytics/strategies').flush({ strategies: [] });
    fixture.detectChanges();
    fixture.componentRef.setInput('tab', 'overview');
    fixture.detectChanges();
    fixture.componentRef.setInput('tab', 'why');
    fixture.detectChanges();
    backend.expectNone('/api/v1/analytics/strategies');
    expect((fixture.nativeElement as HTMLElement).querySelector('sb-trade-strategy-record')?.textContent)
      .toContain('The registry has no entry for RSI Divergence');
  });

  it('renders the level sources exactly once', () => {
    const text = mount('why').textContent ?? '';
    expect(text.split('Fib 1.618').length - 1).toBe(1);
    expect(text.split('Swing low').length - 1).toBe(1);
  });

  it('shows the gate margins section with its caveat on the Why tab', () => {
    const text = mount('why').textContent ?? '';
    expect(text).toContain("Gate margins (vs today's thresholds)");
    expect(text).toContain(
      "Margins are measured against today's thresholds, not the ones in force when this plan was issued.",
    );
    expect(text).toContain('Calendar in the holding window');
  });

  it('keeps the gate rows on a legacy record that has no detail', () => {
    const el = mount('why', {
      ...DETAIL,
      explanation: null,
      confirmed_by: [],
      target_sources: [],
      stop_sources: [],
      confidence_breakdown: null,
      quality_breakdown: [],
      status_history: [],
      gates: [{
        key: 'rs', label: 'Relative strength', value: null, threshold: 25,
        margin: null, applies: false, parts: [], note: 'exempt',
      }],
    });
    const text = el.textContent ?? '';
    expect(text).toContain('logged before the admin UI captured the full alert detail');
    expect(text).toContain('Relative strength');
    expect(text).not.toContain('Why this trade');
    expect(text).not.toContain('Quality breakdown');
  });

  it('hosts the outcome path on Overview', () => {
    const el = mount('overview');
    expect(el.querySelector('sb-outcome-path')).toBeTruthy();
    expect(el.querySelector('sb-trade-outcome-card')).toBeTruthy();
    expect(el.textContent).toContain('Timeline');
  });

  it('hosts the plan chart on the Chart tab', () => {
    const el = mount('chart');
    expect(el.querySelector('sb-plan-chart')).toBeTruthy();
  });
});

describe('TradeDetail — arrival banner from the plan page (v151)', () => {
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
  });

  afterEach(() => history.replaceState(null, ''));

  function mountWithState(state: object | null, status: string, overrides: object = {}) {
    history.replaceState(state, '');
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(DETAIL, status, overrides));
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('says the plan is closed when redirected from a closed plan', () => {
    const el = mountWithState({ from: 'plan' }, 'CLOSED');
    expect(el.querySelector('.arrival')?.textContent).toContain('This plan is closed');
  });

  it('says the plan was cancelled when redirected from a cancelled plan', () => {
    const el = mountWithState({ from: 'plan' }, 'CANCELLED');
    expect(el.querySelector('.arrival')?.textContent).toContain('This plan was cancelled');
  });

  it('says the plan has expired when redirected from an expired pending plan', () => {
    const el = mountWithState({ from: 'plan' }, 'PENDING', { bars_to_expiry: 0 });
    expect(el.querySelector('.arrival')?.textContent).toContain('This plan has expired');
  });

  it('shows no banner on a direct visit', () => {
    const el = mountWithState(null, 'CLOSED');
    expect(el.querySelector('.arrival')).toBeNull();
  });

  it('shows no banner for a live plan even with the state set', () => {
    const el = mountWithState({ from: 'plan' }, 'ACTIVE');
    expect(el.querySelector('.arrival')).toBeNull();
  });
});

describe('arrivalBanner', () => {
  it('words each terminal case', () => {
    expect(arrivalBanner('PENDING', 0)).toBe('This plan has expired — this is its trade record.');
    expect(arrivalBanner('CANCELLED', null)).toBe('This plan was cancelled — this is its trade record.');
    expect(arrivalBanner('CLOSED', null)).toBe('This plan is closed — this is its trade record.');
  });

  it('returns nothing for a plan that is still open', () => {
    expect(arrivalBanner('PENDING', 3)).toBe('');
    expect(arrivalBanner('PENDING', null)).toBe('');
    expect(arrivalBanner('ACTIVE', null)).toBe('');
    expect(arrivalBanner('PARTIAL', null)).toBe('');
    expect(arrivalBanner(null, null)).toBe('');
  });
});

describe('TradeDetail — responsive card layout (v166 TD11)', () => {
  const source = readFileSync(join(process.cwd(), 'src/app/workspaces/trades/trade-detail.ts'), 'utf8');
  const styles = source.split('styles: `')[1].split('`,')[0];

  it('gives back navigation the shared control height for phone touch targets', () => {
    const backStyles = styles.match(/\.back\s*\{([^}]+)\}/)?.[1] ?? '';
    expect(backStyles).toMatch(/min-height:\s*var\(--control-h\)/);
  });

  it('sizes the cards container independently of the viewport', () => {
    expect(styles).toMatch(/\.grid-host\s*\{[^}]*container:\s*cards\s*\/\s*inline-size/);
    expect(styles).toMatch(/\.card-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)[^}]*align-items:\s*stretch[^}]*grid-template-areas:\s*var\(--areas-1\)/);
  });

  it('switches named areas only at the tablet and desktop container floors', () => {
    expect(styles).toMatch(/@container cards \(min-width: 640px\)\s*\{\s*\.card-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)[^}]*grid-template-areas:\s*var\(--areas-2\)/);
    expect(styles).toMatch(/@container cards \(min-width: 1024px\)\s*\{\s*\.card-grid\s*\{[^}]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)[^}]*grid-template-areas:\s*var\(--areas-3\)/);
    expect(styles.match(/@container[^\{]+/g)?.map(query => query.trim())).toEqual([
      '@container cards (min-width: 640px)', '@container cards (min-width: 1024px)',
    ]);
    expect(styles).not.toMatch(/@media|@container[^\{]*[<>]/);
  });

  it('gives every cell a shrinkable single track and its own inline size', () => {
    const cell = styles.match(/\.cell\s*\{([^}]+)\}/)?.[1];
    expect(cell).toMatch(/container-type:\s*inline-size/);
    expect(cell).toMatch(/display:\s*grid/);
    expect(cell).toMatch(/min-width:\s*0/);
    expect(cell).toMatch(/grid-template-columns:\s*minmax\(0, 1fr\)/);
  });

  it('stretches one-panel cards while preserving the two context rows', () => {
    expect(styles).toMatch(/:host ::ng-deep \.cell > \* > sb-panel:only-child\s*\{[^}]*display:\s*block[^}]*height:\s*100%/);
    expect(styles).toMatch(/:host ::ng-deep \.cell > \* > sb-panel:only-child \.panel\s*\{[^}]*height:\s*100%/);
    expect(styles).toMatch(/\.cell\[data-area="context"\]\s*\{[^}]*grid-template-rows:\s*auto 1fr[^}]*gap:\s*var\(--section-gap\)/);
  });

  it('keeps obsolete panel and definition-list rules out of the page', () => {
    expect(source.split('template: `')[1].split('styles: `')[0]).not.toMatch(/<dl\b|class="panels"/);
    expect(styles).not.toMatch(/\.panels\b|(?:^|\})\s*(?:dl|dt|dd)\b/);
  });

  it.each(['position-card', 'strategy-record-card', 'level-sources-card', 'scores-card'])(
    'lets %s use two definition columns only when its cell has room', name => {
      const card = readFileSync(join(process.cwd(), `src/app/workspaces/trades/${name}.ts`), 'utf8');
      expect(card).toMatch(/@container \(min-width: 640px\)\s*\{\s*dl\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)[^}]*column-gap:\s*var\(--space-20\)/);
      const cardStyles = card.split('styles: `')[1].split('`,')[0];
      // Keep the wide-cell override last: a later base gap shorthand would
      // reset its column-gap even though the container query still matches.
      expect(cardStyles).toMatch(/@container \(min-width: 640px\)\s*\{\s*dl\s*\{[^}]+\}\s*\}\s*$/);
    },
  );
});
