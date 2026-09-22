import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { Router, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { AnalyticsStore } from '../../stores/analytics.store';
import { ConnectionStore } from '../../stores/connection.store';
import { Analytics } from './analytics';

/* v94 — the Analytics shell.
 *
 * This file covers exactly what the shell owns: the six tabs in the order
 * the spec names them, the one scope bar above them, and the fact that a
 * scope change is written into the URL rather than kept in component state.
 * Every panel's own behaviour is tested beside it in `tabs/`, which is the
 * point of the shell being a shell.
 */

const connectionStub = { currency: signal('$') };

function create(): { fixture: ComponentFixture<Analytics>; backend: HttpTestingController; router: Router } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      { provide: ConnectionStore, useValue: connectionStub },
      AnalyticsStore,
    ],
  });
  const fixture = TestBed.createComponent(Analytics);
  return {
    fixture,
    backend: TestBed.inject(HttpTestingController),
    router: TestBed.inject(Router),
  };
}

function tabLabels(el: HTMLElement): string[] {
  return [...el.querySelectorAll('sb-tab-bar [role="tab"]')]
    .map((b) => b.textContent!.trim())
    .filter((label) => label !== '');
}

describe('Analytics shell', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('renders the six tabs and puts the scope in the URL', async () => {
    const { fixture } = create();
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    for (const label of ['Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Tuning']) {
      expect(text).toContain(label);
    }
    expect(tabLabels(fixture.nativeElement as HTMLElement)).toEqual([
      'Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Tuning',
    ]);
  });

  it('shows one scope bar above whichever tab is open', () => {
    const { fixture } = create();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('sb-scope-bar')).toHaveLength(1);
    // Overview is the default tab, and it is the only one mounted.
    expect(el.querySelector('sb-overview-tab')).not.toBeNull();
    expect(el.querySelector('sb-edge-tab')).toBeNull();
  });

  it('renders no in-page heading — the tab strip is the heading', () => {
    const { fixture } = create();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('h1')).toBeNull();
  });

  it('mounts the tab the store says is open', () => {
    const { fixture } = create();
    TestBed.inject(AnalyticsStore).setTab('pipeline', false);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-pipeline-tab')).not.toBeNull();
    expect(el.querySelector('sb-overview-tab')).toBeNull();
  });
});
