# v124 — Fibonacci impulse-leg instrument and anchor diagnostic

**Version:** ui 1.21.0 · bot 2.0.0 (at writing)
**Bump:** none (a pure module no live path imports, plus a read-only measurement script)
**Edge:** none (integrity) — measurement only; it is the shared instrument and the admission test for four follow-on `expectancy` arms

## Why

The partner's Fibonacci handbook makes four claims:

1. A retracement is only meaningful when drawn on a **real impulse leg**, not
   between "the highest and lowest point you can see".
2. The leg must matter in the **larger structure**; a neat internal minor move
   is a trap.
3. A Fib level is a **location (a zone)**, not an entry button; confluence
   makes a location worth watching.
4. Entry needs **reaction and confirmation** at the location.

`fibonacci_entries` (`swingbot/core/market/entry_filters.py`) does the thing
claim 1 warns against: its anchors are the rolling max High and min Low over a
fixed `fib_lookback` window (15–378 bars). The low is often only where the
window happens to start, and it drifts as the window rolls. The only structure
check is "low came before high". `levels.py` feeds the same rolling-window Fib
prices into the confluence scan.

Every closed Fibonacci pre-registration (v84 extension target, v101 stops and
reclaim entry, v102 Rolling S/R confluence, v103 level stop and continuation,
v113 `1w`) was measured on those anchors. Anchor selection is therefore a
mechanism outside all of them, which is what `backtest-methodology.md`
requires before Fibonacci is reopened.

This spec builds the leg and measures, on the 2015–2025 diagnostic window, whether each of the four
claims shows any signal in the bot's own trades. It gates nothing.

## Scope

In: a new `swingbot/core/market/fib_leg.py`; a read-only script
`scripts/backtest/measure_fib_anchor_diagnostic.py`; one results document.

Out: any change to `fibonacci_entries`, `levels.py`, plans, alerts, charts,
config flags or stored records. Each of those is a follow-on arm with its own
spec and pre-registration (see "What follows").

## The leg (`fib_leg.py`)

`impulse_leg(df, direction, origin_k) -> DataFrame`, one row per bar `t`.
Bullish shown; bearish mirrors every comparison.

- **Origin.** The most recent swing low of strength `origin_k` that is
  confirmed at `t`, taken from v121's `structure.confirmed_pivots(df,
  k=origin_k)`. A later, higher major low replaces it once confirmed, so the
  leg is always the most recent impulse.
- **End.** The bar with the highest High in `(origin, t]`, first occurrence on
  ties. The leg is defined only once that bar is at least 3 bars old (the same
  lag v121 uses), so a pullback has begun.
- **No leg** (all outputs NaN) when no origin is confirmed, the end is younger
  than 3 bars, or any Low after the origin is below the origin price.
- **Origin strength.** `origin_k = max(3, fib_lookback // 6)`, read from
  `strategy_types.HORIZONS`. That gives 3 on the shortest horizons and 63 on
  `9m`. The origin is old by construction, so its confirmation lag costs no
  entries. The divisor 6 is a frozen descriptive default here; a follow-on
  arm that searches it must pre-register its own grid.

Output columns: `origin_idx`, `origin_price`, `end_idx`, `end_price`,
`leg_atr` (leg size ÷ ATR14 at `t`), `leg_bars`, `level_382`, `level_500`,
`level_618`, `retrace_now` (from Close), `retrace_deepest` (from the lowest
Low since the end), `zone_touch` (`Low[t] <= level_500` and `Close[t] >=
level_618`), and `broke_structure` (the end price exceeds the last
strength-`origin_k` swing high before the origin; NaN if none exists).

**Causality contract.** Row `t` computed on `df` equals the last row computed
on `df.iloc[:t+1]`. Pivot lag lives only in `confirmed_pivots`; `fib_leg.py`
adds no pivot detection of its own. `broke_structure` needs the pivot before
the origin, which v121's last-two frame may not expose. The plan confirms
this, and if needed adds a read-only accessor to `structure.py` rather than a
second pivot implementation.

## The diagnostic

`scripts/backtest/measure_fib_anchor_diagnostic.py`, read-only, modelled on
`measure_fib_diagnostic.py` (v101) and `measure_fib_v103.py`.

- **Window (partner decision, 2026-10-02):** entries and features on
  2015-01-01..2025-12-31, extended cache `data/backtest_cache_ext`, the v103
  universe. The window bounds entry dates; bars before 2015 serve only as
  lookback history. The script refuses any diagnostic window starting before
  2015-01-01 or ending after 2025-12-31.
- **Outcome resolution past the window.** A trade entered on or before
  2025-12-31 and still open then may resolve on later (2026) bars, exactly as
  the harness already does for every window. That is outcome resolution only:
  no feature, bucket or verdict reads a bar after the entry bar.
- **Holdout and budget.** 2026 is the holdout, per the v104/v113 precedent.
  v103 already spent Fibonacci's 2024–25 VALIDATION shot (bullish `b=0.1`,
  FAIL). This is a diagnostic, not a validation shot: it spends no budget and
  re-scores no closed candidate. Reading 2024–25 here is a deliberate partner
  exception to the "2024–2025 tainted for selection" rule, limited to
  admitting arms to a spec. Every follow-on arm must name its own holdout in
  its pre-registration.
- **Trades:** today's Fibonacci entries through `run_backtest` with the v2 +
  scale-out engine. Bearish is unmasked inside the script only, through
  `entry_filters.gate_override`, and is reported as description.
- **Sanity check, on v103's own window.** Before the diagnostic runs, the
  script runs the same trade collector on 2010-01-01..2023-12-31 (`TRAIN_EXT`)
  and the bullish baseline must reproduce v103's reference arm: N=815,
  WR 36.81%, ExpR +0.2219, universe 73. That proves the instrument matches
  v103. The 2015 lower bound and the 2025 upper bound apply to the diagnostic
  window only; this check runs on exactly 2010-01-01..2023-12-31 and nothing
  else. A difference is explained in a committed note before any bucket is
  read, and the report refuses to write tables until that note exists.

Each arm has **one primary split**, fixed here. All features are computed at
the entry bar from `df.iloc[:t+1]`.

| Arm | Primary split (favourable vs rest) | Also described, cannot promote an arm |
|---|---|---|
| 1 Anchored entry | Rolling low within 0.25 ATR of the leg origin **and** rolling high within 0.25 ATR of the leg end, vs not (including no leg) | rolling low is not a 3-bar fractal low; `broke_structure`; `leg_atr` quintiles |
| 2 Zone + confluence | `collect_candidate_levels` yields a Volume Profile or AVWAP price inside the leg's 0.5–0.618 zone widened by 0.25 ATR, vs not (including no leg) | `zone_touch` vs close-only test; tested ratio; the same test against the rolling tested level |
| 3 Confirmation | `Close[t] > High[t-1]`, vs not | lower wick at least half the bar's range |
| 4 Confluence scan | On confluence-arm trades whose level includes a Fibonacci-family candidate: that candidate within 0.25 ATR of a leg price (origin, three levels, end), vs not | re-derived N / WR / ExpR for the whole confluence population on this window |

The 0.25 ATR tolerance is one frozen constant shared by arms 1, 2 and 4.
Leg-dependent splits (arms 1, 2, 4) are also reported at divisors 4 and 8.
AVWAP candidates exist only while `AVWAP_LEVELS_ENABLED` is on; the script
records the flag's value in its output. Rolling S/R is excluded from arm 2
because v102 closed it; Zigzag Pivot is
excluded because v49 measured it as 0.838 redundant with Fibonacci.

Arm 4 depends on identifying the Fibonacci candidate behind a confluence
trade. A confluence plan does not carry its level sources, so the script
rebuilds them. Three rules, decided by the partner on 2026-10-02:

- **Map-bar recompute.** `levels_asof` caches one level map per 5-bar bucket,
  built at the first bar the replay visits in it:
  `max(MIN_BARS[h], (index // 5) * 5)`, never after the entry. The script
  rebuilds that map, re-splits it against the entry close as the replay
  does, and recomputes `collect_candidate_levels` **on that map bar**, not the
  entry bar. That is the frame that produced the level.
- **"The level" is the stop level and the target-1 level** of the scenario,
  the two `primary_strategy_for` reads. Its Fibonacci candidates are the
  Fibonacci-family labels in those two levels.
- **All-or-nothing rebuild.** A trade is identified only if the plan's stop
  equals `_clamp_stop_to_hard_cap(trigger, rebuilt stop level, is_bull)`. If
  even one confluence trade fails, arm 4 is reported as **not measurable with
  this instrument** and does not proceed on this diagnostic.

**Exit rule, fixed in advance.** An arm proceeds to its own spec only if, on
the bullish side, the favourable bucket has a higher win rate **and** an ExpR
no lower than the rest, with N ≥ 30 in each bucket. Arms 1, 2 and 4 must also
keep the win-rate sign at two of the three divisors. An arm that fails closes
as a no-lift row in `backtest-methodology.md` with no budget spent. An arm
that passes has earned a spec, nothing more: it still faces Stage −1 to
Stage 3 under its own pre-registration.

**Success bar for the follow-on arms** (partner decision, 2026-10-02). Two
separate verdicts. The v72 funnel against today's rolling-anchor Fibonacci
decides whether an arm ships; a pass ships even if the strategy stays `WEAK`.
The badge clauses (`win_rate >= 50`, `ExpR > 0`, N floors) are computed
alongside and decide only whether the registry row becomes `VALIDATED`.

Output: `docs/superpowers/results/YYYY-MM-DD-v124-fib-anchor-diagnostic.md`
with every bucket table, this exit rule quoted, and raw JSON beside it. The
run is dispatched to `backtest-runner`, chunked per direction, with flushed
per-ticker progress and a percent figure past 15 minutes.

## Testing

- **Truncation:** for every cut `t`, `impulse_leg(df.iloc[:t+1])`'s last row
  equals `impulse_leg(df).iloc[t]`.
- **Known answers** on hand-built frames, each with a bearish mirror: a clean
  leg; a higher major low restarting the leg; a broken origin returning NaN;
  an end younger than 3 bars returning NaN; a leg that does and does not
  break the prior major high; `zone_touch` true and false.
- **Short frames** return all NaN and never raise.
- **Script:** refuses a diagnostic window starting before 2015-01-01 or
  ending after 2025-12-31, and a reproduction window other than
  2010-01-01..2023-12-31; bucket arithmetic
  checked against a small fixture of hand-labelled trades.
- `no-lookahead` skill review of `fib_leg.py` and the script's feature code.
- Every new function stays under cyclomatic complexity 15.

## What follows

Each only if the diagnostic admits it, in this order, each with its own spec:

1. **Anchored Fibonacci entry** — `fibonacci_entries` draws from the leg.
2. **Zone + confluence family** — 0.5–0.618 zone with a Volume Profile or
   AVWAP level inside it.
3. **Confirmation trigger** — a stronger entry-bar condition.
4. **Anchored Fib levels in the confluence scan** — `levels.py` emits leg
   levels in place of rolling-window ones.

Arms 2–4 are measured against the same baseline as arm 1, not stacked on its
winner, so one arm's failure does not contaminate another.

**Major-tier leg origin (bridge to v130, noted 2026-10-04).** The handbook
asks for a swing with a clear reaction that fits the structure. `origin_k`
gets "major" only by widening the fractal window. v130's major tier tests the
handbook's version instead: the departure broke the prior opposite swing and
reacted by at least 2 ATR. A measurement spec that takes the leg origin from
v130's `major_pivots` is written only if **both** of these hold:

- arm 1 here passes
- v130 declares the major tier "more informative"

That spec freezes its own splits without reading either report's buckets.
This spec's contract and exit rule are unchanged.

## Non-goals

- No stop, target or exit change: v84, v101 and v103 closed those.
- No bearish rescue: bearish rows are description only.
- No feature, bucket or verdict reads a bar after its entry bar; bars after
  2025-12-31 serve only to resolve trades still open then. No 2026 entry is
  ever read.
- No selection from the "also described" columns.

## Parallelisation

- **Sequential:** `fib_leg.py` before the script (the script consumes
  `impulse_leg`). The leg's own functions are a chain: origin, then end, then
  features.
- **Sequential:** the four arm feature blocks are logically independent but
  live in one script file, so they are written one after another.
- **Group 1 (parallel with `fib_leg.py`):** the read-only check of whether
  the confluence replay can identify a trade's Fibonacci candidate (arm 4)
  touches no file and consumes no new symbol.
- **Blocked on v121:** implementation must not start until v121's
  `structure.py` is merged, the same rule v122 and v123 follow.
- Full suite once, as the plan's final task. The measurement run comes after
  it.
