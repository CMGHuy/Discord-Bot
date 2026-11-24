import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { SessionStore } from '../stores/session.store';
import { DEFAULT_PHONE_TAB_PATHS } from './nav';
import { PhoneTabBar } from './phone-tab-bar';
import { TAB_BAR_PREF_KEY, TAB_BAR_STORAGE, TabBarPrefs } from './tab-bar-prefs';

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
});
