import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { ChartContainer } from '../chart-container';
import { DonutComponent } from '../donut';
import { DotPlot } from '../dot-plot';
import { Gauge } from '../gauge';
import { Sparkline } from '../sparkline';
import { DRAW_FALLBACK_MS, DrawIn, DrawShape } from './draw-in';
import { MotionStarts } from './motion-starts';
import { MotionState, provideMotion } from './motion.service';
import { RouteEntryService } from './route-entry.service';

function configure(mode: MotionState): void {
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), provideRouter([]), provideMotion(mode)],
  });
}

@Component({
  imports: [DrawIn],
  template: `@if (shown()) {
    <div class="chart" [sbDrawIn]="key()" [drawShape]="shape()" [drawReady]="ready()"><span class="inner"></span></div>
  }`,
})
class Host {
  readonly shown = signal(true);
  readonly key = signal('sparkline:Equity');
  readonly shape = signal<DrawShape>('inset');
  readonly ready = signal(true);
}

function mount(patch: (host: Host) => void = () => undefined) {
  const fixture = TestBed.createComponent(Host);
  patch(fixture.componentInstance);
  fixture.detectChanges();
  const chart = () => (fixture.nativeElement as HTMLElement).querySelector('.chart') as HTMLElement;
  return { fixture, chart, starts: TestBed.inject(MotionStarts), entry: TestBed.inject(RouteEntryService) };
}

describe('DrawIn (spec v168 §3 #9)', () => {
  it('under On clips the chart in with the inset reveal and records the start', () => {
    configure('on');
    const { chart, starts } = mount();
    expect(chart().classList).toContain('sb-draw-in');
    expect(starts.entries()).toContainEqual({ kind: 'draw-in', key: 'sparkline:Equity' });
  });

  it('uses the radial reveal for drawShape circle', () => {
    configure('on');
    const { chart } = mount((host) => host.shape.set('circle'));
    expect(chart().classList).toContain('sb-draw-in-radial');
    expect(chart().classList).not.toContain('sb-draw-in');
  });

  it('a second claim in the same activation renders unclipped', () => {
    configure('on');
    mount();
    const second = mount();
    expect(second.chart().classList).not.toContain('sb-draw-in');
    expect(second.starts.count('draw-in')).toBe(1);
  });

  it('re-created after a refetch, the chart does not draw in again', () => {
    configure('on');
    const { fixture, chart, starts } = mount();
    fixture.componentInstance.shown.set(false);
    fixture.detectChanges();
    fixture.componentInstance.shown.set(true);
    fixture.detectChanges();
    expect(chart().classList).not.toContain('sb-draw-in');
    expect(starts.count('draw-in')).toBe(1);
  });

  for (const mode of ['reduced', 'off', 'pending'] as const) {
    it(`spends the claim but never clips under ${mode}`, () => {
      configure(mode);
      const { chart, starts, entry } = mount();
      expect(chart().classList).not.toContain('sb-draw-in');
      expect(starts.count('draw-in')).toBe(0);
      expect(entry.claim('sparkline:Equity')).toBe(false);
    });
  }

  it('waits for drawReady before it claims, then draws in once ready', () => {
    configure('on');
    const { fixture, chart, starts } = mount((host) => host.ready.set(false));
    expect(chart().classList).not.toContain('sb-draw-in');
    expect(starts.count('draw-in')).toBe(0);
    fixture.componentInstance.ready.set(true);
    fixture.detectChanges();
    expect(chart().classList).toContain('sb-draw-in');
    expect(starts.count('draw-in')).toBe(1);
  });

  it("removes the class on its own animationend, not on a child's", () => {
    configure('on');
    const { chart } = mount();
    chart().querySelector('.inner')!.dispatchEvent(new Event('animationend', { bubbles: true }));
    expect(chart().classList).toContain('sb-draw-in');
    chart().dispatchEvent(new Event('animationend'));
    expect(chart().classList).not.toContain('sb-draw-in');
  });

  it('removes the class after DRAW_FALLBACK_MS when no animationend arrives', async () => {
    configure('on');
    const { chart } = mount();
    expect(chart().classList).toContain('sb-draw-in');
    await new Promise((resolve) => setTimeout(resolve, DRAW_FALLBACK_MS + 50));
    expect(chart().classList).not.toContain('sb-draw-in');
  });

  it('leaves no class behind when destroyed mid-reveal', () => {
    configure('on');
    const { fixture, chart } = mount();
    const element = chart();
    fixture.destroy();
    expect(element.classList).not.toContain('sb-draw-in');
  });
});

describe('the five chart primitives draw in (spec v168 §3 #9)', () => {
  function keys(): string[] {
    return TestBed.inject(MotionStarts).entries().filter((start) => start.kind === 'draw-in').map((start) => start.key);
  }

  it('sb-sparkline reveals its svg left to right', () => {
    configure('on');
    const f = TestBed.createComponent(Sparkline);
    f.componentRef.setInput('points', [1, 3, 2]);
    f.componentRef.setInput('label', 'Equity');
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('svg')!.classList).toContain('sb-draw-in');
    expect(keys()).toEqual(['sparkline:Equity']);
  });

  it('sb-gauge reveals its svg radially', () => {
    configure('on');
    const f = TestBed.createComponent(Gauge);
    f.componentRef.setInput('label', 'Heat utilisation');
    f.componentRef.setInput('value', 62);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('svg')!.classList).toContain('sb-draw-in-radial');
    expect(keys()).toEqual(['gauge:Heat utilisation']);
  });

  it('sb-donut reveals its svg radially', () => {
    configure('on');
    const f = TestBed.createComponent(DonutComponent);
    f.componentRef.setInput('slices', [
      { label: 'Win', count: 3, tone: 'pos' },
      { label: 'Loss', count: 2, tone: 'neg' },
    ]);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('svg')!.classList).toContain('sb-draw-in-radial');
    expect(keys()).toEqual(['donut']);
  });

  it('sb-dot-plot reveals its svg left to right', () => {
    configure('on');
    const f = TestBed.createComponent(DotPlot);
    f.componentRef.setInput('points', [{ label: 'MACD', n: 140, value: 0.2 }]);
    f.componentRef.setInput('floor', 20);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('svg')!.classList).toContain('sb-draw-in');
    expect(keys()).toEqual(['dot-plot:ExpR']);
  });

  it('sb-chart-container waits for the chart to be ready, then reveals the surface', () => {
    configure('on');
    const f = TestBed.createComponent(ChartContainer);
    f.componentRef.setInput('caption', 'Price');
    f.componentRef.setInput('loading', true);
    f.detectChanges();
    const surface = (f.nativeElement as HTMLElement).querySelector('.surface')!;
    expect(surface.classList).not.toContain('sb-draw-in');
    expect(keys()).toEqual([]);
    f.componentRef.setInput('loading', false);
    f.detectChanges();
    expect(surface.classList).toContain('sb-draw-in');
    expect(keys()).toEqual(['chart:Price']);
  });

  it('under the Off test default no primitive clips', () => {
    configure('off');
    const f = TestBed.createComponent(Sparkline);
    f.componentRef.setInput('points', [1, 3, 2]);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('svg')!.classList).not.toContain('sb-draw-in');
    expect(keys()).toEqual([]);
  });
});
