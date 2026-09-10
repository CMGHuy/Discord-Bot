import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { MarketIndexStore } from '../../stores/market-index.store';
import { num, pct } from '../../ui/format';

/** Yahoo symbol -> the label the tile shows. `/market/tape` echoes back the
 *  literal symbol it was asked to price (see `MarketIndexStore`), which is
 *  never what a reader wants to see next to a price. */
const INDEX_LABELS: Record<string, string> = {
  '^GSPC': 'S&P 500',
  '^NDX': 'Nasdaq 100',
  '^DJI': 'Dow Jones',
  '^VIX': 'VIX',
};

/**
 * Lane A — fixed market indices (S&P 500, Nasdaq 100, Dow Jones, VIX).
 *
 * First-party now: `MarketIndexStore` prices these through the same
 * `/market/tape` batched-yfinance path Lane B (`NamesLane`) already uses, so
 * this renders through the identical `tape.css` markup — one scroll speed,
 * one dark-theme palette shared with the rest of the app, and a VIX reading
 * this app actually controls, rather than a cross-origin TradingView widget
 * whose speed, theme and per-symbol availability were all outside our reach.
 *
 * The track is rendered twice and translated -50%, exactly like `NamesLane` —
 * see that file's class comment for why (the loop has no snap-back).
 */
@Component({
  selector: 'sb-market-lane',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './tape.css',
  template: `
    <div class="lane" role="region" aria-label="Market tape">
      <div class="cap">mkt</div>
      <div class="viewport">
        <div class="track">
          @for (pass of [0, 1]; track pass) {
            @for (row of market.rows(); track row.symbol) {
              <span class="tile" [attr.aria-hidden]="pass === 1 ? 'true' : null">
                <span class="sym">{{ label(row.symbol) }}</span>
                @if (row.price !== null) {
                  <span class="px" [class.up]="up(row)" [class.down]="down(row)">{{ num(row.price) }}</span>
                  @if (row.change_pct !== null) {
                    <span [class.up]="up(row)" [class.down]="down(row)">{{ pct(row.change_pct) }}</span>
                  }
                } @else {
                  <span class="ctx muted">no price</span>
                }
              </span>
            }
          }
        </div>
      </div>
      <div class="cap end">live</div>
    </div>
  `,
})
export class MarketLane {
  protected readonly market = inject(MarketIndexStore);
  protected readonly num = num;
  protected readonly pct = pct;

  protected label(symbol: string): string {
    return INDEX_LABELS[symbol] ?? symbol;
  }

  protected up(row: { change_pct: number | null }): boolean {
    return row.change_pct !== null && row.change_pct >= 0;
  }

  protected down(row: { change_pct: number | null }): boolean {
    return row.change_pct !== null && row.change_pct < 0;
  }
}
