import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { PlanCell } from './plan-cell';

function render(entry: number | null, target: number | null, stop: number | null) {
  const f = TestBed.createComponent(PlanCell);
  f.componentRef.setInput('entry', entry);
  f.componentRef.setInput('target', target);
  f.componentRef.setInput('stop', stop);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('PlanCell', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('reads entry -> target / stop for a long', () => {
    expect(render(178, 195, 170).textContent!.replace(/\s+/g, ' ').trim())
      .toBe('178.00 → 195.00 / 170.00');
  });

  it('reads the same way for a short, where the target is the lower number', () => {
    expect(render(178, 162, 186).textContent!.replace(/\s+/g, ' ').trim())
      .toBe('178.00 → 162.00 / 186.00');
  });

  it('colours target and stop by role, not by which is larger', () => {
    // The regression this guards: inferring role from magnitude reads
    // correctly on every long and inverts on every short.
    const el = render(178, 162, 186);
    expect(el.querySelector('.target')!.textContent!.trim()).toBe('162.00');
    expect(el.querySelector('.stop')!.textContent!.trim()).toBe('186.00');
  });

  it('renders an em dash for a missing level rather than NaN', () => {
    expect(render(178, null, 170).textContent).toContain('—');
  });

  it('carries the spelled-out tooltip', () => {
    expect(render(178, 195, 170).querySelector('[title]')!.getAttribute('title'))
      .toBe('Entry 178.00 · Target 195.00 · Stop 170.00');
  });
});
