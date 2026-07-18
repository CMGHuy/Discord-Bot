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
