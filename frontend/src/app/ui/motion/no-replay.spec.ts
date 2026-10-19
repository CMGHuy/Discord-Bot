import { Component, Injectable, inject, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, RouterOutlet, provideRouter, withRouterConfig } from '@angular/router';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../../api/event-stream';
import { BACKGROUND_REFRESH_INFO, LIVE_REFRESH_DEBOUNCE_MS } from '../../routing/route-loading.service';
import { RouteRefreshService } from '../../routing/route-refresh.service';
import { Async } from '../async';
import { ChartContainer } from '../chart-container';
import { Figure } from '../figure';
import { Sparkline } from '../sparkline';
import { StatTile } from '../stat-tile';
import { MotionStartKind, MotionStarts } from './motion-starts';
import { DRAW_FALLBACK_MS } from './draw-in';
import { provideMotion } from './motion.service';
import { RouteEntrance } from './route-entrance';

/**
 * The no-replay gate (spec v168 §4). Entrance-type motion (route entrance and
 * CSS stagger, first count-up, draw-in) runs once per route activation. A
 * background refresh or an sb-async refetch must never start one again.
 */

/**
 * The page's fetch state: flipping it is what a refetch does to sb-async. The
 * children sit behind an @if on it because projected content is built once by
 * the page and only detached by sb-async; a real page re-creates its children
 * when its own data conditional flips, and that is the replay path under test.
 */
@Injectable({ providedIn: 'root' })
class PageData {
  readonly loading = signal(false);
}

@Component({
  imports: [Async, Figure, StatTile, Sparkline, ChartContainer],
  template: `
    <div class="sb-stack">
      <sb-async [loading]="data.loading()" emptyReason="no-data-yet" emptyTitle="Nothing yet">
        @if (!data.loading()) {
          <sb-figure label="Expectancy" [value]="0.42" />
          <sb-stat-tile label="Win rate" value="54.2%" />
          <sb-sparkline label="Equity" [points]="[1, 3, 2]" />
          <sb-chart-container caption="Price"><canvas></canvas></sb-chart-container>
        }
      </sb-async>
    </div>
  `,
})
class Page {
  protected readonly data = inject(PageData);
}

/** The shell's routed host, as shell.html has it. */
@Component({
  imports: [RouterOutlet, RouteEntrance],
  template: '<div class="workspace-content" sbRouteEntrance><router-outlet /></div>',
})
class Host {}

/** The kinds that must never replay. `count-change` and `flash` are the intended push reactions. */
const ENTRANCE_KINDS: readonly MotionStartKind[] = ['entrance', 'count-first', 'draw-in'];

function tally(starts: MotionStarts): Record<string, number> {
  return Object.fromEntries(ENTRANCE_KINDS.map((kind) => [kind, starts.count(kind)]));
}

interface Rig {
  fixture: ComponentFixture<Host>;
  router: Router;
  starts: MotionStarts;
  data: PageData;
  settle(): Promise<void>;
  go(url: string): Promise<void>;
  query(selector: string): Element | null;
}

function setup(): Rig {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(
        [{ path: 'a', component: Page }, { path: 'b', component: Page }],
        withRouterConfig({ onSameUrlNavigation: 'reload' }),
      ),
      provideMotion('on'),
      { provide: EventStream, useValue: { raised: new Subject<string>() } },
    ],
  });
  const fixture = TestBed.createComponent(Host);
  fixture.detectChanges();
  const router = TestBed.inject(Router);
  const settle = async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  };
  return {
    fixture,
    router,
    starts: TestBed.inject(MotionStarts),
    data: TestBed.inject(PageData),
    settle,
    async go(url) {
      await router.navigateByUrl(url);
      await settle();
    },
    query: (selector) => (fixture.nativeElement as HTMLElement).querySelector(selector),
  };
}

beforeEach(() => {
  // Each frame arrives asynchronously one COUNT_MS later, so a count-up runs to its final text.
  let frameTime = 0;
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frameTime += 10_000;
    return setTimeout(() => callback(frameTime), 0) as unknown as number;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('no replay on a push or a refetch (spec v168 §4)', () => {
  it('the first activation starts the entrance, the first count-ups and the draw-ins', async () => {
    const rig = setup();
    await rig.go('/a');
    const entries = rig.starts.entries();
    expect(entries).toContainEqual({ kind: 'entrance', key: 'route' });
    expect(entries).toContainEqual({ kind: 'count-first', key: 'figure:Expectancy' });
    expect(entries).toContainEqual({ kind: 'count-first', key: 'stat:Win rate' });
    expect(entries).toContainEqual({ kind: 'draw-in', key: 'sparkline:Equity' });
    expect(entries).toContainEqual({ kind: 'draw-in', key: 'chart:Price' });
    expect(rig.starts.count('entrance')).toBe(1);
  });

  it("(a) RouteRefreshService's background refresh starts nothing new", async () => {
    const rig = setup();
    const refresh = TestBed.inject(RouteRefreshService);
    await rig.go('/a');
    const before = tally(rig.starts);
    const navigate = vi.spyOn(rig.router, 'navigateByUrl');

    refresh.requestMutationRefresh();
    await new Promise((resolve) => setTimeout(resolve, LIVE_REFRESH_DEBOUNCE_MS + 100));
    expect(navigate).toHaveBeenCalledWith('/a', {
      onSameUrlNavigation: 'reload',
      replaceUrl: true,
      info: BACKGROUND_REFRESH_INFO,
    });
    await navigate.mock.results[0]!.value;
    await rig.settle();

    expect(tally(rig.starts)).toEqual(before);
  });

  it('(b) sb-async going loading -> content re-creates the children but starts nothing new', async () => {
    const rig = setup();
    await rig.go('/a');
    // Let the first draw-in's fallback timer remove its class, so a class seen later is a new start.
    await new Promise((resolve) => setTimeout(resolve, DRAW_FALLBACK_MS + 100));
    await rig.settle();
    expect(rig.query('sb-sparkline svg')!.classList).not.toContain('sb-draw-in');
    const before = tally(rig.starts);

    rig.data.loading.set(true);
    await rig.settle();
    expect(rig.query('sb-figure')).toBeNull();
    rig.data.loading.set(false);
    await rig.settle();
    expect(rig.query('sb-figure')).not.toBeNull();

    expect(tally(rig.starts)).toEqual(before);
    expect(rig.starts.count('count-change')).toBe(0);
    expect(rig.query('sb-sparkline svg')!.classList).not.toContain('sb-draw-in');
    expect(rig.query('sb-figure .value')!.textContent!.trim()).toBe('0.42');
  });

  it('a same-URL reload and a query-only change start nothing new', async () => {
    const rig = setup();
    await rig.go('/a');
    const before = tally(rig.starts);

    await rig.router.navigateByUrl('/a', { onSameUrlNavigation: 'reload' });
    await rig.settle();
    await rig.go('/a?tab=open');
    await rig.go('/a#top');

    expect(tally(rig.starts)).toEqual(before);
  });

  it('a path change starts every entrance kind again', async () => {
    const rig = setup();
    await rig.go('/a');
    const first = tally(rig.starts);
    for (const kind of ENTRANCE_KINDS) expect(first[kind], kind).toBeGreaterThan(0);

    await rig.go('/b');

    const second = tally(rig.starts);
    for (const kind of ENTRANCE_KINDS) expect(second[kind], kind).toBe(first[kind] * 2);
  });
});
