# v195 — Graphite, Part 3: true minus and risk units, danger variants, panel and panel header

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-8:" -A 400 <this file>`.

**Scope of this part (V195-7..V195-9):** spec §1.1 (colour is never the only cue), §5.2 (risk figures carry both units), Phase 2 (buttons, panel, panel header) and corrections 5 and 6. V195-7 makes `pct()`, `money()` and `rMultiple()` print the true minus U+2212, exports it as `MINUS`, and adds `riskUnits`, the one formatter that renders a risk figure as money and % of account side by side (consumed by V195-25 and V195-27). V195-8 splits the danger button into `danger` (solid, the killswitch only) and `danger-quiet` (today's bordered look, every other destructive control) and gives `ConfirmDialog` a `dangerVariant` (consumed by V195-21 and every Phase 5 page). V195-9 re-skins `sb-panel`, `sb-panel-header` and `sb-section-head`: a 13px title with its hint beside it, quiet meta on the right, density-driven panel padding, and a `[header-actions]` slot on `sb-panel-header`.

**Where commands run.** Shell state does not persist between Bash calls and `cd` breaks the guardrail hooks, so every command below spells out the worktree path:

- `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`
- `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`

Frontend runs through `npm --prefix "$WT/frontend" ...`. Edit files only under `$WT/`; never the main tree's copies.

**The state parts 1 and 2 leave (read before editing).** After V195-6, in `$WT`:

- `frontend/src/styles/tokens.css`: Graphite tier 2 (`--neg #f06e66`, `--accent-fill #2563c4`); tier 3 flat (`--panel-bg: var(--surface)`, `--panel-shadow: none`, `--btn-fill: var(--accent-fill)`, `--btn-fill-hover: var(--accent-fill-hi)`); `--text-micro`/`--text-chip` floored at 12px; `--text-table` 13px and `--text-body` 14px unchanged; density tokens `--cell-pad-y`, `--cell-pad-x`, `--panel-pad` (dense `:root`: `var(--space-14)` for `--panel-pad`; comfortable at ≥ 1024px with a fine pointer: `var(--space-20)` and `--text-table` 14px; touch block: `var(--space-14)`).
- `frontend/src/styles.css`: V195-6 rewrote the `body` comment and `.register-instrument`; `.sb-panel { box-shadow: var(--panel-shadow); }` is unchanged (primitives.spec G3 and elevation.spec pin it; the token being `none` is what flattens it).
- `frontend/src/app/ui/layout.ts`: `<section class="panel sb-panel">` (V195-5 removed `sb-lift`); v194 (V194-14b) removed the host `title`, so the header `sb-hint` is the panel's only description.
- `frontend/src/app/ui/button.spec.ts`: V195-5 replaced the glow case in `describe('v168 #5: hover and press', ...)` with `casts no elevation shadow itself, and nothing glows on hover (v195 §1.2)`. `button.ts` itself is untouched since v168: its comments still describe the gradient and the glow; V195-8 rewrites them.
- `frontend/src/app/ui/text-styles.spec.ts`: V195-3 changed the import to `import { allSources, stripComments } from './testing/all-sources';`, retitled the `.sb-label` case to 12px and replaced the last describe with `v195: no literal text size below 12px`.
- `frontend/src/app/ui/format.ts`: v194 (V194-7) added `shareCount` and `riskPct` (`riskPct(value)`: `ABSENT` for null, `'0.00%'` for exact zero, `'<0.01%'` under 0.01, else `grouped(value, 2) + '%'`).

v194 also edited `layout.ts`, `confirm-dialog.ts`, `plan-cell.ts`, `settings-tab.ts` and several specs this part touches: every step below names its edit by symbol or by the exact string, never by line number. Re-read each file before editing it.

---

# Phase 1 — Tokens (signs)

### Task V195-7: True minus in `pct`, `money`, `rMultiple`; `MINUS`; `riskUnits` (money · % of account); sign spec
**Model:** sonnet — two small pure formatters and one new helper, but the sign change ripples into a dozen component specs that must each be traced back to these helpers, not to a local formatter.

**Files:**
- Create: `frontend/src/app/ui/risk-units.ts`
- Create: `frontend/src/app/ui/risk-units.spec.ts`
- Modify: `frontend/src/app/ui/format.ts` (new `MINUS` and private `signOf` after `ABSENT`; `pct`, `money`, `rMultiple`, `signed`)
- Modify: `frontend/src/app/ui/format.spec.ts` (import line; the `money` describe's loss case; one new describe)
- Modify: `frontend/src/app/ui/unit-format.spec.ts` (one new describe)
- Modify: `frontend/src/app/ui/plan-cell.spec.ts` (two expected strings)
- Modify: `frontend/src/app/ui/pnl-cell.spec.ts` (one expected string)
- Modify: `frontend/src/app/workspaces/calendar/calendar.spec.ts` (two `it.each` rows)
- Modify: `frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts` (one expected string)
- Modify: `frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts` (one expected string)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts` (two expected strings)
- Modify: `frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts` (one expected string)
- Modify: `frontend/src/app/workspaces/trades/outcome-tiles.spec.ts` (one expected string)
- Modify: `frontend/src/app/workspaces/trades/plan-card.spec.ts` (one expected string)
- Modify: `frontend/src/app/workspaces/trades/trade-figures.spec.ts` (one expected string)
- Modify: `frontend/src/app/workspaces/trades/why/outcome-path.spec.ts` (one expected string)

**Interfaces:**
- Consumes: `ABSENT`, `num`, `amount`, `grouped` (private), `riskPct` (v194 V194-7, `format.ts`), `inUnit`/`alwaysMoney` (`unit-format.ts`, unchanged: they call `pct`/`money`/`rMultiple` and inherit the sign).
- Produces (V195-25 and V195-27 import these exact names):
  - `export const MINUS = '\u2212';` from `frontend/src/app/ui/format.ts`.
  - `pct(v, d)`, `money(v, unit, d)`, `rMultiple(v)`: `'+'` for a positive value, `MINUS` for a negative one, no sign for zero or `-0`; the magnitude is formatted exactly as before (`toFixed` for `pct` and `rMultiple`, en-US grouping for `money`, unit suffix kept: `'−1,234.50 €'`, correction 5).
  - `signed(v, d)`: unchanged output, now built on the same private `signOf`.
  - `export function riskUnits(pct: number | null | undefined, balance: number | null | undefined, unit: string): string` from `frontend/src/app/ui/risk-units.ts`: `'1,420 $ · 1.42%'` (`amount(|pct| / 100 × balance, unit, 0)` + `' · '` + `riskPct(|pct|)`, one `MINUS` on each part when `pct < 0`); `'— · 1.42%'` when `balance` is null, undefined or not finite; `'—'` when `pct` is null, undefined or not finite.

**Which assertions move, and why only these.** Correction 5 changes three helpers. A spec expectation changes only if its negative figure is produced by `pct`, `money` or `rMultiple` (directly or through `inUnit`, `alwaysMoney`, `PnlCell`, `PlanCell.signedPct`, `candleReadout`, the outcome tiles, `legRsLine`, …). These keep their ASCII hyphen because they do **not** go through the helpers, and are **not** edited here: `cancels.helpers.ts` `rText` (cancels specs), `reports/attribution-tab.ts` `formatR` (attribution and gates specs), `equity-candles.model.ts` `drawdownPart` (`num(loss)%`: the `Max drawdown within range -4.55%` / `-2.00%` expectations in both equity-candles specs), `trade-detail.ts`'s regime line, `trading-performance.ts`'s local `toFixed` (`-0.16R`), histogram bin labels (`toFixed`; `Histogram.isNegative` keys on their ASCII `-`), and the `inline-md`/`figure-text` spec inputs. Those local formatters are reported in the return's OPEN as a follow-up; widening this task to them is scope the ledger does not carry. CSV export is server-side (`/trades/export.csv`), and no frontend code parses a helper's output for its sign (plan-time grep for `startsWith('-')`, `includes('-')` and `/^-/` over non-spec sources: only `trades.store.ts`'s sort parameter and the histogram labels, neither a helper output). `parseFigureText` (`ui/motion/figure-text.ts`) takes any non-digit prefix, so a `StatTile` counting up `'−1.20R'` keeps its true minus (it already does for `signed()` output).

- [ ] **Step 1: Confirm the v194 formatter this task builds on**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" grep -n "export function riskPct" -- frontend/src/app/ui/format.ts
git -C "$WT" grep -n "export const MINUS\|export function riskUnits" -- frontend/src/app/ui
```

Expected: the first prints one line (`riskPct`, from v194); the second prints nothing. If `riskPct` is missing, v194 is not merged: stop and report (the index's Precondition).

- [ ] **Step 2: Write the failing sign spec**

In `$WT/frontend/src/app/ui/format.spec.ts`:

1. Replace the import line with

```ts
import { MINUS, amount, held, money, pct, quantity, rMultiple, signed, timeInZone } from './format';
```

(If v194 added `shareCount`/`riskPct` to this import, keep them in the list.)

2. In `describe('money', ...)`, replace the case `signs a loss with its native minus, not a doubled one` with

```ts
  it('signs a loss with one true minus, not a hyphen and not a doubled sign (v195 correction 5)', () => {
    expect(money(-1234.5, '€')).toBe('−1,234.50 €');
  });
```

3. Append at the end of the file:

```ts
/* v195 §1.1, correction 5: colour is never the only cue. Every P&L, R and
 * return figure carries an explicit sign, and a loss carries U+2212, the
 * same glyph signed() has always used: a hyphen is narrower than a digit
 * even in a mono face, so a column of hyphen-negatives does not align. */
describe('v195: a true minus on every signed figure', () => {
  const HYPHEN = '-';

  it('exports the minus sign once, as U+2212', () => {
    expect(MINUS).toBe('\u2212');
    expect(MINUS).not.toBe(HYPHEN);
  });

  it('signs pct both ways and keeps its decimals', () => {
    expect(pct(1.5)).toBe('+1.50%');
    expect(pct(-1.5)).toBe('−1.50%');
    expect(pct(-12.34, 1)).toBe('−12.3%');
    expect(pct(0)).toBe('0.00%');
    expect(pct(-0)).toBe('0.00%');
    expect(pct(null)).toBe('—');
    expect(pct(undefined)).toBe('—');
  });

  it('signs money both ways, groups the magnitude and keeps the unit suffix', () => {
    expect(money(12345.6, '€')).toBe('+12,345.60 €');
    expect(money(-212, '$', 0)).toBe('−212 $');
    expect(money(-1234567.891, '$')).toBe('−1,234,567.89 $');
    expect(money(0, '€')).toBe('0.00 €');
    expect(money(-0, '€')).toBe('0.00 €');
    expect(money(null, '€')).toBe('—');
  });

  it('signs an R multiple both ways', () => {
    expect(rMultiple(1.84)).toBe('+1.84R');
    expect(rMultiple(-0.3)).toBe('−0.30R');
    expect(rMultiple(0)).toBe('0.00R');
    expect(rMultiple(null)).toBe('—');
  });

  it('prints no hyphen-minus from any signed helper', () => {
    for (const value of [-0.004, -1, -2.5, -1234.567]) {
      for (const text of [pct(value), pct(value, 0), money(value, '$'), money(value, '€', 0), rMultiple(value), signed(value)]) {
        expect(text, `${value} -> ${text}`).not.toContain(HYPHEN);
        expect(text.startsWith(MINUS), `${value} -> ${text}`).toBe(true);
      }
    }
  });

  it('leaves the unsigned level formatter unsigned and zero unsigned', () => {
    expect(amount(1420, '$', 0)).toBe('1,420 $');
    expect(signed(0)).toBe('0.00');
  });
});
```

4. In `$WT/frontend/src/app/ui/unit-format.spec.ts` (one line today), append below the existing `describe`, on new lines:

```ts

describe('unit-format signs (v195 correction 5)', () => {
  const loss = { r: -1.25, pct: -3.4, money: -1240 };

  it('carries the true minus into every headline unit', () => {
    expect(inUnit(loss, 'r', '$')).toBe('−1.25R');
    expect(inUnit(loss, 'pct', '$')).toBe('−3.40%');
    expect(inUnit(loss, 'money', '$')).toBe('−1,240.00 $');
    expect(alwaysMoney(loss, '€')).toBe('−1,240.00 €');
  });
});
```

- [ ] **Step 3: Write the failing `riskUnits` spec**

Create `$WT/frontend/src/app/ui/risk-units.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { ABSENT, MINUS } from './format';
import { riskUnits } from './risk-units';

/* v195 §5.2: open risk and cap headroom show money and % of account side by
 * side, against the dollar-risk cap. Never one unit alone, never an
 * invented figure. */
describe('riskUnits', () => {
  it('renders money and % of account together, money first', () => {
    expect(riskUnits(1.42, 100_000, '$')).toBe('1,420 $ · 1.42%');
    expect(riskUnits(2, 123_456.78, '€')).toBe('2,469 € · 2.00%');
  });

  it('rounds the money to whole units and keeps two decimals on the percentage', () => {
    expect(riskUnits(1.25, 10_000, '$')).toBe('125 $ · 1.25%');
    expect(riskUnits(0.333, 10_000, '$')).toBe('33 $ · 0.33%');
  });

  it('keeps the percentage and marks the money absent when the balance is unknown', () => {
    expect(riskUnits(1.42, null, '$')).toBe(`${ABSENT} · 1.42%`);
    expect(riskUnits(1.42, undefined, '$')).toBe(`${ABSENT} · 1.42%`);
    expect(riskUnits(1.42, Number.NaN, '$')).toBe(`${ABSENT} · 1.42%`);
  });

  it('is absent as a whole when the percentage is unknown', () => {
    expect(riskUnits(null, 100_000, '$')).toBe(ABSENT);
    expect(riskUnits(undefined, 100_000, '$')).toBe(ABSENT);
    expect(riskUnits(Number.POSITIVE_INFINITY, 100_000, '$')).toBe(ABSENT);
  });

  it('renders zero risk as zero in both units, unsigned', () => {
    expect(riskUnits(0, 50_000, '$')).toBe('0 $ · 0.00%');
    expect(riskUnits(-0, 50_000, '$')).toBe('0 $ · 0.00%');
  });

  it("keeps riskPct's floor for a sliver of risk", () => {
    expect(riskUnits(0.004, 100_000, '$')).toBe('4 $ · <0.01%');
  });

  it('puts one true minus on each part of a negative figure (headroom past the cap)', () => {
    expect(riskUnits(-0.5, 100_000, '$')).toBe(`${MINUS}500 $ · ${MINUS}0.50%`);
    expect(riskUnits(-0.5, 100_000, '$')).not.toContain('-');
    expect(riskUnits(-0.5, null, '$')).toBe(`${ABSENT} · ${MINUS}0.50%`);
  });
});
```

- [ ] **Step 4: Run them to make sure they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/format.spec.ts --include src/app/ui/unit-format.spec.ts --include src/app/ui/risk-units.spec.ts
```

Expected: FAIL. `risk-units.spec.ts` cannot resolve `./risk-units`; `format.spec.ts` has no `MINUS` export, and its money-loss case, the pct/money/rMultiple loss cases and the no-hyphen case fail; `unit-format.spec.ts`'s new case fails on the hyphen.

- [ ] **Step 5: Implement the true minus**

In `$WT/frontend/src/app/ui/format.ts`:

1. After `export const ABSENT = '—';` add:

```ts

/** U+2212 MINUS SIGN: the one glyph a loss is signed with (v195 §1.1,
 *  correction 5). Not the hyphen-minus: a hyphen is narrower than a digit
 *  even in a mono face, so a column of hyphen-negatives does not align with
 *  a column of positives, and it reads as a dash at a glance. */
export const MINUS = '\u2212';

/** The sign of a movement: '+' for a gain, MINUS for a loss, nothing for
 *  zero (or -0, which `< 0` does not catch), because zero has none. The
 *  caller formats the magnitude, so no formatter prints its own minus. */
function signOf(value: number): string {
  if (value > 0) return '+';
  return value < 0 ? MINUS : '';
}
```

2. Replace the return line of `pct`

```ts
  return `${value > 0 ? '+' : ''}${value.toFixed(decimals)}%`;
```

with

```ts
  return `${signOf(value)}${Math.abs(value).toFixed(decimals)}%`;
```

3. In `money`, replace

```ts
  // toLocaleString already prints its own minus for a negative value; an
  // explicit sign is only needed for the positive case.
  return `${value > 0 ? '+' : ''}${grouped(value, decimals)} ${unit}`;
```

with

```ts
  // v195 correction 5: the sign is ours (a true minus) and the magnitude is
  // toLocaleString's -- which would otherwise print a hyphen-minus itself.
  return `${signOf(value)}${grouped(Math.abs(value), decimals)} ${unit}`;
```

4. Replace the return line of `rMultiple`

```ts
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}R`;
```

with

```ts
  return `${signOf(value)}${Math.abs(value).toFixed(2)}R`;
```

5. In `signed`, replace the two lines after the finite-number guard

```ts
  if (value === 0) return num(0, decimals);
  return value > 0 ? `+${num(value, decimals)}` : `−${num(Math.abs(value), decimals)}`;
```

with

```ts
  return `${signOf(value)}${num(Math.abs(value), decimals)}`;
```

and in its doc comment change `The minus is U+2212, not a hyphen.` to `The minus is U+2212 (MINUS), not a hyphen; since v195 pct, money and rMultiple use it too.`

6. In the doc comments of `pct` and `money`, append one sentence before the closing `*/`: ` A loss is signed with MINUS (v195 correction 5).`

- [ ] **Step 6: Implement `riskUnits`**

Create `$WT/frontend/src/app/ui/risk-units.ts`:

```ts
import { ABSENT, MINUS, amount, riskPct } from './format';

/**
 * A risk figure in both units at once -- money and % of account, "1,420 $ ·
 * 1.42%" -- for open risk and cap headroom (v195 §5.2). The partner's 2% cap
 * limits money risked, so a %-only tile hides the figure the cap is about
 * and a money-only tile hides how close it is.
 *
 * `pct` is the source figure: the server sends heat as % of the account
 * balance. The money part uses the server's own relation, pct / 100 x
 * balance (`trade_risk_pct`, swingbot/admin/api_v1/risk.py), so it is never
 * a second, drifting computation. No balance: the money part is the em dash
 * and the percentage still shows ("— · 1.42%") -- never an invented figure.
 * No percentage: the whole figure is absent.
 *
 * Both parts are levels, formatted by the unsigned `amount` (whole units)
 * and v194's `riskPct` (two decimals, "<0.01%" for a sliver). A negative
 * value -- headroom past the cap -- carries one true minus on each part.
 */
export function riskUnits(
  pct: number | null | undefined,
  balance: number | null | undefined,
  unit: string,
): string {
  if (!isFiniteNumber(pct)) return ABSENT;
  const sign = pct < 0 ? MINUS : '';
  const magnitude = Math.abs(pct);
  const money = isFiniteNumber(balance)
    ? `${sign}${amount((magnitude / 100) * balance, unit, 0)}`
    : ABSENT;
  return `${money} · ${sign}${riskPct(magnitude)}`;
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}
```

- [ ] **Step 7: Run the new specs to make sure they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/format.spec.ts --include src/app/ui/unit-format.spec.ts --include src/app/ui/risk-units.spec.ts --include src/app/ui/numeric.spec.ts --include src/app/ui/motion/figure-text.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `numeric.spec.ts` stays green: `risk-units.ts` interpolates no raw number and calls no `toLocaleString`.

- [ ] **Step 8: Move the component specs that pin a hyphen from these helpers**

First list every candidate in the worktree (v194 may have added some since the plan was written):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" grep -nE "['\"\`>( ]-[0-9][0-9,]*(\.[0-9]+)?(R|%| ?\\$| [A-Z€£]{1,3})" -- 'frontend/src/**/*.spec.ts'
```

Then run the whole frontend to see which of them the change actually breaks:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
```

Expected failures, each a hyphen that becomes U+2212 in the expected string (old → new; find each by its old string, not by line):

| Spec | Old expected | New expected | Helper |
|---|---|---|---|
| `frontend/src/app/ui/plan-cell.spec.ts` | `'Trail 49.94 → 52.44 (+17.7% / -2.5%)'` | `'Trail 49.94 → 52.44 (+17.7% / −2.5%)'` | `pct` via `signedPct` |
| `frontend/src/app/ui/plan-cell.spec.ts` | `'100.00 → 97.00 / 90.00 (-3.0% - 10.0%)'` | `'100.00 → 97.00 / 90.00 (−3.0% - 10.0%)'` (the ` - ` separator is a template literal and stays) | `pct` via `riseText` |
| `frontend/src/app/ui/pnl-cell.spec.ts` | `'-1.35% (-6.10 €)'` | `'−1.35% (−6.10 €)'` | `pct`, `money` |
| `frontend/src/app/workspaces/calendar/calendar.spec.ts` | `['currency', '-60.00 €', 'neg']`, `['r', '-0.60R', 'neg']` | `['currency', '−60.00 €', 'neg']`, `['r', '−0.60R', 'neg']` | `money`, `rMultiple` |
| `frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts` | `'-1.20R'` | `'−1.20R'` | `rMultiple` |
| `frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts` | `'Held 2d 5h 30m · Shares 10 · MFE +2.40R · MAE -0.30R'` | `'Held 2d 5h 30m · Shares 10 · MFE +2.40R · MAE −0.30R'` | `rMultiple` |
| `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts` | `['-12.50 €', '-0.12% vs prev close']` and `p.text === '-12.50 €'` | `['−12.50 €', '−0.12% vs prev close']` and `p.text === '−12.50 €'` | `money`, `pct` |
| `frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts` | `'-4.00% (-40.00 €)'` | `'−4.00% (−40.00 €)'` | `pct`, `money` |
| `frontend/src/app/workspaces/trades/outcome-tiles.spec.ts` | `'now 105.00 · -3.81% to trigger'` | `'now 105.00 · −3.81% to trigger'` | `pct` |
| `frontend/src/app/workspaces/trades/plan-card.spec.ts` | `'-5.00%'` | `'−5.00%'` | `pct` |
| `frontend/src/app/workspaces/trades/trade-figures.spec.ts` | `'0.00R / -1.00R'` | `'0.00R / −1.00R'` | `rMultiple` via `legRsLine` |
| `frontend/src/app/workspaces/trades/why/outcome-path.spec.ts` | `'-1.00R'` | `'−1.00R'` | `rMultiple` |

Type the new strings with the real character (U+2212; an editor that cannot type it writes `\u2212` inside the string literal). Do **not** touch the `Max drawdown within range -4.55%` / `-2.00%` expectations (`drawdownPart` uses `num`), nor any cancels, attribution, gates, histogram, inline-md or figure-text expectation (local formatters or inputs, see above).

If the whole-frontend run fails on an expectation not in this table: open the component that renders it, and change the expected hyphen to U+2212 **only** if the figure comes from `pct`, `money`, `rMultiple`, `inUnit` or `alwaysMoney`; otherwise the failure is something else and must be diagnosed, not re-signed. Add each extra file to the `git add` below and name it in the commit message body.

- [ ] **Step 9: Run the moved specs, then the whole frontend and lint**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/plan-cell.spec.ts --include src/app/ui/pnl-cell.spec.ts --include src/app/workspaces/calendar/calendar.spec.ts --include src/app/workspaces/calendar/day/calendar-day.spec.ts --include src/app/workspaces/calendar/day/day-trade-card.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts --include src/app/workspaces/dashboard/trade-drawer.spec.ts --include src/app/workspaces/trades/outcome-tiles.spec.ts --include src/app/workspaces/trades/plan-card.spec.ts --include src/app/workspaces/trades/trade-figures.spec.ts --include src/app/workspaces/trades/why/outcome-path.spec.ts
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: PASS, `0 failed`, `0 xfailed`, lint clean.

- [ ] **Step 10: Close**

Close: standard (test: `frontend/src/app/ui/format.spec.ts`), plus `frontend/src/app/ui/risk-units.spec.ts` in step 2 of the close. No browser pass: no layout changes, and the signs are pinned by the specs above. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/ui/format.ts frontend/src/app/ui/format.spec.ts frontend/src/app/ui/unit-format.spec.ts frontend/src/app/ui/risk-units.ts frontend/src/app/ui/risk-units.spec.ts frontend/src/app/ui/plan-cell.spec.ts frontend/src/app/ui/pnl-cell.spec.ts frontend/src/app/workspaces/calendar/calendar.spec.ts frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts frontend/src/app/workspaces/trades/outcome-tiles.spec.ts frontend/src/app/workspaces/trades/plan-card.spec.ts frontend/src/app/workspaces/trades/trade-figures.spec.ts frontend/src/app/workspaces/trades/why/outcome-path.spec.ts
git -C "$WT" commit -m "feat(v195): true minus on every signed figure; riskUnits for money and % of account (V195-7)" -m "Spec 1.1 and correction 5: pct, money and rMultiple sign a loss with U+2212 (exported as MINUS), as signed already did; magnitudes and the money unit suffix are unchanged. Spec 5.2: riskUnits renders a risk figure as money and % of account together, the money from pct / 100 x balance and an em dash for an unknown balance. Component specs that pinned a hyphen from these helpers now pin the true minus; local formatters (cancels rText, attribution formatR, the drawdown readout) are unchanged." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

---

# Phase 2 — Primitives

### Task V195-8: Button variants: `danger` solid (killswitch only), new `danger-quiet`; every existing `danger` call site renamed; `ConfirmDialog.dangerVariant`
**Model:** sonnet — one primitive's variant table, one dialog input and a mechanical rename over nine call sites, guarded by a source-scan spec; the only judgement is keeping the killswitch on the solid variant.

**Files:**
- Modify: `frontend/src/app/ui/button.ts` (whole file rewritten below: `ButtonVariant`, the doc comment, the primary/danger comments and rules, the new `danger-quiet` rules)
- Modify: `frontend/src/app/ui/button.spec.ts` (variant loop; `v80 D4: the button restyle` danger case and two primary case titles; one new describe)
- Modify: `frontend/src/app/ui/confirm-dialog.ts` (`[variant]` binding of the confirm button; `destructive` doc comment; new `dangerVariant` input)
- Modify: `frontend/src/app/ui/controls.spec.ts` (the `defaults the confirm action to the danger variant` case; one new host and describe at the end)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (the `data-action="close-all"` button)
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (the `slot="clear-open"` and `slot="clear-history"` buttons)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (the header action buttons' `[variant]`)
- Modify: `frontend/src/app/workspaces/system/logs-tab.ts` (the `slot="clear"` button)
- Modify: `frontend/src/app/workspaces/system/scan-tab.ts` (the Restart bot button)
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts` (the Discard button: `ghost` becomes `danger-quiet`)
- Modify: `frontend/src/app/workspaces/analytics/tabs/tuning.ts` (the proposal Delete button)
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (the killswitch `sb-confirm-dialog` gains `dangerVariant="danger"`; the killswitch button keeps `'danger'`)
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts` (`buttonVariants`; the buttons help text; the confirm-dialog demo button)
- Modify (not in the ledger row, see Interfaces): `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (one `toContain('danger')`), `frontend/src/app/workspaces/gallery/gallery.spec.ts` (the variant list)

**Interfaces:**
- Consumes: `Button`, `ButtonVariant` (`ui/button.ts`); `ConfirmDialog` and its `destructive` input (`ui/confirm-dialog.ts`); `allSources`, `stripComments` (`ui/testing/all-sources.ts`); `resolveToken` (`ui/testing/resolve-token.ts`); the Graphite `--neg` (`#f06e66`) and `--bg` (`#0d0f12`) from V195-2; `--btn-fill`/`--btn-fill-hover` flat from V195-3.
- Produces (V195-21, V195-24, V195-25, V195-27, V195-29, V195-30 and V195-33 use these exact names):
  - `ButtonVariant` gains `'danger-quiet'` (union order: `'primary' | 'secondary' | 'danger' | 'danger-quiet' | 'ghost' | 'icon' | 'chip' | 'segment' | 'link' | 'danger-icon'`).
  - `.danger` paints `background: var(--neg); border-color: var(--neg); color: var(--bg);` (solid; hover `filter: brightness(1.1)`); `.danger-quiet` paints today's `.danger` (transparent, `--neg` border and text, fills `--neg` with `--bg` ink on hover).
  - `ConfirmDialog.dangerVariant = input<'danger' | 'danger-quiet'>('danger-quiet')`; the confirm button is `destructive() ? dangerVariant() : 'primary'`.
  - The Risk killswitch is the only workspace call site of `'danger'` (and the gallery, the reference page); the spec in Step 1 enforces it.
- Ledger gap: `trade-detail.spec.ts` asserts the Delete button's class `danger` and `gallery.spec.ts` lists every variant; both must move with the rename. No other task edits either file before V195-30 (`trade-detail.spec.ts`) and V195-33 (`gallery.spec.ts`), both later and sequential.

**The rule this task encodes (Phase 2, correction 6).** Today's `danger` already has the quiet look (bordered, fills on hover). Every existing `danger` call site becomes `danger-quiet` with no visual change, and `danger` becomes the new solid fill, used by the killswitch alone, so a halt never looks like housekeeping. Two visual changes are deliberate: the killswitch engage button turns solid, and Settings' Discard (a `ghost` today, behind a confirm) becomes `danger-quiet`, because the spec lists discard settings among the destructive actions. Every `sb-confirm-dialog` without a `dangerVariant` now confirms with `danger-quiet`, which is today's look; the Risk killswitch dialog sets `dangerVariant="danger"`, so engaging and releasing the killswitch both confirm on the solid red. `danger-icon` (the Watchlist row bin) is unchanged.

Solid `danger` ink: `--bg` on `--neg` is about 6.5:1 (`#0d0f12` on `#f06e66`, WCAG relative luminance 0.0049 vs 0.306); the hover's `brightness(1.1)` only lightens the fill, which raises it. Step 1 pins ≥ 4.5 through `resolveToken`.

- [ ] **Step 1: Write the failing button tests**

In `$WT/frontend/src/app/ui/button.spec.ts`:

1. Add two imports after `import { Button, type ButtonVariant } from './button';`:

```ts
import { allSources, stripComments } from './testing/all-sources';
import { resolveToken } from './testing/resolve-token';
```

2. In `describe('Button variants', ...)`, change the loop list to

```ts
  for (const variant of ['primary', 'secondary', 'danger', 'danger-quiet', 'ghost', 'icon',
                         'chip', 'segment', 'link'] as ButtonVariant[]) {
```

and add, after the loop:

```ts
  it('emits exactly one variant class, so danger-quiet is never also danger', () => {
    const el = render('danger-quiet');
    expect([...el.classList]).toEqual(['danger-quiet']);
  });
```

3. In `describe('v80 D4: the button restyle', ...)`: change the describe's leading comment line `/* v167 §3: the fill is the tier-3 gradient. A gradient is an image, so it` / `* must be \`background\`, never \`background-color\` (which would drop it). */` to

```ts
  /* v195 §1.2: the fill is one flat tier-3 colour (--btn-fill), still set
   * through the background shorthand so no gradient can creep back as an
   * image under a background-color. */
```

rename `fills primary with the button gradient and its own ink` to `fills primary with the flat button fill and its own ink`, rename `hovers primary onto the lighter gradient, not a flat color-mix` to `hovers primary onto the lighter fill, not a color-mix` (both bodies unchanged), and replace the case `outlines danger in the loss colour and fills it on hover` with:

```ts
  /* v195 Phase 2, correction 6: two danger variants, so a halt never looks
   * like housekeeping. */
  it('paints danger as one solid loss-colour fill with ground ink (the killswitch)', () => {
    const danger = rule(':host(.danger)');
    expect(danger).toContain('background: var(--neg)');
    expect(danger).toContain('border-color: var(--neg)');
    expect(danger).toContain('color: var(--bg)');
    expect(danger).not.toContain('transparent');
    expect(rule(':host(.danger:not([disabled]):hover)')).toContain('filter: brightness(1.1)');
  });

  it('outlines danger-quiet in the loss colour and fills it on hover (the old danger look)', () => {
    const quiet = rule(':host(.danger-quiet)');
    expect(quiet).toContain('background: transparent');
    expect(quiet).toContain('border-color: var(--neg)');
    expect(quiet).toContain('color: var(--neg)');
    const hover = rule(':host(.danger-quiet:not([disabled]):hover)');
    expect(hover).toContain('background: var(--neg)');
    expect(hover).toContain('color: var(--bg)');
  });

  it('keeps the solid danger ink readable: --bg on --neg clears WCAG AA', () => {
    const lum = (hex: string) => {
      const ch = (i: number) => {
        const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
        return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * ch(0) + 0.7152 * ch(1) + 0.0722 * ch(2);
    };
    const [hi, lo] = [lum(resolveToken('--neg')), lum(resolveToken('--bg'))].sort((a, b) => b - a);
    expect((hi + 0.05) / (lo + 0.05)).toBeGreaterThanOrEqual(4.5);
  });
```

4. Append at the end of the file:

```ts
/* v195 Phase 2, correction 6: the solid danger is the killswitch's alone.
 * Every other destructive control (close all, clear, restart, discard,
 * delete) is danger-quiet. The gallery is the primitive reference and shows
 * every variant, so it is the one other file allowed to name it. */
describe('v195: danger is the killswitch alone', () => {
  const SOLID_DANGER = /variant="danger"|'danger'(?!-)/;
  const ALLOWED = ['app/workspaces/gallery/gallery.ts', 'app/workspaces/risk/risk.ts'];

  it('appears as a button variant only on the Risk killswitch and in the gallery', () => {
    const users = allSources()
      .filter(({ name }) => name.startsWith('app/workspaces/') || name.startsWith('app/shell/'))
      .filter(({ source }) => SOLID_DANGER.test(stripComments(source)))
      .map(({ name }) => name);
    expect(users).toEqual(ALLOWED);
  });

  it('confirms the killswitch on the solid variant', () => {
    const risk = allSources().find(({ name }) => name === 'app/workspaces/risk/risk.ts')!.source;
    expect(risk).toContain('dangerVariant="danger"');
  });
});
```

- [ ] **Step 2: Write the failing dialog tests**

In `$WT/frontend/src/app/ui/controls.spec.ts`:

1. Replace the case `defaults the confirm action to the danger variant` with

```ts
  it('defaults the confirm action to danger-quiet, the housekeeping variant (v195 correction 6)', () => {
    host.confirmOpen.set(true);
    fixture.detectChanges();

    const confirm = [...el().querySelectorAll('sb-confirm-dialog button')].at(-1)!;
    expect(confirm.classList).toContain('danger-quiet');
    expect(confirm.classList).not.toContain('danger');
  });
```

2. Append at the end of the file:

```ts
@Component({
  imports: [ConfirmDialog],
  template: `
    <sb-confirm-dialog
      [open]="true"
      title="Engage the killswitch"
      consequence="No new trade opens until it is released."
      [destructive]="destructive()"
      [dangerVariant]="variant()"
    />
  `,
})
class DangerHost {
  readonly destructive = signal(true);
  readonly variant = signal<'danger' | 'danger-quiet'>('danger');
}

/* v195 Phase 2, correction 6: the killswitch confirms on the solid danger,
 * everything else on danger-quiet; a non-destructive confirm stays primary. */
describe('ConfirmDialog dangerVariant', () => {
  let fixture: ComponentFixture<DangerHost>;

  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(DangerHost);
    fixture.detectChanges();
  });

  const confirm = (): HTMLButtonElement =>
    [...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('sb-confirm-dialog button')].at(-1)!;

  it('paints the confirm action solid danger when the caller asks for it', () => {
    expect(confirm().classList).toContain('danger');
    expect(confirm().classList).not.toContain('danger-quiet');
  });

  it('paints it danger-quiet when asked', () => {
    fixture.componentInstance.variant.set('danger-quiet');
    fixture.detectChanges();
    expect(confirm().classList).toContain('danger-quiet');
  });

  it('stays primary for a non-destructive confirm, whatever the danger variant', () => {
    fixture.componentInstance.destructive.set(false);
    fixture.detectChanges();
    expect(confirm().classList).toContain('primary');
    expect(confirm().className).not.toContain('danger');
  });
});
```

`Component`, `signal`, `ComponentFixture`, `beforeEach`, `installDialogPolyfill` and `provideZonelessChangeDetection` are already imported at the top of the file.

- [ ] **Step 3: Run them to make sure they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/button.spec.ts --include src/app/ui/controls.spec.ts
```

Expected: FAIL. `button.spec.ts`: the `danger-quiet` class cases, the solid-danger and danger-quiet rule cases, and both `danger is the killswitch alone` cases (nine workspace files use the solid variant; no `dangerVariant` on Risk). `controls.spec.ts`: the default case (the class is `danger`) and the whole `ConfirmDialog dangerVariant` describe (the template does not compile: `dangerVariant` is not an input). The contrast case already passes.

- [ ] **Step 4: Rewrite `button.ts`**

Replace the whole of `$WT/frontend/src/app/ui/button.ts` with (only `ButtonVariant`, the doc comment, the primary comments, the `danger` rules and the new `danger-quiet` rules differ from the file as V195-5 left it; every other rule is byte-identical):

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'danger'
  | 'danger-quiet'
  | 'ghost'
  | 'icon'
  | 'chip'
  | 'segment'
  | 'link'
  | 'danger-icon';

/**
 * The button variants spec 3's inventory names, and no others (see
 * `ButtonVariant` above for the current list).
 *
 * Applied to a NATIVE `<button>` through an attribute selector rather than
 * wrapping one in a custom element. A wrapper has to re-implement `disabled`,
 * `type="submit"`, focus, the Enter/Space keys and the accessibility tree, and
 * usually re-implements most of them. This way the element in the DOM is
 * the button the browser already knows how to operate, and this component only
 * supplies the paint.
 *
 * Two danger variants (v195 Phase 2, correction 6), so a halt never looks
 * like housekeeping:
 * - `danger` is the solid loss-colour fill, for the killswitch ALONE -- the
 *   one safety control. button.spec.ts fails if any other workspace uses it.
 * - `danger-quiet` (the look `danger` had until v195: a loss-colour outline
 *   that fills on hover) is every other irreversible action -- close all,
 *   clear, restart, discard, delete.
 * Both pair with `ConfirmDialog` (its `dangerVariant` input), which is what
 * makes those actions hard to trigger by accident. `danger-icon` is a v77
 * addition for destructive icon-only controls, and pairs with `ConfirmDialog`
 * exactly as `danger-quiet` does.
 *
 * v80 D4 restyles every variant through tokens. `segment` and `chip` are
 * deprecated in favour of `sb-segmented`; Migration moves their call sites.
 */
@Component({
  selector: 'button[sb-button]',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<ng-content />`,
  host: {
    '[class]': 'classes()',
    '[attr.aria-busy]': 'loading() || null',
    '[disabled]': 'disabled() || loading() || null',
  },
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: var(--space-6);
      min-height: var(--control-h);
      padding: 0 var(--space-14);
      border: 1px solid transparent;
      border-radius: var(--control-radius);
      font-family: var(--font-sans);
      font-size: var(--text-table);
      font-weight: 600;
      cursor: pointer;
      transition: background var(--transition), border-color var(--transition),
        color var(--transition), filter var(--dur-base) var(--ease-out),
        transform var(--dur-instant) var(--ease-out), box-shadow var(--dur-base) var(--ease-out);
    }
    :host(:focus-visible) { outline: 1px solid var(--accent); outline-offset: 2px; }
    :host([disabled]) { opacity: 0.45; cursor: default; }
    /* Press (v168 §3 #5), every device. On touch, where nothing hovers, the
       press also tints; an inset shadow is a fill, not elevation, so G3
       does not count it. */
    :host(:not([disabled]):active) { transform: scale(.97); }
    @media (hover: none) {
      :host(:not([disabled]):active) { box-shadow: inset 0 0 0 100vmax var(--accent-soft); }
    }

    /* Blue is interactive-only, which is exactly what a primary button is --
       the one place the accent is allowed to carry weight. --accent is the
       text-safe blue and too light to carry white ink, so a filled button
       paints --btn-fill (tier 3: --accent-fill) with --on-accent on top.
       v195 §1.2: the fill is one flat colour, no gradient and no glow; it
       stays in the background shorthand so a gradient can never come back
       underneath a background-color. */
    :host(.primary) { background: var(--btn-fill); color: var(--on-accent); }
    /* Hover swaps to the lighter fill (--accent-fill-hi) and brightens a
       touch; a component never casts its own elevation shadow
       (primitives.spec.ts G3). */
    :host(.primary:not([disabled]):hover) { background: var(--btn-fill-hover); filter: brightness(1.1); }

    /* A hairline on whatever ground it sits on. Panels separate by hairlines
       now (v80 D3), and a raised fill made every secondary look pressed. */
    :host(.secondary) {
      background: transparent;
      border-color: var(--border-strong);
      color: var(--text);
    }
    :host(.secondary:not([disabled]):hover) { border-color: var(--text-muted); background: var(--surface-raised); }

    /* Red here is not P&L -- it is the one sanctioned exception, because an
       irreversible control that does not look dangerous is worse than a
       colour rule kept perfectly.

       v195: the solid fill is the killswitch's alone. --bg ink on --neg
       clears 6:1 (button.spec.ts pins >= 4.5). Hover brightens the fill,
       which only raises the contrast. */
    :host(.danger) {
      background: var(--neg);
      border-color: var(--neg);
      color: var(--bg);
    }
    :host(.danger:not([disabled]):hover) { filter: brightness(1.1); }

    /* Every other irreversible action: the outline danger had until v195.
       Fills on hover (v80 D4): the moment before an irreversible click is
       the one place this control should shout. */
    :host(.danger-quiet) {
      background: transparent;
      border-color: var(--neg);
      color: var(--neg);
    }
    :host(.danger-quiet:not([disabled]):hover) { background: var(--neg); color: var(--bg); }

    :host(.ghost) { min-width: var(--hit-min); background: transparent; color: var(--text-secondary); }
    :host(.ghost:not([disabled]):hover) { color: var(--text); background: var(--surface-raised); }

    :host(.icon) {
      min-height: var(--control-h);
      padding: var(--space-4);
      background: transparent;
      color: var(--text-muted);
      line-height: 1;
    }
    :host(.icon:not([disabled]):hover) { color: var(--text); background: var(--surface-raised); }

    /* A destructive icon control. Not expressible as \`icon\` plus
       \`danger-quiet\`: \`classes\` emits exactly one variant class,
       deliberately. Geometry is \`icon\`'s; the colour is \`danger-quiet\`'s.
       Every call site must supply an aria-label -- the icon inside is
       aria-hidden, so without one the control announces nothing at all. */
    :host(.danger-icon) {
      padding: var(--space-4);
      min-width: 0;
      border-color: transparent;
      background: transparent;
      /* Quiet until reached for. A saturated red bin on all 77 watchlist rows
         was the loudest thing on the page and one tap from a delete; it now
         stays out of the way and turns red only on hover or focus. */
      color: var(--text-faint);
      line-height: 1;
    }
    :host(.danger-icon:not([disabled]):hover),
    :host(.danger-icon:not([disabled]):focus-visible) {
      color: var(--neg);
      background: color-mix(in srgb, var(--neg) 14%, transparent);
    }

    /* Deprecated (v80 D4): a toggle is sb-segmented now. Kept working until
       Migration moves the call sites.

       A filter toggle. Reads as a chip, behaves as a button: versions/ had
       four of these hand-rolled because no variant covered a control that is
       a chip in appearance and a toggle in function. \`.on\` is the pressed
       state and pairs with aria-pressed at the call site. */
    :host(.chip) {
      min-height: var(--control-h);
      min-width: var(--hit-min);
      padding: var(--space-4) var(--space-8);
      border-color: var(--border);
      border-radius: var(--chip-radius);
      background: var(--surface-raised);
      color: var(--text-secondary);
      font-size: var(--text-chip);
      font-weight: 500;
    }
    :host(.chip:not([disabled]):hover) { border-color: var(--border-strong); color: var(--text); }
    :host(.chip.on) {
      border-color: var(--accent);
      background: var(--accent-soft);
      color: var(--text);
    }

    /* Deprecated (v80 D4) with chip above, for the same sb-segmented.

       One cell of a segmented control. The group owns the outer border and
       the radius; a segment owns only its divider, so segments sit flush. */
    :host(.segment) {
      border-color: transparent;
      border-radius: 0;
      background: transparent;
      color: var(--text-secondary);
      font-weight: 500;
    }
    :host(.segment:not([disabled]):hover) { color: var(--text); }
    :host(.segment.current) { background: var(--accent-soft); color: var(--text); }

    /* A button that must look like a link because it sits in running text.
       Still a button: it performs an action rather than navigating, and an
       <a> without an href is not focusable. */
    :host(.link) {
      min-height: var(--control-h);
      min-width: var(--hit-min);
      padding: 0;
      background: transparent;
      color: var(--accent);
      font-size: var(--text-table);
      font-weight: 500;
    }
    :host(.link:not([disabled]):hover) { text-decoration: underline; }

    /* v80 D4 -- a finger needs a square target. The same condition as the
       tokens.css touch block (phone and tablet since v179), where
       --control-h is already 44px. */
    @media (pointer: coarse), (max-width: 1023px) {
      :host(.icon), :host(.danger-icon) { min-width: var(--control-h); min-height: var(--control-h); }
    }
  `,
})
export class Button {
  readonly variant = input<ButtonVariant>('secondary');
  readonly disabled = input(false);
  /** Disables the button and marks it busy, so a slow command cannot be sent
   *  twice by an impatient second click. */
  readonly loading = input(false);

  protected readonly classes = computed(() => this.variant());
}
```

Before saving, diff the rules this block does not change against the worktree's current file (`git -C "$WT" diff --stat` after saving shows only `button.ts`; `git -C "$WT" diff frontend/src/app/ui/button.ts` must show changes only in `ButtonVariant`, the doc comment, the primary comments, the danger/danger-quiet block and the `danger-icon` comment). If V195-5 or v194 left a rule here that differs from the block above (the plan read `button.ts` before either ran), keep the worktree's version of that rule.

- [ ] **Step 5: Give `ConfirmDialog` its danger variant**

In `$WT/frontend/src/app/ui/confirm-dialog.ts`:

1. In the template, replace

```html
              [variant]="destructive() ? 'danger' : 'primary'"
```

with

```html
              [variant]="destructive() ? dangerVariant() : 'primary'"
```

2. Replace the `destructive` doc comment and declaration

```ts
  /** Paints the confirm button `danger`. Default true: everything routed
   *  through this dialog is destructive, and a caller that wants the softer
   *  variant should have to say so. */
  readonly destructive = input(true);
```

with

```ts
  /** Paints the confirm button in `dangerVariant`. Default true: everything
   *  routed through this dialog is destructive, and a caller that wants the
   *  primary variant should have to say so. */
  readonly destructive = input(true);
  /** Which danger paint a destructive confirm takes (v195 Phase 2,
   *  correction 6). `danger-quiet`, the default, is housekeeping: close,
   *  clear, restart, discard, delete. `danger`, the solid fill, is the
   *  killswitch's alone, so a halt never looks like housekeeping. Ignored
   *  when `destructive` is false. */
  readonly dangerVariant = input<'danger' | 'danger-quiet'>('danger-quiet');
```

3. In the class doc comment, change `The gate in front of every destructive action — close, cancel, delete,` / `clear-open, the killswitch.` so it ends `clear-open, the killswitch (the only caller that sets dangerVariant="danger").`

- [ ] **Step 6: Rename every housekeeping call site**

Re-read each file first and edit by the quoted string (v194 changed some of these files):

1. `$WT/frontend/src/app/workspaces/dashboard/dashboard.ts`: in the `close-all-menu` block, `<button sb-button variant="danger" type="button"` (the one followed by `data-action="close-all"`) → `<button sb-button variant="danger-quiet" type="button"`.
2. `$WT/frontend/src/app/workspaces/trades/trades.ts`: in both the `slot="clear-open"` and the `slot="clear-history"` buttons, `variant="danger"` → `variant="danger-quiet"`.
3. `$WT/frontend/src/app/workspaces/trades/trade-detail.ts`: `[variant]="kind === 'delete' ? 'danger' : 'secondary'"` → `[variant]="kind === 'delete' ? 'danger-quiet' : 'secondary'"`.
4. `$WT/frontend/src/app/workspaces/system/logs-tab.ts`: `<button slot="clear" sb-button variant="danger" type="button" (click)="asking.set(true)">` → `<button slot="clear" sb-button variant="danger-quiet" type="button" (click)="asking.set(true)">`.
5. `$WT/frontend/src/app/workspaces/system/scan-tab.ts`: in the Restart bot button (`[loading]="store.restarting()"`), `variant="danger"` → `variant="danger-quiet"`.
6. `$WT/frontend/src/app/workspaces/system/settings-tab.ts`: in the button whose `(click)` is `confirmDiscard.set(true)` (label `Discard`), `variant="ghost"` → `variant="danger-quiet"`.
7. `$WT/frontend/src/app/workspaces/analytics/tabs/tuning.ts`: in the proposal Delete button (`(click)="pendingDelete.set(proposal)"`), `variant="danger"` → `variant="danger-quiet"`.
8. `$WT/frontend/src/app/workspaces/risk/risk.ts`: the killswitch button keeps `[variant]="store.killswitchOn() ? 'secondary' : 'danger'"`. In the `sb-confirm-dialog` whose `[open]` is `asking()` and `(confirmed)` is `confirm()`, add a line after `[working]="store.toggling()"`:

```html
      dangerVariant="danger"
```

and in the comment above `.kill-value.engaged` change `matching the` / `danger button:` to `matching the solid danger button (v195: the killswitch's alone):`.
9. `$WT/frontend/src/app/workspaces/gallery/gallery.ts`:
   - `buttonVariants`: `'primary', 'secondary', 'danger', 'ghost', 'icon', 'danger-icon', 'link', 'chip', 'segment',` → `'primary', 'secondary', 'danger', 'danger-quiet', 'ghost', 'icon', 'danger-icon', 'link', 'chip', 'segment',`.
   - In the buttons panel's `<p class="sb-help">`, after `use sb-segmented.` add: ` <code>danger</code> (solid) is the killswitch's alone; every other destructive control is <code>danger-quiet</code>.`
   - In the `sb-confirm-dialog` demo panel, `<button sb-button variant="danger" type="button" (click)="confirmOpen.set(true)">` → `<button sb-button variant="danger-quiet" type="button" (click)="confirmOpen.set(true)">`.

Then the two specs that pin the old name:

10. `$WT/frontend/src/app/workspaces/trades/trade-detail.spec.ts`: in `offers the %s commands in the header`, `expect(buttons.at(-1)?.classList).toContain('danger');` → `expect(buttons.at(-1)?.classList).toContain('danger-quiet');`.
11. `$WT/frontend/src/app/workspaces/gallery/gallery.spec.ts`: in `shows every button variant, including v77's danger-icon`, the list becomes `['primary', 'secondary', 'danger', 'danger-quiet', 'ghost', 'icon', 'danger-icon', 'link', 'chip', 'segment']`.

Check nothing was missed:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" grep -nE "variant=\"danger\"|'danger'([^-]|$)" -- 'frontend/src/app/workspaces/**/*.ts' 'frontend/src/app/shell/**/*.ts' ':!*.spec.ts'
```

Expected: exactly the Risk killswitch button line and the gallery `buttonVariants` line.

- [ ] **Step 7: Run the tests to make sure they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/button.spec.ts --include src/app/ui/controls.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/system/logs-tab.spec.ts --include src/app/workspaces/system/scan-tab.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/contrast.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `primitives.spec.ts` stays green: the new rules add no hex, no non-inset shadow and no radius literal. `contrast.spec.ts` stays green: its `--text-faint` scan does not cover `button.ts`'s `danger-icon` rule (unchanged).

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 8: Check the look at three widths**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard` and click through to the `/ui` gallery and to Risk. At 1440, 768 and 390: in the gallery's Buttons panel `danger` is a solid red fill with dark ink and `danger-quiet` is a red outline that fills on hover (hover at 1440 only); on Risk the Engage killswitch button is solid red, and its confirm dialog's confirm button is solid red too; on the Dashboard the Close all open/partial trigger is still the red outline. Save the PNGs under the session scratchpad.

- [ ] **Step 9: Close**

Close: standard (test: `frontend/src/app/ui/button.spec.ts`), plus `frontend/src/app/ui/controls.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/ui/button.ts frontend/src/app/ui/button.spec.ts frontend/src/app/ui/confirm-dialog.ts frontend/src/app/ui/controls.spec.ts frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts frontend/src/app/workspaces/system/logs-tab.ts frontend/src/app/workspaces/system/scan-tab.ts frontend/src/app/workspaces/system/settings-tab.ts frontend/src/app/workspaces/analytics/tabs/tuning.ts frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/gallery/gallery.ts frontend/src/app/workspaces/gallery/gallery.spec.ts
git -C "$WT" commit -m "feat(v195): solid danger for the killswitch alone, danger-quiet for housekeeping (V195-8)" -m "Phase 2 and correction 6: every existing danger call site (close all, clear open/history, delete, clear log, restart bot, delete proposal, the gallery demo) becomes danger-quiet with no visual change, Settings' Discard moves from ghost to danger-quiet, and danger becomes a solid --neg fill with --bg ink used only by the Risk killswitch. ConfirmDialog.dangerVariant (default danger-quiet) picks the confirm paint; the killswitch dialog sets danger. button.spec fails if any other workspace uses the solid variant." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-9: Panel, panel header and section head re-skinned: surface + hairline, 13px semibold sentence-case title, hint beside it, quiet meta right, `[header-actions]` slot
**Model:** sonnet — three small primitives re-skinned and one projection slot added, with their pinning specs moved; the care is in keeping every existing baseline and touch-hint pin green while the meta moves right.

**Files:**
- Modify: `frontend/src/app/ui/layout.ts` (`Panel` only: its `h2`, `header`, `.body`, `.panel-digest` and `.panel-problem` rules and its doc comment)
- Modify: `frontend/src/app/ui/layout.spec.ts` (`PANEL_TITLE`; the two `.body` padding pins; two new cases)
- Modify: `frontend/src/app/ui/panel-header.ts` (whole file rewritten below)
- Modify: `frontend/src/app/ui/panel-header.spec.ts` (the `TITLE` list and one title case; the `keeps N=, total and the hint inside the heading line` case; one new describe)
- Modify: `frontend/src/app/ui/section-head.ts` (`h1`, `h2` and `.status` rules; the status span's class)
- Modify: `frontend/src/app/ui/section-head.spec.ts` (one new describe)
- Modify: `frontend/src/styles.css` (new `.sb-meta` after `.sb-help`; one paragraph appended to the `.sb-panel` comment)
- Modify: `frontend/src/app/ui/text-styles.spec.ts` (two new describes)

**Interfaces:**
- Consumes: `Panel`, `PanelHeader`, `SectionHead`, `Hint` (unchanged API); `--panel-pad` (V195-6: dense `var(--space-14)`, comfortable `var(--space-20)` at ≥ 1024px with a fine pointer, touch `var(--space-14)`); `--text-table` (13px; 14px in comfortable); `--text-title` (20px), `--text-subhead` (16px), `--text-micro` (12px after V195-3), `--text-muted`; `readFileSync`/`join`, `stripComments` already imported in `text-styles.spec.ts` (V195-3).
- Produces (V195-21, V195-26 and V195-32 rely on these):
  - `sb-panel-header` projection slot `[header-actions]`, rendered inside the right-hand `.meta` group after N=, all-time, the total and the Table toggle.
  - `sb-panel-header` DOM: `header > .heading (h2, sb-hint?)` + `header > .meta.sb-meta (.n?, .all-time?, .total?, button.table?, [header-actions])`.
  - Global class `.sb-meta` (`styles.css`): `color: var(--text-muted); font-size: var(--text-micro); font-variant-numeric: tabular-nums;`, the one quiet-meta style.
  - Panel and panel-header titles: `font-family: var(--font-sans); font-weight: 600; font-size: var(--text-table); color: var(--text); letter-spacing: normal;`, no `text-transform`.
  - `sb-panel` body, header, digest and problem rows pad horizontally with `var(--panel-pad)`.
  - `sb-section-head`: `h1` at `--text-title`, `h2` at `--text-subhead`, both `var(--font-sans)`, 600, `letter-spacing: normal`; `<span class="status sb-meta">`.

**What changes, and what is already there.** `sb-panel` already paints `--panel-bg` (the surface step since V195-3) with a 1px `--panel-border` and no lift (V195-5), and its hint already sits right after the `h2` (v194 made it the panel's only description). This task moves the title to the 13px table step (spec §1.3: "table 13", Phase 2: "13px semibold"), pads the panel with the density token so comfortable gets 20px, and pins the hint's place. `sb-panel-header` today keeps N=, all-time and the total inside the heading line next to the title; Phase 2 puts the quiet meta on the right, so they move into a right-aligned `.meta` group beside a new `[header-actions]` slot, and the hint moves directly after the title. `sb-section-head` keeps its 20px `h1` (Phase 4's page title is 20px) and its 16px `h2` (a section above several panels sits a step above the 13px panel title; only the gallery uses level 2); it gains the UI face and `letter-spacing: normal` explicitly, and its status slot takes the shared `.sb-meta`. `.sb-panel`'s `box-shadow: var(--panel-shadow)` stays in `styles.css` (primitives.spec G3 and elevation.spec pin it; the token is `none`); only its comment moves. The header's minimum height (`calc(var(--control-h) + 2 * var(--space-10) + 1px)`) and its baseline alignment are unchanged (v179 §3.3/§3.4).

- [ ] **Step 1: Write the failing panel tests**

In `$WT/frontend/src/app/ui/layout.spec.ts`:

1. In `PANEL_TITLE`, change `'font-size: var(--text-body);',` to `'font-size: var(--text-table);',`, and change the comment above it to `/** v186 D1, v195 Phase 2: the one panel title, 13px -- the same list is pinned in panel-header.spec.ts. */`.
2. In `sets the title in the UI face, 600, at body size, as the text was given`, rename it `sets the title in the UI face, 600, at the 13px table step, as the text was given` and add as its last line `expect(h2).not.toContain('--text-body');`.
3. In `keeps one gap between the header and the first row of the body` and in `keeps the full body padding on a panel with no heading`, change `toContain('padding: var(--space-14)')` to `toContain('padding: var(--panel-pad)')`.
4. In `describe('sb-panel header: one height, one baseline (v179 §3.3, §3.4)', ...)`, add after `wraps long headings within the padded header`:

```ts
  /* v195 §1.4: the panel's padding follows row density (14px dense, 20px
   * comfortable on a desktop fine pointer), header and body alike, so the
   * title stays aligned with the content under it. */
  it('pads the header, body, digest and problem rows with the density token', () => {
    expect(ruleIn(PANEL, 'header')).toContain('padding: var(--space-10) var(--panel-pad)');
    expect(ruleIn(PANEL, '.body')).toContain('padding: var(--panel-pad)');
    expect(ruleIn(PANEL, '.panel-digest')).toContain('padding: var(--space-10) var(--panel-pad)');
    expect(ruleIn(PANEL, '.panel-problem')).toContain('padding: var(--space-10) var(--panel-pad)');
    expect(PANEL).not.toContain('var(--space-14)');
  });

  it('puts the hint right beside the title, before the actions (v195 Phase 2)', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const f = TestBed.createComponent(Panel);
    f.componentRef.setInput('heading', 'Exposure');
    f.componentRef.setInput('description', 'What is at risk, by ticker.');
    f.detectChanges();
    const header = (f.nativeElement as HTMLElement).querySelector('header')!;
    expect([...header.children].map((child) => child.tagName.toLowerCase())).toEqual(['h2', 'sb-hint', 'div']);
  });
```

- [ ] **Step 2: Write the failing panel-header tests**

In `$WT/frontend/src/app/ui/panel-header.spec.ts`:

1. Add `Component` to the `@angular/core` import: `import { Component, provideZonelessChangeDetection } from '@angular/core';`.
2. Replace the case `keeps N=, total and the hint inside the heading line` with:

```ts
  /* v195 Phase 2: the hint sits right beside the title; the quiet meta
   * (N=, all-time, total) and the Table toggle sit together on the right. */
  it('keeps the hint beside the title and the meta on the right', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(PanelHeader);
    fixture.componentRef.setInput('title', 'Equity');
    fixture.componentRef.setInput('n', 972);
    fixture.componentRef.setInput('total', '−2,150.95 €');
    fixture.componentRef.setInput('hint', 'Pre-tax, paper trades.');
    fixture.componentRef.setInput('tableable', true);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const heading = el.querySelector('.heading')!;
    expect([...heading.children].map((child) => child.tagName.toLowerCase())).toEqual(['h2', 'sb-hint']);
    const meta = el.querySelector('header > .meta')!;
    for (const selector of ['.n', '.total', 'button.table']) {
      expect(meta.querySelector(selector), selector).not.toBeNull();
      expect(heading.querySelector(selector), selector).toBeNull();
    }
    expect(meta.classList).toContain('sb-meta');
  });
```

3. In `describe('PanelHeader: the one panel title (v186 D1)', ...)`: change `TITLE`'s `'font-size: var(--text-body);',` to `'font-size: var(--text-table);',`; rename `sets the title exactly like sb-panel: UI face, 600, body size, no transform` to `sets the title exactly like sb-panel: UI face, 600, the 13px table step, no transform`, and add to it `expect(h2).not.toContain('--text-body');`.
4. Append at the end of the file:

```ts
@Component({
  imports: [PanelHeader],
  template: `
    <sb-panel-header [title]="'Equity'" [n]="12">
      <button header-actions type="button">Export</button>
    </sb-panel-header>
  `,
})
class ActionsHost {}

describe('PanelHeader header-actions slot (v195 Phase 2)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/panel-header.ts'), 'utf8');
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('projects [header-actions] into the right-hand meta group, after the meta', () => {
    const fixture = TestBed.createComponent(ActionsHost);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const action = el.querySelector('button[header-actions]')!;
    expect(action.closest('.meta')).not.toBeNull();
    expect(action.closest('.heading')).toBeNull();
    const n = el.querySelector('.meta .n')!;
    expect(n.compareDocumentPosition(action) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('right-aligns the meta group on the shared baseline and hides it when empty', () => {
    const meta = SOURCE.match(/[\s`]\.meta \{[^}]*\}/)?.[0] ?? '';
    expect(meta).toContain('justify-content: flex-end');
    expect(meta).toContain('margin-left: auto');
    expect(meta).toContain('align-items: baseline');
    expect(SOURCE).toMatch(/\.meta:empty \{\s*display: none;\s*\}/);
  });

  it('renders no meta group content and no hint for a bare title', () => {
    const fixture = TestBed.createComponent(PanelHeader);
    fixture.componentRef.setInput('title', 'Calibration');
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-hint')).toBeNull();
    expect(el.querySelector('.meta')!.children.length).toBe(0);
  });
});
```

- [ ] **Step 3: Write the failing section-head and text-style tests**

1. Append to `$WT/frontend/src/app/ui/section-head.spec.ts`:

```ts
/* v195 Phase 2 / §1.3: headings are sentence case in the UI face; the
 * status slot is quiet meta, the same style as a panel header's. */
describe('SectionHead re-skin (v195)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/section-head.ts'), 'utf8');
  const ruleOf = (pattern: RegExp) => SOURCE.match(pattern)?.[0] ?? '';
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('sets both heading levels in the UI face at 600, sentence case as given', () => {
    const h1 = ruleOf(/\sh1 \{[^}]*\}/);
    const h2 = ruleOf(/\sh2 \{[^}]*\}/);
    for (const heading of [h1, h2]) {
      expect(heading).toContain('font-family: var(--font-sans)');
      expect(heading).toContain('font-weight: 600');
      expect(heading).toContain('letter-spacing: normal');
      expect(heading).not.toContain('text-transform');
    }
    expect(h1).toContain('font-size: var(--text-title)');
    expect(h2).toContain('font-size: var(--text-subhead)');
  });

  it('renders the status slot as quiet meta, styled once globally', () => {
    const f = TestBed.createComponent(SlotHost);
    f.detectChanges();
    const status = (f.nativeElement as HTMLElement).querySelector('.status')!;
    expect(status.classList).toContain('sb-meta');
    const rule = ruleOf(/\.status \{[^}]*\}/);
    expect(rule).not.toContain('color:');
    expect(rule).not.toContain('font-size:');
  });
});
```

2. Append to `$WT/frontend/src/app/ui/text-styles.spec.ts`:

```ts
describe('v195 Phase 2: the one quiet-meta style', () => {
  it('.sb-meta is muted micro text with tabular figures, never the faint rule colour', () => {
    const r = rule('sb-meta');
    expect(r).toContain('color: var(--text-muted)');
    expect(r).toContain('font-size: var(--text-micro)');
    expect(r).toContain('font-variant-numeric: tabular-nums');
    expect(r).not.toContain('--text-faint');
  });
});

describe('v195 Phase 2: one panel title, sentence case', () => {
  const read = (path: string) => stripComments(readFileSync(join(process.cwd(), path), 'utf8'));
  const titles = (source: string) => [...source.matchAll(/[\s`]h[12]\s*\{[^}]*\}/g)].map(([m]) => m);
  const TITLE = [
    'font-family: var(--font-sans);',
    'font-weight: 600;',
    'font-size: var(--text-table);',
    'color: var(--text);',
    'letter-spacing: normal;',
  ];

  it('sets sb-panel and sb-panel-header titles identically, at the 13px table step', () => {
    const panel = titles(read('src/app/ui/layout.ts'))[0];
    const header = titles(read('src/app/ui/panel-header.ts'))[0];
    for (const declaration of TITLE) {
      expect(panel, `layout.ts ${declaration}`).toContain(declaration);
      expect(header, `panel-header.ts ${declaration}`).toContain(declaration);
    }
  });

  it('uppercases no title in the panel, panel-header or section-head primitive', () => {
    for (const path of ['src/app/ui/layout.ts', 'src/app/ui/panel-header.ts', 'src/app/ui/section-head.ts']) {
      const found = titles(read(path));
      expect(found.length, path).toBeGreaterThan(0);
      for (const title of found) expect(title, path).not.toContain('text-transform');
    }
  });
});
```

- [ ] **Step 4: Run them to make sure they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/layout.spec.ts --include src/app/ui/panel-header.spec.ts --include src/app/ui/section-head.spec.ts --include src/app/ui/text-styles.spec.ts
```

Expected: FAIL. `layout.spec.ts`: the title case, both `.body` padding cases and the density padding case (`puts the hint right beside the title` already passes: it pins today's order). `panel-header.spec.ts`: the title case, `keeps the hint beside the title and the meta on the right`, and the three `header-actions` cases. `section-head.spec.ts`: both cases. `text-styles.spec.ts`: `.sb-meta` and `sets sb-panel and sb-panel-header titles identically` (the uppercase case already passes).

- [ ] **Step 5: Re-skin `sb-panel`**

Re-read `$WT/frontend/src/app/ui/layout.ts` (v194 and V195-5 edited the `Panel` block) and edit the `Panel` component's styles by rule:

1. `header`: `padding: var(--space-10) var(--space-14);` → `padding: var(--space-10) var(--panel-pad);`.
2. The comment above `h2` (`/* v186 D1 -- the one panel title, the same declarations as` …) becomes:

```css
    /* v186 D1 -- the one panel title, the same declarations as
       sb-panel-header's h2: sentence case as given, Inter 600. v195 Phase 2:
       at the 13px table step (spec §1.3), a step under the 14px body so the
       figures in the panel, not its label, carry the weight.
       .sb-label (mono caps) is the FIELD and tile label style, not a title. */
```

and in the `h2` rule `font-size: var(--text-body);` → `font-size: var(--text-table);`.
3. `.body { padding: var(--space-14); }` → `.body { padding: var(--panel-pad); }`, and the comment above `.body.tight` stays.
4. `.panel-digest` and `.panel-problem`: `padding: var(--space-10) var(--space-14);` → `padding: var(--space-10) var(--panel-pad);` in both.
5. In the `Panel` class doc comment (`A titled box. ...`), append a paragraph before its closing `*/`:

```ts
 *
 * v195 Phase 2: a surface step and a 1px hairline (--panel-bg, --panel-border),
 * no lift and no shadow; a 13px sentence-case title with its hint right
 * beside it; padding from --panel-pad, so the panel follows row density.
```

Check no `--space-14` is left in the `Panel` block (the `expect(PANEL).not.toContain('var(--space-14)')` case reads only the `sb-panel` component's slice of the file; `TabBar` and `Drawer` keep their own spacing).

- [ ] **Step 6: Rewrite `sb-panel-header`**

Replace the whole of `$WT/frontend/src/app/ui/panel-header.ts` with:

```ts
import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

import { Hint } from './hint';

/** Consistent panel provenance: title, population, scope, definition, and table view.
 *
 * v179 §3.4: title, N=, total and the hint share the text baseline; the
 * header is one control tall. v186 D1: the title matches sb-panel's.
 * v195 Phase 2: the title (13px, 600, sentence case as given) has its `?`
 * hint right beside it on the left; the quiet meta (N=, all-time, the
 * total), the Table toggle and the `[header-actions]` slot sit together on
 * the right, styled by the global `.sb-meta`. */
@Component({
  selector: 'sb-panel-header',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint],
  template: `
    <header>
      <div class="heading">
        <h2>{{ title() }}</h2>
        @if (hint()) { <sb-hint [text]="hint()!" [label]="title() + ' definition'" /> }
      </div>
      <div class="meta sb-meta">
        @if (n() !== null) { <span class="n num">N={{ n() }}</span> }
        @if (allTime()) { <span class="all-time">all-time</span> }
        @if (total()) { <span class="total">{{ total() }}</span> }
        @if (tableable()) { <button type="button" class="table sb-hit" [attr.aria-pressed]="tableOpen()" (click)="tableOpen.set(!tableOpen())">Table</button> }
        <ng-content select="[header-actions]" />
      </div>
    </header>
  `,
  styles: `
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      align-content: center;
      justify-content: space-between;
      gap: var(--space-6) var(--space-8);
      min-height: var(--control-h);
    }
    .heading { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--space-6); min-width: 0; }
    h2 { margin: 0; font-family: var(--font-sans); font-weight: 600; font-size: var(--text-table); color: var(--text); letter-spacing: normal; overflow-wrap: anywhere; }
    .meta { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: flex-end; gap: var(--space-6) var(--space-10); margin-left: auto; }
    .meta:empty { display: none; }
    .n,.all-time { font-family: var(--font-num); font-size:var(--text-micro); letter-spacing:.06em; text-transform:uppercase; color: var(--text-muted); }
    .all-time { color:var(--warn); }
    .total { font-family: var(--font-figure); font-weight: var(--figure-weight); letter-spacing: var(--figure-tracking); font-variant-numeric: tabular-nums; font-size: var(--text-chip); color: var(--text-secondary); }
    .table { border:0; padding:0; background:none; color:var(--accent); cursor:pointer; font:inherit; font-size:var(--text-chip); }
    .table:focus-visible { outline:1px solid var(--accent); outline-offset:2px; }
    @media (pointer: coarse), (max-width: 1023px) {
      sb-hint { margin-block: calc((14px - var(--control-h)) / 2); }
    }
  `,
})
export class PanelHeader {
  readonly title = input.required<string>();
  readonly n = input<number | null>(null);
  readonly allTime = input(false);
  readonly hint = input<string | null>(null);
  readonly tableable = input(false);
  readonly total = input<string | null>(null);
  readonly tableOpen = model(false);
}
```

The selectors `.n,.all-time`, `.all-time { color:var(--warn); }` and the touch `@media` block keep the exact spelling the existing specs match. A header with no meta renders no element in `.meta` (the `renders no meta group content` case pins that); `:empty` then hides the group, and should a whitespace text node survive compilation the empty group still has no width of its own, only the header's gap.

- [ ] **Step 7: Re-skin `sb-section-head` and add `.sb-meta`**

1. In `$WT/frontend/src/app/ui/section-head.ts`:
   - Template: `<span class="status"><ng-content select="[status]" /></span>` → `<span class="status sb-meta"><ng-content select="[status]" /></span>`.
   - Replace the three rules

```css
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; overflow-wrap: anywhere; }
    h2 { margin: 0; font-size: var(--text-subhead); font-weight: 600; overflow-wrap: anywhere; }
    .status { display: inline-flex; align-items: baseline; gap: var(--space-8); color: var(--text-secondary); font-size: var(--text-chip); }
```

with

```css
    /* v195 §1.3: sentence case as given, in the UI face. Level 1 is the
       20px title step (sb-page's title takes it in Phase 4); level 2 marks
       a section above several panels, so it sits a step above their 13px
       titles. */
    h1 { margin: 0; font-family: var(--font-sans); font-size: var(--text-title); font-weight: 600; letter-spacing: normal; overflow-wrap: anywhere; }
    h2 { margin: 0; font-family: var(--font-sans); font-size: var(--text-subhead); font-weight: 600; letter-spacing: normal; overflow-wrap: anywhere; }
    /* Colour and size come from the global .sb-meta (styles.css). */
    .status { display: inline-flex; align-items: baseline; gap: var(--space-8); }
```

2. In `$WT/frontend/src/styles.css`, directly after the `.sb-help { ... }` rule, add:

```css

/* v195 Phase 2 -- the one quiet-meta style: the count, as-of or total that
 * sits beside a title (sb-panel-header's meta group, sb-section-head's
 * status slot). Muted, never --text-faint: that is a rule colour, not text
 * (correction 13). A child may set its own face or size (a panel total
 * keeps its figure face); this is the quiet default under it. */
.sb-meta {
  color: var(--text-muted);
  font-size: var(--text-micro);
  font-variant-numeric: tabular-nums;
}
```

3. In the comment above `.sb-panel { box-shadow: var(--panel-shadow); }`, replace its last line `* first, so an element carrying both classes reads as the overlay. */` with

```css
 * first, so an element carrying both classes reads as the overlay.
 *
 * v195 §1.2: --panel-shadow is `none`, so an in-flow panel is flat: a
 * surface step and sb-panel's own 1px hairline. The rule stays so G3 still
 * sees exactly one panel cast and one overlay shadow. */
```

- [ ] **Step 8: Run the tests to make sure they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/layout.spec.ts --include src/app/ui/panel-header.spec.ts --include src/app/ui/section-head.spec.ts --include src/app/ui/text-styles.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/workspaces/analytics/tabs/variance-band-panel.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `elevation.spec.ts` still finds the `.panel` rule (`background: var(--panel-bg);`, `border: var(--panel-border);`, `border-radius: var(--panel-radius);`) and `styles.css`'s two casts; `contrast.spec.ts`'s v186 scan finds no `color: var(--text-faint)` in `layout.ts` or `panel-header.ts`; `variance-band-panel.spec.ts` still finds `sb-panel-header h2` and no focusable element.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. A failure in a workspace spec that read panel-header meta inside `.heading` is a missed pin: move its selector to `.meta`, never back.

- [ ] **Step 9: Check the look at three widths**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`, then click to Analytics (Overview: `sb-panel-header` with N= and a Table toggle) and to the `/ui` gallery (both section-head levels). At 1440: panel titles are 13px (`getComputedStyle(h2).fontSize`), the hint glyph sits right after each title, N= and Table sit at the right edge of the header, and a panel body's padding is 14px; then `localStorage.setItem('ui.density', 'comfortable')`, reload through `/app/dashboard`, click back: the body padding is 20px and title and first row stay aligned. At 768 and 390: the meta group wraps under the title on a narrow panel without overflowing, the hint keeps its 44px target, and the body padding is 14px. Save the PNGs under the session scratchpad.

- [ ] **Step 10: Close**

Close: standard (test: `frontend/src/app/ui/panel-header.spec.ts`), plus `frontend/src/app/ui/layout.spec.ts`, `frontend/src/app/ui/section-head.spec.ts` and `frontend/src/app/ui/text-styles.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/ui/layout.ts frontend/src/app/ui/layout.spec.ts frontend/src/app/ui/panel-header.ts frontend/src/app/ui/panel-header.spec.ts frontend/src/app/ui/section-head.ts frontend/src/app/ui/section-head.spec.ts frontend/src/styles.css frontend/src/app/ui/text-styles.spec.ts
git -C "$WT" commit -m "feat(v195): flat panel, 13px titles, quiet meta right and a header-actions slot (V195-9)" -m "Phase 2: sb-panel and sb-panel-header titles move to the 13px table step, sentence case, with the hint right beside the title; sb-panel-header's N=, all-time, total and Table toggle move into a right-aligned meta group with a new [header-actions] slot; panel padding follows --panel-pad (row density). sb-section-head headings take the UI face explicitly and its status slot uses the new global .sb-meta quiet-meta style." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```
