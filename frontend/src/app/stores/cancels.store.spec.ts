import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { CANCEL_PAYLOAD, EMPTY_CANCEL_PAYLOAD } from '../testing/cancel-fixtures';
import { CANCELS_URL, CancelsStore, NO_FILTER } from './cancels.store';

const keys = (value: object): string[] => Object.keys(value).sort();
// What `cancel_precision.precision_payload` emits (index Contracts). A fixture
// that drifts from the wire fails here, before a screen spec passes against it.
const PAYLOAD_KEYS = ['baseline', 'caption', 'cards', 'data_as_of', 'generated_at', 'headline',
  'out_of_scope', 'risk_cap_label', 'rows', 'rule_changes', 'small_n_threshold', 'splits', 'tp1_note', 'window'];
const FIGURE_KEYS = ['counts', 'excluded', 'n', 'net_r', 'net_r_ci', 'precision', 'precision_ci',
  'r_avoided', 'r_missed', 'small_n', 'ties', 'total', 'unresolved_r'];
const ROW_KEYS = ['badge', 'cancel_date', 'cap_size_pct', 'direction', 'entry', 'entry_model', 'entry_source',
  'excluded', 'exit_date', 'horizon_key', 'origin', 'outcome', 'plan_id', 'r', 'raw_reason', 'reason',
  'stop', 'stop_ceiling_pct', 'strategy', 'ticker', 'tie', 'tp1'];

function setup(): { store: InstanceType<typeof CancelsStore>; http: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
    ],
  });
  return { store: TestBed.inject(CancelsStore), http: TestBed.inject(HttpTestingController) };
}

describe('CancelsStore', () => {
  let store: InstanceType<typeof CancelsStore>;
  let http: HttpTestingController;

  beforeEach(() => {
    ({ store, http } = setup());
  });

  it('fixtures carry the v188 wire shape', () => {
    expect(keys(CANCEL_PAYLOAD)).toEqual(PAYLOAD_KEYS);
    expect(keys(EMPTY_CANCEL_PAYLOAD)).toEqual(PAYLOAD_KEYS);
    const p = CANCEL_PAYLOAD;
    const figures = [
      ...Object.values(p.headline), p.baseline, ...Object.values(p.cards),
      ...Object.values(p.splits.origin), ...Object.values(p.splits.direction),
      ...Object.values(p.splits.horizon),
    ];
    for (const f of figures) {
      expect(keys(f)).toEqual(FIGURE_KEYS);
      expect(keys(f.counts)).toEqual(['right', 'unresolved', 'untriggered_after_cancel', 'wrong']);
    }
    for (const r of p.rows) expect(keys(r)).toEqual(ROW_KEYS);
    expect(keys(p.cards)).toEqual(['expired', 'invalidated', 'other', 'risk_cap', 'risk_cap_fill']);
  });

  it('loads the payload once from /api/v1/cancel-precision', () => {
    expect(CANCELS_URL).toBe('/api/v1/cancel-precision');
    store.load().subscribe();
    expect(store.loading()).toBe(true);
    const req = http.expectOne(CANCELS_URL);
    expect(req.request.method).toBe('GET');
    req.flush(CANCEL_PAYLOAD);
    expect(store.data()).toEqual(CANCEL_PAYLOAD);
    expect(store.loading()).toBe(false);
    expect(store.error()).toBeNull();
    expect(store.rows().length).toBe(6);
    http.verify();
  });

  it('keeps the figures on screen when a reload fails', () => {
    store.load().subscribe();
    http.expectOne(CANCELS_URL).flush(CANCEL_PAYLOAD);
    store.load().subscribe({ error: () => undefined });
    http.expectOne(CANCELS_URL).flush(
      { error: { code: 'internal', message: 'boom' } },
      { status: 500, statusText: 'Server Error' },
    );
    expect(store.data()).toEqual(CANCEL_PAYLOAD);
    expect(store.error()).toBeTruthy();
    expect(store.loading()).toBe(false);
  });

  it('toggles a card, an outcome and a split', () => {
    store.pickCard('risk_cap');
    expect(store.filter().card).toBe('risk_cap');
    store.pickCard('risk_cap');
    expect(store.filter().card).toBeNull();
    store.pickCard('expired');
    store.pickCard('invalidated');
    expect(store.filter().card).toBe('invalidated');

    store.pickOutcome('wrong');
    expect(store.filter().outcome).toBe('wrong');
    store.pickOutcome('wrong');
    expect(store.filter().outcome).toBeNull();

    store.pickSplit({ dim: 'origin', value: 'regular' });
    store.pickSplit({ dim: 'origin', value: 'regular' });
    expect(store.filter().split).toBeNull();
    store.pickSplit({ dim: 'origin', value: 'regular' });
    store.pickSplit({ dim: 'origin', value: 'next_session' });
    expect(store.filter().split).toEqual({ dim: 'origin', value: 'next_session' });

    store.pickOutcome('right');
    store.pickCard(null);
    expect(store.filter().card).toBeNull();
    expect(store.filter().outcome).toBe('right');
    expect(store.filter().split).toEqual({ dim: 'origin', value: 'next_session' });
  });

  it('filters rows through filterRows', () => {
    store.load().subscribe();
    http.expectOne(CANCELS_URL).flush(CANCEL_PAYLOAD);
    store.pickCard('risk_cap_fill');
    expect(store.rows().map((r) => r.entry_model)).toEqual(['cancel_fill']);
    store.clearFilter();
    expect(store.filter()).toEqual(NO_FILTER);
    expect(store.rows().length).toBe(6);
  });

  it('has no rows before the first load', () => {
    expect(store.rows()).toEqual([]);
    expect(store.data()).toBeNull();
    expect(store.filter()).toEqual(NO_FILTER);
  });
});
