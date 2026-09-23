import { readFileSync } from 'node:fs'; import { join } from 'node:path'; import { Component, provideZonelessChangeDetection } from '@angular/core'; import { TestBed } from '@angular/core/testing'; import { beforeEach, describe, expect, it } from 'vitest';
import { Panel } from './layout'; import { Viewport } from './breakpoints'; import { PanelGrid, PanelTrack } from './panel-grid';
import { ComponentFixture } from '@angular/core/testing';
import { signal } from '@angular/core';
const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/panel-grid.ts'), 'utf8');
@Component({ imports: [PanelGrid, Panel], template: `<sb-panel-grid [track]="track"><sb-panel heading="One" /><sb-panel heading="Two" /><sb-panel heading="Three" /></sb-panel-grid>` }) class Host { track: PanelTrack = 'narrow'; }
function render(track?: PanelTrack) { const f = TestBed.createComponent(Host); if (track) f.componentInstance.track = track; f.detectChanges(); return (f.nativeElement as HTMLElement).querySelector('sb-panel-grid') as HTMLElement; }
describe('PanelGrid (v80 D4)', () => { beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('defaults narrow and accepts wide', () => { expect(render().classList).toContain('narrow'); expect(render('wide').classList).toContain('wide'); });
  it('lays panels directly as grid items', () => { const grid = render(); expect(getComputedStyle(grid).display).toBe('grid'); expect([...grid.children]).toHaveLength(3); });
  it('offers two track widths and one-column phone fallback', () => { expect([...SOURCE.matchAll(/minmax\(min\((\d+)px, 100%\), 1fr\)/g)].map(([, width]) => width)).toEqual(['220', '320']); expect(SOURCE).toMatch(/@media \(max-width: 639px\) \{\s*:host, :host\(\.wide\) \{ grid-template-columns: minmax\(0, 1fr\); \}/); });
});

@Component({
  imports: [PanelGrid],
  template: `
    <sb-panel-grid [order]="order()" [viewportAt]="viewportAt()">
      <div data-panel-id="positions">P</div>
      <div data-panel-id="performance">Q</div>
      <div data-panel-id="activity">R</div>
    </sb-panel-grid>
  `,
})
class OrderHost {
  readonly viewportAt = signal<Viewport | null>(null);
  readonly order = signal<Partial<Record<Viewport, string[]>> | null>(null);
}

describe('sb-panel-grid ordering', () => {
  let fixture: ComponentFixture<OrderHost>;
  let host: OrderHost;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(OrderHost);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const orders = () =>
    [...(fixture.nativeElement as HTMLElement).querySelectorAll('[data-panel-id]')]
      .map((n) => (n as HTMLElement).style.order);

  it('sets no order when none is declared', () => {
    expect(orders()).toEqual(['', '', '']);
  });

  it('orders by the band it is in', () => {
    host.order.set({ xs: ['performance', 'positions', 'activity'] });
    host.viewportAt.set('xs');
    fixture.detectChanges();
    // performance first, positions second, activity third
    expect(orders()).toEqual(['1', '0', '2']);
  });

  it('falls back to declaration order in a band with no entry', () => {
    host.order.set({ xs: ['performance', 'positions', 'activity'] });
    host.viewportAt.set('lg');
    fixture.detectChanges();
    expect(orders()).toEqual(['', '', '']);
  });

  it('leaves an unnamed panel after the named ones rather than dropping it', () => {
    host.order.set({ xs: ['activity'] });
    host.viewportAt.set('xs');
    fixture.detectChanges();
    const [positions, performance, activity] = orders();
    expect(Number(activity)).toBeLessThan(Number(positions));
    expect(Number(activity)).toBeLessThan(Number(performance));
  });
});
