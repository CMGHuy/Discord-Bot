import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Checkbox, Select, TextInput } from './form-controls';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/form-controls.ts'), 'utf8');

function render(type: 'text' | 'search' | 'number' | 'password' | 'date') {
  const f = TestBed.createComponent(TextInput);
  f.componentRef.setInput('type', type);
  f.componentRef.setInput('ariaLabel', 'field');
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('input')!;
}

describe('TextInput', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders a native date picker for type=date', () => {
    expect(render('date').getAttribute('type')).toBe('date');
  });

  it('still renders the pre-existing types', () => {
    for (const t of ['text', 'search', 'number', 'password'] as const) {
      expect(render(t).getAttribute('type')).toBe(t);
    }
  });
});

describe('v80 D4: form controls', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('labels all three controls with the one shared label style', () => {
    const select = TestBed.createComponent(Select);
    select.componentRef.setInput('options', []);
    select.componentRef.setInput('label', 'Strategy');
    select.detectChanges();
    expect((select.nativeElement as HTMLElement).querySelector('.sb-label')!.textContent!.trim())
      .toBe('Strategy');

    const input = TestBed.createComponent(TextInput);
    input.componentRef.setInput('label', 'Ticker');
    input.detectChanges();
    expect((input.nativeElement as HTMLElement).querySelector('.sb-label')!.textContent!.trim())
      .toBe('Ticker');

    const box = TestBed.createComponent(Checkbox);
    box.componentRef.setInput('label', 'Has note');
    box.componentRef.setInput('topLabel', 'Filter');
    box.detectChanges();
    expect((box.nativeElement as HTMLElement).querySelector('.top-label')!.classList)
      .toContain('sb-label');
  });

  it('declares no label typography of its own', () => {
    expect(SOURCE).not.toMatch(/text-transform:\s*uppercase/);
    expect(SOURCE).not.toMatch(/letter-spacing:\s*0\.1em/);
  });

  it('sizes field text with --text-control, which is 16px on touch', () => {
    expect(SOURCE.match(/font-size: var\(--text-control\)/g)?.length ?? 0).toBeGreaterThanOrEqual(2);
  });

  it('never prints readable text in the divider-only grey', () => {
    expect(SOURCE).not.toContain('--text-faint');
  });

  it('lets a text input shrink to a narrow grid cell instead of keeping the native 20-character width (v179 layout audit)', () => {
    // At 390 the filter bar's two-column grid gave the host 141px while the input's intrinsic width kept
    // the label 233px wide, so the field's label was cut by the panel.
    const at = SOURCE.indexOf("selector: 'sb-text-input'");
    const styles = SOURCE.slice(at, SOURCE.indexOf('export class TextInput', at));
    expect(styles).toMatch(/:host \{ min-width: 0; \}/);
    expect(styles).toMatch(/\.field \{[^}]*max-width: 100%/);
    expect(styles).toMatch(/\n {4}input \{[^}]*min-width: 0;/);
  });
});

/* v195 Phase 2: since V195-3 a panel is the flat --surface, so a field on
 * --surface had no fill step left against it. Fields sit one step down, on
 * the --bg well, behind the strong hairline; the accent is the focus ring
 * and the checkbox tick only. */
describe('v195 Phase 2: flat fields', () => {
  const field = (tag: 'select' | 'input') => SOURCE.match(new RegExp(`\\n {4}${tag} \\{[^}]*\\}`))?.[0] ?? '';

  it('fills the select and the text input with the --bg well behind the strong hairline', () => {
    for (const tag of ['select', 'input'] as const) {
      const rule = field(tag);
      expect(rule, tag).toContain('background: var(--bg);');
      expect(rule, tag).toContain('border: 1px solid var(--border-strong);');
      expect(rule, tag).toContain('border-radius: var(--control-radius);');
      expect(rule, tag).toContain('transition: border-color var(--transition);');
    }
    expect(SOURCE).not.toContain('background: var(--surface);');
  });

  it('keeps the accent to the focus ring and the checkbox tick', () => {
    expect(SOURCE).toMatch(/select:focus-visible \{ outline: 1px solid var\(--accent\); outline-offset: 1px; \}/);
    expect(SOURCE).toMatch(/input:focus-visible \{ outline: 1px solid var\(--accent\); outline-offset: 1px; \}/);
    expect(SOURCE).toMatch(/input \{ accent-color: var\(--accent\); \}/);
  });
});
