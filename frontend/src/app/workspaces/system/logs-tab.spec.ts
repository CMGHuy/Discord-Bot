import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Logs } from '../../api/models';
import { SystemStore } from '../../stores/system.store';
import { LogsTab } from './logs-tab';

function payload(overrides: Partial<Logs> = {}): Logs {
  return { source: 'bot', lines: 500, path: 'logs/bot.log', content: '', ...overrides };
}

/** SystemStore's onInit fires all three of settings/logs/scan together
 *  regardless of which tab component is under test -- flushed empty so
 *  they don't leave pending requests behind for a spec that only cares
 *  about logs. */
function flushOtherFetches(backend: HttpTestingController): void {
  backend
    .expectOne('/api/v1/system/settings')
    .flush({ sections: [], audit: [], restart_available: false });
  backend
    .expectOne((r) => r.url === '/api/v1/system/scan')
    .flush({ status: 'idle' } as never);
}

function seed(): { fixture: ComponentFixture<LogsTab>; backend: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      SystemStore,
    ],
  });
  const fixture = TestBed.createComponent(LogsTab);
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

describe('LogsTab states', () => {
  it('shows a skeleton while loading, before the first response', () => {
    const { fixture } = seed();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeTruthy();
  });

  it('shows the error state on a first-load failure', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flushOtherFetches(backend);
    backend
      .expectOne((r) => r.url === '/api/v1/system/logs')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.failed')).toBeTruthy();
  });

  it('shows the empty state, not a spinner, for an empty log file', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flushOtherFetches(backend);
    backend
      .expectOne((r) => r.url === '/api/v1/system/logs')
      .flush(payload({ content: '' }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('This log is empty');
    expect(el.querySelector('.skeleton')).toBeNull();
  });

  it('keeps the source picker and refresh button usable while the log is empty', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flushOtherFetches(backend);
    backend
      .expectOne((r) => r.url === '/api/v1/system/logs')
      .flush(payload({ content: '' }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const refresh = [...el.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Refresh'),
    );
    expect(refresh).toBeTruthy();
  });
});
