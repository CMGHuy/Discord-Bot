# v219 — Partials tab: runner endings, part 2: frontend and release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v219 — Partials tab: runner endings](../specs/2026-11-07-v219-partials-runner-endings-design.md)
**Index:** [2026-11-07-v219-partials-runner-endings_0-index.md](2026-11-07-v219-partials-runner-endings_0-index.md) — Goal, Global Constraints, the **payload contract** (`runner_endings`, with the worked block for `_book()`), Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks V219-5..V219-7. V219-5 needs only the payload contract (it can run beside Part 1). V219-6 follows V219-5 and, for its layout audit, a worktree where V219-4 is merged. V219-7 runs last.

Facts from Part 1 this part relies on:

- `build_report` no longer emits `outcomes`; it emits `runner_endings` exactly as the index's payload contract states.
- `counterfactuals.giveback` lists **decidable** runners only (manual closes, no-TP2 runners and runners with TP2 at or below TP1 are out) and a new `counterfactuals.giveback_excluded: int` counts the closed runners it dropped. For `_book()` with `MANUAL` that is `giveback == [0.2, 1.26, 0.6]`, `giveback_excluded == 2`; `path_unavailable` stays `1` and `runner_r_unavailable` stays `0`.
- Shares are percentages 0–100 at 1 dp; `lo`/`hi` are the Wilson 95% bounds as percentages, exactly `0.0` at `k == 0` and `100.0` at `k == n`; all three are `null` when the denominator is 0.

---

# Phase 3 — Frontend

### Task V219-5: Frontend model, fixture and the Runner endings helpers

**Model:** sonnet — new types and pure view helpers from a fixed payload contract; normal TDD in two new files.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (v142 Partials block, `PartialsOutcome` / `AnalyticsPartials` at :906-925)
- Modify: `frontend/src/app/workspaces/analytics/tabs/partials.fixture.ts` (whole file, 62 lines)
- Create: `frontend/src/app/workspaces/analytics/tabs/runner-endings.ts` (helpers only in this task; V219-5b adds the component to the same file)
- Create: `frontend/src/app/workspaces/analytics/tabs/runner-endings.spec.ts`

**Interfaces:**
- Consumes: the index's payload contract (`runner_endings`) and its worked block for `_book()` with `MANUAL`. No backend code.
- Produces (V219-5b and V219-6 read these):
  - Types in `models.ts` (in full in Step 1): `PartialsEnding`, `PartialsShare`, `PartialsEndingCard`, `PartialsEndingRow`, `PartialsOddsSegment`, `PartialsOddsBar`, `PartialsRunnerEndings`; `AnalyticsPartials.runner_endings: PartialsRunnerEndings`; `counterfactuals.giveback_excluded: number`. (`outcomes` stays until V219-6.)
  - Fixture exports: `RUNNER_ENDINGS_FIXTURE: PartialsRunnerEndings` (the index's worked block), `RUNNER_ENDINGS_EMPTY: PartialsRunnerEndings` (n 0, every share null); `PARTIALS_FIXTURE.runner_endings` is `RUNNER_ENDINGS_FIXTURE`.
  - From `runner-endings.ts`: `ENDING_META: Record<PartialsEnding, EndingMeta>`, `shareText(s)`, `intervalText(s)`, `endingCards(block): EndingCardView[]`, `scorecardRows(block): ScorecardRowView[]`, `oddsBars(block): OddsBarView[]`, `exclusionNote(block): string`; copy constants `RUNNER_ENDINGS_HINT`, `PEAK_HINT`, `BREAKEVEN_HINT`, `ODDS_HINT`; their view types (`EndingCardView`, `ScorecardRowView`, `OddsBarView`, …).

**Background.** The tab's convention (`partials.ts`) is that every figure arrives computed from `swingbot/core/analytics/partials.py`; the frontend only formats. These helpers turn the block into display strings so the template stays plain and the formatting is unit-tested. They do **not** import from `partials.ts`: V219-6 makes `partials.ts` import this file, and a two-way import between a component and its host is a cycle. The few formatters needed are local. Tones are the tab's (index § Global Constraints). The Giveback share has its own denominator (decidable runners), so its count reads "of N decidable", never "of N runners".

- [ ] **Step 1: Add the types to `models.ts`**

Directly after `export interface PartialsOutcome …` (:906), insert:

```ts
/** v219 — `runner_endings` (`partials.py::runner_endings`): how closed runners
 *  ended. Shares are percentages 0-100 (1 dp) with Wilson 95% bounds `lo`/`hi`;
 *  all three are null when `denominator` is 0. Giveback's denominator is the
 *  decidable runners, the four endings' is `n`. R figures are runner R on the
 *  plan's initial risk; `progress` is % of the TP1→TP2 distance (0-100). */
export type PartialsEnding = 'tp2' | 'trail' | 'floor' | 'other' | 'giveback';
export interface PartialsShare {
  n: number; denominator: number; share: number | null; lo: number | null; hi: number | null; thin: boolean;
}
export interface PartialsEndingCard extends PartialsShare { ending: 'tp2' | 'floor' | 'giveback' | 'trail'; }
export interface PartialsEndingRow extends PartialsShare {
  ending: PartialsEnding;
  r_n: number; avg_r: number | null; median_r: number | null; total_r: number | null; vs_all_out: number | null;
  path_n: number; best_r: number | null; progress: number | null; gave_back: number | null; sessions: number | null;
}
export interface PartialsOddsSegment {
  ending: Exclude<PartialsEnding, 'giveback'>; n: number; share: number | null; lo: number | null; hi: number | null;
}
export interface PartialsOddsBar { level: number; n: number; thin: boolean; split: PartialsOddsSegment[]; }
export interface PartialsRunnerEndings {
  n: number; decidable: number;
  cards: PartialsEndingCard[]; rows: PartialsEndingRow[]; odds: PartialsOddsBar[];
  excluded: { no_tp2: number; runner_r_unavailable: number; manual_close: number; unpathed: number; no_tp2_distance: number };
}
```

In `AnalyticsPartials`, add `runner_endings: PartialsRunnerEndings;` on the line after `outcomes: PartialsOutcome[];`, and change the counterfactuals line `path_unavailable: number; runner_r_unavailable: number;` to `path_unavailable: number; runner_r_unavailable: number; giveback_excluded: number;`.

- [ ] **Step 2: Extend the fixture**

In `partials.fixture.ts`, replace the import line with:

```ts
import {
  AnalyticsPartials, PartialsBreakdownRow, PartialsEnding, PartialsEndingCard, PartialsEndingRow, PartialsKpis,
  PartialsOddsSegment, PartialsRunnerEndings, PartialsShare,
} from '../../../api/models';
```

Insert after the `row` helper (:12), before `PARTIALS_FIXTURE`:

```ts
/** v219 — the index's worked `runner_endings` block for `_book()` + `MANUAL`:
 *  A tp2, C trail, B floor, D manual ("other"); F (no TP2) is out; D is not
 *  decidable (manual close), so 3 decidable runners and no giveback. */
type RTuple = [number, number | null, number | null, number | null, number | null];
type PathTuple = [number, number | null, number | null, number | null];
const share = (n: number, denominator: number, pct: number | null, lo: number | null, hi: number | null): PartialsShare =>
  ({ n, denominator, share: pct, lo, hi, thin: true });
const endingRow = (ending: PartialsEnding, s: PartialsShare, r: RTuple, path: PathTuple,
  sessions: number | null): PartialsEndingRow => ({
  ending, ...s, r_n: r[0], avg_r: r[1], median_r: r[2], total_r: r[3], vs_all_out: r[4],
  path_n: path[0], best_r: path[1], progress: path[2], gave_back: path[3], sessions,
});
const cardsOf = (rows: PartialsEndingRow[]): PartialsEndingCard[] =>
  (['tp2', 'floor', 'giveback', 'trail'] as const).map((ending) => {
    const { n, denominator, share: pct, lo, hi, thin } = rows.find((r) => r.ending === ending)!;
    return { ending, n, denominator, share: pct, lo, hi, thin };
  });
const seg = (ending: PartialsOddsSegment['ending'], n: number, pct: number | null, lo: number | null,
  hi: number | null): PartialsOddsSegment => ({ ending, n, share: pct, lo, hi });

const QUARTER = share(1, 4, 25, 4.6, 69.9);
const ROWS: PartialsEndingRow[] = [
  endingRow('tp2', QUARTER, [1, 4, 4, 2, 1], [1, 4.2, 100, 0.2], 4),
  endingRow('trail', QUARTER, [1, 3, 3, 1.5, 0.5], [1, 3.6, 80, 0.6], 2),
  endingRow('floor', QUARTER, [1, 1.34, 1.34, 0.67, -0.33], [1, 2.6, 30, 1.26], 2),
  endingRow('other', QUARTER, [1, 2.5, 2.5, 1.25, 0.25], [0, null, null, null], 2),
  endingRow('giveback', share(0, 3, 0, 0, 56.2), [0, null, null, null, null], [0, null, null, null], null),
];
const THIRD = (ending: PartialsOddsSegment['ending']) => seg(ending, 1, 33.3, 6.1, 79.2);
const HALF = [seg('tp2', 1, 50, 9.5, 90.5), seg('trail', 1, 50, 9.5, 90.5),
  seg('floor', 0, 0, 0, 65.8), seg('other', 0, 0, 0, 65.8)];

export const RUNNER_ENDINGS_FIXTURE: PartialsRunnerEndings = {
  n: 4, decidable: 3, cards: cardsOf(ROWS), rows: ROWS,
  odds: [
    { level: 25, n: 3, thin: true, split: [THIRD('tp2'), THIRD('trail'), THIRD('floor'), seg('other', 0, 0, 0, 56.2)] },
    { level: 50, n: 2, thin: true, split: HALF },
    { level: 75, n: 2, thin: true, split: HALF },
  ],
  excluded: { no_tp2: 1, runner_r_unavailable: 0, manual_close: 1, unpathed: 0, no_tp2_distance: 0 },
};

/** Every runner still open: a measured zero, not an error. */
const NONE = share(0, 0, null, null, null);
const EMPTY_ROWS = (['tp2', 'trail', 'floor', 'other', 'giveback'] as const).map((ending) =>
  endingRow(ending, NONE, [0, null, null, null, null], [0, null, null, null], null));
export const RUNNER_ENDINGS_EMPTY: PartialsRunnerEndings = {
  n: 0, decidable: 0, cards: cardsOf(EMPTY_ROWS), rows: EMPTY_ROWS,
  odds: [25, 50, 75].map((level) => ({
    level, n: 0, thin: true,
    split: (['tp2', 'trail', 'floor', 'other'] as const).map((e) => seg(e, 0, null, null, null)),
  })),
  excluded: { no_tp2: 0, runner_r_unavailable: 0, manual_close: 0, unpathed: 0, no_tp2_distance: 0 },
};
```

In `PARTIALS_FIXTURE`, add `runner_endings: RUNNER_ENDINGS_FIXTURE,` after the `outcomes` array, change `giveback: [0.2, 1.26, 0.6, 0.4],` to `giveback: [0.2, 1.26, 0.6],`, and change `path_unavailable: 1, runner_r_unavailable: 0,` to `path_unavailable: 1, runner_r_unavailable: 0, giveback_excluded: 2,` (Part 1: F's 0.4 left the strip with the no-TP2 runners).

- [ ] **Step 3: Write the failing helper tests**

Create `frontend/src/app/workspaces/analytics/tabs/runner-endings.spec.ts`:

```ts
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
```

- [ ] **Step 4: Run it to verify it fails**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/runner-endings.spec.ts`
Expected: FAIL — `Failed to resolve import "./runner-endings"`.

- [ ] **Step 5: Write the helpers**

Create `frontend/src/app/workspaces/analytics/tabs/runner-endings.ts`:

```ts
import {
  PartialsEnding, PartialsEndingRow, PartialsOddsSegment, PartialsRunnerEndings, PartialsShare,
} from '../../../api/models';
import { ABSENT, MINUS } from '../../../ui/format';

/* v219 — Runner endings: how each closed runner ended (TP2, trailing stop,
 * breakeven floor, other) and how many gave back a good move. Every figure is
 * computed server-side (`partials.py::runner_endings`); these helpers only
 * format it. Statistics only: nothing here is a gate or a rule. */

export type EndingTone = 'pos' | 'neg' | 'warn' | 'accent';
export interface EndingMeta { label: string; card: string; tone: EndingTone; hint: string; }

export const RUNNER_ENDINGS_HINT =
  'How each closed runner ended, and the R behind each ending. R, before commissions and tax.';
export const PEAK_HINT = 'The peak is known only afterwards; it is not a target.';
export const BREAKEVEN_HINT = 'The floor locks ⅔ of the TP1 gain.';
export const ODDS_HINT = 'Read off this book; any threshold taken from it is screened on backtest data first.';
const GIVEBACK_HINT = 'Got at least half way from TP1 to TP2, then closed below the TP1 price, whatever '
  + 'the ending. Its share is of the decidable runners, not of the four endings.';

export const ENDING_META: Record<PartialsEnding, EndingMeta> = {
  tp2: { label: 'TP2', card: 'Runner at TP2', tone: 'pos', hint: '' },
  trail: { label: 'Trailing stop', card: 'Trailing stop', tone: 'accent', hint: '' },
  floor: { label: 'Breakeven', card: 'Runner at breakeven', tone: 'neg', hint: BREAKEVEN_HINT },
  other: { label: 'Other', card: 'Other', tone: 'warn', hint: 'Stall, time, manual and unrecorded closes.' },
  giveback: { label: 'Giveback (any ending)', card: 'Giveback', tone: 'warn', hint: GIVEBACK_HINT },
};

export interface EndingCardView {
  ending: PartialsEnding; label: string; tone: EndingTone; hint: string;
  share: string; interval: string; count: string; thin: boolean;
}
export interface ScorecardRowView {
  ending: PartialsEnding; label: string; tone: EndingTone; hint: string; thin: boolean; cross: boolean;
  n: string; share: string; interval: string; of: string;
  /** Avg R, Med R, Total R, vs all-out, Best R seen, % to TP2, Gave back, Sessions. */
  cells: string[];
}
export interface OddsSegmentView {
  ending: PartialsEnding; label: string; tone: EndingTone; grow: number; text: string; interval: string;
}
export interface OddsBarView {
  level: number; label: string; n: number; thin: boolean; aria: string; segments: OddsSegmentView[];
}

type Pct = Pick<PartialsShare, 'share' | 'lo' | 'hi'>;

export const shareText = (s: Pct): string => (s.share === null ? ABSENT : `${s.share.toFixed(1)}%`);
export const intervalText = (s: Pct): string =>
  (s.lo === null || s.hi === null ? '' : `95% CI ${s.lo.toFixed(1)}–${s.hi.toFixed(1)}%`);
const signedR = (v: number | null): string =>
  (v === null ? ABSENT : `${v < 0 ? MINUS : '+'}${Math.abs(v).toFixed(2)}R`);
const plainR = (v: number | null): string =>
  (v === null ? ABSENT : `${v < 0 ? MINUS : ''}${Math.abs(v).toFixed(2)}R`);
const pctCell = (v: number | null): string => (v === null ? ABSENT : `${v.toFixed(1)}%`);
const sessionsCell = (v: number | null): string =>
  (v === null ? ABSENT : Number.isInteger(v) ? String(v) : v.toFixed(1));
const countText = (ending: PartialsEnding, s: PartialsShare): string =>
  `${s.n} of ${s.denominator} ${ending === 'giveback' ? 'decidable' : 'runners'}`;

export function endingCards(block: PartialsRunnerEndings): EndingCardView[] {
  return block.cards.map((c) => {
    const meta = ENDING_META[c.ending];
    return { ending: c.ending, label: meta.card, tone: meta.tone, hint: meta.hint,
      share: shareText(c), interval: intervalText(c), count: countText(c.ending, c), thin: c.thin };
  });
}

function scoreCells(r: PartialsEndingRow): string[] {
  return [signedR(r.avg_r), signedR(r.median_r), signedR(r.total_r), signedR(r.vs_all_out),
    signedR(r.best_r), pctCell(r.progress), plainR(r.gave_back), sessionsCell(r.sessions)];
}

export function scorecardRows(block: PartialsRunnerEndings): ScorecardRowView[] {
  return block.rows.map((r) => {
    const meta = ENDING_META[r.ending];
    const cross = r.ending === 'giveback';
    return { ending: r.ending, label: meta.label, tone: meta.tone, hint: meta.hint, thin: r.thin, cross,
      n: String(r.n), share: shareText(r), interval: intervalText(r),
      of: cross ? `of ${r.denominator} decidable` : '', cells: scoreCells(r) };
  });
}

function oddsSegment(seg: PartialsOddsSegment): OddsSegmentView {
  const meta = ENDING_META[seg.ending];
  return { ending: seg.ending, label: meta.label, tone: meta.tone, grow: seg.share ?? 0,
    text: `${meta.label} ${seg.n} · ${shareText(seg)}`, interval: intervalText(seg) };
}

export function oddsBars(block: PartialsRunnerEndings): OddsBarView[] {
  return block.odds.map((bar) => {
    const label = `Got ${bar.level}% of the way to TP2`;
    const segments = bar.split.map(oddsSegment);
    return { level: bar.level, label, n: bar.n, thin: bar.thin, segments,
      aria: `${label}, N ${bar.n}: ${segments.map((s) => s.text).join(', ')}` };
  });
}

export function exclusionNote(block: PartialsRunnerEndings): string {
  const x = block.excluded;
  return `${block.n} closed runners with a TP2 (${x.no_tp2} closed without a TP2 left out). `
    + `Best R seen, % to TP2, Gave back, Giveback and the odds read ${block.decidable} decidable runners; `
    + `left out: ${x.manual_close} manual closes, ${x.unpathed} without a price path, `
    + `${x.runner_r_unavailable} without a runner price (counted in N and Share only), `
    + `${x.no_tp2_distance} with TP2 at or below TP1.`;
}
```

- [ ] **Step 6: Run the tests to verify they pass, and the tab and store specs still pass**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/runner-endings.spec.ts --include src/app/workspaces/analytics/tabs/partials.spec.ts --include src/app/stores/analytics.partials.spec.ts`
Expected: PASS, 0 failed. (`partials.spec.ts` still passes: `outcomes` is untouched until V219-6, and its giveback-bin test uses its own literal.)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/workspaces/analytics/tabs/partials.fixture.ts frontend/src/app/workspaces/analytics/tabs/runner-endings.ts frontend/src/app/workspaces/analytics/tabs/runner-endings.spec.ts
git commit -m "feat(ui): runner_endings model, fixture and Runner endings view helpers (V219-5)"
```

### Task V219-5b: The `sb-runner-endings` component: cards, pinned scorecard, CSS odds bars

**Model:** sonnet — one standalone presentational component over V219-5's tested helpers, with its three-width CSS.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/runner-endings.ts` (created by V219-5: imports at the top, component appended at the end)
- Modify: `frontend/src/app/workspaces/analytics/tabs/runner-endings.spec.ts` (created by V219-5: imports at the top, new `describe` blocks appended)

**Interfaces:**
- Consumes (V219-5): `PartialsRunnerEndings`; `endingCards`, `scorecardRows`, `oddsBars`, `exclusionNote`, `PEAK_HINT`, `BREAKEVEN_HINT`, `ODDS_HINT`; fixtures `RUNNER_ENDINGS_FIXTURE`, `RUNNER_ENDINGS_EMPTY`. Existing: `Hint` (`frontend/src/app/ui/hint.ts`, inputs `text`, `label`; no injected services).
- Produces (V219-6 hosts it): `export class RunnerEndings`, selector `sb-runner-endings`, inputs `block: PartialsRunnerEndings` (required) and `thinN: number` (required). It renders no panel or header of its own; the host wraps it in `<sb-panel class="wide">` with an `sb-panel-header`.

**Background.** Layout C (index § Global Constraints): desktop has four cards in a row, then the full-width scorecard, then the odds bars. Below 1024 px the cards go 2×2; the scorecard scrolls inside `.table-scroll` with the Ending column pinned (`position:sticky`, opaque `var(--panel-bg)`, the token `sb-panel` paints itself with in `ui/layout.ts`, so scrolled cells never show through). Below 640 px each odds bar stacks: label, then a full-width track, then a legend that wraps. `sb-share-bar` has no slot for an interval or a group N, so the odds bars are a plain CSS flex track with the share as `flex-grow`; segments with no runners are not drawn, but every ending stays in the legend with its count, share and Wilson interval. Thin (N < `thinN`) is marked with a visible "thin" tag on every card, row and bar (and the row is dimmed like the tab's breakdown table), never hidden. Breakpoints are only 639/640 and 1023/1024 (`ui/breakpoints.ts`). The required copy sits where the spec puts it: `PEAK_HINT` on the Best R seen and % to TP2 headers, `BREAKEVEN_HINT` on the Breakeven card and row (through `ENDING_META.floor.hint`), `ODDS_HINT` as visible text under the odds bars.

- [ ] **Step 1: Write the failing component tests**

In `runner-endings.spec.ts`, replace the first import line (`import { describe, expect, it } from 'vitest';`) with:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { beforeEach, describe, expect, it } from 'vitest';

import { PartialsRunnerEndings } from '../../../api/models';
import { Hint } from '../../../ui/hint';
```

and add `BREAKEVEN_HINT, ODDS_HINT, PEAK_HINT, RunnerEndings,` to the existing `./runner-endings` import. Append at the end of the file:

```ts
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
    const { el } = mount(BLOCK, 12);
    expect(el.querySelector('.thin-mark')?.getAttribute('title')).toBe('Under N=12: shown, not trusted.');
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/runner-endings.spec.ts`
Expected: FAIL — `RunnerEndings` is not exported from `./runner-endings` (the helper tests from V219-5 still pass).

- [ ] **Step 3: Write the component**

At the top of `runner-endings.ts`, add before the `../../../api/models` import:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
```

and after the `../../../ui/format` import:

```ts
import { Hint } from '../../../ui/hint';
```

Append at the end of the file:

```ts
@Component({
  selector: 'sb-runner-endings',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint],
  template: `
    <div class="cards">@for (card of cards(); track card.ending) {
      <article class="card" [attr.data-tone]="card.tone" [class.thin]="card.thin">
        <p class="card-label"><span class="card-name">{{ card.label }}</span>
          @if (card.hint) { <sb-hint [text]="card.hint" [label]="card.label + ' definition'" /> }</p>
        <p class="card-share">{{ card.share }}</p>
        <p class="card-interval">{{ card.interval }}</p>
        <p class="card-count">{{ card.count }}@if (card.thin) { <span class="thin-mark" [title]="thinTitle()">thin</span> }</p>
      </article>
    }</div>
    <div class="table-scroll"><table class="scorecard">
      <thead><tr>
        <th class="pin" scope="col">Ending</th><th scope="col">N</th><th scope="col">Share</th>
        <th scope="col">Avg R</th><th scope="col">Med R</th><th scope="col">Total R</th><th scope="col">vs all-out</th>
        <th scope="col">Best R seen <sb-hint [text]="peakHint" label="Best R seen definition" /></th>
        <th scope="col">% to TP2 <sb-hint [text]="peakHint" label="% to TP2 definition" /></th>
        <th scope="col">Gave back</th><th scope="col">Sessions</th>
      </tr></thead>
      <tbody>@for (row of rows(); track row.ending) {
        <tr [class.thin]="row.thin" [class.cross]="row.cross">
          <th class="pin" scope="row"><span class="key" [attr.data-tone]="row.tone"></span><span class="row-label">{{ row.label }}</span>
            @if (row.hint) { <sb-hint [text]="row.hint" [label]="row.label + ' definition'" /> }
            @if (row.thin) { <span class="thin-mark" [title]="thinTitle()">thin</span> }</th>
          <td class="num">{{ row.n }}</td>
          <td class="num share">{{ row.share }}@if (row.of) { <span class="of">{{ row.of }}</span> }<small>{{ row.interval }}</small></td>
          @for (cell of row.cells; track $index) { <td class="num">{{ cell }}</td> }
        </tr>
      }</tbody>
    </table></div>
    <div class="odds">
      <p class="odds-title">If the runner got this far, how it ended</p>
      @for (bar of odds(); track bar.level) {
        <div class="odds-row" [class.thin]="bar.thin">
          <p class="odds-label">{{ bar.label }} <span class="odds-n">N {{ bar.n }}</span>
            @if (bar.thin) { <span class="thin-mark" [title]="thinTitle()">thin</span> }</p>
          <div class="track" role="img" [attr.aria-label]="bar.aria">@for (s of bar.segments; track s.ending) {
            @if (s.grow > 0) { <span class="seg" [attr.data-tone]="s.tone" [style.flex-grow]="s.grow"></span> }
          }</div>
          <ul class="legend">
            @if (bar.n === 0) { <li class="none">no runner got this far</li> }
            @for (s of bar.segments; track s.ending) {
              <li><span class="key" [attr.data-tone]="s.tone"></span><span>{{ s.text }}</span><small>{{ s.interval }}</small></li>
            }
          </ul>
        </div>
      }
      <p class="note">{{ oddsHint }}</p>
    </div>
    <p class="note">{{ exclusions() }}</p>
  `,
  styles: `:host{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--space-14);min-width:0}[data-tone='pos']{--tone:var(--pos)}[data-tone='neg']{--tone:var(--neg)}[data-tone='warn']{--tone:var(--warn)}[data-tone='accent']{--tone:var(--accent)}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--space-10)}.card{min-width:0;padding:var(--space-10);border:var(--panel-border);border-top:3px solid var(--tone,var(--accent));border-radius:var(--panel-radius)}.card p{margin:0}.card-label{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-4);font-size:var(--text-chip);color:var(--text-secondary)}.card-share{margin-top:var(--space-4);font-size:var(--text-metric);font-variant-numeric:tabular-nums}.card.thin .card-share{color:var(--text-faint)}.card-interval,.card-count{font-size:var(--text-micro);color:var(--text-secondary);overflow-wrap:anywhere}.key{display:inline-block;flex:none;width:10px;height:10px;margin-right:var(--space-6);border-radius:var(--radius-sm);background:var(--tone,var(--accent))}.thin-mark{margin-left:var(--space-4);font-size:var(--text-micro);color:var(--text-faint);text-transform:uppercase}.table-scroll{overflow-x:auto;max-width:100%}.scorecard{width:100%;border-collapse:separate;border-spacing:0;font-size:var(--text-table)}.scorecard th,.scorecard td{padding:var(--space-4) var(--space-8);text-align:left;border-bottom:1px solid var(--border);white-space:nowrap;vertical-align:top}.scorecard .num{text-align:right;font-variant-numeric:tabular-nums}.scorecard .pin{position:sticky;left:0;z-index:1;background:var(--panel-bg);white-space:normal;min-width:8rem;max-width:11rem}.scorecard small,.scorecard .of{display:block;font-size:var(--text-micro);color:var(--text-faint)}.scorecard tr.thin td{color:var(--text-faint)}.scorecard tr.cross>*{border-top:2px solid var(--border-strong)}.odds{display:grid;gap:var(--space-10);min-width:0}.odds p{margin:0}.odds-title{font-size:var(--text-chip);color:var(--text-secondary)}.odds-row{display:grid;grid-template-columns:minmax(10rem,14rem) minmax(0,1fr);gap:var(--space-4) var(--space-10);align-items:center}.odds-row .legend{grid-column:2}.odds-label{font-size:var(--text-table);overflow-wrap:anywhere}.odds-n{color:var(--text-secondary);font-variant-numeric:tabular-nums}.track{display:flex;gap:2px;height:14px;overflow:hidden;background:var(--bg);border-radius:var(--radius-sm)}.seg{display:block;flex-basis:0;min-width:2px;background:var(--tone,var(--accent))}.odds-row.thin .track{opacity:.6}.legend{display:flex;flex-wrap:wrap;gap:var(--space-6) var(--space-14);margin:0;padding:0;list-style:none;font-size:var(--text-chip)}.legend li{display:inline-flex;align-items:baseline;flex-wrap:wrap;gap:var(--space-4);min-width:0;color:var(--text-secondary)}.legend li span:not(.key){overflow-wrap:anywhere}.legend small{color:var(--text-faint);font-size:var(--text-micro)}.legend .none{color:var(--text-faint);font-style:italic}.note{margin:0;font-size:var(--text-micro);color:var(--text-faint)}@media(max-width:1023px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:639px){.odds-row{grid-template-columns:minmax(0,1fr)}.odds-row .legend{grid-column:1}}`,
})
export class RunnerEndings {
  readonly block = input.required<PartialsRunnerEndings>();
  readonly thinN = input.required<number>();
  readonly peakHint = PEAK_HINT;
  readonly oddsHint = ODDS_HINT;
  readonly cards = computed(() => endingCards(this.block()));
  readonly rows = computed(() => scorecardRows(this.block()));
  readonly odds = computed(() => oddsBars(this.block()));
  readonly exclusions = computed(() => exclusionNote(this.block()));
  readonly thinTitle = computed(() => `Under N=${this.thinN()}: shown, not trusted.`);
}
```

Check the tokens the styles use exist before running: `git grep -n -e "--panel-bg:" -e "--border-strong:" -e "--text-metric:" -e "--radius-sm:" frontend/src/styles` — each must print a definition; a missing one is a `BLOCKED:` report, not a guessed substitute.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/runner-endings.spec.ts`
Expected: PASS, 0 failed (the V219-5 helper tests and the new component and layout-source tests). The header test reads each `th`'s first text node because `sb-hint` keeps its popover text in the DOM (`ui/hint.ts`, the `.pop` span); keep the label text first in every `th`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/runner-endings.ts frontend/src/app/workspaces/analytics/tabs/runner-endings.spec.ts
git commit -m "feat(ui): sb-runner-endings -- ending cards, pinned scorecard and CSS odds bars (V219-5b)"
```

### Task V219-6: Partials tab hosts Runner endings; "Runner outcome mix" removed; three-width check

**Model:** sonnet — one page's wiring and removal, plus its layout audit at 390, 768 and 1440 px.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/partials.ts` (imports :3-19, `BUCKETS` :34-40, `outcomeSegments` :80-85, `imports:` :148-149, template panels :164-176, `outcomes` computed :209)
- Modify: `frontend/src/app/workspaces/analytics/tabs/partials.spec.ts` (imports :12-16, outcome test :68-72, panel test :108-118, thin test :120-122; new tests appended)
- Modify: `frontend/src/app/api/models.ts` (`PartialsBucket`, `PartialsOutcome`, `AnalyticsPartials.outcomes`)
- Modify: `frontend/src/app/workspaces/analytics/tabs/partials.fixture.ts` (the `outcomes` array)

**Interfaces:**
- Consumes: `RunnerEndings` (selector `sb-runner-endings`, inputs `block`, `thinN`) and `RUNNER_ENDINGS_HINT` (V219-5b / V219-5, `./runner-endings`); `RUNNER_ENDINGS_EMPTY` (V219-5, `./partials.fixture`); `AnalyticsPartials.runner_endings`, `counterfactuals.giveback_excluded` (V219-5). For the layout audit: a backend serving `runner_endings` (V219-4 merged into the worktree).
- Produces: removes `PartialsOutcome`, `PartialsBucket`, `AnalyticsPartials.outcomes`, `outcomeSegments`, `BUCKETS` and the fixture's `outcomes`. Nothing new for later tasks.

**Background.** Part 1 dropped the `outcomes` key from the payload, so the "Runner outcome mix" share bar has nothing to read. Its only consumers are `partials.ts` (:81, :167, :209), its fixture and the one helper test (`git grep -n "outcomes\|PartialsOutcome\|PartialsBucket" frontend/src` before and after; after, no hit may remain outside comments). `PartialsBucket` was used only by `BUCKETS`, so it goes too.

Placement. `.panels` is a two-column grid with sparse auto-flow, so a `.wide` panel placed after an odd number of half panels leaves a hole beside the last one. Removing the outcome mix leaves five half panels. The order becomes: Funnel | Does the runner pay?, then **Runner endings** (wide, where the outcome mix sat), then TP2 ladder | Split what-if, then **Giveback** made `.wide` (its histogram is unchanged; only its width changes, so no row is half empty), then Hold times and Breakdown as today. The Giveback strip now reads decidable runners only (Part 1); its hint says so and names `giveback_excluded`.

The breakdown thin test must scope to `.breakdown`: the scorecard adds five thin rows of its own.

- [ ] **Step 1: Write the failing tab tests**

In `partials.spec.ts`, replace the `./partials` import (:12-15) and the fixture import (:16) with:

```ts
import {
  PartialsTab, funnelRows, givebackBins, kpiTiles, ladderRows, monthTrend,
  rText, runnerWaterfall, splitRows, touchRows,
} from './partials';
import { PARTIALS_FIXTURE, RUNNER_ENDINGS_EMPTY } from './partials.fixture';
import { RunnerEndings } from './runner-endings';
```

Delete the test `it('labels each outcome with its average runner R', …)` (:68-72).

In `it('renders every panel from one payload, hero first among the KPIs', …)`, replace the selector list line with:

```ts
    for (const selector of ['sb-runner-endings', 'sb-waterfall', 'sb-histogram', 'sb-strip-plot', 'sb-segmented']) {
```

and add after the loop:

```ts
    expect(el.querySelector('sb-share-bar')).toBeNull();
    expect(el.textContent).not.toContain('Runner outcome mix');
```

In `it('dims thin breakdown rows and switches dimension in place', …)`, change `expect(el.querySelectorAll('tr.thin')).toHaveLength(2);` to `expect(el.querySelectorAll('.breakdown tr.thin')).toHaveLength(2);`.

Append a new block after the `describe('PartialsTab', …)` block:

```ts
describe('PartialsTab Runner endings (v219)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('hosts the section in a wide panel with the payload block and the tab threshold', () => {
    const { fixture, el } = render(PARTIALS_FIXTURE);
    const host = fixture.debugElement.query(By.directive(RunnerEndings)).componentInstance as RunnerEndings;
    expect(host.block()).toBe(PARTIALS_FIXTURE.runner_endings);
    expect(host.thinN()).toBe(10);
    expect(el.querySelector('sb-runner-endings')?.closest('sb-panel')?.classList.contains('wide')).toBe(true);
    expect(hintText(fixture, 'Runner endings definition')).toContain('R, before commissions and tax.');
  });

  it('keeps every half panel paired: Runner endings after the first pair, Giveback wide', () => {
    const { el } = render(PARTIALS_FIXTURE);
    const panels = [...el.querySelectorAll('.panels > sb-panel')];
    const title = (p: Element) => p.querySelector('sb-panel-header')?.getAttribute('title')
      ?? p.querySelector('sb-panel-header h2, sb-panel-header h3')?.textContent?.trim();
    const wide = panels.map((p) => p.classList.contains('wide'));
    expect(wide).toEqual([false, false, true, false, false, true, true, true]);
    expect(panels[2].querySelector('sb-runner-endings')).not.toBeNull();
    expect(panels[5].querySelector('sb-histogram')).not.toBeNull();
    expect(title(panels[1])).toContain('Does the runner pay?');
  });

  it('says how many closed runners the Giveback strip left out', () => {
    const { fixture } = render(PARTIALS_FIXTURE);
    const texts = fixture.debugElement.queryAll(By.directive(Hint))
      .map((d) => d.componentInstance as Hint).filter((h) => h.label() === 'Giveback definition').map((h) => h.text());
    expect(texts.some((t) => t.includes('2 closed runners left out'))).toBe(true);
  });

  it('renders all-open runners as measured zeros, not an error or the empty state', () => {
    const { el } = render({ ...PARTIALS_FIXTURE, runner_endings: RUNNER_ENDINGS_EMPTY });
    expect(el.querySelector('sb-panel-error')).toBeNull();
    expect(el.querySelector('sb-empty-state')).toBeNull();
    expect([...el.querySelectorAll('sb-runner-endings .card-share')].map((c) => c.textContent?.trim()))
      .toEqual(['—', '—', '—', '—']);
  });
});
```

(`title()` tries the header's `title` attribute first: `sb-panel-header` takes `title` as an input, and Angular leaves a static input's attribute on the host element. If the attribute is absent in this build, the fallback reads the rendered heading. Read `frontend/src/app/ui/panel-header.ts` once if both come back `undefined`, and point the fallback at its heading element; do not change the component.)

- [ ] **Step 2: Run them to verify they fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/partials.spec.ts`
Expected: FAIL — no `sb-runner-endings` in the tab, `sb-share-bar` still present, the wide-panel pattern differs, no "left out" Giveback hint.

- [ ] **Step 3: Wire the tab**

In `partials.ts`:

1. Imports. In the `../../../api/models` import, drop `PartialsBucket`. Delete the line `import { ShareBar, ShareSegment } from '../../../ui/share-bar';`. After the `../../../ui/waterfall` import add:

```ts
import { RUNNER_ENDINGS_HINT, RunnerEndings } from './runner-endings';
```

2. Delete the `BUCKETS` constant (:34-40) and the `outcomeSegments` function with its blank line (:80-85).

3. In the `@Component` `imports:` array, replace `ShareBar` with `RunnerEndings`.

4. Replace the template lines from `<sb-panel><sb-panel-header title="Funnel"` through the Giveback panel's closing `</sb-panel>` (:164-176) with:

```html
          <sb-panel><sb-panel-header title="Funnel" [n]="p.n" hint="Share of filled trades reaching each stage." />
            <sb-bar-list [rows]="funnel()" mode="rate" [format]="pctFmt" /></sb-panel>
          <sb-panel><sb-panel-header title="Does the runner pay?" [n]="p.kpis.beat_all_out_n" [hint]="runnerPayHint" />
            <sb-waterfall [steps]="waterfall()" [format]="rFmt" totalLabel="Actual ExpR" /></sb-panel>
          <sb-panel class="wide"><sb-panel-header title="Runner endings" [n]="p.runner_endings.n" [hint]="runnerEndingsHint" />
            <sb-runner-endings [block]="p.runner_endings" [thinN]="p.thin_n" /></sb-panel>
          <sb-panel><sb-panel-header title="TP2 ladder" [n]="ladderN()" [hint]="ladderHint" />
            <sb-bar-list [rows]="ladder()" [format]="rFmt" />
            <sb-bar-list [rows]="touches()" mode="rate" [format]="pctFmt" /></sb-panel>
          <sb-panel><sb-panel-header title="Split what-if" [n]="p.kpis.beat_all_out_n" [hint]="splitHint" />
            <sb-bar-list [rows]="split()" [format]="rFmt" /></sb-panel>
          <sb-panel class="wide"><sb-panel-header title="Giveback" [n]="p.counterfactuals.giveback.length" [hint]="givebackHint()" />
            <sb-histogram [bins]="giveback()" /></sb-panel>
```

5. In the class, delete `readonly outcomes = computed(() => this.shape(outcomeSegments, []));` and add, after `readonly splitHint = …;`:

```ts
  /* v219: the section's header carries the basis of its R; the Giveback strip
   * reads the same decidable runners as the section's path figures. */
  readonly runnerEndingsHint = RUNNER_ENDINGS_HINT;
  readonly givebackHint = computed(() => 'Best R the runner saw minus the R it banked, over the decidable '
    + `runners Runner endings reads; ${this.data()?.counterfactuals.giveback_excluded ?? 0} closed runners `
    + 'left out (manual closes, no TP2, no price path, TP2 at or below TP1).');
```

- [ ] **Step 4: Drop `outcomes` from the model and fixture**

In `models.ts`, delete the `PartialsBucket` type line, the `PartialsOutcome` interface line and `outcomes: PartialsOutcome[];` inside `AnalyticsPartials`. In `partials.fixture.ts`, delete the `outcomes: [ … ],` array (9 lines). Then:

Run: `git grep -n "outcomes\b\|PartialsOutcome\|PartialsBucket\|outcomeSegments\|BUCKETS" -- frontend/src`
Expected: no hit in `partials.ts`, `partials.spec.ts`, `partials.fixture.ts` or `models.ts` (hits in unrelated features that use their own `outcomes` field are not this task's; read each remaining hit's file name to confirm).

- [ ] **Step 5: Run the specs to verify they pass**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/partials.spec.ts --include src/app/workspaces/analytics/tabs/runner-endings.spec.ts --include src/app/stores/analytics.partials.spec.ts`
Expected: PASS, 0 failed. Then type-check the whole app once: `cd frontend && npx tsc -p tsconfig.app.json --noEmit` → no errors (a stale `outcomes` reference anywhere fails here).

- [ ] **Step 6: Three-width layout audit of `/insights/analytics?tab=partials`**

Needs V219-4 merged into this worktree (the backend must serve `runner_endings`).

1. The worktree's gitignored `.env` must point `DATABASE_URL` at the shared `swing-db` (port 56789, `.env` credentials; never print them). Run `/replicate-prod-db` first so the tab has real runners.
2. `cd frontend && npm run build`, then copy the build over the served bundle: `cp -r frontend/dist/frontend/browser/. swingbot/admin/static/app/` (`admin_ui.py` serves `static/app`, not `dist`; check the served `main-*.js` name equals the one in `dist`).
3. `python admin_ui.py` (a local instance from `.env`'s values), then `node frontend/scripts/browse.mjs login --base http://localhost:1234`.
4. `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440` → fix every finding on `/insights/analytics?tab=partials` and re-run until it exits 0. Findings on other routes are not this task's; list them in the report.
5. At most four clipped shots, e.g. `node frontend/scripts/browse.mjs shots --base http://localhost:1234 --path "/insights/analytics?tab=partials" --widths 390 --clip "sb-runner-endings"`, and the same at 768 and 1440. Check: four cards in a row at 1440 and 2×2 at 768 and 390; the scorecard scrolls inside its panel with the Ending column pinned and opaque; each odds bar stacks (label, full-width track, wrapping legend) at 390; the Giveback row is set apart; "thin" tags show; nothing widens the page.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/partials.ts frontend/src/app/workspaces/analytics/tabs/partials.spec.ts frontend/src/app/api/models.ts frontend/src/app/workspaces/analytics/tabs/partials.fixture.ts
git commit -m "feat(ui): Partials tab shows Runner endings in place of the outcome mix; layout audit clean at 390/768/1440 (V219-6)"
```

Commit any audit fix inside `runner-endings.ts` separately, naming the finding (`fix(ui): …`).


# Phase 4 — Release

### Task V219-7: Release: ui minor, bot patch, version history

**Model:** haiku — a fixed `VERSION.json` bump and one generator run, no judgement calls.

**Files:**
- Modify: `VERSION.json`
- Modify: `swingbot/admin/version_history.json` (regenerated, never hand-edited)

**Interfaces:**
- Consumes: V219-1..V219-6 (and V219-5b) committed in the worktree, each green on its narrow run.
- Produces: nothing in code; the release marker and the regenerated history.

**Background.** `docs/claude/working-conventions.md` § How: the bump is its own commit and goes **last**; then `python scripts/dev/build_version_matrix.py` regenerates `swingbot/admin/version_history.json`, which is committed separately. The generator walks `git log` for `VERSION.json`, so the bump must be committed **before** it runs (an uncommitted bump is recorded as `"commit": "uncommitted"`). `tests/scripts/test_build_version_matrix.py::test_the_committed_file_matches_the_current_generator` fails if the file's `current` pair differs from `VERSION.json`. Levels (index header): **ui minor** (a new section on the Partials tab), **bot patch** (the `/analytics/partials` payload swaps `outcomes` for `runner_endings`; no bot behaviour changes). The generator takes no flags: any argument, `--help` included, still runs it and rewrites the file.

- [ ] **Step 1: Read the current versions**

Run: `git fetch origin && git show origin/main:VERSION.json && cat VERSION.json`
Use the higher of the two pairs as the base (another plan may have released on `main` since this worktree branched; the merge would otherwise reuse a number, as `8bf3e79c` had to fix). At plan time the base is `ui 1.40.3`, `bot 2.17.3`, which gives `ui 1.41.0`, `bot 2.17.4`.

- [ ] **Step 2: Bump `VERSION.json`**

Set `ui` to the next minor (`X.Y.Z` → `X.(Y+1).0`), `bot` to the next patch (`X.Y.Z` → `X.Y.(Z+1)`), and both `ui_updated` and `bot_updated` to the UTC time from `date -u '+%Y-%m-%d %H-%M-%S'`. From the plan-time base the file reads:

```json
{
  "ui": "1.41.0",
  "bot": "2.17.4",
  "ui_updated": "<date -u output>",
  "bot_updated": "<date -u output>"
}
```

(keep the file's existing key order and two-space indent; replace `<date -u output>` with the real stamp, e.g. `2026-11-09 10-15-00`).

- [ ] **Step 3: Commit the bump**

```bash
git add VERSION.json
git commit -m "release(ui,bot): ui 1.41.0, bot 2.17.4 -- Partials tab Runner endings: ending cards, scorecard, odds; outcomes key replaced (v219)"
```

(use the numbers from Step 2 if the base moved).

- [ ] **Step 4: Regenerate the history and check it**

Run: `python scripts/dev/build_version_matrix.py`
Expected: `wrote swingbot\admin\version_history.json: 2 components, <N> releases`.

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: PASS, 0 failed. Then `git diff swingbot/admin/version_history.json` shows the new pair with this bump's commit hash (not `"uncommitted"`).

- [ ] **Step 5: Commit the history**

```bash
git add swingbot/admin/version_history.json
git commit -m "chore(ui,bot): 1.41.0 / 2.17.4 -- Partials tab Runner endings (v219)"
```

No full suite here: CI runs it after the push (CLAUDE.md § Commands).
