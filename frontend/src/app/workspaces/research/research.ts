import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';

import { LedgerRow, StrategyRow } from '../../api/models';
import { LedgerFilters, ResearchStore, filtersToParams } from '../../stores/research.store';
import { Async, asyncInputs } from '../../ui/async';
import { Button } from '../../ui/button';
import { Chip, ChipTone } from '../../ui/chip';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, EmptyState, RowContext } from '../../ui/data-table/data-table.types';
import { TextInput } from '../../ui/form-controls';
import { Drawer, Panel } from '../../ui/layout';
import { SegmentOption, Segmented } from '../../ui/segmented';
import { Toolbar, ToolbarControl } from '../../ui/toolbar';

export const DISCLAIMER = 'Historical measurement on paper trades; not a forecast or advice.';

const HYPOTHESIS_MAX = 90;

/** A verdict's colour says how the measurement came out, never whether to
 *  act on it. A verdict added to the ledger later stays neutral. */
const VERDICT_TONE: Record<string, ChipTone> = {
  PASS: 'good',
  'SCREEN-PASS': 'good',
  FAIL: 'bad',
  'SCREEN-FAIL': 'bad',
  'NO-LIFT': 'neutral',
  OPEN: 'info',
  UNMEASURABLE: 'muted',
  WITHDRAWN: 'muted',
  'SCREEN-UNDERPOWERED': 'warn',
};

const fixed = (value: number | null, digits: number): string | null =>
  value === null ? null : value.toFixed(digits);

/**
 * Research — every pre-registration this repo has measured, and the badge
 * each strategy earned.
 *
 * Read-only. The ledger is a git-tracked record that ships inside the image,
 * so the page shows it as of the deployed build and offers no way to edit
 * it; rows are appended through `scripts/reports/preregistration_ledger.py`.
 *
 * Two stacked sections rather than tabs: the registry is about a dozen rows
 * and reads as context for the ledger below it.
 */
@Component({
  selector: 'sb-research',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Async, Button, Chip, DataTable, Drawer, Panel, Segmented, TextInput, Toolbar],
  host: { class: 'register-instrument' },
  template: `
    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="no-data-yet"
      emptyTitle="No ledger"
      emptyHint="The pre-registration ledger is empty in this build."
      [skeletonRows]="10"
      [skeletonCols]="6"
      (retry)="store.load()"
    >
      <sb-panel heading="Strategy registry">
        <p class="caption">Figures in R, pre-tax.</p>
        <sb-async
          [empty]="store.registry().length === 0"
          [staleAsOf]="null"
          emptyReason="measured-zero"
          emptyTitle="No strategy has a registry entry"
        >
          <sb-data-table
            [rows]="store.registry()"
            [columns]="registryColumns()"
            [visible]="registryVisible"
            [rowKey]="strategyKey"
            [fillPage]="false"
          />
        </sb-async>
      </sb-panel>

      <sb-panel heading="Pre-registration ledger">
        <sb-toolbar [controls]="controls()">
          <div slot="verdict" class="verdicts" role="group" aria-label="Verdict">
            @for (verdict of store.verdicts(); track verdict) {
              <button sb-button variant="chip" type="button" class="verdict"
                      [class.on]="isOn(verdict)" [attr.aria-pressed]="isOn(verdict)"
                      (click)="toggleVerdict(verdict)">
                {{ verdict }} <span class="num">{{ store.verdictCounts()[verdict] }}</span>
              </button>
            }
          </div>
          <sb-segmented slot="instrument" label="Instrument" [options]="instrumentOptions()"
                        [value]="store.filters().instrument" (valueChange)="setInstrument($event)" />
          <sb-text-input slot="search" type="search" ariaLabel="Search id and hypothesis"
                         placeholder="Search id or hypothesis"
                         [value]="store.filters().search" (valueChange)="setSearch($event)" />
        </sb-toolbar>

        <sb-data-table
          [rows]="store.visible()"
          [columns]="ledgerColumns()"
          [visible]="ledgerVisible"
          [rowKey]="ledgerKey"
          [sort]="store.sort()"
          [pagination]="store.pageSpec()"
          [emptyState]="noMatch"
          (sortChange)="store.setSort($event)"
          (pageChange)="store.setPage($event)"
          (rowActivate)="store.select($event.id)"
        />
        <p class="caption">
          The ledger as of the deployed build. Append rows with
          <code>scripts/reports/preregistration_ledger.py</code>; this page never edits it.
        </p>
      </sb-panel>
    </sb-async>

    <p class="disclaimer">{{ disclaimer }}</p>

    <sb-drawer [open]="store.selected() !== null" [heading]="store.selected()?.id ?? ''"
               (closed)="store.select(null)">
      @if (store.selected(); as row) {
        <dl class="detail">
          <dt>Date</dt><dd>{{ row.date }}</dd>
          <dt>Hypothesis</dt><dd>{{ row.hypothesis }}</dd>
          <dt>Instrument</dt><dd>{{ row.instrument }}</dd>
          <dt>Verdict</dt><dd><sb-chip [label]="row.verdict" [tone]="verdictTone(row.verdict)" /></dd>
          <dt>N</dt><dd class="num">{{ row.n ?? '—' }}</dd>
          <dt>ExpR</dt><dd class="num">{{ figure(row.exp_r, 3) }}</dd>
          <dt>p</dt><dd class="num">{{ figure(row.p, 4) }}</dd>
          <dt>q</dt>
          <dd>
            <span class="num">{{ figure(row.q, 4) }}</span>
            <span class="aside">
              reported, never gating — BH over all {{ store.familySize() }} ledger rows with a
              p-value, mixing instruments; filters do not change it
            </span>
          </dd>
          <dt>Record</dt>
          <dd>
            <code class="record" [class.missing]="!row.record_exists">{{ row.record }}</code>
            <button sb-button variant="link" type="button" (click)="copy(row.record)">
              {{ copied() === row.record ? 'Copied' : 'Copy path' }}
            </button>
            @if (!row.record_exists) { <span class="aside">not in this deploy</span> }
            <span class="aside">window and method: see record</span>
          </dd>
        </dl>
      }
    </sb-drawer>

    <ng-template #tierCell let-row>
      <span class="tier">
        <sb-chip [label]="row.status" [tone]="tierTone(row.status)" />
        <span class="aside">{{ row.run_date ?? 'no run date' }} · {{ row.window ?? 'no window' }}</span>
      </span>
    </ng-template>
    <ng-template #verdictCell let-row>
      <sb-chip [label]="row.verdict" [tone]="verdictTone(row.verdict)" />
    </ng-template>
    <ng-template #hypothesisCell let-row>
      <span [attr.title]="row.hypothesis">{{ truncate(row.hypothesis) }}</span>
    </ng-template>
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); }
    .caption, .disclaimer { margin: 0; color: var(--text-faint); font-size: var(--text-micro); }
    .verdicts { display: flex; flex-wrap: wrap; gap: var(--space-6); }
    .verdict.on { color: var(--accent); }
    .tier { display: inline-flex; align-items: center; gap: var(--space-8); flex-wrap: wrap; }
    .aside { color: var(--text-faint); font-size: var(--text-micro); }
    .detail { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: var(--space-6) var(--space-14); margin: 0; }
    .detail dt { color: var(--text-muted); }
    .detail dd { margin: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }
    .record { font-family: var(--font-mono); overflow-wrap: anywhere; }
    .record.missing { text-decoration: line-through; color: var(--text-faint); }
  `,
})
export class Research {
  protected readonly store = inject(ResearchStore);
  private readonly router = inject(Router);

  protected readonly disclaimer = DISCLAIMER;
  protected readonly copied = signal<string | null>(null);

  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (data) => data.ledger.rows.length === 0 }),
  );

  private readonly tierCell = viewChild.required<TemplateRef<RowContext<StrategyRow>>>('tierCell');
  private readonly verdictCell = viewChild.required<TemplateRef<RowContext<LedgerRow>>>('verdictCell');
  private readonly hypothesisCell = viewChild.required<TemplateRef<RowContext<LedgerRow>>>('hypothesisCell');

  protected readonly registryVisible = ['strategy', 'status', 'n', 'expectancy_r', 'live_n', 'evidence_decay'];
  protected readonly registryColumns = computed<ColumnDef<StrategyRow>[]>(() => [
    { key: 'strategy', header: 'Strategy', value: (row) => row.strategy },
    { key: 'status', header: 'Badge tier', cell: this.tierCell() },
    { key: 'n', header: 'OOS N', numeric: true, value: (row) => row.n },
    { key: 'expectancy_r', header: 'OOS ExpR', numeric: true, value: (row) => fixed(row.expectancy_r, 2) },
    { key: 'live_n', header: 'Live N', numeric: true, value: (row) => row.live_n },
    { key: 'evidence_decay', header: 'Evidence', value: (row) => row.evidence_decay },
  ]);

  protected readonly ledgerVisible = ['date', 'id', 'hypothesis', 'instrument', 'n', 'exp_r', 'p', 'q', 'verdict'];
  protected readonly ledgerColumns = computed<ColumnDef<LedgerRow>[]>(() => [
    { key: 'date', header: 'Date', sortable: true, value: (row) => row.date },
    { key: 'id', header: 'Id', sortable: true, value: (row) => row.id },
    { key: 'hypothesis', header: 'Hypothesis', cell: this.hypothesisCell(), inlineFrom: 'md' },
    { key: 'instrument', header: 'Instrument', sortable: true, value: (row) => row.instrument, inlineFrom: 'md' },
    { key: 'n', header: 'N', numeric: true, sortable: true, value: (row) => row.n },
    { key: 'exp_r', header: 'ExpR', numeric: true, sortable: true, value: (row) => fixed(row.exp_r, 3) },
    { key: 'p', header: 'p', numeric: true, sortable: true, value: (row) => fixed(row.p, 4), inlineFrom: 'md' },
    { key: 'q', header: 'q', numeric: true, sortable: true, value: (row) => fixed(row.q, 4), inlineFrom: 'md' },
    { key: 'verdict', header: 'Verdict', sortable: true, cell: this.verdictCell() },
  ]);

  protected readonly noMatch: EmptyState = {
    title: 'No pre-registration matches these filters',
    hint: 'Clear a verdict, the instrument or the search.',
  };

  protected readonly instrumentOptions = computed<SegmentOption[]>(() => [
    { value: '', label: 'All' },
    ...this.store.instruments().map((instrument) => ({ value: instrument, label: instrument })),
  ]);

  protected readonly controls = computed<ToolbarControl[]>(() => {
    const filters = this.store.filters();
    return [
      { id: 'verdict', label: 'Verdict', active: filters.verdicts.length > 0 },
      { id: 'instrument', label: 'Instrument', inlineFrom: 'md', active: filters.instrument !== '' },
      { id: 'search', label: 'Search', inlineFrom: 'md', active: filters.search !== '' },
    ];
  });

  protected readonly strategyKey = (row: StrategyRow): string => row.strategy;
  protected readonly ledgerKey = (row: LedgerRow): string => row.id;

  protected isOn(verdict: string): boolean {
    return this.store.filters().verdicts.includes(verdict);
  }

  protected toggleVerdict(verdict: string): void {
    const current = this.store.filters().verdicts;
    const verdicts = current.includes(verdict)
      ? current.filter((v) => v !== verdict)
      : [...current, verdict];
    this.apply({ verdicts });
  }

  protected setInstrument(instrument: string): void {
    if (instrument !== this.store.filters().instrument) this.apply({ instrument });
  }

  protected setSearch(search: string): void {
    if (search !== this.store.filters().search) this.apply({ search });
  }

  protected verdictTone(verdict: string): ChipTone {
    return VERDICT_TONE[verdict] ?? 'neutral';
  }

  /** WEAK is muted so it is visibly not VALIDATED. The tier text itself is
   *  the server's, verbatim. */
  protected tierTone(status: string): ChipTone {
    return status === 'VALIDATED' ? 'good' : 'muted';
  }

  protected truncate(text: string): string {
    return text.length > HYPOTHESIS_MAX ? `${text.slice(0, HYPOTHESIS_MAX - 1)}…` : text;
  }

  protected figure(value: number | null, digits: number): string {
    return fixed(value, digits) ?? '—';
  }

  protected copy(path: string): void {
    void navigator.clipboard?.writeText(path);
    this.copied.set(path);
  }

  /** The URL is the filter state: the resolver reads it back into the store,
   *  so a reload and a shared link land on the same rows. */
  private apply(patch: Partial<LedgerFilters>): void {
    const next = { ...this.store.filters(), ...patch };
    this.router.navigate([], {
      queryParams: filtersToParams(next), queryParamsHandling: 'merge', replaceUrl: true,
    });
  }
}
