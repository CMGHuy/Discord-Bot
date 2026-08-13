import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import {
  ApplicationRef,
  Signal,
  WritableSignal,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { SettingField, Settings } from '../api/models';
import { SystemStore } from './system.store';

/* NG50 — settings, logs and scan.
 *
 * The tests that matter are about NOT losing things: a draft to another
 * session's save, an unknown key to a silent skip, a credential to a form
 * that writes the mask back as a real value.
 */

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();

  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }

  changes(name: string): Signal<number> {
    return this.counterFor(name).asReadonly();
  }

  raise(name: string): void {
    this.counterFor(name).update((n) => n + 1);
  }
}

function field(over: Partial<SettingField> = {}): SettingField {
  return {
    key: 'RISK_PCT',
    label: 'Risk per trade',
    type: 'float',
    value: '1.0',
    default: '1.0',
    help: '',
    min: 0.1,
    max: 5,
    step: 0.1,
    options: [],
    sensitive: false,
    hot_reloadable: true,
    ...over,
  };
}

const TOKEN = field({
  key: 'DISCORD_TOKEN',
  label: 'Bot token',
  type: 'password',
  value: '•••',
  sensitive: true,
  hot_reloadable: false,
});

const FLAG = field({
  key: 'SCALE_OUT',
  label: 'Scale out',
  type: 'checkbox',
  value: false,
});

const SETTINGS: Settings = {
  sections: [
    {
      name: 'Risk',
      icon: '',
      description: '',
      fields: [field(), FLAG],
    },
    { name: 'Discord Connection', icon: '', description: '', fields: [TOKEN] },
  ],
  audit: [
    { ts: '2026-08-12T10:00:00Z', changes: [{ key: 'RISK_PCT', old: '0.5', new: '1.0' }] },
    'not an entry',
  ],
  restart_available: true,
};

const SCAN = {
  pending: false,
  triggered_at: null,
  paused: false,
  paused_at: null,
  running: false,
  bot_alive: true,
  bot_last_seen: null,
  bot_session_active: true,
  bot_scan_paused: false,
};

describe('SystemStore', () => {
  let store: InstanceType<typeof SystemStore>;
  let backend: HttpTestingController;
  let events: FakeEventStream;

  beforeEach(() => {
    events = new FakeEventStream();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
        SystemStore,
      ],
    });
    store = TestBed.inject(SystemStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();

  /** The three requests the store issues on creation, in one call. */
  const boot = (settings: Partial<Settings> = {}) => {
    tick();
    backend.expectOne('/api/v1/system/settings').flush({ ...SETTINGS, ...settings });
    backend.expectOne('/api/v1/system/logs?source=bot').flush({
      source: 'bot',
      lines: 500,
      path: '/app/logs/bot.log',
      content: 'started',
    });
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
  };

  /* -- the schema-driven form -------------------------------------------- */

  it('holds the schema and derives no field list of its own', () => {
    boot();

    expect(store.sections()).toHaveLength(2);
    expect(store.fields().map((f) => f.key)).toEqual([
      'RISK_PCT',
      'SCALE_OUT',
      'DISCORD_TOKEN',
    ]);
    expect(store.restartAvailable()).toBe(true);
  });

  it('shows the server value until a field is edited', () => {
    boot();
    const risk = store.fields()[0];

    expect(store.currentValue(risk)).toBe('1.0');
    store.edit(risk, '2.0');
    expect(store.currentValue(risk)).toBe('2.0');
    expect(store.dirtyKeys()).toEqual(['RISK_PCT']);
  });

  it('drops a field from the draft when it is edited back', () => {
    // Typing a value and undoing it must not leave a pending save, and must
    // not send a no-op the server would diff to nothing.
    boot();
    const risk = store.fields()[0];

    store.edit(risk, '2.0');
    store.edit(risk, '1.0');

    expect(store.dirty()).toBe(false);
  });

  it('keeps checkbox values as booleans, not strings', () => {
    boot();
    const flag = store.fields()[1];

    expect(store.currentValue(flag)).toBe(false);
    store.edit(flag, true);
    expect(store.currentValue(flag)).toBe(true);
  });

  it('never sends the mask back as a credential', () => {
    // The server reads `•••` as "leave it", but only because it arrives
    // unchanged. Retyping it identically must also be a no-op here.
    boot();
    const token = store.fields()[2];

    expect(store.currentValue(token)).toBe('•••');
    store.edit(token, '•••');

    expect(store.dirty()).toBe(false);
  });

  it('narrows the audit log and drops entries it cannot read', () => {
    boot();

    expect(store.audit()).toHaveLength(1);
    expect(store.audit()[0].changes[0].key).toBe('RISK_PCT');
  });

  /* -- preview and save --------------------------------------------------- */

  it('previews only the changed fields, wrapped in settings', () => {
    boot();
    store.edit(store.fields()[0], '2.0');
    store.previewChanges();

    const request = backend.expectOne('/api/v1/system/settings/preview');
    // A partial body is the expected shape: the server overlays it on what
    // is on disk, where a full-form submission would write back every value
    // this form loaded and revert a concurrent change.
    expect(request.request.body).toEqual({ settings: { RISK_PCT: '2.0' } });

    request.flush({
      diff: [
        { key: 'RISK_PCT', label: 'Risk per trade', old: '1.0', new: '2.0', sensitive: false },
      ],
      restart_required: [],
    });

    expect(store.preview()).toHaveLength(1);
    expect(store.awaitingSave()).toBe(true);
  });

  it('refuses to save without a preview', () => {
    // Preview-before-save is spec v14's, and a save path that could skip it
    // would become the one every later caller used.
    boot();
    store.edit(store.fields()[0], '2.0');

    store.save();

    backend.verify();
    expect(store.saving()).toBe(false);
  });

  it('drops an approved preview as soon as anything else is edited', () => {
    // The diff on screen would no longer be the diff that gets written.
    boot();
    store.edit(store.fields()[0], '2.0');
    store.previewChanges();
    backend
      .expectOne('/api/v1/system/settings/preview')
      .flush({ diff: [], restart_required: [] });

    store.edit(store.fields()[1], true);

    expect(store.preview()).toBeNull();
    expect(store.awaitingSave()).toBe(false);
  });

  it('saves the approved draft and re-reads the document', () => {
    boot();
    store.edit(store.fields()[0], '2.0');
    store.previewChanges();
    backend
      .expectOne('/api/v1/system/settings/preview')
      .flush({ diff: [], restart_required: [] });

    store.save();
    const request = backend.expectOne('/api/v1/system/settings');
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({ settings: { RISK_PCT: '2.0' } });

    request.flush({
      diff: [
        { key: 'RISK_PCT', label: 'Risk per trade', old: '1.0', new: '2.0', sensitive: false },
      ],
      restart_required: [],
      hot_reload: { ok: true, message: 'signalled' },
    });

    // Re-read rather than patched from the diff: the server may normalise a
    // value, and the audit list has a new entry either way.
    backend.expectOne('/api/v1/system/settings').flush(SETTINGS);
    expect(store.dirty()).toBe(false);
    expect(store.saved()?.hot_reload.ok).toBe(true);
  });

  it('reports a failed hot reload without calling the save a failure', () => {
    // The .env write SUCCEEDED; only the signal telling the bot to re-read
    // it did not, which is routine outside Docker.
    boot();
    store.edit(store.fields()[0], '2.0');
    store.previewChanges();
    backend
      .expectOne('/api/v1/system/settings/preview')
      .flush({ diff: [], restart_required: [] });
    store.save();
    backend.expectOne('/api/v1/system/settings').flush({
      diff: [],
      restart_required: [],
      hot_reload: { ok: false, message: 'no bot container' },
    });
    backend.expectOne('/api/v1/system/settings').flush(SETTINGS);

    expect(store.formError()).toBeNull();
    expect(store.saved()?.hot_reload.ok).toBe(false);
  });

  it('keeps the draft when the server rejects a value', () => {
    boot();
    store.edit(store.fields()[0], '99');
    store.previewChanges();
    backend.expectOne('/api/v1/system/settings/preview').flush(
      { error: { code: 'invalid', message: 'Risk per trade must be at most 5' } },
      { status: 400, statusText: 'Bad Request' },
    );

    expect(store.formError()).toContain('at most 5');
    expect(store.currentValue(store.fields()[0])).toBe('99');
    expect(store.preview()).toBeNull();
  });

  /* -- the settings event ------------------------------------------------- */

  it('reloads on a settings event when nothing is being edited', () => {
    boot();

    events.raise('settings');
    tick();
    backend.expectOne('/api/v1/system/settings').flush(SETTINGS);

    expect(store.settingsStale()).toBe(false);
  });

  it('warns instead of reloading a form with unsaved edits', () => {
    // Spec v14 Decision 8. Losing typed configuration to another session's
    // save is worse than showing values a few seconds old -- and it is the
    // kind of loss noticed only after pressing save.
    boot();
    store.edit(store.fields()[0], '2.0');

    events.raise('settings');
    tick();

    backend.verify();
    expect(store.settingsStale()).toBe(true);
    expect(store.currentValue(store.fields()[0])).toBe('2.0');
  });

  it('discards the draft only when asked to', () => {
    boot();
    store.edit(store.fields()[0], '2.0');
    events.raise('settings');
    tick();

    store.discardDraftAndReload();
    backend.expectOne('/api/v1/system/settings').flush(SETTINGS);

    expect(store.dirty()).toBe(false);
    expect(store.settingsStale()).toBe(false);
  });

  /* -- import ------------------------------------------------------------- */

  it('names the keys an import skipped, not just the count', () => {
    // Someone importing an older export needs to know what did not land.
    boot();
    store.importSettings('RISK_PCT=2.0\nOLD_KEY=1\n');
    backend
      .expectOne('/api/v1/system/settings/import')
      .flush({ applied: 1, unknown_keys: ['OLD_KEY'] });
    backend.expectOne('/api/v1/system/settings').flush(SETTINGS);

    expect(store.importMessage()).toContain('OLD_KEY');
    expect(store.importMessage()).toContain('Applied 1');
  });

  /* -- logs --------------------------------------------------------------- */

  it('clears the tail when switching source, so the wrong log is never shown under the right heading', () => {
    boot();

    store.setLogSource('admin');
    expect(store.logs()).toBeNull();

    backend.expectOne('/api/v1/system/logs?source=admin').flush({
      source: 'admin',
      lines: 500,
      path: '/app/logs/admin.log',
      content: 'admin line',
    });
    expect(store.logs()?.content).toBe('admin line');
  });

  it('treats "no file to clear" as a message rather than a failure', () => {
    boot();

    store.clearLogs();
    backend
      .expectOne('/api/v1/system/logs?source=bot')
      .flush({ source: 'bot', ok: false, message: 'No log file to clear.' });

    // No refetch: there was nothing to clear, so the tail on screen is
    // still correct.
    backend.verify();
    expect(store.logsMessage()).toContain('No log file');
    expect(store.logsError()).toBeNull();
  });

  /* -- scan and restart --------------------------------------------------- */

  it('takes the new status from the command response, with no follow-up GET', () => {
    boot();

    store.runScanCommand('pause');
    backend.expectOne('/api/v1/system/scan/pause').flush({
      ok: true,
      message: 'Automatic scanning paused — manual !check still works.',
      scan: { ...SCAN, paused: true },
    });

    backend.verify();
    expect(store.scanPaused()).toBe(true);
    expect(store.scanMessage()).toContain('paused');
  });

  it('refetches the scan status on a bot event', () => {
    boot();

    events.raise('bot');
    tick();
    backend.expectOne('/api/v1/system/scan').flush({ ...SCAN, bot_alive: false });

    expect(store.botAlive()).toBe(false);
  });

  it('tells "cannot restart here" apart from "the restart failed"', () => {
    // The Docker socket mount is optional. A deployment that cannot restart
    // must not be reported as a restart that went wrong.
    boot();

    store.restartBot();
    backend.expectOne('/api/v1/system/bot/restart').flush(
      {
        error: {
          code: 'unavailable',
          message: 'Restarting needs the Docker socket mounted into the admin container.',
        },
      },
      { status: 503, statusText: 'Service Unavailable' },
    );

    expect(store.restartUnavailable()).toBe(true);
    expect(store.restartMessage()).toContain('Docker socket');
    expect(store.restarting()).toBe(false);
  });
});
