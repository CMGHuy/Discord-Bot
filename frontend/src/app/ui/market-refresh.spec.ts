import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LiveValuesStore } from '../stores/live-values.store';
import { MarketRefresh } from './market-refresh';

describe('sb-market-refresh (v201)', () => {
  const requestRefresh = vi.fn();

  beforeEach(() => {
    requestRefresh.mockReset();
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: LiveValuesStore, useValue: { requestRefresh } }],
    });
  });

  function button(symbols: string[]): HTMLButtonElement {
    const f = TestBed.createComponent(MarketRefresh);
    f.componentRef.setInput('symbols', symbols);
    f.detectChanges();
    return (f.nativeElement as HTMLElement).querySelector('button') as HTMLButtonElement;
  }

  it('a click requests a refresh of its symbols', () => {
    button(['MSFT']).click();
    expect(requestRefresh).toHaveBeenCalledWith(['MSFT']);
  });

  it('is disabled with an empty list', () => {
    const b = button([]);
    expect(b.disabled).toBe(true);
    b.click();
    expect(requestRefresh).not.toHaveBeenCalled();
  });
});
