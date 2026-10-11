import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../../../api/event-stream';
import { Leg, StatusEvent, TradeDetailStore } from '../../../stores/trade-detail.store';
import { dateTime } from '../../../ui/format';
import { OutcomePath } from './outcome-path';

const LEGS: Leg[] = [
  { fraction: 0.5, exitPrice: 110, r: 2, reason: 'TP1' },
  { fraction: 0.5, exitPrice: null, r: null, reason: null },
];
const EVENTS: StatusEvent[] = [
  { status: 'PENDING', reason: 'Waiting for trigger', at: '2026-10-10T10:00:00Z' },
  { status: 'OPEN', reason: 'Triggered', at: '2026-10-10T11:00:00Z' },
];

describe('OutcomePath', () => {
  let fixture: ComponentFixture<OutcomePath>;
  let root: HTMLElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [OutcomePath],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: { changes: () => signal(0) } },
        TradeDetailStore,
      ],
    });
    fixture = TestBed.createComponent(OutcomePath);
    root = fixture.nativeElement;
  });

  function render(legs: Leg[] = [], timeline: StatusEvent[] = []): void {
    fixture.componentRef.setInput('legs', legs);
    fixture.componentRef.setInput('timeline', timeline);
    fixture.detectChanges();
  }

  it('renders no panels when both inputs are absent', () => {
    fixture.detectChanges();
    expect(root.querySelectorAll('sb-panel')).toHaveLength(0);
  });

  it('omits Scale-out for a single leg', () => {
    render([LEGS[0]]);
    expect(root.querySelectorAll('sb-panel')).toHaveLength(0);
  });

  it('labels the first leg First and every subsequent leg Runner with unsigned shares', () => {
    render([...LEGS, { fraction: 0.25, exitPrice: 115, r: 3, reason: 'Target' }]);
    const labels = [...root.querySelectorAll('dt')].map((node) => node.textContent?.trim());
    expect(labels).toEqual(['First 50%', 'Runner 50%', 'Runner 25%']);
    expect(root.textContent).not.toContain('+50%');
  });

  it('renders closed exit prices, signed R and reasons while identifying an open runner', () => {
    render(LEGS);
    expect(root.textContent).toContain('110.00');
    expect(root.querySelector('.pos')?.textContent).toBe('+2.00R');
    expect(root.textContent).toContain('TP1');
    expect(root.textContent).toContain('still open');
    render([LEGS[0], { fraction: null, exitPrice: 95, r: -1, reason: 'Stop' }]);
    expect(root.querySelector('.neg')?.textContent).toBe('-1.00R');
    expect(root.textContent).toContain('Stop');
  });

  it('renders status events in order with their reasons and formatted times', () => {
    render([], EVENTS);
    expect([...root.querySelectorAll('.tl-status')].map((node) => node.textContent))
      .toEqual(['PENDING', 'OPEN']);
    expect([...root.querySelectorAll('.tl-reason')].map((node) => node.textContent))
      .toEqual(['Waiting for trigger', 'Triggered']);
    expect([...root.querySelectorAll('.tl-at')].map((node) => node.textContent))
      .toEqual(EVENTS.map((event) => dateTime(event.at)));
  });

  it('shows timeline alone for a pending plan without legs or optional event metadata', () => {
    render([], [{ status: 'PENDING', reason: null, at: null }]);
    expect(root.querySelectorAll('sb-panel')).toHaveLength(1);
    expect(root.textContent).toContain('Timeline');
    expect(root.textContent).not.toContain('Scale-out');
    expect(root.querySelector('.tl-status')?.textContent).toBe('PENDING');
    expect(root.querySelector('.tl-reason')).toBeNull();
    expect(root.querySelector('.tl-at')).toBeNull();
  });

  it('uses the store settled legs in preference to live legs', () => {
    const store = TestBed.inject(TradeDetailStore);
    const backend = TestBed.inject(HttpTestingController);
    store.setId('settled-trade');
    backend.expectOne((request) => request.url.endsWith('/trades/settled-trade')).flush({
      id: 'settled-trade', ticker: 'AAPL', status: 'CLOSED',
      detail: {
        legs: [{ fraction: 1, exit_price: 999, r: 99, reason: 'Live record' }],
        legs_realized: [
          { fraction: 0.5, exit_price: 110, r: 2, reason: 'Settled first' },
          { fraction: 0.5, exit_price: 115, r: 3, reason: 'Settled runner' },
        ],
      },
    });
    backend.expectOne('/api/v1/trades/settled-trade/journal')
      .flush({ journaled: false, entry: null });
    render(store.legs(), store.timeline());
    expect(root.textContent).toContain('Settled first');
    expect(root.textContent).toContain('Settled runner');
    expect(root.textContent).not.toContain('Live record');
    expect(root.textContent).not.toContain('999');
    backend.verify();
  });
});
