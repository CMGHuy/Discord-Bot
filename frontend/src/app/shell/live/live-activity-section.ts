import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LiveEvent, LiveEventKind, LiveEventsMeta, LiveTone } from '../../api/models';
import { MINUS, amount, timeInZone } from '../../ui/format';
import { PanelError } from '../../ui/panel-error';
import { scanAge } from '../freshness-chip';
import { isStale, liveTime } from './live-state';

export interface PnlParts { r: string; amount: string | null; }
export interface ActivityRow { key: string; time: string; text: string; tone: LiveTone; pnl: PnlParts | null; line: string; }
export interface ActivityView {
  state: 'loading' | 'unavailable' | 'ok'; rows: ActivityRow[];
  missing: string | null; scanWarning: string | null; quiet: boolean;
}

const DEFAULT_CURRENCY = '€';           // ConnectionStore.currency()'s own fallback
const PAPER = '(paper, pre-cost)';
const KIND_WORDS: Readonly<Record<LiveEventKind, string>> = {
  plan_alerted: 'alerts', paper_filled: 'paper fills', tp1_hit: 'TP1 hits', trade_closed: 'closes', killswitch: 'killswitch',
};

function signOf(value: number): string {
  if (value > 0) return '+';
  return value < 0 ? MINUS : '';
}

/** '+2.1R' and '441 €' (unsigned: the R carries the sign); null without P&L. */
export function pnlParts(pnl: LiveEvent['pnl'], currency: string): PnlParts | null {
  if (pnl === null) return null;
  return {
    r: `${signOf(pnl.r)}${Math.abs(pnl.r).toFixed(1)}R`,
    amount: pnl.amount === null ? null : amount(Math.abs(pnl.amount), currency, 0),
  };
}

/** The row's one line: the server's text, then ' · +2.1R (441 €) (paper, pre-cost)' for a P&L row. */
export function activityLine(e: LiveEvent, currency: string = DEFAULT_CURRENCY): string {
  const parts = pnlParts(e.pnl, currency);
  if (parts === null) return e.text;
  return parts.amount === null ? `${e.text} · ${parts.r} ${PAPER}` : `${e.text} · ${parts.r} (${parts.amount}) ${PAPER}`;
}

/** 'Some sources unavailable: TP1 hits' for a partial read; null otherwise. */
export function missingText(meta: LiveEventsMeta | null): string | null {
  if (meta?.availability !== 'partial') return null;
  const words = meta.missing.map((kind) => KIND_WORDS[kind]);
  return words.length ? `Some sources unavailable: ${words.join(', ')}` : 'Some sources unavailable';
}

/** 'No scan since 09:00 (5h ago)' once the last success is past the 900 s rule; null while fresh. */
function scanWarning(lastSuccess: string | null, now: Date): string | null {
  if (!isStale(lastSuccess, now)) return null;
  const age = scanAge(lastSuccess, now.getTime());
  return age === null ? 'No scan yet' : `No scan since ${timeInZone(lastSuccess, 'Europe/Berlin')} (${age})`;
}

function activityState(meta: LiveEventsMeta | null, loading: boolean): ActivityView['state'] {
  if (meta === null) return loading ? 'loading' : 'unavailable';
  return meta.availability === 'unavailable' ? 'unavailable' : 'ok';
}

function rowOf(e: LiveEvent, now: Date, currency: string): ActivityRow {
  return {
    key: `${e.at}|${e.kind}|${e.ref ?? ''}`, time: liveTime(e.at, now), text: e.text, tone: e.tone,
    pnl: pnlParts(e.pnl, currency), line: activityLine(e, currency),
  };
}

/** What the section shows (spec v202 §6): a missed scan is never a quiet day. */
export function activityView(
  events: readonly LiveEvent[], meta: LiveEventsMeta | null, loading: boolean,
  lastSuccess: string | null, now: Date, currency: string,
): ActivityView {
  const rows = events.map((e) => rowOf(e, now, currency));
  const warning = scanWarning(lastSuccess, now);
  const state = activityState(meta, loading);
  return { state, rows, missing: missingText(meta), scanWarning: warning, quiet: state === 'ok' && rows.length === 0 && warning === null };
}

let nextId = 0;

/**
 * Activity -- v203 (spec v202 §4.4). The last events from /live, each with
 * its Berlin time and age, a tone and one line; every P&L line reads
 * "(paper, pre-cost)". A partial read says which sources failed, a failed
 * one says so with a retry, and a stopped bot reads "No scan since …".
 */
@Component({
  selector: 'sb-live-activity',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, PanelError],
  template: `
    <section class="live-section" [attr.aria-labelledby]="headingId">
      <h2 class="title" [id]="headingId">Activity</h2>
      @switch (view().state) {
        @case ('loading') { <p class="muted" role="status">Loading…</p> }
        @case ('unavailable') { <sb-panel-error message="Activity unavailable" (retry)="retry.emit()" /> }
        @default {
          @if (view().scanWarning; as warning) { <p class="scan-warning warn" role="status">{{ warning }}</p> }
          @if (view().rows.length) {
            <ol class="events">
              @for (row of view().rows; track row.key) {
                <li [class]="'tone-' + row.tone">
                  <span class="dot" aria-hidden="true"></span>
                  <time>{{ row.time }}</time>
                  <span class="line">{{ row.text }}@if (row.pnl; as pnl) { · <span class="r">{{ pnl.r }}</span>@if (pnl.amount) {<span class="amt"> ({{ pnl.amount }})</span>}<span class="paper"> (paper, pre-cost)</span>}</span>
                </li>
              }
            </ol>
          }
          @if (view().quiet) { <p class="quiet">Nothing yet today</p> }
          @if (view().missing; as missing) { <p class="faint">{{ missing }}</p> }
        }
      }
      @if (view().state !== 'loading') {
        <a class="link sb-hit" routerLink="/system" [queryParams]="logParams">Full activity log →</a>
      }
    </section>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .title { margin: 0 0 var(--space-6); color: var(--text-muted); font-size: var(--text-micro); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    p { margin: 0 0 var(--space-4); font-size: var(--text-table); overflow-wrap: anywhere; }
    .events { display: flex; flex-direction: column; gap: var(--space-6); margin: 0 0 var(--space-6); padding: 0; list-style: none; }
    li { display: grid; grid-template-columns: auto 1fr; gap: 0 var(--space-6); align-items: baseline; min-width: 0; font-size: var(--text-table); }
    .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted); grid-row: span 2; align-self: center; }
    time { color: var(--text-muted); font-variant-numeric: tabular-nums; }
    .line { grid-column: 2; min-width: 0; color: var(--text); overflow-wrap: anywhere; }
    .amt, .paper { color: var(--text-secondary); }
    .tone-info .dot { background: var(--accent); }
    .tone-positive .dot { background: var(--pos); }
    .tone-positive .r { color: var(--pos); }
    .tone-negative .dot { background: var(--neg); }
    .tone-negative .r { color: var(--neg); }
    .tone-warning .dot { background: var(--warn); }
    .muted, .quiet, .faint { color: var(--text-muted); }
    .faint { font-size: var(--text-micro); }
    .warn { color: var(--warn); }
    .link { display: inline-flex; align-items: center; min-height: var(--control-h); color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .link:hover { text-decoration: underline; }
  `,
})
export class LiveActivitySection {
  readonly events = input<readonly LiveEvent[]>([]);
  readonly meta = input<LiveEventsMeta | null>(null);
  readonly loading = input(false);
  readonly lastSuccess = input<string | null>(null);
  readonly now = input.required<Date>();
  readonly currency = input(DEFAULT_CURRENCY);
  readonly retry = output<void>();

  protected readonly headingId = `live-activity-${nextId++}`;
  protected readonly logParams = { tab: 'logs' };
  protected readonly view = computed(() => activityView(
    this.events(), this.meta(), this.loading(), this.lastSuccess(), this.now(), this.currency(),
  ));
}
