# v240 — Doctena night, plan 1 of 5: Theme and type — Part 3: the type sweeps

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V240-14" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) (§2 tabular figures, §1 corrected `--text-faint`, §11 gates)
**Index:** [2026-11-23-v240-doctena-night-theme-and-type_0-index.md](2026-11-23-v240-doctena-night-theme-and-type_0-index.md) — Goal, Global Constraints, Decisions 3 and 4, Parallelisation and the task ledger live there.

This part empties the two pending sets V240-9 created in
`frontend/src/app/ui/type-gates.spec.ts`, one area per task, and V240-16
deletes the pending machinery. Every task is the same shape:

1. **Red:** delete the area's entries from `TABULAR_PENDING` and
   `FAINT_PENDING`. The gate's "passes" test now runs on those files and
   fails, naming each offending selector.
2. **Faint fix (mechanical, scripted):** in every listed file, every
   `color: var(--text-faint)` (the `color` property exactly; never
   `border-color`, `background` or `fill`) becomes
   `color: var(--text-muted)` (index Decision 3). The script asserts the
   per-file count, which equals the gate's rule count at `146b4600`, so a
   drifted file stops the run instead of being half-fixed.
3. **Tabular fix (by hand, listed rule by rule):** every rule that reads
   `--font-num`/`--font-mono` or styles a `.num` cell gains
   `font-variant-numeric: tabular-nums;` (index Decision 4: no
   exemptions; tickers and labels are unaffected because it only changes
   digits). Multi-line rules get it on its own line directly below the
   `font-family` line, same indentation; one-line rules get it before the
   closing `}` in the rule's own spacing style.
4. **Pins:** the few specs that pin an old rule verbatim move with it.
5. **Green:** the gate plus the touched files' specs.

Line numbers are at `146b4600`; earlier tasks (V240-2, -7, -8, -11) shift
some of them. Find each rule by its selector, never by line number alone.
If the gate names a selector these lists do not, the code moved after
`146b4600`: fix that rule the same way, and say so in the commit message.
Never widen a gate predicate or re-add a pending entry to get green.

# Phase 6: The type sweeps

### Task V240-13: Sweep 1: `app/ui/`, `app/shell/`, `styles.css`

**Model:** sonnet — 27 files of shared primitives and shell chrome, three spec pins that move with them, and edits in files V240-8 and V240-11 already changed; a wrong rule here shows on every page.

**Files:**
- Modify (faint): `frontend/src/app/shell/breadcrumb.ts`, `frontend/src/app/ui/age-hint.ts`, `frontend/src/app/ui/bar-list.ts`, `frontend/src/app/ui/button.ts`, `frontend/src/app/ui/column-picker.ts`, `frontend/src/app/ui/direction-arrow.ts`, `frontend/src/app/ui/freshness.ts`, `frontend/src/app/ui/market-value.ts`, `frontend/src/app/ui/matrix.ts`, `frontend/src/app/ui/metric-chip.ts`, `frontend/src/app/ui/plan-cell.ts`, `frontend/src/app/ui/pnl-basis.ts`, `frontend/src/app/ui/share-bar.ts`, `frontend/src/app/ui/status-cell.ts`
- Modify (tabular): `frontend/src/app/shell/login/login.css`, `frontend/src/app/shell/shell.css`, `frontend/src/app/ui/async.ts`, `frontend/src/app/ui/chip.ts`, `frontend/src/app/ui/confidence-cell.ts`, `frontend/src/app/ui/data-table/data-table.ts`, `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/panel-header.ts`, `frontend/src/app/ui/plan-cell.ts`, `frontend/src/app/ui/pnl-cell.ts`, `frontend/src/app/ui/stat-tile.ts`, `frontend/src/app/ui/status-cell.ts`, `frontend/src/styles.css`
- Modify (pins): `frontend/src/app/shell/breadcrumb.spec.ts`, `frontend/src/app/ui/svg-colour.spec.ts`, `frontend/src/app/ui/stat-tile.spec.ts`
- Modify: `frontend/src/app/ui/type-gates.spec.ts`

**Interfaces:**
- Consumes: `TABULAR_PENDING`, `FAINT_PENDING` in `frontend/src/app/ui/type-gates.spec.ts` (V240-9). `button.ts` after V240-8 (uppercase `:host`, resets on the icon variants); `metric-chip.ts` and `plan-cell.ts` after V240-11 (`fixed()`, `formatR`). Neither earlier task touches a rule this task edits.
- Produces: both pending sets hold no `app/ui/`, `app/shell/` or `styles.css` entry.

Why: these are the shared primitives and the shell, so the two rules land
on every page at once. `--text-faint` stays a divider colour (index
Decision 3); every caption, hint, separator glyph and quiet icon here moves
to `--text-muted`. That includes the matrix's missing-cell dash, which
`svg-colour.spec.ts` allowed until now, and the breadcrumb separators,
which `breadcrumb.spec.ts` pinned to faint. Black's captions get lighter
too, which is the spec's intent.

- [ ] **Step 1: Remove this area's pending entries (red)**

In `frontend/src/app/ui/type-gates.spec.ts`, delete these 13 lines from
`TABULAR_PENDING`:

```ts
  'app/shell/login/login.css',
  'app/shell/shell.css',
  'app/ui/async.ts',
  'app/ui/chip.ts',
  'app/ui/confidence-cell.ts',
  'app/ui/data-table/data-table.ts',
  'app/ui/hint.ts',
  'app/ui/panel-header.ts',
  'app/ui/plan-cell.ts',
  'app/ui/pnl-cell.ts',
  'app/ui/stat-tile.ts',
  'app/ui/status-cell.ts',
  'styles.css',
```

and these 14 lines from `FAINT_PENDING`:

```ts
  'app/shell/breadcrumb.ts',
  'app/ui/age-hint.ts',
  'app/ui/bar-list.ts',
  'app/ui/button.ts',
  'app/ui/column-picker.ts',
  'app/ui/direction-arrow.ts',
  'app/ui/freshness.ts',
  'app/ui/market-value.ts',
  'app/ui/matrix.ts',
  'app/ui/metric-chip.ts',
  'app/ui/plan-cell.ts',
  'app/ui/pnl-basis.ts',
  'app/ui/share-bar.ts',
  'app/ui/status-cell.ts',
```

After the edit `TABULAR_PENDING` starts at
`'app/workspaces/analytics/tabs/tuning.ts'` and `FAINT_PENDING` at
`'app/workspaces/analytics/tabs/benchmark.ts'`.

- [ ] **Step 2: Run the gate to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/type-gates.spec.ts`
Expected: FAIL — 27 tests: 13 `… sets tabular-nums on every --font-num,
--font-mono and .num rule` and 14 `… paints no text in --text-faint`, each
listing the selectors below.

- [ ] **Step 3: Move the faint text to `--text-muted` (script)**

Run from the repo root. It reads and writes bytes, so line endings are
kept:

```bash
python - <<'EOF'
import re
from pathlib import Path

FAINT = re.compile(r'(?<![-\w])color(\s*):(\s*)var\(--text-faint\)')
# file -> faint text rules at 146b4600 (= type-gates' offender count)
FILES = {
    'app/shell/breadcrumb.ts': 1,     # .sep
    'app/ui/age-hint.ts': 1,          # .age-hint
    'app/ui/bar-list.ts': 2,          # .n; li.withheld .label,li.withheld .value
    'app/ui/button.ts': 1,            # :host(.danger-icon)
    'app/ui/column-picker.ts': 1,     # label.locked
    'app/ui/direction-arrow.ts': 1,   # .absent
    'app/ui/freshness.ts': 1,         # .freshness
    'app/ui/market-value.ts': 1,      # .mv-meta
    'app/ui/matrix.ts': 1,            # .missing
    'app/ui/metric-chip.ts': 1,       # .absent
    'app/ui/plan-cell.ts': 3,         # .entry.pending; .trail; .sep
    'app/ui/pnl-basis.ts': 1,         # .pnl-basis
    'app/ui/share-bar.ts': 1,         # .none
    'app/ui/status-cell.ts': 1,       # .hint
}
for name, expected in FILES.items():
    path = Path('frontend/src') / name
    text = path.read_bytes().decode('utf-8')
    new, n = FAINT.subn(r'color\1:\2var(--text-muted)', text)
    assert n == expected, f'{name}: {n} faint colour reads, expected {expected}'
    path.write_bytes(new.encode('utf-8'))
    print(f'{name}: {n}')
EOF
```

Expected: 14 lines printed, no `AssertionError`. An assertion names a file
whose count moved since `146b4600`. Open it, check that each
`color: var(--text-faint)` is a text colour inside a style rule, fix the
count in the dict, and re-run (files already rewritten report 0 then, so
drop them from the dict first).

The comment above `:host(.danger-icon)` in `button.ts` ("Quiet until
reached for …") still holds: muted is quiet, and the hover/focus rule
below it still turns the icon `--neg`.

- [ ] **Step 4: Add `tabular-nums` to the numeric rules**

Multi-line rules: add `font-variant-numeric: tabular-nums;` on its own
line directly below the `font-family` line shown, same indentation.

| File | Rule (line at `146b4600`) | Below this line |
|---|---|---|
| `app/shell/login/login.css` | `.mark {` (20) | `  font-family: var(--font-mono);` |
| `app/shell/shell.css` | `.brand .word {` (154) | `  font-family: var(--font-mono);` |
| `app/ui/async.ts` | `.stale-badge {` (215) | `      font-family: var(--font-mono);` |
| `app/ui/chip.ts` | `.chip {` (96) | `      font-family: var(--font-mono);` |
| `app/ui/confidence-cell.ts` | `.conf {` (52) | `      font-family: var(--font-mono);` |
| `app/ui/hint.ts` | `.glyph {` (177) | `      font-family: var(--font-mono);` |
| `app/ui/plan-cell.ts` | `.plan {` (69) | `      font-family: var(--font-mono);` |
| `styles.css` | `.sb-label {` (118) | `  font-family: var(--font-mono);` |

One-line rules: replace the whole rule with the line below, keeping the
file's own leading indentation (the 4-space blocks are `styles:`
literals).

`app/shell/shell.css` (186):

```css
.palette-trigger .shortcut { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-micro); color: var(--text-muted); }
```

`app/ui/data-table/data-table.ts` (378, 383, 448, 528, 539; each replaces
the rule with the same selector):

```css
    td.num { white-space: nowrap; font-variant-numeric: tabular-nums; }
    .num.sort, th.num .sort { justify-content: flex-end; font-variant-numeric: tabular-nums; }
    .detail-value { min-width: 0; text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .compact-cell.num ~ .compact-cell.num { margin-left: 0; font-variant-numeric: tabular-nums; }
    .compact-total .num { font-family: var(--font-num); font-variant-numeric: tabular-nums; font-weight: 600; color: var(--text); }
```

`app/ui/panel-header.ts` (53):

```css
.n,.all-time { font-family: var(--font-num); font-variant-numeric: tabular-nums; font-size:var(--text-micro); letter-spacing:.06em; text-transform:uppercase; color: var(--text-muted); }
```

`app/ui/pnl-cell.ts` (39):

```css
    .pnl { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-table); white-space: nowrap; }
```

`app/ui/stat-tile.ts` (134):

```css
    .sample, .secondary { font-family: var(--font-num); font-variant-numeric: tabular-nums; }
```

`app/ui/status-cell.ts` (180, 183):

```css
    .end { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-chip); }
    .pct { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-table); color: var(--text-secondary); }
```

- [ ] **Step 5: Move the three pins**

`frontend/src/app/shell/breadcrumb.spec.ts`: replace the test
`'draws the separators in the rule colour and the text in the muted one
(correction 13)'` (line 158) with:

```ts
  it('draws the separators and the crumbs in the muted colour (v240: --text-faint is never text)', () => {
    expect(SOURCE).toMatch(/\.sep \{[^}]*color: var\(--text-muted\)/);
    expect(SOURCE).toMatch(/li \{[^}]*color: var\(--text-muted\)/);
    expect(SOURCE).not.toContain('--text-faint');
  });
```

`frontend/src/app/ui/svg-colour.spec.ts`: replace the `FAINT_ALLOWED`
declaration and its comment (lines 25-30) with:

```ts
/**
 * Selectors allowed to keep --text-faint, each with its reason. Empty since
 * v240: the matrix's missing-cell dash moved to --text-muted with every
 * other faint text (type-gates.spec.ts). Add an entry only with a reason.
 */
const FAINT_ALLOWED: Partial<Record<(typeof SVG_PRIMITIVES)[number], string[]>> = {};
```

`frontend/src/app/ui/stat-tile.spec.ts` line 132: replace with

```ts
    expect(SOURCE).toMatch(/\.sample, \.secondary \{ font-family: var\(--font-num\); font-variant-numeric: tabular-nums; \}/);
```

- [ ] **Step 6: Run the gate and the touched files' specs**

Run:

```bash
cd frontend && npx ng test --watch=false \
  --include src/app/ui/type-gates.spec.ts --include src/app/ui/svg-colour.spec.ts \
  --include src/app/ui/contrast.spec.ts --include src/app/ui/text-styles.spec.ts \
  --include src/app/shell/breadcrumb.spec.ts --include src/app/shell/shell.spec.ts \
  --include src/app/ui/age-hint.spec.ts --include src/app/ui/bar-list.spec.ts \
  --include src/app/ui/button.spec.ts --include src/app/ui/column-picker.spec.ts \
  --include src/app/ui/direction-arrow.spec.ts --include src/app/ui/freshness.spec.ts \
  --include src/app/ui/market-value.spec.ts --include src/app/ui/matrix.spec.ts \
  --include src/app/ui/metric-chip.spec.ts --include src/app/ui/plan-cell.spec.ts \
  --include src/app/ui/pnl-basis.spec.ts --include src/app/ui/share-bar.spec.ts \
  --include src/app/ui/status-cell.spec.ts --include src/app/ui/async.spec.ts \
  --include src/app/ui/chip.spec.ts --include src/app/ui/confidence-cell.spec.ts \
  --include src/app/ui/data-table/data-table.spec.ts --include src/app/ui/hint.spec.ts \
  --include src/app/ui/panel-header.spec.ts --include src/app/ui/pnl-cell.spec.ts \
  --include src/app/ui/stat-tile.spec.ts
```

Expected: PASS. A 60s `Timeout waiting for worker` is machine load: re-run
once. A remaining type-gates failure names a selector Step 4 missed (or one
added after `146b4600`): fix it the same way.

- [ ] **Step 7: Prove the faint gate still bites in this area**

Temporarily change `frontend/src/app/ui/freshness.ts`'s `.freshness`
`color: var(--text-muted)` back to `color: var(--text-faint)` and run
`cd frontend && npx ng test --watch=false --include src/app/ui/type-gates.spec.ts`.
Expected: FAIL — `app/ui/freshness.ts paints no text in --text-faint`.
Undo that one word by hand (a `git checkout` of the file would also undo
the sweep) and re-run: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/ui/type-gates.spec.ts \
  frontend/src/app/shell/breadcrumb.ts frontend/src/app/ui/age-hint.ts frontend/src/app/ui/bar-list.ts \
  frontend/src/app/ui/button.ts frontend/src/app/ui/column-picker.ts frontend/src/app/ui/direction-arrow.ts \
  frontend/src/app/ui/freshness.ts frontend/src/app/ui/market-value.ts frontend/src/app/ui/matrix.ts \
  frontend/src/app/ui/metric-chip.ts frontend/src/app/ui/plan-cell.ts frontend/src/app/ui/pnl-basis.ts \
  frontend/src/app/ui/share-bar.ts frontend/src/app/ui/status-cell.ts \
  frontend/src/app/shell/login/login.css frontend/src/app/shell/shell.css frontend/src/app/ui/async.ts \
  frontend/src/app/ui/chip.ts frontend/src/app/ui/confidence-cell.ts frontend/src/app/ui/data-table/data-table.ts \
  frontend/src/app/ui/hint.ts frontend/src/app/ui/panel-header.ts frontend/src/app/ui/pnl-cell.ts \
  frontend/src/app/ui/stat-tile.ts frontend/src/styles.css \
  frontend/src/app/shell/breadcrumb.spec.ts frontend/src/app/ui/svg-colour.spec.ts frontend/src/app/ui/stat-tile.spec.ts
git commit -m "style(v240): sweep 1 -- ui/, shell/ and styles.css: tabular-nums on numeric rules, captions and glyphs off --text-faint

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V240-14: Sweep 2: analytics, reports, research, cancels, guide, gallery

**Model:** haiku — a scripted colour swap with a count check plus eight one-declaration additions listed verbatim; no logic, no spec pin moves.

**Files:**
- Modify (faint): `frontend/src/app/workspaces/analytics/tabs/benchmark.ts`, `frontend/src/app/workspaces/analytics/tabs/execution.ts`, `frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.ts`, `frontend/src/app/workspaces/analytics/tabs/partials.ts`, `frontend/src/app/workspaces/analytics/tabs/pipeline.ts`, `frontend/src/app/workspaces/analytics/tabs/runner-endings.ts`, `frontend/src/app/workspaces/analytics/tabs/variance-band-panel.ts`, `frontend/src/app/workspaces/cancels/cancels-summary.ts`, `frontend/src/app/workspaces/guide/guide.ts`, `frontend/src/app/workspaces/reports/attribution-tab.ts`, `frontend/src/app/workspaces/reports/gates-tab.ts`, `frontend/src/app/workspaces/reports/reports.ts`, `frontend/src/app/workspaces/research/research.ts`
- Modify (tabular): `frontend/src/app/workspaces/analytics/tabs/tuning.ts`, `frontend/src/app/workspaces/cancels/cancels-summary.ts`, `frontend/src/app/workspaces/gallery/gallery.ts`, `frontend/src/app/workspaces/guide/guide.ts`, `frontend/src/app/workspaces/reports/gates-tab.ts`, `frontend/src/app/workspaces/research/research.ts`
- Modify: `frontend/src/app/ui/type-gates.spec.ts`

**Interfaces:**
- Consumes: `TABULAR_PENDING`, `FAINT_PENDING` in `frontend/src/app/ui/type-gates.spec.ts` after V240-13 (no `app/ui/`, `app/shell/` or `styles.css` entry left). `gallery.ts` after V240-8 (its `h1` gained `letter-spacing: -0.02em`; this task edits a different rule).
- Produces: both pending sets hold no `analytics/`, `reports/`, `research/`, `cancels/`, `guide/` or `gallery/` entry.

Why: the analytics and reports pages carry most of the small print (as-of
stamps, captions, footnotes, `dt` labels, "thin sample" marks). It moves to
`--text-muted` so it reads at 4.5:1 on every surface in both themes, and
the numeric columns of the tuning diff, cancels summary and gallery demo
align under Jost's proportional digits. Specs touched: none pin these
rules (checked at `146b4600`; `vertical-centre.spec.ts` reads the gallery
`.num` rule with `toMatch(/white-space:\s*nowrap/)`, which still holds).

- [ ] **Step 1: Remove this area's pending entries (red)**

In `frontend/src/app/ui/type-gates.spec.ts`, delete these 6 lines from
`TABULAR_PENDING`:

```ts
  'app/workspaces/analytics/tabs/tuning.ts',
  'app/workspaces/cancels/cancels-summary.ts',
  'app/workspaces/gallery/gallery.ts',
  'app/workspaces/guide/guide.ts',
  'app/workspaces/reports/gates-tab.ts',
  'app/workspaces/research/research.ts',
```

and these 14 lines from `FAINT_PENDING`:

```ts
  'app/workspaces/analytics/tabs/benchmark.ts',
  'app/workspaces/analytics/tabs/execution.ts',
  'app/workspaces/analytics/tabs/override-fidelity-panel.ts',
  'app/workspaces/analytics/tabs/overview.ts',
  'app/workspaces/analytics/tabs/partials.ts',
  'app/workspaces/analytics/tabs/pipeline.ts',
  'app/workspaces/analytics/tabs/runner-endings.ts',
  'app/workspaces/analytics/tabs/variance-band-panel.ts',
  'app/workspaces/cancels/cancels-summary.ts',
  'app/workspaces/guide/guide.ts',
  'app/workspaces/reports/attribution-tab.ts',
  'app/workspaces/reports/gates-tab.ts',
  'app/workspaces/reports/reports.ts',
  'app/workspaces/research/research.ts',
```

- [ ] **Step 2: Run the gate to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/type-gates.spec.ts`
Expected: FAIL — 20 tests: 6 `… sets tabular-nums on every --font-num,
--font-mono and .num rule` and 14 `… paints no text in --text-faint`.

- [ ] **Step 3: Move the faint text to `--text-muted` (script)**

Run from the repo root. It reads and writes bytes, so line endings are
kept:

```bash
python - <<'EOF'
import re
from pathlib import Path

FAINT = re.compile(r'(?<![-\w])color(\s*):(\s*)var\(--text-faint\)')
W = 'app/workspaces/'
# file -> faint text rules at 146b4600 (= type-gates' offender count)
FILES = {
    W + 'analytics/tabs/benchmark.ts': 4,       # .sub, .caption, .clamp, .stamp; .group-note; .strip-line, .exposure-caption, .markers; .footnote p
    W + 'analytics/tabs/execution.ts': 2,       # dt; small
    W + 'analytics/tabs/override-fidelity-panel.ts': 3,  # dt; small; .excluded,.excluded td
    W + 'analytics/tabs/overview.ts': 2,        # .as-of; .pairs dt
    W + 'analytics/tabs/partials.ts': 2,        # .breakdown tr.thin td; .footer
    W + 'analytics/tabs/pipeline.ts': 1,        # dt
    W + 'analytics/tabs/runner-endings.ts': 7,  # .card.thin .card-share; .thin-mark; .scorecard small,.scorecard .of; .scorecard tr.thin td; .legend small; .legend .none; .note
    W + 'analytics/tabs/variance-band-panel.ts': 1,  # .caption
    W + 'cancels/cancels-summary.ts': 1,        # .caption, .note, .as-of, .tp1-note, .pair-label, .survival, .ties, .manual, .split-empty
    W + 'guide/guide.ts': 1,                    # sb-guide .md .permalink
    W + 'reports/attribution-tab.ts': 1,        # .aside, .caption, .footer
    W + 'reports/gates-tab.ts': 1,              # .aside, .caption, .footer
    W + 'reports/reports.ts': 1,                # .disclaimer
    W + 'research/research.ts': 3,              # .caption, .disclaimer; .aside; .record.missing
}
for name, expected in FILES.items():
    path = Path('frontend/src') / name
    text = path.read_bytes().decode('utf-8')
    new, n = FAINT.subn(r'color\1:\2var(--text-muted)', text)
    assert n == expected, f'{name}: {n} faint colour reads, expected {expected}'
    path.write_bytes(new.encode('utf-8'))
    print(f'{name}: {n}')
EOF
```

Expected: 14 lines printed, 30 reads in all, no `AssertionError`. An
assertion names a file whose count moved since `146b4600`. Open it, check
that each `color: var(--text-faint)` is a text colour inside a style rule,
fix the count in the dict, drop the files already rewritten (they report
0 now) and re-run.

`research.ts`'s `.record.missing` keeps its `text-decoration:
line-through`: the strike-through, not the colour, says "missing".

- [ ] **Step 4: Add `tabular-nums` to the numeric rules**

Multi-line rule: in `app/workspaces/analytics/tabs/tuning.ts`, the
`.log {` rule (line 289), add `      font-variant-numeric: tabular-nums;`
directly below `      font-family: var(--font-mono);` (line 298).

One-line rules: replace each rule with the line below, keeping the file's
own leading indentation.

`app/workspaces/analytics/tabs/tuning.ts` (270, 332):

```css
    code { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .diff .num { text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

`app/workspaces/cancels/cancels-summary.ts` (160):

```css
    .num { font-family: var(--font-num); font-variant-numeric: tabular-nums; }
```

`app/workspaces/gallery/gallery.ts` (989):

```css
    .numerics-demo th.num, .numerics-demo td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
```

`app/workspaces/guide/guide.ts` (139):

```css
    sb-guide .md pre { max-width: 100%; overflow-x: auto; padding: var(--space-8); background: var(--bg); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

`app/workspaces/reports/gates-tab.ts` (128):

```css
    .word { font-family: var(--font-mono); font-variant-numeric: tabular-nums; color: var(--text-muted); letter-spacing: 0.08em; }
```

`app/workspaces/research/research.ts` (206):

```css
    .record { font-family: var(--font-mono); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
```

- [ ] **Step 5: Run the gate and the touched files' specs**

Run:

```bash
cd frontend && npx ng test --watch=false \
  --include src/app/ui/type-gates.spec.ts --include src/app/ui/vertical-centre.spec.ts \
  --include src/app/workspaces/analytics/tabs/benchmark.spec.ts \
  --include src/app/workspaces/analytics/tabs/execution.spec.ts \
  --include src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts \
  --include src/app/workspaces/analytics/tabs/overview.spec.ts \
  --include src/app/workspaces/analytics/tabs/partials.spec.ts \
  --include src/app/workspaces/analytics/tabs/pipeline.spec.ts \
  --include src/app/workspaces/analytics/tabs/runner-endings.spec.ts \
  --include src/app/workspaces/analytics/tabs/variance-band-panel.spec.ts \
  --include src/app/workspaces/analytics/tabs/tuning.spec.ts \
  --include src/app/workspaces/cancels/cancels-summary.spec.ts \
  --include src/app/workspaces/guide/guide.spec.ts \
  --include src/app/workspaces/gallery/gallery.spec.ts \
  --include src/app/workspaces/reports/attribution-tab.spec.ts \
  --include src/app/workspaces/reports/gates-tab.spec.ts \
  --include src/app/workspaces/reports/reports.spec.ts \
  --include src/app/workspaces/research/research.spec.ts
```

Expected: PASS. A 60s `Timeout waiting for worker` is machine load: re-run
once. A remaining type-gates failure names a selector Steps 3 and 4 missed
(or one added after `146b4600`): fix it the same way.

- [ ] **Step 6: Prove the tabular gate still bites in this area**

Temporarily delete the `font-variant-numeric: tabular-nums;` you added to
`research.ts`'s `.record` rule and run
`cd frontend && npx ng test --watch=false --include src/app/ui/type-gates.spec.ts`.
Expected: FAIL — `app/workspaces/research/research.ts sets tabular-nums on
every --font-num, --font-mono and .num rule`. Put the declaration back by
hand and re-run: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/type-gates.spec.ts \
  frontend/src/app/workspaces/analytics/tabs/benchmark.ts frontend/src/app/workspaces/analytics/tabs/execution.ts \
  frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts frontend/src/app/workspaces/analytics/tabs/overview.ts \
  frontend/src/app/workspaces/analytics/tabs/partials.ts frontend/src/app/workspaces/analytics/tabs/pipeline.ts \
  frontend/src/app/workspaces/analytics/tabs/runner-endings.ts frontend/src/app/workspaces/analytics/tabs/variance-band-panel.ts \
  frontend/src/app/workspaces/analytics/tabs/tuning.ts frontend/src/app/workspaces/cancels/cancels-summary.ts \
  frontend/src/app/workspaces/guide/guide.ts frontend/src/app/workspaces/gallery/gallery.ts \
  frontend/src/app/workspaces/reports/attribution-tab.ts frontend/src/app/workspaces/reports/gates-tab.ts \
  frontend/src/app/workspaces/reports/reports.ts frontend/src/app/workspaces/research/research.ts
git commit -m "style(v240): sweep 2 -- analytics, reports, research, cancels, guide, gallery: tabular-nums on numeric rules, small print off --text-faint

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V240-15: Sweep 3: dashboard, calendar, trades, plans, risk

**Model:** haiku — a scripted colour swap with a count check plus 22 one-declaration additions listed verbatim; no logic, no spec pin moves.

**Files:**
- Modify (faint): `frontend/src/app/workspaces/calendar/calendar.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`, `frontend/src/app/workspaces/dashboard/panels/exposure-by-horizon.ts`, `frontend/src/app/workspaces/dashboard/panels/market-movers.ts`, `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`, `frontend/src/app/workspaces/dashboard/panels/watchlist-panel.ts`, `frontend/src/app/workspaces/plans/plan-detail.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/trades/trade-detail.ts`, `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/trades/why/outcome-path.ts`
- Modify (tabular): `frontend/src/app/workspaces/calendar/calendar.ts`, `frontend/src/app/workspaces/calendar/day/calendar-day.ts`, `frontend/src/app/workspaces/calendar/day/day-trade-card.ts`, `frontend/src/app/workspaces/calendar/day/trade-sparkline.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/dashboard/panels/market-movers.ts`, `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`, `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`, `frontend/src/app/workspaces/dashboard/panels/watchlist-panel.ts`, `frontend/src/app/workspaces/plans/plan-detail.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/trades/trade-detail.ts`, `frontend/src/app/workspaces/trades/trades.ts`
- Modify: `frontend/src/app/ui/type-gates.spec.ts`

**Interfaces:**
- Consumes: `TABULAR_PENDING`, `FAINT_PENDING` in `frontend/src/app/ui/type-gates.spec.ts` after V240-14. `plan-detail.ts` and `trade-detail.ts` after V240-8 (`.plan-title`/`.trade-title` gained `letter-spacing: -0.02em`; this task edits the `.ticker`, `.trade-id` and faint rules next to them, not those).
- Produces: both pending sets hold no `dashboard/`, `calendar/`, `trades/`, `plans/` or `risk/` entry.

Why: these are the pages with the most figures on them: the calendar's
day values and agenda amounts, the trade cards' prices, the tickers and
P&L plans in every table. Under Jost's proportional digits they only line
up with `tabular-nums`. Their quiet text (as-of stamps, empty-panel lines,
weekend dates, the trade id, the note state) moves to `--text-muted`.
Specs touched: none pin these rules (checked at `146b4600`; the DOM specs
query `.ticker`, `.trade-id`, `.as-of` and the like by class only).

- [ ] **Step 1: Remove this area's pending entries (red)**

In `frontend/src/app/ui/type-gates.spec.ts`, delete these 13 lines from
`TABULAR_PENDING`:

```ts
  'app/workspaces/calendar/calendar.ts',
  'app/workspaces/calendar/day/calendar-day.ts',
  'app/workspaces/calendar/day/day-trade-card.ts',
  'app/workspaces/calendar/day/trade-sparkline.ts',
  'app/workspaces/dashboard/dashboard.ts',
  'app/workspaces/dashboard/panels/market-movers.ts',
  'app/workspaces/dashboard/panels/recent-activity.ts',
  'app/workspaces/dashboard/panels/trading-performance.ts',
  'app/workspaces/dashboard/panels/watchlist-panel.ts',
  'app/workspaces/plans/plan-detail.ts',
  'app/workspaces/risk/risk.ts',
  'app/workspaces/trades/trade-detail.ts',
  'app/workspaces/trades/trades.ts',
```

and these 12 lines from `FAINT_PENDING`:

```ts
  'app/workspaces/calendar/calendar.ts',
  'app/workspaces/dashboard/dashboard.ts',
  'app/workspaces/dashboard/panels/equity-candles.ts',
  'app/workspaces/dashboard/panels/exposure-by-horizon.ts',
  'app/workspaces/dashboard/panels/market-movers.ts',
  'app/workspaces/dashboard/panels/recent-activity.ts',
  'app/workspaces/dashboard/panels/watchlist-panel.ts',
  'app/workspaces/plans/plan-detail.ts',
  'app/workspaces/risk/risk.ts',
  'app/workspaces/trades/trade-detail.ts',
  'app/workspaces/trades/trades.ts',
  'app/workspaces/trades/why/outcome-path.ts',
```

After the edit both sets hold only `system/`, `versions/` and
`watchlist/` entries.

- [ ] **Step 2: Run the gate to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/type-gates.spec.ts`
Expected: FAIL — 25 tests: 13 `… sets tabular-nums on every --font-num,
--font-mono and .num rule` and 12 `… paints no text in --text-faint`.

- [ ] **Step 3: Move the faint text to `--text-muted` (script)**

Run from the repo root. It reads and writes bytes, so line endings are
kept:

```bash
python - <<'EOF'
import re
from pathlib import Path

FAINT = re.compile(r'(?<![-\w])color(\s*):(\s*)var\(--text-faint\)')
W = 'app/workspaces/'
# file -> faint text rules at 146b4600 (= type-gates' offender count)
FILES = {
    W + 'calendar/calendar.ts': 5,                   # .as-of; .outside .dom; .weekend .dom; .agenda-date; .agenda-count
    W + 'dashboard/dashboard.ts': 1,                 # .pnl-plan .sep
    W + 'dashboard/panels/equity-candles.ts': 1,     # .part + .part::before
    W + 'dashboard/panels/exposure-by-horizon.ts': 1,  # .empty
    W + 'dashboard/panels/market-movers.ts': 1,      # .empty
    W + 'dashboard/panels/recent-activity.ts': 2,    # .at; .empty
    W + 'dashboard/panels/watchlist-panel.ts': 1,    # th
    W + 'plans/plan-detail.ts': 1,                   # .loading-title
    W + 'risk/risk.ts': 4,                           # .clock; .kill-detail; .cluster-index; .none
    W + 'trades/trade-detail.ts': 6,                 # .loading-title; .trade-id; .no-detail; .note-field:disabled; .note-state; .todo
    W + 'trades/trades.ts': 1,                       # .last-close
    W + 'trades/why/outcome-path.ts': 1,             # .tl-at
}
for name, expected in FILES.items():
    path = Path('frontend/src') / name
    text = path.read_bytes().decode('utf-8')
    new, n = FAINT.subn(r'color\1:\2var(--text-muted)', text)
    assert n == expected, f'{name}: {n} faint colour reads, expected {expected}'
    path.write_bytes(new.encode('utf-8'))
    print(f'{name}: {n}')
EOF
```

Expected: 12 lines printed, 25 reads in all, no `AssertionError`. An
assertion names a file whose count moved since `146b4600`. Open it, check
that each `color: var(--text-faint)` is a text colour inside a style rule,
fix the count in the dict, drop the files already rewritten (they report
0 now) and re-run.

`equity-candles.ts` also reads `--text-faint` from TypeScript for the
canvas seam colour (`token('--text-faint')`); that is a chart mark, not a
CSS `color:`, and the script's pattern does not touch it.

- [ ] **Step 4: Add `tabular-nums` to the numeric rules**

Multi-line rules: add `font-variant-numeric: tabular-nums;` on its own
line directly below the `font-family` line shown, same indentation.

| File (`app/workspaces/…`) | Rule (line at `146b4600`) | Below this line |
|---|---|---|
| `calendar/calendar.ts` | `.value {` (474) | `      font-family: var(--font-mono);` (481) |
| `calendar/day/day-trade-card.ts` | `.prices, .stats {` (105) | `      font-family: var(--font-mono);` (108) |
| `dashboard/dashboard.ts` | `.pnl-plan {` (643) | `      font-family: var(--font-mono);` (644) |
| `plans/plan-detail.ts` | `.ticker {` (304) | `      font-family: var(--font-mono);` (305) |
| `trades/trade-detail.ts` | `.ticker {` (510) | `      font-family: var(--font-mono);` (511) |
| `trades/trade-detail.ts` | `.trade-id {` (534) | `      font-family: var(--font-mono);` (535) |

One-line rules: replace each rule with the line below, keeping the file's
own leading indentation. Paths are under `frontend/src/app/workspaces/`.

`calendar/calendar.ts` (503, 518, 522, 547):

```css
    .agenda-value { flex: 1 1 auto; text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; color: var(--text); }
    .dow .num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; text-align: right; }
    .day-row .amount { margin-left: auto; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .day-leaders p { margin: var(--space-4) 0; color: var(--text-secondary); font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-table); }
```

`calendar/day/calendar-day.ts` (254, 261, 265):

```css
    .compare dd { margin: 0; color: var(--text); font-family: var(--font-mono); font-variant-numeric: tabular-nums; text-align: right; }
    .mtd span { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .breakdown .num { text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

`calendar/day/day-trade-card.ts` (100):

```css
    .figures { display: inline-flex; gap: var(--space-10); margin-left: auto; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

`calendar/day/trade-sparkline.ts` (136):

```css
    .spark-empty { color: var(--text-muted); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

`dashboard/dashboard.ts` (614), `risk/risk.ts` (814) and
`trades/trades.ts` (705), the same rule in all three:

```css
    sb-row-link { color: var(--accent); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

`dashboard/panels/market-movers.ts` (49):

```css
    .symbol { font-family: var(--font-mono); font-variant-numeric: tabular-nums; color: var(--text); }
```

`dashboard/panels/recent-activity.ts` (89; not the `.event-hit:hover
.ticker` rule at 81):

```css
    .ticker { font-family: var(--font-mono); font-variant-numeric: tabular-nums; color: var(--text); font-weight: 600; }
```

`dashboard/panels/trading-performance.ts` (271):

```css
    .mobile-summary strong { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

`dashboard/panels/watchlist-panel.ts` (52):

```css
    .symbol { color: var(--accent); font-family: var(--font-mono); font-variant-numeric: tabular-nums; text-decoration: none; }
```

`trades/trades.ts` (701):

```css
    .last-close-value { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

- [ ] **Step 5: Run the gate and the touched files' specs**

Run:

```bash
cd frontend && npx ng test --watch=false \
  --include src/app/ui/type-gates.spec.ts \
  --include src/app/workspaces/calendar/calendar.spec.ts \
  --include src/app/workspaces/calendar/day/calendar-day.spec.ts \
  --include src/app/workspaces/calendar/day/day-trade-card.spec.ts \
  --include src/app/workspaces/calendar/day/trade-sparkline.spec.ts \
  --include src/app/workspaces/dashboard/dashboard.spec.ts \
  --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts \
  --include src/app/workspaces/dashboard/panels/exposure-by-horizon.spec.ts \
  --include src/app/workspaces/dashboard/panels/market-movers.spec.ts \
  --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts \
  --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts \
  --include src/app/workspaces/dashboard/panels/watchlist-panel.spec.ts \
  --include src/app/workspaces/plans/plan-detail.spec.ts \
  --include src/app/workspaces/risk/risk.spec.ts \
  --include src/app/workspaces/trades/trade-detail.spec.ts \
  --include src/app/workspaces/trades/trades.spec.ts \
  --include src/app/workspaces/trades/why/outcome-path.spec.ts
```

Expected: PASS. A 60s `Timeout waiting for worker` is machine load: re-run
once. A remaining type-gates failure names a selector Steps 3 and 4 missed
(or one added after `146b4600`): fix it the same way.

- [ ] **Step 6: Prove the faint gate still bites in this area**

Temporarily change `risk.ts`'s `.cluster-index` `color: var(--text-muted)`
back to `color: var(--text-faint)` and run
`cd frontend && npx ng test --watch=false --include src/app/ui/type-gates.spec.ts`.
Expected: FAIL — `app/workspaces/risk/risk.ts paints no text in
--text-faint`. Undo that one word by hand and re-run: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/type-gates.spec.ts \
  frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/day/calendar-day.ts \
  frontend/src/app/workspaces/calendar/day/day-trade-card.ts frontend/src/app/workspaces/calendar/day/trade-sparkline.ts \
  frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.ts \
  frontend/src/app/workspaces/dashboard/panels/exposure-by-horizon.ts frontend/src/app/workspaces/dashboard/panels/market-movers.ts \
  frontend/src/app/workspaces/dashboard/panels/recent-activity.ts frontend/src/app/workspaces/dashboard/panels/trading-performance.ts \
  frontend/src/app/workspaces/dashboard/panels/watchlist-panel.ts frontend/src/app/workspaces/plans/plan-detail.ts \
  frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/trades/trade-detail.ts \
  frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/trades/why/outcome-path.ts
git commit -m "style(v240): sweep 3 -- dashboard, calendar, trades, plans, risk: tabular-nums on figures and tickers, quiet text off --text-faint

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V240-16: Sweep 4: system, versions, watchlist; pending lists deleted

**Model:** haiku — the last scripted colour swap and 16 listed one-declaration additions, then a deletion in one spec file whose replacement code is given whole.

**Files:**
- Modify (faint): `frontend/src/app/workspaces/system/logs-tab.ts`, `frontend/src/app/workspaces/system/scan-tab.ts`, `frontend/src/app/workspaces/system/settings-tab.ts`, `frontend/src/app/workspaces/versions/versions.ts`, `frontend/src/app/workspaces/watchlist/earnings-calendar.ts`, `frontend/src/app/workspaces/watchlist/watchlist.ts`
- Modify (tabular): `frontend/src/app/workspaces/system/logs-tab.ts`, `frontend/src/app/workspaces/system/scan-tab.ts`, `frontend/src/app/workspaces/system/settings-tab.ts`, `frontend/src/app/workspaces/versions/versions.ts`, `frontend/src/app/workspaces/watchlist/earnings-calendar.ts`, `frontend/src/app/workspaces/watchlist/ticker-detail.ts`, `frontend/src/app/workspaces/watchlist/watchlist.ts`
- Modify: `frontend/src/app/ui/type-gates.spec.ts` (pending sets, their tests and the `pending` field deleted; one coverage test added)

**Interfaces:**
- Consumes: `frontend/src/app/ui/type-gates.spec.ts` after V240-15: `TABULAR_PENDING` holds exactly the 7 entries and `FAINT_PENDING` exactly the 6 entries this task fixes; `Gate`, `GATES`, `SOURCES`, `offenders`, `NUM_FACE`, `NUM_CELL` as V240-9 wrote them.
- Produces: `TABULAR_PENDING`/`FAINT_PENDING` and their "still offends" and "names only scanned files" tests deleted; `Gate` loses its `pending` field; both gates run over every source with no exemptions.

Why: the last three areas, then the scaffolding goes. Once no file is
pending, a pending set can only ever be used to excuse a new offender, so
it is deleted rather than left empty. A coverage test makes sure the
tabular gate still has numeric rules to look at (77 at `146b4600`), so a
parser regression that finds no rules cannot pass the gate silently.

- [ ] **Step 1: Delete the pending machinery (red)**

In `frontend/src/app/ui/type-gates.spec.ts`:

1. Delete the whole `const TABULAR_PENDING … ]);` and
   `const FAINT_PENDING … ]);` declarations.
2. Replace the last paragraph of the header comment (from `Each gate starts
   with a pending set of today's offenders.` to `so the sets never hold a
   fixed file.`) with:

```ts
 * Both gates started (V240-9) with a pending set of the offenders they
 * found; part 3's sweeps emptied it area by area and V240-16 deleted it.
 * They now run over every source with no exemptions: fix the rule, never
 * add one back.
```

3. Replace the `Gate` type and the `GATES` array with:

```ts
type Gate = {
  id: string;
  rule: string;
  offends: (rule: StyleRule) => boolean;
};

const GATES: Gate[] = [
  {
    id: 'tabular',
    rule: 'sets tabular-nums on every --font-num, --font-mono and .num rule',
    offends: (rule) => (NUM_FACE.test(rule.body) || NUM_CELL.test(rule.selector)) && !TABULAR.test(rule.body),
  },
  {
    id: 'faint',
    rule: 'paints no text in --text-faint',
    offends: (rule) => FAINT_TEXT.test(rule.body),
  },
];
```

4. Replace the whole `for (const gate of GATES) { describe(…) }` block
   (the one with the `gate.pending.has(name)` branch and the `'names only
   scanned files in its pending set'` test) with:

```ts
for (const gate of GATES) {
  describe(`v240 type gate: ${gate.id}`, () => {
    for (const { name, rules } of SOURCES) {
      it(`${name} ${gate.rule}`, () => {
        expect(offenders(gate, rules)).toEqual([]);
      });
    }
  });
}

describe('v240 type gates: they still have something to check', () => {
  it('finds the numeric rules (77 at 146b4600), so an empty parse cannot pass', () => {
    const numeric = SOURCES.flatMap(({ rules }) => rules)
      .filter((rule) => NUM_FACE.test(rule.body) || NUM_CELL.test(rule.selector));
    expect(numeric.length).toBeGreaterThanOrEqual(70);
  });
});
```

The `'v240 type gates: the predicates'` block and the `'nothing hides from
them'` block stay exactly as they are.

- [ ] **Step 2: Run the gate to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/type-gates.spec.ts`
Expected: FAIL — 13 tests: 7 `… sets tabular-nums on every --font-num,
--font-mono and .num rule` (`system/logs-tab`, `system/scan-tab`,
`system/settings-tab`, `versions/versions`, `watchlist/earnings-calendar`,
`watchlist/ticker-detail`, `watchlist/watchlist`) and 6 `… paints no text
in --text-faint`. The coverage test passes. Any other failure means a
file earlier sweeps missed: fix it as Steps 3 and 4 do.

- [ ] **Step 3: Move the faint text to `--text-muted` (script)**

Run from the repo root. It reads and writes bytes, so line endings are
kept:

```bash
python - <<'EOF'
import re
from pathlib import Path

FAINT = re.compile(r'(?<![-\w])color(\s*):(\s*)var\(--text-faint\)')
W = 'app/workspaces/'
# file -> faint text rules at 146b4600 (= type-gates' offender count)
FILES = {
    W + 'system/logs-tab.ts': 3,            # .hidden-count; .meta; .none
    W + 'system/scan-tab.ts': 1,            # .meta
    W + 'system/settings-tab.ts': 10,       # .field-count; .legend; .default-badge; .asymmetry; .find .found; .key; .secret; .category-rail span; .audit-ts; .none
    W + 'versions/versions.ts': 7,          # .label; .chip.quiet; .release-meta, .provenance; .telemetry-cards .n; .tooltip .when; .ticks; .section-help
    W + 'watchlist/earnings-calendar.ts': 2,  # .cell.dim .day-num; .est
    W + 'watchlist/watchlist.ts': 2,        # .hit-have; .as-of
}
for name, expected in FILES.items():
    path = Path('frontend/src') / name
    text = path.read_bytes().decode('utf-8')
    new, n = FAINT.subn(r'color\1:\2var(--text-muted)', text)
    assert n == expected, f'{name}: {n} faint colour reads, expected {expected}'
    path.write_bytes(new.encode('utf-8'))
    print(f'{name}: {n}')
EOF
```

Expected: 6 lines printed, 25 reads in all, no `AssertionError`. An
assertion names a file whose count moved since `146b4600`. Open it, check
that each `color: var(--text-faint)` is a text colour inside a style rule,
fix the count in the dict, drop the files already rewritten (they report
0 now) and re-run.

`versions.ts`'s `.chip.quiet` stays distinguishable from a live chip by
its `cursor: default` and the missing `.on` state, not by colour alone.

- [ ] **Step 4: Add `tabular-nums` to the numeric rules**

Multi-line rules: add `font-variant-numeric: tabular-nums;` on its own
line directly below the `font-family` line shown, same indentation.

| File (`app/workspaces/…`) | Rule (line at `146b4600`) | Below this line |
|---|---|---|
| `system/logs-tab.ts` | `.log {` (199) | `      font-family: var(--font-mono);` (207) |
| `system/settings-tab.ts` | `.default-badge {` (456) | `      font-family: var(--font-mono);` (458) |
| `system/settings-tab.ts` | `.key {` (504) | `      font-family: var(--font-mono);` (506) |
| `system/settings-tab.ts` | `.import-text {` (611) | `      font-family: var(--font-mono);` (619) |

`versions.ts` holds three rules that put several declarations on one line
inside a multi-line rule; replace those lines exactly (paths under
`frontend/src/app/workspaces/`):

`versions/versions.ts` `.chip {` (264), line 265:

```css
      font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--register-label);
```

`versions/versions.ts` `.lane-name {` (281), line 281 (line 282 stays):

```css
    .lane-name { width: var(--lane-w); flex: none; font-family: var(--font-mono); font-variant-numeric: tabular-nums;
```

`versions/versions.ts` `.ticks {` (350), line 353 (after Step 3 it reads
`--text-muted`):

```css
      font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--register-label); color: var(--text-muted);
```

One-line rules: replace each rule with the line below, keeping the file's
own leading indentation.

`system/scan-tab.ts` (184):

```css
    code { font-family: var(--font-mono); font-variant-numeric: tabular-nums; color: var(--text); }
```

`system/settings-tab.ts` (571, after Step 3; 603):

```css
    .category-rail span { color: var(--text-muted); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .audit-change { color: var(--text-secondary); font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-chip); }
```

`versions/versions.ts` (241):

```css
    .stale code, .muted code { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-micro); }
```

`watchlist/earnings-calendar.ts` (169):

```css
    .symbol { color: var(--text); font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-chip); font-weight: 600; }
```

`watchlist/ticker-detail.ts` (153) and `watchlist/watchlist.ts` (579),
the same rule in both:

```css
    sb-row-link { color: var(--accent); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

`watchlist/watchlist.ts` (545, 573):

```css
    .input { display: block; width: 100%; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    .hit-symbol { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

- [ ] **Step 5: Run the gate and the touched files' specs**

Run:

```bash
cd frontend && npx ng test --watch=false \
  --include src/app/ui/type-gates.spec.ts \
  --include src/app/workspaces/system/logs-tab.spec.ts \
  --include src/app/workspaces/system/scan-tab.spec.ts \
  --include src/app/workspaces/system/settings-tab.spec.ts \
  --include src/app/workspaces/versions/versions.spec.ts \
  --include src/app/workspaces/watchlist/earnings-calendar.spec.ts \
  --include src/app/workspaces/watchlist/ticker-detail.spec.ts \
  --include src/app/workspaces/watchlist/watchlist.spec.ts
```

Expected: PASS. `versions.spec.ts`'s `--lane-w` test reads the `.ticks`
and `.lane-name` rules and only forbids `4.5rem` in them, which still
holds. A 60s `Timeout waiting for worker` is machine load: re-run once.

- [ ] **Step 6: Confirm nothing pending is left, and that both gates bite**

Run: `git grep -n "PENDING\|pending" -- frontend/src/app/ui/type-gates.spec.ts`
Expected: no output.

Then, one at a time, temporarily (a) delete the
`font-variant-numeric: tabular-nums;` you added to `watchlist.ts`'s
`.hit-symbol` rule, and (b) change `scan-tab.ts`'s `.meta`
`color: var(--text-muted)` back to `color: var(--text-faint)`; after each,
run `cd frontend && npx ng test --watch=false --include src/app/ui/type-gates.spec.ts`.
Expected: FAIL naming `app/workspaces/watchlist/watchlist.ts`, then
`app/workspaces/system/scan-tab.ts`. Undo each change by hand and re-run:
PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/type-gates.spec.ts \
  frontend/src/app/workspaces/system/logs-tab.ts frontend/src/app/workspaces/system/scan-tab.ts \
  frontend/src/app/workspaces/system/settings-tab.ts frontend/src/app/workspaces/versions/versions.ts \
  frontend/src/app/workspaces/watchlist/earnings-calendar.ts frontend/src/app/workspaces/watchlist/ticker-detail.ts \
  frontend/src/app/workspaces/watchlist/watchlist.ts
git commit -m "style(v240): sweep 4 -- system, versions, watchlist; the type gates' pending lists are gone, both run with no exemptions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
