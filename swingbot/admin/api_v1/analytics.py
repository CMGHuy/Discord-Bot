"""GET /api/v1/analytics/* — the historical-analysis surface.

Spec 3 folds Performance, Strategies, Calibration and Tuning into one
Analytics workspace, rendered as four tabs (spec v14 Decision 6). These
endpoints back those tabs.

**"UI renders, analytics computes."** Every figure here already exists,
computed by `swingbot.core.analytics` and cached in
`data/analytics_snapshot.json`. These routes project it; they do not
derive. The one exception is `/performance`, which assembles the six
metrics spec 3 relocated from the Dashboard header out of
`TradeLog.get_extended_stats` -- an assembly of existing values, not a new
calculation.

Rendered artefacts are stripped. The old `pages._sparkline_svg` gave Jinja an
`<svg>` string; the SPA gets the underlying series and draws it itself,
because sub-project 3 owns how a sparkline looks.
"""
from __future__ import annotations

from datetime import datetime

from flask import jsonify, request

from swingbot.core.tracking.performance import TradeLog

from . import ApiError, _positive_int, api_v1
from .auth import require_auth


def _snapshot(fresh: bool = False) -> dict:
    """The analytics snapshot, self-healing.

    A missing or expired snapshot rebuilds on this very request rather than
    500ing -- the behaviour /api/stats already has, and the reason the
    Analytics workspace works on a fresh install.
    """
    from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot

    if fresh:
        refresh_snapshot()
        return load_snapshot(max_age_seconds=3600) or {}
    return load_snapshot(max_age_seconds=3600) or refresh_snapshot() or {}


@api_v1.route("/analytics/snapshot", methods=["GET"])
@require_auth
def analytics_snapshot():
    """The whole snapshot, forwarded verbatim (was /api/stats)."""
    return jsonify(_snapshot(fresh=request.args.get("fresh") == "1"))


def _iso_day(name: str) -> str | None:
    """Read a `YYYY-MM-DD` query parameter, or raise ApiError.

    A malformed date is a 400, never a silently-dropped filter. Accepting
    `?from=last-tuesday` and quietly returning the whole history is how a user
    ends up reading all-time numbers as this month's -- the same class of bug
    SR52 fixed on the Trades list, where filters applied only to the rows that
    happened to be on screen.
    """
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise ApiError("invalid", f"{name} must be a YYYY-MM-DD date", 400)
    return raw


def _scope(extra: tuple[str, ...] = ()):
    """Parse the request's BookScope or 400 (spec v94 D5). `extra` names
    route-specific parameters (e.g. `dim`) that are not scope fields."""
    from swingbot.core.analytics.scope import ScopeError, parse_scope, reject_unknown

    try:
        reject_unknown(request.args, extra)
        return parse_scope(request.args)
    except ScopeError as exc:
        raise ApiError("invalid", str(exc), 400)


def _all_trades(tl: TradeLog) -> list[dict]:
    """Every trade in every ledger; `scope.select` applies the ledger filter."""
    return tl.get_trades(status=None, limit=None, ledger=None) or []


def _index_benchmark(spy_cum, start: str | None) -> list[dict]:
    """SPY as a percent series indexed to the first point at/after `start`
    (spec v94 D6/H5: one axis -- SPY is only ever drawn in % mode).

    `spy_cum` is a `{date: cumulative_level}` mapping -- the only shape this
    key has ever had. It came from `TradeLog.get_detailed_stats`, dropped as
    dead code in 4ae117dc; `get_extended_stats` (what `/performance` reads
    today) does not compute `spy_cum` at all, so in production this is
    `{}` until a real benchmark fetch is wired back in. No producer -- past
    or present -- has ever emitted a list-of-rows shape for this key, so
    this does not invent handling for one; a non-dict input is treated as
    absent.
    """
    if not isinstance(spy_cum, dict):
        return []
    rows = sorted((str(d)[:10], float(v)) for d, v in spy_cum.items() if v is not None)
    rows = [(d, v) for d, v in rows if not start or d >= start]
    if not rows:
        return []
    base = rows[0][1]
    if not base:
        return []
    return [{"date": d, "pct": round((v / base - 1) * 100, 4)} for d, v in rows]


def _soak_for(strategy: str):
    from swingbot.core.backtesting.registry import get_badge
    from swingbot.core.edge.strategy_soak import soak_verdict
    from swingbot.core.planning.plan_store import PlanStore
    plans = [plan for plan in PlanStore().all() if plan.source == "strategy" and plan.strategy == strategy]
    badge = get_badge("strategy", strategy)
    return soak_verdict(plans, badge), badge


@api_v1.route("/analytics/soak", methods=["GET"])
@require_auth
def analytics_soak():
    unknown = set(request.args) - {"strategy"}
    if unknown:
        raise ApiError("invalid", f"unknown parameter {sorted(unknown)[0]!r}; allowed: ['strategy']", 400)
    strategy = (request.args.get("strategy") or "").strip()
    if not strategy:
        raise ApiError("invalid", "strategy is required", 400)
    verdict, badge = _soak_for(strategy)
    return jsonify({"strategy": strategy,
                    "badge": {"status": badge.status, "n": badge.n, "expectancy_r": badge.expectancy_r},
                    "verdict": verdict})


@api_v1.route("/analytics/performance", methods=["GET"])
@require_auth
def analytics_performance():
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

    Every figure is computed in `core.analytics.metrics` -- this route selects
    and assembles, it does not derive. That is the same "one definition per
    stat" rule that keeps `aggregate.py` delegating, and the reason the
    annualised Sharpe here is `sharpe() * annualisation_factor()` rather than
    a second Sharpe expression written inline.
    """
    from swingbot.admin.dashboard import closed_pnl
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.scope import closed_only, echo, select

    scope = _scope()
    tl = TradeLog()
    all_raw = _all_trades(tl)
    all_closed = closed_only(all_raw)                # the real, unscoped book -- balance_at reads THIS
    closed = select(all_closed, scope)                # every other block below reads THIS list
    scoped = closed
    start, end = scope.start, scope.end
    stats = tl.get_stats(trades=all_raw)             # totals.total/open stay book-wide
    stats.update(tl.get_extended_stats(trades=all_raw))
    realized = [p for p in (closed_pnl(t) for t in closed) if p is not None]

    from swingbot.core.planning import account as account_module
    base_balance = float(account_module.load_account_config().get("base_balance") or 0.0)
    # There is exactly one real pooled account balance -- it has no
    # per-strategy/per-ledger/per-horizon meaning, so this reads the
    # unscoped `all_closed`, filtered only by date via balance_at's own
    # `before` cutoff, matching /analytics/equity-curve's window_balance.
    window_balance = m.balance_at(all_closed, start, base_balance)
    returns = [r for r in (m.trade_return_pct(t) for t in scoped) if r is not None]
    factor = m.annualisation_factor(scoped)
    raw_sharpe, raw_sortino = m.sharpe(returns), m.sortino(returns)

    return jsonify({
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
        "expectancy_r": m.expectancy_r(closed),
        "expectancy_n": len(m.r_multiples(closed)),
        "by_confidence": tl.get_stats_by_confidence(),
        "weak": tl.weak_summary(),

        "range": {
            "from": start, "to": end,
            "span_years": (round(sy, 4) if (sy := m.span_years(scoped)) is not None else None),
            "n": len(scoped),
        },
        "derived": {
            "avg_win_pct": m.avg_win_pct(scoped),
            "avg_loss_pct": m.avg_loss_pct(scoped),
            "total_return_pct": m.total_return_pct(scoped, window_balance),
            "annualised_return_pct": m.annualised_return_pct(scoped, window_balance),
            "calmar": m.calmar(scoped, window_balance),
            "volatility_ann_pct": m.volatility_ann_pct(scoped),
            "trades_per_month": m.trades_per_month(scoped),
            "pct_in_market": m.pct_in_market(scoped),
            # Annualised by multiplying the module's per-trade ratio, never by
            # re-deriving one here -- see this docstring's last paragraph.
            "sharpe_ann": round(raw_sharpe * factor, 4) if raw_sharpe is not None else None,
            "sortino_ann": round(raw_sortino * factor, 4) if raw_sortino is not None else None,
            "win_rate": m.win_rate(scoped),
            "expectancy_r": m.expectancy_r(scoped),
        },
        "distributions": {
            "returns": m.histogram(returns, bins=12),
            "r_multiples": m.histogram(m.r_multiples(scoped), bins=12),
        },
        "rolling_returns": m.rolling_return_pct(scoped),
        "holding_period_split": m.holding_period_split(scoped),
        "risk_reward_split": m.risk_reward_split(scoped),
        "calendar": m.calendar_returns(scoped, window_balance),
        "cumulative_by_strategy": m.cumulative_pnl_by_strategy(scoped),
        # Best-effort: get_extended_stats swallows a failed yfinance fetch and
        # returns {}. The key is always present so the workspace never has to
        # distinguish "no benchmark" from "no such field".
        "benchmark": {"spy_cum": stats.get("spy_cum") or {}},
        "rolling_wr": m.rolling_win_rate(scoped, window=50),
        "rolling_exp_r": m.rolling_expectancy_r(scoped, window=50),
        **echo(scope, len(scoped)),
    })


@api_v1.route("/analytics/equity-curve", methods=["GET"])
@require_auth
def analytics_equity_curve():
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

    `benchmark.spy_indexed` re-bases `spy_cum` (see `_index_benchmark`) to
    the scope's own start so the SPY overlay and the account curve always
    share the same day-zero, never SPY's own inception.
    """
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.scope import closed_only, echo, select
    from swingbot.core.planning import account as account_module

    scope = _scope()
    tl = TradeLog()
    all_raw = _all_trades(tl)
    closed = closed_only(all_raw)
    scoped = select(closed, scope)
    base_balance = float(account_module.load_account_config().get("base_balance") or 0.0)
    window_balance = m.balance_at(closed, scope.start, base_balance)
    spy_cum = (tl.get_extended_stats(trades=all_raw) or {}).get("spy_cum") or {}

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

    return jsonify({
        "points": points,
        "points_n": len(points),
        "as_of": points[-1]["date"] if points else None,
        "benchmark": {"spy_indexed": _index_benchmark(spy_cum, scope.start)},
        **echo(scope, len(scoped)),
    })


@api_v1.route("/analytics/by-dimension", methods=["GET"])
@require_auth
def analytics_by_dimension():
    """One row per strategy or per horizon, carrying BOTH ExpR and total R
    (spec v14 D40) -- the Analytics Performance tab's strategy table and
    horizon bar list share this one endpoint and toggle client-side between
    the two measures. Consumed by R9-05.

    `total_r` is a true sum of `metrics.r_multiple()` over the group, never
    `exp_r * n`: a trade with no computable R is skipped from both the mean
    and `n`, but it was never going to contribute to the sum either, and a
    client deriving one from the other would print a number nobody actually
    computed once such a trade exists in the group.

    `badge` (the strategy's registry validation verdict, via the same
    `get_badge("strategy", ...)` pooled lookup `core.planning.params` already
    uses to stamp a live plan) is attached only for `dim=strategy` --
    horizons carry no registry verdict of their own, and a horizon row would
    otherwise carry an always-empty column.

    `dim=horizon` groups by the real `HORIZONS` vocabulary only: a trade
    whose `horizon_key` isn't one of the ten real horizons is dropped from
    this view rather than inventing a row for a key nothing else recognizes.
    Horizon rows are ordered by horizon progression (2w..9m); strategy rows
    alphabetically, for a stable render.

    `as_of` is scoped to the trades that actually survived grouping for
    THIS `dim`, never the unfiltered closed-trade set. `dim=horizon` drops
    any trade whose `horizon_key` isn't real HORIZONS vocabulary (see
    above); if a freshly-closed trade with such a legacy/unrecognized
    horizon were allowed to set `as_of`, the stamp would claim the rows are
    more current than the data actually shown -- the same "screen hides how
    stale its data is" bug class as an empty range rendering as zeroes.

    spec v94 D7/H1: every `aggregate.DIMENSIONS` value, not just
    strategy/horizon; rate fields are null under `MIN_CELL_N`.
    """
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.aggregate import DIMENSIONS, MIN_CELL_N, group_by
    from swingbot.core.analytics.risk_metrics import max_drawdown_r
    from swingbot.core.analytics.scope import closed_only, echo, select
    from swingbot.core.backtesting.registry import get_badge
    from swingbot.core.market.strategy_types import HORIZONS
    from swingbot.core.tracking.performance import primary_strategy_label

    scope = _scope(extra=("dim",))
    dim = (request.args.get("dim") or "").strip()
    if dim not in DIMENSIONS:
        raise ApiError("invalid", f"dim must be one of {list(DIMENSIONS)}, got {dim!r}", 400)

    scoped = select(closed_only(_all_trades(TradeLog())), scope)

    if dim == "strategy":            # the real per-trade label, as before
        groups: dict[str, list[dict]] = {}
        for t in scoped:
            groups.setdefault(primary_strategy_label(t), []).append(t)
    elif dim == "horizon":
        groups = {k: v for k, v in group_by(scoped, dim).items() if k in HORIZONS}
    else:
        groups = group_by(scoped, dim)

    if dim == "horizon":
        order = {h: i for i, h in enumerate(HORIZONS)}
        keys = sorted(groups, key=lambda k: order.get(k, len(order)))
    elif dim == "month":
        keys = sorted(groups)
    else:
        keys = sorted(groups, key=lambda k: (-len(groups[k]), str(k)))

    rows = []
    for key in keys:
        trades = groups[key]
        ordered = sorted(trades, key=lambda t: t.get("closed_at") or "")
        rs = [r for t in ordered if (r := m.r_multiple(t)) is not None]
        thin = len(trades) < MIN_CELL_N
        row = {
            "key": str(key), "n": len(trades),
            "wins": sum(1 for t in trades if t.get("status") == "win"),
            "losses": sum(1 for t in trades if t.get("status") == "loss"),
            "exp_r": None if thin else m.expectancy_r(trades),
            "win_rate": None if thin else m.win_rate(trades),
            "profit_factor": None if thin else m.profit_factor(trades),
            "avg_win_r": None if thin else m.avg_win_r(trades),
            "avg_loss_r": None if thin else m.avg_loss_r(trades),
            "total_r": (round(sum(rs), 4) if rs else None),
            "total_pnl": round(sum(float(t.get("realized_pnl_amount") or 0.0) for t in trades), 2),
            "max_drawdown_r": max_drawdown_r(rs),
        }
        if dim == "strategy":
            row["badge"] = get_badge("strategy", key).status
            verdict, _ = _soak_for(key)
            row["soak"] = {"pass": verdict["pass"], "n_closed": verdict["n_closed"],
                           "clauses": verdict["clauses"]} if verdict["n_closed"] else None
        rows.append(row)

    dated = [t["closed_at"][:10] for trades in groups.values() for t in trades if t.get("closed_at")]
    return jsonify({"rows": rows, "as_of": max(dated) if dated else None,
                    "min_cell_n": MIN_CELL_N, **echo(scope, len(scoped))})


@api_v1.route("/analytics/heat-grid", methods=["GET"])
@require_auth
def analytics_heat_grid():
    """Strategy × horizon grid over the scoped book (spec v94 D7/H1).

    Only strategies whose scoped total clears ``MIN_CELL_N`` get a row; the
    rest fold into one ``Other`` row so a sparse book does not turn into a
    confident-looking wall of noise. Every cell under the floor carries its
    count and null rates for the client to render as a blank, dotted cell.
    """
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.aggregate import MIN_CELL_N
    from swingbot.core.analytics.scope import closed_only, echo, select
    from swingbot.core.market.strategy_types import HORIZONS
    from swingbot.core.tracking.performance import primary_strategy_label

    scope = _scope()
    scoped = select(closed_only(_all_trades(TradeLog())), scope)
    cols = list(HORIZONS)
    by_strategy: dict[str, list[dict]] = {}
    for trade in scoped:
        if trade.get("horizon_key") in HORIZONS:
            by_strategy.setdefault(primary_strategy_label(trade), []).append(trade)

    def cell(trades: list[dict]) -> dict:
        thin = len(trades) < MIN_CELL_N
        return {
            "n": len(trades),
            "exp_r": None if thin else m.expectancy_r(trades),
            "win_rate": None if thin else m.win_rate(trades),
        }

    fat = sorted(
        (strategy for strategy, trades in by_strategy.items() if len(trades) >= MIN_CELL_N),
        key=lambda strategy: (-len(by_strategy[strategy]), strategy),
    )
    cells = []
    for row, strategy in enumerate(fat):
        for column, horizon in enumerate(cols):
            cells.append({
                "r": row,
                "c": column,
                **cell([trade for trade in by_strategy[strategy]
                        if trade.get("horizon_key") == horizon]),
            })

    folded_names = [strategy for strategy in by_strategy if strategy not in fat]
    folded_trades = [trade for strategy in folded_names for trade in by_strategy[strategy]]
    folded = {
        "n_strategies": len(folded_names),
        "cells": [
            {"c": column, **cell([trade for trade in folded_trades
                                   if trade.get("horizon_key") == horizon])}
            for column, horizon in enumerate(cols)
        ],
    }
    return jsonify({
        "rows": fat,
        "cols": cols,
        "cells": cells,
        "folded": folded,
        "min_cell_n": MIN_CELL_N,
        **echo(scope, len(scoped)),
    })


@api_v1.route("/analytics/journal", methods=["GET"])
@require_auth
def analytics_journal():
    """SR55 — the trailing-week digest and the recurring lessons.

    Both already existed (`core.analytics.insights`) and were rendered by the
    since-deleted `pages.py:journal_page`; only the API in front of them was
    missing, which is why the parity audit found this cluster with nothing on
    the wire.

    This is NOT a rebuilt Journal page. Spec v14 Decision 4 collapsed that
    page deliberately: the digest and lessons are analytics and belong on the
    Analytics workspace, while a single trade's excursions belong beside the
    note that explains them, on the detail view. Serving both from here would
    re-create the page the IA change removed.

    `today` comes from the server clock rather than a parameter. The digest is
    "the trailing week", and letting a client choose the anchor would turn a
    fixed report into an ad-hoc query with no pre-registered meaning.
    """
    import datetime as dt

    from swingbot.core.analytics.insights import top_lessons, weekly_digest
    from swingbot.core.analytics.journal import JournalStore
    from swingbot.core.analytics.scope import closed_only, echo, select

    scope = _scope(extra=("lessons",))
    raw_lessons = (request.args.get("lessons") or "").strip()
    lessons_n = _positive_int(raw_lessons, "lessons") if raw_lessons else 5

    try:
        entries = JournalStore().entries()
    except Exception:
        # Same posture as `_noted_ids`: an unreadable journal degrades to
        # "nothing to report" rather than failing an analytics tab whose
        # other panels came from elsewhere and are fine.
        entries = []

    scoped = select(closed_only(_all_trades(TradeLog())), scope)
    ids = {trade.get("id") for trade in scoped}
    entries = [entry for entry in entries if entry.get("trade_id") in ids]

    return jsonify({
        "digest": weekly_digest(entries, scoped, today=dt.datetime.now().date()),
        "lessons": top_lessons(entries, n=lessons_n),
        # The sample behind both lists. A digest drawn from three entries and
        # one drawn from three hundred should not read the same way.
        "entries_n": len(entries),
        **echo(scope, len(scoped)),
    })


@api_v1.route("/analytics/strategies", methods=["GET"])
@require_auth
def analytics_strategies():
    """Registry rows are all-time; scoped series describe this book slice.

    A badge is a methodology verdict and must not change with a filter.
    Contribution, cumulative R, and sparklines do obey BookScope (v94 D5/D9).
    """
    from swingbot.admin.queries import _registry_rows, _rolling_win_rate_series
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.scope import closed_only, echo, select
    from swingbot.core.tracking.performance import primary_strategy_label

    scope = _scope()
    rows = _registry_rows()
    scoped = select(closed_only(_all_trades(TradeLog())), scope)
    labeled = [{**trade, "strategy": primary_strategy_label(trade)} for trade in scoped]
    for row in rows:
        strat = [trade for trade in labeled if trade["strategy"] == row["strategy"]]
        row["win_rate_series"] = _rolling_win_rate_series(strat, window=10)

    by_strategy: dict[str, list[dict]] = {}
    for trade in labeled:
        by_strategy.setdefault(trade["strategy"], []).append(trade)
    contribution, cumulative = [], {}
    for name, trades in by_strategy.items():
        ordered = sorted(trades, key=lambda trade: trade.get("closed_at") or "")
        rs = [(trade, r) for trade in ordered if (r := m.r_multiple(trade)) is not None]
        contribution.append({
            "strategy": name,
            "total_r": round(sum(r for _, r in rs), 4) if rs else None,
            "n": len(trades),
        })
        running, series = 0.0, []
        for trade, r in rs:
            running += r
            series.append({"date": (trade.get("closed_at") or "")[:10], "cum_r": round(running, 4)})
        cumulative[name] = series
    contribution.sort(key=lambda row: (-(abs(row["total_r"]) if row["total_r"] is not None else -1), row["strategy"]))
    return jsonify({
        "strategies": rows,
        "registry_scope": "all-time",
        "contribution": contribution,
        "cumulative": cumulative,
        **echo(scope, len(scoped)),
    })


@api_v1.route("/analytics/exit-quality", methods=["GET"])
@require_auth
def analytics_exit_quality():
    """Exit-quality aggregates over the scoped book (spec v94 D8).

    Journal-derived blocks join on ``trade_id`` so the winners-only
    histograms describe the same population as the exit strip above them.
    """

    from swingbot.core.analytics import exit_quality as eq
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.aggregate import MIN_CELL_N
    from swingbot.core.analytics.journal import JournalStore
    from swingbot.core.analytics.scope import closed_only, echo, select

    scope = _scope()
    scoped = select(closed_only(_all_trades(TradeLog())), scope)
    ids = {trade.get("id") for trade in scoped}
    entries = [entry for entry in JournalStore().entries() if entry.get("trade_id") in ids]
    return jsonify({"exit_reasons": m.exit_reason_split(scoped),
                    "unmapped_reasons": m.unmapped_exit_reasons(scoped),
                    "hold_by_outcome": m.hold_by_outcome(scoped),
                    "efficiency": eq.efficiency_histogram(entries),
                    "mae": eq.mae_histogram(entries),
                    "scatter": eq.mfe_mae_points(entries),
                    "coverage": eq.coverage(entries),
                    "min_cell_n": MIN_CELL_N,
                    **echo(scope, len(scoped))})


@api_v1.route("/analytics/calibration", methods=["GET"])
@require_auth
def analytics_calibration():
    calibration = _snapshot().get("calibration", {})
    return jsonify({
        "deciles": calibration.get("deciles", []),
        "levels": calibration.get("levels", []),
        "drift": calibration.get("drift", []),
    })


@api_v1.route("/analytics/registry", methods=["GET"])
@require_auth
def analytics_registry():
    from swingbot.admin.queries import _registry_rows

    return jsonify({"registry": _registry_rows()})


@api_v1.route("/analytics/plans", methods=["GET"])
@require_auth
def analytics_plans():
    """Lifecycle funnel, fill rate/time-to-fill, and badge/tier distribution
    over every plan ever posted -- the Plans tab. 'UI renders, analytics
    computes': the actual walk is `_plan_lifecycle`, this route only calls
    and forwards it, same as every other route in this module.
    """
    from swingbot.admin.queries import _plan_lifecycle
    from swingbot.core.planning.plan_store import PlanStore

    return jsonify(_plan_lifecycle(PlanStore().all()))
