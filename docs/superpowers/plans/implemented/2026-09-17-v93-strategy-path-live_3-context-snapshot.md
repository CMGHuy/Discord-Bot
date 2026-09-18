# Strategy path goes live — Part 3: Phase 2 (entry-context snapshot)

Index, header block, global constraints and the parallelisation map: `2026-09-17-v93-strategy-path-live_0-index.md`. Spec: `docs/superpowers/specs/2026-09-17-v93-strategy-path-live-design.md` (§3).

**Must not run beside Phase 1a Group A** — Task 20 edits `analyze.py` and `strategy_pass.py`.

# Phase 2 — Entry-context snapshot

### Task 16: `edge/context.py` — `entry_context` with the truncation test

**Files:**
- Create: `swingbot/core/edge/context.py`
- Test: `tests/edge/test_entry_context.py`

**Interfaces:**
- Consumes: `indicators.atr(df, period)`, `indicators.rsi(series, period)`, `indicators.adx(df, period)`, `indicators.ema(series, period)`; `gates.gap_stats(df)`, `gates.stop_beyond_gap_noise(stop_pct, p90)`; `strategy_types.HORIZONS[hk]["fib_lookback"]`.
- Produces: `entry_context(df, *, direction, horizon_key, stop, target, asof=None) -> dict` with exactly the keys `FEATURE_KEYS`; `HTF_EMA_PERIOD` (equal to `scanning.regime._HTF_EMA_PERIOD`).

- [ ] **Step 1: Write the failing tests**

`tests/edge/test_entry_context.py`:

```python
import json
import math

import numpy as np
import pytest

from swingbot.core.edge import context as ctx
from tests.helpers import make_ohlcv


def _df(n=400, seed=3):
    rng = np.random.RandomState(seed)
    closes = 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, n))
    rows = []
    for c in closes:
        rows.append((c * (1 + rng.normal(0, 0.003)), c * 1.01, c * 0.99, c))
    return make_ohlcv(rows, start="2024-06-03", volume=1_000_000)


def test_keys_are_fixed_and_json_serialisable():
    df = _df()
    out = ctx.entry_context(df, direction="bullish", horizon_key="3m", stop=df["Close"].iloc[-1] * 0.95,
                            target=df["Close"].iloc[-1] * 1.10,
                            asof={"regime2_state": "bull_quiet", "rs_pctile": 71.0, "sector_pctile": 60.0, "rs_combined": 67.7})
    assert set(out) == set(ctx.FEATURE_KEYS)
    json.dumps(out)                                   # plain numbers/strings/None only
    assert out["direction"] == "bullish" and out["horizon_key"] == "3m"
    assert out["regime2_state"] == "bull_quiet" and out["rs_combined"] == 67.7
    assert out["planned_rr"] == pytest.approx(2.0, rel=1e-6)
    assert out["stop_pct"] == pytest.approx(5.0, rel=1e-6)
    assert 0.0 <= out["atr_pctile_250"] <= 100.0
    assert 0.0 <= out["bb_width_pctile_250"] <= 100.0
    assert out["dow"] == df.index[-1].dayofweek


def test_truncation_no_lookahead():
    """architecture.md: the vector at bar i from the full frame equals the
    vector from the frame cut at i -- for every i past warm-up."""
    df = _df()
    for i in range(300, len(df), 17):
        full = ctx.entry_context(df.iloc[: i + 1], direction="bearish", horizon_key="4w",
                                 stop=df["Close"].iloc[i] * 1.04, target=df["Close"].iloc[i] * 0.92)
        trunc = ctx.entry_context(df.iloc[: i + 1].copy(), direction="bearish", horizon_key="4w",
                                  stop=df["Close"].iloc[i] * 1.04, target=df["Close"].iloc[i] * 0.92)
        assert full == trunc
    # and no feature at bar i changes when later bars are appended
    base = ctx.entry_context(df.iloc[:350], direction="bullish", horizon_key="2m", stop=90.0, target=120.0)
    again = ctx.entry_context(df.iloc[:350], direction="bullish", horizon_key="2m", stop=90.0, target=120.0)
    assert base == again


def test_short_frame_yields_none_not_defaults():
    df = _df(n=30)
    out = ctx.entry_context(df, direction="bullish", horizon_key="9m", stop=95.0, target=110.0)
    assert out["atr_pctile_250"] is None and out["bb_width_pctile_250"] is None
    assert out["htf_aligned"] is None                  # 200-EMA needs 210 bars
    assert out["adx_14"] is None or isinstance(out["adx_14"], float)
    assert out["regime2_state"] is None and out["rs_pctile"] is None


def test_htf_alignment_direction_aware():
    up = make_ohlcv([100 + i for i in range(400)], start="2024-06-03")
    assert ctx.entry_context(up, direction="bullish", horizon_key="3m", stop=490.0, target=520.0)["htf_aligned"] is True
    assert ctx.entry_context(up, direction="bearish", horizon_key="3m", stop=510.0, target=480.0)["htf_aligned"] is False


def test_htf_period_map_matches_regime_module():
    from swingbot.core.scanning.regime import _HTF_EMA_PERIOD
    assert ctx.HTF_EMA_PERIOD == _HTF_EMA_PERIOD


def test_gap_fragility_flag():
    df = _df()
    close = df["Close"].iloc[-1]
    tight = ctx.entry_context(df, direction="bullish", horizon_key="2w", stop=close * 0.999, target=close * 1.05)
    wide = ctx.entry_context(df, direction="bullish", horizon_key="2w", stop=close * 0.90, target=close * 1.20)
    assert tight["gap_fragile"] is True and wide["gap_fragile"] is False
    assert tight["gap_p90_pct"] == wide["gap_p90_pct"] > 0


def test_nan_inputs_become_none():
    df = _df()
    df.loc[df.index[-1], "Volume"] = float("nan")
    out = ctx.entry_context(df, direction="bullish", horizon_key="2w", stop=90.0, target=120.0)
    assert out["vol_ratio_20"] is None
    assert not any(isinstance(v, float) and math.isnan(v) for v in out.values())
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/edge/test_entry_context.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`swingbot/core/edge/context.py`:

```python
"""v93: the entry-context snapshot -- one feature function, three stamp sites.

Every input is the entry bar or earlier (NO-LOOKAHEAD, architecture.md). A
feature that cannot be computed yet is None, never a default that looks
like a measurement. Cross-sectional values (regime2 state, RS percentiles)
are passed in through `asof` by callers that already hold them as-of the
bar -- this module never reaches for the universe itself.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from swingbot.core.edge.gates import gap_stats, stop_beyond_gap_noise
from swingbot.core.market.indicators import adx, atr, ema, rsi
from swingbot.core.market.strategy_types import HORIZONS

# Same map scanning/regime.get_htf_bias uses; duplicated here (and pinned by
# a test) because get_htf_bias returns None whenever HTF_CONFLUENCE_ENABLED
# is off, and a feature must not disappear with a display flag.
HTF_EMA_PERIOD = {
    "2w": 50, "4w": 50, "2m": 50,
    "3m": 200, "4m": 200, "5m": 200, "6m": 200, "7m": 200, "8m": 200, "9m": 200,
}

PCTILE_WINDOW = 250
PCTILE_MIN_OBS = 60
ASOF_KEYS = ("regime2_state", "rs_pctile", "sector_pctile", "rs_combined")

FEATURE_KEYS = (
    # geometry
    "stop_atr", "stop_pct", "planned_rr", "swing_high_atr", "swing_low_atr", "horizon_key", "direction",
    # ticker state at the bar
    "atr_pctile_250", "vol_ratio_20", "rsi_14", "adx_14", "bb_width_pctile_250",
    "htf_aligned", "gap_p90_pct", "gap_fragile", "dow",
    # cross-sectional, as-of, passed in
    *ASOF_KEYS,
)


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else round(v, 6)


def _pct_rank_last(series: pd.Series, window: int = PCTILE_WINDOW) -> float | None:
    tail = series.iloc[-window:].dropna()
    if len(tail) < PCTILE_MIN_OBS:
        return None
    last = tail.iloc[-1]
    return _num(100.0 * float((tail <= last).mean()))


def entry_context(df: pd.DataFrame, *, direction: str, horizon_key: str,
                  stop: float, target: float, asof: dict | None = None) -> dict:
    out: dict = {k: None for k in FEATURE_KEYS}
    out["direction"], out["horizon_key"] = direction, horizon_key
    if df is None or len(df) < 20:
        return out
    close = float(df["Close"].iloc[-1])
    atr_s = atr(df, 14)
    atr_v = _num(atr_s.iloc[-1])
    risk = abs(close - float(stop))
    reward = abs(float(target) - close)

    out["stop_pct"] = _num(risk / close * 100.0) if close else None
    out["planned_rr"] = _num(reward / risk) if risk > 0 else None
    if atr_v:
        out["stop_atr"] = _num(risk / atr_v)
        lb = HORIZONS[horizon_key]["fib_lookback"]
        if len(df) >= lb:
            hi = float(df["High"].iloc[-lb:].max()); lo = float(df["Low"].iloc[-lb:].min())
            out["swing_high_atr"] = _num((hi - close) / atr_v)
            out["swing_low_atr"] = _num((close - lo) / atr_v)
        out["atr_pctile_250"] = _pct_rank_last(atr_s / df["Close"])

    vol_avg = df["Volume"].rolling(20).mean().iloc[-1]
    out["vol_ratio_20"] = _num(df["Volume"].iloc[-1] / vol_avg) if vol_avg and not math.isnan(vol_avg) else None
    out["rsi_14"] = _num(rsi(df["Close"], 14).iloc[-1])
    out["adx_14"] = _num(adx(df, 14).iloc[-1]) if len(df) >= 30 else None

    ma20 = df["Close"].rolling(20).mean(); sd20 = df["Close"].rolling(20).std()
    out["bb_width_pctile_250"] = _pct_rank_last((4.0 * sd20 / ma20))

    period = HTF_EMA_PERIOD.get(horizon_key)
    if period is not None and len(df) >= period + 10:
        e = float(ema(df["Close"], period).iloc[-1])
        out["htf_aligned"] = bool(close > e) if direction == "bullish" else bool(close < e)

    g = gap_stats(df)
    if g["n"] > 0:
        out["gap_p90_pct"] = _num(g["p90_gap_pct"])
        if out["stop_pct"] is not None:
            out["gap_fragile"] = not stop_beyond_gap_noise(out["stop_pct"], g["p90_gap_pct"])

    out["dow"] = int(df.index[-1].dayofweek)

    for k in ASOF_KEYS:
        v = (asof or {}).get(k)
        out[k] = v if k == "regime2_state" else _num(v)
    return out
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/edge/test_entry_context.py`
Expected: green. If `test_gap_fragility_flag` fails because the synthetic opens gap less than 0.1 % at the 90th percentile, widen the fixture's open noise (`rng.normal(0, 0.006)`), not the assertion.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/context.py tests/edge/test_entry_context.py
git commit -m "feat(v93): edge/context.entry_context -- no-lookahead entry snapshot with truncation test"
```

---

### Task 17: `stamp_entry_context`, the `entry_context` plan/trade/journal fields

**Files:**
- Modify: `swingbot/core/planning/params.py` (after `stamp_cohort`)
- Modify: `swingbot/core/planning/plan_types.py` (add field)
- Modify: `swingbot/core/tracking/performance.py` (`log_trade` kw + record key)
- Modify: `swingbot/core/analytics/journal.py` (`build_entry`)
- Modify: `swingbot/core/scanning/scan_run.py` (the `trade_log.log_trade(...)` call in the alert loop: pass `entry_context`)
- Test: `tests/planning/test_entry_context_stamp.py`, `tests/analytics/test_journal_entry_context.py`

**Interfaces:**
- Consumes: `context.entry_context` (Task 16).
- Produces: `params.stamp_entry_context(plan, df, asof: dict | None) -> None` (sets `plan.entry_context`); `TradePlanV2.entry_context: dict`; `log_trade(..., entry_context=None)` → `record["entry_context"]`; journal rows carry `entry_context`.

- [ ] **Step 1: Write the failing tests**

`tests/planning/test_entry_context_stamp.py`:

```python
from swingbot.core.planning.params import stamp_entry_context
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_from_dict, plan_to_dict
from swingbot.core.edge.context import FEATURE_KEYS
from tests.helpers import make_ohlcv


def _plan():
    return TradePlanV2(plan_id="p", ticker="AAPL", created_at="2026-09-17", source="strategy",
                       strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
                       trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=95.0, tp1=110.0,
                       tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
                       quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.PENDING)


def test_stamp_sets_full_vector_and_round_trips():
    df = make_ohlcv([100 + i * 0.1 for i in range(400)], start="2024-06-03")
    p = _plan()
    assert p.entry_context == {}
    stamp_entry_context(p, df, {"regime2_state": "bull_quiet", "rs_pctile": 55.0})
    assert set(p.entry_context) == set(FEATURE_KEYS)
    assert p.entry_context["regime2_state"] == "bull_quiet"
    assert plan_from_dict(plan_to_dict(p)).entry_context == p.entry_context


def test_stamp_never_raises(monkeypatch):
    from swingbot.core.planning import params
    monkeypatch.setattr(params, "entry_context", lambda *a, **k: 1 / 0)
    p = _plan()
    stamp_entry_context(p, None, None)
    assert p.entry_context == {}
```

`tests/analytics/test_journal_entry_context.py`:

```python
from swingbot.core.analytics.journal import build_entry


def test_journal_entry_carries_entry_context():
    trade = {"id": "t1", "ticker": "AAPL", "status": "win", "entry": 100.0, "stop_loss": 95.0,
             "exit_price": 110.0, "direction": "bullish", "opened_at": "2026-09-10T10:00:00+00:00",
             "closed_at": "2026-09-12T10:00:00+00:00", "entry_context": {"rsi_14": 41.2}}
    assert build_entry(trade, None)["entry_context"] == {"rsi_14": 41.2}
    trade.pop("entry_context")
    assert build_entry(trade, None)["entry_context"] == {}
```

Also append to `tests/tracking/test_ledger_stats.py`:

```python
def test_log_trade_records_entry_context(log):
    tid = log.log_trade(ticker="AAPL", strategy="MACD", horizon_key="3m", direction="bullish",
                        confidence_level=None, confidence_label="x", entry=100.0, stop_loss=95.0,
                        take_profit=110.0, entry_context={"rsi_14": 40.0})
    assert log.get_trade(tid)["entry_context"] == {"rsi_14": 40.0}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/planning/test_entry_context_stamp.py tests/analytics/test_journal_entry_context.py -v`
Expected: FAIL (`ImportError: stamp_entry_context`; `KeyError: 'entry_context'`)

- [ ] **Step 3: Implement**

`plan_types.py`: after `first_seen_price` add
```python
    entry_context: dict = field(default_factory=dict)   # v93: edge/context.entry_context at creation
```

`params.py`: add `from swingbot.core.edge.context import entry_context` at the top and, after `stamp_cohort`:
```python
def stamp_entry_context(plan: TradePlanV2, df, asof: dict | None) -> None:
    """v93. Frame is the caller's no-lookahead slice (live: the frame it
    scanned; replay/backtest: df.iloc[:i+1]). Never raises: a snapshot
    failure leaves {} and the plan still posts."""
    try:
        plan.entry_context = entry_context(df, direction=plan.direction, horizon_key=plan.horizon_key,
                                           stop=plan.stop_loss, target=plan.tp1, asof=asof)
    except Exception:
        log.warning("entry_context stamping failed for %s/%s -- left empty", plan.ticker, plan.horizon_key,
                    exc_info=True)
        plan.entry_context = {}
```
(if `params.py` has no `log`, add `import logging; log = logging.getLogger(__name__)`.)

`performance.py`: `log_trade(..., ledger=None, entry_context=None)`; in `record` after `"ledger"` add `"entry_context": entry_context or {},   # v93`.

`journal.py`, `build_entry`: after `"risk_features": ...` add `"entry_context": trade.get("entry_context") or {},`.

`scan_run.py`, in the alert loop's `trade_log.log_trade(...)` call, add `entry_context=plan_v2.entry_context if plan_v2 is not None else None,` and `ledger=plan_v2.ledger if plan_v2 is not None else None,` (confluence plans default to `main`).

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_entry_context_stamp.py`, `... tests/analytics/test_journal_entry_context.py`, `... tests/tracking/test_ledger_stats.py`, `... tests/analytics/test_journal.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/params.py swingbot/core/planning/plan_types.py swingbot/core/tracking/performance.py swingbot/core/analytics/journal.py swingbot/core/scanning/scan_run.py tests/planning/test_entry_context_stamp.py tests/analytics/test_journal_entry_context.py tests/tracking/test_ledger_stats.py
git commit -m "feat(v93): stamp_entry_context; entry_context on plans, trade records and journal rows"
```

---

### Task 18: Backtest stamp site + the as-of cross-sectional builder

**Files:**
- Create: `swingbot/core/backtesting/asof_context.py`
- Modify: `swingbot/core/backtesting/backtest.py` (`BacktestTrade`, `run_backtest`, `run_backtest_daterange`)
- Test: `tests/backtesting/test_asof_context.py`, `tests/backtesting/test_backtest_context.py`

**Interfaces:**
- Consumes: `factors.RS_WINDOW`, `factors.relative_return`, `factors.rs_percentile`, `factors.rs_score`, `regime2.regime_series`.
- Produces: `asof_context.build_asof(frames: dict[str, DataFrame], spy_df, *, sector_of_ticker: dict, sector_etf_frames: dict, sector_of_etf: dict) -> dict[str, DataFrame]` (per ticker, indexed by that ticker's dates, columns `regime2_state, rs_pctile, sector_pctile, rs_combined`); `asof_context.asof_row(asof_df, ts) -> dict`; `BacktestTrade.context: dict | None = None`; `run_backtest(..., asof=None)` and `run_backtest_daterange(..., asof=None)`.

- [ ] **Step 1: Write the failing tests**

`tests/backtesting/test_asof_context.py`:

```python
import numpy as np
import pandas as pd

from swingbot.core.backtesting import asof_context as ac
from swingbot.core.edge import factors
from tests.helpers import make_ohlcv


def _universe(seed=1, n=300):
    rng = np.random.RandomState(seed)
    frames = {}
    for i, sym in enumerate(["AAA", "BBB", "CCC", "DDD"]):
        closes = 100 * np.cumprod(1 + rng.normal(0.0002 * (i + 1), 0.01, n))
        frames[sym] = make_ohlcv(list(closes), start="2024-01-02")
    spy = make_ohlcv(list(100 * np.cumprod(1 + rng.normal(0.0003, 0.008, n))), start="2024-01-02")
    etfs = {"XLK": make_ohlcv(list(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))), start="2024-01-02"),
            "XLF": make_ohlcv(list(100 * np.cumprod(1 + rng.normal(0.0001, 0.01, n))), start="2024-01-02")}
    sector_of_ticker = {"AAA": "Technology", "BBB": "Technology", "CCC": "Financials"}   # DDD unmapped
    sector_of_etf = {"XLK": "Technology", "XLF": "Financials"}
    return frames, spy, etfs, sector_of_ticker, sector_of_etf


def test_last_bar_matches_point_in_time_rs_percentile():
    frames, spy, etfs, sot, soe = _universe()
    asof = ac.build_asof(frames, spy, sector_of_ticker=sot, sector_etf_frames=etfs, sector_of_etf=soe)
    rels = [factors.relative_return(f, spy) for f in frames.values()]
    for sym, df in frames.items():
        expected = factors.rs_percentile(df, spy, universe_rels=rels)
        assert asof[sym]["rs_pctile"].iloc[-1] == expected


def test_sector_and_combined():
    frames, spy, etfs, sot, soe = _universe()
    asof = ac.build_asof(frames, spy, sector_of_ticker=sot, sector_etf_frames=etfs, sector_of_etf=soe)
    exp_sector = factors.sector_rs_percentile("Technology", etfs, spy, sector_of_etf=soe)
    assert asof["AAA"]["sector_pctile"].iloc[-1] == exp_sector
    assert asof["AAA"]["rs_combined"].iloc[-1] == factors.rs_score(asof["AAA"]["rs_pctile"].iloc[-1], exp_sector)
    assert np.isnan(asof["DDD"]["sector_pctile"].iloc[-1])
    assert asof["DDD"]["rs_combined"].iloc[-1] == asof["DDD"]["rs_pctile"].iloc[-1]


def test_regime_column_and_warmup_nans():
    frames, spy, etfs, sot, soe = _universe()
    asof = ac.build_asof(frames, spy, sector_of_ticker=sot, sector_etf_frames=etfs, sector_of_etf=soe)
    col = asof["AAA"]["regime2_state"]
    assert set(col.dropna().unique()) <= {"bull_quiet", "bull_volatile", "bear_quiet", "bear_volatile"}
    assert np.isnan(asof["AAA"]["rs_pctile"].iloc[: factors.RS_WINDOW]).all()


def test_asof_row_converts_nan_to_none_and_missing_date_to_empty():
    frames, spy, etfs, sot, soe = _universe()
    asof = ac.build_asof(frames, spy, sector_of_ticker=sot, sector_etf_frames=etfs, sector_of_etf=soe)
    early = ac.asof_row(asof["AAA"], asof["AAA"].index[5])
    assert early["rs_pctile"] is None and set(early) == {"regime2_state", "rs_pctile", "sector_pctile", "rs_combined"}
    assert ac.asof_row(asof["AAA"], pd.Timestamp("1999-01-01")) == {}
    assert ac.asof_row(None, asof["AAA"].index[-1]) == {}
```

`tests/backtesting/test_backtest_context.py`:

```python
import numpy as np
import pandas as pd

import swingbot.core.backtesting.backtest as bt
from swingbot.core.edge.context import FEATURE_KEYS
from tests.conftest import make_ohlcv


def _forced(monkeypatch, df, bar, **kw):
    bull = pd.Series(False, index=df.index); bear = pd.Series(False, index=df.index)
    bull.iloc[bar] = True
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *a, **k: (bull, bear))
    return bt.run_backtest("TEST", df, "EMA Crossover", "2w", **kw)


def test_v1_and_v2_trades_carry_context(monkeypatch):
    closes = np.full(120, 100.0); closes[81:] = 104.0
    df = make_ohlcv(closes, spread_pct=1.0)
    for kw in ({"exit_model": "v1"}, {"exit_model": "v2", "scale_out": True}):
        s = _forced(monkeypatch, df, 80, frictions=False, **kw)
        assert s.trades, kw
        c = s.trades[0].context
        assert set(c) == set(FEATURE_KEYS)
        assert c["direction"] == "bullish" and c["horizon_key"] == "2w"
        assert c["regime2_state"] is None                  # no asof passed


def test_context_uses_only_bars_up_to_entry(monkeypatch):
    closes = np.full(120, 100.0); closes[81:] = 104.0
    df = make_ohlcv(closes, spread_pct=1.0)
    s = _forced(monkeypatch, df, 80, frictions=False)
    from swingbot.core.edge.context import entry_context
    t = s.trades[0]
    direct = entry_context(df.iloc[:81], direction="bullish", horizon_key="2w", stop=t.stop_loss, target=t.take_profit)
    assert t.context == direct


def test_asof_row_is_joined_by_entry_date(monkeypatch):
    closes = np.full(120, 100.0); closes[81:] = 104.0
    df = make_ohlcv(closes, spread_pct=1.0)
    asof = pd.DataFrame({"regime2_state": ["bear_quiet"] * 120, "rs_pctile": 12.5, "sector_pctile": np.nan,
                         "rs_combined": 12.5}, index=df.index)
    s = _forced(monkeypatch, df, 80, frictions=False, asof=asof)
    assert s.trades[0].context["regime2_state"] == "bear_quiet"
    assert s.trades[0].context["rs_pctile"] == 12.5 and s.trades[0].context["sector_pctile"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/backtesting/test_asof_context.py tests/backtesting/test_backtest_context.py -v`
Expected: FAIL (`ModuleNotFoundError`; `AttributeError: 'BacktestTrade' object has no attribute 'context'`)

- [ ] **Step 3: Implement**

`swingbot/core/backtesting/asof_context.py`:

```python
"""v93: per-bar cross-sectional inputs for entry_context, computed once per
universe run. Vectorised twins of edge/factors' point-in-time functions;
tests pin last-bar equality with them."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from swingbot.core.edge.factors import RS_WINDOW, rs_score
from swingbot.core.edge.regime2 import regime_series

COLUMNS = ("regime2_state", "rs_pctile", "sector_pctile", "rs_combined")


def _rel_series(df: pd.DataFrame, spy: pd.DataFrame, window: int) -> pd.Series:
    t = df["Close"] / df["Close"].shift(window) - 1.0
    s = (spy["Close"] / spy["Close"].shift(window) - 1.0).reindex(df.index, method="ffill")
    return t - s


def _pct_rank_rows(matrix: pd.DataFrame) -> pd.DataFrame:
    """Per date: 100 * share of universe values <= this value (ties count,
    self included) -- exactly rs_percentile's mean(rel >= r), rounded to 1dp."""
    ranked = matrix.rank(axis=1, method="max", pct=True) * 100.0
    return ranked.round(1)


def build_asof(frames: dict, spy_df: pd.DataFrame, *, sector_of_ticker: dict,
               sector_etf_frames: dict, sector_of_etf: dict, window: int = RS_WINDOW) -> dict:
    rels = pd.DataFrame({sym: _rel_series(df, spy_df, window) for sym, df in frames.items()})
    rs = _pct_rank_rows(rels)
    etf_rels = pd.DataFrame({etf: _rel_series(df, spy_df, window) for etf, df in sector_etf_frames.items()})
    etf_rank = _pct_rank_rows(etf_rels) if len(etf_rels.columns) >= 2 else pd.DataFrame(index=etf_rels.index)
    etf_of_sector = {v: k for k, v in sector_of_etf.items()}
    regime = regime_series(spy_df)
    out = {}
    for sym, df in frames.items():
        row = pd.DataFrame(index=df.index)
        row["regime2_state"] = regime.reindex(df.index, method="ffill")
        row["rs_pctile"] = rs[sym].reindex(df.index)
        etf = etf_of_sector.get(sector_of_ticker.get(sym))
        if etf is not None and etf in etf_rank.columns:
            row["sector_pctile"] = etf_rank[etf].reindex(df.index, method="ffill")
        else:
            row["sector_pctile"] = np.nan
        combined = 0.7 * row["rs_pctile"] + 0.3 * row["sector_pctile"]
        row["rs_combined"] = combined.where(row["sector_pctile"].notna(), row["rs_pctile"])
        out[sym] = row
    return out


def asof_row(asof_df: pd.DataFrame | None, ts) -> dict:
    if asof_df is None or ts not in asof_df.index:
        return {}
    r = asof_df.loc[ts]
    def clean(v):
        if isinstance(v, str):
            return v
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(f) else f
    return {k: clean(r[k]) for k in COLUMNS}
```

Note on `rs_score`: the combined column above is `0.7*rs + 0.3*sector`, the same frozen constants `rs_score` uses; the test asserts equality against `rs_score` so a drift in either would fail.

`backtest.py`:
- `BacktestTrade`: add `context: dict | None = None` after `runner_outcome`.
- Imports: `from swingbot.core.edge.context import entry_context` and `from swingbot.core.backtesting.asof_context import asof_row`.
- `run_backtest(..., frictions: bool = True, asof=None)`; docstring line: "`asof` (v93): per-date cross-sectional frame from `asof_context.build_asof` for this ticker, or None -> those four features are None."
- At **both** `trades.append(BacktestTrade(` sites add:
```python
                context=entry_context(df.iloc[:i + 1], direction=direction, horizon_key=horizon_key,
                                      stop=stop_loss, target=take_profit, asof=asof_row(asof, df.index[i])),
```
- `run_backtest_daterange(..., tp2_mode="none", asof=None)` → pass `asof=asof` through to `run_backtest`.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_asof_context.py`, `... tests/backtesting/test_backtest_context.py`, `... tests/backtesting/test_backtest_engine.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/asof_context.py swingbot/core/backtesting/backtest.py tests/backtesting/test_asof_context.py tests/backtesting/test_backtest_context.py
git commit -m "feat(v93): BacktestTrade.context at both construction sites; as-of cross-sectional builder"
```

---

### Task 19: Confluence replay stamp site

**Files:**
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (`replay_scenarios` ~L72–156, `_replay_ticker` ~L181, `run_scenario_backtest` ~L219)
- Test: `tests/backtesting/test_replay_context.py`

**Interfaces:**
- Consumes: `params.stamp_entry_context`, `asof_context.asof_row`.
- Produces: `replay_scenarios(..., asof=None)` — every yielded plan carries `entry_context`; `run_scenario_backtest(..., asof_map: dict | None = None)` passes `asof_map.get(ticker)` to each worker.

- [ ] **Step 1: Write the failing test**

`tests/backtesting/test_replay_context.py`:

```python
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.edge.context import FEATURE_KEYS
from tests.helpers import make_ohlcv

pytestmark = pytest.mark.slow


def _structured_df():
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


def test_replayed_plans_carry_context_from_the_window():
    df = _structured_df()
    asof = pd.DataFrame({"regime2_state": "bull_quiet", "rs_pctile": 80.0, "sector_pctile": np.nan,
                         "rs_combined": 80.0}, index=df.index)
    out = bs.replay_scenarios("AAPL", df, "4w", asof=asof)
    assert out, "fixture must yield at least one plan (same fixture as test_backtest_scenarios)"
    for i, plan in out:
        assert set(plan.entry_context) == set(FEATURE_KEYS)
        assert plan.entry_context["regime2_state"] == "bull_quiet"
        # window discipline: dow of the entry bar, not of the frame's last bar
        assert plan.entry_context["dow"] == df.index[i].dayofweek


def test_replay_without_asof_leaves_cross_sectional_none():
    df = _structured_df()
    out = bs.replay_scenarios("AAPL", df, "4w")
    assert all(p.entry_context["rs_pctile"] is None for _, p in out)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/backtesting/test_replay_context.py -v`
Expected: FAIL with `TypeError: replay_scenarios() got an unexpected keyword argument 'asof'`

- [ ] **Step 3: Implement**

`backtest_scenarios.py`:
- imports: `from swingbot.core.planning.params import stamp_entry_context` and `from swingbot.core.backtesting.asof_context import asof_row`.
- `replay_scenarios(..., dcb_params=None, asof=None)`; after `if plan is None: continue` add
```python
            stamp_entry_context(plan, window, asof_row(asof, window.index[-1]))
```
- `_replay_ticker(args)`: unpack one extra trailing element `asof_df` (default `None` when the tuple is shorter: `asof_df = args[N] if len(args) > N else None`) and pass `asof=asof_df` to `replay_scenarios`.
- `run_scenario_backtest(frames, start, end, *, gates, ..., asof_map=None)`: when building each worker's args tuple, append `asof_map.get(ticker) if asof_map else None`.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_replay_context.py` and `... tests/backtesting/test_backtest_scenarios.py` and `... tests/backtesting/test_scenario_parallel.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/backtest_scenarios.py tests/backtesting/test_replay_context.py
git commit -m "feat(v93): stamp entry_context on replayed confluence plans (as-of aware)"
```

---

### Task 20: Live stamp sites — `attach_plan_v2` and the strategy pass

**Files:**
- Modify: `swingbot/core/scanning/analyze.py` (`attach_plan_v2` ~L327–388)
- Modify: `swingbot/core/scanning/strategy_pass.py` (`build_strategy_plan_at`, `run_strategy_pass`)
- Modify: `swingbot/core/scanning/scan_run.py` (`_maybe_run_strategy_pass`: pass `asof_of`)
- Test: `tests/scanning/test_live_context_stamp.py`

**Interfaces:**
- Consumes: `params.stamp_entry_context` (Task 17).
- Produces: `attach_plan_v2` stamps `plan.entry_context` from `{regime2_state, rs_pctile: rs_percentile, sector_pctile: item.sector_rs_percentile, rs_combined: item.rs_combined}`; `build_strategy_plan_at(..., asof: dict | None = None)`; `run_strategy_pass(..., asof_of=None)` where `asof_of(ticker) -> dict`.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_live_context_stamp.py`:

```python
from types import SimpleNamespace

import pytest

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.scanning import analyze, strategy_pass as sp
from tests.helpers import make_ohlcv


def _plan():
    return TradePlanV2(plan_id="p", ticker="AAPL", created_at="2026-09-16", source="confluence",
                       strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
                       trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=95.0, tp1=110.0,
                       tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
                       quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.PENDING)


def test_attach_plan_v2_stamps_with_item_readings(monkeypatch):
    import swingbot.config as config
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *a, **k: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda sc: "MACD")
    seen = {}
    def fake_stamp(plan, df, asof):
        seen["asof"] = asof; plan.entry_context = {"stamped": True}
    monkeypatch.setattr(analyze, "stamp_entry_context", fake_stamp)
    df = make_ohlcv([100.0] * 300, start="2025-06-02")
    item = SimpleNamespace(rs_combined=61.0, sector_rs_percentile=55.0, conf=None, htf_bias=None,
                           target_confluence=None)
    scenario = SimpleNamespace(direction="bullish", entry=100.0)
    analyze.attach_plan_v2(item, scenario, df, "AAPL", "3m", rs_percentile=64.0, regime2_state="bull_quiet")
    assert item.plan_v2.entry_context == {"stamped": True}
    assert seen["asof"] == {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": 55.0, "rs_combined": 61.0}


def test_strategy_plan_stamps_once(monkeypatch):
    calls = []
    monkeypatch.setattr(sp, "build_strategy_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(sp, "stamp_badge", lambda p: None)
    monkeypatch.setattr(sp, "stamp_cohort", lambda p, s: None)
    monkeypatch.setattr(sp, "stamp_entry_context", lambda p, df, asof: calls.append(asof))
    df = make_ohlcv([100.0] * 300, start="2025-06-02")
    sp.build_strategy_plan_at(df, ticker="AAPL", strategy="MACD", horizon_key="3m", direction="bullish",
                              regime2_state="bear_quiet", asof={"rs_pctile": 10.0})
    assert calls == [{"rs_pctile": 10.0}]


def test_live_and_replay_use_the_same_function():
    """Single source: both stamp sites import params.stamp_entry_context."""
    from swingbot.core.backtesting import backtest_scenarios as bs
    from swingbot.core.planning import params
    assert analyze.stamp_entry_context is params.stamp_entry_context
    assert bs.stamp_entry_context is params.stamp_entry_context
    assert sp.stamp_entry_context is params.stamp_entry_context
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/scanning/test_live_context_stamp.py -v`
Expected: FAIL with `AttributeError: module ... analyze has no attribute 'stamp_entry_context'`

- [ ] **Step 3: Implement**

`analyze.py`: import `from swingbot.core.planning.params import stamp_entry_context` (module-level, so the identity test holds). In `attach_plan_v2`, right after `item.plan_v2 = plan`:
```python
        stamp_entry_context(plan, df, {
            "regime2_state": regime2_state,
            "rs_pctile": rs_percentile,
            "sector_pctile": getattr(item, "sector_rs_percentile", None),
            "rs_combined": getattr(item, "rs_combined", None),
        })
```

`strategy_pass.py`: import `stamp_entry_context` from `params`; `build_strategy_plan_at(..., regime2_state, asof: dict | None = None)` and after the cohort stamp add `stamp_entry_context(plan, df_completed, {**(asof or {}), "regime2_state": regime2_state})`. `run_strategy_pass(..., asof_of=None)`: call `build_strategy_plan_at(..., asof=(asof_of(ticker) if asof_of else None))`.

`scan_run.py`, `_maybe_run_strategy_pass`: alongside `rs_combined_of`, define
```python
    def asof_of(ticker):
        if rs_cache is None or spy_df is None or fresh_data.get(ticker) is None:
            return {}
        pct = rs_factors.rs_percentile(fresh_data[ticker], spy_df, universe_rels=rs_cache.get("rels"))
        sector = sector_of_ticker.get(ticker)
        sec = None
        if sector and sector_etf_frames and etf_symbol_of_sector.get(sector) in sector_etf_frames:
            sec = rs_factors.sector_rs_percentile(sector, sector_etf_frames, spy_df,
                                                  sector_of_etf={v: k for k, v in etf_symbol_of_sector.items()})
        return {"rs_pctile": pct, "sector_pctile": sec,
                "rs_combined": rs_factors.rs_score(pct, sec) if sec is not None else pct}
```
and pass `asof_of=asof_of` into `run_strategy_pass`. (`rs_combined_of` can now be `lambda t: asof_of(t).get("rs_combined")`.)

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_live_context_stamp.py`, `... tests/scanning/test_strategy_pass_run.py`, `... tests/scanning/test_engine_v2_plans.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/analyze.py swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/scan_run.py tests/scanning/test_live_context_stamp.py
git commit -m "feat(v93): live entry_context stamps in attach_plan_v2 and the strategy pass"
```

---

### Task 21: Range script trade export with context; cost measurement

**Files:**
- Modify: `scripts/backtest/run_backtest_range.py` (args, as-of build, `run_backtest(..., asof=)`, `--trades-jsonl` writer)
- Create: `docs/superpowers/results/<YYYY-MM-DD>-v93-context-cost.md` (date of the run)
- Test: `tests/scripts/test_range_trades_jsonl.py`

**Interfaces:**
- Consumes: `asof_context.build_asof`, `load_cached`, `universe.sector_map("watchlist"|<universe>)`, `sector_map("etfs")`.
- Produces: `--trades-jsonl PATH` (one JSON object per windowed trade: `ticker, strategy, horizon_key` + `dataclasses.asdict(trade)`), `--context on|off` (default `on`; `off` skips the as-of build and passes `asof=None` — used only for the cost measurement), and a `write_trades_jsonl(rows, path)` helper.

- [ ] **Step 1: Write the failing test**

`tests/scripts/test_range_trades_jsonl.py`:

```python
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))


def test_write_trades_jsonl_one_row_per_trade(tmp_path):
    import run_backtest_range as rr
    from swingbot.core.backtesting.backtest import BacktestTrade
    t = BacktestTrade(entry_date="2021-03-01", exit_date="2021-03-05", direction="bullish", entry=100.0,
                      stop_loss=95.0, take_profit=110.0, outcome="win", exit_price=110.0, return_pct=10.0,
                      r_multiple=2.0, holding_days=4, context={"rsi_14": 40.0})
    out = tmp_path / "t.jsonl"
    rr.write_trades_jsonl([("AAPL", "MACD", "3m", t)], out)
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"ticker": "AAPL", "strategy": "MACD", "horizon_key": "3m", "entry_date": "2021-03-01",
                     "exit_date": "2021-03-05", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
                     "take_profit": 110.0, "outcome": "win", "exit_price": 110.0, "return_pct": 10.0,
                     "r_multiple": 2.0, "holding_days": 4, "runner_outcome": None, "context": {"rsi_14": 40.0}}]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/scripts/test_range_trades_jsonl.py -v`
Expected: FAIL with `AttributeError: module 'run_backtest_range' has no attribute 'write_trades_jsonl'`

- [ ] **Step 3: Implement**

In `run_backtest_range.py`:

```python
import dataclasses

def write_trades_jsonl(rows, path) -> None:
    """(ticker, strategy, horizon_key, BacktestTrade) -> one JSON line each.
    The `context` dict rides along verbatim -- this is the training table
    spec 2 reads."""
    with open(path, "w", encoding="utf-8") as f:
        for ticker, strategy, hk, t in rows:
            f.write(json.dumps({"ticker": ticker, "strategy": strategy, "horizon_key": hk,
                                **dataclasses.asdict(t)}) + "\n")


def _build_asof_map(tickers: list, frames: dict, universe: str | None):
    """v93: cross-sectional as-of inputs for every loaded frame, once per run."""
    from swingbot.core.backtesting.asof_context import build_asof
    from swingbot.core.marketdata.universe import sector_map
    spy = _market_frame()
    if spy is None:
        print("    ! no SPY frame -- as-of context disabled for this run", flush=True)
        return {}
    sector_of_etf = sector_map("etfs")
    etf_frames = {etf: f for etf in sector_of_etf if (f := load_cached(etf)) is not None}
    sector_of_ticker = sector_map(universe or "watchlist")
    return build_asof(frames, spy, sector_of_ticker=sector_of_ticker,
                      sector_etf_frames=etf_frames, sector_of_etf=sector_of_etf)
```

Args: `ap.add_argument("--trades-jsonl", dest="trades_jsonl", default=None)` and `ap.add_argument("--context", choices=["on", "off"], default="on")`.

In the main strategy loop: load every frame first (the loop already calls `_with_context(load_cached(ticker))` per ticker — hoist that into a `frames = {}` pre-pass over `tickers` so `_build_asof_map(tickers, frames, args.universe)` can run once), then `asof_map = _build_asof_map(...) if args.context == "on" else {}`; call `run_backtest(..., asof=asof_map.get(ticker))`; collect `trade_rows.extend((ticker, strat, hk, t) for t in tr)`; after the report, `if args.trades_jsonl: write_trades_jsonl(trade_rows, args.trades_jsonl)`.

- [ ] **Step 4: Cost measurement (dispatch to `backtest-runner`)**

Run each twice, taking the wall-clock from the runner's report (one strategy, TRAIN, current arithmetic):

```bash
python scripts/backtest/run_backtest_range.py --train --strategy MACD --exit-model v2 --scale-out --context off
python scripts/backtest/run_backtest_range.py --train --strategy MACD --exit-model v2 --scale-out --context on --trades-jsonl data/v93_macd_train.jsonl
```

Write `docs/superpowers/results/<date>-v93-context-cost.md` with both timings, the ratio, the row count in the JSONL and the share of rows whose `rs_pctile` is non-null. **Cap: `on` ≤ 1.20 × `off`.** If exceeded, precompute `atr(df,14)`, `rsi`, `adx`, the Bollinger width series and `gap_stats` once per frame in `_plan_series`-style and index them in `entry_context` via an optional `precomputed=` argument; re-measure; the doc records both attempts.

- [ ] **Step 5: Run the tests and commit**

Run: `python scripts/dev/testrun.py file tests/scripts/test_range_trades_jsonl.py`
Expected: green.

```bash
git add scripts/backtest/run_backtest_range.py tests/scripts/test_range_trades_jsonl.py docs/superpowers/results/*-v93-context-cost.md
git commit -m "feat(v93): --trades-jsonl training-table export with entry_context; as-of build; cost measured"
```
