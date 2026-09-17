import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ScanProgressRecord } from '../api/models';
import { LINGER_MS, ScanProgressStrip } from './scan-progress';

const NOW = Date.parse('2026-09-16T14:00:00Z');

const record = (over: Partial<ScanProgressRecord> = {}): ScanProgressRecord => ({
  at: new Date(NOW).toISOString(),
  pct: 66,
  stage: 'analyzing',
  current_ticker: 'AAPL',
  done: 50,
  total: 100,
  qualifying_found: 3,
  ...over,
});

describe('ScanProgressStrip', () => {
  let fixture: ComponentFixture<ScanProgressStrip>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ScanProgressStrip],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(ScanProgressStrip);
    fixture.componentRef.setInput('now', NOW);
  });

  const render = (running: boolean, progress: ScanProgressRecord | null) => {
    fixture.componentRef.setInput('running', running);
    fixture.componentRef.setInput('progress', progress);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  };

  it('renders nothing at all when no scan is running', () => {
    expect(render(false, null).querySelector('.strip')).toBeNull();
  });

  it('shows a determinate bar carrying the published percentage', () => {
    const bar = render(true, record()).querySelector('[role="progressbar"]')!;
    expect(bar.getAttribute('aria-valuenow')).toBe('66');
    expect(bar.querySelector<HTMLElement>('.fill')!.style.width).toBe('66%');
  });

  it('names the phase, the ticker and the phase-local counts', () => {
    const text = render(true, record()).textContent!;
    expect(text).toContain('Analysing');
    expect(text).toContain('AAPL');
    expect(text).toContain('50/100');
  });

  it('counts alerts, not tickers, once the scan is building alerts', () => {
    const text = render(true, record({
      stage: 'building alerts', pct: 94, done: 1, total: 4, current_ticker: null,
    })).textContent!;
    expect(text).toContain('Building alerts');
    expect(text).toContain('1/4');
  });

  it('never claims 0% while it is still waiting for the first record', () => {
    // "A scan started and has achieved nothing" is a different statement
    // from "a scan started"; only the second one is known here.
    const el = render(true, null);
    expect(el.querySelector('.strip')).not.toBeNull();
    expect(el.querySelector('[role="progressbar"]')!.getAttribute('aria-valuenow')).toBeNull();
    expect(el.textContent).not.toContain('0%');
  });

  it('stops claiming live progress once the record has gone stale', () => {
    const stale = record({ at: new Date(NOW - 45_000).toISOString() });
    const el = render(true, stale);
    expect(el.querySelector('.strip')!.classList).toContain('stalled');
    expect(el.textContent).toContain('no progress');
  });

  it('treats an unparseable timestamp as stalled rather than as current', () => {
    const el = render(true, record({ at: 'not a date' }));
    expect(el.querySelector('.strip')!.classList).toContain('stalled');
  });

  it('omits the ticker separator when no ticker is being worked on', () => {
    const text = render(true, record({ current_ticker: null })).textContent!;
    expect(text).not.toContain('·  ·');
    expect(text.trim()).not.toMatch(/·\s*$/);
  });

  describe('finishing', () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it('holds a completed bar briefly instead of vanishing mid-sweep', () => {
      render(true, record());
      const el = render(false, null);
      expect(el.querySelector('.strip')).not.toBeNull();
      expect(el.querySelector('[role="progressbar"]')!.getAttribute('aria-valuenow'))
        .toBe('100');
    });

    it('disappears once the hold elapses', () => {
      render(true, record());
      render(false, null);
      vi.advanceTimersByTime(LINGER_MS + 50);
      fixture.detectChanges();
      expect((fixture.nativeElement as HTMLElement).querySelector('.strip')).toBeNull();
    });

    it('a scan starting during the hold shows that scan, not the old one', () => {
      render(true, record());
      render(false, null);
      const el = render(true, record({ pct: 12, done: 3, total: 25 }));
      expect(el.querySelector('[role="progressbar"]')!.getAttribute('aria-valuenow'))
        .toBe('12');
      vi.advanceTimersByTime(LINGER_MS + 50);
      fixture.detectChanges();
      expect((fixture.nativeElement as HTMLElement).querySelector('.strip'))
        .not.toBeNull();
    });
  });
});
