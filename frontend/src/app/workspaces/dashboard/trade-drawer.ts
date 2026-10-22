import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TradeRow } from '../../api/models';
import { ConnectionStore } from '../../stores/connection.store';
import { CLOCK } from '../../ui/clock';
import { ABSENT, dateTime, elapsedHours, held, money, num, pct, text } from '../../ui/format';
import { Drawer } from '../../ui/layout';
import { sideLabel } from '../trades/trade-figures';
import { livePnlPct, liveUnrealizedAmount } from './dashboard.helpers';
import { RowActions } from './row-actions';

/** The header marker. The bot only paper-trades (CLAUDE.md, eToro roadmap
 *  stage 0); a drawer that looks like a position ticket must say so. */
export const PAPER_MARKER = 'Paper trade';

export interface TradeDrawerField {
  key: string;
  label: string;
  value: string;
  numeric: boolean;
  tone: 'pos' | 'neg' | null;
}

type Tone = TradeDrawerField['tone'];

/** Realised for a closed leg, live for an open or pending one -- the same
 *  split the Dashboard's P&L cell makes (`dashboard.ts` `#pnlCell`), from
 *  the same helpers, so the drawer can never disagree with the table. */
export function drawerPnl(row: TradeRow): { pct: number | null; amount: number | null } {
  if (row.pnl_pct !== null) return { pct: row.pnl_pct, amount: row.realized_pnl_amount };
  return { pct: livePnlPct(row), amount: liveUnrealizedAmount(row) };
}

function toneOf(value: number | null): Tone {
  if (value === null || value === 0) return null;
  return value > 0 ? 'pos' : 'neg';
}

/** Percentage first, the amount beside it -- the money floor (spec §3.1):
 *  P&L is never shown as a percentage alone when an amount exists. */
function pnlText(row: TradeRow, currency: string): string {
  const { pct: percent, amount } = drawerPnl(row);
  if (percent === null && amount === null) return ABSENT;
  if (amount === null) return pct(percent);
  return `${pct(percent)} (${money(amount, currency)})`;
}

function field(key: string, label: string, value: string, numeric = false, tone: Tone = null): TradeDrawerField {
  return { key, label, value, numeric, tone };
}

/** A pending plan has no fill yet: the level it waits on is its trigger. */
function entryField(row: TradeRow): TradeDrawerField {
  return row.entry === null
    ? field('trigger', 'Trigger', num(row.trigger_price), true)
    : field('entry', 'Entry', num(row.entry), true);
}

/** The original plan stop, as the trade detail's plan card shows it (`risk_stop`;
 *  `stop_loss` is the working stop once PARTIAL), then the working stop only
 *  when it has moved off it on a position that is still live. */
function stopFields(row: TradeRow): TradeDrawerField[] {
  const planned = row.risk_stop ?? row.stop_loss;
  const fields = [field('stop', 'Stop', num(planned), true)];
  const live = row.status === 'ACTIVE' || row.status === 'PARTIAL';
  if (live && row.stop_loss !== null && planned !== null && row.stop_loss !== planned) {
    fields.push(field('working_stop', 'Working stop', num(row.stop_loss), true));
  }
  return fields;
}

/** Everything the drawer shows, from the loaded row alone (spec §3.2: no
 *  fetch). Absent values are the em dash, never NaN or an empty cell. */
export function tradeDrawerFields(row: TradeRow, currency: string, nowMs: number): TradeDrawerField[] {
  return [
    field('direction', 'Direction', sideLabel(row.direction) ?? ABSENT),
    field('status', 'Status', text(row.status_label || row.status)),
    field('pnl', 'P&L', pnlText(row, currency), true, toneOf(drawerPnl(row).pct)),
    entryField(row),
    ...stopFields(row),
    field('tp1', 'TP1', num(row.target1 ?? row.target), true),
    field('tp2', 'TP2', num(row.target2), true),
    field('rr', 'R:R', num(row.risk_reward), true),
    field('opened', 'Opened', dateTime(row.opened_at)),
    field('held', 'Held', held(row.held_hours ?? elapsedHours(row.opened_at, nowMs)), true),
    field('strategy', 'Strategy', text(row.strategy)),
    field('horizon', 'Horizon', text(row.horizon)),
  ];
}

/**
 * One trade, summarised in a drawer — v179 §3.2.
 *
 * Owns its `sb-drawer` so the "Paper trade" marker can be projected into the
 * drawer's header (`[drawer-header]`): Angular projects only what the
 * parent template writes between the `<sb-drawer>` tags. The Dashboard mounts
 * this only while a trade is open; `closed` tells it the drawer closed itself
 * (×, Escape, backdrop), `actionDone` that a row action changed the trade.
 *
 * Desktop: the drawer's side panel; phone: its bottom sheet. No media query
 * here -- the geometry is `sb-drawer`'s.
 */
@Component({
  selector: 'sb-trade-drawer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Drawer, RowActions, RouterLink],
  template: `
    <sb-drawer [open]="true" [heading]="row().ticker" (closed)="closed.emit()">
      <span drawer-header class="paper-marker"
            title="The bot places no orders: every trade on this page is a paper trade.">{{ paperMarker }}</span>
      <dl class="fields">
        @for (item of fields(); track item.key) {
          <div class="field" [attr.data-field]="item.key">
            <dt>{{ item.label }}</dt>
            <dd [class.num]="item.numeric" [class.pos]="item.tone === 'pos'" [class.neg]="item.tone === 'neg'"
                [class.long]="item.key === 'direction' && item.value.toLowerCase() === 'long'"
                [class.short]="item.key === 'direction' && item.value.toLowerCase() === 'short'">{{ item.value }}</dd>
          </div>
        }
      </dl>
      <div class="drawer-actions">
        <a class="full-trade sb-hit" [routerLink]="['/trades', row().id]">Open full trade →</a>
        <sb-row-actions [row]="row()" placement="up" (done)="actionDone.emit()" />
      </div>
    </sb-drawer>
  `,
  styles: `
    :host { display: contents; }
    .paper-marker {
      padding: 0 var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--chip-radius);
      color: var(--text-secondary);
      font-size: var(--text-chip);
      letter-spacing: .04em;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .fields { display: grid; gap: var(--space-6); margin: 0; }
    /* Label and value at two faces (UI and numeric) on one line: baseline,
       never centre (spec §3.4). */
    .field {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: var(--space-10);
      min-width: 0;
    }
    /* Meaning carried by colour: risk levels red, targets green, the setup
       (strategy, horizon) in the accent; rows get a faint raised surface. */
    .field { padding: var(--space-4) var(--space-8); border-radius: var(--radius-sm); background: var(--surface-raised); border-left: 2px solid transparent; }
    .field[data-field='stop'], .field[data-field='working_stop'] { border-left-color: var(--neg); }
    .field[data-field='stop'] dd, .field[data-field='working_stop'] dd { color: var(--neg); }
    .field[data-field='tp1'], .field[data-field='tp2'] { border-left-color: var(--pos); }
    .field[data-field='tp1'] dd, .field[data-field='tp2'] dd { color: var(--pos); }
    .field[data-field='entry'], .field[data-field='trigger'], .field[data-field='rr'] { border-left-color: var(--accent); }
    .field[data-field='entry'] dd, .field[data-field='trigger'] dd { color: var(--accent); }
    .field[data-field='strategy'] dd, .field[data-field='horizon'] dd { color: var(--accent); }
    .field[data-field='direction'] dd.long { color: var(--pos); font-weight: 600; }
    .field[data-field='direction'] dd.short { color: var(--neg); font-weight: 600; }
    dd.pos { color: var(--pos); }
    dd.neg { color: var(--neg); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { margin: 0; min-width: 0; font-size: var(--text-table); text-align: right; overflow-wrap: anywhere; }
    .drawer-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-10);
      margin-top: var(--space-14);
      padding-top: var(--space-10);
      border-top: 1px solid var(--border);
    }
    /* RowActions opens towards its left: keep its trigger at the right edge
       so the menu stays inside the drawer, including when the line wraps. */
    sb-row-actions { margin-left: auto; }
    .full-trade { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .full-trade:hover { text-decoration: underline; }
  `,
})
export class TradeDrawer {
  readonly row = input.required<TradeRow>();
  readonly closed = output<void>();
  readonly actionDone = output<void>();

  private readonly connection = inject(ConnectionStore);
  private readonly now = inject(CLOCK);

  protected readonly paperMarker = PAPER_MARKER;
  protected readonly fields = computed(() =>
    tradeDrawerFields(this.row(), this.connection.currency(), this.now()));
}
