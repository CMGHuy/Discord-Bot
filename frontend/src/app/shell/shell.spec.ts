import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import {
  Component,
  Signal,
  WritableSignal,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, Routes, provideRouter } from '@angular/router';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import { RouteLoadingService } from '../routing/route-loading.service';
import { PreferencesStore } from '../stores/preferences.store';
import { LiveValuesStore } from '../stores/live-values.store';
import { TapeStore } from '../stores/tape.store';
import { ViewportService } from '../ui/breakpoints';
import { CLOCK } from '../ui/clock';
import { DENSITY_STORAGE } from '../ui/density.service';
import { provideMotion } from '../ui/motion/motion.service';
import { NAV_ENTRIES } from './nav';
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

/** The shell mounts the stalled-refresher banner, which reads this store; the
 *  fake keeps the real one (and its /market/updates fetch) out of these specs. */
const fakeLiveValues = () => ({ stalled: signal(false), status: signal(null) });

@Component({ template: '' })
class Blank {}

/** The providers every v195 shell describe uses: the same fakes as the
 *  `shell navigation` block, with a route table the breadcrumb can read. */
function shellProviders(routes: Routes = []) {
  return [
    provideZonelessChangeDetection(),
    provideRouter(routes),
    provideHttpClient(),
    provideHttpClientTesting(),
    { provide: EventStream, useValue: new FakeEventStream() },
    { provide: TapeStore, useValue: { load: vi.fn(), visible: signal(false), rows: signal([]), asOf: signal(null) } },
    { provide: LiveValuesStore, useValue: fakeLiveValues() },
  ];
}

const readSource = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');

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
        { provide: LiveValuesStore, useValue: fakeLiveValues() },
      ],
    });
  });

  it('runs the tape as a strip under the top bar, not inside it (v195 Phase 3)', () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;

    const main = el.querySelector('.main') as HTMLElement;
    expect(Array.from(main.children).map((c) => c.tagName.toLowerCase()))
      .toEqual(['header', 'div', 'sb-refresher-banner', 'div']);
    // v203 Moved: the workspace now sits in .workspace-row beside the Live column.
    expect(main.children[3].classList).toContain('workspace-row');
    expect(main.querySelector(':scope > .workspace-row > main.workspace')).not.toBeNull();
    expect(main.children[1].classList).toContain('tape-strip');
    expect(main.querySelector(':scope > .tape-strip > sb-tape')).not.toBeNull();
    expect(el.querySelector('header.topbar sb-tape')).toBeNull();
  });

  it('keeps no clock in the bar: times live in the dock and the strip', () => {
    // v203 Retired 'shows the date and time from the ambient clock' (spec v202 D5).
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('header.topbar .clock')).toBeNull();
    expect(readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '')).not.toMatch(/\.clock\b/);
    const code = readSource('src/app/shell/shell.ts').replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
    expect(code).not.toMatch(/readonly now\b/);
  });

  it('renders the killswitch as a full-width strip below the bar, only when engaged', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('.killswitch-strip')).toBeNull();

    TestBed.inject(HttpTestingController).expectOne('/api/v1/risk/killswitch').flush({
      killswitch: { on: true, reason: null, at: null,
        availability: { state: 'ok', checked_at: '2026-10-28T00:00:00+00:00', reason: null } },
    });
    f.detectChanges();

    const strip = el.querySelector('.killswitch-strip')!;
    expect(strip.getAttribute('role')).toBe('alert');
    expect(strip.textContent).toContain('KILLSWITCH ENGAGED');
    expect(strip.parentElement?.classList.contains('main')).toBe(true);
    expect(strip.previousElementSibling?.classList.contains('tape-strip')).toBe(true);
  });

  it('shows unknown shell state after a fresh failed read, with a stale observation', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    const ok = { state: 'ok', checked_at: '2026-10-28T00:00:00+00:00', reason: null };
    http.expectOne('/api/v1/risk/killswitch').flush({ killswitch: {
      on: false, reason: null, at: null, availability: ok,
    } });
    f.detectChanges();
    expect(f.nativeElement.querySelector('.killswitch-strip')).toBeNull();
    (f.componentInstance as unknown as { refreshKillswitch(): void }).refreshKillswitch();
    http.expectOne('/api/v1/risk/killswitch').flush({}, { status: 503, statusText: 'unavailable' });
    f.detectChanges();
    const strip = f.nativeElement.querySelector('.killswitch-strip') as HTMLElement;
    expect(strip.getAttribute('role')).toBe('status');
    expect(strip.textContent).toContain('STATE UNAVAILABLE');
    expect(strip.textContent).toContain('Last observed clear');
    expect(strip.textContent).toContain('stale');
    http.expectNone('/api/v1/risk/killswitch');
  });

  it('hangs the scan progress from the top bar, out of the flow (v195 Phase 3)', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;

    const strip = el.querySelector('sb-scan-progress')!;
    expect(el.querySelectorAll('sb-scan-progress')).toHaveLength(1);
    // In the sticky bar, so it shows on every route; the bar's last child,
    // so it paints over its own siblings' edge rather than between them.
    expect(strip.parentElement?.matches('header.topbar')).toBe(true);
    expect(strip.nextElementSibling).toBeNull();
    expect(el.querySelector('.workspace sb-scan-progress')).toBeNull();
    // Absolute (its own :host), re-anchored under the bar's bottom edge: it
    // never takes layout, so a scan every few minutes never shunts the page.
    const css = readSource('src/app/shell/shell.css');
    expect(css.match(/^\.topbar > sb-scan-progress \{[^}]*\}/m)?.[0]).toContain('inset: 100% 0 auto 0;');
  });

  /* v195 §1.2: depth comes from surface steps and borders only. The ambient
   * glow layer (v168 §3 #10) is gone, and the routed host is a plain div:
   * the route-entrance directive and its .sb-entering class are retired. */
  it('paints no ambient layer and routes into a plain host (v195 §1.2)', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const shell = (f.nativeElement as HTMLElement).querySelector('.shell') as HTMLElement;

    expect(shell.querySelectorAll('.ambient')).toHaveLength(0);
    const host = shell.querySelector('.workspace-content') as HTMLElement;
    expect(host).not.toBeNull();
    expect(host.classList.contains('sb-entering')).toBe(false);
    expect(host.hasAttribute('sbrouteentrance')).toBe(false);
  });

  it('no longer ships the route-entrance directive (v195 §1.2)', () => {
    const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
    expect(read('src/app/shell/shell.html')).not.toContain('sbRouteEntrance');
    expect(read('src/app/shell/shell.ts')).not.toContain('RouteEntrance');
    expect(existsSync(join(process.cwd(), 'src/app/ui/motion/route-entrance.ts'))).toBe(false);
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
  it('keeps the work destinations and System as two named lists', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const lists = (f.nativeElement as HTMLElement).querySelectorAll('nav.rail ul.nav[aria-label]');
    expect([...lists].map((ul) => ul.getAttribute('aria-label'))).toEqual(['Destinations', 'System']);
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

  it('marks the active entry with the pill and a brighter glyph and label', () => {
    const css = readSource('src/app/shell/shell.css');
    expect(css.match(/^\.rail-link\.active \.rail-pill \{[^}]*\}/m)?.[0]).toContain('background: var(--accent-soft);');
    expect(css.match(/^\.rail-link\.active \{[^}]*\}/m)?.[0]).toContain('color: var(--text);');
    expect(css.match(/^\.rail-link \{[^}]*\}/m)?.[0]).toContain('color: var(--text-muted);');
    expect(css).not.toMatch(/sb-nav-indicator|border-left-color/);
  });

  it('sizes each entry 64x52, a 24px icon over a micro label', () => {
    const css = readSource('src/app/shell/shell.css');
    const link = css.match(/^\.rail-link \{[^}]*\}/m)?.[0] ?? '';
    expect(link).toContain('width: 64px;');
    expect(link).toContain('min-height: 52px;');
    expect(css).toMatch(/^\.rail-pill sb-icon svg \{[^}]*width: 24px;[^}]*height: 24px;/m);
    expect(css.match(/^\.rail-label \{[^}]*\}/m)?.[0]).toContain('font-size: var(--text-micro);');
  });

  it('keeps the ui and bot versions in a hint at the foot of the rail', async () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    await f.whenStable();
    const el = f.nativeElement as HTMLElement;
    // Nothing until the first /health answer: a version that reads 0.0.0
    // while it waits looks real.
    expect(el.querySelector('sb-hint.version')).toBeNull();
    const backend = TestBed.inject(HttpTestingController);
    for (const request of backend.match((r) => r.url.endsWith('/health'))) {
      request.flush({
        ok: true,
        versions: { ui: '1.36.1', bot: '2.15.3', last_updated: '2026-10-25T06:00:00Z' },
        market_active: true,
        currency: '€',
      });
    }
    f.detectChanges();
    await f.whenStable();
    const foot = el.querySelector('nav.rail > .rail-version')!;
    const hint = foot.querySelector('sb-hint.version')!;
    expect(hint.querySelector('[role=tooltip]')!.textContent!.trim())
      .toBe('ui 1.36.1 · bot 2.15.3 · updated 2026-10-25T06:00:00Z');
    expect(el.querySelector('.version-row')).toBeNull();
  });

  it('drops the tape on a phone before it lets the bar overflow', () => {
    const css = readSource('src/app/shell/shell.css');
    // v95 A2's declared breakpoint. The subtitle it used to drop at 1023px
    // has left the bar (v195: the breadcrumb leads, sb-page carries the title).
    expect(css).toMatch(/max-width:\s*639px[\s\S]*\.tape-strip[\s\S]*display:\s*none/);
    expect(css).not.toContain('.page-subtitle');
  });

  it('renders the brand as the mark alone, named for assistive tech and labelled on focus', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const brand = el.querySelector('nav.rail > a.rail-brand') as HTMLAnchorElement;
    expect(brand.querySelector('sb-icon')).not.toBeNull();
    expect(brand.textContent!.trim()).toBe('');
    expect(brand.getAttribute('aria-label')).toContain('Bomeo Capital');
    expect(brand.nextElementSibling!.tagName.toLowerCase()).toBe('sb-hint');
  });

  it('the brand mark links back to the Dashboard', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const brand = el.querySelector('a.rail-brand') as HTMLAnchorElement;
    expect(brand.tagName).toBe('A');
    // RouterLink resolves and sets a real `href`, independent of whether the
    // test's route table (provideRouter([])) actually registers the path.
    expect(brand.getAttribute('href')).toBe('/dashboard');
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
        { provide: LiveValuesStore, useValue: fakeLiveValues() },
    { provide: LiveValuesStore, useValue: fakeLiveValues() },
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

describe('live cues (v168 §3 #10)', () => {
  const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');

  /** The first `<selector> { ... }` rule, verbatim. */
  function ruleOf(css: string, selector: string): string {
    const at = css.indexOf(`${selector} {`);
    expect(at, selector).toBeGreaterThanOrEqual(0);
    return css.slice(at, css.indexOf('}', at) + 1);
  }

  /* v195 §1.2: the glow layer and the stacking context it needed are gone. */
  it('declares no ambient layer and no stacking context for one', () => {
    const css = read('src/app/shell/shell.css');
    const code = css.replace(/\/\*[\s\S]*?\*\//g, '');
    expect(ruleOf(css, '.shell')).not.toContain('isolation');
    expect(code).not.toMatch(/\.ambient\s*\{/);
    expect(code).not.toContain('--glow-ambient');
  });

  it('blinks a halo behind the avatar, green when the bot is live and red when offline', () => {
    const source = read('src/app/shell/profile-menu.ts');
    expect(source).toMatch(/\.halo\.up\s*\{[^}]*var\(--pos\)[^}]*animation:\s*sb-halo-blink/s);
    expect(source).toMatch(/\.halo\.down\s*\{[^}]*var\(--neg\)[^}]*animation:\s*sb-halo-blink/s);
    expect(source).toMatch(/\.halo\.resting\s*\{\s*animation:\s*none;\s*\}/s);
  });

  it('sweeps the scan strip with an accent gradient, same keyframe and timing', () => {
    const css = read('src/app/shell/scan-progress.css');
    expect(css).toMatch(/\.fill\.sweeping\s*\{[^}]*background:\s*linear-gradient\(90deg, transparent, var\(--accent\)\);/s);
    expect(css).toMatch(/\.fill\.sweeping\s*\{[^}]*animation:\s*sb-scan-sweep 1\.4s ease-in-out infinite;/s);
  });
});

describe('shell topbar centred on one axis (v179 layout audit)', () => {
  const css = readFileSync(join(process.cwd(), 'src/app/shell/shell.css'), 'utf8');
  const rule = (selector: string) => css.match(
    new RegExp(`^${selector.replaceAll('.', '\\.')} \\{[^}]*\\}`, 'm'),
  )?.[0] ?? '';

  it('centres the title block, tape, status cluster and avatar on the bar', () => {
    expect(rule('.topbar')).toMatch(/align-items:\s*center/);
  });

  it('gives the topbar and the rail mark the same height, so the two centres meet', () => {
    expect(rule('.topbar')).toContain('height: var(--topbar-h)');
    expect(rule('.rail-brand')).toContain('height: var(--topbar-h)');
    expect(rule('.topbar')).toContain('position: sticky;');
  });
});

describe('shell labelled rail (v202 §3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: shellProviders([
        { path: 'trades', component: Blank },
        { path: 'trades/calendar', component: Blank },
        { path: 'plans/:id', component: Blank },
        { path: 'insights/analytics', component: Blank },
        { path: 'system/versions', component: Blank },
      ]),
    });
  });

  async function mount() {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  const labelOf = (link: Element) => link.querySelector('.rail-label')!.textContent!.trim();

  it('draws six labelled destinations, five work entries then System at the foot (v202 §3)', async () => {
    const { el } = await mount();
    const rail = el.querySelector('nav.rail')!;
    expect(rail.getAttribute('aria-label')).toBe('Primary');
    expect(rail.firstElementChild!.matches('a.rail-brand')).toBe(true);
    const lists = [...rail.querySelectorAll(':scope > ul.nav')];
    expect(lists.map((ul) => ul.className)).toEqual(['nav rail-work', 'nav rail-foot']);
    const labels = (ul: Element) => [...ul.querySelectorAll(':scope > li > a.rail-link')].map(labelOf);
    expect(labels(lists[0])).toEqual(['Dashboard', 'Watchlist', 'Trades', 'Risk', 'Insights']);
    expect(labels(lists[1])).toEqual(['System']);
    expect(lists[1].nextElementSibling!.matches('.rail-version')).toBe(true);
    expect(rail.querySelector('.rail-divider, sb-nav-indicator, .nav-group-label')).toBeNull();
  });

  it('draws each entry as its icon over its visible label, with no hint and no title', async () => {
    const { el } = await mount();
    const links = [...el.querySelectorAll<HTMLAnchorElement>('nav.rail a.rail-link')];
    expect(links.map((a) => a.getAttribute('href'))).toEqual(NAV_ENTRIES.map((entry) => entry.path));
    for (const link of links) {
      const label = labelOf(link);
      // The visible label is the accessible name; the icon is aria-hidden.
      expect(link.hasAttribute('aria-label'), label).toBe(false);
      expect(link.hasAttribute('title'), label).toBe(false);
      expect(link.querySelector(':scope > .rail-pill > sb-icon')!.getAttribute('title'), label).toBe('');
      expect(link.textContent!.trim(), label).toBe(label);
      expect(link.parentElement!.querySelector('sb-hint'), label).toBeNull();
    }
    expect(el.querySelectorAll('nav.rail ul.nav button')).toHaveLength(0);
  });

  it.each([
    ['/trades', 'Trades'],
    ['/trades/calendar', 'Trades'],
    ['/plans/7', 'Trades'],
    ['/insights/analytics?tab=tuning#x', 'Insights'],
    ['/system/versions', 'System'],
  ])('lights exactly one entry, aria-current, on %s', async (url, label) => {
    const { fixture, el } = await mount();
    await TestBed.inject(Router).navigateByUrl(url);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const active = [...el.querySelectorAll('a.rail-link.active')];
    expect(active.map(labelOf)).toEqual([label]);
    expect(active[0].getAttribute('aria-current')).toBe('page');
    expect(el.querySelectorAll('nav.rail [aria-current]')).toHaveLength(1);
  });

  it('lights nothing off the nav model', async () => {
    // The test bed starts at '', which navEntryFor resolves to null.
    const { el } = await mount();
    expect(el.querySelectorAll('a.rail-link.active, nav.rail [aria-current]')).toHaveLength(0);
  });

  it('has no expanded, collapsed or overlay state, and ignores a stored shell.sidebar', async () => {
    const { fixture, el } = await mount();
    const backend = TestBed.inject(HttpTestingController);
    for (const request of backend.match((r) => r.url.endsWith('/system/preferences'))) {
      request.flush({ preferences: { 'shell.sidebar': 'expanded' } });
    }
    fixture.detectChanges();
    await fixture.whenStable();
    expect(el.querySelector('.shell')!.className).toBe('shell');
    for (const gone of ['.collapse', '.menu-button', '.scrim', '.sidebar', '.rail-tagline', 'nav.rail .word']) {
      expect(el.querySelector(gone), gone).toBeNull();
    }
    // Read nowhere and written nowhere: no preference write left the page.
    expect(backend.match((r) => r.method !== 'GET')).toEqual([]);
    const code = readSource('src/app/shell/shell.ts').replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
    for (const word of ['shell.sidebar', 'toggleSidebar', 'userCollapsed', 'overlayOpen', 'railed', 'applyStoredSidebar']) {
      expect(code, word).not.toContain(word);
    }
  });
});

describe('shell top bar (v195 Phase 3, correction 9)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: shellProviders([{ path: 'trades', component: Blank }]) });
  });

  it('leads the bar with the wordmark, the divider and the breadcrumb, and renders no heading of its own', async () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await TestBed.inject(Router).navigateByUrl('/trades');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const bar = el.querySelector('header.topbar')!;
    // v203 Moved: the wordmark leads the bar; the breadcrumb follows the divider.
    ['a.brand', 'span.topbar-divider', 'sb-breadcrumb.topbar-lead'].forEach((selector, index) =>
      expect(bar.children[index].matches(selector), selector).toBe(true));
    const crumbs = [...bar.querySelectorAll('nav[aria-label="Breadcrumb"] li')]
      .map((li) => li.textContent!.replace('/', '').trim());
    expect(crumbs).toEqual(['Trades', 'Book']);
    expect(el.querySelectorAll('h1')).toHaveLength(0);
    expect(el.querySelector('.page-title, .page-subtitle')).toBeNull();
  });

  it('sizes the rail and the bar from two shell tokens, with no animated width', () => {
    const css = readSource('src/app/shell/shell.css');
    const shell = css.match(/^\.shell \{[^}]*\}/m)?.[0] ?? '';
    expect(shell).toContain('--rail-width: 80px;');
    expect(shell).toContain('--topbar-h: 40px;');
    expect(shell).toContain('grid-template-columns: var(--rail-width) 1fr;');
    expect(shell).not.toContain('transition');
    // The touch rules win (spec §1.4): the bar grows to hold 44px controls.
    expect(css).toMatch(/@media \(pointer: coarse\), \(max-width: 1023px\)\s*\{\s*\.shell \{ --topbar-h: 48px; \}/);
  });
});

describe('shell top-bar cluster (v195 Phase 3)', () => {
  const NOW = Date.parse('2026-10-27T12:00:00Z');
  const html = document.documentElement;
  let stored: Map<string, string>;

  beforeEach(() => {
    stored = new Map();
    TestBed.configureTestingModule({
      providers: [
        ...shellProviders(),
        { provide: DENSITY_STORAGE, useValue: { get: (key: string) => stored.get(key) ?? null, set: (key: string, value: string) => stored.set(key, value) } },
      ],
    });
    TestBed.overrideProvider(CLOCK, { useValue: signal(NOW) });
  });

  afterEach(() => {
    delete html.dataset['density'];
  });

  async function mount() {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await fixture.whenStable();
    return { fixture, el: fixture.nativeElement as HTMLElement, backend: TestBed.inject(HttpTestingController) };
  }

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  const scanStatus = (overrides: Record<string, unknown>) => ({
    pending: false, triggered_at: null, paused: false, paused_at: null, running: false,
    bot_alive: true, bot_last_seen: '2026-10-27T11:57:00Z', bot_healthy: true,
    bot_last_success: '2026-10-27T11:48:00Z', bot_consecutive_failures: 0,
    bot_session_active: true, bot_scan_paused: false, progress: null, ...overrides,
  });

  it('keeps only the alarm and killswitch chips in the cluster, hidden at no width', async () => {
    // v203 Retired 'puts the killswitch and freshness chips in the cluster' and
    // 'ages the freshness chip …' (spec v202 D5: freshness, connection and the clock
    // live in the dock and strip; V203-4's botRows pins the freshness words).
    const { el } = await mount();
    const cluster = el.querySelector('header.topbar > .status-cluster')!;
    expect([...cluster.children].map((c) => c.tagName.toLowerCase())).toEqual(['sb-alarm-chip', 'sb-killswitch-chip']);
    expect(el.querySelector('header.topbar sb-freshness-chip, header.topbar sb-connection-status')).toBeNull();
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    expect(css).not.toMatch(/(sb-killswitch-chip|sb-alarm-chip|\.status-cluster)[^{}]*\{[^}]*display:\s*none/);
  });

  const alarmText = (el: HTMLElement) =>
    el.querySelector('header.topbar > .status-cluster > sb-alarm-chip button.alarm-chip .text')?.textContent?.trim() ?? null;

  it('raises no alarm before /health answers, nor while all is well', async () => {
    const { fixture, el, backend } = await mount();
    expect(alarmText(el)).toBeNull();                  // botAlive still null: a cold load is no alarm
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) request.flush(scanStatus({}));
    await settle(fixture);
    expect(alarmText(el)).toBeNull();                  // last success 12 min ago, under the 900 s rule
  });

  it.each([
    ['the bot is not alive', { bot_alive: false }, 'Bot down'],
    ['the last success is older than 900 s', { bot_last_success: '2026-10-27T11:40:00Z' }, 'Data stale 20 min'],
    ['no tick ever succeeded', { bot_last_success: null }, 'Data stale'],
  ])('raises the alarm chip when %s', async (_, overrides, text) => {
    const { fixture, el, backend } = await mount();
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) request.flush(scanStatus(overrides));
    await settle(fixture);
    expect(alarmText(el)).toBe(text);
  });

  it('raises Disconnected when the event stream degrades', async () => {
    class DegradedStream extends FakeEventStream {
      override state(): 'degraded' {
        return 'degraded';
      }
    }
    TestBed.overrideProvider(EventStream, { useValue: new DegradedStream() });
    const { el } = await mount();
    expect(alarmText(el)).toBe('Disconnected');
  });

  it('shows no killswitch state until the risk endpoint answers, then the answer', async () => {
    const { fixture, el, backend } = await mount();
    const chip = () => el.querySelector('sb-killswitch-chip a');
    expect(chip()).toBeNull();
    for (const request of backend.match((r) => r.url.endsWith('/risk/killswitch'))) {
      request.flush({ killswitch: { on: true } });
    }
    await settle(fixture);
    expect(chip()!.textContent!.trim()).toBe('Halted');
    expect(el.querySelector('.killswitch-strip')).not.toBeNull();
  });

  it('writes ui.density and data-density from the profile menu', async () => {
    const { fixture, el } = await mount();
    expect(html.dataset['density']).toBe('dense');
    el.querySelector<HTMLButtonElement>('sb-profile-menu .avatar')!.click();
    fixture.detectChanges();
    const comfortable = Array.from(el.querySelectorAll<HTMLButtonElement>('sb-profile-menu .density-control .segment'))
      .find((button) => button.textContent!.trim() === 'Comfortable')!;
    comfortable.click();
    await settle(fixture);
    expect(html.dataset['density']).toBe('comfortable');
    expect(stored.get('ui.density')).toBe('comfortable');
    const pressed = Array.from(el.querySelectorAll<HTMLButtonElement>('sb-profile-menu .density-control .segment'))
      .find((button) => button.getAttribute('aria-pressed') === 'true')!;
    expect(pressed.textContent!.trim()).toBe('Comfortable');
  });
});

describe('shell on a phone (v195 Phase 3)', () => {
  let phone: WritableSignal<boolean>;

  beforeEach(() => {
    phone = signal(true);
    TestBed.configureTestingModule({ providers: shellProviders([{ path: 'insights/research', component: Blank }]) });
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: phone, isNarrow: signal(true), viewport: signal('xs') },
    });
  });

  async function mount() {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  const sheet = (el: HTMLElement) => el.querySelector('sb-more-sheet [role=dialog]');
  const moreTab = (el: HTMLElement) => el.querySelector<HTMLButtonElement>('sb-phone-tab-bar button.more')!;

  it('swaps the rail for the bottom tab bar, with the More sheet closed', async () => {
    const { el } = await mount();
    expect(el.querySelector('sb-phone-tab-bar')).not.toBeNull();
    expect(sheet(el)).toBeNull();
    const css = readSource('src/app/shell/shell.css');
    const phoneBlock = css.slice(css.indexOf('@media (max-width: 639px)'));
    expect(phoneBlock).toMatch(/\.rail \{ display: none; \}/);
    expect(phoneBlock).toMatch(/\.shell \{ grid-template-columns: 1fr; \}/);
    expect(phoneBlock).toContain('.main { padding-bottom: calc(56px + env(safe-area-inset-bottom)); }');
  });

  it('leads the phone bar with the diamond and the wordmark, then the cluster, the search icon and the avatar', async () => {
    // v203 Retired 'collapses the bar to the title, the two chips, …' (spec v202 §3).
    const { el } = await mount();
    const bar = el.querySelector('header.topbar')!;
    const order = ['a.brand', 'div.status-cluster', 'button.search-trigger', 'sb-profile-menu', 'sb-scan-progress'];
    expect(bar.children).toHaveLength(order.length);
    order.forEach((selector, index) => expect(bar.children[index].matches(selector), selector).toBe(true));
    const brand = bar.querySelector('a.brand')!;
    expect(brand.firstElementChild!.matches('sb-icon')).toBe(true);
    expect(brand.querySelectorAll('.word span')).toHaveLength(2);
    expect(bar.querySelector('sb-breadcrumb, span.topbar-divider, button.palette-trigger')).toBeNull();
    const search = bar.querySelector('button.search-trigger')!;
    expect(search.getAttribute('aria-label')).toBe('Search or jump to a page');
    // The magnifier: sb-icon's default label for 'search' (V195-14).
    expect(search.querySelector('sb-icon')!.getAttribute('title')).toBe('Search');
    expect(bar.querySelector('.status-cluster sb-killswitch-chip')).not.toBeNull();
    expect(bar.querySelector('.status-cluster sb-alarm-chip')).not.toBeNull();
  });

  it('opens the More sheet from the More tab, and the tab closes it again', async () => {
    const { fixture, el } = await mount();
    moreTab(el).click();
    await settle(fixture);
    expect(sheet(el)).not.toBeNull();
    expect(moreTab(el).getAttribute('aria-expanded')).toBe('true');
    moreTab(el).click();
    await settle(fixture);
    expect(sheet(el)).toBeNull();
  });

  it('closes the More sheet on Escape and when a page is chosen', async () => {
    const { fixture, el } = await mount();
    moreTab(el).click();
    await settle(fixture);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(sheet(el)).toBeNull();
    moreTab(el).click();
    await settle(fixture);
    el.querySelector<HTMLAnchorElement>('sb-more-sheet a.page[href="/insights/research"]')!.click();
    await settle(fixture);
    expect(sheet(el)).toBeNull();
  });

  it('closes the More sheet when its search field is used', async () => {
    const { fixture, el } = await mount();
    moreTab(el).click();
    await settle(fixture);
    el.querySelector<HTMLButtonElement>('sb-more-sheet button.search')!.click();
    await settle(fixture);
    expect(sheet(el)).toBeNull();
  });

  it('forgets an open sheet when the window grows past phone width', async () => {
    const { fixture, el } = await mount();
    moreTab(el).click();
    await settle(fixture);
    phone.set(false);
    await settle(fixture);
    expect(el.querySelector('sb-phone-tab-bar')).toBeNull();
    phone.set(true);
    await settle(fixture);
    expect(sheet(el)).toBeNull();
  });
});

describe('shell above phone width (v195 Phase 3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: shellProviders() });
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: signal(false), isNarrow: signal(false), viewport: signal('md') },
    });
  });

  it('renders no tab bar, no More sheet and no phone search icon', () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-phone-tab-bar')).toBeNull();
    expect(el.querySelector('sb-more-sheet')).toBeNull();
    expect(el.querySelector('button.search-trigger')).toBeNull();
    expect(el.querySelector('nav.rail')).not.toBeNull();
  });
});

describe('shell command palette (v195 §3.1)', () => {
  let phone: WritableSignal<boolean>;

  beforeEach(() => {
    phone = signal(false);
    TestBed.configureTestingModule({ providers: shellProviders() });
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: phone, isNarrow: signal(false), viewport: signal('md') },
    });
  });

  afterEach(() => {
    document.querySelectorAll('.palette-probe').forEach((node) => node.remove());
  });

  async function mount() {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  const palette = (el: HTMLElement) => el.querySelector('sb-command-palette [role=dialog]');
  const keydown = (init: KeyboardEventInit, target: EventTarget = document.body) =>
    target.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init }));
  const escape = () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  const probe = <T extends HTMLElement>(tag: string): T => {
    const node = document.createElement(tag) as T;
    node.classList.add('palette-probe');
    document.body.appendChild(node);
    return node;
  };

  it('puts the trigger after the cluster, before the avatar, and opens the palette from it', async () => {
    const { fixture, el } = await mount();
    const trigger = el.querySelector<HTMLButtonElement>('header.topbar > button.palette-trigger')!;
    // v203 Moved (spec v202 §3): the Ctrl K trigger follows the cluster.
    expect(trigger.previousElementSibling!.matches('div.status-cluster')).toBe(true);
    expect(trigger.nextElementSibling!.matches('sb-profile-menu')).toBe(true);
    expect(trigger.textContent).toContain('Search or jump…');
    expect(trigger.getAttribute('aria-keyshortcuts')).toBe('Control+K Meta+K /');
    expect(trigger.querySelector('kbd.shortcut')!.getAttribute('aria-hidden')).toBe('true');
    expect(palette(el)).toBeNull();

    trigger.focus();
    trigger.click();
    await settle(fixture);
    expect(palette(el)).not.toBeNull();
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    // Closing hands focus back to the trigger (FocusTrap's restore).
    escape();
    await settle(fixture);
    expect(palette(el)).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('opens on Ctrl+K and on ⌘K', async () => {
    const { fixture, el } = await mount();
    expect(keydown({ key: 'k', ctrlKey: true })).toBe(false); // default prevented
    await settle(fixture);
    expect(palette(el)).not.toBeNull();
    escape();
    await settle(fixture);
    keydown({ key: 'k', metaKey: true });
    await settle(fixture);
    expect(palette(el)).not.toBeNull();
  });

  it('opens on / outside a text field, and leaves / to the field inside one', async () => {
    const { fixture, el } = await mount();
    const field = probe<HTMLInputElement>('input');
    expect(keydown({ key: '/' }, field)).toBe(true); // not prevented: the slash is typed
    await settle(fixture);
    expect(palette(el)).toBeNull();
    keydown({ key: '/' });
    await settle(fixture);
    expect(palette(el)).not.toBeNull();
  });

  it('never opens over an open dialog', async () => {
    const { fixture, el } = await mount();
    probe<HTMLDialogElement>('dialog').setAttribute('open', '');
    keydown({ key: 'k', ctrlKey: true });
    await settle(fixture);
    expect(palette(el)).toBeNull();
  });

  it('opens from the phone search icon and from the More sheet, focus landing in its field', async () => {
    phone.set(true);
    const { fixture, el } = await mount();
    expect(el.querySelector('button.palette-trigger')).toBeNull();

    el.querySelector<HTMLButtonElement>('header.topbar button.search-trigger')!.click();
    await settle(fixture);
    expect(palette(el)).not.toBeNull();
    escape();
    await settle(fixture);

    el.querySelector<HTMLButtonElement>('sb-phone-tab-bar button.more')!.click();
    await settle(fixture);
    el.querySelector<HTMLButtonElement>('sb-more-sheet button.search')!.click();
    await settle(fixture);
    // The sheet closes first, then the palette opens: never one under the other.
    expect(el.querySelector('sb-more-sheet [role=dialog]')).toBeNull();
    expect(palette(el)).not.toBeNull();
    expect(document.activeElement).toBe(el.querySelector('sb-command-palette input[role=combobox]'));
  });

  it('mounts the palette after the More sheet, so a hand-over restores focus in that order', () => {
    const html = readSource('src/app/shell/shell.html');
    expect(html.indexOf('<sb-command-palette')).toBeGreaterThan(html.indexOf('<sb-more-sheet'));
    expect(html.indexOf('<sb-command-palette')).toBeLessThan(html.indexOf('<sb-toast-host'));
  });
});

describe('section tabs in the shell (v202 §1)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: shellProviders([
        { path: 'trades', component: Blank },
        { path: 'trades/calendar', component: Blank },
        { path: 'trades/:id', component: Blank },
        { path: 'risk', component: Blank },
      ]),
    });
  });

  async function go(fixture: ComponentFixture<Shell>, url: string): Promise<void> {
    await TestBed.inject(Router).navigateByUrl(url);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function at(url: string): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await go(fixture, url);
    return fixture.nativeElement as HTMLElement;
  }

  const current = (el: HTMLElement) =>
    [...el.querySelectorAll('sb-section-tabs a[aria-current="page"]')].map((a) => a.textContent!.trim());

  it('draws the tabs at the top of the workspace, before the routed page', async () => {
    const el = await at('/trades/calendar');
    const content = el.querySelector('main.workspace > .workspace-content')!;
    expect(content.firstElementChild!.tagName.toLowerCase()).toBe('sb-section-tabs');
    expect([...content.querySelectorAll('sb-section-tabs a')].map((a) => a.textContent!.trim()))
      .toEqual(['Book', 'Calendar', 'Cancels']);
    expect(current(el)).toEqual(['Calendar']);
  });

  it("keeps the destination's first section active on a detail page", async () => {
    expect(current(await at('/trades/812'))).toEqual(['Book']);
  });

  it('draws no tabs on a single page', async () => {
    expect((await at('/risk')).querySelectorAll('sb-section-tabs a')).toHaveLength(0);
  });

  it('moves the current tab when the URL moves to another section, and drops the tabs off it', async () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    await go(fixture, '/trades');
    expect(current(el)).toEqual(['Book']);
    await go(fixture, '/trades/calendar');
    expect(current(el)).toEqual(['Calendar']);
    await go(fixture, '/risk');
    expect(el.querySelectorAll('sb-section-tabs a')).toHaveLength(0);
  });
});

describe('shell live dock (v203)', () => {
  const NOW = Date.parse('2026-10-29T13:00:00Z');
  const narrow = signal(false);
  const phone = signal(false);
  const at = '2026-10-29T12:59:00Z';
  const SNAPSHOT = {
    heat: { availability: 'ok', as_of: at, reason: null, open_pct: 5.1, cap_pct: 6, utilisation_pct: 85, open_amount: 2459,
            cap_amount: 2893, headroom_pct: 0.9, headroom_amount: 434, balance: 48210, includes_resting: true },
    awaiting: { availability: 'ok', as_of: at, reason: null, count: 3, next_expiry: null },
    killswitch: { availability: 'ok', as_of: at, reason: null, engaged: false, since: null, detail: null },
    events: [], events_meta: { availability: 'ok', as_of: at, missing: [] },
  };
  const scan = (botAlive: boolean) => ({
    pending: false, triggered_at: null, paused: false, paused_at: null, running: false, bot_alive: botAlive,
    bot_last_seen: '2026-10-29T12:58:00Z', bot_healthy: true, bot_last_success: '2026-10-29T12:58:00Z',
    bot_consecutive_failures: 0, bot_session_active: true, bot_scan_paused: false, progress: null,
  });

  beforeEach(() => {
    narrow.set(false);
    phone.set(false);
    TestBed.configureTestingModule({ providers: shellProviders(['dashboard', 'trades', 'risk'].map((path) => ({ path, component: Blank }))) });
    TestBed.overrideProvider(CLOCK, { useValue: signal(NOW) });
    TestBed.overrideProvider(ViewportService, { useValue: { isPhone: phone, isNarrow: narrow, viewport: signal('lg') } });
  });

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function mount(url: string) {
    await TestBed.inject(Router).navigateByUrl(url);
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    const backend = TestBed.inject(HttpTestingController);
    for (const request of backend.match((r) => r.url.endsWith('/system/preferences'))) request.flush({ preferences: {} });
    for (const request of backend.match((r) => r.url.endsWith('/live'))) request.flush(SNAPSHOT);
    await settle(fixture);
    return { fixture, el: fixture.nativeElement as HTMLElement, backend };
  }

  it('docks the open dock on Dashboard, beside the workspace', async () => {
    const { el } = await mount('/dashboard');
    const row = el.querySelector('.main > .workspace-row')!;
    expect(row.classList).toContain('dock-open');
    expect(row.querySelector(':scope > main.workspace + aside.live-column[aria-label="Live"] > sb-live-dock')).not.toBeNull();
    expect(row.querySelector('sb-live-edge-tab')).toBeNull();
  });

  it('collapses to the edge tab elsewhere, warning-toned and named', async () => {
    const { el } = await mount('/trades');
    expect(el.querySelector('.workspace-row')!.classList).toContain('dock-collapsed');
    const tab = el.querySelector<HTMLButtonElement>('aside.live-column > sb-live-edge-tab button.edge-tab')!;
    expect(tab.classList).toContain('warn');
    expect(tab.getAttribute('aria-label')).toBe('Open the live dock. Warning: Heat near cap. Heat 2,459 € · 5.1% / 6%. 3 awaiting order');
    expect(el.querySelector('sb-live-dock')).toBeNull();
  });

  it('names a downed bot on the edge tab', async () => {
    const { fixture, el, backend } = await mount('/trades');
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) request.flush(scan(false));
    await settle(fixture);
    expect(el.querySelector('button.edge-tab')!.getAttribute('aria-label')).toContain('Warning: Heat near cap, Bot down.');
  });

  it('remembers the toggle per destination, through PreferencesStore', async () => {
    const { fixture, el } = await mount('/trades');
    el.querySelector<HTMLButtonElement>('button.edge-tab')!.click();
    await settle(fixture);
    expect(el.querySelector('aside.live-column > sb-live-dock')).not.toBeNull();
    expect(TestBed.inject(PreferencesStore).values()['shell.dock']).toEqual({ '/trades': true });
    el.querySelector<HTMLButtonElement>('sb-live-dock .dock-head button')!.click();
    await settle(fixture);
    expect(el.querySelector('sb-live-edge-tab')).not.toBeNull();
    expect(TestBed.inject(PreferencesStore).values()['shell.dock']).toEqual({ '/trades': false });
  });

  it('never docks below 1024 px', async () => {
    narrow.set(true);
    const { el } = await mount('/dashboard');
    expect(el.querySelector('aside.live-column')).toBeNull();
    expect(el.querySelector('sb-live-dock')).toBeNull();
    expect(el.querySelector('.workspace-row')!.className).not.toMatch(/dock-/);
  });

  it('sizes the column from one token: 320px open, 40px collapsed, sticky under the bar', () => {
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    const rule = (selector: string) => css.match(new RegExp(`^${selector.replace(/[.]/g, '\\.')} \\{[^}]*\\}`, 'm'))?.[0] ?? '';
    expect(rule('.dock-open')).toContain('--dock-width: 320px;');
    expect(rule('.dock-collapsed')).toContain('--dock-width: 40px;');
    for (const declaration of ['width: var(--dock-width);', 'position: sticky;', 'top: var(--topbar-h);', 'overflow-y: auto;']) {
      expect(rule('.live-column')).toContain(declaration);
    }
  });

  it('shows the strip under the tape below 1024 px, and opens the dock from the right on a tablet', async () => {
    narrow.set(true);
    const { fixture, el } = await mount('/trades');
    const strip = el.querySelector<HTMLButtonElement>('.main > .tape-strip + sb-live-strip button.live-strip')!;
    expect(strip).not.toBeNull();
    expect(strip.classList).toContain('warn');                 // heat at 85 % of the cap
    expect(el.querySelector('aside.live-column')).toBeNull();
    strip.click();
    await settle(fixture);
    const dialog = el.querySelector('sb-live-sheet [role=dialog]')!;
    expect(dialog.classList).toContain('right');
    expect(dialog.querySelector('sb-live-dock')).not.toBeNull();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')).toBeNull();
  });

  it('opens from the bottom on a phone, and the scrim closes it', async () => {
    narrow.set(true);
    phone.set(true);
    const { fixture, el } = await mount('/trades');
    el.querySelector<HTMLButtonElement>('button.live-strip')!.click();
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')!.classList).toContain('bottom');
    el.querySelector<HTMLElement>('sb-live-sheet .scrim')!.click();
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')).toBeNull();
  });

  it('closes the sheet on navigation, and when the window widens to docked', async () => {
    narrow.set(true);
    const { fixture, el } = await mount('/trades');
    el.querySelector<HTMLButtonElement>('button.live-strip')!.click();
    await settle(fixture);
    await TestBed.inject(Router).navigateByUrl('/risk');
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')).toBeNull();
    el.querySelector<HTMLButtonElement>('button.live-strip')!.click();
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')).not.toBeNull();
    narrow.set(false);
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')).toBeNull();
    expect(el.querySelector('sb-live-strip')).toBeNull();
    expect(el.querySelector('aside.live-column > sb-live-dock')).not.toBeNull();   // Risk opens by default
  });

  it('shows no strip and no sheet at 1024 px and wider', async () => {
    const { el } = await mount('/trades');
    expect(el.querySelector('sb-live-strip')).toBeNull();
    expect(el.querySelector('sb-live-sheet [role=dialog]')).toBeNull();
  });

  it('opens the collapsed dock from the alarm chip', async () => {
    const { fixture, el, backend } = await mount('/trades');
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) request.flush(scan(false));
    await settle(fixture);
    el.querySelector<HTMLButtonElement>('sb-alarm-chip button.alarm-chip')!.click();
    await settle(fixture);
    expect(el.querySelector('aside.live-column > sb-live-dock')).not.toBeNull();
  });

  it('opens the sheet from the alarm chip below 1024 px', async () => {
    narrow.set(true);
    const { fixture, el, backend } = await mount('/trades');
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) request.flush(scan(false));
    await settle(fixture);
    el.querySelector<HTMLButtonElement>('sb-alarm-chip button.alarm-chip')!.click();
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog] sb-live-dock')).not.toBeNull();
  });
});

describe('shell top bar (v203, spec v202 §3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: shellProviders([{ path: 'trades', component: Blank }]) });
    TestBed.overrideProvider(ViewportService, { useValue: { isPhone: signal(false), isNarrow: signal(false), viewport: signal('lg') } });
  });

  function render(): HTMLElement {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('orders the bar: wordmark, divider, breadcrumb, cluster, search, avatar', () => {
    const bar = render().querySelector('header.topbar')!;
    const order = ['a.brand', 'span.topbar-divider', 'sb-breadcrumb.topbar-lead', 'div.status-cluster',
      'button.palette-trigger', 'sb-profile-menu', 'sb-scan-progress'];
    expect(bar.children).toHaveLength(order.length);
    order.forEach((selector, index) => expect(bar.children[index].matches(selector), selector).toBe(true));
    expect(bar.querySelector('span.topbar-divider')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('renders the two-tone wordmark as two spans, not one coloured string', () => {
    // Restored from fdf6b78a^ (spec v202 D2).
    expect(render().querySelectorAll('.brand .word span').length).toBe(2);
  });

  it('gives the wordmark the pre-v195 treatment, Capital in the accent, linking to the Dashboard', () => {
    const brand = render().querySelector('header.topbar > a.brand')!;
    expect([...brand.querySelectorAll('.word span')].map((x) => x.textContent)).toEqual(['Bomeo', 'Capital']);
    expect(brand.getAttribute('href')).toBe('/dashboard');
    expect(brand.getAttribute('aria-label')).toContain('Bomeo Capital');
    expect(brand.querySelector('sb-icon')).toBeNull();          // the diamond heads the rail above phone width
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    const rule = (selector: string) => css.match(new RegExp('^' + selector.replace(/[.]/g, '[.]') + ' [{][^}]*[}]', 'm'))?.[0] ?? '';
    for (const declaration of ['font-family: var(--font-mono);', 'font-size: var(--text-body);', 'font-weight: 700;',
      'letter-spacing: -0.02em;', 'white-space: nowrap;']) {
      expect(rule('.brand .word')).toContain(declaration);
    }
    expect(rule('.brand .word span:last-child')).toContain('color: var(--accent);');
  });
});
