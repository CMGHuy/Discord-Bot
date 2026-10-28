import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
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
