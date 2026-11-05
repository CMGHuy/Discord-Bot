import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { LiveAwaiting } from '../../api/models';
import { isStale, liveTime } from './live-state';

export type AwaitingState = 'loading' | 'unavailable' | 'empty' | 'ok';
export interface AwaitingView {
  state: AwaitingState; count: number | null; expiry: string | null;
  reason: string | null; asOf: string; stale: boolean;
}

/** '30 Oct': the Berlin day a session-dated plan expires; null when none. */
export function expiryDay(iso: string | null): string | null {
  const at = iso ? new Date(iso) : null;
  if (at === null || Number.isNaN(at.getTime())) return null;
  return at.toLocaleDateString('en-GB', { timeZone: 'Europe/Berlin', day: 'numeric', month: 'short' });
}

function awaitingState(a: LiveAwaiting | null, loading: boolean): AwaitingState {
  if (a === null) return loading ? 'loading' : 'unavailable';
  if (a.availability !== 'ok' || a.count === null) return 'unavailable';
  return a.count === 0 ? 'empty' : 'ok';
}

/** What the section shows, from the /live awaiting block. */
export function awaitingView(a: LiveAwaiting | null, loading: boolean, now: Date): AwaitingView {
  return {
    state: awaitingState(a, loading),
    count: a?.count ?? null,
    expiry: expiryDay(a?.next_expiry ?? null),
    reason: a?.reason ?? null,
    asOf: liveTime(a?.as_of ?? null, now),
    stale: a !== null && isStale(a.as_of, now),
  };
}

let nextId = 0;

/**
 * Plans awaiting order -- v203 (spec v202 §4.2). A state count of PENDING
 * plans, never a since-last-visit badge: it drops only when a plan fills,
 * expires or is cancelled. The next expiry shows only for plans that carry
 * `valid_session`, where it is exact; bar-count plans get no guess.
 */
@Component({
  selector: 'sb-live-awaiting',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <section class="live-section" [attr.aria-labelledby]="headingId">
      <h2 class="title" [id]="headingId">Plans awaiting order</h2>
      @switch (view().state) {
        @case ('loading') { <p class="muted" role="status">Loading…</p> }
        @case ('unavailable') {
          <p class="muted">Plans unavailable@if (view().reason; as reason) { · {{ reason }}}</p>
        }
        @default {
          <p class="figure"><span class="count">{{ view().count }}</span> awaiting order</p>
          @if (view().state === 'ok') {
            @if (view().expiry; as expiry) { <p class="aside-note">Next expires {{ expiry }}</p> }
            <a class="link sb-hit" routerLink="/trades" [queryParams]="pendingParams">Show in Book ›</a>
          }
          <p class="as-of" [class.warn]="view().stale">As of {{ view().asOf }}</p>
        }
      }
    </section>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .title { margin: 0 0 var(--space-6); color: var(--text-muted); font-size: var(--text-micro); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    p { margin: 0 0 var(--space-4); font-size: var(--text-table); overflow-wrap: anywhere; }
    .figure { color: var(--text-secondary); }
    .count { color: var(--text); font-size: var(--text-body); font-weight: 600; font-variant-numeric: tabular-nums; }
    .aside-note, .muted, .as-of { color: var(--text-muted); }
    .as-of.warn { color: var(--warn); }
    .link { display: inline-flex; align-items: center; min-height: var(--control-h); color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .link:hover { text-decoration: underline; }
  `,
})
export class LiveAwaitingSection {
  readonly awaiting = input<LiveAwaiting | null>(null);
  readonly loading = input(false);
  readonly now = input.required<Date>();

  protected readonly headingId = `live-awaiting-${nextId++}`;
  /** The Book's own filter vocabulary (trades.ts: `{ value: 'PENDING', param: 'status' }`). */
  protected readonly pendingParams = { status: 'PENDING' };
  protected readonly view = computed(() => awaitingView(this.awaiting(), this.loading(), this.now()));
}
