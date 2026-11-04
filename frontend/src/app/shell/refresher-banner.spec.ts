import { WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveValuesStore } from '../stores/live-values.store';
import { RefresherBanner } from './refresher-banner';

describe('sb-refresher-banner (v201)', () => {
  let stalled: WritableSignal<boolean>;

  beforeEach(() => {
    stalled = signal(false);
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: LiveValuesStore, useValue: { stalled } }],
    });
  });

  it('is hidden while the refresher runs', () => {
    const f = TestBed.createComponent(RefresherBanner);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('.refresher-strip')).toBeNull();
  });

  it('shows the exact alert when stalled', () => {
    stalled.set(true);
    const f = TestBed.createComponent(RefresherBanner);
    f.detectChanges();
    const strip = (f.nativeElement as HTMLElement).querySelector('.refresher-strip');
    expect(strip?.getAttribute('role')).toBe('alert');
    expect(strip?.textContent?.trim()).toBe('Prices paused: refresher not running');
  });
});
