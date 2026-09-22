import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  TemplateRef,
  viewChild,
  WritableSignal,
} from '@angular/core';

import { AnalyticsStore, GridRow, JobStatus, JobSummary, ProposalRow } from '../../../stores/analytics.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { Button } from '../../../ui/button';
import { Chip, qualityTone } from '../../../ui/chip';
import { ConfirmDialog } from '../../../ui/confirm-dialog';
import { createClientPage } from '../../../ui/data-table/client-page';
import { DataTable } from '../../../ui/data-table/data-table';
import { ColumnDef } from '../../../ui/data-table/data-table.types';
import { Select } from '../../../ui/form-controls';
import { ABSENT, dateTime } from '../../../ui/format';
import { ControlRow, Panel } from '../../../ui/layout';
import { PaginationComponent } from '../../../ui/pagination';
import { PanelHeader } from '../../../ui/panel-header';
import { readTablePerPage, writeTablePerPage } from '../../../ui/table-prefs';
import { allKeys, expectancy, GRID_COLUMNS, PAST_JOBS_COLUMNS, rate } from '../analytics.columns';

/** A proposal with its parameter diff already paired up for rendering. */
interface ProposalView extends ProposalRow {
  params: { key: string; current: string; proposed: string }[];
  trainSummary: string;
}

/**
 * v94 Tuning -- launch a TRAIN grid, watch it, stage a proposal.
 *
 * Moved verbatim from the old monolith (Task T6): same fields, same actions,
 * same confirm-dialog copy. Not scoped -- no `n`, no all-time badge on its
 * panel headers -- a tuning job and its proposals are not a slice of the
 * closed book, so the scope bar's N has nothing to say about them.
 *
 * Progress arrives on the `jobs` event, never a timer: the store's
 * `loadTuning`/`loadJob` are driven by the server's watcher on
 * `admin_jobs.json` and `tuning_results/`, so this component only ever
 * reads what the store already holds.
 */
@Component({
  selector: 'sb-tuning-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, ControlRow, Select, Button, Chip, DataTable, PaginationComponent, ConfirmDialog],
  template: `
    <sb-panel>
      <sb-panel-header title="Run a TRAIN grid" />
      <p class="section-help">
        A grid search runs one strategy's parameters through every
        combination in its tuning grid against the fixed TRAIN window
        (2020-01-01 .. 2023-12-31) —
        never the VALIDATION window the badges on the Strategies tab are
        measured against. That firewall is what keeps those badges honest,
        so no date input exists here or anywhere in this workbench.
      </p>

      @if (store.jobActive()) {
        <p class="section-help">
          A job is running. The server allows one at a time, so the
          launcher returns when it finishes.
        </p>
      } @else {
        <sb-control-row class="launch">
          <sb-select
            label="Strategy"
            placeholder="Pick a strategy"
            [(value)]="strategy"
            [options]="strategyOptions()"
          />
          <button
            sb-button
            type="button"
            variant="primary"
            [disabled]="strategy() === ''"
            [loading]="store.launching()"
            (click)="launch()"
          >
            Launch TRAIN grid
          </button>
        </sb-control-row>
        @if (store.launchError(); as message) {
          <p class="alert" role="alert">{{ message }}</p>
        }
      }
    </sb-panel>

    @if (store.job(); as job) {
      <sb-panel [flush]="true">
        <sb-panel-header [title]="'Job ' + job.id" class="flush-head" />
        <div class="jobhead">
          <sb-chip [label]="jobStateLabel(job)" [tone]="jobTone(job)" />
          <span class="muted">started {{ dateTime(job.started_at) }}</span>
        </div>
        <pre class="log">{{ job.log_tail || 'No output yet.' }}</pre>
        <p class="section-help">
          Progress arrives on the <code>jobs</code> event. Nothing on this
          page polls, and the log stays put when the job ends.
        </p>
      </sb-panel>
    }

    <!-- SR51. The results table, and the Propose button that lived in it.
         Without this the tab could start work and file work away but not
         act on what a run found -- which left the Proposals panel below
         unreachable by any normal route. -->
    @if (store.grid().length) {
      <sb-panel [flush]="true">
        <sb-panel-header [title]="gridHeading()" class="flush-head" />
        @if (store.proposeResult(); as message) {
          <p class="section-help" role="status">{{ message }}</p>
        }
        @if (store.proposeError(); as message) {
          <p class="alert" role="alert">{{ message }}</p>
        }

        <sb-data-table
          [rows]="gridPage.visible()"
          [columns]="gridColumns()"
          [visible]="gridKeys"
          [rowKey]="gridRowKey"
          [pagination]="gridPage.pageSpec()"
          [showPerPage]="true"
          (pageChange)="gridPage.setPage($event)"
          (perPageChange)="onPerPage('grid', $event)"
        />

        <p class="section-help">
          A row clears the bar at 30 or more evaluated trades, a win rate of
          80% or better, positive expectancy, and no more than half the
          candidate signals excluded. Among the rows that clear it, prefer
          the highest expectancy.
        </p>
      </sb-panel>
    }

    @if (store.pastJobs(); as past) {
      @if (past.length) {
        <sb-panel [flush]="true">
          <sb-panel-header title="Earlier jobs" class="flush-head" />
          <sb-data-table
            [rows]="pastJobsPage.visible()"
            [columns]="pastJobsColumns"
            [visible]="pastJobsKeys"
            [rowKey]="pastJobRowKey"
            [pagination]="pastJobsPage.pageSpec()"
            (pageChange)="pastJobsPage.setPage($event)"
          />
        </sb-panel>
      }
    }

    <sb-panel>
      <sb-panel-header title="Proposals" />
      <p class="section-help">
        A proposal is a staged parameter change, not an applied one:
        applying means editing <code>entry_filters.DEFAULT_PARAMS</code> by
        hand, running the suite, and only then spending a validation shot.
      </p>

      @if (proposalViews().length === 0) {
        <p class="muted">No proposals yet.</p>
      }
      @for (proposal of proposalsPage.visible(); track proposal.filename) {
        <div class="proposal">
          <header class="proposal-head">
            <strong>{{ proposal.strategy }}</strong>
            <span class="muted">
              {{ dateTime(proposal.created_at) }} · job {{ proposal.job_id }}
            </span>
          </header>
          <table class="diff">
            <thead>
              <tr><th>Parameter</th><th class="num">Current</th><th class="num">Proposed</th></tr>
            </thead>
            <tbody>
              @for (param of proposal.params; track param.key) {
                <tr>
                  <td>{{ param.key }}</td>
                  <td class="num muted">{{ param.current }}</td>
                  <td class="num">{{ param.proposed }}</td>
                </tr>
              }
            </tbody>
          </table>
          <p class="muted">{{ proposal.trainSummary }}</p>
          <button
            sb-button
            type="button"
            variant="danger"
            (click)="pendingDelete.set(proposal)"
          >
            Delete
          </button>
        </div>
      }
      <sb-pagination [pagination]="proposalsPage.pageSpec()" (pageChange)="proposalsPage.setPage($event)" />
    </sb-panel>

    <ng-template #gridPassesCell let-row>
      @if (row.passes) {
        <sb-chip label="Clears" tone="q5" />
      }
    </ng-template>
    <ng-template #gridProposeCell let-row>
      <button
        sb-button
        variant="secondary"
        type="button"
        [loading]="store.proposing() === row.row_index"
        (click)="askPropose(row)"
      >
        Propose
      </button>
    </ng-template>

    <sb-confirm-dialog
      [open]="pendingDelete() !== null"
      title="Delete this proposal?"
      [consequence]="deleteConsequence()"
      confirmLabel="Delete"
      (confirmed)="confirmDelete()"
      (cancelled)="pendingDelete.set(null)"
    />

    <!-- Proposing writes a file that stages a change to how the bot trades.
         It is not destructive, but it is not nothing either, and the dialog is
         where the difference between staging and applying gets said out loud
         rather than left to a panel note further down the page. -->
    <sb-confirm-dialog
      [open]="pendingPropose() !== null"
      title="Stage these parameters?"
      [consequence]="proposeConsequence()"
      confirmLabel="Propose"
      [working]="store.proposing() !== null"
      (confirmed)="confirmPropose()"
      (cancelled)="pendingPropose.set(null)"
    />
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); }

    .alert {
      padding: var(--space-8) var(--space-10);
      border: 1px solid var(--warn);
      border-radius: var(--radius);
      color: var(--warn);
      font-size: var(--text-table);
    }

    .section-help { max-width: 70ch; }
    .section-help + .section-help, .section-help + .launch { margin-top: var(--space-10); }
    code { font-family: var(--font-mono); }

    /* Flush panels (Job, Grid results, Earlier jobs) put their table edge to
     * edge, which leaves sb-panel-header with none of the padding the panel
     * body would otherwise supply -- this restores it, matching the header
     * every non-flush panel here already gets for free. */
    .flush-head {
      display: block;
      padding: var(--space-10) var(--space-14);
      border-bottom: 1px solid var(--border);
    }
    sb-panel .section-help { padding: 0 var(--space-14); }

    .jobhead {
      display: flex;
      align-items: center;
      gap: var(--space-10);
      padding: var(--space-10) var(--space-14);
    }
    .log {
      max-height: 320px;
      margin: 0;
      padding: var(--space-10) var(--space-14);
      overflow: auto;
      background: var(--bg);
      border-top: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
      font-family: var(--font-mono);
      font-size: var(--text-table);
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .log + .section-help { padding: var(--space-10) var(--space-14); }

    .proposal {
      margin-top: var(--space-10);
      padding: var(--space-10);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }
    .proposal-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--space-10);
      margin-bottom: var(--space-8);
      font-size: var(--text-table);
    }
    .diff { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .diff th, .diff td {
      padding: var(--space-4) var(--space-8);
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    .diff th {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .diff .num { text-align: right; font-family: var(--font-mono); }
    .proposal .muted { display: block; margin: var(--space-8) 0; }
  `,
})
export class TuningTab {
  protected readonly store = inject(AnalyticsStore);
  private readonly preferences = inject(PreferencesStore);
  protected readonly dateTime = dateTime;

  /* -- tuning ------------------------------------------------------------ */

  protected readonly strategy = signal('');

  /** Rebuilt from the still-current `AnalyticsStrategies` shape -- the old
   *  `store.strategyNames()` this read was removed in the v94 S1-S4 rewrite.
   *  `/analytics/strategies` groups its contribution rows by strategy name
   *  server-side, so this is already one row per strategy; no dedup needed.
   *  Not re-sorted: `contribution` arrives sorted by contribution magnitude
   *  (`-abs(total_r), strategy` -- `analytics.py`'s `/analytics/strategies`),
   *  and re-sorting it alphabetically here would throw that away. */
  protected readonly strategyOptions = computed(() =>
    (this.store.strategies()?.contribution ?? [])
      .map((c) => ({ value: c.strategy, label: c.strategy })),
  );

  protected jobStateLabel(job: JobStatus): string {
    const state = job.state.toUpperCase();
    return job.returncode === null || job.returncode === undefined
      ? state
      : `${state} (exit ${job.returncode})`;
  }

  /** Amber for a failure, greyscale otherwise. A failed job is a caution to
   *  act on, not a loss — and red is reserved for P&L. */
  protected jobTone(job: JobStatus) {
    if (job.state === 'failed') return qualityTone('C');
    if (job.state === 'running' || job.state === 'queued') return qualityTone('A');
    return qualityTone(null);
  }

  protected launch(): void {
    const strategy = this.strategy();
    if (strategy) this.store.startTune(strategy);
  }

  /* -- SR51: the grid results --------------------------------------------- */

  private readonly gridPassesCell = viewChild.required<TemplateRef<unknown>>('gridPassesCell');
  private readonly gridProposeCell = viewChild.required<TemplateRef<unknown>>('gridProposeCell');

  protected readonly gridColumns = computed(() =>
    attach(GRID_COLUMNS, {
      passes: this.gridPassesCell(),
      propose: this.gridProposeCell(),
    }),
  );

  protected readonly gridKeys = allKeys(GRID_COLUMNS);
  protected readonly pastJobsKeys = allKeys(PAST_JOBS_COLUMNS);

  private readonly perPageSignals = new Map<string, WritableSignal<number>>();
  private perPageFor(table: string) {
    let current = this.perPageSignals.get(table);
    if (!current) {
      current = signal(readTablePerPage(this.preferences.values(), 'analytics-' + table));
      this.perPageSignals.set(table, current);
    }
    return current;
  }
  protected onPerPage(table: string, value: number): void {
    this.perPageFor(table).set(value);
    this.preferences.update((prefs) => writeTablePerPage(prefs, 'analytics-' + table, value));
  }

  protected readonly gridRowKey = (row: GridRow) => String(row.row_index);
  protected readonly gridPage = createClientPage(() => this.store.grid(), () => this.perPageFor('grid')());
  protected readonly pastJobRowKey = (row: JobSummary) => row.id;
  protected readonly pastJobsPage = createClientPage(() => this.store.pastJobs(), () => this.perPageFor('past-jobs')());
  protected readonly pastJobsColumns = PAST_JOBS_COLUMNS; // static, no cell slots needed

  protected readonly pendingPropose = signal<GridRow | null>(null);

  protected readonly gridHeading = computed(() => {
    const strategy = this.store.gridStrategy();
    return strategy ? `Grid results — ${strategy}` : 'Grid results';
  });

  protected askPropose(row: GridRow): void {
    this.pendingPropose.set(row);
  }

  protected readonly proposeConsequence = computed(() => {
    const row = this.pendingPropose();
    if (!row) return '';
    const strategy = this.store.gridStrategy() ?? 'this strategy';
    // Says outright what staging is and is not. The Jinja page put this in a
    // tip icon on a card heading, where it was read once.
    return (
      `Records ${row.paramLabel} as a candidate for ${strategy}. ` +
      'Nothing changes about how the bot trades: applying means editing ' +
      'entry_filters.DEFAULT_PARAMS by hand, running the suite, and only then ' +
      'spending a validation shot.' +
      (row.passes
        ? ''
        : ' This row did NOT clear the acceptance bar.')
    );
  });

  protected confirmPropose(): void {
    const row = this.pendingPropose();
    if (!row) return;
    this.store.propose(row.row_index);
    this.pendingPropose.set(null);
  }

  /* -- proposals ----------------------------------------------------------- */

  protected readonly pendingDelete = signal<ProposalRow | null>(null);

  /** Proposals with their parameter diff paired up. Built once per change
   *  rather than by a method the template calls per row: a method would
   *  return a new array on every check and defeat `@for`'s tracking. */
  protected readonly proposalViews = computed<ProposalView[]>(() =>
    this.store.proposals().map((proposal) => {
      const current = proposal.current_params ?? {};
      const proposed = proposal.proposed_params ?? {};
      return {
        ...proposal,
        params: Object.entries(proposed).map(([key, value]) => ({
          key,
          // An em dash, not "undefined": a parameter the code does not
          // currently set is missing, not set to the string "undefined".
          current: current[key] === undefined ? ABSENT : String(current[key]),
          proposed: String(value),
        })),
        trainSummary: trainSummary(proposal),
      };
    }),
  );

  /** Each proposal is a card with its own nested diff table, not flat row
   *  data -- `sb-data-table` doesn't fit, so this gets its own small pager
   *  rather than the shared component. */
  protected readonly proposalsPage = createClientPage(() => this.proposalViews(), 8);

  protected readonly deleteConsequence = computed(() => {
    const proposal = this.pendingDelete();
    return proposal
      ? `Removes the staged ${proposal.strategy} proposal from disk. Nothing running changes — a proposal was never applied.`
      : '';
  });

  protected confirmDelete(): void {
    const proposal = this.pendingDelete();
    if (!proposal) return;
    this.store.removeProposal(proposal.filename);
    this.pendingDelete.set(null);
  }
}

/** The templates are declared once per table on this workspace, so they
 *  cannot be typed to one row shape at their declaration site. The cast is
 *  contained here rather than repeated at every call site. */
function attach<T>(
  columns: ColumnDef<T>[],
  cells: Record<string, TemplateRef<unknown>>,
): ColumnDef<T>[] {
  return columns.map((column) =>
    cells[column.key]
      ? { ...column, cell: cells[column.key] as unknown as ColumnDef<T>['cell'] }
      : column,
  );
}

/** The TRAIN-window figures a proposal was frozen from, on one line. */
function trainSummary(proposal: ProposalRow): string {
  const stats = proposal.train_stats ?? {};
  const n = typeof stats['n_eval'] === 'number' ? stats['n_eval'] : null;
  const wr = typeof stats['win_rate'] === 'number' ? stats['win_rate'] : null;
  const er = typeof stats['expectancy_r'] === 'number' ? stats['expectancy_r'] : null;
  return `TRAIN: N=${n ?? ABSENT} · WR=${rate(wr)} · ExpR=${expectancy(er)}`;
}
