import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { DirectionArrow } from './direction-arrow';
import { styleRules } from './testing/style-rules';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/direction-arrow.ts'), 'utf8');

/** The `long` and `short` drawings from icon.ts (V241-2). sb-icon's `name`
 *  is a property binding with no DOM trace, so the drawing is the check. */
const LONG_D = 'M3 17l6-6 4 4 8-8 M15 7h6v6';
const SHORT_D = 'M3 7l6 6 4-4 8 8 M15 17h6v-6';

function render(direction: string | null) {
  const f = TestBed.createComponent(DirectionArrow);
  f.componentRef.setInput('direction', direction);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

const drawn = (el: HTMLElement) =>
  el.querySelector('.arrow > sb-icon svg path')?.getAttribute('d') ?? null;

describe('DirectionArrow', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('draws the rising trend arrow for a long', () => {
    const el = render('bullish');
    expect(drawn(el)).toBe(LONG_D);
    expect(el.querySelector('.long')).not.toBeNull();
    // No text glyph left: the shape no longer depends on the font.
    expect(el.textContent!.trim()).toBe('');
  });

  it('draws the falling trend arrow for a short', () => {
    const el = render('bearish');
    expect(drawn(el)).toBe(SHORT_D);
    expect(el.querySelector('.short')).not.toBeNull();
    expect(el.textContent!.trim()).toBe('');
  });

  it('is an em dash when the direction is unknown', () => {
    const el = render(null);
    expect(el.textContent!.trim()).toBe('—');
    expect(el.querySelector('sb-icon')).toBeNull();
  });

  it('draws at the table size, 16px', () => {
    const svg = render('bullish').querySelector('sb-icon svg')!;
    expect(svg.getAttribute('width')).toBe('16');
  });

  it('names itself for a screen reader, because the icon is the whole cell', () => {
    // Not optional: an arrow with no accessible name makes the entire column
    // unreadable to anyone not looking at it. role="img" is what makes a
    // screen reader announce a span's aria-label once it holds no text.
    const el = render('bullish');
    const arrow = el.querySelector('[aria-label]')!;
    expect(arrow.getAttribute('aria-label')).toBe('Long (bullish)');
    expect(arrow.getAttribute('title')).toBe('Long (bullish)');
    expect(arrow.getAttribute('role')).toBe('img');
  });

  it('names a short the same way', () => {
    const arrow = render('bearish').querySelector('[aria-label]')!;
    expect(arrow.getAttribute('aria-label')).toBe('Short (bearish)');
    expect(arrow.getAttribute('title')).toBe('Short (bearish)');
    expect(arrow.getAttribute('role')).toBe('img');
  });

  it('keeps the icon out of the name: no tooltip of its own, svg hidden', () => {
    // Exactly one name per cell: "Long (bullish)", never "Long (bullish) Long".
    const el = render('bullish');
    expect(el.querySelectorAll('[aria-label]')).toHaveLength(1);
    expect(el.querySelector('sb-icon')!.getAttribute('title')).toBe('');
    expect(el.querySelector('sb-icon svg')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('colours long and short with --pos and --neg, the recorded valence exception', () => {
    const rules = styleRules('direction-arrow.ts', SOURCE);
    expect(rules.find((r) => r.selector === '.long')?.body).toContain('var(--pos)');
    expect(rules.find((r) => r.selector === '.short')?.body).toContain('var(--neg)');
  });
});
