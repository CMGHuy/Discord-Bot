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
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import { VoiceNotifier } from '../voice/voice-notifier';
import { ScanEventProgress, TapeShock } from '../api/models';
import { RouteLoadingService } from '../routing/route-loading.service';
import { PreferencesStore } from '../stores/preferences.store';
import { LiveValuesStore } from '../stores/live-values.store';
import { TapeFeed } from '../stores/tape-feed';
import { TapeStore } from '../stores/tape.store';
import { installDialogPolyfill } from '../testing/dialog-polyfill';
import { ViewportService } from '../ui/breakpoints';
import { CLOCK } from '../ui/clock';
import { DENSITY_STORAGE } from '../ui/density.service';
import { THEME_STORAGE, ThemeStorage } from '../ui/theme.service';
import { styleRules } from '../ui/testing/style-rules';
import { HINT_HOVER_DELAY_MS } from '../ui/hint';
import { LONG_PRESS_MS } from '../ui/long-press';
import { POPOVER_OPEN_ATTR } from '../testing/popover-polyfill';
import { provideMotion } from '../ui/motion/motion.service';
import { NAV_ENTRIES } from './nav';
import { Shell } from './shell';
import { TAB_BAR_STORAGE, TabBarStorage } from './tab-bar-prefs';
import { SessionStore } from '../stores/session.store';

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

  /** v206: ConnectionStore patches the strip from this; null = fetch instead. */
  payload(): Signal<ScanEventProgress | null> {
    return signal<ScanEventProgress | null>(null).asReadonly();
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

/** The shell as the admin sees it, unless a test already gave the session a
 *  role (v207). Called late so a test can still override providers first. */
function createShell() {
  const session = unprotected(TestBed.inject(SessionStore));
  if (!session.role()) patchState(session, { status: 'authenticated', username: 'admin', role: 'admin' });
  return TestBed.createComponent(Shell);
}

/** An in-memory ui.theme store, so no shell spec writes the real localStorage (v225). */
function memoryThemeStorage(map = new Map<string, string>()): ThemeStorage {
  return { get: (key) => map.get(key) ?? null, set: (key, value) => void map.set(key, value) };
}

/** An in-memory ui.tabbar, so no shell spec writes jsdom's localStorage (v240 §6). */
function memoryTabBarStorage(map = new Map<string, string>()): TabBarStorage {
  return { get: (key) => map.get(key) ?? null, set: (key, value) => void map.set(key, value) };
}

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
    { provide: THEME_STORAGE, useValue: memoryThemeStorage() },
    { provide: TAB_BAR_STORAGE, useValue: memoryTabBarStorage() },
  ];
}

const readSource = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');

afterEach(() => {
  delete document.documentElement.dataset['theme'];
});

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
    const fixture = createShell();
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
    const f = createShell();
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('header.topbar .clock')).toBeNull();
    expect(readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '')).not.toMatch(/\.clock\b/);
    const code = readSource('src/app/shell/shell.ts').replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
    expect(code).not.toMatch(/readonly now\b/);
  });

  it('renders the killswitch as a full-width strip below the bar, only when engaged', () => {
    const f = createShell();
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
    const f = createShell();
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
    const f = createShell();
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
    const f = createShell();
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
    const fixture = createShell();
    fixture.detectChanges();
    expect(tapeStub.load).toHaveBeenCalledTimes(1);
  });

  it('shows an accessible, non-interactive overlay inside the pending workspace', () => {
    const routeLoading = { visible: signal(false), label: signal('Loading Trades') };
    TestBed.overrideProvider(RouteLoadingService, { useValue: routeLoading });
    const f = createShell();
    f.detectChanges();
    routeLoading.visible.set(true);
    f.detectChanges();
    const workspace = (f.nativeElement as HTMLElement).querySelector('.workspace')!;
    expect(workspace.classList.contains('route-pending')).toBe(true);
    expect(workspace.querySelector('[role="status"]')?.textContent).toContain('Loading Trades');
    expect(workspace.querySelector('.route-loading-overlay')).not.toBeNull();
  });
  it('keeps the work destinations and System as two named lists', () => {
    const f = createShell();
    f.detectChanges();
    const lists = (f.nativeElement as HTMLElement).querySelectorAll('nav.rail ul.nav[aria-label]');
    expect([...lists].map((ul) => ul.getAttribute('aria-label'))).toEqual(['Destinations', 'System']);
  });

  it('cycles the text-size control in the profile menu through 90/100/110/125 and wraps back to 90', () => {
    const f = createShell();
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

  it('marks the active entry with the accent-soft fill and a 3px accent bar on the inner edge (v247 §5)', () => {
    const css = readSource('src/app/shell/shell.css');
    const active = css.match(/^\.rail-link\.active \{[^}]*\}/m)?.[0] ?? '';
    expect(active).toContain('background: var(--accent-soft);');
    expect(active).toContain('color: var(--text);');
    const bar = css.match(/^\.rail-link\.active::after \{[^}]*\}/m)?.[0] ?? '';
    for (const declaration of ['content: "";', 'position: absolute;', 'width: 3px;',
      'right: calc((var(--rail-width) - 44px) / -2);', 'border-radius: var(--pill-radius);',
      'background: var(--accent);']) {
      expect(bar, declaration).toContain(declaration);
    }
    // The bar is placed against the link, so the link is its containing block.
    const link = css.match(/^\.rail-link \{[^}]*\}/m)?.[0] ?? '';
    expect(link).toContain('position: relative;');
    expect(link).toContain('color: var(--text-muted);');
    expect(css).not.toMatch(/sb-nav-indicator|border-left-color|\.rail-pill/);
  });

  it('sizes each entry 44x44 with a 24px icon and no label rule (v247 §5)', () => {
    const css = readSource('src/app/shell/shell.css');
    const link = css.match(/^\.rail-link \{[^}]*\}/m)?.[0] ?? '';
    expect(link).toContain('width: 44px;');
    expect(link).toContain('height: 44px;');
    expect(link).not.toContain('flex-direction: column;');
    // The icon draws at 24 through sb-icon's size input (v240 §4); no rule
    // reaches into the svg to resize it.
    expect(styleRules('shell.css', css).filter((rule) => /sb-icon\s+svg/.test(rule.selector))).toEqual([]);
    expect(css).not.toMatch(/\.rail-label/);
  });

  it('keeps the ui and bot versions in a hint at the foot of the rail', async () => {
    const f = createShell();
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
    // v240 §4 correction: the version hint draws the info icon like every
    // other hint; the "v" letter it used to opt into is gone.
    const trigger = hint.querySelector('button.trigger')!;
    expect(trigger.getAttribute('aria-label')).toBe('Version');
    expect(trigger.querySelector('sb-icon svg path')!.getAttribute('d'))
      .toBe('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v5.5 M12 7.6v.1');
    expect(trigger.textContent!.trim()).toBe('');
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
    const f = createShell();
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const brand = el.querySelector('nav.rail > a.rail-brand') as HTMLAnchorElement;
    expect(brand.querySelector('sb-icon')).not.toBeNull();
    expect(brand.textContent!.trim()).toBe('');
    expect(brand.getAttribute('aria-label')).toContain('Bomeo Capital');
    expect(brand.nextElementSibling!.tagName.toLowerCase()).toBe('sb-hint');
  });

  it('the brand mark links back to the Dashboard', () => {
    const f = createShell();
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

describe('shell phone bar worst case (v210)', () => {
  const css = readFileSync(join(process.cwd(), 'src/app/shell/shell.css'), 'utf8');
  const phone = css.slice(css.lastIndexOf('@media (max-width: 639px)'));

  it('lets the chip cluster shrink so search and the profile avatar stay on screen', () => {
    expect(phone).toMatch(/\.status-cluster \{[^}]*min-width: 0;/);
  });

  it('spends the wordmark on the shock pill: the diamond stays, the words go visually', () => {
    expect(phone).toMatch(/\.topbar:has\(\.shock-pill\):has\(sb-read-only-badge\) \.brand \.word \{[^}]*clip-path: inset\(50%\);/);
    expect(phone).not.toMatch(/\.brand \.word \{[^}]*display: none/);
  });

  it('collapses the wordmark only when the read-only badge shares the bar with the pill', () => {
    expect(phone).not.toMatch(/\.topbar:has\(\.shock-pill\) \.brand/);
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
    const fixture = createShell();
    await settle(fixture);
    expect(html.dataset['motion']).toBe('pending');
  });

  it('defaults to on once preferences load without a stored mode', async () => {
    const fixture = createShell();
    await settle(fixture);
    flushPreferences({});
    await settle(fixture);
    expect(html.dataset['motion']).toBe('on');
  });

  it('restores a stored mode onto <html>', async () => {
    const fixture = createShell();
    await settle(fixture);
    flushPreferences({ 'shell.motion': 'reduced' });
    await settle(fixture);
    expect(html.dataset['motion']).toBe('reduced');
  });

  it('falls back to on for an unknown stored value', async () => {
    const fixture = createShell();
    await settle(fixture);
    flushPreferences({ 'shell.motion': 'sparkly' });
    await settle(fixture);
    expect(html.dataset['motion']).toBe('on');
  });

  it('writes shell.motion and data-motion when the control is used', async () => {
    const fixture = createShell();
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

describe('shell icon rail (v247, spec v240 §5)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: shellProviders([
        { path: 'trades', component: Blank },
        { path: 'calendar', component: Blank }, { path: 'calendar/:date', component: Blank },
        { path: 'plans/:id', component: Blank },
        { path: 'insights/analytics', component: Blank },
        { path: 'system/versions', component: Blank },
      ]),
    });
  });

  async function mount() {
    const fixture = createShell();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  /** v247: a rail link is named by its aria-label alone; it draws no text. */
  const labelOf = (link: Element) => link.getAttribute('aria-label') ?? '';
  /** The role="tooltip" popover the link's aria-describedby points at (its sb-hint). */
  const tooltipOf = (el: HTMLElement, link: Element) =>
    el.querySelector(`[id="${link.getAttribute('aria-describedby')}"]`) as HTMLElement;
  const isOpen = (tooltip: HTMLElement) => tooltip.hasAttribute(POPOVER_OPEN_ATTR);
  async function settle(fixture: ComponentFixture<Shell>) {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }
  const railLink = (el: HTMLElement, path: string) =>
    el.querySelector<HTMLAnchorElement>(`nav.rail a.rail-link[href="${path}"]`)!;

  /** jsdom has no PointerEvent: a MouseEvent carrying pointerType and pointerId
   *  is what sbLongPress reads (ui/long-press.spec.ts does the same). */
  function pointer(type: string, pointerType = 'touch'): MouseEvent {
    const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: 30, clientY: 120 });
    Object.defineProperty(event, 'pointerType', { value: pointerType });
    Object.defineProperty(event, 'pointerId', { value: 1 });
    return event;
  }

  /** Holds a pointer on the link for LONG_PRESS_MS and lifts it. Only
   *  setTimeout is faked: the hint's requestAnimationFrame stays real. */
  async function hold(fixture: ComponentFixture<Shell>, link: Element, pointerType = 'touch') {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      link.dispatchEvent(pointer('pointerdown', pointerType));
      vi.advanceTimersByTime(LONG_PRESS_MS);
      link.dispatchEvent(pointer('pointerup', pointerType));
    } finally {
      vi.useRealTimers();
    }
    await settle(fixture);
  }

  const tap = () => new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });

  it('draws seven labelled destinations, six work entries then System at the foot (v247)', async () => {
    const { el } = await mount();
    const rail = el.querySelector('nav.rail')!;
    expect(rail.getAttribute('aria-label')).toBe('Primary');
    expect(rail.firstElementChild!.matches('a.rail-brand')).toBe(true);
    const lists = [...rail.querySelectorAll(':scope > ul.nav')];
    expect(lists.map((ul) => ul.className)).toEqual(['nav rail-work', 'nav rail-foot']);
    const labels = (ul: Element) => [...ul.querySelectorAll(':scope > li > a.rail-link')].map(labelOf);
    expect(labels(lists[0])).toEqual(['Dashboard', 'Watchlist', 'Trades', 'Calendar', 'Risk', 'Insights']);
    expect(labels(lists[1])).toEqual(['System']);
    expect(lists[1].nextElementSibling!.matches('.rail-version')).toBe(true);
    expect(rail.querySelector('.rail-divider, sb-nav-indicator, .nav-group-label')).toBeNull();
  });

  const asViewer = (name = 'viewer1') =>
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: name, role: 'viewer' });

  it('drops the System foot list for a viewer and keeps the version hint at the foot (v207)', async () => {
    asViewer();
    const { el } = await mount();
    const rail = el.querySelector('nav.rail')!;
    const lists = [...rail.querySelectorAll(':scope > ul.nav')];
    expect(lists.map((ul) => ul.className)).toEqual(['nav rail-work']);
    expect([...lists[0].querySelectorAll('a.rail-link')].map(labelOf))
      .toEqual(['Dashboard', 'Watchlist', 'Trades', 'Calendar', 'Risk', 'Insights']);
    expect(rail.querySelector('a[href="/system"]')).toBeNull();
    const version = lists[0].nextElementSibling as HTMLElement;
    expect(version.matches('.rail-version')).toBe(true);
    expect(version.style.marginTop).toBe('auto');
  });

  it('shows the read-only badge first in the status cluster for a viewer only (v207)', async () => {
    asViewer('viewer1');
    const { el } = await mount();
    const cluster = el.querySelector('.status-cluster')!;
    expect(cluster.firstElementChild!.tagName.toLowerCase()).toBe('sb-read-only-badge');
    expect(cluster.querySelector('sb-read-only-badge')!.textContent).toContain('Read-only · viewer1');
    expect(cluster.querySelector('sb-killswitch-chip')).not.toBeNull();
  });

  it('shows no badge to the admin (v207)', async () => {
    const { el } = await mount();
    expect(el.querySelector('sb-read-only-badge')).toBeNull();
  });

  it('names each entry by aria-label alone, draws no label, and gives it one anchored hint with that name', async () => {
    const { el } = await mount();
    const links = [...el.querySelectorAll<HTMLAnchorElement>('nav.rail a.rail-link')];
    expect(links.map((a) => a.getAttribute('href'))).toEqual(NAV_ENTRIES.map((entry) => entry.path));
    expect(el.querySelector('nav.rail .rail-label, nav.rail .rail-pill')).toBeNull();
    links.forEach((link, index) => {
      const label = NAV_ENTRIES[index].label;
      expect(link.getAttribute('aria-label'), label).toBe(label);
      expect(link.hasAttribute('title'), label).toBe(false);
      // No visible text: the icon is the link's only child, and it is unnamed.
      expect(link.textContent!.trim(), label).toBe('');
      expect([...link.children].map((child) => child.tagName.toLowerCase()), label).toEqual(['sb-icon']);
      expect(link.querySelector(':scope > sb-icon')!.getAttribute('title'), label).toBe('');
      // One hint per entry, beside the link in its <li>, describing it with the same name.
      expect(link.parentElement!.querySelectorAll('sb-hint'), label).toHaveLength(1);
      const tooltip = tooltipOf(el, link);
      expect(tooltip.getAttribute('role'), label).toBe('tooltip');
      expect(tooltip.textContent!.trim(), label).toBe(label);
      expect(isOpen(tooltip), label).toBe(false);
    });
    expect(el.querySelectorAll('nav.rail ul.nav button')).toHaveLength(0);
  });

  it('gives a viewer a hint on every entry it sees and none naming System (v207)', async () => {
    asViewer();
    const { el } = await mount();
    const links = [...el.querySelectorAll<HTMLAnchorElement>('nav.rail a.rail-link')];
    expect(links.map(labelOf)).toEqual(['Dashboard', 'Watchlist', 'Trades', 'Calendar', 'Risk', 'Insights']);
    expect(el.querySelectorAll('nav.rail li > sb-hint')).toHaveLength(links.length);
    expect([...el.querySelectorAll('nav.rail li [role="tooltip"]')].map((tip) => tip.textContent!.trim()))
      .not.toContain('System');
  });

  it('opens the entry hint at once on keyboard focus, and closes it on blur and on Escape', async () => {
    const { fixture, el } = await mount();
    const link = railLink(el, '/watchlist');
    const tooltip = tooltipOf(el, link);
    link.dispatchEvent(new FocusEvent('focus'));
    await settle(fixture);
    expect(isOpen(tooltip)).toBe(true);
    link.dispatchEvent(new FocusEvent('blur'));
    await settle(fixture);
    expect(isOpen(tooltip)).toBe(false);
    link.dispatchEvent(new FocusEvent('focus'));
    await settle(fixture);
    expect(isOpen(tooltip)).toBe(true);
    link.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(isOpen(tooltip)).toBe(false);
  });

  it('opens the entry hint on hover only after the hint delay, and a leave before it cancels', async () => {
    const { fixture, el } = await mount();
    const link = railLink(el, '/risk');
    const tooltip = tooltipOf(el, link);
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      link.dispatchEvent(new MouseEvent('mouseenter'));
      fixture.detectChanges();
      vi.advanceTimersByTime(HINT_HOVER_DELAY_MS - 1);
      fixture.detectChanges();
      expect(isOpen(tooltip)).toBe(false);
      vi.advanceTimersByTime(1);
      fixture.detectChanges();
      expect(isOpen(tooltip)).toBe(true);
      link.dispatchEvent(new MouseEvent('mouseleave'));
      fixture.detectChanges();
      expect(isOpen(tooltip)).toBe(false);
      // A pass over the link shorter than the delay never opens it.
      link.dispatchEvent(new MouseEvent('mouseenter'));
      vi.advanceTimersByTime(HINT_HOVER_DELAY_MS - 50);
      link.dispatchEvent(new MouseEvent('mouseleave'));
      vi.advanceTimersByTime(HINT_HOVER_DELAY_MS);
      fixture.detectChanges();
      expect(isOpen(tooltip)).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows one rail tooltip at a time', async () => {
    const { fixture, el } = await mount();
    const first = railLink(el, '/trades');
    const second = railLink(el, '/calendar');
    first.dispatchEvent(new FocusEvent('focus'));
    await settle(fixture);
    expect(isOpen(tooltipOf(el, first))).toBe(true);
    second.dispatchEvent(new FocusEvent('focus'));
    await settle(fixture);
    expect(isOpen(tooltipOf(el, second))).toBe(true);
    expect(isOpen(tooltipOf(el, first))).toBe(false);
    expect(el.querySelectorAll(`nav.rail li [role="tooltip"][${POPOVER_OPEN_ATTR}]`)).toHaveLength(1);
  });

  it('draws the brand and every destination icon at 24px through sb-icon size (v240 §4)', async () => {
    const { el } = await mount();
    const svgs = [...el.querySelectorAll(
      'nav.rail > a.rail-brand > sb-icon svg, nav.rail a.rail-link > sb-icon svg',
    )];
    // The brand plus one icon per destination.
    expect(svgs).toHaveLength(1 + NAV_ENTRIES.length);
    for (const svg of svgs) {
      expect(svg.getAttribute('width')).toBe('24');
      expect(svg.getAttribute('height')).toBe('24');
      expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
    }
  });

  it.each([
    ['/trades', 'Trades'],
    ['/calendar', 'Calendar'], ['/calendar/2026-10-01', 'Calendar'],
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

  it('makes every rail link a long-press host, and the brand mark not one', async () => {
    const { el } = await mount();
    const links = [...el.querySelectorAll('nav.rail a.rail-link')];
    expect(links).toHaveLength(NAV_ENTRIES.length);
    for (const link of links) expect(link.classList.contains('sb-long-press'), labelOf(link)).toBe(true);
    expect(el.querySelector('nav.rail a.rail-brand')!.classList.contains('sb-long-press')).toBe(false);
  });

  it('opens the entry hint on a 500ms touch hold and not a moment before', async () => {
    const { fixture, el } = await mount();
    const link = railLink(el, '/calendar');
    const tooltip = tooltipOf(el, link);
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      link.dispatchEvent(pointer('pointerdown'));
      vi.advanceTimersByTime(LONG_PRESS_MS - 1);
      fixture.detectChanges();
      expect(isOpen(tooltip)).toBe(false);
      vi.advanceTimersByTime(1);
    } finally {
      vi.useRealTimers();
    }
    await settle(fixture);
    expect(isOpen(tooltip)).toBe(true);
    expect(tooltip.textContent!.trim()).toBe('Calendar');
  });

  it('keeps the held-open hint after the finger lifts, and swallows the click so it navigates nowhere', async () => {
    const { fixture, el } = await mount();
    const router = TestBed.inject(Router);
    const before = router.url;
    const link = railLink(el, '/trades');
    await hold(fixture, link);
    expect(isOpen(tooltipOf(el, link))).toBe(true);
    link.dispatchEvent(tap());
    await settle(fixture);
    expect(router.url).toBe(before);
    expect(isOpen(tooltipOf(el, link))).toBe(true);
  });

  it('closes the held-open hint on the next touch anywhere, and on Escape', async () => {
    const { fixture, el } = await mount();
    const link = railLink(el, '/risk');
    await hold(fixture, link);
    expect(isOpen(tooltipOf(el, link))).toBe(true);
    document.body.dispatchEvent(pointer('pointerdown'));
    await settle(fixture);
    expect(isOpen(tooltipOf(el, link))).toBe(false);

    await hold(fixture, link);
    expect(isOpen(tooltipOf(el, link))).toBe(true);
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(isOpen(tooltipOf(el, link))).toBe(false);
  });

  it('never opens on a mouse held down, and that click still navigates (hover covers a mouse)', async () => {
    const { fixture, el } = await mount();
    const link = railLink(el, '/trades');
    await hold(fixture, link, 'mouse');
    expect(isOpen(tooltipOf(el, link))).toBe(false);
    link.dispatchEvent(tap());
    await settle(fixture);
    expect(TestBed.inject(Router).url).toBe('/trades');
  });

  it('moves a held-open hint to the entry held next (one at a time)', async () => {
    const { fixture, el } = await mount();
    const first = railLink(el, '/dashboard');
    const second = railLink(el, '/insights');
    await hold(fixture, first);
    expect(isOpen(tooltipOf(el, first))).toBe(true);
    await hold(fixture, second);
    expect(isOpen(tooltipOf(el, second))).toBe(true);
    expect(isOpen(tooltipOf(el, first))).toBe(false);
  });
});

describe('shell top bar (v195 Phase 3, correction 9)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: shellProviders([{ path: 'trades', component: Blank }]) });
  });

  it('leads the bar with the wordmark, the divider and the breadcrumb, and renders no heading of its own', async () => {
    const fixture = createShell();
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
    expect(crumbs).toEqual(['Trades']);
    expect(el.querySelectorAll('h1')).toHaveLength(0);
    expect(el.querySelector('.page-title, .page-subtitle')).toBeNull();
  });

  it('sizes the rail and the bar from two shell tokens, with no animated width', () => {
    const css = readSource('src/app/shell/shell.css');
    const shell = css.match(/^\.shell \{[^}]*\}/m)?.[0] ?? '';
    expect(shell).toContain('--rail-width: 64px;');
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
        { provide: THEME_STORAGE, useValue: memoryThemeStorage(stored) },
      ],
    });
    TestBed.overrideProvider(CLOCK, { useValue: signal(NOW) });
  });

  afterEach(() => {
    delete html.dataset['density'];
    delete html.dataset['theme'];
  });

  async function mount() {
    const fixture = createShell();
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

  it('keeps only the voice, alarm and killswitch chips in the cluster, hidden at no width', async () => {
    // v203 Retired 'puts the killswitch and freshness chips in the cluster' and
    // 'ages the freshness chip …' (spec v202 D5: freshness, connection and the clock
    // live in the dock and strip; V203-4's botRows pins the freshness words).
    // v227: the voice chip joins, before the alarm chip.
    const { el } = await mount();
    const cluster = el.querySelector('header.topbar > .status-cluster')!;
    expect([...cluster.children].map((c) => c.tagName.toLowerCase()))
      .toEqual(['sb-voice-chip', 'sb-alarm-chip', 'sb-killswitch-chip']);
    expect(el.querySelector('header.topbar sb-freshness-chip, header.topbar sb-connection-status')).toBeNull();
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    expect(css).not.toMatch(/(sb-killswitch-chip|sb-alarm-chip|sb-voice-chip|\.status-cluster)[^{}]*\{[^}]*display:\s*none/);
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

  const themeButton = (el: HTMLElement) => el.querySelector<HTMLButtonElement>('header.topbar > button.theme-toggle')!;

  it('toggles Dark blue from the bar: aria-pressed, data-theme and ui.theme move together', async () => {
    const { fixture, el } = await mount();
    const button = themeButton(el);
    expect(button.getAttribute('aria-label')).toBe('Dark blue theme');
    // v240: Dark blue is the default, so the bar starts pressed.
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(html.dataset['theme']).toBe('navy');

    button.click();
    await settle(fixture);
    expect(button.getAttribute('aria-pressed')).toBe('false');
    expect(html.dataset['theme']).toBe('graphite');
    expect(stored.get('ui.theme')).toBe('graphite');
    expect(button.getAttribute('aria-label')).toBe('Dark blue theme');

    button.click();
    await settle(fixture);
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(html.dataset['theme']).toBe('navy');
    expect(stored.get('ui.theme')).toBe('navy');
  });

  it('starts pressed when this browser stored Dark blue', async () => {
    stored.set('ui.theme', 'navy');
    const { el } = await mount();
    expect(themeButton(el).getAttribute('aria-pressed')).toBe('true');
    expect(html.dataset['theme']).toBe('navy');
  });

  it('starts unpressed when this browser stored Black', async () => {
    stored.set('ui.theme', 'graphite');
    const { el } = await mount();
    expect(themeButton(el).getAttribute('aria-pressed')).toBe('false');
    expect(html.dataset['theme']).toBe('graphite');
  });

  it('is a 44px-hit icon button with the theme glyph and an anchored "Dark blue theme" hint', async () => {
    const { el } = await mount();
    const button = themeButton(el);
    expect(button.classList).toContain('sb-hit');
    expect(button.classList).toContain('icon');
    expect(button.querySelector('sb-icon')).not.toBeNull();
    const tip = el.querySelector('header.topbar > sb-hint [role=tooltip]')!;
    expect(tip.textContent!.trim()).toBe('Dark blue theme');
    expect(button.getAttribute('aria-describedby')).toBe(tip.id);
  });

  it('shows the pressed state as the accent glyph on the accent tint', () => {
    const css = readSource('src/app/shell/shell.css');
    const rule = css.match(/\.theme-toggle\[aria-pressed="true"\][^{]*\{[^}]*\}/)?.[0] ?? '';
    expect(rule).toContain('color: var(--accent);');
    expect(rule).toContain('background: var(--accent-soft);');
    expect(css).toMatch(/\.theme-toggle\[aria-pressed="true"\]:not\(\[disabled\]\):hover/);
  });
});

describe('v225: one theme across the bar button and the profile menu', () => {
  const NOW = Date.parse('2026-10-27T12:00:00Z');
  const html = document.documentElement;
  let stored: Map<string, string>;
  const fakeStorage = () => ({
    get: (key: string) => stored.get(key) ?? null,
    set: (key: string, value: string) => stored.set(key, value),
  });

  beforeEach(() => {
    stored = new Map();
    TestBed.configureTestingModule({
      providers: [
        ...shellProviders(),
        { provide: DENSITY_STORAGE, useValue: fakeStorage() },
        { provide: THEME_STORAGE, useValue: memoryThemeStorage(stored) },
      ],
    });
    TestBed.overrideProvider(CLOCK, { useValue: signal(NOW) });
  });

  afterEach(() => {
    delete html.dataset['density'];   // data-theme is cleared by the file-level afterEach (V225-6)
  });

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function mount() {
    const fixture = createShell();
    await settle(fixture);
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  const openMenu = async (fixture: ComponentFixture<unknown>, el: HTMLElement) => {
    el.querySelector<HTMLButtonElement>('sb-profile-menu .avatar')!.click();
    await settle(fixture);
  };
  const themeSegments = (el: HTMLElement) =>
    Array.from(el.querySelectorAll<HTMLButtonElement>('sb-profile-menu .theme-control .segment'));
  const segment = (el: HTMLElement, label: 'Black' | 'Dark blue') =>
    themeSegments(el).find((button) => button.textContent!.trim() === label)!;
  const pressedSegment = (el: HTMLElement) =>
    themeSegments(el).find((button) => button.getAttribute('aria-pressed') === 'true')!.textContent!.trim();
  const barButton = (el: HTMLElement) => el.querySelector<HTMLButtonElement>('header.topbar button.theme-toggle');

  it('writes ui.theme and data-theme from the menu row, and the bar button follows', async () => {
    const { fixture, el } = await mount();
    expect(html.dataset['theme']).toBe('navy');
    await openMenu(fixture, el);
    segment(el, 'Black').click();
    await settle(fixture);
    expect(html.dataset['theme']).toBe('graphite');
    expect(stored.get('ui.theme')).toBe('graphite');
    expect(pressedSegment(el)).toBe('Black');
    expect(barButton(el)!.getAttribute('aria-pressed')).toBe('false');
  });

  it('moves the pressed segment when the bar button is clicked, and the bar when the menu is', async () => {
    const { fixture, el } = await mount();
    await openMenu(fixture, el);
    expect(pressedSegment(el)).toBe('Dark blue');
    barButton(el)!.click();
    await settle(fixture);
    expect(html.dataset['theme']).toBe('graphite');
    // A click outside the menu closes it (ProfileMenu's document click); reopen to read it.
    if (!el.querySelector('sb-profile-menu [role=menu]')) await openMenu(fixture, el);
    expect(pressedSegment(el)).toBe('Black');
    segment(el, 'Dark blue').click();
    await settle(fixture);
    expect(barButton(el)!.getAttribute('aria-pressed')).toBe('true');
    expect(stored.get('ui.theme')).toBe('navy');
  });

  it('keeps the Theme row on a phone, where it is the only switch', async () => {
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: signal(true), isNarrow: signal(true), viewport: signal('xs') },
    });
    const { fixture, el } = await mount();
    expect(barButton(el)).toBeNull();
    await openMenu(fixture, el);
    segment(el, 'Black').click();
    await settle(fixture);
    expect(html.dataset['theme']).toBe('graphite');
    expect(stored.get('ui.theme')).toBe('graphite');
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
    const fixture = createShell();
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
    expect(bar.querySelector('button.theme-toggle')).toBeNull();
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
    const fixture = createShell();
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
    const fixture = createShell();
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
    expect(trigger.nextElementSibling!.matches('button.theme-toggle')).toBe(true);   // v225: then the theme toggle, then the avatar
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
        { path: 'trades/:id', component: Blank },
        { path: 'insights/analytics', component: Blank },
        { path: 'insights/research', component: Blank },
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
    const fixture = createShell();
    fixture.detectChanges();
    await go(fixture, url);
    return fixture.nativeElement as HTMLElement;
  }

  const current = (el: HTMLElement) =>
    [...el.querySelectorAll('sb-section-tabs a[aria-current="page"]')].map((a) => a.textContent!.trim());

  it('draws the tabs at the top of the workspace, before the routed page', async () => {
    const el = await at('/insights/research');
    const content = el.querySelector('main.workspace > .workspace-content')!;
    expect(content.firstElementChild!.tagName.toLowerCase()).toBe('sb-section-tabs');
    expect([...content.querySelectorAll('sb-section-tabs a')].map((a) => a.textContent!.trim()))
      .toEqual(['Analytics', 'Research', 'Reports', 'Guide']);
    expect(current(el)).toEqual(['Research']);
  });

  it('draws no tabs on Trades or a trade detail, a single page since v247', async () => {
    expect((await at('/trades')).querySelectorAll('sb-section-tabs a')).toHaveLength(0);
    expect((await at('/trades/812')).querySelectorAll('sb-section-tabs a')).toHaveLength(0);
  });

  it('draws no tabs on a single page', async () => {
    expect((await at('/risk')).querySelectorAll('sb-section-tabs a')).toHaveLength(0);
  });

  it('moves the current tab when the URL moves to another section, and drops the tabs off it', async () => {
    const fixture = createShell();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    await go(fixture, '/insights/analytics');
    expect(current(el)).toEqual(['Analytics']);
    await go(fixture, '/insights/research');
    expect(current(el)).toEqual(['Research']);
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
    const fixture = createShell();
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
    const f = createShell();
    f.detectChanges();
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('orders the bar: wordmark, divider, breadcrumb, cluster, search, theme, avatar', () => {
    const bar = render().querySelector('header.topbar')!;
    const order = ['a.brand', 'span.topbar-divider', 'sb-breadcrumb.topbar-lead', 'div.status-cluster',
      'button.palette-trigger', 'button.theme-toggle', 'sb-hint', 'sb-profile-menu', 'sb-scan-progress'];
    expect(bar.children).toHaveLength(order.length);
    order.forEach((selector, index) => expect(bar.children[index].matches(selector), selector).toBe(true));
    expect(bar.querySelector('span.topbar-divider')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('renders the two-tone wordmark as two spans with a real space between them (v247, spec v240 D8)', () => {
    const word = render().querySelector('header.topbar > a.brand .word')!;
    expect(word.querySelectorAll('span')).toHaveLength(2);
    expect([...word.querySelectorAll('span')].map((x) => x.textContent)).toEqual(['Bomeo', 'Capital']);
    // An ordinary U+0020, not a no-break space and not nothing.
    expect(word.textContent).toBe('Bomeo Capital');
  });

  it('draws Bomeo in the text colour at 700 and Capital in the accent at 500, in the sans face, linking to the Dashboard', () => {
    const brand = render().querySelector('header.topbar > a.brand')!;
    expect(brand.getAttribute('href')).toBe('/dashboard');
    expect(brand.getAttribute('aria-label')).toBe('Bomeo Capital — go to the Dashboard');
    expect(brand.querySelector('sb-icon')).toBeNull();          // the diamond heads the rail above phone width
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    const rule = (selector: string) =>
      css.match(new RegExp('^' + selector.replace(/[.]/g, '[.]') + ' [{][^}]*[}]', 'm'))?.[0] ?? '';
    const word = rule('.brand .word');
    for (const declaration of ['font-family: var(--font-sans);', 'font-size: var(--text-body);', 'font-weight: 700;',
      'letter-spacing: -0.02em;', 'white-space: nowrap;', 'color: var(--text);']) {
      expect(word, declaration).toContain(declaration);
    }
    // No figures in a wordmark: no mono face and no tabular figures (v247 Decision 10).
    expect(word).not.toContain('--font-mono');
    expect(word).not.toContain('tabular-nums');
    const capital = rule('.brand .word span:last-child');
    expect(capital).toContain('color: var(--accent);');
    expect(capital).toContain('font-weight: 500;');
    // Nav and brand never read the money colours (spec v240 §1).
    expect(word + capital).not.toMatch(/--pos|--neg/);
  });
});

describe('shell phone shock pill (v210)', () => {
  const shockState: TapeShock = {
    label: 'SHOCK', since: '2026-11-05T14:45:00+00:00', as_of: '2026-11-05T15:00:00+00:00',
    breadth_pct: 42, sectors_down: 5, sectors_total: 8, spy_atr_move: -1.8, qqq_atr_move: -2.3,
    vix_level: 21.13, vix_chg_pct: 27.2, vix_missing: false,
  };

  // The real MarketIndexStore (the shell injects it) and V210-3b's sb-tape
  // read the feed too, so the fake carries every member they touch.
  function mount(phone: boolean, state: TapeShock | null): HTMLElement {
    TestBed.configureTestingModule({ providers: shellProviders() });
    TestBed.overrideProvider(TapeFeed, {
      useValue: {
        register: vi.fn(), refresh: vi.fn(), rows: signal({}), asOf: signal(null),
        loading: signal(false), shock: signal(state),
      },
    });
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: signal(phone), isNarrow: signal(phone), viewport: signal(phone ? 'xs' : 'md') },
    });
    const fixture = createShell();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows SHOCK in the phone status cluster, before the alarm and killswitch chips', () => {
    const el = mount(true, shockState);
    const cluster = el.querySelector('header.topbar .status-cluster')!;
    expect(cluster.querySelector('sb-shock-pill .shock-pill')!.textContent!.trim()).toBe('SHOCK');
    const tags = [...cluster.children].map((c) => c.tagName.toLowerCase());
    expect(tags.indexOf('sb-shock-pill')).toBeGreaterThanOrEqual(0);
    expect(tags.indexOf('sb-shock-pill')).toBeLessThan(tags.indexOf('sb-alarm-chip'));
    expect(tags.indexOf('sb-shock-pill')).toBeLessThan(tags.indexOf('sb-killswitch-chip'));
  });

  it('shows RECOVERY on a phone too', () => {
    const el = mount(true, { ...shockState, label: 'RECOVERY' });
    expect(el.querySelector('.status-cluster .shock-pill')!.textContent!.trim()).toBe('RECOVERY');
  });

  it('shows no pill on NORMAL', () => {
    expect(mount(true, { ...shockState, label: 'NORMAL' }).querySelector('.shock-pill')).toBeNull();
  });

  it('shows no pill without a shock object (detector off)', () => {
    expect(mount(true, null).querySelector('.shock-pill')).toBeNull();
  });

  it('renders no pill above phone width: the tape badge covers it there', () => {
    expect(mount(false, shockState).querySelector('sb-shock-pill')).toBeNull();
  });
});

describe('shell voice notifications (v227)', () => {
  it('starts the voice notifier once, when the shell is created', () => {
    const start = vi.fn();
    TestBed.configureTestingModule({
      providers: [...shellProviders(), { provide: VoiceNotifier, useValue: { start } }],
    });
    createShell().detectChanges();
    expect(start).toHaveBeenCalledTimes(1);
  });

  it('mounts the chip after the viewer badge and before the alarm chip', () => {
    const html = readSource('src/app/shell/shell.html');
    const cluster = html.slice(html.indexOf('class="status-cluster"'));
    const at = (tag: string) => cluster.indexOf(tag);
    expect(at('<sb-voice-chip />')).toBeGreaterThan(at('<sb-read-only-badge'));
    expect(at('<sb-voice-chip />')).toBeGreaterThan(at('<sb-shock-pill'));
    expect(at('<sb-voice-chip />')).toBeLessThan(at('<sb-alarm-chip'));
  });

  it('never lets the chip shrink on a phone', () => {
    const css = readSource('src/app/shell/shell.css');
    const phone = css.slice(css.lastIndexOf('@media (max-width: 639px)'));
    expect(phone).toMatch(/sb-voice-chip \{[^}]*flex: none;/);
  });
});

describe('shell tab-bar editor (v240 §6)', () => {
  let phone: WritableSignal<boolean>;

  beforeEach(() => {
    installDialogPolyfill();
    phone = signal(true);
    TestBed.configureTestingModule({ providers: [...shellProviders([{ path: 'dashboard', component: Blank }]), provideMotion('off')] });
    TestBed.overrideProvider(ViewportService, { useValue: { isPhone: phone, isNarrow: signal(true), viewport: signal('xs') } });
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'admin', role: 'admin' });
  });

  async function settle(fixture: ComponentFixture<Shell>): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function openEditor() {
    const fixture = createShell();
    await settle(fixture);
    const el = fixture.nativeElement as HTMLElement;
    el.querySelector<HTMLButtonElement>('sb-phone-tab-bar button.more')!.click();
    await settle(fixture);
    const edit = el.querySelector<HTMLButtonElement>('sb-more-sheet button.edit')!;
    edit.click();
    await settle(fixture);
    return { fixture, el, edit };
  }

  const editorOpen = (el: HTMLElement) => el.querySelector('sb-tab-bar-editor dialog')?.hasAttribute('open') ?? false;
  const sheet = (el: HTMLElement) => el.querySelector('sb-more-sheet [role=dialog]');

  it('opens the editor over the More sheet; Escape leaves the sheet; Done returns focus to Edit tab bar', async () => {
    const { fixture, el, edit } = await openEditor();
    expect(editorOpen(el)).toBe(true);
    expect(sheet(el)).not.toBeNull();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(sheet(el)).not.toBeNull();
    el.querySelector<HTMLButtonElement>('sb-tab-bar-editor .actions button.done')!.click();
    await settle(fixture);
    expect(editorOpen(el)).toBe(false);
    expect(sheet(el)).not.toBeNull();
    expect(document.activeElement).toBe(edit);
  });

  it('shows an edit on the bar and in the More sheet at once', async () => {
    const { fixture, el } = await openEditor();
    el.querySelector<HTMLButtonElement>('sb-tab-bar-editor li[data-path="/watchlist"] button.remove')!.click();
    await settle(fixture);
    expect([...el.querySelectorAll('sb-phone-tab-bar .tab-label')].map((n) => n.textContent!.trim()))
      .toEqual(['Home', 'Trades', 'Calendar', 'More']);
    expect([...el.querySelectorAll('sb-more-sheet .group-label')].map((n) => n.textContent!.trim())).toContain('Watchlist');
  });

  it('closes the editor with its sheet when the window leaves phone width', async () => {
    const { fixture, el } = await openEditor();
    phone.set(false);
    await settle(fixture);
    expect(el.querySelector('sb-tab-bar-editor')).toBeNull();
    phone.set(true);
    await settle(fixture);
    expect(editorOpen(el)).toBe(false);
    expect(sheet(el)).toBeNull();
  });
});
