import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { LiveKillswitch } from '../../api/models';
import { ConnectionState } from '../../stores/connection.store';
import { ABSENT, timeInZone } from '../../ui/format';
import { scanAge } from '../freshness-chip';
import { isStale, liveTime } from './live-state';

export interface BotRow { key: string; label: string; value: string; warn: boolean; }

export interface BotSectionInput {
  botAlive: boolean | null; botHealthy: boolean | null; scanRunning: boolean;
  lastSuccess: string | null; lastSeen: string | null; streamState: ConnectionState;
  marketActive: boolean | null; killswitch: LiveKillswitch | null; now: Date;
}

const STREAM_WORDS: Readonly<Record<ConnectionState, string>> = {
  connecting: 'Connecting', live: 'Live', degraded: 'Polling (stream down)', dead: 'Offline',
};
const STREAM_DOWN: ReadonlySet<ConnectionState> = new Set(['degraded', 'dead']);

/** Scanner state: never "Running" or "Idle" before /system/scan answers. */
function scannerWord(i: BotSectionInput): string {
  if (i.botAlive === null) return ABSENT;
  if (i.botAlive === false) return 'Down';
  if (i.botHealthy === false) return 'Failing';
  return i.scanRunning ? 'Running' : 'Idle';
}

/** The freshness chip's words, as a row. */
function freshnessWord(i: BotSectionInput): string {
  if (i.botAlive === null) return ABSENT;
  const age = scanAge(i.lastSuccess ?? i.lastSeen, i.now.getTime());
  return age === null ? 'No scan yet' : `Scan ${age}`;
}

function marketWord(active: boolean | null): string {
  if (active === null) return ABSENT;
  return active ? 'Open' : 'Closed';
}

/** The killswitch in plain language (spec v202 §4); unknown reads as the chip does. */
export function killswitchText(k: LiveKillswitch | null): string {
  if (k === null || k.availability === 'unavailable' || k.engaged === null) return 'Killswitch ?';
  if (!k.engaged) return 'Clear';
  return k.since ? `Active: new alerts paused since ${timeInZone(k.since, 'Europe/Berlin')}` : 'Active: new alerts paused';
}

/** The Bot section's rows, in order, each with its words and warning tone. */
export function botRows(i: BotSectionInput): BotRow[] {
  const stale = i.botAlive !== null && isStale(i.lastSuccess, i.now);
  return [
    { key: 'scanner', label: 'Scanner', value: scannerWord(i), warn: i.botAlive === false || i.botHealthy === false },
    { key: 'last-scan', label: 'Last scan', value: liveTime(i.lastSuccess, i.now), warn: stale },
    { key: 'freshness', label: 'Data', value: freshnessWord(i), warn: stale },
    { key: 'stream', label: 'Event stream', value: STREAM_WORDS[i.streamState], warn: STREAM_DOWN.has(i.streamState) },
    { key: 'market', label: 'Market', value: marketWord(i.marketActive), warn: false },
    { key: 'killswitch', label: 'Killswitch', value: killswitchText(i.killswitch), warn: i.killswitch?.engaged === true },
  ];
}

let nextId = 0;

/**
 * The Live dock's Bot section -- v203 (spec v202 §4.1). It absorbs the top
 * bar's freshness and connection chips and the clock. Pure inputs: the
 * dock (V203-7) wires ConnectionStore, LiveStore.killswitch() and the shell
 * clock, so every state is a one-line test. Wording lives in botRows.
 */
@Component({
  selector: 'sb-live-bot',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="live-section" [attr.aria-labelledby]="headingId">
      <h2 class="title" [id]="headingId">Bot</h2>
      <dl class="rows">
        @for (row of rows(); track row.key) {
          <div class="row" [class.warn]="row.warn">
            <dt>{{ row.label }}</dt>
            <dd>{{ row.value }}</dd>
          </div>
        }
      </dl>
    </section>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .title { margin: 0 0 var(--space-6); color: var(--text-muted); font-size: var(--text-micro); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    .rows { display: flex; flex-direction: column; gap: var(--space-4); margin: 0; }
    .row { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0 var(--space-8); min-width: 0; font-size: var(--text-table); }
    dt { color: var(--text-secondary); }
    dd { margin: 0; min-width: 0; color: var(--text); font-variant-numeric: tabular-nums; text-align: right; overflow-wrap: anywhere; }
    .warn dd { color: var(--warn); }
  `,
})
export class LiveBotSection {
  readonly botAlive = input<boolean | null>(null);
  readonly botHealthy = input<boolean | null>(null);
  readonly scanRunning = input(false);
  readonly lastSuccess = input<string | null>(null);
  readonly lastSeen = input<string | null>(null);
  readonly streamState = input.required<ConnectionState>();
  readonly marketActive = input<boolean | null>(null);
  readonly killswitch = input<LiveKillswitch | null>(null);
  readonly now = input.required<Date>();

  protected readonly headingId = `live-bot-${nextId++}`;
  protected readonly rows = computed(() => botRows({
    botAlive: this.botAlive(), botHealthy: this.botHealthy(), scanRunning: this.scanRunning(),
    lastSuccess: this.lastSuccess(), lastSeen: this.lastSeen(), streamState: this.streamState(),
    marketActive: this.marketActive(), killswitch: this.killswitch(), now: this.now(),
  }));
}
