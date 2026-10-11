import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { LevelsBlock, PAPER_LINE, entryTypeWord } from './levels-block';

function mount(inputs: Record<string, unknown> = {}): ComponentFixture<LevelsBlock> {
  const fixture = TestBed.createComponent(LevelsBlock);
  for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
  fixture.detectChanges();
  return fixture;
}

function rows(fixture: ComponentFixture<LevelsBlock>): string[][] {
  return [...fixture.nativeElement.querySelectorAll('dl > div')].map((row: HTMLElement) =>
    [...row.querySelectorAll('dt, dd')].map((cell) => cell.textContent?.trim() ?? ''));
}

describe('entryTypeWord', () => {
  it.each([
    ['stop_entry', 'bullish', 'Buy stop'], ['stop_entry', 'bearish', 'Sell stop'],
    ['stop_entry', null, 'Stop entry'], ['stop_entry', 'sideways', 'Stop entry'],
    ['limit', 'bullish', 'Buy limit'], ['limit', 'bearish', 'Sell limit'],
    ['limit', null, 'Limit entry'], ['limit', 'sideways', 'Limit entry'],
    ['market', 'bullish', 'At market'], ['market', 'bearish', 'At market'],
    ['market', null, 'At market'], [null, 'bullish', '—'],
    ['future_order', 'bullish', 'future_order'],
    ['constructor', 'bullish', 'constructor'], ['__proto__', null, '__proto__'],
    ['stop_entry', 'constructor', 'Stop entry'],
  ])('renders %s with direction %s as %s', (type, direction, expected) => {
    expect(entryTypeWord(type, direction)).toBe(expected);
  });
});

describe('LevelsBlock', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('shows a single Levels panel, missing values, paper line and no controls or sources', () => {
    const f = mount();
    expect(f.nativeElement.querySelectorAll('sb-panel')).toHaveLength(1);
    expect(f.nativeElement.querySelector('h2').textContent.trim()).toBe('Levels');
    expect(rows(f)).toEqual([
      ['Order', '—'], ['Entry', '—'], ['Stop', '—'], ['Target 1', '—'],
      ['Target 2', '—'], ['R:R', '—'],
    ]);
    expect(PAPER_LINE).toBe('Paper plan — this page places no orders.');
    expect(f.nativeElement.querySelector('.muted').textContent.trim()).toBe(PAPER_LINE);
    expect(f.nativeElement.querySelectorAll('button, a, input, select, textarea, .sources')).toHaveLength(0);
  });

  it('orders populated rows, formats unsigned shares, and applies stop and target colors', () => {
    const f = mount({ direction: 'bullish', entryType: 'stop_entry', trigger: 100,
      entry: 101, stop: 95, target1: 110, target2: 120, riskReward: 2.5,
      acceptanceLevel: 99, tp1Pct: 50, breakevenTriggerPct: 75, stopLabel: 'Initial stop' });
    expect(rows(f)).toEqual([
      ['Order', 'Buy stop'], ['Trigger', '100.00'], ['Entry', '101.00'],
      ['Initial stop', '95.00'], ['Target 1', '110.00'], ['Target 2', '120.00'],
      ['R:R', '2.50'], ['Acceptance level', '99.00'], ['TP1 closes', '50%'],
      ['Break-even at', '75% of TP1'],
    ]);
    expect(f.nativeElement.querySelector('dd.neg').textContent.trim()).toBe('95.00');
    expect([...f.nativeElement.querySelectorAll('dd.pos')].map((el: HTMLElement) => el.textContent?.trim()))
      .toEqual(['110.00', '120.00']);
  });

  it('keeps zero optional values visible and removes each row when cleared', () => {
    const f = mount({ trigger: 0, acceptanceLevel: 0, tp1Pct: 0, breakevenTriggerPct: 0 });
    expect(rows(f).map(([label]) => label)).toEqual([
      'Order', 'Trigger', 'Entry', 'Stop', 'Target 1', 'Target 2', 'R:R',
      'Acceptance level', 'TP1 closes', 'Break-even at',
    ]);
    for (const name of ['trigger', 'acceptanceLevel', 'tp1Pct', 'breakevenTriggerPct']) {
      f.componentRef.setInput(name, null);
    }
    f.detectChanges();
    expect(rows(f)).toHaveLength(6);
  });
});
