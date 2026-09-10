# v84 — Strategy rescue v2: reopening the WEAK badges

**Bump:** bot minor
**Edge:** expectancy (Tier 1 is `none (integrity)` — see §3)
**Date:** 2026-09-10
**Status:** spec, not yet planned

## 1. Why this exists

On 2026-09-10 the legacy badge refresh
(`results/2026-09-10-legacy-badge-refresh-train.md`) demoted Fibonacci, RSI and
Support/Resistance from `VALIDATED` to `WEAK`, leaving the registry at **2
VALIDATED (MACD, Volume Profile) and 9 WEAK**. That refresh answered "do the
stale badges still hold?" (they don't). This spec answers the next question:
**which of the nine can be legitimately rescued, and by what mechanism.**

Nine per-strategy investigations were run first (2026-09-10, one research pass
per strategy, TRAIN-window only, no VALIDATION budget touched). Their findings
are the substance of §4. Two of them changed the shape of the problem:

- **The staleness cuts both ways.** EMA Crossover's WEAK badge was measured
  against the pre-v31 fixed reward:risk table and the old 80% floor. Re-measured
  under current arithmetic it scores **61.8% WR, N=55, ExpR +0.494** — it clears
  every badge clause with room. MA Ribbon (48.1%) and RSI Divergence (48.0%) are
  likewise near-misses, not the distant failures their stale badges implied.
- **Two strategies need no new mechanism at all**, only a re-derivation of a
  horizon gate that was hand-calibrated before v31 and never revisited.

## 2. Non-negotiables

This campaign operates strictly inside `docs/claude/backtest-methodology.md`:

- **TRAIN and the fold stages are free and repeatable; VALIDATION is one shot,
  ever, per strategy.** No strategy reaches Stage 3 without clearing Stage 1
  (plateau, not a spike) and its applicable fold stage.
- **The fold stage uses two instruments, by design** (added 2026-09-10 during
  planning, after verifying the tooling). Where a mechanism is a `config.Field`
  and a genuine two-arm comparison exists — RSI Divergence, MA Ribbon,
  Support/Resistance, Fibonacci — Stage 2 is the **`gate_win_rate` delta gate**
  (≥2/3 folds improving, no fold worse than −1.0pp, per-fold N≥30), fed by a
  purpose-built arms harness. Where no second arm exists — EMA Crossover (the
  mechanism is unchanged by definition), Break & Retest and VWAP (a
  `STRATEGY_GATES` constant, not a config Field) — Stage 2 is the
  **fold-stability rule**: badge clauses hold in ≥2 of 3 fold years at N≥15
  each, no fold year below −0.05R.
  **Why:** `gate_win_rate` scores a delta between arms. For a strategy whose
  mechanism does not change, every fold delta is exactly `0.0`, so the gate
  fails by construction — EMA Crossover would fail at 61.8% WR. A badge is an
  absolute threshold on its own population; scoring it with a delta gate is a
  category error. Conversely the absolute rule never asks whether the *change*
  helped, so it is not permitted where a real second arm exists.
  **`wf_run.py` cannot produce Stage 2 input** (pooled `delta_expectancy_r`
  only, no per-trade rows) — **a `wf_run.py` PASS is not a Stage 2 pass.**
- **A negative result closes a strategy.** "No configuration cleared the rule"
  is the finished answer, recorded as-is. Nothing in this spec licenses a
  re-run at a looser threshold.
- **Badge threshold is frozen:** `win_rate >= 50`, `expectancy_r > 0`,
  `N >= 30` (train) / `N >= 15` (validation), scratches+timeouts ≤ 50%.
  **The pre-v31 80% floor is not restored for any run here.**
- **No ML in the live path.** Every mechanism below is a deterministic
  rule on an already-computed series.
- Registry rows are machine-generated only
  (`run_backtest_range.py --emit-registry --run-date <date> --pass-wr 50`),
  never hand-edited.

**Closed pre-registrations that no mechanism here may repeat:** `REGIME_ALLOW`
(pool-wide regime gate, 0/44 cells), v32/v33 blended-confidence scores (two
independent failures), `EFFECTIVE_CONFLUENCE` (degenerate), `LEVEL_TOUCH_STRENGTH`
(no lift, post-selection tiebreak), `DEAD_CAT_BOUNCE_VETO` (validation failed),
EMA Crossover's pullback-entry redesign, MA Ribbon's ribbon-width/expansion grid,
RSI Divergence's confirmation-quality (volume-ratio/reclaim-depth) grid, and
RSI's ADX+Bollinger range-regime gate.

## 3. Structure: three tiers

Tiering is by **cost to test**, not by expected payoff — the cheap
confirmations run first so the campaign banks certain wins before spending
effort on speculative ones.

**Tier 1 — re-measurement only, `Edge: none (integrity)`.** No code change to
any signal. These strategies' mechanisms are unchanged; only the arithmetic
beneath them changed, system-wide, in v31. Re-measuring an unchanged mechanism
against new system-wide arithmetic is the same operation v31 itself performed
for Break & Retest, MACD, VWAP and Volume Profile — it is **not** reopening a
closed pre-registration, because the question ("does this mechanism clear the
floor under the arithmetic that now exists?") has never been asked.

**Tier 2 — near-misses, one new axis each, `Edge: expectancy`.** Each sits
within ~4pp of the floor with positive expectancy. Each gets one new mechanism
on an axis no closed pre-registration touched, tested by a small free TRAIN
grid.

**Tier 3 — wide gaps, `Edge: expectancy`, honestly speculative.** Fibonacci has
a concrete, well-motivated mechanism, but a 14.6pp gap is large enough that
failure is a live possibility and an acceptable outcome. (Elliott Wave was the
other Tier 3 candidate until planning withdrew it — see §4.8.)

## 4. Per-strategy hypotheses

### 4.1 EMA Crossover — Tier 1, no new mechanism

**Current state:** WEAK badge from 2026-07-18 (75.0% WR vs the old 80% floor,
N=36) — measured under the deleted fixed reward:risk table.
**Fresh TRAIN under current arithmetic:** N=55, WR **61.8%**, ExpR **+0.494**,
excl 28% — clears every badge clause.
**Live logic:** `DEFAULT_PARAMS["EMA Crossover"]` (`entry_filters.py:217-228`)
already carries the round-2 pullback-entry default (`entry_mode="pullback"`,
`pullback_max_bars=15`); the entry function itself is `ema_cross_entries`
(`entry_filters.py:231`). Both unchanged.
**Mechanism:** none. This is a re-measurement, not a retry.
**Why legitimate:** the closed verdict was "this mechanism fails under the
fixed-R:R arithmetic." That arithmetic no longer exists. See §3, Tier 1.
**Pre-registered rule:** Stage 1 plateau + Stage 2 walkforward under current
v2/scale-out arithmetic; if ≥2/3 folds improve, no fold worse than −1.0pp, and
per-fold N≥30 → spend the one VALIDATION shot. Either free stage failing ⇒
record WEAK from that stage, no VALIDATION spent.

### 4.2 Break & Retest — Tier 1, horizon re-scope

**Current state:** WEAK, closed under v31 at 49.1% WR (0.9pp short).
**Fresh TRAIN:** pooled 48.0%, N=298 — but **bimodal by horizon**, not
uniformly weak. 2m/3m/4m clear the floor (53.1%/57.1%/51.4%, ExpR
+0.38/+0.32/+0.21); 6m is the only negative-ExpR cell (27.8%, −0.157); 7m/8m/2w
sit at 42.9–46.7%.
**Mechanism:** restrict to horizons `{2m, 3m, 4m}`. Pooled over those three:
**N=105, WR 53.3%, ExpR ≈ +0.31.**
**Implementation note (verified 2026-09-10):** `STRATEGY_GATES`
(`strategy_types.py:204-219`) currently has **no "Break & Retest" key at all** —
only Fibonacci, RSI, MA Ribbon, VWAP, Support/Resistance, MACD and Volume
Profile. `entries_for` (`entry_filters.py:126`) reads
`STRATEGY_GATES.get(strategy)` at line 146, so Break & Retest today falls
through completely unrestricted. The change is therefore to **add** a new entry
(`{"horizons": ("2m","3m","4m")}`), not to edit an existing one. The masking
machinery already exists and is exercised by seven other strategies; only the
key is new. `break_retest_entries` itself (`entry_filters.py:470`) is unchanged.
**Why genuinely new:** no closed pre-registration touches per-strategy horizon
scoping. The structural claim — a breakout-retest works while the break is
fresh and decays as the level ages — is consistent with the observed decay
pattern rather than fitted to it.
**Caveat to carry into the plan:** the qualifying horizons were *identified
from* this TRAIN table, so the Stage 1 plateau check is doing real work here —
if 2m/3m/4m is a spike rather than a plateau across adjacent horizon subsets,
it does not proceed.
**Pre-registered rule:** with the gate applied, TRAIN pooled WR ≥ 50, ExpR > 0,
N ≥ 30 (already satisfied — treat as confirmatory), then Stage 1 + Stage 2 as
above before VALIDATION.

### 4.3 VWAP — Tier 1, horizon re-scope (backup mechanism held in reserve)

**Current state:** WEAK, closed under v31 at 49.3% WR (0.7pp short — the
closest near-miss of the nine).
**Fresh TRAIN:** the live gate (`strategy_types.py:212`) is bullish-only across
`{4w,6m,7m,8m,9m}`, and its own source comment confirms it was calibrated
against the **pre-v31 fixed reward:risk table and never re-derived**. Per
horizon: `4w` N=68 WR **52.9%** ExpR +0.335 (clears the floor); `6m` 35.7%
(−0.078); `7m` 40.0%; `8m` 38.5%; `9m` 11.1% (N=9, −0.519). The pooled failure
is entirely the four long horizons.
**Mechanism:** re-derive the gate to bullish + `{4w}` only.
**Backup mechanism (only if 4w-only fails Stage 1/2):** a VWAP slope-persistence
gate — require VWAP's own rate of change `(vwap − vwap.shift(8)) / atr` to
exceed a fixed minimum in the trade direction, replacing the current
magnitude-free 3-bar direction check. New axis: no closed pre-registration
touched VWAP's slope dynamics, and it is a single deterministic threshold on
one series, not a blended score.
**Pre-registered rule:** 4w-only must clear TRAIN (WR≥50, ExpR>0, N≥30) and
Stage 1/2 before VALIDATION. Only on Stage 1/2 failure does the slope gate get
tested, as a filter on that same 4w population, under the same rule. If both
fail ⇒ closed, no VALIDATION spent.

### 4.4 RSI Divergence — Tier 2, highest leverage in the campaign

**Current state:** WEAK (REJECTED-ON-TRAIN 2026-07-18).
**Fresh TRAIN:** **N=1534**, WR 48.0%, ExpR +0.257 — 2.0pp short, and
remarkably flat: every horizon sits in a 44.4–49.0% band. No horizon or regime
weakness (200-day regime and 50-day trend gates are already baked into every
signal via `compute_shared_gates`). **This is by far the largest population in
the campaign — 2pp here outweighs a large relative win anywhere else.**
**Prior closed attempt:** confirmation *quality* (reclaim-bar volume ratio,
reclaim depth) — 0/9 configs; tightening either knob lowered WR while shrinking
N.
**Mechanism:** the RSI-turn confirmation is currently single-bar
(`turn_bull = (rsi14 > reclaim) & (rsi14 > rsi14.shift(1))`) — one uptick,
prone to immediately rolling over. Require **N consecutive bars of RSI moving
in the trade direction** before the reclaim confirms.
**Why genuinely new:** oscillator-momentum *persistence* — an axis neither the
closed pool-wide regime gate (price/MA-based) nor the closed confirmation-quality
gate (price/volume-based) touched.
**Pre-registered rule:** TRAIN grid `min_consecutive_rsi_turn ∈ {2, 3, 4}`;
a config qualifies at WR≥50, ExpR>0, N≥30, excl≤50%, **and must show a plateau
across adjacent values, not a lone spike**. 0/3 qualifying ⇒ REJECTED-ON-TRAIN,
permanently WEAK, no VALIDATION spent.

### 4.5 MA Ribbon — Tier 2

**Current state:** WEAK (REJECTED-ON-TRAIN 2026-07-18, 0/6 configs — graded
against the old 80% floor).
**Fresh TRAIN:** N=233, WR 48.1%, ExpR +0.270 — 1.9pp short. 2m is the drag
(33.3%, N=12, negative ExpR); the two largest buckets 2w (46.9%, N=81) and 4w
(48.6%, N=74) sit just under the floor with solid ExpR.
**Prior closed attempt:** ribbon-width *magnitude* (`min_width_pctile`,
`require_expanding`) — that axis is closed.
**Mechanism:** an N-bar alignment-confirmation gate — require the fast/mid
ordering relative to slow (`all_above_slow` / `all_below_slow`, already computed
in `signals.py:360-361`) to hold continuously for K bars *before* the crossover
bar triggers, instead of firing same-bar.
**Why genuinely new:** width measures instantaneous separation *magnitude*;
confirmation-bar count measures *temporal persistence*, targeting whipsaw
false-starts rather than narrow ribbons. Different failure mode, different axis.
**Pre-registered rule:** TRAIN sweep `confirm_bars ∈ {2, 3}`; qualify at WR≥50,
ExpR>0, N≥30, excl≤50%, plateau required. 0/2 qualifying ⇒ closes this axis
too, no VALIDATION spent.

### 4.6 Support/Resistance — Tier 2

**Current state:** WEAK as of 2026-09-10, TRAIN 45.7%, ExpR +0.316 (best ExpR
of the near-misses), N=247. Never had a rescue attempt.
**Failure mode:** `support_resistance_entries` (`entry_filters.py:419-452`)
treats "resistance" as the single highest bar over `sr_lookback` — a spike or
wick counts the same as a well-tested ceiling. The population isn't
discriminating strong breakouts from weak ones. (`STRATEGY_GATES` already
restricts it to bullish + `{2m,3m}`, so the eight zero-trade horizons are a
deliberate gate, not a data artifact.)
**Mechanism:** a level-touch **significance filter at entry** — require the
broken level to have been approached and rejected at least twice in the lookback
window (price came within `0.5×ATR14` and closed back below, on two separate
prior occasions) before an entry qualifies.
**Why genuinely new, and the adjacency to declare:** the closed
`LEVEL_TOUCH_STRENGTH` (v36) used touch-count as a **post-qualification
confidence tiebreak between already-selected target candidates** and measured
net-negative. This uses the same underlying signal at a different pipeline
point — gating *which setups fire* rather than scoring already-fired ones.
**The plan must state this adjacency in its own pre-registration** rather than
presenting the mechanism as unrelated.
**Pre-registered rule:** TRAIN WR≥50, ExpR>0, N≥30, excl≤50% on the filtered
population, plateau across the touch-count/tolerance grid required.

### 4.7 Fibonacci — Tier 3

**Current state:** WEAK as of 2026-09-10, TRAIN 35.4%, ExpR +0.232, N=246 —
14.6pp short, and near-uniform across all ten horizons (30.0–44.4%), which
rules out a horizon-scoping fix.
**Failure mode — it's the target, not the entry.** `fibonacci_entries`
(`entry_filters.py:169-211`) is a well-gated retracement-bounce; nothing there
obviously broke. But `select_structural_target` (`targets.py:10-57`, added by
v31) picks the nearest candidate clearing `MIN_RISK_REWARD_RATIO = 1.5`, and
Fibonacci's candidate set (`fib_target_candidates`, `targets.py:179`, whose
extension loop at lines 202-204 runs `for ratio in (1.272, 1.618)`) jumps from
the 0.786 retracement straight to the **1.272 and 1.618 extensions**. The 0.786
side is usually too close to clear 1.5×, so the chosen target is often a long,
rarely-touched reach. The positive ExpR alongside a collapsed win rate is the
classic wide-target signature (`1/(1+X)` break-even math).
**Mechanism:** add the **1.0 extension** (`swing_high + 1.0×diff` /
`swing_low − 1.0×diff`) to `fib_target_candidates` — a standard Fibonacci
projection, currently just missing between 0.786 and 1.272. The
nearest-qualifying selection is monotonic, so adding a strictly-closer real
candidate can only pull targets nearer or leave them unchanged.
**Geometry note (important):** this moves target geometry by construction, so it
is **not** eligible for the six-clause acceptance funnel (clause 3 would reject
it by design). It is judged on the **badge threshold** — a strategy-cell
measurement, which is the correct instrument here and the same one every other
section uses. The plan must say so explicitly, per the methodology's rule that a
geometry-moving change names the gate it is using.
**Expected trade:** win rate up, ExpR partly spent. The +0.232 cushion is what
funds it; the pre-registered rule keeps ExpR > 0 as a hard floor.
**Pre-registered rule:** TRAIN WR≥50, **ExpR>0**, N≥30, excl≤50% with the 1.0
candidate added and nothing else changed.

### 4.8 Elliott Wave — WITHDRAWN 2026-09-10, before any measurement

**This hypothesis was invalid and is withdrawn. Do not implement it.** It is
kept here, struck through rather than deleted, so the error is on the record.

**What planning found:** both halves of the mechanism proposed below **already
ship**. `entry_filters.elliott_wave_entries:703` already applies
`w2_min_retrace=0.382` / `w2_max_retrace=0.618` / `w2_max_duration_ratio=0.75`
plus a wave-0 overlap check (`:719-746`) and a separate `depth_min/max`
0.30–0.80 band; volume confirmation (`vol_ok = Volume >= vol_avg20 * 0.9`,
`VOL_OK_MULT` at `:29`) is already ANDed into both series (`:762,765`).

**Why it got past review:** the research pass read only the raw detector
`indicators.elliott_wave3_entries` and never found
`entry_filters.elliott_wave_entries`, the adapter that wraps it. The
symbol-verification pass then confirmed the detector *exists* — which it does —
without asking whether the proposed mechanism was already implemented. Existence
is not the same question as absence-of-the-proposed-change.

**Why implementing it would have been a methodology violation:** the proposed
0.382–**0.786** band is *looser* than the live 0.382–0.618, and these gates
**are** the round-2 Elliott Wave rescue whose VALIDATION shot is already spent
(`results/2026-07-rescue-elliott-validation.md`;
`tests/market/test_rescue_elliott.py:7` already uses the 0.382/0.786 pair).
Shipping it would have re-run a closed pre-registration at a loosened
threshold — the exact failure the one-shot budget exists to prevent.

**Also worth carrying forward:** `entry_filters.elliott_wave_entries:708-709`
hard-returns nothing for every horizon except `4w`, so any future Elliott Wave
mechanism inherits that volume ceiling regardless of its merits.

**Status: no new hypothesis exists.** Reopening Elliott Wave needs a genuinely
new mechanism and its own pre-registration. One was deliberately not invented to
fill this slot — a forced hypothesis is worse than an empty one.

---

<details>
<summary>Original (withdrawn) §4.8 text, retained for the record</summary>

### ~~4.8 Elliott Wave — Tier 3~~

**Current state:** WEAK (passed TRAIN, FAILED VALIDATION 2026-07-18 at 77.3% vs
the old 80% floor).
**Fresh TRAIN:** N=104, WR 32.7%, ExpR +0.184 — confirmed failure under current
arithmetic. All signal volume concentrates at 4w; every other horizon triggers
zero entries (a signal-density quirk worth noting, not the rescue lever).
**Failure mode:** `elliott_wave3_entries` (`indicators.py:215`) is deliberately
simplified and says so in its own docstring — a 3-pivot zigzag where wave 2 need
only clear wave 0 (`p2 > p0`), firing when price closes back above the wave-1
high. There is **no retracement-depth validation and no volume confirmation**.
It is effectively "any higher low followed by a break of the prior high."
**Mechanism (two gates, one hypothesis):** (a) wave 2's pullback depth must fall
inside **0.382–0.786** of the wave 0→1 move — the classical valid range, where
today a 5% or a 95% retrace both pass; (b) the wave-3 breakout bar's volume must
exceed its 20-bar average.
**Why genuinely new:** tightens wave-count validity itself, specific to this
strategy's own theory, never implemented. No closed pre-registration touches
wave-structure validity.
**Pre-registered rule:** TRAIN grid over retracement band width as the single
free parameter; **a plateau across ≥3 adjacent band widths is required** — a lone
passing configuration does not qualify.
**Honest caveat:** wave counting is the most subjective of the eleven
strategies, by the code's own admission. A clean failure here is a legitimate
and informative outcome, and the plan should not treat it as a problem to solve.

</details>

### 4.9 RSI — recommended deprioritise / drop

**Current state:** WEAK as of 2026-09-10, TRAIN 23.7% WR, ExpR **−0.120**,
N=38, excl 52% (over the ceiling). The weakest of the nine on every axis.
**The finding that matters:** the ADX+Bollinger range-regime gate from round 2
is **baked unconditionally into `DEFAULT_PARAMS["RSI"]`**
(`entry_filters.py:512-515`, `max_adx: 20`) — it is not a config toggle the
TRAIN run could have skipped. So the mechanism that earned RSI's original
`VALIDATED` badge **has itself collapsed under v31 arithmetic**. The
per-horizon uniformity (N≈4 everywhere, N=2 at 2w) confirms the gate fires on
the same handful of calendar days across 77 tickers × 4 years; horizon changes
only exit geometry, not signal generation.
**Fallback mechanism if pursued anyway:** replace the regime *instrument* —
20-day ATR-as-%-of-price ranked against its trailing 252-day distribution,
requiring the current reading below the 40th percentile, instead of
`adx_series(df) < 20`. Vol-percentile measures compression directly; ADX
measures directional-movement strength and is whipsaw-prone. Different
instrument, not a retuned `max_adx`.
**Recommendation: leave RSI out of this campaign.** Any measured win rate on
~4 trades per horizon is a coin flip, and round 1 already showed that loosening
the regime filter reintroduces the trending-tape bleed the gate exists to
prevent — so there is little room to buy volume without giving back win rate.
If it is pursued regardless, the rule is TRAIN WR≥50, ExpR>0, **N≥30** with the
thin-sample risk stated explicitly in the results doc.

## 5. Sequencing and budget

Run in tier order; within Tier 2, RSI Divergence first (largest N).

| # | Strategy | Tier | New code? | VALIDATION shot |
|---|---|---|---|---|
| 1 | EMA Crossover | 1 | none | 1 if Stage 1/2 clear |
| 2 | Break & Retest | 1 | new `STRATEGY_GATES` entry | 1 if Stage 1/2 clear |
| 3 | VWAP | 1 | gate constant (+ slope gate only on failure) | 1 if Stage 1/2 clear |
| 4 | RSI Divergence | 2 | new param + filter | 1 if TRAIN grid + Stage 1/2 clear |
| 5 | MA Ribbon | 2 | new param + filter | 1 if TRAIN grid + Stage 1/2 clear |
| 6 | Support/Resistance | 2 | new entry filter | 1 if TRAIN grid + Stage 1/2 clear |
| 7 | Fibonacci | 3 | `FIB_TARGET_1_0_EXTENSION` config Field + measurement script | 1 if TRAIN + folds clear |
| — | Elliott Wave | — | — | **none — WITHDRAWN, mechanism already ships (§4.8)** |
| — | RSI | — | — | **none — dropped (§4.9)** |

**Maximum VALIDATION budget spend: 7 shots, one per strategy, and only for
strategies that clear every free stage first.** Realistically fewer: Fibonacci
and parts of Tier 2 are expected to die on TRAIN, which is the funnel working.

**A note on the two withdrawals.** Elliott Wave and RSI are excluded for
opposite reasons: RSI has a mechanism that was measured and failed, Elliott Wave
has a mechanism that was never needed because it already exists. Neither slot
was backfilled with an invented hypothesis. Seven real shots beat nine
manufactured ones.

## 6. Success criteria

1. Every strategy above reaches a **recorded verdict** — rescued, or closed with
   its negative result written to `results/` and a row added to the
   closed-pre-registrations table. No strategy is left in an undocumented state.
2. No VALIDATION shot is spent on a strategy that failed a free stage.
3. Registry badges are updated only via `--emit-registry`, never by hand.
4. **A campaign that rescues only Tier 1 is a success, not a failure.** The
   honest expected outcome is roughly 3 rescued (Tier 1), 1–2 from Tier 2, and
   Tier 3 uncertain.

## 7. Limitations

- **Tier 1's horizon gates were identified from the same TRAIN table used to
  score them.** The Stage 1 plateau requirement is the guard against fitting
  noise; if a gate's advantage is a spike across adjacent subsets rather than a
  plateau, it does not proceed. This is the single largest overfit risk in the
  campaign and the plan must not soften it.
- **Validation-window reuse.** Each shot spent here is another distinct look at
  the tainted 2024–25 window. The count of prior looks should be stated in the
  final results doc, as round 2's wrap-up did.
- Several strategies (VWAP, Support/Resistance, Break & Retest) already carry
  hand-calibrated `STRATEGY_GATES` masks from pre-v31 tuning. This spec
  re-derives two of them; the rest remain on stale calibration and are out of
  scope.
- Nothing here addresses the confluence scan — still the largest and only
  negative population in the book, and by prior gap analysis a higher-ExpR
  target than any single strategy rescue. This campaign was chosen over it
  deliberately, at the human partner's direction.
