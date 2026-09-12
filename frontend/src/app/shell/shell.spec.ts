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
import { RouteTitleService } from '../routing/route-title.service';
import { TapeStore } from '../stores/tape.store';
import { CLOCK } from '../ui/clock';
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

  it('carries both lanes inside the top bar row, not beneath it', () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;

    const main = el.querySelector('.main') as HTMLElement;
    expect(Array.from(main.children).map((c) => c.tagName.toLowerCase()))
      .toEqual(['header', 'main']);

    const header = el.querySelector('header.topbar') as HTMLElement;
    expect(header.querySelector('sb-market-lane')).not.toBeNull();
    expect(header.querySelector('sb-names-lane')).not.toBeNull();
  });

  it('shows the date and time from the ambient clock', () => {
    // A fixed instant, so the assertion is not a function of when the suite runs.
    const fixed = new Date('2026-09-11T16:58:00').getTime();
    TestBed.overrideProvider(CLOCK, { useValue: signal(fixed) });
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const text = (f.nativeElement as HTMLElement).querySelector('.clock')?.textContent ?? '';
    expect(text).toContain('Sep 11, 2026');
    expect(text).toContain('16:58');
  });

  it('renders the killswitch as a full-width strip below the bar, only when engaged', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('.killswitch-strip')).toBeNull();

    // killswitchOn is a protected signal set from the risk endpoint; drive it
    // the way the component does rather than reaching into the instance.
    (f.componentInstance as unknown as { killswitchOn: WritableSignal<boolean> })
      .killswitchOn.set(true);
    f.detectChanges();

    const strip = el.querySelector('.killswitch-strip')!;
    expect(strip.getAttribute('role')).toBe('alert');
    expect(strip.textContent).toContain('KILLSWITCH ENGAGED');
    expect(strip.parentElement?.classList.contains('main')).toBe(true);
    expect(strip.previousElementSibling?.tagName.toLowerCase()).toBe('header');
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
  it('groups the ten workspaces into three named groups', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const labels = [...el.querySelectorAll('.nav-group-label')].map((n) => n.textContent?.trim());
    expect(labels).toEqual(['MONITOR', 'REVIEW', 'SYSTEM']);
    expect(el.querySelectorAll('.nav a').length).toBe(10);
  });

  it('keeps each group a real list so the grouping reaches assistive tech', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const groups = (f.nativeElement as HTMLElement).querySelectorAll('ul[aria-labelledby]');
    expect(groups.length).toBe(3);
  });

  it('cycles the text-size control in the profile menu through 90/100/110/125 and wraps back to 90', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    // Scoped to sb-profile-menu -- the sidebar mark has its own `.avatar` image.
    el.querySelector<HTMLButtonElement>('sb-profile-menu .avatar')!.click();
    f.detectChanges();

    const button = el.querySelector<HTMLButtonElement>('.zoom')!;
    expect(button.textContent?.trim()).toBe('Aa 100%');

    button.click();
    f.detectChanges();
    expect(button.textContent?.trim()).toBe('Aa 110%');

    button.click();
    f.detectChanges();
    expect(button.textContent?.trim()).toBe('Aa 125%');

    // Wraps past the last choice back to the first, rather than sticking.
    button.click();
    f.detectChanges();
    expect(button.textContent?.trim()).toBe('Aa 90%');
  });

  it('renders the route title and subtitle in the top bar', () => {
    const titles = TestBed.inject(RouteTitleService);
    titles.set('Dashboard', "What's happening right now");
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('.topbar .page-title')?.textContent?.trim()).toBe('Dashboard');
    expect(el.querySelector('.topbar .page-subtitle')?.textContent?.trim())
      .toBe("What's happening right now");
  });

  it('renders no subtitle element at all when the route has none', () => {
    TestBed.inject(RouteTitleService).set('Bare', null);
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('.page-subtitle')).toBeNull();
  });

  it('marks the active entry with an accent rail rather than colour alone', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const link = (f.nativeElement as HTMLElement).querySelector('.nav a')!;
    link.classList.add('active');
    f.detectChanges();
    // The rule must exist in the component stylesheet; colour alone fails
    // contrast guidance for state, which is why this asserts a border.
    const styles = [...document.styleSheets]
      .flatMap((sheet) => { try { return [...sheet.cssRules]; } catch { return []; } })
      .map((rule) => rule.cssText);
    // Not a single `.includes('.nav a.active')` -- Angular's emulated
    // encapsulation inserts an `[_ngcontent-*]` attribute selector between
    // `.nav` and `a.active`, so that exact substring never appears in the
    // compiled stylesheet even when the rule is present.
    expect(styles.some((text) =>
      text.includes('.nav') && text.includes('a.active') && text.includes('border-left')))
      .toBe(true);
  });

  it('keeps the version block pinned to the foot of the rail', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const foot = (f.nativeElement as HTMLElement).querySelector('.sidebar-foot');
    expect(foot).not.toBeNull();
    expect(foot?.parentElement?.classList.contains('sidebar')).toBe(true);
  });

  it('drops the subtitle and the clock before it lets the bar overflow', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const rules = [...document.styleSheets]
      .flatMap((sheet) => { try { return [...sheet.cssRules]; } catch { return []; } })
      .map((rule) => rule.cssText)
      .join('\n');
    // Both must be hidden under a max-width query -- the order in the spec is
    // subtitle first, then clock, so the subtitle's breakpoint is the wider one.
    expect(rules).toMatch(/max-width:\s*900px[\s\S]*\.page-subtitle[\s\S]*display:\s*none/);
    expect(rules).toMatch(/max-width:\s*720px[\s\S]*\.clock[\s\S]*display:\s*none/);
  });

  it('renders the brand mark beside the wordmark', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('.brand sb-icon')).not.toBeNull();
    expect(el.querySelector('.brand')!.textContent).toContain('Bomeo');
  });

  it('renders the two-tone wordmark as two spans, not one coloured string', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelectorAll('.brand .word span').length).toBe(2);
  });

  it('renders the rail tagline', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('.rail-tagline')!.textContent)
      .toContain('Trade smarter. Build further.');
  });

  it('keeps the mark and drops the words when the rail is collapsed', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    // Drives the real toggle rather than reaching into the instance --
    // the same mechanism a user actually has.
    el.querySelector<HTMLButtonElement>('.collapse')!.click();
    f.detectChanges();
    expect(el.querySelector('.brand sb-icon')).not.toBeNull();
    expect(el.querySelector('.brand .word')).toBeNull();
  });
});
