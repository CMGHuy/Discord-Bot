# UI Elevation (v54) Implementation Plan — Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the admin SPA from "competent dark dashboard" to an instrument you can read for hours without being misled, by finishing the primitive layer, making state honest, reviving the elevation ladder and enforcing every rule with a test.

**Architecture:** Five sequential-ish waves over the existing Angular 20 signal-based SPA. Wave `_1` builds every shared part (primitive variants, four new composites, `sb-async`, the `/ui` gallery, the regression gate); waves `_2`–`_5` install those parts across the eight workspaces. No existing token changes value, so a component left untouched keeps rendering exactly as it does today.

**Tech Stack:** Angular 20 (standalone, signals, `input()`/`model()`, `@if`/`@for`, OnPush), TypeScript, plain CSS with custom properties, Vitest via `@angular/build:unit-test`, no component library, no CSS framework.

**Spec:** `docs/superpowers/specs/2026-08-23-v54-ui-elevation-design.md`

## Global Constraints

Every task's requirements implicitly include all of these.

- **`Bump: ui minor`, `Edge: none (integrity)`.** This plan buys no expectancy and must not be described as if it does.
- **Do not start until v50, v51, v52 and v53 are merged to `main`.** Verify with `git log --oneline main | grep -E "v5[0-3]"` before Task 1.
- **No existing token changes value.** Tokens may be *added*. Changing one is a review defect — the whole no-silent-breakage argument in the spec rests on this.
- **No off-scale values.** Font size from the closed set `--text-micro|chip|table|body|subhead|title|metric`; spacing from `--space-4|6|8|10|14|20`; one control height `--control-h`. A literal `px` is permitted only for a 1px/2px border.
- **One hue, one valence.** `--pos` good, `--neg` bad, `--warn` caution, `--accent` interactive, `--info` neutral. A sixth semantic hue is a review defect. Chart series colours are a separate namespace (see `_4`).
- **Dark only.** No `prefers-color-scheme` block, no `[data-theme]` hook.
- **Every component is `standalone`, `ChangeDetectionStrategy.OnPush`, and uses signal inputs** (`input()`, `input.required()`, `model()`). Do not add `ControlValueAccessor` — `form-controls.ts:5` records that this app does not use Angular forms.
- **Test command:** `cd frontend && npm test`. Single file: `npm test -- --include src/app/ui/foo.spec.ts`.
- **`ng test` intermittently dies at exactly 60s** with `[vitest-pool-runner]: Timeout waiting for worker to respond`. This is load, not a broken suite, and the cause is documented in `frontend/vitest.config.ts`. **A re-run succeeds — treat a fresh timeout as "try again".** Never "fix" it by editing the pool config.
- **(G10) Python suite must stay at `1686 passed, 66 skipped, 0 failed, 0 xfailed`.** This plan touches no Python; a moved count means something unintended happened. Check with `python scripts/dev/testrun.py full` before the final merge of each wave, not per task.
- **Commit per task**, message style `feat(v54): …` / `refactor(v54): …` / `test(v54): …`, matching this repo's existing history.

## Wave order and parallelisation

```
_1-primitives (D7)                  SOLO WAVE — nothing runs beside it
       |
       +-- _2-states    (D3)        parallel with _3
       +-- _3-craft     (D2, D4)    parallel with _2
                |
                +-- _4-register (D1, D5)   parallel with _5
                +-- _5-ia-a11y  (D6)       parallel with _4
```

- **`_1` runs alone.** It edits `ui/` and touches every workspace file. This working tree is shared between concurrent sessions — two agents in one file overwrite rather than merge. `_1` merges to `main` before any other wave starts.
- **`_2` ∥ `_3`.** Disjoint files: `_2` edits workspace templates to install `sb-async`; `_3` edits `tokens.css`, `ui/` numeric primitives and the elevation rule. Neither reads the other's output.
- **`_4` ∥ `_5`.** `_4` needs `_3`'s `--shadow-overlay` and elevation classes; `_5` needs `_2`'s `sb-async` host for `aria-busy`. Between themselves they are disjoint — `_4` is panels and charts, `_5` is shell nav, live regions and the flash directive.
- **The order is load-bearing.** Styling the elevation ladder before `_1` extracts `sb-section-head` would mean styling seven copies of one header and then deleting six.

## Parts

| Part | Decisions | Tasks | Deliverable |
|---|---|---|---|
| [`_1-primitives`](2026-08-23-v54-ui-elevation_1-primitives.md) | D7 | 1–12 | Every shared part exists, is reachable at `/ui`, and is enforced by a gate |
| [`_2-states`](2026-08-23-v54-ui-elevation_2-states.md) | D3 | 13–21 | All 8 workspaces show honest loading / empty / error / stale |
| [`_3-craft`](2026-08-23-v54-ui-elevation_3-craft.md) | D2, D4 | 22–29 | Elevation ladder live with the one-shadow law; numeric law applied |
| [`_4-register`](2026-08-23-v54-ui-elevation_4-register.md) | D1, D5 | 30–37 | Two registers declared per panel; one chart system, no raw hexes |
| [`_5-ia-a11y`](2026-08-23-v54-ui-elevation_5-ia-a11y.md) | D6 | 38–44 | Grouped nav, live regions, focus management, meaningful motion |

## Acceptance gates

Copied verbatim from the spec. A wave is not done until its gates pass.

| # | Gate | Enforced in |
|---|---|---|
| G1 | `sb-async` wraps every fetch-backed region | `_2` T21 |
| G2 | Every `sb-async` empty branch passes an explicit reason | `_1` T10 (type), `_2` T21 (test) |
| G3 | `box-shadow` appears in exactly one rule in the codebase | `_3` T24 |
| G4 | Zero hex literals outside `tokens.css` | `_1` T12, `_4` T36 |
| G5 | Every text-token / surface-token pair ≥ 4.5:1, or documented as non-text | `_5` T43 |
| G6 | No layout shift on data arrival | `_2` T21 |
| G7 | `ui/primitives.spec.ts` passes, allowlist entries all justified | `_1` T12 |
| G8 | `/ui` renders every exported primitive | `_1` T11 |
| G9 | No `--chart-*` member within ΔE 10 of `--pos` or `--neg` | `_4` T35 |
| G10 | Python suite unchanged; frontend vitest green | every wave |

## Close-out

When the last wave merges:

1. `git mv` this plan's six files **and** the spec into `implemented/`.
2. Bump `VERSION.json`'s `ui` line (minor). Leave `bot` alone — no Python changed.
3. `git worktree remove` the `2026-08-23-v54-ui-elevation` worktree, then `git branch -d` its branch. `-d`, never `-D`.
4. Regenerate `version_history` per the repo's usual close-out.
