import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';

import { ApiClient } from '../api/api-client';
import { EventStream, MARKET_DATA_MIN_INTERVAL_MS } from '../api/event-stream';
import { RegimeDay, RegimeEpisode, RegimeResponse } from '../api/models';

/** What the dashboard banner (V239-15) renders; `null` means hidden. */
export interface RegimeBanner {
  kind: 'reading' | 'none';
  tone: 'bear' | 'correction' | 'muted';
  label: string;
  /** Confirmed-episode session count; null when today is not that episode. */
  since: number | null;
  numbers: string | null;
  words: string | null;
  /** True when a pullback day sits inside a confirmed correction episode. */
  pullback: boolean;
  accessibleName: string;
}

/** Episode labels that are not a correction a pullback day can sit inside. */
const NOT_A_CORRECTION_EPISODE = new Set(['Normal', 'No reading']);

function isHidden(res: RegimeResponse | null): boolean {
  return !res || res.mode === 'off' || !res.today || res.today.state === 'NORMAL';
}

function unknownBanner(): RegimeBanner {
  return {
    kind: 'none', tone: 'muted', label: 'No reading', since: null, numbers: null, words: null,
    pullback: false, accessibleName: 'Regime: no reading',
  };
}

function titleFor(today: RegimeDay, episode: RegimeEpisode | null): { label: string; pullback: boolean } {
  const pullbackDay = today.state === 'CORRECTION' && today.pullback_trigger === true;
  if (pullbackDay && episode && !NOT_A_CORRECTION_EPISODE.has(episode.label)) {
    return { label: episode.label, pullback: true };
  }
  return { label: today.display.label, pullback: false };
}

/** `'dip in an uptrend'` -> `'Dip in an uptrend.'` */
function sentence(words: string): string {
  const trimmed = words.trim();
  if (!trimmed) return trimmed;
  const capped = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  return capped.endsWith('.') ? capped : `${capped}.`;
}

/** `'Correction · Stress'` -> `'Correction, stress'` */
function spoken(label: string): string {
  const [first, ...rest] = label.split('·').map((part) => part.trim());
  return [first, ...rest.map((part) => part.toLowerCase())].join(', ');
}

function accessibleName(label: string, since: number | null, pullback: boolean, numbers: string | null): string {
  const count = since === null ? '' : `, ${since} ${since === 1 ? 'session' : 'sessions'}`;
  const chip = pullback ? ', pullback watch' : '';
  const figures = numbers ? `; ${numbers}` : '';
  return `Regime ${spoken(label)}${count}${chip}${figures}`;
}

function readingBanner(today: RegimeDay, episode: RegimeEpisode | null): RegimeBanner {
  const { label, pullback } = titleFor(today, episode);
  const since = episode && episode.label === label ? episode.since_sessions : null;
  const numbers = today.display.numbers;
  return {
    kind: 'reading', tone: today.state === 'BEAR' ? 'bear' : 'correction', label, since, numbers,
    words: sentence(today.display.words), pullback,
    accessibleName: accessibleName(label, since, pullback, numbers),
  };
}

/** The dashboard banner for one `/market/regime` answer; `null` hides it. */
export function regimeBanner(res: RegimeResponse | null): RegimeBanner | null {
  if (isHidden(res)) return null;
  const today = res!.today!;
  if (today.state === 'UNKNOWN') return unknownBanner();
  return readingBanner(today, res!.episode);
}

/** v239: the daily bear-regime reading, refetched after each scan pass.
 *  The banner is hidden while loading and on error (never a stale label). */
@Injectable({ providedIn: 'root' })
export class RegimeStore {
  private readonly api = inject(ApiClient);
  private readonly response = signal<RegimeResponse | null>(null);
  private readonly _status = signal<'loading' | 'ready' | 'error'>('loading');
  private latest = 0;

  readonly status = this._status.asReadonly();
  readonly banner = computed(() => (this._status() === 'ready' ? regimeBanner(this.response()) : null));

  constructor() {
    // The scan pass writes the day's row; `scan` fires ~1/s while a scan runs.
    const scan = inject(EventStream).changes('scan', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS });
    effect(() => {
      scan();
      untracked(() => this.refresh());
    });
  }

  refresh(): void {
    const request = ++this.latest;
    this.api.marketRegime().subscribe({
      next: (res) => {
        if (request !== this.latest) return;
        this.response.set(res ?? null);
        this._status.set('ready');
      },
      error: (err: unknown) => {
        if (request !== this.latest) return;
        console.error('regime: /market/regime failed; the banner stays hidden', err);
        this.response.set(null);
        this._status.set('error');
      },
    });
  }
}
