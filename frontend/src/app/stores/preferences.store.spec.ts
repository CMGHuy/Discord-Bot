import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { PreferencesStore, WRITE_DEBOUNCE_MS } from './preferences.store';

/* NG32 — column-picker persistence, server-side. */

const ENDPOINT = '/api/v1/system/preferences';

describe('PreferencesStore', () => {
  let store: InstanceType<typeof PreferencesStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
      ],
    });
    store = TestBed.inject(PreferencesStore);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => vi.useRealTimers());

  const loadWith = (preferences: object) => {
    store.load();
    backend.expectOne(ENDPOINT).flush({ preferences });
  };

  it('shares one request between imperative and resolver preference loading', () => {
    store.load();
    const resolved: void[] = [];
    store.resolve().subscribe((value) => resolved.push(value));

    const request = backend.expectOne(ENDPOINT);
    request.flush({ preferences: { tables: { trades: ['ticker'] } } });

    expect(store.isLoaded()).toBe(true);
    expect(resolved).toEqual([undefined]);
  });
  it('reads preferences once', () => {
    loadWith({ tables: { trades: ['ticker'] } });

    expect(store.columns('trades')).toEqual(['ticker']);

    // A second load must not re-read: this is the one piece of state whose
    // only writer is this browser, so a re-read could only overwrite what
    // the user just did with what they did a moment earlier.
    store.load();
    backend.verify();
  });

  it('distinguishes "never chosen" from "all hidden"', () => {
    // Conflating them would make "hide every column" unrepresentable, and
    // the table would silently spring back to its defaults.
    loadWith({ tables: { trades: [] } });

    expect(store.columns('trades')).toEqual([]);
    expect(store.columns('never-touched')).toBeNull();
  });

  it('applies a change locally at once', () => {
    loadWith({});

    store.setColumns('trades', ['ticker', 'pnl_pct']);

    // The UI must not wait on a round trip to show a ticked checkbox.
    expect(store.columns('trades')).toEqual(['ticker', 'pnl_pct']);
  });

  it('writes once for a burst of changes', () => {
    loadWith({});

    store.setColumns('trades', ['a']);
    store.setColumns('trades', ['a', 'b']);
    store.setColumns('trades', ['a', 'b', 'c']);
    backend.verify(); // nothing written yet

    vi.advanceTimersByTime(WRITE_DEBOUNCE_MS);

    // Four checkboxes would otherwise be four PUTs. The write is a whole
    // object replace, so only the last one carries anything new.
    const request = backend.expectOne(ENDPOINT);
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({ preferences: { tables: { trades: ['a', 'b', 'c'] } } });
    request.flush({ preferences: request.request.body.preferences });
  });

  it('does not write before the burst settles', () => {
    loadWith({});
    store.setColumns('trades', ['a']);

    vi.advanceTimersByTime(WRITE_DEBOUNCE_MS - 1);

    backend.verify();
  });

  it('keeps other tables when one changes', () => {
    loadWith({ tables: { trades: ['a'], watchlist: ['symbol'] } });

    store.setColumns('trades', ['b']);
    vi.advanceTimersByTime(WRITE_DEBOUNCE_MS);

    const request = backend.expectOne(ENDPOINT);
    expect(request.request.body.preferences.tables).toEqual({
      trades: ['b'],
      watchlist: ['symbol'],
    });
    request.flush({ preferences: request.request.body.preferences });
  });

  it('resets a table back to its default', () => {
    loadWith({ tables: { trades: ['a'] } });

    store.resetColumns('trades');
    vi.advanceTimersByTime(WRITE_DEBOUNCE_MS);

    expect(store.columns('trades')).toBeNull();
    const request = backend.expectOne(ENDPOINT);
    expect(request.request.body.preferences.tables).toEqual({});
    request.flush({ preferences: request.request.body.preferences });
  });

  it('can write immediately when asked', () => {
    loadWith({});
    store.setColumns('trades', ['a']);

    store.flush();

    backend.expectOne(ENDPOINT).flush({ preferences: {} });
    // The pending timer must not fire a second write after a flush.
    vi.advanceTimersByTime(WRITE_DEBOUNCE_MS * 2);
    backend.verify();
  });

  it('flushing with nothing pending writes nothing', () => {
    loadWith({});
    store.flush();
    backend.verify();
  });

  it('survives a failed read with defaults', () => {
    store.load();
    backend.expectOne(ENDPOINT).error(new ProgressEvent('error'), { status: 0 });

    expect(store.columns('trades')).toBeNull();

    // Marked loaded regardless, so one bad request does not retry on every
    // single navigation for the rest of the session.
    store.load();
    backend.verify();
  });

  it('survives a failed write without losing local state', () => {
    loadWith({});
    store.setColumns('trades', ['a']);
    vi.advanceTimersByTime(WRITE_DEBOUNCE_MS);

    backend.expectOne(ENDPOINT).error(new ProgressEvent('error'), { status: 0 });

    // Losing a column preference is not worth a toast over the workspace
    // someone is reading, and this session stays correct either way.
    expect(store.columns('trades')).toEqual(['a']);
  });
});