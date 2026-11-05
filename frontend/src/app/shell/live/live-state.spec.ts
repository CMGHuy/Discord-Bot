import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { LiveHeat } from '../../api/models';
import { STALE_AFTER_SEC } from '../../ui/freshness';
import {
  DOCK_DEFAULT_OPEN, DOCK_PREF_KEY, LiveWarning, LiveWarningInput, alarmFor, dockDefaultOpen, heatStripText, heatTone,
  isStale, liveTime, liveWarnings, readDockOpen, warningLabel, writeDockOpen,
} from './live-state';

const NOW = new Date('2026-10-29T13:00:00Z');            // 14:00 in Berlin (CET)
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const calm: LiveWarningInput = { utilisationPct: 50, lastSuccess: ago(2), now: NOW, streamState: 'live', botAlive: true, killswitchOn: false };
const heat = (over: Partial<LiveHeat> = {}): LiveHeat => ({
  availability: 'ok', as_of: ago(0), reason: null, open_pct: 4.2, cap_pct: 6, utilisation_pct: 70, open_amount: 2010.4,
  cap_amount: 2893, headroom_pct: 1.8, headroom_amount: 883, balance: 48210, includes_resting: true, ...over,
});

describe('the stale rule (one 900 s rule, ui/freshness.ts)', () => {
  it('exports 900 s and freshness.ts uses it as its default', () => {
    expect(STALE_AFTER_SEC).toBe(900);
    expect(readFileSync(join(process.cwd(), 'src/app/ui/freshness.ts'), 'utf8')).toContain('input<number>(STALE_AFTER_SEC)');
  });
  it.each([[null, true], ['not a time', true], [ago(14), false], [ago(15), false], [ago(16), true]])(
    'isStale(%s) is %s', (at, stale) => expect(isStale(at, NOW)).toBe(stale));
  it('takes another window when given one', () => expect(isStale(ago(3), NOW, 60)).toBe(true));
});

describe('heatTone: amber from 80 %, over above 100 %, never clamped', () => {
  it.each([[null, 'unknown'], [Number.NaN, 'unknown'], [0, 'ok'], [79.9, 'ok'], [80, 'near'], [100, 'near'], [100.1, 'over'], [130, 'over']])(
    '%s -> %s', (pct, tone) => expect(heatTone(pct as number | null)).toBe(tone));
});

describe('liveWarnings', () => {
  it('raises nothing on a calm book', () => expect(liveWarnings(calm)).toEqual([]));
  it.each<[Partial<LiveWarningInput>, LiveWarning[]]>([
    [{ utilisationPct: 85 }, ['heat-near-cap']],
    [{ utilisationPct: 130 }, ['over-cap']],
    [{ lastSuccess: ago(20) }, ['stale']],
    [{ lastSuccess: null }, ['stale']],
    [{ streamState: 'degraded' }, ['disconnected']],
    [{ streamState: 'dead' }, ['disconnected']],
    [{ streamState: 'connecting' }, []],
    [{ botAlive: false }, ['bot-down']],
    [{ killswitchOn: true }, ['killswitch']],
    [{ killswitchOn: null }, []],
  ])('%o -> %o', (change, expected) => expect(liveWarnings({ ...calm, ...change })).toEqual(expected));
  it('raises no stale alarm before /health answers', () => {
    expect(liveWarnings({ ...calm, botAlive: null, lastSuccess: null })).toEqual([]);
  });
  it('lists every warning at once, in the fixed order', () => {
    expect(liveWarnings({ utilisationPct: 101, lastSuccess: ago(300), now: NOW, streamState: 'dead', botAlive: false, killswitchOn: true }))
      .toEqual(['over-cap', 'stale', 'disconnected', 'bot-down', 'killswitch']);
  });
  it('names each warning', () => {
    expect((['heat-near-cap', 'over-cap', 'stale', 'disconnected', 'bot-down', 'killswitch'] as LiveWarning[]).map(warningLabel))
      .toEqual(['Heat near cap', 'Over cap', 'Data stale', 'Disconnected', 'Bot down', 'Killswitch active']);
  });
});

describe('alarmFor: the top bar alarm, in exactly three conditions', () => {
  const base = { lastSuccess: ago(2), now: NOW, streamState: 'live' as const, botAlive: true };
  it('is null when nothing is wrong, and before /health answers', () => {
    expect(alarmFor(base)).toBeNull();
    expect(alarmFor({ ...base, botAlive: null, lastSuccess: null })).toBeNull();
  });
  it.each([[16, 'Data stale 16 min'], [59, 'Data stale 59 min'], [300, 'Data stale 5h'], [3000, 'Data stale 2d']])(
    'words a %s-minute-old success as %s', (min, text) => expect(alarmFor({ ...base, lastSuccess: ago(min) })).toEqual({ kind: 'stale', text }));
  it('words a missing success as plain Data stale', () => {
    expect(alarmFor({ ...base, lastSuccess: null })).toEqual({ kind: 'stale', text: 'Data stale' });
  });
  it('puts bot-down over disconnected over stale', () => {
    const all = { ...base, lastSuccess: ago(60), streamState: 'dead' as const, botAlive: false };
    expect(alarmFor(all)).toEqual({ kind: 'bot-down', text: 'Bot down' });
    expect(alarmFor({ ...all, botAlive: true })).toEqual({ kind: 'disconnected', text: 'Disconnected' });
  });
});

describe('heatStripText', () => {
  it('reads dollars, then percent against the cap', () => expect(heatStripText(heat(), '$')).toBe('Heat 2,010 $ · 4.2% / 6%'));
  it('adds Over cap above 100 % and never clamps', () => {
    expect(heatStripText(heat({ open_amount: 3100, open_pct: 7.8, utilisation_pct: 130 }), '$')).toBe('Heat 3,100 $ · 7.8% / 6% · Over cap');
    expect(heatStripText(heat({ utilisation_pct: 100 }), '€')).toBe('Heat 2,010 € · 4.2% / 6%');
  });
  it.each([['null', null], ['unavailable', heat({ availability: 'unavailable' })], ['no amount', heat({ open_amount: null })],
    ['no cap', heat({ cap_pct: null })]])('prints Heat — for %s', (_, value) => expect(heatStripText(value, '$')).toBe('Heat —'));
});

describe('liveTime', () => {
  it('prints Berlin time and the age', () => expect(liveTime(ago(6), NOW)).toBe('13:54 · 6m ago'));
  it('crosses into summer time correctly', () => {
    expect(liveTime('2026-07-01T07:00:00Z', new Date('2026-07-01T12:00:00Z'))).toBe('09:00 · 5h ago');
  });
  it.each([[null], [''], ['garbage']])('prints — for %s', (iso) => expect(liveTime(iso, NOW)).toBe('—'));
});

describe('the dock preference (shell.dock, keyed by destination)', () => {
  it('opens on Dashboard and Risk only by default', () => {
    expect([...DOCK_DEFAULT_OPEN]).toEqual(['/dashboard', '/risk']);
    expect(['/dashboard', '/risk', '/trades', '/insights', '/system', null].map(dockDefaultOpen))
      .toEqual([true, true, false, false, false, false]);
  });
  it('reads a stored boolean, else the fallback', () => {
    const prefs = { [DOCK_PREF_KEY]: { '/trades': true, '/risk': 'yes' } };
    expect(readDockOpen(prefs, '/trades', false)).toBe(true);
    expect(readDockOpen(prefs, '/risk', true)).toBe(true);
    expect(readDockOpen(prefs, '/watchlist', false)).toBe(false);
    for (const junk of [null, 'open', ['/trades'], 7]) {
      expect(readDockOpen({ [DOCK_PREF_KEY]: junk }, '/trades', false), String(junk)).toBe(false);
    }
    expect(readDockOpen({}, '/dashboard', true)).toBe(true);
  });
  it('writes a new object, keeping other keys and destinations', () => {
    const before = { 'x.other': 1, [DOCK_PREF_KEY]: { '/risk': false } };
    const after = writeDockOpen(before, '/trades', true);
    expect(after).toEqual({ 'x.other': 1, [DOCK_PREF_KEY]: { '/risk': false, '/trades': true } });
    expect(before[DOCK_PREF_KEY]).toEqual({ '/risk': false });
    expect(writeDockOpen({ [DOCK_PREF_KEY]: 'junk' }, '/risk', true)).toEqual({ [DOCK_PREF_KEY]: { '/risk': true } });
  });
});
