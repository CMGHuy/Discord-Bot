# v194 — UI integrity: tooltips that open, figures that are true — Part 5b: remaining title conversions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md)
**Index:** [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md) — Global Constraints, `### Standard task close`, Parallelisation and the task ledger live there. Spill of part 5 (`_5-leg-surfaces-and-titles.md`, V194-13..V194-15).

### Task V194-15b: A3 part 4 — convert the remaining workspace titles; assert `TITLE_PENDING` is empty

**Model:** sonnet — five small title conversions plus one assertion; every value is fixed below.

**Files:**
- Modify: `frontend/src/app/workspaces/cancels/cancels-summary.ts:34,38`
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts:33,181`
- Modify: `frontend/src/app/workspaces/versions/versions.ts:47,103-107,121-125,288-292`
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts:174,416`
- Modify: `frontend/src/app/ui/title-usage.allow.ts`, `frontend/src/app/ui/title-usage.spec.ts`
- Test: `frontend/src/app/workspaces/cancels/cancels-summary.spec.ts`, `frontend/src/app/workspaces/system/settings-tab.spec.ts`, `frontend/src/app/workspaces/versions/versions.spec.ts`, `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`, `frontend/src/app/ui/title-usage.spec.ts`

**Interfaces:**
- Consumes: `Hint`; `TITLE_ALLOW`, `TITLE_PENDING` (V194-14, with V194-14b's and V194-15's entries already removed).
- Produces: `SETTINGS_RESTART_HINT` (`settings-tab.ts`), `WATCHLIST_FALLBACK_HINT` (`watchlist.ts`); `TITLE_PENDING` empty for good. V194-16 consumes `TITLE_ALLOW` (echo and control-name sites only from here on).

- [ ] **Step 1: Write the failing tests.**

`frontend/src/app/ui/title-usage.spec.ts`, append inside `describe('native title usage (v194 A3)')`:

```ts
  it('has converted every explanation site: only echoes and control names keep a title', () => {
    expect(TITLE_PENDING.map((s) => `${s.file} :: ${s.binding}`)).toEqual([]);
    expect(TITLE_ALLOW.every((s) => s.kind === 'echo' || s.kind === 'control-name')).toBe(true);
  });
```

`frontend/src/app/workspaces/cancels/cancels-summary.spec.ts`: in the existing test that renders a `.small-n` mark (`git grep -n "small-n" frontend/src/app/workspaces/cancels/cancels-summary.spec.ts`), after its existing `.small-n` assertion add (with that test's fixture `f`):

```ts
    expect(q(f, '.small-n')!.hasAttribute('title')).toBe(false);
    expect(text(q(f, '.small-n + sb-hint [role="tooltip"]'))).toMatch(/^Fewer than \d+ resolved plans: an anecdote, not a rate\.$/);
```

If no test renders a `.small-n` mark yet, add one: `create({ ...CANCEL_PAYLOAD, … })` with one row's `small_n: true` (the field the `#mark` template reads), then the two lines above.

`frontend/src/app/workspaces/system/settings-tab.spec.ts`: add `SETTINGS_RESTART_HINT` to the import from `./settings-tab`; in the existing test that renders a restart-required field (`git grep -n "restart" frontend/src/app/workspaces/system/settings-tab.spec.ts`), after its `.restart` assertion add:

```ts
    const restart = (fixture.nativeElement as HTMLElement).querySelector('.restart')!;
    expect(restart.hasAttribute('title')).toBe(false);
    expect(restart.nextElementSibling!.querySelector('[role="tooltip"]')!.textContent!.trim()).toBe(SETTINGS_RESTART_HINT);
```

`frontend/src/app/workspaces/versions/versions.spec.ts`: append inside its top-level `describe`, seeding the same payload its first `seed(...)` test uses:

```ts
  it('names the hatched lane and the bracket in a visible legend, not in titles (v194 A3)', async () => {
    const fixture = seed(PAYLOAD);
    await fixture.whenStable();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.absent[title], .bracket[title]')).toBeNull();
    const legend = el.querySelector('.lane-legend')!.textContent!.replace(/\s+/g, ' ');
    expect(legend).toContain('did not exist yet');
    expect(legend).toContain('the releases listed below');
  });
```

(`PAYLOAD` = the `VersionHistory` constant the spec's first `seed(...)` call passes; use its real name.)

`frontend/src/app/workspaces/watchlist/watchlist.spec.ts`: add `WATCHLIST_FALLBACK_HINT` to the import from `./watchlist` and append inside its top-level `describe`:

```ts
  it('explains a yfinance fallback price in a hint beside the badge (v194 A3)', () => {
    const r = firstRow({ price_source: 'yfinance-fallback' });
    const badge = r.querySelector('.source-badge')!;
    expect(badge.textContent!.trim()).toBe('fallback');
    expect(badge.hasAttribute('title')).toBe(false);
    expect(badge.nextElementSibling!.querySelector('[role="tooltip"]')!.textContent!.trim()).toBe(WATCHLIST_FALLBACK_HINT);
  });

  it('shows neither badge nor hint for a plain Alpaca price', () => {
    const r = firstRow({ price_source: 'alpaca' });
    expect(r.querySelector('.source-badge')).toBeNull();
  });
```

- [ ] **Step 2: Run them to see them fail.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/title-usage.spec.ts --include src/app/workspaces/cancels/cancels-summary.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts --include src/app/workspaces/versions/versions.spec.ts --include src/app/workspaces/watchlist/watchlist.spec.ts`. Expected: FAIL — `TITLE_PENDING` still lists the five sites below, and the new constants are not exported.

- [ ] **Step 3: Cancels** (`cancels-summary.ts`). Add `import { Hint } from '../../ui/hint';`; `imports: [Panel, Button, NgTemplateOutlet],` → `imports: [Panel, Button, NgTemplateOutlet, Hint],`; `:38`

```html
        <span class="small-n" title="Fewer than {{ data().small_n_threshold }} resolved plans: an anecdote, not a rate">N &lt; {{ data().small_n_threshold }}</span>
```
→
```html
        <span class="small-n">N &lt; {{ data().small_n_threshold }}</span>
        <sb-hint [text]="smallNHint()" label="About small samples" align="left" />
```

and in the class (import `computed` from `@angular/core` if it is not already):

```ts
  /** v194 A3: why a small-N figure is marked -- in a hint, not a native title. */
  protected readonly smallNHint = computed(
    () => `Fewer than ${this.data().small_n_threshold} resolved plans: an anecdote, not a rate.`,
  );
```

- [ ] **Step 4: Settings** (`settings-tab.ts`). Add the `Hint` import (`'../../ui/hint'`) and to `imports` (`:33`). Above the `@Component`:

```ts
/** v194 A3: what the "restart" mark means. */
export const SETTINGS_RESTART_HINT = 'Restart required to take effect.';
```

`:181`: `<span class="restart" title="Restart required to take effect">restart</span>` → `<span class="restart">restart</span><sb-hint [text]="restartHint" label="About restart" align="left" />`; class: `protected readonly restartHint = SETTINGS_RESTART_HINT;`. The `title="Default value"` (`:175`) and `[title]="'Reset to ' + field.default"` (`:201`) sites stay (`echo`).

- [ ] **Step 5: Versions** (`versions.ts`). `:103-107`

```html
                <div class="absent" [style.left.%]="(1 - lane.absentWidth) * 100"
                     [style.width.%]="lane.absentWidth * 100"
                     title="This component did not exist yet"></div>
```
→
```html
                <div class="absent" [style.left.%]="(1 - lane.absentWidth) * 100"
                     [style.width.%]="lane.absentWidth * 100"></div>
```

`:122-124`

```html
          <div class="bracket" [style.left.%]="store.bracket().start * 100"
               [style.width.%]="store.bracket().width * 100"
               title="The releases listed below"></div>
        </div>
```
→
```html
          <div class="bracket" [style.left.%]="store.bracket().start * 100"
               [style.width.%]="store.bracket().width * 100"></div>
        </div>
        <!-- v194 A3: these two marks used to explain themselves in titles on
             non-focusable divs, which no phone or keyboard reaches. -->
        <p class="lane-legend">
          <span class="key"><span class="swatch absent-swatch" aria-hidden="true"></span>did not exist yet</span>
          <span class="key"><span class="swatch bracket-swatch" aria-hidden="true"></span>the releases listed below</span>
        </p>
```

Styles, after `.bracket { … }` (`:291-292`):

```css
    .lane-legend { display: flex; flex-wrap: wrap; gap: var(--space-4) var(--space-14); margin: var(--space-4) 0 0 calc(var(--lane-w) + var(--space-8)); color: var(--text-secondary); font-size: var(--text-table); }
    .lane-legend .key { display: inline-flex; align-items: center; gap: var(--space-4); }
    .swatch { display: inline-block; width: 14px; height: 8px; }
    .bracket-swatch { border: 1px solid var(--text-faint); border-top: none; }
    @media (max-width: 599px) { .lane-legend { margin-left: 0; } }
```

and `.absent-swatch` takes the fill declarations of `.absent` (`:288-289`: copy its `background`/`background-image` lines verbatim into `.absent-swatch { … }` so the key matches the hatch).

- [ ] **Step 6: Watchlist** (`watchlist.ts`). Add the `Hint` import and append `Hint` to the `imports` array (`:174`). Above the `@Component`:

```ts
/** v194 A3: what the "fallback" badge means. */
export const WATCHLIST_FALLBACK_HINT = 'Alpaca missed this quote; yfinance answered instead.';
```

`:416`: `<span class="source-badge" title="Alpaca missed this quote; yfinance answered instead">fallback</span>` → `<span class="source-badge">fallback</span><sb-hint [text]="fallbackHint" label="About fallback prices" align="left" />`; class: `protected readonly fallbackHint = WATCHLIST_FALLBACK_HINT;`.

- [ ] **Step 7: Allow-list.** Delete the five entries whose note starts `V194-15b:` from `frontend/src/app/ui/title-usage.allow.ts`. `grep -c "explanation-pending', note" "$WT/frontend/src/app/ui/title-usage.allow.ts"` prints `0`; `grep -c "^  { file:" …` prints the final site count (expected 21) for the commit message.

- [ ] **Step 8: Run.** The Step 2 command. Expected: PASS. Then the whole frontend run and lint (standard close). Playwright at 390 on `/app/versions` and `/app/watchlist`: the legend wraps under the lanes, and the fallback hint glyph has its 44px touch target.

Close: standard (test: `frontend/src/app/ui/title-usage.spec.ts`); commit `feat(v194): last explanation titles become hints or visible text; TITLE_PENDING empty, <N> title sites left (V194-15b)`.
