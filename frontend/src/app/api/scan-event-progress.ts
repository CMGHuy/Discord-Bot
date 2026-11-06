import { ScanEventProgress, ScanProgressRecord } from './models';

type Fields = Record<string, unknown>;

function isObject(value: unknown): value is Fields {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/** A complete `ScanProgressRecord` holding only its own fields, or null. */
function parseRecord(value: unknown): ScanProgressRecord | null {
  if (!isObject(value)) return null;
  const { at, pct, stage, current_ticker, done, total, qualifying_found } = value;
  const ticker = current_ticker === null || typeof current_ticker === 'string';
  if (typeof at !== 'string' || typeof stage !== 'string' || !ticker) return null;
  if (!isNumber(pct) || !isNumber(done) || !isNumber(total) || !isNumber(qualifying_found)) return null;
  return { at, pct, stage, current_ticker: current_ticker as string | null, done, total, qualifying_found };
}

/**
 * The validated payload of a `scan` SSE frame (v206 P1-c), or null.
 *
 * `frame` is the parsed JSON body, `{seq, at, progress?}`. Null means
 * "nothing usable": a thin frame (the server's read failed, or an older
 * server), or anything malformed. Never partial -- a record missing one
 * field is null as a whole, so the store falls back to `/system/scan`
 * instead of patching half a bar.
 */
export function parseScanEventProgress(frame: unknown): ScanEventProgress | null {
  const payload = isObject(frame) ? frame['progress'] : undefined;
  if (!isObject(payload)) return null;
  const { running, progress } = payload;
  if (typeof running !== 'boolean' || progress === undefined) return null;
  if (progress === null) return { running, progress: null };
  const record = parseRecord(progress);
  return record === null ? null : { running, progress: record };
}
