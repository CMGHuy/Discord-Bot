import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { BarList, BarListMode, BarRow } from './bar-list';

function render(rows: BarRow[], opts: { mode?: BarListMode; max?: number; reference?: number; floor?: number } = {}) {
  const fixture = TestBed.createComponent(BarList);
  fixture.componentRef.setInput('rows', rows);
  fixture.componentRef.setInput('format', (v: number) => `${v.toFixed(1)}%`);
  if (opts.mode) fixture.componentRef.setInput('mode', opts.mode);
  if (opts.max !== undefined) fixture.componentRef.setInput('max', opts.max);
  if (opts.reference !== undefined) fixture.componentRef.setInput('reference', opts.reference);
  if (opts.floor !== undefined) fixture.componentRef.setInput('withheldFloor', opts.floor);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}
const fills = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('.fill')];
describe('BarList', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('draws losses left of zero', () => { const [loss, gain] = fills(render([{ label: 'a', value: -80 }, { label: 'b', value: 40 }])); expect(loss.dataset['tone']).toBe('neg'); expect(loss.style.left).toBe('0%'); expect(loss.style.width).toBe('50%'); expect(gain.dataset['tone']).toBe('pos'); expect(gain.style.left).toBe('50%'); expect(gain.style.width).toBe('25%'); });
  it('honours max and omits zero/null bars', () => { const el=render([{label:'a',value:.5},{label:'b',value:0},{label:'c',value:null}],{max:1}); expect(fills(el)[0].style.width).toBe('25%'); expect(fills(el)).toHaveLength(1); expect(el.querySelectorAll('.value')[2].textContent!.trim()).toBe('—'); });
  it('scales rates and places a reference', () => { const el=render([{label:'a',value:64.705882,n:357}],{mode:'rate',reference:50}); expect(parseFloat(fills(el)[0].style.width)).toBeCloseTo(64.71,1); expect(el.querySelector<HTMLElement>('.ref')!.style.left).toBe('50%'); expect(el.querySelector('.n')!.textContent!.trim()).toBe('n=357'); });
  it('colours rates by their reference and clamps them', () => { const el=render([{label:'hi',value:130},{label:'lo',value:40}],{mode:'rate',reference:50}); expect(fills(el).map(x=>x.dataset['tone'])).toEqual(['above','below']); expect(fills(el)[0].style.width).toBe('100%'); });
  it('withholds rows below the floor', () => { const el=render([{label:'Saturday',value:null,n:3,withheld:true}],{mode:'rate',reference:50,floor:20}); expect(fills(el)).toHaveLength(0); expect(el.querySelector('li')!.classList).toContain('withheld'); expect(el.querySelector('.n')!.textContent!.trim()).toBe('n=3 · <20'); });
});
