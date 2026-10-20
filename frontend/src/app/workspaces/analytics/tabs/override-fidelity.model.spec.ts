import { describe, expect, it } from 'vitest';

import {
  APPROX_LABEL, CAPTION, COUNTS_HINT, EMPTY_COPY, STATUS_LABEL, badgeCopy, badgeTone,
  exclusionNotes, isCounted, liveHint, netEffect, netTone, plural, recordedLine, signedR,
  signedUsd, waitingOnLine,
} from './override-fidelity.model';
import {
  OVERRIDE_FIDELITY_FIXTURE, VERDICT_FLOORS_MET, VERDICT_RECORDED_COST, VERDICT_WAITING_ON,
} from './override-fidelity.fixture';

const F = OVERRIDE_FIDELITY_FIXTURE;
const M = '\u2212';                              // the true minus the formatters print

describe('override-fidelity model', () => {
  it('pluralises a count of one and of many', () => {
    expect(plural(1, 'row', 'rows')).toBe('1 row');
    expect(plural(0, 'row', 'rows')).toBe('0 rows');
    expect(plural(15, 'close', 'closes')).toBe('15 closes');
  });

  it('signs dollars and R with a true minus, and prints a dash for none', () => {
    expect(signedUsd(59.35, '$')).toBe('+$59.35');
    expect(signedUsd(-1234.5, '€')).toBe(`${M}€1,234.50`);
    expect(signedUsd(0, '$')).toBe('$0.00');
    expect(signedUsd(null, '$')).toBe('—');
    expect(signedR(1.187)).toBe('+1.19 R');
    expect(signedR(-0.3)).toBe(`${M}0.30 R`);
    expect(signedR(null)).toBe('—');
  });

  it('leads the net effect with dollars, then R', () => {
    expect(netEffect(F.summary, '$')).toBe('+$59.35 · +1.19 R');
  });

  it('keeps the net-effect tile neutral while WAITING, whatever its sign', () => {
    expect(F.summary.sum_delta_r).toBeGreaterThan(0);
    expect(netTone(F.verdict, F.summary)).toBe('neutral');
    expect(netTone(VERDICT_FLOORS_MET, F.summary)).toBe('neutral');
    expect(netTone(VERDICT_RECORDED_COST, F.summary)).toBe('pos');               // live sum > 0
    expect(netTone(VERDICT_RECORDED_COST, { ...F.summary, sum_delta_r: -2.4 })).toBe('neg');
    expect(netTone(VERDICT_RECORDED_COST, { ...F.summary, sum_delta_r: 0 })).toBe('neutral');
  });

  it('words WAITING below the count floor as "N of 30 needed"', () => {
    expect(badgeCopy(F.verdict, '$')).toBe('1 of 30 needed. No conclusion yet.');
    expect(waitingOnLine(F.verdict)).toBeNull();                 // the count is the reason
  });

  it('words a met count with other floors failing as waiting on other conditions', () => {
    expect(badgeCopy(VERDICT_WAITING_ON, '$'))
      .toBe('34 of 30 counted. Waiting on other conditions. No conclusion yet.');
    expect(waitingOnLine(VERDICT_WAITING_ON)).toBe('Waiting on: at least 10 distinct weeks '
      + '(now 8); no open rows (now 2 open); left-out rows at most 20% (now 25%)');
    expect(waitingOnLine({ ...VERDICT_WAITING_ON, weeks: 11, excluded_share: 0.1, open_n: 1,
      waiting_on: ['open'] })).toBe('Waiting on: no open rows (now 1 open)');
  });

  it('words floors met but not yet recorded without a target or an action', () => {
    expect(badgeCopy(VERDICT_FLOORS_MET, '$'))
      .toBe('Floors met (34 of 30). Awaiting the one recorded evaluation. No conclusion yet.');
    expect(waitingOnLine(VERDICT_FLOORS_MET)).toBeNull();
    expect(recordedLine(VERDICT_FLOORS_MET)).toBeNull();
    expect(liveHint(VERDICT_FLOORS_MET)).toBeNull();
  });

  it('words a recorded verdict from the recorded figures, R and CI first', () => {
    const lead = `Overrides would have differed by ${M}0.22 R per override on average vs the engine `
      + `(95% CI [${M}0.24, ${M}0.20], 31 overrides).`;
    expect(badgeCopy(VERDICT_RECORDED_COST, '$')).toBe(
      `${lead} Modelled size, before tax: ${M}$1,364.00 summed over the recorded overrides.`);
    const saved = badgeCopy({ ...VERDICT_RECORDED_COST, state: 'SAVED', mean_delta_r: 0.04,
      ci: [0.01, 0.07], sum_delta_usd: 59.35 }, '$');
    expect(saved).toBe('Overrides would have differed by +0.04 R per override on average vs the '
      + 'engine (95% CI [+0.01, +0.07], 31 overrides). Modelled size, before tax: +$59.35 '
      + 'summed over the recorded overrides.');
    expect(badgeCopy({ ...VERDICT_RECORDED_COST, state: 'INCONCLUSIVE', mean_delta_r: -0.02,
      ci: [-0.05, 0.01] }, '$')).toBe('No clear difference vs the engine: mean '
      + `${M}0.02 R per override (95% CI [${M}0.05, +0.01], 31 overrides).`);
    expect(badgeCopy({ ...VERDICT_RECORDED_COST, sum_delta_usd: null }, '$')).toBe(lead);
    for (const state of ['COST', 'SAVED'] as const) {
      expect(badgeCopy({ ...VERDICT_RECORDED_COST, state }, '$')).not.toMatch(/\b(cost|saved)\b/i);
    }
    expect(waitingOnLine(VERDICT_RECORDED_COST)).toBeNull();
  });

  it('writes the recorded line, with the bar-close count pluralised', () => {
    const head = `Recorded on 2026-12-04 from 31 overrides over 12 weeks: mean ${M}0.22 R per `
      + `override, 95% CI ${M}0.24 to ${M}0.20 R. Before costs: ${M}0.20 R.`;
    expect(recordedLine(VERDICT_RECORDED_COST))
      .toBe(`${head} 2 overrides priced from a bar close, not a quote.`);
    expect(recordedLine({ ...VERDICT_RECORDED_COST, bar_close_n: 1 }))
      .toBe(`${head} 1 override priced from a bar close, not a quote.`);
    expect(recordedLine({ ...VERDICT_RECORDED_COST, bar_close_n: 0 })).toBe(head);
    expect(recordedLine(F.verdict)).toBeNull();
  });

  it('labels the live tiles once a verdict is recorded', () => {
    expect(liveHint(VERDICT_RECORDED_COST)).toBe('live, may have moved since recorded on 2026-12-04');
    expect(liveHint(F.verdict)).toBeNull();
  });

  it('tones only a recorded direction on the badge', () => {
    expect(badgeTone(F.verdict)).toBe('neutral');
    expect(badgeTone(VERDICT_FLOORS_MET)).toBe('neutral');
    expect(badgeTone(VERDICT_RECORDED_COST)).toBe('neg');
    expect(badgeTone({ ...VERDICT_RECORDED_COST, state: 'SAVED' })).toBe('pos');
    expect(badgeTone({ ...VERDICT_RECORDED_COST, state: 'INCONCLUSIVE' })).toBe('neutral');
  });

  it('writes one exclusion note per non-zero count, singular for one', () => {
    expect(exclusionNotes(F.summary, F.verdict)).toEqual([
      '1 close from one bulk clear on 2026-09-30 is not a decision, so it is left out',
      '1 estimated row is shown but not counted',
      '1 stale data row is left out',
    ]);
    expect(exclusionNotes(F.summary, { ...F.verdict, open_n: 1 })).toContain(
      '1 row is still open and not counted yet. No conclusion is recorded while any are open.');
  });

  it('writes the plural forms, in the order bulk, estimated, open, then statuses', () => {
    const many = { ...F.summary, bulk_dates: { '2026-09-30': 15 }, approx_n: 3,
      n_by_status: { ...F.summary.n_by_status, open: 2, unstamped: 1, stale: 2, split_affected: 2 } };
    expect(exclusionNotes(many, { ...F.verdict, open_n: 2 })).toEqual([
      '15 closes from one bulk clear on 2026-09-30 are not decisions, so they are left out',
      '3 estimated rows are shown but not counted',
      '2 rows are still open and not counted yet. No conclusion is recorded while any are open.',
      '1 unstamped row is left out',
      '2 stale data rows are left out',
      '2 split or dividend adjusted rows are left out',
    ]);
    const quiet = { ...F.summary, bulk_dates: {}, approx_n: 0,
      n_by_status: { ...F.summary.n_by_status, stale: 0 } };
    expect(exclusionNotes(quiet, F.verdict)).toEqual([]);
  });

  it('counts only individual, stamped, resolved rows', () => {
    expect(F.rows.map(isCounted)).toEqual([true, false, false, false]);
  });

  it('keeps the fixed copy verbatim', () => {
    expect(CAPTION).toBe('Compares the overrides you made with what the engine would have done. '
      + 'Past closes only, not advice on future ones. A close for a reason the engine cannot see '
      + '(a gap, earnings, needing the cash) can still be right. Figures are after modelled costs '
      + "and before tax. Dollars use the plan's modelled position size. Closing early can also "
      + 'change the tax holding period. There is no target number of overrides.');
    expect(EMPTY_COPY).toBe('No manual overrides in scope.');
    expect(APPROX_LABEL).toBe('estimated exit: daily close, not your fill');
    expect(COUNTS_HINT).toBe('counts ignore size');
    expect(STATUS_LABEL.unstamped).toBe('unstamped');
    expect(STATUS_LABEL.split_affected).toBe('split or dividend adjusted');
  });
});
