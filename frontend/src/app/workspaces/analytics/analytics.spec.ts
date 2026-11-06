import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { Router, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { AnalyticsStore } from '../../stores/analytics.store';
import { ConnectionStore } from '../../stores/connection.store';
import { ANALYTICS_TAB_LIST, Analytics, visibleAnalyticsTabs } from './analytics';
import { analyticsTabFor } from './analytics.routes';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { RouteTitleService } from '../../routing/route-title.service';

import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { Role } from '../../api/models';
import { SessionStore } from '../../stores/session.store';

let role: Role = 'admin';
beforeEach(() => { role = 'admin'; });
function signInAs(as: Role): void {
  patchState(unprotected(TestBed.inject(SessionStore)), {
    status: 'authenticated', username: as === 'admin' ? 'admin' : 'viewer1', role: as,
  });
}

/* v94 — the Analytics shell.
 *
 * This file covers exactly what the shell owns: the seven tabs in the order
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
  signInAs(role);
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

  it('renders the seven tabs and puts the scope in the URL', async () => {
    const { fixture } = create();
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    for (const label of ['Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Tuning', 'Partials']) {
      expect(text).toContain(label);
    }
    expect(tabLabels(fixture.nativeElement as HTMLElement)).toEqual([
      'Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Tuning', 'Partials',
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

  it('renders the route title as the one h1, from sb-page', () => {
    const { fixture } = create();
    TestBed.inject(RouteTitleService).set('Analytics', 'What already happened, measured');
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Analytics');
  });

  it('mounts the Partials tab from the store', () => {
    const { fixture } = create();
    TestBed.inject(AnalyticsStore).setTab('partials', false);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('sb-partials-tab')).not.toBeNull();
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

/* -- v195 Phase 4 -- Analytics on sb-page ----------------------------------- */

describe('Analytics on sb-page (v195 Phase 4)', () => {
  it('puts the tab strip and the one scope bar in the scope slot, in that order', () => {
    const { fixture } = create();
    fixture.detectChanges();
    const scope = (fixture.nativeElement as HTMLElement).querySelector('sb-page [page-scope]')!;
    expect([...scope.children].map((c) => c.tagName.toLowerCase())).toEqual(['sb-tab-bar', 'sb-scope-bar']);
    expect(scope.querySelector('.danger, .danger-quiet')).toBeNull();
  });

  it('mounts the open tab in the primary slot, and has no header action or KPI slot', () => {
    const { fixture } = create();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-page [page-primary] sb-overview-tab')).not.toBeNull();
    expect(el.querySelector('[page-actions]')).toBeNull();
    expect(el.querySelector('[page-kpis]')).toBeNull();
  });

  it('imports Page', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/analytics.ts'), 'utf8');
    expect(src).toContain('<sb-page');
    expect(src).toMatch(/import \{ Page \} from '\.\.\/\.\.\/ui\/page';/);
  });
});

/* -- v207 -- Tuning is an admin tool (spec Decision 3) ------------------- */

describe('Analytics for a viewer (v207)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('lists Tuning for the admin and not for a viewer, order otherwise kept', () => {
    expect(visibleAnalyticsTabs(true).map((t) => t.id)).toEqual(ANALYTICS_TAB_LIST.map((t) => t.id));
    expect(visibleAnalyticsTabs(false).map((t) => t.id)).toEqual(
      ['overview', 'attribution', 'execution', 'edge', 'pipeline', 'partials']);
  });

  it('renders six tabs for a viewer and seven for the admin', () => {
    const asAdmin = create().fixture;
    asAdmin.detectChanges();
    expect(tabLabels(asAdmin.nativeElement as HTMLElement)).toContain('Tuning');
    role = 'viewer';
    const asViewer = create().fixture;
    asViewer.detectChanges();
    expect(tabLabels(asViewer.nativeElement as HTMLElement)).toEqual(
      ['Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Partials']);
  });

  it('resolves Overview for a viewer asking for tuning, and nothing else changes', () => {
    expect(analyticsTabFor('tuning', false)).toBe('overview');
    expect(analyticsTabFor('tuning', true)).toBe('tuning');
    for (const tab of ['overview', 'attribution', 'execution', 'edge', 'pipeline', 'partials'] as const) {
      expect(analyticsTabFor(tab, false)).toBe(tab);
    }
  });

  it('rewrites ?tab=tuning away for a viewer, and leaves it for the admin', async () => {
    const arrive = async () => {
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
      signInAs(role);
      const router = TestBed.inject(Router);
      await router.navigateByUrl('/?tab=tuning');
      const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
      TestBed.createComponent(Analytics).detectChanges();
      return navigate;
    };
    expect(await arrive()).not.toHaveBeenCalled();
    role = 'viewer';
    expect(await arrive()).toHaveBeenCalledWith([], {
      queryParams: { tab: null }, queryParamsHandling: 'merge', replaceUrl: true,
    });
  });
});
