# v90 — Rejection-only armed entries: a follow-through voids the arm

**Version:** ui 1.18.2 · bot 1.9.0
**Bump:** none (measurement only, as v88 A1 was). A live lifecycle, if it is
ever written, is its own document with its own `Bump:`.
**Edge:** expectancy
**Date:** 2026-09-16

## 1. Why this exists

v88 measured armed confluence entries — a scenario arms, and a test of its
stop level followed by a *reaction* there turns it into a plan — and closed
`NO_ELIGIBLE_CELL` at Stage 1 on 2026-09-16. All 24 cells failed clause (b):
every `ΔExpR` sat below the −0.01R margin, and alert volume grew 485–591%
over baseline rather than falling.

The close-out diagnosis broke Run 1's Stage-1-window rows out by the reaction
kind that confirmed each arm (`market/reaction.py`: R1 rejection, R2
follow-through, R3 reclaim). Re-derived pooled from `data/v88/run1/*.jsonl`
over 2018-06-01..2020-12-31 — **not** the selection script's mix-standardised
figures:

| arm | reaction | N | WR | ExpR |
|---|---|---|---|---|
| baseline (`replay_scenarios`) | — | 1928 | 41.4% | +0.100R |
| `M1-N3-k0.25-b0.10` | **R1** | 1545 | **48.1%** | **+0.135R** |
| `M1-N3-k0.25-b0.10` | R2 | 9029 | 38.7% | +0.010R |
| `M1-N3-k0.25-b0.10` | R3 | 1522 | 38.4% | −0.002R |
| `M2-N3-k0.25-b0.10` | **R1** | 1553 | **48.5%** | **+0.141R** |
| `M2-N3-k0.25-b0.10` | R2 | 8225 | 35.7% | +0.058R |
| `M2-N3-k0.25-b0.10` | R3 | 1510 | 37.7% | +0.082R |

**R1 beats baseline on both axes; R2 and R3 do not, and they are 85–90% of
every cell's population.** v88 pooled all three into one measured arm, so the
large weak majority buried the small strong minority at every grid point. No
position of `N`, `k` or `b` can fix that — which is why the v88 row in
`backtest-methodology.md` closes the door on re-running that grid.

`walk_arm` (`backtesting/armed_replay.py`) confirms an arm at the **first**
bar whose `reaction_kind` is non-`None`, whatever kind that is. R2/R3 are not
a weaker path the grid tunes; they are the arm's dominant *exit*, terminating
most arms before a rejection can occur.

**Hypothesis.** Confluence setups whose entry waits for a *rejection* at the
stop level — and which are abandoned outright when price instead follows
through or reclaims — win more often, at better expectancy, than setups
entered immediately.

## 2. Decisions taken in the brainstorm (human partner, 2026-09-16)

1. **Only R1 confirms.** R2 and R3 stop confirming arms and become terminal
   cancels instead.
2. **R2 and R3 stay distinguishable** as two named cancel reasons, not one
   generic cancel — the funnel must keep showing how arms die.
3. **The mode axis is dropped.** `M2` existed only to give R2/R3 a market
   fill; with neither confirming, `M1`/`M2` are the same mechanism.
4. **The `b` axis is refined; `N` and `k` are untouched** (§3.4), and no
   threshold or tolerance anywhere is changed.
5. **Measurement only.** A live ARMED lifecycle is written only if this
   passes VALIDATION — v88 §5 still describes it and is not restated here.

## 3. The rejection-only armed replay

Confluence-sourced plans only; strategy-sourced plans are untouched. Daily
bars, under the NO-LOOKAHEAD rule: everything decided at bar `j` reads
`df.iloc[:j+1]` only.

### 3.1 What changes

**One branch in `walk_arm`.** Today:

```python
if kind is not None:
    return ArmOutcome("confirmed", t, kind, first_test)
```

becomes: confirm only on `reaction.R1`; `R2` returns
`ArmOutcome("cancelled_follow_through", t)` and `R3` returns
`ArmOutcome("cancelled_reclaim", t)`. Both are terminal — the walk stops at
the same bar it stops at today, and the arm is simply abandoned instead of
traded. Waiting past a follow-through is not an option on offer: once price
has closed beyond the previous bar's extreme, the entry thesis (get in near
the level, just after it holds) is void, and a later rejection would be a
rejection of a different level.

**`Cell` drops `mode`** — it becomes `(n, k, b)` and `cell_id` becomes
`N{n}-k{k}-b{b}` (e.g. `N3-k0.25-b0.10`). `MODES` is deleted from
`armed_measurement.py`.

**`plan_at` loses its market-entry branch.** `market = cell.mode == "M2" and
kind in (R2, R3)` can no longer be true, so it and the `record_transition`
straight-to-ACTIVE path are deleted. Every confirmed plan is a stop-entry at
the rejection bar's extreme with `STOP_ENTRY_EXPIRY_BARS`, which is what
`M1` already did for R1 in v88.

### 3.2 What does not change

`reaction.py` is untouched — R1/R2/R3 keep their exact v88 definitions, so
what counts as a rejection is not being redefined to suit the result. Stop
re-anchoring (`min(level, low since first test) − b·ATR`), the re-gating
chain (`regate_stop_distance` → `regate_no_target` → `regate_reward` →
`regate_confluence`), the arm-exclusivity rule, `COOLDOWN_BARS = 5`,
`CONFLUENCE_TOLERANCE_PCT`, the baseline arm, the universe and the horizons
are all exactly as v88 ran them.

**The `R3 > R2 > R1` precedence inside `reaction_kind` is also unchanged, and
that now decides outcomes it never used to.** When all three confirmed, the
precedence only picked a label; here it picks *confirm or abandon*. A bar
that is both a reclaim and a rejection — price closed below support
yesterday, today wicks down and closes back above it on a long lower wick —
resolves as R3 and is therefore **cancelled**, despite arguably being the
strongest shape on the board. This spec accepts that cost deliberately:
re-ordering the precedence would mean redefining the detector at the same
moment we start selecting on it, which is the move that makes a result
unfalsifiable. It is recorded here as the leading candidate for a *separate*
future mechanism, not as a knob this plan may turn.

### 3.3 Why this is not a re-label of v88's R1 rows

It would be easy to assume the confirmed population here is identical to the
R1-tagged rows already visible in §1, since the walk terminates at the same
bar either way. **It is not**, because of `replay_armed`'s cooldown:
`last_issued[direction]` is set only when a plan *issues*, and suppresses new
arms for `COOLDOWN_BARS`. In v88, R2/R3 confirmations issued plans and so
cast that 5-bar shadow; here they never issue, releasing arms that v88 never
evaluated — some of which will confirm on R1. Those new arms then set
`busy_until`, which can in turn suppress arms v88 *did* evaluate, so the
divergence cascades in both directions.

This is already visible in v88's own data: `M1` and `M2` should give byte-
identical R1 rows (R1 takes a stop-entry in both modes) and do not —
1545 vs 1553 trades at `N3-k0.25-b0.10` — precisely because their differing
R2/R3 issuances released different arms downstream.

**The results doc must therefore report the overlap as a measured number:**
how many of this run's confirmed trades also appear in `data/v88/run1`'s
R1-tagged set for the same knobs, and how many are new. The degree of
reproduction is evidence to be shown, not an assumption to be asserted.

### 3.4 Grid — 30 cells

| Knob | Values | Changed from v88? |
|---|---|---|
| `N` arm window | 3, 5, 10 bars | no |
| `k` test proximity | 0.25, 0.5 ATR | no |
| `b` stop buffer | 0.00, 0.05, 0.10, 0.15, 0.20 ATR | **yes — refined** |
| mode | — | **removed** |

**Why `b` is refined, stated plainly.** v88 sampled `b` at two points, 0.10
and 0.25, which its own TRAIN data shows are ~0.062R apart on a steep
monotone knob (R1-only ExpR: +0.128–0.147R at b=0.10, +0.058–0.083R at
b=0.25). `plateau_report` disqualifies an adopted value whose adjacent
neighbour differs by more than `PLATEAU_TOLERANCE_R = 0.03R`, so a two-point
axis that far apart makes the plateau check *unable to pass* regardless of
the mechanism's merit — the v49 "degenerate by construction" failure mode.
Five values at even 0.05 ATR steps, spanning no buffer to a moderate one,
let the check do its job.

**This refinement was chosen after inspecting v88's TRAIN window** — the
knowledge that b=0.10 beats b=0.25 is why the axis is resampled around the
modest-buffer regime, and why 0.25 is dropped. It is a fix to an axis too
coarse to test, not a loosened threshold: `PLATEAU_TOLERANCE_R` stays 0.03R,
every eligibility clause stays as v88 pre-registered it, and `N` and `k` are
deliberately left alone so no further degrees of freedom enter.

**Known risk on the new `b=0.00` cells.** A zero buffer puts the stop exactly
at the reaction low, which is the tightest stop on the axis and so fails
`min_stop_distance_pct` most often — those arms die at `regate_stop_distance`
and never post. v88's R1 rows cut alert volume 7.6–20.2% against baseline at
b∈{0.10,0.25}, comfortably inside clause (a)'s 25% ceiling, but the b=0.00
cells have never been measured and may breach it. If they do they are simply
ineligible, and the clause is **not** relaxed to admit them.

**Baseline arm:** today's `replay_scenarios` on the same tickers, horizons
and window. **Width:** full cached universe × all 10 horizons.

**Cost.** As v88: the level map and confluence counts are computed once per
`(ticker, horizon)` and shared; cells replay only reaction detection, plan
construction and `simulate_exit`. v88's 24 cells took 1h41m over 88 tickers;
30 cells should land near two hours. Sharded per ticker, resumable, flushed
percent progress in a log deleted on completion, dispatched to
`backtest-runner`.

## 4. Pre-registration

### 4.1 Stages (v72 funnel; no constant changes)

Identical to v88 §4.1 in every threshold. Restated so this document stands
alone:

1. **Stage 1 — selection**, on **2018-06-01..2020-12-31** only. A cell is
   **eligible** iff (a) alert-volume cut <= 25% vs baseline, (b)
   `ΔExpR >= −0.01R`, (c) mix-standardised `ΔWR > 0`. Among eligible cells,
   select the **greatest `ΔExpR`**; ties → greater `ΔWR`, then smaller `N`.
   **Plateau:** `plateau_report` (tolerance 0.03R) on each of `N`, `k`, `b`,
   holding the others at the selected values. Any spike disqualifies. With
   mode gone, every axis is ordered and every axis is checked.
   **No eligible cell → `NO_ELIGIBLE_CELL`; a spike → `SPIKE`.**
2. **Stage 0 — MDE**, on the selected cell: `validate_component.py --stage
   mde` with the Stage 1 effect, `observed_days` = the train window's length,
   `target_days = 730`. Below MDE → **refused, budget intact.**
3. **Stage 2 — walk-forward**, selected cell only, fold-test 2021 / 2022 /
   2023: >= 2 of 3 folds improving, no fold worse than −1.0pp, per-fold
   N >= 30.
4. **Stage 3 — VALIDATION, one shot**, 2024-01-01..2025-12-31: clauses 1–5;
   clause 6 reports `SKIPPED` (not a subset feature) and a SKIP never blocks.
   A missing permutation p is a FAIL.

Clause (c) is what carries the human partner's standing constraint that this
work must not cost win rate: no cell that lowers `ΔWR` can be selected at
all, at any expectancy.

### 4.2 The permutation — a random-delay null

As v88 §4.2: n = 200, seed 42, the same purpose-built null (does the reaction
carry information beyond simply waiting?). One change follows from §3.1 —
the population is every arm that confirmed **on R1**, issued or regated, and
each permutation redraws that arm's confirmation bar uniformly from its own
`[i, i + N]` window. The drawn bar's entry is a stop-entry, since there is no
longer a mode whose fill depends on the reaction kind. The statistic stays
mix-standardised `ΔWR` vs baseline.

### 4.3 Integrity guards

- **VALIDATION lock in code:** the instrument refuses to replay 2024–25
  unless handed a Stage 2 results doc reading **Overall: PASS**.
- **Overlap disclosure:** §3.3's measured overlap against v88's R1 rows is a
  required section of the Stage 1 results doc, not optional colour.
- **Truncation tests:** the arm state machine keeps its
  `full.iloc[:-1] == trunc` test, extended to cover the two new cancels.
- **No search can touch it.** `N`, `k` and `b` live as constants in the
  measurement module, not as `config.Field`s.
- **Recorded limitations,** quoted in every results doc: daily-bar ordering
  is conservative (stop before target on the same bar); the universe is
  today's cached tickers (survivorship). v88's third limitation — M2's market
  fill at an untradeable close — is **gone**, because market fills are gone.

### 4.4 What Stage 1 can and cannot prove here

**Stage 1 is a weak test in this plan and must not be read as a strong one.**
The mechanism was designed by inspecting v88 Run 1's Stage-1-window rows
broken out by reaction kind (§1). The population Stage 1 scores overlaps that
inspection heavily — §3.3 explains why it is not identical, but the bulk of
it is the same trades. A Stage 1 PASS here is therefore close to a
reproduction of the observation that motivated the plan, and is expected.

What preserves this as a real hypothesis test is that **the diagnosis was
confined to 2018-06-01..2020-12-31**. The fold years (2021/2022/2023) and the
VALIDATION window (2024–25) have never been inspected broken out by reaction
kind, by this session or any other. They stay un-inspected until their stage
runs. **Stage 2 and Stage 3 carry all of this plan's confirmatory weight.**

No one may query `data/v88/run1` or any v90 output for reaction-kind
behaviour outside the Stage 1 window before the corresponding stage runs.

### 4.5 Outcomes

| Result | What happens |
|---|---|
| `NO_ELIGIBLE_CELL` / `SPIKE` / MDE refused / Stage 2 FAIL | Closed, VALIDATION budget intact. Row added to `backtest-methodology.md`'s closed table. |
| Stage 3 FAIL | Closed, budget spent, recorded as-is. |
| Stage 3 PASS | Closed PASS, recorded. The live ARMED lifecycle (v88 §5) is brainstormed and specced next. |

**Outcome (2026-09-17):** SPIKE at Stage 1; the live ARMED lifecycle is not written.

## 5. Deliverables

- `swingbot/core/backtesting/armed_replay.py` — the changed terminal
  condition, the two new cancel states, `Cell` without `mode`, `plan_at`
  without the market branch, and the permutation's R1-only population.
- `swingbot/core/backtesting/armed_measurement.py` — `MODES` deleted, `B_GRID`
  refined, `CELLS` rebuilt over three axes.
- `scripts/backtest/measure_armed_entries.py` — unchanged in shape; the
  overlap report (§3.3) rendered into the Stage 1 doc by `select` (where
  §4.3 requires it), and `OUT_ROOT` moved to `data/v90` so v88's run stays
  intact as the comparison input.
- `swingbot/core/market/reaction.py` — **not modified.**
- Results under `docs/superpowers/results/`: Stage 1 selection (full 30-cell
  table, plateau reports on all three axes, the rule quoted, the overlap
  disclosure), then each later stage reached.
- Close-out: the closed-table row in `backtest-methodology.md`, whatever the
  verdict.

## 6. Testing

- `walk_arm`: an R1 frame confirms; an R2 frame returns
  `cancelled_follow_through`; an R3 frame returns `cancelled_reclaim`; each
  bearish mirror.
- An arm whose R2 bar precedes an R1 bar cancels at the R2 bar and issues
  nothing — the explicit "we do not wait past a follow-through" assertion.
- Cooldown release (§3.3): a frame where a v88-style R2 issuance would have
  suppressed a later arm now lets that arm through and confirm on R1.
- `plan_at` yields a stop-entry at the rejection bar's extreme with
  `expiry_bars = STOP_ENTRY_EXPIRY_BARS` for every cell — no cell produces a
  market entry.
- v88's deleted M2 tests (`test_m2_goes_straight_to_market_on_a_follow_through`,
  `test_m2_keeps_a_rejection_as_a_stop_entry`) are removed, not adapted; the
  arm-exclusivity/cooldown and NO-LOOKAHEAD truncation tests have their
  fixtures re-derived, since confirmation bars move.
- Permutation determinism (seed 42 → identical p).
- One full-suite run, as the plan's final task.

## Parallelisation

- **Group 1 (parallel):** `armed_measurement.py`'s grid change + its tests;
  the `summary` overlap report against v88's run1 (reads a fixture, not the
  live replay).
- **Sequential:** `armed_replay.py`'s terminal-condition change first — every
  other code task consumes it. Then `plan_at`'s market-branch removal, then
  the permutation's population change, then the test re-derivation. Runs
  strictly in stage order — Stage 1, then 0, then 2, then 3 — each gated on
  the previous result doc. The full-suite run after the last code task and
  before the first long run.
