---
name: pooled-numbers
description: Use when about to state a pooled expectancy, ExpR, win rate, sample size N, R-multiple or strategy badge tier -- in a message, a spec, a plan or a commit. Requires re-deriving the figure from the live book rather than quoting one from a document. Not for a figure the user just supplied, and not for a number being read back from a file open in this context.
---

# Pooled numbers

## Step 1 — Read the authority

`docs/claude/edge-priorities.md` for what "pooled" means here and why
expectancy leads win rate. `docs/claude/backtest-methodology.md` for which
window a figure belongs to and how a badge tier is scored. This skill does
not restate either.

## Step 2 — Every pooled figure in a document is stale until re-derived

The 2026-09-10 badge refresh demoted three strategies and invalidated every
pooled figure quoted against the old registry. A number in a spec or plan
records what was true when it was written, not what is true now — the
registry, not the prose that once cited it, is the current state.

## Step 3 — Re-derive, and say from what

Name the source, the window and the N alongside the figure. A pooled number
without its N is not a claim, it is a mood. "Roughly what the doc says" is
not a derivation — re-run the query or re-read the registry row that
produced the figure, then quote what actually came back.

## Step 4 — Say which dimensions have no N

Slicing the book far enough produces confident nonsense: a strategy, a
horizon and a regime intersected down far enough will read however you want
it to. If a dimension's N is too thin to support the claim being made, say
so in the same sentence as the figure, not in a footnote three paragraphs
later.

## The gate

The figure, its N, its window and its source all appear together, or the
figure does not appear at all.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "the spec says ExpR is X" | The spec says what it was; the registry says what it is. |
| "roughly, from memory" | A remembered R-multiple is a fabricated one — re-derive it or don't state it. |
| "the badge says VALIDATED" | Check the registry's `run_date`; a badge can outlive the population it was scored on. |
| "it's basically the same number as last time" | "Basically the same" is a re-derivation skipped, not one performed. |

## Trigger table

Should fire: about to summarise how a strategy or the book is performing.
Should fire: writing an `Edge:` header's justification in a spec or plan.
Should fire: answering "is this strategy working" or "is this worth
building on."
Should fire: drafting a commit message that cites a win rate or an ExpR.
Should not fire: the user quotes a number and asks a follow-up about it.
Should not fire: reading a `results/*.md` file aloud that is already open
in context.
Should not fire: discussing a hypothetical strategy or a made-up scenario.
