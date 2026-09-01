import { computed, effect, inject } from '@angular/core';
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
import { Observable } from 'rxjs';

import { routeRequest } from '../routing/route-request';
import { Dashboard, DashboardScope } from '../api/models';

interface DashboardSlice {
  data: Dashboard | null;
  loading: boolean;
  error: string | null;
  /** SR58 — the date scope. A fetch parameter, so it lives here rather than
   *  in the component: the server does the date filtering, and a scope held
   *  in the component could not narrow the realised figures at all. */
  scope: DashboardScope;
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
    data: null, loading: false, error: null, scope: 'today',
  }),
  withComputed(({ data }) => ({
    /** True until the first response, and never again. Distinguishes "no
     *  data yet" from "a refetch is in flight", which want different UI:
     *  a skeleton once, and nothing at all thereafter. */
    empty: computed(() => data() === null),

    balance: computed(() => data()?.account_balance ?? null),
    openPnlPct: computed(() => data()?.open_pnl_pct ?? null),
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
  withMethods((store, api = inject(ApiClient)) => {
    const resolve = (): Observable<void> => routeRequest(api.dashboard(store.scope()), {
      start: () => patchState(store, { loading: true }),
      next: (data) => patchState(store, { data, loading: false, error: null }),
      error: (error) => patchState(store, {
        loading: false,
        error: error.code === 'unavailable' ? 'The admin is not responding.' : error.message,
      }),
    });
    return {
      resolve,
      load(): void { resolve().subscribe({ error: () => undefined }); },
      setScope(scope: DashboardScope): void {
        if (scope === store.scope()) return;
        patchState(store, { scope });
        resolve().subscribe({ error: () => undefined });
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const account = events.changes('account');
      const trades = events.changes('trades');
      let initialized = false;
      effect(() => {
        account();
        trades();
        if (initialized) store['load']();
        initialized = true;
      });
    },
  }),
);