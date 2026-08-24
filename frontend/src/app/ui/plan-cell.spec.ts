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

  /* -- SR53: the trigger fallback -------------------------------------- */

  function renderWithTrigger(entry: number | null, trigger: number | null) {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', entry);
    f.componentRef.setInput('target', 195);
    f.componentRef.setInput('stop', 170);
    f.componentRef.setInput('trigger', trigger);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('shows the trigger when nothing has filled yet', () => {
    // A PENDING plan has no entry. Without this the cell read
    // "— → 195.00 / 170.00": both levels, and no price that would put you in
    // them, which is the number the old plans board led with.
    const el = renderWithTrigger(null, 176.5);
    expect(el.textContent!.replace(/\s+/g, ' ').trim())
      .toBe('176.50 → 195.00 / 170.00');
  });

  it('says in the tooltip that the first number is a trigger', () => {
    // The dashed styling alone does not distinguish a waiting plan from a
    // filled one, and a trigger read as a fill is a position you think you
    // have and do not.
    expect(renderWithTrigger(null, 176.5).querySelector('[title]')!.getAttribute('title'))
      .toBe('Trigger 176.50 (not yet filled) · Target 195.00 · Stop 170.00');
  });

  it('marks the trigger as provisional', () => {
    expect(renderWithTrigger(null, 176.5).querySelector('.entry')!.classList
      .contains('pending')).toBe(true);
  });

  it('prefers the fill once there is one', () => {
    // Both are present on a filled plan: the trigger is history at that point,
    // and the entry is what the position actually cost.
    const el = renderWithTrigger(178, 176.5);
    expect(el.querySelector('.entry')!.textContent!.trim()).toBe('178.00');
    expect(el.querySelector('.entry')!.classList.contains('pending')).toBe(false);
  });

  it('still reads an em dash when there is neither', () => {
    const el = renderWithTrigger(null, null);
    expect(el.querySelector('.entry')!.textContent!.trim()).toBe('—');
    expect(el.querySelector('.entry')!.classList.contains('pending')).toBe(false);
  });

  /* -- the trailing-stop tooltip ---------------------------------------- */

  it('says "Trailing stop" once TP1 has banked, not plain "Stop"', () => {
    // A PARTIAL short's stop legitimately sits BELOW entry (it protects the
    // profit TP1 already locked in, not the original risk) -- which reads
    // as backwards unless the tooltip says why.
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 71.64);
    f.componentRef.setInput('target', null);
    f.componentRef.setInput('stop', 69.85);
    f.componentRef.setInput('trailing', true);
    f.detectChanges();
    expect(f.nativeElement.querySelector('[title]').getAttribute('title'))
      .toBe('Entry 71.64 · Target — · Trailing stop 69.85');
  });

  it('says plain "Stop" when not trailing (the default)', () => {
    expect(render(178, 195, 170).querySelector('[title]')!.getAttribute('title'))
      .toBe('Entry 178.00 · Target 195.00 · Stop 170.00');
  });
});
