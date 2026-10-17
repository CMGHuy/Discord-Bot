import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { ProviderHealthRow, SystemHealth } from '../../api/models';
import { ABSENT, dateTime, num, share } from '../../ui/format';
import { Panel } from '../../ui/layout';

/** One rendered row. The text is built here rather than in the template so
 *  the spec can pin "unknown renders —, never 0%" without a DOM. */
export interface ProviderHealthLine {
  at: string;
  tickers: string;
  fallback: string;
  fallbackBreach: boolean;
  empty: string;
  emptyBreach: boolean;
  stale: string;
}

const isKnown = (value: number | null | undefined): value is number =>
  value !== null && value !== undefined;

/** A fraction as an unsigned percentage with one decimal; unknown → "—".
 *  `share`, not `pct`: a rate is a level, not a gain or a loss. */
export function rateText(rate: number | null | undefined): string {
  return isKnown(rate) ? share(rate * 100, 1) : ABSENT;
}

/** The comparison the bot alerts on (`ops_watch.provider_verdict`): strictly
 *  above `pct / 100`. An unknown rate never breaches. */
export function breaches(rate: number | null | undefined, pct: number): boolean {
  return isKnown(rate) && rate > pct / 100;
}

function emptyText(row: ProviderHealthRow): string {
  return isKnown(row.empty_symbols)
    ? `${num(row.empty_symbols, 0)} (${rateText(row.empty_rate)})`
    : ABSENT;
}

/** Server order (newest first) is kept. */
export function providerLines(health: SystemHealth | null): ProviderHealthLine[] {
  if (!health) return [];
  const { fallback_pct, empty_pct } = health.thresholds;
  return health.providers.map((row) => ({
    at: dateTime(row.at),
    tickers: num(row.tickers, 0),
    fallback: rateText(row.provider_fallback_rate),
    fallbackBreach: breaches(row.provider_fallback_rate, fallback_pct),
    empty: emptyText(row),
    emptyBreach: breaches(row.empty_rate, empty_pct),
    stale: num(row.stale_symbols, 0),
  }));
}

/**
 * v148 — the last 20 scans' provider figures, newest first.
 *
 * A breach is marked in the danger colour AND with the words "over limit":
 * colour alone fails anyone who cannot tell the red apart, and this is the
 * table someone reads to decide whether the data feed is broken.
 */
@Component({
  selector: 'sb-provider-health-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Data providers">
      <p class="explain">
        Recent scans, newest first. The ops channel is alerted when fallback is above {{ fallbackPct() }}% or empty is above {{ emptyPct() }}% of a scan.
        Stale counts frames whose last bar is older than the previous NYSE session; it is shown here, not alerted on.
      </p>
      @if (lines().length) {
        <div class="scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Scan</th>
                <th scope="col" class="right">Tickers</th>
                <th scope="col" class="right">Fallback</th>
                <th scope="col" class="right">Empty</th>
                <th scope="col" class="right">Stale</th>
              </tr>
            </thead>
            <tbody>
              @for (line of lines(); track $index) {
                <tr>
                  <td>{{ line.at }}</td>
                  <td class="num right">{{ line.tickers }}</td>
                  <td class="num right" [class.breach]="line.fallbackBreach">{{ line.fallback }}@if (line.fallbackBreach) {<span class="flag"> · over limit</span>}</td>
                  <td class="num right" [class.breach]="line.emptyBreach">{{ line.empty }}@if (line.emptyBreach) {<span class="flag"> · over limit</span>}</td>
                  <td class="num right">{{ line.stale }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="explain">No scan recorded yet.</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .explain {
      max-width: 72ch;
      margin: 0 0 var(--space-10);
      color: var(--text-secondary);
      font-size: var(--text-table);
      line-height: 1.5;
    }
    .scroll { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    th {
      padding: var(--space-6) var(--space-8);
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
      font-weight: 500;
      text-align: left;
      white-space: nowrap;
    }
    td {
      padding: var(--space-6) var(--space-8);
      border-bottom: 1px solid var(--border);
      color: var(--text);
      white-space: nowrap;
    }
    .right { text-align: right; }
    .breach { color: var(--neg); font-weight: 600; }
  `,
})
export class ProviderHealthPanel {
  readonly health = input<SystemHealth | null>(null);

  protected readonly lines = computed(() => providerLines(this.health()));
  protected readonly fallbackPct = computed(() => this.health()?.thresholds.fallback_pct ?? ABSENT);
  protected readonly emptyPct = computed(() => this.health()?.thresholds.empty_pct ?? ABSENT);
}
