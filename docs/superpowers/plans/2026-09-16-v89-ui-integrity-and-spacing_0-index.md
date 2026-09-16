# v89 Admin UI Integrity and Spacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-16-v89-ui-integrity-and-spacing-design.md`
**Bump:** ui patch
**Edge:** none (integrity)

**Goal:** Make every number the admin UI shows mean what its label says, and give every workspace one spacing rule between panels.

**Architecture:**
- **Four shared frontend pieces land first:** the `--section-gap` token plus a global `.sb-stack` class, two static guard specs, one `sb-bar-list` chart component, and one `sb-inline-md` formatter.
- **Four backend changes follow, in the admin API only:**
  - Admin expectancy and win rate come from `core/analytics/metrics`.
  - Total, annualised and monthly returns and Calmar come from the account equity walk.
  - The exit-quality endpoint returns the close-reason strings it cannot map.
  - The trades list returns `prices_as_of`.
- **Then one task per workspace file,** applying that workspace's integrity items and the spacing rule together, since both edit the same component.
- **The plan ends** with the full suites, a deploy the partner approves, a live gap audit, and the exit-reason mapping built from the strings production reports.

**Tech Stack:** Angular 21 (standalone, signals, zoneless), Vitest through `ng test`, Python 3.11, Flask, pytest.

## Global Constraints

- **Worktree:** `.claude/worktrees/2026-09-16-v89-ui-integrity-and-spacing/`, branch `2026-09-16-v89-ui-integrity-and-spacing`, created from `main` at UA1. Every command in Parts 1–4 runs with that worktree as the working directory. Never `cd` in a Bash command; use `git -C` or absolute paths.
- **Spacing rule (spec §4.2):**
  - `--section-gap` is `--space-20`, and `--space-14` below 640px.
  - It is the gap between sibling panels, vertical and horizontal, in both registers.
  - Panels, panel rows and section headings carry no outer `margin-top`/`margin-bottom`/`margin-block`.
  - Tile groups use `--space-10`.
  - Off-scale `1px`/`2px` gaps and paddings become `--space-4`; hairline borders are exempt.
- **Expectancy on admin surfaces is `metrics.expectancy_r`** (per trade, legs blended, scratches included). **Win rate is `metrics.win_rate`.** Every tile or row showing either also shows its N.
- **Do not change `swingbot/core/tracking/performance.py`.** Its `stats` expectancy feeds plan confidence (`scanning/plan_table.py`), which is bot behaviour. It is out of scope (spec §3.3).
- **Account returns** (total, annualised, Calmar, by month) are computed from `metrics.equity_curve` over `base_balance` from `account.load_account_config()`, rebased to the balance at the range start.
- **The exit-reason mapping is exact-match only.** Never add a substring or fuzzy fallback (`metrics._exit_reason_bucket` docstring).
- **No `innerHTML`** for server-provided text. Bold is rendered by splitting into segments.
- **Component style budget:** `anyComponentStyle` errors at 8 kB (`frontend/angular.json`). Any task adding CSS to `analytics.ts` must delete at least as much as it adds.
- **Per-task checks:**
  - Python: `python scripts/dev/testrun.py file <test file>`.
  - Frontend: `npm --prefix frontend test -- --include <spec path relative to frontend/>`.
  - Each suite runs in full **once**, in UA14.
- **Commits:** messages start `feat(v89):` / `fix(v89):` / `test(v89):` / `docs(v89):` and end with the session's attribution lines.
- **Never run `scripts/ops/ssh-hetzner.sh` without a command argument.** Production reads in this plan go through the admin API in a logged-in browser, not SSH.

## Parts

| File | Tasks | What |
|---|---|---|
| `_1-foundation.md` | UA1–UA3 | spacing token, stack class and guard specs; `sb-bar-list`; `sb-inline-md`, gauge/donut fixes, one pager count per table |
| `_2-backend.md` | UA4–UA7 | expectancy/win-rate unification with N; account-based returns; unmapped exit reasons; `prices_as_of` |
| `_3-workspaces.md` | UA8–UA12 | Dashboard; Risk; Trades + Trade detail; Calendar; Watchlist + System + Versions |
| `_4-analytics.md` | UA13 | Analytics workspace and store |
| `_5-verify-and-close.md` | UA14–UA17 | audit script + full suites + merge; deploy + live audit; exit-reason mapping from live strings; close-out |

## Parallelisation

- **Sequential first:** UA1 → UA2 → UA3.
  - UA1 introduces `--section-gap`, `.sb-stack` and the two guard specs that every later frontend task must keep green.
  - UA2 creates `ui/bar-list.ts`.
  - UA3 edits `ui/pagination.ts` and `ui/data-table/data-table.ts`, which the Trades task (UA10) depends on.
- **Group A (parallel, may start any time after UA1):** UA4, UA5, UA6, UA7. They are backend-only.
  - UA4 edits `admin/api_v1/dashboard.py` and the `analytics.py` top-level block.
  - UA5 edits `metrics.py` return functions and the `analytics.py` `derived`/`calendar` lines.
  - UA6 edits `metrics.py` exit-reason functions and the `analytics.py` exit-quality route.
  - UA7 edits `admin/api_v1/trades.py`.
  - **UA4, UA5 and UA6 all touch `admin/api_v1/analytics.py`,** and UA5 and UA6 both touch `metrics.py`, but in disjoint functions. Run them in one session, one after another (UA4 → UA5 → UA6), or give each its own worktree branch and merge. Only UA7 is truly independent.
- **Group B (parallel, after UA3 and after the Group A task each one consumes):**
  - UA8 Dashboard (consumes UA4, UA7)
  - UA9 Risk (consumes UA1 only)
  - UA10 Trades + Trade detail (consumes UA3)
  - UA11 Calendar (consumes UA1 only)
  - UA12 Watchlist + System + Versions (consumes UA1 only)

  Each owns disjoint workspace files. **UA8 also edits `api/models.ts`,** and so do UA13 and UA7's consumer lines. To stay parallel, UA8 adds its fields in one contiguous block under `interface Dashboard`, and UA13 edits only `AnalyticsPerformance`, `AnalyticsExitQuality` and the calendar row type.
- **UA13 Analytics** runs after UA2, UA3, UA4, UA5 and UA6. It consumes `sb-bar-list`, `sb-inline-md`, the N fields, the new calendar row shape and `unmapped_reasons`.
- **Strictly sequential:** UA14 (after everything above) → UA15 (deploy needs a merged, green `main` and the partner's go-ahead) → UA16 (needs production's unmapped strings) → UA17.

## Task index

| ID | Task | Part |
|---|---|---|
| UA1 | `--section-gap`, `.sb-stack`, confirm-dialog `display: contents`, token and margin guard specs | 1 |
| UA2 | `sb-bar-list` (signed and rate modes) | 1 |
| UA3 | `sb-inline-md`; gauge `height`; donut centre fill; one count and per-page selector per table | 1 |
| UA4 | Admin expectancy/win rate/payoff from `metrics`, with `*_n` fields | 2 |
| UA5 | Account-based total/annualised return, Calmar and monthly returns | 2 |
| UA6 | `unmapped_reasons` on `/analytics/exit-quality` | 2 |
| UA7 | `prices_as_of` on `/trades` | 2 |
| UA8 | Dashboard: N on tiles, outcome-coloured activity, freshness, spacing | 3 |
| UA9 | Risk: adaptive risk precision, € at risk, sector-unknown state, scan-health absent state, gauge removed, spacing | 3 |
| UA10 | Trades + Trade detail: count text, markdown, spacing | 3 |
| UA11 | Calendar: future days, today outline, weekday table alignment, spacing | 3 |
| UA12 | Watchlist, System, Versions: spacing and off-scale values | 3 |
| UA13 | Analytics: bar lists, N on Overall, markdown journal, exit-quality warning, by-ticker win rate, labels, spacing | 4 |
| UA14 | Audit script, full suites, merge | 5 |
| UA15 | Deploy (partner approval) and live audit | 5 |
| UA16 | Exit-reason mapping from production strings | 5 |
| UA17 | Close-out: version bump, history, move docs | 5 |
