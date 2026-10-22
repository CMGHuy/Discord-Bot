import { computed, effect, inject, untracked } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { EventStream } from '../api/event-stream';
import { Observable, Subject, debounceTime, defer } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { routeRequest } from '../routing/route-request';
import { Dashboard, DashboardScope } from '../api/models';
import { readScopePreset, writeScopePreset } from '../ui/equity-chart-prefs';
import {
  ChartTarget,
  ScopePreset,
  ScopeSelection,
  TimeWindow,
  chartWindowFor,
  scopeToRequest,
} from '../workspaces/dashboard/panels/equity-range.model';
import { PreferencesStore } from './preferences.store';

interface DashboardSlice {
  data: Dashboard | null;
  loading: boolean;
  error: string | null;
  /** SR58, reshaped by v181 -- what the panel is scoped to: a preset (1D,
   *  5D … All) or a Range the partner dragged or zoomed to. A fetch input,
   *  so it lives here: the server does the date filtering. `scope` is
   *  derived from it. */
  selection: ScopeSelection;
  /** The window the latest request was sent with (null for 1D and All). The
   *  Closed tab reads it through `closedWindow`, so the table under the KPI
   *  cards always asks for the window the cards were asked for. */
  requestWindow: TimeWindow | null;
  /** A refetch failed while figures were on screen: they are kept, dimmed,
   *  with a stale hint (spec v181 § 9). Never set by a failed first load. */
  stale: boolean;
  /** Bumped on every programmatic chart move (a preset click, a restored
   *  preset); the chart moves when it changes. 0 = nothing asked yet. */
  targetSeq: number;
}

/** How long a pan or zoom must settle before the KPIs refetch (spec § 8). */
export const RANGE_DEBOUNCE_MS = 300;

const NOT_RESPONDING = 'The admin is not responding.';

function sameWindow(selection: ScopeSelection, window: TimeWindow): boolean {
  return selection.kind === 'range'
    && selection.window.from === window.from && selection.window.to === window.to;
}

function isPreset(selection: ScopeSelection, preset: ScopePreset): boolean {
  return selection.kind === 'preset' && selection.preset === preset;
}

function failure(hadData: boolean, error: ApiError): Partial<DashboardSlice> {
  return {
    loading: false,
    stale: hadData,
    error: error.code === 'unavailable' ? NOT_RESPONDING : error.message,
  };
}

/**
 * Pulls one finite number out of a loosely typed server bag.
 *
 * Two of the Dashboard's fields are `unknown[]` / `Record<string, unknown>` in
 * `models.ts` on purpose: their shape is decided by the Python side
 * (`build_sizing_note`, the equity snapshot) and pinning a TypeScript
 * interface to it would make every backend tweak a compile error in the
 * client. The cost is that the narrowing has to happen somewhere, and the
 * store is the right somewhere -- a template that did it would be asserting a
 * wire format, and a component that trusted the `unknown` blindly would print
 * `[object Object]` the first time the backend renamed a key.
 *
 * Anything that is not a finite number becomes `null` rather than `0`: a
 * metric that failed to arrive is not a metric that is zero, which is the rule
 * running through `ui/format.ts` and every card on this screen.
 */
function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * The Dashboard's nine metrics.
 *
 * **This is the reference shape.** Every workspace store in Phase 4 copies
 * it: `withState` for what the server said, `withComputed` for anything
 * derived, `withMethods` for the one `load()`, and a `withHooks` effect that
 * turns the relevant events into refetches. Read this one before writing
 * another.
 *
 * Three properties are the point, and each is easy to lose:
 *
 * **It holds one server response and derives everything else.** No merging,
 * no accumulating, no local edits. An event means refetch, so a store that
 * merged would be a second copy of the server's data, slowly diverging --
 * the failure mode spec v13 Decision 3 exists to prevent.
 *
 * **The first effect run IS the initial load.** There is no separate
 * bootstrap call, so the load path and the refetch path cannot drift apart
 * -- a class of bug where the screen is right on arrival and wrong after an
 * update, or vice versa.
 *
 * **A refetch failure keeps the previous data on screen.** Replacing nine
 * live numbers with an error panel because one poll failed is worse than
 * showing slightly stale numbers next to a warning, especially when the
 * event stream reconnects seconds later.
 */
export const DashboardStore = signalStore(
  withState<DashboardSlice>({
    // 'active' ("Today + open") and 'today' were merged into one Today
    // toggle -- the server already treated them identically for the
    // realised figures, and Today's own definition now folds in "or still
    // open, however old" (see Trades' `today` filter), so a separate
    // "+ open" mode has nothing left to add. 'active' stays a valid value
    // the server accepts, for any link that still names it.
    // v181: 'today' is now the 1D preset, 'all' the All preset.
    data: null, loading: false, error: null,
    selection: { kind: 'preset', preset: '1D' },
    requestWindow: null, stale: false, targetSeq: 0,
  }),
  withComputed(({ data, selection, requestWindow, targetSeq }) => ({
    /** True until the first response, and never again. Distinguishes "no
     *  data yet" from "a refetch is in flight", which want different UI:
     *  a skeleton once, and nothing at all thereafter. */
    empty: computed(() => data() === null),

    /* -- v181: the scope selection ---------------------------------------- */

    /** The `/dashboard` mode the selection maps to: 1D -> `today`, All ->
     *  `all`, every other preset and a Range -> `range`. */
    scope: computed<DashboardScope>(() => scopeToRequest(selection(), new Date()).mode),

    /** The chosen preset, or null under a hand-picked Range. */
    preset: computed<ScopePreset | null>(() => {
      const current = selection();
      return current.kind === 'preset' ? current.preset : null;
    }),

    /** The Closed tab's window: the latest KPI request's (null for 1D/All,
     *  where the tab keeps its `today` flag or no filter). */
    closedWindow: computed(() => requestWindow()),

    /** Where the chart should move, and a sequence number that changes only
     *  for a programmatic move. Under a Range the window is the Range itself
     *  and `seq` does not move, so a hand pan never moves the chart back. */
    chartTarget: computed<ChartTarget>(() => {
      const current = selection();
      const window = current.kind === 'preset'
        ? chartWindowFor(current.preset, new Date())
        : current.window;
      return { window, seq: targetSeq() };
    }),

    balance: computed(() => data()?.account_balance ?? null),
    openPnlPct: computed(() => data()?.open_pnl_pct ?? null),
    openPnlAmount: computed(() => data()?.open_pnl_amount ?? null),
    riskUsedPct: computed(() => data()?.risk_used_pct ?? null),
    riskCapPct: computed(() => data()?.risk_cap_pct ?? null),

    openTrades: computed(() => data()?.open_trades ?? 0),

    /* -- SR58: realised P&L over the scoped closes -------------------- */

    /** The scope the SERVER applied, not the one we asked for. If the two
     *  ever disagree the parameter silently did not take, which is exactly
     *  what this echo exists to make visible. */
    appliedScope: computed(() => data()?.scope?.mode ?? null),

    realizedAmount: computed(() => data()?.realized?.amount ?? null),
    realizedPct: computed(() => data()?.realized?.pct ?? null),
    realizedCount: computed(() => data()?.realized?.n ?? 0),
    realizedWins: computed(() => data()?.realized?.wins ?? 0),
    realizedLosses: computed(() => data()?.realized?.losses ?? 0),
    avgConfidence: computed(() => data()?.avg_confidence ?? null),
    winRate: computed(() => data()?.win_rate ?? null),
    expectancyR: computed(() => data()?.expectancy_r ?? null),
    payoffRatio: computed(() => data()?.payoff_ratio ?? null),
    winRateN: computed(() => data()?.win_rate_n ?? null),
    expectancyN: computed(() => data()?.expectancy_n ?? null),
    equity30d: computed(() => data()?.equity_30d ?? null),

    /** The 30 balance points, as numbers the `Sparkline` can draw.
     *
     *  Non-numbers are dropped rather than coerced: a `null` balance in the
     *  middle of the series would become 0 under `Number()` and draw a spike
     *  to the floor that never happened. The server already ships at most 30
     *  points, so there is no cap to apply here. */
    equityPoints: computed<readonly number[]>(() => {
      const points = data()?.equity_30d?.points ?? [];
      return points
        .map(finiteNumber)
        .filter((point): point is number => point !== null);
    }),

    /** The window's percentage change, which is the number the sparkline is
     *  labelled with. P&L direction, so it is one of the few figures allowed
     *  to be green or red. */
    equityChangePct: computed(() => data()?.equity_30d?.change_pct ?? null),

    /**
     * "What does one trade cost right now", in dollars.
     *
     * The server answers this in two shapes because sizing has two modes. In
     * `account_pct` there is a single fixed premium per trade. In `risk_pct`
     * (the default) there is no fixed premium at all -- position value varies
     * with how far the stop sits, up to the max-position cap -- so the cap is
     * the only single number that is true, and `positionPremiumIsCap` exists
     * so the chip can say "max" rather than quietly presenting a ceiling as
     * a typical cost.
     */
    positionPremium: computed(() => {
      const premium = data()?.position_premium;
      if (!premium) return null;
      return premium['mode'] === 'account_pct'
        ? finiteNumber(premium['premium'])
        : finiteNumber(premium['max_position']);
    }),

    positionPremiumIsCap: computed(() => data()?.position_premium?.['mode'] === 'risk_pct'),

    /** SR59 -- the raw sizing note, for the workspace to write its
     *  explanation from. Exposed rather than formatted here: the sentence is
     *  copy and belongs with the other copy, and this store already refuses
     *  to hold presentation. */
    sizingNote: computed(() => data()?.position_premium ?? null),

    /**
     * The five plan-lifecycle counts — SR53.
     *
     * The Jinja dashboard had these as a strip of clickable cards; the SPA had
     * the status chips they navigated to, with no numbers on them. A chip that
     * says "Pending" and a chip that says "Pending 4" answer different
     * questions, and the second is the one worth landing on.
     *
     * Rendered in lifecycle order rather than by size: PENDING → ACTIVE →
     * PARTIAL → CLOSED → CANCELLED is the order a plan moves through, and
     * sorting by count would reshuffle the row every time a trade closed.
     *
     * A count of zero is kept, not dropped. "No pending plans" is information;
     * a strip that shed its empty entries would change width as the session
     * went on.
     */
    lifecycle: computed<{ status: string; count: number }[]>(() => {
      const raw = data()?.lifecycle;
      // An EMPTY object, not just a missing one. `_lifecycle_counts` returns
      // {} rather than raising, because the Dashboard is the landing page and
      // one degraded panel beats a 500 for the other nine figures — so {} has
      // to mean "no strip". Rendering five zeros for it would be a claim about
      // the account rather than an admission the counts are unavailable.
      if (!raw || Object.keys(raw).length === 0) return [];
      return ['PENDING', 'ACTIVE', 'PARTIAL', 'CLOSED', 'CANCELLED'].map((status) => ({
        status,
        count: finiteNumber(raw[status]) ?? 0,
      }));
    }),

    /** The plan-lifecycle diagram's "Expires" definition names this number.
     *  Null while loading rather than falling back to a guess -- a wrong
     *  number in the legend is worse than a blank line for a beat. */
    defaultExpiryBars: computed(() => data()?.default_expiry_bars ?? null),

    /** Risk used as a fraction of the cap, for a meter. Null rather than 0
     *  when either side is missing: an empty meter and a meter at zero look
     *  identical and mean opposite things. */
    riskUtilisation: computed(() => {
      const used = data()?.risk_used_pct;
      const cap = data()?.risk_cap_pct;
      if (used == null || cap == null || cap === 0) return null;
      return used / cap;
    }),
  })),
  withMethods((store, api = inject(ApiClient), prefs = inject(PreferencesStore)) => {
    let latestRequest = 0;
    // Bumped by a preset click, so a Range still inside its debounce never
    // lands on top of the preset the partner chose after it.
    let rangeGeneration = 0;
    let chosen = false;
    const ranges = new Subject<{ window: TimeWindow; generation: number }>();

    // `defer`: the request number and the window are taken when the route
    // resolver or a method subscribes. `untracked`: `load()` runs inside the
    // onInit effect, and a tracked read would refetch on every selection
    // change on top of the method's own refetch.
    const resolve = (): Observable<void> => defer(() => {
      const request = ++latestRequest;
      const current = (): boolean => request === latestRequest;
      const { mode, window } = scopeToRequest(untracked(() => store.selection()), new Date());
      return routeRequest(api.dashboard(mode, window), {
        start: () => patchState(store, { loading: true, requestWindow: window }),
        next: (data) => {
          if (current()) patchState(store, { data, loading: false, error: null, stale: false });
        },
        error: (error) => {
          if (current()) patchState(store, failure(untracked(() => store.data()) !== null, error));
        },
      });
    });

    const refetch = (): void => { resolve().subscribe({ error: () => undefined }); };

    const select = (selection: ScopeSelection): void => {
      patchState(store, { selection });
      refetch();
    };

    const setPreset = (preset: ScopePreset): void => {
      chosen = true;
      rangeGeneration += 1;
      patchState(store, { targetSeq: store.targetSeq() + 1 });
      if (isPreset(store.selection(), preset)) return;
      prefs.update((current) => writeScopePreset(current, preset));
      select({ kind: 'preset', preset });
    };

    ranges.pipe(debounceTime(RANGE_DEBOUNCE_MS), takeUntilDestroyed()).subscribe(
      ({ window, generation }) => {
        if (generation !== rangeGeneration || sameWindow(store.selection(), window)) return;
        select({ kind: 'range', window });
      },
    );

    return {
      resolve,
      load: refetch,
      setPreset,
      /** A user pan or zoom settled on `window` (V181-15 calls this). Never
       *  persisted: a reload returns to the last preset (spec § 1). */
      setRange(window: TimeWindow): void {
        chosen = true;
        ranges.next({ window, generation: rangeGeneration });
      },
      /** The pre-v181 Today / All days toggle, kept until V181-14 replaces it. */
      setScope(scope: DashboardScope): void {
        setPreset(scope === 'all' ? 'All' : '1D');
      },
      /** The preset restored from preferences, once they have loaded. Moves
       *  the chart there; refetches only if a load already went out with the
       *  default. A no-op once the partner has chosen. */
      adoptStoredPreset(preset: ScopePreset): void {
        if (chosen || isPreset(store.selection(), preset)) return;
        patchState(store, { selection: { kind: 'preset', preset }, targetSeq: store.targetSeq() + 1 });
        if (latestRequest > 0) refetch();
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream), prefs = inject(PreferencesStore)) {
      // v181 -- restore the stored preset once preferences are in. Created
      // before the load effect below, so on a warm start (preferences already
      // loaded) it runs first and the initial load asks for the stored scope.
      let adopted = false;
      effect(() => {
        if (adopted || !prefs.isLoaded()) return;
        adopted = true;
        const preset = readScopePreset(prefs.values());
        untracked(() => store.adoptStoredPreset(preset));
      });
      const account = events.changes('account');
      const trades = events.changes('trades');
      // Coalesces the two signal reads (2026-09-14): closing a trade raises
      // BOTH a `trades` event and an `account` event (the balance moved
      // too) from the same scan tick. `effect()` re-runs on any dependency
      // change and reads both every time, so without this the dashboard
      // reloaded twice for one logical update -- the same
      // "settle within a short window, then act once" pattern
      // RouteRefreshService already uses for the identical problem at the
      // route level.
      //
      // The FIRST effect run is exempted from the debounce -- it IS the
      // initial load (see the comment on `load()`'s call site below), and
      // there is nothing racing it yet to coalesce against; debouncing it
      // too would just add 300ms to the dashboard's first paint for no
      // benefit.
      const refresh = new Subject<void>();
      refresh.pipe(debounceTime(300), takeUntilDestroyed()).subscribe(() => store['load']());
      let first = true;
      effect(() => {
        account();
        trades();
        if (first) {
          first = false;
          store['load']();
        } else {
          refresh.next();
        }
      });
    },
  }),
);
