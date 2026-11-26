import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { pct, share } from './format';
import { Hint } from './hint';
import { HELD_STATUSES, NO_PRICE_REASON, NO_PRICE_TEXT } from './position-format';
import { PREV_CLOSE_LABEL, type PriceKind } from './position-progress';
import { PERFORMANCE_CAVEAT } from './stat-tile';
import { StatusIndicator } from './status-indicator';

/**
 * Statuses that have no position by nature — nothing has opened, or it is
 * already over. A row in one of these has no bar because there is nothing to
 * draw, and the chip already says so.
 *
 * Anything NOT in this set is live, so a missing bar means the price lookup
 * failed, and that is worth distinguishing from a quiet trade.
 *
 * Derived from the status rather than matched against `status_label`: keying
 * a behaviour off a human-readable string means the day someone improves the
 * wording, the hint silently stops appearing.
 */
const NO_POSITION_YET = new Set(['PENDING', 'CLOSED', 'CANCELLED', 'EXPIRED']);

/** The subset of a TradeRow this cell reads. Structural rather than importing
 *  TradeRow, so the component can be rendered from a fixture. */
export interface StatusCellRow {
  status: string;
  progress_pct: number | null;
  entry_pct: number | null;
  progress_band: string | null;
  blink_seconds: number | null;
  status_label: string;
  /** True when the bar was drawn from a price that was not a live intraday
   *  tick this request (a fast_info fallback, or a last-known-good cache
   *  entry served past its TTL -- see `TradeRow.current_price_stale`'s own
   *  docstring for the MRNA incident this flags). The bar still draws at its
   *  real, computed position -- the point is to say the number backing it
   *  might be stale, not to hide it. */
  current_price_stale: boolean;
  /** 'trailing' = a PARTIAL runner with no TP2: there is no target to draw a
   *  bar toward, which is not the same as a failed price lookup. */
  bar_kind?: string;
  /** Fraction of the position TP1 already closed (0-1); null until PARTIAL. */
  banked_fraction?: number | null;
  /** Trailing runner only: P&L % if the trailing stop is hit (the bar's 0%)
   *  and at the best price since TP1 (its 100%), both vs the original fill. */
  stop_pnl_pct?: number | null;
  best_pnl_pct?: number | null;
  /** Spec v248 § 1d: 'prev_close' forces the bar neutral and the dot still. */
  price_kind?: PriceKind;
  /** Spec v248 § 1e: null (not absent) with no last_close means "no price yet". */
  current_price?: number | null;
  /** Spec v248 § 1e: the cached daily close; read only to tell "no price yet" apart. */
  last_close?: number | null;
}

/** Spec v248 § 1e: a held row with neither a current price nor a cached close.
 *  Strict `=== null` on current_price: a row without the field keeps "no price". */
function noPriceYet(r: StatusCellRow): boolean {
  return HELD_STATUSES.has(r.status) && r.current_price === null && (r.last_close ?? null) === null;
}

/**
 * Where a live position sits between its stop and its target — spec v18
 * Decision 5. Three parts: a pulsing dot, a bar with an entry tick, and the
 * percentage.
 *
 * **It computes nothing.** Every number arrives on the row from SR7, which
 * gets them from `trade_proximity` — the same function behind the bot's
 * near-close alerts. Doing the arithmetic here as well is how the UI and the
 * alerts end up disagreeing about how close a trade is to its stop. On a
 * prev-close row it only forces the band neutral and the dot still (spec v248
 * § 1d); the arithmetic still arrives on the row.
 *
 * The colour comes from `progress_band` naming a pair of tokens, never from a
 * hex on the wire, so a repaint is a change to tokens.css and not to the API.
 *
 * Degraded states reuse `StatusIndicator` rather than reimplementing a chip.
 * There is one definition of what an ACTIVE pill looks like and this is not
 * it.
 *
 * **No per-status icon here, deliberately (2026-09-14).** That vocabulary
 * (`pending`/`opened`/`partial`/`closed`/`cancelled`) lives only in Recent
 * Activity now, on direct request -- this table keeps its dot+bar/chip
 * language instead of also carrying the icon. A trailing-stop runner's
 * trailing-stop icon sits in the ID cell beside the partial-leg icon (on
 * request, 2026-10-17), not here.
 */
/** v194 A3: what the two ends of a trailing runner's bar are. */
export const STATUS_ENDS_HINT = 'Left figure: P&L if the trailing stop is hit. Right figure: P&L at the best price since TP1. '
  + `Both per share from the original entry, in percent. ${PERFORMANCE_CAVEAT}`;
/** v194 A3: why "delayed" shows. */
export const STATUS_STALE_HINT = "This position's price could not be freshly fetched; the number shown may be delayed.";

@Component({
  selector: 'sb-status-cell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StatusIndicator, Hint],
  template: `
    @if (bar(); as b) {
      <span class="cell">
        <span
          class="dot"
          [class]="b.band"
          [attr.data-still]="b.still ? '' : null"
          [style.--blink]="b.blink"
          [style.animation-duration]="b.blink"
          aria-hidden="true"
        ></span>
        @if (ends(); as e) {
          <span class="end neg">{{ e.stop }}</span>
        }
        <span
          class="track"
          role="progressbar"
          [attr.aria-label]="b.title"
          [attr.aria-valuenow]="b.pct"
          aria-valuemin="0"
          aria-valuemax="100"
          [title]="b.title"
        >
          <span class="fill" [class]="b.band" [style.width.%]="b.pct"></span>
          <!-- Where entry sits on the same scale, so "in profit" is a
               position relative to this mark rather than a separate column. -->
          <span class="tick" [style.left.%]="b.entry" aria-hidden="true"></span>
        </span>
        @if (ends(); as e) {
          <span class="end pos">{{ e.best }}</span>
          <sb-hint [text]="endsHint" label="About the two P&L figures" align="left" />
        } @else {
          <span class="pct">{{ b.pct }}%</span>
        }
        @if (row().current_price_stale) {
          <span class="hint stale">delayed</span>
          <sb-hint [text]="staleHint" label="About delayed prices" align="left" />
        }
      </span>
    } @else {
      <span class="cell no-bar">
        <sb-status-indicator [status]="row().status" />
        @if (hint(); as h) {
          <span class="hint">{{ h.text }}</span>
          @if (h.reason) {
            <span class="reason">{{ h.reason }}</span>
          }
        }
      </span>
    }
  `,
  styles: `
    .cell { display: inline-flex; align-items: baseline; gap: var(--space-6); }
    /* The hint + reason cell wraps; the bar cell (dot, track, percentage) never does. */
    .cell.no-bar { flex-wrap: wrap; }

    .track {
      position: relative;
      align-self: center;
      width: 72px;
      height: 4px;
      border-radius: var(--pill-radius);
      background: var(--surface-raised);
      overflow: hidden;
    }
    .fill {
      display: block;
      height: 100%;
      transition: width var(--dur-base) var(--ease-out);
    }
    /* The band names which pair to interpolate between; the pair itself lives
       in tokens.css. Neutral is flat -- a gradient with nowhere to go reads as
       a gradient that failed to load. */
    .fill.toward_target { background: linear-gradient(90deg, var(--text-muted), var(--pos)); }
    .fill.toward_stop   { background: linear-gradient(90deg, var(--neg), var(--text-muted)); }
    .fill.neutral       { background: var(--text-muted); }

    .tick {
      position: absolute;
      top: -2px;
      width: 1px;
      height: 8px;
      background: var(--text-secondary);
      transform: translateX(-0.5px);
    }

    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      flex: none;
      background: currentColor;
      animation-name: sb-pulse-blink;
      animation-timing-function: ease-in-out;
      animation-iteration-count: infinite;
    }
    .dot.toward_target { color: var(--pos); }
    .dot.toward_stop   { color: var(--neg); }
    .dot.neutral       { color: var(--text-muted); }
    .dot[data-still] { animation: none; }


    /* Motion = Off steadies the dot and the fill: styles/motion.css. */

    .end { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-chip); }
    .end.neg { color: var(--neg); }
    .end.pos { color: var(--pos); }
    .pct { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-table); color: var(--text-secondary); }
    .hint { font-size: var(--text-chip); color: var(--text-muted); }
    .reason { font-size: var(--text-micro); color: var(--text-muted); }
    /* --warn is the design system's designated token for stale data (see
       tokens.css's own legend) -- distinct from the plain --text-faint
       "no price" hint, because this bar DID get a number, just not
       necessarily a live one. */
    .hint.stale { color: var(--warn); }
  `,
})
export class StatusCell {
  readonly row = input.required<StatusCellRow>();
  protected readonly endsHint = STATUS_ENDS_HINT;
  protected readonly staleHint = STATUS_STALE_HINT;

  /** Null whenever there is no position to draw — which selects the chip. */
  protected readonly bar = computed(() => {
    const r = this.row();
    if (r.progress_pct === null || r.progress_band === null) return null;
    const prev = r.price_kind === 'prev_close';
    return {
      pct: Math.max(0, Math.min(100, Math.round(r.progress_pct))),
      entry: Math.max(0, Math.min(100, r.entry_pct ?? 0)),
      band: prev ? 'neutral' : r.progress_band,
      still: prev,
      title: prev ? PREV_CLOSE_LABEL : r.status_label,
      // Seconds, with a floor: a period of 0 would freeze the animation on
      // whichever frame it happened to stop at.
      blink: `${r.blink_seconds ?? 1.4}s`,
    };
  });

  /**
   * Why the bar is missing, when that is worth saying.
   *
   * A PENDING or CLOSED row has no bar because there is no position — the
   * chip already says so and a hint would be noise. A row that IS live and
   * still has no bar means the price lookup failed, and that is worth
   * distinguishing from a quiet trade.
   */
  protected readonly hint = computed((): { text: string; reason: string | null } | null => {
    const r = this.row();
    if (NO_POSITION_YET.has(r.status)) return null;
    if (noPriceYet(r)) return { text: NO_PRICE_TEXT, reason: NO_PRICE_REASON };
    // A trailing runner has a price and a stop but no target, so the bar is
    // withheld by design -- saying "no price" there would be false.
    return { text: r.bar_kind !== 'trailing' ? 'no price' : 'trailing', reason: null };
  });

  /** Signed P&L % at both ends of a trailing runner's bar, or null. */
  protected readonly ends = computed(() => {
    const r = this.row();
    if (r.bar_kind !== 'trailing' || r.stop_pnl_pct == null || r.best_pnl_pct == null) return null;
    const f = (v: number) => pct(v, 1);
    return { stop: f(r.stop_pnl_pct), best: f(r.best_pnl_pct) };
  });
}

/** The partial icon's tooltip on a live PARTIAL row: how much is still open.
 *  The status cell no longer prints it ("50% open"); it lives on the icon. */
export function partialOpenTitle(row: { status: string; banked_fraction?: number | null }): string | null {
  if (row.status !== 'PARTIAL') return null;
  if (row.banked_fraction == null) return 'Partially closed';
  return `Partially closed -- ${share((1 - row.banked_fraction) * 100)} still open`;
}
