# v125 — Location, leg phase and plan-provenance features in the entry snapshot

**Version:** ui 1.21.1 · bot 2.0.0 (at writing)
**Bump:** bot patch (new fields on stored trade records; no alert, gate or exit changes)
**Edge:** none (integrity) — measurement only; it is the instrument a later
structure-break entry pre-registration (the "#3" spec) is checked against,
and it answers whether synthetic targets / clamped stops carry the losses

## Why

A price-action course the partner shared (Days 15-20: market context, key
zones, confirmation, setup chain, stop = invalidation, TP from structure)
was mapped against the bot on 2026-10-02. Most of it is built or closed
(v17 regime gate, v33 MTF gate, v36 touch strength, v88/v90 rejection entry,
v104 structural stops, v31 structural targets). Three claims were never
measured:

1. **Synthetic targets and clamped stops (Days 19-20).** When no real level
   sits inside `MAX_RISK_REWARD_RATIO`, `select_structural_target`
   (`planning/targets.py`) returns an invented price at exactly the cap; when
   a confluence stop is beyond the 2% hard cap, `_clamp_stop_to_hard_cap`
   (`planning/builders.py`) overwrites it to 1.75%. These are precisely the
   course's "TP chosen for a pretty RR" and "arbitrary SL". **Neither leaves
   a trace** on the plan, so the question "do these plans carry the losses?"
   cannot be answered from stored data. A 2026-10-02 attempt to infer them
   from `entry_context.planned_rr ≈ 2.5` / `stop_pct ≈ 1.75` failed:
   `planned_rr` is measured from the bar close, not the planned entry, and
   only 49 of 458 closed live trades carried a snapshot at all.
2. **Location (Day 15).** Nothing records whether price is *at* a zone or in
   the middle of the range.
3. **Movement and zone quality (Days 15-16).** v121 adds HH/HL structure and
   impulse/pullback legs, but no categorical leg phase, no lifecycle state of
   the zone being traded, and no measure of how decisively price left that
   zone (the course's "strong reaction" and "origin of a strong move").

## Scope

In: a new pure module `swingbot/core/market/location.py`; a pure
`plan_provenance` helper and one optional `entry=` keyword in
`edge/context.py`; the new keys appended to `FEATURE_KEYS`; passing the
planned entry at the four snapshot call sites; new keys and one cross-table
in v121's `scripts/reports/volume_context_report.py`.

Out: any gate, score weight, exit rule, alert text, chart change, builder
return type, or backfill of historical records. The structure-break entry
trigger is a separate expectancy spec.

**Depends on v121** (`market/structure.py:confirmed_pivots` and the
report script). Implementation must not start until v121 is merged.

**Ordering constraint.** The structure-break entry spec ("#3") must be
written and its grid frozen **before** this report is ever run, for the same
reason v121 froze v122/v123 first: no bucket table may leak into selection.

## Features (all at entry bar `t`, from `df.iloc[:t+1]`)

Direction-aware keys are expressed for the trade's direction (mirror for
bearish), as in v121. "Entry-side level" = nearest support at or below
`Close[t]` for bullish (nearest resistance at or above for bearish);
"opposing level" = nearest resistance above (support below). Levels come
from `levels.build_level_map(df, HORIZONS[horizon_key], Close[t])` built
**inside** the feature function on the truncated frame, so live and replay
are identical and no level map has to be threaded through the call sites.

| Key | Definition | Course |
|---|---|---|
| `target_capped` | `abs(tp1 - (entry ± abs(entry - stop) * max_rr)) <= 1e-6 * max(1, abs(entry))`; `None` when `entry` not supplied | D20 |
| `stop_clamped` | `abs(planned_loss_pct(entry, stop) - (HARD_MAX_PLANNED_LOSS_PCT - CLAMP_HEADROOM_PCT)) <= 1e-6` **and** `config.CLAMP_STOP_TO_HARD_CAP`; `None` when `entry` not supplied | D19 |
| `zone_dist_atr` | `abs(Close[t] - entry-side level) / ATR14[t]`; `None` if no entry-side level | D15 location |
| `room_atr` | `abs(opposing level - Close[t]) / ATR14[t]`; `None` if none | D20 |
| `range_pos` | bullish: `(Close[t] - SL) / (SH - SL)` with SH/SL the last **confirmed** swing high/low (v121 `confirmed_pivots`); bearish: `(SH - Close[t]) / (SH - SL)`; not clipped; `None` if `SH <= SL` or either missing | D15 location |
| `leg_phase` | bullish: `"impulse"` if `Close[t] > SH`, `"broken"` if `Close[t] < SL`, else `"pullback"`; mirror for bearish; `None` if SH/SL missing | D15 movement |
| `zone_state` | `classify_levels(df, t, [entry-side level], horizon_key=...)[0].state` (fresh / tested / delivered / decaying); `None` if it returns `[]` | D16 criterion 2 |
| `zone_touches` | that `LevelState.touches` | D16 criterion 2 |
| `zone_departure_atr` | let `j` = last bar `< t` whose range touched the entry-side level (within the lifecycle module's touch tolerance); max direction-signed `(Close[k] - level)` over `k ∈ (j, min(j+10, t)]`, divided by `ATR14[t]`; `None` if no touch or no bar after it | D16 criteria 1, 3 |

**Why the two flags are derived, not threaded.** Both values are produced by
fixed arithmetic from the same `entry` and `stop`, so exact equality
identifies them at all six `select_structural_target` call sites without
changing a builder's return type. A real level landing exactly on the
synthetic price within 1e-6 relative is negligible. The flag needs the
**planned** entry (the trigger), not the fill: every call site passes
`entry=` explicitly, and the two strategy-replay sites
(`backtesting/backtest.py:417`, `:495`) pass the pre-slippage `entry`, never
`entry_fill`. With no `entry=`, both flags are `None`, never guessed.
`max_rr` is read from the plan's `ScanParams` where the caller has them, else
`config.MAX_RISK_REWARD_RATIO`; the plan confirms each site.

**Not duplicates of v121's leg-shape keys** (added to v121 in `669e332e`).
`pullback_depth_frac` is the *deepest* retracement of the impulse leg
`SL0..SH`; `range_pos` is where the *close* sits in the latest confirmed
swing range, `SL` being the last confirmed low (which can postdate `SH`).
v121's leg keys are all `None` once `Close[t] > High[SH]`; `leg_phase`
labels that case `"impulse"` instead of leaving it blank. If a reviewer
finds a v125 key numerically identical to a v121 key on the fixtures, drop
the v125 key rather than ship a duplicate.

All thresholds above (the 10-bar departure window, 1e-6 tolerances, 60-bar
minimum) are frozen descriptive definitions, not search knobs; changing one
is a new spec.

## Placement and data flow

- `market/location.py` holds `location_features(df, direction, horizon_key)
  -> dict` returning the seven location/leg/zone keys. Fewer than 60 bars or
  no ATR → all `None`, never raises.
- `edge/context.py` gains `plan_provenance(entry, stop, tp1, max_rr) -> dict`
  and `entry_context(..., entry=None)`. `entry_context` merges both dicts;
  the nine keys are appended to `FEATURE_KEYS` so the existing
  `{key: None}` default covers short frames and old records. Pre-existing
  keys are untouched.
- Call sites: `planning/params.py:stamp_entry_context` (passes `plan.entry`;
  live confluence via `scanning/analyze.py:396`, live strategy via
  `scanning/strategy_pass.py:70`, confluence replay via
  `backtesting/backtest_scenarios.py:155`) and the two direct calls in
  `backtesting/backtest.py`.
- **Storage**: follows whatever v121 Task 4 settles (expected JSONB document,
  no Alembic revision); the plan re-confirms with the `schema-change` skill.
  A missing key on an old record reads as `None` — the existing default, not
  read-time upcasting. No backfill.

## No-lookahead

Every input is `df.iloc[:t+1]`. Pivots come **only** from v121's
`confirmed_pivots` (confirmation lag lives in one place). `classify_levels`
already slices to `:i+1`. `zone_departure_atr` caps its window at `t` even
when the last touch is within 10 bars of entry. The live snapshot may end on
a forming bar exactly as v121's does; acceptable for a descriptive record,
and no consumer may act on these keys without calling the pure functions on
completed bars.

## Report

Extend `scripts/reports/volume_context_report.py` (v121) with the nine keys
(categorical as-is; continuous by fixed TRAIN quintiles) and one cross-table
`target_capped × stop_clamped` (N, WR, ExpR, sum R), split confluence /
strategy and per direction — inheriting v121's TRAIN-only refusal for
`--source replay` (any window touching 2024-01-01 or later is refused) and
its "live = monitoring only, no inferential statistic" header. The header
adds: **not to be used to choose the structure-break entry spec's grid
values** (frozen in that spec before this report exists).

## Testing

- `location_features`: hand-built frames with known answers for each key —
  price sitting on a support (`zone_dist_atr` ≈ 0), mid-range
  (`range_pos` ≈ 0.5), above the last SH (`"impulse"`), below the last SL
  (`"broken"`), a touch followed by a 3-ATR close-away
  (`zone_departure_atr` ≈ 3) — plus bearish mirrors.
- Truncation: for every cut `t`, `location_features(df.iloc[:t+1])` equals
  the value computed at `t` by walking the full frame; departure never reads
  a bar after `t`.
- `plan_provenance` against real builder output: a `build_confluence_plan`
  whose nearest qualifying level is beyond the cap → `target_capped=True`;
  a scenario stop beyond 2% → `stop_clamped=True`; an ordinary plan →
  `False`/`False`; `entry=None` → both `None`.
- `entry_context` witness: every pre-existing key byte-identical on a
  fixture captured before the change; < 60 bars → every new key `None`.
- Report: the cross-table renders; replay window ending after 2023-12-31 is
  refused (inherited test still passes).
- `no-lookahead` skill review on `location.py` and `context.py`.

## Parallelisation

`market/location.py` and `plan_provenance` are independent of each other and
can be built in parallel. The `entry_context` merge and the four call-site
changes consume both. The report extension consumes the stored keys. The
storage re-confirmation (schema-change skill) is independent and can run
beside the feature work. Full suite once at the end. Whole spec waits on
v121 being merged.
