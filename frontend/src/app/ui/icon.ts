import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * The icon set — spec v18 Decision 8.
 *
 * **Hand-authored, no package, no font, no CDN.** The repo's zero-third-party
 * constraint is not an aesthetic preference: an icon font is a network request
 * to somebody else's host on every page load, and an icon package is tens of
 * thousands of glyphs shipped to use eleven. Eleven paths cost less than the
 * dependency's own README.
 *
 * All stroke, no fill, on a 16×16 grid at 1.5 stroke width, so the whole set
 * looks like one hand and scales without hinting. `currentColor` is what lets
 * a single definition serve an active nav entry, a hovered one and a muted one
 * without three copies of the path data.
 *
 * Always `aria-hidden`. The accessible name belongs on the control the icon
 * sits inside — a nav link that labels itself AND contains a labelled icon
 * announces "Trades Trades".
 */
export const ICON_NAMES = [
  'dashboard',
  'trades',
  'analytics',
  'watchlist',
  'risk',
  'system',
  'versions',
  'collapse',
  'expand',
  'profile',
  'signout',
  'menu',
] as const;

export type IconName = (typeof ICON_NAMES)[number];

/** Path data only — every shared attribute lives on the `<svg>` below. */
const PATHS: Record<IconName, string> = {
  // A 2×2 grid of panels: the shape of a summary screen.
  dashboard: 'M2 2h5v5H2z M9 2h5v5H9z M2 9h5v5H2z M9 9h5v5H9z',
  // A candlestick: two wicks and a body, which is what the table is about.
  trades: 'M5 2v3 M5 11v3 M3.5 5h3v6h-3z M11 2v2 M11 12v2 M9.5 4h3v8h-3z',
  // Rising bars.
  analytics: 'M2 14V9 M6 14V5 M10 14V7 M14 14V3',
  // An eye: the list you are watching but not in.
  watchlist: 'M1 8s2.5-4.5 7-4.5S15 8 15 8s-2.5 4.5-7 4.5S1 8 1 8z M8 9.8A1.8 1.8 0 1 0 8 6.2a1.8 1.8 0 0 0 0 3.6z',
  // A shield: protection, the killswitch, the heat cap.
  risk: 'M8 1.5 2.5 4v4c0 3.2 2.3 5.6 5.5 6.5 3.2-.9 5.5-3.3 5.5-6.5V4z',
  // A cog, drawn as a ring plus four teeth rather than twelve points -- at
  // 16px the fine-toothed version is mud.
  system: 'M8 10.2A2.2 2.2 0 1 0 8 5.8a2.2 2.2 0 0 0 0 4.4z M8 1.5v2 M8 12.5v2 M1.5 8h2 M12.5 8h2 M3.4 3.4l1.4 1.4 M11.2 11.2l1.4 1.4 M12.6 3.4l-1.4 1.4 M4.8 11.2l-1.4 1.4',
  // Stacked layers: two components released as one image, over and over.
  versions: 'M8 1.5 1.5 5 8 8.5 14.5 5z M1.5 8.2 8 11.7l6.5-3.5 M1.5 11.4 8 14.9l6.5-3.5',
  collapse: 'M10 4 6 8l4 4',
  expand: 'M6 4l4 4-4 4',
  // A head and shoulders.
  profile: 'M8 8a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z M3 14c0-2.5 2.2-4 5-4s5 1.5 5 4',
  // A door with an arrow leaving it.
  signout: 'M6 2H3v12h3 M9.5 5.5 12 8l-2.5 2.5 M12 8H6',
  menu: 'M2 4h12 M2 8h12 M2 12h12',
};

@Component({
  selector: 'sb-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (path(); as d) {
      <svg
        viewBox="0 0 16 16"
        width="16"
        height="16"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path [attr.d]="d" />
      </svg>
    }
  `,
  styles: `
    :host { display: inline-flex; line-height: 0; }
  `,
})
export class Icon {
  readonly name = input.required<IconName>();

  /**
   * Undefined for a name with no path, which renders nothing.
   *
   * A missing icon should leave a gap rather than take the screen down: the
   * name arrives from a nav config, and a typo there should not be fatal to
   * the shell that contains it.
   */
  protected readonly path = computed<string | undefined>(() => PATHS[this.name()]);
}
