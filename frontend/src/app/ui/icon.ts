import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * The icon set — spec v18 Decision 8, redrawn by v240 §4 (doctena night).
 *
 * **Hand-authored, no package, no font, no CDN.** The repo's zero-third-party
 * constraint is not an aesthetic preference: an icon font is a network request
 * to somebody else's host on every page load, and an icon package is tens of
 * thousands of glyphs shipped to use a few dozen. These paths cost less than
 * the dependency's own README.
 *
 * Stroked on a 24×24 grid at 1.8 width with round caps and joins, so the whole
 * set looks like one hand. `size` sets only the rendered width and height
 * (16 in tables and inline text, 20 in lists, 24 in the rail and the phone tab
 * bar); the viewBox stays 24, and the stroke scales with it, so one drawing
 * serves every size. A caller picks a size; it never overrides the svg in CSS.
 *
 * A few icons carry one filled sub-path (`FILLS`): Pending's sand, Opened's
 * broadcast source, Partial's banked half. The svg is `fill="none"`, so the
 * filled part is a second path with its own `fill="currentColor"`.
 *
 * `currentColor` is what lets a single definition serve an active nav entry,
 * a hovered one and a muted one without three copies of the path data.
 *
 * Always `aria-hidden`. The accessible name belongs on the control the icon
 * sits inside — a nav link that labels itself AND contains a labelled icon
 * announces "Trades Trades".
 */
export const ICON_NAMES = [
  'dashboard',
  'trades',
  'analytics',
  'calendar',
  'watchlist',
  'risk',
  'system',
  'versions',
  'collapse',
  'expand',
  'profile',
  'signout',
  'menu',
  'trash',
  'clock',
  'more',
  'opened',
  'closed',
  'pending',
  'partial',
  'cancelled',
  'trailing',
  'brand',
  'reports',
  'research',
  'search',
  'theme',
] as const;

export type IconName = (typeof ICON_NAMES)[number];

/** The sizes an icon draws at: tables and inline text, lists, rail and tab bar. */
export type IconSize = 16 | 20 | 24;

/** Stroked path data only — every shared attribute lives on the `<svg>` below. */
const PATHS: Record<IconName, string> = {
  // A gauge with its needle: the one-glance read of the book.
  dashboard: 'M3.5 17a8.5 8.5 0 0 1 17 0 M12 8.5V10 M6.6 10.6l1 1 M17.4 10.6l-1 1 M12 17l3.6-4.6 M3.5 20h17',
  // Two candlesticks, wicks and bodies: what the table is about.
  trades: 'M7 3v4 M7 17v4 M5 7h4v10H5z M17 3v3 M17 15v6 M15 6h4v9h-4z',
  // A light bulb with a rising line inside it: Insights, what the book teaches.
  analytics:
    'M9.5 18h5 M10.3 21h3.4 M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.1v.1h5v-.1c0-.8.4-1.6 1.1-2.1A6 6 0 0 0 12 3z M9.5 10.5l1.7-1.7 1.6 1.6 1.9-2',
  // A month grid: a header bar, two binder rings and day marks.
  calendar: 'M4 5.5h16v15H4z M4 10h16 M8.5 3v4 M15.5 3v4 M8 13.5h2 M14 13.5h2 M8 17h2',
  // Binoculars: tickers watched for a setup (an eye reads as show/hide).
  watchlist:
    'M6.5 19.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M17.5 19.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M10 16h4 M3.4 14.6 5.5 5h3.2l1 9 M20.6 14.6 18.5 5h-3.2l-1 9',
  // A shield with a percent sign: the 2% dollar-risk cap and the heat cap.
  risk:
    'M12 2.5 4.5 5.5v6c0 4.6 3.2 8.4 7.5 10 4.3-1.6 7.5-5.4 7.5-10v-6z M9.3 15.2l5.4-6.4 M9.6 10.2a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8z M14.4 15.6a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8z',
  // A monitor with a pulse line: health and versions (a gear reads as settings).
  system: 'M3 4h18v12H3z M8 20h8 M12 16v4 M5.5 10h3l1.5-3 2 6 1.5-3h5',
  // Stacked layers: two components released as one image, over and over.
  versions: 'M12 3 3 7.5l9 4.5 9-4.5z M3 12l9 4.5 9-4.5 M3 16.5 12 21l9-4.5',
  // A chevron pointing left: fold the rail or panel away.
  collapse: 'M15 6l-6 6 6 6',
  // A chevron pointing right: open it out (also a collapsed row's marker).
  expand: 'M9 6l6 6-6 6',
  // A head and shoulders.
  profile: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4.5 20.5c0-3.5 3.3-5.5 7.5-5.5s7.5 2 7.5 5.5',
  // A door with an arrow leaving it.
  signout: 'M10 4H5v16h5 M15 8l4 4-4 4 M19 12H9',
  // Three bars.
  menu: 'M4 7h16 M4 12h16 M4 17h16',
  // A bin: lid, handle, tapered body and two staves.
  trash: 'M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13 M10 11v5 M14 11v5',
  // A dial with two hands: the wall clock in the top bar.
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3.5 2',
  // Three dots: the row overflow menu. Zero-length strokes; the round caps
  // draw the dots.
  more: 'M5 12h.01 M12 12h.01 M19 12h.01',
  // A live-signal broadcast, two arcs each side of a solid source (FILLS):
  // the position is running. A status, not a direction.
  opened: 'M8.2 15.8a5.4 5.4 0 0 1 0-7.6 M15.8 8.2a5.4 5.4 0 0 1 0 7.6 M5.4 18.6a9.3 9.3 0 0 1 0-13.2 M18.6 5.4a9.3 9.3 0 0 1 0 13.2',
  // A finish flag on its pole: the trade ended, neutral for winners and
  // losers alike.
  closed: 'M5 21V4 M5 4h13l-2.5 4L18 12H5',
  // An hourglass with sand left in the lower bulb (FILLS): waiting for the
  // entry trigger, nothing has happened yet.
  pending: 'M6 3h12 M6 21h12 M7 3c0 4 5 5.5 5 9s-5 5-5 9 M17 3c0 4-5 5.5-5 9s5 5 5 9',
  // A circle whose right half is solid (FILLS): TP1 banked, the runner live.
  partial: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z',
  // A crossed-out circle: void, never filled (EXPIRED maps here too) --
  // distinct from `closed`'s flag so a plan that never filled cannot be
  // misread as one that did.
  cancelled: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M8.5 8.5l7 7 M15.5 8.5l-7 7',
  // An upward stair with an arrowhead: the stop ratchets with price and
  // never gives ground, which is what a trailing stop does.
  trailing: 'M3 19h5v-5h5V9h5 M15 4.5h4.5V9',
  // A diamond: the rail's brand mark, a shape that inherits currentColor.
  brand: 'M12 2.5 21 12l-9 9.5L3 12z',
  // A page with a folded corner and ruled text lines: a document, not a
  // chart, so Reports and Insights never share a glyph.
  reports: 'M6 3h9l3 3v15H6z M15 3v3h3 M9 11h6 M9 14.5h6 M9 18h3.5',
  // A flask: experiments and their verdicts -- the strategy registry and the
  // pre-registration ledger (the magnifier belongs to `search`, v195).
  research: 'M9 3h6 M10 3v6l-5.4 9.3A1.8 1.8 0 0 0 6.2 21h11.6a1.8 1.8 0 0 0 1.6-2.7L14 9V3 M7 15h10',
  // A magnifying glass: the command palette's trigger and the phone bar's
  // search icon (v195 correction 1).
  search: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z M15.5 15.5 20 20',
  // A crescent moon: the theme toggle (both themes are dark).
  theme: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z',
};

/** The solid part of an icon, drawn after its stroke with `fill="currentColor"`. */
const FILLS: Partial<Record<IconName, string>> = {
  // The sand already fallen: a small heap in the hourglass's lower bulb.
  pending: 'M9.5 18.5h5L12 16z',
  // The broadcast's source: a solid dot between the arcs.
  opened: 'M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
  // The banked half: the circle's right half, solid.
  partial: 'M12 3a9 9 0 0 1 0 18z',
};

/** The tooltip an icon shows when its caller gives none, so no icon is mute. */
const LABELS: Record<IconName, string> = {
  dashboard: 'Dashboard', trades: 'Trades', analytics: 'Analytics', calendar: 'Calendar',
  watchlist: 'Watchlist', risk: 'Risk', system: 'System', versions: 'Versions',
  collapse: 'Collapse', expand: 'Expand', profile: 'Profile', signout: 'Sign out',
  menu: 'Menu', trash: 'Delete', clock: 'Clock', more: 'More actions',
  opened: 'Opened', closed: 'Closed', pending: 'Pending', partial: 'Partially closed',
  cancelled: 'Cancelled', trailing: 'Trailing stop', brand: 'Swingbot',
  reports: 'Reports', research: 'Research', search: 'Search',
  theme: 'Theme',
};

@Component({
  selector: 'sb-icon',
  host: { '[attr.title]': 'tip()' },
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (path(); as d) {
      <svg
        viewBox="0 0 24 24"
        [attr.width]="size()"
        [attr.height]="size()"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path [attr.d]="d" />
        @if (fill(); as f) {
          <path class="fill" [attr.d]="f" fill="currentColor" stroke="none" />
        }
      </svg>
    }
  `,
  styles: `
    /* vertical-align centres an icon set inline in running text on that
       text; in a flex row (every current use) it is ignored. */
    :host { display: inline-flex; line-height: 0; vertical-align: middle; }
  `,
})
export class Icon {
  readonly name = input.required<IconName>();
  /** Overrides the default tooltip (the icon's name). */
  readonly title = input<string | undefined>(undefined);
  /** Rendered width and height in px; the drawing stays on the 24 grid. */
  readonly size = input<IconSize>(16);
  protected readonly tip = computed(() => this.title() ?? LABELS[this.name()]);

  /**
   * Undefined for a name with no path, which renders nothing.
   *
   * A missing icon should leave a gap rather than take the screen down: the
   * name arrives from a nav config, and a typo there should not be fatal to
   * the shell that contains it.
   */
  protected readonly path = computed<string | undefined>(() => PATHS[this.name()]);
  /** The filled sub-path, for the few icons that have one; rendered second. */
  protected readonly fill = computed<string | undefined>(() => FILLS[this.name()]);
}

/** One icon per plan lifecycle status -- lives here, not on any one
 *  consumer, because Recent Activity is the only place it is used
 *  (2026-09-14: deliberately kept out of the Open Positions table) but the
 *  mapping itself is about the icon set, not about that one panel. EXPIRED
 *  reads as `cancelled` -- a plan that never filled either way. */
export const STATUS_ICON: Record<string, IconName> = {
  PENDING: 'pending',
  ACTIVE: 'opened',
  PARTIAL: 'partial',
  CLOSED: 'closed',
  CANCELLED: 'cancelled',
  EXPIRED: 'cancelled',
};
