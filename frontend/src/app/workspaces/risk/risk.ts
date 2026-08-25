import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';

import { RiskPosition } from '../../api/models';
import { RiskStore } from '../../stores/risk.store';
import { asyncInputs, Async } from '../../ui/async';
import { Button } from '../../ui/button';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, RowContext } from '../../ui/data-table/data-table.types';
import { dateTime, num, text } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { RowLink } from '../../ui/row-link';
import { SectionHead } from '../../ui/section-head';
import { Sparkline } from '../../ui/sparkline';

/**
 * Risk — exposure, heat against `PORTFOLIO_HEAT_CAP_PCT`, and the killswitch.
 *
 * Spec v14 Decision 7 keeps this as its own destination because it owns an
 * operational control rather than a readout. That control is the whole reason
 * the workspace exists, so it sits at the top, above the numbers that justify
 * pulling it.
 *
 * **"Risk used" appears here and on the Dashboard. That is one number in two
 * places, not two features.** The Dashboard's card is the glance; this page is
 * where the breakdown behind it lives, and both read `heat.open_pct` -- the
 * sum of the same `trade_risk_pct` the exposure table lists row by row.
 *
 * The engaged state is *also* rendered by the shell, and deliberately so: it
 * changes what the bot does regardless of which workspace is open, so it
 * cannot be a fact you have to navigate here to learn. The shell holds one
 * boolean of its own for that; this is not a second copy of the workspace's
 * state.
 *
 * Four panels below the fold -- sector heat, correlated clusters, the
 * drawdown throttle, scan health -- carry over from the Jinja page. The specs
 * are silent on all four, and silence is not a decision to drop them.
 */
@Component({
  selector: 'sb-risk',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Async, Button, ConfirmDialog, DataTable, Panel, RowLink, SectionHead, Sparkline],
  // v54 D1: exposure-by-position is a table and the rest of this workspace
  // (heat, sectors, clusters, scan health) is the same operational reading
  // that table's numbers roll up into -- tight rows, more per screen -- so
  // it defaults to the instrument register. On the host (a static class, not
  // a template wrapper) because :host is the ancestor the register's four
  // variables need to reach.
  host: { class: 'register-instrument' },
  // Provided on the component: created on entry, destroyed on exit, so the
  // workspace cannot hold stale exposure while you are looking at another.
  providers: [RiskStore],
  template: `
    <sb-section-head heading="Risk">
      @if (store.error(); as message) {
        <!-- Kept unconditional, unlike Dashboard/Trades: the killswitch and
             scan-health panels below stay outside the sb-async wrap (see
             its comment) and have no error surface of their own -- this is
             the only place their staleness shows. It does duplicate the
             wrapped panel's own error/stale display on a first-load
             failure, which is an acceptable trade for not losing the
             killswitch's error visibility. -->
        <span actions class="stale" role="status">{{ message }}</span>
      }
    </sb-section-head>

    <!-- killswitch ------------------------------------------------------ -->

    <sb-panel heading="Killswitch">
      <div class="kill">
        <div class="kill-state">
          <span class="kill-value" [class.engaged]="store.killswitchOn()">
            {{ store.killswitchOn() ? 'ENGAGED' : 'Clear' }}
          </span>
          <p class="kill-explain">
            @if (store.killswitchOn()) {
              The bot is not opening new positions. Open trades are still
              monitored and can still close.
            } @else {
              The bot is free to open new positions as setups appear.
            }
          </p>
          @if (killswitchDetail(); as detail) {
            <p class="kill-detail">{{ detail }}</p>
          }
        </div>

        <!-- Both directions go through the dialog. Releasing is as
             consequential as engaging -- it puts money back at risk -- and a
             one-click release beside a guarded engage is an invitation to
             undo a deliberate stop by accident. -->
        <button
          sb-button
          [variant]="store.killswitchOn() ? 'secondary' : 'danger'"
          type="button"
          [loading]="store.toggling()"
          [disabled]="store.empty()"
          (click)="ask()"
        >
          {{ store.killswitchOn() ? 'Release killswitch' : 'Engage killswitch' }}
        </button>
      </div>

      @if (store.commandError(); as message) {
        <!-- Held until the next attempt rather than auto-dismissed: the user
             asked for a state change that did not happen, and nothing else
             on this screen says so. -->
        <p class="command-error" role="alert">
          {{ message }}
          <button sb-button variant="ghost" type="button" (click)="store.dismissCommandError()">
            Dismiss
          </button>
        </p>
      }
    </sb-panel>

    <sb-confirm-dialog
      [open]="asking()"
      [title]="dialogTitle()"
      [consequence]="dialogConsequence()"
      [confirmLabel]="dialogConfirm()"
      [working]="store.toggling()"
      (confirmed)="confirm()"
      (cancelled)="asking.set(false)"
    />

    <!-- heat, exposure, sector/cluster breakdown --------------------------
         One sb-async around the three panels that read the fetch's numbers.
         The killswitch panel above and the scan-health panel below stay
         outside it deliberately: the killswitch is an operational control
         that must stay usable at zero open risk (an operator may want to
         engage it exactly when flat, to stop the bot opening anything new),
         and scan health answers "is the scanner healthy", a question that
         has nothing to do with whether risk exposure happens to be zero
         right now. Both already degrade gracefully via the store's own
         null-safe defaults while the first fetch is in flight. -->
    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="measured-zero"
      emptyTitle="No open risk"
      emptyHint="No position is currently exposed."
      [skeletonRows]="6"
      [skeletonCols]="5"
      (retry)="store.load()"
    >
    <sb-panel heading="Portfolio heat">
      <div class="heat">
        <span class="heat-figure num" [class]="heatClass()">
          {{ fmt(store.openHeatPct()) }}%
        </span>
        <span class="heat-cap num">of {{ fmt(store.heatCapPct(), 1) }}% cap</span>
      </div>

      <!-- An explicit null check, not a truthiness one: zero heat is a real
           state and an empty track is how it should look. Binding the
           fraction with "as" would hide the meter exactly when nothing is
           at risk. -->
      @if (store.heatMeterFraction() !== null) {
        <div
          class="track"
          role="meter"
          aria-label="Portfolio heat against the cap"
          [attr.aria-valuenow]="store.heatUtilisationPct()"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <!-- Only the WIDTH is clamped. The percentage beside it is not:
               130% of the cap is exactly the state worth seeing, and a bar
               that overflowed its track would just look broken. -->
          <span
            class="fill"
            [class]="heatClass()"
            [style.width.%]="(store.heatMeterFraction() ?? 0) * 100"
          ></span>
        </div>
      }

      <p class="heat-note" [class.warn]="store.heatNearCap()">
        {{ heatNote() }}
      </p>

      <div class="states">
        @if (store.paused()) {
          <span class="state warn">Scanning paused</span>
        }
        <!-- SR62. risk.html:125-129. -->
        <p class="section-help">
          Derived from the account's own equity curve: the deeper the current
          drawdown, the smaller every new position, so a losing run compounds
          down instead of up.
        </p>
        @if (store.throttled()) {
          <!-- The drawdown throttle sizes new positions down without
               stopping them. It is not the killswitch and must not read as
               one. -->
          <span class="state warn">
            Drawdown throttle at ×{{ fmt(store.throttleMultiplier()) }}
          </span>
        }
        @if (!store.paused() && !store.throttled() && !store.empty()) {
          <span class="state">Sizing unthrottled</span>
        }
      </div>
    </sb-panel>

    <!-- exposure -------------------------------------------------------- -->

    <sb-panel heading="Exposure by position" [flush]="true">
      <sb-data-table
        [rows]="store.positions()"
        [columns]="columns()"
        [visible]="visible"
        [rowKey]="rowKey"
        [emptyState]="emptyState"
      />
    </sb-panel>

    <div class="split">
      <sb-panel heading="Sector heat">
        @if (store.sectorHeat().length) {
          <dl class="sectors">
            @for (row of store.sectorHeat(); track row.sector) {
              <div>
                <dt>{{ fmtText(row.sector) }}</dt>
                <dd class="num">{{ fmt(row.heat_pct) }}%</dd>
              </div>
            }
          </dl>
        } @else {
          <p class="none">No sector exposure.</p>
        }
      </sb-panel>

      <sb-panel heading="Correlated clusters">
        <!-- SR62. risk.html:97-100. The panel listed the clusters without
             ever saying why they matter. -->
        <p class="section-help">
          Positions in one cluster tend to lose together, so their combined
          risk is larger than the per-trade numbers suggest.
        </p>
        @if (store.clusters(); as clusters) {
          @if (clusters.length) {
            <!-- Correlated positions are one bet wearing several tickers:
                 the heat figure above counts them separately, and this is
                 the panel that says so. -->
            <ul class="clusters">
              @for (cluster of clusters; track cluster.index) {
                <li>
                  <span class="cluster-index">{{ cluster.index }}</span>
                  <span class="cluster-tickers num">{{ cluster.tickers.join(' · ') }}</span>
                </li>
              }
            </ul>
          } @else {
            <p class="none">No correlated clusters among open positions.</p>
          }
        }
      </sb-panel>
    </div>
    </sb-async>

    <sb-panel heading="Scan health">
      <div class="scan">
        <div class="scan-figures">
          <span class="scan-latest num">{{ fmt(store.scanLatestS(), 1) }}s</span>
          <span class="scan-label">last scan</span>
        </div>
        @if (store.scanDurations().length) {
          <sb-sparkline
            [points]="store.scanDurations()"
            label="Recent scan durations, in seconds"
          />
        }
      </div>
      @if (store.scanSlowdown()) {
        <!-- Amber, not red: a slow scan is a caution about freshness, not a
             loss. It matters here because stale scans mean the exposure
             above is older than it looks. -->
        <p class="heat-note warn">
          Scans are running slower than usual — setups and prices may be stale.
        </p>
      }
    </sb-panel>

    <!-- cells ----------------------------------------------------------- -->

    <ng-template #tickerCell let-row>
      <sb-row-link [link]="['/trades', row.trade_id]">{{ row.ticker }}</sb-row-link>
    </ng-template>

    <ng-template #riskCell let-row>
      <!-- Plain, not red. This is risk budget, not a loss -- painting it red
           would claim money that has not been lost. -->
      <span class="num">{{ fmt(row.risk_pct) }}%</span>
    </ng-template>
  `,
  styles: `
    /* minmax(0, 1fr), not the implicit auto track. An auto column is floored
       at its widest child's min-content, so one un-shrinkable panel stretched
       the workspace past the viewport and took the page sideways with it.
       Clamping the track is what makes the children's own overflow-x
       containers the thing that scrolls instead.
       No backticks in here: these styles live in a TS template literal. */
    /* v54 D1: --space-20 was this rule's own literal before the registers
       existed; --register-pad's instrument rung is --space-10, so both
       gaps below shrink -- the tighter rhythm density is the point of
       opting this workspace into the instrument register. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--register-pad); }

    /* -- killswitch -- */
    .kill {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: var(--register-pad);
    }
    .kill-value {
      font-size: var(--text-subhead);
      font-weight: 700;
      letter-spacing: 0.04em;
    }
    /* The one place on this screen where red is not P&L, matching the
       danger button: a stop that does not look like a stop is worse than a
       colour rule kept perfectly. */
    .kill-value.engaged { color: var(--neg); }
    .kill-explain {
      margin-top: var(--space-6);
      max-width: 60ch;
      color: var(--text-secondary);
      font-size: var(--text-table);
      line-height: 1.5;
    }
    .kill-detail {
      margin-top: var(--space-6);
      color: var(--text-faint);
      font-size: var(--text-chip);
    }
    .command-error {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      margin-top: var(--space-14);
      color: var(--neg);
      font-size: var(--text-table);
    }

    /* -- heat -- */
    .heat { display: flex; align-items: baseline; gap: var(--space-8); }
    .heat-figure { font-size: var(--text-metric); font-weight: 700; line-height: 1.1; }
    /* The caption beside the hero figure -- same role as MetricCard's .sub,
       which is what --register-label was introduced for. --text-table (13px)
       shrinks to the instrument rung (11px); never grows. */
    .heat-cap { color: var(--text-muted); font-size: var(--register-label); }

    .track {
      height: 6px;
      margin-top: var(--space-10);
      max-width: 520px;
      background: var(--bg);
      border-radius: 3px;
      overflow: hidden;
    }
    .fill { display: block; height: 100%; background: var(--text-muted); }
    .fill.warn { background: var(--warn); }

    .heat-note {
      margin-top: var(--space-8);
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    .warn { color: var(--warn); }

    .states { display: flex; flex-wrap: wrap; gap: var(--space-8); margin-top: var(--space-10); }
    .state {
      padding: 1px var(--space-6);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text-secondary);
      /* --text-micro, not --register-label: this is an eyebrow tag, not a
         caption, and --register-label grows to --text-table in the
         presentation register (styles.css's register comment) -- an eyebrow
         must not grow just because it sits inside a presentation panel. */
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .state.warn { border-color: var(--warn); }

    /* -- the two side-by-side panels -- */
    .split {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: var(--register-pad);
    }
    .sectors > div {
      display: flex;
      justify-content: space-between;
      gap: var(--space-10);
      padding: var(--space-4) 0;
      font-size: var(--text-table);
    }
    .sectors dt { color: var(--text-secondary); }

    .clusters { display: grid; gap: var(--space-6); }
    .clusters li {
      display: flex;
      align-items: baseline;
      gap: var(--space-8);
      font-size: var(--text-table);
    }
    .cluster-index { color: var(--text-faint); font-size: var(--register-label); }

    .none { color: var(--text-faint); font-size: var(--text-table); }

    /* -- scan health -- */
    .scan { display: flex; align-items: center; gap: var(--register-pad); }
    .scan-figures { display: flex; align-items: baseline; gap: var(--space-6); }
    .scan-latest { font-size: var(--text-subhead); font-weight: 600; }
    /* --text-micro, not --register-label -- an eyebrow tag, see .state above. */
    .scan-label { color: var(--text-secondary); font-size: var(--text-micro); text-transform: uppercase; letter-spacing: 0.1em; }
    .scan sb-sparkline { flex: 1 1 auto; min-width: 80px; max-width: 320px; }

    sb-row-link { color: var(--accent); font-family: var(--font-mono); }

    @media (max-width: 720px) {
      .kill { flex-direction: column; align-items: stretch; }
    }
  `,
})
export class Risk {
  protected readonly store = inject(RiskStore);

  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (data) => data.positions.length === 0 }),
  );

  /** The dialog is open. Only ever set from the button, so there is no state
   *  where a confirmation is showing for a toggle nobody asked for. */
  protected readonly asking = signal(false);

  protected readonly rowKey = (row: RiskPosition) => row.trade_id;

  protected readonly emptyState = {
    title: 'No open positions',
    hint: 'Nothing is at risk right now.',
  };

  private readonly tickerCell =
    viewChild.required<TemplateRef<RowContext<RiskPosition>>>('tickerCell');
  private readonly riskCell =
    viewChild.required<TemplateRef<RowContext<RiskPosition>>>('riskCell');

  protected readonly visible = ['ticker', 'strategy', 'shares', 'entry', 'stop_loss', 'risk_pct'];

  /** No column picker and no sorting: the server sorts by risk descending,
   *  which is the one order this table is read in, and a six-column table
   *  has nothing to hide. */
  protected readonly columns = computed<ColumnDef<RiskPosition>[]>(() => [
    { key: 'ticker', header: 'Ticker', cell: this.tickerCell() },
    { key: 'strategy', header: 'Strategy', value: (row) => text(row.strategy) },
    { key: 'shares', header: 'Shares', value: (row) => num(row.shares, 0), numeric: true },
    { key: 'entry', header: 'Entry', value: (row) => num(row.entry), numeric: true },
    { key: 'stop_loss', header: 'Stop', value: (row) => num(row.stop_loss), numeric: true },
    { key: 'risk_pct', header: 'Risk %', numeric: true, cell: this.riskCell() },
  ]);

  protected readonly heatClass = computed(() => (this.store.heatNearCap() ? 'warn' : ''));

  protected readonly heatNote = computed(() => {
    const utilisation = this.store.heatUtilisationPct();
    if (utilisation === null) return 'Portfolio heat is not available.';
    if (this.store.heatOverCap()) {
      // Over the cap is a real state, not an impossible one: the cap gates
      // new entries, and open positions can drift past it as stops move.
      return `${utilisation.toFixed(0)}% of the cap — over budget. New entries are blocked until heat falls.`;
    }
    return `${utilisation.toFixed(0)}% of the risk budget in use.`;
  });

  /** Who engaged it and when, when the server recorded it. */
  protected readonly killswitchDetail = computed(() => {
    const kill = this.store.killswitch();
    if (!kill?.on) return null;
    const reason = kill.reason ? `Reason: ${kill.reason}` : null;
    const at = kill.at ? `Engaged ${dateTime(kill.at)}` : null;
    return [at, reason].filter(Boolean).join(' · ') || null;
  });

  protected readonly dialogTitle = computed(() =>
    this.store.killswitchOn() ? 'Release the killswitch' : 'Engage the killswitch',
  );

  /** Names what changes, per spec v14 — not "are you sure?". Both sentences
   *  are about the bot's behaviour, because that is the thing being changed;
   *  neither of them is reversible without coming back here. */
  protected readonly dialogConsequence = computed(() => {
    const count = this.store.positions().length;
    const open = count === 1 ? '1 open position' : `${count} open positions`;
    return this.store.killswitchOn()
      ? `The bot will resume opening new positions immediately, on top of the ${open} it already holds.`
      : `The bot will stop opening new positions. The ${open} it holds stay open and keep being monitored — this does not close anything.`;
  });

  protected readonly dialogConfirm = computed(() =>
    this.store.killswitchOn() ? 'Release' : 'Engage',
  );

  protected ask(): void {
    this.asking.set(true);
  }

  protected confirm(): void {
    // Read before the request: the store's own state flips as soon as the
    // response lands, and reading it inside the callback would toggle back.
    this.store.toggleKillswitch(!this.store.killswitchOn());
    this.asking.set(false);
  }

  protected fmt = num;
  protected fmtText = text;
}
