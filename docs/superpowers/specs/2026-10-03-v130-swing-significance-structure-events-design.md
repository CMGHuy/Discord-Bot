# v130 — Swing significance tiers and BOS/CHoCH events in the entry snapshot

**Version:** ui 1.21.1 · bot 2.0.0 (at writing)
**Bump:** bot patch (new fields on stored trade records; no alert, gate or exit changes)
**Edge:** none (integrity) — measurement only; its verdict decides whether a follow-on `expectancy` spec (a major-structure gate or a CHoCH cooldown) gets written

## Why

The partner shared five price-action pages on 2026-10-03 ("Daiken/BigWhale": swing
high/low, how to see a swing, swing → market structure, "not every swing
matters", and a conclusion on BOS/CHoCH). They make one argument:

1. A swing is defined by the **reaction after** the extreme, not by being the
   highest candle.
2. Swings come in tiers: major, minor and micro noise. A swing becomes major
   because the move away from it **changed structure**, not because it is
   bigger. The pages' test: "after this point, did price make a move clear
   enough to change structure?"
3. Structure (HH/HL/LH/LL) comes from comparing swings. BOS and CHoCH are read
   only after structure. BOS is a break in the trend's direction. CHoCH is a
   break of the important opposite swing, a possible shift.
4. Fib, S/R and liquidity only mean something when anchored on the right swing.

The repo has the structure half of this in v121 (`structure_state`,
`hh_failed`, …), but every v121 key rests on **k=3 fractals**. On daily bars
the pages would call most of those minor swings or micro noise. Nothing in code
or specs gives a pivot a significance tier, and nothing labels a break as BOS
or CHoCH. v124 gets "major" only by widening the fractal window (`origin_k` up
to 63). That measures window width, not the reaction-and-impact test above.

This spec builds the tier and the events as a causal instrument and asks one
question: **does structure read off major swings separate trade outcomes better
than structure read off k=3 swings?**

## Not a re-run of a closed row

| Closed / open row | Why this is different |
|---|---|
| v17 regime gate (0/44), v33 MTF (regressed) | Those gated entries on index/regime or higher-timeframe trend. v130 gates nothing, it only records. A follow-on gate must argue its own difference from both (see "What follows") |
| v121 `structure_state` | Same rule, different swing set. v121's k=3 keys stay byte-identical and are the comparison baseline |
| v124 `origin_k` | Window-width "major". v130's tier is reaction + structural impact on the same k=3 pivots. v124 is untouched |
| v127 MSB / HL trigger | An entry trigger on a *minor* break after a zone test. v130 labels *major* breaks at entry time and changes no entry |

## Scope

In:
- new functions in v121's `swingbot/core/market/structure.py`
- new keys in the entry-context snapshot (`swingbot/core/edge/context.py`)
- a read-only report script

Out:
- any gate, entry, stop, target or exit change
- chart drawing of tiers or events
- the `levels.py` confluence vote (option C of the brainstorm, deferred)
- backfill of historical trade records
- a second pivot detector

## Definitions (bullish shown; bearish mirrors every comparison)

Everything reads v121's `confirmed_pivots(df, k=3)`. A k=3 pivot at bar `i` is
knowable from `i + 3`. `ATR14` is `indicators.atr(df, 14)`.

### Major tier

Take a confirmed k=3 swing low at bar `i`. Let `SH_ref` be the High of the last
confirmed k=3 swing high whose pivot index is `< i`. (Its confirmation bar is
`< i + 3`, so it is known whenever the low is.)

The low **becomes major at the first bar `j ≥ i + 3`** where both hold:

- **Structural impact:** `Close[j] > SH_ref`
- **Reaction size:** `max(High[i..j]) − Low[i] ≥ M × ATR14[i]`, with
  `M = 2.0` frozen (`SWING_MAJOR_ATR_M`, a module constant, not a config
  knob; a follow-on that wants to search it pre-registers its own grid). ATR
  is taken at the pivot bar so the scale is fixed when the swing forms.

**Disqualification.** If any `Low[i+1..j']` is strictly below `Low[i]` before
both conditions hold, the low can never become major. A broken swing has no
reaction left to earn.

**No reference.** If no `SH_ref` exists (start of history), the low stays
minor.

**Timing.** Before `j` the low is minor. The tier is a fact *from bar `j`
onward*, never back-dated.

The swing-high mirror: `Close[j] < SL_ref`,
`High[i] − min(Low[i..j]) ≥ M × ATR14[i]`, and disqualified by a strictly
higher High.

### Major structure state

v121's `structure_state` rule applied only to pivots that are major **as of
bar `t`**:
- `up` if the last two major SHs rise **and** the last two major SLs rise
- `down` if both fall
- `mixed` otherwise
- `None` with fewer than 2 of either

Ordering is by pivot index. A pivot that became major later than a newer one
still sorts by where it sits on the chart.

### BOS / CHoCH events

Let `MSH` be the last major swing high known at bar `j − 1`. A **bullish
structure event** fires at bar `j` when `Close[j] > High[MSH]`. Each major SH
fires **at most once**: the first such close after it became major.

- Major state at `j − 1` is `down` → **bullish CHoCH**
- `up` or `mixed` → **bullish BOS**
- `None` → no event

Bearish events mirror with the last major swing low and `Close[j] < Low[MSL]`.

### Snapshot keys (at entry bar `t`, from `df.iloc[:t+1]`)

The keys are stated for the trade's direction, as v121's are, so analysis never
branches.

| Key | Definition |
|---|---|
| `structure_state_major` | major structure state at `t` (`up`/`down`/`mixed`/`None`) |
| `structure_aligned_major` | `up` for a bullish trade / `down` for a bearish one; `None` if the state is `None` |
| `major_sh_atr` | `(High[last major SH] − Close[t]) / ATR14[t]`; `None` if none |
| `major_sl_atr` | `(Close[t] − Low[last major SL]) / ATR14[t]`; `None` if none |
| `struct_event_last` | the latest event at bar `≤ t`: `bos_with`, `bos_against`, `choch_with`, `choch_against` ("with" = the event's direction equals the trade's), or `None` |
| `struct_event_bars_ago` | `t − j` for that event; `None` if none |
| `last_sl_reaction_atr` | `(max(High[i..t]) − Low[i]) / ATR14[i]` for the last confirmed k=3 swing low `i`; `None` if it was undercut or none exists |
| `last_sh_reaction_atr` | mirror for the last confirmed k=3 swing high |

The two reaction keys are continuous and descriptive. They let the report show
whether `M = 2.0` sits on a real step or in the middle of a smooth slope.

## Placement and data flow

`market/structure.py` gains three pure functions beside v121's:

- `major_pivots(df) -> DataFrame`: one row per bar. For each of the last two
  major SHs and the last two major SLs known at that bar, it gives the pivot
  index and price.
- `structure_events(df) -> DataFrame`: one row per bar, with the latest event
  kind (`bos`/`choch`), its direction and its bar index.
- `major_structure_features(df, direction) -> dict`: the keys above.

`edge/context.py:entry_context` merges `major_structure_features` beside v121's
`structure_features`, and the keys are appended to `FEATURE_KEYS`. The live
stamp (`planning/params.py:stamp_entry_context`) and replay
(`backtesting/backtest.py`, `backtest_scenarios.py`) gain them with no new
wiring, exactly as v121's do. Frames under 60 bars return all `None` and never
raise. A live snapshot may end in today's forming bar. That is acceptable for a
descriptive record, as v121 states; a consumer that *acts* on these keys must
compute them on completed bars only.

Storage follows whatever v121's plan confirms for `entry_context` (JSON
payload or typed columns). The plan re-checks it with the `schema-change`
skill.

**Dependency.** v121 must be merged first: `confirmed_pivots` and
`structure_features` must exist on `main`. The spec and plan can be committed
now; implementation starts after the merge.

## Report

`scripts/reports/structure_tier_report.py` reuses v121's bucketing helper from
`scripts/reports/volume_context_report.py` (imported, not copied). It buckets
**closed** trades and prints N, win rate and ExpR per bucket, separately for
confluence-sourced and strategy-sourced trades and per direction.

- `--source replay`: TRAIN `2020-01-01..2023-12-31` only. Any window touching
  2024-01-01 or later is refused.
- `--source live`: the production book, monitoring only. The header says it
  overlaps the 2026 holdout and prints no inferential statistic.

Tables:

1. **k=3 vs major, side by side:** `structure_aligned` (v121) against
   `structure_aligned_major`, each as aligned / not aligned / `None`.
2. **Events:** `struct_event_last` × `struct_event_bars_ago` in fixed buckets
   `0–5`, `6–20`, `21+`.
3. **Reaction:** `last_sl_reaction_atr` (bullish trades) and
   `last_sh_reaction_atr` (bearish trades) in fixed quintiles of the TRAIN
   population.
4. **Tier census:** the share of confirmed k=3 pivots that ever become major,
   and the median bars from pivot to its major bar, per horizon. This shows
   how thin the AND tier is before anyone reads Tables 1–3.

Buckets with `N < 30` print as `thin`, with no ExpR.

### Pre-registered verdict (descriptive, fixed before any run)

For each source and direction, let `spread(key) = ExpR(aligned) −
ExpR(not aligned)`.

**"Major tier more informative"** is declared only if **all** of these hold:

1. `spread(structure_aligned_major) > spread(structure_aligned)` in the
   **confluence-sourced** population, which is the bulk of the live book.
2. All four buckets entering those two spreads have `N ≥ 30`.
3. The sign of `spread(structure_aligned_major)` is the same for bullish and
   bearish trades, or the bearish side is `thin`.

Otherwise the verdict is **"not more informative"**, and the spec closes into
`no-lift/` as a finished measurement.

The verdict decides **only** whether a follow-on expectancy spec is written.
It never picks that spec's thresholds. Tables 2–3 are descriptive and carry no
verdict.

## What follows (only on "more informative")

A separate `expectancy` spec, for example a `structure_aligned_major` gate or a
cooldown after `choch_against`. It must:
- freeze its grid without reading this report's buckets
- state why it is not a re-run of v17 or v33
- clear both the v72 and v92 gates on TRAIN → VALIDATION

## Testing

- **Truncation:** for every cut `t` on fixture and real-symbol frames,
  `major_pivots`, `structure_events` and `major_structure_features` computed on
  `df.iloc[:t+1]` equal row `t` of the full-frame result.
- **Timing:** a pivot is never major before `i + 3` or before its qualifying
  bar `j`. Events read only majors known at `j − 1`, so a swing high never
  fires an event on the bar it becomes major.
- **Hand-built fixtures, each with a bearish mirror:**
  - a break of `SH_ref` with only 1.5 ATR of reaction → minor
  - 2.5 ATR of reaction without breaking `SH_ref` → minor
  - both conditions met → major at the exact bar the later of the two is met
  - an undercut before qualifying → never major
  - no `SH_ref` → minor
  - down-state then a close above the last major SH → `choch`
  - up-state then a close above → `bos`
  - a second close above the same SH → no second event
  - with/against labelling for a bullish and a bearish trade
- **Witness:** every pre-existing and v121 key in `entry_context` stays
  byte-identical on a fixture. On a frame under 60 bars, every new key is
  `None`.
- **Report:** refuses a replay window ending after 2023-12-31; prints `thin`
  under `N = 30`.
- **Review:** `no-lookahead` skill on `structure.py` and `context.py`.
- **Complexity:** every new function is under complexity 15.

## Non-goals

- No live behaviour change: no alert, gate, entry, stop, target or exit reads
  these keys.
- No backfill: replay supplies the history.
- No second pivot implementation and no change to v121's or v124's contracts.
- No search over `M` or the event-bucket edges.

## Parallelisation

- `major_pivots` → `structure_events` → `major_structure_features` is a chain:
  events need the major set, and the features need both.
- The `context.py` integration needs the features.
- The report needs the stored keys and v121's bucketing helper.
- The storage re-check (`schema-change` skill) is independent and can run
  beside the pivot work.
- Everything waits on v121 being merged.
- Full suite once, at the end.
