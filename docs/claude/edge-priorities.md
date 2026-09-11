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
while raising expectancy. **For ranking work, expectancy is the objective and
win rate the constraint**: a change that raises win rate while lowering `ExpR`
is a regression, not a win.

**Inside the v72 acceptance gate the two swap roles, and that is not a
contradiction.** The gate scores one feature against the baseline it replaces
on a geometry-locked population (clause 3 forbids the target-pulling that
trades one for the other), so there win rate is the objective and expectancy a
non-inferiority floor — the only remaining axis is discrimination, which moves
both together. Ranking asks *what to build*; the gate asks *did this one thing
work*. The old absolute `>= 50` acceptance floor is gone from feature
acceptance and survives only as a strategy-badge threshold
(`docs/claude/backtest-methodology.md`).

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

**These rows were last true 2026-07** and are now known-stale: the `VALIDATED`
row's N=814 population still includes Fibonacci/RSI/Support-Resistance trades,
all three of which dropped to `WEAK` on 2026-09-10
(`results/2026-09-10-legacy-badge-refresh-train.md`) before this campaign began.
Plan v84 (strategy rescue v2) then spent its own measurement budget against the
remaining `WEAK` population and **rescued none of the seven strategies it
tried** — registry badge state is unchanged by v84 itself, and stands at **2
`VALIDATED` (MACD, Volume Profile), 9 `WEAK`** both before and after this
campaign (`docs/claude/backtest-methodology.md`'s closed-pre-registrations
table has the seven per-strategy rows). Do not re-derive the pooled table
above from `2026-07-pooled-validation.md`'s membership list without first
excluding the three demoted strategies.

## What this rule does not do

**It does not loosen a single acceptance gate.** It governs *what to work on*,
never *what threshold to accept*. It is not a licence to re-run a closed
pre-registration, to re-read the tainted 2024–25 window for selection, or to
reach a win-rate bar by shrinking `N`.

A profit motive is exactly the pressure `backtest-methodology.md` was written to
resist — when the two conflict, the methodology wins and the plan gets a *new*
pre-registered hypothesis or nothing.
