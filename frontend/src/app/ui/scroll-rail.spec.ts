import { describe, expect, it, vi } from 'vitest';

import { edgeFades, revealActive } from './scroll-rail';

/** jsdom lays nothing out: fake the three numbers a rail is measured by. */
function rail(scrollWidth: number, clientWidth: number, scrollLeft = 0): HTMLElement {
  const el = document.createElement('div');
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth });
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth });
  Object.defineProperty(el, 'scrollLeft', { configurable: true, writable: true, value: scrollLeft });
  vi.spyOn(el, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, clientWidth, 44));
  return el;
}

function item(left = 0, right = 100): { el: HTMLElement; spy: ReturnType<typeof vi.fn> } {
  const el = document.createElement('button');
  const spy = vi.fn();
  Object.defineProperty(el, 'scrollIntoView', { configurable: true, value: spy });
  vi.spyOn(el, 'getBoundingClientRect').mockReturnValue(new DOMRect(left, 1000, right - left, 44));
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
  it('moves only far enough to reveal an item past the right edge', () => {
    const container = rail(900, 390);
    revealActive(container, item(550, 630).el);
    expect(container.scrollLeft).toBe(240);
  });

  it('moves only far enough to reveal an item past the left edge', () => {
    const container = rail(900, 390, 300);
    revealActive(container, item(-70, 10).el);
    expect(container.scrollLeft).toBe(230);
  });

  it('preserves ancestor scroll positions when an embedded rail is below the viewport', () => {
    const ancestor = document.createElement('main');
    const container = rail(900, 390);
    const { el, spy } = item(20, 80);
    ancestor.append(container);
    container.append(el);
    ancestor.scrollTop = 120;
    // jsdom has no native scrolling. Model its measured ancestor side effect.
    spy.mockImplementation(() => { ancestor.scrollTop = 900; });
    revealActive(container, el);
    expect(ancestor.scrollTop).toBe(120);
    expect(container.scrollLeft).toBe(0);
  });

  it('leaves a fully visible active item in place', () => {
    const container = rail(900, 390, 150);
    revealActive(container, item(100, 200).el);
    expect(container.scrollLeft).toBe(150);
  });

  it('does nothing when the rail does not overflow', () => {
    // The desktop settings rail is a vertical list: scrolling it "into view"
    // could only move the page.
    const container = rail(300, 300);
    revealActive(container, item(400, 480).el);
    expect(container.scrollLeft).toBe(0);
  });

  it('does nothing without an active item', () => {
    expect(() => revealActive(rail(900, 390), null)).not.toThrow();
  });

  it('reveals horizontally without depending on scrollIntoView support', () => {
    const container = rail(900, 390);
    const { el } = item(500, 580);
    Object.defineProperty(el, 'scrollIntoView', { configurable: true, value: undefined });
    revealActive(container, el);
    expect(container.scrollLeft).toBe(190);
  });
});
