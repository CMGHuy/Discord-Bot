import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { ShareBar, ShareSegment } from './share-bar';
const render = (segments: ShareSegment[]) => { const fixture = TestBed.createComponent(ShareBar); fixture.componentRef.setInput('segments', segments); fixture.componentRef.setInput('label', 'Outcome'); fixture.detectChanges(); return fixture.nativeElement as HTMLElement; };
describe('ShareBar', () => { beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] })); it('sizes and labels segments by share', () => { const el = render([{ label: 'Wins', count: 53, tone: 'pos' }, { label: 'Losses', count: 47, tone: 'neg' }]); expect([...el.querySelectorAll('.seg')].map((s) => (s as HTMLElement).style.flexGrow)).toEqual(['53', '47']); expect(el.querySelector('.legend')!.textContent).toContain('53%'); expect([...el.querySelectorAll('.seg')].every((s) => s.getAttribute('tabindex') === '0')).toBe(true); }); it('labels an empty composition', () => { const el = render([{ label: 'Wins', count: 0 }, { label: 'Losses', count: 0 }]); expect(el.querySelectorAll('.seg').length).toBe(0); expect(el.textContent).toContain('no observations'); }); });

describe('ShareBar containment (v179 §3.3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/share-bar.ts'), 'utf8');

  it('has a host that can shrink inside a grid track', () => {
    expect(src).toContain(':host { display:block; min-width:0; }');
  });

  it('lets a long legend item break instead of pushing the page wide', () => {
    expect(src).toMatch(/\.legend li \{[^}]*min-width:0;[^}]*flex-wrap:wrap;/);
    expect(src).toMatch(/\.legend li span:not\(\.key\) \{ overflow-wrap:anywhere; \}/);
  });
});

describe('ShareBar reads SVG_CHART_TOKENS (v246 §A3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/share-bar.ts'), 'utf8');

  it('imports the shared tokens and declares no chart ink, radius or gap of its own', () => {
    expect(src).toMatch(/import \{[^}]*SVG_CHART_TOKENS[^}]*\} from '\.\/chart\/chart-theme'/);
    expect(src).not.toMatch(/var\(--(pos|neg|accent|radius-sm)\)/);
    expect(src).not.toContain('gap:2px');
  });

  it('takes the tones, the segment gap and the radius from the tokens', () => {
    expect(src).toContain("[data-tone='pos'] { background:var(${SVG_CHART_TOKENS.pos}); }");
    expect(src).toContain("[data-tone='neg'] { background:var(${SVG_CHART_TOKENS.neg}); }");
    expect(src).toContain("[data-tone='accent'] { background:var(${SVG_CHART_TOKENS.line}); }");
    expect(src).toContain('gap:${SVG_CHART_TOKENS.barGap}px;');
    expect(src).toContain('border-radius:var(${SVG_CHART_TOKENS.barRadius});');
  });
});
