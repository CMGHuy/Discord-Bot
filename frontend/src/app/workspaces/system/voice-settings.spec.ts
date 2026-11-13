import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { FeedKindFamily } from '../../api/models';
import { FakeSpeech, fakeUtterance } from '../../voice/fake-speech';
import { VOICE_STORAGE, VOICE_STORAGE_KEY } from '../../voice/voice-prefs';
import { SPEECH, UTTERANCE, VoiceSpeaker } from '../../voice/voice-speaker';
import { NO_VOICE_NOTE, VOICE_OFF_REASON, VoiceSettings, familyRow, spokenHint } from './voice-settings';

const KINDS_URL = '/api/v1/feed-posts/kinds';

function families(): FeedKindFamily[] {
  return [
    {
      family: 'ENTRY', label: 'Entry', default_on: true,
      kinds: [
        { kind: 'FILLED', label: 'FILLED', phrase: 'Order filled', sample: 'Order filled, AAPL' },
        { kind: 'ENTRY_TRIGGERED', label: 'ENTRY TRIGGERED', phrase: 'Entry triggered', sample: 'Entry triggered, AAPL' },
      ],
    },
    {
      family: 'WATCH', label: 'Watch', default_on: false,
      kinds: [
        { kind: 'NEAR_STOP', label: 'NEAR STOP', phrase: 'Near stop', sample: 'Near stop, AAPL' },
        { kind: 'NEAR_TP', label: 'NEAR TARGET', phrase: 'Near target', sample: 'Near target, AAPL' },
      ],
    },
  ];
}

function mount(stored: string | null = null, speech: FakeSpeech | null = new FakeSpeech()) {
  const map = new Map<string, string>();
  if (stored !== null) map.set(VOICE_STORAGE_KEY, stored);
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: SPEECH, useValue: speech },
      { provide: UTTERANCE, useValue: fakeUtterance },
      {
        provide: VOICE_STORAGE,
        useValue: {
          get: (key: string) => map.get(key) ?? null,
          set: (key: string, value: string) => {
            map.set(key, value);
          },
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(VoiceSettings);
  fixture.detectChanges();
  const backend = TestBed.inject(HttpTestingController);
  const el = fixture.nativeElement as HTMLElement;
  const saved = () => JSON.parse(map.get(VOICE_STORAGE_KEY) ?? '{}');
  return { fixture, backend, el, speech, saved };
}

async function loaded(stored: string | null = null, speech: FakeSpeech | null = new FakeSpeech()) {
  const ctx = mount(stored, speech);
  ctx.backend.expectOne(KINDS_URL).flush({ families: families() });
  await ctx.fixture.whenStable();
  ctx.fixture.detectChanges();
  return ctx;
}

function switchNamed(el: HTMLElement, label: string): HTMLButtonElement {
  const found = [...el.querySelectorAll<HTMLButtonElement>('button[role="switch"]')]
    .find((button) => button.textContent!.trim() === label);
  if (!found) throw new Error(`no switch labelled ${label}`);
  return found;
}

function click(fixture: { detectChanges(): void }, button: HTMLButtonElement): void {
  button.click();
  fixture.detectChanges();
}

describe('VoiceSettings (v227)', () => {
  it('renders the block heading and the master switch, on by default', async () => {
    const { el } = await loaded();
    expect(el.querySelector('h2')!.textContent!.trim()).toBe('Voice notifications');
    expect(switchNamed(el, 'Speak simple-channel posts').getAttribute('aria-checked')).toBe('true');
    expect(el.textContent).not.toContain(VOICE_OFF_REASON);
    expect(el.querySelector('details.voice')!.hasAttribute('open')).toBe(true);
  });

  it('starts every family on except Watch', async () => {
    const { el } = await loaded();
    expect(switchNamed(el, 'Entry').getAttribute('aria-checked')).toBe('true');
    expect(switchNamed(el, 'FILLED').getAttribute('aria-checked')).toBe('true');
    expect(switchNamed(el, 'Watch').getAttribute('aria-checked')).toBe('false');
    expect(switchNamed(el, 'NEAR STOP').getAttribute('aria-checked')).toBe('false');
  });

  it('master off saves, greys every switch below it, and says why', async () => {
    const { el, fixture, saved } = await loaded();
    click(fixture, switchNamed(el, 'Speak simple-channel posts'));
    expect(saved().enabled).toBe(false);
    expect(switchNamed(el, 'Speak simple-channel posts').disabled).toBe(false);
    for (const label of ['Entry', 'FILLED', 'ENTRY TRIGGERED', 'Watch', 'NEAR STOP', 'NEAR TARGET']) {
      expect(switchNamed(el, label).disabled).toBe(true);
    }
    expect(el.textContent).toContain(VOICE_OFF_REASON);
  });

  it('a kind switch saves just that kind and leaves its family mixed', async () => {
    const { el, fixture, saved } = await loaded();
    click(fixture, switchNamed(el, 'FILLED'));
    expect(saved().kinds).toEqual({ FILLED: false });
    expect(switchNamed(el, 'FILLED').getAttribute('aria-checked')).toBe('false');
    expect(switchNamed(el, 'Entry').getAttribute('aria-checked')).toBe('mixed');
  });

  it('a mixed family switch turns the whole family on in one save', async () => {
    const { el, fixture, saved } = await loaded(JSON.stringify({ kinds: { FILLED: false } }));
    expect(switchNamed(el, 'Entry').getAttribute('aria-checked')).toBe('mixed');
    click(fixture, switchNamed(el, 'Entry'));
    expect(saved().kinds).toEqual({ FILLED: true, ENTRY_TRIGGERED: true });
    expect(switchNamed(el, 'Entry').getAttribute('aria-checked')).toBe('true');
  });

  it('the Watch switch turns both near-stop and near-target on', async () => {
    const { el, fixture, saved } = await loaded();
    click(fixture, switchNamed(el, 'Watch'));
    expect(saved().kinds).toEqual({ NEAR_STOP: true, NEAR_TP: true });
    expect(switchNamed(el, 'NEAR TARGET').getAttribute('aria-checked')).toBe('true');
  });

  it('shows under each kind what will be spoken', async () => {
    const { el } = await loaded();
    const hintId = switchNamed(el, 'FILLED').getAttribute('aria-describedby')!;
    expect(el.querySelector(`#${hintId}`)!.textContent!.trim()).toBe('Says: Order filled, <ticker>');
  });

  it('falls back to the defaults on a garbled store', async () => {
    const { el } = await loaded('{not json');
    expect(switchNamed(el, 'Speak simple-channel posts').getAttribute('aria-checked')).toBe('true');
    expect(switchNamed(el, 'Watch').getAttribute('aria-checked')).toBe('false');
    expect(switchNamed(el, 'Entry').getAttribute('aria-checked')).toBe('true');
  });

  it('keeps the master switch working while the kinds load and after they fail', async () => {
    const { el, fixture, backend, saved } = mount();
    expect(el.querySelector('sb-spinner')).toBeTruthy();
    backend.expectOne(KINDS_URL).flush({ error: { code: 'unavailable', message: 'x' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelector('sb-panel-error')).toBeTruthy();
    expect(el.querySelector('sb-spinner')).toBeNull();
    click(fixture, switchNamed(el, 'Speak simple-channel posts'));
    expect(saved().enabled).toBe(false);
    click(fixture, el.querySelector<HTMLButtonElement>('sb-panel-error button')!);
    backend.expectOne(KINDS_URL).flush({ families: families() });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelector('sb-panel-error')).toBeNull();
    expect(switchNamed(el, 'FILLED')).toBeTruthy();
  });
});

describe('familyRow (v227)', () => {
  const entry = families()[0];

  it('is all on, mixed or all off from the kind flags', () => {
    expect(familyRow(entry, () => true)).toMatchObject({ allOn: true, mixed: false });
    expect(familyRow(entry, (kind) => kind === 'FILLED')).toMatchObject({ allOn: false, mixed: true });
    expect(familyRow(entry, () => false)).toMatchObject({ allOn: false, mixed: false });
  });

  it('is neither on nor mixed for a family with no kinds', () => {
    expect(familyRow({ ...entry, kinds: [] }, () => true)).toMatchObject({ allOn: false, mixed: false, kinds: [] });
  });

  it('carries the spoken hint for every kind', () => {
    expect(familyRow(entry, () => true).kinds.map((kind) => kind.hint)).toEqual([
      'Says: Order filled, <ticker>',
      'Says: Entry triggered, <ticker>',
    ]);
    expect(spokenHint('Near stop')).toBe('Says: Near stop, <ticker>');
  });
});

describe('VoiceSettings layout (v227)', () => {
  const source = readFileSync(join(process.cwd(), 'src/app/workspaces/system/voice-settings.ts'), 'utf8');

  it('stacks the families on a phone and sets two columns from the 640px breakpoint', () => {
    expect(source).toMatch(/\.families \{[^}]*grid-template-columns: minmax\(0, 1fr\);/);
    expect(source).toMatch(/@media \(min-width: 640px\) \{\s*\.families \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/);
  });

  it('never truncates a label and explains nothing through title', () => {
    expect(source).not.toMatch(/text-overflow|white-space: nowrap/);
    expect(source).not.toMatch(/\stitle=/);
  });
});

describe('VoiceSettings previews and the no-voice note (v227)', () => {
  it('previews a kind sample on tap, without unlocking the chip', async () => {
    const speech = new FakeSpeech();
    const { el } = await loaded(null, speech);
    const preview = el.querySelector<HTMLButtonElement>('button[aria-label="Preview FILLED"]')!;
    expect(preview.disabled).toBe(false);
    expect(preview.textContent!.trim()).toBe('▶');
    preview.click();
    expect(speech.texts()).toEqual(['Order filled, AAPL']);
    expect(TestBed.inject(VoiceSpeaker).state()).toBe('locked');
  });

  it('has one preview per kind, all disabled while the master is off', async () => {
    const { el, fixture } = await loaded();
    const previews = () => [...el.querySelectorAll<HTMLButtonElement>('button.preview')];
    expect(previews().length).toBe(4);
    click(fixture, switchNamed(el, 'Speak simple-channel posts'));
    expect(previews().every((button) => button.disabled)).toBe(true);
  });

  it('says so when this browser has no voice, and disables the previews', async () => {
    const { el } = await loaded(null, null);
    const status = el.querySelector('.master [role="status"]')!;
    expect(status.textContent!.trim()).toBe(NO_VOICE_NOTE);
    expect(el.textContent).not.toContain(VOICE_OFF_REASON);
    const previews = [...el.querySelectorAll<HTMLButtonElement>('button.preview')];
    expect(previews.length).toBe(4);
    expect(previews.every((button) => button.disabled)).toBe(true);
  });

  it('gives the preview a full hit area', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/workspaces/system/voice-settings.ts'), 'utf8');
    expect(source).toMatch(/\.preview \{[^}]*min-width: var\(--hit-min\);/);
  });
});
