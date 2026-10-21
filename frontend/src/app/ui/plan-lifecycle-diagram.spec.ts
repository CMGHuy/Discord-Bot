import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { ViewportService } from './breakpoints';
import { PlanLifecycleDiagram } from './plan-lifecycle-diagram';

/** v179 layout audit: the SVG's viewBox shrinks its text to 4.7-5.2px on a phone, so below `sm` the same
 *  state machine is a vertical stepper of real text; tablet and desktop keep the diagram. */
describe('PlanLifecycleDiagram', () => {
  function render(phone: boolean): HTMLElement {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: ViewportService, useValue: { isPhone: signal(phone) } }],
    });
    const fixture = TestBed.createComponent(PlanLifecycleDiagram);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  const text = (el: Element) => (el.textContent ?? '').replace(/\s+/g, ' ').trim();

  it('keeps the SVG diagram at tablet and desktop widths, with no stepper', () => {
    const el = render(false);
    expect(el.querySelector('svg[role="img"]')).not.toBeNull();
    expect(el.querySelector('ol.stepper')).toBeNull();
  });

  it('reflows to a vertical stepper on phones: no SVG, one step per state in lifecycle order', () => {
    const el = render(true);
    expect(el.querySelector('svg')).toBeNull();
    const steps = [...el.querySelectorAll('ol.stepper > li.step')];
    expect(steps.map((s) => s.querySelector('.state')!.textContent!.trim()))
      .toEqual(['PENDING', 'ACTIVE', 'PARTIAL', 'CLOSED', 'CANCELLED']);
  });

  it('carries every transition of the diagram, with its trigger', () => {
    const steps = [...render(true).querySelectorAll('ol.stepper > li.step')].map(text);
    expect(steps[0]).toContain('fills');
    expect(steps[0]).toMatch(/ACTIVE/);
    expect(steps[0]).toMatch(/expires \/ invalidated/);
    expect(steps[0]).toMatch(/CANCELLED/);
    expect(steps[1]).toContain('TP1 hit');
    expect(steps[1]).toMatch(/stop hit \(before TP1\)/);
    expect(steps[2]).toContain('TP2 / trail stop');
  });

  it('marks CLOSED and CANCELLED as where a plan ends', () => {
    const steps = [...render(true).querySelectorAll('ol.stepper > li.step')];
    expect(steps.map((s) => s.classList.contains('terminal'))).toEqual([false, false, false, true, true]);
  });

  it('names the stepper for assistive technology instead of hiding it in an image role', () => {
    const list = render(true).querySelector('ol.stepper')!;
    expect(list.getAttribute('aria-label')).toBe('Plan lifecycle');
    expect(list.closest('[role="img"]')).toBeNull();
  });

  it('sizes the diagram text in user units so it renders at the 11px floor however far the viewBox shrinks', async () => {
    const original = Object.getOwnPropertyDescriptor(Element.prototype, 'clientWidth')!;
    Object.defineProperty(Element.prototype, 'clientWidth', {
      configurable: true, get() { return (this as HTMLElement).id.startsWith('root') ? 340 : 0; /* the TestBed host */ },
    });
    try {
      TestBed.configureTestingModule({
        providers: [provideZonelessChangeDetection(), { provide: ViewportService, useValue: { isPhone: signal(false) } }],
      });
      const fixture = TestBed.createComponent(PlanLifecycleDiagram);
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();
      // 340px of a 680-unit viewBox is half scale: 11px text needs 22 units.
      expect((fixture.nativeElement as HTMLElement).style.getPropertyValue('--lc-scale')).toBe('0.5');
    } finally {
      Object.defineProperty(Element.prototype, 'clientWidth', original);
    }
    const src = readFileSync(join(process.cwd(), 'src/app/ui/plan-lifecycle-diagram.ts'), 'utf8');
    expect(src).toMatch(/\.edge-label \{[^}]*font-size:\s*calc\(var\(--text-micro\) \/ var\(--lc-scale, 1\)\)/s);
    expect(src).toMatch(/\.node text \{[^}]*font-size:\s*calc\(var\(--text-chip\) \/ var\(--lc-scale, 1\)\)/s);
  });

  it('sets the stepper text at the 11px floor tokens and lets it wrap, never scroll sideways', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/ui/plan-lifecycle-diagram.ts'), 'utf8');
    expect(src).toMatch(/\.stepper[^}]*\{[^}]*font-size:\s*var\(--text-chip\)/s);
    expect(src).toMatch(/overflow-wrap:\s*anywhere/);
    expect(src).not.toMatch(/overflow-x:\s*(auto|scroll)/);
  });
});
