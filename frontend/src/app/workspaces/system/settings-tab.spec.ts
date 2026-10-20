import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { SettingField, Settings } from '../../api/models';
import { SystemStore } from '../../stores/system.store';
import { SettingsTab } from './settings-tab';

function payload(overrides: Partial<Settings> = {}): Settings {
  return { sections: [], audit: [], restart_available: false, ...overrides };
}

/** SystemStore's onInit fires all three of settings/logs/scan together
 *  regardless of which tab component is under test. */
function flushOtherFetches(backend: HttpTestingController): void {
  backend
    .expectOne((r) => r.url === '/api/v1/system/logs')
    .flush({ source: 'bot', lines: 500, path: 'logs/bot.log', content: '' });
  backend
    .expectOne((r) => r.url === '/api/v1/system/scan')
    .flush({ status: 'idle' } as never);
}

function seed(): { fixture: ComponentFixture<SettingsTab>; backend: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      SystemStore,
    ],
  });
  const store = TestBed.inject(SystemStore);
  store.loadSettings();
  const fixture = TestBed.createComponent(SettingsTab);
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

describe('SettingsTab states', () => {
  it('shows a skeleton while loading, before the first response', () => {
    const { fixture } = seed();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeTruthy();
  });

  it('shows the error state on a first-load failure', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend
      .expectOne('/api/v1/system/settings')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.failed')).toBeTruthy();
  });

  it('shows the schema with no skeleton once settings has loaded', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/system/settings').flush(payload());
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeNull();
    expect(el.querySelector('.failed')).toBeNull();
  });
});

/* -- v95 D3 -- touch targets and a collapsing field grid -------------------- */

describe('System settings touch targets', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/system/settings-tab.ts'), 'utf8');

  // .restart is a status pill ("Restart required to take effect"), not a
  // button -- a plain <span> with no click handler and cursor: help. Only
  // .reset (a real per-field button, store.resetField(field)) needs the
  // shared control height; the plan's own sketch named .restart too, but
  // inflating a non-interactive span to 44px has nothing to accomplish.
  it('.reset meets the shared control height', () => {
    const rule = src.match(/\.reset\s*\{[^}]*\}/s)?.[0] ?? '';
    expect(rule).toMatch(/min-height:\s*var\(--control-h\)/);
  });

  it('.restart stays a plain status pill, not a control', () => {
    expect(src).toMatch(/<span class="restart"/);
  });

  it('field grid collapses rather than overflowing a narrow panel', () => {
    expect(src).toMatch(/minmax\(\s*min\(100%,\s*260px\)/);
  });
});

/* -- v179 §6b.5 -- the settings category rail fades and reveals ----------- */

function field(key: string): SettingField {
  return {
    key, label: key, type: 'str', value: 'x', default: 'x', help: '',
    min: null, max: null, step: null, options: [], sensitive: false, hot_reloadable: true,
  };
}

const RAIL_SECTIONS = ['Discord', 'Scanning', 'Pipeline', 'Risk'].map((name) => ({
  name, icon: 'settings', description: '', fields: [field(name.toLowerCase())],
}));

function railGeometry(el: HTMLElement, scrollWidth: number, clientWidth: number, scrollLeft: number): void {
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth });
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(el, 'scrollLeft', { configurable: true, value: scrollLeft });
}

describe('Settings category rail (v179 §6b.5)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/system/settings-tab.ts'), 'utf8');
  let spy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    spy = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: spy });
  });

  afterEach(() => {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>)['scrollIntoView'];
  });

  async function loaded() {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/system/settings').flush(payload({ sections: RAIL_SECTIONS }));
    await fixture.whenStable();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    return { fixture, el, rail: el.querySelector('nav.category-rail') as HTMLElement };
  }

  it('fades the far edge while more categories sit off-screen', async () => {
    const { fixture, el, rail } = await loaded();
    railGeometry(rail, 700, 358, 0);
    rail.dispatchEvent(new Event('scroll'));
    fixture.detectChanges();
    const strip = el.querySelector('.rail-strip')!;
    expect(strip.classList).toContain('fade-end');
    expect(strip.classList).not.toContain('fade-start');
  });

  it('brings the chosen category into view along the rail', async () => {
    const { fixture, rail } = await loaded();
    railGeometry(rail, 700, 358, 0);
    const risk = [...rail.querySelectorAll('button')].find((b) => b.textContent!.includes('Risk'))!;
    risk.click();
    fixture.detectChanges();
    await fixture.whenStable();
    expect((spy.mock.contexts.at(-1) as HTMLElement).textContent).toContain('Risk');
  });

  it('draws the fades with the same gradient as sb-tab-bar', () => {
    expect(src).toMatch(/\.rail-strip::before \{[^}]*linear-gradient\(to right, var\(--bg\), transparent\)/);
    expect(src).toMatch(/\.rail-strip\.fade-start::before, \.rail-strip\.fade-end::after \{ opacity: 1; \}/);
  });

  it('re-measures on window resize and lets the strip shrink in the phone layout', () => {
    expect(src).toContain(`'(window:resize)': 'measureRail()'`);
    expect(src).toMatch(/\.rail-strip \{[^}]*min-width: 0;/);
  });
});
