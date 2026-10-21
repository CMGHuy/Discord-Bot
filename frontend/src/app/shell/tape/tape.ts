import {
  ChangeDetectionStrategy, Component, DestroyRef, ElementRef, afterRenderEffect, computed, inject, signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { MarketIndexStore } from '../../stores/market-index.store';
import { TapeStore } from '../../stores/tape.store';
import { Flash } from '../../ui/flash';
import { ABSENT, num, pct } from '../../ui/format';
import { TAPE_PAGE_SECONDS, tapePages } from './tape-pages';

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
 * v179 layout audit: the strip no longer slides a doubled track under the
 * lane's edge (that cut a symbol or a price at the edge by design). It shows
 * whole tiles only -- as many as the lane fits -- and turns to the next page
 * every `TAPE_PAGE_SECONDS` (`tape-pages.ts`), so every flagged symbol is
 * still reached. The page holds while the pointer or focus is on the strip.
 * Tiles off the current page stay in the DOM (`.off`: out of flow, hidden)
 * so their width can still be measured.
 */
@Component({
  selector: 'sb-tape',
  standalone: true,
  imports: [RouterLink, Flash],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './tape.css',
  template: `
    <div class="lane" role="region" aria-label="Market tape"
         [attr.title]="asOfTime() === ABSENT ? null : 'Tape data as of ' + asOfTime()">
      <div class="cap">mkt</div>
      <div class="viewport" #viewport (mouseenter)="hold(true)" (mouseleave)="hold(false)"
           (focusin)="hold(true)" (focusout)="hold(false)">
        <div class="track">
          @for (tile of tiles(); track tile.key; let i = $index) {
            <a class="tile sb-hit" [routerLink]="tile.link" [sbFlash]="tile.change_pct"
               [class.off]="!onPage(i)"
               [attr.tabindex]="tile.link && onPage(i) ? null : -1">
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
        </div>
      </div>
    </div>
  `,
})
export class Tape {
  private readonly market = inject(MarketIndexStore);
  private readonly tape = inject(TapeStore);
  protected readonly num = num;
  protected readonly pct = pct;
  protected readonly ABSENT = ABSENT;

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly viewportRef = viewChild<ElementRef<HTMLElement>>('viewport');
  /** The lane's width, kept by a ResizeObserver -- the page split depends on it. */
  private readonly laneWidth = signal(0);
  /** Index lists of the tiles that fit together; empty until the first measure. */
  private readonly pages = signal<number[][]>([]);
  private readonly page = signal(0);
  private held = false;
  private readonly onCurrentPage = computed(() => new Set(this.pages()[this.page()] ?? []));

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
      // Read for reactivity, not value: the tiles' own widths change with the
      // data and the lane's with the window.
      this.tiles();
      const lane = this.laneWidth();
      if (lane > 0) this.measure(lane);
    });
    afterRenderEffect(() => {
      const el = this.viewportRef()?.nativeElement;
      if (!el) return;
      this.laneWidth.set(el.clientWidth);
      if (typeof ResizeObserver === 'undefined') return;
      const observer = new ResizeObserver(() => this.laneWidth.set(el.clientWidth));
      observer.observe(el);
      return () => observer.disconnect();
    });
    const timer = setInterval(() => this.turn(), TAPE_PAGE_SECONDS * 1000);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  private measure(lane: number): void {
    const widths = [...this.host.nativeElement.querySelectorAll<HTMLElement>('.tile')].map((t) => t.offsetWidth);
    const next = tapePages(widths, lane);
    if (JSON.stringify(next) !== JSON.stringify(this.pages())) this.pages.set(next);
    if (this.page() >= next.length) this.page.set(0);
  }

  private turn(): void {
    const count = this.pages().length;
    if (!this.held && count > 1) this.page.update((p) => (p + 1) % count);
  }

  protected hold(on: boolean): void {
    this.held = on;
  }

  /** Before the first measure every tile counts as on the page. */
  protected onPage(index: number): boolean {
    return this.pages().length === 0 || this.onCurrentPage().has(index);
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
