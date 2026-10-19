"""v174 § 5: intermarket diagnostics for a context idea's results doc.

Six read-outs printed beside the verdict and never part of it: effective
sample, null overlap, SPY selloff split, per-episode concentration, the
screen-family BH q, and the scope sentence. Nothing here reads or writes a
summary's verdict. Every decide is ``verdict.decide`` looked up at call
time, so a patched decide (the runner tests' 500 resamples) reaches it.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import context as pit
from swingbot.core.backtesting.screen import verdict

EPISODE_GAP = 5    # a new shock episode starts more than 5 sessions after the last shock day
HEADING = "## Intermarket diagnostics (printed, never gating)"
SPEC_FILE = "2026-10-18-v174-intermarket-shock-screens-design.md"
HASH_FILE = "docs/superpowers/results/2026-10-18-v174-context-hashes.json"


# --- dates ------------------------------------------------------------------

def shock_days(idea, data: pit.ContextData, *, event_start: str, event_end: str) -> pd.DatetimeIndex:
    """SPY sessions in [event_start, event_end] where the idea fires on the
    calendar itself (one shock day fires every member with a bar on it)."""
    frames = {name: data.frames[name] for name in idea.context}
    fired = idea.events(data.calendar, frames).reindex(data.calendar.index, fill_value=False)
    days = data.calendar.index[np.asarray(fired, dtype=bool)]
    inside = (days >= pd.Timestamp(event_start)) & (days <= pd.Timestamp(event_end))
    return pd.DatetimeIndex(days[inside])


def signal_days(entry_dates: list[str], sessions: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """The session before each entry date: the signal day t (entry is t+1's
    open). ``pd.NaT`` when no session precedes the entry."""
    sessions = pd.DatetimeIndex(sessions)
    entries = pd.DatetimeIndex(pd.to_datetime(list(entry_dates)))
    positions = sessions.searchsorted(entries, side="left") - 1
    return [sessions[p] if p >= 0 else pd.NaT for p in positions]


def episodes(days: pd.DatetimeIndex, sessions: pd.DatetimeIndex,
             gap: int = EPISODE_GAP) -> list[pd.DatetimeIndex]:
    """Shock days grouped into runs; two days more than ``gap`` sessions
    apart start a new episode."""
    days = pd.DatetimeIndex(sorted(days))
    if not len(days):
        return []
    positions = pd.DatetimeIndex(sessions).get_indexer(days)
    breaks = np.flatnonzero(np.diff(positions) > gap) + 1
    starts, stops = np.r_[0, breaks], np.r_[breaks, len(days)]
    return [days[a:b] for a, b in zip(starts, stops)]


# --- ledger family and scope -------------------------------------------------

def screen_family_q(rows: list[dict], row: dict, instrument: str) -> float | None:
    """BH q of ``row`` across the rows of one instrument only (§ 5.5)."""
    family = [r for r in [*rows, row] if r["instrument"] == instrument]
    return stats.ledger_qvalues(family).get(row["id"])


def scope_sentence(idea) -> str:
    """The frozen-definition wording of spec § What the two shots can and
    cannot say, for the ledger hypothesis and the results doc."""
    p = idea.params
    op = ">=" if p["z"] > 0 else "<="
    return ("Scope: a shock proxy, not Murphy's intermarket claim itself; a fail "
            f"closes exactly this frozen definition ({p['series']} {p['lookback']}-day "
            f"return z {op} {p['z']:+.1f} vs its trailing {p['window']} values, long "
            f"only, the fixed {idea.time_cap_bars}-bar race) and nothing broader: not "
            "intermarket analysis, not a slow-regime test, not a bearish or "
            "longer-horizon variant.")


# --- compute ----------------------------------------------------------------

def _paired(rows) -> list:
    return [verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
            for row in rows]


def _decide(rows):
    """``verdict.decide`` at call time; None for no rows."""
    return verdict.decide(_paired(rows)) if rows else None


def _per_year(days, events) -> dict:
    shock = Counter(day.year for day in days)
    kept = Counter(int(row["entry_date"][:4]) for row in events)
    return {year: (shock.get(year, 0), kept.get(year, 0)) for year in verdict.YEARS}


def _sample(events, days, runs) -> dict:
    return {"n": len(events), "shock_days": len(days), "episodes": len(runs),
            "weeks": len(stats.group_by_week(_paired(events))),
            "per_year": _per_year(days, events)}


def _overlap(events, restricted, cap: int) -> dict:
    return {"cap": cap, "n": len(events),
            "official": verdict.mean_d([], _paired(events)),
            "restricted": None if restricted is None else verdict.decide(_paired(restricted))}


def _bucket(value) -> str:
    if value is None or not np.isfinite(value):
        return "undefined"
    return "down" if value < 0 else "up"


def _selloff(events, signals, days, spy_r5) -> dict:
    groups = {"down": [], "up": [], "undefined": []}
    for row, day in zip(events, signals):
        value = np.nan if pd.isna(day) else spy_r5.get(day, np.nan)
        groups[_bucket(value)].append(row)
    on_shock = spy_r5.reindex(days).dropna()
    return {"shock_down": int((on_shock < 0).sum()), "shock_up": int((on_shock >= 0).sum()),
            "shock_mean": float(on_shock.mean()) if len(on_shock) else None,
            "down": _decide(groups["down"]), "up": _decide(groups["up"]),
            "undefined": len(groups["undefined"])}


def _label(run) -> str:
    first, last = run[0].strftime("%Y-%m-%d"), run[-1].strftime("%Y-%m-%d")
    return first if first == last else f"{first}..{last}"


def _concentration(events, signals, runs) -> dict:
    """Each episode's share of mean(d): sum of its d over the total N."""
    where = {day: i for i, run in enumerate(runs) for day in run}
    sums, counts, unmatched = Counter(), Counter(), 0
    for row, day in zip(events, signals):
        i = None if pd.isna(day) else where.get(day)
        if i is None:
            unmatched += 1
            continue
        sums[i] += row["r_event"] - row["r_null"]
        counts[i] += 1
    rows = sorted(((_label(runs[i]), counts[i], sums[i] / len(events)) for i in counts),
                  key=lambda item: item[2], reverse=True)
    return {"rows": rows, "unmatched": unmatched,
            "delta": verdict.mean_d([], _paired(events))}


def compute(idea, events: list[dict], restricted: list[dict] | None,
            data: pit.ContextData, *, event_start: str, event_end: str) -> dict:
    """The four computed diagnostics (§ 5.1-5.4); q and scope are rendered
    from their own inputs. Pure: ``events`` and ``restricted`` are only read."""
    sessions = data.calendar.index
    days = shock_days(idea, data, event_start=event_start, event_end=event_end)
    runs = episodes(days, sessions)
    signals = signal_days([row["entry_date"] for row in events], sessions)
    spy_r5 = pit.r_lookback(data.calendar["Close"])
    return {"sample": _sample(events, days, runs),
            "overlap": _overlap(events, restricted, idea.time_cap_bars),
            "selloff": _selloff(events, signals, days, spy_r5),
            "concentration": _concentration(events, signals, runs)}


# --- render -------------------------------------------------------------------

def _fmt(value, spec: str = "+.4f") -> str:
    return "n/a" if value is None else format(value, spec)


def _render_data(data, context_start: str, window_start: str) -> list:
    lines = [f"**Context data** (v174 spec `{SPEC_FILE}`): context series loaded from "
             f"{context_start} for the z warm-up; the stock window starts {window_start}. "
             f"Adjusted closes, the bytes pinned by SHA-256 in `{HASH_FILE}`.", "",
             "| Series | rows | first bar | last bar | fetched | SHA-256 |",
             "|---|---|---|---|---|---|"]
    lines += [f"| {r['ticker']} | {r['rows']} | {r['first']} | {r['last']} | "
              f"{r['fetched']} | `{r['sha256']}` |"
              for _, r in sorted(data.records.items())]
    return lines


def _render_sample(sample) -> list:
    lines = ["### 1. Effective sample", "",
             f"Kept ticker events N = {sample['n']}, from {sample['shock_days']} shock days "
             f"in {sample['episodes']} episodes (runs more than {EPISODE_GAP} sessions "
             f"apart) over {sample['weeks']} distinct ISO entry weeks. One shock day fires "
             "every member with a bar, so the screen tests the episodes, not N, and the "
             f"N >= {verdict.MIN_N} clause cannot see that. The week-clustered percentile "
             "bootstrap undercovers with this few clusters, so the lower bound is looser "
             "than nominal.", "",
             "| Year | shock days | kept events |", "|---|---|---|"]
    lines += [f"| {year} | {shocks} | {kept} |"
              for year, (shocks, kept) in sample["per_year"].items()]
    return lines


def _render_overlap(overlap) -> list:
    head = f"Official ΔExpR {_fmt(overlap['official'])}R over N = {overlap['n']}."
    v = overlap["restricted"]
    if v is None:
        return ["### 2. Null overlap", "", head + " Restricted null not run."]
    return ["### 2. Null overlap", "",
            head + f" With the null pool restricted to bars at least {overlap['cap']} "
            "sessions from any shock day (same seed, K and cap; an event left with fewer "
            f"than 5 candidates drops out): ΔExpR {_fmt(v.delta_exp_r)}R, 95% "
            f"week-clustered interval {_fmt(v.ci_low)}R to {_fmt(v.ci_high)}R, N = {v.n}. "
            "The gap shows how far pre-shock and post-shock null races moved the "
            "official figure."]


def _split_row(label: str, v) -> str:
    if v is None:
        return f"| {label} | 0 | n/a | n/a |"
    return (f"| {label} | {v.n} | {_fmt(v.delta_exp_r)}R | "
            f"{_fmt(v.ci_low)}R to {_fmt(v.ci_high)}R |")


def _render_selloff(selloff) -> list:
    mean = selloff["shock_mean"]
    mean_text = "n/a" if mean is None else f"{100.0 * mean:+.2f}%"
    return ["### 3. SPY selloff split", "",
            f"SPY's own 5-day return on the shock days: {selloff['shock_down']} below 0, "
            f"{selloff['shock_up']} at or above 0, mean {mean_text}.", "",
            "| SPY 5-day return at the signal day | N | ΔExpR | 95% interval |",
            "|---|---|---|---|",
            _split_row("< 0", selloff["down"]), _split_row(">= 0", selloff["up"]), "",
            f"Kept events with no SPY 5-day return at their signal day: "
            f"{selloff['undefined']}. A pass carried by the < 0 half is a mean-reversion "
            "effect, not an intermarket one."]


def _render_concentration(conc) -> list:
    top_two = sum(row[2] for row in conc["rows"][:2]) if conc["rows"] else None
    lines = ["### 4. Concentration by shock episode", "",
             "Each episode's contribution to ΔExpR = (sum of its d) / N, largest first. "
             f"ΔExpR {_fmt(conc['delta'])}R; the two largest episodes add "
             f"{_fmt(top_two)}R.", "",
             "| Episode (signal days) | kept events | contribution to ΔExpR |",
             "|---|---|---|"]
    lines += [f"| {label} | {n} | {_fmt(share)}R |" for label, n, share in conc["rows"]]
    return lines + ["", "Kept events whose signal day is no shock day (a gap in the "
                        f"stock's own calendar): {conc['unmatched']}."]


def _render_family(screen_q) -> list:
    return ["### 5. Multiple comparisons", "",
            f"BH q = {_fmt(screen_q, '.4f')} across the `screen-v1` family (this idea "
            "plus every earlier screen row); the head line's q runs across the whole "
            "ledger. Reported, never gating."]


def render(diag: dict, data: pit.ContextData, *, context_start: str, window_start: str,
           screen_q: float | None, scope: str) -> list[str]:
    """The § 5 section as lines; the caller joins them like every other section."""
    parts = [_render_data(data, context_start, window_start),
             _render_sample(diag["sample"]), _render_overlap(diag["overlap"]),
             _render_selloff(diag["selloff"]),
             _render_concentration(diag["concentration"]),
             _render_family(screen_q), ["### 6. Scope", "", scope]]
    lines = [HEADING, "", "None of these lines is a clause of the verdict above; the "
             "verdict is computed exactly as for every other screen."]
    for part in parts:
        lines += [""] + part
    return lines
