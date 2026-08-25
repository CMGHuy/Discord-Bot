# Skills and tools for this repo

Referenced from the root `CLAUDE.md`.

- `superpowers:subagent-driven-development` — the plans in
  `docs/superpowers/plans/` are written for it (`### Task E42` + checkboxes).
  This is the default loop for plan execution; its `task-brief` and
  `review-package` scripts are what keep giant plans out of context.
- `superpowers:test-driven-development` — matches how entry filters get built
  here (fixture first, REPL-tune until the ungated function fires, freeze).
- `superpowers:systematic-debugging` — before any "fix" to a backtest number
  or a failing gate; guessing at these is expensive.
- `superpowers:verification-before-completion` — this repo has a documented
  history of tasks marked done that weren't. Verify against `git log` and the
  actual files.
- `superpowers:brainstorming` then `superpowers:writing-plans` for new
  components, so the result matches the existing plan format.
- `Explore` subagent for wide code searches; `feature-dev:code-reviewer` or
  `/code-review` for review passes.
- **One subagent at a time** unless the human partner explicitly asks for
  several — the rule and its reasoning live in the root `CLAUDE.md`'s "Repo
  tooling" paragraph. A plan's `## Parallelisation` section maps what *could*
  run concurrently; it is not permission to launch it.
- Skip `frontend-design`/`dataviz` conventions for the admin UI unless asked —
  it follows the existing TradingView-style theme.
