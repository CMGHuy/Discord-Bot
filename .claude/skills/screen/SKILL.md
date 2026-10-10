---
name: screen
description: "Run the Stage -2 idea screen for one idea as a one-shot ritual: check the committed definition, the ledger and the results docs, optionally smoke-test on a few tickers, dispatch the real run, then commit the results doc and the ledger row together. Invoked explicitly as /screen <idea>, never model-triggered."
disable-model-invocation: true
---

# Idea screen

One real run per idea, ever, and a `SCREEN-FAIL` is a finished result.
Arguments: `$ARGUMENTS` (one idea name, written `<idea>` below).

## Step 1 — Read the authority

`python scripts/dev/doc_section.py docs/claude/backtest-methodology.md "Funnel stages"`.
Exit code 2 means the heading is gone: read the whole file instead. The pass
rule, the race, the null and the one-shot rule live there; this skill
restates none of them.

## Step 2 — The definition is the pre-registration

`<idea>` must be a key of `IDEAS` in
`swingbot/core/backtesting/screen/ideas/__init__.py`. If it is not, the idea
is written and committed **before** any run, in a commit that touches no file
under `docs/superpowers/results/`.

## Step 3 — Run against the committed code

`git status --short swingbot/core/backtesting/screen/` must print nothing: the
idea module and the shared `race.py`, `null.py` and `verdict.py` are the
committed ones. Note `git log -1 --format=%H -- swingbot/core/backtesting/screen/`
as the definition hash. Anything uncommitted: stop.

## Step 4 — Not screened before

`grep -n '"id": "screen-<idea>"' docs/superpowers/results/preregistration-ledger.jsonl`
and `ls docs/superpowers/results/*-screen-<idea>.md` must both find nothing.
Either hit: stop and report it. A results doc with no row is a crash between
the doc write and the ledger append; its verdict was still read.

## Step 5 — Not a retry under a new name

`grep -o '"id": "screen-[^"]*"' docs/superpowers/results/preregistration-ledger.jsonl`
lists every screened idea. If `<idea>` looks like a variant of one, stop and
ask the partner (`AskUserQuestion`) whether it is a new hypothesis. A closed
fail is never retried under a similar name, and this skill does not decide.

## Step 6 — Optional smoke test

`python scripts/backtest/screen_idea.py --idea <idea> --tickers <two or three, comma-separated> --dry-run`
writes nothing. The guardrails hook (`_rule_screen_rerun`) denies a
`--dry-run` without `--tickers`; a real run with a non-default `--ledger` or
`--results-dir`; a run of an idea that has a ledger row or a results doc; a
run wrapped in a quoted string (`ssh-hetzner.sh "..."`, `pwsh -Command "..."`);
and a line it cannot tokenise. A deny is the rule: never route round it.

## Step 7 — The real run

Dispatch `backtest-runner` with `python scripts/backtest/screen_idea.py --idea <idea>`,
defaults only, on this machine (the screen's cache is local). Relay its
verdict line only.

## Step 8 — Record

Add `**Definition commit:** <hash from Step 3>` under the results doc's title.
Stage the results doc and the ledger and commit them together, with a message
that names the idea and the verdict but never quotes the command line (the
hook reads a quoted run as a wrapped one). State the verdict exactly as the
script printed it.

## The gate

One committed results doc and one ledger row for `<idea>`, from a single real
run against the committed definition.
