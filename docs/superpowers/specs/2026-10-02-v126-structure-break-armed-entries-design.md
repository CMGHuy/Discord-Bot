# v126 — Structure-break armed entries: wait for a minor break (or a higher low) after the zone test

**Version:** ui 1.21.1 · bot 2.0.0 (at writing)
**Bump:** none (measurement only, as v88/v90 were). A live lifecycle, if it is
ever written, is its own document with its own `Bump:`.
**Edge:** expectancy

## 1. Why this exists

A price-action course the partner shared (Day 17 "Confirmation": *a good zone
is not an order — touch → rejection → minor structure break → higher low →
continuation*) was mapped against the bot on 2026-10-02. Confluence plans
still enter on the touch (market, or a stop-entry for breakouts —
`planning/builders.py:325`, `:437`), and the confluence pool is the
population known to be negative (≈80% of the live book at −0.136R measured
2026-09-10 — point-in-time, re-derive before leaning on it).

Two pre-registrations already tested *armed* confluence entries and closed:

- **v88** — confirm on the first R1/R2/R3 reaction: `NO_ELIGIBLE_CELL`, alert
  volume +485–591%.
- **v90** — confirm on R1 rejection only: `SPIKE`. Direction held everywhere
  (ΔWR +3.3 to +7.1pp on all 30 cells, ΔExpR > 0 on 22) but the pick failed
  the `b`-axis plateau, which the close-out traced to the issue-dependent
  5-bar cooldown reshaping the population as `b` moved.

Both rows in `docs/claude/backtest-methodology.md` say **"reopening needs a
genuinely new mechanism, not a looser margin or another grid over these
knobs."** This spec claims that standing on two grounds, stated so a
reviewer can reject the claim:

1. **The confirmation is multi-bar swing structure, not a single-bar candle
   shape.** `market/reaction.py`'s R1/R2/R3 predicates are not used at all.
2. **The population is defined by a touch-episode rule, not the cooldown.**
   v90's failure mode — `COOLDOWN_BARS` set only when a plan *issues*, so
   voided arms release others nonlinearly — cannot occur.

**Hypothesis.** Confluence setups whose entry waits for a close above the
last confirmed minor swing high after the zone test (optionally: only after a
confirmed higher low) win more often, at better expectancy, than the same
setups entered on the touch.

## 2. Decisions taken in the brainstorm (human partner, 2026-10-02)

1. **Entry trigger only.** Zone-origin scoring stays descriptive (v125
   `zone_departure_atr`) and may earn its own pre-registration later.
2. **Confluence-sourced plans only**, matching v88/v90's population and
   baseline so the comparison to those closed results is clean.
3. **`b` frozen at 0.10 ATR** (v88's original pre-registered value), not an
   axis. The stop question belongs to v104 (closed) and is not re-litigated.
4. **One arm per touch episode** replaces `COOLDOWN_BARS` for this arm.
5. **Measurement only.**

## 3. The structure-break armed replay

Confluence-sourced scenarios only; daily bars; NO-LOOKAHEAD — everything
decided at bar `j` reads `df.iloc[:j+1]` only. Bullish described; bearish is
the mirror throughout.

### 3.1 State machine (per scenario level)

- **Arm.** Opens at the first bar `i` whose low comes within `k·ATR14[i]` of
  the scenario's level — v88's first-test rule, unchanged. **Touch low**
  `L_j = min(Low[i..j])`.
- **Trigger** (cell axis `trigger`):
  - `MSB` — at bar `j > i`: `Close[j] > SH_j`, where `SH_j` is the last
    swing high **confirmed at `j`** per v121's
    `market/structure.py:confirmed_pivots(df, k=3)` (pivot order not
    re-tuned; v121 froze it at 3).
  - `HL` — as `MSB`, but additionally a swing low confirmed at `j`, with
    index `> i`, whose low `> L_j`, must exist.
- **Cancel — zone failed.** `Close[j] < L_{j-1} − 0.10·ATR14[j]` → terminal
  `cancelled_zone_failed`, where `L_{j-1} = min(Low[i..j-1])` is the touch
  low *before* bar `j` (an inclusive `L_j` could never fire, since
  `Close[j] >= Low[j] >= L_j`; corrected at planning). The stop still uses
  the inclusive `L_j`. On a bar that both fails the zone and breaks
  structure, the cancel wins.
- **Expire.** No trigger by bar `i + N` → terminal `expired`.
- **Entry.** Stop-entry at `High[j]` of the trigger bar with
  `STOP_ENTRY_EXPIRY_BARS = 2` (v90's value).
- **Stop.** v88's re-anchoring, `min(level, L_j) − b·ATR14[j]`, `b = 0.10`
  frozen. Then v88's re-gating chain inside `armed_replay.plan_at`
  unchanged (reason codes `regate_invalid_atr`, `regate_stop_distance`,
  `regate_no_target`, `regate_reward`, `regate_confluence`), so the hard
  cap, the clamp and the structural-target rule apply exactly as live.
- **Touch episode.** After an arm terminates (issued, regated, cancelled or
  expired), the same level re-arms only after some bar closes more than
  `(k + 1)·ATR14` away from it in the trade's favour. Arms of *different*
  levels are independent. `COOLDOWN_BARS` is not consulted by this arm.
  v88's arm-exclusivity rule (one live arm per ticker × direction) is kept.

### 3.2 What does not change

The level map, confluence counting and scenario construction; the
re-gating chain; `simulate_exit` (exit model v2 with scale-out); the
baseline arm (`replay_scenarios` on the same tickers, horizons, window); the
universe (full cached universe × all 10 horizons); `reaction.py`; and
**v88/v90's code paths in `armed_replay.py`** — the new walk lives in a
sibling module (`backtesting/structure_arm.py`) that reuses the harness's
plan construction, regates and exit simulation, so v88 and v90 remain
reproducible byte-for-byte.

### 3.3 Grid — 12 cells

| Knob | Values | Note |
|---|---|---|
| `trigger` | `MSB`, `HL` | categorical |
| `N` arm window | 5, 10, 15 bars | starts at 5, not v88's 3: a k=3 pivot needs 3 bars to confirm, so N=3 cannot contain a break |
| `k` test proximity | 0.25, 0.5 ATR | v88's values, unchanged |

`cell_id = {trigger}-N{n}-k{k}` (e.g. `MSB-N10-k0.25`). Constants live in the
measurement module, never as `config.Field`s, so no search can touch them.
**Cost:** about half of v88's 24 cells / 1h41m; sharded per ticker,
resumable, flushed percent progress in a log deleted on completion,
dispatched to `backtest-runner`.

## 4. Pre-registration

### 4.1 Stages (v72 funnel; identical thresholds to v88/v90)

1. **Stage 1 — selection**, on **2018-06-01..2020-12-31** only. Eligible iff
   (a) alert-volume cut ≤ 25% vs baseline, (b) `ΔExpR ≥ −0.01R`, (c)
   mix-standardised `ΔWR > 0`. Select the **greatest `ΔExpR`**; ties →
   greater `ΔWR`, then smaller `N`. **Plateau:** `plateau_report`
   (tolerance 0.03R) on `N` and `k`, holding the others at the selected
   values; `trigger` is categorical — both rows reported, not
   plateau-checked. Any spike disqualifies. **No eligible cell →
   `NO_ELIGIBLE_CELL`; a spike → `SPIKE`.**
2. **Stage 0 — MDE** on the selected cell: `validate_component.py --stage
   mde`, `observed_days` = train window length, `target_days = 730`. Below
   MDE → refused, budget intact.
3. **Stage 2 — walk-forward**, selected cell only, fold-test 2021 / 2022 /
   2023: ≥ 2 of 3 folds improving, no fold worse than −1.0pp, per-fold
   N ≥ 30.
4. **Stage 3 — VALIDATION, one shot**, 2024-01-01..2025-12-31: clauses 1–5;
   clause 6 `SKIPPED` (not a subset feature) and a SKIP never blocks. A
   missing permutation p is a FAIL.

Clause (c) carries the partner's standing constraint: no cell that lowers
`ΔWR` can be selected at any expectancy.

### 4.2 Permutation — random-delay null

n = 200, seed 42. Population: every arm that triggered (issued or regated);
each permutation redraws its trigger bar uniformly from `[i, i + N]` and
enters by stop-entry at that bar's high. Statistic: mix-standardised `ΔWR`
vs baseline. It asks whether the *structure break* carries information
beyond simply waiting.

### 4.3 Integrity guards

- **VALIDATION lock in code:** the instrument refuses 2024–25 unless handed
  a Stage 2 results doc reading **Overall: PASS**.
- **What has been inspected.** The Stage 1 window was broken out by
  *reaction kind* for v88/v90; it has **never** been inspected for swing
  structure. Folds 2021–23 and 2024–25 have never been inspected by either.
  No one may query any v88/v90/v121/v125 output for structure-break
  behaviour outside the Stage 1 window before the corresponding stage runs.
- **v125's report must not run before this spec and its plan are
  committed** (v125 §Scope ordering constraint), and its tables may not
  change this grid.
- **Population disclosure:** the Stage 1 results doc reports, per cell, how
  many arms ended issued / regated / `cancelled_zone_failed` / `expired`,
  and the alert-volume ratio vs baseline — the v88 volume blow-up must be
  visible if it recurs.
- **Truncation tests** on the state machine: `full.iloc[:-1] == trunc`, and a
  pivot confirmed at bar `p + 3` cannot trigger before it.
- **Recorded limitations,** quoted in every results doc: daily-bar ordering
  is conservative (stop before target on the same bar); the universe is
  today's cached tickers (survivorship).

### 4.4 Outcomes

| Result | What happens |
|---|---|
| `NO_ELIGIBLE_CELL` / `SPIKE` / MDE refused / Stage 2 FAIL | Closed, VALIDATION budget intact. Row added to `backtest-methodology.md`'s closed table. |
| Stage 3 FAIL | Closed, budget spent, recorded as-is. |
| Stage 3 PASS | Closed PASS, recorded. A live ARMED lifecycle is brainstormed and specced next. |

## 5. Dependencies

- **v121 must be merged** (`confirmed_pivots`). Implementation starts by
  verifying that symbol on `main`.
- Independent of v125's code; ordered before v125's report (§4.3).

## 6. Deliverables

- `swingbot/core/backtesting/structure_arm.py` — the walk (§3.1), touch
  episode bookkeeping, the per-cell replay reusing `armed_replay`'s plan
  construction / regates / exit simulation, the permutation population.
- `swingbot/core/backtesting/armed_measurement.py` (or a sibling) — the
  12-cell grid and scoring, reusing `CellScore` / selection / plateau code
  without changing v90's grid.
- `scripts/backtest/measure_structure_arm.py` — run / select / stage
  subcommands mirroring `measure_armed_entries.py`; `OUT_ROOT = data/v126`.
- Results under `docs/superpowers/results/`: Stage 1 selection (full
  12-cell table, plateau reports on `N` and `k`, the rule quoted, the
  population disclosure), then each later stage reached.
- Close-out: the closed-table row in `backtest-methodology.md`, whatever the
  verdict.

## 7. Testing

- Walk: an `MSB` frame triggers at the first close above the confirmed SH;
  an `HL` frame does not trigger on the same break without the higher low,
  then does once it is confirmed; a close below `L − 0.10·ATR` cancels; no
  trigger by `i + N` expires; bearish mirrors of each.
- A swing high whose pivot bar is `p` cannot trigger before bar `p + 3`.
- Touch episode: a level re-tested immediately after its arm terminates does
  not re-arm; after a close `> (k+1)·ATR` away it does; a different level
  arms independently.
- Plan: stop-entry at the trigger bar's high, `expiry_bars = 2`, stop
  `min(level, L) − 0.10·ATR`.
- v88/v90 regression: their existing tests pass unchanged (the sibling
  module does not touch `armed_replay.py`'s walks).
- Permutation determinism (seed 42 → identical p).
- One full-suite run, as the plan's final task, before the first long run.

## Parallelisation

- **Group 1 (parallel):** the 12-cell grid + scoring module and its tests;
  the measure script's CLI skeleton.
- **Sequential:** the `structure_arm.py` walk first (every replay task
  consumes it), then the per-cell replay, then the permutation population.
  Full suite after the last code task and before the first long run. The
  stages run strictly in order — Stage 1, then 0, then 2, then 3 — each gated
  on the previous result doc.
