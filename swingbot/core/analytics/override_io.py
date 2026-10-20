"""v173: the I/O around the override-fidelity report -- the inputs, the stored
verdict, and the one evaluation.

`run_daily_check` is the only code that evaluates the frozen pre-registration
and the only writer of its verdict row; the bot's daily loop
(commands/scanning/loops.py:override_verdict_check) is its only caller. The
report script and the admin API import `load_inputs` and `stored_verdict` and
never evaluate. The primary key of `preregistration_verdicts` is the
idempotency authority: once a row exists, nothing is replayed or recomputed.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.analytics import runner_path as rp
from swingbot.core.db.engine import get_engine
from swingbot.core.db.repositories.preregistration_verdicts import verdict_repo

log = logging.getLogger(__name__)

RESULT_RECORDED = "recorded"
RESULT_ALREADY = "already recorded"
RESULT_WAITING = "waiting"
RECORDED_LOG = ("override_verdict_check: %s verdict %s recorded on %s and frozen. "
                "Mirror it into docs/superpowers/results/preregistration-ledger.jsonl: run "
                "scripts/reports/execution_fidelity_report.py --production --mirror-row on the VM, "
                "append the printed line on main and commit (standing procedure in %s).")


def load_inputs() -> tuple[list, dict[str, dict]]:
    """Every plan, and every trade keyed by plan_id (first record wins;
    trades without a plan_id are skipped)."""
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.tracking.performance import TradeLog

    plans = PlanStore().all()
    trades: dict[str, dict] = {}
    for trade in TradeLog().get_trades(status=None, limit=None, ledger=None) or []:
        plan_id = trade.get("plan_id")
        if plan_id and plan_id not in trades:
            trades[plan_id] = trade
    return plans, trades


def stored_verdict(repo=None) -> dict | None:
    """The recorded verdict row for the v173 ledger id, or None."""
    return (repo or verdict_repo()).recorded(of.LEDGER_ID)


def _evaluate(asof: date, inputs_fn, bars_fn) -> dict | None:
    """The stored record when the floors hold, else None."""
    plans, trades = inputs_fn()
    report = ov.build_report(plans, trades, bars_fn, asof, None, config.CURRENCY_SYMBOL)
    if not report["verdict"]["evaluable"]:
        return None
    verdict = ov.evaluate_verdict(report["rows"])
    return ov.verdict_record(verdict, ov.counted(report["rows"]), report["engine_flags"],
                             recorded_on=asof)


def run_daily_check(now: datetime, *, inputs_fn=None, bars_fn=None, repo=None,
                    engine=None) -> str:
    """Evaluate and record the verdict the first time the floors hold; once.
    The existence check and the insert share one transaction; the plan read
    inside it opens its own connection, which is fine: a concurrent second
    insert writes nothing and reports "already recorded"."""
    repo = repo or verdict_repo()
    asof = of.latest_completed_session(now)
    with (engine or get_engine()).begin() as conn:
        if repo.recorded(of.LEDGER_ID, conn=conn) is not None:
            return RESULT_ALREADY
        record = _evaluate(asof, inputs_fn or load_inputs, bars_fn or rp.cached_daily_bars)
        if record is None:
            return RESULT_WAITING
        if not repo.insert_once(record, conn=conn):
            return RESULT_ALREADY
    log.warning(RECORDED_LOG, record["verdict"], of.LEDGER_ID, record["recorded_on"],
                ov.RESULTS_RECORD)
    return RESULT_RECORDED
