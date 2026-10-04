"""v93 strategy-sourced alert pass helpers."""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
import pandas as pd

from swingbot.core.market import market_context
from swingbot.core.market.entry_filters import ENTRY_FUNCS, entries_for
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.params import stamp_badge, stamp_cohort, stamp_entry_context
from swingbot.core.planning.stop_scope import risk_sizing_ok
from swingbot.core.tracking import ledger as ledger_mod
from swingbot.core.edge.rs_gate import rs_verdict
from swingbot.core.edge.gates import PULLBACK_VOLUME_REASON, pullback_dryup_blocks
from swingbot.core.scanning.alert_embeds import (build_strategy_alert_embed,
                                                 build_strategy_simple_embed)

log = logging.getLogger(__name__)
from swingbot.core.market.session import is_regular_session, session_date


def completed_frame(df: pd.DataFrame, now) -> pd.DataFrame:
    """Remove only today's still-forming daily bar during the regular session."""
    if df is None or len(df) == 0:
        return df
    if df.index[-1].date().isoformat() == session_date(now) and is_regular_session(now):
        return df.iloc[:-1]
    return df


def already_emitted(store, ticker: str, strategy: str, horizon_key: str, bar_date: str) -> bool:
    """Whether a persisted strategy plan already represents this completed bar."""
    return any(getattr(plan, "source", None) == "strategy"
               and plan.ticker == ticker and plan.strategy == strategy
               and plan.horizon_key == horizon_key and plan.created_at == bar_date
               for plan in store.all())


def strategy_signals(df_completed: pd.DataFrame, horizon_key: str, *, spy_df) -> list[tuple[str, str]]:
    """Return entry-rule signals firing on the last completed bar only."""
    if spy_df is None or len(spy_df) == 0:
        import logging
        logging.getLogger(__name__).warning("strategy pass: no SPY frame this scan -- strategy signals skipped (fail-closed)")
        return []
    frame = df_completed if market_context.has_context(df_completed) else market_context.attach(df_completed, spy_df=spy_df)
    fired = []
    for strategy in ENTRY_FUNCS:
        try:
            bullish, bearish = entries_for(strategy, frame, horizon_key)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("strategy pass: %s/%s raised -- skipped", strategy, horizon_key, exc_info=True)
            continue
        if len(bullish) and bool(bullish.iloc[-1]):
            fired.append((strategy, "bullish"))
        if len(bearish) and bool(bearish.iloc[-1]):
            fired.append((strategy, "bearish"))
    return fired


def build_strategy_plan_at(df_completed: pd.DataFrame, *, ticker: str, strategy: str,
                           horizon_key: str, direction: str, regime2_state: str | None, asof: dict | None = None):
    """Build and freeze all immutable issuance stamps for one strategy signal."""
    plan = build_strategy_plan(df_completed, len(df_completed) - 1, ticker=ticker,
                               strategy=strategy, horizon_key=horizon_key, direction=direction)
    if plan is None:
        return None
    stamp_badge(plan)
    stamp_cohort(plan, regime2_state)
    stamp_entry_context(plan, df_completed, {**(asof or {}), "regime2_state": regime2_state})
    plan.ledger = ledger_mod.ledger_for(plan.source, plan.badge)
    return plan


@dataclass
class PassResult:
    plans: list = field(default_factory=list)
    alerts: list = field(default_factory=list)
    opened: int = 0
    stored_only: int = 0
    rs_blocked: int = 0
    skipped_dup: int = 0
    sizing_blocked: int = 0
    compression_rejected: int = 0
    earnings_excluded_by_mode: Counter = field(default_factory=Counter)
    compression_reasons: Counter = field(default_factory=Counter)
    # "<mode>:<reason>" (mode broad|isolated|none), the broad/isolated split of compression_reasons.
    compression_reasons_by_mode: Counter = field(default_factory=Counter)
    compression_shadow: list = field(default_factory=list)  # audit records of the masked raw signal
    pullback_volume: int = 0


@dataclass
class _PassDeps:
    """The collaborators one strategy pass threads through every signal."""

    plan_store: object
    trade_log: object
    mode: str
    live_allow: set
    rs_combined_of: object
    asof_of: object = None
    compression_of: object = None  # (ticker, frame) -> (mode, reason); None = fail closed
    earnings_of: object = None  # ticker -> EarningsSnapshot observed by `now`; None = fail closed
    now: object = None  # the decision timestamp (tz-aware)


def _regime_for(regimes, frame):
    if regimes is None:
        return None
    # Lazy import avoids scan engine's analyze <-> engine import cycle.
    from swingbot.core.scanning import analyze

    return analyze._regime_at(regimes, frame.index[-1])


def _rs_blocked(ticker: str, direction: str, rs_combined_of) -> bool:
    """Return whether the live v93 laggard rule blocks a bearish signal."""
    if direction != "bearish":
        return False
    rs_value = rs_combined_of(ticker)
    verdict = rs_verdict(ticker, direction, rs_value if rs_value is not None else 50.0,
                         rs_available=rs_value is not None)
    return verdict["status"] == "block"


def _open_trade(deps: _PassDeps, plan, *, ticker, strategy, horizon, direction) -> None:
    deps.trade_log.log_trade(
        ticker=ticker, strategy=strategy, horizon_key=horizon, direction=direction,
        confidence_level=None, confidence_label="strategy signal", entry=plan.trigger_price,
        stop_loss=plan.stop_loss, take_profit=plan.tp1, target2=plan.tp2,
        plan_id=plan.plan_id, badge=plan.badge, quality_score=plan.quality_score,
        source=plan.source, cohort_label=plan.cohort_label,
        cohort_stats=plan.cohort_stats, risk_features=plan.risk_features,
        ledger=plan.ledger, entry_context=plan.entry_context)


def _compression_context(ticker, strategy, frame, deps: _PassDeps):
    """(stamp, reject_reason) for the masked compression strategy; other strategies pass through.

    The verdict is compression_context.decide_compression_entry -- the same pure function the
    research replay calls -- fed from this pass's hooks. No hook wired = fail closed."""
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT
    from swingbot.core.scanning.compression_context import decide_compression_entry
    if strategy != COMPRESSION_SHORT:
        return {}, None
    mode, reason = deps.compression_of(ticker, frame) if deps.compression_of else (None, "no_context")
    snapshot = deps.earnings_of(ticker) if (deps.earnings_of and mode is not None) else None
    return decide_compression_entry(ticker, frame, mode=mode, mode_reason=reason,
                                    snapshot=snapshot, now=deps.now)


def _count_compression_reject(result: "PassResult", stamp: dict, reason: str) -> None:
    """One rejected compression candidate: the flat counter, the broad/isolated split, the earnings tally."""
    mode = stamp.get("compression_mode")
    result.compression_rejected += 1
    result.compression_reasons[reason] += 1
    result.compression_reasons_by_mode[f"{mode or 'none'}:{reason}"] += 1
    if reason.startswith("earnings_") and mode:
        result.earnings_excluded_by_mode[mode] += 1


def compression_shadow_record(frame, *, ticker, horizon, deps: _PassDeps, result: "PassResult",
                              seen: set | None = None):
    """Shadow evaluation of the masked compression strategy on the raw signal: the decision, a plan
    built for audit, and a record. Never a stored plan, alert, paper trade or order instruction.

    Skipped (None) when the bar has no raw signal, the mask admits this cell (the normal path owns it),
    or (ticker, horizon, bar_date) is already in `seen` -- a re-scan of the same completed bar neither
    fetches earnings again nor re-counts the candidate. The key is added to `seen` once evaluated.
    """
    from swingbot.core.market.short_entries import compression_short_frame
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT, admits
    from swingbot.core.planning.plan_types import plan_to_dict
    from swingbot.core.planning.short_builders import compression_rejection_reason
    if admits(COMPRESSION_SHORT, "bearish", horizon):
        return None
    signal = compression_short_frame(frame, horizon)["signal"]
    if not len(signal) or not bool(signal.iloc[-1]):
        return None
    key = (ticker, horizon, frame.index[-1].date().isoformat())
    if seen is not None:
        if key in seen:
            return None
        seen.add(key)
    stamp, reason = _compression_context(ticker, COMPRESSION_SHORT, frame, deps)
    plan = None
    if reason is None:
        plan = build_strategy_plan(frame, len(frame) - 1, ticker=ticker, strategy=COMPRESSION_SHORT,
                                   horizon_key=horizon, direction="bearish")
        if plan is None:
            reason = compression_rejection_reason(frame, len(frame) - 1, horizon)
        else:
            plan.entry_context = {**(plan.entry_context or {}), **stamp}
    if reason is not None:
        _count_compression_reject(result, stamp, reason)
    return {"ticker": ticker, "horizon": horizon, "bar_date": frame.index[-1].date().isoformat(),
            "mode": stamp.get("compression_mode"), "reason": reason, "alert": False,
            "plan": plan_to_dict(plan) if plan is not None else None}


def _goes_live(deps: _PassDeps, strategy: str) -> bool:
    """Live eligibility; the masked compression strategy must be named in a non-empty allow-list."""
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT
    if deps.mode != "live":
        return False
    if strategy == COMPRESSION_SHORT:
        return strategy in deps.live_allow
    return not deps.live_allow or strategy in deps.live_allow


def _count_plan_none(result: PassResult, frame, strategy, horizon, stamp: dict) -> None:
    """A compression candidate that cleared the decision but built no plan: count why."""
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT
    from swingbot.core.planning.short_builders import compression_rejection_reason
    if strategy == COMPRESSION_SHORT:
        _count_compression_reject(result, stamp, compression_rejection_reason(frame, len(frame) - 1, horizon))


def _dryup_blocked(frame, *, ticker, strategy, direction, horizon) -> bool:
    """Reject scoped pullbacks using the pass's completed daily frame."""
    if not pullback_dryup_blocks(frame, direction, source="strategy", strategy=strategy):
        return False
    log.debug("%s (%s, %s, %s): rejected %s", ticker, horizon, strategy,
              direction, PULLBACK_VOLUME_REASON)
    return True


def _emit_signal(result: PassResult, frame, *, ticker, strategy, direction, horizon,
                 bar_date, regime, deps: _PassDeps) -> None:
    """Store and, when eligible, alert one fired strategy signal."""
    if already_emitted(deps.plan_store, ticker, strategy, horizon, bar_date):
        result.skipped_dup += 1
        return
    if _rs_blocked(ticker, direction, deps.rs_combined_of):
        result.rs_blocked += 1
        return
    if _dryup_blocked(frame, ticker=ticker, strategy=strategy, direction=direction, horizon=horizon):
        result.pullback_volume += 1
        return
    stamp, reject_reason = _compression_context(ticker, strategy, frame, deps)
    if reject_reason:
        _count_compression_reject(result, stamp, reject_reason)
        return
    plan = build_strategy_plan_at(
        frame, ticker=ticker, strategy=strategy, horizon_key=horizon,
        direction=direction, regime2_state=regime,
        asof=deps.asof_of(ticker) if deps.asof_of else None)
    if plan is None:
        _count_plan_none(result, frame, strategy, horizon, stamp)
        return
    plan.entry_context = {**(plan.entry_context or {}), **stamp}
    if not risk_sizing_ok(plan):
        log.error(
            "strategy pass: %s %s %s %s uses structural stops but has no risk-based sizing "
            "-- not stored, not posted (v104 fail-closed)",
            ticker, strategy, horizon, direction)
        result.sizing_blocked += 1
        return
    deps.plan_store.add(plan)
    result.plans.append(plan)
    goes_live = _goes_live(deps, strategy)
    if not goes_live or deps.trade_log.open_trade_for_ticker(ticker) is not None:
        result.stored_only += 1
        return
    _open_trade(deps, plan, ticker=ticker, strategy=strategy, horizon=horizon, direction=direction)
    result.opened += 1
    # v110 §6.1: the simple-channel mirror is an embed like every other alert's.
    result.alerts.append((build_strategy_alert_embed(plan), None, plan,
                          build_strategy_simple_embed(plan)))


def _shadow_step(result: PassResult, frame, *, ticker, horizon, deps: _PassDeps, seen) -> None:
    """The compression shadow evaluation, isolated: a raise here is logged and never costs the ticker's
    remaining horizons or strategies their own signals."""
    try:
        record = compression_shadow_record(frame, ticker=ticker, horizon=horizon, deps=deps,
                                           result=result, seen=seen)
    except Exception:
        log.warning("compression shadow: %s/%s failed -- continuing", ticker, horizon, exc_info=True)
        return
    if record is not None:
        result.compression_shadow.append(record)


def run_strategy_pass(tickers, fresh_data, *, now, horizons, spy_df, regimes,
                      rs_combined_of, mode: str, live_allow: set, trade_log, plan_store,
                      asof_of=None, compression_of=None, earnings_of=None,
                      shadow_seen: set | None = None) -> PassResult:
    """Build strategy plans after confluence; only eligible live plans open trades.

    `shadow_seen`: (ticker, horizon, bar_date) keys of compression shadow records already written; the
    caller loads it so a re-scan of one completed bar records and counts it once."""
    result = PassResult()
    deps = _PassDeps(plan_store, trade_log, mode, live_allow, rs_combined_of, asof_of, compression_of,
                     earnings_of, now)
    for ticker in tickers:
        raw = fresh_data.get(ticker)
        if raw is None or len(raw) == 0:
            continue
        try:
            frame = completed_frame(raw, now)
            if frame is None or len(frame) == 0:
                continue
            bar_date = frame.index[-1].date().isoformat()
            regime = _regime_for(regimes, frame)
            for horizon in horizons:
                for strategy, direction in strategy_signals(frame, horizon, spy_df=spy_df):
                    _emit_signal(result, frame, ticker=ticker, strategy=strategy, direction=direction,
                                 horizon=horizon, bar_date=bar_date, regime=regime, deps=deps)
                _shadow_step(result, frame, ticker=ticker, horizon=horizon, deps=deps,
                             seen=shadow_seen)
        except Exception:
            log.warning("strategy pass: %s failed -- continuing", ticker, exc_info=True)
    return result
