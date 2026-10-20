import { describe, expect, it } from 'vitest';

import { BandCurrent, BandHorizon, VarianceBandOk } from '../../../api/models';
import {
  BAR_LABELS, CAPTION, CAVEAT, HEADER_COPY, PANEL_TITLE, ZONE_COPY,
  bandSegments, barAriaLabel, compositionLine, dollarNote, drawdownMarkerText, exprLine,
  insufficientCopy, markerPercent, moneyText, runMarkerText, scaleMax, secondaryText,
  spanText, uncertaintyText,
} from './variance-band.model';

const H20: BandHorizon = {
  horizon: 20, weeks_span: 5.3,
  run: { p80: 3, p95: 4, p95_lo: 4, p95_hi: 5 },
  drawdown: { p80: 3.12, p95: 4.4, p95_lo: 3.9, p95_hi: 5.06 },
};
const H50: BandHorizon = {
  horizon: 50, weeks_span: 13.2,
  run: { p80: 4, p95: 7, p95_lo: 6, p95_hi: 8 },
  drawdown: { p80: 4.81, p95: 6.62, p95_lo: 5.9, p95_hi: 7.4 },
};
const CURRENT: BandCurrent = {
  run: 4, run_age_days: 9, drawdown: 5.27, drawdown_age_days: 23,
  run_zone: 'normal', drawdown_zone: 'rough', zone: 'rough',
};
const COMPOSITION: VarianceBandOk['composition'] = {
  days_by_era: { v2: 118, legacy: 42 },
  trades_by_horizon: { '2w': 88, '4w': 131, unknown: 3 },
};

describe('variance-band copy constants (verbatim from the spec)', () => {
  it('carries the title, header, caveat and caption word for word', () => {
    expect(PANEL_TITLE).toBe('Normal bad luck');
    expect(HEADER_COPY).toBe("Whole book, closed trades only. Filters don't apply.");
    expect(CAVEAT).toBe("This book's past results are not positive. A run within their range is still a losing run.");
    expect(CAPTION).toBe(
      "Simulated from this book's closed trades, resampled by week. It shows the range of losing runs these past "
      + "results produce by chance; it is not a forecast. Checked continuously, so 'beyond 95%' will sometimes "
      + 'appear by chance alone. Paper book, before tax.',
    );
  });

  it('carries the bar labels and one copy line per zone', () => {
    expect(BAR_LABELS).toEqual({ run: 'Losing days in a row', drawdown: 'Drawdown over the last 50 close days' });
    expect(ZONE_COPY).toEqual({
      normal: "Within the range this book's past trades produce",
      rough: 'Deeper than 80% of simulated runs, within 95%',
      outside: 'Beyond 95% of simulated runs',
    });
  });

  it('formats the insufficient state with its counts so far', () => {
    expect(insufficientCopy(64, 15)).toBe('Needs 100 close days over 20 weeks (64 days, 15 weeks so far).');
  });
});

describe('band segments', () => {
  it('gives three labelled segments with their values as text, widths summing to 100', () => {
    const segments = bandSegments(H50.run, 'days');
    expect(segments.map((s) => [s.zone, s.label, s.range])).toEqual([
      ['normal', 'Normal', '≤ 4 days'],
      ['rough', 'Rough', '> 4 to ≤ 7 days'],
      ['outside', 'Outside', '> 7 days'],
    ]);
    expect(segments.reduce((sum, s) => sum + s.width, 0)).toBeCloseTo(100, 6);
  });

  it('writes R ranges with one decimal', () => {
    expect(bandSegments(H50.drawdown, 'R').map((s) => s.range))
      .toEqual(['≤ 4.8R', '> 4.8 to ≤ 6.6R', '> 6.6R']);
  });

  it('omits the empty rough zone when p80 equals p95', () => {
    const segments = bandSegments({ p80: 3, p95: 3 }, 'days');
    expect(segments.map((s) => s.zone)).toEqual(['normal', 'outside']);
    expect(segments.map((s) => s.range)).toEqual(['≤ 3 days', '> 3 days']);
    expect(segments.reduce((sum, s) => sum + s.width, 0)).toBeCloseTo(100, 6);
  });

  it('still draws a bar for an all-win book (p95 = 0)', () => {
    expect(scaleMax({ p80: 0, p95: 0 })).toBe(1);
    const segments = bandSegments({ p80: 0, p95: 0 }, 'days');
    expect(segments.map((s) => s.zone)).toEqual(['normal', 'outside']);
    expect(segments[1].width).toBe(100);
  });

  it('places the marker on the same scale and clamps it to the bar', () => {
    expect(scaleMax(H50.run)).toBe(8.75);
    expect(markerPercent(7, H50.run)).toBeCloseTo(80, 6);
    expect(markerPercent(0, H50.run)).toBe(0);
    expect(markerPercent(40, H50.run)).toBe(100);
    expect(markerPercent(-1, H50.run)).toBe(0);
  });
});

describe('marker and line text', () => {
  it('writes the run marker with its age', () => {
    expect(runMarkerText(CURRENT)).toBe('now: 4 days, 9 calendar days long');
    expect(runMarkerText({ ...CURRENT, run: 1, run_age_days: 1 })).toBe('now: 1 day, 1 calendar day long');
    expect(runMarkerText({ ...CURRENT, run: 0, run_age_days: null })).toBe('now: 0 days');
  });

  it('writes the drawdown marker with approximate dollars only when they exist', () => {
    expect(drawdownMarkerText(CURRENT, { median_risk: 59.26, drawdown_usd: 312.34 }, '$'))
      .toBe('now: 5.3R (≈ $312.34), 23 calendar days since the peak');
    expect(drawdownMarkerText(CURRENT, undefined, '$'))
      .toBe('now: 5.3R, 23 calendar days since the peak');
    expect(drawdownMarkerText({ ...CURRENT, drawdown: 0, drawdown_age_days: null }, undefined, '€'))
      .toBe('now: 0.0R');
  });

  it('writes money unsigned with the symbol first, grouped', () => {
    expect(moneyText(1312.346, '$')).toBe('$1,312.35');
    expect(moneyText(-40, '€')).toBe('€40.00');
  });

  it("states the band's own uncertainty", () => {
    expect(uncertaintyText(H50.run)).toBe('p95 ≈ 7 (6–8)');
    expect(uncertaintyText(H50.drawdown, 'R')).toBe('p95 ≈ 6.6R (5.9–7.4R)');
  });

  it('writes the span and the 20-day secondary line', () => {
    expect(spanText(H50)).toBe("50 close days ≈ 13.2 weeks at this book's pace");
    expect(spanText(H20)).toBe("20 close days ≈ 5.3 weeks at this book's pace");
    expect(secondaryText(H20)).toBe('Over 20 close days: p95 4 days in a row, 4.4R drawdown');
  });

  it('writes the ExpR line with N and window', () => {
    expect(exprLine({ value: 0.214, n: 222, start: '2026-01-05', end: '2026-10-16', ci: [0.02, 0.41], not_positive: false }))
      .toBe('Book: ExpR +0.21R over N=222 trades (2026-01-05 to 2026-10-16)');
    expect(exprLine({ value: null, n: 0, start: null, end: null, ci: null, not_positive: true }))
      .toBe('Book: ExpR — over N=0 trades (— to —)');
  });

  it('writes the composition line', () => {
    expect(compositionLine(COMPOSITION)).toBe('Close days: 118 v2, 42 legacy · Trades: 2w 88, 4w 131, unknown 3');
    expect(compositionLine({ days_by_era: { v2: 0, legacy: 0 }, trades_by_horizon: {} }))
      .toBe('Close days: 0 v2, 0 legacy · Trades: —');
  });

  it('says how the dollar figure is derived', () => {
    expect(dollarNote({ median_risk: 59.26, drawdown_usd: 312.34 }, '$'))
      .toBe('≈ $ = R × the median per-trade dollar risk ($59.26), from shares × entry-to-stop distance.');
  });

  it("gives each bar a text equivalent for screen readers", () => {
    const segments = bandSegments(H50.run, 'days');
    expect(barAriaLabel(BAR_LABELS.run, segments, runMarkerText(CURRENT)))
      .toBe('Losing days in a row: Normal ≤ 4 days, Rough > 4 to ≤ 7 days, Outside > 7 days. now: 4 days, 9 calendar days long');
  });
});

describe('copy discipline', () => {
  /** Every string the panel can show, for one full band with dollars. */
  function everyString(): string[] {
    const dollars = { median_risk: 59.26, drawdown_usd: 312.34 };
    return [
      PANEL_TITLE, HEADER_COPY, CAPTION, CAVEAT, ...Object.values(ZONE_COPY), ...Object.values(BAR_LABELS),
      insufficientCopy(64, 15),
      ...bandSegments(H50.run, 'days').flatMap((s) => [s.label, s.range]),
      ...bandSegments(H50.drawdown, 'R').flatMap((s) => [s.label, s.range]),
      runMarkerText(CURRENT), drawdownMarkerText(CURRENT, dollars, '$'),
      uncertaintyText(H50.run), uncertaintyText(H50.drawdown, 'R'), spanText(H20), spanText(H50),
      secondaryText(H20), compositionLine(COMPOSITION), dollarNote(dollars, '$'),
      exprLine({ value: -0.1, n: 40, start: '2026-01-05', end: '2026-10-16', ci: [-0.3, 0.1], not_positive: true }),
    ];
  }

  it('never uses the word "edge"', () => {
    for (const text of everyString()) expect(text).not.toMatch(/\bedge\b/i);
  });

  it('never opens a sentence with an instruction verb', () => {
    // "entry-to-stop distance" names a price distance (a noun), so the
    // check is on imperative position: the start of a string or sentence.
    const imperative = /(^|[.;:!?]\s+)(stop|check|skip|size|review)\b/i;
    for (const text of everyString()) expect(text).not.toMatch(imperative);
  });
});
