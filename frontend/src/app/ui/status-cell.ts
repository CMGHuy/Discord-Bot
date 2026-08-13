import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

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
}

/**
 * Where a live position sits between its stop and its target — spec v18
 * Decision 5. Three parts: a pulsing dot, a bar with an entry tick, and the
 * percentage.
 *
 * **It computes nothing.** Every number arrives on the row from SR7, which
 * gets them from `trade_proximity` — the same function behind the bot's
 * near-close alerts. Doing the arithmetic here as well is how the UI and the
 * alerts end up disagreeing about how close a trade is to its stop.
 *
 * The colour comes from `progress_band` naming a pair of tokens, never from a
 * hex on the wire, so a repaint is a change to tokens.css and not to the API.
 *
 * Degraded states reuse `StatusIndicator` rather than reimplementing a chip.
 * There is one definition of what an ACTIVE pill looks like and this is not
 * it.
 */
@Component({
  selector: 'sb-status-cell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StatusIndicator],
  template: `
    @if (bar(); as b) {
      <span class="cell">
        <span
          class="dot"
          [class]="b.band"
          [style.--blink]="b.blink"
          [style.animation-duration]="b.blink"
          aria-hidden="true"
        ></span>
        <span
          class="track"
          role="progressbar"
          [attr.aria-label]="row().status_label"
          [attr.aria-valuenow]="b.pct"
          aria-valuemin="0"
          aria-valuemax="100"
          [title]="row().status_label"
        >
          <span class="fill" [class]="b.band" [style.width.%]="b.pct"></span>
          <!-- Where entry sits on the same scale, so "in profit" is a
               position relative to this mark rather than a separate column. -->
          <span class="tick" [style.left.%]="b.entry" aria-hidden="true"></span>
        </span>
        <span class="pct">{{ b.pct }}%</span>
      </span>
    } @else {
      <span class="cell">
        <sb-status-indicator [status]="row().status" />
        @if (hint(); as h) {
          <span class="hint">{{ h }}</span>
        }
      </span>
    }
  `,
  styles: `
    .cell { display: inline-flex; align-items: center; gap: var(--space-6); }

    .track {
      position: relative;
      width: 72px;
      height: 4px;
      border-radius: 2px;
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
      animation-name: pulse;
      animation-timing-function: ease-in-out;
      animation-iteration-count: infinite;
    }
    .dot.toward_target { color: var(--pos); }
    .dot.toward_stop   { color: var(--neg); }
    .dot.neutral       { color: var(--text-muted); }

    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }

    /* The pulse says "this is live right now", which is exactly the kind of
       motion someone with vestibular sensitivity has asked the OS to stop. */
    @media (prefers-reduced-motion: reduce) {
      .dot { animation: none; }
      .fill { transition: none; }
    }

    .pct { font-family: var(--font-mono); font-size: var(--text-table); color: var(--text-secondary); }
    .hint { font-size: var(--text-chip); color: var(--text-faint); }
  `,
})
export class StatusCell {
  readonly row = input.required<StatusCellRow>();

  /** Null whenever there is no position to draw — which selects the chip. */
  protected readonly bar = computed(() => {
    const r = this.row();
    if (r.progress_pct === null || r.progress_band === null) return null;
    return {
      pct: Math.max(0, Math.min(100, Math.round(r.progress_pct))),
      entry: Math.max(0, Math.min(100, r.entry_pct ?? 0)),
      band: r.progress_band,
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
  protected readonly hint = computed(() =>
    NO_POSITION_YET.has(this.row().status) ? null : 'no price',
  );
}
