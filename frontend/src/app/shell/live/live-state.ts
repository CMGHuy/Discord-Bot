import { LiveHeat, Preferences } from '../../api/models';
import { ConnectionState } from '../../stores/connection.store';
import { ABSENT, amount, timeInZone } from '../../ui/format';
import { STALE_AFTER_SEC } from '../../ui/freshness';
import { scanAge } from '../freshness-chip';

/**
 * Live state, worded once -- v203 (spec v202 §3, §4, §6). The edge tab, the
 * strip, the alarm chip and the dock sections all read these, so a state
 * never reads two ways on two surfaces. Pure, and table-driven.
 */
export type LiveWarning = 'heat-near-cap' | 'over-cap' | 'stale' | 'disconnected' | 'bot-down' | 'killswitch';

export interface LiveWarningInput {
  utilisationPct: number | null; lastSuccess: string | null; now: Date;
  streamState: ConnectionState; botAlive: boolean | null; killswitchOn: boolean | null;
}

export type AlarmKind = 'bot-down' | 'disconnected' | 'stale';
export interface Alarm { kind: AlarmKind; text: string; }
export type HeatTone = 'unknown' | 'ok' | 'near' | 'over';

const NEAR_CAP_PCT = 80;
const MINUTE_MS = 60_000;
const BERLIN = 'Europe/Berlin';

/** True when `lastSuccess` is absent, unreadable or older than the window. */
export function isStale(lastSuccess: string | null, now: Date, staleAfterSec = STALE_AFTER_SEC): boolean {
  const at = lastSuccess ? Date.parse(lastSuccess) : Number.NaN;
  return Number.isNaN(at) || (now.getTime() - at) / 1000 > staleAfterSec;
}

/** Amber from 80 % of the cap, "over" above 100 %. Never clamped, never red (Phase 1). */
export function heatTone(utilisationPct: number | null): HeatTone {
  if (utilisationPct === null || !Number.isFinite(utilisationPct)) return 'unknown';
  if (utilisationPct > 100) return 'over';
  return utilisationPct >= NEAR_CAP_PCT ? 'near' : 'ok';
}

const disconnected = (state: ConnectionState) => state === 'dead' || state === 'degraded';
/** Stale counts only once /health has answered: a cold load is not an alarm. */
const staleAfterHealth = (i: { botAlive: boolean | null; lastSuccess: string | null; now: Date }) =>
  i.botAlive !== null && isStale(i.lastSuccess, i.now);

const WARNING_RULES: readonly (readonly [LiveWarning, (i: LiveWarningInput) => boolean])[] = [
  ['heat-near-cap', (i) => heatTone(i.utilisationPct) === 'near'],
  ['over-cap', (i) => heatTone(i.utilisationPct) === 'over'],
  ['stale', staleAfterHealth],
  ['disconnected', (i) => disconnected(i.streamState)],
  ['bot-down', (i) => i.botAlive === false],
  ['killswitch', (i) => i.killswitchOn === true],
];

const WARNING_LABELS: Readonly<Record<LiveWarning, string>> = {
  'heat-near-cap': 'Heat near cap', 'over-cap': 'Over cap', stale: 'Data stale',
  disconnected: 'Disconnected', 'bot-down': 'Bot down', killswitch: 'Killswitch active',
};

/** Every warning that applies, in the type's fixed order. */
export function liveWarnings(input: LiveWarningInput): LiveWarning[] {
  return WARNING_RULES.filter(([, applies]) => applies(input)).map(([warning]) => warning);
}

export function warningLabel(warning: LiveWarning): string {
  return WARNING_LABELS[warning];
}

/** 'Data stale 12 min' / '… 5h' / '… 2d'; plain 'Data stale' with no time. */
function staleText(lastSuccess: string | null, now: Date): string {
  const at = lastSuccess ? Date.parse(lastSuccess) : Number.NaN;
  if (Number.isNaN(at)) return 'Data stale';
  const minutes = Math.floor(Math.max(0, now.getTime() - at) / MINUTE_MS);
  if (minutes < 60) return `Data stale ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `Data stale ${hours}h` : `Data stale ${Math.floor(hours / 24)}d`;
}

type AlarmInput = Omit<LiveWarningInput, 'utilisationPct' | 'killswitchOn'>;
const ALARM_RULES: readonly (readonly [AlarmKind, (i: AlarmInput) => boolean, (i: AlarmInput) => string])[] = [
  ['bot-down', (i) => i.botAlive === false, () => 'Bot down'],
  ['disconnected', (i) => disconnected(i.streamState), () => 'Disconnected'],
  ['stale', staleAfterHealth, (i) => staleText(i.lastSuccess, i.now)],
];

/** The top bar's alarm (spec v202 §3): only while it applies, else null. */
export function alarmFor(input: AlarmInput): Alarm | null {
  const rule = ALARM_RULES.find(([, applies]) => applies(input));
  return rule ? { kind: rule[0], text: rule[2](input) } : null;
}

const percent = (value: number) => `${Number(value.toFixed(1))}%`;

/** 'Heat 2,010 € · 4.2% / 6%', plus ' · Over cap' above 100 %; 'Heat —' when unknown.
 *  Money goes through the app's `amount()` (ui/format.ts), unit after the figure. */
export function heatStripText(heat: LiveHeat | null, currency: string): string {
  if (heat?.availability !== 'ok' || heat.open_amount === null || heat.open_pct === null || heat.cap_pct === null) {
    return `Heat ${ABSENT}`;
  }
  const text = `Heat ${amount(heat.open_amount, currency, 0)} · ${percent(heat.open_pct)} / ${percent(heat.cap_pct)}`;
  return heatTone(heat.utilisation_pct) === 'over' ? `${text} · Over cap` : text;
}

/** '14:32 · 6m ago': Berlin local time and the freshness chip's age wording. */
export function liveTime(iso: string | null, now: Date): string {
  const age = scanAge(iso, now.getTime());
  return age === null ? ABSENT : `${timeInZone(iso, BERLIN)} · ${age}`;
}

/* -- the dock's open/collapsed preference (spec v202 §4, D4) ------------- */

export const DOCK_PREF_KEY = 'shell.dock';
export const DOCK_DEFAULT_OPEN: ReadonlySet<string> = new Set(['/dashboard', '/risk']);

export function dockDefaultOpen(destination: string | null): boolean {
  return destination !== null && DOCK_DEFAULT_OPEN.has(destination);
}

function dockMap(prefs: Preferences): Record<string, unknown> {
  const raw = prefs[DOCK_PREF_KEY];
  return raw !== null && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
}

/** The stored choice for one destination; anything but a boolean is the fallback. */
export function readDockOpen(prefs: Preferences, destination: string, fallback: boolean): boolean {
  const stored = dockMap(prefs)[destination];
  return typeof stored === 'boolean' ? stored : fallback;
}

/** A new preferences object with this destination's choice set. */
export function writeDockOpen(prefs: Preferences, destination: string, open: boolean): Preferences {
  return { ...prefs, [DOCK_PREF_KEY]: { ...dockMap(prefs), [destination]: open } };
}
