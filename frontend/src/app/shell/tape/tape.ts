import {
  ChangeDetectionStrategy, Component, ElementRef, afterRenderEffect, computed, inject, signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { MarketIndexStore } from '../../stores/market-index.store';
import { TapeStore } from '../../stores/tape.store';
import { Flash } from '../../ui/flash';
import { ABSENT, num, pct } from '../../ui/format';
import { TAPE_MIN_DURATION_S, tapeDurationSeconds } from './tape-speed';

/** Yahoo symbol -> the label the tile shows. `/market/tape` echoes back the
 *  literal symbol it was asked to price, which is never what a reader wants
 *  to see next to a price. */
const INDEX_LABELS: Record<string, string> = {
  '^GSPC': 'S&P 500',
  '^NDX': 'Nasdaq 100',
  '^DJI': 'Dow Jones',
  '^VIX': 'VIX',
};

/** One row of either source, reshaped to the one tile template needs. */
interface Tile {
  key: string;
  label: string;
  price: number | null;
  change_pct: number | null;
  link: string | null;
  context_label: string | null;
  context_kind: string | null;
}

/**
 * The shell's one topbar tape — combines the fixed market indices and the
 * flagged watchlist symbols into a single scrolling strip, indices first
 * (spec: they orient the reader before the per-symbol detail does).
 *
 * Replaces the earlier two-lane split (`MarketLane`/`NamesLane`, each its
 * own `:host { flex: 1 1 0% }` half of `.topbar-tape`) on direct request:
 * splitting the bar evenly wasted half of it on the four-index lane while
 * starving the often much longer watchlist lane. One combined track means
 * there is only ever one width to divide, and it goes to whichever content
 * actually needs it.
 *
 * The track is rendered twice and translated -50% (`tape.css`'s
 * `tape-slide` keyframes) so the loop has no snap-back — same convention
 * the two lanes this replaces already used.
 */
@Component({
  selector: 'sb-tape',
  standalone: true,
  imports: [RouterLink, Flash],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './tape.css',
  template: `
    <div class="lane" role="region" aria-label="Market tape">
      <div class="cap">mkt</div>
      <div class="viewport">
        <div class="track" #track [style.animation-duration.s]="duration()">
          @for (pass of [0, 1]; track pass) {
            @for (tile of tiles(); track tile.key) {
              <a class="tile" [routerLink]="tile.link" [sbFlash]="tile.change_pct"
                 [attr.aria-hidden]="pass === 1 ? 'true' : null"
                 [attr.tabindex]="tile.link && pass !== 1 ? null : -1">
                <span class="sym">{{ tile.label }}</span>
                @if (tile.price !== null) {
                  <span class="px" [class.up]="up(tile)" [class.down]="down(tile)">{{ num(tile.price) }}</span>
                  @if (tile.change_pct !== null) {
                    <span [class.up]="up(tile)" [class.down]="down(tile)">{{ pct(tile.change_pct) }}</span>
                  }
                } @else {
                  <span class="ctx muted">no price</span>
                }
                @if (tile.context_label) {
                  <span class="ctx" [class.muted]="tile.context_kind === 'earnings'">
                    {{ tile.context_label }}
                  </span>
                }
              </a>
            }
          }
        </div>
      </div>
      <!-- Outside .track, deliberately -- a badge inside the moving element
           scrolls out of view, so the freshness signal would blink in and
           out and be absent exactly when someone glances at it. -->
      <span class="cap end as-of" [attr.title]="asOf()"
            [attr.aria-label]="'Tape data as of ' + asOfTime()">
        <span aria-hidden="true">◷</span> {{ asOfTime() }}
      </span>
    </div>
  `,
})
export class Tape {
  private readonly market = inject(MarketIndexStore);
  private readonly tape = inject(TapeStore);
  protected readonly num = num;
  protected readonly pct = pct;

  private readonly trackRef = viewChild<ElementRef<HTMLElement>>('track');
  /** Measured from the track's own rendered width (after every render the
   *  row data could have changed it) rather than a fixed duration -- see
   *  tape-speed.ts. */
  protected readonly duration = signal(TAPE_MIN_DURATION_S);

  protected readonly tiles = computed<Tile[]>(() => {
    const indices: Tile[] = this.market.rows().map((r) => ({
      key: `idx:${r.symbol}`,
      label: INDEX_LABELS[r.symbol] ?? r.symbol,
      price: r.price,
      change_pct: r.change_pct,
      link: null,
      context_label: null,
      context_kind: null,
    }));
    const stocks: Tile[] = this.tape.rows().map((r) => ({
      key: `stk:${r.symbol}`,
      label: r.symbol,
      price: r.price,
      change_pct: r.change_pct,
      link: `/watchlist/${r.symbol}`,
      context_label: r.context_label,
      context_kind: r.context_kind,
    }));
    return [...indices, ...stocks];
  });

  /** Whichever source has answered — the two stores refetch on the same
   *  `scan` event, so they age together in practice. */
  protected readonly asOf = computed(() => this.tape.asOf() ?? this.market.asOf());

  constructor() {
    afterRenderEffect(() => {
      // Read for reactivity, not value -- the track element itself does not
      // change when the row data does, so without a signal read here this
      // effect would run once on first render (an empty track) and never
      // again. Same reasoning as the two components this replaces.
      this.tiles();
      const el = this.trackRef()?.nativeElement;
      if (el) this.duration.set(tapeDurationSeconds(el.scrollWidth));
    });
  }

  protected up(tile: { change_pct: number | null }): boolean {
    return tile.change_pct !== null && tile.change_pct >= 0;
  }

  protected down(tile: { change_pct: number | null }): boolean {
    return tile.change_pct !== null && tile.change_pct < 0;
  }

  protected readonly asOfTime = computed(() => {
    const iso = this.asOf();
    if (!iso) return ABSENT;
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) return ABSENT;
    return parsed.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  });
}
