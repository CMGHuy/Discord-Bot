import { provideZonelessChangeDetection, signal, WritableSignal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AnalyticsStrategies } from '../../../api/models';
import { AnalyticsStore, GridRow, JobStatus, JobSummary, ProposalRow } from '../../../stores/analytics.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { installDialogPolyfill } from '../../../testing/dialog-polyfill';
import { TuningTab } from './tuning';

// ConfirmDialog is a real <dialog>; jsdom has no showModal()/close(). See the
// polyfill for why <dialog> stays.
installDialogPolyfill();

function strategies(names: string[]): AnalyticsStrategies {
  return {
    strategies: [],
    registry_scope: 'all-time',
    contribution: names.map((strategy) => ({ strategy, total_r: 1, n: 40 })),
    cumulative: {},
    scope: {} as never,
    n: names.length,
  };
}

function gridRow(overrides: Partial<GridRow> = {}): GridRow {
  return {
    row_index: 0,
    params: { rsi_period: 14 },
    paramLabel: 'rsi_period=14',
    n_eval: 40,
    win_rate: 82,
    expectancy_r: 0.3,
    excluded_share: 0.1,
    passes: true,
    ...overrides,
  };
}

function proposalRow(overrides: Partial<ProposalRow> = {}): ProposalRow {
  return {
    filename: 'rsi-1.json',
    strategy: 'RSI',
    created_at: '2026-09-01T12:00:00Z',
    job_id: 'job-1',
    proposed_params: { rsi_period: 21 },
    current_params: { rsi_period: 14 },
    train_stats: { n_eval: 40, win_rate: 82, expectancy_r: 0.3 },
    ...overrides,
  };
}

interface StoreStub {
  strategies: WritableSignal<AnalyticsStrategies | null>;
  jobActive: WritableSignal<boolean>;
  launching: WritableSignal<boolean>;
  launchError: WritableSignal<string | null>;
  job: WritableSignal<JobStatus | null>;
  grid: WritableSignal<GridRow[]>;
  gridStrategy: WritableSignal<string | null>;
  proposeResult: WritableSignal<string | null>;
  proposeError: WritableSignal<string | null>;
  proposing: WritableSignal<number | null>;
  pastJobs: WritableSignal<JobSummary[]>;
  proposals: WritableSignal<ProposalRow[]>;
  startTune: ReturnType<typeof vi.fn>;
  propose: ReturnType<typeof vi.fn>;
  removeProposal: ReturnType<typeof vi.fn>;
}

function storeStub(overrides: Partial<Record<keyof StoreStub, unknown>> = {}): StoreStub {
  return {
    strategies: signal(strategies(['RSI', 'MACD'])),
    jobActive: signal(false),
    launching: signal(false),
    launchError: signal(null),
    job: signal(null),
    grid: signal([]),
    gridStrategy: signal(null),
    proposeResult: signal(null),
    proposeError: signal(null),
    proposing: signal(null),
    pastJobs: signal([]),
    proposals: signal([]),
    startTune: vi.fn(),
    propose: vi.fn(),
    removeProposal: vi.fn(),
    ...overrides,
  } as StoreStub;
}

function render(store: StoreStub) {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: AnalyticsStore, useValue: store },
      { provide: PreferencesStore, useValue: { values: () => ({}), update: () => undefined } },
    ],
  });
  const fixture = TestBed.createComponent(TuningTab);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('TuningTab', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('offers every strategy with contribution history in the launcher, in the server\'s contribution-magnitude order, and disables Launch until one is picked', () => {
    // RSI before MACD -- alphabetically backwards -- so this also proves the
    // picker does not re-sort what `/analytics/strategies` already ordered.
    const { el } = render(storeStub());
    const options = [...el.querySelectorAll('sb-select option')].map((o) => o.textContent!.trim());
    expect(options).toEqual(['Pick a strategy', 'RSI', 'MACD']);
    const launch = [...el.querySelectorAll('button')].find((b) => b.textContent!.includes('Launch TRAIN grid'))!;
    expect(launch.disabled).toBe(true);
  });

  it('launches the picked strategy and hides the form while a job is queued or running', () => {
    const store = storeStub();
    const { fixture, el } = render(store);
    const select = el.querySelector<HTMLSelectElement>('sb-select select')!;
    select.value = 'RSI';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    const launch = [...el.querySelectorAll('button')].find((b) => b.textContent!.includes('Launch TRAIN grid'))!;
    expect(launch.disabled).toBe(false);
    launch.click();
    expect(store.startTune).toHaveBeenCalledWith('RSI');

    store.jobActive.set(true);
    fixture.detectChanges();
    expect(el.querySelector('sb-select')).toBeNull();
    expect(el.textContent).toContain('A job is running.');
  });

  it('surfaces a launch error without touching the form state', () => {
    const store = storeStub({ launchError: signal('startTune failed: 409') });
    const { el } = render(store);
    expect(el.querySelector('.alert')?.textContent).toContain('startTune failed: 409');
  });

  /** The tuning page used to poll with a 3s `setTimeout` + reload; the store
   *  now updates `job` purely off the server's `jobs` event. This proves the
   *  component reflects that signal the instant it changes -- no timer of any
   *  length has to elapse for the log tail to update. */
  it('renders job progress the instant the jobs-event-driven signal changes, never a timer', () => {
    vi.useFakeTimers();
    try {
      const store = storeStub();
      const { fixture, el } = render(store);
      expect(el.querySelector('.log')).toBeNull();

      store.job.set({
        id: 'job-9', kind: 'tune', state: 'running', started_at: '2026-09-01T10:00:00Z',
        finished_at: null, returncode: null, log_tail: 'evaluating combo 4/50',
      });
      fixture.detectChanges();

      expect(el.querySelector('.log')!.textContent).toContain('evaluating combo 4/50');
      expect(el.textContent).toContain('Progress arrives on the');
    } finally {
      vi.useRealTimers();
    }
  });

  it('labels a failed job with its exit code', () => {
    const store = storeStub({
      job: signal({
        id: 'job-2', kind: 'tune', state: 'failed', started_at: '2026-09-01T10:00:00Z',
        finished_at: '2026-09-01T10:05:00Z', returncode: 1, log_tail: 'Traceback...',
      }),
    });
    const { el } = render(store);
    expect(el.querySelector('sb-chip')?.textContent).toContain('FAILED (exit 1)');
  });

  it('shows no grid panel until a grid exists', () => {
    const { el } = render(storeStub());
    expect(el.textContent).not.toContain('Grid results');
  });

  it('heads the grid panel with the strategy that produced it once a grid exists', () => {
    const { el } = render(storeStub({ grid: signal([gridRow()]), gridStrategy: signal('RSI') }));
    expect(el.textContent).toContain('Grid results — RSI');
    expect(el.querySelector('sb-data-table')).not.toBeNull();
  });

  it('stages a proposal only after the confirm dialog is accepted', () => {
    const store = storeStub({ grid: signal([gridRow({ row_index: 3 })]), gridStrategy: signal('RSI') });
    const { fixture, el } = render(store);

    const proposeButton = [...el.querySelectorAll('button')].find((b) => b.textContent!.trim() === 'Propose')!;
    proposeButton.click();
    fixture.detectChanges();

    const dialogs = el.querySelectorAll<HTMLDialogElement>('sb-confirm-dialog dialog');
    expect(dialogs[1].open).toBe(true);
    expect(dialogs[1].textContent).toContain('rsi_period=14');
    expect(store.propose).not.toHaveBeenCalled();

    [...dialogs[1].querySelectorAll('button')].at(-1)!.click();
    expect(store.propose).toHaveBeenCalledWith(3);
  });

  it('names what a delete removes before it removes it', () => {
    const store = storeStub({ proposals: signal([proposalRow({ filename: 'rsi-2.json', strategy: 'RSI' })]) });
    const { fixture, el } = render(store);

    const deleteButton = [...el.querySelectorAll('button')].find((b) => b.textContent!.trim() === 'Delete')!;
    deleteButton.click();
    fixture.detectChanges();

    const dialogs = el.querySelectorAll<HTMLDialogElement>('sb-confirm-dialog dialog');
    expect(dialogs[0].open).toBe(true);
    expect(dialogs[0].textContent).toContain('Removes the staged RSI proposal from disk.');

    [...dialogs[0].querySelectorAll('button')].at(-1)!.click();
    expect(store.removeProposal).toHaveBeenCalledWith('rsi-2.json');
  });

  it('renders the parameter diff and the TRAIN summary for each proposal', () => {
    const { el } = render(storeStub({ proposals: signal([proposalRow()]) }));
    expect(el.querySelector('.diff')!.textContent).toContain('rsi_period');
    expect(el.textContent).toContain('TRAIN: N=40 · WR=');
  });

  it('says plainly that there are no proposals yet, rather than an empty table', () => {
    const { el } = render(storeStub());
    expect(el.textContent).toContain('No proposals yet.');
  });

  it('is not scoped -- no N badge and no all-time badge on its panel headers', () => {
    const { el } = render(storeStub({ grid: signal([gridRow()]) }));
    expect(el.querySelector('.n')).toBeNull();
    expect(el.querySelector('.all-time')).toBeNull();
  });
});
