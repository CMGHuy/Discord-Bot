import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { DateRange } from './date-range';
import { Field } from './field';

function setup(from: string | null = null, to: string | null = null) {
  const f = TestBed.createComponent(DateRange);
  f.componentRef.setInput('from', from);
  f.componentRef.setInput('to', to);
  f.detectChanges();
  return f;
}

function input(f: ReturnType<typeof setup>, which: 'from' | 'to'): HTMLInputElement {
  return (f.nativeElement as HTMLElement).querySelector(`input.${which}`)!;
}

describe('DateRange (v85 D32)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders both bounds as native date inputs', () => {
    const f = setup();
    expect(input(f, 'from').type).toBe('date');
    expect(input(f, 'to').type).toBe('date');
  });

  it('emits both bounds when one changes', () => {
    const f = setup('2026-04-01', null);
    let emitted: unknown = null;
    f.componentInstance.changed.subscribe((v: unknown) => (emitted = v));
    const el = input(f, 'to');
    el.value = '2026-04-28';
    el.dispatchEvent(new Event('change'));
    expect(emitted).toEqual({ from: '2026-04-01', to: '2026-04-28' });
  });

  it('emits null for a cleared bound rather than an empty string', () => {
    const f = setup('2026-04-01', '2026-04-28');
    let emitted: { from: string | null; to: string | null } | null = null;
    f.componentInstance.changed.subscribe((v: { from: string | null; to: string | null }) => (emitted = v));
    const el = input(f, 'from');
    el.value = '';
    el.dispatchEvent(new Event('change'));
    expect(emitted!.from).toBeNull();
  });

  it('stops the end bound from preceding the start bound', () => {
    const f = setup('2026-04-20', null);
    expect(input(f, 'to').min).toBe('2026-04-20');
  });

  it('labels both inputs', () => {
    const f = setup();
    expect(input(f, 'from').getAttribute('aria-label')).toBe('From date');
    expect(input(f, 'to').getAttribute('aria-label')).toBe('To date');
  });
});

const RANGE_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/date-range.ts'), 'utf8');
const RANGE_PHONE = RANGE_SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';

@Component({
  imports: [Field, DateRange],
  template: `
    <sb-field [label]="label()" size="auto" [fullRow]="true">
      <sb-date-range [from]="from" [to]="null" (changed)="last = $event" />
    </sb-field>
  `,
})
class RangeInField {
  readonly label = signal('Opened');
  readonly from = '2026-04-01';
  last: unknown = null;
}

describe('DateRange as one field (v246 §A2)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function mount(label = 'Opened') {
    const f = TestBed.createComponent(RangeInField);
    f.componentInstance.label.set(label);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    return { f, from: el.querySelector('input.from') as HTMLInputElement, to: el.querySelector('input.to') as HTMLInputElement };
  }

  it('names both bounds after the field\'s one label', () => {
    const { from, to } = mount();
    expect(from.getAttribute('aria-label')).toBe('Opened from');
    expect(to.getAttribute('aria-label')).toBe('Opened to');
  });

  it('keeps its own bound names in a field with no label', () => {
    const { from, to } = mount('');
    expect(from.getAttribute('aria-label')).toBe('From date');
    expect(to.getAttribute('aria-label')).toBe('To date');
  });

  it('still emits both bounds from inside a field', () => {
    const { f, to } = mount();
    to.value = '2026-04-28';
    to.dispatchEvent(new Event('change'));
    expect(f.componentInstance.last).toEqual({ from: '2026-04-01', to: '2026-04-28' });
  });

  it('draws From and To at M width and the shared control height', () => {
    const rule = RANGE_SOURCE.match(/\n {4}input \{[^}]*\}/)?.[0] ?? '';
    expect(rule).toContain('width: var(--field-m)');
    expect(rule).toContain('height: var(--control-h)');
    expect(rule).toContain('min-width: 0');
  });

  it('takes the full row below 640px and splits it 50/50 between From and To', () => {
    expect(RANGE_PHONE).toMatch(/:host \{ display: block; width: 100%; \}/);
    expect(RANGE_PHONE).toMatch(/\.field \{ display: flex; \}/);
    expect(RANGE_PHONE).toMatch(/input \{ flex: 1 1 0; width: auto; \}/);
  });
});
