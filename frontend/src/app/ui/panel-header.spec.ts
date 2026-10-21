import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { PanelHeader } from './panel-header';

describe('PanelHeader', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  const render = (inputs: Record<string, unknown>) => { const fixture = TestBed.createComponent(PanelHeader); for (const [key, value] of Object.entries(inputs)) fixture.componentRef.setInput(key, value); fixture.detectChanges(); return { fixture, el: fixture.nativeElement as HTMLElement }; };
  it('states title, N and currency total', () => { const { el } = render({ title: 'Equity', n: 312, total: '+$1,240' }); expect(el.textContent).toContain('Equity'); expect(el.querySelector('.n')!.textContent).toContain('N=312'); expect(el.querySelector('.total')!.textContent).toBe('+$1,240'); expect(el.querySelector('.all-time')).toBeNull(); });
  it('badges all-time panels and hides unknown N', () => { const { el } = render({ title: 'Calibration', allTime: true }); expect(el.querySelector('.all-time')!.textContent).toContain('all-time'); expect(el.querySelector('.n')).toBeNull(); });
  it('toggles tableOpen', () => { const { fixture, el } = render({ title: 'By horizon', tableable: true }); (el.querySelector('button.table') as HTMLButtonElement).click(); fixture.detectChanges(); expect(fixture.componentInstance.tableOpen()).toBe(true); expect((el.querySelector('button.table') as HTMLButtonElement).getAttribute('aria-pressed')).toBe('true'); });
});

describe('PanelHeader alignment (v179 §3.4)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/panel-header.ts'), 'utf8');

  it('puts title, N=, total and hint on one baseline, one control tall', () => {
    expect(SOURCE).toMatch(/[\s`]header \{[^}]*align-items:\s*baseline/);
    expect(SOURCE).toMatch(/[\s`]header \{[^}]*min-height:\s*var\(--control-h\)/);
    expect(SOURCE).toMatch(/\.heading \{[^}]*align-items:\s*baseline/);
    expect(SOURCE).not.toMatch(/align-items:\s*center/);
  });

  it('does not let the 44px touch hint push its title off a header without one (v179 layout audit)', () => {
    // The hint's trigger is a 44px box on touch widths; baseline-aligned in the heading it made the line 44px
    // tall and put the title 2-3px lower than in a sibling panel's header with no hint. Its negative block
    // margin brings its layout height back to the 14px glyph, the hit area stays 44px.
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 1023px\) \{([^}]*\})\s*\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toMatch(/sb-hint \{[^}]*margin-block:\s*calc\(\(14px - var\(--control-h\)\) \/ 2\)/);
  });

  it('keeps N=, total and the hint inside the heading line', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(PanelHeader);
    fixture.componentRef.setInput('title', 'Equity');
    fixture.componentRef.setInput('n', 972);
    fixture.componentRef.setInput('total', '−2,150.95 €');
    fixture.componentRef.setInput('hint', 'Pre-tax, paper trades.');
    fixture.detectChanges();
    const heading = (fixture.nativeElement as HTMLElement).querySelector('.heading')!;
    for (const selector of ['h2', '.n', '.total', 'sb-hint']) {
      expect(heading.querySelector(selector), selector).not.toBeNull();
    }
  });
});
