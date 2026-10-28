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
import { TestBed } from '@angular/core/testing';
import { Router, Routes, provideRouter } from '@angular/router';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import { RouteLoadingService } from '../routing/route-loading.service';
import { PreferencesStore } from '../stores/preferences.store';
import { TapeStore } from '../stores/tape.store';
import { CLOCK } from '../ui/clock';
import { provideMotion } from '../ui/motion/motion.service';
import { POPOVER_OPEN_ATTR } from '../testing/popover-polyfill';
import { NAV_GROUPS } from './nav';
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
  it('keeps each of the four groups a real, named list for assistive tech', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const groups = (f.nativeElement as HTMLElement).querySelectorAll('nav.rail ul.nav[aria-label]');
    expect(groups.length).toBe(4);
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

  it('marks the active entry with the bar, a tint and a brighter glyph, not colour alone', () => {
    // v168 §3 #6 kept: one sliding sb-nav-indicator in the rail. On an
    // icon-only rail weight means nothing, so the third cue is the glyph's
    // colour stepping from muted to full text.
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelectorAll('nav.rail > sb-nav-indicator').length).toBe(1);
    const css = readSource('src/app/shell/shell.css');
    const active = css.match(/^\.rail-link\.active \{[^}]*\}/m)?.[0] ?? '';
    expect(active).toContain('background: var(--accent-soft);');
    expect(active).toContain('color: var(--text);');
    expect(css.match(/^\.rail-link \{[^}]*\}/m)?.[0]).toContain('color: var(--text-muted);');
    expect(css).not.toMatch(/border-left-color/);
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
    const foot = el.querySelector('nav.rail > .rail-foot')!;
    const hint = foot.querySelector('sb-hint.version')!;
    expect(hint.querySelector('[role=tooltip]')!.textContent!.trim())
      .toBe('ui 1.36.1 · bot 2.15.3 · updated 2026-10-25T06:00:00Z');
    expect(el.querySelector('.version-row')).toBeNull();
  });

  it('drops the clock and the tape on a phone before it lets the bar overflow', () => {
    const css = readSource('src/app/shell/shell.css');
    // v95 A2's declared breakpoint. The subtitle it used to drop at 1023px
    // has left the bar (v195: the breadcrumb leads, sb-page carries the title).
    expect(css).toMatch(/max-width:\s*639px[\s\S]*\.clock[\s\S]*display:\s*none/);
    expect(css).toMatch(/max-width:\s*639px[\s\S]*\.topbar-tape[\s\S]*display:\s*none/);
    expect(css).not.toContain('.page-subtitle');
  });

  it('renders the brand as the mark alone, named for assistive tech and labelled on focus', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const brand = el.querySelector('nav.rail .mark a.brand') as HTMLAnchorElement;
    expect(brand.querySelector('sb-icon')).not.toBeNull();
    expect(brand.textContent!.trim()).toBe('');
    expect(brand.getAttribute('aria-label')).toContain('Bomeo Capital');
    expect(brand.nextElementSibling!.tagName.toLowerCase()).toBe('sb-hint');
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
    expect(rule('.mark')).toContain('height: var(--topbar-h)');
    expect(rule('.topbar')).toContain('position: sticky;');
  });
});

describe('shell icon rail (v195 Phase 3, correction 10)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: shellProviders([{ path: 'trades', component: Blank }]) });
  });

  async function mount() {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('is one rail of four unlabelled groups split by thin rules', async () => {
    const { el } = await mount();
    const rail = el.querySelector('nav.rail')!;
    expect(rail.getAttribute('aria-label')).toBe('Primary');
    expect([...rail.querySelectorAll('ul.nav')].map((ul) => ul.getAttribute('aria-label')))
      .toEqual(['Monitor', 'Review', 'Insights', 'System']);
    const dividers = [...rail.querySelectorAll('.rail-divider')];
    expect(dividers).toHaveLength(3);
    for (const divider of dividers) {
      expect(divider.getAttribute('aria-hidden')).toBe('true');
      expect(divider.textContent!.trim()).toBe('');
      // Between groups, never before the first or after the last.
      expect(divider.previousElementSibling!.matches('ul.nav')).toBe(true);
      expect(divider.nextElementSibling!.matches('ul.nav')).toBe(true);
    }
    expect(el.querySelector('.nav-group-label')).toBeNull();
  });

  it('names every entry and labels it with an anchored hint, never a title', async () => {
    const { el } = await mount();
    const links = [...el.querySelectorAll<HTMLAnchorElement>('nav.rail a.rail-link')];
    expect(links.map((a) => a.getAttribute('aria-label')))
      .toEqual(NAV_GROUPS.flatMap((group) => group.entries.map((entry) => entry.label)));
    for (const link of links) {
      const name = link.getAttribute('aria-label')!;
      expect(link.hasAttribute('title'), name).toBe(false);
      expect(link.querySelector('sb-icon')!.getAttribute('title'), name).toBe('');
      expect(link.textContent!.trim(), name).toBe('');
      const hint = link.nextElementSibling as HTMLElement;
      expect(hint.tagName.toLowerCase(), name).toBe('sb-hint');
      expect(hint.classList, name).toContain('anchored');
      const pop = hint.querySelector('[role=tooltip]')!;
      expect(pop.textContent!.trim(), name).toBe(name);
      expect(link.getAttribute('aria-describedby'), name).toBe(pop.id);
    }
  });

  it('shows an entry label on keyboard focus without adding a tab stop', async () => {
    const { fixture, el } = await mount();
    const trades = el.querySelector<HTMLAnchorElement>('a.rail-link[aria-label="Trades"]')!;
    const pop = trades.nextElementSibling!.querySelector('[role=tooltip]')!;
    expect(pop.hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
    trades.dispatchEvent(new FocusEvent('focus'));
    fixture.detectChanges();
    await fixture.whenStable();
    expect(pop.hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    expect(el.querySelectorAll('nav.rail ul.nav button')).toHaveLength(0);
  });

  it('marks the routed entry active', async () => {
    const { fixture, el } = await mount();
    await TestBed.inject(Router).navigateByUrl('/trades');
    fixture.detectChanges();
    await fixture.whenStable();
    expect([...el.querySelectorAll('a.rail-link.active')].map((a) => a.getAttribute('aria-label')))
      .toEqual(['Trades']);
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
    for (const gone of ['.collapse', '.menu-button', '.scrim', '.sidebar', '.rail-tagline', '.brand .word']) {
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

  it('leads the bar with the breadcrumb and renders no heading of its own', async () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await TestBed.inject(Router).navigateByUrl('/trades');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const bar = el.querySelector('header.topbar')!;
    expect(bar.firstElementChild!.tagName.toLowerCase()).toBe('sb-breadcrumb');
    const crumbs = [...bar.querySelectorAll('nav[aria-label="Breadcrumb"] li')]
      .map((li) => li.textContent!.replace('/', '').trim());
    expect(crumbs).toEqual(['Review', 'Trades']);
    expect(el.querySelectorAll('h1')).toHaveLength(0);
    expect(el.querySelector('.page-title, .page-subtitle')).toBeNull();
  });

  it('sizes the rail and the bar from two shell tokens, with no animated width', () => {
    const css = readSource('src/app/shell/shell.css');
    const shell = css.match(/^\.shell \{[^}]*\}/m)?.[0] ?? '';
    expect(shell).toContain('--rail-w: 48px;');
    expect(shell).toContain('--topbar-h: 40px;');
    expect(shell).toContain('grid-template-columns: var(--rail-w) 1fr;');
    expect(shell).not.toContain('transition');
    // The touch rules win (spec §1.4): the bar grows to hold 44px controls.
    expect(css).toMatch(/@media \(pointer: coarse\), \(max-width: 1023px\)\s*\{\s*\.shell \{ --topbar-h: 48px; \}/);
  });
});
