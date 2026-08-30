import { computed, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { Observable } from 'rxjs';

import { routeRequest } from '../routing/route-request';
import { Killswitch, Risk, RiskPosition, SectorHeat } from '../api/models';

interface RiskSlice {
  data: Risk | null;
  loading: boolean;
  error: string | null;

  /** The killswitch command is in flight. Separate from `loading`, which is
   *  the read: a toggle must lock its own button without blanking the page,
   *  and the page reloading must not unlock a command still in the air. */
  toggling: boolean;
  /** A failed toggle, kept until the next attempt. This is the one error on
   *  the screen the reader must act on -- believing the bot stopped taking
   *  positions when it did not is the worst outcome this workspace has. */
  commandError: string | null;
}

/** A cluster is a list of correlated tickers. The server ships
 *  `list[list[str]]` but `models.ts` types it `unknown[]`, because the shape
 *  is `_collect_portfolio_state`'s to decide -- see `DashboardStore`'s
 *  `finiteNumber` for the same trade-off. Narrowing happens here so the
 *  template is not asserting a wire format, and anything that is not a list
 *  of strings is dropped rather than rendered as `[object Object]`. */
function tickerList(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const tickers = value.filter((item): item is string => typeof item === 'string');
  return tickers.length ? tickers : null;
}

/**
 * Exposure, portfolio heat against the cap, and the killswitch.
 *
 * Same shape as `DashboardStore` -- read that one first. Two things differ,
 * and both come from this being the only workspace that holds an
 * operational control rather than a readout:
 *
 * **It has a command as well as a load.** `toggleKillswitch` applies the
 * server's response immediately instead of waiting for the refetch. The
 * `risk` event is raised by a file watcher over `killswitch.json`, so it
 * arrives a poll interval later; a screen that showed the old state for that
 * second would be answering "is the bot still trading" wrongly, in the
 * dangerous direction.
 *
 * **A failed command is kept, not swallowed.** A load failure leaves the
 * previous numbers up with a stale marker, exactly as elsewhere. A failed
 * toggle sets `commandError` and holds it, because the user asked for a
 * state change that did not happen and nothing else on the screen will say
 * so.
 *
 * Everything the Jinja Risk page renders is projected by `GET /risk`, and
 * everything projected is surfaced here: sector heat, correlated clusters,
 * the drawdown throttle and scan health included. Dropping a panel is a
 * decision someone makes on purpose in the SPA, not something that happens
 * because a store forgot to expose a field.
 */
export const RiskStore = signalStore(
  withState<RiskSlice>({
    data: null,
    loading: false,
    error: null,
    toggling: false,
    commandError: null,
  }),
  withComputed(({ data }) => ({
    /** True until the first response and never again -- a skeleton once,
     *  and nothing at all on refetches. */
    empty: computed(() => data() === null),

    /* -- heat ------------------------------------------------------------ */

    openHeatPct: computed(() => data()?.heat?.open_pct ?? null),
    heatCapPct: computed(() => data()?.heat?.cap_pct ?? null),

    /** **Not clamped.** 130% of the cap is precisely the situation the
     *  reader must see, and a number that stops at 100 would hide it. Only
     *  the bar's width is clamped, below, so it cannot overflow its track. */
    heatUtilisationPct: computed(() => data()?.heat?.utilisation_pct ?? null),

    /** The meter's fill, 0..1. Null rather than 0 when utilisation is
     *  unknown: an empty meter and a meter at zero look identical and mean
     *  opposite things. */
    heatMeterFraction: computed(() => {
      const utilisation = data()?.heat?.utilisation_pct;
      if (utilisation === null || utilisation === undefined) return null;
      return Math.min(1, Math.max(0, utilisation / 100));
    }),

    /** Amber from 80% of the cap. Amber, never red: being near the risk
     *  budget is a caution, not a loss, and red means money on this screen. */
    heatNearCap: computed(() => (data()?.heat?.utilisation_pct ?? 0) >= 80),
    heatOverCap: computed(() => (data()?.heat?.utilisation_pct ?? 0) > 100),

    /* -- exposure -------------------------------------------------------- */

    /** Already sorted by risk descending server-side, and left that way: the
     *  position carrying the most risk is the one this table exists to
     *  surface. These rows sum to `openHeatPct` -- both come from
     *  `heat.trade_risk_pct`, which is what makes the table and the meter
     *  above it agree. */
    positions: computed<RiskPosition[]>(() => data()?.positions ?? []),

    sectorHeat: computed<SectorHeat[]>(() => data()?.sector_heat ?? []),

    /** Numbered for display here rather than server-side: 1..n is
     *  presentation, and the API ships the lists unlabelled. */
    clusters: computed<{ index: number; tickers: string[] }[]>(() =>
      (data()?.clusters ?? [])
        .map(tickerList)
        .filter((tickers): tickers is string[] => tickers !== null)
        .map((tickers, position) => ({ index: position + 1, tickers })),
    ),

    /* -- throttle and killswitch ----------------------------------------- */

    /** 1.0 means unthrottled. The server already substitutes 1.0 for a
     *  missing value, so a null here would be a contract change rather than
     *  a normal state. */
    throttleMultiplier: computed(() => data()?.throttle?.multiplier ?? null),
    /** The drawdown throttle has cut size, or scanning is paused outright.
     *  Either one changes what the bot will do next, which is why they sit
     *  beside the killswitch rather than in a footnote. */
    throttled: computed(() => (data()?.throttle?.multiplier ?? 1) < 1),
    paused: computed(() => data()?.throttle?.paused ?? false),

    killswitch: computed<Killswitch | null>(() => data()?.killswitch ?? null),
    killswitchOn: computed(() => data()?.killswitch?.on ?? false),

    /* -- scan health ----------------------------------------------------- */

    scanDurations: computed<readonly number[]>(
      () => data()?.scan_health?.durations_s ?? [],
    ),
    scanLatestS: computed(() => data()?.scan_health?.latest_s ?? null),
    scanSlowdown: computed(() => data()?.scan_health?.slowdown ?? false),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    const resolve = (): Observable<void> => routeRequest(api.risk(), {
      start: () => patchState(store, { loading: true }),
      next: (data) => patchState(store, { data, loading: false, error: null }),
      error: (error) => patchState(store, {
        loading: false,
        error: error.code === 'unavailable' ? 'The admin is not responding — these figures may be stale.' : error.message,
      }),
    });
    return {
      resolve,
      load(): void { resolve().subscribe({ error: () => undefined }); },
      toggleKillswitch(on: boolean): void {
        patchState(store, { toggling: true, commandError: null });
        api.setKillswitch(on).subscribe({
          next: ({ killswitch }) => { const data = store.data(); patchState(store, { toggling: false, data: data ? { ...data, killswitch } : data }); },
          error: (error: ApiError) => patchState(store, { toggling: false, commandError: error.code === 'unavailable' ? `The admin is not responding — the killswitch is NOT ${on ? 'engaged' : 'released'}.` : error.message }),
        });
      },
      dismissCommandError(): void { patchState(store, { commandError: null }); },
    };
  }),
);