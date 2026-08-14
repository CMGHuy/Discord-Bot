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
import { AnalyticsStrategies, JournalEntry, TradeDetail } from '../api/models';
import { StrategyRow } from './analytics.store';

/* -- the narrowed shapes of the loosely typed detail fields ---------------
 *
 * SR49. Nine fields on `TradeDetailFields` were typed, fetched and rendered by
 * nothing — each appeared exactly once in `frontend/src`, in `models.ts`
 * itself. Several are `unknown[]` / `Record<string, unknown>` on purpose,
 * because the Python side owns their shape and pinning an interface to it
 * would make every backend tweak a compile error here.
 *
 * The narrowing therefore lives in this store rather than in the template, the
 * same rule `DashboardStore.finiteNumber` follows: a template that narrowed
 * would be asserting a wire format, and one that trusted the `unknown` blindly
 * would print `[object Object]` the first time a key was renamed. Every
 * narrower below drops what it cannot read instead of rendering a confident
 * blank.
 */

/** One row of `quality_breakdown`. The wire form is a two-element list, not an
 *  object — `plan_engine.py:141` converts the scoring tuples to lists so JSON
 *  round-trips cleanly. */
export interface QualityFactor {
  label: string;
  points: number;
}

/** One `status_history` entry — `plan_engine.py:735` appends exactly this. */
export interface StatusEvent {
  status: string;
  reason: string | null;
  at: string | null;
}

/** One scale-out leg. `r` is present once the leg has closed; `reason` says
 *  why it closed. A leg with neither is the runner, still live. */
export interface Leg {
  fraction: number | null;
  exitPrice: number | null;
  r: number | null;
  reason: string | null;
}

export interface ConfidenceFactor {
  factor: string;
  note: string;
}

/** A strategy/horizon pair that independently agreed with this setup. */
export interface Confirmation {
  strategy: string;
  horizon: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asText(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() === '' ? null : value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** `[label, points]` pairs. Anything that is not a readable pair is dropped:
 *  a factor with no points is not a factor, and a zero would be a claim. */
function toQualityFactors(raw: unknown[]): QualityFactor[] {
  return raw.flatMap((row) => {
    if (!Array.isArray(row) || row.length < 2) return [];
    const label = asText(row[0]);
    const points = asNumber(row[1]);
    return label !== null && points !== null ? [{ label, points }] : [];
  });
}

function toStatusEvents(raw: unknown[]): StatusEvent[] {
  return raw.flatMap((row) => {
    if (!isRecord(row)) return [];
    const status = asText(row['status']);
    // A transition with no status is not a transition. Reason and time are
    // both genuinely optional -- the first entry often has neither.
    return status === null
      ? []
      : [{ status, reason: asText(row['reason']), at: asText(row['at']) }];
  });
}

function toLegs(raw: unknown[]): Leg[] {
  return raw.flatMap((row) =>
    isRecord(row)
      ? [{
          fraction: asNumber(row['fraction']),
          exitPrice: asNumber(row['exit_price']),
          r: asNumber(row['r']),
          reason: asText(row['reason']),
        }]
      : [],
  );
}

/** `confidence_breakdown` is a factor -> note map, rendered in insertion
 *  order. Object key order is insertion order for string keys, which is what
 *  the scoring code produced and the order the Jinja table showed. */
function toConfidenceFactors(raw: unknown): ConfidenceFactor[] {
  if (!isRecord(raw)) return [];
  return Object.entries(raw).flatMap(([factor, note]) => {
    const text = asText(note);
    return text === null ? [] : [{ factor, note: text }];
  });
}

/** `confirmed_by` carries `{strategy, horizon_key}` objects, though `models.ts`
 *  types it `string[]`. Both forms are accepted rather than trusting either:
 *  the type is wrong today and correcting it does not guarantee what an older
 *  trade record on disk contains. */
function toConfirmations(raw: unknown[]): Confirmation[] {
  return raw.flatMap((row) => {
    if (typeof row === 'string') {
      return row.trim() === '' ? [] : [{ strategy: row, horizon: null }];
    }
    if (!isRecord(row)) return [];
    const strategy = asText(row['strategy']);
    return strategy === null
      ? []
      : [{ strategy, horizon: asText(row['horizon_key']) }];
  });
}

/** Free-text source labels, de-duplicated. The Jinja tooltip concatenated the
 *  target and stop lists and piped them through `unique`; the same name
 *  appearing on both sides is common and saying it twice adds nothing. */
function toSources(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  for (const item of raw) {
    const text = asText(item);
    if (text !== null) seen.add(text);
  }
  return [...seen];
}

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

  /** SR55 — the journal entry behind the note: MFE, MAE, exit efficiency,
   *  tags and the auto-lesson.
   *
   *  Read from its own endpoint rather than widened into `/trades/:id`,
   *  because the detail response is what the whole view blocks on and a
   *  journal read failure must not empty the position itself. */
  journal: JournalEntry | null;
  /** True once the endpoint has answered "no entry". Distinct from
   *  `journal === null`, which is also the pre-response state — rendering
   *  those the same way would flash "not journaled" on every open. */
  journalAnswered: boolean;
  journalError: string | null;
}

/**
 * One trade, for the detail view — `GET /api/v1/trades/:id`.
 *
 * Same shape as `DashboardStore` and `TradesStore`: one server response in,
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
    journal: null,
    journalAnswered: false,
    journalError: null,
  }),
  // eslint-disable-next-line max-len
  withComputed(({ data, noteDraft, noteAcked, noteSaving, noteError, noteUnjournaled, strategies,
                 journal, journalAnswered }) => ({
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

    /* -- the plan's reasoning (SR49) ------------------------------------- */

    /** Why the bot took this trade, in its own words. The single largest piece
     *  of per-trade prose the old UI had, and the field most obviously worth
     *  rendering: everything else on this screen is a number. */
    explanation: computed(() => asText(data()?.detail?.explanation ?? null)),

    /** The other strategy/horizon pairs that independently agreed. */
    confirmedBy: computed<Confirmation[]>(() =>
      toConfirmations(data()?.detail?.confirmed_by ?? []),
    ),

    /** What put the target where it is, and the stop where it is. Separate
     *  lists rather than the Jinja tooltip's merged one: on the detail view
     *  there is room to say which level each source justifies, and that is the
     *  question the tooltip could not answer. */
    targetSources: computed<string[]>(() => toSources(data()?.detail?.target_sources)),
    stopSources: computed<string[]>(() => toSources(data()?.detail?.stop_sources)),
    target2Sources: computed<string[]>(() => toSources(data()?.detail?.target2_sources)),

    /** The 8-10 factors behind the Lv1-5 confidence level. */
    confidenceFactors: computed<ConfidenceFactor[]>(() =>
      toConfidenceFactors(data()?.detail?.confidence_breakdown),
    ),

    /** The factors behind the quality score, and so behind the A/B/C tier. */
    qualityFactors: computed<QualityFactor[]>(() =>
      toQualityFactors(data()?.detail?.quality_breakdown ?? []),
    ),

    /** The plan's audit trail: created, then every transition with its reason.
     *  `created_at` is prepended as the first event, which is how the Jinja
     *  timeline read -- the history array itself does not contain it. */
    timeline: computed<StatusEvent[]>(() => {
      const detail = data()?.detail;
      if (!detail) return [];
      const history = toStatusEvents(detail.status_history ?? []);
      const created = asText(detail.created_at);
      if (created === null) return history;
      return [
        { status: 'CREATED', reason: asText(detail.plan_source), at: created },
        ...history,
      ];
    }),

    /** Scale-out legs. `legs_realized` is preferred when present -- it is the
     *  settled record; `legs` is the live one. */
    legs: computed<Leg[]>(() => {
      const detail = data()?.detail;
      if (!detail) return [];
      const realized = toLegs(detail.legs_realized ?? []);
      return realized.length ? realized : toLegs(detail.legs ?? []);
    }),

    /** The stop-entry price still being waited on. For a PENDING plan this is
     *  the only actionable price on the screen -- `entry` is null until it
     *  fills. */
    triggerPrice: computed(() => asNumber(data()?.detail?.trigger_price ?? null)),

    /** Break-even trigger as a percentage of the entry-to-TP1 distance, and
     *  TP1's own share of the position. Both are fractions on the wire. */
    breakevenTriggerPct: computed(() => {
      const value = asNumber(data()?.detail?.breakeven_trigger_fraction ?? null);
      return value === null ? null : value * 100;
    }),
    tp1Pct: computed(() => {
      const value = asNumber(data()?.detail?.tp1_fraction ?? null);
      return value === null ? null : value * 100;
    }),

    /**
     * True when this record predates the detail capture entirely.
     *
     * Not the same as "some fields are empty". A plan-backed trade with no
     * explanation recorded is one absent field; a legacy row has none of them
     * and never will, and the Jinja page said so outright rather than showing
     * a screen of em dashes that look like a loading failure.
     */
    detailAbsent: computed(() => {
      const detail = data()?.detail;
      if (!detail) return false;   // nothing has arrived yet — not the same thing
      return (
        asText(detail.explanation) === null &&
        (detail.confirmed_by ?? []).length === 0 &&
        (detail.quality_breakdown ?? []).length === 0 &&
        (detail.status_history ?? []).length === 0 &&
        !isRecord(detail.confidence_breakdown) &&
        (detail.target_sources ?? []).length === 0 &&
        (detail.stop_sources ?? []).length === 0
      );
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
    /* -- SR55: the journal entry behind the note --------------------- */

    /** The three excursion figures, as render-ready rows. Empty until the
     *  endpoint answers, and empty when it answers "no entry" — an open
     *  position has no excursions to report and must not show three dashes
     *  implying it does. */
    excursions: computed<{ label: string; value: number | null; unit: string; decimals: number }[]>(
      () => {
        const entry = journal();
        if (!entry) return [];
        return [
          { label: 'MFE', value: entry.mfe_r, unit: 'R', decimals: 2 },
          { label: 'MAE', value: entry.mae_r, unit: 'R', decimals: 2 },
          {
            // Stored 0-1; shown as a percentage, because "captured 31% of the
            // favourable move" is the sentence a reader is trying to form.
            label: 'Exit efficiency',
            value: entry.exit_efficiency === null ? null : entry.exit_efficiency * 100,
            unit: '%',
            decimals: 0,
          },
        ];
      }),

    journalTags: computed<string[]>(() => journal()?.tags ?? []),
    autoLesson: computed<string | null>(() => journal()?.auto_lesson ?? null),

    /** The endpoint has answered and there is no entry — the normal state of
     *  an open position, and a state rather than an error. */
    journalAbsent: computed(() => journalAnswered() && journal() === null),

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

      // SR55. Its own request and its own error: the excursions explain the
      // note, and losing them must not take the position down with them.
      // `journaled: false` is a normal 200 here, not an error to catch.
      api.tradeJournal(id).subscribe({
        next: (response) =>
          patchState(store, {
            journal: response.entry,
            journalAnswered: true,
            journalError: null,
          }),
        error: (error: ApiError) =>
          patchState(store, {
            journalAnswered: true,
            journalError:
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
