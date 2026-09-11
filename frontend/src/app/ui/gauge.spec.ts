import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Gauge } from './gauge';

function render(inputs: Record<string, unknown>): HTMLElement {
  const f = TestBed.createComponent(Gauge);
  f.componentRef.setInput('label', 'Heat utilisation');
  f.componentRef.setInput('value', 62);
  for (const [key, val] of Object.entries(inputs)) f.componentRef.setInput(key, val);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.gauge')!;
}

describe('Gauge (v85 D36)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('prints the value', () => {
    expect(render({}).querySelector('.readout')!.textContent).toContain('62');
  });

  it('prints a null value as no-value', () => {
    expect(render({ value: null }).querySelector('.readout')!.textContent!.trim()).toBe('—');
  });

  it('prints the true figure past the maximum rather than clamping it', () => {
    expect(render({ value: 130 }).querySelector('.readout')!.textContent).toContain('130');
  });

  it('clamps only the needle', () => {
    const el = render({ value: 130 });
    const angle = Number(el.querySelector('.needle')!.getAttribute('data-angle'));
    expect(angle).toBe(180);
  });

  it('marks the over-limit state with more than colour', () => {
    const el = render({ value: 130 });
    expect(el.classList).toContain('over');
    expect(el.querySelector('.readout')!.textContent).toContain('over limit');
  });

  it('does not mark exactly at the limit as over', () => {
    expect(render({ value: 100 }).classList).not.toContain('over');
  });

  it('exposes the reading to assistive tech', () => {
    const el = render({ value: 62 });
    expect(el.getAttribute('role')).toBe('meter');
    expect(el.getAttribute('aria-valuenow')).toBe('62');
  });
});
