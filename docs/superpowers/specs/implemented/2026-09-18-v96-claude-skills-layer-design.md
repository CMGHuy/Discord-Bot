Version: ui 1.18.4 · bot 1.9.4
Bump: none
Edge: none (integrity)
Depends on: nothing. Touches `.claude/` and `docs/claude/` only; no bot or UI
code, no data, no production surface.

# v96 — The skills layer: turning read-before-you-work prose into rules that fire

## 1. Why

This repo's operating knowledge lives in three places with three different
enforcement strengths, and the strongest rules sit in the weakest place.

| Where | Lines | Fires |
|---|---|---|
| `CLAUDE.md` | <200 | Always — loaded every session |
| `.claude/hooks/guardrails.py` | ~240 | Mechanically, at `PreToolUse`, as a **deny** |
| `docs/claude/*.md` | 1,724 | Only when a session remembers to read it |

The third row is the problem. 1,724 lines of the most expensive lessons this
repo has learned — the v72 six-clause acceptance gate, the closed
pre-registration table, the version counter that concurrent sessions race, the
rule that a live production fix must be mirrored back before the task is done —
are on the honour system. `CLAUDE.md` names each file and says "read before
working in that area." That instruction is correct and it is not a mechanism.

The failures this produces are documented, not hypothetical:

- **`/task-brief` exists because of one of them.** Briefs generated from plan
  files shipped wrong symbol assumptions in E7, E8, E17, E18, E30, E35, E45,
  E46, E48 and E49 — ten occurrences, every one caught by hand. The skill
  turned a remembered check into a mechanical one and the class stopped.
- **Stale pooled numbers have shipped twice.** The 2026-09-10 badge refresh
  demoted Fibonacci, RSI and Support-Resistance from VALIDATED to WEAK, which
  invalidated pooled figures quoted elsewhere; the live-book ExpR of −0.136R
  over N=782 is routinely re-quoted from memory rather than re-derived.
- **The one rule `CLAUDE.md` marks "hard rule, no exceptions" is entirely
  unenforced.** `guardrails.py` covers unscoped globs, root-level recursive
  grep, cross-worktree writes, huge-plan reads, bare `pytest`, and `cat` of the
  big docs. It has **no branch-deletion rule at all**. "Never delete a branch
  whose name contains `backup`" is prose, and prose is what a session skips
  when it is confident.

Skills are the missing layer between *documented* and *enforced*. This spec
designs that layer: eleven skills and three hook rules, ranked, with the
mechanism chosen per item rather than uniformly.

`Edge: none (integrity)`. This buys no edge and is worth building — it exists so
that the work which *does* buy edge cannot be silently invalidated by a rule
nobody re-read.

## 2. What exists today

- **Skills (2):** `gate`, `task-brief` — both `disable-model-invocation: true`,
  so both fire only when typed.
- **Subagents (3):** `backtest-runner`, `symbol-verifier`, `test-runner`.
  **Not extended by this spec**, per the one-agent-at-a-time budget rule in
  `skills-tools.md`.
- **Hooks (4):** `guardrails.py` (`PreToolUse`, 6 rules, fails open by
  construction), `session-cursor.ps1`, `notify.ps1`, `usage-watch.ps1`.
- **Reference docs (10):** `docs/claude/*.md`, none auto-loaded.
- **Tests:** `tests/hooks/test_guardrails.py` already unit-tests the hook.

## 3. The inventory

Ranked by the cost of the failure prevented, not by effort. Three tiers, each
with its own invocation model.

### 3.1 Tier 1 — Integrity gates (model-invocable)

These fire unprompted. That is the entire reason they are worth building: a gate
that waits to be typed is a gate the confident session walks past.

1. **`backtest-gate`** — fires before any backtest, grid, walk-forward or
   validation run, and before interpreting one. Step 1 reads
   `backtest-methodology.md`. Enforces the v72 six-clause acceptance gate, the
   four-stage funnel, TRAIN/VALIDATION separation, frozen constants, and a hard
   stop against the closed pre-registration table at
   `backtest-methodology.md:123`. **Highest-value item in this spec** — it is
   the only one where the failure ships a false edge into a live book.
2. **`no-lookahead`** — fires on edits to entry-signal and feature computation
   under `swingbot/core/market/`, `swingbot/core/edge/`,
   `swingbot/core/scanning/`. Lookahead bias is the bug class that silently
   inflates every downstream number and displays nothing.
3. **`pooled-numbers`** — fires when a pooled ExpR, win rate, sample size or
   badge tier is about to be stated. Requires re-derivation from the live book;
   forbids quoting a figure from a document.
4. **`mirror-prod`** — fires on any state-changing command against
   `167.233.26.185`. Enforces `CLAUDE.md`'s rule that a live fix is mirrored
   into the repo and committed before the task is done.

### 3.2 Tier 2 — Rituals (slash-only, `disable-model-invocation: true`)

Multi-step chores with an exact correct sequence and no judgement in them.
Zero triggering risk; pure keystroke and error saving.

5. **`/close-out`** — resolve `Bump:` against the `VERSION.json` on disk (never
   a plan header, never memory), increment only the named line, stamp
   `*_updated`, regenerate `version_history.json` via
   `scripts/dev/build_version_matrix.py` **in the same commit**, move the plan
   to `implemented/`, remove the worktree. The last five commits on `main` are
   this sequence executed by hand.
6. **`/new-doc`** — create a spec or plan: recompute the repo-wide counter with
   the canonical `find` + `git log` command **immediately before** the commit,
   write the `Bump:`/`Edge:` (and, for a spec, `Version:`) header block, add
   `## Parallelisation`, honour the 1500-line-per-file cap by splitting, use
   `### Task N:` and `# Phase N —` (one hash) so the document stays greppable,
   and commit on `main` rather than a branch.
7. **`/deploy`** — the Hetzner sequence from `docs/deploy/DEPLOY_HETZNER.md`:
   build, two containers off one image, `.env` SIGHUP hot-reload versus a
   restart, post-deploy verification. Pairs with `mirror-prod`.

### 3.3 Tier 3 — Seam briefings (model-invocable, narrow descriptions)

Just-in-time architecture, so a fresh session works in the right layer without
reading ten reference docs first.

8. **`edge-module`** — adding or changing a strategy/edge module: the registry,
   badge tiers, the entry-signal single source, the scan-pipeline insertion
   point. Reads `architecture.md`.
9. **`alert-surface`** — `scan_engine` / `scan_embeds` / `embeds.py`: the two
   OHLCV caches, the legacy shims, the silent no-ops, and that an empty table
   is a measured answer rather than a stub. Reads `known-traps.md`.
10. **`schema-change`** — the Postgres strangler pattern, per-store migration,
    and `parity_report` as the only verifier to trust.
11. **`worktree-lifecycle`** — naming, never editing a worktree from the main
    tree, teardown at close-out, and pausing before merging a branch a
    concurrent session may hold. Reads `document-lifecycle.md` and
    `working-conventions.md`.

### 3.4 The cut line

**Items 1–8 are the committed scope.** Items 9–11 are the ones whose underlying
docs a session would plausibly just read, and Phase 4 is built so they can be
dropped without leaving anything half-finished.

## 4. Skill anatomy — the thin loader

Every skill in this spec has the same five parts. Uniformity is the point: a
reviewer can diff one against another and see immediately what is missing.

```markdown
---
name: backtest-gate
description: <trigger-shaped — see §5>
# Tier 2 only:
# disable-model-invocation: true
---

# <Title>

## Step 1 — Read the authority
`docs/claude/backtest-methodology.md` — the six-clause gate and the closed
pre-registration table. Read it before anything else in this skill.

## Step 2..N — Procedure
Exact PowerShell commands, in order.

## The gate
What "pass" means, stated mechanically. No adjectives.

## Known wrong turns
| Tempting | Reality |

## Trigger table
Should fire: … · Should not fire: …   (Tier 1 and 3 only — see §7)
```

**The hard constraint: no `SKILL.md` restates a threshold, table, constant or
acceptance clause that lives in `docs/claude/`.** It cites the file and line and
sends the reader there. This is what stops the skills layer becoming a third
source of truth that drifts — the failure mode that would make this spec a net
negative. `/gate` and `/task-brief` already read this way; it is the house
style, not a new convention.

**Budget: 80 lines per `SKILL.md`.** A loader that needs more is carrying
content that belongs in `docs/claude/`, and the fix is to move it there and
cite it, never to raise the budget.

## 5. Descriptions — the part that decides whether this works

Tier 1 is only worth building if it fires when a session did not think to ask,
and stays silent otherwise. A skill that loads 80 lines on every message
mentioning "backtest" is a context landmine on a repo that already documents
several. Three rules, all testable by reading the description alone:

1. **Name the trigger action, not the topic.**
   - Wrong: `Backtesting methodology for this repo.`
   - Right: `Use when about to run, re-run or interpret any backtest, grid,
     walk-forward or validation script (run_backtest_range.py,
     tune_strategy.py) — before the command, not after.`
2. **Put the literal script paths and flag names in the description.** Matching
   runs on token overlap, and `tune_strategy.py`, `--exit-model`, `--scale-out`
   are the strings that actually appear when the trigger is real.
3. **Add an explicit negative clause wherever over-firing is plausible.**
   `Not for reading a backtest result already in context, and not for the test
   suite (use /gate).`

Tier 3 descriptions must name the **directories** they cover, so a briefing
fires on an edit there and nowhere else.

## 6. Hook rules

Division of labour: **a hook is a mechanical precondition and it denies; a skill
is a procedure and it teaches.** Anything checkable from the tool input alone is
a hook rule, because a skill can be reasoned around and a `PreToolUse` deny
cannot. Each deny message names the skill to invoke next.

**The hook's own invariant constrains what may become a rule.**
`guardrails.py`'s docstring states that `evaluate()` reads no files and spawns
no subprocesses — that is precisely why all 44 of its cases are unit-testable
without a live session, and it is not being relaxed for this spec. A check that
needs the filesystem or git belongs in a skill, not the hook. Two candidate
rules were re-shaped by this constraint, and one was moved out entirely.

Three rules, all added to the existing `guardrails.py`, all pure functions of
their tool input, all failing open by construction so `CLAUDE.md` still wins on
disagreement:

- **`branch-safety`** — refs containing `backup`, or matching `stable-*`, on
  `git branch -d/-D`, `git push --delete`, `git update-ref -d`. Closes the
  repo's only "no exceptions" rule. Pure string match, roughly fifteen lines.
- **`closed-preregistration`** — a backtest or grid command naming a **closed
  knob**. Not `--strategy "<name>"`: the table closes *specific mechanisms*,
  and several rows name a strategy whose other hypotheses remain open
  (`Break & Retest` is closed for a `{2m,3m,4m}` horizon gate and open for
  anything else), so matching on strategy name would deny legitimate work
  daily. The rule matches the **knob tokens** the table closes —
  `DEAD_CAT_BOUNCE_VETO`, `EARNINGS_BLACKOUT_SESSIONS`,
  `EFFECTIVE_CONFLUENCE_ENABLED`, `LEVEL_TOUCH_STRENGTH`,
  `DATA_DRIVEN_STOPS_ENABLED`, `AVWAP_LEVELS_ENABLED`, `REGIME_ALLOW`,
  `FIB_TARGET_1_0_EXTENSION` and the rest — appearing in a `--grid` or env
  assignment on `tune_strategy.py` / `run_backtest_range.py`. Those are
  unambiguous: a closed knob back in a grid is a re-run by definition.

  The tokens live as a **constant in `guardrails.py`**, keeping `evaluate()`
  pure. Drift is caught by a **bidirectional test**: every token in the
  constant must appear in `backtest-methodology.md`, and every backtick-quoted
  `ALL_CAPS_TOKEN` inside the closed-pre-registration table must appear in the
  constant — so a row added to the doc fails the suite until the constant
  catches up. The reverse half cannot see lower-case knobs
  (`min_level_touches`, `confirm_bars`); those are covered by the forward half
  only, and that limit is stated rather than papered over. The doc stays the
  single source of truth per §4; the check moves from call time to suite time,
  where it costs nothing and still cannot silently rot.
- **`plan-doc-shape`** — on a write to `docs/superpowers/specs/` or `plans/`:
  deny a filename that does not match `YYYY-MM-DD-vN-<name>.md`, and deny
  content containing `## Phase ` at line start. The second half is the exact
  failure `document-conventions.md` records for v24 and v25 — a plan written
  with two hashes returns **zero** for `grep -n "^# Phase"` and is invisible to
  the tooling that exists to keep it out of context. Both halves are pure
  string checks on `file_path` and `content`.

**Moved out of the hook: the version-collision check.** Knowing whether a `vN`
is already taken requires reading two directories and `git log --all`. It stays
where it already belongs — a mandatory step of **`/new-doc`** (§3.2, item 6),
run immediately before the commit, exactly as `document-conventions.md`
prescribes. The hook catches the shape; the skill catches the race.

Each rule lands with cases in the existing `tests/hooks/test_guardrails.py` —
one that denies, one that allows, one that proves it fails open on malformed
input.

**Override.** `closed-preregistration` denies a run that is sometimes
legitimate (reproducing a past result). The deny message states the escape and
the escape requires the human partner to authorise it explicitly. Consistent
with `git-safety.md`: ask the human partner, do not decide. A session cannot
self-clear this one.

## 7. Proving a skill actually fires

Without this step, "model-invocable" is a hope rather than a property.

Each Tier 1 and Tier 3 skill carries a **trigger table** in its own body: about
four prompts that must fire it and about four near-misses that must not. The
near-misses are the valuable half — they are what a reviewer checks the
description against.

**Works.** The Phase 0 spike (Task S2) confirmed `claude plugin eval` accepts a
path straight to a repo-local skill directory as its target — no
`.claude-plugin/plugin.json` manifest required. `claude plugin eval
.claude/skills/<skill-name>` resolves that directory as the plugin under test,
loads an `evals/` suite beneath it, and runs it (a throwaway two-case suite
against `.claude/skills/gate` scored and reported cleanly: `claude plugin eval
.claude/skills/gate --runs 1 --no-publish --trust-plugin`). Each skill's
trigger table becomes that skill's eval corpus: one `evals/<case>/prompt.md` +
`graders/*.md` pair per table row, fires and near-misses alike. Wiring the
existing trigger tables into real `evals/` suites is follow-up work for
Phase 4, not this spike.

## 8. Source of truth, sync, and the 200-line ceiling

- **The inventory table lives in `docs/claude/skills-tools.md`** (34 lines
  today), which is already the file `CLAUDE.md` points at for exactly this
  question. `CLAUDE.md` is at its line limit by design and gains at most one
  amended line, noting that the integrity tier now fires unprompted.
- **`.codex/AGENTS.md` gets a condensed mirror**, one-way and Claude-authored
  per `CLAUDE.md`. Codex must know the hook rules exist or it will hit denies
  it cannot explain. Condensed, not copied.
- **No `docs/claude/*.md` file is deleted or emptied** by this spec. They remain
  the authority; the skills point at them.

## 9. Non-goals

- **No new subagents.** The three that exist are sufficient and the
  one-at-a-time budget rule constrains that surface deliberately.
- **No testing skill.** `/gate` covers it.
- **No frontend-design or dataviz conventions** for the admin UI —
  `skills-tools.md` waives them explicitly.
- **No git-safety *skill*.** There is no judgement in "do not delete that
  branch"; it is a hook rule and nothing else.
- **No change to bot or UI behaviour.** Hence `Bump: none`.

## 10. Risks and rollback

| Risk | Severity | Mitigation / rollback |
|---|---|---|
| A Tier 1 skill over-fires, loading 80 lines on every message | The real one | Trigger tables (§7) catch most of it pre-merge. Rollback is **one line** — add `disable-model-invocation: true` and the skill demotes to slash-only. No code change, no revert, no lost work. |
| A skill drifts from its `docs/claude/` authority | High, and silent | The no-restatement rule (§4), plus a check that no `SKILL.md` contains a bare numeric threshold. |
| `closed-preregistration` denies a legitimate reproduction | Medium | Documented escape, authorised by the human partner only (§6). |
| The closed-name constant drifts from `backtest-methodology.md` | Medium | The drift test (§6) fails the suite the moment the doc and the constant disagree. |
| `plan-doc-shape` denies a legitimate non-conforming write | Low | The two patterns it denies are both unconditional rules in `document-conventions.md`; a legitimate violation does not exist. Fails open like the rest. |
| Eleven descriptions permanently resident in context | Negligible | ~500 tokens total. Named here so it is a measured answer rather than an unknown. |

## 11. Parallelisation

- **Sequential: Phase 0 before everything.** It fixes the loader template, the
  description rules and the `skills-tools.md` table skeleton; every later task
  fills that template in.
- **Sequential: Phase 1 before Phase 2.** Tier 1 deny messages name the skills,
  and the skills cite the hook behaviour.
- **Sequential within Phase 1**, despite the three rules being unrelated: all
  three edit `guardrails.py` and `tests/hooks/test_guardrails.py`, and the
  disjoint-files test is about files, not subject matter. Stated explicitly so
  the next session does not re-derive it and dispatch them concurrently.
- **Group B (parallel), Phase 2:** `backtest-gate`, `no-lookahead`,
  `pooled-numbers`, `mirror-prod` — one new directory each, no shared file, no
  contract dependency.
- **Group C (parallel), Phase 3:** `/close-out`, `/new-doc`, `/deploy` — one
  new directory each.
- **Group D (parallel), Phase 4:** `edge-module`, `alert-surface`,
  `schema-change`, `worktree-lifecycle` — one new directory each.
- **Sequential: the `skills-tools.md` table and the `.codex/AGENTS.md` mirror
  last**, after the final skill lands, because both enumerate what shipped.

## 12. Acceptance

1. `tests/hooks/test_guardrails.py` covers all three new rules, including one
   fail-open case each, and the full suite is green (`0 failed`, `0 xfailed`).
2. `git branch -D some-backup-branch` is denied, with a message naming the
   rule and pointing at `git-safety.md`.
2a. `evaluate()` still reads no files and spawns no subprocesses — the three
   new rules are pure functions of their tool input, and the closed-name drift
   test is the only thing that touches `backtest-methodology.md`.
3. Every shipped `SKILL.md` is at most 80 lines and contains no numeric
   threshold that `docs/claude/` owns.
4. Every Tier 1 and Tier 3 skill carries a trigger table with at least three
   should-fire and three should-not-fire entries.
5. `docs/claude/skills-tools.md` lists every shipped skill with its tier and
   invocation model; `CLAUDE.md` remains under 200 lines.
6. `.codex/AGENTS.md` names the three hook rules.
