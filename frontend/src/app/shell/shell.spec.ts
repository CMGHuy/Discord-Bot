import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import {
  Signal,
  WritableSignal,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject } from 'rxjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import { RouteLoadingService } from '../routing/route-loading.service';
import { TapeStore } from '../stores/tape.store';
import { Shell } from './shell';

/** Same fake as `chart.store.spec.ts`/`connection.store.spec.ts` -- a counter
 *  per event name, bumped by name rather than replayed as an object, matching
 *  `EventStream.changes()`. `state`/`connect`/`lastSeq`/`raised` are here
 *  because the shell also wires `ConnectionStore` and `RouteRefreshService`,
 *  both real and calling straight through to this fake. */
class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();
  private readonly raisedSubject = new Subject<string>();
  readonly raised = this.raisedSubject.asObservable();
  readonly lastSeq = signal<number | null>(null);

  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }

  changes(name: string): Signal<number> {
    return this.counterFor(name).asReadonly();
  }

  state(): 'connecting' | 'live' | 'degraded' {
    return 'live';
  }

  connect(): void {
    /* no-op */
  }

  emit(name: string): void {
    this.counterFor(name).update((n) => n + 1);
    this.raisedSubject.next(name);
  }
}

describe('shell navigation', () => {
  let events: FakeEventStream;
  let tapeStub: {
    load: ReturnType<typeof vi.fn>;
    visible: WritableSignal<boolean>;
    rows: WritableSignal<unknown[]>;
    asOf: WritableSignal<string | null>;
  };

  beforeEach(() => {
    events = new FakeEventStream();
    tapeStub = {
      load: vi.fn(),
      visible: signal(false),
      rows: signal([]),
      asOf: signal(null),
    };
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
        { provide: TapeStore, useValue: tapeStub },
      ],
    });
  });

  it('places both lanes between the topbar and the workspace', () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    const main = fixture.nativeElement.querySelector('.main') as HTMLElement;
    const order = Array.from(main.children).map((el) => el.tagName.toLowerCase());
    expect(order).toEqual(['header', 'sb-market-lane', 'sb-names-lane', 'main']);
  });

  it('loads the tape once on construction', () => {
    // This only proves the constructor's one-time `this.tape.load()` --
    // NOT that `Shell` reacts to a `scan` event, which it does not do and
    // does not need to: `TapeStore` owns that refetch itself
    // (`withHooks.onInit` in `tape.store.ts`), independent of whether the
    // shell exists. That behaviour -- a SECOND load caused by nothing but a
    // `scan` event, with no explicit `load()` call in the test -- is
    // regression-tested in `tape.store.spec.ts`, where the effect actually
    // lives. Asserting an `events.emit('scan')` here would be tautological:
    // `tapeStub.load` is already satisfied by construction before any emit.
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    expect(tapeStub.load).toHaveBeenCalledTimes(1);
  });

  it('shows an accessible, non-interactive overlay inside the pending workspace', () => {
    const routeLoading = { visible: signal(false), label: signal('Loading Trades') };
    TestBed.overrideProvider(RouteLoadingService, { useValue: routeLoading });
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    routeLoading.visible.set(true);
    f.detectChanges();
    const workspace = (f.nativeElement as HTMLElement).querySelector('.workspace')!;
    expect(workspace.classList.contains('route-pending')).toBe(true);
    expect(workspace.querySelector('[role="status"]')?.textContent).toContain('Loading Trades');
    expect(workspace.querySelector('.route-loading-overlay')).not.toBeNull();
  });
  it('groups the eight workspaces into three named groups', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const labels = [...el.querySelectorAll('.nav-group-label')].map((n) => n.textContent?.trim());
    expect(labels).toEqual(['MONITOR', 'REVIEW', 'SYSTEM']);
    expect(el.querySelectorAll('.nav a').length).toBe(8);
  });

  it('keeps each group a real list so the grouping reaches assistive tech', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const groups = (f.nativeElement as HTMLElement).querySelectorAll('ul[aria-labelledby]');
    expect(groups.length).toBe(3);
  });
});