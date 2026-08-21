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
- Holiday shift: a static module-level frozenset of NYSE full-day closures
  **that fall on a Friday** — the only ones that can displace an expiration.
  A Friday closure does two things: it cancels that week's weekly expiration,
  and if it was the nominal third Friday it moves the monthly expiration back
  to the Thursday. Confirmed during the v40 survey that the repo has no
  existing holiday list and no `pandas_market_calendars` dependency, so this
  table is new; it is scoped to Fridays on purpose and must not be used as a
  general market calendar. It needs manual extension for future years —
  carried with a `LAST_YEAR_COVERED` constant so a maintainer knows when.

  Two real collisions land inside the 2026-2030 window the table covers, and
  both are worth keeping as tests: **2026-06-19** (Juneteenth) and
  **2030-04-19** (Good Friday) are each the nominal third Friday of their
  month *and* a full-day closure, so expiration moves to the Thursday.
- Quarterly "triple/quad witching" Fridays (Mar/Jun/Sep/Dec) are classified
  as `'monthly'`, not a distinct tier — YAGNI; add a third tier later only if
  the two-tier behavior proves insufficient in practice.
- Fully unit-testable with no mocking: feed it known dates, assert the tier.

### 2. Tier resolution — a module, not a context column

**Corrected 2026-08-21 while writing plan v44; the original draft said to add
a `ctx_opex_tier` column to `market_context`. Reading the code showed that to
be wrong on two counts:**

- `market_context.get()` returns `None` whenever `REGIME_GATES_ENABLED` is off
  (`market_context.py:134-135`). Routing opex through `CTX_COLUMNS` would wire
  this feature's on/off switch to an unrelated flag — turning regime gating off
  would silently stop opex caution too, with nothing saying so.
- The context block exists to align an **external** series (SPY-derived regime)
  onto a ticker's index without lookahead; `market_context.py`'s docstring
  argues that at length. Opex has no external series — the tier is a pure
  function of the bar's own date — so there is nothing to align and the
  machinery buys nothing.

The tier is therefore resolved by `opex.current_tier()` in the new module,
called once per scan in `engine.py` and passed down, rather than recomputed per
ticker per horizon.

### 3. Gate (`swingbot/core/market/entry_filters.py`)

New `apply_opex_caution(...)`, added alongside the existing
`apply_regime_gate` (~line 112), called from the same site in the entry
pipeline immediately after it:

| tier | Min confidence level | Min strategies confirmed | Near-close entry suppression | Stop/size adjustment |
|---|---|---|---|---|
| `'monthly'` | `+OPEX_MONTHLY_CONFIDENCE_BUMP` (capped Lv5) | `+OPEX_MONTHLY_CONFLUENCE_BUMP` (capped 10) | suppress new entries inside `OPEX_NEAR_CLOSE_SUPPRESS_MINUTES` of **16:00 US/Eastern** | stop widened by `OPEX_STOP_WIDEN_PCT` (ATR path only), size cut by `OPEX_SIZE_REDUCTION_PCT` |
| `'weekly'` | no change | `+OPEX_WEEKLY_CONFLUENCE_BUMP` (capped 10) | none | none |
| `None` | no change | no change | no change | no change |

**Corrected 2026-08-21 while writing plan v44.** Three things the original
draft got wrong, each found by reading the code:

- **The bumps are integers, not floats.** Both gates are integer dials —
  `MIN_ALERT_CONFIDENCE_LEVEL` is a `select` over `1..5` (`config.py:174-176`)
  and `MIN_TARGET_CONFLUENCE_COUNT` a `number` over `1..10`
  (`config.py:167-173`). A float bump has nowhere to land. Since a single
  1-5 level dial cannot express two tiers of "bump" from a default of 4,
  monthly takes both dials and weekly takes the confluence dial only — that
  asymmetry is what makes weekly the lighter tier.
- **The near-close anchor is 16:00 US/Eastern, not `SESSION_END_HOUR`.**
  `SESSION_END_HOUR` defaults to `23` **Europe/Berlin** (`config.py:121-123`),
  which is 17:00 ET — an hour *after* the US close. A window measured back
  from it would have fired entirely after the market shut.
- **Only the ATR stop is widened.** `plan_engine.py:770-776` documents that
  fib / Elliott / S-R stops sit behind real structure and must not be scaled,
  because scaling slides the stop off the level it exists to hide behind.

Both gates meet in one helper, `_build_requirement_checks` (`embeds.py:174`),
which is where the tightening lands. Suppression is expressed as an extra
`RequirementCheck` rather than a separate code path, so it feeds the existing
`all_requirements_met` gate and the funnel counters — open-trade monitoring,
which shares the same scan tick, is untouched.

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
- `OPEX_MONTHLY_CONFIDENCE_BUMP` — int, default `1` (levels added, capped Lv5).
- `OPEX_MONTHLY_CONFLUENCE_BUMP` — int, default `1` (strategies added, capped 10).
- `OPEX_WEEKLY_CONFLUENCE_BUMP` — int, default `1` (the only weekly tightening).
- `OPEX_NEAR_CLOSE_SUPPRESS_MINUTES` — int, default `60`, measured back from
  16:00 US/Eastern.
- `OPEX_STOP_WIDEN_PCT` — float, default `10` (percent, ATR path only).
- `OPEX_SIZE_REDUCTION_PCT` — float, default `25` (percent, both sizing modes).

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
