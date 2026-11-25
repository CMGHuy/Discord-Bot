import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Checkbox, Select, TextInput } from './form-controls';
import { Field } from './field';

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
 * the --bg well, behind the control border (v240: --control-border, 3:1 in
 * Navy); the accent is the focus ring and the checkbox tick only. */
describe('v195 Phase 2: flat fields', () => {
  const field = (tag: 'select' | 'input') => SOURCE.match(new RegExp(`\\n {4}${tag} \\{[^}]*\\}`))?.[0] ?? '';

  it('fills the select and the text input with the --bg well behind the control border', () => {
    for (const tag of ['select', 'input'] as const) {
      const rule = field(tag);
      expect(rule, tag).toContain('background: var(--bg);');
      expect(rule, tag).toContain('border: 1px solid var(--control-border);');
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

const OPTIONS = [{ value: 'rsi', label: 'RSI' }];

@Component({
  imports: [Field, Select, TextInput],
  template: `
    <sb-field id="f-strategy" label="Strategy" size="m">
      <sb-select id="strategy" label="Strategy" [options]="options" />
    </sb-field>
    <sb-field id="f-ticker" label="Ticker" size="l">
      <sb-text-input id="ticker" placeholder="AAPL" />
    </sb-field>
    <sb-field id="f-bare" size="s">
      <sb-select id="bare" [options]="options" ariaLabel="Horizon filter" />
    </sb-field>
    <sb-field id="f-origin" label="Origin" size="s">
      <sb-select id="origin" [options]="options" ariaLabel="Plan origin" />
    </sb-field>
    <sb-field id="f-empty" size="s">
      <sb-select id="empty" [options]="options" />
    </sb-field>
    <sb-select id="standalone" label="Strategy" [options]="options" />
  `,
})
class InField {
  readonly options = OPTIONS;
}

describe('v246 §A2: controls inside sb-field', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function mount(): HTMLElement {
    const f = TestBed.createComponent(InField);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  const control = (el: HTMLElement, id: string) =>
    el.querySelector(`#${id} select, #${id} input`) as HTMLElement;

  it('draws one label per field: the field\'s, never the control\'s own', () => {
    const el = mount();
    for (const id of ['f-strategy', 'f-ticker', 'f-origin']) {
      expect(el.querySelectorAll(`#${id} .sb-label`)).toHaveLength(1);
      expect(el.querySelector(`#${id} .sb-label`)!.classList).toContain('field-label');
    }
  });

  it('names the control by its own label, then its ariaLabel, then the field\'s label', () => {
    const el = mount();
    expect(control(el, 'strategy').getAttribute('aria-label')).toBe('Strategy');
    expect(control(el, 'ticker').getAttribute('aria-label')).toBe('Ticker');
    expect(control(el, 'bare').getAttribute('aria-label')).toBe('Horizon filter');
    expect(control(el, 'origin').getAttribute('aria-label')).toBe('Plan origin');
  });

  it('drops the aria-label attribute rather than printing an empty one when nothing names the control', () => {
    expect(control(mount(), 'empty').hasAttribute('aria-label')).toBe(false);
  });

  it('marks a control inside a field, and only there', () => {
    const el = mount();
    expect(el.querySelector('#strategy')!.classList).toContain('in-field');
    expect(el.querySelector('#ticker')!.classList).toContain('in-field');
    expect(el.querySelector('#standalone')!.classList).not.toContain('in-field');
  });

  it('leaves a standalone control exactly as before: its own visible label, no aria-label', () => {
    const el = mount();
    expect(el.querySelector('#standalone .sb-label')!.textContent!.trim()).toBe('Strategy');
    expect(control(el, 'standalone').hasAttribute('aria-label')).toBe(false);
  });

  it('sizes the select and the input from the field\'s width, native width standalone', () => {
    const block = (selector: string, from: string) => {
      const at = SOURCE.indexOf(from);
      return SOURCE.slice(at).match(new RegExp(`\\n {4}${selector} \\{[^}]*\\}`))?.[0] ?? '';
    };
    expect(block('select', "selector: 'sb-select'")).toContain('width: var(--sb-control-w, auto)');
    expect(block('input', "selector: 'sb-text-input'")).toContain('width: var(--sb-control-w, auto)');
    expect(SOURCE.match(/:host\(\.in-field\) \{ display: block;/g)?.length ?? 0).toBe(2);
    expect(SOURCE.match(/:host\(\.in-field\) \.field \{ display: flex; \}/g)?.length ?? 0).toBe(2);
  });
});
