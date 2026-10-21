import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import{provideZonelessChangeDetection}from'@angular/core';import{TestBed}from'@angular/core/testing';import{beforeEach,describe,expect,it}from'vitest';import{HeatGrid}from'./heat-grid';describe('HeatGrid',()=>{beforeEach(()=>TestBed.configureTestingModule({providers:[provideZonelessChangeDetection()]}));it('blanks withheld cells and renders folded row',()=>{const f=TestBed.createComponent(HeatGrid);f.componentRef.setInput('rows',['MACD']);f.componentRef.setInput('cols',['2w','1m']);f.componentRef.setInput('cells',[{r:0,c:0,n:3,value:null},{r:0,c:1,n:40,value:.3}]);f.componentRef.setInput('foldedRow',{label:'Other (5)',cells:[{c:0,n:7,value:null},{c:1,n:2,value:null}]});f.detectChanges();const e=f.nativeElement as HTMLElement,tds=[...e.querySelectorAll('td')];expect(tds[0].classList.contains('withheld')).toBe(true);expect(tds[0].textContent!.trim()).toBe('n=3');expect(tds[1].getAttribute('data-step')).toBe('p2');expect(e.querySelectorAll('tbody tr').length).toBe(2)})});

const HEAT_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/heat-grid.ts'), 'utf8');

function setGeometry(el: HTMLElement, scrollWidth: number, clientWidth: number, scrollLeft: number): void {
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth });
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(el, 'scrollLeft', { configurable: true, value: scrollLeft });
}

describe('HeatGrid containment (v179 §3.3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function wide() {
    const f = TestBed.createComponent(HeatGrid);
    const cols = ['1w', '2w', '3w', '1m', '2m', '3m', '6m', '7m', '8m', '9m'];
    f.componentRef.setInput('rows', ['MACD', 'RSI']);
    f.componentRef.setInput('cols', cols);
    f.componentRef.setInput('cells', cols.flatMap((_, c) => [0, 1].map((r) => ({ r, c, n: 40, value: c / 10 - 0.4 }))));
    f.detectChanges();
    return { f, el: f.nativeElement as HTMLElement };
  }

  it('keeps every column in the DOM -- 8m and 9m scroll into view, they are not dropped', () => {
    const { el } = wide();
    const headers = [...el.querySelectorAll('thead th[scope="col"]')].map((th) => th.textContent!.trim());
    expect(headers.slice(-2)).toEqual(['8m', '9m']);
  });

  it('fades the far edge while columns sit off-screen', () => {
    const { f, el } = wide();
    const box = el.querySelector('.scroll-x') as HTMLElement;
    setGeometry(box, 700, 330, 0);
    box.dispatchEvent(new Event('scroll'));
    f.detectChanges();
    const frame = el.querySelector('.frame')!;
    expect(frame.classList).toContain('fade-end');
    expect(frame.classList).not.toContain('fade-start');
  });

  it('shrinks with its panel and scrolls only inside its own box', () => {
    expect(HEAT_SOURCE).toContain(':host{display:block;min-width:0;max-width:100%}');
    expect(HEAT_SOURCE).toContain('.scroll-x{overflow-x:auto}');
    expect(HEAT_SOURCE).toContain("import{edgeFades}from'./scroll-rail'");
  });
});
