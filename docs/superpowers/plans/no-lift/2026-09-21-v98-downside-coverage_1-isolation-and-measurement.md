# Downside coverage (v98) — Part 1: isolation and the Q-INV measurement

> Header block, goal, discrepancies, global constraints and the parallelisation
> map live in `2026-09-21-v98-downside-coverage_0-index.md`. Read it first — the
> constraints in it govern every task here, including "do not regenerate the
> cohort registry" and "one full-suite run, in Part 2".

# Phase 1 — Isolation: make the long book provably unreachable

### Task D1: Population classifier and ETF tagging

The single source of truth for "which population does this symbol belong to". Every
later task imports from here rather than re-listing four tickers, so the basket is
changed in exactly one place.

**Files:**
- Create: `swingbot/core/market/populations.py`
- Create: `tests/market/test_populations.py`
- Modify: `data/universe/etfs.json` (add the four rows — DISC-2)

**Interfaces:**
- Produces: `INVERSE_SYMBOLS: tuple[str, ...]`, `EQUITY = "equity"`,
  `INVERSE = "inverse"`, `population_of(ticker: str) -> str`,
  `is_inverse(ticker: str) -> bool`. Consumed by D2, D3, D4, D5, D13, D14.
- Consumes: nothing. Deliberately dependency-free (no `config` import) so it can be
  imported from `cohort_registry.py`, which is loaded during registry reads.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_populations.py
import json
from pathlib import Path

from swingbot.core.market import populations as pop


def test_the_four_inverse_symbols_and_only_those():
    assert pop.INVERSE_SYMBOLS == ("PSQ", "SH", "RWM", "DOG")


def test_population_of_is_case_insensitive_and_defaults_to_equity():
    assert pop.population_of("PSQ") == pop.INVERSE
    assert pop.population_of("psq") == pop.INVERSE
    assert pop.population_of("AAPL") == pop.EQUITY
    assert pop.population_of("GC=F") == pop.EQUITY   # futures are not the basket
    assert pop.population_of("") == pop.EQUITY
    assert pop.population_of(None) == pop.EQUITY


def test_equity_is_the_literal_string_the_cohort_keys_use():
    # D2 keys existing cells on this exact value; a rename silently rebands.
    assert pop.EQUITY == "equity"


def test_all_four_are_tagged_as_etfs_in_the_universe_file():
    # DISC-2: untagged, events.get_next_earnings_date does a live Yahoo
    # lookup per scan that can never succeed.
    from swingbot.core.marketdata.universe import is_etf
    for sym in pop.INVERSE_SYMBOLS:
        assert is_etf(sym), f"{sym} missing from data/universe/etfs.json"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_populations.py`
Expected: FAIL — `ModuleNotFoundError: swingbot.core.market.populations`

- [ ] **Step 3: Write the module**

```python
# swingbot/core/market/populations.py
"""Which measured population a symbol belongs to (v98).

The long book was measured on a liquidity-filtered *equity* universe. The v98
inverse basket is an out-of-population extrapolation onto the same shipped
bullish arms, so every place that pools outcomes -- the cohort registry's
`pool_mean_r`, badge drift's live win rate, the open-slot warning -- has to
tell the two apart or the new population silently re-bands the old one.

Deliberately dependency-free: cohort_registry.py imports this during a
registry read, so a `config` import here would drag the whole settings
module into that path.

The basket is fixed by the v98 spec on measured hedge quality and liquidity
against this specific watchlist (PSQ -0.936 / SH -0.910 / RWM -0.848 /
DOG -0.811 correlation vs the book). Adding a symbol here is a new
pre-registration, not an edit -- current arithmetic was only ever measured on
these four (docs/superpowers/results/2026-09-21-v98-q-inv-train.md).
"""
from __future__ import annotations

EQUITY = "equity"
INVERSE = "inverse"

#: Unleveraged -1x index inverses only. Leveraged (-2x/-3x) products carry
#: path-dependent daily-rebalance decay that breaks multi-month horizons
#: structurally; unleveraged SECTOR inverses (MYY/REK/SEF/EFZ) are excluded on
#: measured evidence -- $0.2-0.4M median daily dollar volume. See the spec.
INVERSE_SYMBOLS: tuple[str, ...] = ("PSQ", "SH", "RWM", "DOG")

_INVERSE_SET = frozenset(INVERSE_SYMBOLS)


def population_of(ticker: str | None) -> str:
    """Return ``INVERSE`` for a basket member, ``EQUITY`` for everything else.

    Everything-else is the safe default on purpose: an unknown symbol lands in
    the population the registry already describes rather than creating a cell
    nothing was measured against.
    """
    if not ticker:
        return EQUITY
    return INVERSE if str(ticker).upper() in _INVERSE_SET else EQUITY


def is_inverse(ticker: str | None) -> bool:
    return population_of(ticker) == INVERSE
```

- [ ] **Step 4: Add the four rows to `data/universe/etfs.json`**

Append, matching the existing row shape exactly (`_REQUIRED_KEYS` in
`marketdata/universe.py` is `{symbol, name, sector, etf}`; unknown keys are dropped
and a row missing one is skipped silently):

```json
  {"symbol": "PSQ", "name": "ProShares Short QQQ", "sector": "Inverse", "etf": true},
  {"symbol": "SH", "name": "ProShares Short S&P500", "sector": "Inverse", "etf": true},
  {"symbol": "RWM", "name": "ProShares Short Russell2000", "sector": "Inverse", "etf": true},
  {"symbol": "DOG", "name": "ProShares Short Dow30", "sector": "Inverse", "etf": true}
```

Read the file first and match its indentation. `"sector": "Inverse"` is a new
sector value — check it does not collide with a key in
`fetch._etf_symbol_of_sector()`; if it does, use `"Inverse Index"` and update the
test. The sector only matters for `correlation.cluster_exposure`'s *fallback* path
(`correlation.py:39`, used only when correlation is uncomputable), and these four
always have computable correlation.

- [ ] **Step 5: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_populations.py`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/populations.py tests/market/test_populations.py data/universe/etfs.json
git commit -m "feat(v98): population classifier for the inverse basket + ETF tagging"
```

### Task D2: Extend the cohort key with population

Spec Isolation requirement 1. `band()` classifies each cell against a pooled
`pool_mean_r`; an inverse trade carries `direction="bullish"` and would land in the
same cell as long-AAPL, shifting the pool and re-banding equity cells whose own
performance never changed. **Existing bullish cell keys must stay byte-identical**
so the committed `cohort_registry.json` keeps resolving without regeneration.

**Files:**
- Modify: `swingbot/core/backtesting/cohort_registry.py`
- Modify: `swingbot/core/planning/params.py` (`stamp_cohort`, line 131)
- Modify: `scripts/backtest/emit_cohort_registry.py`
- Test: `tests/test_cohort_registry.py`, `tests/test_emit_cohort_registry.py`

**Interfaces:**
- Consumes: `market.populations.population_of` (D1).
- Produces: `cohort_key(direction, regime2_state, population=EQUITY) -> str`,
  `get_cohort(direction, regime2_state, population=EQUITY) -> Cohort`. A
  `pool_mean_r_by_population` block in the emitted JSON, read with fallback to the
  existing scalar `pool_mean_r`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_cohort_registry.py
from swingbot.core.market.populations import EQUITY, INVERSE


def test_equity_key_is_byte_identical_to_the_pre_v98_form():
    # The committed cohort_registry.json was generated under the 2-arg key.
    # Any suffix here invalidates every existing cell at once.
    assert cr.cohort_key("bullish", "bull_quiet") == "bullish|bull_quiet"
    assert cr.cohort_key("bullish", "bull_quiet", EQUITY) == "bullish|bull_quiet"


def test_inverse_population_gets_its_own_cell():
    assert cr.cohort_key("bullish", "bull_quiet", INVERSE) == "bullish|bull_quiet|inverse"


def test_inverse_lookup_does_not_read_an_equity_cell(tmp_path):
    _write_registry(tmp_path, {"bullish|bull_quiet": {
        "n_live": 100, "n_backtest": 100,
        "win_rate_live": 70.0, "expectancy_r_live": 1.5,
        "win_rate_backtest": 70.0, "expectancy_r_backtest": 1.5}})
    assert cr.get_cohort("bullish", "bull_quiet", INVERSE).label == "COHORT_UNKNOWN"
    assert cr.get_cohort("bullish", "bull_quiet", EQUITY).label != "COHORT_UNKNOWN"


def test_inverse_cell_bands_against_its_own_pool_not_the_equity_pool(tmp_path):
    path = tmp_path / "cohort_registry.json"
    path.write_text(json.dumps({
        "run_date": "2026-09-21", "window": "t",
        "pool_mean_r": 1.50,
        "pool_mean_r_by_population": {"equity": 1.50, "inverse": 0.10},
        "cells": {"bullish|bull_quiet|inverse": {
            "n_live": 0, "n_backtest": 80,
            "win_rate_backtest": 55.0, "expectancy_r_backtest": 0.40}},
    }), encoding="utf-8")
    cr.reload_registry()
    cr.load_registry(path)
    # 0.40 is far BELOW the equity pool (1.50 -> POOR) but clearly ABOVE its
    # own (0.10 + 0.15 -> STRONG). Reading the wrong pool is visible here.
    assert cr.get_cohort("bullish", "bull_quiet", INVERSE).label == "COHORT_STRONG"
    cr.reload_registry()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_cohort_registry.py`
Expected: FAIL — `cohort_key() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Implement**

In `swingbot/core/backtesting/cohort_registry.py`:

```python
from swingbot.core.market.populations import EQUITY


def cohort_key(direction: str, regime2_state: str, population: str = EQUITY) -> str:
    """Return the registry key for the plan's directional/regime/population cell.

    v98: the equity form is deliberately the un-suffixed 2-part key, NOT
    "...|equity". The committed cohort_registry.json was generated before this
    argument existed; suffixing the default would invalidate every cell in it
    at once and silently return COHORT_UNKNOWN for the entire long book.
    """
    if population == EQUITY:
        return f"{direction}|{regime2_state}"
    return f"{direction}|{regime2_state}|{population}"
```

and in `get_cohort`, take `population: str = EQUITY`, pass it to `cohort_key`, and
resolve the pool per population:

```python
def _pool_mean_for(registry: dict, population: str) -> float:
    """Band an inverse cell against the inverse pool, never the equity pool.

    Falls back to the flat pool_mean_r for any registry emitted before v98 --
    which, for an equity lookup, is exactly the number it always used.
    """
    by_pop = registry.get("pool_mean_r_by_population") or {}
    if population in by_pop:
        return float(by_pop[population])
    return float(registry.get("pool_mean_r", 0.0))
```

using it in place of `float(registry.get("pool_mean_r", 0.0))` at line 100.

In `swingbot/core/planning/params.py:stamp_cohort`, derive the population from the
plan's own ticker (`plan.ticker`, `plan_types.py:24`) and record it so a stored
plan says which pool it was banded against:

```python
    from swingbot.core.backtesting.cohort_registry import get_cohort
    from swingbot.core.market.populations import population_of

    population = population_of(plan.ticker)
    cohort = get_cohort(plan.direction, regime2_state, population)
    plan.cohort_label = cohort.label
    plan.cohort_stats = {
        "label": cohort.label,
        "regime2_state": regime2_state,
        "population": population,
        ...
    }
```

Both callers (`planning/builders.py:317`, `scanning/strategy_pass.py:67`) keep their
existing two-argument call — the ticker comes off the plan, not the call site.

- [ ] **Step 4: Carry the ticker through the emitter**

`scripts/backtest/emit_cohort_registry.py:_normalize_live_trades` currently drops
the ticker, so `aggregate_cells` cannot classify. Add `"ticker": trade.get("ticker")`
to the dict it builds, then in `aggregate_cells`:

```python
        key = cohort_key(direction, str(matches.iloc[0]),
                         population_of(trade.get("ticker")))
        buckets.setdefault(key, []).append(float(realized_r))
```

and replace `_pool_mean_r` with a per-population version emitting both the legacy
scalar (unchanged meaning: the equity pool) and the new block:

```python
def _pool_means(live: list[dict], backtest: list[dict]) -> tuple[float, dict]:
    """Return (equity pool mean, {population: pool mean}).

    The scalar stays the EQUITY figure so a registry emitted by this script is
    still read correctly by a pre-v98 checkout -- the equity book is all such a
    checkout can see anyway.
    """
    by_pop: dict[str, list[float]] = {}
    for trade in live + backtest:
        if trade.get("r_realized") is None:
            continue
        by_pop.setdefault(population_of(trade.get("ticker")), []).append(
            float(trade["r_realized"]))
    means = {p: round(sum(v) / len(v), 6) for p, v in by_pop.items() if v}
    return means.get(EQUITY, 0.0), means
```

Confirm the backtest replay JSON (`--backtest`, e.g. `data/confluence_replay.json`)
carries a `ticker` field before relying on it; if it does not, `population_of(None)`
returns `EQUITY`, which is the correct reading for a replay of the equity universe —
assert that in `tests/test_emit_cohort_registry.py` rather than leaving it implicit.

- [ ] **Step 5: Run both test files**

```bash
python scripts/dev/testrun.py file tests/test_cohort_registry.py
python scripts/dev/testrun.py file tests/test_emit_cohort_registry.py
```
Expected: PASS both.

**Do NOT run `emit_cohort_registry.py` in this task.** The committed
`cohort_registry.json` stays exactly as it is; this task only makes a future
regeneration safe.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/cohort_registry.py swingbot/core/planning/params.py \
        scripts/backtest/emit_cohort_registry.py tests/test_cohort_registry.py \
        tests/test_emit_cohort_registry.py
git commit -m "feat(v98): key cohort cells by population, equity keys byte-identical"
```

### Task D3: Filter badge and drift populations to equities

Spec Isolation requirement 2. `analytics/calibration.py:83 badge_drift()` compares
a strategy's live closed trades against its committed out-of-sample win rate. The
registry's OOS numbers were measured on equities only. An inverse trade logged
under the same strategy name moves the live side of that comparison and can trip
the pre-registered `live_n >= 20 and live_wr < oos_wr - 10.0` decay alert on a
strategy whose equity behaviour never changed.

**The pre-registered rule itself is not touched** — only which trades are eligible
to be counted against it, which is a population question, not a threshold question.

**Files:**
- Modify: `swingbot/core/analytics/calibration.py`
- Modify: `swingbot/core/analytics/insights.py` (line 144), `swingbot/core/analytics/snapshots.py` (line 63)
- Test: `tests/analytics/test_calibration.py` (create if absent; check
  `tests/analytics/` for the existing file name first)

**Interfaces:**
- Consumes: `market.populations.population_of`, `EQUITY` (D1).
- Produces: `badge_drift(closed, registry_entries, population=EQUITY)`.

- [ ] **Step 1: Write the failing test**

```python
from swingbot.core.analytics.calibration import badge_drift
from swingbot.core.market.populations import EQUITY, INVERSE


def _t(ticker, outcome):
    return {"ticker": ticker, "strategy": "RSI", "outcome": outcome,
            "r_realized": 1.0 if outcome == "win" else -1.0}


_REG = [{"strategy": "RSI", "status": "VALIDATED", "n": 100,
         "win_rate": 60.0, "run_date": "2026-01-01"}]


def test_inverse_losses_do_not_drag_the_equity_drift_row():
    equity = [_t("AAPL", "win")] * 25
    inverse = [_t("PSQ", "loss")] * 25
    row = badge_drift(equity + inverse, _REG)[0]
    assert row["live_n"] == 25          # inverse excluded
    assert row["live_wr"] == 100.0
    assert row["drift_alert"] is False  # would alert at 50% if pooled


def test_population_inverse_selects_only_the_inverse_trades():
    rows = badge_drift([_t("AAPL", "win")] * 25 + [_t("PSQ", "loss")] * 25,
                       _REG, population=INVERSE)
    assert rows[0]["live_n"] == 25 and rows[0]["live_wr"] == 0.0


def test_missing_ticker_counts_as_equity():
    # Legacy rows predate the ticker field on some paths; they belong to the
    # population the registry describes, not to a new one.
    assert badge_drift([{"strategy": "RSI", "outcome": "win"}] * 25,
                       _REG)[0]["live_n"] == 25
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_calibration.py`
Expected: FAIL — `badge_drift() got an unexpected keyword argument 'population'`

- [ ] **Step 3: Implement**

In `calibration.py`, add the parameter and filter **once, at the top**, before the
per-strategy loop, so every row in the result describes one population:

```python
def badge_drift(closed: list[dict], registry_entries: list[dict],
                population: str = EQUITY) -> list[dict]:
    """...existing docstring...

    v98: `population` restricts which live trades are eligible. The registry's
    out-of-sample numbers were measured on the equity universe, so pooling the
    inverse basket into the live side compares two different populations and
    can raise a decay alert on a strategy whose equity behaviour is unchanged.
    The PRE-REGISTERED rule (live_n >= 20, live_wr < oos_wr - 10.0) is NOT
    touched -- this changes the eligible set, not the threshold.
    """
    from swingbot.core.market.levels import strategy_family
    from swingbot.core.market.populations import population_of

    closed = [t for t in closed if population_of(t.get("ticker")) == population]
```

Leave `insights.py:144` and `snapshots.py:63` calling it with two arguments — the
default is `EQUITY`, which is exactly today's meaning for today's book. Add a
one-line comment at each site saying so, so a later reader does not "fix" it by
passing the full set. Also update `calibration.py`'s module docstring to name the
population argument.

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/analytics/test_calibration.py`
Expected: PASS (3 new tests, existing tests unchanged)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/calibration.py swingbot/core/analytics/insights.py \
        swingbot/core/analytics/snapshots.py tests/analytics/test_calibration.py
git commit -m "feat(v98): badge drift compares equity live trades to equity OOS numbers"
```

### Task D4: Inverse sub-cap of 4, held outside the 30

Spec Isolation requirement 3, re-derived per **DISC-1**: the 30-slot limit is
advisory today, so there is nothing to "hold outside" until a real counter exists.
Two halves:

1. The long warning at `scan_run.py:823-827` counts **equity** open positions only,
   so an open PSQ never changes the text of a long alert.
2. The inverse basket gets a **hard** concurrent cap of 4 — the full basket, chosen
   so no instrument is arbitrarily locked out of a decline. The four are ~0.95
   correlated with each other and should be read as roughly one trade at 4x size;
   the cap exists for isolation, not diversification.

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py`
- Modify: `swingbot/core/tracking/performance.py` (add the population-aware count)
- Test: `tests/scanning/test_inverse_slot_cap.py`

**Interfaces:**
- Consumes: `market.populations.population_of`, `INVERSE_SYMBOLS` (D1);
  `config.INVERSE_MAX_CONCURRENT` (D12 — until then read with
  `getattr(config, "INVERSE_MAX_CONCURRENT", 4)`).
- Produces: `performance.TradeLog.open_count_by_population() -> dict[str, int]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/scanning/test_inverse_slot_cap.py
import pytest

from swingbot.core.scanning import scan_run


def _open(ticker):
    return {"ticker": ticker, "status": "open"}


def test_equity_slot_warning_ignores_open_inverse_positions():
    opens = [_open("AAPL")] * 29 + [_open("PSQ"), _open("SH")]
    # 31 open in total, but only 29 equities -- below the 30 limit, so the
    # long alert must NOT gain a warning it would not have had before.
    assert scan_run.slot_warning(opens, max_open=30) is None


def test_equity_slot_warning_still_fires_on_thirty_equities():
    assert scan_run.slot_warning([_open("AAPL")] * 30, max_open=30) is not None


def test_inverse_cap_blocks_a_fifth_concurrent_inverse():
    opens = [_open(s) for s in ("PSQ", "SH", "RWM", "DOG")]
    assert scan_run.inverse_slot_available("PSQ", opens, cap=4) is False


def test_inverse_cap_never_consumes_a_long_slot():
    # 30 equities open -- the long book is "full" -- and an inverse still fires.
    opens = [_open("AAPL")] * 30
    assert scan_run.inverse_slot_available("PSQ", opens, cap=4) is True


def test_equity_candidate_is_never_subject_to_the_inverse_cap():
    opens = [_open(s) for s in ("PSQ", "SH", "RWM", "DOG")]
    assert scan_run.inverse_slot_available("AAPL", opens, cap=4) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_inverse_slot_cap.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.scanning.scan_run' has no attribute 'slot_warning'`

- [ ] **Step 3: Implement the two helpers in `scan_run.py`**

```python
def slot_warning(open_trades: list[dict], max_open: int) -> str | None:
    """The advisory "already N open" line for an EQUITY candidate.

    v98/DISC-1: this counts equities only. max_open_positions has never been a
    hard gate -- it composes this string and nothing else -- so the only way an
    open inverse position can reach a long alert is through this text. Counting
    the basket here would change long alerts, which the isolation constraint
    forbids.
    """
    from swingbot.core.market.populations import EQUITY, population_of
    n = sum(1 for t in open_trades if population_of(t.get("ticker")) == EQUITY)
    if n < max_open:
        return None
    return (f"{n} paper trades already open (limit {max_open}) "
            f"— consider skipping new size here.")


def inverse_slot_available(ticker: str, open_trades: list[dict],
                           cap: int | None = None) -> bool:
    """Whether a new INVERSE position may open. Always True for an equity.

    The cap is enforced against the inverse population ONLY and is held
    entirely outside max_open_positions: the two counters never share a number,
    so a full long book cannot starve the basket and a full basket cannot
    starve the long book. cap=4 is the whole basket (spec Decision 1) -- its
    purpose is isolation, not diversification; the four are ~0.95 correlated
    and are one trade at 4x size.
    """
    from swingbot import config
    from swingbot.core.market.populations import INVERSE, population_of
    if population_of(ticker) != INVERSE:
        return True
    limit = cap if cap is not None else getattr(config, "INVERSE_MAX_CONCURRENT", 4)
    held = sum(1 for t in open_trades if population_of(t.get("ticker")) == INVERSE)
    return held < limit
```

Then wire them at the existing site (`scan_run.py:823-827`), replacing the inline
`open_count`/`warning` block with `warning = slot_warning(open_trades, max_open)`,
and add the cap check to the guard that decides whether to log a new paper trade
(the `else` branch at line 818 already handles the "already has an open trade" case
— put `inverse_slot_available(result.ticker, open_trades)` alongside it, logging at
INFO when it suppresses, so a skipped inverse is visible in
`/opt/swing-bot/logs/*.log`). `open_trades` is already re-read per item for the
heat cap a few lines below (line ~869) — reuse that read rather than adding another.

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scanning/test_inverse_slot_cap.py`
Expected: PASS (5 tests)

Also run the neighbouring scan tests, since this edits a live code path:
`python scripts/dev/testrun.py file tests/scanning/test_scan_run.py`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/scan_run.py swingbot/core/tracking/performance.py \
        tests/scanning/test_inverse_slot_cap.py
git commit -m "feat(v98): inverse sub-cap of 4 held outside the 30-slot long warning"
```

### Task D5: Per-symbol horizon overlay resolved at call time

Spec Isolation requirement 4. The horizon restriction Q-INV will select must apply
to the four inverse symbols **only**, and must never be implemented by writing into
`STRATEGY_GATES` or `HORIZONS`. Both are module-level dicts shared by the live
scanner and the backtest in the same process; a mutation leaks into whatever else
is running.

The overlay ships **empty** in this task. Q-INV has not run yet, and an overlay
with a guessed horizon list would be exactly the unmeasured constant this repo's
discipline exists to prevent. D12 fills it from D11's verdict.

**Files:**
- Modify: `swingbot/core/market/entry_filters.py`
- Modify: `swingbot/core/market/strategy_types.py` (the overlay table + comment)
- Test: `tests/market/test_symbol_horizon_overlay.py`

**Interfaces:**
- Consumes: `market.populations` (D1).
- Produces: `strategy_types.SYMBOL_HORIZON_OVERLAY: dict[str, tuple[str, ...]]`
  (empty here), `entry_filters.entries_for(..., ticker: str | None = None)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_symbol_horizon_overlay.py
import copy

import pandas as pd
import pytest

from swingbot.core.market import entry_filters, strategy_types
from tests.conftest import make_trend_df


def test_overlay_ships_empty_until_q_inv_selects_a_subset():
    assert strategy_types.SYMBOL_HORIZON_OVERLAY == {}


def test_overlay_blocks_a_horizon_for_its_symbol_only(monkeypatch):
    monkeypatch.setitem(strategy_types.SYMBOL_HORIZON_OVERLAY, "PSQ", ("4w",))
    df = make_trend_df(120, direction="up")
    bull_blocked, _ = entry_filters.entries_for("RSI", df, "6m", ticker="PSQ")
    bull_allowed, _ = entry_filters.entries_for("RSI", df, "4w", ticker="PSQ")
    bull_equity, _ = entry_filters.entries_for("RSI", df, "6m", ticker="AAPL")
    assert not bull_blocked.any()          # 6m not in PSQ's overlay
    assert bull_allowed.equals(entry_filters.entries_for("RSI", df, "4w")[0])
    assert bull_equity.equals(entry_filters.entries_for("RSI", df, "6m")[0])


def test_no_ticker_argument_is_byte_identical_to_the_pre_v98_call(monkeypatch):
    monkeypatch.setitem(strategy_types.SYMBOL_HORIZON_OVERLAY, "PSQ", ("4w",))
    df = make_trend_df(120, direction="up")
    a, b = entry_filters.entries_for("RSI", df, "6m")
    assert a.equals(entry_filters.entries_for("RSI", df, "6m", ticker=None)[0])
    assert b.equals(entry_filters.entries_for("RSI", df, "6m", ticker=None)[1])


def test_overlay_never_mutates_the_shared_tables(monkeypatch):
    monkeypatch.setitem(strategy_types.SYMBOL_HORIZON_OVERLAY, "PSQ", ("4w",))
    gates_before = copy.deepcopy(strategy_types.STRATEGY_GATES)
    horizons_before = copy.deepcopy(strategy_types.HORIZONS)
    df = make_trend_df(120, direction="up")
    for hk in ("4w", "6m"):
        entry_filters.entries_for("RSI", df, hk, ticker="PSQ")
    assert strategy_types.STRATEGY_GATES == gates_before
    assert strategy_types.HORIZONS == horizons_before


def test_gate_override_is_not_called_outside_tests():
    """gate_override() mutates STRATEGY_GATES in place and can leak into a
    concurrent live scan. It is a test fixture, not a production tool."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[2]
    offenders = []
    for path in list((root / "swingbot").rglob("*.py")) + list((root / "scripts").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\bgate_override\s*\(", text) and path.name != "entry_filters.py":
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"gate_override() called outside tests: {offenders}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_symbol_horizon_overlay.py`
Expected: FAIL — `AttributeError: ... has no attribute 'SYMBOL_HORIZON_OVERLAY'`

- [ ] **Step 3: Add the overlay table to `strategy_types.py`**

Place it directly after `STRATEGY_GATES` (line ~239), so a reader of one sees the
other:

```python
# v98 per-SYMBOL horizon overlay -- resolved at call time by
# entry_filters.entries_for, ANDed with STRATEGY_GATES rather than replacing it.
#
# Deliberately a separate table: STRATEGY_GATES and HORIZONS are module-level
# dicts shared by the live scanner and the backtest inside one process, so a
# per-symbol restriction written INTO them leaks into every other symbol and
# into any concurrent scan. entry_filters.gate_override() has exactly that
# failure mode and is a test fixture only.
#
# Empty until v98's Q-INV TRAIN measurement selects a horizon subset for the
# inverse basket on real data -- expense ratio and daily-rebalance drag are
# unmodelled elsewhere and are what decide this table's contents. An entry
# added here without a results document behind it is an unmeasured constant.
# {"PSQ": ("4w", "2m")} reads as: on PSQ, only these horizons may emit.
SYMBOL_HORIZON_OVERLAY: dict[str, tuple[str, ...]] = {}
```

- [ ] **Step 4: Resolve it in `entries_for`**

Extend the signature with a trailing keyword and AND the overlay into the existing
`allowed()` closure (`entry_filters.py:127-163`), leaving the STRATEGY_GATES branch
byte-identical:

```python
def entries_for(strategy: str, df: pd.DataFrame, horizon_key: str,
                params: dict | None = None,
                regimes: "pd.Series | None" = None,
                ticker: str | None = None) -> tuple[pd.Series, pd.Series]:
    """...existing docstring...

    v98: `ticker` is optional and defaults to None, which reproduces the
    pre-v98 behaviour exactly -- all 12 existing call sites keep working
    unchanged. When supplied, SYMBOL_HORIZON_OVERLAY is consulted and ANDed
    with STRATEGY_GATES. Nothing is written back to either table.
    """
    ...
    from swingbot.core.market.strategy_types import SYMBOL_HORIZON_OVERLAY
    overlay = SYMBOL_HORIZON_OVERLAY.get((ticker or "").upper())
    if overlay is not None and horizon_key not in overlay:
        return _off(df), _off(df)
```

Put that check **after** the ENTRY_FUNCS dispatch and before/alongside the gates
block; returning two all-False series is the same shape every other block produces
and keeps the NO-LOOKAHEAD `.fillna(False)` invariant trivially (a constant-False
series has nothing to truncate).

Then pass `ticker=` from the two consumers of the single entry source:
`swingbot/core/backtesting/backtest.py:_vectorized_entries` and
`swingbot/core/market/signals.py` (`grep -n "entries_for" swingbot/` for the exact
sites). Every other call site stays as it is.

- [ ] **Step 5: Run to verify it passes**

```bash
python scripts/dev/testrun.py file tests/market/test_symbol_horizon_overlay.py
python scripts/dev/testrun.py file tests/market/test_entry_filters.py
```
Expected: PASS both. The second is the regression check that the default path did
not move.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/entry_filters.py swingbot/core/market/strategy_types.py \
        swingbot/core/backtesting/backtest.py swingbot/core/market/signals.py \
        tests/market/test_symbol_horizon_overlay.py
git commit -m "feat(v98): per-symbol horizon overlay resolved at call time, tables untouched"
```

---

# Phase 2 — Q-INV: which horizons clear on real inverse-ETF data

**Q-INV — On real inverse-ETF data, which horizons clear the gate under current
arithmetic?** This is a new question nobody has asked, not a re-run of v93 or of
anything else in `backtest-methodology.md`'s closed table. It takes its own
pre-registered shot on TRAIN. VALIDATION is not spent under any outcome.

### Task D6: ETF friction model (expense ratio + rebalance drag)

The spec's own "What is genuinely new" section: the synthetic -1x series that
motivated this route models **no** expense ratio and **no** daily-rebalance drag,
and drag compounds with holding period — which is exactly what decides the horizon
restriction. Measuring with equity frictions would measure the wrong instrument.

`swingbot/core/edge/frictions.py` today has two globals — `SLIPPAGE_BPS` (5.0) and
a commission converted to R — and **no carry cost at all**. It needs a holding-period
term, applied to the inverse population only.

**Files:**
- Modify: `swingbot/core/edge/frictions.py`
- Test: `tests/edge/test_frictions_carry.py`

**Interfaces:**
- Produces: `CARRY_BPS_PER_YEAR: dict[str, float]`,
  `carry_cost_r(ticker, holding_days, risk_dollars, entry_price, shares) -> float`.
- Consumes: `market.populations.population_of` (D1).

- [ ] **Step 1: Source the two constants, and write them down**

Take each instrument's **published net expense ratio** from the ProShares fact
sheet (PSQ/SH/RWM/DOG are all 0.95% gross as of the last public filing — **verify
the current figure, do not trust this line**), and estimate the daily-rebalance
drag empirically from the fetched data in D7 as
`mean(inverse daily return + benchmark daily return)` annualised — the residual
after the -1x relationship is removed. Record both, with their source and date, in
the pre-registration (D8). A constant with no source is exactly what this plan's
`Edge: volume` budget is being spent to avoid.

- [ ] **Step 2: Write the failing test**

```python
# tests/edge/test_frictions_carry.py
from swingbot.core.edge import frictions


def test_equity_carries_nothing():
    assert frictions.carry_cost_r("AAPL", holding_days=180, risk_dollars=100.0,
                                  entry_price=100.0, shares=10) == 0.0


def test_carry_scales_with_holding_period():
    short = frictions.carry_cost_r("PSQ", 30, 100.0, 100.0, 10)
    long_ = frictions.carry_cost_r("PSQ", 270, 100.0, 100.0, 10)
    assert 0.0 < short < long_
    assert long_ == pytest.approx(short * 9, rel=0.02)  # linear in days


def test_carry_is_a_deduction_in_R_against_the_risk_basis():
    # 0.0095/yr on $1000 notional over 365 days = $9.50 = 0.095R at $100 risk
    r = frictions.carry_cost_r("PSQ", 365, 100.0, 100.0, 10)
    assert r == pytest.approx(0.095, rel=0.05)
```

- [ ] **Step 3: Run to verify it fails, then implement**

```python
#: Annual holding cost in bps for the v98 inverse basket: published net
#: expense ratio + measured daily-rebalance drag. Sourced and dated in
#: docs/superpowers/results/2026-09-21-v98-q-inv-preregistration.md. Equities
#: carry nothing -- a stock has no expense ratio and does not rebalance.
CARRY_BPS_PER_YEAR: dict[str, float] = {}   # filled in Step 1, per symbol


def carry_cost_r(ticker, holding_days, risk_dollars=None,
                 entry_price=None, shares=None) -> float:
    """Holding cost as an R deduction, linear in holding days.

    The clean backtest holds an inverse ETF for free. A real one pays an
    expense ratio daily and bleeds the daily-rebalance residual, and both
    compound with holding period -- which is exactly the axis v98's horizon
    restriction is decided on. Linear (not compounded) is the conservative
    simplification at these magnitudes and is stated as such in the
    pre-registration; it understates the cost by <2% at 270 days.
    """
```

Apply it in the backtest's R computation for the inverse population **only**, at
the same place `commission_r` is subtracted (`grep -n "commission_r"
swingbot/core/backtesting/backtest.py`). Gate the whole thing on
`population_of(ticker) == INVERSE` so equity arithmetic is byte-identical — this is
what makes the closed-book invariance check in D15 possible at all.

- [ ] **Step 4: Verify and commit**

```bash
python scripts/dev/testrun.py file tests/edge/test_frictions_carry.py
python scripts/dev/testrun.py file tests/backtesting/test_backtest_engine.py
git add swingbot/core/edge/frictions.py swingbot/core/backtesting/backtest.py \
        tests/edge/test_frictions_carry.py
git commit -m "feat(v98): ETF carry cost (expense ratio + rebalance drag) for the inverse basket"
```

### Task D7: Fetch real data for the four instruments

Real data, not synthetic. The spec's self-gating evidence came from a synthetic -1x
SPY series; every number in Phase 2 must come from the actual instruments' price
history, which is the whole point of Q-INV.

**Files:**
- Modify: `scripts/data/fetch_backtest_data.py` (only if the basket cannot be
  fetched without it — see Step 2)
- Creates (untracked): `market_data/daily/{PSQ,SH,RWM,DOG}.csv`

- [ ] **Step 1: Fetch**

```bash
python scripts/data/fetch_backtest_data.py --start 2018-06-01 --end 2025-12-31
```

`fetch_backtest_data.py:54` loads `data/watchlist.json` directly. The four symbols
are **not** on the watchlist yet and must not be added there in this task —
`watchlist.json` is the live scan universe and editing it here would start alerting
before Q-INV has run. Fetch them explicitly instead:

```bash
python -c "
import sys; sys.path.insert(0, '.')
from scripts.data.fetch_backtest_data import fetch_one   # check the real name first
for s in ('PSQ','SH','RWM','DOG'): fetch_one(s, '2018-06-01', '2025-12-31')
"
```

Read the script before running this — if it exposes no reusable per-symbol entry
point, add a `--symbols PSQ,SH,RWM,DOG` argument alongside the existing `--universe`
rather than bending the watchlist. That is the smaller change and it is the one a
later session will need again.

- [ ] **Step 2: Verify the data before trusting it**

```bash
python -c "
import pandas as pd
for s in ('PSQ','SH','RWM','DOG'):
    df = pd.read_csv(f'market_data/daily/{s}.csv', index_col=0, parse_dates=True)
    print(s, len(df), df.index.min().date(), df.index.max().date(),
          'nans:', int(df[['Open','High','Low','Close','Volume']].isna().sum().sum()))
"
```

Expect ~1900 rows each spanning 2018-06..2025-12 and **zero** NaNs in OHLCV.
Sanity-check the sign relationship — PSQ's daily returns should correlate roughly
−0.95 with QQQ's. A positive correlation means the wrong symbol was fetched, and
every downstream number would be measuring a long ETF. Check `MIN_BARS["9m"] = 390`
is comfortably satisfied so no horizon is starved of history.

- [ ] **Step 3: Record the drag constant**

With real data in hand, compute the daily-rebalance drag D6 Step 1 needs:

```bash
python -c "
import pandas as pd
bench = {'PSQ':'QQQ','SH':'SPY','RWM':'IWM','DOG':'DIA'}
for inv, b in bench.items():
    a = pd.read_csv(f'market_data/daily/{inv}.csv', index_col=0, parse_dates=True)['Close'].pct_change()
    c = pd.read_csv(f'market_data/daily/{b}.csv', index_col=0, parse_dates=True)['Close'].pct_change()
    j = pd.concat([a, c], axis=1).dropna()
    print(inv, 'drag bps/yr:', round(-(j.iloc[:,0] + j.iloc[:,1]).mean() * 252 * 10000, 1))
"
```

If a benchmark (IWM, DIA) is not cached, fetch it the same way as Step 1. Write the
four figures into `CARRY_BPS_PER_YEAR` (D6) and into the pre-registration (D8).

- [ ] **Step 4: Commit**

Only `scripts/data/fetch_backtest_data.py` and `frictions.py`'s filled constant are
tracked — `market_data/` is ignored.

```bash
git add scripts/data/fetch_backtest_data.py swingbot/core/edge/frictions.py
git commit -m "feat(v98): fetch the inverse basket and derive its rebalance drag"
```

### Task D8: Write and commit the Q-INV pre-registration

**This must be committed before Task D9 runs.** A selection rule written after
seeing the numbers is not a selection rule. The results document (D11) quotes this
one **verbatim**.

**Files:**
- Create: `docs/superpowers/results/2026-09-21-v98-q-inv-preregistration.md`

- [ ] **Step 1: Write it**

The document states, and nothing more:

- **Question.** Q-INV: on real inverse-ETF data, which horizons clear the gate
  under current arithmetic?
- **Window.** TRAIN `2020-01-01..2023-12-31` only. VALIDATION
  `2024-01-01..2025-12-31` is **not spent by this plan under any outcome.**
- **Arithmetic, frozen for the duration.** `--exit-model v2 --scale-out
  --tp2 levels --frictions on`, plus the D6 ETF carry cost. No parameter is
  touched between runs.
- **Instruments.** PSQ, SH, RWM, DOG. Measured **per instrument and pooled.**
- **The selection rule, stated once:**

  > A horizon subset clears only with **WR ≥ 50%**, **ExpR > 0**, **decided N ≥ 30**,
  > **scratch+timeout share ≤ 50%**, and **at least two anchored fold years with
  > N ≥ 15 and positive ExpR**. An instrument that fails alone does not ride in on
  > the basket's pooled number: the basket ships only if **every** instrument
  > clears on its own **and** the pooled figures clear. If nothing clears, the
  > component closes and **no instrument ships** — no threshold is loosened, and
  > **no second grid is run on the same question.**

- **Fold years.** Anchored, matching `backtest-methodology.md`'s existing shape
  (fold-train `2018-06..2020 / ..2021 / ..2022`, fold-test `2021 / 2022 / 2023`).
- **Constants and their sources.** The four `CARRY_BPS_PER_YEAR` figures with the
  published expense ratio, its filing date, and the measured drag from D7 Step 3.
  Note the linear (non-compounded) carry simplification explicitly.
- **What a PASS ships.** The clearing horizon subset written into
  `SYMBOL_HORIZON_OVERLAY`, behind `INVERSE_INSTRUMENTS_ENABLED` **default on**,
  with the three pre-merge preconditions of the spec's Evaluation contract.

- [ ] **Step 2: Commit before running anything**

```bash
git add docs/superpowers/results/2026-09-21-v98-q-inv-preregistration.md
git commit -m "docs(v98): pre-register Q-INV before any inverse-ETF run"
```

Confirm with `git log --oneline -1` that this commit exists before starting D9. If
D9 has already run, the shot is not pre-registered and cannot be made so
retroactively.

### Task D9: Run Q-INV on TRAIN, per instrument and pooled

**Dispatch to the `backtest-runner` subagent.** This is a four-instrument × 10-horizon
replay over a four-year window and will run tens of minutes; its per-symbol progress
must not enter the main context.

**Files:**
- Creates: `docs/superpowers/results/2026-09-21-v98-q-inv-train-{psq,sh,rwm,dog}.json`
- Creates: `docs/superpowers/results/2026-09-21-v98-q-inv-train-pooled.json`

- [ ] **Step 1: Dispatch**

```
Agent(subagent_type="backtest-runner", description="Q-INV TRAIN run", prompt="""
Run the v98 Q-INV TRAIN measurement. The pre-registration is
docs/superpowers/results/2026-09-21-v98-q-inv-preregistration.md -- read it
first and do not deviate from it in any respect.

Four instruments: PSQ, SH, RWM, DOG. Data is already cached in market_data/daily/.

Per instrument:
  python scripts/backtest/run_backtest_range.py --train \
    --universe <the single symbol> --exit-model v2 --scale-out \
    --tp2 levels --frictions on \
    --json docs/superpowers/results/2026-09-21-v98-q-inv-train-<sym>.json \
    --trades-jsonl <scratch>/qinv-<sym>.jsonl

Check run_backtest_range.py's --universe semantics first: it resolves a NAMED
universe file via marketdata/universe.py, not a bare symbol. If a single symbol
cannot be passed, write data/universe/v98_inverse.json with the four rows
(symbol/name/sector/etf, same shape as etfs.json) and filter per instrument from
the emitted trades instead of running four times.

Then pool the four trade sets and compute the same figures over the union.

Report, for each instrument AND for the pooled set, BROKEN DOWN BY HORIZON:
decided N, win rate, ExpR, and the scratch+timeout share. Report per-fold-year
N and ExpR for the anchored folds named in the pre-registration. Report the
numbers only -- do not apply the selection rule, do not recommend a subset, and
do not adjust any parameter. If a run fails, report the failure; do not retry
with different settings.

Print flushed per-instrument progress. If the run passes 15 minutes, the
progress must resolve to a percent figure in a log you delete on completion.
""")
```

- [ ] **Step 2: Record the raw output**

Commit the JSON results as they came out, before any interpretation:

```bash
git add docs/superpowers/results/2026-09-21-v98-q-inv-train-*.json
git commit -m "chore(v98): raw Q-INV TRAIN output, four instruments and pooled"
```

### Task D10: Anchored fold-year stability

The "at least two anchored fold years with N ≥ 15 and positive ExpR" clause. It is
its own task because it is the clause that has closed four of this repo's last six
pre-registrations (`backtest-methodology.md:139-145`) — a pooled TRAIN row clearing
while the folds do not is the normal outcome here, not the surprising one.

- [ ] **Step 1: Extract the per-fold table**

From D9's per-fold output, build one table per instrument and one pooled:

| Instrument | Horizon subset | Fold year | N | ExpR | Clears (N≥15 ∧ ExpR>0) |

- [ ] **Step 2: Apply the clause, and only this clause**

Count clearing fold years per (instrument, horizon subset). Fewer than two is a
FAIL for that cell, whatever its pooled TRAIN numbers say. Do not re-run anything,
do not widen the fold definition, do not pool folds to reach N≥15.

- [ ] **Step 3: Record**

Append the table to the results document D11 creates. No commit of its own; D11
commits both.

### Task D11: Q-INV verdict — the decision point

**This task decides whether Phase 3 exists.** Apply the pre-registered rule to D9's
and D10's numbers exactly as written, then stop and record.

**Files:**
- Create: `docs/superpowers/results/2026-09-21-v98-q-inv-train.md`
- Modify: `docs/claude/backtest-methodology.md` (add one row to the closed table)

- [ ] **Step 1: Quote the selection rule verbatim**

Copy the rule block from D8 into the results document **as a blockquote, unedited**,
above any number. A reader must be able to check the verdict against the rule
without opening a second file.

- [ ] **Step 2: Apply it, per instrument first**

For each of PSQ, SH, RWM, DOG and each horizon subset: WR ≥ 50, ExpR > 0,
decided N ≥ 30, scratch+timeout ≤ 50%, ≥2 clearing fold years. Then the pooled set.
**An instrument that fails alone does not ride in on the pooled number** — if any
one of the four fails, the basket fails. The per-instrument table goes in the
document whether it clears or not.

- [ ] **Step 3: Write the verdict, in one of exactly two forms**

**PASS** — name the horizon subset, per instrument, and state that Phase 3 proceeds
under the spec's three pre-merge preconditions.

**FAIL** — state it plainly and stop. Then:
- `SYMBOL_HORIZON_OVERLAY` stays `{}`, no config flag is added, no symbol reaches
  `watchlist.json`, Tasks D12–D17 are **not executed**.
- Phase 1's isolation work stays merged: it is correct on its own terms, costs
  nothing with no inverse symbols present, and is what makes a future attempt
  cheap. Phase 4 (D18) still runs over it.
- The plan closes to `docs/superpowers/plans/no-lift/`
  (`docs/claude/document-lifecycle.md`), and the `Bump:` header is amended to
  `none` in the closing commit with one clause saying why — a negative result
  ships no code.
- **No threshold is loosened and no second grid is run on the same question.** A
  different instrument set, a different exit model or a compounded carry model is
  each a **new** hypothesis needing a new pre-registration.

- [ ] **Step 4: Add the row to the closed-pre-registration table**

In `docs/claude/backtest-methodology.md`, after the v93 row (line 150), matching the
existing column shape:

```markdown
| Q-INV inverse-instrument horizons (v98) | <PASS: horizon subset per instrument, N/WR/ExpR> \| <FAIL: what failed, per instrument> — **TRAIN + folds only, no VALIDATION spent.** Reopening needs a genuinely new mechanism, not a looser threshold | `results/2026-09-21-v98-q-inv-train.md`, `results/2026-09-21-v98-q-inv-preregistration.md` |
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/2026-09-21-v98-q-inv-train.md docs/claude/backtest-methodology.md
git commit -m "docs(v98): Q-INV TRAIN verdict and closed-pre-registration row"
```

---

