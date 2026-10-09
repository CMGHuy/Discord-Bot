---
name: panel
description: Dispatch expert role reviewers (/panel role[,role...] target) over a spec, plan, diff or backtest result, one at a time through the expert-reviewer agent, and merge their findings. Run as /panel, or by Claude itself right after committing a spec that carries a Panel header line, and before /close-out of a plan built from such a spec.
---

# Expert panel

## Step 1 — Read the authority

`docs/claude/skills-tools.md` § Expert roles holds the roster and each role's
reviewer model. `docs/claude/document-conventions.md` § The header block holds
the `**Panel:**` line. This skill is the checklist; the reasoning lives there.

## Step 2 — Resolve the roles and the target

Roles come from the argument, or from the spec's `**Panel:**` line when Claude
runs this itself. Every role must be a row of the roles table; an unknown role
stops the panel and names the valid ones -- never substitute a near match. The
target is one or more paths, or a git range (`main...<branch>`).

## Step 3 — Dispatch serially

For each role, in the order given, dispatch the `expert-reviewer` agent with
`role=<role>`, the target, and that role's reviewer model from the roles table
as the `model` override. In Codex, pass the mapped model and effort from the
AGENTS.md "Model tiers" table. Wait for it to return before dispatching the
next: serially, one at a time (`skills-tools.md`). Never fan out, even for
three roles.

## Step 4 — Merge

Drop every finding that cites no `file:line`, git range or doc section. Merge
duplicates across roles, keeping the stricter tag. List `BLOCKING` first, then
`ADVISORY`, each line naming its role. A role that returned `CLEAN` is listed
as clean, not omitted.

## Step 5 — Record the outcome

- **Spec review** -- after the spec is committed, before the partner reviews
  it. Revise the spec for each finding you accept, then append a
  `## Panel review` section listing every finding as `<role>: <one line> --
  applied` or `-- rejected: <why>`. Commit on `main`.
- **Pre-close-out** -- the plan's full diff (`main...<branch>`, or
  `<merge>^1...<branch>` once merged) and its recorded results. An unresolved
  `BLOCKING` finding stops `/close-out`: fix it on the branch, or record it in
  `.superpowers/sdd/progress.md` as `rejected: <why>`.
- **On demand** -- return the merged list; record nothing unless asked.

## The gate

Every role returned; every surviving finding cites evidence; every `BLOCKING`
finding is applied or rejected with a reason before the step it guards.
