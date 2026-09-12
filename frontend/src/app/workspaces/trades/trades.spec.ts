import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter, Router } from '@angular/router';
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
import { Trades } from './trades';

function row(overrides: Partial<TradeRow>): TradeRow {
  return {
    id: 't1', origin: 'plan', status: 'CLOSED', ticker: 'AAPL',
    direction: 'bullish', strategy: null, horizon: null, tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 100, stop_loss: 95, target: 110, target2: null,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: null, shares: 5, open_shares: null, position_value: null,
    current_price: null, exit_price: 110, realized_pnl_amount: 50,
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

/** Mount Trades directly, with no route matching it. Every route-bound
 *  input (`status`, `outcome`, `direction`, ...) sits at its unset default,
 *  which is what "nothing in the lane is filtered" and "renders the eight
 *  chips" need -- neither reads the URL. */
function render(): ComponentFixture<Trades> {
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
  return fixture;
}

/** The `.chip` inside the control bar's lane whose text trims to `label`. */
function chip(fixture: ComponentFixture<Trades>, label: string): HTMLButtonElement {
  const found = Array.from(
    (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
      'sb-control-bar [filters] .chip',
    ),
  ).find((el) => el.textContent!.trim() === label);
  if (!found) throw new Error(`no chip labelled "${label}"`);
  return found;
}

describe('Trades — the promoted status/outcome/direction lane', () => {
  it('renders the eight promoted chips in the control bar', () => {
    const labels = Array.from(
      (render().nativeElement as HTMLElement).querySelectorAll('sb-control-bar [filters] .chip'),
    ).map((c) => c.textContent!.trim());
    expect(labels).toEqual(['All', 'Open', 'Closed', 'Pending', 'Win', 'Loss', 'Long', 'Short']);
  });

  it('marks All active when nothing in the lane is filtered', () => {
    const el = render().nativeElement as HTMLElement;
    expect(el.querySelector('.chip')!.classList).toContain('active');
  });

  it('keeps the filter bar for the filters the lane does not carry', () => {
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
      'sb-control-bar sb-date-range input.to',
    ) as HTMLInputElement;
    to.value = '2026-04-28';
    to.dispatchEvent(new Event('change'));

    expect(navigateSpy).toHaveBeenCalledWith([], {
      queryParams: { opened_from: null, opened_to: '2026-04-28', page: null },
      queryParamsHandling: 'merge',
    });
  });
});
