# v129 — Acceptance-failure exits: sweep-tolerant zone stops and breakout return-into-range

**Version:** ui 1.21.1 · bot 2.0.0 (at writing)
**Bump:** bot patch (inert flag at default; an arm ships default-on only if it clears VALIDATION)
**Edge:** harvest — same entries, exits judged on acceptance (a close) instead of a touch

## Why

The partner's six-page range/liquidity handbook (2026-10-03, "Daiken/BigWhale")
makes one argument across every page: an obvious level attracts resting stops
("STOP LOSS / PENDING ORDERS" under equal lows), price often **sweeps** it
intrabar and reclaims, and the meaningful event is **acceptance**, a close
beyond the level that is not reclaimed. "Break ≠ confirmation"; "break + long
wick + return into range → beware the false breakout".

The bot does the opposite on its main path. A confluence plan's stop **is**
the nearest support price itself (`levels.py:707`, bearish `:736`), with no
buffer. The 2% cap clamps it to 1.75% (`builders.py:366-383`). Every intrabar
sweep of the level therefore stops the trade out at −1R. Confluence plans are
~80% of the live book, so the loss side of pooled ExpR is where this acts.

Break & Retest is the mirror case. Its stop is a 2·ATR fallback
(`builders.py:39-79`) unrelated to the broken level. A close back inside the
old range, the handbook's false-breakout signal, is ignored until that much
wider stop is hit.

No closed pre-registration has tested a close-based exit after entry. Nearest:
- v114 and v104 changed stop **width**, not its basis.
- v92 `STALL_EXIT_ENABLED` was unmeasurable by construction.
- v88's "close below L not reclaimed" applied to arming before entry.

See the closed-results table in `docs/claude/backtest-methodology.md`.

## Pre-registered claim

Judging a level-leaning trade by acceptance (a daily close beyond its level)
rather than by an intrabar touch raises per-trade expectancy, under the v92
harvest gate, on the same entries.

Two arms, two independent populations. Each is judged on its own, and a pass
in one never carries the other.

| Arm | Population | Change vs today | Grid |
|---|---|---|---|
| **Z — sweep tolerance** | confluence plans (`source == "confluence"`) | Intrabar stop moves from `level` to the **disaster stop**. Add a close exit at `level ∓ b·ATR14`. **1R = entry → disaster stop.** | `m ∈ {0.5, 1.0, 1.5}` × `b ∈ {0, 0.25}`, 6 cells |
| **B — acceptance failure** | Break & Retest plans | Stop unchanged (2·ATR fallback). Add a close exit at the broken level `∓ b·ATR14`. | `b ∈ {0, 0.25}`, 2 cells |

Direction is mirrored for bearish plans throughout. Below, bullish is written
and bearish is the mirror.

## Definitions (all frozen at the plan's creating bar)

- **`level`:** the price the trade leans on.
  - Confluence: the **pre-clamp** stop level, i.e. `supports[0].price`
    (bullish) or `resistances[0].price` (bearish), captured before
    `_clamp_stop_to_hard_cap` runs.
  - Break & Retest: the broken `resistance` (bullish) / `support` (bearish)
    value at the entry bar, from the same series `break_retest_entries` already
    computes.
- **`atr`:** ATR14 at the creating bar. Nothing is re-derived from later bars.
- **Disaster stop (arm Z):** `level − m·atr`, then pulled in to the 2% hard
  cap if farther: `max(level − m·atr, entry·(1 − 0.02))` for bullish. This
  value is written into `stop_loss`, so R, sizing, break-even and every
  existing consumer pick it up unchanged.
- **Close threshold:** `level − b·atr`. Stored on the plan as
  `acceptance_close_below` (bearish: a close **above** `level + b·atr`).
- **Not eligible (arm Z):** a confluence plan whose `level` already lies
  beyond the 2% cap. These are exactly the plans the clamp moved. They keep
  today's stop and get no acceptance exit. They are counted and reported,
  never dropped.

## Exit rule

A new pure function in `exit_sim.py`:
`acceptance_exit(plan, bar_close) -> bool`. It is true when
`plan.acceptance_close_below` is set and `bar_close` is beyond it (bullish:
`bar_close < threshold`).

It is called in both `_single_leg_exit_walk` and `_scale_out_exit_walk`, as a
single helper call beside the stall exit. Same-bar order is the existing
conservative convention, extended:

1. intrabar stop (disaster stop for arm Z; unchanged stop for arm B);
2. target / TP1;
3. **acceptance exit at `close[j]`**, with reason `"acceptance_exit"`;
4. stall exit, timeout.

A bar that tags TP1 and closes through the level banks TP1 first, then exits
the remainder at the close. The acceptance exit is in force for the whole
hold, not a first-k-bars window. The handbook's acceptance is not
time-limited, and a window would be one more knob.

**Stop-hit accounting is unchanged:** a stop hit books exactly −1.0R in both
arms and in the baseline, even when the bar gaps through it. This keeps the
pairing fair. Gaps through the disaster stop are a disclosure, not a re-priced
fill.

## Code changes

- **`TradePlanV2`** (`plan_types.py`): two optional fields,
  `acceptance_level: float | None = None` and
  `acceptance_close_below: float | None = None`. Plans are stored records, so
  this follows `docs/claude/schema-evolution.md`'s *add* path. The plan author
  determines whether the Postgres plan store needs an Alembic revision or
  carries the fields through its JSON body, and does whichever applies.
- **`build_confluence_plan`** (`builders.py`): capture `level` before the
  clamp. Always set `acceptance_level`. With the flag on and the plan eligible,
  set the disaster stop and `acceptance_close_below`.
- **`break_retest_entries`** (`entry_filters.py`): a pure refactor that also
  exposes the broken-level series. The existing boolean signals must stay
  byte-identical (asserted by a test). `_trade_plan_at` (`backtest.py:179`) and
  the live strategy path set `acceptance_level` from it for Break & Retest.
- **`exit_sim.py`:** `acceptance_exit` plus the two call sites.
- **`config.py`:**
  - `ACCEPTANCE_EXIT_ENABLED` (bool, default `false`);
  - `ACCEPTANCE_EXIT_ARMS` (subset of `{"Z", "B"}`, default both, read only when enabled);
  - `ACCEPTANCE_DISASTER_ATR_M` (float);
  - `ACCEPTANCE_CLOSE_BUFFER_ATR` (float).

  Defaults for the floats are fixed only after Stage 3. With the flag off they
  are never read.
- **`acceptance_harvest.py`:** a **new** `mde_expectancy_r_paired`, the MDE
  from the variance of per-trade ΔR (component R − baseline R on the same
  entry). The existing `mde_expectancy_r` is left byte-identical so v92's
  closed results stay reproducible.
- **Replay script** `scripts/backtest/measure_acceptance_exits.py`. It replays
  the confluence path (`backtest_scenarios.py`) and Break & Retest once per
  cell. The entries are shared and each is paired with its baseline exit. It
  emits per-arm, per-cell harvest-gate JSON plus the disclosures below.

With the flag off, live scans still record `acceptance_level`, so the live
book starts collecting the input before any decision. No alert text, chart,
target, entry or badge changes.

**Known trap, designed out.** v92's stall exit was unmeasurable because
backtest-built plans never set its field. The first implementation task is a
red test asserting `acceptance_level` is non-`None` on **backtest-constructed**
plans for both Break & Retest (`_trade_plan_at`) and the confluence replay.
It must be red before the wiring and green after.

**Complexity:** both exit walks sit near the < 15 limit. The rule enters each
one as a single helper call.

## Gate and funnel

The v92 harvest gate (`swingbot/core/backtesting/acceptance_harvest.py`),
per arm. Windows are the methodology's: TRAIN 2020-01-01..2023-12-31,
VALIDATION 2024-01-01..2025-12-31.

- **Stage 0, paired MDE precheck** (`mde_expectancy_r_paired`, power 0.80).
  If an arm's MDE exceeds **+0.10R**, that arm closes `UNDERPOWERED`. No
  widened window, looser margin or re-run. Arm B (TRAIN N≈105) is the likely
  candidate.
- **Stage 1, TRAIN plateau.** A cell is eligible when it passes
  `expectancy_gain`, `win_rate_floor` and `volume_floor`. Arm Z selects the
  eligible cell with the highest lower-95% ΔExpR **whose grid neighbours (±1
  step in m or b) are all eligible**. Arm B selects only if both cells are
  eligible, taking the higher lower-95% ΔExpR. No eligible plateau →
  `NO_ELIGIBLE_CELL`.
- **Stage 2, free walk-forward folds** over TRAIN for the selected cell. It
  must not reverse sign in the majority of folds.
- **Stage 3, one-shot VALIDATION** per arm, with `not_luck` (permutation,
  n=200, on ΔExpR). Spent exactly once.

Clause readings:
- **`win_rate_floor` (−2.0pp) is live for both arms.** Z is expected to raise
  WR. B can lower it, because a dip that would have recovered becomes a small
  loss.
- **`volume_floor`** should pass trivially (exit-only) and is reported
  regardless.

**On a pass:** `ACCEPTANCE_EXIT_ENABLED` flips on with `ACCEPTANCE_EXIT_ARMS`
naming only the passing arm(s), at the selected cell's values. **On a fail:**
the arm gets a row in the closed-results table with its verdict, and is never
re-run as specified.

## Reporting (every stage, per arm and cell)

- ΔExpR (bootstrap mean, lower 95%), ΔWR, N.
- Outcome flips in both directions: win→loss and loss→win.
- Exit mix by reason: stop / acceptance_exit / target / TP1+runner / timeout.
- Planned-RR shift (arm Z lowers it by construction; disclosed, not gated).
- Arm Z: not-eligible count, and the count of stop hits where the bar's open
  was already beyond the disaster stop (gap-through).
- Per-horizon N, so a single-horizon mask cannot pass as a cross-horizon
  result (the v102 lesson).

## Testing

- Parity: flag off → replay output byte-identical to the current baseline, for
  both populations.
- `break_retest_entries` signals byte-identical before and after the refactor.
- Trap test (above): `acceptance_level` set on backtest-built plans.
- `acceptance_exit` unit cases: bull/bear, wick-only bar (no exit), close
  exactly on the threshold (no exit; strict inequality), `None` threshold.
- Exit-walk ordering: TP1-and-close-through on one bar; stop-and-close-through
  on one bar (the stop wins at −1.0R).
- Disaster stop: cap pull-in, not-eligible clamped plan, bearish mirror.
- No lookahead: the disaster stop and threshold for a plan created at bar `t`
  are identical when computed on `df.iloc[:t+1]`.
- `mde_expectancy_r_paired` on a hand-computed fixture; `mde_expectancy_r`
  unchanged.

## Out of scope

- Breakout-quality snapshot keys (displacement, close location, follow-through,
  return-into-range) and equal-highs/lows sweep→reclaim. Both are separate
  follow-on specs from the same handbook.
- Any change to entries, targets, the 2% cap, or position sizing beyond what
  `stop_loss` already drives.
- Other strategy-source plans. Only Break & Retest has a well-defined broken
  level.
- Re-pricing gap fills.

## Parallelisation

- **Group A (independent, parallel):**
  1. the `TradePlanV2` fields plus the schema path;
  2. the `break_retest_entries` refactor with its parity test;
  3. `mde_expectancy_r_paired`.
- **Group B (after A1):** the trap test, then confluence and `_trade_plan_at`
  wiring. Needs the fields to exist.
- **Group C (after A1):** `acceptance_exit` and the two exit-walk call sites.
  Needs the fields. Independent of B.
- **Group D (after B, C, A3):** the replay script. Needs plans that carry the
  level, the exit rule and the paired MDE.
- **Group E (after D):** Stages 0–3. Each depends on the previous stage's
  verdict.
- **Last:** full suite once.
