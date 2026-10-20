import { QuoteStamp } from '../../api/models';

const KIND_WORDS: Record<string, string> = {
  trade: 'Live trade',
  mid: 'Bid/ask mid',
  'yf-1m': 'Yahoo 1-min bar',
};

/** v171 D2/D5: the price a posted plan was built from, as one line. The
 *  admin twin of the Discord embed's quote line (alert_embeds.quote_line). */
export function quoteLine(q: QuoteStamp | null | undefined): string {
  if (!q) return 'n/a';
  const session = q.session && q.session !== 'regular' ? `, ${q.session}` : '';
  if (q.confirmed === false || q.kind === 'scan') return `Price not confirmed live${session}`;
  if (q.kind === null) return 'n/a';
  const age = q.age_s === null ? '' : `, ${q.age_s.toFixed(1)} s to post`;
  return `${KIND_WORDS[q.kind] ?? q.kind}${age}${session}`;
}
