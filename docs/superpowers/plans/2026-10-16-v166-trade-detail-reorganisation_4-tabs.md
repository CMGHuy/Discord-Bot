# v166 Trade detail reorganisation. Part 4: the Why and Overview tabs (TD9..TD10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task TD9:" -A 500 docs/superpowers/plans/2026-10-16-v166-trade-detail-reorganisation_4-tabs.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v166-trade-detail-reorganisation-design.md`](../specs/2026-10-16-v166-trade-detail-reorganisation-design.md) (§ 2 Tabs, § 3 Overview, § 4 Why, § 6 Journal, § 7 absent cards; Edge cases; amendments 2, 4, 8)
**Index:** [`2026-10-16-v166-trade-detail-reorganisation_0-index.md`](2026-10-16-v166-trade-detail-reorganisation_0-index.md) carries the header, `## Global Constraints`, `## Review Focus`, `## Parallelisation`, the task ledger and the spec-case rewrite map. Every task below implicitly includes the Global Constraints.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation`. Never `cd`; use `git -C $WT` and `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`. All file paths below are relative to `$WT`.

**`GATES`** = `--include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts` (written out in full in every command below).

**Order.** TD9 then TD10, both on `trade-detail.ts` and `trade-detail.spec.ts`, after TD6 (part 2). TD9 needs TD8 (part 3: `ScoresCard`, `LevelSourcesCard`, `hasLevelSources`, `StrategyRecordCard`, `whyAreas`, `WhyCard`, `CardAreas`). TD10 needs TD7 (part 3: `PlanCard`, `PositionCard`, `OutcomeCard`, `PlanFigures`, `PositionFigures`) and TD9.

**State this part starts from (after TD5, TD6).** `trade-detail.ts` has `header.head` (identity line with `.identity`, `.trade-title .side`, `.tags`, `.actions`) followed by `<sb-outcome-strip>` and `<sb-tab-bar>`; the tabs are still `plan`, `live`, `chart`, `notes`, `strategy`. The Live tab has no Actions panel. `trade-detail.spec.ts` has lost the two stale-flag cases (TD5) and the "offers Close" case (TD6) from describe A, and gained the `TradeDetail — outcome strip (v166)` and `TradeDetail — identity line (v166)` blocks.

**Two binding choices made here, both inside the ledger:**
- The area maps are bound as three single custom properties, `[style.--areas-1]`, `[style.--areas-2]`, `[style.--areas-3]`, not through one `[style]="areaStyle(...)"` object. `ui/spacing.spec.ts` counts a custom property as defined only when some file contains `--name:` or `[style.--name]` (the `calendar.ts` `[style.--heat]` precedent); an object key `'--areas-1'` in `why-areas.ts` matches neither, so `var(--areas-1)` would fail the gate. `areaStyle()` (TD8) stays exported and unused by the page.
- TD9 adds a minimal one-column `.card-grid` rule (`grid-template-areas: var(--areas-1)`), so the named `grid-area` on each cell resolves against a real template from the first commit. TD11 adds the container and the 640 / 1024 queries on top of it.

**Three device classes (`docs/claude/ui-design.md` § Device classes, § Checklist).** Both tabs are designed for phone (< 640), tablet (640–1023) and desktop (>= 1024) at once:
- Columns per class: the grid is one column in reading order on a phone, two on a tablet, three on a desktop, decided by the grid's **container** width, not the viewport (TD9 lays the one-column base and the computed area maps; TD11 adds `@container cards (min-width: 640px | 1024px)`). No per-device saved choice exists on this page.
- The tab bar is the shared `sb-tab-bar` (not edited): four tabs (`Overview · Why · Chart · Journal`) fit at 390 px, it scrolls inside its own strip rather than the page, and its tabs take `min-height: var(--control-h)`, which the touch block in `tokens.css` raises to 44 px on phone and tablet. Tabs switch on click/tap and arrow keys, never on hover.
- No horizontal page scroll: every new wrapper (`.grid-host`, `.card-grid`, `.cell`) carries `min-width: 0` and the grid uses `minmax(0, 1fr)` columns.
- Done means checked at 1440, 1024, 768 and 390 px with Playwright (TD12), never claude-in-chrome.

---

# Phase 4 — Tabs

### Task TD9: Why tab: replaces Strategy; per-cell `WhyPanel` sections, Scores, Level sources, Context; lazy registry on `why`; Why-tab spec rewrites

**Model:** sonnet — template restructuring in one component, layout fixed by the spec

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (imports; `TABS` :40-47; module constants after `ABSENT_SECTIONS` :54; `@Component` `imports:` array; template `@case ('strategy')` :511-573; styles `.panels` :659-664, `.notes, .strategy {}` :708 and `.decayed` :775-779; class body after `stripTiles` (TD5); constructor registry effect :955-962)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (describe A cases :155, :161, :168, :176, :258; describe E cases :544, :550, :559; one new describe block after the TD6 `TradeDetail — identity line (v166)` block)

**Interfaces:**
- Consumes (TD8, `scores-card.ts`): `SCORES_NOTE` (the string `Scores rank setups; they are not win probabilities.`); component `ScoresCard`, selector `sb-trade-scores-card`, inputs `confidence: number | null`, `level: number | null`, `quality: number | null`, `badge: string | null`.
- Consumes (TD8, `level-sources-card.ts`): component `LevelSourcesCard`, selector `sb-trade-level-sources`, inputs `target: readonly string[]`, `stop: readonly string[]`, `target2: readonly string[]`, `confirmedBy: readonly Confirmation[]` (panel `Level sources`, rows `Target` / `Stop` / `Target 2` / `Confirmed by`); `hasLevelSources(target, stop, target2, confirmedBy): boolean`.
- Consumes (TD8, `strategy-record-card.ts`): component `StrategyRecordCard`, selector `sb-trade-strategy-record`, inputs `strategy: string | null`, `row: StrategyRow | null`, `error: string | null` (panel `Strategy record`).
- Consumes (TD8, `why-areas.ts`): `type WhyCard = 'why' | 'scores' | 'sources' | 'breakdown' | 'gates' | 'context'`; `interface CardAreas {one: string; two: string; three: string}`; `whyAreas(present: ReadonlySet<WhyCard>): CardAreas`.
- Consumes (existing store, unchanged): `explanation()`, `targetSources()`, `stopSources()`, `target2Sources()`, `confirmedBy()`, `confidencePoints()`, `confidenceUnevaluated()`, `confidenceFactors()`, `qualityFactors()`, `gates()`, `calendar()`, `sessionsSinceCreated()`, `detailAbsent()`, `strategies()`, `strategiesError()`, `strategyRow()`, `loadStrategies()`.
- Consumes (existing `TradeDetail`): `whySections` (`ABSENT_SECTIONS` on a legacy record, else `WHY_SECTIONS`); `stripTiles` (TD5) as the insertion point.
- Produces (`trade-detail.ts`): `TABS` = plan, live, chart, notes, why (interim; TD10 makes it final); `TradeDetail.whyPresent: Signal<ReadonlySet<WhyCard>>`; `TradeDetail.whyGrid: Signal<CardAreas>`; `TradeDetail.cellSections` (module constant `CELL_SECTIONS`, one `WhySection` list per WhyPanel cell); the `.grid-host`, `.card-grid`, `.cell`, `.context` style rules that TD10 reuses and TD11 extends.
- Produces (Why tab DOM, ledger TD9): `div.grid-host > div.card-grid.why-grid` carrying `[style.--areas-1|2|3]`, holding one `div.cell[data-area="<card>"]` per present card, in reading order `why`, `scores`, `sources`, `breakdown`, `gates`, `context`, each with `style="grid-area: <card>"`. A legacy record's `p.no-detail` sits above `div.grid-host`.

**Rules (spec § 4, § 7 Absent cards, Review Focus 3).** A card is mounted only when it would render something, and its area is then absent from `whyAreas()`:
- `why`: the `explanation` section is allowed by `whySections()` and `store.explanation()` is not null.
- `scores`: any of `confidence_score`, `confidence_level`, `quality_score`, `badge` is not null (a legacy row carries none, so Why collapses to gates + context there).
- `sources`: the `levels` section is allowed (it is not, on a legacy record) and `hasLevelSources(...)` is true.
- `breakdown`: the `confidence` section is allowed and there is at least one confidence point, confidence factor or quality factor — the same three terms as WhyPanel's own condition (`why-panel.ts:52`).
- `gates`: the `gates` section is allowed (always, today).
- `context`: always (the calendar section is in both section lists, and the Strategy record always has a line to say).

The Plan tab is left as it is in this task (it still hosts the full `sb-why-panel` and its own no-detail note), so describe E's `hosts the levels block, the two plan panels and the Why panel on the Plan tab` stays green until TD10 deletes the tab.

**Device classes (`docs/claude/ui-design.md`).** Phone: one column in reading order (`--areas-1`, laid here). Tablet and desktop: `--areas-2` / `--areas-3` from `whyAreas()`, switched by the grid's container width in TD11. The cells carry `min-width: 0` so a long source list or gate row wraps inside its card instead of scrolling the page.

- [ ] **Step 1: Rewrite the eight Why cases and add the Why-tab block**

In `frontend/src/app/workspaces/trades/trade-detail.spec.ts`, describe A (`TradeDetail — the fields that rendered nowhere`), replace

```ts
  it('renders the explanation on the Plan tab', () => {
    expect(render('plan')).toContain(
      'Price reclaimed the 50-day after a three-week base.',
    );
  });

  it('renders what confirmed the setup', () => {
    const text = render('plan');
    expect(text).toContain('Confirmed by');
    expect(text).toContain('VWAP');
    expect(text).toContain('2w');
  });

  it('renders what justifies each level', () => {
    const text = render('plan');
    expect(text).toContain('Target confirmed by');
    expect(text).toContain('Fib 1.618');
    expect(text).toContain('Stop confirmed by');
    expect(text).toContain('Swing low');
  });

  it('renders both breakdowns', () => {
    const text = render('plan');
```

with

```ts
  it('renders the explanation on the Why tab', () => {
    expect(render('why')).toContain(
      'Price reclaimed the 50-day after a three-week base.',
    );
  });

  it('renders what confirmed the setup', () => {
    const text = render('why');
    expect(text).toContain('Confirmed by');
    expect(text).toContain('VWAP');
    expect(text).toContain('2w');
  });

  it('renders what justifies each level', () => {
    // v166: the trade page's own Level sources card, not WhyPanel's
    // "Levels & methods" section (spec § 4).
    const text = render('why');
    expect(text).toContain('Level sources');
    expect(text).toContain('Fib 1.618');
    expect(text).toContain('Swing low');
  });

  it('renders both breakdowns', () => {
    const text = render('why');
```

(the rest of `renders both breakdowns` is unchanged). In `says a legacy record has no detail rather than showing blank panels`, change its first line

```ts
    const text = render('plan', {
```

to

```ts
    const text = render('why', {
```

leaving its detail object and its three `expect` lines unchanged.

In describe E (`TradeDetail — the shared Why components (v151)`), replace

```ts
  it('renders the level sources exactly once', () => {
    const text = mount('plan').textContent ?? '';
    expect(text.split('Target confirmed by').length - 1).toBe(1);
    expect(text.split('Stop confirmed by').length - 1).toBe(1);
  });

  it('shows the gate margins section with its caveat on the Plan tab', () => {
    const text = mount('plan').textContent ?? '';
```

with

```ts
  it('renders each level source exactly once on the Why tab', () => {
    // v151 showed the sources in two panels at once; v166 has one card for
    // them, and WhyPanel's levels section is not mounted on this page.
    const text = mount('why').textContent ?? '';
    expect(text.split('Fib 1.618').length - 1).toBe(1);
    expect(text.split('Swing low').length - 1).toBe(1);
  });

  it('shows the gate margins section with its caveat on the Why tab', () => {
    const text = mount('why').textContent ?? '';
```

(the rest of that case is unchanged), and in `keeps the gate rows on a legacy record that has no detail` change

```ts
    const el = mount('plan', {
```

to

```ts
    const el = mount('why', {
```

leaving the rest of that case unchanged.

Add this import after the `./trade-detail` import at the top of the file:

```ts
import { SCORES_NOTE } from './scores-card';
```

Then add this describe block directly after the `TradeDetail — identity line (v166)` block (TD6):

```ts
describe('TradeDetail — Why tab (v166)', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  /** Mount on the Why tab (unless another is named) and settle the detail. */
  function mount(detail: object = DETAIL, overrides: object = {}, tab = 'why') {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail, 'ACTIVE', overrides));
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  const cells = (el: HTMLElement) =>
    [...el.querySelectorAll('.grid-host > .card-grid.why-grid > .cell')].map((node) =>
      node.getAttribute('data-area'),
    );

  function cell(el: HTMLElement, area: string): HTMLElement {
    const found = el.querySelector<HTMLElement>(`.why-grid > .cell[data-area="${area}"]`);
    if (!found) throw new Error(`no Why cell "${area}"`);
    return found;
  }

  /* A record that predates detail capture (spec Edge cases). */
  const LEGACY = {
    ...DETAIL,
    explanation: null,
    confirmed_by: [],
    target_sources: [],
    stop_sources: [],
    target2_sources: [],
    confidence_breakdown: null,
    quality_breakdown: [],
    status_history: [],
  };
  /* ...and a row with no scores, as a legacy row has. */
  const NO_SCORES = { confidence_score: null, confidence_level: null, quality_score: null, badge: null };

  it('lays every card out in reading order on a full record', () => {
    expect(cells(mount().el)).toEqual(['why', 'scores', 'sources', 'breakdown', 'gates', 'context']);
  });

  it('mounts one WhyPanel section per cell', () => {
    const { el } = mount();
    expect(cell(el, 'why').textContent).toContain('Why this trade');
    expect(cell(el, 'why').textContent).not.toContain('Gate margins');
    expect(cell(el, 'breakdown').textContent).toContain('Quality breakdown');
    expect(cell(el, 'breakdown').textContent).not.toContain('Why this trade');
    expect(cell(el, 'gates').textContent).toContain("Gate margins (vs today's thresholds)");
    expect(cell(el, 'context').textContent).toContain('Calendar in the holding window');
    expect(cell(el, 'context').querySelector('sb-trade-strategy-record')).not.toBeNull();
  });

  it('never mounts WhyPanel\'s levels section on the Why tab', () => {
    expect(mount().el.textContent).not.toContain('Levels & methods');
  });

  it('shows the scores with their caveat', () => {
    const text = cell(mount().el, 'scores').textContent ?? '';
    expect(text).toContain('78');
    expect(text).toContain('Lv4');
    expect(text).toContain('80');
    expect(text).toContain('VALIDATED');
    expect(text).toContain(SCORES_NOTE);
  });

  it('drops the explanation cell when there is no explanation', () => {
    expect(cells(mount({ ...DETAIL, explanation: null }).el)).toEqual([
      'scores', 'sources', 'breakdown', 'gates', 'context',
    ]);
  });

  it('drops the Scores cell when the record carries no score', () => {
    expect(cells(mount(DETAIL, NO_SCORES).el)).not.toContain('scores');
  });

  it('drops the Level sources cell when every source list is empty', () => {
    const { el } = mount({
      ...DETAIL, confirmed_by: [], target_sources: [], stop_sources: [], target2_sources: [],
    });
    expect(cells(el)).not.toContain('sources');
    expect(el.querySelector('sb-trade-level-sources')).toBeNull();
  });

  it('drops the breakdown cell when there are no points and no factors', () => {
    const { el } = mount({ ...DETAIL, confidence_breakdown: null, quality_breakdown: [] });
    expect(cells(el)).not.toContain('breakdown');
  });

  it('collapses a legacy record to its gate rows and context, under the no-detail note', () => {
    const { el } = mount(LEGACY, NO_SCORES);
    expect(cells(el)).toEqual(['gates', 'context']);
    expect(el.querySelector('p.no-detail')?.textContent).toContain(
      'logged before the admin UI captured the full alert detail',
    );
  });

  it('fetches the strategy registry on first arrival at Why', () => {
    mount();
    backend.expectOne('/api/v1/analytics/strategies').flush({ strategies: [], heatmap: {} });
  });

  it('does not fetch the registry on another tab', () => {
    mount(DETAIL, {}, 'chart');
    expect(backend.match('/api/v1/analytics/strategies')).toHaveLength(0);
  });

  it('shows the Strategy record under Context once the registry answers', () => {
    const { fixture, el } = mount();
    backend.expectOne('/api/v1/analytics/strategies').flush({ strategies: [], heatmap: {} });
    fixture.detectChanges();
    expect(cell(el, 'context').textContent).toContain('Strategy record');
  });

  it('has a Why tab and no Strategy tab', () => {
    const labels = [...mount().el.querySelectorAll('sb-tab-bar .tab .label')].map((label) =>
      label.textContent?.trim(),
    );
    expect(labels).toContain('Why');
    expect(labels).not.toContain('Strategy');
  });
});
```

`tradeResponse()` defaults give the scores asserted above (`confidence_score` 78, `confidence_level` 4, `quality_score` 80, `badge` `'VALIDATED'`). `DETAIL` carries a confidence breakdown and a quality breakdown, so `breakdown` is present on the full record.

- [ ] **Step 2: Run the page spec to verify the new cases fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts`
Expected: FAIL — the rewritten describe-A and describe-E cases (`why` is an unknown tab today and renders Plan, which has no `Level sources` card) and the `TradeDetail — Why tab (v166)` cases (`no Why cell ...`, empty `cells`, no registry request). Every other block passes.

- [ ] **Step 3: Replace the Strategy tab with Why in `trade-detail.ts`**

Add these imports after the `./trade-figures` import (TD6):

```ts
import { LevelSourcesCard, hasLevelSources } from './level-sources-card';
import { ScoresCard } from './scores-card';
import { StrategyRecordCard } from './strategy-record-card';
import { CardAreas, WhyCard, whyAreas } from './why-areas';
```

Add `ScoresCard,`, `LevelSourcesCard,` and `StrategyRecordCard,` to the `@Component` `imports:` array (after `OutcomeStrip,`).

Replace `TABS` and its doc comment:

```ts
/** Plan · Live · Chart · Notes · Strategy — spec 3's five, in its order. */
const TABS: Tab[] = [
  { id: 'plan', label: 'Plan' },
  { id: 'live', label: 'Live' },
  { id: 'chart', label: 'Chart' },
  { id: 'notes', label: 'Notes' },
  { id: 'strategy', label: 'Strategy' },
];
```

with

```ts
/** v166 (interim, TD9): Why replaces Strategy. TD10 replaces Plan and Live
 *  with Overview and renames Notes to Journal. */
const TABS: Tab[] = [
  { id: 'plan', label: 'Plan' },
  { id: 'live', label: 'Live' },
  { id: 'chart', label: 'Chart' },
  { id: 'notes', label: 'Notes' },
  { id: 'why', label: 'Why' },
];
```

Directly after the `ABSENT_SECTIONS` constant, add:

```ts
/** One WhyPanel section per Why-tab cell (spec § 4). Each section is already
 *  its own sb-panel, so one instance per grid cell reuses the shared
 *  component unchanged. Its `levels` section is not used on this page: the
 *  Level sources card replaces it. */
const CELL_SECTIONS = {
  why: ['explanation'],
  breakdown: ['confidence'],
  gates: ['gates'],
  calendar: ['calendar'],
} as const satisfies Record<string, readonly WhySection[]>;

/** What decides whether each Why card would render anything. */
interface WhyInputs {
  allowed: readonly WhySection[];
  explanation: string | null;
  hasScores: boolean;
  hasSources: boolean;
  hasBreakdown: boolean;
}

/**
 * The Why cards that would render something (spec § 7 "Absent cards"). A card
 * that would render nothing is not mounted, and `whyAreas()` drops its area so
 * its row partner widens instead of leaving a hole. A section excluded by
 * `ABSENT_SECTIONS` (a legacy record) is absent too.
 */
function presentWhyCards(inputs: WhyInputs): ReadonlySet<WhyCard> {
  const { allowed } = inputs;
  const present = new Set<WhyCard>(['context']);
  if (allowed.includes('explanation') && inputs.explanation !== null) present.add('why');
  if (inputs.hasScores) present.add('scores');
  if (allowed.includes('levels') && inputs.hasSources) present.add('sources');
  if (allowed.includes('confidence') && inputs.hasBreakdown) present.add('breakdown');
  if (allowed.includes('gates')) present.add('gates');
  return present;
}
```

In the template, replace the whole `@case ('strategy') { ... }` block (from `@case ('strategy') {` through the `}` that closes it, just before the `}` that closes `@switch`) with:

```html
      @case ('why') {
        @if (store.trade(); as trade) {
          @if (store.detailAbsent()) {
            <!-- Not an error and not an empty card per field: this record
                 predates the detail capture entirely, and nine em dashes read
                 as a failed load rather than as a fact about an old trade. -->
            <p class="no-detail">
              This trade was logged before the admin UI captured the full alert
              detail — only its gate rows and calendar are available here; its
              levels are on Overview.
            </p>
          }
          <!-- v166 -- the reasoning, one card per grid cell. The area map is
               computed (whyAreas), so a card that would render nothing is
               not mounted and its row partner takes the row. -->
          <div class="grid-host">
            <div
              class="card-grid why-grid"
              [style.--areas-1]="whyGrid().one"
              [style.--areas-2]="whyGrid().two"
              [style.--areas-3]="whyGrid().three"
            >
              @if (whyPresent().has('why')) {
                <div class="cell" data-area="why" style="grid-area: why">
                  <sb-why-panel [sections]="cellSections.why" [explanation]="store.explanation()" />
                </div>
              }
              @if (whyPresent().has('scores')) {
                <div class="cell" data-area="scores" style="grid-area: scores">
                  <sb-trade-scores-card
                    [confidence]="trade.confidence_score"
                    [level]="trade.confidence_level"
                    [quality]="trade.quality_score"
                    [badge]="trade.badge"
                  />
                </div>
              }
              @if (whyPresent().has('sources')) {
                <div class="cell" data-area="sources" style="grid-area: sources">
                  <sb-trade-level-sources
                    [target]="store.targetSources()"
                    [stop]="store.stopSources()"
                    [target2]="store.target2Sources()"
                    [confirmedBy]="store.confirmedBy()"
                  />
                </div>
              }
              @if (whyPresent().has('breakdown')) {
                <div class="cell" data-area="breakdown" style="grid-area: breakdown">
                  <sb-why-panel
                    [sections]="cellSections.breakdown"
                    [confidencePoints]="store.confidencePoints()"
                    [confidenceUnevaluated]="store.confidenceUnevaluated()"
                    [confidenceFactors]="store.confidenceFactors()"
                    [qualityFactors]="store.qualityFactors()"
                  />
                </div>
              }
              @if (whyPresent().has('gates')) {
                <div class="cell" data-area="gates" style="grid-area: gates">
                  <sb-why-panel
                    [sections]="cellSections.gates"
                    [status]="trade.status"
                    [barsToExpiry]="trade.bars_to_expiry"
                    [sessionsSinceCreated]="store.sessionsSinceCreated()"
                    [gates]="store.gates()"
                  />
                </div>
              }
              <!-- Context: two panels stacked in one cell (spec § 4) -- the
                   calendar section, then the registry's record for this
                   trade's strategy (read-only: the place to change those
                   numbers is a validation run, not a trade). Always present. -->
              <div class="cell context" data-area="context" style="grid-area: context">
                <sb-why-panel [sections]="cellSections.calendar" [calendar]="store.calendar()" />
                <sb-trade-strategy-record
                  [strategy]="trade.strategy"
                  [row]="store.strategyRow()"
                  [error]="store.strategiesError()"
                />
              </div>
            </div>
          </div>
        }
      }
```

- [ ] **Step 4: Add the class members and retarget the registry effect**

In the `TradeDetail` class, directly after the `stripTiles` computed (TD5), add:

```ts
  /* -- v166: the Why tab ------------------------------------------------- */

  protected readonly cellSections = CELL_SECTIONS;

  /** The Why cards that would render something; see `presentWhyCards`. The
   *  breakdown test mirrors WhyPanel's own confidence condition: points, or
   *  confidence factors, or quality factors. */
  protected readonly whyPresent = computed<ReadonlySet<WhyCard>>(() => {
    const trade = this.store.trade();
    const scores = trade
      ? [trade.confidence_score, trade.confidence_level, trade.quality_score, trade.badge]
      : [];
    return presentWhyCards({
      allowed: this.whySections(),
      explanation: this.store.explanation(),
      hasScores: scores.some((value) => value !== null && value !== undefined),
      hasSources: hasLevelSources(
        this.store.targetSources(),
        this.store.stopSources(),
        this.store.target2Sources(),
        this.store.confirmedBy(),
      ),
      hasBreakdown:
        Object.keys(this.store.confidencePoints() ?? {}).length > 0
        || this.store.confidenceFactors().length > 0
        || this.store.qualityFactors().length > 0,
    });
  });

  /** The Why tab's area map for 1, 2 and 3 columns, bound as --areas-1/2/3. */
  protected readonly whyGrid = computed<CardAreas>(() => whyAreas(this.whyPresent()));
```

In the constructor, replace the registry effect

```ts
    // The registry is only needed by one tab, and it is the same request for
    // every trade -- so it is fetched on first arrival at the tab rather than
    // with the trade.
    effect(() => {
      if (this.activeTab() === 'strategy' && this.store.strategies() === null) {
        untracked(() => this.store.loadStrategies());
      }
    });
```

with

```ts
    // The registry is only needed by one tab (Why's Strategy record, v166),
    // and it is the same request for every trade -- so it is fetched on first
    // arrival at the tab rather than with the trade.
    effect(() => {
      if (this.activeTab() === 'why' && this.store.strategies() === null) {
        untracked(() => this.store.loadStrategies());
      }
    });
```

- [ ] **Step 5: Update the styles**

Replace

```css
    .notes, .strategy {}
```

with

```css
    .notes {}
```

Delete the `.decayed` rule (the warning now lives in `strategy-record-card.ts`, TD8):

```css
    .decayed {
      margin-top: var(--space-10);
      color: var(--warn);
      font-size: var(--text-table);
    }
```

Directly after the `.panels { ... }` rule, add:

```css
    /* v166 -- the card grid the Why and Overview tabs place their cards in.
       One column here, in reading order (the phone layout); TD11 makes
       .grid-host the container and switches to --areas-2 / --areas-3 at
       640 / 1024 px of container width. The maps are computed
       (why-areas.ts) and bound as --areas-1/2/3 on the grid; each cell
       names its own grid-area. */
    .grid-host {
      min-width: 0;
    }
    .card-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: var(--areas-1);
      gap: var(--section-gap);
    }
    .cell {
      min-width: 0;
    }
    /* Two panels stacked in one cell: the calendar, then the Strategy record. */
    .context {
      display: grid;
      align-content: start;
      gap: var(--section-gap);
    }
```

- [ ] **Step 6: Run the page spec and the UI gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts`
Expected: PASS, 0 failed — every block, including the untouched Plan-tab case `hosts the levels block, the two plan panels and the Why panel on the Plan tab` (TD10 rewrites it). `spacing.spec.ts` counts `--areas-1/2/3` as defined through the `[style.--areas-N]` bindings. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

Then confirm the Strategy tab and its markup are gone from the page:

Run: `git -C $WT grep -n -E "'strategy'|class=\"strategy\"|decayed" -- frontend/src/app/workspaces/trades/trade-detail.ts`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git -C $WT commit -m "feat(v166): TD9 Why tab -- reasoning cards in a computed grid, Strategy tab folded in

Why replaces Strategy: explanation, Scores, Level sources, the confidence
and quality breakdown, gate margins, and Context (calendar plus the
Strategy record) -- one WhyPanel section per cell, each cell mounted only
when it would render something, the area map from whyAreas(). A legacy
record collapses to gates and context under the no-detail note. The
registry now loads on first arrival at Why.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task TD10: Overview tab replaces Plan and Live; final four tabs; legacy `?tab=` rewrite; Journal rename; remaining spec rewrites

**Model:** sonnet — template restructuring in one component, routes fixed by the spec

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (imports; `TABS` / `TAB_IDS`; template `@case ('plan')` and `@case ('live')`, `@case ('notes')`; styles `.stale-flag`, `.muted-gap`, `.progress`; class members `stopLabel`, `fmt*`, `activeTab`, `pnlClass`, `goToTab`; constructor)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (imports; describe A cases :187, :197, :206, :214, :237, :245, :251; describe C :400-463 replaced; describe E cases :535, :581; the tab lists in one TD5 case and one TD6 case; one new describe block after the TD9 `TradeDetail — Why tab (v166)` block)

**Interfaces:**
- Consumes (TD7, `plan-card.ts`): `interface PlanFigures {direction: string | null; status: string; entryType: string | null; trigger: number | null; entry: number | null; riskStop: number | null; stopLoss: number | null; workingStop: number | null; target1: number | null; target2: number | null; acceptance: number | null; riskReward: number | null; riskPerShare: number | null; rewardPerShare: number | null}`; component `PlanCard`, selector `sb-trade-plan-card`, input `figures = input.required<PlanFigures>()` (renders the Order/Trigger/Entry/Stop/Working stop/Target rows, `Move your resting stop to <price>` on ACTIVE/PARTIAL when the working stop differs from `risk_stop`, the R:R line and `PAPER_LINE`).
- Consumes (TD7, `position-card.ts`): `interface PositionFigures {status: string; shares: number | null; positionValue: number | null; dollarAtRisk: number | null; sizingMode: string | null; gapP90Pct: number | null; gapFragile: boolean | null; tp1Pct: number | null; breakevenTriggerPct: number | null; trailAtrMult: number | null; expiresOn: string | null; timeExitOn: string | null; holdCapBars: number | null}`; component `PositionCard`, selector `sb-trade-position-card`, input `figures = input.required<PositionFigures>()` (`$ at risk` labelled `open shares, at original stop` on PARTIAL).
- Consumes (TD7, `outcome-card.ts`): component `OutcomeCard`, selector `sb-trade-outcome-card`, inputs `group = input.required<StatusGroup>()`, `direction = input<string | null>(null)`, `target2 = input<number | null>(null)`, `stopLoss = input<number | null>(null)`, `legs = input<readonly Leg[]>([])`, `timeline = input<readonly StatusEvent[]>([])` (Next block `sb-if-it-gets-there` on open/pending, `Exit legs` panel on closed, timeline through `sb-outcome-path`).
- Consumes (TD8, `why-areas.ts`): `OVERVIEW_AREAS: CardAreas` (cells `plan`, `position`, `outcome`).
- Consumes (TD3, `trade-figures.ts`): `type StatusGroup`; `statusGroup(status: string, exitPrice: number | null): StatusGroup` (already imported by TD6).
- Consumes (TD4, `TradeDetailStore`): `riskStop()`, `riskPerShare()`, `dollarAtRisk()`, `workingStop()`, `trailAtrMult()`, `sizingMode()`, `entryType()`; existing `triggerPrice()`, `rewardPerShare()`, `acceptanceLevel()`, `gapP90Pct()`, `gapFragile()`, `tp1Pct()`, `breakevenTriggerPct()`, `expiresOn()`, `timeExitOn()`, `holdCapBars()`, `legs()`, `timeline()`.
- Consumes (TD9): `.grid-host`, `.card-grid`, `.cell` rules; `TABS` with `why`; the registry effect on `why`.
- Consumes (existing): `PAPER_LINE` from `./why/levels-block` (spec assertion only).
- Produces (`trade-detail.ts`): final `TABS` (`overview` Overview, `why` Why, `chart` Chart, `journal` Journal); exported `LEGACY_TABS: Readonly<Record<string, string | null>>` = `{ plan: null, live: null, notes: 'journal', strategy: 'why' }`; `TradeDetail.planFigures: Signal<PlanFigures | null>`, `TradeDetail.positionFigures: Signal<PositionFigures | null>`, `TradeDetail.outcomeGroup: Signal<StatusGroup>`, `TradeDetail.overviewAreas` (= `OVERVIEW_AREAS`).
- Produces (Overview DOM, ledger TD10): `div.grid-host > div.card-grid.overview-grid` carrying `[style.--areas-1|2|3]`, with cells `div.cell[data-area="plan"]`, `[data-area="position"]`, `[data-area="outcome"]`, each with `style="grid-area: <card>"`. TD11 styles both grids through the shared classes.

**Rules (spec § 2, § 3, § 6; Edge cases; amendment 2).**
- Tab resolution: no parameter -> `overview`; a current id -> itself; a legacy id -> its target from `LEGACY_TABS` (`null` -> `overview`), rendered at once and rewritten in the URL with `router.navigate([], { queryParams: { tab }, queryParamsHandling: 'merge', replaceUrl: true })` through `goToTab`; any other value -> `overview`, with the parameter left in the URL (no navigate).
- `goToTab('overview')` writes no parameter (the default is encoded as none).
- The Outcome card gets the stop that applies now (`trade.stop_loss`, the working stop on PARTIAL) for its Next block, and `store.legs()` / `store.timeline()` unchanged.
- Journal is today's Notes body, moved as-is under the new id.
- Dropped: the Plan tab's Levels block, Per share, If-it-gets-there and Sizing panels, the Opened card, the full `sb-why-panel` and its no-detail note (now on Why); the Live tab's Now, Stop to target and Partial position panels and its `sb-outcome-path`. The trade page stops importing `LevelsBlock`, `SizingPanel`, `IfItGetsThere`, `OutcomePath` (the last two are hosted inside `OutcomeCard`) and `Panel`.

**Device classes (`docs/claude/ui-design.md`).** Phone: Plan, Position, Outcome stacked in that order (`--areas-1`). Tablet: `plan position` / `outcome outcome`. Desktop: `plan position outcome`. All three come from `OVERVIEW_AREAS` and switch on the grid's container width in TD11. Four short tab labels fit the 390 px tab strip; the strip scrolls inside itself if a wider font pushes it, never the page.

- [ ] **Step 1: Rewrite the Plan/Live cases and add the tabs-and-Overview block**

In `frontend/src/app/workspaces/trades/trade-detail.spec.ts`, change the imports at the top:

```ts
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
```

to

```ts
import { Router, provideRouter } from '@angular/router';
import { type MockInstance, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
```

and

```ts
import { TradeDetail, arrivalBanner } from './trade-detail';
```

to

```ts
import { LEGACY_TABS, TradeDetail, arrivalBanner } from './trade-detail';
import { PAPER_LINE } from './why/levels-block';
```

**Describe A** (`TradeDetail — the fields that rendered nowhere`). Delete these six cases (each moves, with its intent, into the new block below): `renders the trigger price and the two fractions unsigned`, `renders the timeline on the Live tab`, `renders the scale-out legs, saying which is still open`, `labels the stop "Trailing stop" once TP1 has banked (PARTIAL)`, `labels the stop plain "Stop" before any TP1 (ACTIVE)`, `does not show a Scale-out panel for a position with one leg`. In `shows the trade id in the header`, change

```ts
    const text = render('plan');
```

to

```ts
    const text = render('');
```

**Describe C.** Replace the whole `describe('TradeDetail — partial position panel (v58)', ...)` block with:

```ts
describe('TradeDetail — the banked TP1 leg on PARTIAL (v58, v166)', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  /* v58 showed the runner as its own "Partial position" panel on the Live
   * tab; v166 states the banked leg once, as the strip's Banked tile, on
   * every tab -- never added into the Unrealised figure (amendment 2). */
  function renderPartial(
    legsRealized: unknown[] = [{ fraction: 0.5, exit_price: 110, r: 2.0, reason: 'tp1' }],
    status = 'PARTIAL',
  ) {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', '');
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(
      tradeResponse({ ...DETAIL, legs_realized: legsRealized, working_stop: 101.33 }, status, {
        risk_stop: 95,
        stop_loss: 101.33,
      }),
    );
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  const banked = (el: HTMLElement) =>
    el.querySelector<HTMLElement>('sb-outcome-strip .tile[data-tile="banked"]');

  it('shows the banked leg as its own strip tile once PARTIAL', () => {
    const text = banked(renderPartial())?.textContent ?? '';
    expect(text).toContain('50% @ 110.00');   // the TP1 leg's own fill
    expect(text).toContain('+2.00R');
  });

  it('shows the pct and dollar figures for the banked leg', () => {
    const text = banked(renderPartial())?.textContent ?? '';
    // tradeResponse() defaults entry=100, shares=10: (110-100)*0.5*10 = 50
    expect(text).toContain('+10.00%');
    expect(text).toContain('+50.00');
  });

  it('shows no Banked tile before anything has banked', () => {
    expect(banked(renderPartial([]))).toBeNull();
  });

  it('shows no Banked tile outside PARTIAL', () => {
    expect(banked(renderPartial(undefined, 'ACTIVE'))).toBeNull();
  });

  it('no longer renders a Partial position panel', () => {
    expect(renderPartial().textContent).not.toContain('Partial position');
  });
});
```

**Describe E** (`TradeDetail — the shared Why components (v151)`). Replace

```ts
  it('hosts the levels block, the two plan panels and the Why panel on the Plan tab', () => {
    const el = mount('plan');
    expect(el.querySelector('sb-levels-block')).toBeTruthy();
    expect(el.querySelector('sb-if-it-gets-there')).toBeTruthy();
    expect(el.querySelector('sb-sizing-panel')).toBeTruthy();
    expect(el.querySelector('sb-why-panel')).toBeTruthy();
    expect(el.textContent).toContain('Paper plan — this page places no orders.');
  });
```

with

```ts
  it('hosts the Plan, Position and Outcome cards on Overview, and the Next block', () => {
    // v166 (amendment 4): the trade page has its own cards; LevelsBlock and
    // SizingPanel stay the plan page's. IfItGetsThere is reused, inside the
    // Outcome card, as the Next block of an open trade.
    const el = mount('');
    expect(el.querySelector('sb-trade-plan-card')).toBeTruthy();
    expect(el.querySelector('sb-trade-position-card')).toBeTruthy();
    expect(el.querySelector('sb-trade-outcome-card sb-if-it-gets-there')).toBeTruthy();
    expect(el.querySelector('sb-levels-block')).toBeNull();
    expect(el.querySelector('sb-sizing-panel')).toBeNull();
    expect(el.querySelector('sb-why-panel')).toBeNull();
    expect(el.textContent).toContain(PAPER_LINE);
  });
```

and replace

```ts
  it('hosts the outcome path on the Live tab', () => {
    const el = mount('live');
    expect(el.querySelector('sb-outcome-path')).toBeTruthy();
    expect(el.textContent).toContain('Scale-out');
    expect(el.textContent).toContain('Timeline');
  });
```

with

```ts
  it('hosts the outcome path inside the Outcome card, with no second Scale-out panel', () => {
    const el = mount('', DETAIL, 'CLOSED', { exit_price: 105, r_multiple: 0.6 });
    const outcome = el.querySelector('sb-trade-outcome-card');
    expect(outcome?.querySelector('sb-outcome-path')).toBeTruthy();
    expect(outcome?.textContent).toContain('Exit legs');
    expect(outcome?.textContent).toContain('Timeline');
    expect(el.textContent).not.toContain('Scale-out');
  });
```

**The TD5 and TD6 blocks.** In `TradeDetail — outcome strip (v166)`, case `sits right under the header on every tab`, change

```ts
    for (const tab of ['', 'notes']) {
```

to

```ts
    for (const tab of ['', 'why', 'journal']) {
```

In `TradeDetail — identity line (v166)`, case `shows the actions on every tab, and no Actions card`, change

```ts
    for (const tab of ['', 'live', 'notes']) {
```

to

```ts
    for (const tab of ['', 'why', 'journal']) {
```

**New block.** Add this describe block directly after the `TradeDetail — Why tab (v166)` block (TD9):

```ts
describe('TradeDetail — tabs and Overview (v166)', () => {
  let backend: HttpTestingController;
  let navigate: MockInstance<Router['navigate']>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  });

  /** Mount (default tab unless one is named) and settle the detail request. */
  function mount(status = 'ACTIVE', overrides: object = {}, detail: object = DETAIL, tab = '') {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail, status, overrides));
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  const labels = (el: HTMLElement) =>
    [...el.querySelectorAll('sb-tab-bar .tab .label')].map((label) => label.textContent?.trim());
  const activeLabel = (el: HTMLElement) =>
    el.querySelector('sb-tab-bar .tab.active .label')?.textContent?.trim();
  const overviewCells = (el: HTMLElement) =>
    [...el.querySelectorAll('.grid-host > .card-grid.overview-grid > .cell')].map((node) =>
      node.getAttribute('data-area'),
    );
  const text = (el: HTMLElement, selector: string) => el.querySelector(selector)?.textContent ?? '';
  const rewrite = (tab: string | null) => [
    [],
    { queryParams: { tab }, queryParamsHandling: 'merge', replaceUrl: true },
  ];

  /* -- tabs ------------------------------------------------------------ */

  it('has four tabs: Overview, Why, Chart, Journal', () => {
    expect(labels(mount())).toEqual(['Overview', 'Why', 'Chart', 'Journal']);
  });

  it('opens on Overview when there is no tab parameter, without touching the URL', () => {
    const el = mount();
    expect(activeLabel(el)).toBe('Overview');
    expect(overviewCells(el)).toEqual(['plan', 'position', 'outcome']);
    expect(navigate).not.toHaveBeenCalled();
  });

  it.each([
    ['plan', null, 'Overview'],
    ['live', null, 'Overview'],
    ['notes', 'journal', 'Journal'],
    ['strategy', 'why', 'Why'],
  ])('rewrites the old ?tab=%s in place and renders its new home', (old, target, label) => {
    const el = mount('ACTIVE', {}, DETAIL, old);
    expect(activeLabel(el)).toBe(label);
    expect(navigate).toHaveBeenCalledWith(...rewrite(target));
  });

  it('pins the legacy map', () => {
    expect(LEGACY_TABS).toEqual({ plan: null, live: null, notes: 'journal', strategy: 'why' });
  });

  it('renders Overview for an unknown tab and leaves the parameter in the URL', () => {
    const el = mount('ACTIVE', {}, DETAIL, 'bogus');
    expect(activeLabel(el)).toBe('Overview');
    expect(overviewCells(el)).toEqual(['plan', 'position', 'outcome']);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('writes no parameter when Overview is chosen', () => {
    const el = mount('ACTIVE', {}, DETAIL, 'why');
    const overview = [...el.querySelectorAll<HTMLElement>('sb-tab-bar .tab')].find(
      (tab) => tab.textContent?.trim() === 'Overview',
    );
    overview?.click();
    expect(navigate).toHaveBeenCalledWith(...rewrite(null));
  });

  it('writes the id of any other tab chosen', () => {
    const el = mount();
    const journal = [...el.querySelectorAll<HTMLElement>('sb-tab-bar .tab')].find(
      (tab) => tab.textContent?.trim() === 'Journal',
    );
    journal?.click();
    expect(navigate).toHaveBeenCalledWith(...rewrite('journal'));
  });

  it('keeps the note field on the Journal tab (was Notes)', () => {
    const el = mount('CLOSED', { exit_price: 110 }, DETAIL, 'journal');
    expect(el.querySelector('textarea#trade-note')).not.toBeNull();
    expect(el.querySelector('label.note-label')?.textContent?.trim()).toBe('Note');
  });

  /* -- Overview: Plan card ---------------------------------------------- */

  it('renders the trigger price and the two fractions unsigned', () => {
    const el = mount();
    const plan = text(el, 'sb-trade-plan-card');
    expect(plan).toContain('Trigger');
    expect(plan).toContain('101.50');
    const position = text(el, 'sb-trade-position-card');
    // "TP1 closes +50%" would read as a gain. It means half the position.
    expect(position).toContain('50%');
    expect(position).not.toContain('+50%');
    expect(position).toContain('60%');
  });

  it('shows the working stop under the original stop once TP1 has banked (PARTIAL)', () => {
    // A PARTIAL short's stop legitimately sits BELOW entry (it protects the
    // profit TP1 already locked in, not the original risk), which reads as
    // backwards unless the card says which stop is which, and what to do.
    const el = mount('PARTIAL', { risk_stop: 95, stop_loss: 99 }, { ...DETAIL, working_stop: 99 });
    const plan = text(el, 'sb-trade-plan-card');
    expect(plan).toContain('Working stop');
    expect(plan).toContain('(was 95.00)');
    expect(plan).toContain('Move your resting stop to 99.00');
    expect(plan).not.toContain('Trailing stop');
  });

  it('shows a plain Stop before any TP1 (ACTIVE)', () => {
    const el = mount('ACTIVE', { risk_stop: 95 }, { ...DETAIL, working_stop: 95 });
    const plan = text(el, 'sb-trade-plan-card');
    expect(plan).toContain('Stop');
    expect(plan).not.toContain('Working stop');
    expect(plan).not.toContain('Move your resting stop');
    expect(plan).not.toContain('Trailing stop');
  });

  it('omits the working-stop row and the resting-stop line when risk_stop is missing', () => {
    // A row built before risk_stop was published (spec Edge cases).
    const el = mount('PARTIAL', { stop_loss: 99 }, { ...DETAIL, working_stop: 99 });
    const plan = text(el, 'sb-trade-plan-card');
    expect(plan).not.toContain('Working stop');
    expect(plan).not.toContain('Move your resting stop');
  });

  /* -- Overview: Position card ------------------------------------------ */

  it('states the dollars at risk on the open shares at the original stop (PARTIAL)', () => {
    // shares 10 (the open count on PARTIAL) x |100 - 95| = 50.00, although
    // stop_loss is the working stop 99 (amendment 2).
    const el = mount('PARTIAL', { risk_stop: 95, stop_loss: 99 }, { ...DETAIL, working_stop: 99 });
    const position = text(el, 'sb-trade-position-card');
    expect(position).toContain('$ at risk');
    expect(position).toContain('50.00');
    expect(position).toContain('open shares, at original stop');
  });

  /* -- Overview: Outcome card ------------------------------------------- */

  it('renders the timeline in the Outcome card', () => {
    const outcome = text(mount(), 'sb-trade-outcome-card');
    expect(outcome).toContain('Timeline');
    // Creation is prepended -- status_history does not contain it.
    expect(outcome).toContain('CREATED');
    expect(outcome).toContain('ACTIVE');
    expect(outcome).toContain('trigger filled');
  });

  it.each(['ACTIVE', 'PARTIAL', 'PENDING'])('shows the Next block on a %s trade', (status) => {
    expect(mount(status).querySelector('sb-trade-outcome-card sb-if-it-gets-there')).not.toBeNull();
  });

  it('shows no Next block on a closed trade', () => {
    const el = mount('CLOSED', { exit_price: 105, r_multiple: 0.6 });
    expect(el.querySelector('sb-if-it-gets-there')).toBeNull();
  });

  it('lists the exit legs of a closed trade, a leg with no exit price as a dash', () => {
    // v58's "still open" leg, re-pinned on a closed record (spec Edge cases:
    // a leg with exit_price null is skipped by the average, listed with "—").
    const outcome = text(mount('CLOSED', { exit_price: 105, r_multiple: 0.6 }), 'sb-trade-outcome-card');
    expect(outcome).toContain('Exit legs');
    expect(outcome).toContain('110.00');
    expect(outcome).toContain('+1.20R');
    expect(outcome).toContain('TP1');
    expect(outcome).toContain('—');
  });

  it('does not list legs on an open position, even with two of them', () => {
    // One leg is not a scale-out, and an open position's legs are not exits.
    const el = mount('ACTIVE', {}, { ...DETAIL, legs: [{ fraction: 1, exit_price: null }] });
    expect(el.textContent).not.toContain('Exit legs');
    expect(el.textContent).not.toContain('Scale-out');
    expect(mount('ACTIVE').textContent).not.toContain('Exit legs');
  });

  it('lists a single-leg close as one leg, with no "+" in the exit label', () => {
    const el = mount('CLOSED', { exit_price: 96, r_multiple: -0.8 }, {
      ...DETAIL,
      legs: [{ fraction: 1, exit_price: 96, r: -0.8, reason: 'stop' }],
    });
    expect(text(el, 'sb-trade-outcome-card')).toContain('Exit legs');
    expect(text(el, 'sb-outcome-strip .tile[data-tile="exit"]')).toContain('Stop');
    expect(text(el, 'sb-outcome-strip .tile[data-tile="exit"]')).not.toContain(' + ');
  });

  /* -- dropped ---------------------------------------------------------- */

  it('drops the Opened, Per share, Now, Stop to target and Partial position cards', () => {
    for (const status of ['ACTIVE', 'PARTIAL', 'CLOSED']) {
      const el = mount(status, { exit_price: status === 'CLOSED' ? 105 : null });
      const headings = [...el.querySelectorAll('sb-panel h2')].map((h) => h.textContent?.trim());
      for (const gone of ['Opened', 'Per share', 'Now', 'Stop to target', 'Partial position']) {
        expect(headings).not.toContain(gone);
      }
    }
  });
});
```

The fixture numbers: `tradeResponse()` defaults are entry 100, shares 10, stop_loss 95; `DETAIL` has `trigger_price` 101.5, `tp1_fraction` 0.5, `breakeven_trigger_fraction` 0.6 and the legs `{0.5, 110, 1.2, 'TP1'}` / `{0.5, null, null, null}` with `legs_realized: []`, so `store.legs()` is the record's `legs`.

- [ ] **Step 2: Run the page spec to verify the new cases fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts`
Expected: FAIL — `TradeDetail — tabs and Overview (v166)` (labels are still Plan/Live/Chart/Notes/Why, no `.overview-grid`, no navigate on a legacy id), the rewritten describe-C and describe-E cases (no `sb-trade-plan-card`, a `Partial position` panel on Live), and the TD5/TD6 cases that now mount `journal` (unknown today, renders Plan). Every other block passes.

- [ ] **Step 3: Final tabs, the legacy map and tab resolution in `trade-detail.ts`**

Replace the TD9 `TABS` constant, its doc comment and `TAB_IDS`:

```ts
/** v166 (interim, TD9): Why replaces Strategy. TD10 replaces Plan and Live
 *  with Overview and renames Notes to Journal. */
const TABS: Tab[] = [
  { id: 'plan', label: 'Plan' },
  { id: 'live', label: 'Live' },
  { id: 'chart', label: 'Chart' },
  { id: 'notes', label: 'Notes' },
  { id: 'why', label: 'Why' },
];

const TAB_IDS = new Set(TABS.map((tab) => tab.id));
```

with

```ts
/** Overview · Why · Chart · Journal (spec v166 § 2). `chart` keeps its id:
 *  the v165 day page links to `?tab=chart`. */
const TABS: Tab[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'why', label: 'Why' },
  { id: 'chart', label: 'Chart' },
  { id: 'journal', label: 'Journal' },
];

const TAB_IDS = new Set(TABS.map((tab) => tab.id));

/** The tab with no `?tab=` parameter. */
const DEFAULT_TAB = 'overview';

/** Pre-v166 tab ids and where their content lives now; `null` is Overview,
 *  written as no parameter. A bookmark or an open browser tab carrying one is
 *  rewritten in place (replaceUrl), so the back button does not step through
 *  the old id. */
export const LEGACY_TABS: Readonly<Record<string, string | null>> = {
  plan: null,
  live: null,
  notes: 'journal',
  strategy: 'why',
};

/** The tab a `?tab=` value renders: itself when current, its new home when
 *  legacy, Overview when absent or unknown (an unknown value is left in the
 *  URL, as before v166 -- a hand-edited URL still shows the trade). */
function resolveTab(requested: string | undefined): string {
  if (!requested) return DEFAULT_TAB;
  if (TAB_IDS.has(requested)) return requested;
  if (Object.hasOwn(LEGACY_TABS, requested)) return LEGACY_TABS[requested] ?? DEFAULT_TAB;
  return DEFAULT_TAB;
}
```

In the class, replace `activeTab` and its doc comment:

```ts
  /** An unknown or absent `?tab=` falls back to Plan rather than rendering
   *  nothing, so a hand-edited or stale URL still shows the trade. */
  protected readonly activeTab = computed(() => {
    const requested = this.tab();
    return requested && TAB_IDS.has(requested) ? requested : 'plan';
  });
```

with

```ts
  /** The tab to render; see `resolveTab`. A legacy id renders its new home
   *  at once, before the URL rewrite below has landed. */
  protected readonly activeTab = computed(() => resolveTab(this.tab()));
```

Replace `goToTab`:

```ts
  protected goToTab(tab: string): void {
    // replaceUrl: flipping between tabs should not fill the history with
    // steps, but the tab must still be in the URL so it can be linked to.
    this.router.navigate([], {
      queryParams: { tab: tab === 'plan' ? null : tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
```

with

```ts
  protected goToTab(tab: string): void {
    // replaceUrl: flipping between tabs should not fill the history with
    // steps, but the tab must still be in the URL so it can be linked to.
    // The default tab is encoded as no parameter.
    this.router.navigate([], {
      queryParams: { tab: tab === DEFAULT_TAB ? null : tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
```

In the constructor, directly after `effect(() => this.store.setId(this.id()));`, add:

```ts
    // v166: an old ?tab= id (plan, live, notes, strategy) is rewritten to its
    // new home in place. Unknown values are not touched.
    effect(() => {
      const requested = this.tab();
      if (!requested || !Object.hasOwn(LEGACY_TABS, requested)) return;
      const target = LEGACY_TABS[requested] ?? DEFAULT_TAB;
      untracked(() => this.goToTab(target));
    });
```

- [ ] **Step 4: Replace Plan and Live with Overview; rename Notes to Journal**

Change the imports. Replace

```ts
import { dateTime, held, num, pct, rMultiple, share, text } from '../../ui/format';
import { Panel, Tab, TabBar } from '../../ui/layout';
```

with

```ts
import { Tab, TabBar } from '../../ui/layout';
```

Delete these four imports:

```ts
import { IfItGetsThere } from './why/if-it-gets-there';
import { LevelsBlock } from './why/levels-block';
import { OutcomePath } from './why/outcome-path';
import { SizingPanel } from './why/sizing-panel';
```

Change the TD6 import

```ts
import { sideLabel, statusGroup } from './trade-figures';
```

to

```ts
import { StatusGroup, sideLabel, statusGroup } from './trade-figures';
```

change the TD9 import

```ts
import { CardAreas, WhyCard, whyAreas } from './why-areas';
```

to

```ts
import { CardAreas, OVERVIEW_AREAS, WhyCard, whyAreas } from './why-areas';
```

and add after it:

```ts
import { OutcomeCard } from './outcome-card';
import { PlanCard, PlanFigures } from './plan-card';
import { PositionCard, PositionFigures } from './position-card';
```

In the `@Component` `imports:` array, delete `Panel,`, `LevelsBlock,`, `IfItGetsThere,`, `SizingPanel,` and `OutcomePath,`, and add `PlanCard,`, `PositionCard,` and `OutcomeCard,` after `StrategyRecordCard,`.

In the template, replace everything from `@case ('plan') {` down to, not including, `@case ('chart') {` (the whole Plan and Live blocks) with:

```html
      @case ('overview') {
        @if (store.trade(); as trade) {
          <!-- v166 -- what the trade is (Plan), what it holds (Position) and
               how it is going or went (Outcome). Plan and Live in one tab:
               the levels were shown three times across them. -->
          <div class="grid-host">
            <div
              class="card-grid overview-grid"
              [style.--areas-1]="overviewAreas.one"
              [style.--areas-2]="overviewAreas.two"
              [style.--areas-3]="overviewAreas.three"
            >
              @if (planFigures(); as figures) {
                <div class="cell" data-area="plan" style="grid-area: plan">
                  <sb-trade-plan-card [figures]="figures" />
                </div>
              }
              @if (positionFigures(); as figures) {
                <div class="cell" data-area="position" style="grid-area: position">
                  <sb-trade-position-card [figures]="figures" />
                </div>
              }
              <div class="cell" data-area="outcome" style="grid-area: outcome">
                <!-- stopLoss is the stop that applies now (the working stop
                     on PARTIAL): the Next block's "reverses" line names the
                     level that would actually be hit. -->
                <sb-trade-outcome-card
                  [group]="outcomeGroup()"
                  [direction]="trade.direction"
                  [target2]="trade.target2"
                  [stopLoss]="trade.stop_loss"
                  [legs]="store.legs()"
                  [timeline]="store.timeline()"
                />
              </div>
            </div>
          </div>
        }
      }
```

Replace `@case ('notes') {` with `@case ('journal') {` (the block's body, `<div class="notes">` and everything in it, is unchanged).

- [ ] **Step 5: Replace the class members**

Delete `stopLabel` with its doc comment (from `/** "Stop" vs "Trailing stop" -- a PARTIAL position's` through the closing `);` of the computed): the Overview Plan card names the working stop itself, and no WhyPanel cell takes a stop label.

Delete the seven format aliases:

```ts
  protected readonly fmt = num;
  protected readonly fmtText = text;
  protected readonly fmtDate = dateTime;
  protected readonly fmtPct = pct;
  protected readonly fmtHeld = held;
  protected readonly fmtShare = share;
  protected readonly fmtR = rMultiple;
```

and the `pnlClass` method:

```ts
  protected pnlClass(value: number | null | undefined): string {
    if (value === null || value === undefined) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  }
```

After the TD9 `whyGrid` computed, add:

```ts
  /* -- v166: the Overview tab -------------------------------------------- */

  protected readonly overviewAreas: CardAreas = OVERVIEW_AREAS;

  /** The Plan card's figures. The original stop (`risk_stop`) and the
   *  working stop are passed separately: on PARTIAL `stop_loss` is the
   *  working stop, and risk per share is measured from `risk_stop`. */
  protected readonly planFigures = computed<PlanFigures | null>(() => {
    const trade = this.store.trade();
    if (!trade) return null;
    return {
      direction: trade.direction,
      status: trade.status,
      entryType: this.store.entryType(),
      trigger: this.store.triggerPrice(),
      entry: trade.entry,
      riskStop: this.store.riskStop(),
      stopLoss: trade.stop_loss,
      workingStop: this.store.workingStop(),
      target1: trade.target,
      target2: trade.target2,
      acceptance: this.store.acceptanceLevel(),
      riskReward: trade.risk_reward,
      riskPerShare: this.store.riskPerShare(),
      rewardPerShare: this.store.rewardPerShare(),
    };
  });

  /** The Position card's figures; `dollarAtRisk` is open shares x risk per
   *  share from the original stop (amendment 2). */
  protected readonly positionFigures = computed<PositionFigures | null>(() => {
    const trade = this.store.trade();
    if (!trade) return null;
    return {
      status: trade.status,
      shares: trade.shares,
      positionValue: trade.position_value,
      dollarAtRisk: this.store.dollarAtRisk(),
      sizingMode: this.store.sizingMode(),
      gapP90Pct: this.store.gapP90Pct(),
      gapFragile: this.store.gapFragile(),
      tp1Pct: this.store.tp1Pct(),
      breakevenTriggerPct: this.store.breakevenTriggerPct(),
      trailAtrMult: this.store.trailAtrMult(),
      expiresOn: this.store.expiresOn(),
      timeExitOn: this.store.timeExitOn(),
      holdCapBars: this.store.holdCapBars(),
    };
  });

  /** Which Outcome card to show: status first, `exit_price` only for a
   *  terminal status that is not CLOSED (statusGroup). */
  protected readonly outcomeGroup = computed<StatusGroup>(() => {
    const trade = this.store.trade();
    return trade ? statusGroup(trade.status, trade.exit_price ?? null) : 'pending';
  });
```

- [ ] **Step 6: Drop the styles only Plan and Live used**

Delete these rules from `styles` (with their comments):

```css
    /* --warn is the design system's designated token for stale data (see
       tokens.css's own legend) -- the price itself still renders, this just
       says the number might not be a live tick (the MRNA incident,
       2026-09-18: a fast_info fallback echoed yesterday's close). */
    .stale-flag {
      display: inline-block;
      margin-left: var(--space-6);
      font-size: var(--text-chip);
      font-weight: normal;
      color: var(--warn);
    }
```

```css
    /* v54: dropped this call site's own .muted rule entirely -- the gate
       forbids redefining that selector at all, not just its colour (which
       was color: var(--text-faint), a drift off the global .muted's
       var(--text-muted), now fixed by using the global unmodified). The
       inline gap it used to add is .muted-gap, a second class alongside
       .muted in the markup so the two concerns stay separately named. */
    .muted-gap {
      margin-left: var(--space-6);
    }
```

```css
    .progress {
      margin-bottom: var(--space-10);
    }
```

(The strip's own `.stale-flag` lives in `outcome-strip.ts`, TD5. `.panels` and the `dl` rules stay for TD11, which removes `.panels`.)

Update the component doc comment's first paragraph:

```ts
 * One trade — the shell and the Plan tab (NG43). Live is NG44, Chart NG45,
 * Notes and Strategy NG46.
```

to

```ts
 * One trade (v166): the identity line and outcome strip on every tab, then
 * Overview, Why, Chart and Journal.
```

- [ ] **Step 7: Run the page spec, the card specs and the UI gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/trades/plan-card.spec.ts --include src/app/workspaces/trades/position-card.spec.ts --include src/app/workspaces/trades/outcome-card.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts`
Expected: PASS, 0 failed — every block, including the six v86 cohort-chip cases, the arrival-banner cases and `TradeDetail states` unchanged. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

Then confirm the page no longer imports or names the old pieces:

Run: `git -C $WT grep -n -E "LevelsBlock|SizingPanel|sb-levels-block|sb-sizing-panel|'plan'|'live'|'notes'|stopLabel|pnlClass|fmt[A-Z]?[a-z]*\b|<sb-panel" -- frontend/src/app/workspaces/trades/trade-detail.ts`
Expected: exactly three lines, all about the plan *origin*, not a tab: `cameFromPlan()`'s doc comment (`state: { from: 'plan' }`) and body (`['from'] === 'plan'`), and the identity line's `trade.origin !== 'plan'` (TD6). No `'live'` or `'notes'`, no `fmt`, no `<sb-panel` (the `LEGACY_TABS` keys are unquoted).

And that the shared components are still untouched:

Run: `git -C $WT diff --stat main -- frontend/src/app/workspaces/trades/why/ frontend/src/app/workspaces/plans/plan-detail.ts frontend/src/app/ui/`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git -C $WT commit -m "feat(v166): TD10 Overview tab, four final tabs, legacy ?tab= rewrite

Overview replaces Plan and Live: the Plan card (order, levels, working
stop and the resting-stop cue), the Position card (dollars at risk at the
original stop) and the Outcome card (Next block while open, exit legs once
closed, the timeline). Tabs are Overview, Why, Chart, Journal; old ids are
rewritten in place (plan/live -> none, notes -> journal, strategy -> why),
unknown ids render Overview and stay in the URL. Opened, Per share, Now,
Stop to target and Partial position are gone; the banked leg is the
strip's Banked tile.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

