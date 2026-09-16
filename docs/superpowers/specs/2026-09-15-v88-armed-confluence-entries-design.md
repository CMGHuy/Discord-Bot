# v88 — Armed confluence entries: waiting for price to react at the level

**Version:** ui 1.18.2 · bot 1.9.0
**Bump:** none (A1 is scripts and results only). A2, if it is ever written,
is its own document with its own `Bump:`.
**Edge:** expectancy
**Date:** 2026-09-15

## 1. Why this exists

The confluence scan is the largest population in the book and its only
negative one (backtest pool 53.5% / −0.171R, N=4641; the live book on
2026-09-10 was 80% confluence-sourced at −0.136R). The human partner asked
for ways the bot can **identify a plan better** — see the signal, read the
candle — and chose, in the 2026-09-15 brainstorm, to measure setup
selection on daily bars first (this spec), with intraday bars archived in
parallel for later (v87).

What a confluence plan waits for today (`backtest_scenarios.replay_scenarios`,
`levels.build_scenarios`, `builders.build_confluence_plan`):

- Every bar, a scenario is built **entered at that bar's close**, stop at the
  nearest real support (bullish) 2–7% away, target at the nearest resistance,
  reward:risk >= 1.5, and >= 2 strategies confirming the target.
- **Nothing requires price to have tested the stop level, or to have reacted
  there.** A stock drifting mid-range qualifies exactly like one that just
  bounced off support. Both directions can qualify on the same bar.
- The existing candlestick factor (`candlestick_patterns.py`, confidence
  factor F) asks only whether the last two bars formed a named pattern,
  *anywhere*. E34 candle-quality-at-a-level shipped as an unwired pure
  function (`results/2026-07-26-edge-folds.md`: never measured, so a first
  measurement is not a re-run).

**Hypothesis.** Confluence setups whose entry waits for a test of the stop
level followed by a price reaction there win more often, at no worse
expectancy, than setups entered immediately.

## 2. Decisions taken in the brainstorm (human partner, 2026-09-15)

1. **Layer A** (setup selection on daily bars) first; intraday entry timing
   is archived forward instead (v87); leading signals parked.
2. **Wait for confirmation**, not a veto and not a label: a scenario arms,
   and only a reaction at the level turns it into a plan.
3. In the live product, an armed scenario **shows under Pending with an
   `[ARMED]` note**; on confirmation it becomes PENDING or goes OPEN directly.
4. **Both entry modes go to TRAIN** (§3.4) and fold-train selection picks one
   before VALIDATION.
5. **Measure first.** A1 is measurement only; A2 (the live ARMED lifecycle)
   is written only if A1 passes VALIDATION.

## 3. The armed replay (A1)

Confluence-sourced plans only; strategy-sourced plans are untouched. All of it
on daily bars, under the NO-LOOKAHEAD rule: everything decided at bar `j`
reads `df.iloc[:j+1]` only.

### 3.1 Arming — and the widening

At bar `i`, arming runs the same scenario construction as today with **one
gate relaxed**: `min_stop_distance_pct` is 0 at arm time. Every other gate
(reward %, max stop distance, reward:risk, target confluence count,
dead-cat-bounce veto) is unchanged. The armed record keeps `direction`, the
level `L` (the scenario's stop price) and `i`.

That relaxation is this spec's **widening**. Today's scan discards a scenario
whose stop is under 2% away — which is precisely when price is *sitting on*
support. Those scenarios can now arm, and the 2% gate is re-applied at
confirmation against the re-anchored stop (§3.3). Without it the arm could
only ever remove trades.

One armed scenario per `(ticker, horizon, direction)` at a time; a new arm for
the same key is ignored while one is live. The existing 5-bar cooldown applies
from each issued plan, as today.

### 3.2 Test and reaction

Window: bars `j` in `[i, i + N]`. Bullish shown; bearish is the exact mirror
(highs for lows, `>=` for `<=`). `ATR_j` = `indicators.atr(window, 14)` at `j`.

- **Test:** `Low_j <= L + k·ATR_j` (a touch within `k` ATR, or a pierce).
- **Reaction**, on a bar at or after the first test bar:
  - **R1 rejection:** bar `j` is itself a test bar, `range_j > 0`, lower wick `min(Open_j, Close_j) − Low_j
    >= 0.5·range_j`, `Close_j >= Low_j + (2/3)·range_j`, and `Close_j >= L`.
  - **R2 follow-through:** `Close_j > High_{j−1}`, with a test on `j` or `j−1`.
  - **R3 reclaim:** some bar in `[max(i, j−2), j−1]` — inside the arm window — closed below `L`, and
    `Close_j >= L`.
  - The first bar satisfying any of them confirms. When one bar satisfies
    several, the strongest names it: R3 > R2 > R1.
- **Expiry:** no reaction by `i + N` → `expired_unarmed`, no plan.
- **Cancel before confirmation:** `High_j >= T1` (the target traded first), or
  a close below `L` not reclaimed within 2 bars → `cancelled_armed`, no plan. The target check starts on the bar after the arm bar; when one bar both reaches the target and reacts, the cancel wins.

The reaction set is **fixed, not gridded** — it is the definition under test,
and gridding it would multiply the comparisons the plateau check must survive.

### 3.3 Stop, target and re-gating at confirmation

- **Stop** `S = min(L, lowest Low from the first test bar through j) − b·ATR_j`.
- **Plan** built through `build_confluence_plan` on `df.iloc[:j+1]` with the
  as-of-`j` level map and a scenario carrying stop `S` — the same constructor,
  target selection (`MIN/MAX_RISK_REWARD_RATIO` 1.5–2.5) and badge/cohort
  stamping as live. Then the entry is set by the entry mode (§3.4).
- **Every gate re-checked against the final entry `E` and stop `S`:** stop
  distance within `[min_stop_distance_pct, max stop]`, reward % >= floor,
  reward:risk inside the band, target confluence >= the configured minimum
  recomputed at `j`. Any failure → `cancelled_regate`, no plan. **A plan is
  never adjusted to fit a gate.**
- Frozen constants untouched: `BREAKEVEN_TRIGGER_FRACTION = 0.5`,
  `tp1_fraction = 0.50`, the reward:risk band.

### 3.4 Entry modes

| Mode | Rule |
|---|---|
| `M1 stop` | Every confirmation → `entry_type="stop_entry"`, trigger `High_j` (bearish: `Low_j`), `expiry_bars = 2`. |
| `M2 split` | R3 or R2 → `entry_type="market"` at `Close_j`. R1 → as `M1`. |

The exit simulator already models both: a market entry fills at the signal
bar's close, a stop-entry scans forward for a trigger touch and returns
`not_triggered` on expiry or invalidation (`exit_sim.simulate_exit`). Exits
run `scale_out=True` with the current exit model, as the baseline does.

### 3.5 Grid — 24 cells

| Knob | Values |
|---|---|
| mode | `M1`, `M2` |
| `N` arm window | 3, 5, 10 bars |
| `k` test proximity | 0.25, 0.5 ATR |
| `b` stop buffer | 0.10, 0.25 ATR |

**Baseline arm:** today's `replay_scenarios` on the same tickers, horizons and
window. **Width:** full cached universe × all 10 horizons, as v82 ran.

**What counts as an alert** (clause 4's volume): every issued plan on either
arm, including a stop-entry that ends `not_triggered` — it was posted. Armed
scenarios that expire, cancel or fail re-gating were never posted and do not
count.

**Cost.** The level map and the confluence counts dominate replay cost. They
are computed once per `(ticker, horizon)` and cached by bar (levels already
refresh per 5-bar bucket); the 24 cells replay the cheap part — reaction
detection, plan construction, `simulate_exit` — over that shared stream.
Shards per ticker, resumable, a flushed percent figure in a progress log
deleted on completion, dispatched to `backtest-runner`.

## 4. Pre-registration

### 4.1 Stages (v72 funnel; no constant changes)

1. **Stage 1 — selection**, on the **earliest fold's train window,
   2018-06-01..2020-12-31** only (it precedes all three fold-test years). A
   cell is **eligible** iff (a) alert-volume cut <= 25% vs baseline (clause 4),
   (b) `ΔExpR >= −0.01R` (clause 2's margin), (c) mix-standardised `ΔWR > 0`.
   Among eligible cells, select the **greatest `ΔExpR`**; ties → greater `ΔWR`,
   then smaller `N`. `ExpR` ranks first per `edge-priorities.md`; the gate
   itself still scores win rate.
   **Plateau:** `backtest_wf.plateau_report` (`PLATEAU_TOLERANCE_R = 0.03`) on
   each ordered knob — `N`, `k`, `b` — holding the other knobs and the mode at
   the selected values. Any spike disqualifies. Mode is categorical and has no
   neighbour.
   **No eligible cell → `NO_ELIGIBLE_CELL`; a spike → `SPIKE`.** Either is a
   finished, negative measurement.
2. **Stage 0 — MDE**, on the selected cell: `validate_component.py --stage mde`
   with the Stage 1 effect, `observed_days` = the train window's length,
   `target_days = 730`. Below MDE → **refused, budget intact.**
3. **Stage 2 — walk-forward**, selected cell only, fold-test 2021 / 2022 /
   2023: >= 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N >= 30.
4. **Stage 3 — VALIDATION, one shot**, 2024-01-01..2025-12-31: clauses 1–5;
   clause 6 reports `SKIPPED` (this is not a subset feature —
   `population_split` sees added and changed trades) and a SKIP never blocks.
   A missing permutation p is a FAIL.

### 4.2 The permutation — a random-delay null

`permutation_test.py` shifts strategy entries through `run_folds` and cannot
see this feature, so the null is purpose-built: **does the reaction carry
information beyond simply waiting?** n = 200, seed 42. Each permutation keeps
the same set of armed scenarios that confirmed in the real run, and moves each
confirmation to a bar drawn uniformly from its own `[i, i + N]` window,
building the stop, entry and gates by §3.3–3.4 exactly as if that bar had
reacted. The stop anchors from the first test at or before the drawn bar, or
from the arm bar when nothing has tested yet; the entry mode follows the
arm's real reaction kind. The population is every arm that confirmed in the
real run, issued or regated. The statistic is mix-standardised `ΔWR` vs
baseline; `p` = the share of permuted `ΔWR >=` the real `ΔWR`.

### 4.3 Integrity guards

- **VALIDATION lock in code:** the instrument refuses to replay 2024–25 unless
  handed a Stage 2 results doc reading **Overall: PASS** (v82's pattern).
- **Truncation tests:** reaction detection and the arm state machine each get
  a `full.iloc[:-1] == trunc` test; every boolean is `.fillna(False)`.
- **No search can touch it.** The four knobs live as constants in the
  measurement module, not as `config.Field`s, so no v75-style grid sweeps them.
- **Recorded limitations,** quoted in every results doc: daily-bar ordering is
  conservative (stop before target on the same bar); the universe is today's
  cached tickers (survivorship); `M2`'s market entry fills at a close the live
  reader could not have traded (§5).

### 4.4 Outcomes

| Result | What happens |
|---|---|
| `NO_ELIGIBLE_CELL` / `SPIKE` / MDE refused / Stage 2 FAIL | Closed, VALIDATION budget intact. Row added to `backtest-methodology.md`'s closed table. A2 not written. |
| Stage 3 FAIL | Closed, budget spent, recorded as-is. A2 not written. |
| Stage 3 PASS | Closed PASS, recorded. A2 brainstormed and specced next. |

## 5. A2 — the live ARMED lifecycle (not built by this spec)

Recorded so the design survives if A1 passes; written as its own document only
then.

- `PlanStatus.ARMED`, **a real status, not PENDING plus a flag.** Every
  consumer of PENDING treats it as an order — `_step_pending` fills on a
  trigger cross, the v81 execution feed posts a ticket — and a flag one of
  them misses would fill a paper trade or ping the real-money channel for an
  unconfirmed setup. A consumer that does not know ARMED ignores it.
  Transitions `ARMED → {PENDING, ACTIVE, CANCELLED}`.
- **Displayed under Pending with an `[ARMED]` note**; never on the execution
  feed until it becomes PENDING or ACTIVE.
- Reactions evaluated on **completed** daily bars only (post-close scan). If
  `M1` is selected this is executable as-is: a stop-entry posted after the
  close rests for the next session, which is what the simulator models. **If
  `M2` is selected, A2 must first decide the live analogue of a market entry at
  a close** — a late-session scan against a partial bar is a live/backtest
  divergence that needs naming, not glossing.
- Open questions for A2's brainstorm: does an ARMED scenario count against
  one-trade-per-ticker (v19) or portfolio heat? Behind a `CONFLUENCE_ARMING`
  flag, default off until the verdict.
- v67: ARMED touches `plan_store._OPEN_STATUSES` and the plans `doc`; A2 adds
  the matching note to v67 task P2-07.

## 6. Deliverables (A1)

- `swingbot/core/market/reaction.py` — pure test/reaction detection (R1–R3),
  no config reads. In `market/` rather than `backtesting/` so A2's live path
  and the replay share one source, as `entry_filters.py` does for strategies.
- `swingbot/core/backtesting/armed_replay.py` — the arm state machine, stop
  re-anchoring, re-gating, both entry modes, and the random-delay permutation.
- `scripts/backtest/measure_armed_entries.py` — `replay` / `select` / `arms` /
  `permute` subcommands on v82's shape (sharded, resumable, progress log).
- Results under `docs/superpowers/results/`: Stage 1 selection (full 24-cell
  table, plateau reports, the rule quoted), then each later stage reached.
- Close-out: the closed-table row in `backtest-methodology.md`, whatever the
  verdict.

## 7. Testing

- R1/R2/R3 each on a hand-built `make_ohlcv` frame that fires, and a near-miss
  that does not; bearish mirrors.
- Arm → confirm → plan, and arm → `expired_unarmed` / `cancelled_armed` /
  `cancelled_regate`, each on a synthetic frame.
- The widening: a scenario with a 1.5% stop is refused by baseline replay,
  arms here, and issues a plan when the re-anchored stop clears 2%.
- Entry modes: `M1` yields a stop-entry at `High_j` with `expiry_bars = 2`;
  `M2` yields market for R2/R3 and stop-entry for R1.
- Truncation tests (§4.3) and a permutation determinism test (seed 42 →
  identical p).
- One full-suite run, as the plan's final task.

## Parallelisation

- **Group 1 (parallel):** `reaction.py` + its tests; the measurement script's
  CLI skeleton, sharding and progress log (against a stub replay).
- **Sequential:** `armed_replay.py` after `reaction.py` (consumes its
  detectors). The permutation after `armed_replay.py` (reuses its §3.3 path).
  Wiring the script to the real replay after both. Runs strictly in stage
  order — Stage 1, then 0, then 2, then 3 — each gated on the previous result
  doc. The full-suite run after the last code task and before the first long
  run.
