import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { confirmationText, hasLevelSources, LevelSourcesCard } from './level-sources-card';

describe('LevelSourcesCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('detects any recorded source and formats confirmations', () => {
    expect(hasLevelSources([], [], [], [])).toBe(false);
    expect(hasLevelSources(['x'], [], [], [])).toBe(true);
    expect(hasLevelSources([], ['x'], [], [])).toBe(true);
    expect(hasLevelSources([], [], ['x'], [])).toBe(true);
    expect(hasLevelSources([], [], [], [{ strategy: 'VWAP', horizon: null }])).toBe(true);
    expect(confirmationText({ strategy: 'VWAP', horizon: '2w' })).toBe('VWAP (2w)');
    expect(confirmationText({ strategy: 'VWAP', horizon: null })).toBe('VWAP');
  });
  it('renders only populated source lists and preserves their order', () => {
    const f = TestBed.createComponent(LevelSourcesCard); f.detectChanges();
    const el: HTMLElement = f.nativeElement;
    expect(el.querySelectorAll('[data-source]')).toHaveLength(0);
    for (const [key, value] of Object.entries({ target: ['Resistance', 'Fib'], stop: ['Support'], target2: ['Range'], confirmedBy: [{ strategy: 'VWAP', horizon: '2w' }, { strategy: 'RSI', horizon: null }] })) f.componentRef.setInput(key, value);
    f.detectChanges();
    expect(el.querySelector('h2')?.textContent).toBe('Level sources');
    expect([...el.querySelectorAll('[data-source]')].map(row => row.getAttribute('data-source'))).toEqual(['Target', 'Stop', 'Target 2', 'Confirmed by']);
    expect([...el.querySelectorAll('li')].map(li => li.textContent?.trim())).toEqual(['Resistance', 'Fib', 'Support', 'Range', 'VWAP (2w)', 'RSI']);
    f.componentRef.setInput('target', []); f.detectChanges();
    expect(el.querySelector('[data-source="Target"]')).toBeNull();
  });
});
