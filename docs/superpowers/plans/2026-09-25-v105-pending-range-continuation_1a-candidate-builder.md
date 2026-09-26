# v105 PENDING daily range continuation — Part 1a: contract, candidate, builder (Tasks 1–3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Header, global constraints, review focus and parallelisation live in
`2026-09-25-v105-pending-range-continuation_0-index.md`. Read them first.
Every task below implicitly includes those constraints.

**File map for this part**

| File | Task | Responsibility |
|---|---|---|
| `docs/superpowers/results/2026-09-25-v105-asof-contract.md` | 1 | frozen dependency and as-of contract |
| `swingbot/core/market/range_candidate.py` | 2 | pure geometry, trend, pivot, pressure, proximity, rearm |
| `tests/market/range_fixtures.py` | 2 | shared synthetic LONG/SHORT frames |
| `swingbot/core/planning/range_builder.py` | 3 | candidate → trigger/stop/TP → `TradePlanV2` |
| `swingbot/core/planning/range_source.py` | 3 | the single live+replay entry point (`range_plan_at`, `screen`, `first_issuable`) |
| `swingbot/core/tracking/ledger.py` | 3 | range source books to the weak ledger while WEAK |
| `swingbot/core/backtesting/range_replay.py` | 4 | daily replay rows, entry-bar diagnostics |
| `swingbot/core/scanning/range_pass.py` | 5 | masked watchlist pass, sector grouping, fresh quote |
| `swingbot/core/scanning/range_embeds.py` | 5 | research alert embed |
| `swingbot/core/scanning/scan_run.py` | 5 | `_maybe_run_range_pass` after the strategy pass |
| `swingbot/core/planning/plan_manager.py` | 5 | `RANGE_PENDING` feed transition |
| `swingbot/core/presentation/instructions.py` | 5 | PLACE instruction; risk-cap divergence for range plans |
| `swingbot/config.py`, `.env.example` | 5 | `RANGE_ALERTS_MODE`, `RANGE_ALERTS_CELL`, `RANGE_ALERTS_LIVE_DIRECTIONS` |

# Phase 1 — Candidate and PENDING lifecycle

### Task 1: Reconcile dependencies and freeze the as-of contract

**Files:**
- Create: `docs/superpowers/results/2026-09-25-v105-asof-contract.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the frozen constants that Tasks 6, 8 and 9 read verbatim (TRAIN
  window, fold years, cache directory and manifest hash, code commit,
  selection rule, holdout eligibility rule).

- [ ] **Step 1: Re-verify the plan-time facts against current code**

Run each command. Every expected result below was true at HEAD 46872d3b. If
one differs, v100/v104 has landed: stop, and follow the index's Global
constraints (inspect the new code, freeze one baseline under the new model).

```bash
git worktree list
git log --oneline -5
git grep -n "class ArmEngine\|def run_arm" -- swingbot        # expect: no output
git grep -n "dollar_risk\|def structural_stop_for" -- swingbot # expect: no output
git grep -n "HARD_MAX_PLANNED_LOSS_PCT = " -- swingbot/core/risk_limits.py  # expect: 2.0
git grep -n "def select_structural_target\|def select_tp2" -- swingbot/core/planning/targets.py
git grep -n "for j in range(entry_index + 1" -- swingbot/core/planning/exit_sim.py  # expect: 2 hits
git grep -n "never filled" -- swingbot/core/presentation/instructions.py  # expect: 1 hit
git grep -n "range_continuation\|RANGE_ALERTS" -- swingbot     # expect: no output
python -c "from swingbot.core.marketdata import backtest_cache as b; print(b.CACHE_DIR)"
```

- [ ] **Step 2: Hash the cache the TRAIN run will read**

```bash
python - <<'PY'
import hashlib
from swingbot.core.marketdata import backtest_cache as b
files = sorted(b.CACHE_DIR.glob("*.csv"))
h = hashlib.sha256()
for f in files:
    h.update(f.name.encode()); h.update(hashlib.sha256(f.read_bytes()).digest())
print(len(files), "files", h.hexdigest())
first = min(f.read_text().splitlines()[1].split(",")[0] for f in files)
print("earliest bar", first)
PY
```

Expected: a file count, a 64-hex digest, and an earliest bar before
`2019-06-01` (TRAIN starts 2020-01-01; the longest candidate warm-up is
`20 + 30 + 5` bars and the longest horizon needs `MIN_BARS["9m"] = 390`).
If the earliest bar is later, record it. The 9m horizon then warms up
inside TRAIN; that is reported, not fixed.

- [ ] **Step 3: Write the contract note**

Fill every `<…>` with the value the commands printed. Nothing else is
left open.

```markdown
# v105 as-of contract and frozen measurement inputs

**Spec:** docs/superpowers/specs/2026-09-25-v105-pending-range-continuation-design.md
**Plan:** docs/superpowers/plans/2026-09-25-v105-pending-range-continuation_0-index.md
**Written at:** <git rev-parse HEAD> (no outcome has been run)

## Dependencies as found
- v100 ArmEngine: absent → bespoke `swingbot/core/backtesting/range_arms.py`
  feeding `acceptance.evaluate` / `scripts/backtest/validate_component.py`.
  It reaches the same live source because both call
  `range_source.range_plan_at` / `first_issuable`.
- v104: no code. Risk model for BOTH arms: `risk_limits.HARD_MAX_PLANNED_LOSS_PCT
  = 2.0` via `capped_planned_loss_pct(HORIZONS[h]["max_risk_pct"])`, drop (not
  clamp); sizing `account.compute_position_size` at trade-log time. If v104
  lands before Task 8, re-freeze here under the new model before any run.
- Target: `targets.select_structural_target`; a synthetic capped TP1 is refused.
- Exit replay: `exit_sim.simulate_exit(scale_out=True)`; fill bar not
  stop/target-checked (`range_replay.EXIT_LIMITATION`).
- Scan insertion: `scan_run._sync_run_scan`, directly after
  `_maybe_run_strategy_pass` (after `_scan_one`'s open-position monitoring,
  liquidity and data-quality screens).
- PlanStore identity: `plan_id` only; range identity lives in
  `plan.entry_context["range"]["identity"]` and `range_candidate.may_rearm`.

## As-of contract
- Decision for session t reads daily bars completed through t-1:
  replay `df.iloc[:i+1]` for session i+1; live `strategy_pass.completed_frame`.
- Live quote: `range_pass.fresh_quote` (`allow_stale=False`, 15 s TTL) for
  proximity/crossing only.
- Replay proximity proxy: Close[i] (the price at which a user places the
  overnight order). Fills examined on bars i+1..i+5.

## Frozen measurement inputs
- TRAIN window: 2020-01-01..2023-12-31. Fold-test years 2021, 2022, 2023.
- Cache: <CACHE_DIR>, <count> files, manifest sha256 <digest>, earliest bar <date>.
- Universe: every cached symbol passing `universe.liquidity_reason` and
  `universe.data_quality_issues` (no ETF exclusion).
- Horizons: all ten keys of `strategy_types.HORIZONS`.
- Constants: as in `range_candidate.py` (N_GRID, D_GRID, TOUCH_ATR, …).
- Exit model: simulate_exit scale_out=True, expiry 5 sessions, worse-of fill.
- Selection rule (`range_arms.select_cell`): eligible = component n ≥ 30 AND
  ΔWR > 0 AND ΔExpR ≥ −0.01; plateau = eligible with ≥ 2 eligible grid
  neighbours (adjacent N or adjacent d); pick max ΔExpR; ties → smaller d,
  then larger N; per direction independently.
- Sector clusters: count distinct `universe.sector_map("sp500")` sectors among
  TRAIN-issued tickers; expected ≥ 8 (fewer is reported as concentration).
- Holdout eligibility: first complete session AFTER the Task 9 pre-registration
  commit; never 2024-01-01..2025-12-31; never v104's 2026 holdout.

## Integrity finding (out of scope, recorded)
`presentation/instructions.py` tells a confluence stop-entry user a
`cancelled_risk_cap` plan "never filled". A resting broker stop that gapped
may have filled. v105 fixes the text for `range_continuation` plans only
(Task 5); the confluence instance needs its own integrity spec.
```

- [ ] **Step 4: Commit**

```bash
git status --short
git add docs/superpowers/results/2026-09-25-v105-asof-contract.md
git commit -m "docs(v105): freeze as-of contract and measurement inputs before any run"
```

**Verification:** Review the note against spec §§ "Boundary with active and
closed work" and "Evidence and acceptance", and `docs/claude/backtest-methodology.md`.
No performance score is produced here.

### Task 2: Implement pure range candidate and causal pressure

**Files:**
- Create: `swingbot/core/market/range_candidate.py`
- Create: `tests/market/range_fixtures.py`
- Test: `tests/market/test_pending_range_candidate.py`

**Interfaces:**
- Consumes: `swingbot.core.market.indicators.atr(df, period=14) -> pd.Series`.
- Produces (every later task uses these exact names):
  - constants `SOURCE_ID = "range_continuation"`, `STRATEGY_NAME = "Range Continuation"`,
    `N_GRID`, `D_GRID`, `ATR_PERIOD`, `TRIGGER_BUFFER_ATR`, `STOP_CUSHION_ATR`
  - `@dataclass(frozen=True) RangeCandidate(ticker, direction, n, range_start, asof, upper, lower, atr, touch_dates, pivot_price, pivot_date, pressure)`
    with `.boundary`, `.width`, `.identity`, `.to_dict()`
  - `min_bars(n) -> int`, `decision_frame(df, session) -> DataFrame`
  - `range_candidate(df, *, n, ticker="", atr_value=None) -> RangeCandidate | None`
  - `proximity(candidate, trigger, price, d) -> str` (`ok|no_quote|crossed|outside_range|too_far`)
  - `may_rearm(candidate, prior_created_at) -> bool`
  - fixtures `long_frame(extra=())`, `short_frame(extra=())`, `mirror(df)`,
    `FLAT`, `TREND_BARS`, `fixed_levels(frame, horizon_key, trigger, direction, params=None)`

- [ ] **Step 1: Write the shared fixtures**

`tests/market/range_fixtures.py`:

```python
"""v105 synthetic daily frames shared by the range tests.

`long_frame()` is a 45-bar uptrend (close 77 -> 99, +0.5 per bar) followed
by a 20-bar range with upper 106.0 and lower 100.0. The range has
trigger-side touches at range positions 2, 7, 17 and 19, a confirmed pivot
low of 105.0 at position 17 (its right-hand bar, position 18, is complete),
and directional pressure on its last three bars. `mirror()` reflects a
frame around 200, so every LONG case has an exact SHORT twin with an
identical ATR.
"""
from tests.helpers import make_ohlcv

TREND_BARS = 45
RANGE_BARS = (
    (100.5, 102.0, 100.0, 101.5),
    (101.5, 103.5, 101.5, 103.0),
    (103.0, 106.0, 102.5, 104.0),
    (104.0, 104.5, 102.0, 102.5),
    (102.5, 103.0, 101.0, 101.5),
    (101.5, 102.5, 100.5, 102.0),
    (102.0, 103.5, 101.5, 103.0),
    (103.0, 105.8, 102.5, 104.5),
    (104.5, 105.0, 103.0, 103.5),
    (103.5, 104.0, 102.0, 102.5),
    (102.5, 103.0, 101.2, 101.8),
    (101.8, 103.0, 101.6, 102.8),
    (102.8, 104.0, 102.2, 103.6),
    (103.6, 104.6, 102.8, 103.2),
    (103.2, 104.0, 102.4, 103.0),
    (103.0, 104.2, 103.0, 103.8),
    (105.3, 105.6, 105.2, 105.4),
    (105.4, 105.8, 105.0, 105.5),
    (105.5, 105.7, 105.1, 105.6),
    (105.6, 105.9, 105.3, 105.8),
)
# Inside the range: no trigger touch, no close through the stop.
FLAT = (105.5, 105.9, 105.2, 105.6)


def trend_bars():
    return [(c - 0.25, c + 1.0, c - 1.0, c) for c in (77 + 0.5 * k for k in range(TREND_BARS))]


def long_frame(extra=()):
    return make_ohlcv(trend_bars() + list(RANGE_BARS) + list(extra), start="2023-01-02")


def mirror(df, pivot=200.0):
    out = df.copy()
    out["Open"] = pivot - df["Open"]
    out["High"] = pivot - df["Low"]
    out["Low"] = pivot - df["High"]
    out["Close"] = pivot - df["Close"]
    return out


def short_frame(extra=()):
    """`extra` is written in LONG terms and mirrored with everything else."""
    return mirror(long_frame(extra))


def fixed_levels(frame, horizon_key, trigger, direction, params=None):
    """Stand-in for range_source.range_target_levels: one real level ~2R out."""
    return [round(trigger * (1.025 if direction == "bullish" else 0.975), 2)]
```

- [ ] **Step 2: Write the failing tests**

`tests/market/test_pending_range_candidate.py`:

```python
"""v105 Task 2: pure, causal range candidate geometry and pressure."""
import math

import pandas as pd
import pytest

from swingbot.core.market import range_candidate as rc
from swingbot.core.market.indicators import atr
from tests.market.range_fixtures import FLAT, TREND_BARS, long_frame, short_frame

BOOM = (106.0, 140.0, 105.9, 139.0)


def _iso(df, pos):
    return df.index[pos].date().isoformat()


def _window(highs, lows=None, closes=None):
    lows = lows or [h - 1 for h in highs]
    closes = closes or [h - 0.5 for h in highs]
    idx = pd.bdate_range("2024-01-01", periods=len(highs))
    return pd.DataFrame({"Open": closes, "High": highs, "Low": lows, "Close": closes}, index=idx)


def test_long_candidate_geometry():
    df = long_frame()
    cand = rc.range_candidate(df, n=20, ticker="AAA")
    assert cand is not None
    assert cand.direction == "bullish"
    assert (cand.upper, cand.lower) == (106.0, 100.0)
    assert cand.range_start == _iso(df, TREND_BARS)
    assert cand.asof == _iso(df, -1)
    assert math.isclose(cand.atr, float(atr(df, 14).iloc[-1]))
    assert len(cand.touch_dates) >= 2
    assert (cand.pivot_price, cand.pivot_date) == (105.0, _iso(df, TREND_BARS + 17))
    assert cand.pressure is True
    assert cand.boundary == 106.0
    assert cand.identity == f"range_continuation:AAA:bullish:N20:{cand.range_start}"
    assert cand.to_dict()["identity"] == cand.identity


def test_short_candidate_mirrors_long():
    long_c = rc.range_candidate(long_frame(), n=20, ticker="AAA")
    short_c = rc.range_candidate(short_frame(), n=20, ticker="AAA")
    assert short_c.direction == "bearish"
    assert math.isclose(short_c.upper, 200 - long_c.lower)
    assert math.isclose(short_c.lower, 200 - long_c.upper)
    assert math.isclose(short_c.pivot_price, 200 - long_c.pivot_price)
    assert math.isclose(short_c.atr, long_c.atr)
    assert short_c.touch_dates == long_c.touch_dates
    assert short_c.pressure is True
    assert short_c.boundary == short_c.lower


def test_missing_warmup_returns_none():
    df = long_frame()
    assert rc.range_candidate(df.iloc[-(rc.min_bars(20) - 1):], n=20) is None


def test_unregistered_n_is_refused():
    with pytest.raises(ValueError):
        rc.range_candidate(long_frame(), n=12)


def test_touches_must_be_two_sessions_apart():
    adjacent = _window([100, 100, 106, 106, 100, 100])
    assert len(rc.separated_touches(adjacent, "bullish", 106, 99, 1.0)) == 1
    apart = _window([100, 106, 100, 106, 100, 100])
    assert len(rc.separated_touches(apart, "bullish", 106, 99, 1.0)) == 2


@pytest.mark.parametrize("width, ok", [(1.99, False), (2.0, True), (8.0, True), (8.01, False)])
def test_width_edges(width, ok):
    assert rc.width_ok(100.0 + width, 100.0, 1.0) is ok


def test_trend_is_read_from_bars_before_the_range_only():
    df = long_frame()
    assert rc.trend_direction(df.iloc[:-20]) == "bullish"
    crashed = df.copy()
    crashed.iloc[-20:, :4] = crashed.iloc[-20:, :4] - 30.0
    assert rc.trend_direction(crashed.iloc[:-20]) == "bullish"
    flat = df.iloc[:-20].copy()
    flat[["Open", "High", "Low", "Close"]] = 100.0
    assert rc.trend_direction(flat) is None


def test_decision_frame_excludes_the_current_session_bar():
    df = long_frame()
    session = _iso(df, -1)
    frame = rc.decision_frame(df, session)
    assert frame.index[-1] == df.index[-2]
    blown = df.copy()
    blown.iloc[-1, blown.columns.get_loc("High")] = 500.0
    assert rc.range_candidate(rc.decision_frame(blown, session), n=20) == rc.range_candidate(frame, n=20)


def test_pivot_needs_its_right_hand_bar():
    w = _window([5, 5, 5, 5], lows=[3.0, 2.0, 2.5, 1.0])
    assert rc.confirmed_pivot(w, "bullish") == (2.0, w.index[1].date().isoformat())
    assert rc.confirmed_pivot(_window([5, 5, 5], lows=[3.0, 3.0, 1.0]), "bullish") == (None, None)


def test_pressure_needs_zone_closes_and_a_rising_low():
    window = long_frame().iloc[-20:]
    assert rc.pressure(window, "bullish", 106.0, 100.0) is True
    falling = window.copy()
    falling.iloc[-1, falling.columns.get_loc("Low")] = 104.0
    assert rc.pressure(falling, "bullish", 106.0, 100.0) is False
    low_closes = window.copy()
    low_closes.iloc[-2:, low_closes.columns.get_loc("Close")] = 103.0
    assert rc.pressure(low_closes, "bullish", 106.0, 100.0) is False


def test_future_breakout_leaves_earlier_candidates_unchanged():
    base = long_frame([FLAT] * 5)
    boom = long_frame([FLAT] * 5 + [BOOM] * 5)
    for i in range(rc.min_bars(10) - 1, len(base)):
        for n in rc.N_GRID:
            assert rc.range_candidate(base.iloc[: i + 1], n=n) == rc.range_candidate(boom.iloc[: i + 1], n=n)


def test_full_series_atr_equals_truncated_atr_at_every_bar():
    df = long_frame([FLAT] * 5 + [BOOM] * 5)
    full = atr(df, rc.ATR_PERIOD)
    for i in range(rc.min_bars(10) - 1, len(df)):
        truncated = df.iloc[: i + 1]
        for n in rc.N_GRID:
            assert rc.range_candidate(truncated, n=n) == rc.range_candidate(
                truncated, n=n, atr_value=float(full.iloc[i]))


@pytest.mark.parametrize("price, expected", [
    (None, "no_quote"), (float("nan"), "no_quote"), (106.2, "crossed"),
    (106.1, "outside_range"), (105.9, "ok"), (100.5, "too_far")])
def test_proximity_long(price, expected):
    cand = rc.range_candidate(long_frame(), n=20)
    assert rc.proximity(cand, 106.15, price, 0.5) == expected


def test_may_rearm_only_after_prior_creation():
    cand = rc.range_candidate(long_frame(), n=20)
    assert rc.may_rearm(cand, None)
    assert not rc.may_rearm(cand, cand.range_start)
    assert not rc.may_rearm(cand, cand.asof)
    day_before = (pd.Timestamp(cand.range_start) - pd.Timedelta(days=1)).date().isoformat()
    assert rc.may_rearm(cand, day_before)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_pending_range_candidate.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'swingbot.core.market.range_candidate'`.

- [ ] **Step 4: Implement the module**

`swingbot/core/market/range_candidate.py`:

```python
"""v105: pre-break daily range continuation candidates.

Pure and causal. Every function reads only the frame it is handed, and the
caller hands it daily bars completed through t-1 (`decision_frame` in the
replay, `strategy_pass.completed_frame` live). The live quote on session t
reaches this module only through `proximity`, which reads geometry frozen
here and never edits it.

A candidate is the geometry of one range and nothing else: no stop, no
target, no plan. `swingbot/core/planning/range_builder.py` owns those.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

import pandas as pd

from swingbot.core.market.indicators import atr

SOURCE_ID = "range_continuation"
STRATEGY_NAME = "Range Continuation"

# Frozen by the v105 spec. Feasibility rules and TRAIN axes, not knobs: a
# failed gate never loosens them (docs/claude/backtest-methodology.md).
N_GRID = (10, 15, 20)
D_GRID = (0.25, 0.50, 0.75)
ATR_PERIOD = 14
TOUCH_ATR = 0.25
MIN_TOUCH_GAP = 2            # window positions apart: at least one bar between visits
MIN_WIDTH_ATR = 2.0
MAX_WIDTH_ATR = 8.0
TREND_SMA = 30
TREND_SLOPE_BARS = 5
TRIGGER_BUFFER_ATR = 0.10
STOP_CUSHION_ATR = 0.10
PRESSURE_BARS = 3
PRESSURE_MIN_CLOSES = 2
PRESSURE_ZONE = 0.25


@dataclass(frozen=True)
class RangeCandidate:
    ticker: str
    direction: str                 # "bullish" | "bearish"
    n: int
    range_start: str               # ISO date of the window's first bar
    asof: str                      # ISO date of the last completed bar (t-1)
    upper: float
    lower: float
    atr: float
    touch_dates: tuple[str, ...]
    pivot_price: float | None      # latest confirmed internal three-bar pivot
    pivot_date: str | None
    pressure: bool

    @property
    def boundary(self) -> float:
        return self.upper if self.direction == "bullish" else self.lower

    @property
    def width(self) -> float:
        return self.upper - self.lower

    @property
    def identity(self) -> str:
        return f"{SOURCE_ID}:{self.ticker}:{self.direction}:N{self.n}:{self.range_start}"

    def to_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["touch_dates"] = list(self.touch_dates)
        out["identity"] = self.identity
        return out


def min_bars(n: int) -> int:
    """Warm-up: the pre-range SMA needs TREND_SMA + TREND_SLOPE_BARS bars."""
    return n + TREND_SMA + TREND_SLOPE_BARS


def _iso(ts) -> str:
    return pd.Timestamp(ts).date().isoformat()


def decision_frame(df: pd.DataFrame, session: str) -> pd.DataFrame:
    """The bars a decision on `session` (ISO date) may read: strictly before it."""
    return df.loc[df.index < pd.Timestamp(session)]


def width_ok(upper: float, lower: float, atr_value: float) -> bool:
    width = upper - lower
    return MIN_WIDTH_ATR * atr_value <= width <= MAX_WIDTH_ATR * atr_value


def trend_direction(pre: pd.DataFrame) -> str | None:
    """Trend fixed BEFORE the range: the 30-SMA's slope over its previous
    five bars, plus the last pre-range close on the matching side of it.
    Price action inside the range never reaches this function."""
    sma = pre["Close"].rolling(TREND_SMA).mean()
    if len(sma) <= TREND_SLOPE_BARS:
        return None
    now, then = float(sma.iloc[-1]), float(sma.iloc[-1 - TREND_SLOPE_BARS])
    if not (math.isfinite(now) and math.isfinite(then)):
        return None
    close = float(pre["Close"].iloc[-1])
    if now > then and close > now:
        return "bullish"
    if now < then and close < now:
        return "bearish"
    return None


def separated_touches(window, direction, upper, lower, atr_value) -> tuple[str, ...]:
    """Dates of trigger-side visits within TOUCH_ATR x ATR, each kept visit
    at least MIN_TOUCH_GAP positions after the previous kept one."""
    if direction == "bullish":
        hits = window["High"].to_numpy(dtype=float) >= upper - TOUCH_ATR * atr_value
    else:
        hits = window["Low"].to_numpy(dtype=float) <= lower + TOUCH_ATR * atr_value
    kept, last = [], None
    for pos, hit in enumerate(hits):
        if hit and (last is None or pos - last >= MIN_TOUCH_GAP):
            kept.append(_iso(window.index[pos]))
            last = pos
    return tuple(kept)


def confirmed_pivot(window, direction) -> tuple[float | None, str | None]:
    """Latest three-bar pivot low (LONG) / high (SHORT) with all three bars
    inside the window. Its right-hand bar being IN the frame is what makes it
    confirmed by t-1, so the window's last position is never a pivot."""
    col = "Low" if direction == "bullish" else "High"
    values = window[col].to_numpy(dtype=float)
    for pos in range(len(values) - 2, 0, -1):
        mid, left, right = values[pos], values[pos - 1], values[pos + 1]
        if direction == "bullish" and mid < left and mid < right:
            return float(mid), _iso(window.index[pos])
        if direction == "bearish" and mid > left and mid > right:
            return float(mid), _iso(window.index[pos])
    return None, None


def pressure(window, direction, upper, lower) -> bool:
    """Pre-break directional pressure: at least two of the last three closes
    in the direction-side quarter of the fixed range, and the last low rising
    (LONG) / last high falling (SHORT)."""
    tail = window.iloc[-PRESSURE_BARS:]
    zone = PRESSURE_ZONE * (upper - lower)
    closes = tail["Close"].to_numpy(dtype=float)
    if direction == "bullish":
        in_zone = int((closes >= upper - zone).sum())
        stepping = float(tail["Low"].iloc[-1]) > float(tail["Low"].iloc[-2])
    else:
        in_zone = int((closes <= lower + zone).sum())
        stepping = float(tail["High"].iloc[-1]) < float(tail["High"].iloc[-2])
    return in_zone >= PRESSURE_MIN_CLOSES and stepping


def _atr_at_end(df, atr_value) -> float | None:
    value = float(atr(df, ATR_PERIOD).iloc[-1]) if atr_value is None else float(atr_value)
    return value if math.isfinite(value) and value > 0 else None


def range_candidate(df, *, n, ticker="", atr_value=None) -> RangeCandidate | None:
    """The range candidate as of df's last bar, or None.

    `atr_value` lets the replay pass ATR(14) read off one full-series pass.
    That equals the truncated computation because the Wilder EWM is
    recursive (adjust=False); test_full_series_atr_equals_truncated_atr_at_every_bar
    pins it. No completed close can sit outside the bounds, because the
    bounds ARE the window's max high / min low: that spec rule holds by
    construction.
    """
    if n not in N_GRID:
        raise ValueError(f"n={n} is not in the pre-registered N_GRID {N_GRID}")
    if df is None or len(df) < min_bars(n):
        return None
    value = _atr_at_end(df, atr_value)
    if value is None:
        return None
    window = df.iloc[-n:]
    # Only the tail the SMA test reads: keeps the replay O(bars), not O(bars^2).
    pre = df.iloc[-(n + TREND_SMA + TREND_SLOPE_BARS):-n]
    direction = trend_direction(pre)
    if direction is None:
        return None
    upper, lower = float(window["High"].max()), float(window["Low"].min())
    if not width_ok(upper, lower, value):
        return None
    touches = separated_touches(window, direction, upper, lower, value)
    if len(touches) < 2:
        return None
    pivot_price, pivot_date = confirmed_pivot(window, direction)
    return RangeCandidate(
        ticker=ticker, direction=direction, n=n,
        range_start=_iso(window.index[0]), asof=_iso(window.index[-1]),
        upper=upper, lower=lower, atr=value, touch_dates=touches,
        pivot_price=pivot_price, pivot_date=pivot_date,
        pressure=pressure(window, direction, upper, lower))


def proximity(candidate, trigger, price, d) -> str:
    """Whether a quote may carry a PENDING notice for this candidate:
    'ok' | 'no_quote' | 'crossed' | 'outside_range' | 'too_far'."""
    if price is None or not math.isfinite(price) or price <= 0:
        return "no_quote"
    bull = candidate.direction == "bullish"
    if (price >= trigger) if bull else (price <= trigger):
        return "crossed"
    if not candidate.lower <= price <= candidate.upper:
        return "outside_range"
    distance = (trigger - price) if bull else (price - trigger)
    return "ok" if distance <= d * candidate.atr + 1e-12 else "too_far"


def may_rearm(candidate, prior_created_at: str | None) -> bool:
    """A new range needs its first bar AFTER the prior plan's creation
    session (spec: conservative identity rule, fixed for the first
    measurement, not tuned on the outcome)."""
    return prior_created_at is None or candidate.range_start > prior_created_at
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_pending_range_candidate.py`
Expected: `0 failed`, `0 xfailed`.

- [ ] **Step 6: Check complexity**

Run: `python -m radon cc -s -n C swingbot/core/market/range_candidate.py tests/market/test_pending_range_candidate.py`
Expected: no output (every block below C, i.e. < 11, well under 15).

- [ ] **Step 7: Commit**

```bash
git status --short
git add swingbot/core/market/range_candidate.py tests/market/range_fixtures.py tests/market/test_pending_range_candidate.py
git commit -m "feat(v105): pure causal range candidate, pressure predicate and rearm rule"
```

**Verification:** the narrow run above, radon, and `git diff HEAD~1 --stat`
listing only these three files (no v104 or confluence module touched).

### Task 3: Build one range plan with real target and risk guard

**Files:**
- Create: `swingbot/core/planning/range_builder.py`
- Create: `swingbot/core/planning/range_source.py`
- Modify: `swingbot/core/tracking/ledger.py:12-16` (`ledger_for`)
- Test: `tests/planning/test_pending_range_builder.py`

**Interfaces:**
- Consumes: `RangeCandidate`, `SOURCE_ID`, `STRATEGY_NAME`, `TRIGGER_BUFFER_ATR`,
  `STOP_CUSHION_ATR`, `range_candidate`, `proximity`, `may_rearm` (Task 2);
  `targets.select_structural_target(entry, stop_loss, is_bull, candidate_levels, min_rr, max_rr)`;
  `targets.select_tp2(levels_above, levels_below, direction, entry, tp1)`;
  `levels.build_level_map(df, h, current_price, candidates=None, params=None)`;
  `levels.target_candidates(supports, resistances, direction)`;
  `risk_limits.capped_planned_loss_pct`, `planned_loss_pct`.
- Produces:
  - `range_builder.RangePrices(trigger, stop, risk_cap_fill)`
  - `range_builder.range_prices(candidate, horizon_key) -> tuple[RangePrices | None, str]`
  - `range_builder.build_range_plan(candidate, *, horizon_key, target_levels, min_rr, max_rr, plan_id=None) -> tuple[TradePlanV2 | None, str]`
    Reasons: `ok | no_pivot | bad_arithmetic | risk_cap | no_target | target_beyond_band`.
  - `range_source.RangeBuild(candidate, plan, reason)`
  - `range_source.range_target_levels(frame, horizon_key, trigger, direction, params=None) -> list[float]`
  - `range_source.range_plan_at(frame, *, ticker, horizon_key, n, params=None, atr_value=None, candidate=None, plan_id=None) -> RangeBuild`
  - `range_source.screen(candidate, prior_created_at, require_pressure) -> str | None`
  - `range_source.first_issuable(frame, candidate, horizons, *, price, d, params, counts, build=None) -> tuple[str, TradePlanV2] | None`
  - plan fields: `source="range_continuation"`, `strategy="Range Continuation"`,
    `entry_type="stop_entry"`, `expiry_bars=5`, `badge="WEAK"`, `ledger="weak"`,
    `entry_context={"range": candidate.to_dict(), "risk_cap_fill": float}`

- [ ] **Step 1: Confirm nothing switches on an unknown `source` value**

Run: `git grep -n "\.source\b" -- swingbot | grep -v "source ==\|source in\|getattr"`
Expected: only assignments/reads that pass the value through (trade log,
serialisers, `ledger_for`, registry `_find`). If any dict is *indexed* by
`plan.source` (for example `SOMETHING[plan.source]`), add `"range_continuation"`
to it in this task and list it in the commit message.

- [ ] **Step 2: Write the failing tests**

`tests/planning/test_pending_range_builder.py`:

```python
"""v105 Task 3: range candidate -> PENDING stop-entry plan."""
import math

import pytest

from swingbot.core.market.range_candidate import SOURCE_ID, RangeCandidate
from swingbot.core.planning import range_builder as rb
from swingbot.core.planning import range_source
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.risk_limits import planned_loss_pct
from swingbot.core.tracking.ledger import MAIN, WEAK, ledger_for
from tests.market.range_fixtures import fixed_levels, long_frame
from tests.planning.test_build_confluence_plan import _TIGHT_RANGE_DF, _make_scenario

BAND = dict(min_rr=1.5, max_rr=2.5)


def _cand(direction="bullish", **kw):
    if direction == "bullish":
        base = dict(upper=106.0, lower=100.0, pivot_price=105.0)
    else:
        base = dict(upper=100.0, lower=94.0, pivot_price=95.0)
    base.update(ticker="AAA", direction=direction, n=20, range_start="2024-03-01",
                asof="2024-03-28", atr=1.5, touch_dates=("2024-03-05", "2024-03-12"),
                pivot_date="2024-03-25", pressure=True)
    base.update(kw)
    return RangeCandidate(**base)


def _build(cand, levels, horizon_key="4w"):
    return rb.build_range_plan(cand, horizon_key=horizon_key, target_levels=levels, **BAND)


def test_long_plan_fields():
    plan, reason = _build(_cand(), [108.75, 111.0])
    assert reason == "ok"
    assert (plan.entry_type, plan.status, plan.entry_price) == ("stop_entry", PlanStatus.PENDING, None)
    assert (plan.trigger_price, plan.stop_loss, plan.tp1, plan.tp2) == (106.15, 104.85, 108.75, 111.0)
    assert (plan.source, plan.strategy, plan.expiry_bars) == (SOURCE_ID, "Range Continuation", 5)
    assert (plan.created_at, plan.badge, plan.ledger) == ("2024-03-28", "WEAK", WEAK)
    assert plan.entry_context["range"]["identity"] == _cand().identity
    assert math.isclose(plan.entry_context["risk_cap_fill"], 104.85 / 0.98, abs_tol=1e-4)


def test_short_plan_mirrors_long():
    plan, reason = _build(_cand("bearish"), [91.25, 89.0])
    assert reason == "ok"
    assert (plan.trigger_price, plan.stop_loss, plan.tp1, plan.tp2) == (93.85, 95.15, 91.25, 89.0)
    assert plan.trigger_price < plan.entry_context["range"]["lower"]
    assert plan.tp1 < plan.trigger_price < plan.stop_loss


def test_trigger_and_stop_round_outward_to_the_tick():
    long_p, _ = rb.range_prices(_cand(atr=1.234), "4w")
    assert (long_p.trigger, long_p.stop) == (106.13, 104.87)
    short_p, _ = rb.range_prices(_cand("bearish", atr=1.234), "4w")
    assert (short_p.trigger, short_p.stop) == (93.87, 95.13)


@pytest.mark.parametrize("kw, levels, reason", [
    (dict(pivot_price=None, pivot_date=None), [108.75], "no_pivot"),
    (dict(atr=float("nan")), [108.75], "bad_arithmetic"),
    (dict(pivot_price=107.0), [108.75], "bad_arithmetic"),
    (dict(pivot_price=100.2), [120.0], "risk_cap"),
    ({}, [], "no_target"),
    ({}, [107.0], "no_target"),
    ({}, [115.0], "target_beyond_band"),
])
def test_refusals(kw, levels, reason):
    plan, why = _build(_cand(**kw), levels)
    assert (plan, why) == (None, reason)


def test_gap_fill_beyond_risk_cap_fill_breaks_the_cap():
    prices, _ = rb.range_prices(_cand(), "4w")
    assert math.isclose(planned_loss_pct(prices.risk_cap_fill, prices.stop), 2.0, abs_tol=1e-3)
    assert planned_loss_pct(prices.risk_cap_fill + 0.05, prices.stop) > 2.0


def test_builder_does_not_mutate_its_inputs():
    levels = [108.75, 111.0]
    cand = _cand()
    _build(cand, levels)
    assert levels == [108.75, 111.0]
    assert cand == _cand()


def test_range_source_joins_the_weak_ledger_only_while_weak():
    assert ledger_for(SOURCE_ID, "WEAK") == WEAK
    assert ledger_for(SOURCE_ID, "VALIDATED") == MAIN
    assert ledger_for("strategy", "WEAK") == WEAK
    assert ledger_for("confluence", "WEAK") == MAIN


def test_confluence_stop_entry_trigger_is_unchanged():
    scenario = _make_scenario(entry=100.0, stop_loss=96.0, take_profit=108.0)
    plan = build_confluence_plan(scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
                                 primary_strategy="S/R Confluence")
    assert (plan.source, plan.entry_type, plan.trigger_price, plan.entry_price) == (
        "confluence", "stop_entry", 100.0, None)


def test_range_plan_at_uses_the_frame_and_the_shared_builder(monkeypatch):
    monkeypatch.setattr(range_source, "range_target_levels", fixed_levels)
    build = range_source.range_plan_at(long_frame(), ticker="AAA", horizon_key="4w", n=20)
    assert build.reason == "ok"
    assert build.plan.trigger_price > build.candidate.upper
    assert build.plan.entry_context["range"]["identity"] == build.candidate.identity


def test_screen_orders_rearm_before_pressure():
    cand = _cand(pressure=False)
    assert range_source.screen(cand, cand.asof, True) == "rearm_blocked"
    assert range_source.screen(cand, None, True) == "pressure_rejected"
    assert range_source.screen(cand, None, False) is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_pending_range_builder.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'swingbot.core.planning.range_builder'`.

- [ ] **Step 4: Implement the builder**

`swingbot/core/planning/range_builder.py`:

```python
"""v105: one RangeCandidate -> one PENDING stop-entry TradePlanV2.

The trigger is the candidate's frozen boundary plus TRIGGER_BUFFER_ATR x ATR,
rounded outward to the tick, and set here, independently of any scenario.
build_confluence_plan's stop_entry trigger (the scenario entry) is untouched.
Nothing here reads a dataframe: structural levels arrive as plain prices
from range_source.range_target_levels, so live and replay price identically.

Sizing is not done here, for any source: account.compute_position_size runs
at trade-log time. The risk guard is the drop-not-clamp planned-loss cap the
strategy builders use (`_level_stop_or_none`).
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from swingbot.core.market.range_candidate import (
    SOURCE_ID, STOP_CUSHION_ATR, STRATEGY_NAME, TRIGGER_BUFFER_ATR, RangeCandidate)
from swingbot.core.market.strategy_types import BREAKEVEN_TRIGGER_FRACTION, HORIZONS
from swingbot.core.planning.params import DEFAULT_EXPIRY_BARS, TP1_FRACTION, TRAIL_ATR_MULT
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.planning.targets import select_structural_target, select_tp2
from swingbot.core.risk_limits import capped_planned_loss_pct, planned_loss_pct
from swingbot.core.tracking.ledger import ledger_for

TICK = 0.01


def _up(price: float) -> float:
    return round(math.ceil(round(price / TICK, 6)) * TICK, 2)


def _down(price: float) -> float:
    return round(math.floor(round(price / TICK, 6)) * TICK, 2)


@dataclass(frozen=True)
class RangePrices:
    trigger: float
    stop: float
    risk_cap_fill: float     # worst fill price that still respects the planned-loss cap


def _finite(candidate: RangeCandidate) -> bool:
    values = (candidate.atr, candidate.upper, candidate.lower, candidate.pivot_price)
    return all(math.isfinite(v) for v in values)


def _raw_prices(candidate: RangeCandidate) -> tuple[float, float]:
    buffer = TRIGGER_BUFFER_ATR * candidate.atr
    cushion = STOP_CUSHION_ATR * candidate.atr
    if candidate.direction == "bullish":
        return _up(candidate.upper + buffer), _down(candidate.pivot_price - cushion)
    return _down(candidate.lower - buffer), _up(candidate.pivot_price + cushion)


def _ordered(trigger: float, stop: float, bull: bool) -> bool:
    return stop > 0 and (trigger > stop if bull else trigger < stop)


def range_prices(candidate: RangeCandidate, horizon_key: str) -> tuple[RangePrices | None, str]:
    """Trigger, stop and the worst cap-respecting fill, or (None, reason)."""
    if candidate.pivot_price is None:
        return None, "no_pivot"
    if not _finite(candidate):
        return None, "bad_arithmetic"
    bull = candidate.direction == "bullish"
    trigger, stop = _raw_prices(candidate)
    if not _ordered(trigger, stop, bull):
        return None, "bad_arithmetic"
    cap = capped_planned_loss_pct(HORIZONS[horizon_key]["max_risk_pct"])
    if planned_loss_pct(trigger, stop) > cap + 1e-9:
        return None, "risk_cap"
    cap_fill = stop / (1 - cap / 100) if bull else stop / (1 + cap / 100)
    return RangePrices(trigger, stop, round(cap_fill, 4)), "ok"


def _is_real_level(tp1: float, levels: list[float]) -> bool:
    """select_structural_target returns a SYNTHETIC entry +/- risk x max_rr
    price when the nearest level sits beyond the band. The spec requires a
    real structural target with no projected fallback."""
    return any(math.isclose(tp1, p, rel_tol=0.0, abs_tol=1e-9 * max(1.0, abs(p))) for p in levels)


def build_range_plan(candidate: RangeCandidate, *, horizon_key: str, target_levels,
                     min_rr: float, max_rr: float,
                     plan_id: str | None = None) -> tuple[TradePlanV2 | None, str]:
    """The PENDING plan, or (None, reason): no_pivot | bad_arithmetic |
    risk_cap | no_target | target_beyond_band."""
    prices, reason = range_prices(candidate, horizon_key)
    if prices is None:
        return None, reason
    bull = candidate.direction == "bullish"
    levels = [float(p) for p in target_levels if p is not None and math.isfinite(float(p))]
    tp1 = select_structural_target(prices.trigger, prices.stop, bull, levels, min_rr, max_rr)
    if tp1 is None:
        return None, "no_target"
    if not _is_real_level(tp1, levels):
        return None, "target_beyond_band"
    above, below = (levels, []) if bull else ([], levels)
    plan = TradePlanV2(
        plan_id=plan_id or str(uuid.uuid4()), ticker=candidate.ticker,
        created_at=candidate.asof, source=SOURCE_ID, strategy=STRATEGY_NAME,
        horizon_key=horizon_key, direction=candidate.direction,
        entry_type="stop_entry", trigger_price=prices.trigger, entry_price=None,
        expiry_bars=DEFAULT_EXPIRY_BARS, stop_loss=prices.stop, tp1=tp1,
        tp1_fraction=TP1_FRACTION,
        tp2=select_tp2(above, below, candidate.direction, prices.trigger, tp1),
        breakeven_trigger_fraction=BREAKEVEN_TRIGGER_FRACTION,
        trail_atr_mult=TRAIL_ATR_MULT, quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
        entry_context={"range": candidate.to_dict(), "risk_cap_fill": prices.risk_cap_fill})
    plan.ledger = ledger_for(plan.source, plan.badge)
    return plan, "ok"
```

- [ ] **Step 5: Implement the shared source entry point**

`swingbot/core/planning/range_source.py`:

```python
"""v105: the ONE path from completed bars to an issuable range plan.

The live scan (scanning/range_pass.py) and the replay
(backtesting/range_replay.py) both go through `screen` then
`first_issuable`, which builds through `range_plan_at`. The two paths
differ only in the price they pass: the fresh live quote, or Close[i].
"""
from __future__ import annotations

from dataclasses import dataclass

from swingbot.core.market import levels
from swingbot.core.market.range_candidate import (
    RangeCandidate, may_rearm, proximity, range_candidate)
from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS
from swingbot.core.planning.plan_types import TradePlanV2
from swingbot.core.planning.range_builder import build_range_plan, range_prices


@dataclass(frozen=True)
class RangeBuild:
    candidate: RangeCandidate | None
    plan: TradePlanV2 | None
    reason: str


def range_target_levels(frame, horizon_key, trigger, direction, params=None) -> list[float]:
    """Existing structural levels beyond the trigger, nearest first, from the
    unified level map the confluence path uses. Read off `frame` (completed
    bars only) and nothing else."""
    supports, resistances = levels.build_level_map(frame, HORIZONS[horizon_key], trigger, params=params)
    return levels.target_candidates(supports, resistances, direction)


def _params(params):
    if params is not None:
        return params
    from swingbot.scan_params import ScanParams
    return ScanParams.from_config()


def range_plan_at(frame, *, ticker, horizon_key, n, params=None, atr_value=None,
                  candidate=None, plan_id=None) -> RangeBuild:
    cand = candidate if candidate is not None else range_candidate(
        frame, n=n, ticker=ticker, atr_value=atr_value)
    if cand is None:
        return RangeBuild(None, None, "no_candidate")
    prices, reason = range_prices(cand, horizon_key)
    if prices is None:
        return RangeBuild(cand, None, reason)
    params = _params(params)
    targets = range_target_levels(frame, horizon_key, prices.trigger, cand.direction, params)
    plan, reason = build_range_plan(
        cand, horizon_key=horizon_key, target_levels=targets,
        min_rr=params.min_risk_reward_ratio, max_rr=params.max_risk_reward_ratio,
        plan_id=plan_id)
    return RangeBuild(cand, plan, reason)


def screen(candidate, prior_created_at, require_pressure) -> str | None:
    """Candidate-level refusals, before any horizon or quote is consulted."""
    if not may_rearm(candidate, prior_created_at):
        return "rearm_blocked"
    if require_pressure and not candidate.pressure:
        return "pressure_rejected"
    return None


def first_issuable(frame, candidate, horizons, *, price, d, params, counts,
                   build=None) -> tuple[str, TradePlanV2] | None:
    """The first horizon, in the order given, whose plan builds while `price`
    sits within d x ATR of its trigger. The trigger does not depend on the
    horizon, so a proximity refusal ends the search. `build(horizon_key)`
    defaults to range_plan_at on `frame`; the replay passes a memoised one
    so both pressure arms read the same plan object."""
    if build is None:
        def build(hk):
            return range_plan_at(frame, ticker=candidate.ticker, horizon_key=hk,
                                 n=candidate.n, params=params, candidate=candidate)
    for hk in horizons:
        if len(frame) < MIN_BARS[hk]:
            counts["horizon_warmup"] += 1
            continue
        prices, reason = range_prices(candidate, hk)
        if prices is None:
            counts[reason] += 1
            continue
        where = proximity(candidate, prices.trigger, price, d)
        if where != "ok":
            counts[f"proximity_{where}"] += 1
            return None
        made = build(hk)
        if made.plan is not None:
            return hk, made.plan
        counts[made.reason] += 1
    return None
```

- [ ] **Step 6: Extend the weak-ledger rule**

In `swingbot/core/tracking/ledger.py`, replace `ledger_for`:

```python
#: Sources whose WEAK-badged plans book to the weak ledger. v105's range
#: source joins the v93 strategy path: it has no registry row until its own
#: badge gate passes, so it must never inflate the main ledger.
WEAK_ELIGIBLE_SOURCES = frozenset({"strategy", "range_continuation"})


def ledger_for(source: str | None, badge_status: str | None) -> str:
    """Return the frozen ledger for a newly created plan or trade."""
    if source in WEAK_ELIGIBLE_SOURCES and badge_status == "WEAK":
        return WEAK
    return MAIN
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_pending_range_builder.py`
Expected: `0 failed`, `0 xfailed`.
Then the existing ledger and confluence tests:
`python scripts/dev/testrun.py file tests/planning/test_build_confluence_plan.py`
Expected: `0 failed`. Then `git grep -ln "ledger_for" -- tests`, and run each
listed file with `testrun.py file`. Expected: `0 failed`.

- [ ] **Step 8: Check complexity and commit**

```bash
python -m radon cc -s -n C swingbot/core/planning/range_builder.py swingbot/core/planning/range_source.py swingbot/core/tracking/ledger.py
git status --short
git add swingbot/core/planning/range_builder.py swingbot/core/planning/range_source.py swingbot/core/tracking/ledger.py tests/planning/test_pending_range_builder.py
git commit -m "feat(v105): range plan builder with real structural TP1, drop-not-clamp risk cap, shared source entry point"
```

Expected radon: no output.

**Verification:** narrow runs above and radon.

