import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { DateRange } from './date-range';

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
