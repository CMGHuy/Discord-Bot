import type { CandlestickData, Time, UTCTimestamp } from 'lightweight-charts';

import { EquityBasis, EquityCandle, EquityTimeframe } from '../../../api/models';
import { money, num, pct } from '../../../ui/format';
import { LogicalWindow, PnlTone, RangeStats, drawdownTone, signTone } from './equity-range.model';

/**
 * Pure helpers for `sb-equity-candles` — spec v172 § 5. Everything here is
 * testable without a canvas; the component only wires these to the chart.
 */

export const BASIS_LABEL: Record<EquityBasis, string> = {
  mtm: 'Open + closed',
  realized: 'Closed trades only',
};

/** v172 correction 7: `realized_pnl_amount` carries no slippage or
 *  commission, so the label states both exclusions. */
export const ACCOUNT_LABEL = 'Paper account · before tax and costs';
export const SEAM_LABEL = 'Recording started';
const CHANGE_PART_SUFFIX = 'vs prev close';

/** True for the readout part that carries the % change (it gets the tooltip). */
export const isChangePart = (part: string): boolean => part.endsWith(CHANGE_PART_SUFFIX);

export const CHANGE_PCT_TOOLTIP = "Change from the previous candle's close, not a return on capital";

const NY = 'America/New_York';
const DAY = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric' });
const NY_DAY = new Intl.DateTimeFormat('en-US', { timeZone: NY, month: 'short', day: 'numeric', year: 'numeric' });

export interface CandleColors {
  up: string;
  down: string;
  faint: string;
}

export function isIntraday(tf: EquityTimeframe): boolean {
  return tf === '1H' || tf === '4H';
}

/** Business-day string for 1D/1W; for 1H/4H the New York wall time read as
 *  if it were UTC, so the axis shows New York hours in every viewer zone. */
export function toChartTime(t: string, tf: EquityTimeframe): Time {
  if (!isIntraday(tf)) return t.slice(0, 10) as Time;
  return Math.floor(Date.parse(`${t.slice(0, 19)}Z`) / 1000) as UTCTimestamp;
}

export function toSeriesData(
  candles: readonly EquityCandle[],
  tf: EquityTimeframe,
  colors: CandleColors,
): CandlestickData<Time>[] {
  const out: CandlestickData<Time>[] = [];
  let last = Number.NEGATIVE_INFINITY;
  for (const candle of candles) {
    let time = toChartTime(candle.t, tf);
    if (typeof time === 'number') {
      // The fall-back hour repeats on the wall clock (01:00 EDT, then 01:00
      // EST); the series must be strictly ascending, so a repeat sits 1s later.
      if (time <= last) time = (last + 1) as UTCTimestamp;
      last = time;
    }
    const point: CandlestickData<Time> = { time, open: candle.o, high: candle.h, low: candle.l, close: candle.c };
    if (candle.approx) {
      // Hollow: rebuilt from daily bars, its range is an outer bound.
      point.color = 'transparent';
      point.borderColor = candle.c >= candle.o ? colors.up : colors.down;
      point.wickColor = colors.faint;
    }
    out.push(point);
  }
  return out;
}

function dayLabel(ymd: string): string {
  return DAY.format(new Date(`${ymd}T00:00:00Z`));
}

/** The New York calendar date of an instant. */
function recordingDate(iso: string): string {
  return NY_DAY.format(new Date(iso));
}

export function candleLabel(t: string, tf: EquityTimeframe): string {
  if (tf === '1W') return `Week of ${dayLabel(t.slice(0, 10))}`;
  if (tf === '1D') return dayLabel(t.slice(0, 10));
  return `${dayLabel(t.slice(0, 10))} ${t.slice(11, 16)} ET`;
}

function skippedNote(skipped: number): string {
  return `${skipped} position${skipped === 1 ? '' : 's'} not counted`;
}

export function readoutParts(
  candle: EquityCandle,
  basis: EquityBasis,
  currency: string,
  tf: EquityTimeframe,
): string[] {
  const parts = [
    candleLabel(candle.t, tf),
    `O ${num(candle.o)}`,
    `H ${num(candle.h)}`,
    `L ${num(candle.l)}`,
    `C ${num(candle.c)}`,
    money(candle.change, currency),
    `${pct(candle.change_pct)} ${CHANGE_PART_SUFFIX}`,
    BASIS_LABEL[basis],
  ];
  if (candle.approx) parts.push('approx');
  if (candle.skipped > 0) parts.push(skippedNote(candle.skipped));
  return parts;
}

export function emptyMessage(tf: EquityTimeframe, recordingSince: string | null): string {
  if (isIntraday(tf) && recordingSince) {
    return `No hourly samples yet — recording started ${recordingDate(recordingSince)}`;
  }
  return 'No equity samples yet';
}

export function approxCaption(recordingSince: string | null): string {
  const when = recordingSince ? recordingDate(recordingSince) : 'recording started';
  return `Before ${when}: rebuilt from daily bars — ranges are outer bounds`;
}

/** Index of the first recorded candle that follows a rebuilt one, or -1. */
export function seamIndex(candles: readonly EquityCandle[]): number {
  let sawApprox = false;
  for (let i = 0; i < candles.length; i++) {
    if (candles[i].approx) sawApprox = true;
    else if (sawApprox) return i;
  }
  return -1;
}

/** One readout segment and the colour it carries — spec v181 §5. The tone is
 *  decided here, never in the template, so the colour rule lives once. */
export interface ReadoutPart {
  text: string;
  tone: PnlTone;
}

/** v181 §4: the range summary's labels. "within range" on the drawdown on
 *  purpose: it is measured on closes, so it can be smaller than High→Low. */
export const RANGE_LABELS = {
  change: 'Equity change',
  high: 'High',
  low: 'Low',
  drawdown: 'Max drawdown within range',
} as const;

/** The hovered candle (v172 parts), its two change parts toned by sign. */
export function candleReadout(
  candle: EquityCandle,
  basis: EquityBasis,
  currency: string,
  tf: EquityTimeframe,
): ReadoutPart[] {
  const changeText = money(candle.change, currency);
  const tone = signTone(candle.change);
  return readoutParts(candle, basis, currency, tf).map((text) => ({
    text,
    tone: text === changeText || (isChangePart(text) && candle.change_pct !== null) ? tone : 'neutral',
  }));
}

function drawdownPart(pctValue: number | null): ReadoutPart {
  // Shown as a loss whichever sign the stats carry; an em dash is never coloured.
  if (pctValue === null) return { text: `${RANGE_LABELS.drawdown} —`, tone: 'neutral' };
  // Intl's decimal rounding matches the money/high/low readout at halfway values.
  const loss = pctValue === 0 ? 0 : -Math.abs(pctValue);
  return { text: `${RANGE_LABELS.drawdown} ${num(loss)}%`, tone: drawdownTone(pctValue) };
}

/** The visible range in one line — spec v181 §4. */
export function rangeReadoutParts(stats: RangeStats | null, currency: string): ReadoutPart[] {
  if (!stats) return [];
  const share = stats.changePct === null ? '' : ` (${pct(stats.changePct)})`;
  return [
    { text: `${RANGE_LABELS.change} ${money(stats.change, currency)}${share}`, tone: signTone(stats.change) },
    { text: `${RANGE_LABELS.high} ${num(stats.high)}`, tone: 'neutral' },
    { text: `${RANGE_LABELS.low} ${num(stats.low)}`, tone: 'neutral' },
    drawdownPart(stats.maxDrawdownPct),
  ];
}

/** True while the newest candle is at least half on screen (a bar spans
 *  ±0.5 logical units around its index), or before the first range event. */
export function isAtLiveEdge(range: LogicalWindow | null, count: number): boolean {
  return range === null || count === 0 || range.to >= count - 1.5;
}
