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
});
