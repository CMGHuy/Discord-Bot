Version: ui 1.8.0 · bot 1.3.2
Bump: bot minor (1.3.2 → 1.4.0) — alert gating, alert content (badge), and
trade-plan risk parameters (stop/size) change observably on opex days. `ui`
none: new settings render automatically on the existing generic Settings
page via the `Field(...)` mechanism, same as every other config flag.

# Opex-day caution gating

## Problem

The bot has no concept of options-expiration days. `swingbot/core/market/strategy.py:6`
and `swingbot/core/market/levels_lifecycle.py:9` both note explicitly that
"swingbot has no options data" — the scan pipeline treats every trading day
identically. In practice, standard monthly equity/index options expiration
(the 3rd Friday of each month) and, increasingly, weekly expirations on major
index ETFs (SPY/QQQ/IWM-style Friday expirations) bring elevated pinning and
unwind-driven whipsaw risk, especially into the close. The bot currently has
no way to recognize these days and adjust its posture.

## Non-goals

- **No options-chain data, no gamma exposure, no dealer-positioning math.**
  This spec is pure calendar logic (date math only). GEX/gamma-flip-level
  computation is a separate spec ([[gamma-flip-level-design]],
  `2026-08-21-v43-gamma-flip-level-design.md`) that happens to reuse this
  spec's tier classification but has no other dependency on it.
- **No per-horizon scaling.** Caution applies uniformly across all 10 swing
  horizons (`2w`…`9m`). A future spec could scale behavior by horizon if this
  proves too blunt in practice, but that is out of scope here.
- **No new market-calendar dependency.** No `pandas_market_calendars` or
  similar package. A small static NYSE-holiday table is enough for the one
  edge case that needs it (3rd Friday falling on a holiday).
- **Not touching regime gating.** `apply_regime_gate` and `regime2.py` are
  unmodified; opex caution is an independent, additive gate that runs
  alongside it, not a replacement or extension of the regime state machine.

## Design

### 1. Opex calendar (`swingbot/core/market/opex_calendar.py`, new)

Pure function, no network, no I/O:

```python
def opex_tier(date: datetime.date) -> str | None:
    """'monthly' if date is the 3rd-Friday-equivalent standard equity/index
    expiration for its month (shifted to the preceding Thursday if the 3rd
    Friday is a market holiday), 'weekly' if date is any other Friday,
    else None."""
```

- "3rd Friday of the month" computed by pure date arithmetic (no external
  calendar package).
- Holiday shift: a small static module-level tuple of known NYSE full-day
  holidays (New Year's Day, MLK Day, Presidents' Day, Good Friday, Memorial
  Day, Juneteenth, Independence Day, Labor Day, Thanksgiving, Christmas —
  observed-date rules included) covering the years the bot will realistically
  run. If the 3rd Friday lands on one of these, `opex_tier` returns
  `'monthly'` for the preceding Thursday instead. This table needs periodic
  manual updates for future years — documented with a comment noting the
  last year covered, so a future maintainer knows when to extend it.
- Quarterly "triple/quad witching" Fridays (Mar/Jun/Sep/Dec) are classified
  as `'monthly'`, not a distinct tier — YAGNI; add a third tier later only if
  the two-tier behavior proves insufficient in practice.
- Fully unit-testable with no mocking: feed it known dates, assert the tier.

### 2. Context integration (`swingbot/core/market/market_context.py`)

`get()` (existing, ~line 125-144) already computes and caches a `ctx_regime`
column per scan cycle, short-circuiting to `None` when its enabling flag is
off. This spec adds a `ctx_opex_tier` column using the identical pattern:
computed once per scan cycle from `opex_tier(today)`, cached the same way,
and hard-`None` whenever `OPEX_CAUTION_ENABLED` is off — so a disabled flag
costs nothing extra per scan.

### 3. Gate (`swingbot/core/market/entry_filters.py`)

New `apply_opex_caution(...)`, added alongside the existing
`apply_regime_gate` (~line 112), called from the same site in the entry
pipeline immediately after it:

| `ctx_opex_tier` | Confirmation threshold | Near-close entry suppression | Stop/size adjustment |
|---|---|---|---|
| `'monthly'` | `+OPEX_MONTHLY_THRESHOLD_BUMP` | suppress new entries inside `OPEX_NEAR_CLOSE_SUPPRESS_MINUTES` of `SESSION_END_HOUR` | stop widened by `OPEX_STOP_WIDEN_PCT`, size cut by `OPEX_SIZE_REDUCTION_PCT` |
| `'weekly'` | `+OPEX_WEEKLY_THRESHOLD_BUMP` | none | none |
| `None` | no change | no change | no change |

The near-close suppression window is evaluated against wall-clock time versus
the existing `SESSION_END_HOUR` config (`config.py:118-121`) — no new
session-hours concept, just a new offset applied to the existing one.

Every alert embed gets a small "⚠️ OPEX" (monthly) or "⚠️ Weekly opex"
(weekly) note whenever `ctx_opex_tier` is set, independent of whether that
particular signal passed the gate — a trader glancing at any alert that day
sees the context, matching the existing badge/registry pattern referenced in
`docs/claude/architecture.md`.

### 4. Config (`swingbot/config.py`)

New "Options / Opex" section, following the existing `Field(...)` shape
(example: `REGIME_GATES_ENABLED` at `config.py:598-604`):

- `OPEX_CAUTION_ENABLED` — checkbox, default `false`. Master switch, off
  until validated, matching every other new-behavior flag in this repo.
- `OPEX_MONTHLY_THRESHOLD_BUMP` — float, starting default `1.0`.
- `OPEX_WEEKLY_THRESHOLD_BUMP` — float, starting default `0.5` (smaller than
  the monthly bump).
- `OPEX_NEAR_CLOSE_SUPPRESS_MINUTES` — int, starting default `30`.
- `OPEX_STOP_WIDEN_PCT` — float, starting default `10` (percent).
- `OPEX_SIZE_REDUCTION_PCT` — float, starting default `25` (percent).

These starting defaults ship behind `OPEX_CAUTION_ENABLED=false`; per
`docs/claude/backtest-methodology.md`'s TRAIN/VALIDATION discipline, they
are tuned via backtest as new parameters (not a re-run of any closed
pre-registration) before the flag is ever turned on by default.

### 5. Error handling

- `opex_tier()` is pure and total — every `datetime.date` input has a
  defined output (`'monthly'`, `'weekly'`, or `None`). No exceptions to
  handle.
- If `OPEX_CAUTION_ENABLED` is off, `ctx_opex_tier` is `None` for every row,
  and `apply_opex_caution` is a no-op — identical shape to how
  `apply_regime_gate` fails safe when `REGIME_GATES_ENABLED` is off.
- No new external dependency, no new network call, so no new failure mode
  to guard against beyond the pure-function correctness itself.

## Testing

- `opex_calendar.py`: unit tests covering 3rd-Friday computation across
  months with every possible day-of-week start, the holiday-shift case (3rd
  Friday landing on a known holiday → Thursday), a year boundary, and a
  leap year. Fully deterministic, no mocking.
- `entry_filters.py`: unit tests mirroring the existing `apply_regime_gate`
  tests — threshold-bump math for both tiers, near-close suppression window
  boundary (just before/at/just after the cutoff), and confirmation that the
  gate no-ops cleanly with `OPEX_CAUTION_ENABLED=false`.
- `market_context.py`: confirms `ctx_opex_tier` is cached once per scan cycle
  (not recomputed per ticker) and is `None` when the flag is off.
- Embed/badge: a test asserting the "⚠️ OPEX" note appears on
  `ctx_opex_tier='monthly'` and not on `None`, independent of gate pass/fail.
- Run via `python scripts/dev/testrun.py file <new test file>` while
  iterating; full suite via the `test-runner` subagent before commit, per
  this repo's standing convention.

## Parallelisation

Single cohesive unit — one new pure-logic module
(`opex_calendar.py`), one new column in `market_context.py`, one new gate
function in `entry_filters.py`, and the config Fields. All touch different
files but the gate function depends on the context column which depends on
the calendar module, so build order is sequential:
`opex_calendar.py` → `market_context.py` column → `entry_filters.py` gate →
embed badge → config Fields (can be added any time, independent of the
others). Not worth splitting across parallel sessions — this is a
single-session, single-PR-sized change.
