import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NavigationBehaviorOptions, Router, RouterOutlet, provideRouter, withRouterConfig } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { BACKGROUND_REFRESH_INFO } from '../../routing/route-loading.service';
import { MotionStarts } from './motion-starts';
import { MotionState, provideMotion } from './motion.service';
import { ENTRANCE_FALLBACK_MS, RouteEntrance } from './route-entrance';
import { RouteEntryService } from './route-entry.service';

@Component({ template: '<p>page</p>' })
class Page {}

@Component({
  imports: [RouterOutlet, RouteEntrance],
  template: '<div class="workspace-content" sbRouteEntrance><router-outlet /></div>',
})
class Host {}

interface Rig {
  fixture: ComponentFixture<Host>;
  host: HTMLElement;
  starts: MotionStarts;
  go(url: string, extras?: NavigationBehaviorOptions): Promise<void>;
}

function setup(mode: MotionState): Rig {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(
        [{ path: 'a', component: Page }, { path: 'b', component: Page }],
        withRouterConfig({ onSameUrlNavigation: 'reload' }),
      ),
      provideMotion(mode),
    ],
  });
  const fixture = TestBed.createComponent(Host);
  fixture.detectChanges();
  const router = TestBed.inject(Router);
  return {
    fixture,
    host: (fixture.nativeElement as HTMLElement).querySelector('.workspace-content') as HTMLElement,
    starts: TestBed.inject(MotionStarts),
    async go(url, extras = {}) {
      await router.navigateByUrl(url, extras);
      fixture.detectChanges();
      await fixture.whenStable();
    },
  };
}

const BACKGROUND: NavigationBehaviorOptions = {
  onSameUrlNavigation: 'reload',
  replaceUrl: true,
  info: BACKGROUND_REFRESH_INFO,
};

describe('RouteEntrance (spec v168 §3 #1, #2)', () => {
  it('enters on a new path under On: adds sb-entering and records one entrance', async () => {
    const rig = setup('on');
    await rig.go('/a');
    expect(rig.host.classList).toContain('sb-entering');
    expect(rig.starts.count('entrance')).toBe(1);
    expect(rig.starts.entries()).toContainEqual({ kind: 'entrance', key: 'route' });
  });

  it('does not re-enter on a background refresh, a same-URL reload or a query change', async () => {
    const rig = setup('on');
    await rig.go('/a');
    await rig.go('/a', BACKGROUND);
    await rig.go('/a', { onSameUrlNavigation: 'reload' });
    await rig.go('/a?tab=open');
    expect(rig.starts.count('entrance')).toBe(1);
  });

  it('enters again on a path change', async () => {
    const rig = setup('on');
    await rig.go('/a');
    await rig.go('/b');
    expect(rig.starts.count('entrance')).toBe(2);
    expect(rig.host.classList).toContain('sb-entering');
  });

  it('still enters under Reduced (motion.css makes it a plain fade)', async () => {
    const rig = setup('reduced');
    await rig.go('/a');
    expect(rig.host.classList).toContain('sb-entering');
    expect(rig.starts.count('entrance')).toBe(1);
  });

  it('spends the claim but never animates under Off', async () => {
    const rig = setup('off');
    await rig.go('/a');
    expect(rig.host.classList).not.toContain('sb-entering');
    expect(rig.starts.count('entrance')).toBe(0);
    expect(TestBed.inject(RouteEntryService).claim('route')).toBe(false);
  });

  it('spends the claim but never animates while preferences are pending', async () => {
    const rig = setup('pending');
    await rig.go('/a');
    expect(rig.host.classList).not.toContain('sb-entering');
    expect(rig.starts.count('entrance')).toBe(0);
    expect(TestBed.inject(RouteEntryService).claim('route')).toBe(false);
  });

  it('has no entrance before the first committed navigation', () => {
    const rig = setup('on');
    expect(rig.host.classList).not.toContain('sb-entering');
    expect(rig.starts.count('entrance')).toBe(0);
  });

  it('removes sb-entering once the entrance window has passed', async () => {
    const rig = setup('on');
    await rig.go('/a');
    expect(rig.host.classList).toContain('sb-entering');
    await new Promise((resolve) => setTimeout(resolve, ENTRANCE_FALLBACK_MS + 50));
    expect(rig.host.classList).not.toContain('sb-entering');
  });
});
