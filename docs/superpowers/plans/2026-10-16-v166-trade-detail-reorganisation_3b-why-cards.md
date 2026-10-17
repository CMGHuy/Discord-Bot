# v166 Trade detail reorganisation. Part 3b: Why cards and the area map (TD8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task TD8:" -A 400 docs/superpowers/plans/2026-10-16-v166-trade-detail-reorganisation_3b-why-cards.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v166-trade-detail-reorganisation-design.md`](../specs/2026-10-16-v166-trade-detail-reorganisation-design.md) (this part: § 4 Scores, Level sources, Context's Strategy record; § 7 the computed area map and absent cards; Amendment 1; panel rows on neutral score bars and the "not win probabilities" note)
**Index:** [`2026-10-16-v166-trade-detail-reorganisation_0-index.md`](2026-10-16-v166-trade-detail-reorganisation_0-index.md) carries the header, `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints.

**Why a separate file.** Part 3 (`_3-cards.md`) holds TD7, which alone runs past 1000 lines; TD8 would push that file over the 1500-line cap, and a task is never split or compressed, so TD8 sits here. Ledger, ids, files and contracts are unchanged.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation` (created in TD1 Step 1). Never `cd`; use `git -C $WT` and `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`. All file paths below are relative to `$WT`.

**`GATES`** (from the index) = `--include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts`.

**Order.** TD8 needs only types already on `main` (`Confirmation` from the store, `StrategyRow` from `api/models.ts`). It creates new files only, so it may run beside TD5, TD6 and TD7. It mounts nothing in `trade-detail.ts`: TD9 (Why tab) does, and TD11 adds the container-query CSS that consumes `areaStyle`.

**Shared card styling** (as in part 3). Each card is one `sb-panel` inside a component whose `:host` is `display: block; min-width: 0`. No outer margin on a card (spacing between cards is the grid's `gap`, TD11), no file defines `.pos`, `.neg`, `.muted`, `.head`, `.note`, `.chips` or `.row-link`, no hex literal, only tokens that exist.

---

# Phase 3 — Presentational cards (continued)

### Task TD8: Why cards and the area map: `sb-trade-scores-card`, `sb-trade-level-sources`, `sb-trade-strategy-record`, `whyAreas`

**Model:** sonnet — presentational components and one pure layout function

**Files:**
- Create: `frontend/src/app/workspaces/trades/scores-card.ts`
- Create: `frontend/src/app/workspaces/trades/scores-card.spec.ts`
- Create: `frontend/src/app/workspaces/trades/level-sources-card.ts`
- Create: `frontend/src/app/workspaces/trades/level-sources-card.spec.ts`
- Create: `frontend/src/app/workspaces/trades/strategy-record-card.ts`
- Create: `frontend/src/app/workspaces/trades/strategy-record-card.spec.ts`
- Create: `frontend/src/app/workspaces/trades/why-areas.ts`
- Create: `frontend/src/app/workspaces/trades/why-areas.spec.ts`

**Interfaces:**
- Consumes (`main`): `Confirmation {strategy: string; horizon: string | null}` from `frontend/src/app/stores/trade-detail.store.ts`; `StrategyRow` from `frontend/src/app/api/models.ts:692` (`strategy`, `status`, `n`, `win_rate`, `expectancy_r`, `window`, `run_date`, `live_n`, `live_wr`, `delta_vs_oos`, `decayed`, `evidence_decay`, `gate_description`, `win_rate_series`); `Panel` (`sb-panel`) from `ui/layout.ts`; `num`, `pct`, `text` from `ui/format.ts`.
- Produces (`scores-card.ts`, consumed by TD9): `SCORES_NOTE = 'Scores rank setups; they are not win probabilities.'`; `scoreWidth(value: number | null): number | null` (clamped 0..100, null for null or non-finite); component `ScoresCard`, selector `sb-trade-scores-card`, inputs `confidence = input<number | null>(null)`, `level = input<number | null>(null)`, `quality = input<number | null>(null)`, `badge = input<string | null>(null)`. DOM: `sb-panel` headed `Scores`, `div[data-score="confidence|quality|badge"]` rows, `span.fill` bars, `p.scores-foot`.
- Produces (`level-sources-card.ts`, consumed by TD9): `hasLevelSources(target: readonly string[], stop: readonly string[], target2: readonly string[], confirmedBy: readonly Confirmation[]): boolean`; `confirmationText(c: Confirmation): string` (`VWAP (2w)`, or `VWAP` with no horizon); component `LevelSourcesCard`, selector `sb-trade-level-sources`, inputs `target`, `stop`, `target2` (`input<readonly string[]>([])`) and `confirmedBy` (`input<readonly Confirmation[]>([])`). DOM: `sb-panel` headed `Level sources`, one `div[data-source="Target|Stop|Target 2|Confirmed by"]` per non-empty list, each holding a `ul` with one `li` per entry.
- Produces (`strategy-record-card.ts`, consumed by TD9 and TD11): component `StrategyRecordCard`, selector `sb-trade-strategy-record`, inputs `strategy = input<string | null>(null)`, `row = input<StrategyRow | null>(null)`, `error = input<string | null>(null)`. DOM: `sb-panel` headed `Strategy record`; the today's-Strategy-tab `dl` (Strategy, Status, OOS sample, OOS win rate, OOS expectancy, Live sample, Live win rate, Live vs OOS, Window), `p.decayed` when decayed, else one `p.record-state` line.
- Produces (`why-areas.ts`, consumed by TD9, TD10 and TD11): `type WhyCard = 'why' | 'scores' | 'sources' | 'breakdown' | 'gates' | 'context'`; `WHY_CARDS: readonly WhyCard[]` (reading order); `interface CardAreas {one: string; two: string; three: string}` (each a `grid-template-areas` value: rows double-quoted, space-separated; `'none'` when nothing is present); `whyAreas(present: ReadonlySet<WhyCard>): CardAreas`; `OVERVIEW_AREAS: CardAreas`; `areaStyle(areas: CardAreas): Record<string, string>` -> `{'--areas-1': one, '--areas-2': two, '--areas-3': three}`.

**Decisions this task fixes** (spec § 4, § 7, amendment 1, panel rows):
- **Area maps** (spec § 7, columns per amendment 1: 3 at container >= 1024 px, 2 at 640-1023 px, 1 below 640 px):
  - Why, three columns: `"why why scores" "sources sources sources" "breakdown breakdown breakdown" "gates gates context"`.
  - Why, two columns: `"why why" "scores context" "sources sources" "breakdown breakdown" "gates gates"`.
  - Why, one column: reading order `why`, `scores`, `sources`, `breakdown`, `gates`, `context`.
  - Overview: three `"plan position outcome"`; two `"plan position" "outcome outcome"`; one `"plan" "position" "outcome"`.
- **One collapse rule** for absent cards: an absent card is dropped from its row; the last card kept in that row absorbs the freed columns; a row left empty is dropped (so no doubled gap). This gives every case the spec names: `scores` spans the row when `why` is absent, `gates` spans when `context` is absent, `context` spans the two-column row when `scores` is absent.
- **Which cards are present** is decided by TD9 (it knows the store and `ABSENT_SECTIONS`); `whyAreas` only lays out the set it is given.
- **Scores:** `Confidence` value `90 · Lv5` (level appended only when known), `Quality` `56`, `Badge` as plain text. Bars use a neutral tint (`--text-secondary` on `--surface-raised`), never `.pos`/`.neg`; a null score shows `—` and no bar. The muted line `Scores rank setups; they are not win probabilities.` always shows.
- **Level sources:** rows `Target` / `Stop` / `Target 2` / `Confirmed by`, each a list, a row hidden when its list is empty. TD9 does not mount the card when `hasLevelSources` is false.
- **Strategy record:** today's Strategy-tab content moved as is (same rows, formatters, decayed warning and the three fallback lines `<error>`, `This position has no strategy recorded.`, `The registry has no entry for <strategy>.`), under the heading `Strategy record`.
- **Three device classes** (`docs/claude/ui-design.md` § Device classes, § Checklist): these cards hold no controls, so there is no touch target to size, and none is a paged data table. They render the same markup on phone (< 640), tablet (640-1023) and desktop (>= 1024): `min-width: 0` hosts and `overflow-wrap: anywhere` on list items and values let a card shrink to a phone-width cell without horizontal page scroll. The per-class column count lives only in the area maps above (consumed by TD11's container queries); nothing here queries the viewport.

- [ ] **Step 1: Write the failing area-map spec**

Create `frontend/src/app/workspaces/trades/why-areas.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { CardAreas, OVERVIEW_AREAS, WHY_CARDS, WhyCard, areaStyle, whyAreas } from './why-areas';

function present(...cards: WhyCard[]): ReadonlySet<WhyCard> {
  return new Set(cards);
}

function without(...absent: WhyCard[]): ReadonlySet<WhyCard> {
  return new Set(WHY_CARDS.filter((card) => !absent.includes(card)));
}

/** `"a a b" "c c c"` -> [['a','a','b'], ['c','c','c']] */
function grid(areas: string): string[][] {
  return [...areas.matchAll(/"([^"]*)"/g)].map((match) => match[1].split(' '));
}

describe('whyAreas', () => {
  it('lays out every card as the spec draws it', () => {
    expect(whyAreas(without())).toEqual<CardAreas>({
      one: '"why" "scores" "sources" "breakdown" "gates" "context"',
      two: '"why why" "scores context" "sources sources" "breakdown breakdown" "gates gates"',
      three: '"why why scores" "sources sources sources" "breakdown breakdown breakdown" "gates gates context"',
    });
  });

  it('widens scores across the row when the explanation is absent', () => {
    const areas = whyAreas(without('why'));
    expect(grid(areas.three)[0]).toEqual(['scores', 'scores', 'scores']);
    expect(grid(areas.two)[0]).toEqual(['scores', 'context']);
    expect(areas.one.startsWith('"scores"')).toBe(true);
  });

  it('widens the explanation when scores is absent, and context across the two-column row', () => {
    const areas = whyAreas(without('scores'));
    expect(grid(areas.three)[0]).toEqual(['why', 'why', 'why']);
    expect(grid(areas.two)[1]).toEqual(['context', 'context']);
  });

  it('widens gates when context is absent', () => {
    const areas = whyAreas(without('context'));
    expect(grid(areas.three).at(-1)).toEqual(['gates', 'gates', 'gates']);
    expect(grid(areas.two)[1]).toEqual(['scores', 'scores']);
  });

  it('drops the whole row of an absent full-width card, leaving no empty row', () => {
    const areas = whyAreas(without('sources', 'breakdown'));
    expect(areas.three).toBe('"why why scores" "gates gates context"');
    expect(areas.two).toBe('"why why" "scores context" "gates gates"');
    expect(areas.one).toBe('"why" "scores" "gates" "context"');
  });

  it('collapses a legacy record to gates and context', () => {
    expect(whyAreas(present('gates', 'context'))).toEqual<CardAreas>({
      one: '"gates" "context"',
      two: '"context context" "gates gates"',
      three: '"gates gates context"',
    });
  });

  it("returns 'none' when nothing is present", () => {
    expect(whyAreas(present())).toEqual<CardAreas>({ one: 'none', two: 'none', three: 'none' });
  });

  it('fills every row exactly and names exactly the present cards, for every subset', () => {
    for (let mask = 1; mask < 1 << WHY_CARDS.length; mask++) {
      const cards = WHY_CARDS.filter((_, i) => mask & (1 << i));
      const areas = whyAreas(new Set(cards));
      for (const [key, columns] of [['one', 1], ['two', 2], ['three', 3]] as const) {
        const rows = grid(areas[key]);
        expect(rows.every((row) => row.length === columns)).toBe(true);
        expect(new Set(rows.flat())).toEqual(new Set(cards));
      }
    }
  });
});

describe('OVERVIEW_AREAS and areaStyle', () => {
  it('places plan, position and outcome per column count', () => {
    expect(OVERVIEW_AREAS).toEqual<CardAreas>({
      one: '"plan" "position" "outcome"',
      two: '"plan position" "outcome outcome"',
      three: '"plan position outcome"',
    });
  });

  it('binds the three maps as CSS custom properties', () => {
    expect(areaStyle(OVERVIEW_AREAS)).toEqual({
      '--areas-1': '"plan" "position" "outcome"',
      '--areas-2': '"plan position" "outcome outcome"',
      '--areas-3': '"plan position outcome"',
    });
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/why-areas.spec.ts
```

Expected: FAIL — the build cannot resolve `./why-areas`.

- [ ] **Step 3: Write `why-areas.ts`**

Create `frontend/src/app/workspaces/trades/why-areas.ts`:

```ts
/* v166 — where each card sits in the trade page's card grid (spec § 7).
 *
 * The maps are data, not static CSS, because a card whose content would
 * render nothing is not mounted, and a hole in a fixed map would leave an
 * empty cell beside a narrow card -- the one thing the partner's acceptance
 * rule forbids. TD11's container queries switch between the three values
 * (1 column below 640 px of container width, 2 at 640-1023, 3 at >= 1024;
 * amendment 1). */

export type WhyCard = 'why' | 'scores' | 'sources' | 'breakdown' | 'gates' | 'context';

/** Reading order: the one-column layout and the order TD9 mounts cells in. */
export const WHY_CARDS: readonly WhyCard[] = ['why', 'scores', 'sources', 'breakdown', 'gates', 'context'];

/** `grid-template-areas` values for one, two and three columns. */
export interface CardAreas {
  one: string;
  two: string;
  three: string;
}

/** A card and the columns it spans in its row. */
type Cell = readonly [card: string, span: number];
type Layout = readonly (readonly Cell[])[];

const WHY_THREE: Layout = [
  [['why', 2], ['scores', 1]],
  [['sources', 3]],
  [['breakdown', 3]],
  [['gates', 2], ['context', 1]],
];

const WHY_TWO: Layout = [
  [['why', 2]],
  [['scores', 1], ['context', 1]],
  [['sources', 2]],
  [['breakdown', 2]],
  [['gates', 2]],
];

const WHY_ONE: Layout = WHY_CARDS.map((card) => [[card, 1]] as const);

/** One row's quoted area string, or null when none of its cards is present.
 *  The last card kept absorbs the columns an absent neighbour freed. */
function rowAreas(row: readonly Cell[], present: ReadonlySet<string>, columns: number): string | null {
  const kept = row.filter(([card]) => present.has(card));
  if (kept.length === 0) return null;
  const used = kept.reduce((sum, [, span]) => sum + span, 0);
  const names = kept.flatMap(([card, span], i) =>
    Array<string>(i === kept.length - 1 ? span + columns - used : span).fill(card));
  return `"${names.join(' ')}"`;
}

function layoutAreas(layout: Layout, present: ReadonlySet<string>, columns: number): string {
  const rows = layout.flatMap((row) => {
    const areas = rowAreas(row, present, columns);
    return areas === null ? [] : [areas];
  });
  return rows.length === 0 ? 'none' : rows.join(' ');
}

export function whyAreas(present: ReadonlySet<WhyCard>): CardAreas {
  const cards: ReadonlySet<string> = present;
  return {
    one: layoutAreas(WHY_ONE, cards, 1),
    two: layoutAreas(WHY_TWO, cards, 2),
    three: layoutAreas(WHY_THREE, cards, 3),
  };
}

/** Overview always mounts all three cards. */
export const OVERVIEW_AREAS: CardAreas = {
  one: '"plan" "position" "outcome"',
  two: '"plan position" "outcome outcome"',
  three: '"plan position outcome"',
};

/** The three maps as CSS custom properties for a `[style]` binding on the
 *  grid; TD11's CSS reads `var(--areas-1|2|3)`. */
export function areaStyle(areas: CardAreas): Record<string, string> {
  return { '--areas-1': areas.one, '--areas-2': areas.two, '--areas-3': areas.three };
}
```

- [ ] **Step 4: Run the area-map spec to verify it passes**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/why-areas.spec.ts
```

Expected: all green. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

- [ ] **Step 5: Write the failing card specs**

Create `frontend/src/app/workspaces/trades/scores-card.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { SCORES_NOTE, ScoresCard, scoreWidth } from './scores-card';

function mount(inputs: Record<string, unknown>): ComponentFixture<ScoresCard> {
  const fixture = TestBed.createComponent(ScoresCard);
  for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
  fixture.detectChanges();
  return fixture;
}

function squash(el: Element | null | undefined): string {
  return (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
}

describe('scoreWidth', () => {
  it('clamps a score to a 0..100 bar width', () => {
    expect(scoreWidth(90)).toBe(90);
    expect(scoreWidth(140)).toBe(100);
    expect(scoreWidth(-5)).toBe(0);
  });

  it('draws no bar for an unknown score', () => {
    expect(scoreWidth(null)).toBeNull();
    expect(scoreWidth(Number.NaN)).toBeNull();
  });
});

describe('ScoresCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it("shows SPCX's scores: confidence 90 at Lv5, quality 56, badge WEAK", () => {
    const el = mount({ confidence: 90, level: 5, quality: 56, badge: 'WEAK' }).nativeElement as HTMLElement;
    expect(squash(el.querySelector('h2'))).toBe('Scores');
    expect(squash(el.querySelector('[data-score="confidence"] dd'))).toBe('90 · Lv5');
    expect(squash(el.querySelector('[data-score="quality"] dd'))).toBe('56');
    expect(squash(el.querySelector('[data-score="badge"] dd'))).toBe('WEAK');
  });

  it('says scores are not win probabilities', () => {
    const el = mount({ confidence: 90 }).nativeElement as HTMLElement;
    expect(squash(el.querySelector('.scores-foot'))).toBe(SCORES_NOTE);
    expect(SCORES_NOTE).toBe('Scores rank setups; they are not win probabilities.');
  });

  it('draws neutral bars at the score width, never tinted', () => {
    const el = mount({ confidence: 90, quality: 56 }).nativeElement as HTMLElement;
    const fills = [...el.querySelectorAll<HTMLElement>('span.fill')];
    expect(fills.map((fill) => fill.style.width)).toEqual(['90%', '56%']);
    expect(fills.some((fill) => fill.classList.contains('pos') || fill.classList.contains('neg'))).toBe(false);
  });

  it('prints a dash and no bar for a missing score, and no Lv or badge row when unknown', () => {
    const el = mount({ confidence: null, level: null, quality: 56, badge: null }).nativeElement as HTMLElement;
    expect(squash(el.querySelector('[data-score="confidence"] dd'))).toBe('—');
    expect(el.querySelector('[data-score="confidence"] span.fill')).toBeNull();
    expect(el.querySelector('[data-score="badge"]')).toBeNull();
  });
});
```

Create `frontend/src/app/workspaces/trades/level-sources-card.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Confirmation } from '../../stores/trade-detail.store';
import { LevelSourcesCard, confirmationText, hasLevelSources } from './level-sources-card';

const VWAP: Confirmation = { strategy: 'VWAP', horizon: '2w' };

function mount(inputs: Record<string, unknown>): ComponentFixture<LevelSourcesCard> {
  const fixture = TestBed.createComponent(LevelSourcesCard);
  for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
  fixture.detectChanges();
  return fixture;
}

function items(fixture: ComponentFixture<LevelSourcesCard>, label: string): string[] {
  return [...(fixture.nativeElement as HTMLElement).querySelectorAll(`[data-source="${label}"] li`)]
    .map((li) => (li.textContent ?? '').trim());
}

describe('hasLevelSources and confirmationText', () => {
  it('is false only when all four lists are empty', () => {
    expect(hasLevelSources([], [], [], [])).toBe(false);
    expect(hasLevelSources([], [], ['Fib 2.618'], [])).toBe(true);
    expect(hasLevelSources([], [], [], [VWAP])).toBe(true);
  });

  it('names the confirming strategy with its horizon when known', () => {
    expect(confirmationText(VWAP)).toBe('VWAP (2w)');
    expect(confirmationText({ strategy: 'MACD', horizon: null })).toBe('MACD');
  });
});

describe('LevelSourcesCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('lists what justifies each level and what confirmed the setup', () => {
    const f = mount({ target: ['Fib 1.618', 'Prior high'], stop: ['Swing low'], target2: ['Fib 2.618'], confirmedBy: [VWAP] });
    const el = f.nativeElement as HTMLElement;
    expect((el.querySelector('h2')?.textContent ?? '').trim()).toBe('Level sources');
    expect(items(f, 'Target')).toEqual(['Fib 1.618', 'Prior high']);
    expect(items(f, 'Stop')).toEqual(['Swing low']);
    expect(items(f, 'Target 2')).toEqual(['Fib 2.618']);
    expect(items(f, 'Confirmed by')).toEqual(['VWAP (2w)']);
  });

  it('hides a row whose list is empty', () => {
    const f = mount({ target: ['Fib 1.618'] });
    const labels = [...(f.nativeElement as HTMLElement).querySelectorAll('[data-source]')]
      .map((row) => row.getAttribute('data-source'));
    expect(labels).toEqual(['Target']);
  });
});
```

Create `frontend/src/app/workspaces/trades/strategy-record-card.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { StrategyRow } from '../../api/models';
import { StrategyRecordCard } from './strategy-record-card';

const ROW: StrategyRow = {
  strategy: 'RSI Divergence',
  status: 'VALIDATED',
  n: 42,
  win_rate: 61.9,
  expectancy_r: 0.48,
  window: '2024-01-01..2025-06-30',
  run_date: '2026-09-01',
  live_n: 12,
  live_wr: 58.3,
  delta_vs_oos: -3.6,
  decayed: false,
  evidence_decay: 'fresh',
  gate_description: null,
  win_rate_series: [],
};

function mount(inputs: Record<string, unknown>): ComponentFixture<StrategyRecordCard> {
  const fixture = TestBed.createComponent(StrategyRecordCard);
  for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
  fixture.detectChanges();
  return fixture;
}

function text(fixture: ComponentFixture<StrategyRecordCard>): string {
  return ((fixture.nativeElement as HTMLElement).textContent ?? '').replace(/\s+/g, ' ');
}

function rowLabels(fixture: ComponentFixture<StrategyRecordCard>): string[] {
  return [...(fixture.nativeElement as HTMLElement).querySelectorAll('dl > div > dt')]
    .map((dt) => (dt.textContent ?? '').trim());
}

describe('StrategyRecordCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it("shows today's Strategy-tab rows under the heading Strategy record", () => {
    const f = mount({ strategy: 'RSI Divergence', row: ROW });
    expect(((f.nativeElement as HTMLElement).querySelector('h2')?.textContent ?? '').trim()).toBe('Strategy record');
    expect(rowLabels(f)).toEqual([
      'Strategy', 'Status', 'OOS sample', 'OOS win rate', 'OOS expectancy',
      'Live sample', 'Live win rate', 'Live vs OOS', 'Window',
    ]);
    expect(text(f)).toContain('0.48R');
    expect(text(f)).toContain('2024-01-01..2025-06-30');
    expect((f.nativeElement as HTMLElement).querySelector('.decayed')).toBeNull();
  });

  it('warns when live results have decayed', () => {
    const f = mount({ strategy: 'RSI Divergence', row: { ...ROW, decayed: true } });
    expect(text(f)).toContain("Live results have decayed against this strategy's out-of-sample record.");
  });

  it('says the registry has no entry for an unknown strategy', () => {
    const f = mount({ strategy: 'Volume Profile HVN', row: null });
    expect(text(f)).toContain('The registry has no entry for Volume Profile HVN.');
    expect((f.nativeElement as HTMLElement).querySelector('dl')).toBeNull();
  });

  it('says when no strategy was recorded', () => {
    expect(text(mount({ strategy: null, row: null }))).toContain('This position has no strategy recorded.');
  });

  it('shows the registry error before anything else', () => {
    const f = mount({ strategy: 'RSI Divergence', row: ROW, error: 'Registry unavailable.' });
    expect(text(f)).toContain('Registry unavailable.');
    expect((f.nativeElement as HTMLElement).querySelector('dl')).toBeNull();
  });
});
```

- [ ] **Step 6: Run them to verify they fail**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/scores-card.spec.ts --include src/app/workspaces/trades/level-sources-card.spec.ts --include src/app/workspaces/trades/strategy-record-card.spec.ts
```

Expected: FAIL — the build cannot resolve `./scores-card`, `./level-sources-card` and `./strategy-record-card`.

- [ ] **Step 7: Write `scores-card.ts`**

Create `frontend/src/app/workspaces/trades/scores-card.ts`:

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { num } from '../../ui/format';
import { Panel } from '../../ui/layout';

/** Panel (financial-advisor): a "Confidence 90" beside a WEAK badge reads as
 *  a 90% win chance unless the page says otherwise. */
export const SCORES_NOTE = 'Scores rank setups; they are not win probabilities.';

/** Bar width in percent for a 0-100 score; null draws no bar. */
export function scoreWidth(value: number | null): number | null {
  if (value === null || !Number.isFinite(value)) return null;
  return Math.min(100, Math.max(0, value));
}

/** The Why tab's Scores card (spec § 4). Bars are neutral on purpose: a
 *  score is a rank, not a gain or a loss, so it never borrows --pos/--neg. */
@Component({
  selector: 'sb-trade-scores-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Scores">
      <dl>
        <div data-score="confidence">
          <dt>Confidence</dt>
          <dd>
            <span class="num">{{ fmt(confidence(), 0) }}@if (confidence() !== null && level() !== null) { · Lv{{ level() }} }</span>
            @if (width(confidence()); as pctWidth) {
              <span class="track" aria-hidden="true"><span class="fill" [style.width.%]="pctWidth"></span></span>
            }
          </dd>
        </div>
        <div data-score="quality">
          <dt>Quality</dt>
          <dd>
            <span class="num">{{ fmt(quality(), 0) }}</span>
            @if (width(quality()); as pctWidth) {
              <span class="track" aria-hidden="true"><span class="fill" [style.width.%]="pctWidth"></span></span>
            }
          </dd>
        </div>
        @if (badge(); as label) {
          <div data-score="badge">
            <dt>Badge</dt>
            <dd>{{ label }}</dd>
          </div>
        }
      </dl>
      <p class="scores-foot muted">{{ note }}</p>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    dl { display: grid; gap: var(--space-8); margin: 0; }
    dl > div { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); align-items: center; gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { display: grid; gap: var(--space-4); margin: 0; color: var(--text); font-size: var(--text-table); text-align: right; overflow-wrap: anywhere; }
    .track { display: block; height: 4px; background: var(--surface-raised); border-radius: 2px; }
    .fill { display: block; height: 100%; background: var(--text-secondary); border-radius: 2px; }
    .scores-foot { margin-top: var(--space-10); font-size: var(--text-table); line-height: 1.6; }
  `,
})
export class ScoresCard {
  readonly confidence = input<number | null>(null);
  readonly level = input<number | null>(null);
  readonly quality = input<number | null>(null);
  readonly badge = input<string | null>(null);

  protected readonly note = SCORES_NOTE;
  protected readonly fmt = num;
  protected readonly width = scoreWidth;
}
```

`scoreWidth(0)` is `0`, which `@if (...; as)` treats as falsy, so a score of exactly 0 shows its value with no bar. That is the intended look (an empty bar and no bar read the same).

- [ ] **Step 8: Write `level-sources-card.ts`**

Create `frontend/src/app/workspaces/trades/level-sources-card.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Confirmation } from '../../stores/trade-detail.store';
import { Panel } from '../../ui/layout';

export function confirmationText(c: Confirmation): string {
  return c.horizon ? `${c.strategy} (${c.horizon})` : c.strategy;
}

/** TD9 mounts the card only when this is true (spec § 4: hidden when all
 *  four lists are empty). */
export function hasLevelSources(
  target: readonly string[],
  stop: readonly string[],
  target2: readonly string[],
  confirmedBy: readonly Confirmation[],
): boolean {
  return target.length + stop.length + target2.length + confirmedBy.length > 0;
}

interface SourceRow {
  label: string;
  items: readonly string[];
}

/**
 * The Why tab's Level sources card: what justifies each level, fed straight
 * from the store (`targetSources()`, `stopSources()`, `target2Sources()`,
 * `confirmedBy()`). `WhyPanel`'s `levels` section is not used on the trade
 * page, so the shared component gains no input (spec § 4).
 */
@Component({
  selector: 'sb-trade-level-sources',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Level sources">
      <dl>
        @for (row of rows(); track row.label) {
          <div [attr.data-source]="row.label">
            <dt>{{ row.label }}</dt>
            <dd>
              <ul>
                @for (item of row.items; track $index) {
                  <li>{{ item }}</li>
                }
              </ul>
            </dd>
          </div>
        }
      </dl>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    dl { display: grid; gap: var(--space-8); margin: 0; }
    dl > div { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 3fr); gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { margin: 0; color: var(--text); font-size: var(--text-table); }
    ul { display: grid; gap: var(--space-4); margin: 0; padding: 0; list-style: none; }
    li { overflow-wrap: anywhere; }
  `,
})
export class LevelSourcesCard {
  readonly target = input<readonly string[]>([]);
  readonly stop = input<readonly string[]>([]);
  readonly target2 = input<readonly string[]>([]);
  readonly confirmedBy = input<readonly Confirmation[]>([]);

  protected readonly rows = computed<SourceRow[]>(() =>
    [
      { label: 'Target', items: this.target() },
      { label: 'Stop', items: this.stop() },
      { label: 'Target 2', items: this.target2() },
      { label: 'Confirmed by', items: this.confirmedBy().map(confirmationText) },
    ].filter((row) => row.items.length > 0),
  );
}
```

- [ ] **Step 9: Write `strategy-record-card.ts`**

Create `frontend/src/app/workspaces/trades/strategy-record-card.ts` (the `dl` and the three fallback lines move from `trade-detail.ts`'s `@case ('strategy')` block, :511-574, unchanged in wording and formatters; TD9 deletes the old block):

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { StrategyRow } from '../../api/models';
import { num, pct, text } from '../../ui/format';
import { Panel } from '../../ui/layout';

/** The Why tab's Strategy record (spec § 4, Context cell): the registry's
 *  out-of-sample and live record for this trade's strategy. Read-only on
 *  purpose: the place to change a strategy's numbers is a validation run,
 *  not a trade. */
@Component({
  selector: 'sb-trade-strategy-record',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Strategy record">
      @if (error(); as message) {
        <p class="record-state">{{ message }}</p>
      } @else if (!strategy()) {
        <p class="record-state">This position has no strategy recorded.</p>
      } @else if (row(); as record) {
        <dl>
          <div><dt>Strategy</dt><dd>{{ record.strategy }}</dd></div>
          <div><dt>Status</dt><dd>{{ record.status }}</dd></div>
          <div><dt>OOS sample</dt><dd>{{ fmt(record.n) }}</dd></div>
          <div><dt>OOS win rate</dt><dd>{{ fmtPct(record.win_rate) }}</dd></div>
          <div><dt>OOS expectancy</dt><dd>{{ fmt(record.expectancy_r) }}R</dd></div>
          <div><dt>Live sample</dt><dd>{{ fmt(record.live_n) }}</dd></div>
          <div><dt>Live win rate</dt><dd>{{ fmtPct(record.live_wr) }}</dd></div>
          <div><dt>Live vs OOS</dt><dd>{{ fmtPct(record.delta_vs_oos) }}</dd></div>
          <div><dt>Window</dt><dd>{{ fmtText(record.window) }}</dd></div>
        </dl>
        @if (record.decayed) {
          <!-- The pre-registered decay rule fired: the reason to distrust
               this position's edge, so it belongs on the trade too. -->
          <p class="decayed">Live results have decayed against this strategy's out-of-sample record.</p>
        }
      } @else {
        <p class="record-state">The registry has no entry for {{ fmtText(strategy()) }}.</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    dl { display: grid; gap: var(--space-6); margin: 0; }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { margin: 0; color: var(--text); font-size: var(--text-table); text-align: right; overflow-wrap: anywhere; }
    .record-state {
      padding: var(--space-8);
      border-left: 2px solid var(--border);
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    .decayed { margin-top: var(--space-10); color: var(--warn); font-size: var(--text-table); }
  `,
})
export class StrategyRecordCard {
  readonly strategy = input<string | null>(null);
  readonly row = input<StrategyRow | null>(null);
  readonly error = input<string | null>(null);

  protected readonly fmt = num;
  protected readonly fmtPct = pct;
  protected readonly fmtText = text;
}
```

`.record-state` copies the old `.not-journaled` look (`trade-detail.ts:748`) under a name that says what it is; `trade-detail.ts` keeps its own `.not-journaled` for the Journal tab.

- [ ] **Step 10: Run every TD8 spec and the UI gates**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/why-areas.spec.ts --include src/app/workspaces/trades/scores-card.spec.ts --include src/app/workspaces/trades/level-sources-card.spec.ts --include src/app/workspaces/trades/strategy-record-card.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts
```

Expected: all green. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once. If the confidence cell reads `90 · Lv5` with a doubled or missing space, fix the template's `@if` placement (the `·` sits inside the block, after one space), not the assertion.

Confirm no shared file was touched:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation status --short -- frontend/src/app/workspaces/trades/why frontend/src/app/ui
```

Expected: no output.

- [ ] **Step 11: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation add frontend/src/app/workspaces/trades/why-areas.ts frontend/src/app/workspaces/trades/why-areas.spec.ts frontend/src/app/workspaces/trades/scores-card.ts frontend/src/app/workspaces/trades/scores-card.spec.ts frontend/src/app/workspaces/trades/level-sources-card.ts frontend/src/app/workspaces/trades/level-sources-card.spec.ts frontend/src/app/workspaces/trades/strategy-record-card.ts frontend/src/app/workspaces/trades/strategy-record-card.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation commit -m "feat(ui): trade page Why cards -- Scores, Level sources, Strategy record -- and the computed card-grid area maps"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation status --short
```

Expected: the status command lists no file this task touched.

