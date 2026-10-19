import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import {
  Signal,
  WritableSignal,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import { RouteLoadingService } from '../routing/route-loading.service';
import { RouteTitleService } from '../routing/route-title.service';
import { PreferencesStore } from '../stores/preferences.store';
import { TapeStore } from '../stores/tape.store';
import { CLOCK } from '../ui/clock';
import { provideMotion } from '../ui/motion/motion.service';
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

  it('carries the tape inside the top bar row, not beneath it', () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;

    const main = el.querySelector('.main') as HTMLElement;
    expect(Array.from(main.children).map((c) => c.tagName.toLowerCase()))
      .toEqual(['header', 'main']);

    const header = el.querySelector('header.topbar') as HTMLElement;
    expect(header.querySelector('sb-tape')).not.toBeNull();
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

  it('overlays the scan progress strip on the workspace rather than reflowing it', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;

    const strip = el.querySelector('sb-scan-progress');
    expect(strip).not.toBeNull();

    // Deliberately NOT a sibling of the header the way `.killswitch-strip`
    // is. That one is in the flow because it must never be missed; this one
    // appears every SCAN_INTERVAL_MINUTES all session, and in the flow it
    // would shunt the page down and back several times an hour.
    expect(strip!.parentElement?.classList.contains('workspace')).toBe(true);
    expect(strip!.previousElementSibling).toBeNull();
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

  it('marks the active entry with a rail plus tint and weight, not colour alone', () => {
    // v168 §3 #6: the rail is one sliding sb-nav-indicator in the sidebar,
    // no longer a per-link border; the active link keeps the tint and the
    // weight, so the state still has three cues.
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelectorAll('.sidebar > sb-nav-indicator').length).toBe(1);
    const styles = [...document.styleSheets]
      .flatMap((sheet) => { try { return [...sheet.cssRules]; } catch { return []; } })
      .map((rule) => rule.cssText);
    // Not a single `.includes('.nav a.active')` -- emulated encapsulation
    // inserts an `[_ngcontent-*]` attribute between `.nav` and `a.active`.
    const active = styles.filter((text) => text.includes('.nav') && text.includes('a.active'));
    expect(active.some((text) => text.includes('background') && text.includes('font-weight'))).toBe(true);
    expect(active.some((text) => text.includes('border-left-color'))).toBe(false);
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
    // v95 A2 retriggered these onto the declared breakpoints: the subtitle
    // goes below md (1023), the clock below sm (639).
    expect(rules).toMatch(/max-width:\s*1023px[\s\S]*\.page-subtitle[\s\S]*display:\s*none/);
    expect(rules).toMatch(/max-width:\s*639px[\s\S]*\.clock[\s\S]*display:\s*none/);
  });

  it('renders the brand mark beside the wordmark', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('.brand sb-icon')).not.toBeNull();
    expect(el.querySelector('.brand')!.textContent).toContain('Bomeo');
  });

  it('the brand mark links back to the Dashboard', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const brand = el.querySelector('.brand') as HTMLAnchorElement;
    expect(brand.tagName).toBe('A');
    // RouterLink resolves and sets a real `href`, independent of whether the
    // test's route table (provideRouter([])) actually registers the path.
    expect(brand.getAttribute('href')).toBe('/dashboard');
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

describe('shell.css breakpoints', () => {
  const css = readFileSync(join(process.cwd(), 'src/app/shell/shell.css'), 'utf8');

  it('uses only declared breakpoint values in width queries', () => {
    // A media query at 900px or 720px puts the stylesheet and
    // ViewportService on different scales -- see breakpoints.ts.
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...css.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)]
      .map((m) => m[1]);

    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});

describe('shell motion preference (v168 §1)', () => {
  const html = document.documentElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        { provide: TapeStore, useValue: { load: vi.fn(), visible: signal(false), rows: signal([]), asOf: signal(null) } },
        provideMotion('live'),
      ],
    });
  });

  afterEach(() => {
    delete html.dataset['motion'];
  });

  function flushPreferences(preferences: Record<string, unknown>): void {
    TestBed.inject(HttpTestingController)
      .expectOne((request) => request.method === 'GET' && request.url.endsWith('/system/preferences'))
      .flush({ preferences });
  }

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('starts the cold load as pending in index.html, before any script runs', () => {
    const source = readFileSync(join(process.cwd(), 'src/index.html'), 'utf8');
    expect(source).toMatch(/<html lang="en" data-motion="pending">/);
  });

  it('keeps <html data-motion> pending until preferences load', async () => {
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    expect(html.dataset['motion']).toBe('pending');
  });

  it('defaults to on once preferences load without a stored mode', async () => {
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    flushPreferences({});
    await settle(fixture);
    expect(html.dataset['motion']).toBe('on');
  });

  it('restores a stored mode onto <html>', async () => {
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    flushPreferences({ 'shell.motion': 'reduced' });
    await settle(fixture);
    expect(html.dataset['motion']).toBe('reduced');
  });

  it('falls back to on for an unknown stored value', async () => {
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    flushPreferences({ 'shell.motion': 'sparkly' });
    await settle(fixture);
    expect(html.dataset['motion']).toBe('on');
  });

  it('writes shell.motion and data-motion when the control is used', async () => {
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    flushPreferences({});
    await settle(fixture);
    const el = fixture.nativeElement as HTMLElement;
    el.querySelector<HTMLButtonElement>('sb-profile-menu .avatar')!.click();
    fixture.detectChanges();
    const off = Array.from(el.querySelectorAll<HTMLButtonElement>('sb-profile-menu .motion-control .segment'))
      .find((button) => button.textContent!.trim() === 'Off')!;
    off.click();
    await settle(fixture);
    expect(html.dataset['motion']).toBe('off');
    expect(TestBed.inject(PreferencesStore).values()['shell.motion']).toBe('off');
  });
});
