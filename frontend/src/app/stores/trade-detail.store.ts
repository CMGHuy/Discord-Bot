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
import { AnalyticsStrategies, TradeDetail } from '../api/models';
import { StrategyRow } from './analytics.store';

interface TradeDetailSlice {
  id: string | null;
  data: TradeDetail | null;
  loading: boolean;
  error: string | null;

  /** The Notes tab's unsaved text, or null when it holds nothing the server
   *  has not seen. Null rather than a copy of the server's note, so "the user
   *  typed the same thing back" is not mistaken for an edit. */
  noteDraft: string | null;
  /** The text the server has acknowledged, which is not the same as the text
   *  in `detail.note` until the `journal` refetch lands. Without it the tab
   *  reads "unsaved" for the whole round trip -- and for ever, if the event
   *  stream is disconnected and the refetch never comes. */
  noteAcked: string | null;
  noteSaving: boolean;
  noteError: string | null;
  /** Set when a save comes back 404 because the position has no journal
   *  entry. Journal entries are written at close, so this is the normal
   *  state of an open trade -- NG8 required it be rendered as a state, and it
   *  is only discoverable by trying. */
  noteUnjournaled: boolean;

  /** `/analytics/strategies`, for the read-only Strategy tab. */
  strategies: AnalyticsStrategies | null;
  strategiesError: string | null;
}

/**
 * One trade, for the detail view — `GET /api/v1/trades/:id`.
 *
 * Same shape as `CockpitStore` and `TradesStore`: one server response in,
 * everything derived, and an effect that turns events into refetches. The
 * `id` lives in state rather than being passed to `load()` so that setting it
 * IS the load, exactly as setting the query is the load in `TradesStore` —
 * one way in, and no path that can be forgotten.
 *
 * Refetches on `trades` (price, status, sizing all move when a position does)
 * and on `journal` (the note is part of this response, and the Notes tab
 * writes it). Not on `account`: a balance change does not alter one trade.
 */
export const TradeDetailStore = signalStore(
  withState<TradeDetailSlice>({
    id: null,
    data: null,
    loading: false,
    error: null,
    noteDraft: null,
    noteAcked: null,
    noteSaving: false,
    noteError: null,
    noteUnjournaled: false,
    strategies: null,
    strategiesError: null,
  }),
  // eslint-disable-next-line max-len
  withComputed(({ data, noteDraft, noteAcked, noteSaving, noteError, noteUnjournaled, strategies }) => ({
    empty: computed(() => data() === null),
    trade: computed(() => data()),
    /** The heavy half. Null before the first response rather than an empty
     *  object, so a template cannot read a plan field that has not arrived
     *  and render a confident em dash for it. */
    detail: computed(() => data()?.detail ?? null),

    /** Risk and reward per share, from the plan's own levels. Null unless
     *  both sides are known — half an R:R is not an R:R. */
    riskPerShare: computed(() => {
      const trade = data();
      if (!trade || trade.entry === null || trade.stop_loss === null) return null;
      return Math.abs(trade.entry - trade.stop_loss);
    }),
    rewardPerShare: computed(() => {
      const trade = data();
      if (!trade || trade.entry === null || trade.target === null) return null;
      return Math.abs(trade.target - trade.entry);
    }),

    /* -- notes ----------------------------------------------------------- */

    /** What the textarea shows: the draft if the user has touched it, and
     *  the server's note otherwise. */
    noteText: computed(() => noteDraft() ?? data()?.detail?.note ?? ''),

    /** Whether there is anything to save. Compared against the server's text
     *  rather than "has been typed in", so typing a character and deleting it
     *  settles back to saved instead of autosaving a no-op. */
    noteDirty: computed(() => {
      const draft = noteDraft();
      // Against what the server last ACKNOWLEDGED, falling back to what it
      // sent. The two differ for the length of the `journal` round trip.
      return draft !== null && draft !== (noteAcked() ?? data()?.detail?.note ?? '');
    }),

    /**
     * One field the tab renders instead of four booleans it has to combine.
     *
     * Ordered by what the reader most needs to know: a position that cannot
     * take a note at all outranks a failed save, which outranks the state of
     * the text. Silence would be the worst outcome here -- an autosave that
     * failed while the user kept typing must not look identical to one that
     * succeeded.
     */
    noteStatus: computed<'unjournaled' | 'error' | 'saving' | 'unsaved' | 'saved'>(
      () => {
        if (noteUnjournaled()) return 'unjournaled';
        if (noteError()) return 'error';
        if (noteSaving()) return 'saving';
        const draft = noteDraft();
        if (draft !== null && draft !== (noteAcked() ?? data()?.detail?.note ?? '')) {
          return 'unsaved';
        }
        return 'saved';
      },
    ),

    /* -- strategy -------------------------------------------------------- */

    /** This trade's row out of `/analytics/strategies`, or null when the
     *  trade has no strategy or the registry has never heard of it. The tab
     *  says which of those it is rather than rendering an empty panel. */
    strategyRow: computed<StrategyRow | null>(() => {
      const name = data()?.strategy;
      if (!name) return null;
      const rows = (strategies()?.strategies ?? []) as StrategyRow[];
      return rows.find((row) => row.strategy === name) ?? null;
    }),
  })),
  withMethods((store, api = inject(ApiClient)) => ({
    /** Setting the id is what triggers the load. */
    setId(id: string): void {
      if (id === store.id()) return;
      // Clearing `data` is right here and wrong on a refetch: this is a
      // different trade, and showing the previous one's numbers under the new
      // one's heading would be worse than a skeleton.
      //
      // The draft goes with it. Carrying unsaved text across a navigation
      // would autosave one trade's note onto another.
      patchState(store, {
        id,
        data: null,
        error: null,
        noteDraft: null,
        noteAcked: null,
        noteError: null,
        noteUnjournaled: false,
      });
    },

    /** Record a keystroke. Does not save -- the component debounces and then
     *  calls `saveNote`. */
    editNote(text: string): void {
      patchState(store, { noteDraft: text, noteError: null });
    },

    saveNote(): void {
      const id = store.id();
      const draft = store.noteDraft();
      if (!id || draft === null) return;

      patchState(store, { noteSaving: true, noteError: null });
      api.setTradeNote(id, draft).subscribe({
        next: () =>
          // The draft is NOT cleared here. The server emits `journal`, the
          // effect below refetches, and the response carries the note --
          // clearing now would blank the textarea for the round trip. What is
          // recorded instead is that the server has this exact text, so the
          // tab can say "saved" without waiting for the refetch.
          patchState(store, {
            noteSaving: false,
            noteUnjournaled: false,
            noteAcked: draft,
          }),
        error: (error: ApiError) =>
          patchState(store, {
            noteSaving: false,
            // A 404 means the position has no journal entry, which is the
            // normal state of an open trade rather than a failure worth an
            // error message.
            noteUnjournaled: error.code === 'not_found',
            noteError:
              error.code === 'not_found'
                ? null
                : error.code === 'unavailable'
                  ? 'The admin is not responding — your note is not saved.'
                  : error.message,
          }),
      });
    },

    loadStrategies(): void {
      api.analyticsStrategies().subscribe({
        next: (strategies) => patchState(store, { strategies, strategiesError: null }),
        error: (error: ApiError) =>
          patchState(store, {
            strategiesError:
              error.code === 'unavailable'
                ? 'The admin is not responding.'
                : error.message,
          }),
      });
    },

    load(): void {
      const id = store.id();
      if (!id) return;

      patchState(store, { loading: true });
      api.trade(id).subscribe({
        next: (data) => patchState(store, { data, loading: false, error: null }),
        error: (error: ApiError) =>
          patchState(store, {
            loading: false,
            error:
              error.code === 'unavailable'
                ? 'The admin is not responding.'
                : error.message,
          }),
      });
    },
  })),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const trades = events.changes('trades');
      const journal = events.changes('journal');
      effect(() => {
        trades();
        journal();
        store.id();
        store.load();
      });
    },
  }),
);
