# v169 — UI polish sweep: every workspace on Arctic Navy and the motion system, at three widths

**Version:** ui 1.24.1 · bot 2.5.2 (at writing)
**Bump:** ui patch; bot none. This spec fixes what v167/v168 expose. It adds no features, inputs, API calls or copy, and its one gate change is a test (see § Scope rule). The new look itself was already bumped minor by v167 and v168.
**Edge:** none (integrity). This is presentation only.
**Screen:** exempt (integrity)
**Panel:** senior-engineer
**Status:** spec written 2026-10-16 from the same brainstorm as v167 and v168, and approved in chat. Revised the same day after the panel (see `## Panel review`). Depends on **v167 and v168 both merged**.

## Why

v167 changes the palette and geometry globally, and v168 adds motion through the shared primitives, `sb-panel-grid` included. Global rules reach every screen, but they also expose local assumptions that only held under the old look. For example:
- a panel nested inside a panel now shows a double 8px radius and gradient-on-gradient;
- chips that are now pills wrap differently;
- a table inside an 8px panel needs its corners clipped;
- a hand-built grid gets no stagger.

This spec walks every screen once, at three widths, and fixes those spots so the new look holds everywhere.

## Scope

**Screens.** All 12 directories under `frontend/src/app/workspaces/`: analytics, calendar, dashboard, **gallery**, plans, reports, research, risk, system, trades, versions and watchlist. Each is identified by its routes in `app.routes.ts`, and the plan's first task lists the exact route per screen (for example, the plans workspace is the plan-detail route `plans/:id`, since `plans/` holds only `plan-detail.ts`). The shell is in scope too: `shell/shell.css`, `shell/tape/tape.css`, `shell/scan-progress.css` and `shell/connection-status.ts`. So are the login page (`shell/login/login.css` and its template) and toasts (`shell/toast-host.ts`).

**Scope rule (what a fix may touch).** A fix may change only:
- CSS;
- template `class` attributes;
- swapping hand-built markup for an **existing** primitive.

The two primitive swaps v168 introduced (`[sbStaggerIndex]`, `figure.ts`) count as existing.

A fix may not add or change component inputs or outputs, API calls, stores, routes or user-visible copy. The plan's last task before the full suite checks the branch diff (`git diff main...<branch> -- 'frontend/src/**/*.ts'`). Any `.ts` change other than `styles:`/`template:` blocks, `imports:` arrays and the consistency spec must be named and justified in the task report. Anything outside the rule goes into **`## Handoff` in the plan's `_0-index` file**, never into the code.

## Design

### 1. Evidence: screenshots

**Tool.** `frontend/scripts/browse.mjs` (Playwright only; `skills-tools.md`), always with explicit flags. The script's defaults are production and four widths, and neither is what this spec wants:

```
node frontend/scripts/browse.mjs shots --base http://localhost:4200 --widths 390,768,1440 \
     --path <route> [--path <route> ...] --out <dir>
```

**Environment.** `npm start` in `frontend/` (`ng serve` on :4200) with `python admin_ui.py` on :1234 alongside, per `frontend/proxy.conf.json`.
- The script waits for a headed login, and **the partner types the login** (CLAUDE.md, browser rule). A task that needs one stops and asks for it.
- If the local backend has no data for a screen (an empty table proves nothing about table styling), the task records that screen as "empty locally" in its report. It does not point the script at production: production does not run v167/v168 until they are deployed.

**Storage.**
- The script writes `<slug>@<width>.png` (plus a `.txt` per shot) into `--out`.
- Shots go to `.superpowers/results/v169/{before,after}/` (that directory is git-ignored, so about 80 full-page PNGs stay out of the repo).
- What **is** committed is `docs/superpowers/results/v169/sweep.md`: one row per screen × width, giving the defects found from the catalogue below, the fix commit, and a "clean" mark after the fix.
- The partner reviews the PNGs locally from the ignored folder.

### 2. Fix catalogue

Each row has a **detection rule**, so a task is a finding, not a matter of taste.

| Defect | How it is detected | Fix |
|---|---|---|
| Panel nested in a panel | grep: an `sb-panel`/panel primitive inside another panel's template; and visible double-gradient in the "before" shot | Inner element uses v167's `--panel-inner-bg` and `--panel-inner-radius`, with no `.sb-panel` class (so no shadow). |
| Table or chart corners poking past a panel's radius | "before" shot at 1440 | `overflow: clip` **on the table or chart wrapper element only**, never on the panel. Sticky headers, focus rings, tooltips, popovers, column-picker menus and `.sb-lift` shadows must stay unclipped. Acceptance: a shot with a focused cell and an open column picker on the edge row shows neither cropped. |
| Chips misaligned as pills | "before" shot at 390 and 768 | Row `align-items: center` and a `gap` from the spacing scale. A chip never sets its own radius. |
| **Hand-built** panel grid without stagger | grep `display:\s*grid` in each workspace's component `styles:`. A hit that lays out panels and is not `sb-panel-grid` is hand-built. | Prefer swapping to `sb-panel-grid` (which staggers since v168). If the layout cannot use it, add `.sb-stagger` and `[sbStaggerIndex]`. |
| Headline number not counting up | grep for a KPI or hero value rendered as a bare interpolation rather than through `figure.ts` | Route it through `figure.ts`. **Count-up applies only to headline figures**: portfolio value, P&L, ExpR, win rate, heat, counts in KPI tiles. It never applies to numbers inside tables, chips, tooltips or axis labels. |
| Inline loading text | grep for loading copy outside `sb-async` | Wrap in `sb-async` (shimmer skeleton since v168). |
| Hand-rolled header or section title | grep for heading markup (`<h2`, `<h3`, `.title` classes) in workspace templates that is not inside `sb-panel-header` (`ui/panel-header.ts:7`) or `sb-section-head` (`ui/section-head.ts:19`) | Swap to the primitive. |
| Touch target under 44px on phone or tablet | **New script `frontend/scripts/audit-targets.mjs`** (Playwright): at 390 and 768, it lists every visible `a, button, input, select, [role=button], [tabindex]` with a bounding box under 44×44, per route. Its output goes in `sweep.md`. | Use `--control-h`, or enlarge the hit area with padding or a pseudo-element. |
| Hover-only affordance | The same script lists elements whose only visible change on interaction is a `:hover` rule (computed-style diff on hover with no `:focus-visible` or `:active` counterpart) | Add a visible `:focus-visible` or `:active` state (`ui-design.md`). |

### 3. Shell and login

- **Nav indicator: verify only.** v168 owns it. v169 checks that it tracks sidebar collapse and each Text-size step at all three widths, and records the result in `sweep.md`.
- **Top bar** (`shell/shell.css`): a `--panel-border` bottom hairline and a translucent ground, `color-mix(in srgb, var(--surface) 80%, transparent)`. It sits above v168's fixed glow layer in stacking order, so the glow shows faintly through it, and the "before" and "after" shots confirm that.
- **Login** (`shell/login/`): the page sits outside the shell, so v168's glow layer is not present there. Login gets **its own single, static** `--glow-ambient` layer (no drift), giving one glow per page. The card uses `--panel-*` and the button `--btn-fill`.
- **Tape** (`shell/tape/tape.css`): colours only, through tokens. Its scroll and pause behaviour are v168's.

### 4. Gate: `workspace-consistency.spec.ts` extended

Today it reads only the top-level `.ts` files of each workspace directory (`workspace-consistency.spec.ts:8-19`) and skips `gallery`. Extended:
- **Recursive** over each workspace directory (so `analytics/tabs/*`, `dashboard/panels/*` and the like are scanned), excluding `*.spec.ts`. `gallery` is included.
- **Assertion 1:** no heading markup outside `sb-panel-header` / `sb-section-head`. The pattern is the catalogue's detection rule.
- **Assertion 2:** no panel-layout `display: grid` in a workspace's `styles:` unless the same component also carries `sb-stagger`.
- **Exemptions** live in a commented `CONSISTENCY_EXEMPT` map (file → reason), following the `primitives.spec.ts` allow-list convention: a comment above every entry, checked by the existing "every allowlist entry is justified" test pattern. Workspaces whose sources hold no panel at all (e.g. a routes-only `trades` file, `research`) pass because nothing matches, not through an exemption. The spec names the files it scanned, so an empty scan is visible.

## Interaction with v165 and v166

- v165 (calendar day page) and v166 (trade detail reorganisation) are swept **as they stand on `main` when this plan starts**.
- If either is unmerged at that point, its screen is skipped and noted in the index `## Handoff`.
- Whichever of the two merges after this plan's "after" shots **owns its own re-sweep**: that plan's final pre-suite task runs the §2 catalogue and the §2 audit script on its screens.
- v167's required order (its radius inventory waits for v165/v166) means both will usually have merged before v169 starts.
- This spec never edits another plan's worktree.

## Out of scope

- New features, layout redesigns, copy changes and new animation types (v168).
- Palette or token **value** changes (v167). v169 adds no tokens: `--panel-inner-*` belongs to v167.
- **`swingbot/core/marketdata/export_data.py:91`** (export disclaimer grey `#5a6169`, deferred from v167). It is Python, not frontend. It goes into the index `## Handoff` as a standing follow-up: "check the export figure's background, then derive the disclaimer colour from `chart_style.THEME`, covered by `test_chart_theme.py`".

## Testing

- `workspace-consistency.spec.ts` as extended in §4.
- The v167 and v168 gates (colour, radius, G3, motion home, no replay) stay green across all workspaces. That is the **no-regression** proof.
- The **fix** proof is `sweep.md`: every catalogue defect found in "before" has a fix commit and a "clean" mark in "after". Every `audit-targets.mjs` row at 390/768 is resolved or exempted with a reason.
- Each task quotes its narrow run's verdict line (`npx vitest run src/app/workspaces/<ws>` from `frontend/`).
- The plan ends with the single full-suite task.

## Panel review

Run 2026-10-16. senior-engineer reviewed commit `7efd514c`.

- senior-engineer [BLOCKING]: the `workspace-consistency.spec.ts` extension was infeasible as stated (non-recursive, skips gallery, primitives unnamed, no exemption path) -- applied (§4).
- senior-engineer [BLOCKING]: `--panel-inner` was a new token, against this spec's own out-of-scope line -- applied (moved into v167 tier 3 as `--panel-inner-bg`/`--panel-inner-radius`).
- senior-engineer [BLOCKING]: wrong script path; production base and four-width defaults; output naming; 72+ PNGs in git -- applied (§1: explicit flags, local dev server, the partner types the login, PNGs git-ignored, `sweep.md` committed).
- senior-engineer [BLOCKING]: login glow conflicts with v168's one-glow-in-shell rule -- applied (§3: login has its own static layer; v168 notes it).
- senior-engineer: blanket `overflow: clip` on panels crops sticky headers, focus rings and menus -- applied (wrapper only, with an acceptance check).
- senior-engineer: stagger belongs in the shared `sb-panel-grid`; no detection rules for grids or figures -- applied (v168 §3 #2; detection column in §2; headline-only count-up).
- senior-engineer: hover-only and touch-target checks were subjective; gates prove no regression, not fixes -- applied (`audit-targets.mjs`; `sweep.md` as fix proof).
- senior-engineer: "no features" was unenforceable; `## Handoff` location unnamed -- applied (§ Scope rule, diff check, index `## Handoff`).
- senior-engineer: the export-grey follow-up from v167 was dropped -- applied (§ Out of scope, standing follow-up).
- senior-engineer: re-sweep ownership for late v165/v166; which route is "plans" -- applied (§ Interaction; § Scope route list).
- senior-engineer: the nav indicator is v168's work; file names missing -- applied (§3 verify-only; files named).
- senior-engineer: patch vs minor bump is the partner's call -- kept at patch with the reason in the header (the look itself was bumped minor by v167/v168). Open for the partner to override. The `Model:` tier per task is set at plan time per `model-routing.md`.
