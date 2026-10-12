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

import { EventStream } from '../../../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../../api/interceptors';
import { ChartResponse } from '../../../api/models';
import { ChartStore } from '../../../stores/chart.store';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { PlanChart } from './plan-chart';

// PlanChart renders a real TradeChart once bars arrive, and lightweight-charts
// asks for matchMedia the moment a chart exists. See the polyfill for why.
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

const ID = '44444444-4444-4444-8444-444444444444';

const RESPONSE: ChartResponse = {
  ticker: 'AAPL',
  ohlcv: [
    { t: 1_767_312_000, o: 1, h: 2, l: 0.5, c: 1.5, v: 100 },
    { t: 1_767_398_400, o: 1.5, h: 2.5, l: 1, c: 2, v: 120 },
  ],
  indicators: {
    rsi: [null, 55],
    macd: { line: [null, 0.4], signal: [null, 0.2], hist: [null, 0.2] },
    kc: { upper: [null, 2.4], lower: [null, 0.6] },
  },
  volume_profile: [{ price: 1.5, volume: 220 }],
  levels: { entry: 1.4, stop: 1.1, target1: 2.2, target2: null, working_stop: 1.2 },
  overlays: [
    {
      side: 'target',
      source: 'EMA20',
      shape: { kind: 'curve', label: 'EMA20', points: [[1_767_312_000, 1.2]] },
    },
  ],
  notes: [],
  currency: '$',
};

describe('PlanChart', () => {
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
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  function mount(ticker: string | null, tradeId: string | null) {
    const fixture = TestBed.createComponent(PlanChart);
    fixture.componentRef.setInput('ticker', ticker);
    fixture.componentRef.setInput('tradeId', tradeId);
    fixture.detectChanges();
    return fixture;
  }

  const chartRequest = () =>
    backend.expectOne((req) => req.url === '/api/v1/market/chart/AAPL');

  it('loads the chart for its ticker and plan id', () => {
    mount('AAPL', ID);
    const request = chartRequest();
    expect(request.request.params.get('trade_id')).toBe(ID);
  });

  it('asks for nothing before the ticker is known', () => {
    mount(null, null);
    backend.expectNone((req) => req.url.startsWith('/api/v1/market/chart/'));
  });

  it('captions the chart with the ticker and the drawn methods', () => {
    const fixture = mount('AAPL', ID);
    chartRequest().flush(RESPONSE);
    fixture.detectChanges();
    const caption = (fixture.nativeElement as HTMLElement).querySelector('figcaption');
    expect(caption?.textContent).toContain("AAPL — daily, with this plan's levels · EMA20");
  });

  it('says so when the window has no bars', () => {
    const fixture = mount('AAPL', ID);
    chartRequest().flush({ ...RESPONSE, ohlcv: [] });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent)
      .toContain('No price history for this window');
  });

  it('offers a retry that re-issues the request after a failure', () => {
    const fixture = mount('AAPL', ID);
    chartRequest().flush(
      { error: { code: 'unavailable', message: 'nope' } },
      { status: 503, statusText: 'x' },
    );
    fixture.detectChanges();
    const retry = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.retry');
    expect(retry).toBeTruthy();

    retry!.click();
    fixture.detectChanges();
    chartRequest().flush(RESPONSE);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.retry')).toBeNull();
  });
});
