"""Pure metrics over closed-trade record lists -- no file I/O, no config
imports. Every function degrades gracefully on missing/malformed keys
(skip + count, never raise) per this plan's Global Constraints.

`closed` throughout this module means "a list of trade dicts, some subset
of which may be closed" -- callers are NOT required to pre-filter to
status in ("win", "loss") before calling; every function here filters
internally by whatever status/field it actually needs, so passing the
full unfiltered trades.json list is always safe (open trades simply
contribute nothing, since they lack exit_price/realized_pnl_amount)."""
from __future__ import annotations


def equity_curve(closed: list[dict], starting_balance: float) -> dict:
    """Walk realized P&L in chronological close order to build a running
    account-balance series.

    The very first point is dated at the EARLIEST `opened_at` across the
    input (not the earliest close) so the curve visually starts "before
    any trade closed" at the starting balance, rather than jumping
    straight to the first trade's post-close balance with no baseline --
    this is what makes an equity chart read as "flat, then it moves" for
    the calm period before the first close, instead of starting the
    chart already mid-move.

    Trades missing `realized_pnl_amount` (never settled -- e.g. no
    sizing snapshot at open time) are skipped from the balance walk and
    counted in `skipped_n` so a caller can show "N trades excluded from
    equity curve (unsized)" instead of silently under-counting.
    """
    if not closed:
        return {"points": [], "skipped_n": 0}

    considered = [t for t in closed if t.get("realized_pnl_amount") is not None and t.get("closed_at")]
    skipped_n = len(closed) - len(considered)
    considered.sort(key=lambda t: t["closed_at"])

    opened_dates = [t["opened_at"] for t in closed if t.get("opened_at")]
    points: list[dict] = []
    balance = float(starting_balance)

    # Determine baseline date: prefer earliest opened_at, fall back to earliest closed_at
    # if any trade in considered has a valid date (so baseline is never silently dropped)
    baseline_date = None
    if opened_dates:
        baseline_date = min(opened_dates)[:10]
    elif considered:
        baseline_date = min(considered, key=lambda t: t["closed_at"])["closed_at"][:10]

    if baseline_date:
        points.append({"date": baseline_date, "balance": round(balance, 2), "pnl": 0.0})

    for t in considered:
        pnl = float(t["realized_pnl_amount"])
        balance += pnl
        points.append({"date": t["closed_at"][:10], "balance": round(balance, 2), "pnl": round(pnl, 2)})

    return {"points": points, "skipped_n": skipped_n}


def drawdown_series(points: list[dict]) -> list[dict]:
    """Per-point drawdown as a % of the running peak balance seen so far
    (inclusive of the current point) -- the standard "how far below the
    best-ever balance am I right now" reading, always >= 0.

    Note: when the running peak is zero or negative (a degenerate edge case
    that should not occur in normal operation, since account balances should
    remain non-negative), dd_pct is reported as 0.0 rather than computed,
    since a percentage drawdown cannot be meaningfully expressed from a
    non-positive base."""
    series = []
    peak = None
    for p in points:
        bal = p["balance"]
        peak = bal if peak is None else max(peak, bal)
        dd_pct = (peak - bal) / peak * 100 if peak is not None and peak > 0 else 0.0
        series.append({"date": p["date"], "dd_pct": round(dd_pct, 4)})
    return series


def max_drawdown_pct(points: list[dict]) -> float | None:
    """Worst single-point drawdown across the whole curve. None (not 0.0)
    when there are fewer than 2 points -- a one-point "curve" has no
    meaningful drawdown to report, and 0.0 would misleadingly read as
    "verified flat" rather than "not enough data"."""
    if len(points) < 2:
        return None
    dds = [d["dd_pct"] for d in drawdown_series(points)]
    return max(dds)


def r_multiple(trade: dict) -> float | None:
    """THE single shared R-multiple computation -- every other stat in this
    module and in aggregate.py/calibration.py that needs "how many risk
    units did this trade make or lose" calls this instead of re-deriving
    it, per the Global Constraint "one definition per stat".

    r = (exit - entry) / (entry - stop_loss), sign-flipped for a bearish
    trade so a positive r always means "in the trade's favor" regardless
    of direction. None when any of entry/stop_loss/exit_price is missing,
    direction is not exactly "bullish" or "bearish", or when the stop
    distance is exactly 0 (a malformed record -- dividing by zero risk is
    meaningless, not infinite).
    """
    entry = trade.get("entry")
    stop = trade.get("stop_loss")
    exit_price = trade.get("exit_price")
    if entry is None or stop is None or exit_price is None:
        return None
    direction = trade.get("direction")
    if direction not in ("bullish", "bearish"):
        return None
    risk = abs(entry - stop)
    if risk == 0:
        return None
    is_bull = direction == "bullish"
    raw = (exit_price - entry) if is_bull else (entry - exit_price)
    return raw / risk


def win_rate(closed: list[dict]) -> float | None:
    """wins / (wins + losses) * 100, over trades with status "win"/"loss"
    only -- scratches, timeouts, and manual "closed" exits are excluded
    from both numerator and denominator (see the plan's Global Constraint
    for why: a manual close has no real win/loss verdict to count).
    None when there are zero win/loss trades, not 0.0 -- "no data yet" and
    "0% win rate" must never look the same on a UI.
    """
    wins = sum(1 for t in closed if t.get("status") == "win")
    losses = sum(1 for t in closed if t.get("status") == "loss")
    total = wins + losses
    return (wins / total * 100) if total else None


def expectancy_r(closed: list[dict]) -> float | None:
    """Mean r_multiple() over every trade with a computable R -- i.e. every
    trade for which r_multiple() doesn't return None, regardless of its
    status label. This intentionally includes any future "scratch"/
    "timeout" statuses the v2 exit engine may introduce to live trades
    (they still have a real entry/stop/exit_price and a real R), and
    excludes anything still open or missing fields, without needing a
    parallel status whitelist to stay in sync with r_multiple()'s own
    guard clauses.
    """
    rs = [r for t in closed if (r := r_multiple(t)) is not None]
    return (sum(rs) / len(rs)) if rs else None


def profit_factor(closed: list[dict]) -> float | None:
    """Gross realized profit / |gross realized loss|, over `realized_pnl_amount`
    (the actual currency P&L, not the R-multiple) -- the standard "how many
    dollars won per dollar lost" summary. None when there is no losing
    amount to divide by (this is mathematically infinite, not undefined,
    but reporting None/"n/a" instead of infinity keeps every consumer's
    formatting code simple, and is unambiguous: "no losses yet" is a very
    different message than a huge finite number).
    """
    amounts = [t.get("realized_pnl_amount") for t in closed if t.get("realized_pnl_amount") is not None]
    gross_win = sum(a for a in amounts if a > 0)
    gross_loss = abs(sum(a for a in amounts if a < 0))
    if gross_loss == 0:
        return None
    return gross_win / gross_loss
