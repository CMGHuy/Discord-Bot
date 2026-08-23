import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { TextInput } from './form-controls';

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
