import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { IfItGetsThere } from './if-it-gets-there';

function mount(inputs: Record<string, unknown> = {}): ComponentFixture<IfItGetsThere> {
  const fixture = TestBed.createComponent(IfItGetsThere);
  for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
  fixture.detectChanges();
  return fixture;
}

function rows(fixture: ComponentFixture<IfItGetsThere>): string[] {
  return [...fixture.nativeElement.querySelectorAll('dl > div')]
    .map((row: HTMLElement) => [...row.querySelectorAll('dt, dd')]
      .map(cell => cell.textContent!.replace(/\s+/g, ' ').trim()).join(' '));
}

describe('IfItGetsThere', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('shows the panel heading', () => {
    const f = mount();
    expect(f.nativeElement.querySelector('h2')?.textContent?.trim()).toBe('If it gets there');
  });

  it('explains bullish continuation and reversal using formatted prices', () => {
    const f = mount({ direction: 'bullish', target2: 1234.5, stopLoss: 987.6 });
    const expected = [
      'Continues past resistance 1 next stop 1,234.50',
      'Reverses at resistance 1 pulls back toward support at 987.60',
    ];
    expect(rows(f)).toEqual(expected);
    f.componentRef.setInput('direction', 'unknown');
    f.detectChanges();
    expect(rows(f)).toEqual(expected);
    f.componentRef.setInput('direction', null);
    f.detectChanges();
    expect(rows(f)).toEqual(expected);
  });

  it('swaps support and resistance for bearish trades', () => {
    const f = mount({ direction: 'bearish', target2: 80, stopLoss: 105 });
    expect(rows(f)).toEqual([
      'Continues past support 1 next stop 80.00',
      'Reverses at support 1 pulls back toward resistance at 105.00',
    ]);
  });

  it('explains when no further target level was found', () => {
    const f = mount({ target2: null });
    expect(rows(f)[0]).toBe('Continues past resistance 1 no further level found');
  });

  it('shows a dash for a missing reversal price', () => {
    const f = mount({ stopLoss: null });
    expect(rows(f)[1]).toBe('Reverses at resistance 1 pulls back toward support at —');
  });
});
