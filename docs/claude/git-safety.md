# Git safety — branches you must never delete

Referenced from the root `CLAUDE.md`, which carries the hard rule. This file is
the evidence behind it.

## The rule

**Any branch with `backup` in its name is off limits to every destructive git
command** — `branch -d`, `branch -D`, `push --delete`, and pruning that would
remove it. No exceptions, no "but it looks merged". Ask the human partner; do
not decide.

The same care applies to `stable-*` branches. They are rollback points, not
topic branches, and "already merged" is not what they are for.

## "Merged" is the wrong test for deletable

This repo proves it. `backup-main` and `origin/cleanup-gate-fixtures` are the
same commit (`496caa1`) and carry **242 commits that are not on `main`** — the
entire gatekeeper-v7 line, built to 86/90 and then rolled back by `c84924a`.
`main` deliberately does not contain them. Deleting either branch destroys the
only copy.

A related near-miss is already on record: local `main` was once **135 commits
behind `origin/main`**, where a force push would have destroyed them. Fetch and
compare against `origin/main` before any status claim, commit or push.

## Before ANY branch deletion

```bash
git rev-list --count main..<branch>    # commits that would be lost
```

Non-zero means **stop**. Zero means it is *merged*, which makes deletion safe
only for a topic branch you created for this task — never for a `backup*` or
`stable-*` branch, whose whole purpose is to hold a state `main` moved past.

## The one deletion that is routine

Once a plan's own worktree branch is merged to `main`, remove that worktree and
branch as part of the same close-out:

```bash
git worktree remove <path>
git branch -d <branch>      # -d, not -D
```

`-d` is the point: it refuses unless the branch is actually merged, and that
refusal is your confirmation. This applies to the plan's own topic branch only.

## Stable markers

`stable-YYYY-MM-DD` exists as **both a branch and a tag locally, but usually
only the tag reaches `origin`**. Check both, and push both explicitly when
creating one.
