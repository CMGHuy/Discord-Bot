---
name: prereg
description: "Pre-register a measurement in two phases: before it runs, commit a results-doc stub whose frozen block holds the hypothesis, instrument, metric, N floor, threshold and stopping rule; after it runs, prove the block is unchanged since that commit and append the ledger row. Invoked explicitly as /prereg <id>, never model-triggered."
---
<!-- GENERATED from .claude/skills/prereg/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Pre-registration

The stub's commit hash is the registration, and the second phase never runs
without the first. Arguments: `$ARGUMENTS` (one ledger id, written `<id>`).

## Step 1 — Read the authority

`python scripts/dev/doc_section.py docs/claude/backtest-methodology.md "Funnel stages" "Evidence, registry and ledger"`.
Exit code 2 means a heading is gone: read the whole file instead. Every value
the stub holds is quoted from there; this skill restates none.

## Step 2 — Pick the phase

- `grep -n '"id": "<id>"' docs/superpowers/results/preregistration-ledger.jsonl`
  finds a row: stop. Ledger rows are never edited or repeated.
- `git grep -l -x -F "**Pre-registration id:** <id>" -- docs/superpowers/results/`
  finds nothing: phase Before (Step 3). One doc: phase After (Step 4), with
  that doc as `<record>`. More than one: stop and report them.

## Step 3 — Before: write and commit the stub

Write `docs/superpowers/results/<YYYY-MM-DD>-<id>.md`:

    # <id>: <one-line title>

    **Pre-registration id:** <id>

    ## Frozen block

    - **Hypothesis:** <one sentence, later passed verbatim as --hypothesis>
    - **Instrument:** <one of INSTRUMENTS in swingbot/core/backtesting/instrument/stats.py>
    - **Metric:** <what is measured, on which window>
    - **N floor:** <value> (quoted from <doc>, "<section>")
    - **Pass threshold:** <value> (quoted from <doc>, "<section>")
    - **Stopping rule:** <when the measurement ends>

    ## Results

    _Not yet measured._

A value no Step 1 section owns is a question for the partner
(`AskUserQuestion`), never a choice made here. Commit the stub alone, before
any measurement runs: `git add <record>`, then
`git commit -m "docs(prereg): register <id>"`. Report the hash and stop; the
measurement is not this skill's job.

## Step 4 — After: prove the registration held

1. `git log --reverse --format=%H -- <record>`: the first hash is `<stub>`,
   and `git show <stub>:<record>` still says `_Not yet measured._`. If not,
   results were committed with the stub: stop and report.
2. `diff <(git show <stub>:<record> | sed '/^## Results/q') <(sed '/^## Results/q' <record>)`
   prints nothing: the frozen block is unchanged since `<stub>`. Any printed
   line stops the ritual and is reported as it is, never reconciled.
3. The doc's `## Results` section holds the measured figures.

## Step 5 — After: append the ledger row

`python scripts/reports/preregistration_ledger.py --id <id> --hypothesis "<Hypothesis, verbatim from the stub>" --instrument <instrument> --n <n or null> --exp-r <ExpR or null> --p <p or null> --verdict <verdict> --record <record>`

`--verdict` takes one of the script's choices (`--help`). A measurement with
no p-value passes `--p null`. The printed q-value is reported-only and gates
nothing; say so when you report it. Commit the record and the ledger together.

## The gate

A stub committed before the measurement, a frozen block that never changed,
and a ledger row whose hypothesis matches the stub verbatim.
