import { LiveEvent, LiveEventKind, LiveEventsMeta, LiveTone } from '../../api/models';
import { MINUS, amount, timeInZone } from '../../ui/format';
import { scanAge } from '../freshness-chip';
import { isStale, liveTime } from './live-state';

export interface PnlParts { r: string; amount: string | null; }
export interface ActivityRow { key: string; time: string; text: string; tone: LiveTone; pnl: PnlParts | null; line: string; }
export interface ActivityView {
  state: 'loading' | 'unavailable' | 'ok'; rows: ActivityRow[];
  missing: string | null; scanWarning: string | null; quiet: boolean;
}

const DEFAULT_CURRENCY = '€';           // ConnectionStore.currency()'s own fallback
const PAPER = '(paper, pre-cost)';
const KIND_WORDS: Readonly<Record<LiveEventKind, string>> = {
  plan_alerted: 'alerts', paper_filled: 'paper fills', tp1_hit: 'TP1 hits', trade_closed: 'closes', killswitch: 'killswitch',
};

function signOf(value: number): string {
  if (value > 0) return '+';
  return value < 0 ? MINUS : '';
}

/** '+2.1R' and '441 €' (unsigned: the R carries the sign); null without P&L. */
export function pnlParts(pnl: LiveEvent['pnl'], currency: string): PnlParts | null {
  if (pnl === null) return null;
  return {
    r: `${signOf(pnl.r)}${Math.abs(pnl.r).toFixed(1)}R`,
    amount: pnl.amount === null ? null : amount(Math.abs(pnl.amount), currency, 0),
  };
}

/** The row's one line: the server's text, then ' · +2.1R (441 €) (paper, pre-cost)' for a P&L row. */
export function activityLine(e: LiveEvent, currency: string = DEFAULT_CURRENCY): string {
  const parts = pnlParts(e.pnl, currency);
  if (parts === null) return e.text;
  return parts.amount === null ? `${e.text} · ${parts.r} ${PAPER}` : `${e.text} · ${parts.r} (${parts.amount}) ${PAPER}`;
}

/** 'Some sources unavailable: TP1 hits' for a partial read; null otherwise. */
export function missingText(meta: LiveEventsMeta | null): string | null {
  if (meta?.availability !== 'partial') return null;
  const words = meta.missing.map((kind) => KIND_WORDS[kind]);
  return words.length ? `Some sources unavailable: ${words.join(', ')}` : 'Some sources unavailable';
}

/** 'No scan since 09:00 (5h ago)' once the last success is past the 900 s rule; null while fresh. */
function scanWarning(lastSuccess: string | null, now: Date): string | null {
  if (!isStale(lastSuccess, now)) return null;
  const age = scanAge(lastSuccess, now.getTime());
  return age === null ? 'No scan yet' : `No scan since ${timeInZone(lastSuccess, 'Europe/Berlin')} (${age})`;
}

function activityState(meta: LiveEventsMeta | null, loading: boolean): ActivityView['state'] {
  if (meta === null) return loading ? 'loading' : 'unavailable';
  return meta.availability === 'unavailable' ? 'unavailable' : 'ok';
}

function rowOf(e: LiveEvent, now: Date, currency: string): ActivityRow {
  return {
    key: `${e.at}|${e.kind}|${e.ref ?? ''}`, time: liveTime(e.at, now), text: e.text, tone: e.tone,
    pnl: pnlParts(e.pnl, currency), line: activityLine(e, currency),
  };
}

/** What the section shows (spec v202 §6): a missed scan is never a quiet day. */
export function activityView(
  events: readonly LiveEvent[], meta: LiveEventsMeta | null, loading: boolean,
  lastSuccess: string | null, now: Date, currency: string,
): ActivityView {
  const rows = events.map((e) => rowOf(e, now, currency));
  const warning = scanWarning(lastSuccess, now);
  const state = activityState(meta, loading);
  return { state, rows, missing: missingText(meta), scanWarning: warning, quiet: state === 'ok' && rows.length === 0 && warning === null };
}
