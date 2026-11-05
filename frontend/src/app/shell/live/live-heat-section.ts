import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { LiveHeat } from '../../api/models';
import { ABSENT, amount } from '../../ui/format';
import { PanelError } from '../../ui/panel-error';
import { HeatTone, heatTone, isStale, liveTime } from './live-state';

export type HeatState = 'loading' | 'unavailable' | 'ok';
export interface HeatView {
  state: HeatState; tone: HeatTone; atRisk: string; utilisation: string; room: string;
  utilisationPct: number | null; meterWidth: number; resting: boolean; message: string;
  asOf: string; stale: boolean;
}

const pctText = (value: number) => `${Number(value.toFixed(1))}%`;

/** '2,010 € at risk · 4.2% of 48,210 € · cap 6% (2,893 €)'. A missing
 *  amount drops only its own words; a missing percent gives '—'. */
export function atRiskText(h: LiveHeat, currency: string): string {
  if (h.open_pct === null || h.cap_pct === null) return ABSENT;
  const lead = h.open_amount === null ? 'At risk' : `${amount(h.open_amount, currency, 0)} at risk`;
  const share = h.balance === null ? pctText(h.open_pct) : `${pctText(h.open_pct)} of ${amount(h.balance, currency, 0)}`;
  const cap = h.cap_amount === null ? `cap ${pctText(h.cap_pct)}` : `cap ${pctText(h.cap_pct)} (${amount(h.cap_amount, currency, 0)})`;
  return `${lead} · ${share} · ${cap}`;
}

/** 'Room 883 € · 1.8% under the cap', or 'Over cap by 867 € · 1.8%' when the headroom is negative. */
export function roomText(h: LiveHeat, currency: string): string {
  if (h.headroom_pct === null) return ABSENT;
  const money = h.headroom_amount === null ? '' : `${amount(Math.abs(h.headroom_amount), currency, 0)} · `;
  return h.headroom_pct < 0
    ? `Over cap by ${money}${pctText(-h.headroom_pct)}`
    : `Room ${money}${pctText(h.headroom_pct)} under the cap`;
}

/** '70% of the cap'; above 100 % it adds ' · Over cap', so near and over never look alike. Never clamped. */
export function utilisationText(utilisationPct: number | null): string {
  if (utilisationPct === null) return ABSENT;
  const words = `${pctText(utilisationPct)} of the cap`;
  return heatTone(utilisationPct) === 'over' ? `${words} · Over cap` : words;
}

function heatState(h: LiveHeat | null, loading: boolean): HeatState {
  if (h === null) return loading ? 'loading' : 'unavailable';
  return h.availability === 'ok' && h.open_pct !== null && h.cap_pct !== null ? 'ok' : 'unavailable';
}

/** Only the meter's WIDTH is clamped (as on the Risk page); every number printed is not. */
const meterWidth = (pct: number | null) => Math.min(100, Math.max(0, pct ?? 0));

/** What the section shows, from the /live heat block. */
export function heatView(h: LiveHeat | null, loading: boolean, currency: string, now: Date): HeatView {
  const pct = h?.utilisation_pct ?? null;
  return {
    state: heatState(h, loading),
    tone: heatTone(pct),
    atRisk: h ? atRiskText(h, currency) : ABSENT,
    utilisation: utilisationText(pct),
    room: h ? roomText(h, currency) : ABSENT,
    utilisationPct: pct,
    meterWidth: meterWidth(pct),
    resting: h?.includes_resting === true,
    message: h?.reason ? `Heat unavailable (${h.reason})` : 'Heat unavailable',
    asOf: liveTime(h?.as_of ?? null, now),
    stale: h !== null && isStale(h.as_of, now),
  };
}

let nextId = 0;

/**
 * Portfolio heat -- v203 (spec v202 §4.3). Exactly the Risk page's heat
 * (v202's /live computes it with the same `heat.open_heat`), read from
 * /live only: this component never sees the risk workspace store. Amber from 80 % of the
 * cap, "Over cap" in words above 100 %, never red in Phase 1.
 */
@Component({
  selector: 'sb-live-heat',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PanelError],
  template: `
    <section class="live-section" [attr.aria-labelledby]="headingId">
      <h2 class="title" [id]="headingId">Portfolio heat</h2>
      @switch (view().state) {
        @case ('loading') { <p class="muted" role="status">Loading…</p> }
        @case ('unavailable') { <sb-panel-error [message]="view().message" (retry)="retry.emit()" /> }
        @default {
          <p class="at-risk" [class.warn]="warn()">{{ view().atRisk }}</p>
          <div class="track" role="meter" aria-label="Portfolio heat against the cap"
               [attr.aria-valuenow]="view().utilisationPct" aria-valuemin="0" aria-valuemax="100"
               [attr.aria-valuetext]="view().utilisation">
            <span class="fill" [class.warn]="warn()" [style.width.%]="view().meterWidth"></span>
          </div>
          <p class="util" [class.warn]="warn()">{{ view().utilisation }}</p>
          <p class="room">{{ view().room }}</p>
          @if (view().resting) { <p class="aside-note">incl. resting orders</p> }
          <p class="as-of" [class.warn]="view().stale">As of {{ view().asOf }}</p>
        }
      }
    </section>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .title { margin: 0 0 var(--space-6); color: var(--text-muted); font-size: var(--text-micro); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    p { margin: 0 0 var(--space-4); font-size: var(--text-table); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
    .at-risk { color: var(--text); }
    .util, .room { color: var(--text-secondary); }
    .aside-note, .muted, .as-of { color: var(--text-muted); }
    .warn, .as-of.warn { color: var(--warn); }
    .track { height: 6px; margin: var(--space-6) 0; border-radius: var(--radius-sm); background: var(--border); overflow: hidden; }
    .fill { display: block; height: 100%; background: var(--text-muted); }
    .fill.warn { background: var(--warn); }
  `,
})
export class LiveHeatSection {
  readonly heat = input<LiveHeat | null>(null);
  readonly loading = input(false);
  readonly currency = input.required<string>();
  readonly now = input.required<Date>();
  readonly retry = output<void>();

  protected readonly headingId = `live-heat-${nextId++}`;
  protected readonly view = computed(() => heatView(this.heat(), this.loading(), this.currency(), this.now()));
  protected readonly warn = computed(() => this.view().tone === 'near' || this.view().tone === 'over');
}
