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
- **At most ONE subagent at a time, by default.** Dispatch one, wait for it to
  return, then decide whether the next is still needed. Spawning several at
  once requires the human partner to ask for it explicitly — "in parallel",
  "fan out", a stated count — and a plan's `## Parallelisation` section is a
  map of what *could* run concurrently, not standing permission to launch it.
  This is a budget rule, not a style one: each agent is a full context that
  re-derives what this session already knows, several at once can exhaust the
  session limit mid-task (which has happened here, killing three of five
  audits and losing their work), and the results land as one undigested wall
  the controller must triage anyway. One agent, read its findings, act,
  repeat — the serial version is usually faster in wall-clock terms too,
  because the first result routinely changes what the second should even
  look for.
- Skip `frontend-design`/`dataviz` conventions for the admin UI unless asked —
  it follows the existing TradingView-style theme.
