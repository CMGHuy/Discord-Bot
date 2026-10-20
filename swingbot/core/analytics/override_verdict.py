"""v173 §4: the frozen verdict on manual overrides, its stored record, the
jsonl mirror line, and the report payload.

The rule is frozen in the spec and evaluated once. Population: individual
(not bulk), not approx, resolved rows. It becomes evaluable when there are
>= VERDICT_FLOOR of them over >= WEEK_FLOOR ISO weeks, no eligible row is
still open, and excluded statuses are <= EXCLUDED_CAP of the eligible rows.
The bot's daily job (override_io.run_daily_check) is the only caller of
evaluate_verdict; it stores verdict_record() in preregistration_verdicts,
whose primary key makes the write happen once. Every reader shows that
record and never recomputes it: watching a live interval until it crosses
zero inflates false positives.

Pure: no store, no network, no file reads. build_report takes its inputs
from the caller and never evaluates.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.analytics import override_fidelity as ofi
from swingbot.core.backtesting.instrument import stats

log = logging.getLogger(__name__)

RESULTS_RECORD = "docs/superpowers/results/v173-override-fidelity.md"   # created by V173-11
WAITING = "WAITING"
COST, SAVED, INCONCLUSIVE = "COST", "SAVED", "INCONCLUSIVE"
_EVALUATED = (COST, SAVED, INCONCLUSIVE)
_WAITING_ITEMS = ("count", "weeks", "open", "excluded")
_HYPOTHESIS = ("Manual overrides vs the v2 engine: mean delta R, "
               "week-cluster bootstrap 95% CI [{lo:.3f}, {hi:.3f}]")
_RECORDED_FIELDS = ("n", "weeks", "mean_delta_r", "mean_delta_r_gross", "ci",
                    "sum_delta_r", "sum_delta_usd", "bar_close_n")


@dataclass(frozen=True)
class _View:
    """The fields the rule reads, from an OverrideRow or its to_dict() form.
    `entry_date` is the name stats.group_by_week reads."""
    bulk: bool
    approx: bool
    status: str
    price_source: str
    delta_r: float | None
    delta_r_gross: float | None
    delta_usd: float | None
    entry_date: date | None


def _field(row, name: str):
    return row.get(name) if isinstance(row, dict) else getattr(row, name)


def _day(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _view(row) -> _View:
    return _View(bulk=bool(_field(row, "bulk")), approx=bool(_field(row, "approx")),
                 status=_field(row, "status"), price_source=_field(row, "price_source"),
                 delta_r=_field(row, "delta_r"), delta_r_gross=_field(row, "delta_r_gross"),
                 delta_usd=_field(row, "delta_usd"),
                 entry_date=_day(_field(row, "close_date")))


def _as_dict(row) -> dict:
    return dict(row) if isinstance(row, dict) else row.to_dict()


def _is_eligible(view: _View) -> bool:
    return not view.bulk and not view.approx


def _is_counted(view: _View) -> bool:
    return _is_eligible(view) and view.status == "resolved"


def eligible(rows) -> list:
    """The given rows that are individual and not approx, in order."""
    return [r for r in rows if _is_eligible(_view(r))]


def counted(rows) -> list:
    """The given rows in the verdict population (eligible and resolved), in order."""
    return [r for r in rows if _is_counted(_view(r))]


def _excluded_share(elig: list[_View]) -> float:
    excluded = sum(1 for v in elig if v.status in ofi.EXCLUDED_STATUSES)
    return excluded / len(elig) if elig else 0.0


def conditions(rows) -> dict:
    """The four frozen floors, live: `waiting_on` lists the failing ones in
    the order ("count", "weeks", "open", "excluded"); [] exactly when evaluable."""
    elig = [v for v in map(_view, rows) if _is_eligible(v)]
    population = [v for v in elig if v.status == "resolved"]
    n = len(population)
    weeks = len({stats.iso_week_key(v.entry_date) for v in population})
    open_n = sum(1 for v in elig if v.status == "open")
    share = _excluded_share(elig)
    checks = {"count": n >= ofi.VERDICT_FLOOR, "weeks": weeks >= ofi.WEEK_FLOOR,
              "open": open_n == 0, "excluded": share <= ofi.EXCLUDED_CAP}
    waiting_on = [key for key in _WAITING_ITEMS if not checks[key]]
    return {"n": n, "weeks": weeks, "open_n": open_n, "excluded_share": share,
            "evaluable": not waiting_on, "waiting_on": waiting_on}


def _mean_delta(baseline, _component) -> float | None:
    """The bootstrap statistic: mean ΔR of one draw; None drops an empty draw."""
    return float(np.mean([v.delta_r for v in baseline])) if baseline else None


def _state_for(lo: float, hi: float) -> str:
    if hi < 0:
        return COST
    if lo > 0:
        return SAVED
    return INCONCLUSIVE


def _mean(values: list) -> float | None:
    return round(float(np.mean(values)), 3) if values else None


def _sums(population: list[_View]) -> dict:
    """Mean ΔR (net and before costs), ΣΔR and Σ$ over the counted views."""
    gross = [v.delta_r_gross for v in population if v.delta_r_gross is not None]
    usd = [v.delta_usd for v in population if v.delta_usd is not None]
    return {"mean_delta_r": _mean([v.delta_r for v in population]),
            "mean_delta_r_gross": _mean(gross),
            "sum_delta_r": round(sum(v.delta_r for v in population), 3),
            "sum_delta_usd": round(sum(usd), 2) if usd else None}


def _bar_close_n(views) -> int:
    return sum(1 for v in views if _is_counted(v) and v.price_source == "bar_close")


def evaluate_verdict(rows) -> dict:
    """The one evaluation (only override_io.run_daily_check calls it): the
    week-clustered bootstrap of mean ΔR, seeded, and its 95% interval.
    Raises ValueError unless conditions() holds."""
    cond = conditions(rows)
    if not cond["evaluable"]:
        raise ValueError("override verdict not evaluable; waiting on "
                         + ", ".join(cond["waiting_on"]))
    population = [v for v in map(_view, rows) if _is_counted(v)]
    draws = stats.week_cluster_bootstrap(population, (), _mean_delta,
                                         n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES,
                                         seed=stats.WEEK_BOOTSTRAP_SEED)
    lo, hi = (float(x) for x in np.percentile(draws, [2.5, 97.5]))
    return {"state": _state_for(lo, hi), "n": cond["n"], "weeks": cond["weeks"],
            **_sums(population), "ci": [round(lo, 3), round(hi, 3)],
            "bar_close_n": _bar_close_n(population),
            "excluded_share": round(cond["excluded_share"], 4)}


def verdict_record(verdict: dict, rows: list, engine_flags: dict, *,
                   recorded_on: date) -> dict:
    """The stored record (preregistration_verdicts): the evaluated figures,
    the engine flags in force and the counted rows, JSON-ready."""
    if verdict.get("state") not in _EVALUATED:
        raise ValueError(f"only an evaluated verdict is recorded, got {verdict.get('state')!r}")
    figures = {key: verdict[key] for key in (*_RECORDED_FIELDS, "excluded_share")}
    figures["ci"] = list(verdict["ci"])
    return {"ledger_id": ofi.LEDGER_ID, "verdict": verdict["state"],
            "recorded_on": recorded_on.isoformat(), **figures,
            "engine_flags": dict(engine_flags),
            "rows": [_as_dict(r) for r in counted(rows)]}


def mirror_ledger_row(record: dict) -> dict:
    """The jsonl line for the standing mirror procedure (results doc, V173-11);
    no bot code writes the ledger file."""
    lo, hi = record["ci"]
    entry = {"id": record["ledger_id"], "date": record["recorded_on"],
             "hypothesis": _HYPOTHESIS.format(lo=lo, hi=hi), "instrument": "v2",
             "n": int(record["n"]), "exp_r": float(record["mean_delta_r"]), "p": None,
             "verdict": record["verdict"], "record": RESULTS_RECORD}
    stats.validate_ledger_row(entry)
    return entry


def verdict_payload(rows, recorded: dict | None) -> dict:
    """What the API, the script and the report show. Never evaluates: the
    state is the stored record's verdict, or WAITING; the floors stay live."""
    cond = conditions(rows)
    live = {"needed": ofi.VERDICT_FLOOR, "week_floor": ofi.WEEK_FLOOR,
            "open_n": cond["open_n"], "excluded_share": round(cond["excluded_share"], 4),
            "evaluable": cond["evaluable"], "waiting_on": list(cond["waiting_on"])}
    if recorded is not None:
        return {"state": recorded["verdict"], **live, "recorded": True,
                "recorded_on": recorded["recorded_on"],
                **{key: recorded[key] for key in _RECORDED_FIELDS}}
    return {"state": WAITING, **live, "recorded": False, "recorded_on": None,
            "n": cond["n"], "weeks": cond["weeks"], "mean_delta_r": None,
            "mean_delta_r_gross": None, "ci": None, "sum_delta_r": None,
            "sum_delta_usd": None, "bar_close_n": _bar_close_n(map(_view, rows))}


def _bars_for(bars_fn: Callable[[str], pd.DataFrame | None], ticker: str,
              cache: dict) -> pd.DataFrame | None:
    """One cache read per ticker; an unreadable file is an unreplayable row."""
    if ticker not in cache:
        try:
            cache[ticker] = bars_fn(ticker)
        except Exception as exc:   # noqa: BLE001 -- one bad file never fails the report
            log.warning("override_verdict: bars for %s unreadable: %s", ticker, exc)
            cache[ticker] = None
    return cache[ticker]


def engine_flags() -> dict:
    """The exit-engine flags in force, read live; echoed and stored."""
    return {"stall_exit_enabled": bool(config.STALL_EXIT_ENABLED),
            "runner_structure_exit": str(config.RUNNER_STRUCTURE_EXIT)}


def build_report(plans: list, trades_by_plan: dict[str, dict],
                 bars_fn: Callable[[str], pd.DataFrame | None], asof: date,
                 recorded: dict | None, currency_symbol: str) -> dict:
    """The report payload (index § Report payload). Replays every manual
    close, newest first; the verdict is the stored record's or WAITING."""
    cache: dict = {}
    trades = trades_by_plan or {}
    rows = [ofi.replay_override(p, _bars_for(bars_fn, p.ticker, cache), asof,
                                trades.get(p.plan_id))
            for p in plans if ofi.is_override(p)]
    rows.sort(key=lambda r: (r.close_date or date.min, r.plan_id), reverse=True)
    return {"rows": [r.to_dict() for r in rows], "summary": ofi.summarise(rows),
            "verdict": verdict_payload(rows, recorded), "engine_flags": engine_flags(),
            "asof": asof.isoformat(), "currency_symbol": currency_symbol}
