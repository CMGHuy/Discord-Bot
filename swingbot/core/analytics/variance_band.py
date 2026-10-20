"""v175 Normal bad luck: the range of losing runs this book's past produces.

Pure functions, no I/O: no store, no TradeLog, no config, no network. The
input is the closed book as trade dicts (``status`` in win/loss/closed,
every ledger, ``scope.select`` never applied: the band is whole-book).

The unit is the **close day**: every trade's R (``metrics.r_multiple``) is
summed per America/New_York close date, so five stop-outs on one gap day
are one loss day. A day is a loss below ``-SCRATCH_R``, a win above
``+SCRATCH_R``, a scratch otherwise. A losing run counts consecutive loss
days; a scratch day neither extends nor breaks it; a win day ends it. The
same rule is used for the bootstrap paths and for the current state.

The close date is the UTC ``closed_at`` converted to ET, deliberately
unlike ``pnl_calendar.day_of``'s UTC slice: an after-hours close belongs
to its NYSE session.

Spec: docs/superpowers/specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, NamedTuple

import numpy as np

from swingbot.core.analytics import metrics
from swingbot.core.backtesting.instrument import stats
from swingbot.core.market.session import US_MARKET_TZ

# Frozen constants (v175 Global Constraints): changing one is a new spec.
MIN_DAYS = 100
MIN_WEEKS = 20
HORIZONS = (20, 50)
WINDOW = 50                       # current-drawdown window, == HORIZONS[-1]
PATHS = 10_000
SEED = stats.WEEK_BOOTSTRAP_SEED
SCRATCH_R = 0.05
ROUGH_PCT = 80
OUTSIDE_PCT = 95
OUTER_RESAMPLES = 200
OUTER_PATHS = 1_000               # inner paths per outer resample (plan choice)
CI_PCT = (10, 90)
EXPR_RESAMPLES = 10_000
EXPR_CI_PCT = (2.5, 97.5)
ZONES = ("normal", "rough", "outside")
CAVEAT = ("This book's past results are not positive. "
          "A run within their range is still a losing run.")

Band = dict[str, Any]


@dataclass(frozen=True)
class CloseDay:
    """One NYSE close date: the net R of every trade closed on it."""

    day: dt.date
    r: float
    kind: str


def et_close_date(closed_at: str) -> dt.date:
    """The America/New_York date of a ``closed_at`` stamp (naive = UTC)."""
    stamp = dt.datetime.fromisoformat(closed_at)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(US_MARKET_TZ).date()


def day_kind(r: float) -> str:
    """``loss`` below -SCRATCH_R, ``win`` above +SCRATCH_R, else ``scratch``."""
    if r < -SCRATCH_R:
        return "loss"
    if r > SCRATCH_R:
        return "win"
    return "scratch"


def _dated_r(trades: list[dict]):
    """(ET close date, R) for every trade with a computable R and a close."""
    for trade in trades:
        closed_at = trade.get("closed_at")
        r = metrics.r_multiple(trade)
        if r is None or not closed_at:
            continue
        yield et_close_date(closed_at), r


def close_days(trades: list[dict]) -> list[CloseDay]:
    """Net R per ET close date, in date order (R rounded to 4 dp)."""
    sums: dict[dt.date, float] = defaultdict(float)
    for day, r in _dated_r(trades):
        sums[day] += r
    out = []
    for day in sorted(sums):
        net = round(sums[day], 4)
        out.append(CloseDay(day, net, day_kind(net)))
    return out


def current_run(days: list[CloseDay]) -> tuple[int, dt.date | None]:
    """Loss days in the run in progress at the last close day, and its first day.

    Walks back from the latest day: a loss day counts, a scratch day is
    passed over, a win day ends the walk. ``(0, None)`` when no run is on."""
    length, first = 0, None
    for close_day in reversed(days):
        if close_day.kind == "win":
            break
        if close_day.kind == "loss":
            length, first = length + 1, close_day.day
    return length, first


def window_drawdown(days: list[CloseDay],
                    window: int = WINDOW) -> tuple[float, dt.date | None]:
    """Peak-to-now drawdown in R inside the last ``window`` close days.

    Cumulative R starts from a 0 baseline at the window's start; the peak is
    the latest highest point (the baseline counts, and is dated to the
    window's first day). Returns ``(drawdown rounded to 2 dp, peak day)``,
    ``(0.0, None)`` when the book is at its window peak."""
    tail = days[-window:]
    if not tail:
        return 0.0, None
    cum, peak, peak_day = 0.0, 0.0, tail[0].day
    for close_day in tail:
        cum += close_day.r
        if cum >= peak:
            peak, peak_day = cum, close_day.day
    drawdown = round(peak - cum, 2)
    if drawdown <= 0:
        return 0.0, None
    return drawdown, peak_day


def zone_of(value: float, p80: float, p95: float) -> str:
    """``normal`` at or below p80, ``rough`` up to p95, ``outside`` beyond.

    With ``p80 == p95`` the rough zone is empty."""
    if value <= p80:
        return "normal"
    if value <= p95:
        return "rough"
    return "outside"


def worse_zone(a: str, b: str) -> str:
    """The later of two zones in ``ZONES`` order."""
    return max(a, b, key=ZONES.index)


# --- Week-block path bootstrap -------------------------------------------


def week_blocks(days: list[CloseDay]) -> list[np.ndarray]:
    """Close-day R grouped by the ISO week of the close date.

    ``days`` is in date order (``close_days`` returns it so), so the weeks
    come out in date order and each week's days stay in date order."""
    weeks: dict[str, list[float]] = {}
    for close_day in days:
        key = stats.iso_week_key(close_day.day.isoformat())
        weeks.setdefault(key, []).append(close_day.r)
    return [np.asarray(rs, dtype=float) for rs in weeks.values()]


def _week_picks(lengths: np.ndarray, h: int, n_paths: int,
                rng: np.random.Generator) -> np.ndarray:
    """Week indices per path, wide enough that every path holds ``h`` days.

    A batch of ``ceil(1.5 * h / mean week length) + 2`` picks per path
    covers ``h`` almost always; another batch of the same width is appended
    to every path while any path is still short (deterministic per seed)."""
    width = int(np.ceil(1.5 * h / lengths.mean())) + 2
    picks = rng.integers(0, len(lengths), size=(n_paths, width))
    while (lengths[picks].sum(axis=1) < h).any():
        more = rng.integers(0, len(lengths), size=(n_paths, width))
        picks = np.hstack([picks, more])
    return picks


def sample_paths(blocks: list[np.ndarray], h: int, n_paths: int,
                 rng: np.random.Generator) -> np.ndarray:
    """``n_paths`` paths of ``h`` close days, each whole weeks drawn with
    replacement and concatenated; the last week is truncated.

    Vectorised: every picked week is laid out end to end in one flat index
    array, then each path keeps its first ``h`` entries."""
    lengths = np.array([len(block) for block in blocks])
    starts = np.cumsum(lengths) - lengths
    flat = np.concatenate(blocks)
    picks = _week_picks(lengths, h, n_paths, rng)
    pick_lens = lengths[picks]
    seg_lens = pick_lens.ravel()
    seg_offsets = np.cumsum(seg_lens) - seg_lens
    day_index = (np.repeat(starts[picks].ravel() - seg_offsets, seg_lens)
                 + np.arange(int(seg_lens.sum())))
    row_lens = pick_lens.sum(axis=1)
    row_starts = np.cumsum(row_lens) - row_lens
    take = row_starts[:, None] + np.arange(h)[None, :]
    return flat[day_index[take]]


def path_longest_runs(paths: np.ndarray) -> np.ndarray:
    """Longest losing run per path: a loss day extends it, a scratch day
    neither extends nor breaks it, a win day ends it (``current_run``'s rule)."""
    current = np.zeros(len(paths), dtype=int)
    best = current.copy()
    for column in paths.T:
        current = np.where(column < -SCRATCH_R, current + 1,
                           np.where(column > SCRATCH_R, 0, current))
        best = np.maximum(best, current)
    return best


def path_max_drawdowns(paths: np.ndarray) -> np.ndarray:
    """Maximum drawdown per path in R: running peak of cumulative R (0
    baseline) minus cumulative R."""
    cum = np.cumsum(paths, axis=1)
    peak = np.maximum.accumulate(np.maximum(cum, 0.0), axis=1)
    return (peak - cum).max(axis=1)


def _run_q(values, pct: float) -> int:
    return int(np.percentile(values, pct, method="higher"))


def _dd_q(values, pct: float) -> float:
    return round(float(np.percentile(values, pct)), 2)


def _quantiles(values, outer_p95s, q) -> dict:
    """p80/p95 of the main draw and the CI_PCT range of the outer p95s."""
    return {"p80": q(values, ROUGH_PCT), "p95": q(values, OUTSIDE_PCT),
            "p95_lo": q(outer_p95s, CI_PCT[0]), "p95_hi": q(outer_p95s, CI_PCT[1])}


def _outer_p95s(blocks: list[np.ndarray], h: int, outer: int, outer_paths: int,
                rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """p95 run and p95 drawdown of ``outer`` resampled week sets."""
    runs, drawdowns = [], []
    for _ in range(outer):
        picks = rng.integers(0, len(blocks), size=len(blocks))
        inner = sample_paths([blocks[i] for i in picks], h, outer_paths, rng)
        runs.append(np.percentile(path_longest_runs(inner), OUTSIDE_PCT,
                                  method="higher"))
        drawdowns.append(np.percentile(path_max_drawdowns(inner), OUTSIDE_PCT))
    return np.asarray(runs), np.asarray(drawdowns)


def horizon_band(blocks: list[np.ndarray], h: int, *, paths: int = PATHS,
                 outer: int = OUTER_RESAMPLES, outer_paths: int = OUTER_PATHS,
                 seed: int = SEED) -> dict:
    """The band for one horizon: p80/p95 of the longest losing run and of the
    maximum drawdown over ``h`` close days, with p95's own uncertainty.

    One generator per call: the main draw first, then the outer resamples,
    so a seed reproduces the whole band. ``outer`` must be at least 1."""
    rng = np.random.default_rng(seed)
    main = sample_paths(blocks, h, paths, rng)
    outer_runs, outer_dds = _outer_p95s(blocks, h, outer, outer_paths, rng)
    return {
        "horizon": h,
        "run": _quantiles(path_longest_runs(main), outer_runs, _run_q),
        "drawdown": _quantiles(path_max_drawdowns(main), outer_dds, _dd_q),
    }


# --- The band -------------------------------------------------------------


class _RItem(NamedTuple):
    """A trade as ``stats.week_cluster_bootstrap`` sees it: week of the close."""

    entry_date: str
    r: float


def era_of(trade: dict) -> str:
    """``v2`` for a trade linked to a plan, ``legacy`` (v1) otherwise."""
    return "v2" if trade.get("plan_id") else "legacy"


def _week_count(days: list[CloseDay]) -> int:
    return len({stats.iso_week_key(d.day.isoformat()) for d in days})


def _enough(days: list[CloseDay]) -> bool:
    return len(days) >= MIN_DAYS and _week_count(days) >= MIN_WEEKS


def _usable(closed: list[dict]) -> list[dict]:
    """Trades with a close stamp and a computable R; the rest are skipped."""
    return [t for t in closed
            if t.get("closed_at") and metrics.r_multiple(t) is not None]


def pool_trades(closed: list[dict]) -> tuple[list[dict], str]:
    """The v2 trades once they alone reach the floor, else the whole book."""
    v2 = [t for t in closed if era_of(t) == "v2"]
    if _enough(close_days(v2)):
        return v2, "v2"
    return list(closed), "all"


def composition(closed: list[dict]) -> dict:
    """Close days per era and trades per horizon, over the whole book."""
    days_by_era = {era: len(close_days([t for t in closed if era_of(t) == era]))
                   for era in ("v2", "legacy")}
    horizons = Counter(t.get("horizon_key") or "unknown" for t in closed)
    return {"days_by_era": days_by_era, "trades_by_horizon": dict(sorted(horizons.items()))}


def _mean_r(draw: list, _component=()) -> float | None:
    if not draw:
        return None
    return sum(item.r for item in draw) / len(draw)


def _r_items(pool: list[dict]) -> list[_RItem]:
    """Sorted, so the input order never changes the bootstrap draw."""
    items = []
    for trade in pool:
        r = metrics.r_multiple(trade)
        closed_at = trade.get("closed_at")
        if r is not None and closed_at:
            items.append(_RItem(et_close_date(closed_at).isoformat(), r))
    return sorted(items)


def _expr_ci(pool: list[dict]) -> list[float] | None:
    """EXPR_CI_PCT interval of mean R, resampling weeks of the close date."""
    draws = stats.week_cluster_bootstrap(_r_items(pool), (), _mean_r,
                                         n_resamples=EXPR_RESAMPLES,
                                         seed=stats.WEEK_BOOTSTRAP_SEED)
    if draws.size == 0:
        return None
    lo, hi = np.percentile(draws, EXPR_CI_PCT)
    return [round(float(lo), 3), round(float(hi), 3)]


def expr_block(pool: list[dict], days: list[CloseDay]) -> dict:
    """The pool's ExpR with N, window and week-cluster interval, re-derived
    on every call; ``not_positive`` drives the caveat."""
    raw = metrics.expectancy_r(pool)
    value = None if raw is None else round(raw, 3)
    ci = _expr_ci(pool)
    not_positive = (value is None or value <= 0
                    or (ci is not None and ci[0] <= 0 <= ci[1]))
    return {"value": value, "n": len(metrics.r_multiples(pool)),
            "start": days[0].day.isoformat() if days else None,
            "end": days[-1].day.isoformat() if days else None,
            "ci": ci, "not_positive": not_positive}


def _dollar_risk(trade: dict) -> float | None:
    """shares x |entry - stop_loss| (the v170 basis), None when unknown."""
    shares, entry, stop = trade.get("shares"), trade.get("entry"), trade.get("stop_loss")
    if not shares or entry is None or stop is None:
        return None
    risk = float(shares) * abs(entry - stop)
    return risk if risk > 0 else None


def dollars_block(pool: list[dict], drawdown: float) -> dict | None:
    """The drawdown in dollars at the median per-trade risk; None when no
    pool trade has a dollar risk (the band then omits the key)."""
    risks = [risk for trade in pool if (risk := _dollar_risk(trade)) is not None]
    if not risks:
        return None
    median = round(float(np.median(risks)), 2)
    return {"median_risk": median, "drawdown_usd": round(drawdown * median, 2)}


def _age(start: dt.date | None, asof: dt.date) -> int | None:
    return None if start is None else (asof - start).days + 1


def current_state(days: list[CloseDay], band50: dict) -> dict:
    """The run and window drawdown now, each placed against the 50-day band."""
    asof = days[-1].day
    run, run_start = current_run(days)
    drawdown, peak_day = window_drawdown(days)
    run_zone = zone_of(run, band50["run"]["p80"], band50["run"]["p95"])
    drawdown_zone = zone_of(drawdown, band50["drawdown"]["p80"], band50["drawdown"]["p95"])
    return {"run": run, "run_age_days": _age(run_start, asof),
            "drawdown": drawdown, "drawdown_age_days": _age(peak_day, asof),
            "run_zone": run_zone, "drawdown_zone": drawdown_zone,
            "zone": worse_zone(run_zone, drawdown_zone)}


def _horizon_entry(blocks: list[np.ndarray], h: int, n_days: int,
                   sizes: dict) -> dict:
    entry = horizon_band(blocks, h, **sizes)
    return {**entry, "weeks_span": round(h * len(blocks) / n_days, 1)}


def variance_band(closed: list[dict], *, paths: int = PATHS,
                  outer: int = OUTER_RESAMPLES,
                  outer_paths: int = OUTER_PATHS) -> Band:
    """The whole-book band, or ``insufficient`` below the floor.

    ``closed`` is the closed book (every ledger, no scope applied)."""
    usable = _usable(closed)
    book_days = close_days(usable)
    if not _enough(book_days):
        return {"status": "insufficient", "scope": "whole_book",
                "days": len(book_days), "weeks": _week_count(book_days)}
    pool, pool_name = pool_trades(usable)
    days = close_days(pool)
    blocks = week_blocks(days)
    sizes = {"paths": paths, "outer": outer, "outer_paths": outer_paths}
    horizons = [_horizon_entry(blocks, h, len(days), sizes) for h in HORIZONS]
    current = current_state(days, horizons[-1])
    band: Band = {"status": "ok", "scope": "whole_book", "asof": days[-1].day.isoformat(),
                  "days": len(days), "weeks": len(blocks), "pool": pool_name,
                  "composition": composition(usable), "horizons": horizons,
                  "current": current, "expr": expr_block(pool, days)}
    dollars = dollars_block(pool, current["drawdown"])
    if dollars is not None:
        band["dollars"] = dollars
    return band
