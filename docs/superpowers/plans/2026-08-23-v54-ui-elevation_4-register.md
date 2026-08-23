# UI Elevation (v54) — Part 4: Registers and the chart system

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Index:** `2026-08-23-v54-ui-elevation_0-index.md` — read its Global Constraints first.
**Spec:** `docs/superpowers/specs/2026-08-23-v54-ui-elevation-design.md` (decisions D1, D5)

**Goal:** Every panel declares whether it presents or instruments, and the four chart components draw from one tokenised palette that cannot collide with the valence law.

**Runs after `_3` merges** (needs `--shadow-overlay` and the elevation classes). **Parallel with `_5`** — `_4` is panels and charts, `_5` is shell nav, live regions and motion.

---

### Task 30: The two register classes

**Files:**
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/app/ui/register.spec.ts` (create)

**Interfaces:**
- Produces: `.register-presentation`, `.register-instrument`. Tasks 31–34 apply them.

Both registers draw from the **same closed scales**. A register picks different rungs; it never introduces a value that is not already on the scale.

- [ ] **Step 1: Write the failing test**

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const GLOBAL = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');

const rule = (name: string) => GLOBAL.match(new RegExp(`\\.${name}\\s*\\{[^}]*\\}`, 's'))?.[0] ?? '';

describe('the two registers', () => {
  it('defines both', () => {
    expect(rule('register-presentation')).not.toBe('');
    expect(rule('register-instrument')).not.toBe('');
  });

  for (const name of ['register-presentation', 'register-instrument']) {
    it(`${name} introduces no off-scale value`, () => {
      // Every length must come from a token. A register that needed a new
      // size would be a review defect, exactly as an off-scale literal is.
      const literals = [...rule(name).matchAll(/:\s*([0-9.]+)px/g)]
        .map(([, v]) => Number(v))
        .filter((v) => v > 2);
      expect(literals).toEqual([]);
    });
  }

  it('gives the two registers different density', () => {
    expect(rule('register-presentation')).not.toBe(rule('register-instrument'));
  });
});
```

- [ ] **Step 2: Run, watch it fail, then add the rules to `styles.css`**

```css
/* The two registers — spec v54 D1.
 *
 * DENSITY IS A PROPERTY OF THE PANEL, NOT THE APP.
 *
 * Which one a panel takes is decided by what it ANSWERS:
 *
 *   presentation  "how am I doing?"      hero figures, room to breathe
 *   instrument    "what happened to row 4,192?"   tight rows, more per screen
 *
 * Declared per PANEL, not per workspace, because analytics is genuinely both
 * — its summary strip presents and its tables instrument — and a
 * workspace-level rule would force it to misdeclare itself. A workspace sets
 * a default on its root; a panel may opt out.
 *
 * Both pull from the same closed scales. Neither adds a value. */
.register-presentation {
  --register-gap: var(--space-20);
  --register-pad: var(--space-20);
  --register-figure: var(--text-metric);
  --register-label: var(--text-table);
}

.register-instrument {
  --register-gap: var(--space-8);
  --register-pad: var(--space-10);
  --register-figure: var(--text-table);
  --register-label: var(--text-micro);
}

/* Panels read the four variables rather than the register class, so a panel
 * that opts out of its workspace's default needs no special-casing. */
.register-presentation,
.register-instrument {
  gap: var(--register-gap);
}
```

- [ ] **Step 3: Run, commit**

```bash
git add frontend/src/styles.css frontend/src/app/ui/register.spec.ts
git commit -m "feat(v54): add the presentation and instrument registers"
```

---

### Task 31: Dashboard and Calendar take the presentation register

**Files:** Modify `workspaces/dashboard/dashboard.ts`, and the v53 calendar workspace.

- [ ] Put `class="register-presentation"` on each workspace root.
- [ ] Convert the metric cards to read `var(--register-figure)` and `var(--register-label)` instead of naming `--text-metric` / `--text-table` directly, so a panel that opts out changes with one class.
- [ ] Replace hardcoded gutters in these two files with `var(--register-pad)`.
- [ ] Look at both at 1440px and at 640px. The presentation register must not cause a horizontal scrollbar — `styles.css`'s `min-width: 0` guard covers the grid child, but a hero figure at `--text-metric` in a narrow column can still overflow its own box.
- [ ] Run `npm test`, commit `feat(v54): dashboard and calendar take the presentation register`.

---

### Task 32: Analytics splits registers

**Files:** Modify `workspaces/analytics/analytics.ts` (1582 lines — set classes, do not restructure).

This is the task D1 exists for.

- [ ] Root gets `class="register-instrument"` (its bulk is tables).
- [ ] The summary strip panel gets `class="register-presentation"`, overriding the root.
- [ ] Verify the override actually wins: the four variables are redefined on the inner element, so cascade order handles it — confirm in DevTools that a strip figure computes to `--text-metric` while a table cell in the same page computes to `--text-table`.
- [ ] Commit `feat(v54): analytics presents its summary strip and instruments its tables`.

---

### Task 33: The remaining five take the instrument register

**Files:** Modify `workspaces/{trades,risk,system,watchlist,versions}/*.ts`.

- [ ] `class="register-instrument"` on each root.
- [ ] Replace hardcoded gutters with `var(--register-pad)` and label sizes with `var(--register-label)`.
- [ ] Verify row height did not grow: these five are where density matters, and a register that costs a visible row per table is a regression. Count visible rows at 1080p before and after.
- [ ] Commit `feat(v54): the five working surfaces take the instrument register`.

---

### Task 34: Gate the registers

**Files:** Modify `frontend/src/app/ui/register.spec.ts`.

- [ ] **Step 1: Add the coverage gate**

```ts
import { callSites } from './testing/call-sites';

const WORKSPACE_ROOTS = [
  'workspaces/dashboard/dashboard.ts',
  'workspaces/trades/trades.ts',
  'workspaces/analytics/analytics.ts',
  'workspaces/risk/risk.ts',
  'workspaces/watchlist/watchlist.ts',
  'workspaces/versions/versions.ts',
  'workspaces/system/system.ts',
  'workspaces/calendar/calendar.ts',
];

const sources = new Map(callSites().map(({ name, source }) => [name, source]));

describe('every workspace declares a register', () => {
  for (const file of WORKSPACE_ROOTS) {
    it(`${file} declares one`, () => {
      expect(sources.get(file) ?? '').toMatch(/register-(presentation|instrument)/);
    });
  }
});

describe('both registers are actually used', () => {
  const all = [...sources.values()].join('\n');
  // If everything ended up in one register, D1 was applied mechanically.
  it('uses presentation somewhere', () => expect(all).toContain('register-presentation'));
  it('uses instrument somewhere', () => expect(all).toContain('register-instrument'));
});
```

- [ ] **Step 2: Run, commit** `test(v54): gate that every workspace declares a register`.

---

### Task 35: `--chart-1…8` and the ΔE gate

**Files:**
- Modify: `frontend/src/styles/tokens.css`
- Test: `frontend/src/app/ui/chart-palette.spec.ts` (create)

**Interfaces:**
- Produces: `--chart-1` … `--chart-8`. Tasks 36–37 consume them.

**The rule:** a categorical series colour may never be `--pos` or `--neg`. Green means gain and red means loss on every other surface; a series that happened to be green would lie to a reader every other screen has trained. Series colours are a **separate namespace** — which is also how this squares with `tokens.css`'s "a sixth hue is a review defect": that rule governs *semantic* hues, and series colours are identifiers, not semantics.

- [ ] **Step 1: Write the failing test, with a real ΔE**

Create `frontend/src/app/ui/chart-palette.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

function token(name: string): string {
  const m = CSS.match(new RegExp(`^\\s*${name}:\\s*(#[0-9a-fA-F]{6});`, 'm'));
  if (!m) throw new Error(`${name} is not defined as a hex literal`);
  return m[1];
}

/** sRGB hex -> CIE L*a*b* (D65). Enough for a distance check; this is a gate,
 *  not a colour-management pipeline. */
function lab(hex: string): [number, number, number] {
  const to = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const r = to(parseInt(hex.slice(1, 3), 16) / 255);
  const g = to(parseInt(hex.slice(3, 5), 16) / 255);
  const b = to(parseInt(hex.slice(5, 7), 16) / 255);
  const x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047;
  const y = r * 0.2126 + g * 0.7152 + b * 0.0722;
  const z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883;
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const [fx, fy, fz] = [f(x), f(y), f(z)];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

function deltaE(a: string, b: string): number {
  const [l1, a1, b1] = lab(a);
  const [l2, a2, b2] = lab(b);
  return Math.hypot(l1 - l2, a1 - a2, b1 - b2);
}

const SERIES = Array.from({ length: 8 }, (_, i) => `--chart-${i + 1}`);

describe('the chart series namespace', () => {
  for (const name of SERIES) {
    it(`defines ${name}`, () => expect(() => token(name)).not.toThrow());
  }

  // G9. Green means gain and red means loss everywhere else in this app; a
  // series that happened to be either would be lying.
  for (const name of SERIES) {
    for (const valence of ['--pos', '--neg']) {
      it(`${name} is not confusable with ${valence}`, () => {
        expect(deltaE(token(name), token(valence))).toBeGreaterThan(10);
      });
    }
  }

  it('keeps adjacent series distinguishable at 1px stroke', () => {
    for (let i = 0; i < SERIES.length - 1; i++) {
      expect(deltaE(token(SERIES[i]), token(SERIES[i + 1]))).toBeGreaterThan(15);
    }
  });
});
```

- [ ] **Step 2: Run and watch it fail.**

Run: `cd frontend && npm test -- --include src/app/ui/chart-palette.spec.ts`

- [ ] **Step 3: Add the ramp to `tokens.css`**

```css
  /* -- chart series ------------------------------------------------------
   * A SEPARATE NAMESPACE from the valence hues above, and deliberately so.
   *
   * The valence rule ("a sixth hue is a review defect") governs SEMANTIC
   * colour: --pos means good, --neg means bad, and those meanings hold on
   * every surface. A categorical series colour carries no meaning at all —
   * it is an identifier, telling you which line is AAPL. The two namespaces
   * must not overlap: a green series in an app where green means gain would
   * lie to a reader every other screen has trained.
   *
   * So the one binding rule, checked by chart-palette.spec.ts: no member is
   * within ΔE 10 of --pos or --neg, and adjacent members clear ΔE 15 so they
   * stay apart at a 1px stroke.
   *
   * Derived from the --accent / --info / --warn family rather than picked
   * freely, so the charts still look like they belong to this app. */
  --chart-1: #7b5cfa;
  --chart-2: #46c2ff;
  --chart-3: #ffb43d;
  --chart-4: #b48cff;
  --chart-5: #2f7fd4;
  --chart-6: #d07de0;
  --chart-7: #7fd8e8;
  --chart-8: #c9a227;
```

- [ ] **Step 4: Run the test**

If any pair fails its threshold, **adjust the colour, not the threshold.** The thresholds are the requirement; a loosened gate is a silently worse palette. Record any value you had to move and why in the commit message.

- [ ] **Step 5: Add the eight to `tokens.spec.ts`'s `REQUIRED` list, run, commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/app/ui
git commit -m "feat(v54): add the --chart-1..8 series namespace with a delta-E gate"
```

---

### Task 36: `line-chart` adopts the tokens

**Files:** Modify `frontend/src/app/ui/line-chart.ts:73`.

- [ ] **Step 1: Replace the eight hexes**

```ts
/**
 * Series colours, read from the token namespace rather than declared here.
 *
 * These were eight raw hexes — the only colours in the app outside
 * tokens.css, and unharmonised with the valence law: nothing stopped one of
 * them drifting into green, on a screen where green means gain.
 *
 * Read through getComputedStyle because a canvas/SVG stroke needs a resolved
 * value, not a `var()`. `test-setup.ts` injects tokens.css into the test
 * document, so this resolves under vitest too.
 */
const SERIES = Array.from({ length: 8 }, (_, i) => `--chart-${i + 1}`);

function seriesColour(index: number): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(SERIES[index % SERIES.length])
    .trim();
}
```

Replace every read of the old array with `seriesColour(i)`.

- [ ] **Step 2: Verify against the existing chart specs**

Run: `cd frontend && npm test -- --include src/app/ui/line-chart.spec.ts`

`vitest.config.ts` documents that `test-setup.ts` injects `tokens.css` for exactly this reason (SR35) — if the resolved value comes back empty, that injection is what to check, not this code.

- [ ] **Step 3: Run the hex gate from `_1` T12**

Run: `cd frontend && npm test -- --include src/app/ui/primitives.spec.ts`
Expected: PASS, and `HEX_ALLOWLIST` stays empty — this task is what closes G4.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/ui/line-chart.ts
git commit -m "feat(v54): line-chart reads the series namespace; last raw hexes gone"
```

---

### Task 37: One axis, grid and tooltip across all four charts

**Files:** Create `frontend/src/app/ui/chart/chart-frame.ts`; modify `ui/line-chart.ts`, `ui/sparkline.ts`, `ui/histogram.ts`, `ui/chart/trade-chart.ts`.

- [ ] **Step 1: Read all four and write down where they disagree**

Run: `cd frontend/src/app/ui && grep -n "stroke\|font-size\|--text-\|--border\|grid" line-chart.ts sparkline.ts histogram.ts chart/trade-chart.ts`

Record the axis colour, grid colour, tick font size and tooltip treatment each currently uses. They will not all match — that list is what this task fixes.

- [ ] **Step 2: Extract the shared constants**

```ts
/**
 * The chart chrome every chart shares: axis, grid, ticks, tooltip.
 *
 * The four chart components had each chosen their own axis colour and tick
 * size, so two charts side by side on Analytics did not look like one system.
 * Chrome is not data — it recedes, which is why every value here is a
 * greyscale token and none is a hue.
 */
export const CHART_CHROME = {
  axis: 'var(--border-strong)',
  grid: 'var(--border)',
  tickSize: 'var(--text-micro)',
  tickColour: 'var(--text-muted)',
  tooltipSurface: 'var(--surface-overlay)',
  tooltipBorder: 'var(--border-strong)',
} as const;
```

- [ ] **Step 3: Point all four at it, one at a time, running that chart's spec after each.**

- [ ] **Step 4: Compare them in the gallery**

Add a **Charts** section to `gallery.ts` showing all four with the same data. Their chrome must be indistinguishable.

- [ ] **Step 5: Run everything and commit**

Run: `cd frontend && npm test` → green.
Run: `python scripts/dev/testrun.py full` → unchanged.

```bash
git add frontend/src/app
git commit -m "feat(v54): one chart chrome across line, sparkline, histogram and trade charts"
```

## Wave 4 done when

- [ ] All eight workspaces declare a register, and **both** registers appear (Task 34).
- [ ] Analytics presents its strip and instruments its tables, verified in DevTools.
- [ ] The instrument workspaces lost no visible rows.
- [ ] `--chart-1..8` exist and pass the ΔE gate at the stated thresholds (G9), with no threshold loosened.
- [ ] Zero hex literals outside `tokens.css` (G4 fully closed).
- [ ] The four charts are indistinguishable in chrome, side by side in `/ui`.
- [ ] Python suite unchanged.
