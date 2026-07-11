# Plan A — Analytics & Insight Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single analytics package (`swingbot/core/analytics/`) that turns trades.json + the validation registry + the journal into every number the Discord UX (Plan B) and the admin cockpit (Plan C) display — equity/drawdown, per-dimension stats, quality-score calibration, edge-decay detection, a per-trade lessons journal, and one shared `follow_score` ranking that answers "which plan should I follow today?".

**Architecture:** Pure functions over trade-record lists (no I/O in `metrics.py`/`aggregate.py`/`calibration.py`), a `JournalStore` that auto-writes a lesson entry on every trade close (MFE/MAE, exit efficiency, tags), a nightly `analytics_snapshot.json` so UIs never recompute on request, and an atomic-write JSON layer fixing the existing torn-write risk. Plans B and C only *render* what this package computes — no stat is ever computed twice.

**Tech Stack:** Python 3.11+, pandas 2.3.3, numpy, pytest ≥8. JSON persistence under `data/`. **No new dependencies** (quantstats stays optional in `risk_metrics.py`, untouched).

**Prerequisite:** Unified Plan Engine v2 (`docs/superpowers/plans/2026-07-11-unified-plan-engine-v2.md`) fully implemented: `plan_engine.TradePlanV2`, `quality.py` scores wired, `registry.get_badge`, `plan_store.PlanStore`, `plan_manager.PlanManager`, two-leg trades.json schema.

## Progress

> Updated by the executing session after each task batch. Resume from the first unchecked task.
>
> - **Branch:** `feature/analytics-core` (from `main` after plan-engine-v2 merge)
> - **Completed:** —
> - **Next:** Task A1

## Global Constraints

- **Read-only over trading logic.** This plan never changes entries, exits, sizing, gates, or `STRATEGY_RR_OVERRIDE`. It measures; it does not decide.
- **One definition per stat.** `win_rate` = wins/(wins+losses)×100 over closed win+loss trades; `expectancy_r` = mean realized R over all closed trades with a computable R (r = (exit−entry)/(entry−stop), sign-flipped for bearish) — identical to `performance.get_extended_stats` semantics. Any UI showing a different number is a bug.
- **Validation-window hygiene unchanged:** analytics may *display* registry OOS stats but never triggers a validation-window backtest.
- **Trade dicts are the interface.** Every analytics function takes plain trade-record dicts (schema: `performance.log_trade` record, two-leg v2 extension included). Missing keys degrade gracefully (skip + count), never raise.
- **No I/O in pure modules:** `metrics.py`, `aggregate.py`, `calibration.py`, `rank.py`, `insights.py` import neither `config` paths nor do file reads. I/O lives in `journal.py`, `snapshots.py`, `jsonio.py` only.
- **Every task ends green:** `python -m pytest tests/ -q` and `make check` pass before commit. Run from repo root `E:\Documents\Private\Projects\Discord-Bot`.
- **Timezone:** day-of-week and calendar buckets use Europe/Berlin, matching `performance.get_detailed_stats`.
- **Currency:** amounts formatted with `config.CURRENCY_SYMBOL` (default €) by callers; analytics returns raw floats.
- **Commit style:** conventional commits, one commit per task minimum.

## File Structure (target state)

```
swingbot/core/
  jsonio.py                    NEW  atomic_write_json / read_json (temp+rename, fsync)
  analytics/
    __init__.py                NEW  re-exports public API
    metrics.py                 NEW  equity, drawdown, PF, expectancy, streaks, rolling WR, sharpe/sortino
    mfe_mae.py                 NEW  MFE/MAE/exit-efficiency from cached daily bars
    aggregate.py               NEW  StatRow + stats_by(dimension)
    calibration.py             NEW  score deciles, tier calibration, badge drift
    rank.py                    NEW  follow_score + rank_plans (THE shared ordering)
    journal.py                 NEW  JournalStore, auto entries, tags, notes  → data/journal.json
    insights.py                NEW  weekly digest, edge decay report, top lessons
    snapshots.py               NEW  build/save/load data/analytics_snapshot.json
  performance.py               MOD  jsonio writes; log_trade carries plan metadata; close-hook → journal
  state.py                     MOD  jsonio writes
  account.py                   MOD  jsonio writes
  retrospective.py             MOD  daily recap gains calibration + decay lines
scripts/
  backfill_journal.py          NEW  journal entries for historical closed trades
  export_analytics.py          NEW  CSV/JSON export to exports/analytics/
tests/
  test_jsonio.py, test_metrics_equity.py, test_metrics_ratios.py, test_metrics_streaks.py,
  test_mfe_mae.py, test_aggregate.py, test_calibration.py, test_rank.py,
  test_journal.py, test_journal_tags.py, test_insights.py, test_snapshots.py,
  test_trade_metadata.py, test_analytics_perf.py
```

---

# Phase A0 — Safe persistence & prerequisites (Tasks A1–A4)

### Task A1: Prerequisite interface audit

**Files:**
- Modify: this plan document (Progress note only)

The plan-engine-v2 work defined `quality.py`, `plan_store.PlanStore`, `plan_manager.PlanManager` after this plan was written. Before any code, confirm the names this plan consumes.

- [ ] **Step 1: Verify imports and record actual names**

Run:
```
python -c "from swingbot.core.plan_engine import TradePlanV2, PlanStatus; from swingbot.core.registry import get_badge, load_registry; from swingbot.core import quality, plan_store, plan_manager; print('OK')"
```
Expected: `OK`.

- [ ] **Step 2: Confirm assumed signatures** — `PlanStore` exposes get-all/get-by-id/update (this plan calls them `all(status=None)`, `get(plan_id)`, `update(plan)`); trades.json v2 records carry two-leg keys (`legs` or per-leg exit fields per v2 Task 68). If any name differs, do NOT rename the engine — update the references in Tasks A12, A22, and the snapshot/journal tasks below, and note the mapping in the Progress block.

- [ ] **Step 3: Commit** — `docs: record plan-engine-v2 interface audit for analytics plan` (only if the doc changed).

### Task A2: Atomic JSON I/O

**Files:**
- Create: `swingbot/core/jsonio.py`
- Test: `tests/test_jsonio.py`

**Interfaces:**
- Produces: `atomic_write_json(path: str, obj) -> None` (writes `<path>.tmp`, `os.replace` onto path); `read_json(path: str, default)` (returns `default` on missing file or JSON decode error, logging a warning). Used by every store in this plan and by Tasks A3–A4 migrations.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_jsonio.py
import json, os
from swingbot.core.jsonio import atomic_write_json, read_json

def test_roundtrip(tmp_path):
    p = str(tmp_path / "x.json")
    atomic_write_json(p, {"a": 1})
    assert read_json(p, None) == {"a": 1}
    assert not os.path.exists(p + ".tmp")

def test_read_missing_returns_default(tmp_path):
    assert read_json(str(tmp_path / "nope.json"), []) == []

def test_read_corrupt_returns_default(tmp_path):
    p = str(tmp_path / "bad.json")
    with open(p, "w") as f:
        f.write("{truncated")
    assert read_json(p, {"d": True}) == {"d": True}
```

- [ ] **Step 2: Run `python -m pytest tests/test_jsonio.py -v` — expect FAIL (no module)**

- [ ] **Step 3: Implement**

```python
# swingbot/core/jsonio.py
"""Atomic JSON persistence: write to <path>.tmp then os.replace, so a crash
mid-write can never leave a torn file behind."""
import json
import logging
import os

log = logging.getLogger("swing-bot.jsonio")

def atomic_write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("read_json(%s) failed (%s); returning default", path, exc)
        return default
```

- [ ] **Step 4: Run tests — PASS. Step 5: Commit** — `feat: atomic JSON write layer (jsonio)`

### Task A3: TradeLog persists atomically

**Files:**
- Modify: `swingbot/core/performance.py` (`TradeLog._load` ~:173, `TradeLog._save` ~:182)
- Test: `tests/test_trade_metadata.py` (file created here, extended in A12)

- [ ] **Step 1: Failing test** — construct `TradeLog(path=tmp trades.json)`, `log_trade(...)` a minimal trade, then assert file parses and `path + ".tmp"` does not exist; corrupt the file, assert a fresh `TradeLog` starts with `[]` instead of raising.
- [ ] **Step 2: Replace the bodies of `_load`/`_save` with `read_json(self.path, [])` / `atomic_write_json(self.path, self.trades)`. Keep `_LOCK` usage untouched.**
- [ ] **Step 3: `python -m pytest tests/ -q` — full suite must stay green (TradeLog is widely used). Step 4: Commit** — `refactor: TradeLog reads/writes via jsonio`

### Task A4: StateStore + account persist atomically

**Files:**
- Modify: `swingbot/core/state.py` (`_save` ~:36), `swingbot/core/account.py` (its save path)
- Test: extend `tests/test_jsonio.py` with `test_statestore_atomic(tmp_path)`

- [ ] **Step 1: Failing test** — StateStore at tmp path: `set_last_trend`, assert no `.tmp` remains and reload returns the value.
- [ ] **Step 2: Swap `json.dump` bodies for `atomic_write_json`, `json.load` for `read_json` (defaults: `{}` state, account's existing self-healing default).**
- [ ] **Step 3: Full suite green. Step 4: Commit** — `refactor: state + account persistence via jsonio`

---

# Phase A1 — Metrics core (Tasks A5–A12)

All functions in `swingbot/core/analytics/metrics.py`, pure, typed docstrings. Package `__init__.py` created in Task A5 re-exporting each addition as it lands.

### Task A5: Equity curve

**Files:**
- Create: `swingbot/core/analytics/__init__.py`, `swingbot/core/analytics/metrics.py`
- Test: `tests/test_metrics_equity.py`

**Interfaces:**
- Produces: `equity_curve(closed: list[dict], starting_balance: float) -> dict` returning `{"points": [{"date": iso, "balance": float, "pnl": float}], "skipped_n": int}`. First point is `starting_balance` dated at the earliest `opened_at`; one point per close, ordered by `closed_at`; trades missing `realized_pnl_amount` are skipped and counted in `skipped_n`.

- [ ] **Step 1: Failing test**

```python
# tests/test_metrics_equity.py
from swingbot.core.analytics.metrics import equity_curve

def _t(closed_at, pnl, opened_at="2026-01-02T10:00:00+00:00"):
    return {"status": "win" if pnl >= 0 else "loss", "opened_at": opened_at,
            "closed_at": closed_at, "realized_pnl_amount": pnl}

def test_equity_curve_walks_balance():
    curve = equity_curve([_t("2026-01-05T10:00:00+00:00", 50.0),
                          _t("2026-01-03T10:00:00+00:00", -20.0)], 1000.0)
    pts = curve["points"]
    assert [p["balance"] for p in pts] == [1000.0, 980.0, 1030.0]  # sorted by close date
    assert curve["skipped_n"] == 0

def test_equity_curve_skips_unsized_trades():
    curve = equity_curve([{"status": "win", "closed_at": "2026-01-03T00:00:00+00:00",
                           "opened_at": "2026-01-02T00:00:00+00:00"}], 500.0)
    assert curve["skipped_n"] == 1 and len(curve["points"]) == 1
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement** (sort by `closed_at`, running sum; `date` = ISO date part of the timestamp; guard `realized_pnl_amount is None`).
- [ ] **Step 4: PASS. Step 5: Commit** — `feat: analytics equity_curve`

### Task A6: Drawdown

**Files:** Modify `metrics.py`; test `tests/test_metrics_equity.py`

**Interfaces:**
- Produces: `drawdown_series(points: list[dict]) -> list[dict]` — per equity point `{"date", "dd_pct"}` where `dd_pct = (peak - balance) / peak * 100` (≥ 0); `max_drawdown_pct(points) -> float | None` (None when < 2 points).

- [ ] **Step 1: Failing test** — balances `[1000, 1100, 990, 1200]` → dd `[0.0, 0.0, 10.0, 0.0]`, max 10.0; empty list → `max_drawdown_pct` None.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: analytics drawdown`

### Task A7: Win rate, expectancy, profit factor

**Files:** Modify `metrics.py`; test `tests/test_metrics_ratios.py`

**Interfaces:**
- Produces: `win_rate(closed) -> float | None`; `expectancy_r(closed) -> float | None`; `r_multiple(trade) -> float | None` (the single shared R computation: `(exit−entry)/(entry−stop)`, negated for bearish, None when stop distance is 0 or fields missing); `profit_factor(closed) -> float | None` (gross wins / |gross losses| over `realized_pnl_amount`; None when no losing amount).

- [ ] **Step 1: Failing test** — three fixture trades: bullish win entry 100 stop 95 exit 104 → r=0.8; bearish loss entry 100 stop 105 exit 106 → r=−1.2; expectancy = −0.2; win_rate = 50.0; profit_factor with pnl amounts +80/−40 → 2.0. Also `win_rate([])` is None.
- [ ] **Step 2–4: Implement (reuse `r_multiple` inside `expectancy_r`), PASS, commit** — `feat: analytics ratio metrics`

### Task A8: Streaks

**Files:** Modify `metrics.py`; test `tests/test_metrics_streaks.py`

**Interfaces:**
- Produces: `streaks(closed) -> dict` — `{"current": int, "current_kind": "win"|"loss"|None, "best_win_streak": int, "worst_loss_streak": int}` over win/loss trades sorted by `closed_at` (scratch/timeout/manual break a streak without starting one).

- [ ] **Step 1: Failing test** — sequence W W L W W W → current 3 win, best 3, worst 1; sequence with a `"closed"` (manual) between two wins → streak resets.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: analytics streaks`

### Task A9: R distribution + rolling win rate

**Files:** Modify `metrics.py`; test `tests/test_metrics_ratios.py`

**Interfaces:**
- Produces: `r_multiples(closed) -> list[float]` (via `r_multiple`, skipping None); `rolling_win_rate(closed, window: int = 20) -> list[dict]` — `{"date", "win_rate"}` per close over the trailing `window` win/loss trades, emitted only once ≥ 5 trades accumulated.

- [ ] **Step 1: Failing test** — 6 alternating W/L trades, window 4 → last point win_rate 50.0; fewer than 5 closed → empty list.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: analytics r distribution + rolling win rate`

### Task A10: Native Sharpe / Sortino

**Files:** Modify `metrics.py`; test `tests/test_metrics_ratios.py`

**Interfaces:**
- Produces: `sharpe(returns: list[float]) -> float | None`, `sortino(returns: list[float]) -> float | None` — per-trade (unannualized, matching `risk_metrics.py` convention), `mean/std(ddof=1)`; sortino divides by downside std; None when `len < 5` or std 0. `trade_return_pct(trade) -> float | None` mirroring `risk_metrics._trade_return_pct` so the two modules agree.

- [ ] **Step 1: Failing test** — returns `[1.0, 2.0, -1.0, 0.5, 1.5]`: assert `sharpe` ≈ 0.7 (compute expected with numpy in the test, don't hand-round); 4 returns → None.
- [ ] **Step 2–4: Implement with numpy, PASS, commit** — `feat: native sharpe/sortino (quantstats stays optional)`

### Task A11: MFE / MAE / exit efficiency

**Files:**
- Create: `swingbot/core/analytics/mfe_mae.py`
- Test: `tests/test_mfe_mae.py` (use `tests/conftest.py::make_ohlcv`)

**Interfaces:**
- Produces: `compute_mfe_mae(trade: dict, df: pd.DataFrame) -> dict | None` → `{"mfe_r": float, "mae_r": float, "exit_efficiency": float | None}`. Bars sliced `opened_at..closed_at` inclusive on the DatetimeIndex. Bullish: `mfe_r = (max(High) − entry)/risk`, `mae_r = max(0, (entry − min(Low))/risk)`; bearish mirrored. `risk = |entry − stop_loss|`; None if risk is 0, dates missing, or slice empty. `exit_efficiency = r_multiple(trade)/mfe_r` when `mfe_r > 0` else None, clamped to [−5, 1].

- [ ] **Step 1: Failing test**

```python
# tests/test_mfe_mae.py
from tests.conftest import make_ohlcv
from swingbot.core.analytics.mfe_mae import compute_mfe_mae

def test_bullish_mfe_mae():
    df = make_ohlcv([(100, 101, 99, 100), (100, 108, 98, 106), (106, 107, 103, 104)],
                    start="2026-03-02")
    t = {"direction": "bullish", "entry": 100.0, "stop_loss": 96.0, "exit_price": 104.0,
         "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-04T15:00:00+00:00",
         "status": "win"}
    m = compute_mfe_mae(t, df)
    assert m["mfe_r"] == 2.0          # (108-100)/4
    assert m["mae_r"] == 0.5          # (100-98)/4
    assert m["exit_efficiency"] == 0.5  # realized 1R of a 2R max move

def test_zero_risk_returns_none():
    df = make_ohlcv([100, 100])
    assert compute_mfe_mae({"entry": 100, "stop_loss": 100, "direction": "bullish",
                            "opened_at": "2026-03-02T00:00:00+00:00",
                            "closed_at": "2026-03-03T00:00:00+00:00"}, df) is None
```

- [ ] **Step 2–4: Implement, PASS, commit** — `feat: MFE/MAE + exit efficiency`

### Task A12: Trade records carry plan metadata

The v2 cutover posts plans with tier/badge/quality, but `performance.log_trade` (record dict at `performance.py:209`) doesn't persist them — so no aggregation by tier/badge is possible. Fix at the source.

**Files:**
- Modify: `swingbot/core/performance.py` (`log_trade` signature ~:186 and record dict ~:209), every `log_trade` caller (grep `log_trade(` — scan engine + plan_manager close path from v2 Task 70)
- Test: `tests/test_trade_metadata.py`

**Interfaces:**
- Produces: `log_trade(..., plan_id: str | None = None, tier: str | None = None, badge: str | None = None, quality_score: int | None = None, source: str | None = None)`; record keys `plan_id, tier, badge, quality_score, source` (None for legacy rows). Consumed by Tasks A14–A18 and Plans B/C.

- [ ] **Step 1: Failing test** — `log_trade(..., plan_id="p1", tier="A", badge="VALIDATED", quality_score=82, source="confluence")`, reload TradeLog from disk, assert all five keys persisted; log without them → keys present with None.
- [ ] **Step 2: Extend signature + record dict.**
- [ ] **Step 3: Thread the fields through every caller that has a `TradePlanV2` in hand (`plan.plan_id`, `plan.tier`, `plan.badge`, `plan.quality_score`, `plan.source`). Callers without a plan pass nothing.**
- [ ] **Step 4: Full suite green. Step 5: Commit** — `feat: trades.json rows carry plan pedigree (plan_id/tier/badge/quality/source)`

---

# Phase A2 — Aggregation & calibration (Tasks A13–A17)

### Task A13: StatRow + first dimension

**Files:**
- Create: `swingbot/core/analytics/aggregate.py`
- Test: `tests/test_aggregate.py`

**Interfaces:**
- Produces: `@dataclass StatRow: key: str; n: int; wins: int; losses: int; win_rate: float | None; expectancy_r: float | None; avg_r: float | None; profit_factor: float | None; total_pnl: float` and `stats_by(closed: list[dict], dimension: str) -> list[StatRow]` sorted by `n` desc. Dimension `"strategy"` groups on `primary_strategy_label(t)` (import from `performance`).

- [ ] **Step 1: Failing test** — 3 closed trades across 2 strategies; assert row count, per-row n/wins/win_rate, and that `total_pnl` sums `realized_pnl_amount` (0.0 when absent).
- [ ] **Step 2–4: Implement (delegates every ratio to `metrics.py` — no local formulas), PASS, commit** — `feat: StatRow aggregation (by strategy)`

### Task A14: All dimensions

**Files:** Modify `aggregate.py`; test `tests/test_aggregate.py`

**Interfaces:**
- Produces: `DIMENSIONS = ("strategy", "horizon", "tier", "badge", "confidence", "direction", "dow", "month", "ticker", "source")`; key extractors: `horizon`→`horizon_key`, `tier`/`badge`/`source`→A12 fields (`"unknown"` when None), `confidence`→`str(confidence_level)`, `dow`→Berlin weekday name of `closed_at`, `month`→`YYYY-MM` of `closed_at`. `stats_by` raises `ValueError` on unknown dimension.

- [ ] **Step 1: Failing test** — one trade with `tier="A"`, `badge="VALIDATED"`, closed on a known Monday: assert `stats_by(..., "tier")[0].key == "A"`, `"dow"` row key `"Monday"`, `"month"` key `"2026-03"`, and `ValueError` on `"nope"`.
- [ ] **Step 2–4: Implement extractor table, PASS, commit** — `feat: aggregation across all 10 dimensions`

### Task A15: Quality-score deciles

**Files:**
- Create: `swingbot/core/analytics/calibration.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Produces: `score_deciles(closed) -> list[dict]` — rows `{"decile": "0-9"…"90-100", "n", "win_rate", "expectancy_r"}` over closed trades with a non-None `quality_score`; empty deciles omitted. This is the live-trade twin of the offline `scripts/audit_quality_score.py` decile table.

- [ ] **Step 1: Failing test** — trades with scores 5, 55, 57, 95 → three rows; the 50s row aggregates 2 trades; win rates computed via `metrics.win_rate`.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: quality-score decile calibration`

### Task A16: Tier calibration

**Files:** Modify `calibration.py`; test `tests/test_calibration.py`

**Interfaces:**
- Produces: `tier_calibration(closed) -> list[dict]` — one row per tier A/B/C: `{"tier", "n", "win_rate", "expectancy_r", "expected_band"}` where `expected_band` is the fixed design intent `{"A": ">=80", "B": "70-80", "C": "<70"}`, and `"ok": bool` (None win_rate or n<10 → ok=None, meaning "insufficient data", not failure).

- [ ] **Step 1: Failing test** — 12 tier-A trades at 10W/2L → win_rate ≈83.3, ok True; 3 tier-B trades → ok None.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: tier calibration vs design bands`

### Task A17: Badge drift (edge decay)

**Files:** Modify `calibration.py`; test `tests/test_calibration.py`

**Interfaces:**
- Produces: `badge_drift(closed, registry_entries: list[dict]) -> list[dict]` — one row per VALIDATED registry strategy: `{"strategy", "oos_n", "oos_wr", "live_n", "live_wr", "delta_wr", "drift_alert": bool}`. **Pre-registered decay rule (do not tune after seeing live data): `drift_alert = live_n >= 20 and live_wr < oos_wr - 10.0`.** `registry_entries` is the parsed `validation_registry.json` list (caller loads via `registry.load_registry()`).

- [ ] **Step 1: Failing test** — registry row Fibonacci oos_wr 81.6; 25 live Fibonacci trades at 64% → `drift_alert` True; same at 78% → False; 10 trades at 40% → False (N floor).
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: badge drift / edge-decay detection`

---

# Phase A3 — The follow score (Task A18)

### Task A18: follow_score + rank_plans

The one shared answer to "which plan do I follow?". Plans B and C must import this — never re-rank locally.

**Files:**
- Create: `swingbot/core/analytics/rank.py`
- Test: `tests/test_rank.py`

**Interfaces:**
- Produces: `follow_score(plan, *, today: dt.date | None = None) -> float` (0–100) and `rank_plans(plans: list, *, today: dt.date | None = None) -> list` (desc by score, tie-break quality_score desc then ticker asc); `today` defaults to the current date, injectable for tests. Accepts `TradePlanV2` instances **or** dicts via an internal `_get(p, name, default=None)` (getattr → .get). Components (fixed weights, documented in the docstring):
  - badge: VALIDATED = 40, else 0
  - quality: `0.4 × quality_score` (0–40)
  - regime: 10 if `_get(p, "regime_aligned")` truthy else 0 (callers stamp this bool; scan engine knows regime)
  - freshness: `max(0, 10 − 2×age_days)` where age_days from `created_at` date vs the `today` param

- [ ] **Step 1: Failing test**

```python
# tests/test_rank.py
import datetime as dt
from swingbot.core.analytics.rank import follow_score, rank_plans

TODAY = dt.date(2026, 7, 11)

def test_validated_a_beats_weak_a():
    val = {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True,
           "created_at": "2026-07-11"}
    weak = dict(val, badge="WEAK")
    assert follow_score(val, today=TODAY) == 40 + 32 + 10 + 10  # 92.0
    assert follow_score(weak, today=TODAY) == 52.0
    assert rank_plans([weak, val], today=TODAY)[0] is val

def test_stale_plan_loses_freshness():
    p = {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True,
         "created_at": "2026-07-01"}
    assert follow_score(p, today=TODAY) == 82.0  # freshness floor 0
```

- [ ] **Step 2–4: Implement, PASS, commit** — `feat: shared follow_score plan ranking`

---

# Phase A4 — Lessons journal (Tasks A19–A24)

### Task A19: JournalStore

**Files:**
- Create: `swingbot/core/analytics/journal.py`
- Test: `tests/test_journal.py`

**Interfaces:**
- Produces: `JournalStore(path: str | None = None)` (default `config.DATA_DIR/journal.json`, list-of-dicts via `jsonio`); methods `add(entry: dict) -> dict` (stamps `created_at`, dedups on `trade_id` by replacing), `get(trade_id) -> dict | None`, `entries(*, strategy=None, tag=None, outcome=None, since=None) -> list[dict]` (newest first), `set_note(trade_id, note: str) -> bool`. Module-level `_LOCK = threading.Lock()` around mutations, matching house pattern.

- [ ] **Step 1: Failing test** — add two entries, filter by tag and strategy, `set_note` roundtrips through a fresh store instance (disk persistence), re-`add` same trade_id replaces not duplicates.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: lessons JournalStore`

### Task A20: Auto entry builder

**Files:** Modify `journal.py`; test `tests/test_journal.py`

**Interfaces:**
- Produces: `build_entry(trade: dict, df: pd.DataFrame | None) -> dict` with exact keys: `trade_id, ticker, strategy, horizon_key, direction, tier, badge, quality_score, outcome` (=status/close reason), `r_realized` (via `metrics.r_multiple`), `mfe_r, mae_r, exit_efficiency` (via `compute_mfe_mae`, None-safe when df is None), `holding_days, tags` (Task A21, `[]` until then), `auto_lesson` (str), `note` (""), `opened_at, closed_at`.
- `auto_lesson` rules (exact, in priority order, first match wins):
  1. loss with `mae_r` ≤ 0.3 and `mfe_r` ≥ 1.0 → `"Trade went {mfe_r:.1f}R in favor before stopping out — exit management, not entry, cost this one."`
  2. win with `exit_efficiency` ≥ 0.8 → `"Clean capture: banked {eff:.0%} of the available move."`
  3. loss with `mae_r` ≥ 1.0 immediately (mfe_r < 0.2) → `"Entry was wrong from the first bar — review the trigger, not the exit."`
  4. scratch/timeout → `"No follow-through within the horizon — count it as rent, not error."`
  5. fallback → `"Outcome {outcome} at {r_realized:+.2f}R."`

- [ ] **Step 1: Failing test** — one fixture trade per rule 1/2/4 + fallback, assert the exact lesson strings and that `df=None` yields `mfe_r=None` without raising.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: auto journal entries with lesson templates`

### Task A21: Auto-tag rules

**Files:** Modify `journal.py`; test `tests/test_journal_tags.py`

**Interfaces:**
- Produces: `tags_for(trade: dict, m: dict | None) -> list[str]` wired into `build_entry`. Exact rules:
  - close reason contains `runner_tp2 | runner_trail | runner_be` → that string as tag
  - `"gap_fill"`: `exit_price` beyond stop (loss) or target (win) by > 0.5% of entry
  - `"near_miss_tp"`: outcome loss/scratch and `m["mfe_r"] >= 0.8 × tp1_r` where `tp1_r = |take_profit − entry| / |entry − stop_loss|`
  - `"fast_win"`: win with `holding_days <= 2`
  - `"slow_burn"`: `holding_days > 30`
  - `"weak_source"`: `badge == "WEAK"`

- [ ] **Step 1: Failing test** — table-driven: five fixture trades, assert exact tag lists (order = rule order above).
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: journal auto-tagging`

### Task A22: Journal on every close

**Files:**
- Modify: `swingbot/core/performance.py` (`update_open_trades` ~:307, `close_if_live_price_hit` ~:665, `close_trade_manual` ~:608), plan_manager close path (v2 Task 62–66 call sites)
- Test: `tests/test_journal.py`

**Interfaces:**
- Produces: module function `journal_trade_close(trade: dict) -> None` in `journal.py` — fetches daily bars via `swingbot.core.data.get_daily_data(ticker)` inside try/except (journal failure must NEVER break a close; log warning), builds + adds entry. Called with each newly-closed trade dict from the four close paths.

- [ ] **Step 1: Failing test** — monkeypatch `get_daily_data` to return a `make_ohlcv` frame; call `journal_trade_close(trade)`; assert JournalStore has the entry. Second test: `get_history` raises → no exception propagates, no entry added.
- [ ] **Step 2: Implement + wire the four call sites (one line each, after the close is persisted).**
- [ ] **Step 3: Full suite green. Step 4: Commit** — `feat: auto journal entry on every trade close`

### Task A23: Manual notes API

**Files:** Modify `journal.py` (already has `set_note`); test `tests/test_journal.py`

**Interfaces:**
- Produces: `set_note` returns False for unknown trade_id (tested), and `entries(has_note=True)` filter for the browsers in Plans B/C.

- [ ] **Step 1: Failing test** — `set_note("missing", "x") is False`; add entry, set note, `entries(has_note=True)` returns exactly it.
- [ ] **Step 2–4: Implement filter, PASS, commit** — `feat: journal manual notes + has_note filter`

### Task A24: Historical backfill script

**Files:**
- Create: `scripts/backfill_journal.py`
- Test: `tests/test_journal.py` (function-level test on its `backfill(trades, store, fetch)` core)

**Interfaces:**
- Produces: CLI `python scripts/backfill_journal.py [--dry-run]` — iterates all closed trades in trades.json lacking a journal entry, builds entries (bars via `data.get_daily_data`, cached-CSV fallback `data/backtest_cache/{TICKER}.csv`), prints `backfilled N, skipped M`. Core logic in a testable `backfill(trades, store, fetch_fn) -> tuple[int, int]`.

- [ ] **Step 1: Failing test** — two closed trades, one already journaled → `backfill` returns `(1, 1)`.
- [ ] **Step 2–4: Implement, PASS, run once for real (`python scripts/backfill_journal.py`), commit** — `feat: journal backfill script`

---

# Phase A5 — Insights & retrospective v2 (Tasks A25–A27)

### Task A25: Weekly digest

**Files:**
- Create: `swingbot/core/analytics/insights.py`
- Test: `tests/test_insights.py`

**Interfaces:**
- Produces: `weekly_digest(entries: list[dict], closed: list[dict], today: dt.date) -> list[str]` — Discord-ready messages (≤1900 chars each) covering the trailing 7 days: headline (n / WR / expectancy / P&L), best & worst trade with their `auto_lesson`, tag frequency top-3, tier calibration one-liner, and up to 3 `note` excerpts. Pure function; posting happens in Plan B.

- [ ] **Step 1: Failing test** — fixture week of 4 entries/closed trades: assert headline contains `"WR 75"` style figures, worst trade's lesson string present, every message under 1900 chars.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: weekly lessons digest`

### Task A26: Edge-decay report + top lessons

**Files:** Modify `insights.py`; test `tests/test_insights.py`

**Interfaces:**
- Produces: `edge_decay_report(closed) -> list[str]` — human lines from `calibration.badge_drift` (loads registry via `registry.load_registry()` at this layer, keeping calibration pure), only alerting rows; empty list when no alerts. `top_lessons(entries, n=5) -> list[str]` — most frequent (auto_lesson template id, tag) pairings with counts.

- [ ] **Step 1: Failing test** — drift fixture producing one alert → one line containing strategy name and both WR figures; no-alert fixture → `[]`.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: edge decay report + top lessons`

### Task A27: Retrospective v2 integration

**Files:**
- Modify: `swingbot/core/retrospective.py` (`build_daily_retrospective` ~:261, `_analyse` ~:522)
- Test: `tests/test_insights.py`

**Interfaces:**
- Consumes: `edge_decay_report`, `tier_calibration`, JournalStore entries for today's closed trades.
- Produces: daily recap gains (a) a `📐 Calibration` line when any tier has `ok=False`, (b) `📉 Edge decay` lines from `edge_decay_report`, (c) each closed-trade line appends its journal `auto_lesson`. Existing rule engine and history persistence untouched.

- [ ] **Step 1: Failing test** — feed `build_daily_retrospective` a day with one decay alert (monkeypatched registry) → output contains the decay line; day without → doesn't.
- [ ] **Step 2–4: Implement, run full suite (retrospective has existing behavior — keep its tests green), commit** — `feat: retrospective consumes calibration + journal`

---

# Phase A6 — Snapshots, export, wrap-up (Tasks A28–A31)

### Task A28: Analytics snapshot build/save/load

**Files:**
- Create: `swingbot/core/analytics/snapshots.py`
- Test: `tests/test_snapshots.py`

**Interfaces:**
- Produces: `build_snapshot(closed: list[dict], starting_balance: float, registry_entries: list[dict]) -> dict` with exact top-level keys: `built_at` (ISO), `overall` (n, wins, losses, win_rate, expectancy_r, profit_factor, sharpe, sortino, max_drawdown_pct, total_pnl, streaks), `equity_curve`, `drawdown`, `rolling_wr`, `by` (`{dimension: [StatRow-as-dict]}` for all 10 dimensions), `calibration` (`{deciles, tiers, drift}`), `r_multiples` (histogram-ready list). `save_snapshot(snap, path=None)` / `load_snapshot(path=None, max_age_seconds=3600) -> dict | None` (None when missing or `built_at` older than max_age) → `data/analytics_snapshot.json` via `jsonio`.

- [ ] **Step 1: Failing test** — build from 5 fixture trades: assert every documented key exists, `by` has all 10 dimensions, load-after-save roundtrips, stale `built_at` → None.
- [ ] **Step 2–4: Implement (pure assembly of Phase A1/A2 functions), PASS, commit** — `feat: analytics snapshot`

### Task A29: Snapshot refresh wiring

**Files:**
- Modify: scan loop end-of-scan hook (`swingbot/commands/scanning.py` — the `@tasks.loop` scan cycle at :362, after alert dispatch) and the close paths already touched in A22
- Test: `tests/test_snapshots.py`

**Interfaces:**
- Produces: `refresh_snapshot() -> None` in `snapshots.py` — assembles inputs (TradeLog closed trades, `account` starting balance, `load_registry()`) and saves; wrapped in try/except-log like the journal hook. Called after each scan cycle and after each batch of closes. Cheap by design (pure recompute over in-memory list).

- [ ] **Step 1: Failing test** — monkeypatch TradeLog/registry, call `refresh_snapshot()`, assert file written; make TradeLog raise → no exception escapes.
- [ ] **Step 2–4: Wire both call sites, PASS, commit** — `feat: snapshot refresh on scan + close`

### Task A30: Analytics export

**Files:**
- Create: `scripts/export_analytics.py`
- Test: `tests/test_snapshots.py` (core `export_all(snapshot, out_dir) -> list[str]`)

**Interfaces:**
- Produces: CLI `python scripts/export_analytics.py [--out exports/analytics]` writing `snapshot.json` (verbatim), `stats_by_<dimension>.csv` (one per dimension, StatRow columns), `equity_curve.csv`, `journal.csv` (all entries). Returns/prints written paths.

- [ ] **Step 1: Failing test** — `export_all(fixture_snapshot, tmp_path)` → files exist, `stats_by_strategy.csv` header row `key,n,wins,losses,win_rate,expectancy_r,avg_r,profit_factor,total_pnl`.
- [ ] **Step 2–4: Implement with `csv.DictWriter`, PASS, commit** — `feat: analytics CSV/JSON export`

### Task A31: Performance benchmark + phase checkpoint

**Files:**
- Test: `tests/test_analytics_perf.py`
- Modify: `README.md` (Analytics section), plan Progress block

- [ ] **Step 1: Benchmark test** — generate 5,000 synthetic closed trades (list comp, no I/O), assert `build_snapshot` completes in < 2.0 s (`time.perf_counter`, generous bound so CI noise doesn't flake).
- [ ] **Step 2: Run everything:** `python -m pytest tests/ -q` and `make check` — green; `python scripts/export_analytics.py` produces files.
- [ ] **Step 3: README section** documenting the package layout, snapshot file, journal file, follow_score formula, and the pre-registered drift rule.
- [ ] **Step 4: Commit** — `docs: analytics core wrap-up + perf benchmark`. Update Progress block. **Plan A done — Plans B and C may start.**
