# Relative Strength Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.7.0 · bot 1.1.4
Bump: bot minor

**Goal:** Promote relative strength from an advisory score component to a
symmetric hard gate, scaled per horizon, exempting non-equities, and activate
the dormant sector-RS path.

**Architecture:** RS computation already exists in `edge/factors.py` and is
untouched. This plan adds an asset-class classifier, per-horizon RS windows, a
sector-ETF fetch, and a pre-scenario gate consuming `rs_score()`.

**Tech Stack:** Python 3.11+, pandas/numpy, yfinance, pytest. No new deps.

## Global Constraints

- **The RS math is not modified.** `relative_return`/`rs_percentile` stay as-is;
  this plan changes what their output is *allowed to do*.
- **Benchmark stays SPY.** Per-asset-class benchmarks are out of scope.
- **Non-equities are never blocked** by this gate.
- **Ships default-OFF** behind `RS_GATE`; flips ON only on VALIDATION.
- **Alert-volume loss ≤ ~30%.**
- **DEPENDS ON v32.** RS's scoring contribution lives in the merged registry.

## v32 landed, but not as this plan assumed

`docs/superpowers/plans/implemented/2026-08-16-v32-unified-confidence-score.md`
merged to `main` on 2026-08-17. The registry itself is real, live code, but
`UNIFIED_CONFIDENCE` stays default-off: v32's own TRAIN measurement could
not even MEASURE RS (needs a historical per-date cross-sectional universe
reconstruction this repo's cache doesn't retain -- same limitation this
plan will need to solve, not something v32 solved for it), so RS was
dropped from `FACTORS` for lack of evidence, not because it was tested and
failed. v32's one-shot VALIDATION run then FAILed regardless (the
near-empty factor pool scored slightly worse than the legacy scorer).
There is no live "merged registry" gating anything in production today,
and no established weight for RS to inherit. Full result:
`docs/superpowers/plans/implemented/v32-train-preregistration.md`.

## v33 also landed with its gate OFF — so "the v33 baseline" means ungated

Added by v33's close-out (2026-08-18), because Step 5 of this plan's Phase 4
tells you to pre-register *"PASS: win rate improves vs. the v33 baseline"*,
and that phrase was written when v33's adjacent-horizon gate was expected to
be live by now. **It is not.**
`docs/superpowers/plans/implemented/2026-08-16-v33-mtf-trend-alignment.md`
completed all 8 tasks, but its one-shot VALIDATION run FAILed: the gate
*lowered* aggregate win rate (47.98% vs. 48.50% ungated, −0.51pp, overlapping
Wilson intervals) while cutting 6.63% of entries, so `MTF_ADJACENT_GATE`
stays `default="false"`. Numbers:
`docs/superpowers/plans/implemented/v33-train-preregistration.md`.

Consequences for this plan, none of which change its task structure:

- **"The v33 baseline" is the ungated population**, i.e. the same baseline
  v33 measured against. Do not write a pre-registration that compares RS
  against a bot running the adjacent gate; nothing runs it.
- **The comparator to state explicitly** is RS-gate-off vs. RS-gate-on on one
  population in the VALIDATION window, exactly as v33 phrased its own Primary
  — not a cross-plan comparison against v33's or v32's numbers.
- **Two consecutive one-shot gates have now FAILed** (v32's merged score,
  v33's adjacent gate), both with overlapping intervals in TRAIN that then
  reversed sign in VALIDATION. Budget for that outcome here rather than
  treating a PASS as the default path, and prefer a TRAIN effect that is
  *Wilson-separated* before spending the VALIDATION shot.
- v33 did leave usable infrastructure: `swingbot/core/market/mtf.py`'s
  tri-state (`aligned` / `opposed` / `exempt`) verdict shape is the pattern
  this plan's "unknown" representability work (Phase 1) should match, and
  `scripts/backtest/measure_adjacent_gate_effect.py` is a worked example of
  measuring a pre-scoring filter that the replay harness cannot see.

## The 50.0 sentinel — read before writing any gate code

`rs_percentile()` (`edge/factors.py:29-38`) returns **`50.0`**, not `None`, when
it cannot compute:

```python
if rel is None or not universe_rels:
    return 50.0
```

`sector_rs_percentile()` does the same (`:66`). So **"unknown" is
indistinguishable from "exactly median"** at the value level.

This is fatal for a symmetric gate: with thresholds around the median, every
ticker whose RS could not be computed lands in the ambiguous middle and is
silently treated as a real, measured, mediocre reading.

`ScanItem.rs_percentile` (`engine.py:174`) is documented as
"`None` when the RS benchmark fetch fails (Task E25)" — so a `None` path does
exist upstream. **Task 1 establishes which of the two representations actually
reaches the gate**, and the gate must distinguish unknown from median before it
blocks anything.

## File Structure

| File | Responsibility |
|---|---|
| `swingbot/core/marketdata/asset_class.py` | **NEW.** `classify(symbol) -> str`, `is_rs_eligible(symbol) -> bool`. |
| `swingbot/core/edge/rs_gate.py` | **NEW.** `rs_verdict(...) -> dict` — the tri-state gate decision. |
| `swingbot/core/market/strategy_types.py` | `rs_window` key per horizon. |
| `swingbot/core/scanning/engine.py` | Applies the gate; sector-ETF fetch; funnel counter. |
| `swingbot/config.py` | `RS_GATE`, `RS_LEADER_PERCENTILE`, `RS_LAGGARD_PERCENTILE`. |
| `tests/marketdata/test_asset_class.py`, `tests/edge/test_rs_gate.py` | **NEW.** |

---

# Phase 1 — Make "unknown" representable

### Task 1: Trace the RS value path and pin down the unknown representation

**Files:**
- Create: `docs/superpowers/plans/v34-rs-value-path.md`

**Interfaces:**
- Produces: the documented contract for what reaches the gate. No production code.

- [ ] **Step 1: Trace every hop**

`refresh_rs_cache` (`engine.py:1101`) → `ScanItem.rs_percentile`
(`engine.py:174`) → `_build_quality_inputs` (`:510`) → `score_plan`. Record at
each hop whether the value can be `None`, and where `50.0` is substituted.

Run: `git grep -n "rs_percentile" -- 'swingbot/**/*.py'`

- [ ] **Step 2: Write a characterization test capturing today's behavior**

```python
# tests/edge/test_rs_value_path.py
def test_rs_percentile_returns_fifty_not_none_on_empty_universe():
    """Characterization: documents the sentinel this plan must work around.
    If this ever returns None, the gate's unknown-handling can be simplified."""
    from swingbot.core.edge.factors import rs_percentile
    assert rs_percentile(_frame_120(), _frame_120(), universe_rels=[]) == 50.0


def test_rs_percentile_returns_fifty_on_short_history():
    from swingbot.core.edge.factors import rs_percentile
    assert rs_percentile(_frame_3(), _frame_120(), universe_rels=[0.1]) == 50.0
```

- [ ] **Step 3: Decide the unknown representation**

Recommended: introduce `RS_UNKNOWN = None` at the **gate boundary** and have the
gate accept an explicit `rs_available: bool`, rather than changing
`rs_percentile`'s return type — several callers rely on a float and changing it
is a wider blast radius than this plan needs.

Record the decision and the reason.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/v34-rs-value-path.md tests/edge/test_rs_value_path.py
git commit -m "docs(v34): pin down the RS unknown-vs-median representation"
```

---

### Task 2: Asset-class classification

**Files:**
- Create: `swingbot/core/marketdata/asset_class.py`
- Test: `tests/marketdata/test_asset_class.py`

**Interfaces:**
- Produces: `classify(symbol) -> str` (`"equity"|"etf"|"fx"|"future"|"index"`),
  `is_rs_eligible(symbol) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/marketdata/test_asset_class.py
import pytest
from swingbot.core.marketdata.asset_class import classify, is_rs_eligible


@pytest.mark.parametrize("symbol,expected", [
    ("AAPL", "equity"), ("NVDA", "equity"),
    ("EURUSD=X", "fx"), ("JPY=X", "fx"),
    ("GC=F", "future"), ("CL=F", "future"),
    ("^GSPC", "index"), ("^VIX", "index"),
])
def test_classify_by_resolved_symbol_shape(symbol, expected):
    assert classify(symbol) == expected


def test_etfs_classify_as_etf_via_the_universe_table():
    assert classify("SPY") == "etf"
    assert classify("XLK") == "etf"


@pytest.mark.parametrize("symbol", ["EURUSD=X", "GC=F", "^GSPC"])
def test_non_equities_are_not_rs_eligible(symbol):
    """RS-vs-SPY is meaningless for FX, futures and indices. They are exempt
    from the gate -- they pass, and the exemption is logged as such."""
    assert is_rs_eligible(symbol) is False


@pytest.mark.parametrize("symbol", ["AAPL", "SPY"])
def test_equities_and_etfs_are_rs_eligible(symbol):
    assert is_rs_eligible(symbol) is True


def test_classification_uses_the_resolved_symbol_not_the_alias():
    """XAUUSD resolves to GC=F. The gate must classify what was actually
    fetched, not the alias the user typed.

    ticker_utils exposes candidate_symbols(ticker) -> list[str] (there is no
    resolve_ticker); the first candidate is the preferred resolution.
    """
    from swingbot.core.marketdata.ticker_utils import candidate_symbols
    assert classify(candidate_symbols("XAUUSD")[0]) == "future"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_asset_class.py`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# swingbot/core/marketdata/asset_class.py
"""Asset-class classification for RS eligibility (v34).

Relative strength versus SPY is only meaningful for things that are, loosely,
equity risk. FX, futures and indices are exempt from the RS gate -- an
exemption that is logged distinctly from a pass, so a scan never reports a
gold future as having 'passed' a comparison that was never run.

Classification is by RESOLVED Yahoo symbol shape, because that is what was
actually fetched: XAUUSD resolves to GC=F, and GC=F is what must be judged.
"""
from __future__ import annotations

_OVERRIDES: dict[str, str] = {
    # Symbols the suffix heuristic gets wrong. Keep small and justified.
}

_RS_ELIGIBLE = {"equity", "etf"}


def classify(symbol: str) -> str:
    if not symbol:
        return "equity"
    sym = symbol.strip().upper()
    if sym in _OVERRIDES:
        return _OVERRIDES[sym]
    if sym.startswith("^"):
        return "index"
    if sym.endswith("=X"):
        return "fx"
    if sym.endswith("=F"):
        return "future"
    from swingbot.core.marketdata.universe import is_etf
    return "etf" if is_etf(sym) else "equity"


def is_rs_eligible(symbol: str) -> bool:
    """False means exempt from the RS gate -- never 'failed' it."""
    return classify(symbol) in _RS_ELIGIBLE
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_asset_class.py`
Expected: PASS

If `candidate_symbols("XAUUSD")[0]` is not `"GC=F"`, read the alias table in
`ticker_utils.py` and assert against whatever it genuinely resolves to — do not
change `classify` to satisfy a wrong expectation.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/marketdata/asset_class.py tests/marketdata/test_asset_class.py
git commit -m "feat(v34): asset-class classification for RS eligibility"
```

---

# Phase 2 — Per-horizon windows and the gate

### Task 3: Per-horizon RS windows

**Files:**
- Modify: `swingbot/core/market/strategy_types.py` (all 10 `HORIZONS` entries)
- Test: `tests/market/test_horizons.py`

**Interfaces:**
- Produces: `HORIZONS[key]["rs_window"]` for all ten horizons.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_horizons.py
import pytest
from swingbot.core.market.strategy_types import HORIZONS


def test_every_horizon_defines_an_rs_window():
    for key, settings in HORIZONS.items():
        assert "rs_window" in settings, f"{key} is missing rs_window"


def test_rs_windows_increase_with_horizon_length():
    """A 2w setup asks 'strong lately?'; a 9m setup asks 'strong for months?'.
    A laggard-over-6-months says little about a two-week swing."""
    windows = [HORIZONS[k]["rs_window"] for k in HORIZONS]
    assert windows == sorted(windows)


def test_shortest_and_longest_windows_are_sane():
    assert HORIZONS["2w"]["rs_window"] == 21      # ~1 trading month
    assert HORIZONS["9m"]["rs_window"] == 189     # ~9 trading months
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_horizons.py`
Expected: FAIL — `2w is missing rs_window`

- [ ] **Step 3: Add `rs_window` to each horizon**

Roughly one horizon-length of trading days, floored at ~21:

```python
# swingbot/core/market/strategy_types.py -- one line per HORIZONS entry
"2w": {..., "rs_window": 21},    # ~1 trading month
"4w": {..., "rs_window": 21},
"2m": {..., "rs_window": 42},
"3m": {..., "rs_window": 63},
"4m": {..., "rs_window": 84},
"5m": {..., "rs_window": 105},
"6m": {..., "rs_window": 126},
"7m": {..., "rs_window": 147},
"8m": {..., "rs_window": 168},
"9m": {..., "rs_window": 189},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_horizons.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/strategy_types.py tests/market/test_horizons.py
git commit -m "feat(v34): per-horizon RS lookback windows"
```

---

### Task 4: The symmetric gate with a tri-state verdict

**Files:**
- Create: `swingbot/core/edge/rs_gate.py`
- Modify: `swingbot/config.py`
- Test: `tests/edge/test_rs_gate.py`

**Interfaces:**
- Consumes: `is_rs_eligible` (Task 2).
- Produces: `rs_verdict(symbol, direction, rs_value, rs_available) -> dict`
  returning `{"status": "pass"|"block"|"exempt", "reason": str}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/edge/test_rs_gate.py
import pytest
from swingbot import config
from swingbot.core.edge.rs_gate import rs_verdict


@pytest.fixture(autouse=True)
def _thresholds(monkeypatch):
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 60.0)
    monkeypatch.setattr(config, "RS_LAGGARD_PERCENTILE", 40.0)


def test_bullish_leader_passes():
    assert rs_verdict("AAPL", "bullish", 75.0, True)["status"] == "pass"


def test_bullish_laggard_blocked():
    assert rs_verdict("AAPL", "bullish", 25.0, True)["status"] == "block"


def test_bearish_laggard_passes():
    """Symmetric: shorting a weak name is the mirror of buying a strong one."""
    assert rs_verdict("AAPL", "bearish", 25.0, True)["status"] == "pass"


def test_bearish_leader_blocked():
    """Shorting a market leader is exactly as bad as buying a laggard."""
    assert rs_verdict("AAPL", "bearish", 75.0, True)["status"] == "block"


def test_middle_band_blocks_neither_direction():
    assert rs_verdict("AAPL", "bullish", 50.0, True)["status"] == "block"
    assert rs_verdict("AAPL", "bearish", 50.0, True)["status"] == "block"


def test_unknown_rs_is_exempt_not_blocked():
    """THE critical case. rs_percentile returns 50.0 when it cannot compute,
    which is indistinguishable from a real median reading. If unknown were
    treated as a value, every ticker with a failed RS fetch would be silently
    blocked in both directions by the middle-band rule above."""
    v = rs_verdict("AAPL", "bullish", 50.0, False)
    assert v["status"] == "exempt"
    assert "unavailable" in v["reason"]


@pytest.mark.parametrize("symbol", ["EURUSD=X", "GC=F", "^GSPC"])
def test_non_equities_exempt_regardless_of_value(symbol):
    v = rs_verdict(symbol, "bullish", 5.0, True)
    assert v["status"] == "exempt"


def test_exempt_reason_names_the_asset_class():
    assert "future" in rs_verdict("GC=F", "bullish", 5.0, True)["reason"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/edge/test_rs_gate.py`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Add the config fields**

```python
# swingbot/config.py, "Trade Filters & Risk"
    Field("RS_GATE", "RS_GATE", "Trade Filters & Risk", "Relative strength gate",
          type="checkbox", default="false",
          help="Require bullish setups on relative leaders and bearish setups on "
               "relative laggards, versus SPY. FX, futures and indices are exempt. "
               "Enable only after VALIDATION."),
    Field("RS_LEADER_PERCENTILE", "RS_LEADER_PERCENTILE", "Trade Filters & Risk",
          "RS leader percentile", type="float", default="60", min=50, max=100, step=5,
          help="Bullish setups need combined RS at or above this percentile."),
    Field("RS_LAGGARD_PERCENTILE", "RS_LAGGARD_PERCENTILE", "Trade Filters & Risk",
          "RS laggard percentile", type="float", default="40", min=0, max=50, step=5,
          help="Bearish setups need combined RS at or below this percentile."),
```

- [ ] **Step 4: Write minimal implementation**

```python
# swingbot/core/edge/rs_gate.py
"""Symmetric relative-strength gate (v34).

Tri-state on purpose. 'exempt' is NOT 'pass': an FX pair and a stock whose RS
fetch failed both skip the check, and conflating either with a real pass would
report a comparison that never ran.

The rs_available flag exists because rs_percentile() returns 50.0 -- not None --
when it cannot compute (edge/factors.py:33-37). Without the flag, a failed
fetch is indistinguishable from a genuine median reading, and the middle band
would block it in both directions.
"""
from __future__ import annotations

from swingbot import config
from swingbot.core.marketdata.asset_class import classify, is_rs_eligible


def rs_verdict(symbol: str, direction: str, rs_value: float,
               rs_available: bool) -> dict:
    if not is_rs_eligible(symbol):
        return {"status": "exempt",
                "reason": f"{classify(symbol)} is exempt from RS-vs-SPY"}
    if not rs_available:
        return {"status": "exempt", "reason": "RS unavailable for this ticker"}

    if direction == "bullish":
        if rs_value >= config.RS_LEADER_PERCENTILE:
            return {"status": "pass",
                    "reason": f"RS {rs_value:.0f} is a relative leader"}
        return {"status": "block",
                "reason": f"RS {rs_value:.0f} below the "
                          f"{config.RS_LEADER_PERCENTILE:.0f} leader threshold"}

    if rs_value <= config.RS_LAGGARD_PERCENTILE:
        return {"status": "pass",
                "reason": f"RS {rs_value:.0f} is a relative laggard"}
    return {"status": "block",
            "reason": f"RS {rs_value:.0f} above the "
                      f"{config.RS_LAGGARD_PERCENTILE:.0f} laggard threshold"}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/edge/test_rs_gate.py`
Expected: PASS (10 tests)

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/edge/rs_gate.py swingbot/config.py tests/edge/test_rs_gate.py
git commit -m "feat(v34): symmetric RS gate with explicit unknown handling"
```

---

# Phase 3 — Sector RS and wiring

### Task 5: Fetch sector ETFs and activate `rs_score`

**Files:**
- Modify: `swingbot/core/scanning/engine.py` (crawl phase, near `:1068-1101`)
- Test: `tests/scanning/test_sector_rs.py`

**Interfaces:**
- Consumes: `sector_rs_percentile`, `rs_score` (`edge/factors.py:53,70` — both
  currently have **zero callers**), `universe.sector_map`.
- Produces: `ScanItem.sector_rs_percentile`, `ScanItem.rs_combined`.

- [ ] **Step 1: Write the failing test**

```python
# tests/scanning/test_sector_rs.py
def test_sector_etfs_are_fetched_for_watchlist_sectors(monkeypatch):
    fetched = []
    monkeypatch.setattr("swingbot.core.scanning.engine._fetch_frames",
                        lambda syms: fetched.extend(syms) or {})
    _crawl_with_watchlist(["AAPL", "JPM"])   # tech + financials
    assert "XLK" in fetched
    assert "XLF" in fetched


def test_rs_combined_weights_ticker_seventy_sector_thirty():
    from swingbot.core.edge.factors import rs_score
    assert rs_score(80.0, 40.0) == pytest.approx(68.0)


def test_unknown_sector_falls_back_to_ticker_only_rs():
    """sector_map is static; a reclassified ticker must not get a wrong
    benchmark -- it falls back and the fallback is logged."""
    item = _scan_item_for("SOMENEWTICKER", sector=None)
    assert item.rs_combined == item.rs_percentile


def test_missing_sector_etf_frame_falls_back_not_blocks():
    item = _scan_item_for("AAPL", sector="Technology", sector_frames={})
    assert item.rs_combined == item.rs_percentile
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_sector_rs.py`
Expected: FAIL — sector ETFs are not fetched

- [ ] **Step 3: Fetch the sector ETFs during the crawl**

Collect the distinct sectors of the watchlist via `universe.sector_map`, map to
their ETFs, and fetch those frames alongside SPY in the existing crawl. Cache
them beside the RS cache — they change once a day.

Confirm the real fetch helper's name first:
`git grep -n "def _crawl_latest_data" -A 20 swingbot/core/scanning/engine.py`

- [ ] **Step 4: Compute and store combined RS per item**

```python
# swingbot/core/scanning/engine.py, in the crawl/item-build phase
sector = sector_of.get(item.ticker)
sector_pctile = None
if sector and sector_etf_frames:
    sector_pctile = sector_rs_percentile(sector, sector_etf_frames, spy_df)
item.sector_rs_percentile = sector_pctile
item.rs_combined = (
    rs_score(item.rs_percentile, sector_pctile)
    if sector_pctile is not None and item.rs_percentile is not None
    else item.rs_percentile
)
```

Add both fields to the `ScanItem` dataclass beside `rs_percentile`
(`engine.py:174`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_sector_rs.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/engine.py tests/scanning/test_sector_rs.py
git commit -m "feat(v34): activate sector RS -- rs_score wired for the first time"
```

---

### Task 6: Apply the gate in the scan loop

**Files:**
- Modify: `swingbot/core/scanning/engine.py`
- Test: `tests/scanning/test_rs_gate_wiring.py`

**Interfaces:**
- Consumes: `rs_verdict` (Task 4), `rs_combined` (Task 5).
- Produces: `rs_blocked` funnel counter.

- [ ] **Step 1: Write the failing test**

```python
# tests/scanning/test_rs_gate_wiring.py
def test_gate_off_by_default(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", False)
    assert len(_scan_with(ticker="AAPL", direction="bullish", rs=10.0)) == 1


def test_gate_on_blocks_a_bullish_laggard(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", True)
    assert _scan_with(ticker="AAPL", direction="bullish", rs=10.0) == []


def test_gate_on_never_blocks_an_exempt_symbol(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", True)
    assert len(_scan_with(ticker="GC=F", direction="bullish", rs=10.0)) == 1


def test_gate_uses_combined_rs_not_bare_ticker_rs(monkeypatch):
    """rs_combined is 0.7*ticker + 0.3*sector. A ticker at 65 in a sector at
    20 combines to 51.5 and must be blocked at a 60 leader threshold."""
    monkeypatch.setattr(config, "RS_GATE", True)
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 60.0)
    assert _scan_with(ticker="AAPL", direction="bullish",
                      rs=65.0, sector_rs=20.0) == []


def test_blocked_scenarios_increment_the_funnel_counter(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", True)
    _items, funnel = _scan_with_funnel(ticker="AAPL", direction="bullish", rs=10.0)
    assert funnel["rs_blocked"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_rs_gate_wiring.py`
Expected: FAIL — laggard scenarios are not dropped

- [ ] **Step 3: Apply the gate before confidence scoring**

```python
# swingbot/core/scanning/engine.py, with the other pre-scenario gates
if config.RS_GATE:
    verdict = rs_verdict(
        item.ticker, scenario.direction,
        item.rs_combined if item.rs_combined is not None else 50.0,
        rs_available=item.rs_combined is not None,
    )
    if verdict["status"] == "block":
        log.debug("%s %s dropped by RS gate: %s", item.ticker,
                  scenario.direction, verdict["reason"])
        rs_blocked += 1
        continue
```

Add `rs_blocked` to the funnel dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_rs_gate_wiring.py`
Expected: PASS

- [ ] **Step 5: Run the fast tier**

Run: `python scripts/dev/testrun.py fast`
Expected: `0 failed`, `0 xfailed`

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/engine.py tests/scanning/test_rs_gate_wiring.py
git commit -m "feat(v34): apply the RS gate in the scan loop behind RS_GATE"
```

---

# Phase 4 — Measure and ship

### Task 7: TRAIN sweep — thresholds, direction split, sector marginal value

**Files:**
- Create: `docs/superpowers/plans/v34-train-preregistration.md`
- Modify: `swingbot/config.py` (threshold defaults)

- [ ] **Step 1: Sweep the two thresholds on TRAIN**

Dispatch via `backtest-runner`. Grid `RS_LEADER_PERCENTILE` ∈ {55,60,65,70,75}
× `RS_LAGGARD_PERCENTILE` ∈ {25,30,35,40,45}. Chunk per-strategy per CLAUDE.md.

- [ ] **Step 2: Report bullish and bearish separately**

Symmetry is a hypothesis, not a fact. If bearish scenarios show no RS effect,
the honest outcome is a bullish-only gate — record that rather than shipping a
symmetric one because it is tidier.

- [ ] **Step 3: Measure sector RS's marginal contribution**

Compare gate performance using `rs_percentile` alone vs. `rs_combined`. **If
sector RS adds nothing measurable, revert Task 5's wiring** and leave
`sector_rs_percentile`/`rs_score` dormant. Shipping unused wiring is the exact
pattern this whole spec family exists to fix.

- [ ] **Step 4: Confirm the TRAIN window spans a regime change**

RS gates are procyclical — most confident right before a leadership rotation. A
TRAIN window with no rotation will overstate the gate. Verify against
`docs/claude/backtest-methodology.md`'s window definitions and state it.

- [ ] **Step 5: Write the pre-registration**

```markdown
## v34 VALIDATION pre-registration
- Primary: win rate at MIN_ALERT_CONFIDENCE_LEVEL=4 with RS_GATE=on.
- Thresholds: leader=<X>, laggard=<Y> (frozen from TRAIN Step 1).
- Scope: <symmetric | bullish-only>, per Step 2.
- Sector RS: <included | reverted>, per Step 3.
- PASS: win rate improves vs. the v33 baseline AND alert volume falls by no
  more than 30%.
- One shot. FAIL means RS_GATE stays default-off.
```

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/v34-train-preregistration.md swingbot/config.py data/v34_train.json
git commit -m "feat(v34): TRAIN threshold sweep and pre-registration"
```

---

### Task 8: VALIDATION, docs, version bump

**Files:**
- Modify: `swingbot/config.py`, `docs/strategy.md`, `VERSION.json`

- [x] **Step 1: Confirm the pre-registration is committed and unedited**

Committed at `5fec126`, the only commit touching it, clean working tree.

- [x] **Step 2: Run VALIDATION once**

~~`python scripts/backtest/run_backtest_range.py --validation --json data/v34_validation.json`~~
**This command was wrong and was NOT run.** `run_backtest_range.py` drives
`swingbot.core.backtesting.backtest`, a replay harness that never calls
`swingbot/core/scanning/engine.py`, so the gate cannot influence its output by
any code path — the same "unmeasurable by construction" trap that burned
`DATA_DRIVEN_STOPS_ENABLED`'s shot. Superseded by the pre-registration, which
names the purpose-built instrument instead:

```
python scripts/backtest/measure_rs_gate_effect.py --validation \
    --cache-dir <main checkout>/data/backtest_cache \
    --json data/v34_validation.json --rows-out data/v34_validation_rows.json
```

- [x] **Step 3: Record the result verbatim. Do not re-run on FAIL.**

**PASS**, recorded in full in the pre-registration's appended result section.
Run once, no re-run.

- [x] **Step 4: On PASS, flip `RS_GATE` to `default="true"`** — done, in
`swingbot/config.py` and `.env.example` together.

- [x] **Step 5: Document in `docs/strategy.md`**

~~Cover the symmetric rule, per-horizon windows~~ — both stale by the time this
step ran. What was documented is what shipped: the **bearish-only** rule (the
bullish arm measured negative and is disabled via `RS_LEADER_PERCENTILE=0`),
the per-horizon windows as a **known gap** rather than a working feature (Task
3's key has zero consumers), the non-equity exemption, and that exemptions are
not passes.

- [x] **Step 6: Run the full suite**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`

- [x] **Step 7: Bump `VERSION.json`, close the spec**

`bot` 1.2.2 → **1.3.0** (minor: RS stops being advisory and starts removing
alerts on the default configuration), then regenerate
`swingbot/admin/version_history.json`. `ui` unchanged. The pre-registration and
the Task 1 tracing note move to `implemented/` alongside the plan and spec, and
every reference to their old paths is re-pointed in the same commit.

---

## Parallelisation

- **Group A (parallel):** Task 1 (tracing doc + characterization test), Task 2
  (`asset_class.py`), Task 3 (`strategy_types.py`) — three disjoint files, no
  contract dependency between them.
- **Sequential: Task 4 after Tasks 1–2.** It consumes `is_rs_eligible` and Task
  1's unknown-representation decision.
- **Sequential: Task 5 after Task 3** (both touch `engine.py`; and Task 5's
  windows come from Task 3).
- **Sequential: Task 6 after Tasks 4–5.** Consumes both.
- **Sequential: Task 7 → Task 8.**
- **Note:** Tasks 5 and 6 both edit `engine.py`. One agent, sequentially — two
  agents overwrite rather than merge in this shared working tree.

## Progress

- [x] Task 1 — Trace the RS value path (`plans/implemented/v34-rs-value-path.md`)
- [x] Task 2 — Asset-class classification
- [x] Task 3 — Per-horizon RS windows — **shipped dormant.** `HORIZONS[hk]["rs_window"]`
      is defined for all ten horizons and has **zero consumers**; the scan runs
      the flat `RS_WINDOW = 63` for every horizon. Measured anyway in Task 7 and
      it was *worse* than the flat window, so it was never wired in. Documented
      as a known gap in `docs/strategy.md`, not as a feature.
- [x] Task 4 — Gate + tri-state verdict — **shipped asymmetric, not symmetric.**
      `RS_LEADER_PERCENTILE=0` disables the bullish arm, which measured negative
      at every TRAIN threshold.
- [x] Task 5 — Sector ETFs + `rs_score` activation — kept, not reverted:
      `rs_combined` beat ticker-only RS on TRAIN *and* on VALIDATION.
- [x] Task 6 — Apply the gate in the scan loop
- [x] Task 7 — TRAIN sweep + pre-registration (`plans/implemented/v34-train-preregistration.md`)
- [x] Task 8 — VALIDATION **PASS**, docs, bump. 48.50% → 49.66% (+1.17pp) for a
      4.07% alert-volume cut, overlapping intervals. `RS_GATE` ships
      `default="true"`; `bot` 1.2.2 → 1.3.0.

**Read the pre-registration's appended result section before citing any number
from this plan's body** — the plan was written expecting a symmetric gate, and
that is not what the measurement allowed to ship.
