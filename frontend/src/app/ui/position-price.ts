import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { BREAKPOINTS } from './breakpoints';
import { num } from './format';
import { MarketValue } from './market-value';
import {
  HELD_STATUSES,
  NO_PRICE_REASON,
  NO_PRICE_TEXT,
  PREV_CLOSE_ARIA,
  PREV_CLOSE_TAG,
  PositionPriceRow,
  closeDateTag,
  positionFigure,
} from './position-format';
import type { PriceKind } from './position-progress';

export type { PositionPriceRow } from './position-format';

type PriceMode = 'live' | 'prev' | 'close' | 'none' | 'empty';

/**
 * The NOW cell of an open position (v248 spec 1d / 1e / 1f). One component owns
 * the `prev close` tag, the age wording and the no-price note, so a position
 * never reads differently on Trades and on the Dashboard.
 *
 * The prev-close branch passes `asOf = null` to sb-market-value (index Decision 3):
 * the dated tag replaces the age, and the error rule treats the row as priceless.
 * Nothing in the cell is focusable, so a live update never moves focus.
 */
@Component({
  selector: 'sb-position-price',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MarketValue],
  template: `
    @switch (mode()) {
      @case ('live') {
        <sb-market-value
          [asOf]="row().price_as_of ?? null"
          [refreshing]="row().price_refreshing ?? false"
          [error]="row().price_error ?? null"
          [errorAt]="row().price_error_at ?? null"
          >{{ price() }}</sb-market-value
        >
      }
      @case ('prev') {
        <span class="pp prev" [title]="prevTitle()"
          ><span class="pp-value">{{ price() }}</span>
          <span class="pp-tag" [attr.aria-label]="prevAria">{{ prevTag() }}</span></span
        >
        <sb-market-value
          [asOf]="null"
          [refreshing]="row().price_refreshing ?? false"
          [error]="row().price_error ?? null"
          [errorAt]="row().price_error_at ?? null"
        />
      }
      @case ('close') {
        <span class="last-close" [title]="'No live quote -- last close, ' + (row().last_close_date ?? 'date unknown')"
          ><span class="last-close-value">{{ closePrice() }}</span>
          <span class="last-close-tag">close {{ closeTag() }}</span></span
        >
        <sb-market-value
          [asOf]="null"
          [refreshing]="row().price_refreshing ?? false"
          [error]="row().price_error ?? null"
          [errorAt]="row().price_error_at ?? null"
        />
      }
      @case ('none') {
        <span class="pp none"
          ><span class="pp-none">{{ noPriceText }}</span> <span class="pp-reason">{{ noPriceReason }}</span></span
        >
        <sb-market-value
          [asOf]="null"
          [refreshing]="row().price_refreshing ?? false"
          [error]="row().price_error ?? null"
          [errorAt]="row().price_error_at ?? null"
        />
      }
      @default {
        <sb-market-value
          [asOf]="null"
          [refreshing]="row().price_refreshing ?? false"
          [error]="row().price_error ?? null"
          [errorAt]="row().price_error_at ?? null"
        />
      }
    }
  `,
  styles: `
    :host {
      display: inline-flex;
      flex-wrap: wrap;
      align-items: baseline;
      column-gap: var(--space-4);
      max-width: 100%;
    }
    .pp,
    .last-close {
      color: var(--text-muted);
      display: inline-flex;
      flex-wrap: wrap;
      align-items: baseline;
      column-gap: var(--space-4);
    }
    .pp-value,
    .last-close-value {
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .pp-tag,
    .last-close-tag,
    .pp-reason {
      font-size: var(--text-micro);
    }
    .pp-none {
      white-space: nowrap;
    }
    @media (max-width: ${BREAKPOINTS.sm - 1}px) {
      :host,
      .pp {
        flex-direction: column;
        align-items: flex-start;
      }
    }
  `,
})
export class PositionPrice {
  readonly row = input.required<PositionPriceRow>();

  protected readonly prevAria = PREV_CLOSE_ARIA;
  protected readonly noPriceText = NO_PRICE_TEXT;
  protected readonly noPriceReason = NO_PRICE_REASON;

  protected readonly mode = computed<PriceMode>(() => {
    const r = this.row();
    if (r.current_price != null) return r.price_kind === 'prev_close' ? 'prev' : 'live';
    if (r.last_close != null) return 'close';
    return HELD_STATUSES.has(r.status) ? 'none' : 'empty';
  });
  protected readonly price = computed(() => num(this.row().current_price));
  protected readonly closePrice = computed(() => num(this.row().last_close));
  protected readonly closeTag = computed(() => closeDateTag(this.row().last_close_date));
  protected readonly prevTag = computed(() => `${PREV_CLOSE_TAG} ${closeDateTag(this.row().last_close_date)}`.trim());
  protected readonly prevTitle = computed(
    () => `Previous close, ${this.row().last_close_date ?? 'date unknown'} -- not a live price`,
  );
}

/** P&L % / R figure with the `at prev close` suffix when the price is not live (spec 1f). */
@Component({
  selector: 'sb-position-figure',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="fig">{{ fig().text }}</span
    >@if (fig().suffix; as s) {<span class="fig-suffix" [attr.aria-label]="aria">{{ s }}</span>}`,
  styles: `
    :host {
      display: inline-flex;
      flex-wrap: wrap;
      align-items: baseline;
      column-gap: var(--space-4);
    }
    .fig {
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }
    .fig-suffix {
      font-size: var(--text-micro);
      color: var(--text-muted);
    }
    @media (max-width: ${BREAKPOINTS.sm - 1}px) {
      :host {
        flex-direction: column;
        align-items: flex-start;
      }
    }
  `,
})
export class PositionFigure {
  readonly value = input<number | null>(null);
  readonly unit = input.required<'pct' | 'r'>();
  readonly kind = input<PriceKind | null>(null);

  protected readonly aria = PREV_CLOSE_ARIA;
  protected readonly fig = computed(() => positionFigure(this.value(), this.unit(), this.kind()));
}
