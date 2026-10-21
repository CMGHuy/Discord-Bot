import { Signal, afterRenderEffect, signal } from '@angular/core';

/** A drawing narrower than this stops shrinking rather than crushing its labels. */
export const CHART_MIN_WIDTH = 240;

/**
 * The drawn width of an SVG chart, kept equal to its host box's width.
 *
 * An SVG with a fixed viewBox and `width: 100%` scales its text with the
 * box: a 320-unit viewBox in a 291px panel draws 11px labels at 10px (v179
 * layout audit, sub-11px text on a phone). Drawing in the box's own width
 * keeps one user unit = one CSS pixel, so `font-size: 11px` is 11px at every
 * width. `fallback` is the width until the first measure (and under jsdom,
 * which has no layout).
 */
export function chartWidth(host: () => HTMLElement | undefined, fallback: number): Signal<number> {
  const width = signal(fallback);
  afterRenderEffect(() => {
    const el = host();
    if (!el) return;
    const read = () => width.set(el.clientWidth > 0 ? Math.max(CHART_MIN_WIDTH, Math.round(el.clientWidth)) : fallback);
    read();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(read);
    observer.observe(el);
    return () => observer.disconnect();
  });
  return width;
}
