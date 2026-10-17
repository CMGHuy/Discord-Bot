import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { ScoresCard, SCORES_NOTE, scoreWidth } from './scores-card';

describe('ScoresCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('clamps finite widths and leaves missing or nonfinite scores absent', () => {
    expect([null, NaN, Infinity, -Infinity].map(scoreWidth)).toEqual([null, null, null, null]);
    expect([-5, 0, 56, 101].map(scoreWidth)).toEqual([0, 0, 56, 100]);
  });
  it('renders score values, level and plain badge with neutral bars', () => {
    const f = TestBed.createComponent(ScoresCard);
    for (const [key, value] of Object.entries({ confidence: 90, level: 5, quality: 56, badge: 'WEAK' })) f.componentRef.setInput(key, value);
    f.detectChanges();
    const el: HTMLElement = f.nativeElement;
    expect(el.querySelector('h2')?.textContent).toBe('Scores');
    expect(el.querySelector('[data-score="confidence"]')?.textContent).toContain('90 · Lv5');
    expect(el.querySelector('[data-score="quality"]')?.textContent).toContain('56');
    expect(el.querySelector('[data-score="badge"]')?.textContent).toContain('WEAK');
    expect([...el.querySelectorAll<HTMLElement>('span.fill')].map(bar => bar.style.width)).toEqual(['90%', '56%']);
    expect(el.querySelector('.pos, .neg, sb-chip')).toBeNull();
    expect(el.querySelector('.scores-foot')?.textContent).toBe(SCORES_NOTE);
  });
  it('keeps null values absent, real zero visible, and omits a null level', () => {
    const f = TestBed.createComponent(ScoresCard); f.detectChanges();
    const el: HTMLElement = f.nativeElement;
    expect(el.querySelectorAll('.fill')).toHaveLength(0);
    expect(el.querySelector('[data-score="confidence"]')?.textContent).toContain('—');
    expect(el.querySelector('[data-score="quality"]')?.textContent).toContain('—');
    expect(el.querySelector('.scores-foot')?.textContent).toBe(SCORES_NOTE);
    f.componentRef.setInput('confidence', 0); f.detectChanges();
    expect(el.querySelector('[data-score="confidence"]')?.textContent).toContain('0');
    expect(el.textContent).not.toContain('Lv');
  });
});
