import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection } from '@angular/core';
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

  /* v195 Phase 2: the hint sits right beside the title; the quiet meta
   * (N=, all-time, total) and the Table toggle sit together on the right. */
  it('keeps the hint beside the title and the meta on the right', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(PanelHeader);
    fixture.componentRef.setInput('title', 'Equity');
    fixture.componentRef.setInput('n', 972);
    fixture.componentRef.setInput('total', '−2,150.95 €');
    fixture.componentRef.setInput('hint', 'Pre-tax, paper trades.');
    fixture.componentRef.setInput('tableable', true);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const heading = el.querySelector('.heading')!;
    expect([...heading.children].map((child) => child.tagName.toLowerCase())).toEqual(['h2', 'sb-hint']);
    const meta = el.querySelector('header > .meta')!;
    for (const selector of ['.n', '.total', 'button.table']) {
      expect(meta.querySelector(selector), selector).not.toBeNull();
      expect(heading.querySelector(selector), selector).toBeNull();
    }
    expect(meta.classList).toContain('sb-meta');
  });
});

describe('PanelHeader: the one panel title (v186 D1)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/panel-header.ts'), 'utf8');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  /** A rule in the one-line styles string starts after whitespace or its backtick. */
  const rule = (selector: string) => SOURCE.match(new RegExp('[\\s`]' + esc(selector) + '\\s*\\{[^}]*\\}'))?.[0] ?? '';
  /** The same list as layout.spec.ts PANEL_TITLE: both primitives set one title. */
  const TITLE = [
    'font-family: var(--font-sans);',
    'font-weight: 600;',
    'font-size: var(--text-table);',
    'color: var(--text);',
    'letter-spacing: normal;',
  ];

  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('sets the title exactly like sb-panel: UI face, 600, the 13px table step, no transform', () => {
    const h2 = rule('h2');
    expect(h2).not.toContain('--text-body');
    for (const declaration of TITLE) expect(h2, declaration).toContain(declaration);
    expect(h2).not.toContain('text-transform');
    expect(h2).not.toContain('--text-subhead');
  });

  it('sets N= and all-time in the numeric face, in a readable colour', () => {
    const meta = rule('.n,.all-time');
    expect(meta).toContain('font-family: var(--font-num);');
    expect(meta).toContain('color: var(--text-muted);');
    expect(meta).not.toContain('--text-faint');
    expect(rule('.all-time')).toContain('color:var(--warn);');
  });

  it('renders the title text as given, with no label class', () => {
    const fixture = TestBed.createComponent(PanelHeader);
    fixture.componentRef.setInput('title', 'Equity');
    fixture.detectChanges();
    const h2 = (fixture.nativeElement as HTMLElement).querySelector('h2')!;
    expect(h2.className).toBe('');
    expect(h2.textContent).toBe('Equity');
  });
});

describe('PanelHeader total (v186 D4)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/panel-header.ts'), 'utf8');

  it('sets the total in the figure face at chip size, secondary colour', () => {
    const total = SOURCE.match(/\.total \{[^}]*\}/)![0];
    expect(total).toContain('font-family: var(--font-figure);');
    expect(total).toContain('font-weight: var(--figure-weight);');
    expect(total).toContain('letter-spacing: var(--figure-tracking);');
    expect(total).toContain('font-variant-numeric: tabular-nums;');
    expect(total).toMatch(/font-size:\s*var\(--text-chip\)/);
    expect(total).toMatch(/color:\s*var\(--text-secondary\)/);
  });

  it('drops the global num class from the total', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(PanelHeader);
    fixture.componentRef.setInput('title', 'Equity');
    fixture.componentRef.setInput('total', '+$1,240');
    fixture.detectChanges();
    const total = (fixture.nativeElement as HTMLElement).querySelector('.total')!;
    expect(total.textContent).toBe('+$1,240');
    expect(total.classList).not.toContain('num');
  });
});

@Component({
  imports: [PanelHeader],
  template: `
    <sb-panel-header [title]="'Equity'" [n]="12">
      <button header-actions type="button">Export</button>
    </sb-panel-header>
  `,
})
class ActionsHost {}

describe('PanelHeader header-actions slot (v195 Phase 2)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/panel-header.ts'), 'utf8');
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('projects [header-actions] into the right-hand meta group, after the meta', () => {
    const fixture = TestBed.createComponent(ActionsHost);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const action = el.querySelector('button[header-actions]')!;
    expect(action.closest('.meta')).not.toBeNull();
    expect(action.closest('.heading')).toBeNull();
    const n = el.querySelector('.meta .n')!;
    expect(n.compareDocumentPosition(action) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('right-aligns the meta group on the shared baseline and hides it when empty', () => {
    const meta = SOURCE.match(/[\s`]\.meta \{[^}]*\}/)?.[0] ?? '';
    expect(meta).toContain('justify-content: flex-end');
    expect(meta).toContain('margin-left: auto');
    expect(meta).toContain('align-items: baseline');
    expect(SOURCE).toMatch(/\.meta:empty \{\s*display: none;\s*\}/);
  });

  it('renders no meta group content and no hint for a bare title', () => {
    const fixture = TestBed.createComponent(PanelHeader);
    fixture.componentRef.setInput('title', 'Calibration');
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-hint')).toBeNull();
    expect(el.querySelector('.meta')!.children.length).toBe(0);
  });
});
