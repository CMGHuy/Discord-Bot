import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {provideZonelessChangeDetection}from'@angular/core';import{TestBed}from'@angular/core/testing';import{beforeEach,describe,expect,it}from'vitest';import{median,StripPlot}from'./strip-plot';describe('StripPlot',()=>{beforeEach(()=>TestBed.configureTestingModule({providers:[provideZonelessChangeDetection()]}));it('calculates medians',()=>{expect(median([3,1,2])).toBe(2);expect(median([1,2,3,4])).toBe(2.5);expect(median([])).toBeNull()});it('draws ticks and medians on one scale',()=>{const f=TestBed.createComponent(StripPlot);f.componentRef.setInput('groups',[{label:'Winners',values:[.2,.3,.4],tone:'pos'},{label:'Losers',values:[.6,.8],tone:'neg'}]);f.detectChanges();const e=f.nativeElement as HTMLElement;expect(e.querySelectorAll('line.tick').length).toBe(5);expect(e.querySelectorAll('line.median').length).toBe(2);expect(e.textContent).toContain('N=3');expect(e.textContent).toContain('median 0.30d')})});

describe('StripPlot draws at its own width (v179 layout audit: 11px text stays 11px)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('sets the viewBox to the host box width, so one unit is one pixel and the labels never shrink', async () => {
    const original = Object.getOwnPropertyDescriptor(Element.prototype, 'clientWidth')!;
    Object.defineProperty(Element.prototype, 'clientWidth', {
      configurable: true, get() { return (this as HTMLElement).classList.contains('host') ? 291 : 0; },
    });
    try {
      const f = TestBed.createComponent(StripPlot);
      f.componentRef.setInput('groups', [{ label: 'Winners', values: [.2], tone: 'pos' }]);
      f.detectChanges();
      await f.whenStable();
      f.detectChanges();
      expect((f.nativeElement as HTMLElement).querySelector('svg')!.getAttribute('viewBox')).toMatch(/^0 0 291 /);
    } finally {
      Object.defineProperty(Element.prototype, 'clientWidth', original);
    }
  });

  it('sizes its labels from the 11px token, not a literal', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/ui/strip-plot.ts'), 'utf8');
    expect(src).not.toMatch(/font-size:\s*11px/);
    expect(src).toMatch(/\.label\{[^}]*font-size:var\(--text-micro\)/);
    expect(src).toMatch(/\.sub\{[^;]*;font-size:var\(--text-micro\)/);
  });
});
