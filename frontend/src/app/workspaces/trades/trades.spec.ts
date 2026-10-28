import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter, Router } from '@angular/router';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { TradeRow } from '../../api/models';
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { TradesStore } from '../../stores/trades.store';
import { isInline } from '../../ui/priority';
import { ToolbarControl } from '../../ui/toolbar';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { compactKeys, drawerKeys, openRowDrawer, phoneViewport } from '../../ui/data-table/testing/reachability';
import { LEG_HINT_TEXT } from './leg-label';
import { numText } from './trades.columns';
import { partialOpenTitle } from '../../ui/status-cell';
import { fxMissingText } from '../analytics/scope-bar';
import { ROW_COUNT_NOTE, EXPORT_HINT, Trades, TRADES_CONTROLS } from './trades';

function row(overrides: Partial<TradeRow>): TradeRow {
  return {
    id: 't1', origin: 'plan', status: 'CLOSED', ticker: 'AAPL',
    direction: 'bullish', strategy: null, horizon: null, tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 100, stop_loss: 95, target: 110, target2: null,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: null, shares: 5, open_shares: null, position_value: null,
    current_price: null, current_price_stale: false, exit_price: 110, realized_pnl_amount: 50,
    pnl_pct: 10, r_multiple: 2, held_hours: 1, opened_at: null, closed_at: null,
    has_note: false, today: true, created_at: null, trigger_price: null,
    follow_score: null, progress_pct: null, entry_pct: null, progress_band: null,
    blink_seconds: null, status_label: 'CLOSED', target_is_banked_tp1: false,
    stop_kind: 'risk', bar_kind: 'none', floor_r: null, price_r: null,
    headroom_r: null, distance_to_trigger_r: null, bars_to_expiry: null,
    leg_index: 0, leg_total: 1,
    ...overrides,
  };
}

describe('Trades rowKey', () => {
  it('is unique for two leg-rows sharing one id', () => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(), provideRouter([]),
        provideHttpClient(), provideHttpClientTesting(),
        TradesStore,
      ],
    });
    const f = TestBed.createComponent(Trades);
    const rowKey = (f.componentInstance as unknown as { rowKey: (r: TradeRow) => string }).rowKey;
    const a = row({ leg_index: 0, leg_total: 2 });
    const b = row({ leg_index: 1, leg_total: 2 });
    expect(rowKey(a)).not.toBe(rowKey(b));
  });
});

/* -- v85 D32 -- the promoted status/outcome/direction chip lane ---------- */

/** Trades reads only currency() from ConnectionStore and
 *  values()/isLoaded()/update() from PreferencesStore -- stubbed rather than
 *  let their own onInit hooks issue real HTTP requests this spec does not
 *  care about (same convention as dashboard.spec.ts). */
const connectionStub = { currency: signal('$') };
const preferencesStub = {
  values: signal({}),
  isLoaded: signal(true),
  update: () => undefined,
};

/** R6-05's own footer tests supply the store's answer directly rather than
 *  standing up a real HTTP round trip -- `total`/`page`/`perPage` become the
 *  `TradesStore`'s `data` (what `pagination()` is computed from), and
 *  `activeFilterCount` becomes that many throwaway query filters (the
 *  computed counts keys, not their names, so which keys is arbitrary). */
interface FooterFixture {
  total: number;
  page: number;
  perPage: number;
  activeFilterCount?: number;
}

/** Mount Trades directly, with no route matching it. Every route-bound
 *  input (`status`, `outcome`, `direction`, ...) sits at its unset default,
 *  which is what "nothing in the lane is filtered" and "renders the eight
 *  chips" need -- neither reads the URL. Passing `footer` additionally seeds
 *  the store's pagination for the count-footer tests below; every earlier
 *  call site here omits it and is unaffected. */
function render(footer?: FooterFixture): ComponentFixture<Trades> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      TradesStore,
      { provide: ConnectionStore, useValue: connectionStub },
      { provide: PreferencesStore, useValue: preferencesStub },
    ],
  });
  const fixture = TestBed.createComponent(Trades);
  fixture.detectChanges();
  if (footer) {
    const filterKeys = ['ticker', 'origin', 'strategy', 'horizon', 'tier', 'badge'] as const;
    const filters: Record<string, string> = {};
    for (let i = 0; i < (footer.activeFilterCount ?? 0); i++) filters[filterKeys[i]] = 'x';

    patchState(unprotected(TestBed.inject(TradesStore)), {
      data: {
        items: footer.total > 0 ? [row({})] : [],
        total: footer.total,
        page: footer.page,
        per_page: footer.perPage,
      },
      query: { page: footer.page, per_page: footer.perPage, ...filters },
    });
    fixture.detectChanges();
  }
  return fixture;
}

/** The `.chip` inside the toolbar's status slot whose text trims to `label`.
 *  v95 C1: the lane used to live inside `sb-control-bar [filters]`; it is
 *  now `sb-toolbar`'s `slot="status"` child, always inline (TRADES_CONTROLS),
 *  so it renders whether or not anything is demoted. */
function chip(fixture: ComponentFixture<Trades>, label: string): HTMLButtonElement {
  const found = Array.from(
    (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
      'sb-toolbar [slot=status] .chip',
    ),
  ).find((el) => el.textContent!.trim() === label);
  if (!found) throw new Error(`no chip labelled "${label}"`);
  return found;
}

describe('Trades — the promoted status/outcome/direction lane', () => {
  it('renders the eight promoted chips in the toolbar', () => {
    const labels = Array.from(
      (render().nativeElement as HTMLElement).querySelectorAll('sb-toolbar [slot=status] .chip'),
    ).map((c) => c.textContent!.trim());
    expect(labels).toEqual(['All', 'Open', 'Closed', 'Pending', 'Win', 'Loss', 'Long', 'Short']);
  });

  it('marks All active when nothing in the lane is filtered', () => {
    const el = render().nativeElement as HTMLElement;
    expect(el.querySelector('.chip')!.classList).toContain('active');
  });

  it('keeps a persistent Clear-all summary now that its filters live in the toolbar', () => {
    // v95 C1: sb-filter-bar no longer wraps the eight field filters (they
    // moved into sb-toolbar's sheet) -- it keeps only its own
    // activeCount/Clear-all summary, distinct from the toolbar's own
    // per-control Guard-1 badge.
    expect((render().nativeElement as HTMLElement).querySelector('sb-filter-bar')).not.toBeNull();
  });

  /*
   * These two assert on the real `Router.navigate` call rather than on
   * `TradesStore.query()` after the click. That is a deliberate departure
   * from the task brief's own sketch, which seeds `store.query()` directly
   * and expects the click to merge over it -- the same "setQuery already
   * projects to the URL" assumption R6-02 already found false. The real
   * mechanism (confirmed by reading trades.ts:713-748) is: `navigate()`
   * calls `Router.navigate([], { queryParams, queryParamsHandling: 'merge' })`;
   * the router then updates this component's route-bound input SIGNALS
   * (`status`, `outcome`, `direction`, ...) from the resulting URL; and only
   * THEN does the constructor's effect rebuild the whole `TradeQuery` from
   * every one of those signals and call `store.setQuery()`. Observing a
   * click land in `store.query()` would mean standing up a real route, its
   * resolver, and `PreferencesStore.resolve()` -- exercising the router's
   * input-binding feature, not this chip lane -- and it still wouldn't
   * support the brief's 4th test, whose manually-seeded `strategy: 'RSI'`
   * would be wiped out by that same real rebuild-from-URL rather than
   * preserved, since nothing put `strategy=RSI` in the URL. `navigate()`'s
   * argument is the one real, already-load-bearing seam every existing
   * filter in this file goes through (ticker/origin/strategy/... above), so
   * asserting it directly is the faithful way to verify "this chip drives
   * navigate(), for exactly these keys" without re-testing the router.
   */
  it('sets the status filter when Open is pressed', () => {
    const f = render();
    const navigateSpy = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);

    chip(f, 'Open').click();

    expect(navigateSpy).toHaveBeenCalledWith([], {
      queryParams: { status: 'open', outcome: null, direction: null, page: null },
      queryParamsHandling: 'merge',
    });
  });

  it('clears status, outcome and direction when All is pressed, and nothing else', () => {
    const f = render();
    const navigateSpy = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);

    chip(f, 'All').click();

    expect(navigateSpy).toHaveBeenCalledWith([], {
      queryParams: { status: null, outcome: null, direction: null, page: null },
      queryParamsHandling: 'merge',
    });
    // "Nothing else": the patch does not even mention strategy (or any other
    // filter) -- queryParamsHandling: 'merge' is what leaves it in the URL.
    const [, extras] = navigateSpy.mock.calls[0]!;
    expect(Object.keys(extras!.queryParams as object).sort()).toEqual([
      'direction', 'outcome', 'page', 'status',
    ]);
  });
});

/* -- v85 D32 -- the opened-at range picker's own translation ------------- */

describe('Trades — the opened-at range', () => {
  /*
   * `onDateRange` is not a plain passthrough like the Export CSV link's
   * `href` binding or the column picker's writes into `PreferencesStore` --
   * it translates `sb-date-range`'s `{from, to}` into the query's
   * `opened_from`/`opened_to` keys before handing the patch to `navigate()`.
   * That mapping is exactly the kind of logic `onLaneChip` above already has
   * a test for ("sets the status filter when Open is pressed"), so this
   * follows the same shape: render, spy on `Router.navigate`, dispatch a
   * real `change` event on the mounted native input, assert the exact patch.
   */
  it('translates a date-range change into opened_from/opened_to and navigates', () => {
    const f = render();
    const navigateSpy = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);

    const to = (f.nativeElement as HTMLElement).querySelector(
      'sb-toolbar [slot=dates] input.to',
    ) as HTMLInputElement;
    to.value = '2026-04-28';
    to.dispatchEvent(new Event('change'));

    expect(navigateSpy).toHaveBeenCalledWith([], {
      queryParams: { opened_from: null, opened_to: '2026-04-28', page: null },
      queryParamsHandling: 'merge',
    });
  });
});

/* -- R6-05 -- the count footer ------------------------------------------- */

/*
 * The task brief's own sketch queries a bare `.count` -- but `sb-column-picker`
 * (mounted in the same control bar, unconditionally, above) already owns that
 * exact class name for its own "12/29" visible-columns badge (see
 * `column-picker.ts:59` and `column-picker.spec.ts:169`, which already depends
 * on `.count` meaning that badge). A bare `el.querySelector('.count')` finds
 * THAT node first, since it renders earlier in the DOM than this footer.
 * `p.count` disambiguates on tag (the badge is a `<span>`; this footer is a
 * `<p>`) without touching the shared component. Same kind of brief-vs-reality
 * departure as the lane-chip tests above, and for the same reason: verified
 * by reading the actual render tree rather than assumed from the sketch.
 */
describe('Trades — the count footer', () => {
  it('leaves the non-empty range to the pager, printed once', () => {
    const el = render({ total: 142, page: 1, perPage: 12 }).nativeElement as HTMLElement;
    expect(el.querySelector('p.count')!.textContent).not.toMatch(/\d+–\d+/);
    expect(el.querySelectorAll('.bar .range')).toHaveLength(1);
    expect(el.querySelector('.bar .range')!.textContent).toContain('1–12 of 142');
  });

  it('distinguishes a filter that matched nothing from an empty log', () => {
    const el = render({ total: 0, page: 1, perPage: 12, activeFilterCount: 2 }).nativeElement as HTMLElement;
    expect(el.querySelector('p.count')!.textContent).toContain('No trades match');
  });

  it('says the log is empty when nothing is filtered and there is nothing', () => {
    const el = render({ total: 0, page: 1, perPage: 12, activeFilterCount: 0 }).nativeElement as HTMLElement;
    expect(el.querySelector('p.count')!.textContent).toContain('No trades yet');
  });
});

/* -- v95 C1 -- the toolbar's priorities ----------------------------------- */

describe('Trades toolbar priorities', () => {
  it('declares a floor for every control', () => {
    // A control with no floor is inline everywhere, which is how the 1700px
    // stack happened. Requiring the declaration makes the choice deliberate.
    expect(TRADES_CONTROLS.every((c) => c.inlineFrom !== undefined)).toBe(true);
  });

  it('keeps the status filter and the column picker inline on a phone', () => {
    const inlineAtXs = TRADES_CONTROLS.filter((c) => c.inlineFrom === 'xs').map((c) => c.id);
    expect(inlineAtXs).toEqual(expect.arrayContaining(['status', 'columns']));
  });

  it('demotes the eight field filters and the date range below md', () => {
    const demoted = ['ticker', 'origin', 'strategy', 'horizon', 'confidence', 'tier', 'badge', 'note', 'dates'];
    for (const id of demoted) {
      const control = TRADES_CONTROLS.find((c) => c.id === id);
      expect(control, `missing control ${id}`).toBeDefined();
      expect(isInline(control!.inlineFrom, 'sm')).toBe(false);
      expect(isInline(control!.inlineFrom, 'md')).toBe(true);
    }
  });

  it('reports a filter as active when it is not at its default', () => {
    // Guard 1: a hidden filter that is narrowing the table must be counted.
    const f = render();
    f.componentRef.setInput('ticker', 'AAPL');
    f.detectChanges();
    const controls = (f.componentInstance as unknown as {
      toolbarControls: () => ToolbarControl[];
    }).toolbarControls();
    expect(controls.find((c) => c.id === 'ticker')!.active).toBe(true);
  });

  it('leaves a filter at its default unmarked', () => {
    const f = render();
    const controls = (f.componentInstance as unknown as {
      toolbarControls: () => ToolbarControl[];
    }).toolbarControls();
    expect(controls.find((c) => c.id === 'ticker')!.active).toBe(false);
    // columns/density/export/clear-* are not filters and report no state.
    expect(controls.find((c) => c.id === 'columns')!.active).toBe(false);
  });
});

/* -- v177: the Plan cell's runner forms on the Trades page -------------- */

/** The RKLB plan as V177-1 serves it: the realized TP1 leg (a CLOSED row
 *  of a still-PARTIAL plan), the open runner, and a second plan whose
 *  runner has closed. */
const RUNNER_ROWS: TradeRow[] = [
  row({ id: 'p1', status: 'CLOSED', direction: 'bearish', entry: 60.67,
        stop_loss: 52.437, target: null, target_is_banked_tp1: true,
        stop_kind: 'trailing', bar_kind: 'trailing', exit_price: 58.33,
        risk_stop: 61.85, runner_best: 49.94, tp1: null, best_pnl_pct: null,
        stop_pnl_pct: null, runner_exit_price: null, runner_exit_reason: null,
        leg_index: 0, leg_total: 2 }),
  row({ id: 'p1', status: 'PARTIAL', status_label: 'PARTIAL', direction: 'bearish',
        entry: 60.67, stop_loss: 52.437, target: null, target_is_banked_tp1: true,
        stop_kind: 'trailing', bar_kind: 'trailing', banked_fraction: 0.5,
        banked_exit_price: 58.33, banked_r: 1.98, exit_price: null,
        risk_stop: 61.85, runner_best: 49.94, tp1: 58.33,
        best_pnl_pct: 17.69, stop_pnl_pct: 13.57, leg_index: 1, leg_total: 2 }),
  row({ id: 'c1', status: 'CLOSED', direction: 'bearish', entry: 60.67,
        stop_loss: 61.85, target: 58.33, exit_price: 52.44, tp1: null,
        runner_exit_price: 52.44, runner_exit_reason: 'tp1_runner_trail',
        leg_index: 1, leg_total: 2 }),
];

/** Trades with `items` in its store, the way the footer tests seed it. */
function renderRows(items: TradeRow[]): HTMLElement {
  const fixture = render();
  patchState(unprotected(TestBed.inject(TradesStore)), {
    data: { items, total: items.length, page: 1, per_page: 12 },
    query: { page: 1, per_page: 12 },
  });
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const cellText = (el: Element): string => el.textContent!.replace(/\s+/g, ' ').trim();

describe('Trades — the Plan cell for runners (v177)', () => {
  it('renders one Plan cell per row', () => {
    expect(renderRows(RUNNER_ROWS).querySelectorAll('sb-plan-cell')).toHaveLength(3);
  });

  it('keeps today\'s single-line cell on the TP1-leg row of a still-PARTIAL plan', () => {
    const [leg] = renderRows(RUNNER_ROWS).querySelectorAll('sb-plan-cell');
    expect(leg.querySelector('.runner')).toBeNull();
    expect(leg.querySelector('.line')).toBeNull();
  });

  it('reads the open runner on two lines', () => {
    const runner = renderRows(RUNNER_ROWS).querySelectorAll('sb-plan-cell')[1];
    expect(cellText(runner.querySelector('.l1')!)).toBe('60.67 → 58.33 / 61.85 (3.9% - 1.9%)');
    expect(cellText(runner.querySelector('.l2')!)).toBe('Trail 49.94 → 52.44 (+17.7% / +13.6%)');
  });

  it('shows the closed runner\'s exit in the target slot', () => {
    const closed = renderRows(RUNNER_ROWS).querySelectorAll('sb-plan-cell')[2];
    expect(cellText(closed)).toBe('60.67 → 52.44 / 61.85 (+13.6% - 1.9%)');
    expect(closed.querySelector('[title]')!.getAttribute('title'))
      .toContain('Runner exit (trailing stop): 52.44');
  });
});

/* -- v179 §3.1 -- Trades on a phone: compact rows and the row drawer ------ */

function renderPhone(items: TradeRow[]): ComponentFixture<Trades> {
  installDialogPolyfill();
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      TradesStore,
      { provide: ConnectionStore, useValue: connectionStub },
      { provide: PreferencesStore, useValue: preferencesStub },
      phoneViewport(),
    ],
  });
  const fixture = TestBed.createComponent(Trades);
  fixture.detectChanges();
  patchState(unprotected(TestBed.inject(TradesStore)), {
    data: { items, total: items.length, page: 1, per_page: 20 },
    query: { page: 1, per_page: 20 },
  });
  fixture.detectChanges();
  return fixture;
}

const tradesTable = (fixture: ComponentFixture<Trades>) =>
  (fixture.nativeElement as HTMLElement).querySelector('sb-data-table') as HTMLElement;

describe('Trades on a phone (v179 §3.1)', () => {
  it('reaches every visible column between the compact row and the drawer (§7.5)', () => {
    const fixture = renderPhone([row({})]);
    openRowDrawer(tradesTable(fixture));
    fixture.detectChanges();
    const shown = (fixture.componentInstance as unknown as { visible: () => string[] }).visible();
    expect([...compactKeys(tradesTable(fixture)), ...drawerKeys(tradesTable(fixture))].sort()).toEqual([...shown].sort());
  });

  it('keeps the P&L amount and the stop on the compact row (money floor)', () => {
    const table = tradesTable(renderPhone([row({ realized_pnl_amount: 50, stop_loss: 95 })]));
    expect(table.querySelector('.line1 > [data-col="pnl_pct"]')!.textContent).toContain('50.00');
    expect(table.querySelector('.line2 > [data-col="plan"] .stop')!.textContent).toContain('95.00');
  });

  it('shows a PENDING row with no fill as em dashes, never NaN, undefined or an empty line', () => {
    const pending = row({
      id: 'p1', status: 'PENDING', status_label: 'PENDING', entry: null, stop_loss: null, target: null,
      exit_price: null, pnl_pct: null, realized_pnl_amount: null, r_multiple: null, shares: null, trigger_price: 101,
    });
    const compactRow = tradesTable(renderPhone([pending])).querySelector('li.compact-row')!;
    expect(compactRow.textContent).not.toMatch(/NaN|undefined|null/);
    for (const line of compactRow.querySelectorAll('.line1, .line2')) expect(line.textContent!.trim()).not.toBe('');
    expect(compactRow.querySelector('[data-col="pnl_pct"]')!.textContent).toContain('—');
  });

  it('links the drawer to the full trade page and does not navigate on the tap', () => {
    const fixture = renderPhone([row({ id: 't9' })]);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate');
    openRowDrawer(tradesTable(fixture));
    fixture.detectChanges();
    const link = tradesTable(fixture).querySelector('a.drawer-detail-link')!;
    expect(link.textContent!.trim()).toBe('Open full trade →');
    expect(link.getAttribute('href')).toBe('/trades/t9');
    expect(navigate).not.toHaveBeenCalled();
  });
});


describe('Trades page-size URL precedence (v194 B2)', () => {
  afterEach(() => preferencesStub.values.set({}));

  const cases = [
    { name: 'URL All over the default', raw: '0', saved: 10, api: 200, choice: '0', range: '1–200 of 1272 (capped)' },
    { name: 'URL 50 over saved All', raw: '50', saved: 0, api: 50, choice: '50', range: '1–50 of 1272' },
    { name: 'saved choice for an invalid URL', raw: '7', saved: 20, api: 20, choice: '20', range: '1–20 of 1272' },
    { name: 'saved All when the URL is absent', raw: undefined, saved: 0, api: 200, choice: '0', range: '1–200 of 1272 (capped)' },
  ];

  for (const testCase of cases) {
    it(`shows and queries ${testCase.name}`, () => {
      preferencesStub.values.set({ 'tables.trades.desktop.per_page': testCase.saved });
      const fixture = render({ total: 1272, page: 1, perPage: testCase.api });
      if (testCase.raw !== undefined) fixture.componentRef.setInput('per_page', testCase.raw);
      fixture.detectChanges();
      const root = fixture.nativeElement as HTMLElement;
      const rows = root.querySelector<HTMLSelectElement>('sb-pagination select[aria-label="Rows per page"]')!;
      expect(rows.value).toBe(testCase.choice);
      expect(root.querySelector('sb-pagination .range')!.textContent).toBe(testCase.range);
      expect(TestBed.inject(TradesStore).query().per_page).toBe(testCase.api);
    });
  }
});

/* -- v194 B3 -- leg rows say which part of the plan they are ------------- */

/** Mount Trades with `items` as the loaded page, in full density so the
 *  `#` column (and its `#numCell` template) is inline at jsdom's width. */
function renderLegRows(items: TradeRow[]): HTMLElement {
  const fixture = render();
  (fixture.componentInstance as unknown as { setDensity(d: 'full' | 'compact'): void }).setDensity('full');
  patchState(unprotected(TestBed.inject(TradesStore)), {
    data: { items, total: items.length, page: 1, per_page: 50 },
    query: { page: 1, per_page: 50 },
  });
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('Trades — leg rows (v194 B3)', () => {
  it('labels both legs of a two-leg plan with their exit reason', () => {
    const el = renderLegRows([
      row({ id: 'plan-aaaaaa', leg_index: 0, leg_total: 2, leg_exit_reason: 'tp1' }),
      row({ id: 'plan-aaaaaa', leg_index: 1, leg_total: 2, leg_exit_reason: 'stop' }),
    ]);
    const labels = [...el.querySelectorAll('.leg')].map((n) => n.firstChild!.textContent!.trim());
    expect(labels[0]).toMatch(/^Leg 1 of 2 · /);
    expect(labels[1]).toMatch(/^Leg 2 of 2 · /);
  });

  it('labels a leg with no recorded reason by its position alone', () => {
    const el = renderLegRows([row({ leg_index: 2, leg_total: 3, leg_exit_reason: null })]);
    expect(el.querySelector('.leg')!.firstChild!.textContent!.trim()).toBe('Leg 3 of 3');
  });

  it('shows no label and no leg hint on a single-leg trade', () => {
    const el = renderLegRows([row({ leg_index: 0, leg_total: 1 })]);
    expect(el.querySelector('.leg')).toBeNull();
    expect(el.querySelector('.leg sb-hint')).toBeNull();
  });

  it('puts an sb-hint naming plans-not-legs on every leg row, in place of the old icon', () => {
    const el = renderLegRows([
      row({ leg_index: 0, leg_total: 2 }),
      row({ leg_index: 1, leg_total: 2 }),
    ]);
    const hints = [...el.querySelectorAll('.leg sb-hint')];
    expect(hints).toHaveLength(2);
    expect(hints[0].textContent).toContain(LEG_HINT_TEXT);
    expect(hints[0].textContent).toContain('count plans on Analytics');   // A4 audit
    expect(hints[0].textContent).not.toContain('plans, not legs');
    expect(el.querySelector('[title="Closed after an earlier partial exit of the same position"]')).toBeNull();
  });

  it('carries the label into the expansion the phone drawer reuses', () => {
    const el = renderLegRows([row({ leg_index: 1, leg_total: 2, leg_exit_reason: 'stop' })]);
    // numText is what the drawer's "Hidden in this view" list prints for the
    // `#` column whenever that column is not inline.
    expect(numText(row({ id: 'plan-123456', leg_index: 1, leg_total: 2, leg_exit_reason: null })))
      .toBe('123456 · Leg 2 of 2');
    expect(el.querySelector('.leg')).not.toBeNull();
  });
});

describe('numText', () => {
  it('is the short id alone for a single-leg trade', () => {
    expect(numText(row({ id: 'abcdefghij', leg_total: 1 }))).toBe('efghij');
  });

  it('keeps a short id whole', () => {
    expect(numText(row({ id: 't1', leg_total: 1 }))).toBe('t1');
  });
});

describe('Trades — the total counts rows, not plans (v194 B3)', () => {
  it('says so under a non-empty table, and the pager still prints the range once', () => {
    const el = render({ total: 142, page: 1, perPage: 12 }).nativeElement as HTMLElement;
    expect(el.querySelector('p.count')!.textContent!.trim()).toBe(ROW_COUNT_NOTE);
    expect(el.querySelectorAll('.bar .range')).toHaveLength(1);
  });

  it('announces rows, not trades', () => {
    const fixture = render({ total: 3, page: 1, perPage: 12 });
    const announce = (fixture.componentInstance as unknown as { announce: () => string | null }).announce;
    expect(announce()).toBe('3 rows');
  });
});

describe('Trades — missing FX rate caveat (v194 B7)', () => {
  it('names how many rows on the page have no rate', () => {
    const el = renderLegRows([
      row({ id: 'a', fx_missing: true, realized_pnl_amount: null }),
      row({ id: 'b', fx_missing: true, realized_pnl_amount: null }),
      row({ id: 'c', fx_missing: false }),
    ]);
    expect(el.querySelector('.fx-caveat')!.textContent!.trim()).toBe(fxMissingText(2));
  });

  it('is absent when every row converted', () => {
    const el = renderLegRows([row({ fx_missing: false }), row({ id: 'b' })]);
    expect(el.querySelector('.fx-caveat')).toBeNull();
  });
});

describe('Trades — explanations are hints, not titles (v194 A3)', () => {
  it('says the export ignores the filters, in a hint beside the link', () => {
    const el = render().nativeElement as HTMLElement;
    expect(el.querySelector('a.export')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('.export-wrap sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(EXPORT_HINT);
  });

  it('explains a partly closed position in a hint outside the row link', () => {
    const r = row({ status: 'PARTIAL', status_label: 'PARTIAL', banked_fraction: 0.25, exit_price: null });
    const el = renderRows([r]);
    expect(el.querySelector('sb-row-link sb-hint')).toBeNull();
    const texts = [...el.querySelectorAll('sb-hint [role="tooltip"]')].map((n) => n.textContent!.trim());
    expect(texts).toContain(partialOpenTitle(r)!);
  });
});
