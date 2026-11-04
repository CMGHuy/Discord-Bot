import { Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Subject, of, throwError } from 'rxjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { TapeResponse, TapeRow } from '../api/models';
import { TapeFeed } from './tape-feed';

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();

  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) { counter = signal(0); this.counters.set(name, counter); }
    return counter;
  }

  changes(name: string, _options?: { minIntervalMs: number }): Signal<number> {
    return this.counterFor(name).asReadonly();
  }

  raise(name: string): void {
    this.counterFor(name).update((n) => n + 1);
  }
}

const row = (symbol: string): TapeRow => ({ symbol, price: 1, change_pct: 0, context_kind: null, context_label: null, sort_rank: 2 });
const flush = async () => { TestBed.tick(); await Promise.resolve(); };

describe('TapeFeed', () => {
  let api: { tape: ReturnType<typeof vi.fn> };
  let events: FakeEventStream;
  let feed: TapeFeed;

  beforeEach(() => {
    api = { tape: vi.fn().mockReturnValue(of({ as_of: '2026-10-29T14:00:00Z', rows: [] })) };
    events = new FakeEventStream();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: ApiClient, useValue: api },
        { provide: EventStream, useValue: events },
      ],
    });
    feed = TestBed.inject(TapeFeed);
  });

  it('two owners registered in one tick make one request for the union', async () => {
    feed.register('tape', signal(['nvda', 'MSFT']));
    feed.register('index', signal(['^GSPC', 'MSFT']));
    feed.refresh(); feed.refresh();
    await flush();
    expect(api.tape).toHaveBeenCalledTimes(1);
    expect(api.tape).toHaveBeenCalledWith(['NVDA', 'MSFT', '^GSPC']);
  });

  it('rows are keyed by upper-case symbol and asOf is the reply stamp', async () => {
    api.tape.mockReturnValue(of({ as_of: '2026-10-29T14:00:00Z', rows: [row('NVDA'), row('^GSPC')] }));
    feed.register('tape', signal(['NVDA'])); feed.register('index', signal(['^GSPC']));
    await flush();
    expect(Object.keys(feed.rows())).toEqual(['NVDA', '^GSPC']);
    expect(feed.asOf()).toBe('2026-10-29T14:00:00Z');
  });

  it('an empty union sends nothing and clears rows', async () => {
    feed.register('tape', signal([]));
    await flush();
    expect(api.tape).not.toHaveBeenCalled();
    expect(feed.rows()).toEqual({});
  });

  it('a throttled scan event refetches once for everyone', async () => {
    feed.register('tape', signal(['NVDA'])); feed.register('index', signal(['^GSPC']));
    await flush();
    events.raise('scan');
    await flush();
    expect(api.tape).toHaveBeenCalledTimes(2);
  });

  it('a market event refetches the union once', async () => {
    feed.register('tape', signal(['NVDA'])); feed.register('index', signal(['^GSPC']));
    await flush();
    events.raise('market');
    await flush();
    expect(api.tape).toHaveBeenCalledTimes(2);
    expect(api.tape).toHaveBeenLastCalledWith(['NVDA', '^GSPC']);
  });

  it("changing one owner's symbols refetches the new union once", async () => {
    const symbols = signal(['NVDA']);
    feed.register('tape', symbols);
    await flush();
    symbols.set(['NVDA', 'AMD']);
    await flush();
    expect(api.tape).toHaveBeenCalledTimes(2);
    expect(api.tape).toHaveBeenLastCalledWith(['NVDA', 'AMD']);
  });

  it('an error keeps the previous rows', async () => {
    api.tape.mockReturnValue(of({ as_of: 'a', rows: [row('NVDA')] }));
    feed.register('tape', signal(['NVDA']));
    await flush();
    api.tape.mockReturnValue(throwError(() => new Error('down')));
    feed.refresh();
    await flush();
    expect(Object.keys(feed.rows())).toEqual(['NVDA']);
    expect(feed.loading()).toBe(false);
  });

  it('a late reply from an older request is dropped', async () => {
    const pending: Subject<TapeResponse>[] = [];
    api.tape.mockImplementation(() => { const s = new Subject<TapeResponse>(); pending.push(s); return s; });
    feed.register('tape', signal(['A']));
    await flush();
    feed.refresh();
    await flush();
    expect(pending.length).toBe(2);
    pending[1].next({ as_of: 'fresh', rows: [row('B')] });
    pending[0].next({ as_of: 'stale', rows: [row('A')] });
    expect(Object.keys(feed.rows())).toEqual(['B']);
    expect(feed.asOf()).toBe('fresh');
  });

  it('a second registration for the same owner replaces the first', async () => {
    feed.register('tape', signal(['OLD']));
    feed.register('tape', signal(['NEW']));
    await flush();
    expect(api.tape).toHaveBeenCalledWith(['NEW']);
  });
});
