import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Chip, ChipTone, QualityChip } from './chip';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/chip.ts'), 'utf8');

function render(tone: ChipTone, caps?: boolean): HTMLElement {
  const f = TestBed.createComponent(Chip);
  f.componentRef.setInput('label', 'Swing');
  f.componentRef.setInput('tone', tone);
  if (caps !== undefined) f.componentRef.setInput('caps', caps);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.chip')!;
}

describe('Chip (v80 D4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  for (const tone of ['neutral', 'good', 'warn', 'info', 'q1', 'q2', 'q3', 'q4', 'q5'] as ChipTone[]) {
    it(`renders the ${tone} tone as a class`, () => {
      expect(render(tone).classList).toContain(tone);
    });
  }

  it('sets mono caps by default', () => {
    expect(render('neutral').classList).toContain('caps');
  });

  it('lets a caller keep mixed case', () => {
    expect(render('neutral', false).classList).not.toContain('caps');
  });

  it('keeps a quality chip mixed case, so Lv4 still reads Lv4', () => {
    const f = TestBed.createComponent(QualityChip);
    f.componentRef.setInput('value', 4);
    f.componentRef.setInput('label', 'Lv4');
    f.detectChanges();
    const chip = (f.nativeElement as HTMLElement).querySelector('.chip')!;
    expect(chip.classList).toContain('q4');
    expect(chip.classList).not.toContain('caps');
    expect(chip.textContent!.trim()).toBe('Lv4');
  });

  it('tints the three state tones rather than outlining them', () => {
    expect(SOURCE).toMatch(/\.good \{[^}]*background: var\(--pos-soft\)/);
    expect(SOURCE).toMatch(/\.warn \{[^}]*background: var\(--warn-soft\)/);
    expect(SOURCE).toMatch(/\.info \{[^}]*background: var\(--info-soft\)/);
  });

  it('grows to a 28px minimum on touch and narrow screens', () => {
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 639px\) \{([\s\S]*?)\n    \}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain('min-height: 28px');
  });

  it('no longer borrows --info for the level-4 band', () => {
    expect(SOURCE).not.toMatch(/\.q4 \{[^}]*--info/);
  });
});
