import { readFileSync } from 'node:fs';
import { join } from 'node:path';
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

const BAR_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/bar-list.ts'), 'utf8');

describe('BarList narrow container (v179 §3.3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('is its own size container and can shrink inside a grid', () => {
    expect(BAR_SOURCE).toContain(':host{display:block;min-width:0;container:bar-list/inline-size}');
  });

  it('drops to two lines -- label, value and n, then the bar -- in a narrow box', () => {
    const narrow = BAR_SOURCE.match(/@container bar-list \(max-width: 26rem\)\{([\s\S]*?\})\}/)?.[1] ?? '';
    expect(narrow).toContain("grid-template-areas:'label value n' 'track track track'");
    expect(narrow).toContain('grid-template-columns:minmax(0,1fr) auto auto');
    for (const area of ['.label{grid-area:label}', '.track{grid-area:track}', '.value{grid-area:value}', '.n{grid-area:n}']) {
      expect(narrow).toContain(area);
    }
  });

  it('no longer squeezes fixed tracks by viewport width', () => {
    expect(BAR_SOURCE).not.toContain('@media(max-width:639px)');
  });

  it('still renders label, bar, value and n for every row -- nothing is dropped', () => {
    const el = render([{ label: 'Saturday', value: 12.5, n: 41 }]);
    const li = el.querySelector('li')!;
    expect(li.querySelector('.label')!.textContent).toBe('Saturday');
    expect(li.querySelector('.track')).not.toBeNull();
    expect(li.querySelector('.value')!.textContent!.trim()).toBe('12.5%');
    expect(li.querySelector('.n')!.textContent!.trim()).toBe('n=41');
  });
});
