# v181 — Dashboard range chart: Part 1b — palette, chart and cards (V181-5..V181-9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V181-7:" -A 400 <this file>`.

**Spec:** [2026-10-21-v181-dashboard-range-chart-design.md](../specs/2026-10-21-v181-dashboard-range-chart-design.md)
**Index:** [2026-10-21-v181-dashboard-range-chart_0-index.md](2026-10-21-v181-dashboard-range-chart_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there and bind every task below.

Work in the worktree `.claude/worktrees/2026-10-21-v181-dashboard-range-chart` (created in V181-1). Frontend commands run from `frontend/`.

**Contracts consumed from part 1a** (ledger rows V181-2..V181-4; this part relies on exactly these names):

- `equity-range.model.ts`: `LogicalWindow`, `RangeStats`, `inWindowCandles(range, candles)`, `rangeStats(candles)` (`null` on no candles), `nextTimeframe(barCount, tf, atHistoryEdge)`, `TF_STEP_UP_BARS`, `TF_STEP_DOWN_BARS`, `shouldLoadOlder(range, hasMore, busy)`, `PnlTone`, `signTone` (`null`/0 → `'neutral'`), `drawdownTone`, `breakevenPairTone`, `riskTone`.
- `EquityCandlesStore`: `data().candles` holds **every loaded page merged, oldest first**; `hasMore`, `pageLoading`, `pageError`, `atLiveEdge` (boolean signals), `loadOlder()`, `setAtLiveEdge(atEdge)`. The stub `equityCandlesStoreStub()` (V181-3) exposes `hasMore`/`pageLoading`/`pageError` as **writable** signals, `atLiveEdge` **read-only** (driven through `setAtLiveEdge`, which sets it), and the two methods as plain functions, so a spec can `vi.spyOn(stub, 'loadOlder')` (spies call through).
- `inWindowCandles(null, …)` returns `[]` (V181-2), and `maxDrawdownPct` is a non-negative magnitude; the readout prints it as `-|x|` either way.

**The app is dark only** (`frontend/src/styles/tokens.css:7`: "Dark only. There is no light theme"). Every "light and dark" check in the index reduces to the one dark theme; nothing below invents a light palette.

**Frontend runner:** `npx ng test --watch=false --include <spec> …` from `frontend/` — never bare `npx vitest run`, which skips the builder's `TestBed.initTestEnvironment()` and fails almost every spec (the index's Global Constraints line quoting `npx vitest run` predates this check). A run that dies after exactly 60 s with `Timeout waiting for worker to respond` ran nothing: re-run it (`docs/claude/testing-cost.md` § Frontend).

---
# Phase 3 — Palette and the baseline primitive

### Task V181-5: Saturated candle palette and its ripple

**Model:** sonnet — five files across two languages held together by pinned fixtures; mechanical but every pin must move in one commit.

**Files:**
- Modify: `frontend/src/styles/palette.css` (valence hues and alpha entries, lines 44-54)
- Modify: `frontend/src/styles/tokens.css:104-105,131-132` (the tier-2 aliases move to the new names)
- Modify: `frontend/src/app/ui/tokens.spec.ts:308-313` (pins)
- Modify: `frontend/src/app/ui/contrast.spec.ts` (append the valence and tint pairs, so the gate actually measures them — today it checks only `--text*` and `--accent`)
- Modify: `frontend/src/test-setup.ts` (header comment example only)
- Modify: `swingbot/core/charts/chart_style.py:63-64,77`
- Modify: `tests/charts/test_chart_theme.py:44-47` (`STYLE_PINS` row appended)
- Regenerate: `tests/charts/resolved_tokens.json` (`python scripts/dev/dump_tokens.py`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (consumed only through the tokens): `--pos` = `#00e5a0`, `--neg` = `#ff4d5e`, `--pos-soft` = `rgba(0, 229, 160, 0.12)`, `--neg-soft` = `rgba(255, 77, 94, 0.12)`; `chart_style.STYLE_VERSION = "v181"`.

The values were measured while writing this task (WCAG ratio and OKLab ΔE with the formulas of `contrast.spec.ts` and `chart-palette.spec.ts`):

| Value | OKLCH chroma (was) | on `--bg` / `--surface` / `--surface-raised` / `--surface-overlay` | on its own 12 % tint over `--surface` / `--surface-raised` | min ΔE to `--chart-1..6` |
|---|---|---|---|---|
| `#00e5a0` (`--pos`) | 0.177 (0.164) | 11.92 / 11.26 / 10.42 / 9.20 | 8.98 / 8.16 | 22.1 (`--chart-5`) |
| `#ff4d5e` (`--neg`) | 0.213 (0.176) | 6.07 / 5.73 / 5.31 / 4.68 | 5.09 / 4.69 | 14.8 (`--chart-2`) |

Both are more saturated than mint/coral, every pair clears 4.5:1, and the Python rule "nothing but gain/loss within ΔE 10 of gain or loss" holds (closest: `chart-2` at 14.8 from `--neg`, `warn` at 21.7 from `--pos`). The TradingView literals (`#089981`, `#f23645`) were rejected: `#089981` sits 7.6 from `--chart-5` and `#f23645` measures 4.35:1 on its own tint. **If any gate below still fails, adjust the value and re-measure — never add an exemption** (index Global Constraints).

- [ ] **Step 1: Write the failing pins**

In `frontend/src/app/ui/tokens.spec.ts`, replace these four rows of `EXPECTED` (lines 308-313; leave the `--warn`, `--info`, `--warn-soft`, `--accent-soft`, `--info-soft` rows alone):

```ts
    ['--pos', '--teal-400', '#00e5a0'],
    ['--neg', '--red-400', '#ff4d5e'],
```

```ts
    ['--pos-soft', '--teal-400-a12', 'rgba(0, 229, 160, 0.12)'],
    ['--neg-soft', '--red-400-a12', 'rgba(255, 77, 94, 0.12)'],
```

Append to `frontend/src/app/ui/contrast.spec.ts`:

```ts
/** A soft tint is an rgba laid over a surface; the figure is read against
 *  the blend, so the gate measures the blend. */
function over(rgba: string, bg: string): string {
  const [r, g, b, a] = rgba.match(/[\d.]+/g)!.map(Number);
  const mix = (fg: number, i: number) =>
    Math.round(a * fg + (1 - a) * parseInt(bg.slice(1 + i * 2, 3 + i * 2), 16));
  return `#${[r, g, b].map((v, i) => mix(v, i).toString(16).padStart(2, '0')).join('')}`;
}

/** v181 §5: every P&L figure is coloured, so the valence tokens are text. */
describe('v181: profit/loss figures read on every surface and on their own tint', () => {
  for (const fg of ['--pos', '--neg', '--warn']) {
    for (const bg of SURFACES) {
      it(`${fg} on ${bg} clears 4.5:1`, () => {
        expect(ratio(resolveToken(fg), resolveToken(bg))).toBeGreaterThanOrEqual(4.5);
      });
    }
  }

  for (const [fg, soft] of [['--pos', '--pos-soft'], ['--neg', '--neg-soft']]) {
    for (const bg of ['--surface', '--surface-raised']) {
      it(`${fg} on ${soft} over ${bg} clears 4.5:1`, () => {
        const ground = over(resolveToken(soft), resolveToken(bg));
        expect(ratio(resolveToken(fg), ground)).toBeGreaterThanOrEqual(4.5);
      });
    }
  }
});
```

In `tests/charts/test_chart_theme.py`, append one row to `STYLE_PINS` (never edit an old row):

```python
STYLE_PINS: tuple[tuple[str, str], ...] = (
    ("fb0f840658155cd0", "v80"),
    ("96d64692ba7c2abf", "v167"),  # v167 §4: Arctic Navy
    ("4f15a0f1fb8a6d1e", "v181"),  # v181 §5: saturated teal/red valence pair
)
```

`4f15a0f1fb8a6d1e` is `sha256(json.dumps(THEME, sort_keys=True))[:16]` with only `pos`/`neg` changed to the values above (computed while writing this task; if Step 4 reports a different live digest, THEME was edited beyond those two keys — fix THEME, not the pin).

- [ ] **Step 2: Run them to see the pins fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/contrast.spec.ts`
Expected: FAIL — `--pos references --teal-400`, `--pos resolves to #00e5a0` and the three sibling pairs fail. The new contrast block already passes on the old palette (it is a gate, not the driver).

Run: `python scripts/dev/testrun.py file tests/charts/test_chart_theme.py`
Expected: FAIL — `test_style_version_is_pinned_to_the_theme_digest` (the live pair is still `96d64692ba7c2abf` / `v167`).

- [ ] **Step 3: Change the palette, the aliases and the Discord mirror**

`frontend/src/styles/palette.css` — replace the valence and alpha blocks (palette names say hue and step, never purpose):

```css
  /* valence hues -- v181 §5: more saturated, TradingView's teal/red
     direction, measured on every surface and on their own tints */
  --teal-400: #00e5a0;
  --red-400: #ff4d5e;
  --amber-300: #ffc266;
  --violet-300: #c3a6ff;

  /* alpha entries: tints and the overlay dim */
  --navy-950-a72: rgba(7, 11, 20, 0.72);
  --teal-400-a12: rgba(0, 229, 160, 0.12);
  --red-400-a12: rgba(255, 77, 94, 0.12);
  --amber-300-a12: rgba(255, 194, 102, 0.12);
  --sky-600-a18: rgba(28, 109, 208, 0.18);
  --violet-300-a14: rgba(195, 166, 255, 0.14);
```

`--mint-400`, `--coral-400` and their `-a12` entries are removed; afterwards `git grep -n "mint-400\|coral-400" frontend/src swingbot` must list nothing but comments.

`frontend/src/styles/tokens.css`:

```css
  --pos: var(--teal-400);
  --neg: var(--red-400);
```

```css
  --pos-soft: var(--teal-400-a12);
  --neg-soft: var(--red-400-a12);
```

In the `frontend/src/test-setup.ts` header comment, change the example `--pos: var(--mint-400)` to `--pos: var(--teal-400)` (comment only).

`swingbot/core/charts/chart_style.py`:

```python
    "pos": "#00e5a0",
    "neg": "#ff4d5e",
```

```python
STYLE_VERSION = "v181"
```

Regenerate the cross-language fixture:

Run: `python scripts/dev/dump_tokens.py`
Expected: `tests/charts/resolved_tokens.json` rewritten — the `mint-400*` / `coral-400*` keys gone; `teal-400`, `teal-400-a12`, `red-400`, `red-400-a12` present; `pos`, `neg`, `pos-soft`, `neg-soft`, `quality-1`, `quality-5`, `flash-up-text`, `flash-down-text` resolved to the new values.

- [ ] **Step 4: Run every gate the palette feeds**

Run: `python scripts/dev/dump_tokens.py --check`
Expected: exit 0.

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/chart/chart-theme.spec.ts`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/charts/test_chart_theme.py`
Expected: PASS — digest pin, THEME byte-for-byte against the tokens, fixture reproduction, gain/loss ΔE ≥ 10, co-occurrence groups.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/palette.css frontend/src/styles/tokens.css frontend/src/test-setup.ts \
  frontend/src/app/ui/tokens.spec.ts frontend/src/app/ui/contrast.spec.ts \
  swingbot/core/charts/chart_style.py tests/charts/test_chart_theme.py tests/charts/resolved_tokens.json
git commit -m "feat(v181): saturated teal/red valence pair; Discord charts follow (STYLE_VERSION v181)" \
  -m "--pos/--neg move to #00e5a0/#ff4d5e. contrast.spec now measures the valence tokens on every surface and on their own soft tint." \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V181-6: Baseline-and-wash series primitive

**Model:** sonnet — a new canvas primitive modelled on an existing one; geometry needs care, no cross-module design.

**Files:**
- Create: `frontend/src/app/ui/chart/primitives/baseline-primitive.ts`
- Create: `frontend/src/app/ui/chart/primitives/baseline-primitive.spec.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks (pattern: `vline-primitive.ts` in the same folder).
- Produces: `interface BaselineSpec { value: number; line: string; above: string; below: string }`; `class BaselinePrimitive implements ISeriesPrimitive<Time>` with `setBaseline(spec: BaselineSpec | null): void`, `current(): BaselineSpec | null` (read by V181-7's spec, like `VLinePrimitive.current()`), and a pane view whose `zOrder()` is `'bottom'` so the wash sits behind the candles.

Spec §5: a dashed line at the visible range's opening equity, a faint `--pos-soft` wash above it and `--neg-soft` below. The primitive knows only a price and three colours; which price and which colours is V181-7's business. A baseline above the pane top means the whole pane is under water (all `below`), and below the pane bottom all `above`; the dashed line is drawn only while it is on screen.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/ui/chart/primitives/baseline-primitive.spec.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';

import { BaselinePrimitive } from './baseline-primitive';

function fakeContext() {
  return {
    save: vi.fn(), restore: vi.fn(), fillRect: vi.fn(), beginPath: vi.fn(),
    moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), setLineDash: vi.fn(),
    fillStyle: '', strokeStyle: '', lineWidth: 0,
    // fillStyle is overwritten between the two washes; record each fill's colour.
    fills: [] as string[],
  };
}

function attach(coordinate: number | null) {
  const primitive = new BaselinePrimitive();
  const requestUpdate = vi.fn();
  const series = { priceToCoordinate: vi.fn(() => coordinate) };
  primitive.attached({ chart: {}, series, requestUpdate } as never);
  return { primitive, requestUpdate, series };
}

function draw(primitive: BaselinePrimitive) {
  const context = fakeContext();
  context.fillRect.mockImplementation(() => context.fills.push(context.fillStyle));
  const target = { useBitmapCoordinateSpace: (cb: (scope: unknown) => void) => cb({
    context, horizontalPixelRatio: 2, verticalPixelRatio: 2, bitmapSize: { width: 400, height: 300 },
  }) };
  primitive.paneViews()[0].renderer()!.draw(target as never);
  return context;
}

const SPEC = { value: 1000, line: 'LINE', above: 'ABOVE', below: 'BELOW' };

describe('BaselinePrimitive', () => {
  it('washes above and below the baseline and dashes the line across the pane', () => {
    const { primitive, series } = attach(50);
    primitive.setBaseline(SPEC);
    const context = draw(primitive);
    expect(series.priceToCoordinate).toHaveBeenCalledWith(1000);
    // y 50 CSS px = 100 bitmap px.
    expect(context.fillRect).toHaveBeenNthCalledWith(1, 0, 0, 400, 100);
    expect(context.fillRect).toHaveBeenNthCalledWith(2, 0, 100, 400, 200);
    expect(context.fills).toEqual(['ABOVE', 'BELOW']);
    expect(context.setLineDash).toHaveBeenCalledWith([8, 8]);
    expect(context.moveTo).toHaveBeenCalledWith(0, 100.5);
    expect(context.lineTo).toHaveBeenCalledWith(400, 100.5);
    expect(context.strokeStyle).toBe('LINE');
  });

  it('puts the whole pane under water when the baseline sits above the top', () => {
    const { primitive } = attach(-20);
    primitive.setBaseline(SPEC);
    const context = draw(primitive);
    expect(context.fillRect).toHaveBeenNthCalledWith(1, 0, 0, 400, 0);
    expect(context.fillRect).toHaveBeenNthCalledWith(2, 0, 0, 400, 300);
    expect(context.stroke).not.toHaveBeenCalled();
  });

  it('puts the whole pane above water when the baseline sits below the bottom', () => {
    const { primitive } = attach(200);
    primitive.setBaseline(SPEC);
    const context = draw(primitive);
    expect(context.fillRect).toHaveBeenNthCalledWith(1, 0, 0, 400, 300);
    expect(context.fillRect).toHaveBeenNthCalledWith(2, 0, 300, 400, 0);
    expect(context.stroke).not.toHaveBeenCalled();
  });

  it('draws nothing without a baseline or before the scale has a coordinate', () => {
    const { primitive } = attach(null);
    expect(draw(primitive).fillRect).not.toHaveBeenCalled();
    primitive.setBaseline(SPEC);
    expect(draw(primitive).fillRect).not.toHaveBeenCalled();
  });

  it('asks the chart to repaint when the baseline changes, and reports it', () => {
    const { primitive, requestUpdate } = attach(50);
    primitive.setBaseline(SPEC);
    expect(requestUpdate).toHaveBeenCalledTimes(1);
    expect(primitive.current()).toEqual(SPEC);
    primitive.setBaseline(null);
    expect(primitive.current()).toBeNull();
  });

  it('paints behind the candles', () => {
    expect(new BaselinePrimitive().paneViews()[0].zOrder?.()).toBe('bottom');
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/primitives/baseline-primitive.spec.ts`
Expected: FAIL — `Failed to resolve import "./baseline-primitive"`.

- [ ] **Step 3: Write the primitive**

Create `frontend/src/app/ui/chart/primitives/baseline-primitive.ts`:

```ts
import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';

/**
 * Above/below water — spec v181 §5. A dashed horizontal line at one price
 * (the visible range's opening equity) with a faint wash above it and below
 * it, painted behind the candles so it never hides one.
 *
 * At most one baseline: `setBaseline(null)` removes it. Which price and which
 * colours is the caller's choice; this class only draws.
 */
export interface BaselineSpec {
  value: number;
  line: string;
  above: string;
  below: string;
}

interface BitmapScope {
  context: CanvasRenderingContext2D;
  horizontalPixelRatio: number;
  verticalPixelRatio: number;
  bitmapSize: { width: number; height: number };
}

interface DrawTarget {
  useBitmapCoordinateSpace: (cb: (scope: BitmapScope) => void) => void;
}

/** Dash and gap, in CSS px. */
const DASH_PX = 4;

class BaselineRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly spec: () => BaselineSpec | null,
    private readonly series: () => ISeriesApi<SeriesType> | null,
  ) {}

  draw(target: DrawTarget): void {
    const spec = this.spec();
    const series = this.series();
    if (!spec || !series) return;
    const y = series.priceToCoordinate(spec.value);
    // No price scale yet (empty series).
    if (y === null) return;
    target.useBitmapCoordinateSpace((scope) => paint(scope, spec, y));
  }
}

function paint(scope: BitmapScope, spec: BaselineSpec, y: number): void {
  const { context, horizontalPixelRatio, verticalPixelRatio, bitmapSize } = scope;
  const py = Math.round(y * verticalPixelRatio);
  // Off the top: the whole pane is under water; off the bottom: all above.
  const split = Math.min(Math.max(py, 0), bitmapSize.height);
  context.save();
  context.fillStyle = spec.above;
  context.fillRect(0, 0, bitmapSize.width, split);
  context.fillStyle = spec.below;
  context.fillRect(0, split, bitmapSize.width, bitmapSize.height - split);
  if (py >= 0 && py <= bitmapSize.height) {
    context.strokeStyle = spec.line;
    context.lineWidth = Math.max(1, Math.floor(verticalPixelRatio));
    context.setLineDash([DASH_PX * horizontalPixelRatio, DASH_PX * horizontalPixelRatio]);
    context.beginPath();
    // +0.5 centres a 1px stroke on the pixel row instead of blurring two.
    context.moveTo(0, py + 0.5);
    context.lineTo(bitmapSize.width, py + 0.5);
    context.stroke();
  }
  context.restore();
}

class BaselinePaneView implements IPrimitivePaneView {
  constructor(private readonly renderer_: BaselineRenderer) {}

  zOrder(): 'bottom' {
    return 'bottom';
  }

  renderer(): IPrimitivePaneRenderer {
    return this.renderer_;
  }
}

export class BaselinePrimitive implements ISeriesPrimitive<Time> {
  private series: ISeriesApi<SeriesType> | null = null;
  private spec: BaselineSpec | null = null;
  private requestUpdate: (() => void) | null = null;
  private readonly views: BaselinePaneView[];

  constructor() {
    this.views = [new BaselinePaneView(new BaselineRenderer(() => this.spec, () => this.series))];
  }

  current(): BaselineSpec | null {
    return this.spec;
  }

  setBaseline(spec: BaselineSpec | null): void {
    this.spec = spec;
    this.requestUpdate?.();
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.series = param.series as ISeriesApi<SeriesType>;
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.series = null;
    this.requestUpdate = null;
  }

  updateAllViews(): void {}

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }
}
```

- [ ] **Step 4: Run it to see it pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/primitives/baseline-primitive.spec.ts --include src/app/ui/chart/primitives/vline-primitive.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/chart/primitives/baseline-primitive.ts frontend/src/app/ui/chart/primitives/baseline-primitive.spec.ts
git commit -m "feat(v181): baseline-and-wash series primitive for the equity chart" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 4 — The chart

### Task V181-7: Chart: range readout, caption, paging trigger, page-error note, baseline, "↦ Latest"

**Model:** sonnet — wires five pure contracts from part 1a into one component; several template and test changes, no new design.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts` (append `ReadoutPart`, `RANGE_LABELS`, `candleReadout`, `rangeReadoutParts`, `isAtLiveEdge`)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`

**Interfaces:**
- Consumes (V181-2, V181-3, V181-4 — `equity-range.model.ts`): `LogicalWindow`, `RangeStats`, `inWindowCandles(range: LogicalWindow | null, candles)`, `rangeStats(candles): RangeStats | null`, `shouldLoadOlder(range: LogicalWindow | null, hasMore: boolean, busy: boolean): boolean`, `PnlTone`, `signTone(value: number | null)`, `drawdownTone(pct: number | null)`. `EquityCandlesStore`: `hasMore()`, `pageLoading()`, `pageError()`, `atLiveEdge()`, `loadOlder()`, `setAtLiveEdge(atEdge)`. (V181-6): `BaselinePrimitive`, `BaselineSpec`.
- Produces: `interface ReadoutPart { text: string; tone: PnlTone }`; `RANGE_LABELS = { change: 'Equity change', high: 'High', low: 'Low', drawdown: 'Max drawdown within range' }`; `candleReadout(candle: EquityCandle, basis: EquityBasis, currency: string, tf: EquityTimeframe): ReadoutPart[]`; `rangeReadoutParts(stats: RangeStats | null, currency: string): ReadoutPart[]` (`[]` on `null`); `isAtLiveEdge(range: LogicalWindow | null, count: number): boolean`. Component: `protected readonly inWindow` (computed over `visible`), `protected onVisibleRange(range: LogicalWindow | null): void` (the chart's range subscription calls it; V181-8 and V181-15 extend it), `protected baseline: BaselinePrimitive | null`, `protected toLatest(): void` (`timeScale().scrollToRealTime()`).

Behaviour (spec §2, §4, §5, §9):
- **Hovering** a candle reads that candle out as today; its money change and `% vs prev close` take `signTone(candle.change)`.
- **No hover**: the readout summarises the in-window candles — `Equity change +12.00 € (+12.00%)` (sign tone), `High …`, `Low …` (neutral), `Max drawdown within range -4.55%` (`drawdownTone`; "—" uncoloured when null). With no in-window candle it falls back to the latest candle.
- `ACCOUNT_LABEL` (unchanged text) moves to sit **directly under the readout** at every width (grid areas), so it is not repeated a second time inside the chart.
- The baseline sits at the first in-window candle's `o` (in All that is the opening balance), dashed in `--text-muted`, washed `--pos-soft` above / `--neg-soft` below.
- Every visible-range change: record it, tell the store whether the last candle is on screen, and call `loadOlder()` when `shouldLoadOlder(range, hasMore, pageLoading)` says so. A failed page leaves the candles and shows "Couldn't load earlier history · Retry" over the chart's left edge; the next pan retries by itself (`pageError` does not block `shouldLoadOlder`).
- "↦ Latest" appears in the controls row while `atLiveEdge()` is false. A scan refresh never moves the viewport (render only fits on a timeframe/basis change, as today).

- [ ] **Step 1: Write the failing model tests**

In `equity-candles.model.spec.ts`, extend the import list with `RANGE_LABELS, candleReadout, isAtLiveEdge, rangeReadoutParts` and append:

```ts
describe('v181 readout parts', () => {
  it('colours only the change parts of a hovered candle, by its sign', () => {
    const parts = candleReadout(candle({ change: -12.5, change_pct: -0.12 }), 'mtm', '€', '1D');
    const toned = parts.filter((p) => p.tone !== 'neutral').map((p) => p.text);
    expect(toned).toEqual(['-12.50 €', '-0.12% vs prev close']);
    expect(parts.find((p) => p.text.startsWith('O '))?.tone).toBe('neutral');
  });

  it('leaves a flat candle uncoloured', () => {
    const parts = candleReadout(candle({ change: 0, change_pct: 0 }), 'mtm', '€', '1D');
    expect(parts.every((p) => p.tone === 'neutral')).toBe(true);
  });

  it('summarises a range: change, high, low, drawdown within range', () => {
    const parts = rangeReadoutParts(
      { change: 12, changePct: 12, high: 120, low: 90, maxDrawdownPct: 4.545 }, '€');
    expect(parts.map((p) => p.text)).toEqual([
      'Equity change +12.00 € (+12.00%)', 'High 120.00', 'Low 90.00',
      'Max drawdown within range -4.55%',
    ]);
    expect(parts.map((p) => p.tone)).toEqual(['pos', 'neutral', 'neutral', 'neg']);
  });

  it('shows drawdown as a loss whichever sign the stats carry', () => {
    const parts = rangeReadoutParts(
      { change: -3, changePct: -1, high: 1, low: 1, maxDrawdownPct: -2 }, '€');
    expect(parts[3].text).toBe(`${RANGE_LABELS.drawdown} -2.00%`);
    expect(parts[0].tone).toBe('neg');
  });

  it('never colours the dash of an undefined drawdown or percentage', () => {
    const parts = rangeReadoutParts(
      { change: 5, changePct: null, high: 1, low: 1, maxDrawdownPct: null }, '€');
    expect(parts[0].text).toBe('Equity change +5.00 €');
    expect(parts[3]).toEqual({ text: 'Max drawdown within range —', tone: 'neutral' });
  });

  it('has nothing to say without stats', () => {
    expect(rangeReadoutParts(null, '€')).toEqual([]);
  });

  it('is at the live edge while the last candle is at least partly on screen', () => {
    expect(isAtLiveEdge(null, 10)).toBe(true);
    expect(isAtLiveEdge({ from: 0, to: 9 }, 10)).toBe(true);
    expect(isAtLiveEdge({ from: 0, to: 8.6 }, 10)).toBe(true);
    expect(isAtLiveEdge({ from: 0, to: 8.4 }, 10)).toBe(false);
    expect(isAtLiveEdge({ from: 0, to: 3 }, 0)).toBe(true);
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`
Expected: FAIL — `candleReadout is not a function` (and its siblings).

- [ ] **Step 3: Add the pure helpers**

In `equity-candles.model.ts`, add to the imports:

```ts
import { LogicalWindow, PnlTone, RangeStats, drawdownTone, signTone } from './equity-range.model';
```

and append:

```ts
/** One readout segment and the colour it carries — spec v181 §5. The tone is
 *  decided here, never in the template, so the colour rule lives once. */
export interface ReadoutPart {
  text: string;
  tone: PnlTone;
}

/** v181 §4: the range summary's labels. "within range" on the drawdown on
 *  purpose: it is measured on closes, so it can be smaller than High→Low. */
export const RANGE_LABELS = {
  change: 'Equity change',
  high: 'High',
  low: 'Low',
  drawdown: 'Max drawdown within range',
} as const;

/** The hovered candle (v172 parts), its two change parts toned by sign. */
export function candleReadout(
  candle: EquityCandle,
  basis: EquityBasis,
  currency: string,
  tf: EquityTimeframe,
): ReadoutPart[] {
  const changeText = money(candle.change, currency);
  const tone = signTone(candle.change);
  return readoutParts(candle, basis, currency, tf).map((text) => ({
    text,
    tone: text === changeText || isChangePart(text) ? tone : 'neutral',
  }));
}

function drawdownPart(pctValue: number | null): ReadoutPart {
  // Shown as a loss whichever sign the stats carry; an em dash is never coloured.
  if (pctValue === null) return { text: `${RANGE_LABELS.drawdown} —`, tone: 'neutral' };
  return { text: `${RANGE_LABELS.drawdown} ${pct(-Math.abs(pctValue))}`, tone: drawdownTone(pctValue) };
}

/** The visible range in one line — spec v181 §4. */
export function rangeReadoutParts(stats: RangeStats | null, currency: string): ReadoutPart[] {
  if (!stats) return [];
  const share = stats.changePct === null ? '' : ` (${pct(stats.changePct)})`;
  return [
    { text: `${RANGE_LABELS.change} ${money(stats.change, currency)}${share}`, tone: signTone(stats.change) },
    { text: `${RANGE_LABELS.high} ${num(stats.high)}`, tone: 'neutral' },
    { text: `${RANGE_LABELS.low} ${num(stats.low)}`, tone: 'neutral' },
    drawdownPart(stats.maxDrawdownPct),
  ];
}

/** True while the newest candle is at least half on screen (a bar spans
 *  ±0.5 logical units around its index), or before the first range event. */
export function isAtLiveEdge(range: LogicalWindow | null, count: number): boolean {
  return range === null || count === 0 || range.to >= count - 1.5;
}
```

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 4: Write the failing component tests**

In `equity-candles.spec.ts`, add `import { token } from '../../../ui/chart/chart-theme';` and a helper below `readout()`:

```ts
function tones(el: HTMLElement): (string | null)[] {
  return [...el.querySelectorAll('.readout .part')].map((p) => p.getAttribute('data-tone'));
}

function at(fixture: { componentInstance: EquityCandles; detectChanges(): void }, from: number, to: number) {
  fixture.componentInstance['onVisibleRange']({ from, to });
  fixture.detectChanges();
}
```

Replace the test `'reads out the latest candle when nothing is hovered'` with:

```ts
  it('reads out the hovered candle, its change toned by sign', () => {
    const { fixture, el } = render(response(MIXED));
    fixture.componentInstance['onCrosshair']({ logical: 2 });
    fixture.detectChanges();
    const parts = readout(el);
    expect(parts[0]).toBe('Oct 20, 2026');
    expect(parts).toContain('C 112.00');
    expect(parts).toContain('+7.00 €');
    expect(parts).toContain('+6.67% vs prev close');
    expect(parts).toContain('Open + closed');
    expect(parts).toContain('2 positions not counted');
    expect(tones(el)[parts.indexOf('+7.00 €')]).toBe('pos');
    expect(tones(el)[parts.indexOf('C 112.00')]).toBe('neutral');
  });

  it('summarises the visible range when nothing is hovered', () => {
    const { fixture, el } = render(response(MIXED));
    at(fixture, 0, 2);
    expect(readout(el)).toEqual([
      'Equity change +12.00 € (+12.00%)', 'High 120.00', 'Low 90.00',
      'Max drawdown within range -4.55%',
    ]);
    expect(tones(el)).toEqual(['pos', 'neutral', 'neutral', 'neg']);
  });
```

In `'explains the percentage in a tooltip'`, hover first: insert `fixture.componentInstance['onCrosshair']({ logical: 2 }); fixture.detectChanges();` after `render` (destructure `fixture` too).

Replace `'follows the crosshair, and returns to the latest candle when it leaves'` with:

```ts
  it('follows the crosshair, and returns to the range summary when it leaves', () => {
    const { fixture, el } = render(response(MIXED));
    at(fixture, 0, 2);
    fixture.componentInstance['onCrosshair']({ logical: 1 });
    fixture.detectChanges();
    expect(readout(el)[0]).toBe('Oct 19, 2026');
    expect(readout(el)).toContain('approx');
    expect(tones(el)[readout(el).indexOf('-5.00 €')]).toBe('neg');

    fixture.componentInstance['onCrosshair']({ logical: undefined });
    fixture.detectChanges();
    expect(readout(el)[0]).toBe('Equity change +12.00 € (+12.00%)');
  });
```

Replace `'always states what the account is'` with:

```ts
  it('states what the account is, directly under the readout', () => {
    const { fixture, el } = render(response(MIXED));
    at(fixture, 0, 2);
    const account = el.querySelector('.readout')!.nextElementSibling;
    expect(account?.classList.contains('account')).toBe(true);
    expect(account?.textContent?.trim()).toBe('Paper account · before tax and costs');
    expect(el.querySelectorAll('.account').length).toBe(1);
  });
```

In `'uses the currency it is given, not the API symbol'`, change the assertion to `expect(readout(el)[0]).toContain('+12.00 £');` after an `at(fixture, 0, 2);`.

Append inside the `describe`:

```ts
  it('draws the baseline at the first in-window open, washed pos above and neg below', () => {
    const { fixture } = render(response(MIXED));
    at(fixture, 1, 2);
    const base = fixture.componentInstance['baseline']?.current();
    expect(base?.value).toBe(110);
    expect(base?.above).toBe(token('--pos-soft'));
    expect(base?.below).toBe(token('--neg-soft'));
    expect(base?.line).toBe(token('--text-muted'));
  });

  it('asks for older history near the left edge, once, only while there is more', () => {
    const { fixture, stub } = render(response(MIXED));
    const loadOlder = vi.spyOn(stub, 'loadOlder');
    stub.hasMore.set(false);
    at(fixture, 1, 2);
    expect(loadOlder).not.toHaveBeenCalled();

    stub.hasMore.set(true);
    at(fixture, 1, 2);
    expect(loadOlder).toHaveBeenCalledTimes(1);

    stub.pageLoading.set(true);
    at(fixture, 0, 2);
    expect(loadOlder).toHaveBeenCalledTimes(1);
  });

  it('keeps the candles and offers a retry when a history page fails', () => {
    const { fixture, el, stub } = render(response(MIXED));
    const loadOlder = vi.spyOn(stub, 'loadOlder');
    stub.pageError.set(true);
    fixture.detectChanges();
    const note = el.querySelector('.page-error')!;
    expect(note.textContent).toContain("Couldn't load earlier history");
    expect(fixture.componentInstance['state']()).toBe('chart');
    note.querySelector('button')!.click();
    expect(loadOlder).toHaveBeenCalledTimes(1);
  });

  it('reports leaving the live edge and offers Latest, which scrolls back', () => {
    const { fixture, el, stub } = render(response(MIXED));
    // vi.spyOn calls through, so the stub's atLiveEdge follows what the component reports.
    const setEdge = vi.spyOn(stub, 'setAtLiveEdge');
    at(fixture, 0, 0);
    expect(setEdge).toHaveBeenLastCalledWith(false);
    expect(stub.atLiveEdge()).toBe(false);
    const scroll = vi.spyOn(
      (fixture.componentInstance as unknown as { chart: { timeScale(): { scrollToRealTime(): void } } })
        .chart.timeScale(), 'scrollToRealTime');
    const latest = [...el.querySelectorAll('button')].find((b) => b.textContent!.includes('Latest'))!;
    latest.click();
    expect(scroll).toHaveBeenCalledTimes(1);

    stub.setAtLiveEdge(true);
    fixture.detectChanges();
    expect([...el.querySelectorAll('button')].some((b) => b.textContent!.includes('Latest'))).toBe(false);
  });

  it('never moves the viewport on a scan refresh while the past is in view', () => {
    const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => 600);
    try {
      const { fixture, stub } = render(response(MIXED));
      const scale = (fixture.componentInstance as unknown as {
        chart: { timeScale(): { fitContent(): void; scrollToRealTime(): void } } }).chart.timeScale();
      const fit = vi.spyOn(scale, 'fitContent');
      const scroll = vi.spyOn(scale, 'scrollToRealTime');
      stub.setAtLiveEdge(false);
      stub.data.set(response([...MIXED, candle('2026-10-21', { o: 112, c: 115 })]));
      fixture.detectChanges();
      expect(fit).not.toHaveBeenCalled();
      expect(scroll).not.toHaveBeenCalled();
    } finally {
      widthSpy.mockRestore();
    }
  });
```

(The host has a width from the start, so the first render fits once, before the spies exist; the refresh must not fit again.)

- [ ] **Step 5: Run them to see them fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
Expected: FAIL — `onVisibleRange is not a function`, no `.page-error`, no Latest button, readout still the latest candle.

- [ ] **Step 6: Wire the component**

In `equity-candles.ts`:

Imports — add:

```ts
import { Button } from '../../../ui/button';
import { BaselinePrimitive } from '../../../ui/chart/primitives/baseline-primitive';
import { LogicalWindow, inWindowCandles, rangeStats, shouldLoadOlder } from './equity-range.model';
```

and in the `./equity-candles.model` import list replace `readoutParts` with `ReadoutPart, candleReadout, isAtLiveEdge, rangeReadoutParts`. Set `imports: [Async, Segmented, Button]`.

Template — replace everything from `<div class="controls">` to the end of the template with:

```html
    <div class="controls">
      <sb-segmented
        class="timeframe"
        label="Candle timeframe"
        [options]="timeframeOptions"
        [value]="store.tf()"
        (valueChange)="onTimeframe($event)"
      />
      <sb-segmented
        class="basis"
        label="Equity basis"
        [options]="basisOptions"
        [value]="store.basis()"
        (valueChange)="onBasis($event)"
      />
      @if (state() === 'chart' && !store.atLiveEdge()) {
        <button sb-button type="button" variant="ghost" class="latest" (click)="toLatest()">↦ Latest</button>
      }
    </div>
    @if (readout().length) {
      <p class="readout">
        @for (part of readout(); track $index) {
          <span class="part" [attr.data-tone]="part.tone"
                [attr.title]="isChangePart(part.text) ? changeTooltip : null">{{ part.text }}</span>
        }
      </p>
    }
    <p class="account">{{ accountLabel }}</p>
    @if (state() !== 'chart') {
      <sb-async
        class="states"
        [loading]="state() === 'loading'"
        [error]="store.error()"
        [empty]="state() === 'empty'"
        emptyReason="no-data-yet"
        [emptyTitle]="emptyTitle()"
        [skeletonRows]="3"
        [skeletonCols]="1"
        (retry)="store.load()"
      />
    }
    <div class="stage">
      <div #host class="chart" [class.hidden]="state() !== 'chart'"></div>
      @if (state() === 'chart' && store.pageError()) {
        <p class="page-error" role="status">
          Couldn't load earlier history ·
          <button sb-button type="button" variant="link" (click)="store.loadOlder()">Retry</button>
        </p>
      }
    </div>
    @if (showCaption()) {
      <p class="caption">{{ caption() }}</p>
    }
```

Styles — replace the `:host` grid areas, `.chart`, `.caption, .account` rules and both media blocks with:

```css
    :host {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: "controls" "readout" "account" "chart" "states" "caption";
      row-gap: var(--space-6);
      min-width: 0;
    }
    .part[data-tone='pos'] { color: var(--pos); }
    .part[data-tone='neg'] { color: var(--neg); }
    .part[data-tone='warn'] { color: var(--warn); }
    .stage { grid-area: chart; position: relative; min-width: 0; }
    .chart { width: 100%; min-width: 0; height: 200px; }
    .chart.hidden { display: none; }
    /* v181 §9: a failed history page never blanks the chart; the note sits
       over its left edge, where the missing history would be. */
    .page-error {
      position: absolute;
      top: var(--space-4);
      left: var(--space-4);
      margin: 0;
      padding: var(--space-4) var(--space-6);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--panel-radius);
      font-size: var(--text-chip);
      color: var(--text-secondary);
    }
    .caption, .account { margin: 0; font-size: var(--text-chip); }
    .caption { grid-area: caption; color: var(--text-muted); }
    .account { grid-area: account; color: var(--text-faint); }

    @media (max-width: 639px) {
      :host { grid-template-areas: "controls" "chart" "states" "readout" "account" "caption"; }
      .controls sb-segmented { flex: 1 1 100%; }
      .chart { height: 160px; }
    }

    @media (min-width: 1024px) {
      :host {
        grid-template-columns: auto minmax(0, 1fr);
        grid-template-areas:
          "controls readout"
          "controls account"
          "chart chart"
          "states states"
          "caption caption";
        column-gap: var(--space-10);
      }
      .readout { align-self: end; justify-self: end; text-align: right; }
      .account { justify-self: end; text-align: right; }
    }
```

(Keep `.controls`, `.readout`, `.part + .part::before`, `.part[title]` and `.states` as they are.)

Class body — change `colors` to carry the baseline colours:

```ts
  private readonly colors = (() => {
    const palette = chartPalette();
    return { up: palette.up, down: palette.down, faint: token('--text-faint'), muted: palette.textMuted,
             posSoft: palette.posSoft, negSoft: palette.negSoft };
  })();
```

Add the field `protected baseline: BaselinePrimitive | null = null;` beside `seam`, change `visible` to `signal<LogicalWindow | null>(null)`, and replace `shown` and `readout` with:

```ts
  /** The whole buckets in view (spec v181 §4): readout, baseline and, in
   *  part 2, the KPI window all read this one list. */
  protected readonly inWindow = computed(() => inWindowCandles(this.visible(), this.candles()));

  private readonly hovered = computed(() => {
    const index = this.hoverIndex();
    return index === null ? null : (this.candles()[index] ?? null);
  });

  /** Hovered candle, else the visible range, else the latest candle. */
  protected readonly readout = computed<ReadoutPart[]>(() => {
    const data = this.store.data();
    if (!data) return [];
    const hovered = this.hovered();
    if (hovered) return candleReadout(hovered, data.basis, this.currency(), data.tf);
    const range = rangeReadoutParts(rangeStats(this.inWindow()), this.currency());
    if (range.length) return range;
    const latest = this.candles().at(-1);
    return latest ? candleReadout(latest, data.basis, this.currency(), data.tf) : [];
  });
```

In the constructor, after the render effect, add:

```ts
    effect(() => {
      const first = this.inWindow()[0];
      untracked(() => this.baseline?.setBaseline(first
        ? { value: first.o, line: this.colors.muted, above: this.colors.posSoft, below: this.colors.negSoft }
        : null));
    });
```

and add `this.baseline = null;` to the `onDestroy` block.

Add the handlers below `onCrosshair`:

```ts
  /** Every visible-range change, user or programmatic: remember it, report
   *  the live edge, and page in older history near the left edge. */
  protected onVisibleRange(range: LogicalWindow | null): void {
    this.visible.set(range);
    const atEdge = isAtLiveEdge(range, this.candles().length);
    if (atEdge !== this.store.atLiveEdge()) this.store.setAtLiveEdge(atEdge);
    if (shouldLoadOlder(range, this.store.hasMore(), this.store.pageLoading())) this.store.loadOlder();
  }

  /** "↦ Latest": back to the newest candle at the current zoom. */
  protected toLatest(): void {
    this.chart?.timeScale().scrollToRealTime();
  }
```

In `create()`, attach the baseline before the seam (so the seam paints over the wash) and route the range subscription through the handler:

```ts
    this.baseline = new BaselinePrimitive();
    series.attachPrimitive(this.baseline);
    this.seam = new VLinePrimitive();
    series.attachPrimitive(this.seam);
    chart.subscribeCrosshairMove((param) => this.onCrosshair(param));
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) =>
      this.onVisibleRange(range ? { from: range.from, to: range.to } : null));
```

`render()` is unchanged: prepended pages and refreshes go through `setData`, which keeps the time scale's right offset, so the view neither jumps on a prepend nor snaps to now on a refresh; only a timeframe/basis change fits.

- [ ] **Step 7: Run the chart and its callers**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/equity-candles.ts \
  frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts \
  frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts \
  frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts
git commit -m "feat(v181): equity chart reads out the visible range, pages older history, baseline and Latest" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V181-8: Auto timeframe on zoom with the programmatic-move flag

**Model:** sonnet — chart-event state machine (flag, pending step, restore) over pure helpers; timing-sensitive but bounded.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts` (append `WallSpan`, `wallSpan`, `chartRangeFor`, `stepDownBlocked`) — only V181-7 and this task touch this file, in sequence; the pure helpers stay out of `equity-range.model.ts`, which V181-12 may be editing in parallel.
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`

**Interfaces:**
- Consumes: V181-2 `nextTimeframe(barCount: number, tf: EquityTimeframe, atHistoryEdge: boolean): EquityTimeframe`; V181-7 `inWindow`, `onVisibleRange`; store `setTimeframe(tf)` (writes the preference, as a manual pick does).
- Produces: `interface WallSpan { from: number; to: number }` (New York wall-clock seconds, `[from, to)`); `wallSpan(candles: readonly EquityCandle[], tf: EquityTimeframe): WallSpan | null`; `chartRangeFor(span: WallSpan, tf: EquityTimeframe): { from: Time; to: Time }`; `stepDownBlocked(tf: EquityTimeframe, first: EquityCandle | undefined, recordingSince: string | null): boolean`. Component: `private programmatic: boolean`, `private moveProgrammatically(fn: () => void): void` (V181-15 reads the flag in `onVisibleRange` and wraps its own `setVisibleRange` in it); `PROGRAMMATIC_SETTLE_MS = 100`.

Behaviour (spec §3, §7):
- On every visible-range change, `nextTimeframe(inWindow().length, tf, stepDownBlocked(…))` decides; a different answer records the in-window span and calls `store.setTimeframe(next)`. No second step while one is waiting for its candles.
- When the new timeframe's candles render, the view is restored to the recorded span with `setVisibleRange` (centre kept, span as close as the new candle width allows) **instead of** `fitContent`.
- **Edge of history:** stepping 1D → 4H is blocked while the window starts before the New York date of `recording_since` (intraday candles only exist from there), and when there is no recording at all. 4H → 1H has the same coverage, 1W → 1D always has daily bars.
- Every viewport change the component makes itself (fit, restore) runs inside `moveProgrammatically`, which holds `programmatic` true until `PROGRAMMATIC_SETTLE_MS` after the call: lightweight-charts delivers the range event on its next paint, not synchronously, so clearing the flag on return would miss it. A manual timeframe pick drops any pending restore.
- A timeframe change touches candles only; the scope window is part 2's and is never derived from the timeframe.

- [ ] **Step 1: Write the failing model tests**

In `equity-candles.model.spec.ts`, extend the import list with `chartRangeFor, stepDownBlocked, wallSpan` and append:

```ts
describe('v181 timeframe step helpers', () => {
  const hourly = (iso: string) => candle({ t: `${iso}-04:00` });

  it('spans whole buckets on the New York wall clock', () => {
    const span = wallSpan([hourly('2026-10-20T09:00:00'), hourly('2026-10-20T15:00:00')], '1H');
    expect(span).toEqual({ from: Date.UTC(2026, 9, 20, 9) / 1000, to: Date.UTC(2026, 9, 20, 16) / 1000 });
    expect(wallSpan([candle({ t: '2026-10-19' }), candle({ t: '2026-10-20' })], '1D'))
      .toEqual({ from: Date.UTC(2026, 9, 19) / 1000, to: Date.UTC(2026, 9, 21) / 1000 });
    expect(wallSpan([], '1D')).toBeNull();
  });

  it('turns a span into chart times for the target timeframe', () => {
    const span = { from: Date.UTC(2026, 9, 19) / 1000, to: Date.UTC(2026, 9, 21) / 1000 };
    expect(chartRangeFor(span, '4H')).toEqual({ from: span.from, to: span.to - 1 });
    expect(chartRangeFor(span, '1D')).toEqual({ from: '2026-10-19', to: '2026-10-20' });
    expect(chartRangeFor(span, '1W')).toEqual({ from: '2026-10-19', to: '2026-10-20' });
  });

  it('blocks 1D -> 4H only where no intraday candles can exist', () => {
    const since = '2026-10-20T13:35:00Z';
    expect(stepDownBlocked('1D', candle({ t: '2026-10-19' }), since)).toBe(true);
    expect(stepDownBlocked('1D', candle({ t: '2026-10-20' }), since)).toBe(false);
    expect(stepDownBlocked('1D', candle({ t: '2026-10-20' }), null)).toBe(true);
    expect(stepDownBlocked('1D', undefined, since)).toBe(true);
    expect(stepDownBlocked('4H', candle({ t: '2026-01-02T09:00:00-05:00' }), since)).toBe(false);
    expect(stepDownBlocked('1W', candle({ t: '2025-01-06' }), since)).toBe(false);
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`
Expected: FAIL — `wallSpan is not a function` (and siblings).

- [ ] **Step 3: Add the helpers**

In `equity-candles.model.ts` append:

```ts
const TF_SECONDS: Record<EquityTimeframe, number> = {
  '1H': 3_600,
  '4H': 14_400,
  '1D': 86_400,
  '1W': 604_800,
};

const NY_ISO_DAY = new Intl.DateTimeFormat('en-CA', {
  timeZone: NY, year: 'numeric', month: '2-digit', day: '2-digit',
});

/** A run of whole buckets on the New York wall clock, `[from, to)`, in
 *  seconds read as if UTC — the same convention as `toChartTime`. */
export interface WallSpan {
  from: number;
  to: number;
}

function wallSeconds(t: string, tf: EquityTimeframe): number {
  const iso = isIntraday(tf) ? `${t.slice(0, 19)}Z` : `${t.slice(0, 10)}T00:00:00Z`;
  return Date.parse(iso) / 1000;
}

/** The span the in-window candles cover: first bucket start to last bucket end. */
export function wallSpan(candles: readonly EquityCandle[], tf: EquityTimeframe): WallSpan | null {
  const last = candles.at(-1);
  if (!last) return null;
  return { from: wallSeconds(candles[0].t, tf), to: wallSeconds(last.t, tf) + TF_SECONDS[tf] };
}

/** `setVisibleRange` arguments that show `span` on timeframe `tf`. */
export function chartRangeFor(span: WallSpan, tf: EquityTimeframe): { from: Time; to: Time } {
  const last = span.to - 1;
  if (isIntraday(tf)) return { from: span.from as UTCTimestamp, to: last as UTCTimestamp };
  const day = (seconds: number) => new Date(seconds * 1000).toISOString().slice(0, 10) as Time;
  return { from: day(span.from), to: day(last) };
}

/** v181 §3 edge of history: 1H/4H candles exist only since recording began,
 *  so zooming into an older 1D window stays on 1D rather than going blank. */
export function stepDownBlocked(
  tf: EquityTimeframe,
  first: EquityCandle | undefined,
  recordingSince: string | null,
): boolean {
  if (tf !== '1D') return false;
  if (!first || recordingSince === null) return true;
  return first.t.slice(0, 10) < NY_ISO_DAY.format(new Date(recordingSince));
}
```

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 4: Write the failing component tests**

In `equity-candles.spec.ts`, add `afterEach` to the vitest import and these helpers above the `describe`:

```ts
/** `count` hourly candles from 2026-10-01 00:00 New York (EDT all month). */
function hourlyCandles(count: number): EquityCandle[] {
  return Array.from({ length: count }, (_, i) => {
    const wall = new Date(Date.UTC(2026, 9, 1) + i * 3_600_000).toISOString().slice(0, 19);
    return candle(`${wall}-04:00`);
  });
}

function dailyCandles(count: number): EquityCandle[] {
  return Array.from({ length: count }, (_, i) =>
    candle(new Date(Date.UTC(2026, 8, 1) + i * 86_400_000).toISOString().slice(0, 10)));
}

type Scale = { fitContent(): void; setVisibleRange(range: unknown): void };
const scaleOf = (fixture: { componentInstance: EquityCandles }) =>
  (fixture.componentInstance as unknown as { chart: { timeScale(): Scale } }).chart.timeScale();
```

Append inside the `describe` (the `at()` helper is V181-7's):

```ts
  describe('auto timeframe (v181 §3)', () => {
    afterEach(() => vi.useRealTimers());

    it('steps up past 250 visible bars and restores the same span on the new candles', () => {
      const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => 600);
      try {
        const { fixture, stub } = render(response(hourlyCandles(300), { tf: '1H' }));
        at(fixture, 0, 299);
        expect(stub.calls.tf).toEqual(['4H']);

        const scale = scaleOf(fixture);
        const restore = vi.spyOn(scale, 'setVisibleRange').mockImplementation(() => {});
        const fit = vi.spyOn(scale, 'fitContent');
        stub.data.set(response(hourlyCandles(80), { tf: '4H' }));
        fixture.detectChanges();
        const from = Date.UTC(2026, 9, 1) / 1000;
        expect(restore).toHaveBeenCalledWith({ from, to: from + 300 * 3600 - 1 });
        expect(fit).not.toHaveBeenCalled();
      } finally {
        widthSpy.mockRestore();
      }
    });

    it('steps down below 15 visible bars', () => {
      const { fixture, stub } = render(
        response(dailyCandles(40), { tf: '1D', recording_since: '2026-08-01T13:30:00Z' }));
      at(fixture, 0, 9);
      expect(stub.calls.tf).toEqual(['4H']);
    });

    it('holds at the edge of history, where no intraday candles exist', () => {
      const { fixture, stub } = render(
        response(dailyCandles(40), { tf: '1D', recording_since: '2026-10-01T13:30:00Z' }));
      at(fixture, 0, 9);
      expect(stub.calls.tf).toEqual([]);
    });

    it('holds between 15 and 250 bars', () => {
      const { fixture, stub } = render(response(dailyCandles(40), { tf: '1D' }));
      at(fixture, 0, 39);
      expect(stub.calls.tf).toEqual([]);
    });

    it('takes one step at a time while the new candles load', () => {
      const { fixture, stub } = render(response(hourlyCandles(300), { tf: '1H' }));
      at(fixture, 0, 299);
      at(fixture, 0, 298);
      expect(stub.calls.tf).toEqual(['4H']);
    });

    it('drops a pending restore when the partner picks a timeframe by hand', () => {
      const { fixture, stub } = render(response(hourlyCandles(300), { tf: '1H' }));
      at(fixture, 0, 299);
      fixture.componentInstance['onTimeframe']('1D');
      expect(fixture.componentInstance['pendingSpan']).toBeNull();
      expect(stub.calls.tf).toEqual(['4H', '1D']);
    });
  });

  describe('programmatic moves (v181 §1, §7)', () => {
    afterEach(() => vi.useRealTimers());

    it('holds the flag through the chart\'s next paint, then releases it', () => {
      vi.useFakeTimers();
      const { fixture } = render(response(MIXED));
      const component = fixture.componentInstance as unknown as {
        programmatic: boolean; moveProgrammatically(fn: () => void): void };
      let inside = false;
      component.moveProgrammatically(() => (inside = component.programmatic));
      expect(inside).toBe(true);
      expect(component.programmatic).toBe(true);
      vi.advanceTimersByTime(99);
      expect(component.programmatic).toBe(true);
      vi.advanceTimersByTime(1);
      expect(component.programmatic).toBe(false);
    });

    it('fits a new timeframe under the flag', () => {
      const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => 600);
      try {
        const { fixture, stub } = render(response(MIXED));
        const component = fixture.componentInstance as unknown as { programmatic: boolean };
        let flagged: boolean | null = null;
        vi.spyOn(scaleOf(fixture), 'fitContent').mockImplementation(() => (flagged = component.programmatic));
        stub.data.set(response(MIXED, { tf: '1W' }));
        fixture.detectChanges();
        expect(flagged).toBe(true);
      } finally {
        widthSpy.mockRestore();
      }
    });
  });
```

- [ ] **Step 5: Run them to see them fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
Expected: FAIL — no timeframe step recorded, `moveProgrammatically is not a function`.

- [ ] **Step 6: Implement the step, the restore and the flag**

In `equity-candles.ts`:

Imports — add `nextTimeframe` to the `./equity-range.model` import and `WallSpan, chartRangeFor, stepDownBlocked, wallSpan` to the `./equity-candles.model` import (`Time` already comes from `lightweight-charts`).

Above the `@Component` decorator:

```ts
/** How long a viewport change the component made itself stays flagged.
 *  lightweight-charts reports the new range on its next paint, so the flag
 *  must outlive the call; 100 ms covers several frames and is far shorter
 *  than any deliberate gesture that follows it. */
export const PROGRAMMATIC_SETTLE_MS = 100;
```

Fields, beside `pendingView`:

```ts
  /** True while a viewport change made by this component (fit, restore, and
   *  in part 2 a preset move) is still being reported back by the chart. */
  private programmatic = false;
  private releaseTimer: ReturnType<typeof setTimeout> | null = null;
  /** An auto step waiting for its candles: the span to show on them. */
  private pendingSpan: { tf: EquityTimeframe; span: WallSpan } | null = null;
```

`onTimeframe` — a hand pick drops a pending restore:

```ts
  protected onTimeframe(value: string): void {
    const tf = EQUITY_TIMEFRAMES.find((option) => option === value);
    if (!tf) return;
    this.pendingSpan = null;
    this.store.setTimeframe(tf as EquityTimeframe);
  }
```

`onVisibleRange` — add the step as its last line:

```ts
  protected onVisibleRange(range: LogicalWindow | null): void {
    this.visible.set(range);
    const atEdge = isAtLiveEdge(range, this.candles().length);
    if (atEdge !== this.store.atLiveEdge()) this.store.setAtLiveEdge(atEdge);
    if (shouldLoadOlder(range, this.store.hasMore(), this.store.pageLoading())) this.store.loadOlder();
    this.autoTimeframe();
  }

  /** v181 §3: more than 250 bars → one step coarser, fewer than 15 → one
   *  step finer, written like a manual pick. The span is kept for the restore. */
  private autoTimeframe(): void {
    const data = this.store.data();
    if (!data || this.pendingSpan) return;
    const window = this.inWindow();
    const next = nextTimeframe(window.length, data.tf,
      stepDownBlocked(data.tf, window[0], data.recording_since));
    const span = wallSpan(window, data.tf);
    if (next === data.tf || !span) return;
    this.pendingSpan = { tf: next, span };
    this.store.setTimeframe(next);
  }

  private moveProgrammatically(fn: () => void): void {
    this.programmatic = true;
    if (this.releaseTimer !== null) clearTimeout(this.releaseTimer);
    try {
      fn();
    } finally {
      this.releaseTimer = setTimeout(() => {
        this.programmatic = false;
        this.releaseTimer = null;
      }, PROGRAMMATIC_SETTLE_MS);
    }
  }
```

`fitWhenVisible` — restore a pending span instead of fitting, both under the flag:

```ts
  private fitWhenVisible(): void {
    const view = this.pendingView;
    const chart = this.chart;
    if (!view || !chart || this.host().nativeElement.clientWidth === 0) return;
    const restore = this.restorableRange();
    this.moveProgrammatically(() => {
      if (restore) chart.timeScale().setVisibleRange(restore);
      else chart.timeScale().fitContent();
    });
    this.renderedView = view;
    this.pendingView = '';
    this.pendingSpan = null;
  }

  /** The recorded span, once the step's own timeframe has candles to show it on. */
  private restorableRange(): { from: Time; to: Time } | null {
    const pending = this.pendingSpan;
    const data = this.store.data();
    if (!pending || !data || data.tf !== pending.tf || !data.candles.length) return null;
    return chartRangeFor(pending.span, pending.tf);
  }
```

In the `onDestroy` block add `if (this.releaseTimer !== null) clearTimeout(this.releaseTimer);`.

If the restored span lies partly before the first loaded candle, lightweight-charts clamps it to the data and the V181-7 paging trigger then loads the older page — no extra code.

- [ ] **Step 7: Run the chart specs**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/equity-candles.ts \
  frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts \
  frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts \
  frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts
git commit -m "feat(v181): equity chart steps timeframe on zoom (250/15 bars) and keeps the span" \
  -m "Viewport moves the component makes itself run under a programmatic flag that outlives the chart's next paint." \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

