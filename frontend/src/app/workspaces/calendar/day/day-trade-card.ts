import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { CalendarTrade, SparkSeries } from '../../../api/models';
import { ConnectionStore } from '../../../stores/connection.store';
import { Chip, ChipTone } from '../../../ui/chip';
import { ABSENT, held, money, num, pct, rMultiple } from '../../../ui/format';
import { R_TOOLTIP } from './day-copy';
import { TradeSparkline } from './trade-sparkline';

/* v165 D5 item 5 -- one row of the day page's Trades list. Every figure is
 * read from the calendar row as served (D1); nothing is re-derived here. */

/** "Leg 2 of 3" for a scale-out leg, null for a whole trade. 1-based, like
 *  the drawer. */
export function legLabel(trade: CalendarTrade): string | null {
  return trade.leg_total > 1 ? `Leg ${trade.leg_index + 1} of ${trade.leg_total}` : null;
}

export function heldLabel(hours: number | null): string {
  return held(hours);
}

/** The `/trades/:id` route takes the plan id when there is one -- the
 *  drawer's and the Trades list's rule. */
export function tradeLinkId(trade: CalendarTrade): string {
  return trade.plan_id ?? trade.trade_id;
}

const DIRECTIONS: Record<string, string> = { bullish: 'Long', bearish: 'Short' };

function sign(value: number | null): 'pos' | 'neg' | null {
  if (value === null || value === 0) return null;
  return value > 0 ? 'pos' : 'neg';
}

@Component({
  selector: 'sb-day-trade-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip, RouterLink, TradeSparkline],
  template: `
    @let t = trade();
    <article class="card">
      <header>
        <strong class="ticker">{{ t.ticker }}</strong>
        <span class="direction">{{ direction() }}</span>
        <span class="setup">{{ t.strategy }} · {{ t.horizon ?? absent }}</span>
        @if (leg(); as label) {
          <span class="leg">{{ label }}</span>
        }
        <sb-chip [label]="t.exit_reason" [tone]="exitTone()" [caps]="false" />
        <span class="figures">
          <span class="pnl" [class.pos]="pnlSign() === 'pos'" [class.neg]="pnlSign() === 'neg'">{{ pnl() }}</span>
          <span class="r" [title]="rTooltip" [class.pos]="rSign() === 'pos'" [class.neg]="rSign() === 'neg'">{{ r(t.r_multiple) }}</span>
          <span class="return">{{ returnPct() }}</span>
        </span>
      </header>
      <p class="prices">
        Entry {{ price(t.entry_price) }} · Exit {{ price(t.exit_price) }} ·
        Final stop {{ price(t.stop_price) }} · TP1 {{ price(t.tp1) }} · TP2 {{ price(t.tp2) }}
      </p>
      <p class="stats">
        Held {{ heldText() }} · Shares {{ sharesText() }} ·
        MFE {{ r(t.mfe_r) }} · MAE {{ r(t.mae_r) }}
      </p>
      <footer>
        <sb-trade-sparkline [series]="series()" [tradeId]="linkId()" />
        <a class="open" [routerLink]="['/trades', linkId()]">Open →</a>
      </footer>
      @if (t.auto_lesson; as lesson) {
        <p class="lesson">{{ lesson }}</p>
      }
      @if (t.tags.length) {
        <p class="tags">
          @for (tag of t.tags; track tag) {
            <span class="tag">{{ tag }}</span>
          }
        </p>
      }
    </article>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .card { padding: var(--space-10) 0; border-bottom: 1px solid var(--border); }
    header { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }
    .direction, .setup, .leg { color: var(--text-secondary); font-size: var(--text-table); }
    .leg { font-size: var(--text-micro); }
    .figures { display: inline-flex; gap: var(--space-10); margin-left: auto; font-family: var(--font-mono); }
    .pnl.pos, .r.pos { color: var(--pos); }
    .pnl.neg, .r.neg { color: var(--neg); }
    .r { cursor: help; }
    .return { color: var(--text-secondary); }
    .prices, .stats {
      margin: var(--space-4) 0 0;
      color: var(--text-secondary);
      font-family: var(--font-mono);
      font-size: var(--text-micro);
      overflow-wrap: anywhere;
    }
    footer {
      display: flex; flex-wrap: wrap; align-items: center;
      gap: var(--space-14); margin-top: var(--space-6);
    }
    .open {
      display: inline-flex; align-items: center; justify-content: center;
      min-height: 44px; min-width: 44px; margin-left: auto;
      color: var(--accent); font-weight: 600; text-decoration: none;
    }
    .open:hover, .open:focus-visible { text-decoration: underline; }
    .lesson { margin: var(--space-6) 0 0; font-size: var(--text-table); }
    .tags { display: flex; flex-wrap: wrap; gap: var(--space-4); margin: var(--space-6) 0 0; }
    .tag {
      padding: 1px var(--space-6);
      border: 1px solid var(--border);
      border-radius: var(--radius-chip);
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }
    @media (max-width: 639px) { .figures { margin-left: 0; width: 100%; } }
  `,
})
export class DayTradeCard {
  readonly trade = input.required<CalendarTrade>();
  readonly series = input<SparkSeries | null | undefined>();

  private readonly connection = inject(ConnectionStore);

  protected readonly absent = ABSENT;
  protected readonly rTooltip = R_TOOLTIP;

  protected readonly linkId = computed(() => tradeLinkId(this.trade()));
  protected readonly leg = computed(() => legLabel(this.trade()));
  protected readonly direction = computed(() => DIRECTIONS[this.trade().direction ?? ''] ?? ABSENT);
  protected readonly exitTone = computed<ChipTone>(() =>
    this.trade().exit_reason === 'other' ? 'muted' : 'neutral',
  );
  protected readonly pnl = computed(() => money(this.trade().pnl_amount, this.connection.currency(), 2));
  protected readonly pnlSign = computed(() => sign(this.trade().pnl_amount));
  protected readonly rSign = computed(() => sign(this.trade().r_multiple));
  protected readonly returnPct = computed(() => pct(this.trade().return_pct));
  protected readonly heldText = computed(() => heldLabel(this.trade().held_hours));
  protected readonly sharesText = computed(() => {
    const shares = this.trade().shares;
    return shares === null ? ABSENT : num(shares, Number.isInteger(shares) ? 0 : 2);
  });

  protected price(value: number | null): string {
    return num(value, 2);
  }

  protected r(value: number | null): string {
    return rMultiple(value);
  }
}
