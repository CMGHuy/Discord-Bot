# v178 — Pre-registered test of runner give-back levels: range-multiple and profit-share arms

**Version:** ui 1.31.0 · bot 2.12.0 (at writing)
**Bump:** bot patch — Phase A adds inert simulator modes behind a default that leaves the live v176 rule byte-identical; nothing the user sees changes. Phase B (live parity) exists only if an arm passes the one-shot VALIDATION, and is then its own spec.
**Edge:** harvest — locks in more of a runner's run before a reversal. Prediction: a small paired ΔExpR against the live fixed 5% (|Δ| under 0.05R; the v176 5% rule measured +0.003R and the two earlier tighter-trail rules measured near zero), sign unknown. The base case is that no arm clears stage 0 (see Stage 0).
**Screen:** harvest-headroom docs/superpowers/results/2026-10-02-v123-runner-headroom.md
**Panel:** risk-manager, veteran-trader, quant-researcher
**Status:** spec written 2026-10-19 from a chat with the partner, who asked for a pullback level that adapts to each trade instead of one fixed percentage, chose to test both families as separate arms, and ruled the v92 overlap a new test (below). Revised the same day after the full panel (quant-researcher, risk-manager, veteran-trader).

## Why

The v176 give-back stops the runner 5% off its best price. Its TRAIN measurement
(`docs/superpowers/results/2026-10-19-v176-giveback-train.md`) was NO-LIFT: ΔExpR
+0.0030R, interval [−0.0124, +0.0159] on the close basis, +0.0100R,
[−0.0071, +0.0258] on the high/low basis. Of the 334 give-back exits, 157 (47%)
were followed by a new best price within 10 daily bars.

A fixed 5% is a different bet on each stock. On a name whose daily range is 8%
of price (RKLB, ATR 4.16 on a 60.67 entry) 5% is about 0.6 of one day's normal
move, so ordinary noise can end the runner. On a calm name it is more than two
days' range. The partner's question: what pullback should end a runner so it
takes profit before the move reverses and gives everything back, with no hard
limit assumed?

This spec does not claim an answer. It pre-registers a small set of
adaptive rules, written down before any is run, and puts them through the
repo's harvest funnel.

## The rules (all frozen before any result is read)

Every rule is another tightening term on the runner stop, exactly the shape of
the v176 give-back: `stop = tightest(existing stop, level)`, active from the
bar after the best price is set, long mirror and short mirror. `E` is the
runner's best price since TP1, `ATR_j` the daily ATR(14) at the bar being
processed, `entry` the original fill.

| Family | Level (long: `E − allowance`, short: `E + allowance`) | Arms |
|---|---|---|
| **R, range multiple** | `allowance = k × ATR_j` | `k` ∈ {0.75, 1.0, 1.25} |
| **S, profit share with a range floor** | `allowance = max(f × |E − entry|, 1.0 × ATR_j)` | `f` ∈ {0.25, 0.33, 0.50} |
| control A | the live v176 rule, fixed 5% of `E` | 1 |
| control B | no give-back (flag off) | 1 |

- Six candidate arms (R×3, S×3) and two controls. The floor in family S is
  fixed at 1.0 × ATR and is not a grid axis.
- **Timing.** The level is set at the close of bar `j` from `E` and `ATR_j`
  (ATR(14) through bar `j`), and first tests bar `j+1`. The tested bar's own
  range never enters its level, so there is no lookahead. A news bar's large
  true range does raise ATR for the next 14 bars; that is part of the rule and
  is reported (see the earnings/true-range split).
- **Never widens, never beyond the floor.** Each level goes through
  `tighter_stop` (`exit_sim.py:272-276`), as the v176 give-back does, so a
  rising ATR or a falling `E`-based level cannot loosen the stop. The runner
  stop starts at `runner_floor` (entry + 2/3 of tp1 − entry,
  `exit_sim.py:555-556`) and is only ever replaced by something tighter, so no
  arm can end on the loss side of entry or beyond 1R. A wide arm whose
  allowance exceeds the profit already made simply never binds below the floor;
  the worst-case exit of every arm is the floor. Corollary: a wide arm is the
  chandelier or floor alone, so its paired difference against control A mostly
  measures "the 5% removed" rather than "k × ATR added".
- Worked example 1, RKLB short (volatile; entry 60.67, `E` = 49.94, profit
  10.73, ATR 4.164): fixed 5% exits at 52.44; R 0.75/1.0/1.25 at 53.06 /
  54.10 / 55.14; S 25/33/50% at 54.10 / 54.10 / 55.31 (the floor binds for
  the first two). Every arm is wider than 5% here.
- Worked example 2, a calm long (entry 100, `E` = 112, profit 12, ATR 1.5):
  fixed 5% exits at 106.40 (allowance 5.60); R 0.75/1.0/1.25 at 110.88 /
  110.50 / 110.13 (allowances 1.13 / 1.50 / 1.88, a fifth to a third of 5%);
  S 25/33/50% at 109.00 / 108.04 / 106.00 (allowances 3.00 / 3.96 / 6.00).
  On a calm name the arms are tighter than 5%, the opposite of RKLB, and
  pooled ΔExpR can net the two cases against each other. Each arm's allowance
  as a share of price (median, 10th and 90th percentile) is reported next to
  the results.
  These are arithmetic, not results.
- The runner stop's source (`runner_stop_source`, `exit_sim.py:279-288`) labels
  a stop "giveback" by comparing it to a level recomputed from the current
  extreme. An ATR-dependent level set on an earlier bar would not match and be
  mislabelled "trail", so for the new modes the level is carried with the stop
  (the source is recorded at the ratchet).

## Ruling on the v92 overlap (the partner, 2026-10-19)

v92 `ADAPTIVE_RUNNER_TRAIL` (closed, `backtest-methodology.md` § Closed
pre-registrations; record `results/2026-09-16-v92-adaptive-trail-train.md`) tested
the chandelier multiple at {1.5, 1.75, 2.0} after a trigger profit {1.5, 2.0,
2.5}R since entry, and found no lift. Its record notes that, because TP1 already
sits at 1.5–2.5R, its low-trigger cells fired on the first runner bar, so it
"is closer to a tighter trail from TP1", with the tightest multiple, 1.5, the
least-bad column; the same record says "a trigger measured from TP1 itself
would be a genuinely new mechanism, not a re-run of this one".

Family R is therefore **adjacent** to v92: lower multiples (all below 1.5),
anchored at the best price since TP1 with no trigger. The same is true of family
S wherever its 1.0 × ATR floor binds. The partner ruled both a new test, not a
re-run, with these conditions:

- No v92 cell is re-run, re-gridded or re-used. No arm here has a multiple
  inside {1.5, 1.75, 2.0}.
- The overlap is disclosed in every result doc. The nearest v92 cell
  (`trigger_r=2.50, mult=1.50`, ΔExpR −0.0045R to +0.0091R across its grid, best
  cell lower bound −0.0131R) is quoted beside each R arm as context, never as a
  threshold.
- A result in the direction v92 leaned is not a replication claim and a null
  result does not reopen v92.

## Not the Stage −2 screen

An exit rule is not an entry idea, so no `SCREEN-PASS` row applies. The
`**Screen:**` line cites the v123 headroom measurement, as v176 does. This is
`Edge: harvest`, so it states the gate it uses instead of the acceptance funnel:
the harvest gate (`acceptance_harvest.evaluate_harvest`, v92) through the same
four stages.

## The test, stage by stage (the rules below are frozen now)

The comparison is **paired on the same entries**, against the live fixed 5%
(control A) as the baseline. Control B is reported for context.

| Stage | Window | What happens | Closes the arm if |
|---|---|---|---|
| −1 reachability | pilot | the arm's knob is reachable by replay and changes at least one outcome | unreachable, or zero changed outcomes: refused, budget intact |
| 0 MDE | fold-train | `--train-effect-r` is the **measured** pooled fold-train paired ΔExpR (arm − control A) over the three fold-train windows, compared with `acceptance.mde_paired` on the same pairs | effect below the MDE: shot refused, budget intact |
| 1 plateau | fold-train (2018-06..2020 / ..2021 / ..2022) | `plateau_report()` (`backtest_wf.py:36`) per family, adopted value = the arm with the highest pooled fold-train ΔExpR, plus the extra rule below | a spike with unstable neighbours: closed |
| 2 walk-forward | fold-test 2021 / 2022 / 2023 | the **harvest** walk-forward gate (`validate_component.py --gate harvest` → `backtest_wf.gate`): ΔExpR per fold, at least 2 of 3 folds improving over control A, no fold worse than −`GATE_MAX_DEGRADATION_R` (0.05R); a fold counts as improving only with at least 30 changed outcomes in it | fails: closed |
| 3 validation | 2024-01-01..2025-12-31 | **one shot**, for the single surviving arm, all clauses of the harvest gate | any clause fails: closed; the live 5% stays |

- **Stage 0 base case.** v176's paired MDE on this entry population was
  0.0181R and the prior effect is about 0.01R, so every arm being refused at
  stage 0 is the expected outcome, not a risk. A refusal is a finished result;
  the 5% stays live. Changed-outcome counts are reported beside every MDE
  (fewer changed trades shrink the MDE, as v123's 0.0009–0.0024R did).
- **Stage 1 extra rule.** `PLATEAU_TOLERANCE_R` (0.03R) is larger than the
  prior effect, so `plateau_report` alone disqualifies little. Added and
  frozen: an adopted arm proceeds only if all three arms of its family have a
  fold-train ΔExpR (vs control A) of the same sign as the adopted arm on at
  least 2 of the 3 fold-train windows. An edge arm (k 0.75 or 1.25, f 0.25 or
  0.50) has one neighbour in `plateau_report` and faces this same family-wide
  rule. An arm refused at stage 0 still counts as a neighbour: stage 0 gates
  the shot, not the measurement.
- **At most one arm reaches stage 3**: the one with the best stage-2 mean
  paired ΔExpR among those that passed stages 1–2. If both families have
  survivors, the larger mean goes through; the other is closed unspent. Ties go
  to the simpler rule (family R).
- **Near-duplicate arms.** Family S collapses toward R at k = 1.0 wherever the
  1.0 × ATR floor binds, which is whenever profit since entry is below 4 / 3 /
  2 ATR for f = 0.25 / 0.33 / 0.50. Reported for each S arm: the share of
  runner exits where the floor binds, and the number of trades whose outcome
  differs from R k = 1.0. The "six arms" are six rules but fewer than six
  distinct behaviours, and the Holm adjustment is conservative by that margin.
- **Counting.** One ledger row per pre-registration (`v178-giveback-levels`),
  not per arm, with the number of arms and cells in its hypothesis text. Its
  `p` is the stage-3 p if stage 3 ran, otherwise the best arm's pooled
  fold-train p; the record names which. The result reports a Holm-adjusted p
  across the six arms. `cells_looked_at` is frozen as: 6 arms × (3 fold-train
  + 3 fold-test) = 36 gating cells, + 6 arms × 10 horizons = 60 per-horizon
  descriptive cells, + 6 control-B comparisons, + 6 arms × 7 descriptive
  blocks = 42, + a trend/chop regime split for each family's best arm and the
  survivor (3 × 2 = 6) = **150**, plus the sensitivity runs below if they run.
  A concentration line is reported: the top-2 horizons' share of ΔR and the
  long/short split.
- **The seven descriptive blocks per arm** (reported, never thresholds, defined
  now so they are not chosen after the results):
  1. drawdown and dollars at fixed risk ($100 per trade, as v176), off against
     on, on the same paired entries;
  2. allowance as a share of price (median, 10th, 90th percentile);
  3. exits followed by a new best price within 10 bars (the v176 statistic,
     157 of 334 = 47%) and runners stopped within 3 bars of setting `E`;
  4. open profit given back at exit, in R and in dollars at fixed risk, with
     its 95th percentile and maximum, and the share of exits that gapped
     through the stop (filled worse than the level), counted as the loss they
     are;
  5. stop moves per runner (how often the stop level changes, counted from the
     arm's own simulation);
  6. the worst calendar week's summed give-back dollars across simultaneous
     runners;
  7. ΔExpR split by whether an earnings gap or a day with true range above
     2 × ATR fell in the runner window.
- **Horizon trade-off.** One daily-ATR multiple applies to every horizon from
  2w to 9m, and a 9m runner's normal pullback is a multi-week swing. A pooled
  pass with the long horizons clearly negative goes to the partner as a
  trade-off, not as a clean pass. A horizon-scaled multiple is a new
  pre-registration.
- **Gate clauses.** The harvest gate's `win_rate_floor` is `SKIPPED` (a post-TP1
  rule cannot move the TP1-touch win rate) and `volume_floor` does not apply
  (the count of trades is unchanged). Win→non-win outcome flips are disclosed.
- **Uncertainty.** The gating interval is the harvest gate's ticker-cluster
  bootstrap. A `week_cluster_bootstrap` interval is reported beside it
  (descriptive, never gating), because give-back exits cluster in market-wide
  reversal weeks.
- **Sensitivity.** Live follows ticks, the simulator follows closes, and the
  gap matters more for a 0.75–1.0 × ATR allowance than for 5% (intraday
  retracement from the high can trip a tight level). The high/low-basis run is
  therefore done for the tightest arm (R k = 0.75), for each family's best
  arm and for the survivor, **TRAIN-side only** (fold-train and fold-test).
  Until it is read, a close-basis result for a tight arm is stated as an
  upper bound on the live result. VALIDATION is read once, for the gating
  stage-3 run, and never for the sensitivity.
- **Stage-3 readings fixed now.** Beside the gating arm-vs-A reading, the
  record reports A-vs-B and arm-vs-B on VALIDATION. v176 found A no better
  than B on TRAIN, so an arm that beats A could still be no better than B.
- Frictions: non-zero slippage and commission in every arm, from
  `swingbot/core/edge/frictions.py`.
- Data source `yfinance`, the 75-ticker cache, both engines, all ten horizons,
  `scale_out=True`, instrument v1. Stated in the frozen block before any window
  is read.
- **Disclosure.** The v176 measurement already read TRAIN for control A (and
  its tick sensitivity). The arm grid above was set with that knowledge of a
  neighbouring rule, not blind to it. Control A's numbers are known and set no
  threshold here.

## Phases

**Phase A: simulator and measurement (this spec).** Add the two families to
`giveback_stop` and to the simulators as **simulator-only module constants**
(`GIVEBACK_MODE` ∈ {`pct` (default), `range`, `profit_share`}, `GIVEBACK_K`,
`GIVEBACK_F`, next to the v176 `GIVEBACK_EXTREME_BASIS`), set by the
measurement script. They are not `.env` fields: `plan_manager.py` calls
`giveback_level` and `runner_giveback_pct`, so a mode read from config inside
them would change live behaviour on a SIGHUP. The default `pct` keeps the live
v176 rule and all existing tests unchanged, and nothing in `plan_manager.py`
changes. The measurement runs through a bespoke script on the v176 template
(`scripts/backtest/measure_runner_giveback.py`), not the standard arm producer.

**Phase B: live parity, only after a stage-3 pass.** The live tick path and the
bar catch-up path need the arm's level from `atr_fn` and the stored extreme.
That is a separate spec, its own panel, and the partner's go-ahead. Until then
production keeps the fixed 5%. Phase B's spec must settle, at least:

- a `stop_moved` alert on every stop change, a minimum move worth acting on and
  tick-size rounding, because an ATR-based level can move every day even when
  `E` has not (the v176 5% rule moves only when `E` ratchets). The arm's
  stop-moves-per-runner count from Phase A is a pass/fail input to that
  go/no-go;
- whether `E` and the stop checks use regular-session ticks only (a thin
  pre- or after-hours print can set `E` or trip a tight level; the simulator
  has no such prints and Phase A excludes the effect);
- the limits of the 75-ticker cache: liquid names only, so the results say
  nothing about thin names, where ATR is noisy. Every result doc states this.

Portfolio heat is unchanged in Phase A and B: `swingbot/core/edge/heat.py` does
not read `working_stop`, runner or `tp1`, and a post-TP1 runner is already
locked at or above entry. The portfolio effect that does exist is
concentration (several runners reversing in the same market-wide week), which
descriptive block 6 reports.

## Out of scope

- Changing the live percentage or turning the v176 rule off.
- Any entry idea, TP1 or TP2 change, or sizing.
- A grid larger than the six arms above. A result that suggests a different
  level (a `k` of 0.5, a different `f`) is a new pre-registration, not a tweak.

## Risks

- **Six arms at roughly 0.01R effects.** The earlier tests of similar rules
  closed near zero. The most likely outcome is a refusal at stage 0 or a
  NO-LIFT. That is a finished result, and the 5% stays live.
- **A volatility-scaled stop can be wide in a real drawdown.** A 1.25 × ATR
  allowance on a name with an 8% daily range is a 10% give-back, bounded
  below by the floor and above by the chandelier. Descriptive blocks 1 and 4
  report drawdown, dollars at fixed risk, and the distribution of open profit
  given back at exit with its 95th percentile and maximum. They never gate, and
  a better paired ΔExpR with a deeper drawdown or larger give-backs goes to the
  partner as a trade-off.
- **A tight arm can reproduce the shake-out.** A stop 0.75 × ATR from the best
  close sits inside one ordinary day's range; R k = 0.75 is the arm most
  likely to repeat v176's 47% shake-out rate. Block 3 measures it directly.
- **Live differs from the simulator.** The simulator trails the best close, the
  live bot trails the best tick. v176 measured the gap (+0.003R against
  +0.010R). The survivor's TRAIN-side high/low sensitivity bounds it.
- **Real-money orders.** The bot moves only its paper stop. A rule that is
  wider than the live 5% would move the paper stop less often; any switch of the
  live rule needs the partner to move broker stops by hand.

## Testing

- `giveback_stop` for each family: long, short, the floor binding and not
  binding, `E` at entry (zero profit), parameter bounds.
- Never widens, in both simulators and every arm: (a) a day where `ATR_j` jumps
  with no new extreme leaves the stop unchanged; (b) the stop series is
  monotone toward price; (c) an ATR that is NaN, zero or missing yields no
  term, never a wider one (`_safe_atr_value`, `exit_sim.py:584`).
- Floor clamp: an allowance larger than the profit since entry (family S, `E`
  near entry, large ATR) exits at the floor, never on the loss side.
- Stop attribution: for an ATR-dependent level set on an earlier bar,
  `runner_stop_source` still reports "giveback", not "trail".
- Simulator parity: `pct` mode is byte-identical to the v176 simulator on an
  existing fixture; each new mode gives a constructed run-up-and-reversal exit
  at the hand-derived level (RKLB arithmetic above); `exit_sim` and
  `exit_sim_v2` agree on every arm.
- No lookahead: a level is built from the extreme and ATR of the bars before
  the one tested, effective the next bar.
- Funnel plumbing: reachability classifies each knob; stage files refused when
  unstamped or wrong-stage; a result file never overwritten; the stage-1 family
  rule and the per-fold changed-outcome floor are unit-tested on synthetic folds.
- The live path is untouched: the existing v176 tests pass unmodified.

## Code facts the plan must honour

From the code brief (`.superpowers/briefs/2026-10-19-v178-runner-giveback-levels-preregistration.md`);
where the wording above and these differ, these win.

- `_safe_atr_value` is `targets.py:134` and substitutes 2% of entry when ATR is
  NaN or ≤ 0 — a replaced term, not "no term". The new modes get their own
  guard: ATR NaN, zero or missing yields no term, and test (c) asserts that.
  `runner_floor` is defined at `exit_sim.py:304` (`:555-556` is a call site).
- The standard arm producer (`measure_arms.py`) refuses any knob that is not
  REACHABLE in `reachability.REGISTRY`, and `REGISTRY` must equal
  `searchable_attrs()` exactly. The new knobs stay out of `_SEARCH_CLASSES`,
  so a bespoke producer is used (`validate_component.py --bespoke-instrument`,
  its reason recorded in the result), as v176 did. Control B
  (`RUNNER_GIVEBACK_ENABLED=false`) is an excluded knob too.
- Funnel plumbing is partly new code, in the bespoke script, behind unit
  tests: `stage_mde` takes a typed `--train-effect-r`, so the script computes
  the pooled fold-train ΔExpR (the fold-train windows are nested, all starting
  2018-06-01) and passes it; `--stage selection` is the v72 win-rate selector and
  `harvest_select.py` requires `lo95 > 0` and ignores `train_folds`, so stage 1
  is the spec's own rule (`plateau_report` per family plus the family-wide
  same-sign rule); `backtest_wf.gate` (`:205`) already gives 0.05R degradation
  and 2-of-3, but counts closed trades, so the "30 changed outcomes per fold"
  floor is added in the script. `gate_expectancy_harvest` (`:255`) exists but is
  not wired in and is not used. The Holm adjustment has no existing code
  (`stats.ledger_qvalues` is Benjamini–Hochberg); it is a small function in the
  script.
- Frictions: the standard producer books none (`ArmTrade.r_multiple` is gross).
  The script applies them after the fact with `expectancy_attribution.net_r`
  (`:110`), as v176 did; `frictions.py` has only `apply_frictions` and
  `commission_r`.
- Descriptive blocks 2–7 need data `ArmTrade` lacks (exit index, price, stop
  source, ATR, stop-move count): the script derives them from the simulator's
  own results, with the v1 walk's `trace` where a move counter is needed.
- New scripts under `scripts/backtest/` carry no date or year literal, call
  `add_instrument_arg` and one reader (`window_for`, `spec_from_args`,
  `require_v1`), per `tests/backtesting/instrument/test_date_literal_guard.py`.
- `.claude/hooks/guardrails.py` denies a `tune_strategy.py` or
  `run_backtest_range.py` command that names a closed knob. The new knobs are
  not on its list and `measure_*.py` commands are not checked. If a v178 row
  is later closed, its knobs join that list and the methodology table in the
  same commit (a test pins both ways).

## Panel review

Spec review, 2026-10-19 (quant-researcher, risk-manager, veteran-trader).

- quant-researcher 1 [BLOCKING]: family R is adjacent to the closed v92 row -- applied. The partner ruled it a new test; conditions and disclosure written in "Ruling on the v92 overlap".
- quant-researcher 2 [BLOCKING]: stage-2 rule named the win-rate fold gate, which the harvest rule skips -- applied (the harvest dExpR walk-forward gate and `GATE_MAX_DEGRADATION_R` are frozen in the stage table).
- quant-researcher 3: stage-1 plateau under-specified and near-vacuous -- applied (adopted value, family-wide same-sign rule on 2 of 3 windows, edge arms, stage-0-refused arms as neighbours).
- quant-researcher 4: family S collapses onto R k = 1.0 -- applied (floor-binding share and differing-trade count reported; tie-break and Holm noted).
- quant-researcher 5: stage-0 effect number unfrozen; base case unstated -- applied (measured pooled fold-train ΔExpR; refusal of every arm named as the base case; changed counts beside each MDE).
- quant-researcher 6: six ledger rows break the one-row convention -- applied (one row, arms and cells in its text, `p` rule named).
- quant-researcher 7: no `cells_looked_at` formula or concentration line -- applied (108, with the formula; top-2 horizon share and long/short split).
- quant-researcher 8: the high/low sensitivity window was unnamed -- applied (TRAIN-side only; VALIDATION read once).
- quant-researcher 9: control A's relation to control B; grid set after v176 -- applied (A-vs-B and arm-vs-B reported at stage 3; plain disclosure).
- quant-researcher 10: per-fold N ≥ 30 counts all trades -- applied (at least 30 changed outcomes per fold).
- quant-researcher 11: week-clustered interval beside the ticker-clustered one -- applied (descriptive).
- quant-researcher 12: the drawdown trade-off belongs to risk-manager -- handed to risk-manager.
- risk-manager 1: the "never widens" invariant was unstated; ATR varies per bar -- applied (rules paragraph; tests a, b, c).
- risk-manager 2: no arm can end on the loss side or beyond 1R, and wide arms reduce to the floor/chandelier -- applied (floor clamp stated, corollary noted, test added).
- risk-manager 3: the open-profit-at-risk distribution is the report that matters -- applied (descriptive block 4, with 95th percentile and maximum).
- risk-manager 4: a stop that moves daily is operationally worse for hand-managed orders -- applied (stop moves per runner is block 5 and a Phase B pass/fail input).
- risk-manager 5: portfolio heat unaffected; real effect is concentration -- applied (one sentence in Phases; worst-week dollars is block 6).
- risk-manager 6: `runner_stop_source` mislabels ATR-dependent levels as "trail" -- applied (level carried with the stop; test added).
- risk-manager 7: the drawdown/dollar block was undefined -- applied (units, basis and the gap-through share fixed in the seven blocks).
- risk-manager 8: noise survival handed to veteran-trader -- see below.
- veteran-trader 1: Phase B needs a stop-moved alert, a minimum move and tick rounding -- applied (Phases).
- veteran-trader 2: the RKLB example only shows the wider-than-5% case -- applied (calm-name worked example; allowance share of price reported).
- veteran-trader 3: the shake-out itself was never measured -- applied (block 3: 10-bar new-best share and stopped within 3 bars).
- veteran-trader 4: close-basis vs live tick gap matters more for tight arms -- applied (high/low run for R k = 0.75, each family's best arm and the survivor, TRAIN-side only; close basis stated as an upper bound until read).
- veteran-trader 5: the ATR definition read as lookahead -- applied in part. The level is set at the close of bar j from data through j and first tests bar j+1, so the tested bar's range never enters its level (timing paragraph). Applied: the earnings / true-range-above-2×ATR split (block 7). Depth on earnings goes to fundamental-analyst if wanted.
- veteran-trader 6: one daily-ATR multiple for 2w–9m horizons -- applied (a pooled pass with long horizons clearly negative goes to the partner; a horizon-scaled multiple is a new pre-registration).
- veteran-trader 7: extended-hours prints and thin names -- applied (Phase B must decide regular-session-only; results state the liquid-universe limit).
- veteran-trader 8: no regime slice -- applied (trend/chop split for each family's best arm and the survivor; cells_looked_at updated to 150).
