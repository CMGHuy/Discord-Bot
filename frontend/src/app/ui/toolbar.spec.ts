import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, beforeEach, expect, it } from 'vitest';

import { Viewport } from './breakpoints';
import { Toolbar, ToolbarControl } from './toolbar';

@Component({
  imports: [Toolbar],
  template: `
    <sb-toolbar [controls]="controls()" [viewportAt]="viewportAt()">
      <button slot="status">Status</button>
      <button slot="ticker">Ticker</button>
      <button slot="badge">Badge</button>
    </sb-toolbar>
  `,
})
class Host {
  readonly viewportAt = signal<Viewport | null>(null);
  readonly controls = signal<ToolbarControl[]>([
    { id: 'status', label: 'Status' },
    { id: 'ticker', label: 'Ticker', inlineFrom: 'md' },
    { id: 'badge', label: 'Badge', inlineFrom: 'md' },
  ]);
}

describe('sb-toolbar', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.viewportAt.set('sm');
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;

  it('keeps above-floor controls inline', () => {
    expect(el().querySelector('.toolbar-inline [slot="status"]')).not.toBeNull();
  });

  it('moves below-floor controls into the sheet, not out of the DOM', () => {
    expect(el().querySelector('.toolbar-inline [slot="ticker"]')).toBeNull();
    expect(el().querySelector('.toolbar-sheet [slot="ticker"]')).not.toBeNull();
  });

  it('starts with the sheet closed', () => {
    expect(el().querySelector('.toolbar-sheet-button')!.getAttribute('aria-expanded'))
      .toBe('false');
  });

  it('offers no sheet button when nothing is demoted', () => {
    host.viewportAt.set('xl');
    fixture.detectChanges();
    expect(el().querySelector('.toolbar-sheet-button')).toBeNull();
  });

  it('names how many demoted controls it holds', () => {
    expect(el().querySelector('.toolbar-sheet-button')!.textContent).toContain('2');
  });

  it('moves the same element back inline rather than rebuilding it', () => {
    // The node identity is the point: a control destroyed and recreated at a
    // breakpoint loses its focus, its open dropdown and any uncommitted text.
    const demoted = el().querySelector('.toolbar-sheet [slot="ticker"]');
    host.viewportAt.set('xl');
    fixture.detectChanges();
    expect(el().querySelector('.toolbar-inline [slot="ticker"]')).toBe(demoted);
  });
});

describe('sb-toolbar active badge', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.viewportAt.set('sm');
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const button = () => el().querySelector('.toolbar-sheet-button')!;

  it('shows no active marker when every demoted control is at its default', () => {
    expect(el().querySelector('.active-dot')).toBeNull();
    expect(button().getAttribute('aria-label')).toBe('Filters — 2 hidden');
  });

  it('marks the sheet when a demoted control is engaged', () => {
    host.controls.set([
      { id: 'status', label: 'Status' },
      { id: 'ticker', label: 'Ticker', inlineFrom: 'md', active: true },
      { id: 'badge', label: 'Badge', inlineFrom: 'md' },
    ]);
    fixture.detectChanges();
    expect(el().querySelector('.active-dot')).not.toBeNull();
    expect(button().getAttribute('aria-label')).toBe('Filters — 2 hidden, 1 active');
  });

  it('counts only DEMOTED actives — an inline active is already visible', () => {
    host.controls.set([
      { id: 'status', label: 'Status', active: true },
      { id: 'ticker', label: 'Ticker', inlineFrom: 'md' },
      { id: 'badge', label: 'Badge', inlineFrom: 'md' },
    ]);
    fixture.detectChanges();
    expect(el().querySelector('.active-dot')).toBeNull();
  });
});

const TOOLBAR_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/toolbar.ts'), 'utf8');
const toolbarRule = (selector: string) =>
  TOOLBAR_SOURCE.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\{[^}]*\\}`))?.[0] ?? '';

describe('sb-toolbar one row pattern (v179 §3.3)', () => {
  let fixture: ComponentFixture<Host>;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    fixture.componentInstance.viewportAt.set('sm');
    fixture.detectChanges();
  });

  it('styles Filters as a normal control button, not the browser-default grey block', () => {
    const rule = toolbarRule('.toolbar-sheet-button');
    expect(rule).toContain('min-height: var(--control-h)');
    expect(rule).toContain('background: var(--surface-raised)');
    expect(rule).toContain('border: 1px solid var(--border)');
    expect(rule).toContain('font: inherit');
  });

  it('shows the demoted count as a numeric badge', () => {
    const badge = (fixture.nativeElement as HTMLElement).querySelector('.toolbar-sheet-button .count')!;
    expect(badge.classList).toContain('num');
    expect(badge.textContent!.trim()).toBe('2');
    expect(toolbarRule('.count')).toContain('border-radius: var(--chip-radius)');
    // v195 Phase 2: a count is not a state, so it takes no accent.
    expect(toolbarRule('.count')).toContain('border: 1px solid var(--border-strong)');
    expect(toolbarRule('.count')).toContain('color: var(--text-secondary)');
    expect(toolbarRule('.count')).not.toContain('accent');
    expect(toolbarRule('.count')).not.toContain('background');
  });

  it('edges the Filters button in the accent while its sheet is open, its one state (v195 Phase 2)', () => {
    const button = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.toolbar-sheet-button')!;
    button.click();
    fixture.detectChanges();
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(toolbarRule(".toolbar-sheet-button[aria-expanded='true']")).toContain('border-color: var(--accent)');
  });

  it('lays the open sheet out in equal columns, two on a phone-width bar', () => {
    expect(TOOLBAR_SOURCE).toMatch(/:host \{[^}]*container: toolbar \/ inline-size;/);
    expect(toolbarRule('.toolbar-sheet.open')).toContain('display: grid');
    expect(TOOLBAR_SOURCE).toMatch(
      /@container toolbar \(max-width: 639px\) \{\s*\.toolbar-sheet\.open \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/,
    );
  });
});


describe('sb-toolbar phone flex ownership (v179 review)', () => {
  it('grows into the width allocated by a panel action slot', () => {
    const host = toolbarRule(':host');
    expect(host).toContain('flex: 1 1 auto');
    expect(host).toContain('min-width: 0');
  });

  it('puts projected controls and Filters in one flex context below the chip line', () => {
    // A full-width chips host inside a boxed inline row consumes the whole
    // outer line, leaving Filters below Columns instead of beside it.
    const phone = TOOLBAR_SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';
    expect(phone).toMatch(/\.toolbar-inline \{[^}]*display: contents;/);
  });
});

/* v195 Phase 2: buttons, chips, segmented, form controls, filter bar,
 * control bar and toolbar are flat, 4px, and spend the accent only on a
 * keyboard focus ring and on selected or engaged state. button.ts is gated
 * by its own spec (V195-8); these are the other six. Source text: jsdom
 * computes no component style. */
const FAMILY = ['chip.ts', 'segmented.ts', 'form-controls.ts', 'filter-bar.ts', 'control-bar.ts', 'toolbar.ts'];
const stylesOf = (file: string) =>
  [...readFileSync(join(process.cwd(), 'src/app/ui', file), 'utf8').matchAll(/styles:\s*`([\s\S]*?)`/g)]
    .map(([, css]) => css)
    .join('\n')
    .replace(/\/\*[\s\S]*?\*\//g, '');
const rulesOf = (css: string) =>
  [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({ selector: selector.trim(), body }));
/** Where the accent may appear: a focus ring, a selected option, an open or engaged filter. */
const ACCENT_STATE = /:focus-visible|\.current\b|\.active\b|\[aria-expanded='true'\]|\[aria-pressed='true'\]/;

describe('the control family is flat (v195 Phase 2)', () => {
  it.each(FAMILY)('%s casts no shadow, paints no gradient, mixes no colour and moves nothing', (file) => {
    const css = stylesOf(file);
    expect(css.length).toBeGreaterThan(0);
    expect(css).not.toMatch(/box-shadow\s*:/);
    expect(css).not.toContain('gradient(');
    expect(css).not.toContain('color-mix(');
    expect(css).not.toMatch(/(?<![-\w])transform\s*:/);
  });

  it.each(FAMILY)('%s rounds every corner with the 4px control or chip radius', (file) => {
    const radii = [...stylesOf(file).matchAll(/border(?:-[a-z]+)*-radius:\s*([^;}]+)/g)].map(([, value]) => value.trim());
    for (const value of radii) expect(['var(--control-radius)', 'var(--chip-radius)'], `${file}: ${value}`).toContain(value);
  });

  it.each(FAMILY)('%s spends the accent only on focus, selected or engaged state', (file) => {
    for (const { selector, body } of rulesOf(stylesOf(file))) {
      for (const declaration of body.split(';').filter((d) => d.includes('var(--accent'))) {
        const allowed = ACCENT_STATE.test(selector) || declaration.trim().startsWith('accent-color:');
        expect(allowed, `${file}: ${selector} { ${declaration.trim()} }`).toBe(true);
      }
    }
  });
});
