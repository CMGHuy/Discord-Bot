import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { SettingField } from '../../api/models';
import { RouteTitleService } from '../../routing/route-title.service';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { SystemStore } from '../../stores/system.store';
import { System } from './system';

async function mount(tab?: string): Promise<{ fixture: ComponentFixture<System>; el: HTMLElement }> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      SystemStore,
    ],
  });
  TestBed.inject(RouteTitleService).set('System', 'Settings, logs, scan control and provider health');
  const fixture = TestBed.createComponent(System);
  if (tab !== undefined) fixture.componentRef.setInput('tab', tab);
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

const tabLabels = (el: HTMLElement) =>
  [...el.querySelectorAll('[role="tab"]')].map((tab) => tab.textContent!.trim());

const selected = (el: HTMLElement) =>
  el.querySelector('[role="tab"][aria-selected="true"]')!.textContent!.trim();

describe('System tabs (v195 §5.1, correction 4)', () => {
  it('orders the bar Scan, Providers, Settings, Logs', async () => {
    const { el } = await mount();
    expect(tabLabels(el)).toEqual(['Scan', 'Providers', 'Settings', 'Logs']);
  });

  it('opens the Providers tab from ?tab=providers', async () => {
    const { el } = await mount('providers');
    expect(selected(el)).toBe('Providers');
    expect(el.querySelector('sb-providers-tab')).toBeTruthy();
    expect(el.querySelector('sb-scan-tab')).toBeNull();
  });

  it('lands on Settings with no ?tab=, though Scan is first in the bar', async () => {
    const { el } = await mount();
    expect(selected(el)).toBe('Settings');
    expect(el.querySelector('sb-settings-tab')).toBeTruthy();
  });

  it('falls back to Settings for an unknown ?tab=', async () => {
    const { el } = await mount('health');
    expect(selected(el)).toBe('Settings');
  });

  it('writes the tab to the URL, and drops it for Settings', async () => {
    const { fixture, el } = await mount();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const tab = (label: string) => [...el.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
      .find((button) => button.textContent!.trim() === label)!;

    tab('Providers').click();
    fixture.detectChanges();
    expect(navigate).toHaveBeenLastCalledWith([], expect.objectContaining({
      queryParams: { tab: 'providers' }, queryParamsHandling: 'merge', replaceUrl: true,
    }));

    tab('Settings').click();
    fixture.detectChanges();
    expect(navigate).toHaveBeenLastCalledWith([], expect.objectContaining({
      queryParams: { tab: null },
    }));
  });
});

/* -- v195 Phase 4 and §5.2 -- System on sb-page, destructive commands in the header -- */

function field(key: string): SettingField {
  return {
    key, label: key, type: 'str', value: 'x', default: 'x', help: '',
    min: null, max: null, step: null, options: [], sensitive: false, hot_reloadable: true,
  };
}

const settingsPayload = (restartAvailable: boolean) => ({
  sections: [{ name: 'Discord', icon: 'settings', description: '', fields: [field('discord')] }],
  audit: [],
  restart_available: restartAvailable,
});

async function settle(fixture: ComponentFixture<System>): Promise<void> {
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
}

const actions = (el: HTMLElement) =>
  [...el.querySelectorAll<HTMLButtonElement>('sb-page header.bar .actions button')];

const openDialog = (el: HTMLElement) => el.querySelector('dialog[open]');

function confirmButton(el: HTMLElement, label: string): HTMLButtonElement {
  return [...openDialog(el)!.querySelectorAll<HTMLButtonElement>('button')]
    .find((button) => button.textContent!.trim() === label)!;
}

describe('System on sb-page (v195 Phase 4, §5.2)', () => {
  beforeAll(() => installDialogPolyfill());

  it('renders the page title as the one h1, the tab bar in the scope bar and the tab as primary', async () => {
    const { el } = await mount();
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('System');
    expect(el.querySelector('sb-page .scope sb-tab-bar')).toBeTruthy();
    expect(el.querySelector('sb-page .primary sb-settings-tab')).toBeTruthy();
    expect(el.querySelector('sb-section-head')).toBeNull();
  });

  it('puts Clear log in the header on Logs, behind a dialog that names the file', async () => {
    const { fixture, el } = await mount('logs');
    const backend = TestBed.inject(HttpTestingController);
    TestBed.inject(SystemStore).loadLogs();
    backend.expectOne((r) => r.method === 'GET' && r.url === '/api/v1/system/logs').flush({
      source: 'bot', lines: 500, path: 'logs/bot.log', content: 'started',
    });
    await settle(fixture);

    const [clear] = actions(el);
    expect(clear.textContent!.trim()).toBe('Clear log');
    expect(clear.dataset['action']).toBe('clear-log');
    expect(clear.classList).toContain('danger-quiet');

    clear.click();
    await settle(fixture);
    expect(openDialog(el)!.textContent).toContain('logs/bot.log will be emptied');

    confirmButton(el, 'Clear').click();
    await settle(fixture);
    const request = backend.expectOne((r) => r.method === 'DELETE' && r.url === '/api/v1/system/logs');
    expect(request.request.params.get('source')).toBe('bot');
    request.flush({ ok: true, message: 'Cleared logs/bot.log' });
    backend.match((r) => r.method === 'GET' && r.url === '/api/v1/system/logs');
    await settle(fixture);
    expect(openDialog(el)).toBeNull();
  });

  it('puts Restart bot in the header on Scan where the deployment can restart, and confirms it', async () => {
    const { fixture, el } = await mount('scan');
    const backend = TestBed.inject(HttpTestingController);
    TestBed.inject(SystemStore).loadSettings();
    backend.expectOne('/api/v1/system/settings').flush(settingsPayload(true));
    await settle(fixture);

    const [restart] = actions(el);
    expect(restart.textContent!.trim()).toBe('Restart bot');
    expect(restart.classList).toContain('danger-quiet');

    restart.click();
    await settle(fixture);
    expect(openDialog(el)!.textContent).toContain('Restart the bot');
    const confirm = confirmButton(el, 'Restart');
    expect(confirm.classList).toContain('danger-quiet');

    confirm.click();
    await settle(fixture);
    backend.expectOne('/api/v1/system/bot/restart').flush({ message: 'Restarting the bot.' });
    await settle(fixture);
    expect(el.textContent).toContain('Restarting the bot.');
  });

  it('offers no restart where the deployment cannot, and says so in the tab', async () => {
    const { fixture, el } = await mount('scan');
    TestBed.inject(SystemStore).loadSettings();
    TestBed.inject(HttpTestingController)
      .expectOne('/api/v1/system/settings').flush(settingsPayload(false));
    await settle(fixture);

    expect(actions(el)).toHaveLength(0);
    expect(el.textContent).toContain('Restarting is unavailable in this deployment');
  });

  it('puts Discard in the header only while there are unsaved settings, and discards on confirm', async () => {
    const { fixture, el } = await mount();
    const store = TestBed.inject(SystemStore);
    store.loadSettings();
    TestBed.inject(HttpTestingController)
      .expectOne('/api/v1/system/settings').flush(settingsPayload(false));
    await settle(fixture);
    expect(actions(el)).toHaveLength(0);
    expect(el.querySelector('.page-actions .dirty')).toBeNull();

    store.edit(store.fields()[0], 'changed');
    await settle(fixture);
    expect(el.querySelector('sb-page header.bar .actions .dirty')!.textContent!.trim())
      .toBe('Unsaved settings');
    const [discard] = actions(el);
    expect(discard.textContent!.trim()).toBe('Discard changes');
    expect(discard.classList).toContain('danger-quiet');

    discard.click();
    await settle(fixture);
    expect(openDialog(el)!.textContent).toContain('Discard unsaved settings?');
    confirmButton(el, 'Discard changes').click();
    await settle(fixture);

    expect(store.dirty()).toBe(false);
    expect(actions(el)).toHaveLength(0);
  });

  it('cancelling a dialog runs nothing', async () => {
    const { fixture, el } = await mount('logs');
    const backend = TestBed.inject(HttpTestingController);
    actions(el)[0].click();
    await settle(fixture);
    confirmButton(el, 'Cancel').click();
    await settle(fixture);

    backend.expectNone((r) => r.method === 'DELETE');
  });

  it('puts no command in the header on Providers', async () => {
    const { el } = await mount('providers');
    expect(actions(el)).toHaveLength(0);
  });

  it('keeps every destructive control and its dialog out of the tab bodies', () => {
    for (const file of ['scan-tab.ts', 'logs-tab.ts', 'settings-tab.ts', 'providers-tab.ts']) {
      const src = readFileSync(join(process.cwd(), 'src/app/workspaces/system', file), 'utf8');
      expect(src, file).not.toMatch(/variant="danger/);
      expect(src, file).not.toContain('<sb-confirm-dialog');
    }
  });
});
