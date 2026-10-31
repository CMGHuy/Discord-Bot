import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { DENSITY_STORAGE } from '../../ui/density.service';
import { stripComments } from '../../ui/testing/all-sources';
import { CommandPalette, isPaletteShortcut, isTypingTarget, shortcutLabel } from './command-palette';

@Component({ template: '' })
class Blank {}

@Component({
  imports: [CommandPalette],
  template: `<sb-command-palette [open]="open()" (closed)="onClosed()" />`,
})
class Host {
  readonly open = signal(true);
  closes = 0;
  onClosed(): void {
    this.closes += 1;
    this.open.set(false);
  }
}

const TICKERS = {
  tickers: [
    { symbol: 'NVDA', company_name: 'NVIDIA Corp', open_trades: 1, closed_trades: 4 },
    { symbol: 'RIOT', company_name: 'Riot Platforms', open_trades: 0, closed_trades: 0 },
  ],
};
const TRADES = {
  items: [
    { id: '812', ticker: 'NVDA', status: 'ACTIVE', strategy: 'RSI', created_at: '2026-10-20T09:00:00Z', opened_at: '2026-10-20T14:30:00Z' },
    { id: '901', ticker: 'AMD', status: 'PENDING', strategy: 'Fibonacci', created_at: '2026-10-26T09:00:00Z', opened_at: null },
  ],
  total: 2, page: 1, per_page: 200,
};

describe('CommandPalette (v195 §3.1)', () => {
  let stored: Map<string, string>;

  beforeEach(() => {
    stored = new Map();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: '**', component: Blank }]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: DENSITY_STORAGE, useValue: { get: (k: string) => stored.get(k) ?? null, set: (k: string, v: string) => stored.set(k, v) } },
      ],
    });
  });

  afterEach(() => {
    delete document.documentElement.dataset['density'];
  });

  async function settle(fixture: ComponentFixture<Host>): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function mount(answer: 'ok' | 'fail' = 'ok') {
    const fixture = TestBed.createComponent(Host);
    await settle(fixture);
    const http = TestBed.inject(HttpTestingController);
    if (answer === 'ok') {
      http.expectOne((r) => r.url.endsWith('/watchlist/tickers')).flush(TICKERS);
      http.expectOne((r) => r.url.endsWith('/trades')).flush(TRADES);
    } else {
      for (const request of http.match(() => true)) {
        request.flush({ error: { code: 'unavailable', message: 'down' } }, { status: 503, statusText: 'Unavailable' });
      }
    }
    await settle(fixture);
    return { fixture, el: fixture.nativeElement as HTMLElement, host: fixture.componentInstance };
  }

  const field = (el: HTMLElement) => el.querySelector<HTMLInputElement>('input[role=combobox]')!;
  const options = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('[role=option]')];
  const optionLabels = (el: HTMLElement) => options(el).map((o) => o.querySelector('.label')!.textContent!.trim());
  const activeId = (el: HTMLElement) => field(el).getAttribute('aria-activedescendant');

  async function type(fixture: ComponentFixture<Host>, el: HTMLElement, text: string): Promise<void> {
    field(el).value = text;
    field(el).dispatchEvent(new Event('input'));
    await settle(fixture);
  }

  async function press(fixture: ComponentFixture<Host>, el: HTMLElement, key: string): Promise<void> {
    field(el).dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
    await settle(fixture);
  }

  it('renders nothing while closed and reads the index only when opened', async () => {
    const fixture = TestBed.createComponent(Host);
    fixture.componentInstance.open.set(false);
    await settle(fixture);
    const http = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[role=dialog]')).toBeNull();
    http.expectNone(() => true);

    fixture.componentInstance.open.set(true);
    await settle(fixture);
    expect(el.querySelector('[role=dialog]')!.getAttribute('aria-modal')).toBe('true');
    expect(http.match((r) => r.url.endsWith('/watchlist/tickers'))).toHaveLength(1);
    expect(document.activeElement).toBe(field(el));
    expect(field(el).getAttribute('aria-controls')).toBe('palette-results');
  });

  it('shows the rail pages and the most recent trades for an empty query', async () => {
    const { el } = await mount();
    const shown = optionLabels(el);
    expect(shown.slice(0, 3)).toEqual(['Dashboard', 'Watchlist', 'Risk']);
    expect(shown.slice(-2)).toEqual(['AMD #901', 'NVDA #812']);
    expect(shown).toHaveLength(13);
  });

  it('ranks as the query is typed, with the first result active', async () => {
    const { fixture, el } = await mount();
    await type(fixture, el, 'ri');
    expect(optionLabels(el).slice(0, 2)).toEqual(['RIOT', 'Risk']);
    expect(activeId(el)).toBe(options(el)[0].id);
    expect(options(el)[0].getAttribute('aria-selected')).toBe('true');
    expect(options(el)[1].getAttribute('aria-selected')).toBe('false');
    expect(options(el)[0].querySelector('.kind')!.textContent!.trim()).toBe('Ticker');
    expect(options(el)[0].querySelector('.sub')!.textContent!.trim()).toBe('Riot Platforms');
  });

  it('moves with the arrow keys and wraps at both ends', async () => {
    const { fixture, el } = await mount();
    await type(fixture, el, 'ri');
    const last = options(el).length - 1;
    await press(fixture, el, 'ArrowDown');
    expect(activeId(el)).toBe(options(el)[1].id);
    await press(fixture, el, 'ArrowUp');
    await press(fixture, el, 'ArrowUp');
    expect(activeId(el)).toBe(options(el)[last].id);
    await press(fixture, el, 'ArrowDown');
    expect(activeId(el)).toBe(options(el)[0].id);
  });

  it('opens the active page on Enter and closes', async () => {
    const { fixture, el, host } = await mount();
    await type(fixture, el, 'risk');
    await press(fixture, el, 'Enter');
    expect(TestBed.inject(Router).url).toBe('/risk');
    expect(host.closes).toBe(1);
    expect(el.querySelector('[role=dialog]')).toBeNull();
  });

  it('opens a ticker, a plan and a workspace tab at their routes, starting fresh each time', async () => {
    const { fixture, el, host } = await mount();
    const router = TestBed.inject(Router);
    const reopen = async () => {
      host.open.set(true);
      await settle(fixture);
      expect(field(el).value).toBe('');
    };

    await type(fixture, el, 'nvda');
    options(el)[0].click();
    await settle(fixture);
    expect(router.url).toBe('/watchlist/NVDA');

    await reopen();
    await type(fixture, el, '901');
    options(el)[0].click();
    await settle(fixture);
    expect(router.url).toBe('/plans/901');

    await reopen();
    await type(fixture, el, 'logs');
    await press(fixture, el, 'Enter');
    expect(router.url).toBe('/system?tab=logs');
    // Fresh cache: the three reopens read nothing again.
    TestBed.inject(HttpTestingController).expectNone(() => true);
  });

  it('applies a density preference in place, without navigating', async () => {
    const { fixture, el, host } = await mount();
    const router = TestBed.inject(Router);
    const before = router.url;
    await type(fixture, el, 'comf');
    expect(optionLabels(el)).toEqual(['Density: Comfortable']);
    await press(fixture, el, 'Enter');
    expect(document.documentElement.dataset['density']).toBe('comfortable');
    expect(stored.get('ui.density')).toBe('comfortable');
    expect(router.url).toBe(before);
    expect(host.closes).toBe(1);
  });

  it('closes on Escape, on the scrim and on Close', async () => {
    const { fixture, el, host } = await mount();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(host.closes).toBe(1);

    host.open.set(true);
    await settle(fixture);
    el.querySelector<HTMLElement>('.scrim')!.click();
    await settle(fixture);
    expect(host.closes).toBe(2);

    host.open.set(true);
    await settle(fixture);
    el.querySelector<HTMLButtonElement>('button.close')!.click();
    await settle(fixture);
    expect(host.closes).toBe(3);
  });

  it('keeps Tab inside the palette: field and Close, never the options', async () => {
    const { el } = await mount();
    const close = el.querySelector<HTMLButtonElement>('button.close')!;
    expect(options(el).every((o) => o.getAttribute('tabindex') === '-1')).toBe(true);
    close.focus();
    close.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }));
    expect(document.activeElement).toBe(field(el));
    field(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }));
    expect(document.activeElement).toBe(close);
  });

  it('says so when nothing matches, such as a symbol that is not on the watchlist', async () => {
    const { fixture, el } = await mount();
    await type(fixture, el, 'ZZZZ');
    expect(options(el)).toHaveLength(0);
    expect(el.querySelector('.none')!.textContent!.trim()).toBe('No matches for “ZZZZ”');
    expect(activeId(el)).toBeNull();
    await press(fixture, el, 'Enter');
    expect(el.querySelector('[role=dialog]')).not.toBeNull();
  });

  it('still serves pages and preferences when the index cannot be read, and says so in one line', async () => {
    const { fixture, el } = await mount('fail');
    expect(el.querySelector('.unavailable')!.textContent!.trim())
      .toBe('Tickers unavailable: pages and preferences still work.');
    expect(optionLabels(el)).toContain('Dashboard');
    await type(fixture, el, 'dense');
    expect(optionLabels(el)).toEqual(['Density: Dense']);
  });

  it('can only navigate and set density: it injects nothing that acts', () => {
    const source = stripComments(readFileSync(join(process.cwd(), 'src/app/shell/palette/command-palette.ts'), 'utf8'));
    const injected = [...source.matchAll(/inject\((\w+)\)/g)].map(([, name]) => name).sort();
    expect(injected).toEqual(['DensityService', 'Router', 'SearchIndexStore']);
    expect(source).not.toMatch(/ApiClient|EventStream|killswitch|restart|triggerScan|HttpClient/i);
  });
});

describe('palette keyboard helpers (v195 §3.1)', () => {
  const make = (html: string): Element => {
    const holder = document.createElement('div');
    holder.innerHTML = html;
    return holder.firstElementChild!;
  };

  it('treats text fields as typing targets, and nothing else', () => {
    expect(isTypingTarget(make('<input type="text">'))).toBe(true);
    expect(isTypingTarget(make('<input>'))).toBe(true);
    expect(isTypingTarget(make('<input type="search">'))).toBe(true);
    expect(isTypingTarget(make('<textarea></textarea>'))).toBe(true);
    expect(isTypingTarget(make('<select></select>'))).toBe(true);
    expect(isTypingTarget(make('<div contenteditable="true"><span>x</span></div>').firstElementChild)).toBe(true);
    expect(isTypingTarget(make('<input type="checkbox">'))).toBe(false);
    expect(isTypingTarget(make('<button>Go</button>'))).toBe(false);
    expect(isTypingTarget(make('<div contenteditable="false"></div>'))).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });

  it('opens on Ctrl+K or ⌘K anywhere, and on / only outside a text field', () => {
    const input = document.createElement('input');
    const shortcut = (init: KeyboardEventInit, target?: Element) => {
      const event = new KeyboardEvent('keydown', init);
      if (target) Object.defineProperty(event, 'target', { value: target });
      return isPaletteShortcut(event);
    };
    expect(shortcut({ key: 'k', ctrlKey: true })).toBe(true);
    expect(shortcut({ key: 'K', metaKey: true })).toBe(true);
    expect(shortcut({ key: 'k', ctrlKey: true }, input)).toBe(true);
    expect(shortcut({ key: 'k' })).toBe(false);
    expect(shortcut({ key: 'k', ctrlKey: true, altKey: true })).toBe(false);
    expect(shortcut({ key: '/' }, document.body)).toBe(true);
    expect(shortcut({ key: '/' }, input)).toBe(false);
    expect(shortcut({ key: '/', ctrlKey: true }, document.body)).toBe(false);
    expect(shortcut({ key: 'Enter' })).toBe(false);
  });

  it('names the shortcut for the platform', () => {
    expect(shortcutLabel('MacIntel')).toBe('⌘K');
    expect(shortcutLabel('iPhone')).toBe('⌘K');
    expect(shortcutLabel('Win32')).toBe('Ctrl K');
    expect(shortcutLabel('')).toBe('Ctrl K');
  });
});
