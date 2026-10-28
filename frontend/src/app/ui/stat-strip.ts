import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * A row of tiles inside a panel, separated by hairlines rather than each
 * tile drawing its own framed box inside the framed panel -- spec v186 D3.
 *
 * The strip draws no rule itself. Its scoped CSS stops at its own template
 * (emulated encapsulation) and the tiles are projected, and no component
 * restyles the inside of a tile (workspace-consistency.spec.ts). It sets
 * inherited custom properties instead, which sb-stat-tile and sb-metric-card
 * read on their own hosts -- the mechanism sb-figure-strip uses for sb-figure:
 *
 * - `--figure-rule: 1px`: each tile draws a start-edge rule (left, top). The
 *   grid is pulled 1px up and left inside this clipping host, so the first
 *   row's top rule and the first column's left rule fall outside: one tile
 *   shows no rule, and an incomplete last row leaves none beside its gap.
 * - `--tile-bg`, `--tile-border`, `--tile-radius`: no surface, frame or corner.
 * - `--tile-tint-off: none`: sb-metric-card drops its pos/neg fill; the
 *   value's colour and sign carry the valence.
 *
 * Columns: the global .sb-strip-grid (styles.css), shared with sb-async's
 * 'tiles' skeleton. With no `cols`, auto-fit at 140px. With `cols`, that many
 * from 1024px, `colsMd` (default 2) from 640px, and 2 below. `fillLast`
 * widens a last tile that would sit alone in a row of two or four columns
 * (a seventh of eight places, say) across the rest of its row.
 */
@Component({
  selector: 'sb-stat-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '[style.--strip-cols]': 'cols()',
    '[style.--strip-cols-md]': 'colsMd()',
  },
  template: `<div class="sb-strip-grid" [class.sb-strip-fixed]="cols() !== null" [class.sb-strip-fill]="fillLast()"><ng-content /></div>`,
  styles: `
    :host {
      --figure-rule: 1px;
      --tile-bg: transparent;
      --tile-border: 0;
      --tile-radius: 0;
      --tile-tint-off: none;
      display: block;
      overflow: hidden;
      min-width: 0;
    }
    .sb-strip-grid { margin: -1px 0 0 -1px; }
  `,
})
export class StatStrip {
  /** Columns from 1024px; null keeps the auto-fit grid. */
  readonly cols = input<number | null>(null);
  /** Columns from 640px to 1023px, when `cols` is set. */
  readonly colsMd = input<number>(2);
  /** Span the last tile across the row it starts (4 or 2 columns only). */
  readonly fillLast = input(false);
}
