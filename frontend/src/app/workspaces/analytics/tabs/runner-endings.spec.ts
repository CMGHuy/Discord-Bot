import { describe, expect, it } from 'vitest';

import { RUNNER_ENDINGS_EMPTY, RUNNER_ENDINGS_FIXTURE } from './partials.fixture';
import {
  ENDING_META, endingCards, exclusionNote, intervalText, oddsBars, scorecardRows, shareText,
} from './runner-endings';

const BLOCK = RUNNER_ENDINGS_FIXTURE;

describe('runner endings helpers', () => {
  it('formats a share and its Wilson interval, and an empty denominator as absent', () => {
    expect(shareText({ share: 25, lo: 4.6, hi: 69.9 })).toBe('25.0%');
    expect(intervalText({ share: 25, lo: 4.6, hi: 69.9 })).toBe('95% CI 4.6–69.9%');
    expect(intervalText({ share: 0, lo: 0, hi: 56.2 })).toBe('95% CI 0.0–56.2%');
    expect(shareText({ share: null, lo: null, hi: null })).toBe('—');
    expect(intervalText({ share: null, lo: null, hi: null })).toBe('');
  });

  it('reuses the tab ending tones', () => {
    expect(Object.fromEntries(Object.entries(ENDING_META).map(([k, m]) => [k, m.tone]))).toEqual(
      { tp2: 'pos', trail: 'accent', floor: 'neg', other: 'warn', giveback: 'warn' });
    expect(ENDING_META.floor.hint).toBe('The floor locks ⅔ of the TP1 gain.');
  });

  it('builds the four cards in order, Giveback over its own decidable denominator', () => {
    const cards = endingCards(BLOCK);
    expect(cards.map((c) => c.label)).toEqual(['Runner at TP2', 'Runner at breakeven', 'Giveback', 'Trailing stop']);
    expect(cards[0]).toMatchObject({ share: '25.0%', interval: '95% CI 4.6–69.9%', count: '1 of 4 runners', thin: true, tone: 'pos' });
    expect(cards[2]).toMatchObject({ share: '0.0%', interval: '95% CI 0.0–56.2%', count: '0 of 3 decidable', tone: 'warn' });
  });

  it('lays out the scorecard: four endings summing to 100%, then the set-apart Giveback row', () => {
    const rows = scorecardRows(BLOCK);
    expect(rows.map((r) => r.label)).toEqual(['TP2', 'Trailing stop', 'Breakeven', 'Other', 'Giveback (any ending)']);
    expect(rows.map((r) => r.cross)).toEqual([false, false, false, false, true]);
    expect(BLOCK.rows.slice(0, 4).reduce((sum, r) => sum + (r.share ?? 0), 0)).toBe(100);
    expect(rows[0]).toMatchObject({ n: '1', share: '25.0%', of: '' });
    expect(rows[0].cells).toEqual(['+4.00R', '+4.00R', '+2.00R', '+1.00R', '+4.20R', '100.0%', '0.20R', '4']);
    expect(rows[2].cells[3]).toBe('−0.33R');
    expect(rows[3].cells.slice(4)).toEqual(['—', '—', '—', '2']);
    expect(rows[4]).toMatchObject({ n: '0', share: '0.0%', of: 'of 3 decidable', interval: '95% CI 0.0–56.2%' });
    expect(rows[4].cells.every((c) => c === '—')).toBe(true);
  });

  it('draws one odds bar per level with its N, every ending listed, empty ones not grown', () => {
    const bars = oddsBars(BLOCK);
    expect(bars.map((b) => [b.label, b.n, b.thin])).toEqual([
      ['Got 25% of the way to TP2', 3, true], ['Got 50% of the way to TP2', 2, true], ['Got 75% of the way to TP2', 2, true]]);
    expect(bars[0].segments.map((s) => s.text)).toEqual(
      ['TP2 1 · 33.3%', 'Trailing stop 1 · 33.3%', 'Breakeven 1 · 33.3%', 'Other 0 · 0.0%']);
    expect(bars[1].segments.map((s) => s.grow)).toEqual([50, 50, 0, 0]);
    expect(bars[1].segments[0].interval).toBe('95% CI 9.5–90.5%');
    expect(bars[0].aria).toContain('N 3');
  });

  it('names every exclusion with its count', () => {
    expect(exclusionNote(BLOCK)).toBe(
      '4 closed runners with a TP2 (1 closed without a TP2 left out). '
      + 'Best R seen, % to TP2, Gave back, Giveback and the odds read 3 decidable runners; left out: '
      + '1 manual closes, 0 without a price path, 0 without a runner price (counted in N and Share only), '
      + '0 with TP2 at or below TP1.');
  });

  it('shapes an all-open scope as measured zeros, never NaN', () => {
    const cards = endingCards(RUNNER_ENDINGS_EMPTY);
    expect(cards.map((c) => [c.share, c.interval, c.count])).toEqual([
      ['—', '', '0 of 0 runners'], ['—', '', '0 of 0 runners'], ['—', '', '0 of 0 decidable'], ['—', '', '0 of 0 runners']]);
    expect(scorecardRows(RUNNER_ENDINGS_EMPTY).flatMap((r) => r.cells).every((c) => c === '—')).toBe(true);
    const bars = oddsBars(RUNNER_ENDINGS_EMPTY);
    expect(bars.flatMap((b) => b.segments.map((s) => s.grow))).toEqual(Array(12).fill(0));
    expect(bars[0].segments[0].text).toBe('TP2 0 · —');
    expect(exclusionNote(RUNNER_ENDINGS_EMPTY)).toMatch(/^0 closed runners with a TP2/);
    expect(JSON.stringify([cards, bars])).not.toContain('NaN');
  });
});
