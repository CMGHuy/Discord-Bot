import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { PanelHeader } from './panel-header';

describe('PanelHeader', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  const render = (inputs: Record<string, unknown>) => { const fixture = TestBed.createComponent(PanelHeader); for (const [key, value] of Object.entries(inputs)) fixture.componentRef.setInput(key, value); fixture.detectChanges(); return { fixture, el: fixture.nativeElement as HTMLElement }; };
  it('states title, N and currency total', () => { const { el } = render({ title: 'Equity', n: 312, total: '+$1,240' }); expect(el.textContent).toContain('Equity'); expect(el.querySelector('.n')!.textContent).toContain('N=312'); expect(el.querySelector('.total')!.textContent).toBe('+$1,240'); expect(el.querySelector('.all-time')).toBeNull(); });
  it('badges all-time panels and hides unknown N', () => { const { el } = render({ title: 'Calibration', allTime: true }); expect(el.querySelector('.all-time')!.textContent).toContain('all-time'); expect(el.querySelector('.n')).toBeNull(); });
  it('toggles tableOpen', () => { const { fixture, el } = render({ title: 'By horizon', tableable: true }); (el.querySelector('button.table') as HTMLButtonElement).click(); fixture.detectChanges(); expect(fixture.componentInstance.tableOpen()).toBe(true); expect((el.querySelector('button.table') as HTMLButtonElement).getAttribute('aria-pressed')).toBe('true'); });
});
