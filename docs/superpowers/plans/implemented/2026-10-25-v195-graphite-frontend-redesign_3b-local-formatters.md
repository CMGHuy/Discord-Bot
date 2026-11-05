# v195 — Graphite, Part 3b: local R and drawdown formatters take the true minus

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below.

**Scope of this part (V195-7b):** spec §1.1 ("every P&L, R and return figure carries an explicit sign … with a true minus sign"). V195-7 moved `pct`, `money` and `rMultiple` to U+2212 (correction 5); five local formatters bypass them and would still print a hyphen. This part routes them through `MINUS` or `rMultiple`. It runs after V195-7 (it imports `MINUS`) and before V195-8; it shares no file with V195-8 or V195-9.

**Where commands run.** `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`.

---

# Phase 1 — Tokens (signs, continued)

### Task V195-7b: The five local R/percent formatters sign a loss with the true minus
**Model:** sonnet — five one-line formatter changes, each routed through `MINUS` or a shared helper, with their pinning specs moved; the care is keeping each formatter's zero and positive output byte-identical.

**Files:**
- Modify: `frontend/src/app/workspaces/cancels/cancels.helpers.ts` (`rText`), `frontend/src/app/workspaces/cancels/cancels.helpers.spec.ts`, `frontend/src/app/workspaces/cancels/cancels-summary.spec.ts`, `frontend/src/app/workspaces/cancels/cancels-table.spec.ts`
- Modify: `frontend/src/app/workspaces/reports/attribution-tab.ts` (`formatR`), `frontend/src/app/workspaces/reports/attribution-tab.spec.ts`, `frontend/src/app/workspaces/reports/gates-tab.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts` (`drawdownPart`), `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`, `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (the regime line: `${expectancyR >= 0 ? '+' : ''}`), `frontend/src/app/workspaces/trades/trade-detail.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` (`fmtFigure`), `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`

**Interfaces:**
- Consumes: `MINUS`, `rMultiple`, `num` (`ui/format.ts`, V195-7).
- Produces: nothing new. `rText` and `formatR` keep their names and signatures (callers in `cancels-summary.ts`, `cancels-table.ts`, `gates-tab.ts` unchanged). V195-26 (`trading-performance.ts`), V195-30 (`trade-detail.ts`) and V195-31 (cancels) edit these files later: they start from this task's state, and this task edits by the quoted symbol string, never by line number.

**Rules kept.** `rText`/`formatR` already equal `rMultiple` for every non-null value (`+1.85R`, `0.00R`), so they delegate to it. `drawdownPart` keeps `num` (its Intl rounding matches the money/high/low readout at halfway values) and only swaps the sign glyph. The regime line keeps `+0.00R` for zero. `fmtFigure` formats signed and unsigned figures alike (win rate, ExpR, payoff); it keeps printing no `+` (unchanged positives) and signs a negative with `MINUS`.

- [ ] **Step 1: Move the specs to the true minus**

Find each by its old string (v194 may have moved lines); type U+2212 (or `\u2212` inside the literal):

| Spec | Old | New |
|---|---|---|
| `cancels.helpers.spec.ts` | `expect(rText(-3.4)).toBe('-3.40R');` | `expect(rText(-3.4)).toBe('−3.40R');` |
| `cancels-summary.spec.ts` | `'-3.40R'`, `'R avoided +23.00R · R missed -26.40R'`, `'Wrong cancels 14 -26.40R missed'`, `'Setup reached TP1 12 -22.20R missed'` | the same with `−` |
| `cancels-table.spec.ts` | `'-1.00R'` | `'−1.00R'` |
| `attribution-tab.spec.ts` | `['+0.22R', '-0.05R', '0.00R', '—']`, `'-0.05R [-0.30R, +0.20R]'` | `['+0.22R', '−0.05R', '0.00R', '—']`, `'−0.05R [−0.30R, +0.20R]'` |
| `gates-tab.spec.ts` | `not.toContain('-0.30R')`, `toContain('-0.08R')` | `not.toContain('−0.30R')`, `toContain('−0.08R')` (the `not` case must name the glyph the code now prints, or it passes vacuously) |
| `equity-candles.model.spec.ts` | `'Max drawdown within range -4.55%'`, `` `${RANGE_LABELS.drawdown} -2.00%` `` | `'Max drawdown within range −4.55%'`, `` `${RANGE_LABELS.drawdown} −2.00%` `` |
| `equity-candles.spec.ts` | `'Max drawdown within range -4.55%'` | `'Max drawdown within range −4.55%'` |
| `trade-detail.spec.ts` | `toContain('-0.38R')` (COHORT_POOR regime text) | `toContain('−0.38R')` |
| `trading-performance.spec.ts` | `expect(text).toContain('-0.16R');` | `expect(text).toContain('−0.16R');` |

Then add the guard cases. Append to `cancels.helpers.spec.ts`:

```ts
describe('rText signs (v195 §1.1)', () => {
  it('matches rMultiple: true minus on a loss, + on a gain, unsigned zero, dash for none', () => {
    expect([rText(-0.3), rText(1.85), rText(0), rText(null)]).toEqual(['−0.30R', '+1.85R', '0.00R', '—']);
  });
});
```

Append to `attribution-tab.spec.ts` (add `formatInterval` to its `./attribution-tab` import if absent):

```ts
describe('formatR signs (v195 §1.1)', () => {
  it('prints no hyphen-minus, alone or in an interval', () => {
    expect(formatR(-1)).toBe('−1.00R');
    expect(formatInterval(-0.3, -0.1)).toBe('[−0.30R, −0.10R]');
    expect(formatInterval(-0.3, -0.1)).not.toContain('-');
  });
});
```

- [ ] **Step 2: Run them to make sure they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/cancels --include src/app/workspaces/reports/attribution-tab.spec.ts --include src/app/workspaces/reports/gates-tab.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts
```

Expected: FAIL on every moved string and both new describes, except the `gates-tab` `not.toContain` case, which passes before and after.

- [ ] **Step 3: Route the five formatters through the true minus**

1. `cancels.helpers.ts`: add `import { rMultiple } from '../../ui/format';` and replace `rText`'s doc and body with

```ts
/** Signed R to two places: `+1.85R`, `−3.40R`, `0.00R`; a dash for none.
 *  v195 §1.1: one implementation, the shared `rMultiple`. */
export function rText(r: number | null): string {
  return rMultiple(r);
}
```

2. `attribution-tab.ts`: add `import { rMultiple } from '../../ui/format';` and replace `formatR`'s body (`if (value === null) return '—';` and the template line) with `return rMultiple(value);`; append ` v195 §1.1: the shared rMultiple, true minus.` to its doc comment.
3. `equity-candles.model.ts`: add `MINUS` to the `../../../ui/format` import; in `drawdownPart` replace

```ts
  return { text: `${RANGE_LABELS.drawdown} ${num(loss)}%`, tone: drawdownTone(pctValue) };
```

with

```ts
  // v195 §1.1: a true minus; the magnitude keeps num's Intl rounding.
  return { text: `${RANGE_LABELS.drawdown} ${loss < 0 ? MINUS : ''}${num(Math.abs(loss))}%`, tone: drawdownTone(pctValue) };
```

4. `trade-detail.ts`: add `import { MINUS } from '../../ui/format';` (or add `MINUS` to an existing `ui/format` import) and in the regime line replace `` `${expectancyR >= 0 ? '+' : ''}${expectancyR.toFixed(2)}R (n=${n}, frozen ${runDate})` `` with `` `${expectancyR >= 0 ? '+' : MINUS}${Math.abs(expectancyR).toFixed(2)}R (n=${n}, frozen ${runDate})` ``.
5. `trading-performance.ts`: change the import to `import { MINUS, amount, pct } from '../../../ui/format';` and replace `fmtFigure`'s return with

```ts
    if (value === null) return '—';
    // v195 §1.1: a negative ExpR carries a true minus; positives unchanged.
    return `${value < 0 ? MINUS : ''}${Math.abs(value).toFixed(decimals)}${unit}`;
```

Check none remain: `git -C "$WT" grep -nE "\? '\+' : ''\}" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts'` prints nothing in these five files.

- [ ] **Step 4: Run them to make sure they pass, then the whole frontend and lint**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/cancels --include src/app/workspaces/reports --include src/app/workspaces/dashboard/panels --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/ui/numeric.spec.ts
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: PASS, `0 failed`, `0 xfailed`. Any other failure that pins a hyphen from one of these five is moved the same way and named in the commit body.

- [ ] **Step 5: Close**

Close: standard (test: `frontend/src/app/workspaces/cancels/cancels.helpers.spec.ts`), plus `frontend/src/app/workspaces/reports/attribution-tab.spec.ts` in step 2 of the close. One frontend commit naming the 14 files above: `fix(v195): local R and drawdown formatters sign a loss with the true minus (V195-7b)`, body: "Spec 1.1: rText and formatR delegate to rMultiple; the drawdown readout, the trade-detail regime line and the trading-performance figures swap the hyphen for MINUS, positives and zero unchanged.", ending with the `Co-Authored-By:` trailer.

