import { readFileSync } from 'node:fs'; import { join } from 'node:path'; import { Component, provideZonelessChangeDetection } from '@angular/core'; import { TestBed } from '@angular/core/testing'; import { beforeEach, describe, expect, it } from 'vitest';
import { Panel } from './layout'; import { PanelGrid, PanelTrack } from './panel-grid';
const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/panel-grid.ts'), 'utf8');
@Component({ imports: [PanelGrid, Panel], template: `<sb-panel-grid [track]="track"><sb-panel heading="One" /><sb-panel heading="Two" /><sb-panel heading="Three" /></sb-panel-grid>` }) class Host { track: PanelTrack = 'narrow'; }
function render(track?: PanelTrack) { const f = TestBed.createComponent(Host); if (track) f.componentInstance.track = track; f.detectChanges(); return (f.nativeElement as HTMLElement).querySelector('sb-panel-grid') as HTMLElement; }
describe('PanelGrid (v80 D4)', () => { beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('defaults narrow and accepts wide', () => { expect(render().classList).toContain('narrow'); expect(render('wide').classList).toContain('wide'); });
  it('lays panels directly as grid items', () => { const grid = render(); expect(getComputedStyle(grid).display).toBe('grid'); expect([...grid.children]).toHaveLength(3); });
  it('offers two track widths and one-column phone fallback', () => { expect([...SOURCE.matchAll(/minmax\(min\((\d+)px, 100%\), 1fr\)/g)].map(([, width]) => width)).toEqual(['220', '320']); expect(SOURCE).toMatch(/@media \(max-width: 639px\) \{\s*:host, :host\(\.wide\) \{ grid-template-columns: minmax\(0, 1fr\); \}/); });
});
