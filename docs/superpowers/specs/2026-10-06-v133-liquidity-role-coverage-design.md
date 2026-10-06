# v133 — Liquidity pools and four-role coverage in the entry snapshot

**Version:** ui 1.21.1 · bot 2.0.1 (at writing)
**Bump:** bot patch (new fields on stored trade records; no alert, gate or exit changes)
**Edge:** none (integrity) — measurement only; its verdict decides whether a follow-on `expectancy` spec (a role-coverage gate on the confluence scan) gets written

## Why

The partner shared six more "Daiken/BigWhale" price-action pages on 2026-10-06
("Order Block + 4 factors"). They make one argument: a zone is a place to
watch, never a trigger. It earns a trade only after four checks of **different
kinds**:

1. **Structure** — is the market HH/HL or LH/LL, and does the zone agree?
2. **Location** — is the zone at a meaningful place (discount for longs,
   premium for shorts, near other levels) or in the middle of noise?
3. **Liquidity** — where are the nearest equal highs/lows and unswept swings,
   and is price likely to run them first?
4. **Reaction** — what did price do at the zone: rejection, displacement, a
   minor break, a retest, or a drive straight through?

The closing page adds: "more factors is not better; what matters is whether
the factors form one logical context."

Mapped against the repo on 2026-10-06:

| Pillar | Status |
|---|---|
| Structure | Built: v121 `structure_state` / `structure_aligned`. v130 (major swings, BOS/CHoCH) is written, not built. Gate versions v17 and v33 are closed failures |
| Location | v125 is written, not on `main`. Nothing on `main` records discount vs premium |
| Liquidity | **Nothing.** No equal-high/low or sweep code exists. v128's spec defers "chop + sweep features" to a follow-on that was never written |
| Reaction | Built: `market/reaction.py` (v88). Used only by the armed-entry replay; not recorded in the entry snapshot |

Two facts about the confluence count make the closing page's claim testable
here:

- **All 12 families in `levels.ALL_STRATEGY_FAMILIES` are level detectors.**
  `count_confirming_strategies` counts how many of them land near the
  **target** price. In the pages' terms that is location evidence only,
  counted up to twelve times. It alone sets `MIN_TARGET_CONFLUENCE_COUNT` and
  the confidence base level.
- v49 already measured that those votes are redundant with each other
  (off-diagonal mean 0.628). v49 did not ask whether a setup has any evidence
  of the **other** kinds.

This spec builds the missing liquidity instrument, records one pass/fail flag
per role, and asks one question: **does the number of distinct roles a setup
covers separate trade outcomes better than the number of level votes it
collects?**

## Not a re-run of a closed row

| Closed / open row | Why this is different |
|---|---|
| v17 regime gate (0/44), v33 MTF (regressed) | Those gated entries on one context signal. v133 gates nothing. A follow-on gate must argue that a conjunction across roles is not either row again (see "What follows") |
| v49 effective confluence (degenerate) | v49 reduced the 12 level votes by their mutual redundancy. v133 leaves the vote count untouched and uses it only as the control column |
| v88 / v90 armed entries | Those changed **when** an entry fires (wait for a reaction). v133 records whether the bar that already fired the entry happened to show a reaction; no entry moves |
| v121 `structure_aligned` | Reused unchanged as the context flag |
| v125 location (open) | v125 records distance to a zone and zone lifecycle. v133's location flag is discount/premium inside the last swing range, from v121 keys already on `main`. Neither depends on the other |
| v127 structure-break entries (open) | An entry trigger on a minor break. v133 changes no entry |
| v130 major swings (open) | v133 reads k=3 pivots only. A major-swing variant is a follow-on if v130 lands |

## Scope

In:
- a new pure module `swingbot/core/market/liquidity.py`
- a new pure module `swingbot/core/market/roles.py`
- new keys in the entry-context snapshot (`swingbot/core/edge/context.py`)
- a read-only report script

Out:
- any gate, entry, stop, target or exit change
- the confidence score and the embed
- order blocks as a new level family (an order block sits beside the FVG that
  follows it; v128 already tests the displacement half)
- chart drawing of pools or sweeps
- backfill of historical trade records
- a second pivot detector

## Definitions (bullish shown; bearish mirrors every comparison)

Everything reads v121's pivot detector, `structure.pivot_confirmations(df,
k=3)`. A k=3 pivot at bar `i` is knowable from `i + 3`. `ATR14` is
`indicators.atr(df, 14)`. All constants below are frozen module constants,
not config knobs; a follow-on that wants to search one pre-registers its own
grid.

| Constant | Value | Meaning |
|---|---|---|
| `POOL_TOLERANCE_ATR` | 0.25 | two pivots this close are "equal" |
| `POOL_LOOKBACK_BARS` | 100 | a pool's older pivot is at most this far behind its newer one |
| `SWEEP_RECLAIM_BARS` | 3 | a sweep must close back within this many bars |
| `PATH_NEAR_ATR` | 1.0 | a stop-side pool nearer than this is "in the way" |
| `PATH_SWEEP_RECENT_BARS` | 5 | a stop-side sweep this recent clears the path |
| `TRIGGER_TEST_K` | 0.25 | `reaction.is_test` tolerance, in ATR |

### Sell-side pool (equal lows)

Take two confirmed k=3 swing lows at bars `i1 < i2` with
`i2 − i1 ≤ POOL_LOOKBACK_BARS`. They form a pool when:

- `|Low[i1] − Low[i2]| ≤ POOL_TOLERANCE_ATR × ATR14[i2 + 3]`. ATR is taken at
  the newer pivot's confirmation bar so the test is fixed when the pool forms.
- No `Low[i1+1 .. i2+3]` other than `Low[i2]` itself is strictly below
  `min(Low[i1], Low[i2])`.

The pool's **level** is `min(Low[i1], Low[i2])`. It **exists from bar
`i2 + 3`**, never back-dated. A pivot may belong to more than one pool.

A buy-side pool (equal highs) mirrors this with swing highs and
`max(High[i1], High[i2])`.

A single unbroken swing is the weaker pool the pages also name. It needs no
new key: v121's `swing_low_atr` and `swing_high_atr` already record it.

### Sweep

A sell-side pool is **live** from the bar it exists until the first bar `j`
with `Low[j] < level`. At that bar the pool is dead, whatever follows.

- **Sweep and reclaim:** some bar `j'` in `[j, j + SWEEP_RECLAIM_BARS]` has
  `Close[j'] > level`. The sweep event is dated at the first such `j'`, and is
  a fact only from bar `j'` onward.
- **Break:** no such close. No sweep event is recorded.

The buy-side mirror: `High[j] > level`, then `Close[j'] < level`.

`reaction.is_reclaim` is not reused here. It requires an earlier **close**
through the level, so it misses the wick-only sweep that is the pages' main
case.

### Liquidity keys (at entry bar `t`, from `df.iloc[:t+1]`)

Stated for the trade's direction. For a bullish trade the **stop side** is
sell-side pools with `level < Close[t]`, and the **target side** is buy-side
pools with `level > Close[t]`.

| Key | Definition |
|---|---|
| `liq_stop_side_atr` | `(Close[t] − level) / ATR14[t]` for the nearest live stop-side pool; `None` if none |
| `liq_target_side_atr` | `(level − Close[t]) / ATR14[t]` for the nearest live target-side pool; `None` if none |
| `liq_sweep_bars_ago` | `t − j'` for the latest sweep-and-reclaim of a stop-side pool dated at or before `t`; `None` if none |
| `stop_in_pool` | `True` when `level − POOL_TOLERANCE_ATR × ATR14[t] ≤ stop ≤ level` for any live stop-side pool; `False` otherwise; `None` if no ATR |
| `target_past_pool` | `True` when `target >` the nearest live target-side pool's level; `False` if a pool exists and the target is at or before it; `None` if no pool |

For `liq_sweep_bars_ago`, "stop-side" is judged by the pool's kind (sell-side
for a bullish trade), not by where its level sits against `Close[t]`.

### Role flags

Each flag is `True`, `False` or `None` (not computable).

| Key | `True` when (bullish) |
|---|---|
| `role_context` | `structure_aligned` is `True`. `None` when `structure_aligned` is `None` |
| `role_location` | `swing_low_atr > 0` and `swing_high_atr > 0` and `swing_low_atr ≤ swing_high_atr`: close is inside the last k=3 swing range and in its lower half (discount). Bearish: `swing_high_atr ≤ swing_low_atr` (premium). `None` when either key is `None` |
| `role_path` | `liq_stop_side_atr` is `None` or `> PATH_NEAR_ATR`, **or** `liq_sweep_bars_ago ≤ PATH_SWEEP_RECENT_BARS`. `None` when ATR is unavailable |
| `role_trigger` | `reaction.reaction_kind` at bar `t` returns `R1` (rejection) or `R3` (reclaim) against the level `L` = the last confirmed k=3 swing low known at `t` (bearish: swing high). Arguments: `tested_now = is_test(t, L, k=TRIGGER_TEST_K, ATR14[t])`, `tested_prev = is_test(t−1, L, k=TRIGGER_TEST_K, ATR14[t−1])`, `floor_index = t − reaction.RECLAIM_BARS`. `None` when no such pivot exists |

`R2` (follow-through) is left out of the trigger on purpose: v88's close-out
found R2/R3 making up 85–90% of reactions, and v90 isolated R1 as the slice
that beat baseline. R3 stays because a reclaim is the close-based form of the
sweep the pages describe.

`role_coverage` is the number of flags that are `True` (0–4). It is `None`
when any flag is `None`, so a missing role is never counted as a failed one.

## Placement and data flow

- `market/liquidity.py`
  - `pools(df) -> DataFrame`: one row per pool with side, level, the bar it
    exists from, the bar it died, and its sweep-and-reclaim bar if any.
  - `liquidity_features(df, direction, stop, target) -> dict`: the five keys.
- `market/roles.py`
  - `role_features(df, direction, structure: dict, liquidity: dict) -> dict`:
    the four flags and `role_coverage`. It takes the already-computed v121 and
    liquidity dicts so nothing is computed twice.
- `edge/context.py:entry_context` merges both beside v121's
  `structure_features`, and the ten keys are appended to `FEATURE_KEYS`. The
  live stamp (`planning/params.py:stamp_entry_context`) and replay
  (`backtesting/backtest.py`, `backtest_scenarios.py`) gain them with no new
  wiring, as v121's did. `entry_context` already receives `stop` and `target`.

Frames under 60 bars return all `None` and never raise. A live snapshot may
end in today's forming bar. That is acceptable for a descriptive record, as
v121 states; a consumer that *acts* on these keys must compute them on
completed bars only.

Storage follows what v121 established for `entry_context`. The plan re-checks
it with the `schema-change` skill.

**Shared file.** v125 and v130 each append to `FEATURE_KEYS` in
`edge/context.py` from their own branches. Whichever lands second rebases its
tuple edit; the keys do not overlap.

## Report

`scripts/reports/role_coverage_report.py` reuses the bucketing and replay
helpers from `scripts/reports/volume_context_report.py` (imported, not
copied). Its replay rows also carry the target confluence count that
`backtest_scenarios.py` already computes for each scenario. It buckets
**closed** trades and prints N, win rate and ExpR per bucket, separately for
confluence-sourced and strategy-sourced trades and per direction.

- `--source replay`: TRAIN `2020-01-01..2023-12-31` only. Any window touching
  2024-01-01 or later is refused.
- `--source live`: the production book, monitoring only. The header says it
  overlaps the 2026 holdout and prints no inferential statistic.

Tables:

1. **Coverage:** `role_coverage` in fixed buckets `0–1`, `2`, `3–4`, plus a
   `None` row.
2. **Control:** target confluence count in buckets `2`, `3`, `4+`
   (confluence-sourced trades only).
3. **Each role alone:** `True` / `False` / `None` for the four flags.
4. **Liquidity:** `stop_in_pool`, `target_past_pool`, and
   `liq_stop_side_atr` in fixed quintiles of the TRAIN population.
5. **Sweep stop-outs:** among losing trades, the share whose stop bar is
   followed within `SWEEP_RECLAIM_BARS` bars by a close back beyond the stop
   price. This reads bars after the exit, so it is computed in the report
   only and is never a snapshot key.
6. **Census:** per horizon, the share of entry bars with a live stop-side
   pool, and with each role flag `None`.

Buckets with `N < 30` print as `thin`, with no ExpR.

### Pre-registered verdict (descriptive, fixed before any run)

In the **confluence-sourced** population, per direction, let
`spread_roles = ExpR(coverage 3–4) − ExpR(coverage 0–1)` and
`spread_votes = ExpR(count 4+) − ExpR(count 2)`.

**"Role coverage more informative"** is declared only if **all** of these hold:

1. `ExpR(0–1) ≤ ExpR(2) ≤ ExpR(3–4)` and `spread_roles > 0`.
2. `spread_roles > spread_votes`.
3. All five buckets entering those two spreads have `N ≥ 30`.
4. The sign of `spread_roles` is the same for bullish and bearish trades, or
   the bearish side is `thin`.

Otherwise the verdict is **"not more informative"**, and the spec closes into
`no-lift/` as a finished measurement.

The verdict decides **only** whether a follow-on expectancy spec is written.
It never picks that spec's thresholds. Tables 3–6 are descriptive and carry no
verdict.

## What follows (only on "more informative")

A separate `expectancy` spec, for example a minimum `role_coverage` on
confluence scenarios. It must:
- freeze its grid without reading this report's buckets
- state why a conjunction across roles is not a re-run of v17 or v33
- clear the v72 gate through the standard funnel (`measure_arms.py`,
  Stage −1 to Stage 3)

Table 5 may separately motivate a `harvest` spec on stop placement relative to
pools. That is its own pre-registration under the v92 gate.

## Testing

- **Truncation:** for every cut `t` on fixture and real-symbol frames,
  `liquidity_features` and `role_features` computed on `df.iloc[:t+1]` equal
  the values computed at row `t` of the full frame.
- **Timing:** a pool never exists before `i2 + 3`. A sweep event is never
  visible before its reclaim bar `j'`.
- **Hand-built fixtures, each with a bearish mirror:**
  - two swing lows 0.2 ATR apart → pool; 0.3 ATR apart → no pool
  - two swing lows more than 100 bars apart → no pool
  - an undercut between the two pivots → no pool
  - wick below the pool with a same-bar close above → sweep at that bar
  - close back above on the third bar after → sweep; on the fourth → break
  - a broken pool is never live again
  - `stop_in_pool` true just below the level, false above it and false beyond
    the tolerance
  - `target_past_pool` true, false and `None`
  - each role flag `True`, `False` and `None`
  - `role_coverage` is `None` when one flag is `None`
  - R2 alone does not set `role_trigger`
- **Witness:** every pre-existing key in `entry_context` stays byte-identical
  on a fixture. On a frame under 60 bars, every new key is `None`.
- **Report:** refuses a replay window ending after 2023-12-31; prints `thin`
  under `N = 30`; Table 5 is absent from every snapshot key list.
- **Review:** `no-lookahead` skill on `liquidity.py`, `roles.py` and
  `context.py`.
- **Complexity:** every new function is under complexity 15.

## Non-goals

- No live behaviour change: no alert, gate, entry, stop, target or exit reads
  these keys.
- No backfill: replay supplies the history.
- No search over any constant in the table above, or over the bucket edges.
- No change to v121's, v88's or v49's contracts.

## Parallelisation

- **Group 1 (parallel):** `liquidity.py` with its tests; the storage re-check
  (`schema-change` skill). Disjoint files, no shared symbol.
- **Sequential:** `roles.py` after `liquidity.py` (it consumes the liquidity
  dict's keys). The `context.py` integration after both (it merges their
  outputs and extends `FEATURE_KEYS`). The report after the integration (it
  reads the stored keys). The measurement run after the report.
- `context.py` is also edited by the v125 and v130 branches; do not run this
  integration task beside either of theirs in the same tree.
- Full suite once, at the end.
