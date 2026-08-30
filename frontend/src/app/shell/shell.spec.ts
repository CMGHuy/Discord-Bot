import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { RouteLoadingService } from '../routing/route-loading.service';
import { Shell } from './shell';

describe('shell navigation', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
  });

  it('shows an accessible, non-interactive overlay inside the pending workspace', () => {
    const routeLoading = { visible: signal(false), label: signal('Loading Trades') };
    TestBed.overrideProvider(RouteLoadingService, { useValue: routeLoading });
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    routeLoading.visible.set(true);
    f.detectChanges();
    const workspace = (f.nativeElement as HTMLElement).querySelector('.workspace')!;
    expect(workspace.classList.contains('route-pending')).toBe(true);
    expect(workspace.querySelector('[role="status"]')?.textContent).toContain('Loading Trades');
    expect(workspace.querySelector('.route-loading-overlay')).not.toBeNull();
  });
  it('groups the eight workspaces into three named groups', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const labels = [...el.querySelectorAll('.nav-group-label')].map((n) => n.textContent?.trim());
    expect(labels).toEqual(['MONITOR', 'REVIEW', 'SYSTEM']);
    expect(el.querySelectorAll('.nav a').length).toBe(8);
  });

  it('keeps each group a real list so the grouping reaches assistive tech', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const groups = (f.nativeElement as HTMLElement).querySelectorAll('ul[aria-labelledby]');
    expect(groups.length).toBe(3);
  });
});