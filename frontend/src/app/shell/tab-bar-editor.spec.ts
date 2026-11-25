import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SessionStore } from '../stores/session.store';
import { installDialogPolyfill } from '../testing/dialog-polyfill';
import { ViewportService } from '../ui/breakpoints';
import { provideMotion } from '../ui/motion/motion.service';
import { navEntriesFor } from './nav';
import { TAB_BAR_PREF_KEY, TAB_BAR_STORAGE } from './tab-bar-prefs';
import { ADD_LIMIT_REASON, TabBarEditor, UNDO_MS } from './tab-bar-editor';

type List = 'on-bar' | 'under-more';
type Action = 'up' | 'down' | 'remove' | 'add';

let stored: Map<string, string>;

function mount(role: 'admin' | 'viewer' = 'admin', saved?: string) {
  installDialogPolyfill();
  stored = new Map(saved === undefined ? [] : [[TAB_BAR_PREF_KEY, saved]]);
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideMotion('off'),
      { provide: ViewportService, useValue: { isPhone: () => true } },
      {
        provide: TAB_BAR_STORAGE,
        useValue: { get: (key: string) => stored.get(key) ?? null, set: (key: string, value: string) => void stored.set(key, value) },
      },
    ],
  });
  patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: role, role });
  const fixture = TestBed.createComponent(TabBarEditor);
  fixture.componentRef.setInput('open', true);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

const text = (node: Element) => node.textContent!.trim();
const labels = (el: HTMLElement, list: List) => [...el.querySelectorAll(`.${list} .row-label`)].map(text);
const rowPaths = (el: HTMLElement, list: List) =>
  [...el.querySelectorAll(`.${list} li.row`)].map((row) => row.getAttribute('data-path')!);
const button = (el: HTMLElement, path: string, action: Action) =>
  el.querySelector<HTMLButtonElement>(`li[data-path="${path}"] button.${action}`)!;
const announced = (el: HTMLElement) => text(el.querySelector('.announce')!);
const savedPaths = () => JSON.parse(stored.get(TAB_BAR_PREF_KEY)!) as string[];

function press(fixture: ComponentFixture<TabBarEditor>, target: HTMLButtonElement): void {
  target.click();
  fixture.detectChanges();
}

describe('TabBarEditor (v240 §6)', () => {
  it('is an sb-drawer headed Edit tab bar, with nothing rendered while closed', () => {
    const { fixture, el } = mount();
    expect(text(el.querySelector('sb-drawer h2')!)).toBe('Edit tab bar');
    expect(el.querySelector('dialog')!.open).toBe(true);
    fixture.componentRef.setInput('open', false);
    fixture.detectChanges();
    expect(el.querySelector('dialog')!.open).toBe(false);
    expect(el.querySelector('.editor')).toBeNull();
  });

  it('lists the bar in order, Home pinned first with no buttons', () => {
    const { el } = mount();
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    const home = el.querySelector('.on-bar li.row')!;
    expect(home.querySelectorAll('button')).toHaveLength(0);
    expect(text(home.querySelector('.pinned')!)).toBe('Always first');
    for (const path of ['/watchlist', '/trades', '/calendar']) {
      for (const action of ['up', 'down', 'remove'] as const) expect(button(el, path, action)).not.toBeNull();
    }
    expect(button(el, '/watchlist', 'up').getAttribute('aria-label')).toBe('Move Watchlist up');
    expect(button(el, '/watchlist', 'down').getAttribute('aria-label')).toBe('Move Watchlist down');
    expect(button(el, '/watchlist', 'remove').getAttribute('aria-label')).toBe('Remove Watchlist from the tab bar');
  });

  it('lists every other page under More, rail order and rail labels, each with an add button', () => {
    const { el } = mount();
    expect(labels(el, 'under-more')).toEqual(['Risk', 'Insights', 'System']);
    expect(rowPaths(el, 'under-more')).toEqual(['/risk', '/insights', '/system']);
    expect(button(el, '/risk', 'add').getAttribute('aria-label')).toBe('Add Risk to the tab bar');
  });

  it('marks up unavailable at position 2 and down at the last position, and those presses do nothing', () => {
    const { fixture, el } = mount();
    expect(button(el, '/watchlist', 'up').getAttribute('aria-disabled')).toBe('true');
    expect(button(el, '/calendar', 'down').getAttribute('aria-disabled')).toBe('true');
    expect(button(el, '/trades', 'up').hasAttribute('aria-disabled')).toBe(false);
    expect(button(el, '/watchlist', 'up').disabled).toBe(false);
    press(fixture, button(el, '/watchlist', 'up'));
    press(fixture, button(el, '/calendar', 'down'));
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    expect(announced(el)).toBe('');
    expect(stored.has(TAB_BAR_PREF_KEY)).toBe(false);
  });

  it('moves a page, saves it, announces its new position and keeps focus on the same button', () => {
    const { fixture, el } = mount();
    press(fixture, button(el, '/watchlist', 'down'));
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Trades', 'Watchlist', 'Calendar']);
    expect(savedPaths()).toEqual(['/dashboard', '/trades', '/watchlist', '/calendar']);
    expect(announced(el)).toBe('Watchlist moved to position 3');
    expect(document.activeElement).toBe(button(el, '/watchlist', 'down'));
    press(fixture, button(el, '/calendar', 'up'));
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Trades', 'Calendar', 'Watchlist']);
    expect(announced(el)).toBe('Calendar moved to position 3');
    expect(document.activeElement).toBe(button(el, '/calendar', 'up'));
  });

  it('removes a page to More in rail order, announces it and focuses its add button', () => {
    const { fixture, el } = mount();
    press(fixture, button(el, '/watchlist', 'remove'));
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Trades', 'Calendar']);
    expect(labels(el, 'under-more')).toEqual(['Watchlist', 'Risk', 'Insights', 'System']);
    expect(announced(el)).toBe('Watchlist moved to More');
    expect(document.activeElement).toBe(button(el, '/watchlist', 'add'));
  });

  it('shows the add-limit reason inline above Under More while the bar is full, and add does nothing', () => {
    const { fixture, el } = mount();
    const reason = el.querySelector('p.reason')!;
    expect(text(reason)).toBe(ADD_LIMIT_REASON);
    expect(ADD_LIMIT_REASON).toBe('The bar holds 4 pages. Remove one to add another.');
    const underMore = el.querySelector('ul.under-more')!;
    expect(reason.compareDocumentPosition(underMore) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const add = button(el, '/risk', 'add');
    expect(add.getAttribute('aria-disabled')).toBe('true');
    expect(add.getAttribute('aria-describedby')).toBe(reason.id);
    press(fixture, add);
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    expect(announced(el)).toBe('');
  });

  it('adds once there is room: the reason goes, the page joins the end and its remove button takes focus', () => {
    const { fixture, el } = mount();
    press(fixture, button(el, '/watchlist', 'remove'));
    expect(el.querySelector('p.reason')).toBeNull();
    expect(button(el, '/risk', 'add').hasAttribute('aria-disabled')).toBe(false);
    expect(button(el, '/risk', 'add').hasAttribute('aria-describedby')).toBe(false);
    press(fixture, button(el, '/risk', 'add'));
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Trades', 'Calendar', 'Risk']);
    expect(savedPaths()).toEqual(['/dashboard', '/trades', '/calendar', '/risk']);
    expect(announced(el)).toBe('Risk added to the tab bar');
    expect(document.activeElement).toBe(button(el, '/risk', 'remove'));
  });

  it('carries the announcements in one polite live region, last in the editor', () => {
    const { el } = mount();
    const regions = el.querySelectorAll('[aria-live]');
    expect(regions).toHaveLength(1);
    expect(regions[0].getAttribute('aria-live')).toBe('polite');
    expect(regions[0].classList).toContain('announce');
    expect(el.querySelector('.editor')!.lastElementChild).toBe(regions[0]);
  });

  it('reports one close when the drawer closes itself (its × button)', () => {
    const { fixture, el } = mount();
    let closed = 0;
    fixture.componentInstance.closed.subscribe(() => (closed += 1));
    el.querySelector<HTMLButtonElement>('sb-drawer header button.close')!.click();
    fixture.detectChanges();
    expect(closed).toBe(1);
  });
});

describe('TabBarEditor preview and edge cases (v240 §6, §8)', () => {
  it('previews the bar it edits, More last, and follows every edit', () => {
    const { fixture, el } = mount();
    const preview = el.querySelector('figure.preview')!;
    expect(el.querySelector('.editor')!.firstElementChild).toBe(preview);
    expect(preview.getAttribute('role')).toBe('img');
    expect(preview.getAttribute('aria-label')).toBe('Tab bar preview: Home, Watchlist, Trades, Calendar, More');
    expect([...preview.querySelectorAll('.preview-label')].map(text)).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar', 'More']);
    press(fixture, button(el, '/trades', 'remove'));
    expect(preview.getAttribute('aria-label')).toBe('Tab bar preview: Home, Watchlist, Calendar, More');
    expect([...preview.querySelectorAll('.preview-label')].map(text)).toEqual(['Home', 'Watchlist', 'Calendar', 'More']);
  });

  it('holds the minimum bar, Home alone, with every other page under More and no reason', () => {
    const { el } = mount('admin', '["/dashboard"]');
    expect(labels(el, 'on-bar')).toEqual(['Home']);
    expect(el.querySelectorAll('.on-bar button')).toHaveLength(0);
    expect(labels(el, 'under-more')).toEqual(['Watchlist', 'Trades', 'Calendar', 'Risk', 'Insights', 'System']);
    expect(el.querySelector('p.reason')).toBeNull();
    expect(el.querySelector('figure.preview')!.getAttribute('aria-label')).toBe('Tab bar preview: Home, More');
  });

  it('never shows a viewer System, even when the stored bar holds it', () => {
    const { el } = mount('viewer', '["/dashboard","/system"]');
    expect(labels(el, 'on-bar')).toEqual(['Home']);
    expect(labels(el, 'under-more')).toEqual(['Watchlist', 'Trades', 'Calendar', 'Risk', 'Insights']);
    expect(el.querySelector('[data-path="/system"]')).toBeNull();
  });
});

describe('TabBarEditor partition (v240 §6 "Risk is never out of reach", §11)', () => {
  const STORED: [string, string | undefined][] = [
    ['nothing', undefined],
    ['Home alone', '["/dashboard"]'],
    ['System and two more', '["/dashboard","/system","/insights","/risk"]'],
    ['an old Calendar path', '["/dashboard","/trades/calendar"]'],
    ['not JSON', 'not json'],
    ['an empty list', '[]'],
  ];

  for (const role of ['admin', 'viewer'] as const) {
    it.each(STORED)(`${role}, stored %s: every page the login may open is in exactly one list`, (_name, value) => {
      const { el } = mount(role, value);
      const all = [...rowPaths(el, 'on-bar'), ...rowPaths(el, 'under-more')];
      expect(new Set(all).size).toBe(all.length);
      expect([...all].sort()).toEqual(navEntriesFor(role === 'admin').map((entry) => entry.path).sort());
      expect(rowPaths(el, 'on-bar')[0]).toBe('/dashboard');
      expect(all).toContain('/risk');
      if (role === 'viewer') expect(all).not.toContain('/system');
    });
  }

  it('keeps the partition through a remove and an add', () => {
    const { fixture, el } = mount();
    press(fixture, button(el, '/watchlist', 'remove'));
    press(fixture, button(el, '/risk', 'add'));
    const all = [...rowPaths(el, 'on-bar'), ...rowPaths(el, 'under-more')];
    expect([...all].sort()).toEqual(navEntriesFor(true).map((entry) => entry.path).sort());
    expect(rowPaths(el, 'on-bar')).toEqual(['/dashboard', '/trades', '/calendar', '/risk']);
  });
});

describe('TabBarEditor styles (v240 §6, §9)', () => {
  const source = readFileSync(join(process.cwd(), 'src/app/shell/tab-bar-editor.ts'), 'utf8');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const rule = (selector: string) => source.match(new RegExp(`^\\s*${esc(selector)} \\{[^}]*\\}`, 'm'))?.[0] ?? '';

  it('gives every row button and every row a 44px target at every width', () => {
    expect(rule('.act')).toContain('min-width: 44px');
    expect(rule('.act')).toContain('min-height: 44px');
    expect(rule('.row')).toContain('min-height: 44px');
  });

  it('never fixes a width, so the drawer sets it (sheet below 640px, 85vw, then 480px)', () => {
    expect(source).not.toMatch(/(?:^|[\s;{])width:\s*\d/m);
  });

  it('wraps a long row label, shares the preview equally, and reads no faint text token', () => {
    expect(rule('.row-label')).toContain('overflow-wrap: anywhere');
    expect(rule('.row-label')).toContain('min-width: 0');
    expect(rule('.preview')).toContain('grid-auto-columns: minmax(0, 1fr)');
    expect(rule('.preview-label')).toContain('text-overflow: ellipsis');
    expect(source).not.toContain('--text-faint');
  });

  it('marks an unavailable button without the disabled attribute, and rounds with tokens only', () => {
    expect(source).toContain(".act[aria-disabled='true']");
    expect(source).not.toMatch(/border-radius:\s*\d+px/);
  });
});

describe('TabBarEditor Reset, Undo and Done (v240 §6, Decision 15)', () => {
  // Spies first, clock second: a setTimeout spy taken while the clock is fake
  // would otherwise be restored after useRealTimers, putting the dead fake
  // setTimeout back on globalThis and hanging every later spec file's timers.
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  const action = (el: HTMLElement, name: 'reset' | 'undo' | 'done') =>
    el.querySelector<HTMLButtonElement>(`.actions button.${name}`);

  it('pins the Undo window at 8 seconds and puts Reset, Done in one wrapping row before the live region', () => {
    const { el } = mount('admin', '["/dashboard","/risk"]');
    expect(UNDO_MS).toBe(8000);
    expect(text(action(el, 'reset')!)).toBe('Reset');
    expect(text(action(el, 'done')!)).toBe('Done');
    expect(action(el, 'undo')).toBeNull();
    expect(el.querySelector('.actions')!.nextElementSibling!.classList).toContain('announce');
  });

  it('marks Reset unavailable on the default bar, and that press does nothing', () => {
    const { fixture, el } = mount();
    expect(action(el, 'reset')!.getAttribute('aria-disabled')).toBe('true');
    press(fixture, action(el, 'reset')!);
    expect(announced(el)).toBe('');
    expect(action(el, 'undo')).toBeNull();
  });

  it('resets to the default, saves and announces it, and offers Undo for exactly 8 seconds', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, el } = mount('admin', '["/dashboard","/risk"]');
    press(fixture, action(el, 'reset')!);
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    expect(savedPaths()).toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
    expect(announced(el)).toBe('Tab bar reset to default');
    expect(action(el, 'undo')).not.toBeNull();
    vi.advanceTimersByTime(UNDO_MS - 1);
    fixture.detectChanges();
    expect(action(el, 'undo')).not.toBeNull();
    vi.advanceTimersByTime(1);
    fixture.detectChanges();
    expect(action(el, 'undo')).toBeNull();
  });

  it('Undo restores the bar from before the reset, announces it and hands focus to Reset', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, el } = mount('admin', '["/dashboard","/risk"]');
    const set = vi.spyOn(globalThis, 'setTimeout');
    const clear = vi.spyOn(globalThis, 'clearTimeout');
    press(fixture, action(el, 'reset')!);
    const undoTimer = set.mock.results[set.mock.calls.findIndex((call) => call[1] === UNDO_MS)].value;
    press(fixture, action(el, 'undo')!);
    expect(labels(el, 'on-bar')).toEqual(['Home', 'Risk']);
    expect(savedPaths()).toEqual(['/dashboard', '/risk']);
    expect(announced(el)).toBe('Tab bar restored');
    expect(action(el, 'undo')).toBeNull();
    expect(document.activeElement).toBe(action(el, 'reset'));
    expect(clear).toHaveBeenCalledWith(undoTimer);
  });

  it('an Undo that expires while focused hands focus to Reset', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, el } = mount('admin', '["/dashboard","/risk"]');
    press(fixture, action(el, 'reset')!);
    action(el, 'undo')!.focus();
    vi.advanceTimersByTime(UNDO_MS);
    fixture.detectChanges();
    expect(document.activeElement).toBe(action(el, 'reset'));
  });

  it('Done closes once, keeps the edits and clears a pending Undo', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, el } = mount('admin', '["/dashboard","/risk"]');
    let closed = 0;
    fixture.componentInstance.closed.subscribe(() => (closed += 1));
    const base = vi.getTimerCount();
    press(fixture, action(el, 'reset')!);
    press(fixture, action(el, 'done')!);
    expect(closed).toBe(1);
    expect(savedPaths()).toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
    expect(vi.getTimerCount()).toBe(base);
  });

  it('closing the editor clears a pending Undo, so reopening shows none', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, el } = mount('admin', '["/dashboard","/risk"]');
    const base = vi.getTimerCount();
    press(fixture, action(el, 'reset')!);
    fixture.componentRef.setInput('open', false);
    fixture.detectChanges();
    expect(vi.getTimerCount()).toBe(base);
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    expect(action(el, 'undo')).toBeNull();
  });

  it('gives the action buttons a 44px target at every width', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/tab-bar-editor.ts'), 'utf8');
    expect(source).toMatch(/^\s*\.actions button \{[^}]*min-height: 44px/m);
    expect(source).toMatch(/^\s*\.actions \{[^}]*flex-wrap: wrap/m);
  });
});
