import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { Realized } from '../../../stores/dashboard.store';
import { money, pct } from '../../../ui/format';
import { Panel } from '../../../ui/layout';
import { SegmentOption, Segmented } from '../../../ui/segmented';
import { Spinner } from '../../../ui/spinner';
import { ScopeSelection, rangeChipLabel, signTone } from './equity-range.model';
import { PANEL_HELP } from './panel-help';

type View = 'scope' | 'today';

const TODAY: SegmentOption = { value: 'today', label: 'Today' };

/**
 * Realised P&L over the closes in scope, with Today one click away.
 *
 * Follows the Dashboard scope (a preset or the range the chart was dragged
 * to), so panning the equity chart re-scopes it with the KPI cards. The Today
 * entry shows the same figures for the New York day alone, whatever the scope
 * is -- the view the old Today / All days toggle gave. Under 1D the two are
 * one and the control is not shown.
 *
 * While the scope refetches, the previous figures stay, dimmed, with a ring
 * beside them: a pan of the chart never blanks or moves the panel.
 */
@Component({
  selector: 'sb-realized-pnl',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Segmented, Spinner],
  template: `
    <sb-panel heading="Realised P&L" [description]="about">
      @if (hasChoice()) {
        <sb-segmented panel-actions label="Realised P&L window" [options]="options()"
                      [value]="view()" (valueChange)="onView($event)" />
      }
      <div class="pnl-body" [class.stale]="stale()" [attr.aria-busy]="busy() || null">
        <div class="figures" [class.busy]="busy()">
          <span class="amount num" [attr.data-tone]="tone()">{{ amountText() }}</span>
          <span class="pct num" [attr.data-tone]="tone()">{{ pctText() }}</span>
          @if (busy()) {
            <sb-spinner class="ring" label="Updating realised P&L" />
          }
        </div>
        <p class="window">{{ windowLabel() }}</p>
        <dl class="stats" [class.busy]="busy()">
          <div><dt>Closed</dt><dd class="num">{{ count('n') }}</dd></div>
          <div><dt>Won</dt><dd class="num" data-tone="pos">{{ count('wins') }}</dd></div>
          <div><dt>Lost</dt><dd class="num" data-tone="neg">{{ count('losses') }}</dd></div>
        </dl>
        @if (emptyHint(); as hint) {
          <p class="hint">{{ hint }}</p>
        }
      </div>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .pnl-body { display: flex; flex-direction: column; gap: var(--space-8); min-width: 0; }
    .pnl-body.stale { opacity: 0.55; }
    /* Mixed sizes on one line share a baseline; the ring is the one centred thing. */
    .figures { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-4) var(--space-14); min-width: 0; }
    .figures.busy .amount, .figures.busy .pct, .stats.busy { opacity: 0.45; }
    .ring { align-self: center; }
    .amount {
      font-size: var(--register-figure, var(--text-metric));
      font-weight: 700;
      line-height: 1.1;
      white-space: nowrap;
    }
    .pct { font-size: var(--text-body); white-space: nowrap; }
    .window { margin: 0; font-size: var(--text-chip); color: var(--text-muted); }
    .stats {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: var(--space-10);
      margin: 0;
    }
    .stats > div { display: flex; flex-direction: column; gap: var(--space-4); min-width: 0; padding: var(--space-6) var(--space-10); border-left: 2px solid var(--border); }
    dt { font-size: var(--text-micro); letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-secondary); }
    dd { margin: 0; font-size: var(--text-body); }
    .hint { margin: 0; font-size: var(--text-chip); color: var(--text-muted); }
    [data-tone='pos'] { color: var(--pos); }
    [data-tone='neg'] { color: var(--neg); }
  `,
})
export class RealizedPnl {
  protected readonly about = PANEL_HELP.realizedPnl;
  /** The scoped realised block; null before the first response. */
  readonly scope = input<Realized | null>(null);
  /** Today's block, whatever the scope. */
  readonly today = input<Realized | null>(null);
  readonly selection = input<ScopeSelection>({ kind: 'preset', preset: '1D' });
  readonly currency = input('€');
  /** The scoped fetch is in flight. */
  readonly loading = input(false);
  /** The today-only fetch is in flight. */
  readonly todayLoading = input(false);
  /** The last scoped refetch failed; the figures are the previous ones. */
  readonly stale = input(false);

  protected readonly view = signal<View>('scope');

  protected readonly isDay = computed(() => {
    const selection = this.selection();
    return selection.kind === 'preset' && selection.preset === '1D';
  });
  /** One window at 1D, so there is nothing to choose between. */
  protected readonly hasChoice = computed(() => !this.isDay());
  protected readonly showToday = computed(() => this.isDay() || this.view() === 'today');

  protected readonly scopeName = computed(() => {
    const selection = this.selection();
    return selection.kind === 'preset' ? selection.preset : 'Range';
  });
  protected readonly options = computed<SegmentOption[]>(() =>
    [{ value: 'scope', label: this.scopeName() }, TODAY]);

  /** Under 1D the scoped block is today's, and arrives with the first fetch. */
  protected readonly figures = computed<Realized | null>(() => {
    if (!this.showToday()) return this.scope() ?? null;
    return (this.isDay() ? (this.scope() ?? this.today()) : this.today()) ?? null;
  });
  protected readonly busy = computed(() =>
    (this.showToday() && !this.isDay() ? this.todayLoading() : this.loading()));

  protected readonly tone = computed(() => signTone(this.figures()?.amount ?? null));
  protected readonly amountText = computed(() => money(this.figures()?.amount ?? null, this.currency()));
  protected readonly pctText = computed(() => pct(this.figures()?.pct ?? null));
  protected readonly windowLabel = computed(() => {
    if (this.showToday()) return 'Today';
    const selection = this.selection();
    if (selection.kind === 'range') return `Range ${rangeChipLabel(selection.window)}`;
    return selection.preset === 'All' ? 'All days' : selection.preset;
  });
  protected readonly emptyHint = computed(() => {
    const figures = this.figures();
    if (figures === null || figures.n > 0) return null;
    if (this.showToday()) return 'none closed today';
    const selection = this.selection();
    return selection.kind === 'preset' && selection.preset === 'All' ? 'none closed' : 'none closed in range';
  });

  /** A dash, never a zero, until a response says how many closed. */
  protected count(key: 'n' | 'wins' | 'losses'): string {
    const figures = this.figures();
    return figures === null ? '—' : String(figures[key]);
  }

  protected onView(value: string): void {
    this.view.set(value === 'today' ? 'today' : 'scope');
  }
}
