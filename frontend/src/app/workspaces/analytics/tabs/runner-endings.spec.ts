import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { beforeEach, describe, expect, it } from 'vitest';

import { PartialsRunnerEndings } from '../../../api/models';
import { Hint } from '../../../ui/hint';

import { RUNNER_ENDINGS_EMPTY, RUNNER_ENDINGS_FIXTURE } from './partials.fixture';
import {
  BREAKEVEN_HINT, ENDING_META, ODDS_HINT, PEAK_HINT, RunnerEndings, endingCards, exclusionNote, intervalText, oddsBars, scorecardRows, shareText,
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

function mount(block: PartialsRunnerEndings, thinN = 10) {
  TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  const fixture = TestBed.createComponent(RunnerEndings);
  fixture.componentRef.setInput('block', block);
  fixture.componentRef.setInput('thinN', thinN);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

function hintText(fixture: ComponentFixture<unknown>, label: string): string {
  const hint = fixture.debugElement.queryAll(By.directive(Hint))
    .map((debug) => debug.componentInstance as Hint).find((h) => h.label() === label);
  if (!hint) throw new Error(`no sb-hint labelled "${label}"`);
  return hint.text();
}

const squish = (el: Element | null | undefined): string => (el?.textContent ?? '').replace(/\s+/g, ' ').trim();

describe('RunnerEndings', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('renders the four cards, Giveback with its decidable denominator, each with interval and thin tag', () => {
    const { el } = mount(BLOCK);
    const cards = [...el.querySelectorAll('.card')];
    expect(cards.map((c) => squish(c.querySelector('.card-name'))))
      .toEqual(['Runner at TP2', 'Runner at breakeven', 'Giveback', 'Trailing stop']);
    expect(squish(cards[0])).toContain('25.0%');
    expect(squish(cards[0])).toContain('95% CI 4.6–69.9%');
    expect(squish(cards[2])).toContain('0 of 3 decidable');
    expect(cards.map((c) => c.getAttribute('data-tone'))).toEqual(['pos', 'neg', 'warn', 'accent']);
    expect(el.querySelectorAll('.card .thin-mark')).toHaveLength(4);
  });

  it('renders the scorecard rows in order, Ending pinned, Giveback set apart with its own denominator', () => {
    const { el } = mount(BLOCK);
    expect([...el.querySelectorAll('.scorecard thead th')].map((th) => (th.firstChild?.textContent ?? '').trim())).toEqual(
      ['Ending', 'N', 'Share', 'Avg R', 'Med R', 'Total R', 'vs all-out', 'Best R seen', '% to TP2', 'Gave back', 'Sessions']);
    const rows = [...el.querySelectorAll('.scorecard tbody tr')];
    expect(rows.map((r) => squish(r.querySelector('.row-label'))))
      .toEqual(['TP2', 'Trailing stop', 'Breakeven', 'Other', 'Giveback (any ending)']);
    expect(rows.map((r) => r.classList.contains('cross'))).toEqual([false, false, false, false, true]);
    expect(rows.every((r) => r.firstElementChild?.matches('th.pin'))).toBe(true);
    expect(el.querySelector('.scorecard thead th')?.classList.contains('pin')).toBe(true);
    expect(el.querySelectorAll('.scorecard tr.thin')).toHaveLength(5);
    const giveback = squish(rows[4].querySelector('td.share'));
    expect(giveback).toContain('0.0%');
    expect(giveback).toContain('of 3 decidable');
    expect(giveback).toContain('95% CI 0.0–56.2%');
    expect(squish(rows[0])).toContain('+4.20R');
  });

  it('draws one odds bar per level with its N; empty endings stay in the legend, not the track', () => {
    const { el } = mount(BLOCK);
    const bars = [...el.querySelectorAll('.odds-row')];
    expect(bars).toHaveLength(3);
    expect(squish(bars[0].querySelector('.odds-label'))).toContain('Got 25% of the way to TP2 N 3');
    expect(bars[0].querySelectorAll('.seg')).toHaveLength(3);
    expect(bars[1].querySelectorAll('.seg')).toHaveLength(2);
    expect(bars[0].querySelectorAll('.legend li')).toHaveLength(4);
    expect(squish(bars[1].querySelector('.legend'))).toContain('Breakeven 0 · 0.0%');
    expect(bars[0].querySelector('.track')?.getAttribute('aria-label')).toContain('N 3');
    expect(el.querySelectorAll('.odds-row .thin-mark')).toHaveLength(3);
  });

  it('carries the required copy and names every exclusion', () => {
    const { fixture, el } = mount(BLOCK);
    expect(hintText(fixture, 'Best R seen definition')).toBe(PEAK_HINT);
    expect(hintText(fixture, '% to TP2 definition')).toBe(PEAK_HINT);
    expect(hintText(fixture, 'Runner at breakeven definition')).toBe(BREAKEVEN_HINT);
    expect(hintText(fixture, 'Breakeven definition')).toBe(BREAKEVEN_HINT);
    expect(squish(el)).toContain(ODDS_HINT);
    expect(squish(el)).toContain('1 manual closes');
    expect(squish(el)).toContain('1 closed without a TP2 left out');
  });

  it('marks thin from the payload and names the tab threshold', () => {
    const solid = { ...BLOCK, cards: BLOCK.cards.map((c) => ({ ...c, thin: false })) };
    expect(mount(solid).el.querySelectorAll('.card .thin-mark')).toHaveLength(0);
    TestBed.resetTestingModule();
    const { fixture } = mount(BLOCK, 12);
    expect(hintText(fixture, 'Thin sample definition')).toBe('Under N=12: shown, not trusted.');
  });

  it('renders an all-open scope as measured zeros, not an error', () => {
    const { el } = mount(RUNNER_ENDINGS_EMPTY);
    expect([...el.querySelectorAll('.card-share')].map((c) => squish(c))).toEqual(['—', '—', '—', '—']);
    expect(el.querySelectorAll('.scorecard tbody tr')).toHaveLength(5);
    expect(el.querySelectorAll('.seg')).toHaveLength(0);
    expect(el.querySelectorAll('.legend .none')).toHaveLength(3);
    expect(squish(el)).toContain('0 closed runners with a TP2');
    expect(squish(el)).not.toContain('NaN');
  });
});

describe('runner-endings.ts layout source', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/tabs/runner-endings.ts'), 'utf8');

  it('uses only declared breakpoint values in width queries', () => {
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });

  it('puts the cards 2x2 below desktop and stacks each odds bar on phone', () => {
    expect(src).toContain('.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))');
    expect(src).toContain('@media(max-width:1023px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}');
    expect(src).toContain('@media(max-width:639px){.odds-row{grid-template-columns:minmax(0,1fr)}');
  });

  it('scrolls the scorecard inside its panel with an opaque pinned Ending column', () => {
    expect(src).toContain('<div class="table-scroll"><table class="scorecard">');
    expect(src).toContain('.table-scroll{overflow-x:auto;max-width:100%}');
    expect(src).toContain('.scorecard .pin{position:sticky;left:0;z-index:1;background:var(--panel-bg)');
  });
});
