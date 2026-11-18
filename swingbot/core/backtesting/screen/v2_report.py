"""v230 A2: what a v2 Δ means, and the v2 descriptive blocks (mean cost per
arm, per-regime means, sector mix). Printed in every v2 results doc; never gating."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

#: (label, first (year, month), last (year, month)); any other entry is REST.
REGIMES = (("2011–2017", (2011, 1), (2017, 12)), ("2018 Q4", (2018, 10), (2018, 12)))
REST = "rest"

#: v1 blocks that re-read the event ticker's own null draw; v2 has none of them.
OMITTED_V2_BLOCKS: tuple[tuple[str, str], ...] = (
    ("restricted", "the v174 null restricted off shock windows redraws from the event "
                   "ticker's own bars"),
    ("stressed", "the v163 2 x slippage trail book re-races the v1 null groups"),
    ("repriced", "the v182 3 x slippage level book re-races the v1 null groups"),
    ("shock", "the v211 shock-day null draws from the event ticker's own SHOCK days"),
    ("control", "the v182 trend-only control book needs a v2 draw of its own, not built "
                "in v230"))

MEANING: dict[str, str] = {
    "ticker": ("Each event's null is K bars from other tickers on the event's own date, in "
               "the same trend state and the same ATR% tercile of that date's eligible "
               "cross-section. Market timing is removed: a pass says the trigger picks "
               "better names than its peers on that day, a different question from v1's "
               "same-ticker, same-month null."),
    "market": ("The trigger fires for every member on one date, so each event's null is the "
               "same ticker in the same trend state on dates in the 252 sessions before the "
               "event, none within the time cap of any of its event dates: a pass says the "
               "event date beats that ticker's own recent dates. No null bar postdates its "
               "event.")}

LOOKAHEAD = ("Every pool value at a date reads that ticker's bars up to that date only, "
             "except race completeness (the race must finish inside the ticker's data), "
             "which reads the data end exactly as v1 does.")


def load_sectors(path) -> dict[str, str] | None:
    """{symbol: sector} from a list of {symbol, sector}; "Unknown" and missing
    sectors are left out. None when the file does not exist."""
    path = Path(path)
    if not path.is_file():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {r["symbol"]: r["sector"] for r in rows
            if r.get("sector") and r["sector"] != "Unknown"}


def _regime(day: str) -> str:
    key = (int(day[:4]), int(day[5:7]))
    for label, first, last in REGIMES:
        if first <= key <= last:
            return label
    return REST


def _mean(rows, key: str) -> float | None:
    return float(np.mean([r[key] for r in rows])) if rows else None


def _arms(rows) -> tuple:
    return len(rows), _mean(rows, "r_event"), _mean(rows, "r_null")


def _grouped(events, key) -> dict[str, list]:
    groups: dict[str, list] = {}
    for row in events:
        groups.setdefault(key(row), []).append(row)
    return groups


def v2_summary(events, *, scope: str, sectors: dict[str, str] | None) -> dict:
    """``events`` are the kept event rows (``r_event``, ``r_null``, ``cost_event``,
    ``cost_null``, ``entry_date``, ``ticker``). Per regime and sector: (N, mean
    R event, mean R null); the sector is the event ticker's, "unmapped" if absent."""
    by_regime = _grouped(events, lambda r: _regime(r["entry_date"]))
    labels = [label for label, _, _ in REGIMES] + [REST]
    sector_mix = None
    if sectors is not None:
        by_sector = _grouped(events, lambda r: sectors.get(r["ticker"], "unmapped"))
        sector_mix = {s: _arms(rows) for s, rows in sorted(by_sector.items())}
    return {"scope": scope,
            "cost": {"event": _mean(events, "cost_event"), "null": _mean(events, "cost_null")},
            "regimes": {label: _arms(by_regime.get(label, [])) for label in labels},
            "sectors": sector_mix}


def _f(x) -> str:
    return "—" if x is None else f"{x:+.4f}"


def _table(title: str, rows: dict) -> list[str]:
    return [title, "", "| | N | mean R event | mean R null |", "|---|---:|---:|---:|",
            *(f"| {k} | {n} | {_f(e)} | {_f(nl)} |" for k, (n, e, nl) in rows.items()), ""]


def render_v2(block: dict) -> list[str]:
    cost = block["cost"]
    lines = ["## Null v2 (v230): what this Δ means", "", MEANING[block["scope"]], "",
             LOOKAHEAD, "",
             f"**Mean cost in R** (gross R − net R): event arm {_f(cost['event'])}, null arm "
             f"{_f(cost['null'])}.", "",
             *_table("**Per regime** (by entry date):", block["regimes"])]
    if block["sectors"] is None:
        lines += ["**Sector mix:** omitted — no sector map was found.", ""]
    else:
        lines += _table("**Sector mix** (the event ticker's sector; `unmapped` = not in the "
                        "map; the null column is those events' nulls):", block["sectors"])
    return lines + ["**Omitted under v2** (each re-reads the v1 same-ticker null draw; none "
                    "gates):", "", *(f"- `{name}`: {why}." for name, why in OMITTED_V2_BLOCKS)]
