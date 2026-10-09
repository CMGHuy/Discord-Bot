# Model routing — which model implements a plan task

Referenced from the root `CLAUDE.md`. Introduced by v145
(`docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md`).
Before it, every implementation task ran on `task-implementer`'s pinned
`sonnet`: a version bump and an entry-signal rewiring got the same model.

## The stamp

In every plan numbered **v146 or above**, the first line under each
`### Task` heading is:

```
**Model:** <haiku|sonnet|opus> — <one-clause reason>
```

- `plan-writer` writes it, from the rubric below.
- `/task-brief` copies it to the top of the brief.
- The controller passes the tier as the `model` override when it dispatches
  `task-implementer`. The agent's own default stays `sonnet`, so a dispatch
  without an override behaves as before.
- `tests/hooks/test_plan_model_stamp.py` fails a plan above v145 with any
  task, in any part, whose first non-blank line is not a valid stamp. Plans
  v145 and earlier are exempt by number and never retrofitted.

## The rubric

| Tier | A task gets it when… | Examples |
|---|---|---|
| `haiku` | Fully specified, no judgement, the diff is fixed by the brief | Doc/config edits, `VERSION.json` bump, a fixture, a rename, a copied pattern |
| `sonnet` (default) | A normal TDD task inside one module, with the behaviour given by the spec | A new metric, an embed field, a store method, an admin endpoint |
| `opus` | Any of: entry signals or no-lookahead territory, a schema migration, crosses at least 2 `swingbot/core` packages, splits a legacy function at complexity ≥ 15, statistical code that feeds a gate | Edge module wiring, an Alembic revision, a backtest gate change |

When a task matches more than one row, **the higher tier wins**.

Review is never weaker than the implementation: `task-reviewer` stays on
`sonnet` whatever the task's tier. Expert reviewers (`expert-reviewer`,
dispatched by `/panel`) run at their role's model from `skills-tools.md`
§ Expert roles, never on haiku.

## The escalation ladder

This replaces the old rule "a task that fails review twice is implemented by
Opus directly".

1. `task-reviewer` returns blocking findings: `SendMessage` the same
   implementer once, at the same tier.
2. Still blocking: dispatch a **fresh** implementer **one tier up**
   (haiku → sonnet → opus), with the findings attached.
3. Still blocking at opus: Opus implements the task inline in the main
   session.

Log each escalation as one line in `.superpowers/sdd/progress.md`:

```
<task id>: <from>→<to> (<reason>)
```

for example `V146-4: sonnet→opus (review: rolling window reads bar k+1)`, and
`V146-4: opus→inline (review: same finding after re-dispatch)` for step 3.

## Retuning the rubric

The escalation lines are the evidence. Retune the rubric here, in its own
commit that cites the lines that motivated it — never per task, and never by
editing a plan's stamps after the fact.
