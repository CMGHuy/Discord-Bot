---
name: worktree-lifecycle
description: Use when creating, entering, merging or removing a git worktree in this repo, or before merging a branch another concurrent session may be working on. Multiple sessions share this working tree, so a merge or a cross-worktree edit can silently overwrite another session's work. Not for ordinary commits on the current branch.
---

# Worktree lifecycle

## Step 1 — Read the authority

`docs/claude/document-lifecycle.md` for naming and removal, and
`docs/claude/working-conventions.md` for the concurrent-session rules. This
skill is a checklist over both; it does not restate their reasoning.

## Step 2 — Never edit a worktree from the main tree

`guardrails.py`'s `_rule_worktree_write` denies an Edit/Write/NotebookEdit
whose target path names a different worktree than the one this session is
running in, and the deny is correct: the edit would land on another branch
and be invisible from here. The same discipline holds in reverse: never edit
a main-tree file from inside a worktree session. Nothing in `guardrails.py`
catches this direction — there is no deny for it — so this is convention,
not tooling.

## Step 3 — Before merging, check whether anyone else is in it

Concurrent Claude sessions in different worktrees of this same repo are
normal here, not an edge case. Before merging a branch you did not spend
this whole session on, run `git worktree list` and check whether its
worktree still exists and looks live (recent commits, uncommitted changes).
Merging on the assumption that a branch is idle is how another session's
in-progress work gets silently clobbered. When in doubt, pause and confirm
with the human partner rather than proceeding.

## Step 4 — Removal belongs to close-out, not to "I am done for today"

A worktree is not cleaned up as a side effect of finishing a session in it.
Removal is a deliberate step tied to the plan closing, with its own ordering
against the version bump and the document move — invoke `/close-out` rather
than running `git worktree remove` by hand.

## The gate

The output of `git worktree list` matches the live plan list: every worktree
still on disk names a plan still at the top level of
`docs/superpowers/plans/`, and nothing sits there orphaned from a plan that
already moved to `implemented/` or `no-lift/`.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "The branch looks merged, I'll clean it up" | Confirm with `git rev-list --count main..<branch>` first — a non-zero count means it isn't. |
| "It has 'backup' in the name but it looks stale" | Hard rule, no exceptions: ask the human partner, never decide this yourself. |
| "I'll just edit the file directly, it's the same repo" | It is not — it's a different branch checked out in a different directory; the edit is invisible from here. |

## Trigger table

Should fire: creating a new worktree to start plan execution.
Should fire: merging a feature branch back into `main`.
Should fire: cleaning up worktrees after a plan closes.
Should not fire: committing on the branch this session is already working in.
Should not fire: running `git status` to check the current tree.
Should not fire: reading a file inside the current worktree.
