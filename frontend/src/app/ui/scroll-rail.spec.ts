import { describe, expect, it, vi } from 'vitest';

import { edgeFades, revealActive } from './scroll-rail';

/** jsdom lays nothing out: fake the three numbers a rail is measured by. */
function rail(scrollWidth: number, clientWidth: number, scrollLeft = 0): HTMLElement {
  const el = document.createElement('div');
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth });
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(el, 'scrollLeft', { configurable: true, value: scrollLeft });
  return el;
}

function item(): { el: HTMLElement; spy: ReturnType<typeof vi.fn> } {
  const el = document.createElement('button');
  const spy = vi.fn();
  Object.defineProperty(el, 'scrollIntoView', { configurable: true, value: spy });
  return { el, spy };
}

describe('edgeFades (v179 §3.3)', () => {
  it('shows no fade when everything fits', () => {
    expect(edgeFades(rail(300, 300))).toEqual({ start: false, end: false });
  });

  it('fades only the far edge at the start of an overflowing rail', () => {
    expect(edgeFades(rail(600, 300, 0))).toEqual({ start: false, end: true });
  });

  it('fades both edges part-way along', () => {
    expect(edgeFades(rail(600, 300, 150))).toEqual({ start: true, end: true });
  });

  it('fades only the near edge once scrolled to the end', () => {
    expect(edgeFades(rail(600, 300, 300))).toEqual({ start: true, end: false });
  });

  it('ignores a sub-pixel overflow (rounding, not hidden content)', () => {
    expect(edgeFades(rail(301, 300, 0))).toEqual({ start: false, end: false });
  });
});

describe('revealActive (v179 §6b.5)', () => {
  it('brings the active item into view along the rail, never jumping the page', () => {
    const { el, spy } = item();
    revealActive(rail(900, 390), el);
    expect(spy).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' });
  });

  it('does nothing when the rail does not overflow', () => {
    // The desktop settings rail is a vertical list: scrolling it "into view"
    // could only move the page.
    const { el, spy } = item();
    revealActive(rail(300, 300), el);
    expect(spy).not.toHaveBeenCalled();
  });

  it('does nothing without an active item', () => {
    expect(() => revealActive(rail(900, 390), null)).not.toThrow();
  });

  it('does nothing where scrollIntoView is missing (jsdom)', () => {
    const el = document.createElement('button');
    Object.defineProperty(el, 'scrollIntoView', { configurable: true, value: undefined });
    expect(() => revealActive(rail(900, 390), el)).not.toThrow();
  });
});
