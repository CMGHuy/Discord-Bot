# v141 — Market-day report: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task, never the file: `grep -n "^### Task V141-3" -A 200 docs/superpowers/plans/2026-10-08-v141-market-day-report.md`.

**Bump:** none
**Edge:** none (integrity) — measurement only
**Spec:** [`docs/superpowers/specs/2026-10-08-v141-market-day-report-design.md`](../specs/2026-10-08-v141-market-day-report-design.md)

**Goal:** One reproducible report that says whether LONG win rate, ExpR and alert volume move with the SPY daily return, on TRAIN backtest trades and on the live paper book, and at which stage volume is lost.

**Architecture:** A pure module, `swingbot/core/analytics/market_day.py`, turns a SPY close series into per-day market forms and buckets, and computes per-bucket trade, volume and sum tables. A script, `scripts/reports/market_day_report.py`, feeds it from two sources and renders markdown: the TRAIN half re-uses plan v51's sweep (`scripts/backtest/measure_alert_density.py`), the live half reads a JSON dump produced on production by a small standalone dump script piped over ssh.

**Tech Stack:** Python 3.11, pandas/numpy, pytest. No new dependency.

## Spec corrections (the code disagrees with the spec; the plan follows the code)

1. **The live half prints no interval and no rank correlation.** The live book overlaps the 2026 holdout that open pre-registrations wait on. `scripts/reports/volume_context_report.py` sets the repo precedent: "monitoring only, and no inferential statistic is printed". Live tables show counts, win rate and ExpR only. The TRAIN half keeps the day-level bootstrap and the Spearman figure.
2. **The spec's open point is closed.** v51's `sweep()` already returns both populations — named strategies and the confluence replay (`replay_scenarios`) — as flat trade dicts. The report uses both and labels them. No second harness.
3. **The sweep rows carry no direction and no close date today.** V141-4 adds `direction` and `closed_at` to them. Confluence rows get `closed_at: None` (the replay result is not asked for an exit date), so the close-day table covers the strategy population and the live book only, and says so.
4. **Backtest cause covers named strategies only.** "Raw entry signals" is `entries_for(strategy, df, horizon)[0]` summed per day; the confluence replay has no separate pre-trade signal count in the sweep. The report says so beside the table.
5. **Live volume counts only days the bot scanned.** A trading day with no scan row is an outage, not a silent day. The denominator is trading days with at least one scan.
6. **The live dump is a separate standalone script.** Production does not have this branch's code. `scripts/reports/market_day_live_dump.py` imports only modules production already runs and is piped over ssh (`python -` reading stdin), read-only. The report then runs locally against the dump.
7. **Day of a live event is the US/Eastern calendar date** of its UTC stamp (`swingbot.core.market.session.US_MARKET_TZ`).
8. **v51 already saw one edge of this.** `docs/superpowers/results/2026-08-23-alert-density-train.md` found busy days carry a positive mean SPY return. That is density against SPY; this plan measures SPY against outcome and volume directly. The results file cites it.

9. **Live scan totals are all-direction.** `scan_run.py` writes `signals` as all scenarios found and `alerts` as all emitted alerts. The `short_funnel` snapshot carries both directions despite its name; `funnel_stage_counts` selects bullish events. Thus the live scan-volume table cannot measure LONG openings or attribute a LONG loss to a stage. The results label totals as all-direction and report the bullish-stage day count separately.

10. **The live LONG-volume question cannot be answered from this dump.** The production scan row stores all-direction `signals` and `alerts` but no LONG/SHORT split, and the available staged bullish funnel covers only six scanned days. Closed trades are a closure-selected subset, not the alert-opening denominator. The result gives all-direction scan volume as context and marks live LONG openings/day and a full-period stage attribution unavailable; a later directional issuance instrument would be needed for those answers.

## Global Constraints

- TRAIN window `2020-01-01..2023-12-31` only. The script refuses any other window for the backtest half. VALIDATION `2024-01-01..2025-12-31` is never read.
- Buckets, fixed: `< -1%`, `-1% .. 0`, `0 .. +1%`, `> +1%`. Exactly `-1.0` → `-1% .. 0`; exactly `0.0` and exactly `+1.0` → `0 .. +1%`.
- Market forms: `same_day` = return of day *t*; `prior_day` = return of day *t−1*; `trailing_5d` = close *t−1* over close *t−6*. All in percent.
- Regime split: `regime2.regime_series` trend word (`bull`/`bear`) of day *t−1*.
- A bucket with fewer than 10 distinct days prints counts and `—` for every rate.
- Bootstrap: resample **days**, 2000 draws, seed 42, 95% percentile interval.
- Win rate and R come from `swingbot/core/analytics/metrics.py`; nothing is redefined.
- Backtest and live are never pooled.
- Universe for the TRAIN half: the backtest cache listing (`runner_headroom.cache_universe()`), because a worktree cannot reach the Postgres watchlist. Every run sets `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache`.
- Every function ends below cyclomatic complexity 15 (`python -m radon cc -s -n C <files>` prints nothing).
- Work in the worktree `.claude/worktrees/2026-10-08-v141-market-day-report/` on the branch of the same name (use the `worktree-lifecycle` skill to create it).
- Per-task check is `python scripts/dev/testrun.py file <the test file>`. The full suite runs once, in V141-8.

## File structure

| File | Responsibility |
|---|---|
| `swingbot/core/analytics/market_day.py` (create) | Pure: market forms, buckets, trade/volume/sum tables, bootstrap, funnel-key parsing |
| `tests/analytics/test_market_day.py` (create) | Unit tests for the module |
| `scripts/backtest/measure_alert_density.py` (modify) | Sweep rows gain `direction`, `closed_at`; progress line gains a percent |
| `scripts/reports/market_day_live_dump.py` (create) | Standalone, read-only: closed trades + scan telemetry as one JSON line |
| `scripts/reports/market_day_report.py` (create) | Adapters, raw-signal count, markdown rendering, CLI |
| `tests/scripts/test_market_day_report.py` (create) | Adapter, rendering and dump-loader tests |
| `docs/superpowers/results/<run date>-v141-market-day.md` (create) | The result |

## Parallelisation

- **Group 1 (parallel):** V141-1, V141-4, V141-5 — three different files, no shared symbol.
- **Sequential:** V141-2 after V141-1 and V141-3 after V141-2 (same module file; each adds functions the next one's tests import beside its own). V141-6 after V141-3, V141-4 and V141-5 (it calls all three). V141-7 after V141-6 (runs the script). V141-8 last (full suite, close-out).

---

### Task V141-1: Market forms and buckets

**Files:**
- Create: `swingbot/core/analytics/market_day.py`
- Test: `tests/analytics/test_market_day.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `FORMS: tuple[str, ...] = ("same_day", "prior_day", "trailing_5d")`
  - `BUCKETS: tuple[str, ...] = ("< -1%", "-1% .. 0", "0 .. +1%", "> +1%")`
  - `MIN_DAYS = 10`
  - `bucket_of(ret: float | None) -> str | None`
  - `market_days(spy_close: pd.Series, regimes: pd.Series | None = None) -> dict[str, dict]` — `{"YYYY-MM-DD": {"same_day": float|None, "prior_day": float|None, "trailing_5d": float|None, "regime": "bull"|"bear"|None}}`
  - `days_in(days: dict, form: str, bucket: str, regime: str | None = None) -> list[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_market_day.py`:

```python
"""v141: market forms, buckets and per-bucket tables. Pure arithmetic."""
from __future__ import annotations

import pandas as pd
import pytest

from swingbot.core.analytics import market_day as md


def _close(values, start="2021-03-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


@pytest.mark.parametrize("ret,bucket", [
    (-1.5, "< -1%"), (-1.0, "-1% .. 0"), (-0.01, "-1% .. 0"),
    (0.0, "0 .. +1%"), (1.0, "0 .. +1%"), (1.01, "> +1%"),
])
def test_bucket_edges(ret, bucket):
    assert md.bucket_of(ret) == bucket


def test_bucket_of_missing_is_none():
    assert md.bucket_of(None) is None
    assert md.bucket_of(float("nan")) is None


def test_forms_are_percent_returns_and_prior_day_is_yesterdays_same_day():
    days = md.market_days(_close([100, 102, 101, 103, 104, 105, 106, 110]))
    keys = list(days)
    assert days[keys[0]]["same_day"] is None                 # no prior close
    assert days[keys[1]]["same_day"] == pytest.approx(2.0)
    assert days[keys[2]]["prior_day"] == pytest.approx(2.0)   # day 1's own return
    # trailing_5d on day 7: close[6] / close[1] - 1 = 106/102 - 1
    assert days[keys[7]]["trailing_5d"] == pytest.approx((106 / 102 - 1) * 100)
    assert days[keys[5]]["trailing_5d"] is None               # needs close[t-6]


def test_lagged_forms_do_not_move_when_later_bars_are_added():
    """prior_day and trailing_5d of day t use closes up to t-1 only, so
    appending or changing day t's own close cannot change them."""
    base = [100, 102, 101, 103, 104, 105, 106, 110]
    full = md.market_days(_close(base))
    bumped = md.market_days(_close(base[:-1] + [50]))
    last = list(full)[-1]
    assert full[last]["prior_day"] == bumped[last]["prior_day"]
    assert full[last]["trailing_5d"] == bumped[last]["trailing_5d"]
    assert full[last]["same_day"] != bumped[last]["same_day"]


def test_regime_is_the_prior_days_trend_word():
    close = _close([100, 101, 102])
    regimes = pd.Series(["bull_quiet", "bear_volatile", "bull_quiet"], index=close.index)
    days = md.market_days(close, regimes)
    keys = list(days)
    assert days[keys[0]]["regime"] is None
    assert days[keys[1]]["regime"] == "bull"
    assert days[keys[2]]["regime"] == "bear"


def test_days_in_filters_by_bucket_and_regime():
    days = {"2021-03-01": {"same_day": 1.5, "prior_day": None, "trailing_5d": None, "regime": "bull"},
            "2021-03-02": {"same_day": 1.2, "prior_day": 1.5, "trailing_5d": None, "regime": "bear"},
            "2021-03-03": {"same_day": -0.5, "prior_day": 1.2, "trailing_5d": None, "regime": "bear"}}
    assert md.days_in(days, "same_day", "> +1%") == ["2021-03-01", "2021-03-02"]
    assert md.days_in(days, "same_day", "> +1%", regime="bear") == ["2021-03-02"]
    assert md.days_in(days, "prior_day", "> +1%") == ["2021-03-02", "2021-03-03"]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_market_day.py`
Expected: FAIL — `cannot import name 'market_day'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/analytics/market_day.py`:

```python
"""v141: trades and alert volume against the market's daily move.

Pure arithmetic -- no I/O, no network, no cache reads. The report script
(scripts/reports/market_day_report.py) owns loading; a later admin panel
re-uses these functions unchanged.

THE LAG RULE. A trade opened on day t may only be explained by `prior_day`
and `trailing_5d`, both built from closes up to t-1. `same_day` uses day t's
own close, which no scan knew: it describes, it can never gate.
"""
from __future__ import annotations

import pandas as pd

FORMS: tuple[str, ...] = ("same_day", "prior_day", "trailing_5d")
# Fixed before any number was read. Redrawing these after seeing a table is
# the exact move the one-shot discipline exists to prevent.
BUCKETS: tuple[str, ...] = ("< -1%", "-1% .. 0", "0 .. +1%", "> +1%")
MIN_DAYS = 10            # below this a bucket shows counts and no rate


def bucket_of(ret: float | None) -> str | None:
    """The bucket of a percent return; None for a missing one."""
    if ret is None or ret != ret:
        return None
    if ret < -1.0:
        return BUCKETS[0]
    if ret < 0.0:
        return BUCKETS[1]
    if ret <= 1.0:
        return BUCKETS[2]
    return BUCKETS[3]


def _number(value) -> float | None:
    return None if value != value else float(value)


def market_days(spy_close: pd.Series, regimes: pd.Series | None = None) -> dict[str, dict]:
    """{day: {same_day, prior_day, trailing_5d, regime}} for every bar.

    `regimes` is regime2.regime_series' label per bar ("bull_quiet", ...);
    the stored regime is the trend word of day t-1, so it is known at t.
    """
    ret = spy_close.pct_change() * 100.0
    frame = pd.DataFrame({
        "same_day": ret,
        "prior_day": ret.shift(1),
        "trailing_5d": (spy_close.shift(1) / spy_close.shift(6) - 1.0) * 100.0,
    })
    trend = regimes.shift(1) if regimes is not None else None
    out: dict[str, dict] = {}
    for ts, row in frame.iterrows():
        label = trend.get(ts) if trend is not None else None
        out[str(ts.date())] = {
            **{form: _number(row[form]) for form in FORMS},
            "regime": label.split("_")[0] if isinstance(label, str) else None,
        }
    return out


def days_in(days: dict, form: str, bucket: str, regime: str | None = None) -> list[str]:
    """Days whose `form` return falls in `bucket` (and in `regime`, if given)."""
    return [day for day, market in days.items()
            if bucket_of(market[form]) == bucket
            and (regime is None or market["regime"] == regime)]
```

- [ ] **Step 4: Run it and watch it pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_market_day.py`
Expected: `VERDICT: PASS`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/market_day.py tests/analytics/test_market_day.py
git commit -m "feat(v141): market forms and fixed return buckets (V141-1)"
```

---

### Task V141-2: Per-bucket trade table with a day-level bootstrap

**Files:**
- Modify: `swingbot/core/analytics/market_day.py` (append)
- Test: `tests/analytics/test_market_day.py` (append)

**Interfaces:**
- Consumes: `BUCKETS`, `MIN_DAYS`, `days_in` (V141-1).
- Produces:
  - A **trade row** is a dict `{"day": "YYYY-MM-DD", "direction": "bullish"|"bearish", "outcome": str, "r": float|None}`; extra keys are ignored.
  - `BOOTSTRAP_N = 2000`, `BOOTSTRAP_SEED = 42`
  - `trade_table(rows: list[dict], days: dict, form: str, *, direction: str = "bullish", regime: str | None = None, intervals: bool = True) -> list[dict]` — one dict per bucket, in `BUCKETS` order: `{"bucket", "n", "days", "win_rate", "exp_r", "win_rate_ci", "exp_r_ci"}`. Rates are `None` below `MIN_DAYS`; `*_ci` is `[lo, hi]` or `None`.
  - `day_rank_correlation(rows: list[dict], days: dict, form: str, *, direction: str = "bullish") -> float | None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_market_day.py`:

```python
def _days(returns, form="same_day", start="2021-03-01"):
    """One market day per return, all in the bull regime."""
    idx = pd.bdate_range(start, periods=len(returns))
    return {str(ts.date()): {"same_day": None, "prior_day": None, "trailing_5d": None,
                             "regime": "bull", form: ret}
            for ts, ret in zip(idx, returns)}


def _row(day, outcome="win", r=1.0, direction="bullish"):
    return {"day": day, "direction": direction, "outcome": outcome, "r": r}


def test_trade_table_counts_trades_and_distinct_days_per_bucket():
    days = _days([1.5] * 12 + [-1.5] * 12)
    keys = list(days)
    rows = [_row(d) for d in keys[:12]] + [_row(keys[0])]            # 13 trades, 12 green days
    rows += [_row(d, "loss", -1.0) for d in keys[12:]]               # 12 trades, 12 red days
    table = {r["bucket"]: r for r in md.trade_table(rows, days, "same_day")}
    assert (table["> +1%"]["n"], table["> +1%"]["days"]) == (13, 12)
    assert table["> +1%"]["win_rate"] == 100.0
    assert table["> +1%"]["exp_r"] == 1.0
    assert table["< -1%"]["win_rate"] == 0.0
    assert table["< -1%"]["exp_r"] == -1.0
    assert table["0 .. +1%"] == {"bucket": "0 .. +1%", "n": 0, "days": 0, "win_rate": None,
                                 "exp_r": None, "win_rate_ci": None, "exp_r_ci": None}


def test_a_bucket_below_the_day_floor_shows_counts_and_no_rate():
    days = _days([1.5] * 9)
    rows = [_row(d) for d in days] * 3            # 27 trades but only 9 days
    row = md.trade_table(rows, days, "same_day")[3]
    assert (row["n"], row["days"]) == (27, 9)
    assert row["win_rate"] is None and row["exp_r"] is None and row["win_rate_ci"] is None


def test_scratches_leave_the_win_rate_denominator_but_stay_in_exp_r():
    days = _days([1.5] * 10)
    keys = list(days)
    rows = [_row(d, "win", 2.0) for d in keys[:5]] + [_row(d, "scratch", 0.0) for d in keys[5:]]
    row = md.trade_table(rows, days, "same_day")[3]
    assert row["win_rate"] == 100.0          # 5 wins / 5 decided
    assert row["exp_r"] == 1.0               # (5*2 + 5*0) / 10


def test_direction_filter_and_regime_filter():
    days = _days([1.5] * 10)
    rows = [_row(d) for d in days] + [_row(d, direction="bearish") for d in days]
    assert md.trade_table(rows, days, "same_day")[3]["n"] == 10
    assert md.trade_table(rows, days, "same_day", direction="bearish")[3]["n"] == 10
    assert md.trade_table(rows, days, "same_day", regime="bear")[3]["n"] == 0


def test_interval_is_over_days_reproducible_and_brackets_the_point():
    days = _days([1.5] * 20)
    keys = list(days)
    rows = [_row(d, "win", 1.0) for d in keys[:10]] + [_row(d, "loss", -1.0) for d in keys[10:]]
    first = md.trade_table(rows, days, "same_day")[3]
    again = md.trade_table(rows, days, "same_day")[3]
    assert first["win_rate_ci"] == again["win_rate_ci"]            # fixed seed
    lo, hi = first["win_rate_ci"]
    assert lo < first["win_rate"] < hi
    assert md.trade_table(rows, days, "same_day", intervals=False)[3]["win_rate_ci"] is None


def test_many_trades_on_one_day_do_not_narrow_the_interval():
    """Ten trades on each of 20 days is still 20 observations."""
    days = _days([1.5] * 20)
    keys = list(days)
    one = [_row(d, "win", 1.0) for d in keys[:10]] + [_row(d, "loss", -1.0) for d in keys[10:]]
    ten = one * 10
    assert (md.trade_table(one, days, "same_day")[3]["win_rate_ci"]
            == md.trade_table(ten, days, "same_day")[3]["win_rate_ci"])


def test_rank_correlation_sign_and_floor():
    returns = [float(i) for i in range(-6, 6)]                       # 12 days
    days = _days(returns)
    keys = list(days)
    rising = [_row(d, "win", float(i)) for i, d in enumerate(keys)]
    falling = [_row(d, "win", float(-i)) for i, d in enumerate(keys)]
    assert md.day_rank_correlation(rising, days, "same_day") == 1.0
    assert md.day_rank_correlation(falling, days, "same_day") == -1.0
    assert md.day_rank_correlation(rising[:9], days, "same_day") is None   # < MIN_DAYS
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_market_day.py`
Expected: FAIL — `module 'swingbot.core.analytics.market_day' has no attribute 'trade_table'`.

- [ ] **Step 3: Implement**

In `swingbot/core/analytics/market_day.py`, add `import numpy as np` above `import pandas as pd`, add `from swingbot.core.analytics import metrics` below it, add the two constants under `MIN_DAYS`, and append the functions:

```python
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42
```

```python
def _by_day(rows: list[dict], direction: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("direction") == direction and row.get("day"):
            out.setdefault(row["day"], []).append(row)
    return out


def _day_arrays(by_day: dict, day_list: list[str]):
    """Per-day (wins, decided, r_sum, r_count) -- what a day resample re-sums."""
    wins, decided, r_sum, r_count = [], [], [], []
    for day in day_list:
        rows = by_day[day]
        rs = [row["r"] for row in rows if row.get("r") is not None]
        wins.append(sum(1 for row in rows if row["outcome"] == "win"))
        decided.append(sum(1 for row in rows if row["outcome"] in ("win", "loss")))
        r_sum.append(sum(rs))
        r_count.append(len(rs))
    return tuple(np.array(a, dtype=float) for a in (wins, decided, r_sum, r_count))


def _interval(numer: np.ndarray, denom: np.ndarray, scale: float, rng) -> list[float] | None:
    """95% percentile interval of sum(numer)/sum(denom) over resampled DAYS.

    Trades opened on one day share that day's market, so the day is the unit
    that is exchangeable -- resampling trades would count one green day ten
    times and call it ten confirmations.
    """
    n_days = len(numer)
    idx = rng.integers(0, n_days, size=(BOOTSTRAP_N, n_days))
    dens = denom[idx].sum(axis=1)
    nums = numer[idx].sum(axis=1)
    values = nums[dens > 0] / dens[dens > 0] * scale
    if not len(values):
        return None
    lo, hi = np.percentile(values, [2.5, 97.5])
    return [round(float(lo), 2), round(float(hi), 2)]


def _bucket_row(bucket: str, by_day: dict, day_list: list[str], intervals: bool, rng) -> dict:
    rows = [row for day in day_list for row in by_day[day]]
    out = {"bucket": bucket, "n": len(rows), "days": len(day_list), "win_rate": None,
           "exp_r": None, "win_rate_ci": None, "exp_r_ci": None}
    if len(day_list) < MIN_DAYS:
        return out
    rs = [row["r"] for row in rows if row.get("r") is not None]
    win_rate = metrics.win_rate([{"status": row["outcome"]} for row in rows])
    out["win_rate"] = None if win_rate is None else round(win_rate, 2)
    out["exp_r"] = round(sum(rs) / len(rs), 4) if rs else None
    if intervals:
        wins, decided, r_sum, r_count = _day_arrays(by_day, day_list)
        out["win_rate_ci"] = _interval(wins, decided, 100.0, rng)
        out["exp_r_ci"] = _interval(r_sum, r_count, 1.0, rng)
    return out


def trade_table(rows: list[dict], days: dict, form: str, *, direction: str = "bullish",
                regime: str | None = None, intervals: bool = True) -> list[dict]:
    """One row per bucket for trades OPENED on days in that bucket."""
    by_day = _by_day(rows, direction)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    return [_bucket_row(bucket, by_day,
                        [day for day in days_in(days, form, bucket, regime) if day in by_day],
                        intervals, rng)
            for bucket in BUCKETS]


def day_rank_correlation(rows: list[dict], days: dict, form: str, *,
                         direction: str = "bullish") -> float | None:
    """Spearman rho between a day's market return and its mean trade R."""
    pairs = []
    for day, day_rows in _by_day(rows, direction).items():
        rs = [row["r"] for row in day_rows if row.get("r") is not None]
        market = days.get(day, {}).get(form)
        if rs and market is not None:
            pairs.append((market, sum(rs) / len(rs)))
    if len(pairs) < MIN_DAYS:
        return None
    x = pd.Series([p[0] for p in pairs]).rank()
    y = pd.Series([p[1] for p in pairs]).rank()
    rho = x.corr(y)
    return None if rho != rho else round(float(rho), 3)
```

- [ ] **Step 4: Run it and watch it pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_market_day.py`
Expected: `VERDICT: PASS`.

- [ ] **Step 5: Complexity, then commit**

Run: `python -m radon cc -s -n C swingbot/core/analytics/market_day.py` — expected: no output.

```bash
git add swingbot/core/analytics/market_day.py tests/analytics/test_market_day.py
git commit -m "feat(v141): per-bucket trade table with a day-level bootstrap (V141-2)"
```

---

### Task V141-3: Volume table, bucket sums and funnel-key parsing

**Files:**
- Modify: `swingbot/core/analytics/market_day.py` (append)
- Test: `tests/analytics/test_market_day.py` (append)

**Interfaces:**
- Consumes: `BUCKETS`, `MIN_DAYS`, `days_in` (V141-1).
- Produces:
  - `volume_table(counts: dict[str, int], days: dict, form: str, *, observed: set[str] | None = None, regime: str | None = None) -> list[dict]` — per bucket `{"bucket", "days", "mean", "median", "zero_share"}`. A day absent from `counts` counts as 0. `observed`, when given, restricts the denominator to those days.
  - `sum_by_bucket(day_values: dict[str, dict[str, float]], days: dict, form: str, *, regime: str | None = None) -> list[dict]` — per bucket `{"bucket", "days", "totals": {key: summed value}}` over the days present in `day_values`.
  - `funnel_stage_counts(snapshot: dict[str, int], direction: str = "bullish") -> dict[str, int]` — flat `{"<stage>:ok": n, "<stage>:rejected": n}` from `ShortFunnel.snapshot()` keys (`direction/source/mode/stage/reason`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_market_day.py`:

```python
def test_volume_counts_silent_days_in_the_denominator():
    days = _days([-1.5] * 10)
    keys = list(days)
    counts = {keys[0]: 4, keys[1]: 2}                 # eight days never appear
    row = md.volume_table(counts, days, "same_day")[0]
    assert row == {"bucket": "< -1%", "days": 10, "mean": 0.6, "median": 0.0, "zero_share": 80.0}


def test_volume_observed_restricts_the_denominator():
    """A day with no scan is an outage, not a silent day."""
    days = _days([-1.5] * 12)
    keys = list(days)
    counts = {keys[0]: 3}
    row = md.volume_table(counts, days, "same_day", observed=set(keys[:10]))[0]
    assert row["days"] == 10 and row["zero_share"] == 90.0


def test_volume_below_the_day_floor_shows_days_only():
    days = _days([-1.5] * 9)
    row = md.volume_table({}, days, "same_day")[0]
    assert row == {"bucket": "< -1%", "days": 9, "mean": None, "median": None, "zero_share": None}


def test_sum_by_bucket_adds_keys_over_present_days_only():
    days = _days([1.5, 1.5, -1.5])
    keys = list(days)
    values = {keys[0]: {"signals": 10, "taken": 4}, keys[2]: {"signals": 6, "taken": 1}}
    table = {r["bucket"]: r for r in md.sum_by_bucket(values, days, "same_day")}
    assert table["> +1%"] == {"bucket": "> +1%", "days": 1, "totals": {"signals": 10, "taken": 4}}
    assert table["< -1%"]["totals"] == {"signals": 6, "taken": 1}
    assert table["0 .. +1%"] == {"bucket": "0 .. +1%", "days": 0, "totals": {}}


def test_funnel_stage_counts_reads_one_direction_and_folds_reasons():
    snapshot = {
        "bullish/base/base/confidence/ok": 7,
        "bullish/base/base/confidence/min_confidence": 3,
        "bullish/base/base/confidence/min_confluence": 2,
        "bullish/base/base/send/ok": 4,
        "bearish/short_universe/weak/confidence/ok": 9,
        "malformed": 1,
    }
    assert md.funnel_stage_counts(snapshot) == {
        "confidence:ok": 7, "confidence:rejected": 5, "send:ok": 4}
    assert md.funnel_stage_counts(snapshot, "bearish") == {"confidence:ok": 9}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_market_day.py`
Expected: FAIL — `has no attribute 'volume_table'`.

- [ ] **Step 3: Implement**

Append to `swingbot/core/analytics/market_day.py`:

```python
def volume_table(counts: dict[str, int], days: dict, form: str, *,
                 observed: set[str] | None = None, regime: str | None = None) -> list[dict]:
    """Alerts (or trades) per day, per bucket, over EVERY day in the bucket.

    A day absent from `counts` is a zero, not a gap: the silent day is the
    thing being measured. `observed` narrows the denominator to days the
    source actually covered (live: days with at least one scan).
    """
    out = []
    for bucket in BUCKETS:
        day_list = [day for day in days_in(days, form, bucket, regime)
                    if observed is None or day in observed]
        row = {"bucket": bucket, "days": len(day_list), "mean": None, "median": None,
               "zero_share": None}
        if len(day_list) >= MIN_DAYS:
            values = np.array([counts.get(day, 0) for day in day_list], dtype=float)
            row["mean"] = round(float(values.mean()), 2)
            row["median"] = round(float(np.median(values)), 2)
            row["zero_share"] = round(float((values == 0).mean() * 100.0), 1)
        out.append(row)
    return out


def sum_by_bucket(day_values: dict[str, dict[str, float]], days: dict, form: str, *,
                  regime: str | None = None) -> list[dict]:
    """Per bucket, the key-wise sum of `day_values` over the days it holds."""
    out = []
    for bucket in BUCKETS:
        day_list = [day for day in days_in(days, form, bucket, regime) if day in day_values]
        totals: dict[str, float] = {}
        for day in day_list:
            for key, value in day_values[day].items():
                totals[key] = totals.get(key, 0) + value
        out.append({"bucket": bucket, "days": len(day_list), "totals": totals})
    return out


def funnel_stage_counts(snapshot: dict[str, int], direction: str = "bullish") -> dict[str, int]:
    """{"<stage>:ok"|"<stage>:rejected": n} for one direction.

    Keys are ShortFunnel.snapshot()'s "direction/source/mode/stage/reason";
    every reason other than "ok" is a rejection at that stage.
    """
    out: dict[str, int] = {}
    for key, count in snapshot.items():
        parts = key.split("/")
        if len(parts) != 5 or parts[0] != direction:
            continue
        name = f"{parts[3]}:{'ok' if parts[4] == 'ok' else 'rejected'}"
        out[name] = out.get(name, 0) + count
    return out
```

- [ ] **Step 4: Run it and watch it pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_market_day.py`
Expected: `VERDICT: PASS`.

- [ ] **Step 5: Complexity, then commit**

Run: `python -m radon cc -s -n C swingbot/core/analytics/market_day.py` — expected: no output.

```bash
git add swingbot/core/analytics/market_day.py tests/analytics/test_market_day.py
git commit -m "feat(v141): volume table, bucket sums and funnel-key parsing (V141-3)"
```

---

### Task V141-4: Sweep rows carry direction and close date

**Files:**
- Modify: `scripts/backtest/measure_alert_density.py` — `_entry_dates_for_ticker` (the two `rows.append({...})` blocks) and `sweep`'s inner `_report`
- Test: `tests/scripts/test_alert_density.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: every row from `sweep()` / `_entry_dates_for_ticker()` additionally carries `"direction": "bullish"|"bearish"` and `"closed_at": "YYYY-MM-DD"|None` (`None` for every confluence row). Existing keys are unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/scripts/test_alert_density.py`:

```python
def test_strategy_rows_carry_direction_and_close_date(monkeypatch):
    """v141 buckets trades by direction and, for one table, by close day."""
    import measure_alert_density as mad
    from swingbot.core.backtesting import backtest

    trade = backtest.BacktestTrade(
        entry_date="2021-03-01", exit_date="2021-03-05", direction="bullish",
        entry=100.0, stop_loss=95.0, take_profit=110.0, outcome="win",
        exit_price=110.0, return_pct=10.0, r_multiple=2.0, holding_days=4)

    class _Summary:
        trades = [trade]

    monkeypatch.setattr(backtest, "run_backtest", lambda *a, **k: _Summary())
    rows, _ = mad._entry_dates_for_ticker(
        "AAA", None, ["2w"], "2021-01-01", "2021-12-31", gates={}, scale_out=True,
        want_strategies=True, want_confluence=False, strategies=["RSI"])

    assert len(rows) == 1
    assert rows[0]["direction"] == "bullish"
    assert rows[0]["closed_at"] == "2021-03-05"
    assert rows[0]["opened_at"] == "2021-03-01"      # unchanged
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_alert_density.py`
Expected: FAIL — `KeyError: 'direction'`.

- [ ] **Step 3: Implement**

In `_entry_dates_for_ticker`, the confluence `rows.append` becomes:

```python
                rows.append({
                    "opened_at": signal_date,
                    "closed_at": None,          # v141: the replay is not asked for an exit date
                    "direction": plan.direction,
                    "ticker": ticker,
                    "horizon": hk,
                    "source": CONFLUENCE_SOURCE,
                    "strategy": CONFLUENCE_SOURCE,
                    "outcome": res.outcome,
                    "r_multiple": res.r_total,
                })
```

and the strategy `rows.append` becomes:

```python
                    rows.append({
                        "opened_at": t.entry_date,
                        "closed_at": t.exit_date,
                        "direction": t.direction,
                        "ticker": ticker,
                        "horizon": hk,
                        "source": "strategy",
                        "strategy": strat,
                        "outcome": t.outcome,
                        "r_multiple": t.r_multiple,
                    })
```

In `sweep`'s `_report`, the print becomes (a run past 15 minutes must show a percent):

```python
            print(f"[{done_units}/{total_units} {done_units / total_units:.0%}] "
                  f"{ticker} {hk} {population} "
                  f"trades={n} ({time.time() - t0:.0f}s elapsed, "
                  f"ticker {done_tickers}/{len(tasks)})", flush=True)
```

- [ ] **Step 4: Run it and watch it pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_alert_density.py`
Expected: `VERDICT: PASS`. If an existing test in that file pins the exact key set of a sweep row, add the two new keys to its expectation — the keys are additive and no v51 consumer reads rows positionally.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_alert_density.py tests/scripts/test_alert_density.py
git commit -m "feat(v141): sweep rows carry direction and close date; progress shows a percent (V141-4)"
```

---

### Task V141-5: Standalone live dump

**Files:**
- Create: `scripts/reports/market_day_live_dump.py`
- Test: `tests/scripts/test_market_day_report.py` (create)

**Interfaces:**
- Consumes: only modules production already runs — `TradeLog`, `primary_strategy_label` (`swingbot/core/tracking/performance.py`), `metrics.r_multiple`, `scope.closed_only`, `telemetry.TELEMETRY_PATH`.
- Produces:
  - `trade_record(trade: dict) -> dict` — `{"opened_at", "closed_at", "direction", "status", "r", "strategy"}`
  - `scan_record(row: dict) -> dict | None` — `{"at", "signals", "alerts", "funnel"}`; `None` for a row with no numeric `duration_s` (deploy markers)
  - `build_dump(trades: list[dict], telemetry_rows: list[dict]) -> dict` — `{"trades": [...], "scans": [...]}`
  - Running the file prints exactly one line: the dump as JSON.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_market_day_report.py`:

```python
"""v141 report script: adapters, rendering, dump loading. No network, no DB."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import market_day_live_dump as dump  # noqa: E402


def _live_trade(**over):
    trade = {"id": "a" * 16, "ticker": "AAPL", "direction": "bullish", "status": "win",
             "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0,
             "opened_at": "2026-09-01T14:35:00+00:00", "closed_at": "2026-09-04T19:00:00+00:00",
             "strategies": ["RSI"]}
    return {**trade, **over}


def test_trade_record_keeps_only_what_the_report_needs():
    record = dump.trade_record(_live_trade())
    assert set(record) == {"opened_at", "closed_at", "direction", "status", "r", "strategy"}
    assert record["r"] == pytest.approx(2.0)          # (110-100)/(100-95)
    assert record["direction"] == "bullish"
    assert "ticker" not in record


def test_scan_record_skips_deploy_markers():
    assert dump.scan_record({"at": "2026-09-01T14:00:00+00:00", "type": "deploy"}) is None
    scan = dump.scan_record({"at": "2026-09-01T14:00:00+00:00", "duration_s": 12.5,
                             "signals": 9, "alerts": 2, "tickers": 80,
                             "short_funnel": {"bullish/base/base/send/ok": 2}})
    assert scan == {"at": "2026-09-01T14:00:00+00:00", "signals": 9, "alerts": 2,
                    "funnel": {"bullish/base/base/send/ok": 2}}


def test_build_dump_drops_open_trades_and_is_json_serialisable():
    out = dump.build_dump(
        [_live_trade(), _live_trade(status="open", exit_price=None, closed_at=None)],
        [{"at": "2026-09-01T14:00:00+00:00", "duration_s": 3.0, "signals": 1, "alerts": 0}])
    assert len(out["trades"]) == 1
    assert out["scans"][0]["funnel"] == {}
    json.dumps(out)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_market_day_report.py`
Expected: FAIL — `No module named 'market_day_live_dump'`.

- [ ] **Step 3: Write the dump script**

Create `scripts/reports/market_day_live_dump.py`:

```python
#!/usr/bin/env python3
"""v141: dump the live book and scan telemetry as ONE JSON line. Read-only.

Standalone on purpose: production does not carry the v141 branch, so this
file imports only modules production already runs and is piped over ssh::

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
        < scripts/reports/market_day_live_dump.py > data/market_day_live.json

It writes nothing on the box. Tickers are deliberately left out -- the report
buckets by day and direction and needs none.
"""
from __future__ import annotations

import json


def trade_record(trade: dict) -> dict:
    from swingbot.core.analytics.metrics import r_multiple
    from swingbot.core.tracking.performance import primary_strategy_label
    return {
        "opened_at": trade.get("opened_at"),
        "closed_at": trade.get("closed_at"),
        "direction": trade.get("direction"),
        "status": trade.get("status"),
        "r": r_multiple(trade),
        "strategy": primary_strategy_label(trade),
    }


def scan_record(row: dict) -> dict | None:
    """One scan row; None for the file's non-scan rows (deploy markers)."""
    if not isinstance(row.get("duration_s"), (int, float)):
        return None
    return {"at": row.get("at"), "signals": row.get("signals", 0),
            "alerts": row.get("alerts", 0), "funnel": row.get("short_funnel") or {}}


def build_dump(trades: list[dict], telemetry_rows: list[dict]) -> dict:
    from swingbot.core.analytics.scope import closed_only
    scans = [scan for row in telemetry_rows if (scan := scan_record(row)) is not None]
    return {"trades": [trade_record(t) for t in closed_only(trades)], "scans": scans}


def _telemetry_rows() -> list[dict]:
    from swingbot.core.scanning.telemetry import TELEMETRY_PATH
    rows = []
    try:
        with open(TELEMETRY_PATH, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
    except OSError:
        pass
    return rows


def main() -> None:
    from swingbot.core.tracking.performance import TradeLog
    trades = TradeLog().get_trades(status=None, limit=None)
    print(json.dumps(build_dump(trades, _telemetry_rows())))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run it and watch it pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_market_day_report.py`
Expected: `VERDICT: PASS`. If `primary_strategy_label` needs a field `_live_trade` lacks, extend the fixture, not the function.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/market_day_live_dump.py tests/scripts/test_market_day_report.py
git commit -m "feat(v141): standalone read-only live dump for the market-day report (V141-5)"
```

---

### Task V141-6: The report script

**Files:**
- Create: `scripts/reports/market_day_report.py`
- Test: `tests/scripts/test_market_day_report.py` (append)

**Interfaces:**
- Consumes:
  - `market_day` — `FORMS`, `BUCKETS`, `market_days`, `trade_table`, `day_rank_correlation`, `volume_table`, `sum_by_bucket`, `funnel_stage_counts` (V141-1..3)
  - `measure_alert_density.load_frames(tickers)`, `.sweep(frames, date_from, date_to, *, horizons, gates, scale_out, strategies, workers)` with rows carrying `direction`/`closed_at` (V141-4)
  - the dump shape `{"trades": [...], "scans": [...]}` (V141-5)
  - `runner_headroom.cache_universe() -> list[str]`, `run_backtest_range._market_frame()`, `regime2.regime_series(spy_df)`, `entry_filters.entries_for(strategy, df, horizon) -> (bullish, bearish)`
- Produces:
  - `sweep_row(row: dict) -> dict`, `live_row(record: dict) -> dict` — both return a trade row `{"day", "closed_day", "direction", "outcome", "r", "strategy", "source"}`
  - `et_day(iso: str | None) -> str | None`
  - `counts_by_day(rows, *, direction="bullish", strategy=None) -> dict[str, int]`
  - `raw_signal_counts(frames, strategies, horizons, date_from, date_to) -> dict[str, int]`
  - `scan_days(scans: list[dict]) -> tuple[dict[str, int], dict[str, dict[str, int]]]` — `(alerts per ET day, funnel sums per ET day incl. "signals" and "alerts")`
  - `load_live_dump(path) -> dict`
  - `backtest_section(rows, days, raw) -> list[str]`, `live_section(rows, scans, days) -> list[str]` — markdown lines
  - CLI: `--backtest`, `--live-json PATH`, `--out PATH`, `--limit N`, `--workers N`

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_market_day_report.py`:

```python
import market_day_report as report  # noqa: E402


def _market(returns, start="2021-03-01"):
    idx = pd.bdate_range(start, periods=len(returns))
    return {str(ts.date()): {"same_day": ret, "prior_day": ret, "trailing_5d": ret, "regime": "bull"}
            for ts, ret in zip(idx, returns)}


def test_et_day_uses_the_us_market_date():
    assert report.et_day("2026-09-02T01:30:00+00:00") == "2026-09-01"     # 21:30 ET the day before
    assert report.et_day("2026-09-01T14:35:00+00:00") == "2026-09-01"
    assert report.et_day(None) is None
    assert report.et_day("not a date") is None


def test_sweep_row_and_live_row_share_one_shape():
    swept = report.sweep_row({"opened_at": "2021-03-01", "closed_at": "2021-03-05",
                              "direction": "bullish", "outcome": "win", "r_multiple": 2.0,
                              "strategy": "RSI", "source": "strategy", "ticker": "AAA", "horizon": "2w"})
    live = report.live_row({"opened_at": "2026-09-01T14:35:00+00:00",
                            "closed_at": "2026-09-04T19:00:00+00:00", "direction": "bullish",
                            "status": "closed", "r": 0.4, "strategy": "RSI"})
    assert set(swept) == set(live) == {"day", "closed_day", "direction", "outcome", "r",
                                       "strategy", "source"}
    assert swept["day"] == "2021-03-01" and swept["closed_day"] == "2021-03-05"
    assert live["day"] == "2026-09-01" and live["closed_day"] == "2026-09-04"
    assert live["outcome"] == "scratch"          # only win/loss are decided
    assert live["source"] == "live"


def test_counts_by_day_filters_direction_and_strategy():
    rows = [{"day": "d1", "direction": "bullish", "strategy": "RSI"},
            {"day": "d1", "direction": "bullish", "strategy": "MACD"},
            {"day": "d1", "direction": "bearish", "strategy": "RSI"},
            {"day": "d2", "direction": "bullish", "strategy": "RSI"}]
    assert report.counts_by_day(rows) == {"d1": 2, "d2": 1}
    assert report.counts_by_day(rows, strategy="RSI") == {"d1": 1, "d2": 1}
    assert report.counts_by_day(rows, direction="bearish") == {"d1": 1}


def test_raw_signal_counts_sums_bullish_entries_in_window(monkeypatch):
    idx = pd.bdate_range("2021-03-01", periods=4)
    frame = pd.DataFrame({"Close": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    bullish = pd.Series([True, False, True, True], index=idx)
    monkeypatch.setattr(report.entry_filters, "entries_for",
                        lambda strategy, df, hk: (bullish, ~bullish))
    counts = report.raw_signal_counts({"AAA": frame, "BBB": frame}, ["RSI"], ["2w"],
                                      "2021-03-02", "2021-03-04")
    assert counts == {"2021-03-03": 2, "2021-03-04": 2}        # day 1 is outside the window


def test_raw_signal_counts_survives_one_bad_pair(monkeypatch):
    idx = pd.bdate_range("2021-03-01", periods=2)
    frame = pd.DataFrame({"Close": [1.0, 2.0]}, index=idx)

    def _boom(strategy, df, hk):
        raise ValueError("no data")

    monkeypatch.setattr(report.entry_filters, "entries_for", _boom)
    assert report.raw_signal_counts({"AAA": frame}, ["RSI"], ["2w"], "2021-01-01", "2021-12-31") == {}


def test_scan_days_sums_scans_into_et_days():
    scans = [
        {"at": "2026-09-01T14:00:00+00:00", "signals": 5, "alerts": 2,
         "funnel": {"bullish/base/base/send/ok": 2, "bullish/base/base/rs/rs_blocked": 1}},
        {"at": "2026-09-01T18:00:00+00:00", "signals": 3, "alerts": 0, "funnel": {}},
        {"at": "2026-09-02T14:00:00+00:00", "signals": 0, "alerts": 0, "funnel": {}},
        {"at": None, "signals": 9, "alerts": 9, "funnel": {}},
    ]
    alerts, sums = report.scan_days(scans)
    assert alerts == {"2026-09-01": 2, "2026-09-02": 0}
    assert sums["2026-09-01"] == {"signals": 8, "alerts": 2, "send:ok": 2, "rs:rejected": 1}
    assert sums["2026-09-02"] == {"signals": 0, "alerts": 0}


def test_load_live_dump_takes_the_json_line_and_ignores_noise(tmp_path):
    path = tmp_path / "dump.json"
    path.write_text('some docker warning\n{"trades": [], "scans": []}\n', encoding="utf-8")
    assert report.load_live_dump(path) == {"trades": [], "scans": []}
    path.write_text("nothing here\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        report.load_live_dump(path)


def test_backtest_section_renders_every_form_with_intervals():
    days = _market([1.5] * 12 + [-1.5] * 12)
    keys = list(days)
    rows = [{"day": d, "closed_day": d, "direction": "bullish", "outcome": "win", "r": 1.0,
             "strategy": "RSI", "source": "strategy"} for d in keys[:12]]
    rows += [{"day": d, "closed_day": None, "direction": "bullish", "outcome": "loss", "r": -1.0,
              "strategy": "confluence", "source": "confluence"} for d in keys[12:]]
    text = "\n".join(report.backtest_section(rows, days, {keys[0]: 5}))
    for form in ("same_day", "prior_day", "trailing_5d"):
        assert form in text
    assert "95% interval" in text
    assert "Spearman" in text
    assert "| > +1% | 12 | 12 | 100.00% " in text
    assert "named strategies only" in text


def test_live_section_prints_no_interval_and_no_correlation():
    days = _market([1.5] * 12, start="2026-09-01")
    keys = list(days)
    rows = [{"day": d, "closed_day": d, "direction": "bullish", "outcome": "win", "r": 1.0,
             "strategy": "RSI", "source": "live"} for d in keys]
    scans = [{"at": f"{d}T14:00:00+00:00", "signals": 4, "alerts": 1,
              "funnel": {"bullish/base/base/send/ok": 1}} for d in keys]
    text = "\n".join(report.live_section(rows, scans, days))
    assert "interval" not in text
    assert "Spearman" not in text
    assert "holdout" in text
    assert "send" in text
    assert "| > +1% | 12 | 12 | 100.00% " in text
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_market_day_report.py`
Expected: FAIL — `No module named 'market_day_report'`.

- [ ] **Step 3: Write the script**

Create `scripts/reports/market_day_report.py`:

```python
#!/usr/bin/env python3
"""v141 descriptive report: LONG win rate, ExpR and alert volume by SPY's daily move.

DESCRIPTIVE ONLY. Four fixed buckets x three market forms x two directions is
a grid, not a test: some cells will look significant by chance. It selects
nothing, registers nothing and moves no badge. A rule on a lagged form is a
separate pre-registered plan.

The backtest half is TRAIN-only (2020-01-01..2023-12-31) and re-uses plan
v51's sweep. The live half reads a dump made on production by
market_day_live_dump.py; it overlaps the 2026 holdout that open
pre-registrations wait on, so it is monitoring only and prints no interval
and no correlation.

    BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache \
        python scripts/reports/market_day_report.py --backtest \
        --live-json data/market_day_live.json --out docs/superpowers/results/<date>-v141-market-day.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest"),
                str(ROOT / "scripts" / "reports")]

from swingbot.core.analytics import market_day as md  # noqa: E402
from swingbot.core.market import entry_filters  # noqa: E402
from swingbot.core.market.session import US_MARKET_TZ  # noqa: E402

TRAIN = ("2020-01-01", "2023-12-31")
DIRECTIONS = (("bullish", "LONG"), ("bearish", "SHORT"))
REGIMES = ((None, "all days"), ("bull", "bull regime"), ("bear", "bear regime"))
FORM_NOTE = {
    "same_day": "same_day -- DESCRIPTIVE ONLY, not known at alert time",
    "prior_day": "prior_day -- known before the scan",
    "trailing_5d": "trailing_5d -- known before the scan",
}
GRID_WARNING = ("> Descriptive grid: 4 buckets x 3 forms x 2 directions x 3 regime cuts. "
                "Some cells will look significant by chance. Nothing here is a selection.")
LIVE_WARNING = ("> Live book: overlaps the 2026 holdout that open pre-registrations wait on. "
                "Monitoring only -- no inferential statistic is printed.")


# -- adapters ----------------------------------------------------------------

def et_day(iso: str | None) -> str | None:
    """US/Eastern calendar date of an ISO timestamp; None when unparseable."""
    if not iso:
        return None
    try:
        stamp = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return str(stamp.date())
    return str(stamp.astimezone(US_MARKET_TZ).date())


def sweep_row(row: dict) -> dict:
    return {"day": row["opened_at"], "closed_day": row.get("closed_at"),
            "direction": row.get("direction"), "outcome": row["outcome"],
            "r": row["r_multiple"], "strategy": row["strategy"], "source": row["source"]}


def live_row(record: dict) -> dict:
    status = record.get("status")
    return {"day": et_day(record.get("opened_at")), "closed_day": et_day(record.get("closed_at")),
            "direction": record.get("direction"),
            "outcome": status if status in ("win", "loss") else "scratch",
            "r": record.get("r"), "strategy": record.get("strategy"), "source": "live"}


def counts_by_day(rows: list[dict], *, direction: str = "bullish",
                  strategy: str | None = None) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        if row.get("direction") != direction or not row.get("day"):
            continue
        if strategy is not None and row.get("strategy") != strategy:
            continue
        out[row["day"]] = out.get(row["day"], 0) + 1
    return out


def raw_signal_counts(frames: dict, strategies, horizons, date_from: str, date_to: str) -> dict[str, int]:
    """{day: bullish entry signals fired} across the universe, before the
    one-position-at-a-time rule turns some of them into trades."""
    out: dict[str, int] = {}
    for ticker, df in frames.items():
        for horizon in horizons:
            for strategy in strategies:
                try:
                    bullish, _ = entry_filters.entries_for(strategy, df, horizon)
                except Exception as error:               # one bad pair must not kill the count
                    print(f"    ! {ticker} {strategy}/{horizon}: {error}", flush=True)
                    continue
                for ts in bullish.index[bullish.fillna(False).to_numpy(dtype=bool)]:
                    day = str(ts.date())
                    if date_from <= day <= date_to:
                        out[day] = out.get(day, 0) + 1
    return out


def scan_days(scans: list[dict]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """(alerts per ET day, per-day sums of signals/alerts/funnel stage counts)."""
    alerts: dict[str, int] = {}
    sums: dict[str, dict[str, int]] = {}
    for scan in scans:
        day = et_day(scan.get("at"))
        if day is None:
            continue
        alerts[day] = alerts.get(day, 0) + int(scan.get("alerts") or 0)
        cell = sums.setdefault(day, {"signals": 0, "alerts": 0})
        cell["signals"] += int(scan.get("signals") or 0)
        cell["alerts"] += int(scan.get("alerts") or 0)
        for key, count in md.funnel_stage_counts(scan.get("funnel") or {}).items():
            cell[key] = cell.get(key, 0) + count
    return alerts, sums


def load_live_dump(path) -> dict:
    """The dump's JSON line; anything docker printed around it is ignored."""
    for line in reversed(Path(path).read_text(encoding="utf-8").splitlines()):
        if line.startswith('{"trades"'):
            return json.loads(line)
    raise SystemExit(f"{path}: no dump line found (expected one starting with {{\"trades\")")


def window_days(days: dict, date_from: str, date_to: str) -> dict:
    return {day: market for day, market in days.items() if date_from <= day <= date_to}


# -- rendering ---------------------------------------------------------------

def _rate(value, suffix="") -> str:
    return "—" if value is None else f"{value:.2f}{suffix}"


def _ci(value) -> str:
    return "—" if value is None else f"{value[0]:.2f} .. {value[1]:.2f}"


def _trade_lines(title: str, table: list[dict], intervals: bool) -> list[str]:
    head = "| bucket | trades | days | win rate | ExpR |"
    rule = "|---|---|---|---|---|"
    if intervals:
        head += " win rate 95% interval | ExpR 95% interval |"
        rule += "---|---|"
    lines = [f"**{title}**", "", head, rule]
    for row in table:
        line = (f"| {row['bucket']} | {row['n']} | {row['days']} | "
                f"{_rate(row['win_rate'], '%')} | {_rate(row['exp_r'], 'R')} |")
        if intervals:
            line += f" {_ci(row['win_rate_ci'])} | {_ci(row['exp_r_ci'])} |"
        lines.append(line)
    return lines + [""]


def _volume_lines(title: str, table: list[dict]) -> list[str]:
    lines = [f"**{title}**", "", "| bucket | days | mean / day | median / day | zero days |",
             "|---|---|---|---|---|"]
    for row in table:
        lines.append(f"| {row['bucket']} | {row['days']} | {_rate(row['mean'])} | "
                     f"{_rate(row['median'])} | {_rate(row['zero_share'], '%')} |")
    return lines + [""]


def _share(numer, denom) -> str:
    return "—" if not denom else f"{numer / denom * 100:.1f}%"


def _trade_block(rows, days, *, intervals: bool) -> list[str]:
    lines: list[str] = []
    for direction, label in DIRECTIONS:
        for form in md.FORMS:
            lines += [f"### {label} by open day -- {FORM_NOTE[form]}", ""]
            if intervals:
                rho = md.day_rank_correlation(rows, days, form, direction=direction)
                lines += [f"Spearman rho, day return vs day mean R: "
                          f"{'—' if rho is None else rho}", ""]
            for regime, regime_label in REGIMES:
                table = md.trade_table(rows, days, form, direction=direction, regime=regime,
                                       intervals=intervals)
                lines += _trade_lines(regime_label, table, intervals)
    return lines


def _close_day_block(rows, days, *, intervals: bool, population: str) -> list[str]:
    closed = [{**row, "day": row["closed_day"]} for row in rows if row.get("closed_day")]
    lines = [f"### LONG by CLOSE day ({population}) -- same_day, MECHANICAL", "",
             "Stops are hit when the market falls, so a red close day shows a low win rate "
             "by construction. Shown for contrast with the open-day tables; not evidence.", ""]
    return lines + _trade_lines("all days", md.trade_table(closed, days, "same_day",
                                                           intervals=intervals), intervals)


def _cause_lines(title: str, table: list[dict], pairs) -> list[str]:
    """`pairs` is [(column label, numerator key, denominator key)]."""
    lines = [f"**{title}**", "", "| bucket | days | " + " | ".join(p[0] for p in pairs) + " |",
             "|---|---|" + "---|" * len(pairs)]
    for row in table:
        totals = row["totals"]
        cells = [f"{totals.get(num, 0)} / {totals.get(den, 0)} = "
                 f"{_share(totals.get(num, 0), totals.get(den, 0))}" for _, num, den in pairs]
        lines.append(f"| {row['bucket']} | {row['days']} | " + " | ".join(cells) + " |")
    return lines + [""]


def backtest_section(rows: list[dict], days: dict, raw: dict[str, int]) -> list[str]:
    lines = ["## Backtest, TRAIN 2020-01-01..2023-12-31", "",
             "Both populations: named strategies and the confluence replay. `day` is the "
             "signal bar's date. Intervals are a 95% interval from a day-level bootstrap "
             "(2000 draws, seed 42).", ""]
    lines += _trade_block(rows, days, intervals=True)
    lines += _close_day_block([r for r in rows if r["source"] == "strategy"], days,
                              intervals=True, population="named strategies")
    lines += ["### LONG trades opened per day", ""]
    for form in md.FORMS:
        lines += _volume_lines(f"all populations -- {FORM_NOTE[form]}",
                               md.volume_table(counts_by_day(rows), days, form))
    for strategy in sorted({row["strategy"] for row in rows if row["direction"] == "bullish"}):
        lines += _volume_lines(f"{strategy} -- prior_day",
                               md.volume_table(counts_by_day(rows, strategy=strategy),
                                               days, "prior_day"))
    taken = counts_by_day([r for r in rows if r["source"] == "strategy"])
    values = {day: {"signals": raw.get(day, 0), "taken": taken.get(day, 0)}
              for day in set(raw) | set(taken)}
    lines += ["### Cause: fewer setups, or the same setups and fewer taken?", "",
              "Covers named strategies only -- the confluence replay has no separate "
              "pre-trade signal count. `signals` are raw bullish entry signals; `taken` "
              "are trades opened under the one-position-at-a-time rule.", ""]
    for form in md.FORMS:
        table = md.sum_by_bucket(values, days, form)
        lines += _cause_lines(FORM_NOTE[form], table, [("taken / signals", "taken", "signals")])
        lines += _volume_lines(f"raw signals per day -- {form}", md.volume_table(raw, days, form))
    return lines


def _stage_pairs(sums: dict[str, dict[str, int]]) -> list[tuple[str, str, str]]:
    """One (label, ok key, reached key) per funnel stage present in the data."""
    from swingbot.core.scanning.short_funnel import STAGES
    present = {key.split(":")[0] for cell in sums.values() for key in cell if ":" in key}
    return [(f"{stage} pass", f"{stage}:ok", f"{stage}:reached")
            for stage in STAGES if stage in present]


def _with_reached(sums: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    out = {}
    for day, cell in sums.items():
        stages = {key.split(":")[0] for key in cell if ":" in key}
        reached = {f"{stage}:reached": cell.get(f"{stage}:ok", 0) + cell.get(f"{stage}:rejected", 0)
                   for stage in stages}
        out[day] = {**cell, **reached}
    return out


def live_section(rows: list[dict], scans: list[dict], days: dict) -> list[str]:
    alerts, sums = scan_days(scans)
    observed = set(alerts)
    funnel_days = sum(1 for cell in sums.values() if any(":" in key for key in cell))
    lines = ["## Live paper book", "", LIVE_WARNING, "",
             f"Closed trades: {len(rows)}. Scanned trading days: {len(observed)}. "
             f"Days with a staged funnel: {funnel_days}.", ""]
    lines += _trade_block(rows, days, intervals=False)
    lines += _close_day_block(rows, days, intervals=False, population="live book")
    lines += ["### Alerts per scanned day", "",
              "Denominator: trading days with at least one scan. A day with no scan is an "
              "outage and is left out.", ""]
    for form in md.FORMS:
        lines += _volume_lines(FORM_NOTE[form],
                               md.volume_table(alerts, days, form, observed=observed))
    lines += ["### Cause: where candidates are lost (bullish)", ""]
    staged = _with_reached(sums)
    for form in md.FORMS:
        table = md.sum_by_bucket(staged, days, form)
        lines += _cause_lines(f"alerts / signals -- {FORM_NOTE[form]}", table,
                              [("alerts / signals", "alerts", "signals")])
        pairs = _stage_pairs(sums)
        if pairs:
            lines += _cause_lines(f"stage pass rates -- {form}", table, pairs)
    return lines


# -- loading and CLI ---------------------------------------------------------

def _spy_days(spy_df) -> dict:
    from swingbot.core.edge.regime2 import regime_series
    return md.market_days(spy_df["Close"], regime_series(spy_df))


def _backtest_inputs(limit: int | None, workers: int | None):
    import measure_alert_density as mad
    import run_backtest_range as rbr
    from runner_headroom import cache_universe
    from swingbot.core.backtesting.backtest import ALL_STRATEGIES
    from swingbot.core.backtesting.backtest_scenarios import CONFLUENCE_GATES
    from swingbot.core.market.strategy_types import LEGACY_HORIZONS

    spy = rbr._market_frame()
    if spy is None:
        raise SystemExit("benchmark not in the backtest cache -- run scripts/data/fetch_backtest_data.py")
    tickers = cache_universe()[:limit] if limit else cache_universe()
    frames, _ = mad.load_frames(tickers)
    swept = mad.sweep(frames, *TRAIN, horizons=list(LEGACY_HORIZONS), gates=CONFLUENCE_GATES,
                      scale_out=True, strategies=list(ALL_STRATEGIES), workers=workers)
    print("counting raw entry signals...", flush=True)
    raw = raw_signal_counts(frames, ALL_STRATEGIES, LEGACY_HORIZONS, *TRAIN)
    return [sweep_row(row) for row in swept], window_days(_spy_days(spy), *TRAIN), raw


def _live_inputs(path):
    from swingbot import config
    from swingbot.core.marketdata import backtest_cache

    dump = load_live_dump(path)
    spy = backtest_cache.fetch(config.MARKET_REGIME_TICKER)      # live dates run past the CSV cache
    if spy is None:
        raise SystemExit("could not fetch the benchmark for the live half")
    rows = [live_row(record) for record in dump["trades"]]
    return rows, dump["scans"], _spy_days(spy)


def main() -> None:
    ap = argparse.ArgumentParser(description="v141 market-day report (descriptive only).")
    ap.add_argument("--backtest", action="store_true", help="run the TRAIN half (slow)")
    ap.add_argument("--live-json", dest="live_json", default=None,
                    help="dump from market_day_live_dump.py")
    ap.add_argument("--out", default=None, help="write markdown here (default: stdout)")
    ap.add_argument("--limit", type=int, default=None,
                    help="first N cached tickers -- smoke runs, never the reported answer")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()
    if not args.backtest and not args.live_json:
        ap.error("need --backtest and/or --live-json")

    lines = ["# v141 -- market-day report", "", GRID_WARNING, ""]
    if args.limit:
        lines += [f"> SMOKE RUN: first {args.limit} tickers only. Not a result.", ""]
    if args.backtest:
        lines += backtest_section(*_backtest_inputs(args.limit, args.workers))
    if args.live_json:
        lines += live_section(*_live_inputs(args.live_json))
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", flush=True)
    else:
        print(text)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run it and watch it pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_market_day_report.py`
Expected: `VERDICT: PASS`.

- [ ] **Step 5: Smoke the real path**

Run:

```bash
BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache \
  python scripts/reports/market_day_report.py --backtest --limit 3 --workers 1
```

Expected: progress lines with a percent, then markdown beginning `# v141 -- market-day report` and a `SMOKE RUN` line. Tables may be mostly `—` at three tickers; that is correct. A traceback is a failure — fix it before committing.

- [ ] **Step 6: Complexity, then commit**

Run: `python -m radon cc -s -n C scripts/reports/market_day_report.py scripts/reports/market_day_live_dump.py` — expected: no output.

```bash
git add scripts/reports/market_day_report.py tests/scripts/test_market_day_report.py
git commit -m "feat(v141): market-day report script -- TRAIN and live halves (V141-6)"
```

---

### Task V141-7: Run it and record the result

**Files:**
- Create: `docs/superpowers/results/<run date>-v141-market-day.md`
- Not committed: `data/market_day_live.json`, `logs/market_day_report.log`

**Interfaces:**
- Consumes: the script (V141-6) and the dump script (V141-5).
- Produces: the results file.

- [ ] **Step 1: Take the live dump (read-only on production)**

Run from the worktree root:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
  < scripts/reports/market_day_live_dump.py > data/market_day_live.json
python -c "import sys; sys.path.insert(0,'scripts/reports'); import market_day_report as r; d=r.load_live_dump('data/market_day_live.json'); print(len(d['trades']),'trades',len(d['scans']),'scans', d['scans'][0]['at'] if d['scans'] else None)"
git status --short data/
```

Expected: a trade count, a scan count and the first scan's timestamp; `git status` shows nothing under `data/` (it is ignored). If the dump has zero scans, or no funnel key starts with `bullish/`, stop and report it — the live cause table would be empty and the partner should know before the report is written. This step changes nothing on production, so the mirror-back rule does not apply.

- [ ] **Step 2: Run the full report through `backtest-runner`**

Dispatch the `backtest-runner` agent (the TRAIN sweep is long) with exactly this command, from the worktree root:

```bash
BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache \
  python scripts/reports/market_day_report.py --backtest \
  --live-json data/market_day_live.json \
  --out docs/superpowers/results/$(date +%F)-v141-market-day.md \
  2>&1 | tee logs/market_day_report.log
rm logs/market_day_report.log
```

Ask it to return only: the final `wrote ...` line, the trade count from `sweep done`, and any line starting `    !`.

- [ ] **Step 3: Write the reading at the top of the results file**

Open the generated file and insert, directly under the grid warning, a section `## Reading` of at most 25 lines that answers, with the table it comes from named each time:

1. Do LONG trades opened on green days win more? Answer for `same_day` (descriptive) and separately for `prior_day` and `trailing_5d` (the only forms a rule could use). Quote the bucket rows and their intervals; say "no visible effect" when the intervals overlap.
2. Does the answer survive the bull/bear split, or is it the slow regime?
3. Does the bot open fewer LONG trades on red days? Quote TRAIN mean per day and zero-day share. State that live LONG-specific rates are unavailable from all-direction scan telemetry, then quote live all-direction alert mean and zero-day share separately as context.
4. If so, which stage: fewer raw signals, or the same signals and fewer taken (TRAIN); for live, give the bullish funnel day count and state whether those staged days actually identify a LONG loss.
5. One closing line: either "candidate for a pre-registered rule: `<form>`, `<direction of effect>`" or "no candidate".

Also add one line citing `docs/superpowers/results/2026-08-23-alert-density-train.md` as the earlier, related density finding.

Every number in the reading is copied from a table in the same file. State nothing about VALIDATION.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/*-v141-market-day.md
git commit -m "docs(v141): market-day report result -- TRAIN and live"
```

---

### Task V141-8: Full suite and close-out

**Files:**
- Modify: this plan (tick the boxes); moved at close-out.

- [ ] **Step 1: Full suite, once**

Dispatch the `test-runner` agent: `python scripts/dev/testrun.py full`. Green is `0 failed` and `0 xfailed`. If the test database is unreachable, start it first (`docker compose --profile test up -d db-test`) so the database tier runs rather than skips.

- [ ] **Step 2: Complexity over everything the plan touched**

Run: `python -m radon cc -s -n C swingbot/core/analytics/market_day.py scripts/reports/market_day_report.py scripts/reports/market_day_live_dump.py`
Expected: no output. (`scripts/backtest/measure_alert_density.py` holds legacy functions; the two this plan edited must not have got worse — compare `radon cc -s` for `_entry_dates_for_ticker` and `sweep` against `main`.)

- [ ] **Step 3: Close out**

Run `/close-out`. `Bump: none` — no `VERSION.json` change. The plan moves to `docs/superpowers/plans/implemented/`, the spec to `docs/superpowers/specs/implemented/`. Merge the worktree branch per the `worktree-lifecycle` skill.

- [ ] **Step 4: Report to the partner**

Give the five answers from the results file's `## Reading`, and say whether step 2 (dashboard panel) and step 3 (pre-registered rule) of the spec now have something to build on.
