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

from datetime import datetime

import numpy as np


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


def streaks(closed: list[dict]) -> dict:
    """Current/best/worst consecutive win or loss run, over win/loss trades
    only, ordered by `closed_at`. Any other status (scratch/timeout/manual
    "closed") is a hard break: it ends whatever streak was running, but is
    never itself counted toward a streak of its own length -- so a
    win/CLOSED/win sequence is two separate 1-trade win streaks, not a
    3-trade streak with a hole in it.

    Trades without a `closed_at` value are skipped entirely before sorting --
    since they have no chronological position, they are excluded from streak
    computation rather than fabricating a position for them.
    """
    # Filter to only trades with a closed_at timestamp before sorting
    # (trades without closed_at have no chronological position, so skip them)
    ordered = sorted([t for t in closed if t.get("closed_at")], key=lambda t: t["closed_at"])
    best_win = worst_loss = current = 0
    current_kind: str | None = None

    for t in ordered:
        status = t.get("status")
        if status not in ("win", "loss"):
            current = 0
            current_kind = None
            continue
        if status == current_kind:
            current += 1
        else:
            current = 1
            current_kind = status
        if status == "win":
            best_win = max(best_win, current)
        else:
            worst_loss = max(worst_loss, current)

    return {"current": current, "current_kind": current_kind,
            "best_win_streak": best_win, "worst_loss_streak": worst_loss}


def r_multiples(closed: list[dict]) -> list[float]:
    """Every computable R-multiple across the input, in whatever order
    `closed` was given -- the raw list a histogram/decile chart bins
    directly. Trades r_multiple() can't compute (missing fields, zero
    risk) are silently skipped, not zero-filled -- a skipped trade should
    not look like a breakeven trade in a histogram."""
    return [r for t in closed if (r := r_multiple(t)) is not None]


def rolling_win_rate(closed: list[dict], window: int = 20) -> list[dict]:
    """Trailing win rate, one point per win/loss close, computed over the
    most recent `window` win/loss trades up to and including that point.

    Emission starts only once at least 5 win/loss trades have accumulated
    (a rolling window over 1-4 trades is nearly pure noise and would make
    an early chart look far more volatile than the track record actually
    is) -- this floor is independent of `window` itself, so `window=4`
    with exactly 6 trades still only emits points 5 and 6, each looking
    back over the last 4.

    Trades without a `closed_at` value are skipped entirely before sorting --
    since they have no chronological position, they are excluded from rolling
    win-rate computation rather than fabricating a position for them.
    """
    # Filter to only win/loss trades with a closed_at timestamp before sorting
    # (trades without closed_at have no chronological position, so skip them)
    wl = sorted([t for t in closed if t.get("status") in ("win", "loss") and t.get("closed_at")],
                key=lambda t: t["closed_at"])
    points = []
    for i in range(len(wl)):
        if i + 1 < 5:
            continue
        window_slice = wl[max(0, i + 1 - window):i + 1]
        wins = sum(1 for t in window_slice if t["status"] == "win")
        wr = wins / len(window_slice) * 100
        points.append({"date": wl[i]["closed_at"][:10], "win_rate": round(wr, 2)})
    return points


MIN_TRADES_FOR_RATIO = 5  # below this, sample noise dominates any Sharpe/Sortino reading


def trade_return_pct(trade: dict) -> float | None:
    """Signed %% return for one closed trade -- mirrors
    risk_metrics._trade_return_pct exactly (same formula, same sign
    convention) so this module's native Sharpe/Sortino and risk_metrics.py's
    optional quantstats-backed ones can never quietly disagree. Returns
    None (rather than raising) when entry/exit_price is missing or entry
    is 0, unlike risk_metrics._trade_return_pct which assumes valid input --
    this copy is the safe-to-call-on-anything version.
    """
    entry = trade.get("entry")
    exit_price = trade.get("exit_price")
    if not entry or exit_price is None:
        return None
    pct = (exit_price - entry) / entry * 100
    return -pct if trade.get("direction") == "bearish" else pct


def sharpe(returns: list[float]) -> float | None:
    """Unannualized per-trade Sharpe: mean(returns) / std(returns, ddof=1).
    None below MIN_TRADES_FOR_RATIO trades or when std is 0 (a dead-flat
    return series has an undefined Sharpe, not an infinite one)."""
    if len(returns) < MIN_TRADES_FOR_RATIO:
        return None
    arr = np.asarray(returns, dtype=float)
    std = float(np.std(arr, ddof=1))
    if std == 0:
        return None
    return float(np.mean(arr)) / std


def sortino(returns: list[float]) -> float | None:
    """Unannualized per-trade Sortino: mean(returns) / downside_deviation,
    where downside_deviation is the population RMS of min(r, 0) across
    ALL returns (positive returns contribute 0 to the sum, per the
    standard Sortino definition -- this is deliberately NOT the std of
    only the negative returns, which would be a different, smaller-sample
    statistic). None below MIN_TRADES_FOR_RATIO trades, or when there is
    no downside at all (every return >= 0 -> downside deviation 0 ->
    undefined ratio, not infinite).
    """
    if len(returns) < MIN_TRADES_FOR_RATIO:
        return None
    arr = np.asarray(returns, dtype=float)
    downside = np.minimum(arr, 0.0)
    downside_std = float(np.sqrt(np.mean(np.square(downside))))
    if downside_std == 0:
        return None
    return float(np.mean(arr)) / downside_std


# ---------------------------------------------------------------------------
# SR54 -- the figures stats.html used to derive in browser JS.
#
# These moved server-side so there stays exactly one definition per stat (the
# same Global Constraint that makes aggregate.py delegate every ratio here).
# Note what is deliberately NOT here: a second Sharpe. stats.html annualised
# its ratios inline; `sharpe`/`sortino` above stay per-trade and unannualised,
# and `annualisation_factor` below is the separate, reusable multiplier.
# ---------------------------------------------------------------------------

_TRADING_DAYS_PER_YEAR = 252
_MIN_HOLD_DAYS = 0.5  # an intraday round trip must not send the factor to infinity
_HOLDING_BUCKETS = (("0-2d", 0.0, 2.0), ("3-7d", 2.0, 7.0),
                    ("8-30d", 7.0, 30.0), ("31d+", 30.0, float("inf")))


def _parse(ts):
    """ISO timestamp -> datetime, or None. Accepts both the bare `YYYY-MM-DD`
    the fixtures use and the full timestamps the trade log actually writes."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _holding_days(trade: dict) -> float | None:
    """Calendar days held. Calendar, not trading, days -- it is the input to
    `pct_in_market`, which is a question about wall-clock exposure."""
    opened, closed_at = _parse(trade.get("opened_at")), _parse(trade.get("closed_at"))
    if opened is None or closed_at is None:
        return None
    return (closed_at - opened).total_seconds() / 86400


def _closed_in_order(closed: list[dict]) -> list[dict]:
    """Trades that actually closed, oldest close first -- the order every
    compounding walk below depends on. Sorting inside each function rather
    than trusting the caller is deliberate: `trades.json` is append-ordered by
    OPEN time, so a long trade opened early can close after a short one
    opened later, and walking them in file order silently mis-compounds."""
    return sorted((t for t in closed if t.get("closed_at")),
                  key=lambda t: t["closed_at"])


def _returns(closed: list[dict]) -> list[float]:
    """Per-trade signed % returns, in close order, skipping anything unpriced."""
    out = []
    for t in _closed_in_order(closed):
        pct = trade_return_pct(t)
        if pct is not None:
            out.append(pct)
    return out


def _compound(returns: list[float]) -> float:
    """Chain % returns multiplicatively and report the result as a %.

    Compounding, not summing: three +10% trades make +33.1%, not +30%. The
    template summed in one place and compounded in another, which is exactly
    the drift that having one function for it prevents.
    """
    factor = 1.0
    for r in returns:
        factor *= (1.0 + r / 100.0)
    return (factor - 1.0) * 100.0


def in_date_range(closed: list[dict], *, start: str | None = None,
                  end: str | None = None) -> list[dict]:
    """Scope a trade list to a closing-date window, both bounds INCLUSIVE.

    Scoped on `closed_at`, not `opened_at`: every figure built on top of this
    is about realised results, and a trade belongs to the window in which it
    resolved. With neither bound set the input is returned untouched (open
    trades included) so callers can pass it unconditionally; with a bound set,
    undated and still-open records drop out, since they have no close to place.
    """
    if start is None and end is None:
        return closed
    out = []
    for t in closed:
        day = (t.get("closed_at") or "")[:10]
        if not day:
            continue
        if start and day < start:
            continue
        if end and day > end:
            continue
        out.append(t)
    return out


def avg_win_pct(closed: list[dict]) -> float | None:
    """Mean % return across winners. None (not 0.0) when there are none."""
    wins = [w for w in (trade_return_pct(t) for t in closed
                        if t.get("status") == "win") if w is not None]
    return round(sum(wins) / len(wins), 4) if wins else None


def avg_loss_pct(closed: list[dict]) -> float | None:
    """Mean % return across losers, left NEGATIVE.

    Kept signed on purpose: a card reading "avg loss -7.5%" cannot be misread,
    whereas a positive 7.5 next to a positive avg win invites exactly that.
    """
    losses = [x for x in (trade_return_pct(t) for t in closed
                          if t.get("status") == "loss") if x is not None]
    return round(sum(losses) / len(losses), 4) if losses else None


def span_years(closed: list[dict]) -> float | None:
    """Years from the earliest open to the latest close, floored at one day.

    The floor is what keeps `annualised_return_pct` finite for a window whose
    trades all opened and closed the same day; without it the exponent is a
    division by zero rather than a very large number.
    """
    ordered = _closed_in_order(closed)
    if not ordered:
        return None
    last = _parse(ordered[-1]["closed_at"])
    if last is None:
        return None
    opens = [d for d in (_parse(t.get("opened_at")) for t in ordered) if d]
    first = min(opens) if opens else last
    days = (last - first).total_seconds() / 86400
    return max(days / 365.25, 1 / 365)


def total_return_pct(closed: list[dict]) -> float | None:
    """Compounded % return across the window. None on an empty window."""
    returns = _returns(closed)
    return round(_compound(returns), 4) if returns else None


def annualised_return_pct(closed: list[dict]) -> float | None:
    """Total return re-expressed as a yearly rate: (1+total)^(1/years) - 1.

    Deliberately NOT clamped. A +10% fortnight really does annualise to a
    number in the thousands, and clamping it would hide how little a short
    window says -- the honest fix is showing the window length beside it,
    which is why the endpoint returns `span_years` too.
    """
    total = total_return_pct(closed)
    years = span_years(closed)
    if total is None or years is None:
        return None
    growth = 1.0 + total / 100.0
    if growth <= 0:
        return -100.0   # account wiped out; the root of a non-positive number is not a rate
    return round((growth ** (1.0 / years) - 1.0) * 100.0, 4)


def annualisation_factor(closed: list[dict]) -> float:
    """sqrt(trading days per year / average holding days).

    The multiplier that turns this module's per-trade `sharpe`/`sortino` into
    annualised ones. It is a separate function precisely so those two keep a
    single definition each -- stats.html folded this into its own Sharpe
    expression, which is how the client and server drifted apart.

    1.0 when no holding period is knowable: an unknown factor must leave the
    ratio it multiplies unchanged rather than scaling it by a guess.
    """
    holds = [h for h in (_holding_days(t) for t in closed) if h is not None]
    if not holds:
        return 1.0
    avg = max(sum(holds) / len(holds), _MIN_HOLD_DAYS)
    return (_TRADING_DAYS_PER_YEAR / avg) ** 0.5


def volatility_ann_pct(closed: list[dict]) -> float | None:
    """Annualised standard deviation of per-trade returns. None below two
    trades, where a sample standard deviation is undefined rather than 0."""
    returns = _returns(closed)
    if len(returns) < 2:
        return None
    arr = np.asarray(returns, dtype=float)
    return round(float(np.std(arr, ddof=1)) * annualisation_factor(closed), 4)


def _equity_points(closed: list[dict]) -> list[dict]:
    """The compounded equity walk on a base of 100, with a flat baseline point
    dated at the first open -- the same shape `drawdown_series` consumes, so
    drawdown keeps one implementation rather than gaining a second one here."""
    ordered = _closed_in_order(closed)
    if not ordered:
        return []
    opens = [d for d in (_parse(t.get("opened_at")) for t in ordered) if d]
    first = min(opens).date().isoformat() if opens else ordered[0]["closed_at"][:10]
    points = [{"date": first, "balance": 100.0}]
    balance = 100.0
    for t in ordered:
        pct = trade_return_pct(t)
        if pct is None:
            continue
        balance *= (1.0 + pct / 100.0)
        points.append({"date": t["closed_at"][:10], "balance": round(balance, 6)})
    return points


def calmar(closed: list[dict]) -> float | None:
    """Annualised return / maximum drawdown.

    None when the curve never drew down: dividing by a zero drawdown is
    undefined, and reporting a huge number for "never lost" would rank a
    two-trade sample above a real track record.
    """
    ann = annualised_return_pct(closed)
    if ann is None:
        return None
    max_dd = max_drawdown_pct(_equity_points(closed))
    if not max_dd:          # None (too few points) or 0.0 (no drawdown at all)
        return None
    return round(ann / abs(max_dd), 4)


def trades_per_month(closed: list[dict]) -> float | None:
    """Closed trades per month over the window. None on an empty window."""
    ordered = _closed_in_order(closed)
    years = span_years(closed)
    if not ordered or years is None:
        return None
    return round(len(ordered) / max(years * 12, 1.0), 4)


def pct_in_market(closed: list[dict]) -> float | None:
    """Share of the window spent holding something, capped at 100%.

    Approximate by construction: it sums holding periods, so concurrent
    positions double-count and push it up. The cap is what keeps that
    readable rather than absurd -- a portfolio running three positions at
    once reports "100% in market", which is true, instead of "300%".
    """
    ordered = _closed_in_order(closed)
    if not ordered:
        return None
    last = _parse(ordered[-1]["closed_at"])
    opens = [d for d in (_parse(t.get("opened_at")) for t in ordered) if d]
    if last is None or not opens:
        return None
    span_days = (last - min(opens)).total_seconds() / 86400
    if span_days <= 0:
        return 100.0
    held = sum(h for h in (_holding_days(t) for t in ordered) if h is not None)
    return round(min(held / span_days * 100.0, 100.0), 4)


def histogram(values: list[float], *, bins: int = 20) -> list[dict]:
    """Equal-width buckets spanning [min, max], as `{lo, hi, count}` rows.

    Empty interior buckets are KEPT. A histogram that drops them silently
    redraws its own x-axis and turns a bimodal distribution into a flat one.
    An empty input is an empty list, not `bins` zero-count rows -- "no data"
    and "all buckets empty" are different statements.
    """
    if not values or bins < 1:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        # Degenerate range: one bucket holding everything beats dividing by 0.
        return [{"lo": round(lo, 6), "hi": round(hi, 6), "count": len(values)}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        counts[min(int((v - lo) / width), bins - 1)] += 1   # top edge -> last bucket
    return [{"lo": round(lo + i * width, 6), "hi": round(lo + (i + 1) * width, 6),
             "count": c} for i, c in enumerate(counts)]


def rolling_return_pct(closed: list[dict], window: int = 20) -> list[dict]:
    """Compounded return over each trailing `window` of closed trades.

    Trade-indexed, not calendar-indexed, matching `rolling_win_rate` above so
    the two can be plotted on one axis. Empty when the window is longer than
    the sample -- a partial window is a different statistic, not this one.
    """
    ordered = [t for t in _closed_in_order(closed) if trade_return_pct(t) is not None]
    if window < 1 or len(ordered) < window:
        return []
    returns = [trade_return_pct(t) for t in ordered]
    return [{"date": ordered[i]["closed_at"][:10],
             "return_pct": round(_compound(returns[i - window + 1:i + 1]), 4)}
            for i in range(window - 1, len(ordered))]


def holding_period_split(closed: list[dict]) -> list[dict]:
    """Trades bucketed by days held, each bucket carrying its own win rate.

    Every bucket is reported even at n=0, because the shape of the answer is
    the point: "the edge is all in the 8-30d band" is only legible next to the
    bands that are empty. `win_rate` is None for an empty bucket, never 0.
    """
    if not closed:
        return []
    out = []
    for name, lo, hi in _HOLDING_BUCKETS:
        members = []
        for t in closed:
            held = _holding_days(t)
            if held is not None and lo <= held <= hi:
                members.append(t)
        rets = [r for r in (trade_return_pct(t) for t in members) if r is not None]
        out.append({"bucket": name, "n": len(members),
                    "win_rate": win_rate(members),
                    "avg_return_pct": round(sum(rets) / len(rets), 4) if rets else None})
    return out


def calendar_returns(closed: list[dict]) -> list[dict]:
    """Compounded return per calendar month of close, oldest first.

    Months with no closes are OMITTED rather than emitted as 0.0 -- a flat
    month and a month you did not trade are different facts, and a calendar
    heatmap that paints them identically is lying about activity.
    """
    by_month: dict[str, list[dict]] = {}
    for t in _closed_in_order(closed):
        if trade_return_pct(t) is None:
            continue
        by_month.setdefault(t["closed_at"][:7], []).append(t)
    return [{"month": m,
             "return_pct": round(_compound([trade_return_pct(t) for t in ts]), 4),
             "n": len(ts)}
            for m, ts in sorted(by_month.items())]


def cumulative_pnl_by_strategy(closed: list[dict]) -> dict[str, list[dict]]:
    """Per-strategy compounded equity walks, `{strategy: [{date, cum_pct}]}`.

    Each strategy is walked on its OWN sequence rather than sliced out of the
    portfolio curve, so a strategy that traded twice in 2020 and twice in 2024
    shows two steps, not a line dragged flat across the gap between them.
    """
    by_strategy: dict[str, list[dict]] = {}
    for t in _closed_in_order(closed):
        if trade_return_pct(t) is None:
            continue
        by_strategy.setdefault(t.get("strategy") or "unknown", []).append(t)
    out: dict[str, list[dict]] = {}
    for name, ts in by_strategy.items():
        factor, points = 1.0, []
        for t in ts:
            factor *= (1.0 + trade_return_pct(t) / 100.0)
            points.append({"date": t["closed_at"][:10],
                           "cum_pct": round((factor - 1.0) * 100.0, 4)})
        out[name] = points
    return out
