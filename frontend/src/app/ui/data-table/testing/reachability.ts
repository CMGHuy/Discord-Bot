import { Provider, signal } from '@angular/core';

import { Viewport, ViewportService } from '../../breakpoints';

/**
 * Column reachability on a phone, read off the DOM -- spec v179 §7.5.
 *
 * Each migrated table's spec asserts that its compact row plus its row
 * drawer show every column the table shows today. These read the
 * `[data-col]` keys `sb-data-table` stamps, so that test stays a few lines.
 * Pass the `sb-data-table` element (or anything containing only one table)
 * as `root`.
 */

function keysIn(root: ParentNode, selector: string): string[] {
  return [...new Set([...root.querySelectorAll(selector)].map((el) => el.getAttribute('data-col') ?? ''))];
}

/** The first compact row's column keys, line 1 then line 2. */
export function compactKeys(root: ParentNode): string[] {
  const row = root.querySelector('li.compact-row');
  return row ? keysIn(row, '.line1 > [data-col], .line2 > [data-col]') : [];
}

/** The open row drawer's column keys, in drawer order. */
export function drawerKeys(root: ParentNode): string[] {
  return keysIn(root, 'sb-drawer.row-drawer dl.drawer-fields > [data-col]');
}

/** Taps compact row `index`. Run change detection afterwards. */
export function openRowDrawer(root: HTMLElement, index = 0): void {
  const hits = root.querySelectorAll<HTMLButtonElement>('li.compact-row > button.compact-hit');
  const hit = hits[index];
  if (!hit) throw new Error(`no compact row at index ${index} (found ${hits.length})`);
  hit.click();
}

/** A `ViewportService` that reads as a phone. jsdom never matches a media
 *  query, and a workspace spec cannot reach `sb-data-table`'s `cardsAt`;
 *  the app reads the service only through these three signals. */
export function phoneViewport(): Provider {
  return {
    provide: ViewportService,
    useValue: { viewport: signal<Viewport>('xs'), isPhone: signal(true), isNarrow: signal(true) },
  };
}
