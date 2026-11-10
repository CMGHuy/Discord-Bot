import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { MarketStatus } from '../api/models';
import { ConnectionStore } from '../stores/connection.store';

/** The D2 windows as the SPA sees them. The server's `.env` knobs are not
 *  served to the SPA; changing one moves what is fetched, and only these
 *  decide when the hint appears. */
export const DASHBOARD_PRICE_WINDOW_S = 15;
export const PAGE_PRICE_WINDOW_S = 60;
export const TAPE_WINDOW_S = 60;

export function ageText(ageS: number | null): string | null {
  if (ageS === null || Number.isNaN(ageS) || ageS < 0) return null;
  if (ageS < 60) return `${Math.round(ageS)} s ago`;
  if (ageS < 3600) return `${Math.floor(ageS / 60)} min ago`;
  return `${Math.floor(ageS / 3600)} h ago`;
}

export type MarketTone = 'fresh' | 'stale' | 'closed' | 'stalled';
export interface MarketAgeLabel { text: string | null; tone: MarketTone; }

interface MarketAgeOptions {
  kind?: 'price' | 'snapshot';
  staleInputs?: boolean;
  computedAt?: string | null;
}

const ET_FORMAT = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});
const HOUR_MS = 3_600_000;

/** "Fri 16:00" in New York time, read through formatToParts so no locale
 *  punctuation leaks in. */
function etStamp(iso: string): string {
  const parts = ET_FORMAT.formatToParts(new Date(iso));
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  return part('weekday') + ' ' + part('hour') + ':' + part('minute');
}

function closedLabel(asOf: string, status: MarketStatus): string {
  const closeAt = status.last_close_at;
  const atClose = closeAt !== null && Date.parse(asOf) >= Date.parse(closeAt) - HOUR_MS;
  return atClose ? 'last close · ' + etStamp(closeAt) + ' ET' : 'as of ' + etStamp(asOf) + ' ET';
}

/**
 * v201: what a priced cell says about its age. A stalled refresher wins (the
 * age is then the honest part), a closed market reads its last close rather
 * than a scary "stale", and otherwise the age is fresh or stale against the
 * server's limit.
 */
export function marketAgeLabel(
  asOf: string | null, nowMs: number, status: MarketStatus | null, opts?: MarketAgeOptions,
): MarketAgeLabel {
  if (opts?.kind === 'snapshot') return snapshotLabel(opts.computedAt ?? null, nowMs, status, opts.staleInputs ?? false);
  const age = asOf === null ? null : (nowMs - Date.parse(asOf)) / 1000;
  if (status?.heartbeat.stalled) return { text: ageText(age), tone: 'stalled' };
  if (status?.session === 'closed') {
    return { text: asOf === null ? null : closedLabel(asOf, status), tone: 'closed' };
  }
  const limit = status?.stale_price_s ?? null;
  const stale = limit !== null && age !== null && age > limit;
  return { text: ageText(age), tone: stale ? 'stale' : 'fresh' };
}

function snapshotLabel(
  computedAt: string | null, nowMs: number, status: MarketStatus | null, staleInputs: boolean,
): MarketAgeLabel {
  const builtAt = computedAt === null ? null : Date.parse(computedAt);
  const age = builtAt === null ? null : (nowMs - builtAt) / 1000;
  if (status?.heartbeat.stalled) return { text: ageText(age), tone: 'stalled' };
  if (computedAt === null) return { text: null, tone: staleInputs ? 'stale' : 'fresh' };
  if (status?.session === 'closed') {
    const closeAt = status.last_close_at;
    if (staleInputs || (closeAt !== null && Date.parse(computedAt) < Date.parse(closeAt))) {
      return { text: 'as of ' + etStamp(computedAt) + ' ET', tone: 'stale' };
    }
    const text = closeAt === null
      ? 'as of ' + etStamp(computedAt) + ' ET'
      : 'as of last close · ' + etStamp(closeAt) + ' ET';
    return { text, tone: 'closed' };
  }
  const limit = status?.stale_snapshot_s ?? null;
  const stale = staleInputs || (limit !== null && age !== null && age > limit);
  return { text: ageText(age), tone: stale ? 'stale' : 'fresh' };
}

/**
 * v171 D2: "12 s ago" beside a price older than its page's window, and
 * nothing otherwise. Prices render at once from the shared cache; this is
 * the only sign that one is older than the page promises (no spinner, no
 * veil, no colour). It does not tick: the page's own refetch moves it,
 * as with sb-freshness.
 */
@Component({
  selector: 'sb-age-hint',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (text(); as t) {
      <span class="age-hint" [attr.title]="'Price is ' + t.replace(' ago', '') + ' old'">{{ t }}</span>
    }
  `,
  styles: `
    :host { display: inline; }
    .age-hint {
      font-size: var(--text-micro);
      color: var(--text-faint);
      white-space: nowrap;
      margin-inline-start: var(--space-4);
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class AgeHint {
  readonly ageS = input<number | null>(null);
  readonly windowS = input.required<number>();
  private readonly connection = inject(ConnectionStore);

  /** Market closed (or not known yet): every quote is "old", so say nothing. */
  protected readonly text = computed(() => {
    const age = this.ageS();
    if (this.connection.marketActive() !== true) return null;
    return age !== null && age > this.windowS() ? ageText(age) : null;
  });
}
