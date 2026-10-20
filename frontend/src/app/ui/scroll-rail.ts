/**
 * Shared measuring for a rail that scrolls sideways — v179 §3.3, §6b.5.
 *
 * Two rails need the same two answers: `sb-tab-bar` (Analytics' seven tabs on
 * a phone) and the System settings `nav.category-rail`. `sb-heat-grid`'s
 * scroll box uses the first. Before this module only the tab bar measured
 * its fades, and neither rail brought the active item into view, so a tab
 * chosen by the URL could load off-screen with nothing pointing at it.
 *
 * Pure DOM reads, no Angular: each caller decides when to call (after the
 * render in which its active item or its item list changed, and on scroll
 * and resize for the fades).
 */

/** Which edges currently hide content. 1px of slack absorbs sub-pixel
 *  rounding, which is not hidden content. */
export function edgeFades(el: HTMLElement): { start: boolean; end: boolean } {
  const overflow = el.scrollWidth - el.clientWidth;
  return {
    start: overflow > 1 && el.scrollLeft > 1,
    end: overflow > 1 && el.scrollLeft < overflow - 1,
  };
}

/**
 * Scroll `active` into view along `container`, if the container overflows.
 *
 * `block: 'nearest'` moves the page only when the item is out of view
 * vertically (it never is on load or after a click on it); `inline:
 * 'nearest'` scrolls the rail the least distance that shows the whole item.
 * A rail that does not overflow is left alone, so a vertical list (the
 * desktop settings rail) can never move the page. jsdom has no
 * `scrollIntoView`; the call is then a no-op rather than an error.
 */
export function revealActive(container: HTMLElement, active: Element | null): void {
  if (!active) return;
  const reveal = (active as HTMLElement).scrollIntoView as HTMLElement['scrollIntoView'] | undefined;
  if (typeof reveal !== 'function') return;
  if (container.scrollWidth - container.clientWidth <= 1) return;
  reveal.call(active, { block: 'nearest', inline: 'nearest' });
}
