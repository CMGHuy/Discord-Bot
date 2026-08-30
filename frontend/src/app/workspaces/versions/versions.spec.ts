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
import { VersionHistory } from '../../api/models';
import { Versions } from './versions';
import { VersionsStore } from '../../stores/versions.store';

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

/** Two components, one bump -- small enough that hover assertions in later
 *  tests can name an exact expected version instead of picking through SIX. */
const PAIRED: VersionHistory = {
  generated_at: '2026-08-15 07:00:00 UTC',
  basis: 'Versions observed together in VERSION.json.',
  live: { ui: '1.2.0', bot: '1.1.2' },
  stale: false,
  components: ['ui', 'bot'],
  current: { ui: '1.2.0', bot: '1.1.2' },
  releases: [
    { date: '2026-07-01', last_seen: '2026-07-04', commit: 'a1', subject: 'first',
      versions: { ui: '1.0.0', bot: '1.0.0' }, changed: ['ui', 'bot'] },
    { date: '2026-07-05', last_seen: '2026-07-31', commit: 'a2', subject: 'ui bumps',
      versions: { ui: '1.2.0', bot: '1.1.2' }, changed: ['ui', 'bot'] },
  ],
};

/** Stand the component up and answer its one request. Each test gets its
 *  own TestBed, same reasoning as the store spec's `seed()`: a fresh
 *  module per test is cheap here and avoids state leaking between cases. */
function seed(payload: VersionHistory): ComponentFixture<Versions> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      VersionsStore,
    ],
  });
  const fixture = TestBed.createComponent(Versions);
  TestBed.inject(VersionsStore).load();
  TestBed.inject(HttpTestingController).expectOne('/api/v1/versions').flush(payload);
  return fixture;
}

function seedUnflushed(): { fixture: ComponentFixture<Versions>; backend: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      VersionsStore,
    ],
  });
  const fixture = TestBed.createComponent(Versions);
  TestBed.inject(VersionsStore).load();
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

describe('Versions', () => {
  it('does not widen when components are added', async () => {
    const fixture = seed(SIX);
    // A narrow host is the real test: the page must fit the container it is
    // given, not merely fit on a wide screen.
    fixture.nativeElement.style.width = '640px';
    await fixture.whenStable();
    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    expect(host.scrollWidth).toBeLessThanOrEqual(host.clientWidth);
  });

  it('puts the "now" tick first, matching the flipped axis', async () => {
    const fixture = seed(SIX);
    await fixture.whenStable();
    fixture.detectChanges();

    const ticks = (fixture.nativeElement as HTMLElement).querySelectorAll('.ticks span');
    expect(ticks).toHaveLength(2);
    expect(ticks[0].classList.contains('now')).toBe(true);
    expect(ticks[1].classList.contains('now')).toBe(false);
  });

  it('flushes the absent region against the trailing (oldest) edge', async () => {
    const fixture = seed(SIX);
    await fixture.whenStable();
    fixture.detectChanges();

    // 'worker' is one of SIX's late arrivals, so it has an absent region.
    const absent = (fixture.nativeElement as HTMLElement).querySelector('.absent') as HTMLElement;
    expect(absent).toBeTruthy();
    const leftPct = parseFloat(absent.style.left);
    const widthPct = parseFloat(absent.style.width);
    // Its trailing edge must sit flush at 100% -- the flipped axis's oldest
    // end -- regardless of the exact dates in the fixture.
    expect(leftPct + widthPct).toBeCloseTo(100, 1);
  });

  it('shows paired versions on hover, worded "paired with" not "compatible", and dims everything except the matching time slice', async () => {
    const fixture = seed(PAIRED);
    await fixture.whenStable();
    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    // components: ['ui', 'bot'] -- the ui lane renders first, so this is
    // its current segment (ui 1.2.0, closed by release a2).
    const current = host.querySelector('.segment.current') as HTMLButtonElement;
    current.dispatchEvent(new Event('pointerenter'));
    fixture.detectChanges();

    const tooltip = host.querySelector('.tooltip');
    expect(tooltip?.textContent).toContain('ui 1.2.0');
    expect(tooltip?.textContent).toContain('paired with: bot 1.1.2');
    expect(tooltip?.textContent).not.toContain('compatible');

    // Two real dim rectangles flank the hovered segment's own geometry --
    // same fractions, not a hand-rederived copy -- leaving exactly its own
    // left/width undimmed in between (v54 Task 24: replaced a single
    // element's 9999px-spread shadow trick with real, gate-visible
    // geometry).
    const dims = host.querySelectorAll('.dim');
    expect(dims).toHaveLength(2);
    const segLeft = parseFloat(current.style.left);
    const segWidth = parseFloat(current.style.width);
    expect(parseFloat((dims[0] as HTMLElement).style.left)).toBeCloseTo(0, 5);
    expect(parseFloat((dims[0] as HTMLElement).style.width)).toBeCloseTo(segLeft, 5);
    expect(parseFloat((dims[1] as HTMLElement).style.left)).toBeCloseTo(segLeft + segWidth, 5);
    expect(parseFloat((dims[1] as HTMLElement).style.width)).toBeCloseTo(100 - segLeft - segWidth, 5);

    current.dispatchEvent(new Event('pointerleave'));
    fixture.detectChanges();
    expect(host.querySelector('.tooltip')).toBeNull();
    expect(host.querySelectorAll('.dim')).toHaveLength(0);
  });
});

describe('Versions states', () => {
  it('shows a skeleton while loading, before the first response', () => {
    const { fixture } = seedUnflushed();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeTruthy();
  });

  it('shows the error state on a first-load failure', async () => {
    const { fixture, backend } = seedUnflushed();
    fixture.detectChanges();
    backend
      .expectOne('/api/v1/versions')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.failed')).toBeTruthy();
  });

  it('shows the no-data-yet empty state, not a spinner, when no history is recorded', async () => {
    const { fixture, backend } = seedUnflushed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/versions').flush({
      generated_at: null,
      basis: null,
      live: {},
      stale: false,
      components: [],
      current: {},
      releases: [],
    } satisfies VersionHistory);
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('No version history');
    expect(el.querySelector('.skeleton')).toBeNull();
  });
});
