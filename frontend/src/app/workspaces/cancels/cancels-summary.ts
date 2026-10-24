import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { CancelFigure, CancelOutcome, CancelPrecision } from '../../api/models';
import { CancelCardKey, CancelFilter, CancelSplit } from '../../stores/cancels.store';
import { Panel } from '../../ui/layout';
import { ciText, figureText, rText } from './cancels.helpers';

const CARDS: readonly { key: CancelCardKey; title: string; note: string | null }[] = [
  { key: 'risk_cap', title: 'risk_cap · from the trigger', note: null },
  { key: 'risk_cap_fill', title: 'risk_cap · from the crossing price', note: null },
  { key: 'invalidated', title: 'invalidated', note: null },
  { key: 'expired', title: 'expired', note: null },
  { key: 'other', title: 'other', note: 'not in the headline' },
];
const OUTCOMES: readonly CancelOutcome[] = ['right', 'wrong', 'unresolved', 'untriggered_after_cancel'];
const CANCEL_WORDS: Record<CancelOutcome, string> = {
  right: 'Right cancels', wrong: 'Wrong cancels',
  unresolved: 'Unresolved', untriggered_after_cancel: 'Untriggered after cancel',
};
const SETUP_WORDS: Record<CancelOutcome, string> = { ...CANCEL_WORDS, right: 'Setup lost', wrong: 'Setup reached TP1' };
const SPLIT_DIMS: readonly { dim: CancelSplit['dim']; title: string }[] = [
  { dim: 'origin', title: 'Origin' }, { dim: 'direction', title: 'Direction' }, { dim: 'horizon', title: 'Horizon' },
];
const SPLIT_LABEL: Record<string, string> = { regular: 'Regular', next_session: 'Next session', long: 'Long', short: 'Short' };

interface SplitRow { key: string; label: string; figure: CancelFigure }
interface SplitGroup { dim: CancelSplit['dim']; title: string; rows: SplitRow[] }

@Component({
  selector: 'sb-cancels-summary',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, NgTemplateOutlet],
  template: `
    <ng-template #mark let-f>
      @if (f.small_n) {
        <span class="small-n" title="Fewer than {{ data().small_n_threshold }} resolved plans: an anecdote, not a rate">N &lt; {{ data().small_n_threshold }}</span>
      }
    </ng-template>

    <sb-panel heading="Were the bot's cancels right?">
      <div class="headline-block">
        <div class="headline">
          <div class="figure" data-figure="precision">
            <span class="label">Precision</span>
            <div class="figure-line">
              <span class="value num">{{ figureText(data().headline.all) }}</span>
              <span class="n">N {{ data().headline.all.n }}</span>
              <ng-container *ngTemplateOutlet="mark; context: { $implicit: data().headline.all }" />
            </div>
            <span class="ci">{{ ciText(data().headline.all.precision_ci) }}</span>
          </div>
          <div class="figure" data-figure="net-r">
            <span class="label">Net R</span>
            <div class="figure-line">
              <span class="value num">{{ rText(data().headline.all.net_r) }}</span>
              <span class="n">N {{ data().headline.all.n }}</span>
              <ng-container *ngTemplateOutlet="mark; context: { $implicit: data().headline.all }" />
            </div>
            <span class="ci">{{ rCi(data().headline.all.net_r_ci) }}</span>
            <span class="split-r">R avoided {{ rText(data().headline.all.r_avoided) }} · R missed {{ rText(-data().headline.all.r_missed) }}</span>
          </div>
        </div>
        <p class="caption">{{ data().caption }}</p>
        <p class="survival">{{ data().headline.all.n }} of {{ data().headline.all.total }} cancels reach the precision N: {{ data().headline.all.counts.unresolved }} unresolved (MTM {{ rText(data().headline.all.unresolved_r) }}), {{ data().headline.all.counts.untriggered_after_cancel }} untriggered after cancel, {{ data().headline.all.excluded }} excluded.</p>
        <p class="ties">{{ data().headline.all.ties }} verdicts decided by a same-bar stop and TP1 touch, counted as the stop.</p>
        <p class="without-risk-cap">Without risk_cap: {{ figureText(data().headline.without_risk_cap) }} · net {{ rText(data().headline.without_risk_cap.net_r) }} <ng-container *ngTemplateOutlet="mark; context: { $implicit: data().headline.without_risk_cap }" /></p>
        <p class="baseline">Filled plans, same window, strategy and horizon: stop first {{ figureText(data().baseline) }} · {{ ciText(data().baseline.precision_ci) }} <ng-container *ngTemplateOutlet="mark; context: { $implicit: data().baseline }" /></p>
        <p class="as-of">Bars as of {{ data().data_as_of ?? '—' }} · @if (data().window.first) {cancels {{ data().window.first }} to {{ data().window.last }}} @else {no scored cancels}</p>
        @if (data().rule_changes.length) {
          <div class="rule-changes">
            <p class="note">Rules changed inside this window, so a pooled figure spans more than one rule:</p>
            <ul>
              @for (rc of data().rule_changes; track rc.date) {
                <li>{{ rc.date }} {{ rc.label }}</li>
              }
            </ul>
          </div>
        }
        <p class="manual">Manual cancels are your decisions and stay out of every figure: {{ data().out_of_scope.manual }}.</p>
      </div>
    </sb-panel>

    <sb-panel heading="By cancel reason">
      <div class="cards-block">
        <div class="cards">
          <div class="pair">
            <p class="pair-label">{{ data().risk_cap_label }}</p>
            @for (c of pairCards; track c.key) {
              <ng-container *ngTemplateOutlet="cardTpl; context: { $implicit: c }" />
            }
          </div>
          @for (c of otherCards; track c.key) {
            <ng-container *ngTemplateOutlet="cardTpl; context: { $implicit: c }" />
          }
        </div>
        <p class="note">Cards pool regular and next-session plans.</p>
        <p class="caption">{{ data().caption }}</p>
      </div>
    </sb-panel>

    <ng-template #cardTpl let-c>
      <button type="button" class="card" [attr.data-card]="c.key" [attr.aria-pressed]="filter().card === c.key" (click)="card.emit(c.key)">
        <span class="title">{{ c.title }}</span>
        <span class="num">{{ figureText(cardFig(c.key)) }}</span>
        <span class="n">N {{ cardFig(c.key).n }}</span>
        <span class="net num">net {{ rText(cardFig(c.key).net_r) }}</span>
        <span class="ci">{{ ciText(cardFig(c.key).precision_ci) }}</span>
        <ng-container *ngTemplateOutlet="mark; context: { $implicit: cardFig(c.key) }" />
        @if (c.note) { <span class="note">{{ c.note }}</span> }
        @if (c.key === 'risk_cap_fill') { <span class="note">{{ fillSources() }}</span> }
      </button>
    </ng-template>

    <sb-panel heading="Right, wrong, unresolved">
      <div class="counts">
        <p class="counts-head">{{ activeTitle() }}</p>
        <ng-container *ngTemplateOutlet="mark; context: { $implicit: active() }" />
        <div class="counts-row">
          @for (o of outcomes; track o) {
            <button type="button" class="count" [attr.data-outcome]="o" [attr.aria-pressed]="filter().outcome === o" (click)="outcome.emit(o)">
              <span class="word">{{ words()[o] }}</span>&ngsp;<span class="num">{{ active().counts[o] }}</span>&ngsp;<span class="r num">{{ countR(o, active()) }}</span>
            </button>
          }
        </div>
        <p class="tp1-note">{{ data().tp1_note }}</p>
      </div>
    </sb-panel>

    <sb-panel heading="Splits">
      <div class="splits">
        @for (g of splitGroups(); track g.dim) {
          <section class="split-group">
            <p class="group-title">{{ g.title }}</p>
            @for (r of g.rows; track r.key) {
              <button type="button" class="split-row" [attr.data-split]="g.dim + ':' + r.key" [attr.aria-pressed]="isSplit(g.dim, r.key)" (click)="split.emit({ dim: g.dim, value: r.key })">
                <span class="label">{{ r.label }}</span>
                <span class="num">{{ figureText(r.figure) }}</span>
                <span class="net num">net {{ rText(r.figure.net_r) }}</span>
                <ng-container *ngTemplateOutlet="mark; context: { $implicit: r.figure }" />
              </button>
            } @empty {
              <p class="split-empty">No rows yet.</p>
            }
          </section>
        }
      </div>
    </sb-panel>
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); container-type: inline-size; container-name: cancels; }
    .headline, .cards, .splits, .pair { display: grid; gap: var(--space-10); grid-template-columns: minmax(0, 1fr); }
    .counts-row { display: grid; gap: var(--space-8); grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
    .figure { display: grid; gap: var(--space-4); align-content: start; }
    .figure-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }
    .value { font-size: var(--text-hero); line-height: 1.1; }
    .num { font-family: var(--font-num); }
    .card, .count, .split-row {
      min-height: var(--control-h); display: grid; gap: var(--space-4); align-content: start;
      padding: var(--space-8) var(--space-10); text-align: left; font: inherit; color: inherit;
      background: var(--surface-raised); border: 1px solid var(--border); border-radius: var(--radius-sm); cursor: pointer;
    }
    .card[aria-pressed='true'], .count[aria-pressed='true'], .split-row[aria-pressed='true'] {
      border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent);
    }
    .small-n { color: var(--warn); font-size: var(--text-micro); }
    .caption, .note, .as-of, .tp1-note, .pair-label, .survival, .ties, .manual, .split-empty {
      margin: 0; color: var(--text-faint); font-size: var(--text-micro);
    }
    .baseline, .without-risk-cap { margin: 0; font-size: var(--text-body); }
    @container cancels (min-width: 640px) {
      .headline, .cards, .splits { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
      .pair { grid-column: 1 / -1; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
      .counts-row { grid-template-columns: none; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); }
    }
    @container cancels (min-width: 1024px) {
      .cards, .splits { grid-template-columns: none; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); }
      .pair { grid-column: span 2; }
    }
  `,
})
export class CancelsSummary {
  readonly data = input.required<CancelPrecision>();
  readonly filter = input.required<CancelFilter>();
  readonly card = output<CancelCardKey | null>();
  readonly outcome = output<CancelOutcome | null>();
  readonly split = output<CancelSplit | null>();

  protected readonly outcomes = OUTCOMES;
  protected readonly pairCards = CARDS.slice(0, 2);
  protected readonly otherCards = CARDS.slice(2);
  protected readonly figureText = figureText;
  protected readonly ciText = ciText;
  protected readonly rText = rText;

  protected readonly active = computed<CancelFigure>(() => {
    const c = this.filter().card;
    return c ? this.data().cards[c] : this.data().headline.all;
  });
  protected readonly activeTitle = computed(() => {
    const c = this.filter().card;
    return c ? (CARDS.find((x) => x.key === c)?.title ?? c) : 'All three reasons, trigger entry';
  });
  protected readonly words = computed(() => {
    const c = this.filter().card;
    return c === 'risk_cap' || c === 'risk_cap_fill' ? SETUP_WORDS : CANCEL_WORDS;
  });
  protected readonly fillSources = computed(() => {
    const fills = this.data().rows.filter((r) => r.entry_model === 'cancel_fill');
    const recorded = fills.filter((r) => r.entry_source === 'recorded').length;
    const estimated = fills.filter((r) => r.entry_source === 'estimated').length;
    return `recorded ${recorded} · estimated ${estimated}`;
  });
  protected readonly splitGroups = computed<SplitGroup[]>(() =>
    SPLIT_DIMS.map(({ dim, title }) => ({
      dim, title,
      rows: Object.entries(this.data().splits[dim] as Record<string, CancelFigure | undefined>)
        .filter((e): e is [string, CancelFigure] => e[1] !== undefined)
        .map(([key, figure]) => ({ key, label: SPLIT_LABEL[key] ?? key, figure })),
    })));

  protected cardFig(key: CancelCardKey): CancelFigure {
    return this.data().cards[key];
  }

  protected countR(o: CancelOutcome, f: CancelFigure): string {
    if (o === 'right') return `${rText(f.r_avoided)} avoided`;
    if (o === 'wrong') return `${rText(-f.r_missed)} missed`;
    if (o === 'unresolved') return `MTM ${rText(f.unresolved_r)}`;
    return 'no R';
  }

  protected rCi(ci: [number, number] | null): string {
    return ci === null ? '95% CI —' : `95% CI [${rText(ci[0])}, ${rText(ci[1])}]`;
  }

  protected isSplit(dim: CancelSplit['dim'], key: string): boolean {
    const s = this.filter().split;
    return s !== null && s.dim === dim && s.value === key;
  }
}
