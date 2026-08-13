import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { ApiClient } from '../../api/api-client';
import { OhlcvStore } from '../../stores/ohlcv.store';
import { TradeDetailStore } from '../../stores/trade-detail.store';
import { Button } from '../../ui/button';
import { QualityChip } from '../../ui/chip';
import { ChartContainer } from '../../ui/chart-container';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { PriceChart } from '../../ui/price-chart';
import { dateTime, held, num, pct, text } from '../../ui/format';
import { Panel, Tab, TabBar } from '../../ui/layout';
import { StatusIndicator } from '../../ui/status-indicator';
import {
  ACTION_LABELS,
  ACTION_TITLES,
  TradeActionKind,
  actionConsequence,
  availableActions,
  runTradeAction,
} from './trade-actions';

/** Plan · Live · Chart · Notes · Strategy — spec 3's five, in its order. */
const TABS: Tab[] = [
  { id: 'plan', label: 'Plan' },
  { id: 'live', label: 'Live' },
  { id: 'chart', label: 'Chart' },
  { id: 'notes', label: 'Notes' },
  { id: 'strategy', label: 'Strategy' },
];

const TAB_IDS = new Set(TABS.map((tab) => tab.id));

/**
 * One trade — the shell and the Plan tab (NG43). Live is NG44, Chart NG45,
 * Notes and Strategy NG46.
 *
 * **The active tab is a query parameter**, for the same reason the Trades
 * list keeps its filters there: a tab held only in component state cannot be
 * linked to, does not survive a reload, and makes the back button skip the
 * whole detail view instead of stepping back through it.
 *
 * `id` arrives as an input rather than through `ActivatedRoute`, so this
 * component is testable without standing up a router.
 */
@Component({
  selector: 'sb-trade-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [TradeDetailStore, OhlcvStore],
  imports: [RouterLink, TabBar, Panel, StatusIndicator, QualityChip, Button, ConfirmDialog, ChartContainer, PriceChart],
  template: `
    <header class="head">
      <a class="back" routerLink="/trades">← Trades</a>

      @if (store.trade(); as trade) {
        <h1>
          <span class="ticker">{{ trade.ticker }}</span>
          <sb-status-indicator
            [status]="trade.status"
            [current]="trade.current_price"
            [entry]="trade.entry"
            [stop]="trade.stop_loss"
            [target]="trade.target"
          />
        </h1>
        <div class="tags">
          @if (trade.horizon) {
            <span class="tag">{{ trade.horizon }}</span>
          }
          @if (trade.strategy) {
            <span class="tag">{{ trade.strategy }}</span>
          }
          @if (trade.tier) {
            <sb-quality-chip [value]="trade.tier" [label]="'Tier ' + trade.tier" />
          }
          @if (trade.confidence_level !== null) {
            <sb-quality-chip
              [value]="trade.confidence_level"
              [label]="'Lv' + trade.confidence_level"
            />
          }
        </div>
      } @else if (store.error(); as message) {
        <h1>{{ message }}</h1>
      } @else {
        <h1 class="skeleton">Loading…</h1>
      }
    </header>

    <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="goToTab($event)" />

    @switch (activeTab()) {
      @case ('plan') {
        @if (store.trade(); as trade) {
          <div class="panels">
            <sb-panel heading="Levels">
              <dl>
                <div><dt>Entry</dt><dd class="num">{{ fmt(trade.entry) }}</dd></div>
                <div>
                  <dt>Stop</dt>
                  <dd class="num neg">{{ fmt(trade.stop_loss) }}</dd>
                </div>
                <div>
                  <dt>Target 1</dt>
                  <dd class="num pos">{{ fmt(trade.target) }}</dd>
                </div>
                <div>
                  <dt>Target 2</dt>
                  <dd class="num pos">{{ fmt(trade.target2) }}</dd>
                </div>
                <div><dt>R:R</dt><dd class="num">{{ fmt(trade.risk_reward) }}</dd></div>
              </dl>
            </sb-panel>

            <sb-panel heading="Per share">
              <dl>
                <div><dt>Risk</dt><dd class="num">{{ fmt(store.riskPerShare()) }}</dd></div>
                <div><dt>Reward</dt><dd class="num">{{ fmt(store.rewardPerShare()) }}</dd></div>
                <div><dt>Direction</dt><dd>{{ fmtText(trade.direction) }}</dd></div>
                <div><dt>Origin</dt><dd>{{ fmtText(trade.origin) }}</dd></div>
              </dl>
            </sb-panel>

            <sb-panel heading="Sizing">
              <dl>
                <div><dt>Shares</dt><dd class="num">{{ fmt(trade.shares, 0) }}</dd></div>
                <div><dt>Deployed</dt><dd class="num">{{ fmt(trade.position_value) }}</dd></div>
                <div>
                  <dt>Sizing mode</dt>
                  <dd>{{ fmtText(store.detail()?.sizing_mode ?? null) }}</dd>
                </div>
                <div>
                  <dt>Working stop</dt>
                  <dd class="num">{{ fmt(store.detail()?.working_stop ?? null) }}</dd>
                </div>
              </dl>
            </sb-panel>

            <sb-panel heading="Opened">
              <dl>
                <div><dt>At</dt><dd>{{ fmtDate(trade.opened_at) }}</dd></div>
                <div><dt>Closed</dt><dd>{{ fmtDate(trade.closed_at) }}</dd></div>
                <div><dt>Entry type</dt><dd>{{ fmtText(store.detail()?.entry_type ?? null) }}</dd></div>
                <div><dt>P&L</dt><dd class="num">{{ fmtPct(trade.pnl_pct) }}</dd></div>
              </dl>
            </sb-panel>
          </div>
        }
      }
      @case ('live') {
        @if (store.trade(); as trade) {
          <div class="panels">
            <sb-panel heading="Now">
              <dl>
                <div><dt>Price</dt><dd class="num">{{ fmt(trade.current_price) }}</dd></div>
                <div>
                  <dt>Unrealised</dt>
                  <dd class="num" [class]="pnlClass(trade.pnl_pct)">{{ fmtPct(trade.pnl_pct) }}</dd>
                </div>
                <div>
                  <dt>Amount</dt>
                  <dd class="num" [class]="pnlClass(trade.realized_pnl_amount)">
                    {{ fmt(trade.realized_pnl_amount) }}
                  </dd>
                </div>
                <div><dt>Held</dt><dd class="num">{{ fmtHeld(trade.held_hours) }}</dd></div>
              </dl>
            </sb-panel>

            <sb-panel heading="Stop to target">
              <div class="progress">
                <sb-status-indicator
                  [status]="trade.status"
                  [current]="trade.current_price"
                  [entry]="trade.entry"
                  [stop]="trade.stop_loss"
                  [target]="trade.target"
                />
              </div>
              <dl>
                <div><dt>Stop</dt><dd class="num neg">{{ fmt(trade.stop_loss) }}</dd></div>
                <div><dt>Entry</dt><dd class="num">{{ fmt(trade.entry) }}</dd></div>
                <div><dt>Target</dt><dd class="num pos">{{ fmt(trade.target) }}</dd></div>
              </dl>
            </sb-panel>

            <sb-panel heading="Actions">
              <div class="commands">
                @for (kind of actionsFor(trade.status); track kind) {
                  <button
                    sb-button
                    [variant]="kind === 'delete' ? 'danger' : 'secondary'"
                    type="button"
                    (click)="ask(kind)"
                  >
                    {{ actionLabels[kind] }}
                  </button>
                }
              </div>
            </sb-panel>
          </div>
        }
      }
      @case ('chart') {
        <div class="chart">
          <sb-chart-container
            [loading]="chart.loading()"
            [error]="chart.error()"
            [hasData]="!chart.isEmpty()"
            [height]="420"
            [caption]="chartCaption()"
          >
            <sb-price-chart [bars]="chart.bars()" [levels]="chart.levels()" />
          </sb-chart-container>
        </div>
      }
      @case ('notes') {
        <div class="notes">
          @if (store.noteStatus() === 'unjournaled') {
            <!-- Not an error. Journal entries are written at close, so an
                 open position has none and cannot take a note yet. Saying so
                 plainly beats a textarea that silently discards what is
                 typed into it. -->
            <p class="not-journaled">
              This position has no journal entry yet. Notes attach when a trade
              closes.
            </p>
          }

          <label class="note-label" for="trade-note">Note</label>
          <textarea
            id="trade-note"
            class="note"
            rows="10"
            [value]="store.noteText()"
            [disabled]="store.noteStatus() === 'unjournaled'"
            (input)="onNoteInput($event)"
            (blur)="flushNote()"
            placeholder="Why this trade, what happened, what to do differently."
          ></textarea>

          <p class="note-state" [class.note-state-bad]="store.noteStatus() === 'error'">
            @switch (store.noteStatus()) {
              @case ('saving') { Saving… }
              @case ('unsaved') { Unsaved changes }
              @case ('error') { {{ store.noteError() }} }
              @case ('unjournaled') { Not journaled yet }
              @default { Saved }
            }
          </p>
        </div>
      }
      @case ('strategy') {
        <div class="strategy">
          @if (store.strategiesError()) {
            <p class="not-journaled">{{ store.strategiesError() }}</p>
          } @else if (!store.trade()?.strategy) {
            <p class="not-journaled">This position has no strategy recorded.</p>
          } @else if (store.strategyRow(); as row) {
            <!-- Read-only on purpose: this is a window into the registry, and
                 the place to change a strategy's numbers is a validation run,
                 not a trade. -->
            <dl>
              <div><dt>Strategy</dt><dd>{{ row.strategy }}</dd></div>
              <div><dt>Status</dt><dd>{{ row.status }}</dd></div>
              <div><dt>OOS sample</dt><dd>{{ fmt(row.n) }}</dd></div>
              <div><dt>OOS win rate</dt><dd>{{ fmtPct(row.win_rate) }}</dd></div>
              <div><dt>OOS expectancy</dt><dd>{{ fmt(row.expectancy_r) }}R</dd></div>
              <div><dt>Live sample</dt><dd>{{ fmt(row.live_n) }}</dd></div>
              <div><dt>Live win rate</dt><dd>{{ fmtPct(row.live_wr) }}</dd></div>
              <div><dt>Live vs OOS</dt><dd>{{ fmtPct(row.delta_vs_oos) }}</dd></div>
              <div><dt>Window</dt><dd>{{ fmtText(row.window) }}</dd></div>
            </dl>
            @if (row.decayed) {
              <!-- The pre-registered decay rule fired. This belongs on the
                   trade, not only on the Analytics page: it is the reason to
                   distrust this position's edge. -->
              <p class="decayed">
                Live results have decayed against this strategy's out-of-sample
                record.
              </p>
            }
          } @else {
            <p class="not-journaled">
              The registry has no entry for {{ fmtText(store.trade()?.strategy) }}.
            </p>
          }
        </div>
      }
    }

    <sb-confirm-dialog
      [open]="pending() !== null"
      [title]="confirmTitle()"
      [consequence]="confirmConsequence()"
      [confirmLabel]="confirmLabel()"
      [working]="working()"
      (confirmed)="runPending()"
      (cancelled)="pending.set(null)"
    />
  `,
  styles: `
    .head { display: grid; gap: var(--space-8); }
    .back { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .back:hover { text-decoration: underline; }

    h1 {
      display: flex;
      align-items: center;
      gap: var(--space-10);
      font-size: var(--text-title);
      font-weight: 600;
    }
    .ticker { font-family: var(--font-mono); }
    .skeleton { color: var(--text-faint); }

    .tags { display: flex; align-items: center; gap: var(--space-6); flex-wrap: wrap; }
    .tag {
      padding: 1px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-chip);
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }

    .panels {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: var(--space-14);
      margin-top: var(--space-14);
    }
    dl { display: grid; gap: var(--space-6); }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { color: var(--text); font-size: var(--text-table); }
    .pos { color: var(--pos); }
    .neg { color: var(--neg); }

    .chart { margin-top: var(--space-14); }
    .progress { margin-bottom: var(--space-10); }
    .commands { display: flex; flex-wrap: wrap; gap: var(--space-8); }

    .notes, .strategy { margin-top: var(--space-14); }
    .note-label {
      display: block;
      margin-bottom: var(--space-6);
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    .note {
      width: 100%;
      padding: var(--space-8);
      background: var(--surface-sunken);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      font: inherit;
      font-size: var(--text-table);
      resize: vertical;
    }
    .note:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
    .note:disabled { color: var(--text-faint); cursor: not-allowed; }
    .note-state {
      margin-top: var(--space-6);
      color: var(--text-faint);
      font-size: var(--text-meta);
    }
    /* The one state the reader must not miss: text they typed is not stored. */
    .note-state-bad { color: var(--neg); }
    .not-journaled {
      margin-bottom: var(--space-10);
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    .decayed { margin-top: var(--space-10); color: var(--warn); font-size: var(--text-table); }

    .todo { margin-top: var(--space-14); color: var(--text-faint); font-size: var(--text-table); }
  `,
})
export class TradeDetail {
  private readonly router = inject(Router);
  private readonly api = inject(ApiClient);
  protected readonly store = inject(TradeDetailStore);
  protected readonly chart = inject(OhlcvStore);

  readonly id = input.required<string>();
  /** The active tab, as a query parameter. */
  readonly tab = input<string>();

  protected readonly tabs = TABS;

  protected readonly fmt = num;
  protected readonly fmtText = text;
  protected readonly fmtDate = dateTime;
  protected readonly fmtPct = pct;
  protected readonly fmtHeld = held;

  /** An unknown or absent `?tab=` falls back to Plan rather than rendering
   *  nothing, so a hand-edited or stale URL still shows the trade. */
  protected readonly activeTab = computed(() => {
    const requested = this.tab();
    return requested && TAB_IDS.has(requested) ? requested : 'plan';
  });

  protected readonly actionLabels = ACTION_LABELS;
  protected readonly actionsFor = availableActions;
  protected readonly pending = signal<TradeActionKind | null>(null);
  protected readonly working = signal(false);

  protected readonly confirmTitle = computed(() => {
    const kind = this.pending();
    return kind ? ACTION_TITLES[kind] : '';
  });

  protected readonly confirmLabel = computed(() => {
    const kind = this.pending();
    return kind ? ACTION_LABELS[kind] : 'Confirm';
  });

  /** The same sentences the Trades list uses -- see `trade-actions.ts` for
   *  why they live in exactly one place. */
  protected readonly confirmConsequence = computed(() => {
    const kind = this.pending();
    const trade = this.store.trade();
    return kind && trade ? actionConsequence(kind, trade) : '';
  });

  protected readonly chartCaption = computed(() => {
    const trade = this.store.trade();
    return trade ? `${trade.ticker} — daily, with this plan's levels` : null;
  });

  /** Autosave delay. Long enough that ordinary typing does not generate a
   *  request per word, short enough that the note is stored before attention
   *  moves on. Blur flushes, so the wait is never the last word on it. */
  private static readonly NOTE_DEBOUNCE_MS = 800;

  private noteTimer: ReturnType<typeof setTimeout> | null = null;

  protected onNoteInput(event: Event): void {
    this.store.editNote((event.target as HTMLTextAreaElement).value);

    if (this.noteTimer !== null) clearTimeout(this.noteTimer);
    this.noteTimer = setTimeout(() => {
      this.noteTimer = null;
      this.store.saveNote();
    }, TradeDetail.NOTE_DEBOUNCE_MS);
  }

  /** Save now rather than at the end of the debounce. Leaving the field is a
   *  stronger signal that the thought is finished than any timer. */
  protected flushNote(): void {
    if (this.noteTimer === null) return;
    clearTimeout(this.noteTimer);
    this.noteTimer = null;
    if (this.store.noteDirty()) this.store.saveNote();
  }

  constructor() {
    effect(() => this.store.setId(this.id()));

    // The registry is only needed by one tab, and it is the same request for
    // every trade -- so it is fetched on first arrival at the tab rather than
    // with the trade.
    effect(() => {
      if (this.activeTab() === 'strategy' && this.store.strategies() === null) {
        untracked(() => this.store.loadStrategies());
      }
    });

    // A pending autosave must not outlive the component: the timer would fire
    // against a destroyed store and the last edit would be lost either way.
    inject(DestroyRef).onDestroy(() => {
      if (this.noteTimer === null) return;
      clearTimeout(this.noteTimer);
      this.noteTimer = null;
    });

    // The chart follows the trade, and carries its id so the endpoint returns
    // this plan's levels rather than a bare price chart. Only once the trade
    // has loaded: the ticker is not known before that.
    effect(() => {
      const trade = this.store.trade();
      this.chart.setTarget(trade?.ticker ?? null, trade?.id ?? null);
    });
  }

  protected pnlClass(value: number | null | undefined): string {
    if (value === null || value === undefined) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  }

  protected ask(kind: TradeActionKind): void {
    this.pending.set(kind);
  }

  protected runPending(): void {
    const kind = this.pending();
    const trade = this.store.trade();
    if (!kind || !trade) return;

    this.working.set(true);
    runTradeAction(this.api, kind, trade.id).subscribe({
      // Deleting removes the thing this route is about, so it navigates away.
      // Close and cancel leave a trade that still has a detail page, and the
      // server's `trades` event refetches it -- no manual reload here, which
      // would double every command.
      next: () => {
        this.working.set(false);
        this.pending.set(null);
        if (kind === 'delete') this.router.navigate(['/trades']);
      },
      error: () => {
        this.working.set(false);
        this.pending.set(null);
      },
    });
  }

  protected goToTab(tab: string): void {
    // replaceUrl: flipping between tabs should not fill the history with
    // steps, but the tab must still be in the URL so it can be linked to.
    this.router.navigate([], {
      queryParams: { tab: tab === 'plan' ? null : tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
