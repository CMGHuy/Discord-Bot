import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveKillswitch } from '../../api/models';
import { BotSectionInput, LiveBotSection, botRows, killswitchText } from './live-bot-section';

const NOW = new Date('2026-10-29T13:00:00Z');              // 14:00 Berlin
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const killswitch = (over: Partial<LiveKillswitch> = {}): LiveKillswitch => ({
  availability: 'ok', as_of: ago(0), reason: null, engaged: false, since: null, detail: null, ...over,
});
const healthy: BotSectionInput = {
  botAlive: true, botHealthy: true, scanRunning: false, lastSuccess: ago(6), lastSeen: ago(1),
  streamState: 'live', marketActive: true, killswitch: killswitch(), now: NOW,
};
const value = (input: BotSectionInput, key: string) => botRows(input).find((row) => row.key === key)!;

describe('botRows (spec v202 §4 Bot, §6)', () => {
  it('lists the six rows in order', () => {
    expect(botRows(healthy).map((row) => [row.label, row.value])).toEqual([
      ['Scanner', 'Idle'], ['Last scan', '13:54 · 6m ago'], ['Data', 'Scan 6m ago'],
      ['Event stream', 'Live'], ['Market', 'Open'], ['Killswitch', 'Clear'],
    ]);
    expect(botRows(healthy).some((row) => row.warn)).toBe(false);
  });

  it('claims nothing before the first answer', () => {
    const cold: BotSectionInput = { ...healthy, botAlive: null, botHealthy: null, lastSuccess: null, lastSeen: null,
      streamState: 'connecting', marketActive: null, killswitch: null };
    expect(botRows(cold).map((row) => row.value)).toEqual(['—', '—', '—', 'Connecting', '—', 'Killswitch ?']);
    expect(botRows(cold).some((row) => row.warn)).toBe(false);
  });

  it.each<[Partial<BotSectionInput>, string, boolean]>([
    [{ botAlive: false }, 'Down', true],
    [{ botHealthy: false }, 'Failing', true],
    [{ botAlive: false, botHealthy: false }, 'Down', true],
    [{ scanRunning: true }, 'Running', false],
    [{ botHealthy: null }, 'Idle', false],
  ])('words the scanner for %o as %s', (change, word, warn) => {
    expect(value({ ...healthy, ...change }, 'scanner')).toMatchObject({ value: word, warn });
  });

  it('warns on a stale last scan and data row, and still says when it was', () => {
    const stale = { ...healthy, lastSuccess: ago(300), lastSeen: ago(300) };
    expect(value(stale, 'last-scan')).toMatchObject({ value: '09:00 · 5h ago', warn: true });
    expect(value(stale, 'freshness')).toMatchObject({ value: 'Scan 5h ago', warn: true });
  });

  it('ages the data row from the last heartbeat when no tick ever succeeded', () => {
    expect(value({ ...healthy, lastSuccess: null, lastSeen: ago(2) }, 'freshness').value).toBe('Scan 2m ago');
    expect(value({ ...healthy, lastSuccess: null, lastSeen: null }, 'freshness')).toMatchObject({ value: 'No scan yet', warn: true });
  });

  it.each([['connecting', 'Connecting', false], ['live', 'Live', false], ['degraded', 'Polling (stream down)', true], ['dead', 'Offline', true]] as const)(
    'words the %s stream as %s', (state, word, warn) => {
      expect(value({ ...healthy, streamState: state }, 'stream')).toMatchObject({ value: word, warn });
    });

  it('reads the market as open or closed', () => {
    expect(value({ ...healthy, marketActive: false }, 'market')).toMatchObject({ value: 'Closed', warn: false });
  });
});

describe('killswitchText', () => {
  it.each<[LiveKillswitch | null, string]>([
    [killswitch({ engaged: true, since: '2026-10-29T08:31:00Z' }), 'Active: new alerts paused since 09:31'],
    [killswitch({ engaged: true, since: null }), 'Active: new alerts paused'],
    [killswitch({ engaged: false }), 'Clear'],
    [killswitch({ engaged: null }), 'Killswitch ?'],
    [killswitch({ availability: 'unavailable', engaged: null, reason: 'db down' }), 'Killswitch ?'],
    [null, 'Killswitch ?'],
  ])('%o reads %s', (state, text) => expect(killswitchText(state)).toBe(text));

  it('warns only while engaged', () => {
    expect(value({ ...healthy, killswitch: killswitch({ engaged: true }) }, 'killswitch').warn).toBe(true);
    expect(value({ ...healthy, killswitch: null }, 'killswitch').warn).toBe(false);
  });
});

describe('LiveBotSection', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function mount(input: BotSectionInput) {
    const fixture = TestBed.createComponent(LiveBotSection);
    for (const [key, val] of Object.entries(input)) fixture.componentRef.setInput(key, val);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders a titled section of label/value rows, warning rows marked', () => {
    const el = mount({ ...healthy, botAlive: false, killswitch: killswitch({ engaged: true, since: '2026-10-29T08:31:00Z' }) });
    const section = el.querySelector('section[aria-labelledby]')!;
    expect(section.querySelector(`#${section.getAttribute('aria-labelledby')}`)!.textContent!.trim()).toBe('Bot');
    const rows = [...el.querySelectorAll('dl > div.row')];
    expect(rows.map((row) => row.querySelector('dt')!.textContent!.trim()))
      .toEqual(['Scanner', 'Last scan', 'Data', 'Event stream', 'Market', 'Killswitch']);
    expect(rows.filter((row) => row.classList.contains('warn')).map((row) => row.querySelector('dt')!.textContent!.trim()))
      .toEqual(['Scanner', 'Killswitch']);
    expect(rows[5].querySelector('dd')!.textContent!.trim()).toBe('Active: new alerts paused since 09:31');
  });

  it('re-renders when an input changes', () => {
    const fixture = TestBed.createComponent(LiveBotSection);
    for (const [key, val] of Object.entries(healthy)) fixture.componentRef.setInput(key, val);
    fixture.detectChanges();
    fixture.componentRef.setInput('scanRunning', true);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('dl > div.row dd')!.textContent!.trim()).toBe('Running');
  });
});
