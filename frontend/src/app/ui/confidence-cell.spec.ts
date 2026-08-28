import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ConfidenceCell } from './confidence-cell';

function render(level: number | null, score: number | null, direction: string | null = null) {
  const f = TestBed.createComponent(ConfidenceCell);
  f.componentRef.setInput('level', level);
  f.componentRef.setInput('score', score);
  f.componentRef.setInput('direction', direction);
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

  it('renders no direction arrow when direction is not given', () => {
    expect(render(4, 78).querySelector('sb-direction-arrow')).toBeNull();
  });

  it('renders the direction arrow to the left of the level when given', () => {
    // The Dashboard's four lifecycle tables fold Direction into this column
    // to save width; every other call site leaves `direction` unset and
    // gets exactly the old markup (the test above).
    const el = render(4, 78, 'bullish');
    const arrow = el.querySelector('sb-direction-arrow');
    expect(arrow).not.toBeNull();
    expect(text(el)).toBe('▲ Lv4 · 78');
  });

  it('still shows the direction arrow when there is no confidence level yet', () => {
    // A PENDING plan has a direction from the moment it is built, well
    // before it has a linked trade to score for confidence -- gating the
    // arrow on level() too would silently lose the only direction info the
    // row has left, now that there is no separate Direction column.
    const el = render(null, null, 'bearish');
    expect(el.querySelector('sb-direction-arrow')).not.toBeNull();
    expect(text(el)).toBe('▼ —');
  });

  it('bands level 4 on the monotonic ramp, not on info blue', () => {
    const root = getComputedStyle(document.documentElement);
    expect(root.getPropertyValue('--quality-4').trim().toLowerCase()).toBe('#9acd32');
  });

  it('leaves info alone for the chart series namespace', () => {
    const root = getComputedStyle(document.documentElement);
    expect(root.getPropertyValue('--info').trim().toLowerCase()).toBe('#46c2ff');
  });
});
