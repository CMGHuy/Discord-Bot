import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ConfidenceCell } from './confidence-cell';

function render(level: number | null, score: number | null) {
  const f = TestBed.createComponent(ConfidenceCell);
  f.componentRef.setInput('level', level);
  f.componentRef.setInput('score', score);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

const text = (el: HTMLElement) => el.textContent!.replace(/\s+/g, ' ').trim();

describe('ConfidenceCell', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('reads level and score together', () => {
    expect(text(render(4, 78))).toBe('Lv4 · 78');
  });

  it('drops the separator entirely when there is no score', () => {
    // Not 'Lv4 · —': a dangling separator reads as a rendering fault rather
    // than as an absent value.
    expect(text(render(4, null))).toBe('Lv4');
  });

  it('is an em dash when there is no level', () => {
    expect(text(render(null, 78))).toBe('—');
  });

  it('bands the badge by level', () => {
    expect(render(4, 78).querySelector('.q4')).not.toBeNull();
    expect(render(1, 12).querySelector('.q1')).not.toBeNull();
  });

  it('falls back to a mid band for a level outside 1-5', () => {
    // Interpolating the level straight into a token name would produce
    // var(--quality-9), which resolves to nothing and renders invisible.
    const el = render(9, 50);
    expect(el.querySelector('.q3')).not.toBeNull();
    expect(el.querySelector('.q9')).toBeNull();
  });
});
