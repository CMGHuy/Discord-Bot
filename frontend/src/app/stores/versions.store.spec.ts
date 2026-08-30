import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { VersionHistory } from '../api/models';
import { VersionsStore } from './versions.store';

/* The Versions workspace's data.
 *
 * What earns tests here is ordering, filtering and paging — the wire is
 * oldest-first and the store reverses it exactly once, a chip toggle is its
 * own clear, and a filter change must not strand the reader on a page that no
 * longer exists. The fetch itself is the same shape as every other store and
 * is covered only where it fails.
 */

let store: InstanceType<typeof VersionsStore>;

/** Stand the store up and answer its one request.
 *
 *  Takes the payload rather than assuming one, because two tests need a
 *  different history (the single-release case below, and the six-component
 *  case in Task 8). `VersionsStore.load()` runs from `onInit`, so the request
 *  is in flight as soon as the store is injected — flushing is all that is
 *  left to do. */
function seed(payload: VersionHistory): void {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      VersionsStore,
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  store = TestBed.inject(VersionsStore);
  store.load();
  http.expectOne('/api/v1/versions').flush(payload);
}

const RESPONSE: VersionHistory = {
  generated_at: '2026-08-15 07:00:00 UTC',
  basis: 'Versions observed together in VERSION.json.',
  live: { ui: '1.2.0', bot: '1.1.2' },
  stale: false,
  components: ['ui', 'bot', 'worker'],
  current: { ui: '1.2.0', bot: '1.1.2', worker: '0.1.0' },
  releases: [
    { date: '2026-07-01', last_seen: '2026-07-04', commit: 'a1', subject: 'first',
      versions: { ui: '1.0.0', bot: '1.0.0', worker: null }, changed: ['ui', 'bot'] },
    { date: '2026-07-05', last_seen: '2026-07-05', commit: 'a2', subject: 'bot moves',
      versions: { ui: '1.0.0', bot: '1.1.2', worker: null }, changed: ['bot'] },
    { date: '2026-07-06', last_seen: '2026-08-15', commit: 'a3', subject: 'worker joins',
      versions: { ui: '1.2.0', bot: '1.1.2', worker: '0.1.0' }, changed: ['ui', 'worker'] },
  ],
};

describe('VersionsStore', () => {
  beforeEach(() => seed(RESPONSE));

  it('reverses the wire order exactly once', () => {
    expect(store.releases().map((r) => r.commit)).toEqual(['a3', 'a2', 'a1']);
  });

  it('filters to the releases carrying a component version', () => {
    store.toggleFilter('bot', '1.1.2');
    expect(store.visible().map((r) => r.commit)).toEqual(['a3', 'a2']);
  });

  it('clears the filter when the same chip is chosen twice', () => {
    store.toggleFilter('bot', '1.1.2');
    store.toggleFilter('bot', '1.1.2');
    expect(store.filter()).toBeNull();
    expect(store.visible()).toHaveLength(3);
  });

  it('never matches a null version — absent is not a value', () => {
    store.toggleFilter('worker', '');
    expect(store.visible()).toHaveLength(0);
  });

  it('resets to page 1 when the filter changes', () => {
    store.setPage(2);
    store.toggleFilter('bot', '1.1.2');
    expect(store.page()).toBe(1);
  });

  it('exposes components, current and basis from the payload', () => {
    expect(store.components()).toEqual(['ui', 'bot', 'worker']);
    expect(store.current()).toEqual(RESPONSE.current);
    expect(store.basis()).toBe(RESPONSE.basis);
  });

  it('surfaces the stale flag', () => {
    seed({ ...RESPONSE, stale: true });
    expect(store.stale()).toBe(true);
  });

  it('reports the pre-slice total in pageSpec, not visible().length', () => {
    expect(store.pageSpec()).toEqual({ total: 3, page: 1, perPage: 25 });
  });

  it('renders nothing rather than throwing when history is empty', () => {
    seed({ ...RESPONSE, components: [], current: {}, releases: [] });
    expect(store.releases()).toEqual([]);
    expect(store.visible()).toEqual([]);
    expect(store.empty()).toBe(false); // a response arrived; it's just empty
  });

  describe('lane geometry', () => {
    it('lays segments out on a time axis, not by release index', () => {
      // RESPONSE's own `ui` lane doesn't isolate this property (its second
      // segment happens to be both later AND longer), so this uses a fixture
      // built so segment[0]'s hold period is unambiguously longer: 10 days,
      // then 1 day. Index order would make them equal; time must not.
      const TIME_AXIS: VersionHistory = {
        ...RESPONSE,
        components: ['ui'],
        current: { ui: '1.2.0' },
        releases: [
          { date: '2026-01-01', last_seen: '2026-01-11', commit: 't1', subject: 'first',
            versions: { ui: '1.0.0' }, changed: ['ui'] },
          { date: '2026-01-12', last_seen: '2026-01-13', commit: 't2', subject: 'bump',
            versions: { ui: '1.1.0' }, changed: ['ui'] },
          { date: '2026-01-14', last_seen: '2026-01-14', commit: 't3', subject: 'bump again',
            versions: { ui: '1.2.0' }, changed: ['ui'] },
        ],
      };
      seed(TIME_AXIS);
      const ui = store.lanes().find((l) => l.component === 'ui')!;
      expect(ui.segments[0].width).toBeGreaterThan(ui.segments[1].width);
    });

    it('every lane sums to 1', () => {
      for (const lane of store.lanes()) {
        const total = lane.segments.reduce((sum, s) => sum + s.width, 0) + lane.absentWidth;
        expect(total).toBeCloseTo(1, 5);
      }
    });

    it('floors a sub-pixel segment and takes the surplus from its neighbours', () => {
      store.setStripWidth(200); // floor = 2/200 = 0.01
      const ui = store.lanes().find((l) => l.component === 'ui')!;
      for (const s of ui.segments) expect(s.width).toBeGreaterThanOrEqual(0.01);
      expect(ui.segments.reduce((sum, s) => sum + s.width, 0)).toBeCloseTo(1, 5);
    });

    it('gives a late component an absent region, not a segment', () => {
      const worker = store.lanes().find((l) => l.component === 'worker')!;
      // The leading gap is a region with no version, never a segment carrying a
      // falsy one — the two render differently and must not be conflated.
      expect(worker.absentWidth).toBeGreaterThan(0);
      expect(worker.segments).toHaveLength(1);
      expect(worker.segments[0].version).toBe('0.1.0');
    });

    it('brackets the visible page', () => {
      const b = store.bracket();
      expect(b.start).toBeGreaterThanOrEqual(0);
      expect(b.start + b.width).toBeLessThanOrEqual(1.000001);
    });

    it('draws the newest segment flush to the strip\'s leading edge', () => {
      // RESPONSE's `ui` lane has two runs (1.0.0 then 1.2.0); the current one
      // is the flip's whole point — it must be at start 0, not buried at the
      // trailing edge where the old oldest-first axis put it.
      const ui = store.lanes().find((l) => l.component === 'ui')!;
      const current = ui.segments[ui.segments.length - 1];
      expect(current.current).toBe(true);
      expect(current.start).toBeCloseTo(0, 5);
    });

    it('trails the earliest segment off toward the strip\'s far edge', () => {
      const ui = store.lanes().find((l) => l.component === 'ui')!;
      const earliest = ui.segments[0];
      // ui's absentWidth is 0 (it existed from the first release), so the
      // earliest segment's trailing edge lands exactly at 1.
      expect(earliest.start + earliest.width).toBeCloseTo(1, 5);
    });

    it('captures paired versions from the run-closing release', () => {
      // a3 closes ui's current run and carries { ui: '1.2.0', bot: '1.1.2',
      // worker: '0.1.0' } -- pairedWith is that snapshot minus ui itself.
      const ui = store.lanes().find((l) => l.component === 'ui')!;
      const current = ui.segments[ui.segments.length - 1];
      expect(current.pairedWith).toEqual({ bot: '1.1.2', worker: '0.1.0' });
    });

    it('excludes a component that had not shipped yet from pairedWith', () => {
      // a2 closes ui's first run (a1..a2, both ui 1.0.0) and carries
      // { ui: '1.0.0', bot: '1.1.2', worker: null } -- worker must not appear.
      const ui = store.lanes().find((l) => l.component === 'ui')!;
      const earliest = ui.segments[0];
      expect(earliest.pairedWith).toEqual({ bot: '1.1.2' });
    });

    it('survives a single release without dividing by zero', () => {
      // One release means a zero-length time span. `tEnd` is floored at `t0 + 1`
      // precisely so this divides by 1 rather than 0 and yields a full-width
      // segment instead of NaN — which would render as an invisible strip.
      const ONE: VersionHistory = {
        ...RESPONSE,
        components: ['ui'],
        current: { ui: '1.0.0' },
        releases: [{
          date: '2026-07-01', last_seen: '2026-07-01', commit: 'a1', subject: 'only',
          versions: { ui: '1.0.0' }, changed: ['ui'],
        }],
      };
      seed(ONE);
      expect(store.lanes()[0].segments[0].width).toBeCloseTo(1, 5);
      expect(Number.isNaN(store.lanes()[0].segments[0].width)).toBe(false);
    });
  });

  it('keeps an error message and stays renderable', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
        VersionsStore,
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    store = TestBed.inject(VersionsStore);
  store.load();
    http.expectOne('/api/v1/versions').flush(
      { error: { code: 'unavailable', message: 'down' } },
      { status: 503, statusText: 'Service Unavailable' },
    );
    expect(store.error()).toBeTruthy();
    expect(store.releases()).toEqual([]);
  });
});
