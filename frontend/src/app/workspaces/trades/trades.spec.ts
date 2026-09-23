import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter, Router } from '@angular/router';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { describe, expect, it, vi } from 'vitest';

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
import { Trades, TRADES_CONTROLS } from './trades';

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
    expect(el.querySelector('p.count')).toBeNull();
    expect(el.querySelectorAll('.pager .range')).toHaveLength(1);
    expect(el.querySelector('.pager .range')!.textContent).toContain('1–12 of 142');
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
