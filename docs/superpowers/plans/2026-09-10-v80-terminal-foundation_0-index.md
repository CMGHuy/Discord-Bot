# v80 — Terminal foundation: implementation plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-10-v80-terminal-foundation-design.md`
**Bump:** ui minor, bot minor
**Edge:** none (integrity)

**Goal:** Land direction C's tokens, the canonical component set with phone
behaviour built in, and the Discord chart palette, without changing any
workspace code.

**Architecture:** Tokens first (`tokens.css`, `styles.css`). Then one task per
shared component file under `frontend/src/app/ui/`, each carrying its own spec
file so the tasks stay file-disjoint. The Discord palette moves independently
in `swingbot/core/charts/`. The UI gallery then shows everything, a browser walk
and one full run of both suites verify it, and a release task closes the plan.

**Tech Stack:** Angular 21 (standalone components, signals, zoneless), Vitest
through `@angular/build:unit-test`, Python 3.11, matplotlib/mplfinance, pytest.

## Global Constraints

- **Hard precondition.** Do not start Task F1 until
  `git merge-base --is-ancestor 24688ff4 main` exits 0 (v77's shell wiring is
  in `main`). `main` already carries v77's `release(ui): 1.13.0 -- live tape`
  commit without v77's code, so `VERSION.json` is not a substitute check. F4 is
  written against v77's `ui/button.ts` (with `danger-icon`) and F25 uses v77's
  `trash` icon.
- **Worktree.** Execute in `.claude/worktrees/2026-09-10-v80-terminal-foundation/`
  on a branch of the same name (`docs/claude/document-lifecycle.md`).
- **No workspace edits.** Nothing under `frontend/src/app/workspaces/` changes
  except `workspaces/gallery/`. Deprecated APIs keep working: `sb-metric-card`,
  `sb-metric-chip`, `sb-filter-chips`, the button `segment`/`chip` variants and
  `sb-section-head`'s `[actions]` slot.
- **Values are copied, never retyped.** Every colour, size and threshold comes
  from the spec's D1, D2 and D3 tables.
- **Font weights.** JetBrains Mono uses only 400/500/700 (the self-hosted
  files). Inter uses 400/500/600/700.
- **`--text-faint` is divider-only.** Never use it for readable text.
  `contrast.spec.ts` documents it as non-text.
- **Frontend test commands run in a subshell from the repo root:**
  `(cd frontend && npx ng test --watch=false --include='**/<file>.spec.ts')`.
  A bare `cd frontend` persists in the tool shell and breaks
  `.claude/hooks/guardrails.py`, which resolves its own path from the repo root.
- **Python per-task command:** `python scripts/dev/testrun.py file <path>`.
- **Commit subjects:** `feat(v80): …`, `test(v80): …`, `fix(v80): …`. End every
  message with the session's attribution lines.
- **Full suites run once, in F27.** Never per task.
- **Known interim red, by design.** `workspaces/gallery/gallery.spec.ts`
  asserts that every `selector: 'sb-…'` under `ui/` appears in the gallery.
  Tasks F15–F20 each add a selector, and the gallery (a shared file) is only
  updated in F25. That spec's `renders sb-<new>` cases therefore fail from F15
  until F25. Do not add gallery entries in Group A tasks: it would make them
  share a file and break the parallelisation below.

## Parts

| File | Phase | Tasks |
|---|---|---|
| `2026-09-10-v80-terminal-foundation_1-tokens.md` | Phase 1 — Tokens | F1–F3 |
| `2026-09-10-v80-terminal-foundation_2a-components.md` | Phase 2 — Canonical components: button, form controls, chip, layout | F4–F7 |
| `2026-09-10-v80-terminal-foundation_2b-components.md` | Phase 2 — table, pager and cells, empty state, section head | F8–F12 |
| `2026-09-10-v80-terminal-foundation_3a-components.md` | Phase 2 — filter bar, `held()`, segmented, figure | F13–F16 |
| `2026-09-10-v80-terminal-foundation_3b-components.md` | Phase 2 — panel grid, status, hint, P&L cell | F17–F20 |
| `2026-09-10-v80-terminal-foundation_4-discord-charts.md` | Phase 3 — Discord charts | F21–F24 |
| `2026-09-10-v80-terminal-foundation_5-gallery-release.md` | Phase 4 — Gallery, verification, release | F25–F28 |

## Parallelisation

- **Sequential first: Phase 1 (F1 → F2 → F3).** All three edit
  `frontend/src/styles/tokens.css`, and F3 also edits `styles.css`. Every later
  frontend task consumes these tokens.
  - F1 (chart series) runs **before** F2 (colours), the reverse of the spec's
    listing. `chart-palette.spec.ts` pins `--chart-1/2/3` to
    `--accent/--info/--warn`, so the pin would fail the moment F2 changed
    `--accent`. Removing it in F1 first keeps every commit green.
- **Group A (parallel, after F3): F4–F20.** One file plus its own spec each:
  - existing components: `button.ts`, `form-controls.ts`, `chip.ts`,
    `layout.ts`, `data-table.ts`, `pagination.ts`, `confidence-cell.ts`,
    `empty-state.ts`, `section-head.ts`, `filter-bar.ts`, `format.ts`;
  - new files: `segmented.ts`, `figure.ts` (plus deprecation comments in
    `metric-card.ts` and `metric-chip.ts`, which no other task touches),
    `panel-grid.ts`, `status.ts`, `hint.ts`, `pnl-cell.ts`.

  No Group A task consumes a symbol another Group A task introduces, and none
  edits `controls.spec.ts`.
- **Group B (Discord), after F2.**
  - **F21 → F22 → F23 run sequentially:** all three touch `chart_style.py` or
    `tests/charts/test_chart_theme.py`, and F23 deletes the file F21 stops
    reading.
  - **F24 runs alongside them:** it touches only `presentation/tokens.py` and
    its test.
  - **F21 waits for F2** because its test reads D1's values out of
    `frontend/src/styles/tokens.css`. It can run alongside F3 and Group A.
  - No Group B task touches another frontend file.
- **Sequential last:**
  - F25 (gallery) after Group A.
  - F26 (browser walk) after F25 and F23.
  - F27 (full suites) after F26.
  - F28 (release and close-out) last.

## Spec coverage

| Spec item | Task(s) |
|---|---|
| D1 colour tokens, contrast margins | F2 |
| D2 six series, `line-chart.ts` `SERIES`, OKLCH band and chroma gate | F1 |
| D3 `.sb-label`, `.sb-help`, `--text-metric` 28px, radii, `--row-h`, `--text-control`, touch block | F3 |
| D3 container-query responsiveness | F8 (`sb-data-table`), F13 (`sb-filter-bar`), F16 (`sb-figure-strip`); see F7 and F17 for the two components that use a viewport query and why |
| D4 `button[sb-button]` (incl. `danger-icon`, deprecated `segment`/`chip`) | F4 |
| D4 `sb-select`, `sb-text-input`, `sb-checkbox` | F5 |
| D4 `sb-chip`, `sb-quality-chip` | F6 |
| D4 `sb-panel`, `sb-tab-bar`, `sb-control-row`, `sb-drawer` | F7 |
| D4 `sb-data-table` phone mode, card mode replaced | F8 |
| D4 `sb-pagination` | F9 |
| D4 / cell contracts: `sb-confidence-cell` (text, mono weight) | F10 |
| D4 `sb-empty-state` reason | F11 |
| D4 `sb-section-head` back/status slots | F12 |
| D4 `sb-filter-bar` counts, `sb-filter-chips` deprecated | F13 |
| Cell contracts: `held()` always shows minutes | F14 |
| D4 `sb-segmented` | F15 |
| D4 `sb-figure`, `sb-figure-strip`; metric-card/chip deprecated | F16 |
| D4 `sb-panel-grid` | F17 |
| D4 `sb-status` | F18 |
| D4 `sb-hint` | F19 |
| Cell contracts: `sb-pnl-cell` | F20 |
| Cell contracts: `sb-direction-arrow`, `sb-plan-cell` unchanged | token-driven, no edit; shown in F25 |
| D4 restyle-only via tokens: `sb-confirm-dialog`, `sb-status-cell`, `sb-status-indicator`, `sb-row-link`, column picker, chart chrome | token-driven, no edit; walked in F26 |
| D5 palette, overlay roles, `THEME` → admin tokens, OKLab ΔE gate | F21 |
| D5 stray literals moved, literal ban | F22 |
| D5 delete `admin/static/tokens.css`, `testrun.py` escalation, features doc | F23 |
| D5 embed `ACCENT_RAMP[3]`, `ACCENT_BLOCKED` | F24 |
| D6 gallery incl. cell-contract row | F25 |
| Gate 1 (`tokens.spec.ts`) | F1, F2, F3 |
| Gate 2 (`contrast.spec.ts`) | F2 |
| Gate 3 (`chart-palette.spec.ts`) | F1 |
| Gate 4 (per-component spec files) | F4–F20 |
| Gate 5 (`test_chart_theme.py`) | F21, F22 |
| Gate 6 (`test_tokens.py`) | F24 |
| Gate 7 (existing gates green unchanged) | F27 |
| Gate 8 (browser walk, chart fixtures) | F26 |
| Gate 9 (full suites once) | F27 |
| Release and close-out | F28 |
