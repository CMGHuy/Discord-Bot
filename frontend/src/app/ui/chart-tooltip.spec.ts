import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { ChartTooltip, HoverState, hoverPosition } from './chart-tooltip';

describe('ChartTooltip', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  const render = (state: HoverState | null) => { const fixture = TestBed.createComponent(ChartTooltip); fixture.componentRef.setInput('state', state); fixture.detectChanges(); return fixture.nativeElement as HTMLElement; };
  it('renders nothing when there is no hover state', () => expect(render(null).querySelector('.tooltip')).toBeNull());
  it('puts value first and binds labels as text', () => { const el = render({ x: 10, y: 20, title: '2026-08-04', rows: [{ label: '<b>MACD</b>', value: '+1.20R', swatch: 'var(--chart-1)' }] }); const row = el.querySelector('.row')!; expect(row.querySelector('.value')!.textContent).toBe('+1.20R'); expect(row.querySelector('.label')!.textContent).toBe('<b>MACD</b>'); expect(row.querySelector('.label')!.querySelector('b')).toBeNull(); expect((row.querySelector('.swatch') as HTMLElement).style.background).toContain('--chart-1'); expect((el.querySelector('.tooltip') as HTMLElement).style.left).toBe('10px'); });
  it('positions hover relative to its host', () => { const host = document.createElement('div'); host.getBoundingClientRect = () => ({ left: 100, top: 50 } as DOMRect); expect(hoverPosition({ clientX: 130, clientY: 70 } as PointerEvent, host)).toEqual({ x: 30, y: 20 }); });
});
