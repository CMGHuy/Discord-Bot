# v202 UI shell cockpit, part 3: full suite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md)
**Index:** [`_0-index.md`](2026-10-29-v202-ui-shell-cockpit_0-index.md): Goal, Global Constraints, Review Focus, Parallelisation and every cross-task contract live there and bind the task below.

Part scope: V202-9, the plan's one full-suite run after V202-1 … V202-8. `<wt>` is the implementation worktree's absolute path.

# Phase 4: Verification

### Task V202-9: Full suite once (the bump is `/close-out`'s)

**Model:** haiku — runs the gates once and routes any failure back to its owning task; no design judgement.

**Files:**
- Modify only when a check below fails: the owning task's files from the index ledger (V202-1 … V202-8, V202-1b and V202-6b included), never a file outside the ledger. No new files. `VERSION.json` is not touched: `/close-out` resolves `Bump: ui minor, bot patch`.

**Interfaces:**
- Consumes: every task of v202. `GET /api/v1/live` (V202-1, V202-1b, V202-3), the routes and redirects (V202-4), the nav model (V202-6, V202-6b), the More sheet, palette and phone tab bar on `NAV_ENTRIES` (V202-7), and `sb-section-tabs` (V202-8).
- Produces: the green full-suite verdict line for `/close-out`. v203 (`2026-10-29-v203-ui-shell-cockpit-dock_0-index.md`) starts only once this plan is merged.

- [ ] **Step 1: Check the branch is complete and clean**

Run: `git -C <wt> status --porcelain` and `git -C <wt> log --oneline main..HEAD`
Expected: status prints nothing. The log shows at least one commit per task V202-1, V202-1b, V202-2 … V202-6, V202-6b, V202-7, V202-8 (10 tasks; more if a reviewer fix-up landed).

- [ ] **Step 2: Sync the database replica**

The full suite includes the Postgres tier (`tests/live_api/` among others). If this session has not synced it yet, the controller runs `/replicate-prod-db` into the one shared `swing-db` container first. No per-task container or database.

- [ ] **Step 3: Complexity and plan gates**

Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: exit 0. `swingbot/admin/api_v1/live.py` and `swingbot/admin/api_v1/live_events.py` are measured, and no function is at 15 or above.

Run: `python <wt>/scripts/dev/plan_lint.py <wt>/docs/superpowers/plans/2026-10-29-v202-ui-shell-cockpit_0-index.md`
Expected: `PASS`.

- [ ] **Step 4: SPA lint and build**

Run: `npm --prefix <wt>/frontend run lint`
Expected: exit 0. Any `eslint-suppressions.json` entry left for `NAV_GROUPS` names only `shell/shell.ts` (the rail, rewritten by v203's V203-1).

Run: `npm --prefix <wt>/frontend run build`
Expected: exit 0, no new warnings.

- [ ] **Step 5: Full suite once**

Dispatch the `test-runner` subagent with: `python <wt>/scripts/dev/testrun.py full`
Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`testing-cost.md`). The run includes the new `live-api` suite (V202-1) and every co-located `*.spec.ts`.

- [ ] **Step 6: On a failure, fix in the owning task and re-run alone**

Find the task whose ledger row lists the failing file. Fix it there, then re-run only that test: `python <wt>/scripts/dev/testrun.py file <test path>` (or `npm --prefix <wt>/frontend test -- --watch=false --include <spec path relative to frontend/>`). Never re-run the whole suite, and never edit a file outside the ledger. If a fix crosses two tasks' files, stop and report it to the controller.

- [ ] **Step 7: Record the verdict**

Append one line to `.superpowers/sdd/progress.md` (append only, never rewrite):

```text
2026-10-29 v202 V202-9 full suite: <passed> passed, 0 failed, 0 xfailed (<duration>) on <wt branch> @ <short sha>
```

- [ ] **Step 8: Commit (only if Step 6 changed files)**

```bash
git -C <wt> add <each fixed path, explicitly>
git -C <wt> commit -m "fix(v202): <what the full suite caught>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

With no fix, there is nothing to commit. The controller runs `/close-out`.
