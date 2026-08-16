import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { VersionHistory } from '../../api/models';
import { Versions } from './versions';

/* The Versions page's one structural guarantee: an open-ended component
 * count costs vertical space, never horizontal. Chips wrap and lanes stack
 * by CSS, but a comment cannot enforce that property -- only a narrow host
 * with more components than the matrix could ever have represented can. */

/** Six components, one of them arriving late. The point is the count: this is
 *  three times what the matrix could represent at all, and the assertion is
 *  that it costs vertical space only. */
const SIX: VersionHistory = {
  generated_at: '2026-08-15 07:00:00 UTC',
  basis: 'Versions observed together in VERSION.json.',
  live: { ui: '2.0.0', bot: '1.1.2', worker: '0.3.0', schema: '4', api: '1.0.0', cron: '0.9.1' },
  stale: false,
  components: ['ui', 'bot', 'worker', 'schema', 'api', 'cron'],
  current: { ui: '2.0.0', bot: '1.1.2', worker: '0.3.0', schema: '4', api: '1.0.0', cron: '0.9.1' },
  releases: [
    { date: '2026-07-01', last_seen: '2026-07-09', commit: 'b1', subject: 'start',
      versions: { ui: '1.0.0', bot: '1.0.0', worker: null, schema: null, api: null, cron: null },
      changed: ['ui', 'bot'] },
    { date: '2026-07-10', last_seen: '2026-08-15', commit: 'b2', subject: 'the rest arrive',
      versions: { ui: '2.0.0', bot: '1.1.2', worker: '0.3.0', schema: '4', api: '1.0.0', cron: '0.9.1' },
      changed: ['ui', 'bot', 'worker', 'schema', 'api', 'cron'] },
  ],
};

describe('Versions', () => {
  it('does not widen when components are added', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    const fixture = TestBed.createComponent(Versions);
    // A narrow host is the real test: the page must fit the container it is
    // given, not merely fit on a wide screen.
    fixture.nativeElement.style.width = '640px';
    TestBed.inject(HttpTestingController).expectOne('/api/v1/versions').flush(SIX);
    await fixture.whenStable();
    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    expect(host.scrollWidth).toBeLessThanOrEqual(host.clientWidth);
  });
});
