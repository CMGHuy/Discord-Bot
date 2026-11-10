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

import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from flask import jsonify, request

from swingbot.admin import market_values
from swingbot.admin.queries import analytics_snapshot_read
from swingbot.core.analytics import admin_snapshots, page_bodies
from swingbot.core.analytics.scope import BookScope, closed_only
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata.shared import admin_refresh
from swingbot.core.tracking.performance import TradeLog

from . import ApiError, _positive_int, api_v1
from .auth import require_auth

log = logging.getLogger(__name__)

def _snapshot(fresh: bool = False) -> dict:
    """The analytics snapshot, self-healing.

    A missing or expired snapshot rebuilds on this very request rather than
    500ing -- the behaviour /api/stats already has, and the reason the
    Analytics workspace works on a fresh install.
    """
    return analytics_snapshot_read(fresh=fresh)[0]


@api_v1.route("/analytics/snapshot", methods=["GET"])
@require_auth
def analytics_snapshot():
    """The whole snapshot, forwarded verbatim (was /api/stats), plus its MarketMeta."""
    doc, meta = analytics_snapshot_read(fresh=request.args.get("fresh") == "1")
    return jsonify({**doc, "market_meta": meta})


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


# v204: the snapshotted route bodies and their helpers live in core
# (`page_bodies`); the old names stay so the other routes keep calling them.
_all_trades = page_bodies._all_trades
_weak_in_account_currency = page_bodies._weak_in_account_currency
_fx_missing_total = page_bodies._fx_missing_total
# v204 V204-14: every route V204-2 marked `snapshot` has its body in `page_bodies`. The
# routes look these names up at call time, so a patched module attribute takes effect.
_performance_body = page_bodies.performance_body
_equity_curve_body = page_bodies.equity_curve_body

_LEDGER_DEFAULT_KEYS: dict[str, Callable[[str], str]] = {
    "analytics.performance": lambda ledger: admin_refresh.performance_key(ledger),
    "analytics.equity_curve": lambda ledger: admin_refresh.equity_curve_key(ledger),
}


def _ledger_default_key(route: str, scope: BookScope) -> str | None:
    """The snapshot key of an unfiltered (ledger-only) view, else None."""
    if scope != BookScope(ledger=scope.ledger):
        return None
    return _LEDGER_DEFAULT_KEYS[route](scope.ledger)


def _closed_tickers() -> list[str]:
    """The sorted unique tickers of the closed book."""
    return sorted({t["ticker"] for t in closed_only(_all_trades(TradeLog())) if t.get("ticker")})


def _fx_as_of(tickers: Iterable[str]) -> str | None:
    """The oldest FX rate date a request body converts with. None means unknown, never
    now: an unmounted daily bar cache is logged and leaves the date open."""
    from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable

    now = admin_snapshots._now()
    try:
        fx_map, _ = admin_snapshots._fx_inputs(list(tickers), on=now.date())
    except DailyCacheUnavailable as exc:
        swallowed(log, "ops.admin.analytics.fx_as_of", exc)
        return None
    return admin_snapshots.build_inputs(computed_at=now, fx=fx_map)["oldest_fx_as_of"]


def request_market_meta(*, fx_missing: int, tickers: Iterable[str], refreshing: bool = False,
                        error: str | None = None) -> dict:
    """The MarketMeta of a body computed on this request (`source: "request"`): the FX
    rows the body left unconverted count as missing."""
    meta = market_values.total_meta([], extra_missing=fx_missing)
    meta["as_of"] = _fx_as_of(tickers)
    meta["refreshing"] = bool(meta["refreshing"] or refreshing)
    if error:
        meta["error"] = error
    return meta


def _stored_view(route: str, key: str | None) -> tuple[dict | None, dict | None]:
    """(served body, snapshot row). Both None when the view has no key, the refresher is
    off or the route is not snapshotted; the body is None when the row has no doc yet."""
    if key is None or not admin_refresh.refresher_on() or route not in admin_snapshots.SNAPSHOT_ROUTES:
        return None, None
    snap = market_values.read_snapshot(key)
    if snap.get("doc") is None:
        return None, snap
    return {**snap["doc"], "market_meta": market_values.snapshot_meta(snap)}, snap


def default_view_body(route: str, key: str | None, compute: Callable[[], dict]) -> dict:
    """A default view's stored snapshot, else the request-time body (which never fetches
    while the refresher is on) with a request MarketMeta. Never an empty body of zeros."""
    served, snap = _stored_view(route, key)
    if served is not None:
        return served
    body = compute()
    body["market_meta"] = request_market_meta(
        fx_missing=int(body.get("fx_missing_count") or 0), tickers=_closed_tickers(),
        refreshing=snap is not None, error=snap["error"] if snap else None)
    return body


def _soak_for(strategy: str):
    from swingbot.core.backtesting.registry import get_badge
    from swingbot.core.edge.strategy_soak import soak_verdict
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.tracking.origin import is_regular
    plans = [plan for plan in PlanStore().all()
             if plan.source == "strategy" and plan.strategy == strategy and is_regular(plan)]
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
    """The scoped performance record: the default view's snapshot, else computed on request."""
    scope = _scope()
    return jsonify(default_view_body("analytics.performance",
                                     _ledger_default_key("analytics.performance", scope),
                                     lambda: _performance_body(scope)))


@api_v1.route("/analytics/equity-curve", methods=["GET"])
@require_auth
def analytics_equity_curve():
    """The scoped equity curve: the default view's snapshot, else computed on request."""
    scope = _scope()
    body = default_view_body("analytics.equity_curve",
                             _ledger_default_key("analytics.equity_curve", scope),
                             lambda: _equity_curve_body(scope))
    # Older snapshots can outlive the retired overlay until the next refresh.
    body.pop("benchmark", None)
    return jsonify(body)


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

    from .money import missing_count, to_account_currency

    scope = _scope(extra=("dim",))
    dim = (request.args.get("dim") or "").strip()
    if dim not in DIMENSIONS:
        raise ApiError("invalid", f"dim must be one of {list(DIMENSIONS)}, got {dim!r}", 400)

    scoped = select(to_account_currency(closed_only(_all_trades(TradeLog()))), scope)

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
                    "min_cell_n": MIN_CELL_N, "fx_missing_count": missing_count(scoped),
                    **echo(scope, len(scoped))})


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
    from swingbot.core.market.strategy_types import HORIZONS, live_horizons
    from swingbot.core.tracking.performance import primary_strategy_label

    scope = _scope()
    scoped = select(closed_only(_all_trades(TradeLog())), scope)
    cols = list(live_horizons())
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
    from swingbot.core.tracking.origin import ALL

    scope = _scope()
    scoped = select(closed_only(_all_trades(TradeLog())), scope)
    # The strip plot needs observations, not only the two aggregates in
    # hold_by_outcome.  Keep the same scoped population and cap the payload
    # so a long-lived book cannot turn an analytics view into a bulk export.
    hold_points = [
        {"outcome": m.resolve_outcome(trade), "days": round(days, 4)}
        for trade in scoped
        if (days := m._holding_days(trade)) is not None
    ][:2000]
    ids = {trade.get("id") for trade in scoped}
    entries = [entry for entry in JournalStore().entries(cohort=ALL) if entry.get("trade_id") in ids]
    return jsonify({"exit_reasons": m.exit_reason_split(scoped),
                    "unmapped_reasons": m.unmapped_exit_reasons(scoped),
                    "hold_by_outcome": m.hold_by_outcome(scoped),
                    "hold_points": hold_points,
                    "efficiency": eq.efficiency_histogram(entries),
                    "mae": eq.mae_histogram(entries),
                    "scatter": eq.mfe_mae_points(entries),
                    "coverage": eq.coverage(entries),
                    "min_cell_n": MIN_CELL_N,
                    **echo(scope, len(scoped))})


def _manual_exit_prices() -> dict[str, float]:
    """plan_id -> the linked trade's exit price.

    A manual close realises the runner as a leg on the TRADE only
    (`TradeLog.close_trade_manual`); the plan records no leg. The Partials
    tab reads that price for a closed runner whose plan carries none.
    """
    return {trade["plan_id"]: float(trade["exit_price"]) for trade in _all_trades(TradeLog())
            if trade.get("plan_id") and trade.get("exit_price") is not None}


@api_v1.route("/analytics/partials", methods=["GET"])
@require_auth
def analytics_partials():
    """TP1->TP2 conversion and runner counterfactuals over the scoped live
    book (spec v142). Plans, not trades: the scope's date range filters on
    FILL date, and `n` is the filled plans in scope. Live book only -- a
    small, non-pre-registered sample, never a gate."""
    from swingbot.core.analytics import partials as pa
    from swingbot.core.analytics.scope import echo
    from swingbot.core.planning.plan_store import PlanStore

    scope = _scope()
    plans = pa.select_plans(PlanStore().all(), scope)
    report = pa.build_report(plans, manual_exits=_manual_exit_prices())
    return jsonify({**report, **echo(scope, len(plans))})


def _override_inputs() -> tuple[list, dict[str, dict]]:
    """Every plan, and every paper trade keyed by its plan id (v173 override_io)."""
    from swingbot.core.analytics import override_io as oio

    return oio.load_inputs()


def _override_verdict() -> dict | None:
    """The stored v173 verdict record from preregistration_verdicts, or None. Read only."""
    from swingbot.core.analytics import override_io as oio

    return oio.stored_verdict()


@api_v1.route("/analytics/override-fidelity", methods=["GET"])
@require_auth
def analytics_override_fidelity():
    """Manual overrides vs the engine left alone (spec v173 section 5).

    Computed on request: each manual close replayed from its fill through
    the v2 exit engine on the live scan's bar cache (never fetched). The
    verdict is the stored preregistration_verdicts record, or WAITING; this
    route never evaluates or writes it -- only the bot's daily job does.
    Global, not scoped: every manual close is in the table."""
    from swingbot import config
    from swingbot.core.analytics import override_fidelity as of
    from swingbot.core.analytics import override_verdict as ov
    from swingbot.core.analytics import runner_path as rp

    recorded = _override_verdict()
    plans, trades = _override_inputs()
    asof = of.latest_completed_session(datetime.now(timezone.utc))
    return jsonify(ov.build_report(plans, trades, rp.cached_daily_bars, asof, recorded,
                                   config.CURRENCY_SYMBOL))


@api_v1.route("/analytics/cohort", methods=["GET"])
@require_auth
def analytics_cohort():
    """v144: one origin cohort's own N, fill rate (issued -> filled), win rate
    and ExpR of its closed trades, and its cancellation-reason histogram. The
    cohort is never folded into any other figure this API serves."""
    from swingbot.core.analytics.cohort import cohort_report
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.tracking.origin import ORIGINS

    origin = (request.args.get("origin") or "").strip()
    if origin not in ORIGINS:
        raise ApiError("invalid", f"origin must be one of {list(ORIGINS)}, got {origin!r}", 400)
    return jsonify(cohort_report(PlanStore().all(), _all_trades(TradeLog()), origin))


@api_v1.route("/analytics/calibration", methods=["GET"])
@require_auth
def analytics_calibration():
    calibration = _snapshot().get("calibration", {})
    return jsonify({
        "deciles": calibration.get("deciles", []),
        "levels": calibration.get("levels", []),
        "drift": calibration.get("drift", []),
        # v164 D4: {"rows": [...], "counts": {...}}. A snapshot cached before
        # the deploy has no key; serve the empty shape, never a 500.
        "live_loss_watch": calibration.get("live_loss_watch") or {"rows": [], "counts": {}},
        "scope": "all-time",
    })


def _closed_book() -> list[dict]:
    """v175: the whole closed book -- every ledger, no BookScope.

    The variance band is whole-book by design (it does not follow the
    Analytics scope bar), so this deliberately skips `_scope()`/`select()`.
    A seam: tests monkeypatch it instead of seeding a store."""
    from swingbot.core.analytics.scope import closed_only

    return closed_only(_all_trades(TradeLog()))


@api_v1.route("/analytics/variance-band", methods=["GET"])
@require_auth
def analytics_variance_band():
    """v175: the range of losing-day runs and drawdowns this book's own closed
    trades produce by chance, and where the book sits now against it.

    Computed on request (no snapshot) so the ExpR beside the band is
    re-derived every call. Takes no parameters: a scope filter would be a
    lie here, so any parameter is a 400, never silently ignored."""
    from swingbot.core.analytics import variance_band as vb

    if request.args:
        raise ApiError("invalid", f"unknown parameter {sorted(request.args)[0]!r}; allowed: []", 400)
    return jsonify(vb.variance_band(_closed_book()))


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
    from swingbot.core.tracking.origin import is_regular

    plans = [plan for plan in PlanStore().all() if is_regular(plan)]
    return jsonify({**_plan_lifecycle(plans), "scope": "all-time"})
