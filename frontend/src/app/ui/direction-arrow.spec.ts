import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { DirectionArrow } from './direction-arrow';

function render(direction: string | null) {
  const f = TestBed.createComponent(DirectionArrow);
  f.componentRef.setInput('direction', direction);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('DirectionArrow', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('is an up arrow for a long', () => {
    const el = render('bullish');
    expect(el.textContent!.trim()).toBe('▲');
    expect(el.querySelector('.long')).not.toBeNull();
  });

  it('is a down arrow for a short', () => {
    const el = render('bearish');
    expect(el.textContent!.trim()).toBe('▼');
    expect(el.querySelector('.short')).not.toBeNull();
  });

  it('is an em dash when the direction is unknown', () => {
    expect(render(null).textContent!.trim()).toBe('—');
  });

  it('names itself for a screen reader, because the glyph is the whole cell', () => {
    // Not optional: an arrow with no accessible name makes the entire column
    // unreadable to anyone not looking at it.
    const el = render('bullish');
    const glyph = el.querySelector('[aria-label]')!;
    expect(glyph.getAttribute('aria-label')).toBe('Long (bullish)');
    expect(glyph.getAttribute('title')).toBe('Long (bullish)');
  });

  it('names a short the same way', () => {
    const glyph = render('bearish').querySelector('[aria-label]')!;
    expect(glyph.getAttribute('aria-label')).toBe('Short (bearish)');
    expect(glyph.getAttribute('title')).toBe('Short (bearish)');
  });
});
