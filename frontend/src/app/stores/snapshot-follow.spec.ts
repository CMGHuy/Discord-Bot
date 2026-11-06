import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MarketMeta, SnapshotUpdate } from '../api/models';
import { LiveValuesStore } from './live-values.store';
import { followSnapshot, snapshotMeta } from './snapshot-follow';

const EARLIER = '2026-10-29T14:00:00Z';
const NEWER = '2026-10-29T14:05:00Z';
const update = (key: string, computed_at: string): SnapshotUpdate =>
  ({ key, computed_at, stale_inputs: false, refreshing: false, error: null });

describe('followSnapshot', () => {
  const map = signal<Record<string, SnapshotUpdate>>({});

  beforeEach(() => {
    map.set({});
    TestBed.configureTestingModule({
      providers: [{
        provide: LiveValuesStore,
        useValue: { snapshot: (key: string) => computed(() => map()[key] ?? null) },
      }],
    });
  });

  function push(key: string, at: string): void {
    map.update((rows) => ({ ...rows, [key]: update(key, at) }));
    TestBed.tick();
  }

  it('reloads once per newer computed_at', () => {
    const reload = vi.fn();
    const loaded = signal<string | null>(EARLIER);
    TestBed.runInInjectionContext(() => followSnapshot(() => 'risk', loaded, reload));
    push('risk', EARLIER);
    expect(reload).not.toHaveBeenCalled();
    push('risk', NEWER);
    expect(reload).toHaveBeenCalledTimes(1);
    loaded.set(NEWER);
    TestBed.tick();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('reloads a request-sourced page once when its first snapshot lands', () => {
    const reload = vi.fn();
    TestBed.runInInjectionContext(() => followSnapshot(() => 'risk', () => null, reload));
    push('risk', NEWER);
    expect(reload).toHaveBeenCalledTimes(1);
    push('risk', NEWER);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('follows nothing when the key is null', () => {
    const reload = vi.fn();
    TestBed.runInInjectionContext(() => followSnapshot(() => null, () => null, reload));
    push('risk', NEWER);
    expect(reload).not.toHaveBeenCalled();
  });

  it('follows each month separately when the key changes', () => {
    const reload = vi.fn();
    const key = signal('calendar:2026-09');
    TestBed.runInInjectionContext(() => followSnapshot(key, () => null, reload));
    push(key(), NEWER);
    key.set('calendar:2026-10');
    push(key(), NEWER);
    expect(reload).toHaveBeenCalledTimes(2);
    key.set('calendar:2026-09');
    TestBed.tick();
    expect(reload).toHaveBeenCalledTimes(2);
  });
});

describe('snapshotMeta', () => {
  const meta: MarketMeta = {
    as_of: EARLIER, refreshing: false, error: null,
    stale_count: 0, missing_count: 0, incomplete: false, source: 'snapshot',
  };
  const live = update('risk', NEWER);

  it('returns null for missing metadata', () => {
    expect(snapshotMeta(undefined, live)).toBeNull();
    expect(snapshotMeta(null, live)).toBeNull();
  });

  it('preserves object identity when there is no live update', () => {
    expect(snapshotMeta(meta, null)).toBe(meta);
  });

  it('reports a refresh from either source', () => {
    expect(snapshotMeta(meta, { ...live, refreshing: true })?.refreshing).toBe(true);
    expect(snapshotMeta({ ...meta, refreshing: true }, live)?.refreshing).toBe(true);
  });

  it('uses the live error only when metadata has none', () => {
    const failed = { ...live, error: 'live error' };
    expect(snapshotMeta(meta, failed)?.error).toBe('live error');
    expect(snapshotMeta({ ...meta, error: 'body error' }, failed)?.error).toBe('body error');
  });
});
