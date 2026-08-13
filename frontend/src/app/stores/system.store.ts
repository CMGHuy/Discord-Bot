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
import {
  Logs,
  ScanStatus,
  SettingField,
  Settings,
  SettingsDiffRow,
  SettingsSaveResult,
} from '../api/models';

/** The two log sources the API accepts. `bot` is the default; a typo'd
 *  source is refused server-side rather than falling back, because reading
 *  the admin log while believing it is the bot's is how someone concludes
 *  the bot is idle. */
export type LogSource = 'bot' | 'admin';

export const SYSTEM_TABS = ['settings', 'logs', 'scan'] as const;
export type SystemTab = (typeof SYSTEM_TABS)[number];

/** One entry of the settings audit log. Narrowed here rather than typed in
 *  `models.ts`: the file is JSONL appended to over time, so an older build's
 *  entry is a shape this version never wrote. */
export interface AuditEntry {
  ts: string | null;
  changes: { key: string; old: string; new: string }[];
}

type ScanCommand = 'trigger' | 'stop' | 'pause' | 'resume';

interface SystemSlice {
  /* settings */
  settings: Settings | null;
  settingsLoading: boolean;
  settingsError: string | null;
  /** Edited fields only, keyed by setting key. Not a copy of the whole
   *  document: the server overlays a partial body on what is on disk, and a
   *  full-form submission would write back every field a concurrent editor
   *  had just changed. */
  draft: Record<string, string | boolean>;
  previewing: boolean;
  /** The approved diff, or null when nothing has been previewed. Non-null
   *  is what puts the form in "confirm this" rather than "keep editing". */
  preview: SettingsDiffRow[] | null;
  restartRequired: string[];
  saving: boolean;
  /** Validation or transport failure from preview/save. Held until the next
   *  attempt: the user asked for a change that did not happen. */
  formError: string | null;
  /** The result of the last successful save, including whether the bot was
   *  actually signalled. */
  saved: SettingsSaveResult | null;
  /** A `settings` event arrived while this form had unsaved edits. The form
   *  is NOT reloaded — see `applySettingsEvent`. */
  settingsStale: boolean;
  importing: boolean;
  /** The result of the last import, successful or not. One line, because
   *  what matters is the count applied AND the keys skipped. */
  importMessage: string | null;

  /* logs */
  logSource: LogSource;
  logs: Logs | null;
  logsLoading: boolean;
  logsError: string | null;
  logsMessage: string | null;

  /* scan */
  scan: ScanStatus | null;
  scanError: string | null;
  /** Which command is in flight, so one button locks rather than all four. */
  scanPending: ScanCommand | null;
  scanMessage: string | null;

  /* bot restart */
  restarting: boolean;
  restartMessage: string | null;
  /** Set when the API answers 503 because the Docker socket is not mounted.
   *  A deployment that cannot restart is not a restart that failed, and the
   *  UI has to say which. */
  restartUnavailable: boolean;
}

/**
 * A field's value as the form should show it. The server sends booleans for
 * checkboxes and `•••` for anything sensitive; everything else is a string.
 *
 * The mask is treated as an ordinary value on purpose. Left alone it never
 * enters the draft, so it is never sent; retyped identically it compares
 * equal here and still is not sent — which is the same "leave this alone"
 * the server's `_effective_form` reads it as. Substituting something else
 * for it would be the one way to write `•••` in as a real credential.
 */
function fieldValue(field: SettingField): string | boolean {
  if (field.type === 'checkbox') return field.value === true;
  return field.value === null || field.value === undefined ? '' : String(field.value);
}

function auditEntry(value: unknown): AuditEntry | null {
  if (typeof value !== 'object' || value === null) return null;
  const row = value as Record<string, unknown>;
  const changes = Array.isArray(row['changes']) ? row['changes'] : [];
  return {
    ts: typeof row['ts'] === 'string' ? row['ts'] : null,
    changes: changes
      .filter((change): change is Record<string, unknown> =>
        typeof change === 'object' && change !== null,
      )
      .map((change) => ({
        key: String(change['key'] ?? ''),
        old: String(change['old'] ?? ''),
        new: String(change['new'] ?? ''),
      })),
  };
}

/**
 * Settings, logs and scan control — the three tabs of the System workspace.
 *
 * One store rather than three because spec v13's table says so, and because
 * the three share one refetch story: `settings`, `scan` and `bot` are
 * separate events, but bot liveness reaches the scan tab through the same
 * `/system/scan` payload the commands return.
 *
 * **The settings form renders from the schema and holds no field list.**
 * `GET /system/settings` ships `Field` entries and values together, so a new
 * setting in `config.py` appears here with no frontend change — a property
 * the Jinja UI has and the rebuild is not allowed to lose. Nothing in this
 * store or its components names a setting.
 *
 * **A `settings` event never overwrites an edit in progress.** Spec v14
 * Decision 8 is explicit: warn rather than silently reloading a form being
 * edited. Losing typed configuration to another session's save — or to your
 * own SIGHUP — is worse than showing values a few seconds old, and the
 * silent version is the one you only notice after clicking save.
 *
 * **The draft carries changed fields only.** The server overlays them on
 * what is on disk; a full-form submission would write back every value the
 * form loaded, quietly reverting a concurrent change to a field this user
 * never touched.
 */
export const SystemStore = signalStore(
  withState<SystemSlice>({
    settings: null,
    settingsLoading: false,
    settingsError: null,
    draft: {},
    previewing: false,
    preview: null,
    restartRequired: [],
    saving: false,
    formError: null,
    saved: null,
    settingsStale: false,
    importing: false,
    importMessage: null,

    logSource: 'bot',
    logs: null,
    logsLoading: false,
    logsError: null,
    logsMessage: null,

    scan: null,
    scanError: null,
    scanPending: null,
    scanMessage: null,

    restarting: false,
    restartMessage: null,
    restartUnavailable: false,
  }),
  withComputed(({ settings, draft, preview, scan }) => ({
    settingsEmpty: computed(() => settings() === null),

    sections: computed(() => settings()?.sections ?? []),

    /** Every field, flattened, for the lookups below. Sections are how the
     *  form is laid out; this is how it is reasoned about. */
    fields: computed<SettingField[]>(() =>
      (settings()?.sections ?? []).flatMap((section) => section.fields),
    ),

    audit: computed<AuditEntry[]>(() =>
      (settings()?.audit ?? [])
        .map(auditEntry)
        .filter((entry): entry is AuditEntry => entry !== null),
    ),

    restartAvailable: computed(() => settings()?.restart_available ?? false),

    dirtyKeys: computed(() => Object.keys(draft())),
    dirty: computed(() => Object.keys(draft()).length > 0),

    /** True once a diff has been approved and nothing has been edited
     *  since — the state in which Save is the only sensible next action. */
    awaitingSave: computed(() => preview() !== null),

    /* -- scan ------------------------------------------------------------ */

    scanRunning: computed(() => scan()?.running ?? false),
    scanPaused: computed(() => scan()?.paused ?? false),
    scanQueued: computed(() => scan()?.pending ?? false),
    botAlive: computed(() => scan()?.bot_alive ?? false),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    /** The value the form shows for a field: the draft if it has been
     *  touched, the server's otherwise. Defined here so both the component
     *  and `submit` read one definition. */
    const currentValue = (field: SettingField): string | boolean => {
      const draft = store.draft();
      return field.key in draft ? draft[field.key] : fieldValue(field);
    };

    const loadSettings = (): void => {
      patchState(store, { settingsLoading: true });
      api.settings().subscribe({
        next: (settings) =>
          patchState(store, {
            settings,
            settingsLoading: false,
            settingsError: null,
            settingsStale: false,
          }),
        error: (error: ApiError) =>
          patchState(store, {
            settingsLoading: false,
            settingsError:
              error.code === 'unavailable'
                ? 'The admin is not responding.'
                : error.message,
          }),
      });
    };

    const loadLogs = (): void => {
      patchState(store, { logsLoading: true });
      api.logs(store.logSource()).subscribe({
        next: (logs) =>
          patchState(store, { logs, logsLoading: false, logsError: null }),
        error: (error: ApiError) =>
          patchState(store, {
            logsLoading: false,
            logsError:
              error.code === 'unavailable'
                ? 'The admin is not responding.'
                : error.message,
          }),
      });
    };

    const loadScan = (): void => {
      api.scanStatus().subscribe({
        next: (scan) => patchState(store, { scan, scanError: null }),
        error: (error: ApiError) =>
          patchState(store, {
            scanError:
              error.code === 'unavailable'
                ? 'The admin is not responding.'
                : error.message,
          }),
      });
    };

    return {
      loadSettings,
      loadLogs,
      loadScan,
      currentValue,

      /**
       * A `settings` event, from another session's save or a SIGHUP.
       *
       * Reloads only when there is nothing to lose. With edits in the form
       * it raises `settingsStale` and leaves every value alone — the warning
       * is the whole feature, and a reload here would silently discard
       * configuration someone was in the middle of typing.
       */
      applySettingsEvent(): void {
        if (store.dirty()) {
          patchState(store, { settingsStale: true });
          return;
        }
        loadSettings();
      },

      /** Take the newer values, discarding the draft. Only ever called from
       *  the warning's own button, so the discard is always something the
       *  user chose. */
      discardDraftAndReload(): void {
        patchState(store, { draft: {}, preview: null, formError: null });
        loadSettings();
      },

      /**
       * Record an edit.
       *
       * A value edited back to what the server sent leaves the draft
       * entirely, so "changed something and changed it back" is not a
       * pending save. Any edit also drops an approved preview: the diff on
       * screen would no longer be the diff that gets written, and a stale
       * approval is worse than none.
       */
      edit(field: SettingField, value: string | boolean): void {
        const draft = { ...store.draft() };
        if (value === fieldValue(field)) delete draft[field.key];
        else draft[field.key] = value;
        patchState(store, { draft, preview: null, formError: null, saved: null });
      },

      resetDraft(): void {
        patchState(store, { draft: {}, preview: null, formError: null });
      },

      /** Ask what would change. The same `settings_diff` runs on save, over
       *  the same overlay, so what is approved is what is written. */
      previewChanges(): void {
        if (!store.dirty()) return;
        patchState(store, { previewing: true, formError: null, saved: null });
        api.previewSettings(store.draft()).subscribe({
          next: ({ diff, restart_required }) =>
            patchState(store, {
              previewing: false,
              preview: diff,
              restartRequired: restart_required,
            }),
          error: (error: ApiError) =>
            patchState(store, {
              previewing: false,
              preview: null,
              // The server validates against the same schema the form was
              // built from, so its message names the field and the bound.
              formError:
                error.code === 'unavailable'
                  ? 'The admin is not responding — nothing was changed.'
                  : error.message,
            }),
        });
      },

      /**
       * Write the approved changes.
       *
       * Refuses to run without a preview. The gate is deliberate: spec v14
       * keeps preview-before-save, and a save path that could skip it would
       * become the one every future caller uses.
       */
      save(): void {
        if (store.preview() === null || !store.dirty()) return;
        patchState(store, { saving: true, formError: null });
        api.saveSettings(store.draft()).subscribe({
          next: (saved) => {
            patchState(store, { saving: false, saved, draft: {}, preview: null });
            // Re-read rather than patching the document from the diff: the
            // server may have normalised a value, and the audit list has a
            // new entry either way. The `settings` event will also fire, but
            // only outside tests and only once the watcher notices.
            loadSettings();
          },
          error: (error: ApiError) =>
            patchState(store, {
              saving: false,
              formError:
                error.code === 'unavailable'
                  ? 'The admin is not responding — nothing was saved.'
                  : error.message,
            }),
        });
      },

      /** The export URL, passed through so the component can put it in an
       *  anchor without injecting `ApiClient` — the browser downloading it
       *  through a normal navigation is the point (a Save dialog and the
       *  server's filename, both of which an XHR throws away). */
      exportUrl: (): string => api.settingsExportUrl(),

      /** The raw log URL, for the same reason: text/plain in a new tab is
       *  the browser's job, not a viewer built here. */
      rawLogUrl: (source: LogSource): string => api.logsRawUrl(source),

      /**
       * Apply a pasted `.env`.
       *
       * Lenient where save is strict, matching the endpoint: the text is
       * quite possibly an export from an older build, and refusing the whole
       * file over one retired key would make every upgrade a manual edit.
       * Both halves of the result are reported — "applied 12" alone hides
       * the four keys that were skipped.
       */
      importSettings(text: string): void {
        const body = text.trim();
        if (!body) return;
        patchState(store, { importing: true, importMessage: null });
        api.importSettings({ text: body }).subscribe({
          next: ({ applied, unknown_keys }) => {
            patchState(store, {
              importing: false,
              importMessage: unknown_keys.length
                ? `Applied ${applied}; skipped unknown key(s): ${unknown_keys.join(', ')}`
                : `Applied ${applied} setting${applied === 1 ? '' : 's'}.`,
              // The file on disk has moved under the form. The draft is
              // dropped because it was written against the old values, and
              // silently keeping it would write them back on the next save.
              draft: {},
              preview: null,
            });
            loadSettings();
          },
          error: (error: ApiError) =>
            patchState(store, {
              importing: false,
              importMessage:
                error.code === 'unavailable'
                  ? 'The admin is not responding — nothing was imported.'
                  : error.message,
            }),
        });
      },

      /* -- logs ---------------------------------------------------------- */

      setLogSource(source: LogSource): void {
        if (source === store.logSource()) return;
        // Cleared, not kept: showing the bot log under the heading "admin"
        // for the length of the request is the exact confusion the API's
        // strict source check exists to prevent.
        patchState(store, { logSource: source, logs: null, logsMessage: null });
        loadLogs();
      },

      clearLogs(): void {
        const source = store.logSource();
        api.clearLogs(source).subscribe({
          next: ({ ok, message }) => {
            // `ok: false` here means there was no file to clear, which is
            // not a failure — it is reported as the message it is.
            patchState(store, { logsMessage: message });
            if (ok) loadLogs();
          },
          error: (error: ApiError) => patchState(store, { logsError: error.message }),
        });
      },

      /* -- scan ---------------------------------------------------------- */

      runScanCommand(command: ScanCommand): void {
        patchState(store, { scanPending: command, scanMessage: null, scanError: null });
        const request = {
          trigger: () => api.triggerScan(),
          stop: () => api.stopScan(),
          pause: () => api.pauseScan(),
          resume: () => api.resumeScan(),
        }[command]();

        request.subscribe({
          // Every command answers with the resulting status, so there is no
          // follow-up GET: these are cooperative (the bot polls a file), and
          // "was it written" is the only question this response can answer.
          next: ({ message, scan }) =>
            patchState(store, { scanPending: null, scanMessage: message, scan }),
          error: (error: ApiError) =>
            patchState(store, {
              scanPending: null,
              scanError:
                error.code === 'unavailable'
                  ? `Could not ${command} the scan — ${error.message}`
                  : error.message,
            }),
        });
      },

      /* -- bot restart --------------------------------------------------- */

      restartBot(): void {
        patchState(store, {
          restarting: true,
          restartMessage: null,
          restartUnavailable: false,
        });
        api.restartBot().subscribe({
          next: ({ message }) =>
            patchState(store, { restarting: false, restartMessage: message }),
          error: (error: ApiError) =>
            patchState(store, {
              restarting: false,
              // 503 covers both "no Docker socket" and "the restart itself
              // failed", and only the server's message tells them apart --
              // so it is shown verbatim rather than replaced with one of
              // ours. `restart_available` on the settings document is the
              // same fact ahead of time, and hides the button entirely.
              restartUnavailable: error.code === 'unavailable',
              restartMessage: error.message,
            }),
        });
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const settings = events.changes('settings');
      effect(() => {
        settings();
        store.applySettingsEvent();
      });

      // Logs have no event of their own -- they are a file the admin tails.
      // Loaded once here; the Logs tab has an explicit refresh, which is
      // honest about what it is rather than a timer that quietly hides how
      // stale the view is.
      store.loadLogs();

      // `scan` covers trigger/pause/stop; `bot` covers the heartbeat, which
      // is rendered on the same tab.
      const scan = events.changes('scan');
      const bot = events.changes('bot');
      effect(() => {
        scan();
        bot();
        store.loadScan();
      });
    },
  }),
);
