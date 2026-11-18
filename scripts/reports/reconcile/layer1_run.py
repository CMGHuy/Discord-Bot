"""v232 layer 1 runner: one TradeRow per exported plan (spec ### Populations, ### Layer 1).

Only a closed, scored row carries backtest values, effects and tags. Unfilled rows keep
would_fill booleans; still-open rows keep nothing from the backtest (holdout).
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from . import layer1, raw_bars, records, sessions, tags

REFUSALS = raw_bars.REFUSALS + ("no_journal", "zero_risk", "no_fill_bar")


@dataclasses.dataclass(frozen=True)
class TradeRow:
    trade_id: str | None
    plan_id: str
    ticker: str
    strategy: str | None
    horizon_key: str | None
    ledger: str
    side: str
    era: str
    klass: str
    refusal: str | None
    entry_date: str
    stamp_source: str
    issue_bucket: str
    r_live_gross: float | None
    cost_r: float | None
    r_live_net: float | None
    values: dict
    effects: dict
    tags: tuple
    gap: dict | None
    entry_slip: tuple | None
    poll_fill: tuple | None
    live_class: str | None
    unfilled_reason: str | None
    would_fill: dict

    @property
    def scored(self) -> bool:
        return self.klass == "closed" and self.refusal is None

    def to_dict(self) -> dict:
        out = dataclasses.asdict(self)
        for key in ("tags", "entry_slip", "poll_fill"):
            out[key] = None if out[key] is None else list(out[key])
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "TradeRow":
        data = {f.name: d.get(f.name) for f in dataclasses.fields(cls)}
        data["tags"] = tuple(data["tags"] or ())
        for key in ("entry_slip", "poll_fill"):
            data[key] = None if data[key] is None else tuple(data[key])
        for key in ("values", "effects", "would_fill"):
            data[key] = data[key] or {}
        return cls(**data)


def _common(rec) -> dict:
    stamp, source = sessions.stamp_source(rec.plan)
    trade = rec.trade
    entry_day = (sessions.ny_time(trade["opened_at"]).date() if trade
                 else sessions.issue_session(stamp))
    return dict(trade_id=trade.get("trade_id") if trade else None, plan_id=rec.plan_id,
                ticker=rec.ticker, strategy=rec.plan.get("strategy"),
                horizon_key=rec.plan.get("horizon_key"), ledger=records.ledger_of(rec),
                side=rec.side, era=records.era_of(rec), klass=records.class_of(rec),
                refusal=None, entry_date=entry_day.isoformat(), stamp_source=source,
                issue_bucket=sessions.issue_bucket(stamp), r_live_gross=None, cost_r=None,
                r_live_net=None, values={}, effects={}, tags=(), gap=None, entry_slip=None,
                poll_fill=None, live_class=None, unfilled_reason=None, would_fill={})


def _first_day(rec) -> dt.date:
    signal = sessions.issue_session(sessions.stamp_source(rec.plan)[0])
    if rec.trade is None:
        return signal
    return min(signal, sessions.issue_session(rec.trade["opened_at"]))


def _exit_day(rec) -> dt.date | None:
    closed = (rec.trade or {}).get("closed_at")
    return sessions.ny_time(closed).date() if closed else None


def _unfilled(rec, bars, row: dict, start) -> dict:
    raw, split = bars(rec.ticker)
    refused = raw_bars.refusal(raw, split, start=start or _first_day(rec), last_exit=None)
    fills = {m: None if refused else layer1.would_fill(rec, raw, m) for m in layer1.FILL_MODELS}
    return {**row, "refusal": refused, "unfilled_reason": records.unfilled_reason(rec),
            "would_fill": fills}


def _live(rec, row: dict, frictions: dict) -> dict:
    gross = layer1.r_live(rec)
    cost = layer1.live_cost_r(rec, frictions)
    return {**row, "r_live_gross": gross, "cost_r": cost, "r_live_net": gross - cost,
            "live_class": layer1.outcome_class(rec.journal.get("outcome"), gross)}


def _scored(rec, raw, row: dict) -> dict:
    values = {m: layer1.score(rec, raw, m) for m in layer1.FILL_MODELS}
    gross, v1 = row["r_live_gross"], values["v1"]
    fill_pos = layer1.bar_position(raw, sessions.issue_session(rec.trade["opened_at"]))
    exit_pos = layer1.bar_position(raw, sessions.issue_session(rec.trade["closed_at"]))
    t = tags.TagInput(rec, raw, fill_pos, exit_pos, layer1.live_risk(rec), gross,
                      v1.r_exit_only, row["live_class"], v1.exit_only_class)
    return {**row, "values": {m: dataclasses.asdict(v) for m, v in values.items()},
            "effects": {m: layer1.effects(gross, v) for m, v in values.items()},
            "tags": tags.tags_for(t), "gap": tags.gap_detail(t),
            "entry_slip": tags.entry_slip(t), "poll_fill": tags.poll_fill(t)}


def _closed(rec, bars, row: dict, frictions: dict, start, last_exit) -> dict:
    if rec.journal is None or rec.journal.get("r_realized") is None:
        return {**row, "refusal": "no_journal"}       # no journal R: no live R, counted at 0R
    try:
        layer1.live_risk(rec)
    except ValueError:
        return {**row, "refusal": "zero_risk"}
    row = _live(rec, row, frictions)
    if row["klass"] == "manual":
        return row
    raw, split = bars(rec.ticker)
    refused = raw_bars.refusal(raw, split, start=start or _first_day(rec),
                               last_exit=last_exit or _exit_day(rec))
    if refused:
        return {**row, "refusal": refused}
    try:
        return _scored(rec, raw, row)
    except ValueError:
        return {**row, "refusal": "no_fill_bar"}


def row_for(rec, bars, *, frictions: dict, start: dt.date | None = None,
            last_exit: dt.date | None = None) -> TradeRow:
    """One plan's row; `bars(ticker)` returns (raw frame, split-adjusted frame)."""
    row = _common(rec)
    if row["klass"] == "unfilled":
        return TradeRow(**_unfilled(rec, bars, row, start))
    if row["klass"] == "still_open":
        return TradeRow(**row)
    return TradeRow(**_closed(rec, bars, row, frictions, start, last_exit))


PROGRESS_EVERY = 25


def _last_exits(export) -> dict[str, dt.date]:
    latest: dict[str, dt.date] = {}
    for rec in export.records:
        day = _exit_day(rec)
        if day is not None and (rec.ticker not in latest or day > latest[rec.ticker]):
            latest[rec.ticker] = day
    return latest


def _memo(bars):
    cache: dict = {}

    def get(ticker: str):
        if ticker not in cache:
            cache[ticker] = bars(ticker)
        return cache[ticker]
    return get


def run_layer1(export, bars, checkpoint, *, frictions: dict, start: dt.date,
               out=print) -> list[TradeRow]:
    """Score every exported plan once, appending each row; a restart skips finished plans."""
    cached, last_exits = _memo(bars), _last_exits(export)
    total = len(export.records)
    done = checkpoint.done()
    todo = [rec for rec in export.records if rec.plan_id not in done]
    out(f"layer 1: {total - len(todo)}/{total} trades already scored, {len(todo)} to go")
    for n, rec in enumerate(todo, 1):
        row = row_for(rec, cached, frictions=frictions, start=start,
                      last_exit=last_exits.get(rec.ticker))
        checkpoint.append(rec.plan_id, row.to_dict())
        if n % PROGRESS_EVERY == 0 or n == len(todo):
            finished = total - len(todo) + n
            out(f"layer 1: {finished}/{total} trades ({100.0 * finished / total:.0f}%)")
    by_plan = {d["plan_id"]: TradeRow.from_dict(d) for d in checkpoint.rows()}
    return [by_plan[rec.plan_id] for rec in export.records if rec.plan_id in by_plan]
