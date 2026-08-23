# Choosing what to work on — expectancy first, win rate second

Referenced from the root `CLAUDE.md`, which carries the short rule. This file
is the reasoning and the current numbers.

## The objective

**The bot exists to make money on paper trades, and every plan competes for the
same finite budget of pre-registered shots.** Rank candidate work by expected
effect on **pooled expectancy (`ExpR`) first, win rate second**, and say so out
loud when a plan is chosen over a higher-impact alternative.

The two are not the same objective and can move against each other: break-even
win rate at reward:risk `X` is `1/(1+X)`, so widening targets lowers win rate
while raising expectancy. **Expectancy is the objective; win rate is a
constraint** (the `>= 50` acceptance gate). A change that raises win rate while
lowering `ExpR` is a regression, not a win.

## The `Edge:` header line

Every new spec and plan carries an **`Edge:`** header line next to `Bump:`,
naming the profit mechanism and its expected direction — one of:

- `Edge: expectancy` — adds or sharpens a discriminator, or removes a
  negative-expectancy population.
- `Edge: harvest` — same setups, more R extracted (exits, targets, sizing).
- `Edge: volume` — same edge per trade, applied to more qualifying setups.
- `Edge: none (integrity)` — correctness, tooling, hygiene, refactor. Legitimate
  and sometimes urgent, but it must **say** it buys no edge rather than implying
  one.

## Where the pooled numbers stand

From `docs/superpowers/results/2026-07-pooled-validation.md`, VALIDATION
2024–25:

| Population | Win rate | ExpR | N |
|---|---|---|---|
| VALIDATED strategies | 84.2% | +0.259R | 814 |
| WEAK strategies | 76.2% | +0.191R | 1389 |
| **Confluence scan** | **53.5%** | **−0.171R** | **4641** |

The confluence scan is the largest population in the book and the only negative
one. **Re-derive these before leaning on them; do not quote them as current
without checking.**

## What this rule does not do

**It does not loosen a single acceptance gate.** It governs *what to work on*,
never *what threshold to accept*. It is not a licence to re-run a closed
pre-registration, to re-read the tainted 2024–25 window for selection, or to
reach a win-rate bar by shrinking `N`.

A profit motive is exactly the pressure `backtest-methodology.md` was written to
resist — when the two conflict, the methodology wins and the plan gets a *new*
pre-registered hypothesis or nothing.
