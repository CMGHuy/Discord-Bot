# v183 — Gap-aware short sizing, and a squeeze/event notice on every short: Part 4 — impact results, release and full suite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Spec:** [2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md](../specs/2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md)
**Index:** [2026-10-21-v183-short-gap-sizing-and-squeeze-notice_0-index.md](2026-10-21-v183-short-gap-sizing-and-squeeze-notice_0-index.md). Goal, Architecture, `## Global Constraints`, `## Contracts`, `## Review Focus`, `## Parallelisation` and the task ledger live there and bind every task below.
**Worktree:** `.claude/worktrees/2026-10-21-v183-short-gap-sizing-and-squeeze-notice` (branch of the same name). Every path below is relative to that worktree until V183-17's merge step.

This part covers the spec's "Measured once, after build (not a gate)" requirement (V183-16) and the plan's single full-suite run, release bump, merge and close-out (V183-17).

# Phase 4 — Impact and release

### Task V183-16: Impact results doc: re-size the live book's closed shorts

**Model:** sonnet — a new read-only report script over finished sizing code, with plain arithmetic and a rendered markdown file; no shared contract is changed.

The spec ("Measured once, after build (not a gate)") asks for one results doc. It re-sizes the live book's closed shorts under the rule, from their stored bars. It reports the share of shorts gap-sized, the mean size cut, dollar P&L at a fixed per-trade risk before and after, the worst five dollar losses before and after, and the short book's max drawdown before and after (`edge/ruin.py`, `risk_metrics.py`). It is descriptive. Nothing reads it, and no threshold turns it into a pass or a fail. `SHORT_GAP_SIZING=false` stays the revert path whatever it shows.

**Decisions fixed here (the implementer does not revisit them):**
- **Fixed per-trade risk.** Both sizings use one account: `balance` 10 000, `risk_pct` 1.0, `sizing_mode` `"risk_pct"`. Position caps are off: `max_position_pct` 1e9, both absolute caps 0. OPEX scaling is pinned to 1.0 while sizing. That way only the gap rule moves the share count, and the figures do not depend on the run date. With live caps the cut is the same or smaller; the doc says so.
- **p99 per trade, no lookahead.** If the trade record already carries a `gap_sizing` stamp with a non-`None` `up_gap_p99_pct` (a trade opened after ship), use that stamp. Otherwise compute `gap_stats(completed, lookback=LOOKBACK)` on the daily bars strictly before the trade's `opened_at` session date (New York). If `n_up < MIN_UP_GAPS`, the trade has no p99: its size stays unchanged and it is counted as `none`.
- **R is the book's own.** `analytics.metrics.r_multiple(trade)` handles legs and gap fills, and does not clamp. Dollar P&L for one side is `shares × |entry − stop_loss| × R`, so a gap fill keeps its real R on both sides, and R is identical before and after by construction.
- **Drawdown.** Dollar max drawdown is `risk_metrics.max_drawdown_r` over the dollar P&L series in `closed_at` order (the function is a plain cumulative-sum drawdown, so it takes dollars as well as R). There is also a bootstrap: `ruin.simulate` over the P&L expressed in units of the fixed risk (`pnl / (balance × risk_pct / 100)`), at the same `risk_pct`, giving `max_dd_p50` / `max_dd_p95` before and after.
- **Where it runs.** Locally, against the `/replicate-prod-db` replica (`swingbot_prod_replica`), with the worktree's code. It never runs on production, which does not carry the v183 sizing until deploy. Read-only: the script reads trades and daily bars and writes only the `--out` file. It never prints `DATABASE_URL` or any other `.env` value.

**Files:**
- Create: `scripts/reports/short_gap_sizing_impact.py`
- Create: `tests/scripts/test_short_gap_sizing_impact.py` (existing `tests/scripts/` directory, suite already listed in `tests/suites.toml`; no manifest edit)
- Create: `docs/superpowers/results/<run-date>-v183-gap-sizing-impact.md` (written by the script in Step 6; `<run-date>` is the day it runs, `YYYY-MM-DD`)

**Interfaces:**
- Consumes:
  - `compute_position_size(entry, stop_loss, account_cfg=None, *, ..., gap_floor_pct=None) -> dict | None`, with result keys `shares`, `gap_sized` (V183-3).
  - `gap_stats(df, lookback=250)["p99_up_gap_pct"]` and `["n_up"]` (V183-2).
  - `gap_sizing.LOOKBACK` (250) and `gap_sizing.MIN_UP_GAPS` (60) (V183-4).
  - Trade key `gap_sizing` = `{"rule", "up_gap_p99_pct", "n_up_gaps"}` (V183-6).
  - Existing: `swingbot.core.analytics.metrics.r_multiple(trade)` (`metrics.py:173`), `swingbot.core.analytics.risk_metrics.max_drawdown_r(r_multiples)` (`risk_metrics.py:174`), `swingbot.core.edge.ruin.simulate(r_multiples, *, risk_pct, ...)` (`ruin.py:18`, keys `max_dd_p50`, `max_dd_p95`), `swingbot.core.market.opex.size_mult` (`opex.py:238`, called as `opex.size_mult()` in `account.py:482`), `TradeLog().get_trades(status="all", limit=None)` (`performance.py:1230`), `swingbot.core.marketdata.data.get_daily_data(ticker, period=...)` (`data.py:36`), `swingbot.core.db.engine.reset_engine()`.
- Produces:
  - `resize_closed_shorts(trades: list[dict], frames: dict[str, pd.DataFrame | None], *, balance: float, risk_pct: float) -> dict`, shaped `{"n_closed_shorts": int, "rows": list[dict], "summary": dict}`.
  - `render_markdown(result: dict, *, run_date: str, db_name: str, balance: float, risk_pct: float) -> str`.
  - The results doc. Nothing later in this plan consumes it except V183-17's close-out check that it exists.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_short_gap_sizing_impact.py`:

```python
"""v183 impact report: closed shorts re-sized under the gap rule at fixed risk (read-only)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.analytics.risk_metrics import max_drawdown_r
from swingbot.core.market import opex
from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import short_gap_sizing_impact as imp  # noqa: E402

BAL, RISK = 10_000.0, 1.0          # fixed risk: $100 per trade


def _bars(up_pct, n=300, start="2024-01-01"):
    """Close 100 every day; even days open up_pct above the prior close, odd days 0.5% below,
    so every up-gap equals up_pct (p99 == up_pct) and n_up is about n / 2."""
    rows = []
    for i in range(n):
        o = 100.0 * (1 + up_pct / 100.0) if i % 2 == 0 else 99.5
        rows.append((o, max(o, 100.0) * 1.001, min(o, 100.0) * 0.999, 100.0))
    return make_ohlcv(rows, start=start)


def _short(tid="t1", ticker="AAA", exit_price=103.0, status="loss", opened="2025-03-01T15:00:00+00:00",
           closed="2025-03-05T15:00:00+00:00", **kw):
    t = {"id": tid, "ticker": ticker, "direction": "bearish", "status": status,
         "entry": 100.0, "stop_loss": 101.0, "exit_price": exit_price,
         "opened_at": opened, "closed_at": closed}
    t.update(kw)
    return t


def _run(trades, frames):
    return imp.resize_closed_shorts(trades, frames, balance=BAL, risk_pct=RISK)


def test_gap_wider_than_stop_cuts_shares_and_keeps_the_real_r():
    out = _run([_short()], {"AAA": _bars(3.0)})
    (row,) = out["rows"]
    assert row["p99_source"] == "bars"
    assert row["p99"] == pytest.approx(3.0)
    assert row["shares_before"] == pytest.approx(100.0)          # $100 / $1 stop
    assert row["shares_after"] == pytest.approx(33.33)           # $100 / max($1, 100 x 3%)
    assert row["gap_sized"] is True
    assert row["r"] == pytest.approx(-3.0)                       # gapped through to 103: real R, not -1
    assert row["pnl_before"] == pytest.approx(-300.0)
    assert row["pnl_after"] == pytest.approx(-99.99)
    s = out["summary"]
    assert s["n_gap_sized"] == 1 and s["share_gap_sized_pct"] == pytest.approx(100.0)
    assert s["mean_cut_pct_gap_sized"] == pytest.approx(66.67, abs=0.01)


def test_stop_wider_than_gap_leaves_the_size_alone():
    (row,) = _run([_short()], {"AAA": _bars(0.5)})["rows"]
    assert row["shares_after"] == row["shares_before"]
    assert row["gap_sized"] is False
    assert row["pnl_after"] == row["pnl_before"]


def test_too_few_up_gaps_means_no_p99_and_no_cut():
    out = _run([_short()], {"AAA": _bars(3.0, n=40)})
    (row,) = out["rows"]
    assert (row["p99"], row["p99_source"]) == (None, "none")
    assert row["shares_after"] == row["shares_before"]
    assert out["summary"]["n_no_p99"] == 1


def test_missing_bars_mean_no_p99():
    (row,) = _run([_short()], {})["rows"]
    assert row["p99_source"] == "none"


def test_only_bars_before_the_open_count():
    early = _bars(0.5, n=300, start="2023-01-02")
    first_late = early.index[-1] + pd.offsets.BDay(1)
    late = _bars(3.0, n=300, start=str(first_late.date()))
    opened = first_late.strftime("%Y-%m-%dT14:00:00+00:00")     # 10:00 New York on the first stormy day
    (row,) = _run([_short(opened=opened)], {"AAA": pd.concat([early, late])})["rows"]
    assert row["p99"] == pytest.approx(0.5)
    assert row["gap_sized"] is False


def test_stored_stamp_wins_over_bars():
    stamp = {"rule": "gap_p99", "up_gap_p99_pct": 2.0, "n_up_gaps": 120}
    (row,) = _run([_short(gap_sizing=stamp)], {})["rows"]
    assert (row["p99"], row["p99_source"]) == (2.0, "stamp")
    assert row["shares_after"] == pytest.approx(50.0)


def test_longs_open_trades_and_unpriceable_records_are_left_out():
    trades = [_short(), _short(tid="o", status="open"), _short(tid="l", direction="bullish"),
              _short(tid="z", stop_loss=100.0)]
    out = _run(trades, {"AAA": _bars(3.0)})
    assert out["n_closed_shorts"] == 2                            # t1 and the zero-risk z
    assert [r["id"] for r in out["rows"]] == ["t1"]


def test_worst_five_are_sorted_per_side_and_capped_at_five():
    trades = [_short(tid=f"t{i}", exit_price=100.0 + i, closed=f"2025-03-{10 + i}T15:00:00+00:00")
              for i in range(1, 7)]
    s = _run(trades, {"AAA": _bars(3.0)})["summary"]
    assert len(s["worst_before"]) == 5 and len(s["worst_after"]) == 5
    assert [w["pnl_before"] for w in s["worst_before"]] == sorted(w["pnl_before"] for w in s["worst_before"])
    assert s["worst_before"][0]["pnl_before"] == pytest.approx(-600.0)


def test_drawdown_is_taken_in_close_order_on_each_side():
    trades = [_short(tid="b", exit_price=103.0, closed="2025-03-03T15:00:00+00:00"),
              _short(tid="a", exit_price=98.0, closed="2025-03-02T15:00:00+00:00"),
              _short(tid="c", exit_price=99.0, closed="2025-03-04T15:00:00+00:00")]
    out = _run(trades, {"AAA": _bars(3.0)})
    ordered = sorted(out["rows"], key=lambda r: r["closed_at"])   # a (+2R), b (-3R), c (+1R)
    dd = out["summary"]["drawdown"]
    assert dd["before"]["max_dd_dollars"] == pytest.approx(max_drawdown_r([r["pnl_before"] for r in ordered]))
    assert dd["before"]["max_dd_dollars"] == pytest.approx(300.0)
    assert dd["after"]["max_dd_dollars"] == pytest.approx(max_drawdown_r([r["pnl_after"] for r in ordered]))
    assert dd["after"]["max_dd_dollars"] < dd["before"]["max_dd_dollars"]
    assert set(dd["before"]) >= {"bootstrap_dd_p50", "bootstrap_dd_p95"}


def test_opex_scaling_never_changes_the_fixed_risk(monkeypatch):
    monkeypatch.setattr(opex, "size_mult", lambda *a, **k: 0.5)
    (row,) = _run([_short()], {"AAA": _bars(3.0)})["rows"]
    assert row["shares_before"] == pytest.approx(100.0)


def test_empty_book_renders_without_numbers():
    out = _run([], {})
    assert out["summary"]["n_analysed"] == 0
    text = imp.render_markdown(out, run_date="2026-11-02", db_name="swingbot_prod_replica",
                               balance=BAL, risk_pct=RISK)
    assert "n/a" in text and "not a gate" in text


def test_markdown_carries_every_measure_and_the_rollback_note():
    out = _run([_short()], {"AAA": _bars(3.0)})
    text = imp.render_markdown(out, run_date="2026-11-02", db_name="swingbot_prod_replica",
                               balance=BAL, risk_pct=RISK)
    for needle in ("# v183 gap sizing impact", "## Result", "## Worst five dollar losses",
                   "## Short-book drawdown", "## Limits", "## Rollback", "SHORT_GAP_SIZING=false",
                   "SHORT_RISK_NOTICE=false", "rollback_to.sh", "stay in the book as recorded",
                   "-$300.00", "-$99.99", "not a gate"):
        assert needle in text, needle


def test_db_name_swap_keeps_credentials_and_host():
    url = "postgresql+psycopg://u:secret@db.local:5432/swingbot"
    assert imp._with_db(url, "swingbot_prod_replica") == \
        "postgresql+psycopg://u:secret@db.local:5432/swingbot_prod_replica"
```

The fixture arithmetic, worked once so a reviewer can check it:
- `_bars(3.0)` has about 125 up-gaps of exactly 3%, so p99 = 3.0.
- Sizing distance = max($1 stop, 100 × 3% = $3) = $3, so shares = 100 / 3 = 33.33.
- Exit at 103 on a short with stop 101 gives R = −3.
- So the dollars are −$300 before and −$99.99 after.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_short_gap_sizing_impact.py`
Expected: collection error `ModuleNotFoundError: No module named 'short_gap_sizing_impact'`.

- [ ] **Step 3: Implement `scripts/reports/short_gap_sizing_impact.py`**

Every function below stays under complexity 15. The constants, `ROLLBACK_NOTE` and `LIMITS` are exact copy.

```python
#!/usr/bin/env python3
"""v183 impact: the live book's closed shorts re-sized under the gap rule.

Read-only and descriptive, never a gate (spec "Measured once, after build").
Each closed bearish paper trade is sized twice at one fixed per-trade risk
(balance x risk_pct / 100; position caps off; OPEX scaling pinned to 1.0):
on the stop, and with the v183 gap floor. The floor is the trade's stored
gap_sizing p99 when it has one, else the p99 of up-gaps over the LOOKBACK
completed daily bars before the trade opened; fewer than MIN_UP_GAPS
up-gaps means no p99 and no change. R is the book's own r_multiple (gap
fills keep their real R); dollar P&L = shares x stop distance x R.

Run locally after /replicate-prod-db, never on production (it has no v183
sizing until deploy). Prints no .env value:
    python scripts/reports/short_gap_sizing_impact.py --db swingbot_prod_replica \
        --out docs/superpowers/results/<run-date>-v183-gap-sizing-impact.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.analytics.metrics import r_multiple  # noqa: E402
from swingbot.core.analytics.risk_metrics import max_drawdown_r  # noqa: E402
from swingbot.core.edge import ruin  # noqa: E402
from swingbot.core.edge.gates import gap_stats  # noqa: E402
from swingbot.core.market import opex  # noqa: E402
from swingbot.core.planning.account import compute_position_size  # noqa: E402
from swingbot.core.planning.gap_sizing import LOOKBACK, MIN_UP_GAPS  # noqa: E402

log = logging.getLogger("short_gap_sizing_impact")

CLOSED = ("win", "loss", "closed")
NY = "America/New_York"
WORST_N = 5
SPEC = "../specs/2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md"

LIMITS = (
    "- p99 over about 125 up-gaps is roughly the one or two largest up-gaps of the year: noisy, accepted in the spec.\n"
    "- Position caps are off and OPEX scaling is pinned to 1.0 so only the gap rule moves size; "
    "with the live caps the cut is the same or smaller.\n"
    "- Trades opened before v183 shipped carry no stamp; their p99 is recomputed from the cached daily bars "
    "before the open, so a bar-cache gap shows up as `none` (size unchanged).\n"
    "- R, win rate and ExpR are identical on both sides by construction (R is measured on the stop); "
    "only dollars move.\n"
)

ROLLBACK_NOTE = (
    "- **No deploy needed:** set `SHORT_GAP_SIZING=false` (and `SHORT_RISK_NOTICE=false` for the notice) in `.env` "
    "or the admin config page; the bot hot-reloads. Plans stamped while the switch was on keep their stamped rule; "
    "plans created after the flip size on the stop exactly as before v183.\n"
    "- **Code rollback** (`scripts/ops/rollback_to.sh`): the `gap_sizing` / `risk_notice` keys on plan docs and "
    "trade records and the `data/short_interest.json` cache are left in place, unread and harmless.\n"
    "- Paper trades already sized by the gap rule stay in the book as recorded; nothing re-sizes them.\n"
)


def _with_db(url: str, name: str) -> str:
    from sqlalchemy.engine import make_url
    return make_url(url).set(database=name).render_as_string(hide_password=False)


def closed_shorts(trades: list[dict]) -> list[dict]:
    return [t for t in trades if t.get("direction") == "bearish" and t.get("status") in CLOSED]


def _opened_session(trade: dict) -> pd.Timestamp:
    ts = pd.Timestamp(trade["opened_at"])
    return pd.Timestamp((ts.tz_convert(NY) if ts.tzinfo is not None else ts).date())


def _bars_p99(trade: dict, bars) -> float | None:
    if bars is None or bars.empty or not trade.get("opened_at"):
        return None
    idx = pd.DatetimeIndex(bars.index)
    idx = idx.tz_localize(None) if idx.tz is not None else idx
    stats = gap_stats(bars[idx < _opened_session(trade)], lookback=LOOKBACK)
    return stats["p99_up_gap_pct"] if stats["n_up"] >= MIN_UP_GAPS else None


def trade_p99(trade: dict, bars) -> tuple[float | None, str]:
    stamp = trade.get("gap_sizing") or {}
    if stamp.get("up_gap_p99_pct") is not None:
        return float(stamp["up_gap_p99_pct"]), "stamp"
    p99 = _bars_p99(trade, bars)
    return (p99, "bars") if p99 is not None else (None, "none")


def _fixed_cfg(balance: float, risk_pct: float) -> dict:
    return {"balance": balance, "risk_pct": risk_pct, "sizing_mode": "risk_pct",
            "max_position_pct": 1e9, "max_position_value_absolute": 0.0,
            "max_risk_amount_absolute": 0.0}


@contextmanager
def _fixed_risk():
    """OPEX weeks scale risk_pct by the run date; this report fixes per-trade risk."""
    with mock.patch.object(opex, "size_mult", return_value=1.0):
        yield


def resize_trade(trade: dict, bars, cfg: dict) -> dict | None:
    r = r_multiple(trade)
    if r is None:
        return None
    entry, stop = float(trade["entry"]), float(trade["stop_loss"])
    before = compute_position_size(entry, stop, cfg)
    if before is None:
        return None
    p99, source = trade_p99(trade, bars)
    after = before if p99 is None else compute_position_size(entry, stop, cfg, gap_floor_pct=p99)
    dist = abs(entry - stop)
    return {"id": trade.get("id"), "ticker": trade.get("ticker"), "closed_at": trade.get("closed_at") or "",
            "r": r, "p99": p99, "p99_source": source,
            "shares_before": before["shares"], "shares_after": after["shares"],
            "gap_sized": bool(after.get("gap_sized")),
            "pnl_before": round(before["shares"] * dist * r, 2),
            "pnl_after": round(after["shares"] * dist * r, 2)}


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _cut_pct(row: dict) -> float:
    return 100.0 * (1.0 - row["shares_after"] / row["shares_before"]) if row["shares_before"] else 0.0


def _worst(rows: list[dict], key: str) -> list[dict]:
    keep = ("ticker", "closed_at", "r", "pnl_before", "pnl_after")
    return [{k: row[k] for k in keep} for row in sorted(rows, key=lambda x: x[key])[:WORST_N]]


def _side_drawdown(pnls: list[float], unit: float, risk_pct: float) -> dict:
    out = {"max_dd_dollars": max_drawdown_r(pnls), "bootstrap_dd_p50": None, "bootstrap_dd_p95": None}
    if pnls and unit > 0:
        sim = ruin.simulate([p / unit for p in pnls], risk_pct=risk_pct)
        out["bootstrap_dd_p50"], out["bootstrap_dd_p95"] = sim["max_dd_p50"], sim["max_dd_p95"]
    return out


def _drawdowns(rows: list[dict], unit: float, risk_pct: float) -> dict:
    ordered = sorted(rows, key=lambda x: x["closed_at"])
    return {side: _side_drawdown([x[f"pnl_{side}"] for x in ordered], unit, risk_pct)
            for side in ("before", "after")}


def _summary(rows: list[dict], balance: float, risk_pct: float) -> dict:
    cut = [x for x in rows if x["gap_sized"]]
    unit = balance * risk_pct / 100.0
    return {"n_analysed": len(rows), "unit": unit,
            "n_no_p99": sum(x["p99_source"] == "none" for x in rows),
            "n_from_stamp": sum(x["p99_source"] == "stamp" for x in rows),
            "n_gap_sized": len(cut),
            "share_gap_sized_pct": 100.0 * len(cut) / len(rows) if rows else None,
            "mean_cut_pct_gap_sized": _mean([_cut_pct(x) for x in cut]),
            "mean_cut_pct_all": _mean([_cut_pct(x) for x in rows]),
            "mean_r": _mean([x["r"] for x in rows]),
            "pnl_before": round(sum(x["pnl_before"] for x in rows), 2),
            "pnl_after": round(sum(x["pnl_after"] for x in rows), 2),
            "worst_before": _worst(rows, "pnl_before"), "worst_after": _worst(rows, "pnl_after"),
            "drawdown": _drawdowns(rows, unit, risk_pct)}


def resize_closed_shorts(trades: list[dict], frames: dict, *, balance: float, risk_pct: float) -> dict:
    cfg = _fixed_cfg(balance, risk_pct)
    shorts = closed_shorts(trades)
    with _fixed_risk():
        rows = [row for t in shorts if (row := resize_trade(t, frames.get(t.get("ticker")), cfg))]
    return {"n_closed_shorts": len(shorts), "rows": rows, "summary": _summary(rows, balance, risk_pct)}
```

`render_markdown(result, *, run_date, db_name, balance, risk_pct) -> str` assembles the sections below from small helpers, one helper per table:
- `_money(x)` gives `-$300.00`, `$1,234.50` or `n/a`.
- `_pct(x, digits=1)` gives `66.7%` or `n/a`.
- `_num(x)` gives `n/a` for `None`.

The output text, with `<...>` holes filled from `result["summary"]`:

```text
# v183 gap sizing impact: the live book's closed shorts re-sized

**Spec:** [v183 design](<SPEC>) § "Measured once, after build (not a gate)"
**Run:** <run_date> on `<db_name>` (read-only replica of production), `scripts/reports/short_gap_sizing_impact.py`
**Status:** descriptive, not a gate. The cut stays unvalidated; `SHORT_GAP_SIZING=false` is the revert path.

## What is measured

Each closed short (status win/loss/closed, direction bearish) is sized twice at a fixed risk of <_money(unit)> per trade (balance <_money(balance)>, <risk_pct>%): on the stop, and with the gap floor `max(|entry - stop|, entry x p99_up_gap / 100)`. p99 source: the trade's stored stamp, else the up-gaps over the 250 completed daily bars before the open (fewer than 60 up-gaps: no p99, no change). Dollar P&L = shares x stop distance x the book's R.

## Result

| Measure | Value |
|---|---|
| Closed shorts in the book | <n_closed_shorts> |
| Analysed (R computable) | <n_analysed> |
| p99 from a stored stamp / from bars / none | <n_from_stamp> / <n_analysed - n_from_stamp - n_no_p99> / <n_no_p99> |
| Gap-sized (share cut) | <n_gap_sized> (<_pct(share_gap_sized_pct)>) |
| Mean size cut, gap-sized shorts | <_pct(mean_cut_pct_gap_sized)> |
| Mean size cut, all analysed shorts | <_pct(mean_cut_pct_all)> |
| Mean R (identical both sides) | <mean_r as +0.000R, or n/a> |
| Dollar P&L at fixed risk, before | <_money(pnl_before)> |
| Dollar P&L at fixed risk, after | <_money(pnl_after)> |

## Worst five dollar losses

Before (stop sizing):

| Ticker | Closed | R | $ before | $ after |
|---|---|---|---|---|
<one row per worst_before entry, Closed = the date part of closed_at, R as +0.00R; a single all-n/a row when empty>

After (gap sizing):

<the same table over worst_after>

## Short-book drawdown

| Measure | Before | After |
|---|---|---|
| Max drawdown, $ in close order | <_money> | <_money> |
| Max drawdown, % of balance | <_pct(max_dd_dollars / balance x 100)> | <...> |
| Bootstrap max drawdown p50 (ruin.simulate, 1000 trades x 2000 paths) | <_pct(bootstrap_dd_p50 x 100)> | <...> |
| Bootstrap max drawdown p95 | <_pct(bootstrap_dd_p95 x 100)> | <...> |

## Limits

<LIMITS>
## Rollback

<ROLLBACK_NOTE>
```

`main(argv=None) -> int`:
- Arguments: `--db` (default `swingbot_prod_replica`), `--balance` (float, default 10000), `--risk-pct` (float, default 1.0), `--out` (Path, optional).
- Set `config.DATABASE_URL = _with_db(config.DATABASE_URL, args.db)`, then call `engine.reset_engine()` before the first store read. The URL is never printed or logged.
- `_trades()` returns `TradeLog().get_trades(status="all", limit=None)`.
- `_frames(tickers)` maps each distinct ticker of `closed_shorts(trades)` to `get_daily_data(ticker, period="5y")`. A ticker that raises maps to `None` and logs `log.warning("%s: no daily bars (%s)", ticker, exc)`.
- Call `resize_closed_shorts(...)`.
- Print one `measure: value` line per Result-table row to stdout, and write `render_markdown(...)` to `--out` when given (UTF-8).
- Return 0.

`_trades` and `_frames` are separate functions, so no test touches the DB or the network.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_short_gap_sizing_impact.py`
Expected: `13 passed`, `0 failed`, `0 xfailed`.

Then run the complexity gate: `python scripts/dev/complexity_gate.py`.
Expected: exit 0, and no function of `short_gap_sizing_impact.py` reported.

- [ ] **Step 5: Commit the script and its tests**

```bash
git add scripts/reports/short_gap_sizing_impact.py tests/scripts/test_short_gap_sizing_impact.py
git commit -m "feat(v183): short gap-sizing impact report -- closed shorts re-sized at fixed risk, read-only

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Replicate production and run the report**

Run `/replicate-prod-db` (default target `swingbot_prod_replica`; production is only read, through `scripts/ops/ssh-hetzner.sh`).
Expected: a `replicate_prod_db: MATCH|DRIFT target=swingbot_prod_replica ...` line.
- On `MISMATCH`, stop and report the printed lines; do not run the report on a bad copy.
- If the replica's `alembic=` is behind `python -m alembic heads`, migrate the replica only (skill Step 4). This plan adds no revision, so a behind replica means production is behind `main`, not this branch.

From the worktree root:

```bash
RUN_DATE="$(date -u +%Y-%m-%d)"
python scripts/reports/short_gap_sizing_impact.py --db swingbot_prod_replica \
  --out "docs/superpowers/results/${RUN_DATE}-v183-gap-sizing-impact.md"
```

Expected: exit 0, summary lines on stdout (no URL, no `.env` value), and the doc written.

`Analysed` should be close to the spec's figure of 265 analysable closed shorts out of 333 (2026-10-21), plus whatever the book has added since. A count far below that, or most rows showing `none`, means the bar cache is cold. In that case, run `python scripts/data/fetch_backtest_data.py` once, then re-run the command. Never edit the numbers by hand.

- [ ] **Step 7: Check the doc, then commit it**

Open the written file and confirm:
- every section from Step 3 is present;
- the Result table shows numbers, not `n/a` (unless the book really has no closed shorts);
- it contains no secret.

Do not add a verdict or a threshold. Any interpretation goes in the task's report to the controller, not in the doc.

```bash
git add "docs/superpowers/results/${RUN_DATE}-v183-gap-sizing-impact.md"
git commit -m "results(v183): gap-sizing impact on the live book's closed shorts -- descriptive, not a gate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V183-17: Version bump, full suite, merge

**Model:** sonnet — release mechanics with fixed commands and one judgement call (stopping on a conflict or a red suite); no product code.

This task is the plan's single full-suite run, then the release, the merge to `main` and `/close-out`. The order matters, and nothing is skipped or reordered:
1. Sync `main` into the branch.
2. Run the full suite.
3. Bump the versions.
4. Merge.
5. Close out.

No full suite runs after the merge (CLAUDE.md).

**Files:**
- Modify: `VERSION.json` (the `bot` and `ui` lines and their `*_updated` stamps)
- Modify: `swingbot/admin/version_history.json` (regenerated by `scripts/dev/build_version_matrix.py`, never hand-edited)
- Moves at close-out (done by `/close-out`, listed so the reviewer expects them):
  - The plan files → `docs/superpowers/plans/implemented/`: `_0-index`, `_1-gap-sizing-core`, `_2-paper-book-display-and-risk-view`, `_3-squeeze-event-notice` and this `_4` part.
  - The spec → `docs/superpowers/specs/implemented/`.

**Interfaces:**
- Consumes: every commit of V183-1..V183-16 on branch `2026-10-21-v183-short-gap-sizing-and-squeeze-notice`, including the results doc from V183-16.
- Produces: the merged branch on `main`, with four release commits (`release(bot)`, `chore(bot)`, `release(ui)`, `chore(ui)`), and the close-out commits.

Paths: `WT=.claude/worktrees/2026-10-21-v183-short-gap-sizing-and-squeeze-notice`, `BR=2026-10-21-v183-short-gap-sizing-and-squeeze-notice`. `MAIN` is the main tree (`E:/Documents/Private/Projects/Discord-Bot`). Run every command in this task with `git -C` / absolute paths, never by `cd`-ing between trees.

- [ ] **Step 1: Check the branch is complete and the main tree untouched**

```bash
git -C "$WT" status --short                 # expected: empty
git -C "$WT" log --oneline main..HEAD       # expected: the V183-1..V183-16 commits, ending with the results(v183) commit
ls "$WT"/docs/superpowers/results/*-v183-gap-sizing-impact.md   # expected: exactly one file
git -C "$MAIN" status --short -- swingbot scripts tests frontend VERSION.json   # expected: no v183 path
```

If the main tree shows a v183 path (a subagent edited the wrong tree), stop. Compare that diff with the branch's commit for the same file. Revert it in the main tree only if it matches, and report it.

- [ ] **Step 2: Bring `main` into the branch, so the suite runs on what will merge**

```bash
git -C "$WT" rev-list --count HEAD..main    # commits on main the branch lacks
```

If the count is 0, go to Step 3.

Otherwise, run `git -C "$WT" merge --no-edit main` (message `merge: main into v183 before release`, matching the `3594dc56` precedent).
- On a conflict, stop. Run `git -C "$WT" merge --abort` and report the conflicting paths: another session's work is involved (`worktree-lifecycle` Step 3), and the partner decides.
- Never resolve a conflict in a v182 file.

- [ ] **Step 3: Run the full suite once, through `test-runner`**

Dispatch the `test-runner` agent with this exact instruction:

> In `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v183-short-gap-sizing-and-squeeze-notice`, run `python scripts/dev/testrun.py full` and report only the verdict line, the failed/xfailed test ids if any, and the complexity-gate result.

Expected: `0 failed`, `0 xfailed`, complexity gate clean. A changed pass count is not a failure (`testing-cost.md`).

In the same step, run the whole frontend spec set once. The UI changed in V183-9 and V183-15:

```bash
cd "$WT/frontend" && npx ng test --watch=false
```

Expected: every spec passes, `0 failed`.

On any failure:
1. Fix it in the file of the task that owns the failing behaviour.
2. Re-run that test alone (`python scripts/dev/testrun.py file <test>`, or `npx ng test --watch=false --include=<spec>`).
3. Commit `fix(v183): <what> -- <why>`.

Never re-run the full suite for the fix. If a failure is in code no v183 task touched and also fails on `main`, it is pre-existing. Record its id in the task report and carry on; the plan does not fix it.

- [ ] **Step 4: Bump the versions, resolved from `VERSION.json` now**

Read `"$WT/VERSION.json"`, never this plan's numbers. After Step 2 it equals `main`'s file. The plan header says **Bump: bot minor, ui patch**:
- `bot`: `X.Y.Z` → `X.(Y+1).0`
- `ui`: `X.Y.Z` → `X.Y.(Z+1)`

At writing these were `2.14.2` → `2.15.0` and `1.33.1` → `1.33.2`. Use the values on disk.

The stamp format is `YYYY-MM-DD HH-MM-SS` in Europe/Berlin time, as in the existing file. Git Bash has no timezone data, so take it from Python:

```bash
cd "$WT" && python - bot <<'PYEOF'
import datetime, json, pathlib, sys, zoneinfo
line = sys.argv[1]
p = pathlib.Path("VERSION.json")
v = json.loads(p.read_text(encoding="utf-8"))
major, minor, patch = (int(x) for x in v[line].split("."))
v[line] = f"{major}.{minor + 1}.0" if line == "bot" else f"{major}.{minor}.{patch + 1}"
v[f"{line}_updated"] = datetime.datetime.now(zoneinfo.ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d %H-%M-%S")
p.write_text(json.dumps(v, indent=2) + "\n", encoding="utf-8")
print(line, v[line])
PYEOF
```

Expected: `bot 2.15.0` (or the next minor on disk). `git -C "$WT" diff VERSION.json` shows exactly the `bot` and `bot_updated` lines changed.

Commit `VERSION.json` alone, then regenerate the history and commit it alone (close-out Step 4 order, per line):

```bash
git -C "$WT" add VERSION.json
git -C "$WT" commit -m "release(bot): <bot version> -- short plans sized so a p99 up-gap stays inside the dollar risk, squeeze/earnings/ex-div notice on every short alert (v183)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
cd "$WT" && python scripts/dev/build_version_matrix.py
git -C "$WT" add swingbot/admin/version_history.json
git -C "$WT" commit -m "chore(bot): <bot version> -- short plans sized so a p99 up-gap stays inside the dollar risk, squeeze/earnings/ex-div notice on every short alert (v183)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Then the same three moves for `ui`: run the snippet with argument `ui` (expected `ui 1.33.2` or the next patch on disk), then regenerate, then commit:
- `release(ui): <ui version> -- plan page shows the short notice lines and the gap-risk cut in the order block, risk page shows open shorts' gap risk beside heat (v183)`
- `chore(ui): <ui version> -- <the same summary>`

Both commit messages end with the `Co-Authored-By` line.

- [ ] **Step 5: Merge into `main`**

```bash
git worktree list                                  # the v183 worktree is listed; note any other live worktree
git -C "$MAIN" branch --show-current               # expected: main
git -C "$MAIN" rev-list --count "$BR"..main        # expected: 0
```

A non-zero count means `main` moved since Step 2. Repeat Step 2 in the worktree.
- If the new `main` commits include a `VERSION.json` bump, the merge conflicts on it. Abort the merge, drop nothing, and redo Step 4 on top of `main`'s values in a new pair of commits per line, so the history stays release-then-chore.
- Re-run only the tests that the merged-in `main` commits reach: `python scripts/dev/testrun.py changed`. This is not the full suite.

Then merge from the main tree:

```bash
git -C "$MAIN" merge --no-ff "$BR" -m "merge(v183): gap-aware short sizing, squeeze/event notice on every short, impact results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "$MAIN" log --oneline -1                    # expected: the merge(v183) commit
git -C "$MAIN" rev-list --count main.."$BR"        # expected: 0
```

If the merge stops on a conflict in the main tree, run `git -C "$MAIN" merge --abort` and report it; do not resolve it there. Do not run the full suite after the merge. Deploying to production is not part of this plan: it is a separate, partner-triggered step (`mirror-prod`).

- [ ] **Step 6: Run `/close-out`**

Invoke the `close-out` skill (standing permission, CLAUDE.md). Notes for its steps:
- **Step 2 (panel):** the spec carries `**Panel:** risk-manager, veteran-trader, staff-engineer`. Run `/panel` with those three roles over `<merge>^1...$BR`, together with the V183-16 results doc. An unresolved `BLOCKING` finding stops the close-out.
- **Steps 3–4 (bump):** the bump was already made in Step 4 of this task, and its four commits are on `main`. Confirm that `VERSION.json` on `main` shows the bumped `bot` and `ui` values and that `swingbot/admin/version_history.json` was regenerated after each. Do not bump again.
- **Step 5 (prediction):** check `Bump: bot minor, ui patch` and `Edge: none (integrity)` against what shipped. The UI changes are display only (one risk-page figure, plan-page lines), which is a patch. If the work turned out otherwise, amend the index header with one clause saying why.
- **Step 6 (move):** `git mv` the five plan files (`_0-index` and parts `_1`..`_4`) into `docs/superpowers/plans/implemented/`, and the spec into `docs/superpowers/specs/implemented/`. Nothing else builds from that spec; the near-high short veto in "What follows" is a queued screen idea, not a spec.
- **Step 7 (worktree):** confirm `git rev-list --count main..$BR` is `0`. The branch name contains no `backup` and does not start with `stable-`. Then remove the worktree and delete the branch.

Expected at the end: `git worktree list` no longer shows the v183 worktree. `git -C "$MAIN" log --oneline -8` shows the merge, the four release/chore commits and the close-out move commit.

