import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { IncompleteNote } from './incomplete-note';

function text(missing: number): string {
  const f = TestBed.createComponent(IncompleteNote);
  f.componentRef.setInput('missing', missing);
  f.detectChanges();
  return ((f.nativeElement as HTMLElement).textContent ?? '').trim();
}

describe('sb-incomplete-note (v201)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('renders nothing at 0', () => expect(text(0)).toBe(''));
  it('is singular at 1', () => expect(text(1)).toBe('incomplete: 1 position unpriced'));
  it('is plural past 1', () => expect(text(3)).toBe('incomplete: 3 positions unpriced'));
});
