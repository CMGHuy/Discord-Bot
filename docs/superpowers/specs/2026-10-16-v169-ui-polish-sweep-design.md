# v169 — UI polish sweep: every workspace on Arctic Navy and the motion system, at three widths

**Version:** ui 1.24.1 · bot 2.5.2 (at writing)
**Bump:** ui patch; bot none. This spec fixes what v167/v168 expose and adds no features.
**Edge:** none (integrity). This is presentation only.
**Screen:** exempt (integrity)
**Panel:** senior-engineer
**Status:** spec written 2026-10-16 from the same brainstorm as v167 and v168, and approved in chat. Depends on **v167 and v168 both merged**.

## Why

v167 changes the palette and geometry globally, and v168 adds motion through the shared primitives. Global rules reach every screen, but they also expose local assumptions that only held under the old look. For example:
- a panel nested inside a panel now shows a double 8px radius and gradient-on-gradient;
- chips that are now pills wrap differently;
- a table inside an 8px panel needs its corners clipped;
- a workspace builds its own panel grid and so gets no stagger.

This spec walks every screen once, at three widths, and fixes those spots so the new look holds everywhere.

## Scope

The 12 workspaces in `frontend/src/app/workspaces/` (analytics, calendar, dashboard, gallery, plans, reports, research, risk, system, trades, versions, watchlist), plus the shell (nav, top bar, tape, scan progress, connection status), the login page and toasts.

## Design

### 1. Evidence first

For each screen, take Playwright screenshots at **390 / 768 / 1440** against the dev server, using `scripts/browse.mjs` (Playwright only, never claude-in-chrome; `skills-tools.md`):
- **before**: `main` with v167 + v168 merged, before this spec's fixes;
- **after**: the end of this spec.

Store them under `docs/superpowers/results/v169/<workspace>/<width>-{before,after}.png`. The plan writes one task per workspace group, and each task starts from its "before" shots.

### 2. Fix catalogue (what a task looks for)

| Defect | Fix |
|---|---|
| Panel nested in a panel | Inner one drops to `--panel-inner` (new tier-3 token in `tokens.css`: flat `--surface-raised`, `--control-radius`, no shadow). |
| Table or chart flush to a panel edge | `overflow: clip` on the panel body, so content follows `--panel-radius`. |
| Chips misaligned as pills | Row `align-items: center` and a `gap` from the spacing scale. A chip never sets its own radius. |
| Workspace panel grid without entrance | Add `.sb-stagger` + `[sbStaggerIndex]` (v168 §3 #2). |
| KPI or hero number not using `figure.ts` | Route it through `figure.ts` so it gets count-up. |
| Inline loading text | Replace with `async.ts` skeleton (v168 §3 #4). |
| Hand-rolled header or section title | Use the shared header and section primitives. Extend `workspace-consistency.spec.ts` to assert it. |
| A hover-only affordance | Add a visible or `:active` affordance (`ui-design.md`). |
| A touch target under 44px on phone or tablet | Fix it with `--control-h`. |

Anything outside this catalogue, such as a layout reorganisation or a missing feature, is **logged as a follow-up** in the plan's `## Handoff`, not done here.

### 3. Shell and login

- The shell nav uses v168's sliding indicator. The top bar gets `--panel-border` bottom hairline and a translucent `--surface` ground.
- The login card is a `--panel-*` panel centred on `--glow-ambient`, with the primary button on `--btn-fill`.
- The tape keeps its scroll. Only its colours change, through tokens.

### 4. Interaction with v165 and v166

The v165 (calendar day page) and v166 (trade detail reorganisation) screens are swept **as they stand on `main` when this plan starts**. If either is still unmerged then, its screen is skipped and noted in `## Handoff`. This spec never edits another plan's worktree.

## Out of scope

New features, layout redesigns, copy changes, palette or token value changes (v167 owns those), and new animation types (v168 owns those).

## Testing

- `workspace-consistency.spec.ts` (extended): every workspace uses the shared header and section primitives, and its panel grid carries `.sb-stagger`.
- The v167 and v168 gates (no raw colour, no raw radius, motion home, no replay) stay green across all workspaces. That green is the main proof of the sweep.
- Before and after screenshots at three widths for every screen in scope.
- The plan ends with the single full-suite task.
