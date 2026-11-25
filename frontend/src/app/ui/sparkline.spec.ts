import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Sparkline } from './sparkline';

function render(points: readonly number[]): SVGPathElement | null {
  const fixture = TestBed.createComponent(Sparkline);
  fixture.componentRef.setInput('points', points);
  fixture.detectChanges();
  return (fixture.nativeElement as HTMLElement).querySelector('path');
}

describe('Sparkline tone (v246 §A3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('tones the line by net direction, first point to last', () => {
    expect(render([1, 3, 2])!.classList.contains('pos')).toBe(true);
    expect(render([3, 1, 2])!.classList.contains('neg')).toBe(true);
    expect(render([2, 5, 2])!.classList.length).toBe(0);
  });

  it('draws nothing for no points and an untoned line for one', () => {
    expect(render([])).toBeNull();
    expect(render([4])!.classList.length).toBe(0);
  });
});

describe('Sparkline reads SVG_CHART_TOKENS (v246 §A3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/sparkline.ts'), 'utf8');

  it('takes its stroke width and gain/loss inks from the shared tokens', () => {
    expect(src).toMatch(/import \{[^}]*SVG_CHART_TOKENS[^}]*\} from '\.\/chart\/chart-theme'/);
    expect(src).toContain('stroke-width: ${SVG_CHART_TOKENS.strokeWidthThin};');
    expect(src).toContain('.pos { stroke: var(${SVG_CHART_TOKENS.pos}); }');
    expect(src).toContain('.neg { stroke: var(${SVG_CHART_TOKENS.neg}); }');
    expect(src).not.toMatch(/stroke-width:\s*[\d.]/);
    expect(src).not.toMatch(/var\(--(pos|neg)\)/);
  });
});
