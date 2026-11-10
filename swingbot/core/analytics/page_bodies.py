"""v204: the request bodies of the routes the refresher snapshots.

`/analytics/performance`, `/analytics/equity-curve` and `/calendar/pnl` were
measured too slow to compute on request (docs/superpowers/results/
2026-10-29-v204-measure-first.md), so their bodies live here, where both the
Flask routes (api_v1 `analytics.py`, `calendar.py`) and the refresher's
builders (`admin_snapshots.py`) call them. The bodies moved unchanged except
that the scope, month and filters arrive as arguments, the first read can be
passed in, money is converted by `fx_convert` with
`fetch=not admin_refresh.refresher_on()` (what api_v1 `money.py` passes) and
`closed_pnl_pct` is called directly. Nothing here imports the admin package.
"""
from __future__ import annotations

import datetime as dt

from swingbot.core.marketdata import fx_convert
from swingbot.core.marketdata.shared import admin_refresh
from swingbot.core.tracking.performance import TradeLog, closed_pnl_pct

missing_count = fx_convert.missing_count


def to_account_currency(rows: list[dict]) -> list[dict]:
    """Copies of `rows` in the account currency; never fetches while the refresher is on."""
    return fx_convert.to_account_currency(rows, fetch=not admin_refresh.refresher_on())


def _all_trades(tl: TradeLog) -> list[dict]:
    """Every trade in every ledger; `scope.select` applies the ledger filter."""
    return tl.get_trades(status=None, limit=None, ledger=None) or []


def _weak_in_account_currency(weak: dict, money_closed: list[dict]) -> tuple[dict, set]:
    """`weak_summary()` with `total_pnl` re-summed from converted rows (v194 B7).

    The store sums stored quote-currency amounts; the weak ledger's rows are
    the same closes, so the overlay reads them from `money_closed`. Returns
    the block and the ids of weak rows lacking a rate (left out of the sum);
    ids, not a count, so a row also in the scoped list is counted once."""
    from swingbot.core.tracking import ledger

    rows = [t for t in money_closed
            if ledger.is_weak(t) and t.get("status") in ("win", "loss", "closed")]
    total = sum(float(t["realized_pnl_amount"]) for t in rows
                if t.get("realized_pnl_amount") is not None)
    return ({**weak, "total_pnl": round(total, 2)},
            {t.get("id") for t in rows if t.get("fx_missing")})


def _fx_missing_total(money_scoped: list[dict], weak_missing_ids: set) -> int:
    """Rows left out of a money figure for want of a rate: the scoped rows
    plus the book-wide weak block's, a row in both counted once."""
    return len({t.get("id") for t in money_scoped if t.get("fx_missing")} | weak_missing_ids)


def _given_or_read(all_raw: list[dict] | None, tl: TradeLog) -> list[dict]:
    """The caller's already-read book, else every trade in every ledger."""
    return _all_trades(tl) if all_raw is None else all_raw


def _calendar_rows(rows: list[dict] | None) -> list[dict]:
    """The caller's already-loaded calendar rows, else every row in the account currency."""
    from swingbot.core.analytics import pnl_calendar as pc
    return pc.load_rows(convert=to_account_currency) if rows is None else rows


def performance_body(scope, *, all_raw: list[dict] | None = None) -> dict:
    """Overall record, the six metrics relocated from the Dashboard, and
    (SR54) every figure `stats.html` used to derive in browser JS.

    Spec 3 accepted the cost of moving wins, losses, avg realised P&L, best
    trade, worst trade and avg holding period one click away. They have to
    actually arrive here, or that trade was a straight loss -- hence the
    explicit block below rather than dumping get_stats() wholesale.

    Every block below is computed over the `BookScope` population (spec v94
    D5) -- `?from=`/`?to=`/`ledger=`/`strategy=`/`horizon=`/`direction=` all
    reach every figure the same way, including the top-level `win_rate` and
    `expectancy_r`. Three things stay book-wide instead: `totals.total`/
    `totals.open`, because an open trade has no close to scope on; and
    `by_confidence` (`get_stats_by_confidence()`) and `weak`
    (`weak_summary()`), which are each other's own separate, never-scoped
    records, not projections of `closed`.

    `scratch_n`/`unscored_n` count the scoped `closed` rows that D2 (v189)
    labelled `closed`/`scratch` or `closed`/`unscored` -- excluded from
    `win_rate` and `win_rate_n` -- and `label_basis_since` is the date from
    which scaled-out closes are labelled by net R (None until deployed).

    Every figure is computed in `core.analytics.metrics` -- this route selects
    and assembles, it does not derive. That is the same "one definition per
    stat" rule that keeps `aggregate.py` delegating, and the reason the
    annualised Sharpe here is `sharpe() * annualisation_factor()` rather than
    a second Sharpe expression written inline.
    """
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.scope import closed_only, echo, select

    tl = TradeLog()
    all_raw = _given_or_read(all_raw, tl)
    all_closed = closed_only(all_raw)                # the real, unscoped book -- balance_at reads THIS
    closed = select(all_closed, scope)                # every other block below reads THIS list
    scoped = closed
    # v194 B7: money figures read converted copies; win rate, R and every
    # percent below keep reading the stored rows (see api_v1/money.py).
    money_closed = to_account_currency(all_closed)
    money_scoped = select(money_closed, scope)
    weak, weak_missing_ids = _weak_in_account_currency(tl.weak_summary(), money_closed)
    start, end = scope.start, scope.end
    stats = tl.get_stats(trades=all_raw)             # totals.total/open stay book-wide
    stats.update(tl.get_extended_stats(trades=all_raw))
    labels = m.label_counts(closed)
    realized = [p for p in (closed_pnl_pct(t) for t in closed) if p is not None]

    from swingbot.core.planning import account as account_module
    base_balance = float(account_module.load_account_config().get("base_balance") or 0.0)
    # There is exactly one real pooled account balance -- it has no
    # per-strategy/per-ledger/per-horizon meaning, so this reads the
    # unscoped `all_closed`, filtered only by date via balance_at's own
    # `before` cutoff, matching /analytics/equity-curve's window_balance.
    window_balance = m.balance_at(money_closed, start, base_balance)
    returns = [r for r in (m.trade_return_pct(t) for t in scoped) if r is not None]
    factor = m.annualisation_factor(scoped)
    raw_sharpe, raw_sortino = m.sharpe(returns), m.sortino(returns)

    return {
        "totals": {
            "total": stats.get("total"),
            "open": stats.get("open"),
            "closed": len(closed),
        },
        # The six spec 3 moved here from the Dashboard header.
        "relocated": {
            "wins": stats.get("wins"),
            "losses": stats.get("losses"),
            "avg_realized_pct": round(sum(realized) / len(realized), 2) if realized else None,
            "best_trade_pct": round(max(realized), 2) if realized else None,
            "worst_trade_pct": round(min(realized), 2) if realized else None,
            "avg_holding_days": stats.get("avg_holding_days"),
        },
        "win_rate": m.win_rate(closed),
        "win_rate_n": sum(1 for t in closed if t.get("status") in ("win", "loss")),
        # v189 D6 -- the closes the rate leaves out, and the date their basis
        # changed. Read through `m.` at request time: V189-27 sets the date.
        "scratch_n": labels["scratch"],
        "unscored_n": labels["unscored"],
        "label_basis_since": m.LABEL_BASIS_SINCE,
        "expectancy_r": m.expectancy_r(closed),
        "expectancy_n": len(m.r_multiples(closed)),
        "by_confidence": tl.get_stats_by_confidence(),
        "weak": weak,

        "range": {
            "from": start, "to": end,
            "span_years": (round(sy, 4) if (sy := m.span_years(scoped)) is not None else None),
            "n": len(scoped),
        },
        "derived": {
            "avg_win_pct": m.avg_win_pct(scoped),
            "avg_loss_pct": m.avg_loss_pct(scoped),
            "total_return_pct": m.total_return_pct(money_scoped, window_balance),
            "annualised_return_pct": m.annualised_return_pct(money_scoped, window_balance),
            "calmar": m.calmar(money_scoped, window_balance),
            "volatility_ann_pct": m.volatility_ann_pct(scoped),
            "trades_per_month": m.trades_per_month(scoped),
            "pct_in_market": m.pct_in_market(scoped),
            # Annualised by multiplying the module's per-trade ratio, never by
            # re-deriving one here -- see this docstring's last paragraph.
            "sharpe_ann": round(raw_sharpe * factor, 4) if raw_sharpe is not None else None,
            "sortino_ann": round(raw_sortino * factor, 4) if raw_sortino is not None else None,
            "win_rate": m.win_rate(scoped),
            "expectancy_r": m.expectancy_r(scoped),
            # v94 T1 -- the Overview tab's Profit factor tile. Unitless
            # (gross win / gross loss in currency), so it belongs beside
            # sharpe_ann/sortino_ann rather than needing its own block; the
            # Strategies by-dimension route already computes the same figure
            # this way (m.profit_factor), so this keeps "one definition per
            # stat" rather than the workspace re-deriving it from bucketed
            # histogram data it cannot do exactly.
            "profit_factor": m.profit_factor(money_scoped),
            # v94 T1 -- the Outcome panel's Avg win/Avg loss/Payoff rows.
            # The panel's own hint text ("means of the R-multiples on each
            # side") is R-based, not the P&L-percent avg_win_pct/avg_loss_pct
            # above -- those answer a different question. Same reuse
            # rationale as profit_factor: the by-dimension route already
            # computes avg_win_r/avg_loss_r this way, and payoff_r is the
            # ratio of those same two numbers (payoff_ratio_from_rs over the
            # SAME r_multiples list -- never re-derived from a different
            # population).
            "avg_win_r": m.avg_win_r(scoped),
            "avg_loss_r": m.avg_loss_r(scoped),
            "payoff_r": m.payoff_ratio(scoped),
        },
        "distributions": {
            "returns": m.histogram(returns, bins=12),
            "r_multiples": m.histogram(m.r_multiples(scoped), bins=12),
        },
        "rolling_returns": m.rolling_return_pct(scoped),
        "holding_period_split": m.holding_period_split(scoped),
        "risk_reward_split": m.risk_reward_split(scoped),
        "calendar": m.calendar_returns(money_scoped, window_balance),
        "cumulative_by_strategy": m.cumulative_pnl_by_strategy(scoped),
        # Best-effort: get_extended_stats swallows a failed yfinance fetch and
        # returns {}. The key is always present so the workspace never has to
        # distinguish "no benchmark" from "no such field".
        "benchmark": {"spy_cum": stats.get("spy_cum") or {}},
        "rolling_wr": m.rolling_win_rate(scoped, window=50),
        "rolling_exp_r": m.rolling_expectancy_r(scoped, window=50),
        # v94 T1 -- the Overview tab's Streaks row. Computed over `closed`,
        # the same BookScope-selected population as everything else on this
        # route (never the unscoped book): a streak that crossed a scope
        # boundary the user drew is not a streak the user asked to see.
        "streaks": m.streaks(closed),
        "fx_missing_count": _fx_missing_total(money_scoped, weak_missing_ids),
        **echo(scope, len(scoped)),
    }


def equity_curve_body(scope, *, all_raw: list[dict] | None = None) -> dict:
    """One point per closed trade, ordered by close date, cumulative in R,
    with a non-negative drawdown-from-running-peak series alongside it --
    the Equity | Drawdown toggle on the Analytics Performance tab reads
    both from this one fetch (spec v14 R9-01, consumed by R9-04).

    Ordered by close date, NOT by calendar day: a day with no closes is not
    a flat day on an R curve, it is a day with no observation, and
    interpolating one would invent a data point that never happened. The
    x-axis is the sequence of trades, dated.

    A point exists for every scoped closed trade -- `points_n` therefore
    always equals the echoed `n` (see below) on this route; nothing is ever
    dropped from the plot. Every R comes from `metrics.r_multiple()` -- the
    one shared R-multiple computation (see its docstring); this route does
    not re-derive it. When a trade's R is NOT computable (missing prices,
    zero risk, an unrecognised direction), its point still exists but
    carries `cum_r`/`drawdown_r` forward UNCHANGED from the previous point
    -- flat, not a 0.0 contribution folded into the running total, which
    would misrepresent an unmeasured trade as a breakeven one. `cum_pnl`/
    `cum_pct` are not gated on R at all: they walk every scoped trade's
    realised P&L regardless of whether R could be computed for it (a
    currency P&L needs no risk denominator to be measurable), so they keep
    moving on a point where `cum_r`/`drawdown_r` are flat. A trade with an
    uncomputable R is therefore visible in the money series and invisible
    (flat) in the R series, on the same point -- never missing from
    `points` outright, which is what would silently understate `as_of` and
    the account's real cumulative P&L for a run ending in such a trade.

    Scoped like `/performance` (spec v94 D5) -- `?from=`/`to=`/`ledger=`/
    `strategy=`/`horizon=`/`direction=` all reach this route via the same
    `BookScope` (`_scope()`/`select()`/`closed_only()`), not a second,
    hand-rolled filter. `n` in the echoed scope (see `scope.echo`) and
    `points_n` (`len(points)`) are the same number on this route today --
    kept as two separate keys anyway (rather than reusing `echo`'s `n` for
    both meanings) because they answer different questions ("how many
    trades are in scope" vs "how many points does this series have") that
    happen to coincide only because nothing is currently skipped from
    `points`.

    """
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.scope import closed_only, echo, select
    from swingbot.core.planning import account as account_module

    tl = TradeLog()
    all_raw = _given_or_read(all_raw, tl)
    # v194 B7: every figure here is money or R, and m.r_multiple never reads
    # the amount, so the whole route reads the converted copies.
    closed = to_account_currency(closed_only(all_raw))
    scoped = select(closed, scope)
    base_balance = float(account_module.load_account_config().get("base_balance") or 0.0)
    window_balance = m.balance_at(closed, scope.start, base_balance)

    ordered = sorted(scoped, key=lambda t: t.get("closed_at") or "")
    points = []
    cum_r = 0.0
    peak = 0.0
    cum_pnl = 0.0
    for t in ordered:
        cum_pnl += float(t.get("realized_pnl_amount") or 0.0)
        r = m.r_multiple(t)
        if r is not None:
            cum_r += r
            peak = max(peak, cum_r)
        points.append({
            "date": (t.get("closed_at") or "")[:10],
            "cum_r": round(cum_r, 4),
            "drawdown_r": round(peak - cum_r, 4),
            "cum_pnl": round(cum_pnl, 2),
            "cum_pct": round(cum_pnl / window_balance * 100, 4) if window_balance else None,
        })

    return {
        "points": points,
        "points_n": len(points),
        "as_of": points[-1]["date"] if points else None,
        "fx_missing_count": missing_count(scoped),
        **echo(scope, len(scoped)),
    }


def calendar_body(month: str, filters: tuple[str | None, str | None], *,
                  rows: list[dict] | None = None) -> dict:
    """One month's day grid, plus the full-history context beside it.

    **Two different scopes in one payload, deliberately.** `days` and
    `totals` are the requested month; `day_of_week`, `best_day`,
    `worst_day` and `streak` are ALL of history under the same
    strategy/horizon filter. A weekday pattern drawn from one month is 4-5
    observations per weekday and would be noise presented as a finding.
    """
    from swingbot.core.analytics import pnl_calendar as pc

    strategy, horizon = filters

    everything = _calendar_rows(rows)
    rows = pc.filter_rows(everything, strategy=strategy, horizon=horizon)
    grid = pc.month_grid(rows, month)
    extremes = pc.best_worst_days(rows)

    return {
        # A panel-level timestamp is the time this filtered view was composed,
        # not a claim about the age of any individual close in the month.
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "month": grid["month"],
        "days": grid["days"],
        "totals": grid["totals"],
        "longest_hold": pc.longest_hold(rows, grid["month"]),
        "day_of_week": pc.day_of_week_breakdown(rows),
        # The same breakdown restricted to the requested month (the one place a
        # 4-5 observations-per-weekday table is wanted: beside the all-history one).
        "month_day_of_week": pc.day_of_week_breakdown(
            [r for r in rows if r["day"].startswith(grid["month"])]),
        "best_day": extremes["best"],
        "worst_day": extremes["worst"],
        "streak": pc.day_streak(rows),
        "fx_missing_count": missing_count(
            [r for r in rows if r["day"].startswith(grid["month"])]),
        # Derived from the UNFILTERED set -- see `available_filters`.
        "filters": pc.available_filters(everything),
    }
