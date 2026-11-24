import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SessionStore } from '../stores/session.store';
import { DEFAULT_PHONE_TAB_PATHS } from './nav';
import { PhoneTabBar } from './phone-tab-bar';
import { TAB_BAR_PREF_KEY, TAB_BAR_STORAGE, TabBarPrefs } from './tab-bar-prefs';
import { POPOVER_OPEN_ATTR } from '../testing/popover-polyfill';
import { HINT_HOVER_DELAY_MS } from '../ui/hint';
import { LONG_PRESS_MS } from '../ui/long-press';

@Component({ template: '' })
class Blank {}

describe('PhoneTabBar (v195 Phase 3, v240 §6)', () => {
  let stored: Map<string, string>;

  beforeEach(() => {
    stored = new Map<string, string>();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: '**', component: Blank }]),
        { provide: TAB_BAR_STORAGE, useValue: { get: (key: string) => stored.get(key) ?? null, set: (key: string, value: string) => void stored.set(key, value) } },
      ],
    });
  });

  const labels = (el: HTMLElement) => [...el.querySelectorAll('.tab .tab-label')].map((n) => n.textContent!.trim());
  const moreLit = (el: HTMLElement) => el.querySelector('button.tab.more')!.classList.contains('active');
  const styles = () => readFileSync(join(process.cwd(), 'src/app/shell/phone-tab-bar.ts'), 'utf8');
  /** One CSS rule of the component's styles block, by its exact selector. */
  const rule = (selector: string) =>
    styles().match(new RegExp(`^\\s*${selector.replace(/[.*]/g, '\\$&')} \\{[^}]*\\}`, 'm'))?.[0] ?? '';

  async function mount(url: string, moreOpen = false) {
    await TestBed.inject(Router).navigateByUrl(url);
    const fixture = TestBed.createComponent(PhoneTabBar);
    fixture.componentRef.setInput('moreOpen', moreOpen);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  const current = (el: HTMLElement) =>
    [...el.querySelectorAll('a.tab[aria-current="page"]')].map((a) => a.querySelector('.tab-label')!.textContent!.trim());

  it('holds the pages stored for this browser, in their order, then More', async () => {
    stored.set(TAB_BAR_PREF_KEY, '["/dashboard","/risk"]');
    const { el } = await mount('/dashboard');
    expect(labels(el)).toEqual(['Home', 'Risk', 'More']);
    expect([...el.querySelectorAll('a.tab')].map((a) => a.getAttribute('href'))).toEqual(['/dashboard', '/risk']);
  });

  it('falls back to the default bar when the stored value is junk', async () => {
    stored.set(TAB_BAR_PREF_KEY, '{not json');
    const { el } = await mount('/dashboard');
    expect(labels(el)).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar', 'More']);
    expect([...el.querySelectorAll('a.tab')].map((a) => a.getAttribute('href'))).toEqual([...DEFAULT_PHONE_TAB_PATHS]);
  });

  it('never shows a stored System tab to a viewer, and shows it to an admin', async () => {
    stored.set(TAB_BAR_PREF_KEY, '["/dashboard","/system"]');
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'viewer', role: 'viewer' });
    const { fixture, el } = await mount('/dashboard');
    expect(labels(el)).toEqual(['Home', 'More']);
    patchState(unprotected(TestBed.inject(SessionStore)), { role: 'admin' });
    fixture.detectChanges();
    expect(labels(el)).toEqual(['Home', 'System', 'More']);
  });

  it('follows an edit at once, and lights a page once the bar holds it', async () => {
    const { fixture, el } = await mount('/risk');
    expect(current(el)).toEqual([]);
    expect(moreLit(el)).toBe(true);
    const prefs = TestBed.inject(TabBarPrefs);
    prefs.remove('/watchlist');
    prefs.add('/risk');
    fixture.detectChanges();
    expect(labels(el)).toEqual(['Home', 'Trades', 'Calendar', 'Risk', 'More']);
    expect(current(el)).toEqual(['Risk']);
    expect(moreLit(el)).toBe(false);
  });

  it('lights More for a calendar day once Calendar left the bar', async () => {
    stored.set(TAB_BAR_PREF_KEY, '["/dashboard","/trades"]');
    const { el } = await mount('/calendar/2026-10-01');
    expect(current(el)).toEqual([]);
    expect(moreLit(el)).toBe(true);
  });

  it('holds Home, Watchlist, Trades, Calendar and More, in that order (v240 §6)', async () => {
    const { el } = await mount('/dashboard');
    expect(el.querySelector('nav')!.getAttribute('aria-label')).toBe('Main pages');
    expect([...el.querySelectorAll('.tab .tab-label')].map((n) => n.textContent!.trim()))
      .toEqual(['Home', 'Watchlist', 'Trades', 'Calendar', 'More']);
    expect([...el.querySelectorAll('a.tab')].map((a) => a.getAttribute('href')))
      .toEqual([...DEFAULT_PHONE_TAB_PATHS]);
  });

  it('marks the current tab, and the list tab for its detail pages', async () => {
    expect(current((await mount('/calendar')).el)).toEqual(['Calendar']);
    expect(current((await mount('/plans/7')).el)).toEqual(['Trades']);
    expect(current((await mount('/watchlist/NVDA')).el)).toEqual(['Watchlist']);
  });

  it('lights Calendar on a calendar day and Trades on the trade book', async () => {
    for (const url of ['/calendar', '/calendar/2026-10-01', '/calendar?month=2026-11']) {
      expect(current((await mount(url)).el), url).toEqual(['Calendar']);
    }
    for (const url of ['/trades', '/trades/812']) {
      expect(current((await mount(url)).el), url).toEqual(['Trades']);
    }
  });

  it('lights More on Risk, which the bar no longer holds', async () => {
    const { el } = await mount('/risk');
    expect(current(el)).toEqual([]);
    expect(el.querySelector('button.tab.more')!.classList).toContain('active');
  });

  it('lights More on a System section', async () => {
    const { el } = await mount('/system/versions');
    expect(current(el)).toEqual([]);
    expect(el.querySelector('button.tab.more')!.classList).toContain('active');
  });

  it('lights More for a page the bar does not hold', async () => {
    const { el } = await mount('/insights/analytics');
    expect(current(el)).toEqual([]);
    expect(el.querySelector('button.tab.more')!.classList).toContain('active');
  });

  it('asks for the More sheet and reports it open', async () => {
    const { fixture, el } = await mount('/dashboard');
    let asked = 0;
    fixture.componentInstance.moreRequested.subscribe(() => (asked += 1));
    const more = el.querySelector<HTMLButtonElement>('button.tab.more')!;
    expect(more.getAttribute('aria-haspopup')).toBe('dialog');
    expect(more.getAttribute('aria-expanded')).toBe('false');
    expect(more.classList).not.toContain('active');
    more.click();
    expect(asked).toBe(1);
    fixture.componentRef.setInput('moreOpen', true);
    fixture.detectChanges();
    expect(more.getAttribute('aria-expanded')).toBe('true');
    expect(more.classList).toContain('active');
  });

  it('keeps every glyph out of the accessible name', async () => {
    const { el } = await mount('/dashboard');
    const icons = [...el.querySelectorAll('sb-icon')];
    expect(icons).toHaveLength(5);
    for (const icon of icons) {
      expect(icon.parentElement!.matches('.glyph[aria-hidden="true"]')).toBe(true);
    }
  });

  it('draws each tab icon at 24px, the tab-bar size (v240 §4)', async () => {
    const { el } = await mount('/dashboard');
    const svgs = [...el.querySelectorAll('sb-icon svg')];
    expect(svgs).toHaveLength(5);
    for (const svg of svgs) {
      expect(svg.getAttribute('width')).toBe('24');
      expect(svg.getAttribute('height')).toBe('24');
    }
  });

  it('sits on the bottom edge at 56px plus the safe-area inset, under the toasts', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/phone-tab-bar.ts'), 'utf8');
    expect(source).toContain('height: calc(56px + env(safe-area-inset-bottom));');
    expect(source).toContain('padding-bottom: env(safe-area-inset-bottom);');
    expect(source).toMatch(/:host \{[^}]*position: fixed;[^}]*z-index: 8;/s);
  });

  it('shares the width equally between however many tabs it holds (v240 §6)', () => {
    const bar = rule('.tabs');
    expect(bar).toContain('grid-auto-flow: column;');
    expect(bar).toContain('grid-auto-columns: minmax(0, 1fr);');
    expect(styles()).not.toMatch(/repeat\(5/);
    expect(rule('.tab')).toContain('min-width: 0;');
  });

  it('marks the active tab with the accent-soft pill and an accent icon, not a top border (v240 §6)', () => {
    const pill = rule('.glyph');
    expect(pill).toContain('border-radius: var(--pill-radius);');
    expect(pill).toContain('width: 48px;');
    expect(pill).toContain('height: 28px;');
    const active = rule('.tab.active .glyph');
    expect(active).toContain('background: var(--accent-soft);');
    expect(active).toContain('color: var(--accent);');
    expect(rule('.tab.active')).toContain('color: var(--text);');
    expect(styles()).not.toMatch(/border-top: 2px|border-top-color/);
  });

  it('labels every tab at the 12px micro size, weight 600, truncating rather than widening (Decision 8)', () => {
    const label = rule('.tab-label');
    for (const declaration of ['font-size: var(--text-micro);', 'font-weight: 600;', 'overflow: hidden;',
      'text-overflow: ellipsis;', 'white-space: nowrap;', 'max-width: 100%;']) {
      expect(label, declaration).toContain(declaration);
    }
    expect(styles()).not.toMatch(/11px|--text-faint/);
  });

  it('keeps the pill on the More button while the sheet is open', async () => {
    const { fixture, el } = await mount('/dashboard');
    fixture.componentRef.setInput('moreOpen', true);
    fixture.detectChanges();
    const more = el.querySelector('button.tab.more')!;
    expect(more.classList).toContain('active');
    expect(more.querySelector('.glyph')).not.toBeNull();
  });

  describe('press and hold (v240 §6, Decision 9)', () => {
    const root = document.documentElement;

    afterEach(() => {
      // Undo the viewport stub: the own properties shadow Element.prototype's getters.
      delete (root as unknown as Record<string, unknown>)['clientWidth'];
      delete (root as unknown as Record<string, unknown>)['clientHeight'];
    });

    const tabLink = (el: HTMLElement, path: string) => el.querySelector<HTMLAnchorElement>(`a.tab[href="${path}"]`)!;
    /** The role="tooltip" popover the tab's aria-describedby points at (its sb-hint). */
    const tooltipOf = (el: HTMLElement, link: Element) =>
      el.querySelector(`[id="${link.getAttribute('aria-describedby')}"]`) as HTMLElement;
    const isOpen = (tooltip: HTMLElement) => tooltip.hasAttribute(POPOVER_OPEN_ATTR);
    async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }) {
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();
    }

    /** jsdom has no PointerEvent: a MouseEvent carrying pointerType and pointerId
     *  is what sbLongPress reads (ui/long-press.spec.ts does the same). */
    function pointer(type: string, pointerType = 'touch'): MouseEvent {
      const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: 100, clientY: 810 });
      Object.defineProperty(event, 'pointerType', { value: pointerType });
      Object.defineProperty(event, 'pointerId', { value: 1 });
      return event;
    }

    /** Holds a pointer on the tab for LONG_PRESS_MS and lifts it. Only
     *  setTimeout is faked: the hint's requestAnimationFrame stays real. */
    async function hold(fixture: Parameters<typeof settle>[0], link: Element, pointerType = 'touch') {
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

    it('gives every tab one tooltip naming its page as the rail does, and More none', async () => {
      const { el } = await mount('/dashboard');
      const links = [...el.querySelectorAll('a.tab')];
      expect(links).toHaveLength(4);
      expect(links.map((link) => tooltipOf(el, link).textContent!.trim()))
        .toEqual(['Dashboard', 'Watchlist', 'Trades', 'Calendar']);
      for (const link of links) {
        expect(tooltipOf(el, link).getAttribute('role')).toBe('tooltip');
        expect(isOpen(tooltipOf(el, link))).toBe(false);
      }
      const more = el.querySelector('button.tab.more')!;
      expect(more.hasAttribute('aria-describedby')).toBe(false);
      expect(el.querySelectorAll('[role="tooltip"]')).toHaveLength(4);
    });

    it('names the tabs of a custom bar too', async () => {
      stored.set(TAB_BAR_PREF_KEY, '["/dashboard","/risk","/insights"]');
      const { el } = await mount('/dashboard');
      expect([...el.querySelectorAll('a.tab')].map((link) => tooltipOf(el, link).textContent!.trim()))
        .toEqual(['Dashboard', 'Risk', 'Insights']);
    });

    it('makes every tab a long-press host and the More button not one', async () => {
      const { el } = await mount('/dashboard');
      for (const link of el.querySelectorAll('a.tab')) expect(link.classList).toContain('sb-long-press');
      expect(el.querySelector('button.tab.more')!.classList).not.toContain('sb-long-press');
    });

    it('opens the tab tooltip on a 500ms touch hold and not a moment before', async () => {
      const { fixture, el } = await mount('/dashboard');
      const link = tabLink(el, '/calendar');
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

    it('keeps the held-open tooltip after the finger lifts, and swallows the click so it navigates nowhere', async () => {
      const { fixture, el } = await mount('/dashboard');
      const router = TestBed.inject(Router);
      const link = tabLink(el, '/trades');
      await hold(fixture, link);
      expect(isOpen(tooltipOf(el, link))).toBe(true);
      link.dispatchEvent(tap());
      await settle(fixture);
      expect(router.url).toBe('/dashboard');
      expect(isOpen(tooltipOf(el, link))).toBe(true);
    });

    it('closes the held-open tooltip on the next touch anywhere, and on Escape', async () => {
      const { fixture, el } = await mount('/dashboard');
      const link = tabLink(el, '/watchlist');
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

    it('never opens on a mouse held down, and that click still navigates', async () => {
      const { fixture, el } = await mount('/dashboard');
      const link = tabLink(el, '/trades');
      await hold(fixture, link, 'mouse');
      expect(isOpen(tooltipOf(el, link))).toBe(false);
      link.dispatchEvent(tap());
      await settle(fixture);
      expect(TestBed.inject(Router).url).toBe('/trades');
    });

    it('opens on a mouse hover only after the hover delay (Decision 6)', async () => {
      const { fixture, el } = await mount('/dashboard');
      const link = tabLink(el, '/watchlist');
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      try {
        link.dispatchEvent(new MouseEvent('mouseenter'));
        vi.advanceTimersByTime(HINT_HOVER_DELAY_MS - 1);
        fixture.detectChanges();
        expect(isOpen(tooltipOf(el, link))).toBe(false);
        vi.advanceTimersByTime(1);
      } finally {
        vi.useRealTimers();
      }
      await settle(fixture);
      expect(isOpen(tooltipOf(el, link))).toBe(true);
    });

    it('moves a held-open tooltip to the tab held next (one at a time)', async () => {
      const { fixture, el } = await mount('/dashboard');
      const first = tabLink(el, '/dashboard');
      const second = tabLink(el, '/calendar');
      await hold(fixture, first);
      expect(isOpen(tooltipOf(el, first))).toBe(true);
      await hold(fixture, second);
      expect(isOpen(tooltipOf(el, second))).toBe(true);
      expect(isOpen(tooltipOf(el, first))).toBe(false);
    });

    it('places the tooltip above its tab, centred, 8px off it', async () => {
      const { fixture, el } = await mount('/dashboard');
      const link = tabLink(el, '/watchlist');
      link.getBoundingClientRect = () =>
        ({ top: 788, bottom: 844, left: 78, right: 156, width: 78, height: 56, x: 78, y: 788, toJSON: () => ({}) }) as DOMRect;
      const pop = tooltipOf(el, link);
      Object.defineProperty(pop, 'offsetWidth', { configurable: true, value: 70 });
      Object.defineProperty(pop, 'offsetHeight', { configurable: true, value: 24 });
      Object.defineProperty(root, 'clientWidth', { configurable: true, value: 390 });
      Object.defineProperty(root, 'clientHeight', { configurable: true, value: 844 });
      await hold(fixture, link);
      expect(pop.style.top).toBe('756px');
      expect(pop.style.left).toBe('82px');
    });
  });
});
