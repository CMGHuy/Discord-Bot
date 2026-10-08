# v142 — Partials analytics tab: Part 1 — production check, contract, live stamps

> Part of [`2026-10-08-v142-partials-analytics-tab_0-index.md`](2026-10-08-v142-partials-analytics-tab_0-index.md). The index carries the header block, the spec resolutions, the Global Constraints, the Review Focus and the full `## Parallelisation`. Read it first. **Pull one task at a time:** `grep -n "^### Task V142-2" -A 300 <this file>`. Part 2 (`_2-backfill-metrics-api.md`) continues Phase 2 with V142-4 and V142-5, then Phase 3.

# Phase 0 — Worktree and production cache check

## Parallelisation

Sequential. V142-0 creates the worktree every later task runs in. Its answer (which cache production holds) fixes the backfill's bar source.

### Task V142-0: Worktree and read-only production cache check

**Files:**
- Create: none in the repo. One probe script in your session scratchpad (never committed).

**Interfaces:**
- Consumes: nothing.
- Produces: the worktree `.claude/worktrees/2026-10-08-v142-partials-analytics-tab` (branch of the same name, off `main`), and a confirmed answer to "which daily cache does production hold for every ticker with a partial plan".

- [ ] **Step 1: Create the worktree**

Use the `worktree-lifecycle` skill. The expected commands are:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-08-v142-partials-analytics-tab -b 2026-10-08-v142-partials-analytics-tab main
```

Expected: `Preparing worktree (new branch '2026-10-08-v142-partials-analytics-tab')`.

- [ ] **Step 2: Write the read-only probe to the scratchpad**

Save as `<scratchpad>/v142_cache_check.py`. It reads plans and checks for files only. It writes nothing and makes no network call.

```python
import os

from swingbot import config
from swingbot.core.marketdata import data_store
from swingbot.core.planning.plan_store import PlanStore

plans = [p for p in PlanStore().all()
         if any(h.get("status") == "PARTIAL" for h in p.status_history)]
tickers = sorted({p.ticker for p in plans})
md = [t for t in tickers if data_store.load_normalized(t, "daily") is not None]
bt_dir = os.path.join(config.DATA_DIR, "backtest_cache")
bt = [t for t in tickers
      if os.path.exists(os.path.join(bt_dir, data_store.safe_symbol(t) + ".csv"))]
print(f"partial plans={len(plans)} tickers={len(tickers)} "
      f"market_data/daily={len(md)} backtest_cache={len(bt)}")
print("missing from market_data/daily:", sorted(set(tickers) - set(md)))
```

- [ ] **Step 3: Run it on production, read-only**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < <scratchpad>/v142_cache_check.py
```

Expected (2026-10-08 values; counts grow over time): `partial plans=190 tickers=48 market_data/daily=48 backtest_cache=4`, then `missing from market_data/daily: []`.

- [ ] **Step 4: Decide**

- `market_data/daily` covers every ticker → the plan's bar source (`runner_path.cached_daily_bars` → `data_store.load_normalized(ticker, "daily")`) stands. Continue.
- Any ticker is missing from `market_data/daily` → **stop and ask the partner** (`AskUserQuestion`). The recommended option is to proceed and let those plans count as `unavailable` in the backfill. Never add a network fetch.

No commit (nothing changed in the repo).

# Phase 1 — The runner_path contract

## Parallelisation

Sequential: V142-1 alone. It introduces `TradePlanV2.runner_path` and every `runner_path` symbol that Group A consumes.

### Task V142-1: runner_path helper and the TradePlanV2 field

**Files:**
- Create: `swingbot/core/analytics/runner_path.py`
- Modify: `swingbot/core/planning/plan_types.py` (after `limit_strict_fill`, the last field of `TradePlanV2`, ~line 152)
- Test: `tests/analytics/test_runner_path.py` (create), `tests/planning/test_plan_serialization.py` (append), `tests/planning/test_plan_store_db.py` (append)

**Interfaces:**
- Consumes: `swingbot.core.market.session.nyse_calendar`, `US_MARKET_TZ`; `swingbot.core.marketdata.data_store.load_normalized`.
- Produces (`swingbot/core/analytics/runner_path.py`):
  - `LADDER_R: tuple[float, ...] = (1.5, 2.0, 2.5, 3.0, 4.0)`; `STOP_EXIT_REASONS: frozenset[str]`
  - `compute_runner_path(plan, bars, *, source: str = "live") -> dict | None`
  - `stamp_runner_path(plan, bars_fn, *, source: str = "live") -> dict | None`: sets `plan.runner_path`, never raises
  - `cached_daily_bars(ticker: str) -> pd.DataFrame | None`: disk only
  - `et_day(stamp) -> date | None`, `transition_day(plan, status: str) -> date | None`, `close_reason(plan) -> str | None`, `tp1_leg(plan) -> dict | None`, `runner_leg(plan) -> dict | None`, `session_span(start: date, end: date) -> int`
  - `TradePlanV2.runner_path: dict | None = None`
  - Test helpers others import from `tests/analytics/test_runner_path.py`: `_closed(reason, runner_price, *, direction="bullish", partial_at=MON, closed_at=WED, runner_leg=True)`, `_bars(rows)`, `LONG_BARS`, `FILL`, `MON`, `WED`.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_runner_path.py`:

```python
"""v142: compute_runner_path -- the runner's post-TP1 path, from daily bars."""
import logging

import pandas as pd
import pytest

from swingbot.core.analytics import runner_path as rp
from swingbot.core.planning.plan_engine import PlanStatus
from tests.planning.test_plan_engine_model import _plan

FILL = "2026-10-01T14:00:00+00:00"     # Thu
MON = "2026-10-05T15:00:00+00:00"      # TP1 session
WED = "2026-10-07T18:00:00+00:00"      # runner exit session


def _closed(reason, runner_price, *, direction="bullish", partial_at=MON, closed_at=WED,
            runner_leg=True):
    """A closed partial plan: entry 100, risk 5, TP1 filled at exactly 2.0R."""
    bull = direction == "bullish"
    sign = 1 if bull else -1
    stop, tp1, tp2 = (95.0, 110.0, 120.0) if bull else (105.0, 90.0, 80.0)
    legs = [{"fraction": 0.5, "exit_price": tp1, "r": 2.0, "reason": "tp1", "closed_at": partial_at}]
    if runner_leg:
        legs.append({"fraction": 0.5, "exit_price": runner_price,
                     "r": (runner_price - 100.0) * sign / 5.0, "reason": reason,
                     "closed_at": closed_at})
    return _plan(direction=direction, entry_price=100.0, stop_loss=stop, tp1=tp1, tp2=tp2,
                 status=PlanStatus.CLOSED, legs_realized=legs,
                 status_history=[{"status": "ACTIVE", "reason": "filled", "at": FILL},
                                 {"status": "PARTIAL", "reason": "tp1_partial", "at": partial_at},
                                 {"status": "CLOSED", "reason": reason, "at": closed_at}])


def _bars(rows):
    """rows: [(YYYY-MM-DD, high, low)] -> a daily OHLC frame."""
    index = pd.to_datetime([day for day, _, _ in rows])
    highs = [high for _, high, _ in rows]
    lows = [low for _, _, low in rows]
    return pd.DataFrame({"Open": lows, "High": highs, "Low": lows, "Close": highs}, index=index)


LONG_BARS = _bars([("2026-10-05", 112.0, 104.0), ("2026-10-06", 116.0, 108.0),
                   ("2026-10-07", 121.0, 115.0)])


def test_long_tp2_runner_path():
    path = rp.compute_runner_path(_closed("tp1_runner_tp2", 120.0), LONG_BARS)
    # MON's low (0.8R) may predate TP1, so it never reaches MAE; TUE's 1.6R does.
    assert path == {"mfe_r": 4.2, "mae_r": 1.6,
                    "ladder": {"1.5": "2026-10-05", "2.0": "2026-10-05", "2.5": "2026-10-06",
                               "3.0": "2026-10-06", "4.0": "2026-10-07"},
                    "sessions_after_tp1": 2, "source": "live"}


def test_short_runner_path_mirrors_the_long():
    bars = _bars([("2026-10-05", 96.0, 88.0), ("2026-10-06", 92.0, 84.0),
                  ("2026-10-07", 85.0, 79.0)])
    path = rp.compute_runner_path(_closed("tp1_runner_tp2", 80.0, direction="bearish"), bars)
    assert (path["mfe_r"], path["mae_r"]) == (4.2, 1.6)
    assert path["ladder"] == {"1.5": "2026-10-05", "2.0": "2026-10-05", "2.5": "2026-10-06",
                              "3.0": "2026-10-06", "4.0": "2026-10-07"}


def test_a_gap_through_a_level_counts_as_touched():
    # TUE gaps from 111 straight to 117: 2.5R (112.5) and 3.0R (115) never trade
    # inside a bar, but the gap went through both.
    bars = _bars([("2026-10-05", 111.0, 105.0), ("2026-10-06", 117.5, 116.5),
                  ("2026-10-07", 118.0, 113.0)])
    path = rp.compute_runner_path(_closed("tp1_runner_trail", 113.0), bars)
    assert path["ladder"]["2.5"] == "2026-10-06" and path["ladder"]["3.0"] == "2026-10-06"


def test_a_stop_exit_session_counts_only_the_exit_fill():
    # WED spikes to 125 (5R) but the trail exit at 113 is assumed to come first.
    bars = _bars([("2026-10-05", 111.0, 105.0), ("2026-10-06", 114.0, 112.0),
                  ("2026-10-07", 125.0, 112.5)])
    path = rp.compute_runner_path(_closed("tp1_runner_trail", 113.0), bars)
    assert path["mfe_r"] == 2.8                  # TUE's 114 -> 2.8R; WED's 125 ignored
    assert path["ladder"]["4.0"] is None and path["ladder"]["3.0"] is None
    assert path["mae_r"] == 2.0                  # TP1 fill; WED's low ignored, exit 2.6R


def test_a_non_stop_exit_session_counts_its_bar():
    bars = _bars([("2026-10-05", 111.0, 105.0), ("2026-10-06", 114.0, 112.0),
                  ("2026-10-07", 125.0, 112.5)])
    path = rp.compute_runner_path(_closed("tp1_runner_progress_stall", 113.0), bars)
    assert path["mfe_r"] == 5.0 and path["ladder"]["4.0"] == "2026-10-07"


def test_tp1_and_exit_on_the_same_session():
    plan = _closed("tp1_runner_be", 106.66666666666667, closed_at="2026-10-05T19:00:00+00:00")
    path = rp.compute_runner_path(plan, _bars([("2026-10-05", 130.0, 90.0)]))
    assert path["sessions_after_tp1"] == 0
    assert path["mfe_r"] == 2.0                  # floored at the TP1 R; the bar is a stop-exit bar
    assert path["mae_r"] == pytest.approx(1.3333, abs=1e-4)
    assert path["ladder"] == {"1.5": "2026-10-05", "2.0": "2026-10-05", "2.5": None,
                              "3.0": None, "4.0": None}


def test_the_tp1_session_counts_a_level_beyond_tp1_its_bar_reached():
    bars = _bars([("2026-10-05", 113.0, 96.0), ("2026-10-06", 112.0, 108.0),
                  ("2026-10-07", 112.0, 108.0)])
    path = rp.compute_runner_path(_closed("tp1_runner_trail", 108.0), bars)
    assert path["ladder"]["2.5"] == "2026-10-05"
    assert path["mae_r"] == 1.6                  # MON's 96 low is not counted


def test_a_missing_session_bar_returns_none():
    bars = _bars([("2026-10-05", 112.0, 104.0), ("2026-10-07", 121.0, 115.0)])  # no TUE
    assert rp.compute_runner_path(_closed("tp1_runner_tp2", 120.0), bars) is None
    assert rp.compute_runner_path(_closed("tp1_runner_tp2", 120.0), None) is None


def test_a_still_forming_exit_session_bar_is_optional():
    bars = _bars([("2026-10-05", 112.0, 104.0), ("2026-10-06", 116.0, 108.0)])  # no WED yet
    path = rp.compute_runner_path(_closed("tp1_runner_tp2", 120.0), bars)
    assert path["mfe_r"] == 4.0                  # the TP2 fill itself
    assert path["ladder"]["4.0"] == "2026-10-07"


def test_a_manual_close_without_a_runner_leg_uses_the_exit_bar():
    plan = _closed("manual", 0.0, runner_leg=False)
    path = rp.compute_runner_path(plan, LONG_BARS)
    assert path["mfe_r"] == 4.2 and path["mae_r"] == 1.6


def test_a_plan_without_a_partial_transition_has_no_path():
    plan = _closed("tp1_runner_tp2", 120.0)
    plan.status_history = [h for h in plan.status_history if h["status"] != "PARTIAL"]
    assert rp.compute_runner_path(plan, LONG_BARS) is None


def test_source_is_recorded():
    path = rp.compute_runner_path(_closed("tp1_runner_tp2", 120.0), LONG_BARS, source="backfill")
    assert path["source"] == "backfill"


def test_stamp_sets_the_field_and_logs_a_miss(caplog):
    plan = _closed("tp1_runner_tp2", 120.0)
    assert rp.stamp_runner_path(plan, lambda ticker: LONG_BARS)["mfe_r"] == 4.2
    assert plan.runner_path["source"] == "live"
    with caplog.at_level(logging.INFO, logger=rp.log.name):
        assert rp.stamp_runner_path(plan, lambda ticker: None) is None
    assert plan.runner_path is None
    assert [r.getMessage() for r in caplog.records if r.name == rp.log.name] == [
        "runner_path: no stamp for p1 (AAPL) -- bars do not cover the runner window"]


def test_stamp_never_raises():
    plan = _closed("tp1_runner_tp2", 120.0)

    def boom(ticker):
        raise OSError("disk gone")

    assert rp.stamp_runner_path(plan, boom) is None
    assert plan.runner_path is None


def test_cached_daily_bars_reads_the_disk_cache_only(monkeypatch):
    from swingbot.core.marketdata import data_store
    calls = []
    monkeypatch.setattr(data_store, "load_normalized",
                        lambda ticker, interval: calls.append((ticker, interval)) or "frame")
    assert rp.cached_daily_bars("AAPL") == "frame"
    assert calls == [("AAPL", "daily")]
```

Append to `tests/planning/test_plan_serialization.py`:

```python
def test_runner_path_defaults_to_none_and_round_trips():
    """v142: a pre-v142 record has no stamp and loads as None -- never inferred."""
    assert _plan().runner_path is None
    d = plan_to_dict(_plan())
    d.pop("runner_path")
    assert plan_from_dict(d).runner_path is None
    path = {"mfe_r": 4.2, "mae_r": 1.6, "sessions_after_tp1": 2, "source": "live",
            "ladder": {"1.5": "2026-10-05", "2.0": "2026-10-05", "2.5": "2026-10-06",
                       "3.0": "2026-10-06", "4.0": None}}
    assert plan_from_dict(plan_to_dict(_plan(runner_path=path))).runner_path == path
```

Append to `tests/planning/test_plan_store_db.py`:

```python
def test_runner_path_round_trips_through_the_doc():
    """v142: the stamp rides in plans.doc (schema-evolution "add"; no Alembic)."""
    plan = _plan()
    plan.runner_path = {"mfe_r": 4.2, "mae_r": 1.6, "sessions_after_tp1": 2, "source": "backfill",
                        "ladder": {"1.5": "2026-10-05", "2.0": None, "2.5": None,
                                   "3.0": None, "4.0": None}}
    PlanStore().add(plan)
    assert PlanStore().get("P1").runner_path == plan.runner_path
```

- [ ] **Step 2: Run them to verify they fail**

```bash
python scripts/dev/testrun.py file tests/analytics/test_runner_path.py
python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py
python scripts/dev/testrun.py file tests/planning/test_plan_store_db.py
```

Expected: FAIL. The first fails with `ImportError: cannot import name 'runner_path'`. The serialization test fails with `TypeError: TradePlanV2.__init__() got an unexpected keyword argument 'runner_path'`. The store test fails with `assert None == {...}`, because `plan_to_dict` drops the unknown attribute. A **SKIPPED** DB test is not a failure for the right reason: start `db-test` first (Global Constraints).

- [ ] **Step 3: Add the field**

In `swingbot/core/planning/plan_types.py`, directly after `    limit_strict_fill: bool = False` (the last `TradePlanV2` field):

```python
    # v142: the runner's post-TP1 path (analytics/runner_path.py), stamped at
    # runner close -- {"mfe_r", "mae_r", "ladder", "sessions_after_tp1",
    # "source"}. None = never stamped (pre-v142, or the bars did not cover the
    # window); readers never infer it, the backfill writes it.
    runner_path: dict | None = None
```

- [ ] **Step 4: Write the helper**

Create `swingbot/core/analytics/runner_path.py`:

```python
"""v142: the runner's post-TP1 price path, stamped onto a plan at runner close.

`compute_runner_path` is pure. R is measured against the plan's initial risk
(`entry_price - stop_loss`), the basis of `metrics.r_multiple`. A daily bar
cannot order intrabar events, so:

- on the TP1 session only the bar's favourable extreme counts (it can only
  have printed after TP1 was crossed); its adverse extreme may predate TP1;
- on the exit session of a stop / floor / trail exit the bar counts for
  nothing -- the exit is assumed to have come first;
- the runner's own fills (TP1 leg, runner leg) are prices that certainly
  traded, so each is a point on its session.

`cached_daily_bars` reads the live scan's own disk cache (market_data/daily)
and never fetches. `stamp_runner_path` never raises: a close is never blocked
by its stamp.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import NamedTuple

import pandas as pd

from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar

log = logging.getLogger(__name__)

#: R levels of the TP2 ladder, keyed in the stamp as "1.5", "2.0", ...
LADDER_R = (1.5, 2.0, 2.5, 3.0, 4.0)
#: Runner closes where a resting stop took the position out (floor, trail).
STOP_EXIT_REASONS = frozenset({"tp1_runner_be", "tp1_runner_trail"})
_TOUCH_TOL = 1e-9


class RunnerContext(NamedTuple):
    entry: float
    risk: float
    sign: int
    r_tp1: float
    exit_r: float | None      # None: no runner leg on the plan (a manual close)
    stop_exit: bool
    tp1_day: dt.date
    exit_day: dt.date


def et_day(stamp) -> dt.date | None:
    """The US/Eastern date of an ISO timestamp; None when absent or unparseable."""
    if not stamp:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(US_MARKET_TZ).date()


def transition_day(plan, status: str) -> dt.date | None:
    """ET date of the first `status_history` entry with `status`."""
    for entry in plan.status_history or []:
        if entry.get("status") == status:
            return et_day(entry.get("at"))
    return None


def close_reason(plan) -> str | None:
    """The reason recorded on the plan's CLOSED transition."""
    return next((entry.get("reason") for entry in plan.status_history or []
                 if entry.get("status") == "CLOSED"), None)


def tp1_leg(plan) -> dict | None:
    return next((leg for leg in plan.legs_realized or [] if leg.get("reason") == "tp1"), None)


def runner_leg(plan) -> dict | None:
    """The realised leg that closed the runner; None while open, and for a
    manual close (the admin close records no leg on the plan)."""
    return next((leg for leg in plan.legs_realized or [] if leg.get("reason") != "tp1"), None)


def session_span(start: dt.date, end: dt.date) -> int:
    """NYSE sessions from `start` to `end`, not counting `start`; 0 for one session."""
    return max(0, len(nyse_calendar().sessions(start, end)) - 1)


def _leg_r(leg: dict | None, entry: float, risk: float, sign: int) -> float | None:
    if leg is None:
        return None
    if leg.get("r") is not None:
        return float(leg["r"])
    price = leg.get("exit_price")
    return None if price is None else (float(price) - entry) * sign / risk


def runner_context(plan) -> RunnerContext | None:
    """Everything the path needs from the plan, or None for a record that
    cannot carry one (no fill, zero risk, no TP1 leg, no dated transitions)."""
    entry, stop = plan.entry_price, plan.stop_loss
    if entry is None or stop is None or entry == stop:
        return None
    risk, sign = abs(entry - stop), (1 if plan.direction == "bullish" else -1)
    r_tp1 = _leg_r(tp1_leg(plan), entry, risk, sign)
    tp1_day, exit_day = transition_day(plan, "PARTIAL"), transition_day(plan, "CLOSED")
    if r_tp1 is None or tp1_day is None or exit_day is None or exit_day < tp1_day:
        return None
    return RunnerContext(entry, risk, sign, r_tp1, _leg_r(runner_leg(plan), entry, risk, sign),
                         close_reason(plan) in STOP_EXIT_REASONS, tp1_day, exit_day)


def _bar_extremes(bars, ctx: RunnerContext) -> dict[dt.date, tuple[float, float]]:
    """{session: (favourable R, adverse R)} for every usable bar in the window."""
    if bars is None or len(bars) == 0 or not {"High", "Low"} <= set(bars.columns):
        return {}
    out: dict[dt.date, tuple[float, float]] = {}
    for stamp, high, low in zip(bars.index, bars["High"], bars["Low"]):
        day = pd.Timestamp(stamp).date()
        if not (ctx.tp1_day <= day <= ctx.exit_day) or pd.isna(high) or pd.isna(low):
            continue
        fav, adv = (high, low) if ctx.sign > 0 else (low, high)
        out[day] = ((float(fav) - ctx.entry) * ctx.sign / ctx.risk,
                    (float(adv) - ctx.entry) * ctx.sign / ctx.risk)
    return out


def _window(ctx: RunnerContext) -> tuple[list[dt.date], list[dt.date]]:
    """(every day the path walks, the days whose bar must exist). The exit
    session's bar is optional: live, it is usually still forming."""
    calendar = nyse_calendar()
    days = sorted(set(calendar.sessions(ctx.tp1_day, ctx.exit_day)) | {ctx.tp1_day, ctx.exit_day})
    required = [day for day in days if day != ctx.exit_day and calendar.is_session(day)]
    return days, required


def _day_points(ctx: RunnerContext, day: dt.date, bar) -> tuple[list[float], list[float]]:
    """(favourable, adverse) R points one session contributes."""
    fav: list[float] = []
    adv: list[float] = []
    is_tp1, is_exit = day == ctx.tp1_day, day == ctx.exit_day
    if is_tp1:
        fav.append(ctx.r_tp1)
        adv.append(ctx.r_tp1)
    if is_exit and ctx.exit_r is not None:
        fav.append(ctx.exit_r)
        adv.append(ctx.exit_r)
    if bar is not None and not (is_exit and ctx.stop_exit):
        fav.append(bar[0])
        if not is_tp1:
            adv.append(bar[1])
    return fav, adv


def _first_touch(best_by_day: dict[dt.date, float], level: float) -> str | None:
    return next((day.isoformat() for day in sorted(best_by_day)
                 if best_by_day[day] >= level - _TOUCH_TOL), None)


def _summarise(ctx: RunnerContext, days, extremes, source: str) -> dict:
    best_by_day: dict[dt.date, float] = {}
    adverse: list[float] = []
    for day in days:
        fav, adv = _day_points(ctx, day, extremes.get(day))
        if fav:
            best_by_day[day] = max(fav)
        adverse.extend(adv)
    return {
        "mfe_r": round(max([ctx.r_tp1, *best_by_day.values()]), 4),
        "mae_r": round(min(adverse), 4),
        "ladder": {f"{level:.1f}": _first_touch(best_by_day, level) for level in LADDER_R},
        "sessions_after_tp1": session_span(ctx.tp1_day, ctx.exit_day),
        "source": source,
    }


def compute_runner_path(plan, bars, *, source: str = "live") -> dict | None:
    """The `runner_path` stamp for a closed partial plan, or None when the
    plan cannot carry one or `bars` do not cover TP1 session .. exit session."""
    ctx = runner_context(plan)
    if ctx is None:
        return None
    days, required = _window(ctx)
    extremes = _bar_extremes(bars, ctx)
    if any(day not in extremes for day in required):
        return None
    return _summarise(ctx, days, extremes, source)


def cached_daily_bars(ticker: str):
    """The live scan's daily cache (`market_data/daily`), from disk. Never a fetch."""
    from swingbot.core.marketdata import data_store
    return data_store.load_normalized(ticker, "daily")


def stamp_runner_path(plan, bars_fn, *, source: str = "live") -> dict | None:
    """Set `plan.runner_path` from `bars_fn(ticker)`; None plus one log line
    when the bars do not cover the window. Never raises."""
    path = None
    try:
        bars = bars_fn(plan.ticker) if bars_fn is not None else None
        path = compute_runner_path(plan, bars, source=source)
    except Exception as exc:
        log.warning("runner_path: stamp failed for %s (%s): %s", plan.plan_id, plan.ticker, exc,
                    exc_info=True)
    if path is None:
        log.info("runner_path: no stamp for %s (%s) -- bars do not cover the runner window",
                 plan.plan_id[:8], plan.ticker)
    plan.runner_path = path
    return path
```

- [ ] **Step 5: Run the tests to verify they pass, and check complexity**

```bash
python scripts/dev/testrun.py file tests/analytics/test_runner_path.py
python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py
python scripts/dev/testrun.py file tests/planning/test_plan_store_db.py
python -m radon cc -s -n C swingbot/core/analytics/runner_path.py
```

Expected: `VERDICT: PASS` ×3 (15, all serialization tests, all store-db tests; none skipped). radon prints nothing (the highest function is `runner_context`, B (9)).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/runner_path.py swingbot/core/planning/plan_types.py tests/analytics/test_runner_path.py tests/planning/test_plan_serialization.py tests/planning/test_plan_store_db.py
git commit -m "$(cat <<'EOF'
feat(v142): runner_path stamp helper and TradePlanV2.runner_path

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

# Phase 2 — Group A: live stamping, manual stamping, backfill, metrics

## Parallelisation

Group A (parallel): V142-2, V142-3, V142-4, V142-5. Each touches only its own two files (listed per task) and consumes only V142-1's symbols. Name the worktree in every dispatch. After each task, check that `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows no change in the main tree.

### Task V142-2: Live stamp on every automated runner close

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py`: the import block (~:16), `PlanManager.__init__` (~:319-338), `_close_runner` (~:1001-1012), `_manager` (~:1303-1312)
- Test: `tests/planning/test_plan_manager_runner_path.py` (create)

**Interfaces:**
- Consumes: `runner_path.stamp_runner_path`, `runner_path.cached_daily_bars` (V142-1); test helpers `FILL`, `MON`, `WED`, `LONG_BARS` from `tests/analytics/test_runner_path.py`.
- Produces: `PlanManager(..., runner_bars_fn=None)`: a new keyword, `ticker -> DataFrame | None`. Every close through `_close_runner` stamps `plan.runner_path` with `source="live"` in the same store write. That covers `tp1_runner_tp2`, `tp1_runner_trail`, `tp1_runner_be`, `tp1_runner_progress_stall`, and `time_exit` of a PARTIAL plan (via `_close_time_exit`), on the poll path and the `check_bar` path. The production `_manager()` passes `rp.cached_daily_bars`.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_plan_manager_runner_path.py`:

```python
"""v142: every runner close stamps runner_path (source "live"); a stamp that
cannot be computed leaves it null and never blocks the close."""
import pytest

from swingbot.core.analytics import runner_path as rp
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_engine import PlanStatus, runner_floor
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.analytics.test_runner_path import FILL, LONG_BARS, MON, WED
from tests.planning.test_plan_engine_model import _plan


def _partial():
    """Entry 100, risk 5, TP1 (110) banked MON at 2.0R, runner open on the floor."""
    return _plan(entry_price=100.0, stop_loss=95.0, tp1=110.0, tp2=120.0,
                 status=PlanStatus.PARTIAL, working_stop=runner_floor(100.0, 110.0),
                 legs_realized=[{"fraction": 0.5, "exit_price": 110.0, "r": 2.0,
                                 "reason": "tp1", "closed_at": MON}],
                 status_history=[{"status": "ACTIVE", "reason": "filled", "at": FILL},
                                 {"status": "PARTIAL", "reason": "tp1_partial", "at": MON}])


def _manager(bars_fn):
    store = PlanStore()
    store.add(_partial())
    mgr = PlanManager(store, lambda ticker: None, runner_bars_fn=bars_fn)
    mgr._now = lambda: WED                      # the runner exits on WED
    return store, mgr


def test_a_floor_close_on_the_bar_path_stamps_live():
    store, mgr = _manager(lambda ticker: LONG_BARS)
    [event] = mgr.check_bar("p1", 107.0, 108.0, 106.0)
    assert event.detail["reason"] == "tp1_runner_be"
    path = store.get("p1").runner_path
    # A floor exit: WED's 121 high is not counted; TUE's 116 is the best.
    assert (path["source"], path["mfe_r"], path["ladder"]["4.0"]) == ("live", 3.2, None)


def test_a_tp2_close_counts_the_exit_session_bar():
    store, mgr = _manager(lambda ticker: LONG_BARS)
    [event] = mgr.check_bar("p1", 118.0, 121.0, 115.0)
    assert event.detail["reason"] == "tp1_runner_tp2"
    path = store.get("p1").runner_path
    assert (path["mfe_r"], path["ladder"]["4.0"]) == (4.2, "2026-10-07")


@pytest.mark.parametrize("reason", ["tp1_runner_trail", "tp1_runner_progress_stall", "time_exit"])
def test_every_runner_close_reason_stamps(reason):
    store, mgr = _manager(lambda ticker: LONG_BARS)
    mgr._close_runner(store.get("p1"), 113.0, reason, 5.0, 1)
    plan = store.get("p1")
    assert plan.status == PlanStatus.CLOSED
    assert plan.runner_path["source"] == "live" and plan.runner_path["sessions_after_tp1"] == 2


def test_missing_bars_close_the_plan_with_a_null_stamp():
    store, mgr = _manager(lambda ticker: None)
    mgr.check_bar("p1", 107.0, 108.0, 106.0)
    plan = store.get("p1")
    assert plan.status == PlanStatus.CLOSED and len(plan.legs_realized) == 2
    assert plan.runner_path is None


def test_a_failing_bar_source_never_blocks_the_close():
    def boom(ticker):
        raise OSError("cache unreadable")

    store, mgr = _manager(boom)
    mgr.check_bar("p1", 107.0, 108.0, 106.0)
    assert store.get("p1").status == PlanStatus.CLOSED
    assert store.get("p1").runner_path is None


def test_no_bar_source_configured_stamps_null():
    store, mgr = _manager(None)
    mgr.check_bar("p1", 107.0, 108.0, 106.0)
    assert store.get("p1").runner_path is None


def test_the_production_manager_reads_the_disk_cache(monkeypatch):
    monkeypatch.setattr(pm, "_MANAGER", None)
    assert pm._manager().runner_bars_fn is rp.cached_daily_bars
```

- [ ] **Step 2: Run it to verify it fails**

`python scripts/dev/testrun.py file tests/planning/test_plan_manager_runner_path.py`
Expected: FAIL with `TypeError: PlanManager.__init__() got an unexpected keyword argument 'runner_bars_fn'`.

- [ ] **Step 3: Implement**

In `swingbot/core/planning/plan_manager.py`, add the import directly under the top-level `from swingbot import config` (line 16; not the function-local copies further down):

```python
from swingbot import config
from swingbot.core.analytics import runner_path as rp
```

Replace the `PlanManager.__init__` signature line:

```python
                 auction_close_fn=None, daily_frame_fn=None):
```

with:

```python
                 auction_close_fn=None, daily_frame_fn=None, runner_bars_fn=None):
```

and directly after `        self.daily_frame_fn = daily_frame_fn   # ticker -> daily OHLCV (v123)` add:

```python
        # v142: ticker -> cached daily bars for the runner_path stamp. Disk
        # only (rp.cached_daily_bars in production); None = stamp null.
        self.runner_bars_fn = runner_bars_fn
```

In `_close_runner`, replace:

```python
        plan.legs_realized.append(leg)
        record_transition(plan, PlanStatus.CLOSED, reason=reason, at=at)
        self._structure_seen.pop(plan.plan_id, None)
```

with:

```python
        plan.legs_realized.append(leg)
        record_transition(plan, PlanStatus.CLOSED, reason=reason, at=at)
        rp.stamp_runner_path(plan, self.runner_bars_fn, source="live")   # v142; never raises
        self._structure_seen.pop(plan.plan_id, None)
```

(The stamp runs after the leg and the CLOSED transition exist, which the helper reads, and before `_persist_terminal`, so it lands in the same write.)

In `_manager()`, replace:

```python
                               price_batch_fn=batch_fn, daily_frame_fn=_daily_frame)
```

with:

```python
                               price_batch_fn=batch_fn, daily_frame_fn=_daily_frame,
                               runner_bars_fn=rp.cached_daily_bars)
```

- [ ] **Step 4: Run the tests to verify they pass, plus the neighbouring manager suites**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_manager_runner_path.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_logging.py
python scripts/dev/testrun.py file tests/planning/test_compression_time_exit.py
python -m radon cc -s -n C swingbot/core/planning/plan_manager.py
```

Expected: `VERDICT: PASS` ×4 (9 in the new file). radon lists only the pre-existing `_step_active` D (21), `poll` C (20), `_on_event` C (15), `_feed_bookkeeping`, `_step_partial`, `_check_bar_active`. `_close_runner`, `__init__` and `_manager` must not appear.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_runner_path.py
git commit -m "$(cat <<'EOF'
feat(v142): stamp runner_path on every automated runner close

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

### Task V142-3: Stamp a manual close of a PARTIAL plan

**Files:**
- Modify: `swingbot/admin/api_v1/trade_commands.py`: the imports (~:25) and `_close_plan` (~:87-108)
- Test: `tests/admin/test_trade_commands_runner_path.py` (create)

**Interfaces:**
- Consumes: `runner_path.stamp_runner_path`, `runner_path.cached_daily_bars`, `runner_path.compute_runner_path` (monkeypatched in tests); `tests.admin.test_api_v1_trades._plan`; `tests.store_seed.seed_store`.
- Produces: `_close_plan` stamps `runner_path` (source `"live"`) when the plan was `PARTIAL` before the close, and only then. The admin container mounts `./market_data` (docker-compose.yml), so the same disk reader works there.

- [ ] **Step 1: Write the failing test**

Create `tests/admin/test_trade_commands_runner_path.py`:

```python
"""v142: closing a PARTIAL plan from the admin UI stamps runner_path; closing
an ACTIVE one does not, and a stamp that cannot be computed never blocks it."""
import pytest

from swingbot.core.analytics import runner_path as rp
from swingbot.core.planning.plan_store import PlanStore
from tests.admin.test_api_v1_trades import _plan
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
_PLAN_ID = "55555555-5555-4555-8555-555555555555"
_STAMP = {"mfe_r": 3.0, "mae_r": 1.5, "sessions_after_tp1": 1, "source": "live",
          "ladder": {"1.5": "2026-08-05", "2.0": None, "2.5": None, "3.0": None, "4.0": None}}


def _partial_record():
    record = _plan(_PLAN_ID, status="PARTIAL")
    record["status_history"] = [
        {"status": "ACTIVE", "reason": "filled", "at": "2026-08-04T14:00:00+00:00"},
        {"status": "PARTIAL", "reason": "tp1_partial", "at": "2026-08-05T15:00:00+00:00"}]
    record["legs_realized"] = [{"fraction": 0.5, "exit_price": 110.0, "r": 1.5, "reason": "tp1"}]
    return record


@pytest.fixture
def logged_in(admin_app, client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: f"bars:{ticker}")

    def fake(plan, bars, *, source="live"):
        seen.append((plan.status, bars, source))
        return dict(_STAMP)

    monkeypatch.setattr(rp, "compute_runner_path", fake)
    return seen


def test_a_manual_partial_close_stamps_from_the_disk_cache(logged_in, calls):
    seed_store("plans", [_partial_record()])
    assert logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close").status_code == 200
    assert calls == [("CLOSED", "bars:AAPL", "live")]
    assert PlanStore().get(_PLAN_ID).runner_path == _STAMP


def test_an_active_close_has_no_runner_and_no_stamp(logged_in, calls):
    seed_store("plans", [_plan(_PLAN_ID, status="ACTIVE")])
    assert logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close").status_code == 200
    assert calls == []
    assert PlanStore().get(_PLAN_ID).runner_path is None


def test_a_null_stamp_still_closes(logged_in, monkeypatch):
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: None)
    seed_store("plans", [_partial_record()])
    assert logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close").status_code == 200
    plan = PlanStore().get(_PLAN_ID)
    assert plan.status == "CLOSED" and plan.runner_path is None
```

- [ ] **Step 2: Run it to verify it fails**

`python scripts/dev/testrun.py file tests/admin/test_trade_commands_runner_path.py`
Expected: FAIL in `test_a_manual_partial_close_stamps_from_the_disk_cache` (`assert [] == [('CLOSED', 'bars:AAPL', 'live')]`). The other two pass already, and that is correct: they pin what must not change.

- [ ] **Step 3: Implement**

In `swingbot/admin/api_v1/trade_commands.py`, replace:

```python
from swingbot.core.tracking.performance import TradeLog
```

with:

```python
from swingbot.core.analytics import runner_path as rp
from swingbot.core.tracking.performance import TradeLog
```

In `_close_plan`, replace:

```python
    # `at` is passed explicitly -- record_transition defaults it to None, and
    # the lifecycle strip's "today" counts read status_history[-1]["at"].
    record_transition(plan, PlanStatus.CLOSED, reason="manual",
                      at=datetime.now(timezone.utc).isoformat())
    store.update(plan)
```

with:

```python
    was_partial = plan.status == PlanStatus.PARTIAL
    # `at` is passed explicitly -- record_transition defaults it to None, and
    # the lifecycle strip's "today" counts read status_history[-1]["at"].
    record_transition(plan, PlanStatus.CLOSED, reason="manual",
                      at=datetime.now(timezone.utc).isoformat())
    if was_partial:   # v142: a manual runner close stamps its path too; never raises
        rp.stamp_runner_path(plan, rp.cached_daily_bars, source="live")
    store.update(plan)
```

(`rp.cached_daily_bars` is looked up at call time, so the tests' monkeypatch on the module reaches it.)

- [ ] **Step 4: Run the tests to verify they pass, plus the existing command suite**

```bash
python scripts/dev/testrun.py file tests/admin/test_trade_commands_runner_path.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py
python -m radon cc -s -n C swingbot/admin/api_v1/trade_commands.py
```

Expected: `VERDICT: PASS` ×2 (3 in the new file). radon does not list `_close_plan`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trade_commands.py tests/admin/test_trade_commands_runner_path.py
git commit -m "$(cat <<'EOF'
feat(v142): stamp runner_path when a PARTIAL plan is closed from the admin UI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```
