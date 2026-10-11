import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { Leg, StatusEvent } from '../../../stores/trade-detail.store';
import { dateTime, num, rMultiple, share } from '../../../ui/format';
import { Panel } from '../../../ui/layout';

/** The settled scale-out results and the plan's ordered audit trail. */
@Component({
  selector: 'sb-outcome-path',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    @if (legs().length > 1) {
      <sb-panel heading="Scale-out">
        <dl class="factors">
          @for (leg of legs(); track $index) {
            <div>
              <dt>
                @if ($index === 0) { First } @else { Runner }
                @if (leg.fraction !== null) {
                  <span class="muted muted-gap">{{ fmtShare(leg.fraction * 100) }}</span>
                }
              </dt>
              <dd class="num">
                @if (leg.exitPrice !== null) {
                  {{ fmt(leg.exitPrice) }}
                  @if (leg.r !== null) {
                    <span [class]="pnlClass(leg.r)">{{ fmtR(leg.r) }}</span>
                  }
                  @if (leg.reason) {
                    <span class="muted muted-gap">{{ leg.reason }}</span>
                  }
                } @else {
                  <span class="muted muted-gap">still open</span>
                }
              </dd>
            </div>
          }
        </dl>
      </sb-panel>
    }

    @if (timeline().length) {
      <sb-panel heading="Timeline">
        <ol class="timeline">
          @for (event of timeline(); track $index) {
            <li>
              <span class="tl-status">{{ event.status }}</span>
              @if (event.reason) {
                <span class="tl-reason">{{ event.reason }}</span>
              }
              @if (event.at) {
                <span class="tl-at">{{ fmtDate(event.at) }}</span>
              }
            </li>
          }
        </ol>
      </sb-panel>
    }
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: var(--section-gap); }
    dl { display: grid; gap: var(--space-6); }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { color: var(--text); font-size: var(--text-table); }
    .factors > div { align-items: baseline; gap: var(--space-14); }
    .factors dd { text-align: right; }
    .muted-gap { margin-left: var(--space-6); }
    .timeline {
      display: grid;
      gap: var(--space-8);
      margin-left: var(--space-6);
      padding-left: var(--space-14);
      border-left: 1px solid var(--border-strong);
      list-style: none;
    }
    .timeline li { position: relative; font-size: var(--text-table); }
    .timeline li::before {
      content: '';
      position: absolute;
      left: calc(-1 * var(--space-14) - 3px);
      top: 0.45em;
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: var(--border-strong);
    }
    .tl-status { color: var(--text); font-weight: 600; }
    .tl-reason { margin-left: var(--space-6); color: var(--text-secondary); }
    .tl-at { margin-left: var(--space-6); color: var(--text-faint); font-size: var(--text-chip); }
  `,
})
export class OutcomePath {
  readonly legs = input<Leg[]>([]);
  readonly timeline = input<StatusEvent[]>([]);

  protected readonly fmt = num;
  protected readonly fmtShare = share;
  protected readonly fmtR = rMultiple;
  protected readonly fmtDate = dateTime;

  protected pnlClass(value: number | null | undefined): string {
    if (value === null || value === undefined) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  }
}
