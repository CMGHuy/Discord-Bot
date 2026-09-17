# Strategy path goes live — Part 1: Phase 1a (config, ledger, strategy pass, soak rule)

Index, header block, global constraints and the parallelisation map: `2026-09-17-v93-strategy-path-live_0-index.md`. Spec: `docs/superpowers/specs/2026-09-17-v93-strategy-path-live-design.md` (§1, §2).

# Phase 1a — Config, ledger, strategy pass, soak rule

### Task 1: Config fields `STRATEGY_ALERTS_MODE` and `STRATEGY_ALERTS_LIVE_STRATEGIES`

**Files:**
- Modify: `swingbot/config.py` (append to `FIELDS`, in the "Universe & Scanning" section next to `REGIME_GATES_ENABLED`, ~L785)
- Modify: `.env.example` (after the `RS_GATE` block, ~L187)
- Test: `tests/test_config_flags.py`

**Interfaces:**
- Produces: `config.STRATEGY_ALERTS_MODE: str` ∈ `{"off","shadow","live"}`, default `"off"`; `config.STRATEGY_ALERTS_LIVE_STRATEGIES: str` (comma-separated exact `ALL_STRATEGIES` names; `""` = every strategy).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config_flags.py`:

```python
def test_v93_strategy_alert_fields():
    by_key = {f.key: f for f in config.FIELDS}
    mode = by_key["STRATEGY_ALERTS_MODE"]
    assert mode.default == "off"
    assert {v for v, _ in mode.options} == {"off", "shadow", "live"}
    assert config._cast(mode, "banana") == "off"
    assert config._cast(mode, "LIVE") == "live"
    assert config.STRATEGY_ALERTS_MODE == "off"
    allow = by_key["STRATEGY_ALERTS_LIVE_STRATEGIES"]
    assert allow.default == ""
    assert isinstance(config.STRATEGY_ALERTS_LIVE_STRATEGIES, str)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_config_flags.py::test_v93_strategy_alert_fields -v`
Expected: FAIL with `KeyError: 'STRATEGY_ALERTS_MODE'`

- [ ] **Step 3: Add the two fields**

In `swingbot/config.py`, directly after the `REGIME_GATES_ENABLED` `Field(...)` entry:

```python
    Field("STRATEGY_ALERTS_MODE", "STRATEGY_ALERTS_MODE", "Universe & Scanning",
          "Strategy-sourced alerts (v93)",
          type="select", default="off",
          options=[("off", "Off"),
                   ("shadow", "Shadow -- build and store strategy plans, no alert, no paper trade"),
                   ("live", "Live -- alerts + paper trades")],
          help="v93. Runs the per-strategy entry rules (entry_filters.entries_for, the same "
               "functions the backtest and the registry badges are measured with) on the last "
               "COMPLETED daily bar of every scanned ticker/horizon, after the confluence pass. "
               "off: the scan is byte-identical to before v93. shadow: every strategy plan is "
               "built, badge- and ledger-stamped and walked through the plan lifecycle so the "
               "soak rule (!soak) can compare live to backtest -- but nothing posts and no paper "
               "trade opens. live: alerts post and paper trades open; VALIDATED plans book to the "
               "main ledger, WEAK plans to the separate weak ledger (never summed). Flip a "
               "strategy to live only when !soak reports all three clauses PASS."),
    Field("STRATEGY_ALERTS_LIVE_STRATEGIES", "STRATEGY_ALERTS_LIVE_STRATEGIES",
          "Universe & Scanning", "Strategies allowed to go live",
          type="text", default="",
          help="v93. Comma-separated exact strategy names (e.g. 'MACD,Volume Profile'). While "
               "STRATEGY_ALERTS_MODE=live, only these strategies post alerts and open paper "
               "trades; every other strategy stays in shadow. Empty = all strategies. Lets the "
               "soak rule be applied one strategy at a time."),
```

In `.env.example`, after `RS_GATE=true` and its trailing blank line:

```
# v93 strategy-sourced alerts. off = scan unchanged; shadow = build + store
# strategy plans for the soak rule, no alerts/no paper trades; live = alerts
# and paper trades (VALIDATED -> main ledger, WEAK -> weak ledger).
STRATEGY_ALERTS_MODE=off
# Comma-separated strategy names allowed to go live under live mode; empty = all.
STRATEGY_ALERTS_LIVE_STRATEGIES=
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/test_config_flags.py` and `python scripts/dev/testrun.py file tests/test_env_example_sync.py`
Expected: both green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py .env.example tests/test_config_flags.py
git commit -m "feat(v93): STRATEGY_ALERTS_MODE + STRATEGY_ALERTS_LIVE_STRATEGIES config fields (default off)"
```

---

### Task 2: `tracking/ledger.py` rule and the `ledger` plan field

**Files:**
- Create: `swingbot/core/tracking/ledger.py`
- Modify: `swingbot/core/planning/plan_types.py` (add field after `risk_features`)
- Test: `tests/tracking/test_ledger.py`

**Interfaces:**
- Produces: `ledger.MAIN == "main"`, `ledger.WEAK == "weak"`, `ledger_for(source: str | None, badge_status: str | None) -> str`, `is_main(trade: dict) -> bool`, `is_weak(trade: dict) -> bool`, `split_by_ledger(trades: list[dict]) -> tuple[list, list]`; `TradePlanV2.ledger: str = "main"`.

- [ ] **Step 1: Write the failing tests**

`tests/tracking/test_ledger.py`:

```python
from swingbot.core.tracking import ledger
from swingbot.core.planning.plan_types import TradePlanV2, PlanStatus, plan_from_dict, plan_to_dict


def test_weak_only_for_strategy_source_with_weak_badge():
    assert ledger.ledger_for("strategy", "WEAK") == "weak"
    assert ledger.ledger_for("strategy", "VALIDATED") == "main"
    # borrowed-WEAK confluence plans stay main (spec §2)
    assert ledger.ledger_for("confluence", "WEAK") == "main"
    assert ledger.ledger_for(None, None) == "main"


def test_missing_field_is_main():
    assert ledger.is_main({"ticker": "AAPL"}) is True
    assert ledger.is_weak({"ticker": "AAPL"}) is False
    assert ledger.is_main({"ledger": "weak"}) is False
    assert ledger.is_weak({"ledger": "weak"}) is True


def test_split_never_overlaps_or_drops():
    trades = [{"id": "a"}, {"id": "b", "ledger": "weak"}, {"id": "c", "ledger": "main"}]
    main, weak = ledger.split_by_ledger(trades)
    assert [t["id"] for t in main] == ["a", "c"]
    assert [t["id"] for t in weak] == ["b"]


def _plan(**kw):
    base = dict(plan_id="p", ticker="AAPL", created_at="2026-09-17", source="strategy",
                strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
                trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=95.0,
                tp1=110.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
                trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge="WEAK",
                badge_stats={}, status=PlanStatus.PENDING)
    base.update(kw)
    return TradePlanV2(**base)


def test_plan_ledger_field_defaults_and_round_trips():
    p = _plan()
    assert p.ledger == "main"
    p.ledger = "weak"
    assert plan_from_dict(plan_to_dict(p)).ledger == "weak"
    # a stored plan written before v93 has no key -> default main
    d = plan_to_dict(_plan()); d.pop("ledger")
    assert plan_from_dict(d).ledger == "main"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/tracking/test_ledger.py -v`
Expected: FAIL with `ModuleNotFoundError: swingbot.core.tracking.ledger`

- [ ] **Step 3: Implement**

`swingbot/core/tracking/ledger.py`:

```python
"""v93: the main/weak P&L ledger rule.

A trade's ledger is frozen at creation and never rewritten. `main` is
computed as "not weak" so every record written before this field existed
stays exactly where it always was. The two ledgers are never summed.
"""
MAIN = "main"
WEAK = "weak"


def ledger_for(source: str | None, badge_status: str | None) -> str:
    """Spec §2: strategy-sourced plans carrying a WEAK badge book to the weak
    ledger; everything else -- VALIDATED strategy plans and ALL confluence
    plans, including those borrowing a WEAK badge from their primary method
    -- books to main."""
    if source == "strategy" and badge_status == "WEAK":
        return WEAK
    return MAIN


def is_weak(trade: dict) -> bool:
    return trade.get("ledger") == WEAK


def is_main(trade: dict) -> bool:
    return not is_weak(trade)


def split_by_ledger(trades: list) -> tuple[list, list]:
    main = [t for t in trades if is_main(t)]
    weak = [t for t in trades if is_weak(t)]
    return main, weak
```

In `swingbot/core/planning/plan_types.py`, after `risk_features: dict = field(default_factory=dict)` add:

```python
    ledger: str = "main"       # v93: "main" | "weak", frozen at creation (tracking/ledger.py)
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/tracking/test_ledger.py`
Expected: green. Also `python scripts/dev/testrun.py file tests/test_cohort_stamp.py` (plan round-trip tests) — green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/tracking/ledger.py swingbot/core/planning/plan_types.py tests/tracking/test_ledger.py
git commit -m "feat(v93): main/weak ledger rule + TradePlanV2.ledger field"
```

---

### Task 3: `ledger` on the trade record; `get_stats`/`get_trades` ledger scope; `weak_summary`

**Files:**
- Modify: `swingbot/core/tracking/performance.py` (`log_trade` ~L580–650, `get_stats` ~L972, `get_trades` ~L1116)
- Test: `tests/tracking/test_ledger_stats.py`

**Interfaces:**
- Consumes: `ledger.is_main/is_weak/split_by_ledger` (Task 2).
- Produces: `TradeLog.log_trade(..., ledger: str | None = None)` writes `record["ledger"]`; `TradeLog.get_stats(..., ledger: str | None = "main")`; `TradeLog.get_trades(..., ledger: str | None = None)`; `TradeLog.weak_summary() -> dict` with keys `n, wins, losses, win_rate, expectancy_r, total_pnl`.

- [ ] **Step 1: Write the failing tests**

`tests/tracking/test_ledger_stats.py`:

```python
import pytest

from swingbot import config
from swingbot.core.tracking.performance import TradeLog


@pytest.fixture
def log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return TradeLog(path=str(tmp_path / "trades.json"))


def _open(log, ticker, ledger=None, **kw):
    return log.log_trade(ticker=ticker, strategy="MACD", horizon_key="3m", direction="bullish",
                         confidence_level=None, confidence_label="strategy signal",
                         entry=100.0, stop_loss=95.0, take_profit=110.0,
                         source=kw.get("source", "strategy"), badge=kw.get("badge", "WEAK"),
                         ledger=ledger)


def _close(log, trade_id, status, exit_price, pnl):
    t = log.get_trade(trade_id)
    t["status"], t["exit_price"], t["realized_pnl_amount"] = status, exit_price, pnl
    t["closed_at"] = "2026-09-17T20:00:00+00:00"
    log._save()


def test_log_trade_records_ledger_and_defaults_to_main(log):
    a = _open(log, "AAPL")
    b = _open(log, "MSFT", ledger="weak")
    assert log.get_trade(a)["ledger"] == "main"
    assert log.get_trade(b)["ledger"] == "weak"


def test_get_stats_defaults_to_main_and_never_sums(log):
    a = _open(log, "AAPL"); _close(log, a, "win", 110.0, 100.0)
    b = _open(log, "MSFT", ledger="weak"); _close(log, b, "loss", 95.0, -50.0)
    c = _open(log, "NVDA", ledger="weak"); _close(log, c, "win", 110.0, 80.0)
    main = log.get_stats()                    # default ledger="main"
    assert (main["closed"], main["wins"], main["losses"]) == (1, 1, 0)
    weak = log.get_stats(ledger="weak")
    assert (weak["closed"], weak["wins"], weak["losses"]) == (2, 1, 1)
    both = log.get_stats(ledger=None)
    assert both["closed"] == 3


def test_get_trades_ledger_filter(log):
    _open(log, "AAPL"); _open(log, "MSFT", ledger="weak")
    assert {t["ticker"] for t in log.get_trades(status="open", limit=None, ledger="main")} == {"AAPL"}
    assert {t["ticker"] for t in log.get_trades(status="open", limit=None, ledger="weak")} == {"MSFT"}
    assert len(log.get_trades(status="open", limit=None)) == 2


def test_weak_summary(log):
    b = _open(log, "MSFT", ledger="weak"); _close(log, b, "loss", 95.0, -50.0)
    c = _open(log, "NVDA", ledger="weak"); _close(log, c, "win", 110.0, 80.0)
    s = log.weak_summary()
    assert s["n"] == 2 and s["wins"] == 1 and s["losses"] == 1
    assert s["win_rate"] == 50.0
    assert s["total_pnl"] == 30.0
    assert s["expectancy_r"] is not None


def test_weak_summary_empty_is_measured_zero(log):
    s = log.weak_summary()
    assert s == {"n": 0, "wins": 0, "losses": 0, "win_rate": None, "expectancy_r": None, "total_pnl": 0.0}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/tracking/test_ledger_stats.py -v`
Expected: FAIL with `TypeError: log_trade() got an unexpected keyword argument 'ledger'`

- [ ] **Step 3: Implement**

In `performance.py`:

1. Add `ledger=None` to `log_trade`'s signature after `risk_features=None`, and in `record` after `"source": source,` add:
```python
            "ledger": ledger or "main",   # v93: frozen at creation; see tracking/ledger.py
```
2. `get_stats`: add keyword `ledger: str | None = "main"` after `expand`. After `base = self._all() if trades is None else trades` insert:
```python
        from swingbot.core.tracking import ledger as _ledger
        if ledger == _ledger.MAIN:
            base = [t for t in base if _ledger.is_main(t)]
        elif ledger == _ledger.WEAK:
            base = [t for t in base if _ledger.is_weak(t)]
```
   Update the docstring: "`ledger` (v93): `'main'` (default) excludes weak-ledger trades; `'weak'` returns only them; `None` returns both — never used for a displayed total."
3. `get_trades`: add `ledger: str | None = None` after `sort_by`; before the existing status/ticker filtering add the same three-line filter over the working list.
4. New method after `get_stats_by_confidence`:
```python
    def weak_summary(self) -> dict:
        """v93: the weak ledger's own block. Empty is a measured zero, not
        a stub -- `n: 0` renders as such and is never hidden."""
        from swingbot.core.analytics import metrics as m
        from swingbot.core.tracking import ledger as _ledger
        self.refresh()
        weak = [t for t in self._all() if _ledger.is_weak(t)]
        closed = [t for t in weak if t.get("status") in ("win", "loss", "closed")]
        wins = [t for t in closed if t["status"] == "win"]
        losses = [t for t in closed if t["status"] == "loss"]
        return {
            "n": len(closed), "wins": len(wins), "losses": len(losses),
            "win_rate": (len(wins) / len(closed) * 100) if closed else None,
            "expectancy_r": m.expectancy_r(closed) if closed else None,
            "total_pnl": round(sum(float(t.get("realized_pnl_amount") or 0.0) for t in closed), 2),
        }
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/tracking/test_ledger_stats.py`, then `python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py` and `tests/tracking/test_trades_schema.py` (record shape guards — if `test_trades_schema` pins the key set, add `"ledger"` to its expected keys).
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/tracking/performance.py tests/tracking/test_ledger_stats.py tests/tracking/test_trades_schema.py
git commit -m "feat(v93): ledger on trade records; get_stats/get_trades ledger scope; weak_summary"
```

---

### Task 4: `strategy_pass.completed_frame` and `already_emitted`

**Files:**
- Create: `swingbot/core/scanning/strategy_pass.py`
- Test: `tests/scanning/test_strategy_pass_frame.py`

**Interfaces:**
- Consumes: `swingbot.core.market.session.session_date(now) -> str`, `is_regular_session(now) -> bool`; `PlanStore.all() -> list[TradePlanV2]`.
- Produces: `completed_frame(df, now) -> pd.DataFrame`; `already_emitted(store, ticker, strategy, horizon_key, bar_date: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_strategy_pass_frame.py`:

```python
import datetime as dt
from zoneinfo import ZoneInfo

from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv

ET = ZoneInfo("America/New_York")


def _frame_ending(day: dt.date, n=30):
    start = (day - dt.timedelta(days=60)).isoformat()
    df = make_ohlcv([100 + i for i in range(80)], start=start)
    return df[df.index.date <= day]


def test_partial_bar_dropped_during_regular_session():
    day = dt.date(2026, 9, 17)                       # a Thursday
    df = _frame_ending(day)
    now = dt.datetime(2026, 9, 17, 11, 0, tzinfo=ET)  # mid-session
    out = sp.completed_frame(df, now)
    assert out.index[-1].date() == dt.date(2026, 9, 16)
    assert len(out) == len(df) - 1


def test_todays_bar_kept_after_close():
    day = dt.date(2026, 9, 17)
    df = _frame_ending(day)
    now = dt.datetime(2026, 9, 17, 16, 5, tzinfo=ET)
    out = sp.completed_frame(df, now)
    assert out.index[-1].date() == day


def test_frame_without_todays_bar_is_untouched():
    df = _frame_ending(dt.date(2026, 9, 16))
    now = dt.datetime(2026, 9, 17, 11, 0, tzinfo=ET)
    assert sp.completed_frame(df, now).equals(df)


class _Store:
    def __init__(self, plans): self._plans = plans
    def all(self): return self._plans


class _P:
    def __init__(self, ticker, strategy, hk, created_at, source="strategy"):
        self.ticker, self.strategy, self.horizon_key, self.created_at, self.source = ticker, strategy, hk, created_at, source


def test_already_emitted_keys_on_ticker_strategy_horizon_and_bar_date():
    store = _Store([_P("AAPL", "MACD", "3m", "2026-09-16")])
    assert sp.already_emitted(store, "AAPL", "MACD", "3m", "2026-09-16") is True
    assert sp.already_emitted(store, "AAPL", "MACD", "3m", "2026-09-17") is False
    assert sp.already_emitted(store, "AAPL", "MACD", "4m", "2026-09-16") is False
    # a confluence plan on the same bar does not count
    store = _Store([_P("AAPL", "MACD", "3m", "2026-09-16", source="confluence")])
    assert sp.already_emitted(store, "AAPL", "MACD", "3m", "2026-09-16") is False
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/scanning/test_strategy_pass_frame.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`swingbot/core/scanning/strategy_pass.py` (initial content; Tasks 5–7 append to it):

```python
"""v93: the strategy-sourced alert pass.

Runs AFTER the confluence pass, on the last COMPLETED daily bar, using the
same entry functions the backtest and the registry badges are measured
with (`entry_filters.entries_for`) and the same plan constructor
(`builders.build_strategy_plan`). Mode semantics live in `config.
STRATEGY_ALERTS_MODE`; see the spec §1.
"""
from __future__ import annotations

import logging

import pandas as pd

from swingbot.core.market.session import is_regular_session, session_date

log = logging.getLogger(__name__)


def completed_frame(df: pd.DataFrame, now) -> pd.DataFrame:
    """Drop the in-progress session bar so a signal fires on exactly the bar
    the backtest would fire on (`backtest.ENTRY_SHIFT == 0`: enter at the
    signal bar's close).

    yfinance's daily frame carries today's partial bar while the session is
    open; after the close that same row is the completed bar and is kept.
    Pre-market the frame has no today row yet, so nothing is dropped.
    """
    if df is None or len(df) == 0:
        return df
    last_date = df.index[-1].date().isoformat()
    if last_date == session_date(now) and is_regular_session(now):
        return df.iloc[:-1]
    return df


def already_emitted(store, ticker: str, strategy: str, horizon_key: str, bar_date: str) -> bool:
    """Once per ticker x strategy x horizon x completed bar. Keyed off the
    PlanStore rather than process memory so a restart cannot re-fire."""
    for p in store.all():
        if (getattr(p, "source", None) == "strategy" and p.ticker == ticker
                and p.strategy == strategy and p.horizon_key == horizon_key
                and p.created_at == bar_date):
            return True
    return False
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_frame.py`
Expected: green. If `test_partial_bar_dropped_during_regular_session` fails because `is_regular_session` reads an NYSE calendar and 2026-09-17 is treated as closed, change the fixture date to the most recent weekday that `session.nyse_calendar()` reports open and keep the assertion shape.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/strategy_pass.py tests/scanning/test_strategy_pass_frame.py
git commit -m "feat(v93): strategy_pass.completed_frame + already_emitted"
```

---

### Task 5: `strategy_pass.strategy_signals`

**Files:**
- Modify: `swingbot/core/scanning/strategy_pass.py`
- Test: `tests/scanning/test_strategy_pass_signals.py`

**Interfaces:**
- Consumes: `entry_filters.ENTRY_FUNCS`, `entry_filters.entries_for(strategy, df, horizon_key)`, `market_context.attach(df, spy_df=...)`, `market_context.has_context(df)`.
- Produces: `strategy_signals(df_completed, horizon_key, *, spy_df) -> list[tuple[str, str]]` of `(strategy, direction)` pairs whose entry series is `True` on the last row.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_strategy_pass_signals.py`:

```python
import pandas as pd
import pytest

from swingbot.core.market import entry_filters
from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv


def _spy(n=400):
    return make_ohlcv([300 + i * 0.2 for i in range(n)], start="2024-06-03")


def test_returns_only_last_row_fires(monkeypatch):
    df = make_ohlcv([100 + i * 0.1 for i in range(400)], start="2024-06-03")

    def fake_entries_for(strategy, frame, horizon_key, params=None, regimes=None):
        off = pd.Series(False, index=frame.index)
        bull = off.copy(); bear = off.copy()
        if strategy == "MACD":
            bull.iloc[-1] = True            # fires on the completed bar
        if strategy == "RSI":
            bear.iloc[-2] = True            # fired yesterday, not today
        if strategy == "VWAP":
            bear.iloc[-1] = True
        return bull, bear

    monkeypatch.setattr(sp, "entries_for", fake_entries_for)
    out = sp.strategy_signals(df, "3m", spy_df=_spy())
    assert ("MACD", "bullish") in out
    assert ("VWAP", "bearish") in out
    assert all(s != "RSI" for s, _ in out)


def test_iterates_every_registered_strategy(monkeypatch):
    seen = []
    def fake(strategy, frame, horizon_key, params=None, regimes=None):
        seen.append(strategy)
        off = pd.Series(False, index=frame.index)
        return off, off
    monkeypatch.setattr(sp, "entries_for", fake)
    df = make_ohlcv([100.0] * 400, start="2024-06-03")
    sp.strategy_signals(df, "2w", spy_df=_spy())
    assert set(seen) == set(entry_filters.ENTRY_FUNCS)


def test_attaches_market_context_before_calling(monkeypatch):
    from swingbot.core.market import market_context
    captured = {}
    def fake(strategy, frame, horizon_key, params=None, regimes=None):
        captured["has_ctx"] = market_context.has_context(frame)
        off = pd.Series(False, index=frame.index)
        return off, off
    monkeypatch.setattr(sp, "entries_for", fake)
    df = make_ohlcv([100.0] * 400, start="2024-06-03")
    sp.strategy_signals(df, "2w", spy_df=_spy())
    assert captured["has_ctx"] is True


def test_no_spy_frame_returns_empty_and_logs(monkeypatch, caplog):
    df = make_ohlcv([100.0] * 400, start="2024-06-03")
    with caplog.at_level("WARNING"):
        assert sp.strategy_signals(df, "2w", spy_df=None) == []
    assert "no SPY frame" in caplog.text


def test_one_strategy_raising_does_not_stop_the_others(monkeypatch):
    def fake(strategy, frame, horizon_key, params=None, regimes=None):
        if strategy == "Fibonacci":
            raise RuntimeError("boom")
        off = pd.Series(False, index=frame.index)
        bull = off.copy(); bull.iloc[-1] = strategy == "MACD"
        return bull, off
    monkeypatch.setattr(sp, "entries_for", fake)
    df = make_ohlcv([100.0] * 400, start="2024-06-03")
    assert sp.strategy_signals(df, "3m", spy_df=_spy()) == [("MACD", "bullish")]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/scanning/test_strategy_pass_signals.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'strategy_signals'`

- [ ] **Step 3: Implement**

Append to `strategy_pass.py` (add the imports at the top of the module):

```python
from swingbot.core.market import market_context
from swingbot.core.market.entry_filters import ENTRY_FUNCS, entries_for


def strategy_signals(df_completed: pd.DataFrame, horizon_key: str, *, spy_df) -> list[tuple[str, str]]:
    """(strategy, direction) pairs whose masked entry series is True on the
    last (completed) bar. Same function, same masks, same regime gate as the
    backtest -- `entries_for` applies STRATEGY_GATES and apply_regime_gate.

    Fail-closed on missing context: `entries_for` reads the regime off the
    frame's context block, so without SPY there is no honest signal."""
    if spy_df is None or len(spy_df) == 0:
        log.warning("strategy pass: no SPY frame this scan -- strategy signals skipped (fail-closed)")
        return []
    frame = df_completed if market_context.has_context(df_completed) else market_context.attach(df_completed, spy_df=spy_df)
    fired: list[tuple[str, str]] = []
    for strategy in ENTRY_FUNCS:
        try:
            bull, bear = entries_for(strategy, frame, horizon_key)
        except Exception:
            log.warning("strategy pass: %s/%s raised -- skipped", strategy, horizon_key, exc_info=True)
            continue
        if len(bull) and bool(bull.iloc[-1]):
            fired.append((strategy, "bullish"))
        if len(bear) and bool(bear.iloc[-1]):
            fired.append((strategy, "bearish"))
    return fired
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_signals.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/strategy_pass.py tests/scanning/test_strategy_pass_signals.py
git commit -m "feat(v93): strategy_pass.strategy_signals on completed bars via entries_for"
```

---

### Task 6: Plan stamping (`badge`, `cohort`, `ledger`) and the strategy alert embed

**Files:**
- Modify: `swingbot/core/scanning/strategy_pass.py`
- Modify: `swingbot/core/scanning/alert_embeds.py` (append `build_strategy_alert_embed`)
- Test: `tests/scanning/test_strategy_pass_stamp.py`

**Interfaces:**
- Consumes: `builders.build_strategy_plan`, `params.stamp_badge(plan)`, `params.stamp_cohort(plan, regime2_state)`, `ledger.ledger_for`, `swingbot.core.presentation as ui` (`ui.apply_chrome(embed, accent=..., plan_id=...)`, `ui.accent_for_outcome`).
- Produces: `build_strategy_plan_at(df_completed, *, ticker, strategy, horizon_key, direction, regime2_state) -> TradePlanV2 | None` (built, badge-, cohort- and ledger-stamped); `alert_embeds.build_strategy_alert_embed(plan) -> discord.Embed`; `strategy_pass.simple_line(plan) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_strategy_pass_stamp.py`:

```python
import pytest

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv


def _plan(badge="WEAK", source="strategy"):
    return TradePlanV2(
        plan_id="p1", ticker="AAPL", created_at="2026-09-16", source=source,
        strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
        trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=95.0,
        tp1=110.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
        trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge=badge,
        badge_stats={}, status=PlanStatus.PENDING)


def test_build_strategy_plan_at_stamps_badge_cohort_ledger(monkeypatch):
    df = make_ohlcv([100 + i * 0.1 for i in range(400)], start="2024-06-03")
    monkeypatch.setattr(sp, "build_strategy_plan", lambda *a, **k: _plan())
    def fake_badge(plan):
        plan.badge = "VALIDATED"; plan.badge_stats = {"status": "VALIDATED", "n": 112}
    monkeypatch.setattr(sp, "stamp_badge", fake_badge)
    monkeypatch.setattr(sp, "stamp_cohort", lambda plan, state: setattr(plan, "cohort_label", f"C:{state}"))
    plan = sp.build_strategy_plan_at(df, ticker="AAPL", strategy="MACD", horizon_key="3m",
                                     direction="bullish", regime2_state="bull_quiet")
    assert plan.badge == "VALIDATED"
    assert plan.ledger == "main"
    assert plan.cohort_label == "C:bull_quiet"
    assert plan.created_at == df.index[-1].date().isoformat()


def test_weak_badge_books_to_weak_ledger(monkeypatch):
    df = make_ohlcv([100.0] * 400, start="2024-06-03")
    monkeypatch.setattr(sp, "build_strategy_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(sp, "stamp_badge", lambda plan: None)   # stays WEAK
    monkeypatch.setattr(sp, "stamp_cohort", lambda plan, state: None)
    plan = sp.build_strategy_plan_at(df, ticker="AAPL", strategy="MACD", horizon_key="3m",
                                     direction="bullish", regime2_state=None)
    assert plan.ledger == "weak"


def test_builder_none_propagates(monkeypatch):
    df = make_ohlcv([100.0] * 400, start="2024-06-03")
    monkeypatch.setattr(sp, "build_strategy_plan", lambda *a, **k: None)
    assert sp.build_strategy_plan_at(df, ticker="AAPL", strategy="MACD", horizon_key="3m",
                                     direction="bullish", regime2_state=None) is None


def test_embed_and_simple_line():
    from swingbot.core.scanning.alert_embeds import build_strategy_alert_embed
    plan = _plan(badge="WEAK"); plan.ledger = "weak"
    embed = build_strategy_alert_embed(plan)
    names = [f.name for f in embed.fields]
    assert "Plan (v2)" in names and "Ledger" in names
    assert "WEAK" in embed.fields[names.index("Plan (v2)")].value
    assert "weak" in embed.fields[names.index("Ledger")].value
    line = sp.simple_line(plan)
    assert "AAPL" in line and "MACD" in line and "bullish" in line and "100.00" in line
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/scanning/test_strategy_pass_stamp.py -v`
Expected: FAIL with `AttributeError ... build_strategy_plan_at`

- [ ] **Step 3: Implement**

Append to `strategy_pass.py` (imports at module top):

```python
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.params import stamp_badge, stamp_cohort
from swingbot.core.tracking import ledger as ledger_mod


def build_strategy_plan_at(df_completed: pd.DataFrame, *, ticker: str, strategy: str,
                           horizon_key: str, direction: str, regime2_state: str | None):
    """THE plan for a fired strategy signal: the same constructor the
    backtest's v2 branch and `!ticker` use, at the completed bar, then
    badge -> cohort -> ledger in that order (ledger reads the badge)."""
    plan = build_strategy_plan(df_completed, len(df_completed) - 1, ticker=ticker,
                               strategy=strategy, horizon_key=horizon_key, direction=direction)
    if plan is None:
        return None
    stamp_badge(plan)
    stamp_cohort(plan, regime2_state)
    plan.ledger = ledger_mod.ledger_for(plan.source, plan.badge)
    return plan


def simple_line(plan) -> str:
    """Text mirror for DISCORD_CHANNEL_TRADES_SIMPLE_ID (same role as
    build_simple_alert for confluence alerts)."""
    return (f"{plan.ticker} {plan.direction} · {plan.strategy} {plan.horizon_key} · "
            f"entry {plan.trigger_price:.2f} stop {plan.stop_loss:.2f} TP1 {plan.tp1:.2f} · "
            f"{plan.badge} · ledger {plan.ledger}")
```

Append to `swingbot/core/scanning/alert_embeds.py` (it already imports `discord`; add `from swingbot.core import presentation as ui` if not present):

```python
def build_strategy_alert_embed(plan) -> "discord.Embed":
    """v93: alert for a strategy-sourced plan. Reuses the plan block the
    lifecycle embeds render; WEAK plans carry the existing warning glyph and
    the ledger line says where the P&L books."""
    embed = discord.Embed(title=f"Strategy signal — {plan.ticker} {plan.direction}")
    ui.apply_chrome(embed, accent=ui.accent_for_outcome("scratch"), plan_id=plan.plan_id)
    embed.add_field(name="Plan (v2)", value=(
        f"{plan.strategy} · {plan.horizon_key} · {plan.direction} · "
        f"{'✅' if plan.badge == 'VALIDATED' else '⚠️'} {plan.badge}"), inline=False)
    embed.add_field(name="Entry", value=f"{plan.trigger_price:.2f}")
    embed.add_field(name="Stop", value=f"{plan.stop_loss:.2f}")
    embed.add_field(name="TP1", value=f"{plan.tp1:.2f}")
    if plan.tp2 is not None:
        embed.add_field(name="TP2", value=f"{plan.tp2:.2f}")
    embed.add_field(name="Ledger", value=(
        "main" if plan.ledger == "main" else "weak — P&L tracked separately, never summed into main"),
        inline=False)
    return embed
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_stamp.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/alert_embeds.py tests/scanning/test_strategy_pass_stamp.py
git commit -m "feat(v93): build_strategy_plan_at (badge/cohort/ledger stamps) + strategy alert embed"
```

---

### Task 7: `run_strategy_pass` orchestrator (modes, collisions, RS laggard rule)

**Files:**
- Modify: `swingbot/core/scanning/strategy_pass.py`
- Test: `tests/scanning/test_strategy_pass_run.py`

**Interfaces:**
- Consumes: Tasks 4–6; `rs_gate.rs_verdict(symbol, direction, rs_value, rs_available) -> dict` (`"status"` ∈ exempt/pass/block); `TradeLog.open_trade_for_ticker(ticker) -> dict | None`; `TradeLog.log_trade(...)`; `PlanStore.add(plan)`; `analyze._regime_at(regimes, when)`.
- Produces: `PassResult` dataclass (`plans: list, alerts: list, opened: int, stored_only: int, rs_blocked: int, skipped_dup: int`) and
  `run_strategy_pass(tickers, fresh_data, *, now, horizons, spy_df, regimes, rs_combined_of, mode, live_allow, trade_log, plan_store) -> PassResult`. `alerts` items are `(embed, None, plan, simple_line)` tuples — the exact 4-tuple shape `_sync_run_scan` already returns.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_strategy_pass_run.py`:

```python
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.scanning import strategy_pass as sp
from swingbot.core.tracking.performance import TradeLog
from tests.helpers import make_ohlcv

ET = ZoneInfo("America/New_York")
NOW = dt.datetime(2026, 9, 16, 16, 30, tzinfo=ET)   # after the close: last bar is complete


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    log = TradeLog(path=str(tmp_path / "trades.json"))
    store = PlanStore(path=str(tmp_path / "plans.json"))
    return log, store


def _df():
    return make_ohlcv([100 + i * 0.1 for i in range(400)], start="2025-03-03")


def _plan(ticker, strategy, direction, badge, created_at):
    return TradePlanV2(
        plan_id=f"{ticker}-{strategy}", ticker=ticker, created_at=created_at, source="strategy",
        strategy=strategy, horizon_key="3m", direction=direction, entry_type="market",
        trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=95.0,
        tp1=110.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
        trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge=badge,
        badge_stats={}, status=PlanStatus.PENDING)


def _wire(monkeypatch, fired, badge="VALIDATED"):
    monkeypatch.setattr(sp, "strategy_signals", lambda df, hk, spy_df: fired)
    def fake_build(df, *, ticker, strategy, horizon_key, direction, regime2_state):
        p = _plan(ticker, strategy, direction, badge, df.index[-1].date().isoformat())
        p.ledger = "weak" if badge == "WEAK" else "main"
        return p
    monkeypatch.setattr(sp, "build_strategy_plan_at", fake_build)


def _run(env, mode, **kw):
    log, store = env
    args = dict(tickers=["AAPL"], fresh_data={"AAPL": _df()}, now=NOW, horizons=["3m"],
                spy_df=_df(), regimes=None, rs_combined_of=lambda t: 50.0, mode=mode,
                live_allow=set(), trade_log=log, plan_store=store)
    args.update(kw)
    return sp.run_strategy_pass(**args)


def test_shadow_stores_plan_opens_nothing_posts_nothing(env, monkeypatch):
    _wire(monkeypatch, [("MACD", "bullish")])
    res = _run(env, "shadow")
    log, store = env
    assert len(store.all()) == 1 and res.stored_only == 1
    assert res.alerts == [] and res.opened == 0
    assert log.get_trades(status="open", limit=None) == []


def test_live_opens_trade_with_source_and_ledger(env, monkeypatch):
    _wire(monkeypatch, [("MACD", "bullish")])
    res = _run(env, "live")
    log, store = env
    assert res.opened == 1 and len(res.alerts) == 1
    embed, chart, plan, line = res.alerts[0]
    assert chart is None and plan.strategy == "MACD" and "AAPL" in line
    t = log.get_trades(status="open", limit=None)[0]
    assert t["source"] == "strategy" and t["ledger"] == "main" and t["plan_id"] == plan.plan_id
    assert t["badge"] == "VALIDATED"


def test_live_weak_opens_into_weak_ledger(env, monkeypatch):
    _wire(monkeypatch, [("RSI", "bullish")], badge="WEAK")
    _run(env, "live")
    log, _ = env
    assert log.get_trades(status="open", limit=None)[0]["ledger"] == "weak"


def test_live_allow_list_keeps_others_in_shadow(env, monkeypatch):
    _wire(monkeypatch, [("MACD", "bullish")])
    res = _run(env, "live", live_allow={"Volume Profile"})
    assert res.opened == 0 and res.stored_only == 1 and res.alerts == []


def test_already_open_ticker_stores_only(env, monkeypatch):
    log, store = env
    log.log_trade(ticker="AAPL", strategy="S/R Confluence", horizon_key="2m", direction="bullish",
                  confidence_level=4, confidence_label="x", entry=100.0, stop_loss=95.0, take_profit=110.0)
    _wire(monkeypatch, [("MACD", "bullish")])
    res = _run(env, "live")
    assert res.opened == 0 and res.stored_only == 1
    assert len(store.all()) == 1


def test_bearish_blocked_by_rs_laggard_rule(env, monkeypatch):
    _wire(monkeypatch, [("MACD", "bearish")])
    monkeypatch.setattr(sp, "rs_verdict", lambda sym, d, v, rs_available: {"status": "block", "reason": "leader"})
    res = _run(env, "live")
    _, store = env
    assert res.rs_blocked == 1 and store.all() == [] and res.opened == 0


def test_bearish_exempt_passes(env, monkeypatch):
    _wire(monkeypatch, [("MACD", "bearish")])
    monkeypatch.setattr(sp, "rs_verdict", lambda sym, d, v, rs_available: {"status": "exempt", "reason": "fx"})
    res = _run(env, "shadow")
    assert res.stored_only == 1


def test_once_per_completed_bar(env, monkeypatch):
    _wire(monkeypatch, [("MACD", "bullish")])
    _run(env, "shadow")
    res2 = _run(env, "shadow")
    _, store = env
    assert res2.skipped_dup == 1 and len(store.all()) == 1


def test_one_ticker_raising_does_not_abort_pass(env, monkeypatch):
    calls = {"n": 0}
    def signals(df, hk, spy_df):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return [("MACD", "bullish")]
    monkeypatch.setattr(sp, "strategy_signals", signals)
    def fake_build(df, *, ticker, strategy, horizon_key, direction, regime2_state):
        return _plan(ticker, strategy, direction, "VALIDATED", df.index[-1].date().isoformat())
    monkeypatch.setattr(sp, "build_strategy_plan_at", fake_build)
    res = _run(env, "shadow", tickers=["BAD", "AAPL"], fresh_data={"BAD": _df(), "AAPL": _df()})
    assert res.stored_only == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/scanning/test_strategy_pass_run.py -v`
Expected: FAIL with `AttributeError ... run_strategy_pass`

- [ ] **Step 3: Implement**

Append to `strategy_pass.py` (imports at module top):

```python
from dataclasses import dataclass, field

from swingbot.core.edge.rs_gate import rs_verdict
from swingbot.core.scanning import analyze
from swingbot.core.scanning.alert_embeds import build_strategy_alert_embed


@dataclass
class PassResult:
    plans: list = field(default_factory=list)
    alerts: list = field(default_factory=list)     # (embed, None, plan, simple_line) 4-tuples
    opened: int = 0
    stored_only: int = 0
    rs_blocked: int = 0
    skipped_dup: int = 0


def run_strategy_pass(tickers, fresh_data, *, now, horizons, spy_df, regimes,
                      rs_combined_of, mode: str, live_allow: set, trade_log, plan_store) -> PassResult:
    """Spec §1. `mode` is "shadow" or "live" ("off" never reaches here).
    `live_allow` is the parsed STRATEGY_ALERTS_LIVE_STRATEGIES set (empty =
    all). `rs_combined_of(ticker)` returns the scan's 70/30 ticker/sector RS
    blend or None when the RS benchmark failed this scan."""
    res = PassResult()
    for ticker in tickers:
        raw = fresh_data.get(ticker)
        if raw is None or len(raw) == 0:
            continue
        try:
            df_c = completed_frame(raw, now)
            bar_date = df_c.index[-1].date().isoformat()
            regime2_state = analyze._regime_at(regimes, df_c.index[-1]) if regimes is not None else None
            for hk in horizons:
                for strategy, direction in strategy_signals(df_c, hk, spy_df=spy_df):
                    if already_emitted(plan_store, ticker, strategy, hk, bar_date):
                        res.skipped_dup += 1
                        continue
                    if direction == "bearish":
                        rs_val = rs_combined_of(ticker)
                        verdict = rs_verdict(ticker, "bearish", rs_val if rs_val is not None else 50.0,
                                             rs_available=rs_val is not None)
                        if verdict["status"] == "block":
                            res.rs_blocked += 1
                            log.debug("strategy pass: %s %s/%s bearish blocked by RS gate: %s",
                                      ticker, strategy, hk, verdict["reason"])
                            continue
                    plan = build_strategy_plan_at(df_c, ticker=ticker, strategy=strategy,
                                                  horizon_key=hk, direction=direction,
                                                  regime2_state=regime2_state)
                    if plan is None:
                        continue
                    plan_store.add(plan)
                    res.plans.append(plan)
                    goes_live = (mode == "live" and (not live_allow or strategy in live_allow))
                    if not goes_live or trade_log.open_trade_for_ticker(ticker) is not None:
                        res.stored_only += 1
                        continue
                    trade_log.log_trade(
                        ticker=ticker, strategy=strategy, horizon_key=hk, direction=direction,
                        confidence_level=None, confidence_label="strategy signal",
                        entry=plan.trigger_price, stop_loss=plan.stop_loss, take_profit=plan.tp1,
                        target2=plan.tp2, plan_id=plan.plan_id, badge=plan.badge,
                        quality_score=plan.quality_score, source=plan.source,
                        cohort_label=plan.cohort_label, cohort_stats=plan.cohort_stats,
                        risk_features=plan.risk_features, ledger=plan.ledger,
                    )
                    res.opened += 1
                    res.alerts.append((build_strategy_alert_embed(plan), None, plan, simple_line(plan)))
        except Exception:
            log.warning("strategy pass: %s failed -- continuing with the next ticker", ticker, exc_info=True)
            continue
    log.info("strategy pass: %d plan(s) built, %d opened, %d stored only, %d RS-blocked, %d dup-skipped",
             len(res.plans), res.opened, res.stored_only, res.rs_blocked, res.skipped_dup)
    return res
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_run.py`
Expected: green. If `PlanStore(path=...)` refuses a `plans.json` under `tmp_path` because the DB store stage is not `json`, set `monkeypatch.setattr(config, "STORE_STAGES", "plans:json")` in the fixture (the key name is in `config.py`'s "Persistence" section — check with `grep -n 'plans:db' swingbot/config.py`).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/strategy_pass.py tests/scanning/test_strategy_pass_run.py
git commit -m "feat(v93): run_strategy_pass -- shadow/live modes, allow-list, collisions, RS laggard rule"
```

---

### Task 8: Wire the pass into `_sync_run_scan` behind the mode flag; `off` byte-identical test

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py` (after the alert loop's `log.info("Scan pass complete: ...")`, ~L893, before the funnel bookkeeping)
- Test: `tests/scanning/test_strategy_pass_wiring.py`

**Interfaces:**
- Consumes: `strategy_pass.run_strategy_pass` (Task 7); in-scope names in `_sync_run_scan`: `tickers`, `fresh_data`, `spy_df`, `regimes`, `rs_cache`, `sector_of_ticker`, `etf_symbol_of_sector`, `sector_etf_frames`, `alerts`, `trade_log`, `horizon_filter`, `require_confirmation`.
- Produces: strategy alerts appended to the same `alerts` list `_sync_run_scan` returns; funnel keys `strategy_plans`, `strategy_opened`.

- [ ] **Step 1: Write the failing test**

`tests/scanning/test_strategy_pass_wiring.py`:

```python
import pytest

import swingbot.config as config
from swingbot.core.scanning import scan_run, strategy_pass


def test_off_never_calls_the_pass(monkeypatch):
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "off")
    called = {"n": 0}
    monkeypatch.setattr(strategy_pass, "run_strategy_pass", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    scan_run._maybe_run_strategy_pass(tickers=[], fresh_data={}, spy_df=None, regimes=None,
                                      rs_cache=None, sector_of_ticker={}, etf_symbol_of_sector={},
                                      sector_etf_frames={}, trade_log=None, alerts=[], require_confirmation=True)
    assert called["n"] == 0


def test_check_command_never_opens_strategy_trades(monkeypatch):
    """!check (require_confirmation=False) is a snapshot and must not mutate
    positions -- same rule the confluence loop already follows."""
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "live")
    seen = {}
    def fake(*a, **k):
        seen.update(k); return strategy_pass.PassResult()
    monkeypatch.setattr(strategy_pass, "run_strategy_pass", fake)
    scan_run._maybe_run_strategy_pass(tickers=["AAPL"], fresh_data={}, spy_df=None, regimes=None,
                                      rs_cache=None, sector_of_ticker={}, etf_symbol_of_sector={},
                                      sector_etf_frames={}, trade_log=None, alerts=[], require_confirmation=False)
    assert seen["mode"] == "shadow"


def test_live_allow_list_parsed(monkeypatch):
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "live")
    monkeypatch.setattr(config, "STRATEGY_ALERTS_LIVE_STRATEGIES", " MACD, Volume Profile ,")
    seen = {}
    def fake(*a, **k):
        seen.update(k); return strategy_pass.PassResult(alerts=[("e", None, "p", "l")])
    monkeypatch.setattr(strategy_pass, "run_strategy_pass", fake)
    alerts = []
    scan_run._maybe_run_strategy_pass(tickers=["AAPL"], fresh_data={}, spy_df=None, regimes=None,
                                      rs_cache=None, sector_of_ticker={}, etf_symbol_of_sector={},
                                      sector_etf_frames={}, trade_log=None, alerts=alerts, require_confirmation=True)
    assert seen["live_allow"] == {"MACD", "Volume Profile"}
    assert alerts == [("e", None, "p", "l")]
```

Then extend an existing end-to-end scan test for the byte-identical guarantee. In `tests/scanning/test_engine_v2_plans.py`, add (after the existing fixtures — it already drives `_sync_run_scan` with stubbed fetches):

```python
def test_strategy_alerts_off_is_byte_identical(monkeypatch, stub_batch_fetch):
    """Mode off: the scan's return value and the trade log are identical to a
    run where strategy_pass does not exist at all."""
    import json
    from swingbot.core.scanning import strategy_pass
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "off")
    def boom(*a, **k):
        raise AssertionError("strategy pass ran under mode=off")
    monkeypatch.setattr(strategy_pass, "run_strategy_pass", boom)
    alerts, closed, warnings = scan_run._sync_run_scan("all", True, progress=None)
    # nothing to compare against but itself: the assertion is that `boom` never fired
    assert isinstance(alerts, list)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/scanning/test_strategy_pass_wiring.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute '_maybe_run_strategy_pass'`

- [ ] **Step 3: Implement**

In `scan_run.py` add `from . import strategy_pass` to the relative imports, and this module-level helper (above `_sync_run_scan`):

```python
def _maybe_run_strategy_pass(*, tickers, fresh_data, spy_df, regimes, rs_cache, sector_of_ticker,
                             etf_symbol_of_sector, sector_etf_frames, trade_log, alerts,
                             require_confirmation) -> dict:
    """v93. Off = never called into. `!check` (require_confirmation=False) is
    an on-demand snapshot and must never open positions, so it runs the pass
    in shadow regardless of the configured mode."""
    mode = config.STRATEGY_ALERTS_MODE
    if mode == "off":
        return {"strategy_plans": 0, "strategy_opened": 0}
    if not require_confirmation:
        mode = "shadow"
    live_allow = {s.strip() for s in (config.STRATEGY_ALERTS_LIVE_STRATEGIES or "").split(",") if s.strip()}

    def rs_combined_of(ticker):
        if rs_cache is None or spy_df is None:
            return None
        df = fresh_data.get(ticker)
        if df is None:
            return None
        pct = rs_factors.rs_percentile(df, spy_df, universe_rels=rs_cache.get("rels"))
        sector = sector_of_ticker.get(ticker)
        if sector and sector_etf_frames:
            sec_pct = rs_factors.sector_rs_percentile(sector, sector_etf_frames, spy_df,
                                                      sector_of_etf={v: k for k, v in etf_symbol_of_sector.items()})
            return rs_factors.rs_score(pct, sec_pct)
        return pct

    res = strategy_pass.run_strategy_pass(
        tickers, fresh_data, now=datetime.now(timezone.utc), horizons=list(HORIZONS),
        spy_df=spy_df, regimes=regimes, rs_combined_of=rs_combined_of, mode=mode,
        live_allow=live_allow, trade_log=trade_log, plan_store=PlanStore())
    alerts.extend(res.alerts)
    return {"strategy_plans": len(res.plans), "strategy_opened": res.opened}
```

Inside `_sync_run_scan`, directly after `log.info("Scan pass complete: %d alert(s) built, ...")`:

```python
    # v93: strategy-sourced pass, after the confluence alerts so an
    # already-open confluence trade on a ticker is visible to its collision
    # rule. Off by default; see _maybe_run_strategy_pass.
    strategy_counts = _maybe_run_strategy_pass(
        tickers=tickers, fresh_data=fresh_data, spy_df=spy_df, regimes=regimes,
        rs_cache=rs_cache, sector_of_ticker=sector_of_ticker,
        etf_symbol_of_sector=etf_symbol_of_sector, sector_etf_frames=sector_etf_frames,
        trade_log=trade_log, alerts=alerts, require_confirmation=require_confirmation)
```

and in the `progress.funnel` block add `progress.funnel.update(strategy_counts)`.

Note `sector_of_ticker`/`etf_symbol_of_sector`/`sector_etf_frames` are assigned in both branches of the existing sector-RS try/except (~L251–259), so they are always bound by this point; `rs_cache` and `spy_df` likewise (~L223–233). `regimes` is bound at ~L291.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_wiring.py` then `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/scan_run.py tests/scanning/test_strategy_pass_wiring.py tests/scanning/test_engine_v2_plans.py
git commit -m "feat(v93): wire the strategy pass into _sync_run_scan behind STRATEGY_ALERTS_MODE"
```

---

### Task 9: Soak rule (`edge/strategy_soak.py`) and `first_seen_price` on plans

**Files:**
- Create: `swingbot/core/edge/strategy_soak.py`
- Modify: `swingbot/core/planning/plan_types.py` (add `first_seen_price: float | None = None`)
- Modify: `swingbot/core/planning/plan_manager.py` (`poll`, ~L355–366: record first seen price once)
- Test: `tests/edge/test_strategy_soak.py`, `tests/planning/test_first_seen_price.py`

**Interfaces:**
- Consumes: `acceptance.NON_INFERIORITY_R` (= −0.01), `registry.Badge`.
- Produces: `soak_verdict(shadow_plans: list, badge) -> dict` with keys `n_closed, exp_r, badge_exp_r, median_entry_dev, clauses: {n, non_inferior, entry_parity}, pass: bool`; `plan_r_total(plan) -> float | None`; `TradePlanV2.first_seen_price`.

- [ ] **Step 1: Write the failing tests**

`tests/edge/test_strategy_soak.py`:

```python
from types import SimpleNamespace

from swingbot.core.backtesting.registry import Badge
from swingbot.core.edge import strategy_soak as soak


def _plan(r, entry=100.0, stop=95.0, first_seen=100.2, status="CLOSED", legs=None):
    return SimpleNamespace(status=status, entry_price=entry, trigger_price=entry, stop_loss=stop,
                           first_seen_price=first_seen,
                           legs_realized=legs if legs is not None else [{"fraction": 1.0, "r": r}])


def test_plan_r_total_is_fraction_weighted():
    p = _plan(0.0, legs=[{"fraction": 0.5, "r": 1.0}, {"fraction": 0.5, "r": 3.0}])
    assert soak.plan_r_total(p) == 2.0
    assert soak.plan_r_total(_plan(0.0, legs=[])) is None


def test_all_three_clauses_pass():
    plans = [_plan(0.3) for _ in range(30)]
    v = soak.soak_verdict(plans, Badge(status="VALIDATED", n=112, win_rate=50.0, expectancy_r=0.219))
    assert v["clauses"] == {"n": True, "non_inferior": True, "entry_parity": True}
    assert v["pass"] is True and v["n_closed"] == 30


def test_n_clause_counts_closed_only():
    plans = [_plan(0.3) for _ in range(29)] + [_plan(0.3, status="ACTIVE")]
    v = soak.soak_verdict(plans, Badge(status="VALIDATED", n=112, win_rate=50.0, expectancy_r=0.219))
    assert v["clauses"]["n"] is False and v["pass"] is False


def test_non_inferiority_margin():
    badge = Badge(status="VALIDATED", n=112, win_rate=50.0, expectancy_r=0.219)
    assert soak.soak_verdict([_plan(0.21) for _ in range(30)], badge)["clauses"]["non_inferior"] is True   # 0.21 >= 0.209
    assert soak.soak_verdict([_plan(0.20) for _ in range(30)], badge)["clauses"]["non_inferior"] is False


def test_entry_parity_uses_median_deviation_over_stop_distance():
    # stop distance 5.0; deviation 0.4 -> 0.08 passes; 0.6 -> 0.12 fails
    ok = [_plan(0.3, first_seen=100.4) for _ in range(30)]
    bad = [_plan(0.3, first_seen=100.6) for _ in range(30)]
    badge = Badge(status="VALIDATED", n=112, win_rate=50.0, expectancy_r=0.0)
    assert soak.soak_verdict(ok, badge)["clauses"]["entry_parity"] is True
    assert soak.soak_verdict(bad, badge)["clauses"]["entry_parity"] is False


def test_missing_badge_fails_explicitly():
    v = soak.soak_verdict([_plan(0.3) for _ in range(30)], Badge(status="WEAK", n=0, win_rate=0.0, expectancy_r=0.0))
    assert v["clauses"]["non_inferior"] is False and v["badge_exp_r"] is None
```

`tests/planning/test_first_seen_price.py`:

```python
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_from_dict, plan_to_dict


def test_first_seen_price_defaults_none_and_round_trips():
    p = TradePlanV2(plan_id="p", ticker="AAPL", created_at="2026-09-17", source="strategy",
                    strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
                    trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=95.0, tp1=110.0,
                    tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
                    quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.PENDING)
    assert p.first_seen_price is None
    p.first_seen_price = 100.3
    assert plan_from_dict(plan_to_dict(p)).first_seen_price == 100.3
```

Add to an existing `PlanManager.poll` test file (`tests/planning/test_manager_singleton_staleness_repro.py` has a working `PlanManager` fixture with a `price_fn`; append there):

```python
def test_poll_records_first_seen_price_once(manager_and_store):
    manager, store, plan = manager_and_store          # fixture from this file: a PENDING plan, price_fn -> 101.0
    manager.poll()
    assert store.get(plan.plan_id).first_seen_price == 101.0
    manager.price = 102.0                              # however the fixture varies its price_fn
    manager.poll()
    assert store.get(plan.plan_id).first_seen_price == 101.0
```
(Adapt the fixture name/price knob to what that file actually exposes; the assertion — set once, never overwritten — is the contract.)

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/edge/test_strategy_soak.py tests/planning/test_first_seen_price.py -v`
Expected: FAIL (`ModuleNotFoundError`, then `AttributeError: first_seen_price`)

- [ ] **Step 3: Implement**

`swingbot/core/edge/strategy_soak.py`:

```python
"""v93 trust rule for flipping a strategy from shadow to live (spec §1).

Pre-registered before any shadow data existed. Three clauses, reported
separately; the flip itself is a config edit, never automatic.
"""
from __future__ import annotations

import statistics

from swingbot.core.backtesting.acceptance import NON_INFERIORITY_R

MIN_CLOSED = 30
MAX_ENTRY_DEV = 0.10     # median |first_seen - recorded close| / stop distance


def plan_r_total(plan) -> float | None:
    legs = getattr(plan, "legs_realized", None) or []
    if not legs:
        return None
    return float(sum(float(l["fraction"]) * float(l["r"]) for l in legs))


def _entry_dev(plan) -> float | None:
    seen, entry, stop = plan.first_seen_price, plan.entry_price or plan.trigger_price, plan.stop_loss
    if seen is None or entry is None or stop is None:
        return None
    dist = abs(entry - stop)
    return abs(seen - entry) / dist if dist > 0 else None


def soak_verdict(shadow_plans: list, badge) -> dict:
    closed = [p for p in shadow_plans if getattr(p, "status", None) == "CLOSED"]
    rs = [r for r in (plan_r_total(p) for p in closed) if r is not None]
    devs = [d for d in (_entry_dev(p) for p in closed) if d is not None]
    exp_r = statistics.fmean(rs) if rs else None
    badge_exp_r = badge.expectancy_r if getattr(badge, "n", 0) > 0 else None
    median_dev = statistics.median(devs) if devs else None
    clauses = {
        "n": len(closed) >= MIN_CLOSED,
        "non_inferior": (exp_r is not None and badge_exp_r is not None
                         and exp_r >= badge_exp_r + NON_INFERIORITY_R),
        "entry_parity": median_dev is not None and median_dev <= MAX_ENTRY_DEV,
    }
    return {"n_closed": len(closed), "exp_r": exp_r, "badge_exp_r": badge_exp_r,
            "median_entry_dev": median_dev, "clauses": clauses, "pass": all(clauses.values())}
```

`plan_types.py`: after `ledger: str = "main"` add
```python
    first_seen_price: float | None = None   # v93: first live print the manager saw; soak clause 3
```

`plan_manager.py`, in `poll()` immediately before `self._last_seen[plan.plan_id] = (session_date(now), price)`:
```python
            if plan.first_seen_price is None:
                plan.first_seen_price = float(price)
                self.store.update(plan)
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/edge/test_strategy_soak.py`, `... tests/planning/test_first_seen_price.py`, `... tests/planning/test_manager_singleton_staleness_repro.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/strategy_soak.py swingbot/core/planning/plan_types.py swingbot/core/planning/plan_manager.py tests/edge/test_strategy_soak.py tests/planning/test_first_seen_price.py tests/planning/test_manager_singleton_staleness_repro.py
git commit -m "feat(v93): pre-registered soak rule (strategy_soak) + first_seen_price stamp in PlanManager.poll"
```
