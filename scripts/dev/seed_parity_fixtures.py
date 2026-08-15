"""Seed this checkout's `data/` with synthetic fixtures for the NG54 walk.

Spec v15 Decision 2b asks for every control to be exercised against a running
pair of UIs, and its list includes clearing open trades, clearing history and
the killswitch. Those must not be walked against real data, so the walk runs
against fixtures built here instead.

**This writes into `config.DATA_DIR`, which is derived from the checkout root**
(`config.py` builds it from `_PROJECT_ROOT`; it is deliberately not
env-driven). Run from the `angular-migration` worktree and it writes the
worktree's own `data/`, which is a different directory from the main
checkout's. It refuses to run anywhere that looks like a real install -- see
`_refuse_if_real` -- because the whole point is that the destructive half of
the walk is safe.

The fixture set is built around the ONE thing that makes this data model
awkward, which the walk has to be able to see: plans.json and trades.json
overlap. A filled plan stays in plans.json as ACTIVE while a linked row is
written to trades.json, and the trades list joins rather than concatenates.
So the set deliberately contains a filled plan *and* its linked trade, and a
legacy trade belonging to no plan at all -- if the join ever regresses to a
concatenation, the walk sees a duplicate row rather than a passing test.

Every id is a fixed literal, not generated: re-running must produce byte-identical
files, or the CSV byte-compare in 2b compares two different things.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402  (needs the path above)
# The real horizon keys. Imported rather than written out: the first version
# of this file invented "1m", "3w" and "6w", which are not horizons at all, so
# the Analytics heatmap silently had nothing to draw. A fixture using keys the
# product does not know produces a plausible-looking screen that proves
# nothing.
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402

# --- ids ------------------------------------------------------------------
# Plan ids are UUID4-shaped because trade_commands.py routes a note by
# guessing plan-vs-trade from the id's shape (`_looks_like_a_plan_id`). A
# plan with a non-UUID id would take the legacy branch and behave unlike
# production for reasons that have nothing to do with the UI being walked.
P_PENDING = "11111111-1111-4111-8111-111111111111"
P_ACTIVE = "22222222-2222-4222-8222-222222222222"
P_PARTIAL = "33333333-3333-4333-8333-333333333333"
P_CANCELLED = "44444444-4444-4444-8444-444444444444"
P_CLOSED = "55555555-5555-4555-8555-555555555555"

T_ACTIVE = "trade-active-0001"      # linked to P_ACTIVE
T_PARTIAL = "trade-partial-0001"    # linked to P_PARTIAL
T_CLOSED = "trade-closed-0001"      # linked to P_CLOSED, a win
T_LEGACY_OPEN = "trade-legacy-open-0001"
T_LEGACY_LOSS = "trade-legacy-loss-0001"


def _plan(plan_id, *, ticker, status, strategy, horizon="4w", direction="bullish",
          tier="A", badge="VALIDATED", quality=72, legs=()):
    return {
        "plan_id": plan_id, "ticker": ticker,
        "created_at": "2026-08-01T10:00:00+00:00",
        "source": "strategy", "strategy": strategy, "horizon_key": horizon,
        "direction": direction, "entry_type": "stop_entry",
        "trigger_price": 100.0, "entry_price": 101.0, "expiry_bars": 5,
        "stop_loss": 95.0, "tp1": 110.0, "tp1_fraction": 0.5, "tp2": 120.0,
        "breakeven_trigger_fraction": 0.5, "trail_atr_mult": 1.5,
        "quality_score": quality, "quality_breakdown": [], "tier": tier,
        "badge": badge, "badge_stats": {}, "status": status,
        "status_history": [], "legs_realized": list(legs),
    }


def _trade(trade_id, *, plan_id, ticker, status, strategy, horizon="4w",
           direction="bullish", tier="A", badge="VALIDATED", quality=72,
           entry=101.0, stop=95.0, tp=110.0, exit_price=None, pnl=None,
           shares=10, closed_at=None):
    return {
        "id": trade_id, "plan_id": plan_id, "ticker": ticker,
        "strategy": strategy, "horizon_key": horizon, "direction": direction,
        "confidence_level": 4, "confidence_label": "High",
        "confidence_score": 81.0, "entry": entry, "stop_loss": stop,
        "take_profit": tp, "target2": 120.0, "risk_reward_ratio": 1.8,
        "tier": tier, "badge": badge, "quality_score": quality,
        "source": "strategy", "legs": [],
        "opened_at": "2026-08-01T10:00:00+00:00", "status": status,
        "closed_at": closed_at, "exit_price": exit_price,
        "realized_pnl_amount": pnl, "shares": shares,
        "position_value": round(entry * shares, 2),
        "target_sources": [], "stop_sources": [], "target2_sources": [],
        "confirmed_by": [], "explanation": None, "confidence_breakdown": None,
    }


def _journal(trade_id, *, ticker, strategy, outcome, r_realized, note,
             closed_at, tier="A", badge="VALIDATED"):
    return {
        "trade_id": trade_id, "ticker": ticker, "strategy": strategy,
        "horizon_key": "4w", "direction": "bullish", "tier": tier,
        "badge": badge, "quality_score": 72, "outcome": outcome,
        "r_realized": r_realized, "mfe_r": 1.9, "mae_r": -0.4,
        "exit_efficiency": 0.74, "holding_days": 3,
        "tags": ["clean-entry"], "auto_lesson": None, "note": note,
        "opened_at": "2026-08-01T10:00:00+00:00", "closed_at": closed_at,
    }


_HORIZON_KEYS = list(HORIZONS)

PLANS = [
    _plan(P_PENDING, ticker="AAPL", status="PENDING", strategy="RSI Divergence"),
    _plan(P_ACTIVE, ticker="MSFT", status="ACTIVE", strategy="MACD Cross",
          horizon="2m", tier="B"),
    # PARTIAL is the state most likely to render wrong, because it is the only
    # one carrying a realized leg while still being an open position.
    _plan(P_PARTIAL, ticker="NVDA", status="PARTIAL", strategy="Breakout",
          horizon="4w", tier="A",
          legs=[{"leg": "tp1", "price": 110.0, "fraction": 0.5,
                 "realized_at": "2026-08-05T14:30:00+00:00", "r_multiple": 1.5}]),
    _plan(P_CANCELLED, ticker="TSLA", status="CANCELLED", strategy="RSI Divergence",
          horizon="2w", tier="C", badge="UNPROVEN", quality=41),
    _plan(P_CLOSED, ticker="AMD", status="CLOSED", strategy="MACD Cross",
          horizon="4w", tier="A"),
]

TRADES = [
    _trade(T_ACTIVE, plan_id=P_ACTIVE, ticker="MSFT", status="open",
           strategy="MACD Cross", horizon="2m", tier="B", entry=402.5,
           stop=388.0, tp=430.0, shares=6),
    _trade(T_PARTIAL, plan_id=P_PARTIAL, ticker="NVDA", status="open",
           strategy="Breakout", horizon="4w", entry=118.2, stop=110.0,
           tp=135.0, shares=25),
    _trade(T_CLOSED, plan_id=P_CLOSED, ticker="AMD", status="win",
           strategy="MACD Cross", entry=142.0, stop=134.0, tp=158.0,
           exit_price=156.4, pnl=143.99, shares=10,
           closed_at="2026-08-08T15:00:00+00:00"),
    # No plan_id: the legacy shape that lives only in trades.json. The join
    # has to pick these up separately, and their status vocabulary differs
    # (open/win/loss rather than the plan statuses).
    _trade(T_LEGACY_OPEN, plan_id=None, ticker="SPY", status="open",
           strategy="Support Bounce", horizon="3m", tier=None, badge=None,
           entry=548.1, stop=536.0, tp=572.0, shares=4),
    _trade(T_LEGACY_LOSS, plan_id=None, ticker="COIN", status="loss",
           strategy="Breakout", horizon="2w", tier="C", badge="UNPROVEN",
           quality=38, entry=210.0, stop=198.0, tp=240.0,
           exit_price=197.4, pnl=-126.0, shares=10,  # noqa: E128
           closed_at="2026-08-06T19:45:00+00:00"),
]

# --- status-bar spectrum --------------------------------------------------
# The QA walk (SR19) has to see a position near its target, near its stop, and
# sitting at entry. Synthetic levels cannot produce those: the bar is computed
# against the LIVE price, and a plan priced at 101 against a real quote of 493
# clamps to 100% every time -- which is correct, and shows nothing.
#
# So these levels are derived FROM the live price at seed time. It costs one
# network call per ticker and makes the walk show the four states it is
# supposed to check rather than four identical full bars.
def _spectrum_plans():
    try:
        from swingbot.core.marketdata.data import get_current_price
    except Exception:
        return [], []

    # (ticker, where the price should sit between stop and target)
    wanted = [("AAPL", 0.85), ("NVDA", 0.15), ("AMD", 0.50)]
    plans, trades = [], []
    for index, (ticker, position) in enumerate(wanted):
        try:
            price = get_current_price(ticker)
        except Exception:
            price = None
        if not price:
            continue
        # Place stop and target ASYMMETRICALLY around the live price so the
        # price itself lands at `position` along the span -- that is what
        # varies the BAR LENGTH. Putting them symmetrically and moving entry
        # instead (the first attempt) varies only the band, leaving three
        # identical half-full bars, which is not what the walk needs to see.
        span = price * 0.20
        stop = round(price - span * position, 2)
        target = round(price + span * (1 - position), 2)
        # Entry mid-span, so the tick sits in the middle and the bar's
        # position relative to it is the thing that reads.
        entry = round(stop + (target - stop) * 0.5, 2)
        pid = f"9{index}999999-9999-4999-8999-99999999999{index}"
        plan = _plan(pid, ticker=ticker, status="ACTIVE", strategy="Breakout",
                     horizon="4w")
        plan.update({"entry_price": entry, "stop_loss": stop, "tp1": target})
        trade = _trade(f"trade-spectrum-{index}", plan_id=pid, ticker=ticker,
                       status="open", strategy="Breakout", horizon="4w",
                       entry=entry, stop=stop, tp=target, shares=10)
        plans.append(plan)
        trades.append(trade)
    return plans, trades


_SPECTRUM_PLANS, _SPECTRUM_TRADES = _spectrum_plans()
PLANS.extend(_SPECTRUM_PLANS)
TRADES.extend(_SPECTRUM_TRADES)

# --- heatmap coverage -----------------------------------------------------
# A5 names "the heatmap at ten horizons" as one of three surfaces wider than
# the row expansion, and the heatmap is a strategy x horizon matrix built from
# CLOSED trades. The five hand-written rows above cover four cells, which
# renders a matrix too small to say anything about width. These fill it: three
# strategies across all ten horizons, alternating win/loss so no cell is
# empty and no column is uniformly one colour.
#
# Closed and legacy (plan_id=None) on purpose. They exist to give the matrix
# something to draw, and adding thirty plans to plans.json would change the
# trades-list row count that the join check above depends on.
_HEATMAP_STRATEGIES = ("RSI Divergence", "MACD Cross", "Breakout")
_HEATMAP_TICKERS = ("AAPL", "MSFT", "NVDA")

for _si, _strategy in enumerate(_HEATMAP_STRATEGIES):
    for _hi, _horizon in enumerate(_HORIZON_KEYS):
        _win = (_si + _hi) % 3 != 0        # two wins per loss, roughly
        TRADES.append(_trade(
            f"trade-heat-{_si}-{_horizon}",
            plan_id=None, ticker=_HEATMAP_TICKERS[_si], status="win" if _win else "loss",
            strategy=_strategy, horizon=_horizon,
            tier="ABC"[_si], badge="VALIDATED" if _win else "UNPROVEN",
            quality=60 + _hi, entry=100.0, stop=94.0, tp=112.0,
            exit_price=112.0 if _win else 94.0,
            pnl=120.0 if _win else -60.0, shares=10,
            closed_at=f"2026-0{7 if _hi < 5 else 8}-{(_hi % 5) * 5 + 1:02d}T15:00:00+00:00",
        ))

# Only closed trades get journal entries -- notes attach on close, which is
# what trade_commands.set_note's 404 message says. A note on the ACTIVE
# position would be a state production cannot produce.
JOURNAL = [
    _journal(T_CLOSED, ticker="AMD", strategy="MACD Cross", outcome="win",
             r_realized=1.8, closed_at="2026-08-08T15:00:00+00:00",
             note="Clean break and hold. Sized correctly for once."),
    _journal(T_LEGACY_LOSS, ticker="COIN", strategy="Breakout", outcome="loss",
             r_realized=-1.05, closed_at="2026-08-06T19:45:00+00:00",
             note="", tier="C", badge="UNPROVEN"),
]

# `ts`, not `date`. account.py reads entry["ts"] unguarded (see
# `balance_series`), so a wrongly-keyed entry is a KeyError deep inside the
# scan loop rather than a missing point on a chart. Getting this wrong is how
# the first version of this file broke five tests in test_engine_v2_plans.py
# -- which read the real DATA_DIR rather than a tmp_path, so a bad fixture
# here reached them. See spec Appendix B2.
ACCOUNT = {
    "balance": 25000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
    "sizing_mode": "risk_pct",
    "balance_history": [
        {"ts": "2026-07-01T00:00:00+00:00", "balance": 24000.0},
        {"ts": "2026-08-01T00:00:00+00:00", "balance": 24800.0},
        {"ts": "2026-08-08T00:00:00+00:00", "balance": 25000.0},
    ],
}

WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "SPY", "COIN"]

FILES = {
    "plans.json": PLANS,
    "trades.json": TRADES,
    "journal.json": JOURNAL,
    "account.json": ACCOUNT,
    "watchlist.json": WATCHLIST,
}


def _refuse_if_real(data_dir: str) -> None:
    """Bail out if this looks like a real install rather than a scratch one.

    The check is the presence of files a fixture directory has no reason to
    hold. It is not airtight -- nothing that inspects a directory can be --
    but it turns "ran it in the wrong terminal" from a data-loss event into
    an error message, which is the difference worth having.
    """
    real_markers = ("backups", "backtest_cache", "market_data_state.json")
    found = [m for m in real_markers if os.path.exists(os.path.join(data_dir, m))]
    if found:
        sys.exit(
            f"REFUSING to seed {data_dir}\n"
            f"  It holds {', '.join(found)}, which fixtures never create -- this\n"
            f"  looks like a real data directory. Run this from the\n"
            f"  angular-migration worktree, whose data/ is its own.\n"
            f"  If this really is scratch, delete those and re-run."
        )


def main() -> int:
    data_dir = config.DATA_DIR
    _refuse_if_real(data_dir)
    os.makedirs(data_dir, exist_ok=True)

    for name, payload in FILES.items():
        path = os.path.join(data_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        print(f"  wrote {name:20s} {len(payload)} record(s)", flush=True)

    heat = len(_HEATMAP_STRATEGIES) * len(_HORIZON_KEYS)
    print(f"\nSeeded {data_dir}")
    print("  5 plans   PENDING / ACTIVE / PARTIAL / CANCELLED / CLOSED")
    print(f"  {len(TRADES)} trades  3 plan-linked (2 open, 1 win) + 2 legacy "
          f"(1 open, 1 loss)")
    print(f"            + {heat} closed for the heatmap "
          f"({len(_HEATMAP_STRATEGIES)} strategies x {len(_HORIZON_KEYS)} horizons)")
    print("  2 journal entries, one with a note and one without")
    print(f"\nThe trades list should show {5 + 2 + heat} rows, not {len(TRADES) + 5}:")
    print("the three plan-linked pairs join into one row each. The higher")
    print("number means the join regressed to a concatenation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
