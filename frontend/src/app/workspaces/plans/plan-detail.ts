import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  untracked,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { TradeDetailStore } from '../../stores/trade-detail.store';
import { asyncInputs, Async } from '../../ui/async';
import { QualityChip } from '../../ui/chip';
import { dateTime, text } from '../../ui/format';
import { StatusIndicator } from '../../ui/status-indicator';
import { quoteLine } from '../trades/quote-line';
import { IfItGetsThere } from '../trades/why/if-it-gets-there';
import { LevelsBlock } from '../trades/why/levels-block';
import { OutcomePath } from '../trades/why/outcome-path';
import { PlanChart } from '../trades/why/plan-chart';
import { SizingPanel } from '../trades/why/sizing-panel';
import { WHY_SECTIONS, WhyPanel } from '../trades/why/why-panel';

/** `_looks_like_a_plan_id` (`swingbot/admin/api_v1/trades.py:648`): plan ids
 *  are 36-char dashed uuid4s, trade ids 16 dash-free characters. */
export function looksLikePlanId(id: string): boolean {
  return id.length === 36 && id.split('-').length - 1 === 4;
}

/** A plan whose open life is over goes to its trade record, with the banner
 *  that says why (spec v151 § Redirects). A Discord link outlives the plan
 *  and must still land somewhere useful. */
export function redirectFor(status: string | null, barsToExpiry: number | null): 'banner' | null {
  if (status === 'CLOSED' || status === 'CANCELLED') return 'banner';
  if (status === 'PENDING' && barsToExpiry === 0) return 'banner';
  return null;
}

export interface PlanTiming {
  status: string | null;
  expiresOn: string | null;
  barsToExpiry: number | null;
  holdCapBars: number | null;
  timeExitOn: string | null;
}

const AT_CLOSE = 'at the close (ET)';

/** Expiry and the time exit both resolve on a daily bar, so each date reads
 *  as a session date "at the close (ET)". A date outside the session
 *  calendar's coverage arrives as null and renders as a dash, never hidden. */
export function timingLines(t: PlanTiming): string[] {
  const lines: string[] = [];
  if (t.status === 'PENDING') {
    const left = t.barsToExpiry === null ? '' : ` (${t.barsToExpiry} bars left)`;
    lines.push(`Expires ${t.expiresOn ?? '—'} ${AT_CLOSE}${left}`);
  }
  if (t.holdCapBars !== null) {
    const on = t.timeExitOn ? ` — ${t.timeExitOn} ${AT_CLOSE}` : '';
    lines.push(`Time exit after ${t.holdCapBars} sessions${on}`);
  }
  return lines;
}

/**
 * One open plan, end to end (spec v151): the levels order-ready, the Why
 * panel, the chart and how it is playing out, on one scrolling page.
 * Reached from a Discord alert's title link.
 *
 * Read-only on purpose. The bot is paper-only, and this page places, edits
 * and cancels nothing; the actions stay on the trade record it links to.
 * A plan that is over redirects there (see `redirectFor`).
 */
@Component({
  selector: 'sb-plan-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    Async,
    QualityChip,
    StatusIndicator,
    WhyPanel,
    LevelsBlock,
    IfItGetsThere,
    SizingPanel,
    OutcomePath,
    PlanChart,
  ],
  template: `
    <header class="plan-head">
      <a class="back" routerLink="/trades">← Trades</a>

      @if (store.trade(); as trade) {
        <div class="plan-title" role="heading" aria-level="2">
          <span class="ticker">{{ trade.ticker }}</span>
          <span class="tag">{{ fmtText(trade.direction) }}</span>
          <sb-status-indicator
            [status]="trade.status"
            [current]="trade.current_price"
            [entry]="trade.entry"
            [stop]="trade.stop_loss"
            [target]="trade.target"
          />
        </div>
        <div class="tags">
          @if (strategyLine(); as line) {
            <span class="tag">{{ line }}</span>
          }
          @if (trade.badge) {
            <span class="tag">{{ trade.badge }}</span>
          }
          @if (trade.confidence_level !== null) {
            <sb-quality-chip
              [value]="trade.confidence_level"
              [label]="'Lv' + trade.confidence_level"
            />
          }
          @if (createdAt(); as at) {
            <span class="created">created {{ fmtDate(at) }}</span>
          }
          <span class="created">Alert price: {{ quoteLine(store.detail()?.quote ?? null) }}</span>
        </div>
        @for (line of timing(); track line) {
          <p class="timing">{{ line }}</p>
        }
      } @else if (store.error(); as message) {
        <p class="plan-title" role="status">{{ message }}</p>
      } @else {
        <!-- Not the sb-async placeholder class: this file uses sb-async, and
             async-coverage.spec.ts bans that literal class name here. -->
        <p class="plan-title loading-title" role="status">Loading…</p>
      }
    </header>

    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="measured-zero"
      emptyTitle="Plan not found"
      [skeletonRows]="3"
      [skeletonCols]="4"
      (retry)="store.load()"
    >
      @if (store.trade(); as trade) {
        <div class="body">
          <div class="panels">
            <sb-levels-block
              [direction]="trade.direction"
              [entryType]="store.detail()?.entry_type ?? null"
              [trigger]="store.triggerPrice()"
              [entry]="trade.entry"
              [stop]="trade.stop_loss"
              [stopLabel]="stopLabel()"
              [target1]="trade.target"
              [target2]="trade.target2"
              [riskReward]="trade.risk_reward"
              [acceptanceLevel]="store.acceptanceLevel()"
              [tp1Pct]="store.tp1Pct()"
              [breakevenTriggerPct]="store.breakevenTriggerPct()"
            />
            <!-- PENDING only: the gap and sizing picture before the trigger
                 fires. A filled plan keeps them on its trade record. -->
            @if (trade.status === 'PENDING') {
              <sb-if-it-gets-there
                [direction]="trade.direction"
                [target2]="trade.target2"
                [stopLoss]="trade.stop_loss"
              />
              <sb-sizing-panel
                [shares]="trade.shares"
                [positionValue]="trade.position_value"
                [sizingMode]="store.detail()?.sizing_mode ?? null"
                [workingStop]="store.detail()?.working_stop ?? null"
                [gapP90Pct]="store.gapP90Pct()"
                [gapFragile]="store.gapFragile()"
              />
            }
          </div>

          <sb-why-panel
            [sections]="sections"
            [status]="trade.status"
            [barsToExpiry]="trade.bars_to_expiry"
            [sessionsSinceCreated]="store.sessionsSinceCreated()"
            [entry]="trade.entry"
            [trigger]="store.triggerPrice()"
            [stop]="trade.stop_loss"
            [stopLabel]="stopLabel()"
            [target1]="trade.target"
            [target2]="trade.target2"
            [acceptanceLevel]="store.acceptanceLevel()"
            [targetSources]="store.targetSources()"
            [stopSources]="store.stopSources()"
            [target2Sources]="store.target2Sources()"
            [confirmedBy]="store.confirmedBy()"
            [confidencePoints]="store.confidencePoints()"
            [confidenceUnevaluated]="store.confidenceUnevaluated()"
            [confidenceFactors]="store.confidenceFactors()"
            [qualityFactors]="store.qualityFactors()"
            [gates]="store.gates()"
            [calendar]="store.calendar()"
            [explanation]="store.explanation()"
          />

          <sb-plan-chart [ticker]="trade.ticker" [tradeId]="trade.id" />

          <sb-outcome-path [legs]="store.legs()" [timeline]="store.timeline()" />

          <a class="record-link" [routerLink]="['/trades', id()]">Open the full trade record</a>
        </div>
      }
    </sb-async>
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: var(--section-gap); }
    .plan-head {
      display: grid;
      gap: var(--space-8);
    }
    .back, .record-link {
      color: var(--accent);
      font-size: var(--text-table);
      text-decoration: none;
    }
    .back:hover, .record-link:hover {
      text-decoration: underline;
    }
    .plan-title {
      margin: 0;
      display: flex;
      align-items: center;
      gap: var(--space-10);
      font-size: var(--text-title);
      font-weight: 600;
    }
    .ticker {
      font-family: var(--font-mono);
    }
    .loading-title {
      color: var(--text-faint);
    }
    .tags {
      display: flex;
      align-items: center;
      gap: var(--space-6);
      flex-wrap: wrap;
    }
    .tag {
      padding: 1px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-chip);
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }
    .created, .timing {
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    .body {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: var(--section-gap);
    }
    .panels {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: var(--section-gap);
      align-items: start;
    }
  `,
})
export class PlanDetail {
  private readonly router = inject(Router);
  protected readonly store = inject(TradeDetailStore);

  readonly id = input.required<string>();

  protected readonly async = computed(() => asyncInputs(this.store, { isEmpty: () => false }));
  protected readonly sections = WHY_SECTIONS;

  protected readonly fmtText = text;
  protected readonly quoteLine = quoteLine;
  protected readonly fmtDate = dateTime;

  /** Same rule as the trade page: a PARTIAL plan's stop is the runner's. */
  protected readonly stopLabel = computed(() =>
    this.store.trade()?.status === 'PARTIAL' ? 'Trailing stop' : 'Stop',
  );

  protected readonly strategyLine = computed(() => {
    const trade = this.store.trade();
    return [trade?.strategy, trade?.horizon].filter((part) => !!part).join(' · ');
  });

  protected readonly createdAt = computed(() => this.store.detail()?.created_at ?? null);

  protected readonly timing = computed(() => {
    const trade = this.store.trade();
    if (!trade) return [];
    return timingLines({
      status: trade.status,
      expiresOn: this.store.expiresOn(),
      barsToExpiry: trade.bars_to_expiry ?? null,
      holdCapBars: this.store.holdCapBars(),
      timeExitOn: this.store.timeExitOn(),
    });
  });

  constructor() {
    // A legacy trade id has no plan page: hand it to the trade record at
    // once, without fetching it here and without the banner state.
    effect(() => {
      const id = this.id();
      if (!looksLikePlanId(id)) {
        untracked(() => this.leave(id, false));
        return;
      }
      this.store.setId(id);
    });

    // Runs on every load, so a plan that closes while the page is open (the
    // store refetches on the `trades` event) still redirects.
    effect(() => {
      const trade = this.store.trade();
      const id = this.id();
      if (!trade || !looksLikePlanId(id)) return;
      if (redirectFor(trade.status, trade.bars_to_expiry ?? null) === 'banner') {
        untracked(() => this.leave(id, true));
      }
    });
  }

  /** replaceUrl: Back from the trade record must not land on this page and
   *  bounce straight back. */
  private leave(id: string, banner: boolean): void {
    this.router.navigate(
      ['/trades', id],
      banner ? { replaceUrl: true, state: { from: 'plan' } } : { replaceUrl: true },
    );
  }
}
