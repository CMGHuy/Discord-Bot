#!/usr/bin/env python3
"""v34 Task 7: what the relative-strength gate costs and buys on TRAIN --
threshold grid, bullish/bearish split, and sector RS's marginal contribution.

WHY NOT tune_strategy.py / run_backtest_range.py (the brief's Step 1
command): those grid a STRATEGY's entry-filter parameters through
`swingbot.core.backtesting.backtest`, a replay harness that never calls
`swingbot.core.scanning.engine` and has no notion of RS_LEADER_PERCENTILE /
RS_LAGGARD_PERCENTILE. v34's gate lives in `_sync_run_scan`'s merge loop
(engine.py, Task 6), so that harness cannot see it by any code path -- the
exact "unmeasurable by construction" failure DATA_DRIVEN_STOPS_ENABLED is a
closed pre-registration for. This script follows v33 Task 7's precedent
(`measure_adjacent_gate_effect.py`) instead: record, per TRAIN trade entry
bar, exactly the RS readings the gate keys on, then SIMULATE the gate's real
decision rule on them.

The simulated gate is the real gate (engine.py + edge/rs_gate.py):
  - RS-ineligible symbols (index / fx / future, marketdata/asset_class.py)
    are EXEMPT and always kept. Exempt is not a pass.
  - bullish: keep iff rs >= leader ; bearish: keep iff rs <= laggard.
  - the value gated on is `rs_combined` = rs_score(ticker_pctile,
    sector_pctile) = 0.7/0.3, falling back to the ticker-only percentile when
    this ticker's own sector ETF is unavailable -- `_apply_sector_rs`'s rule,
    reproduced here including its ticker-specific guard.

RS readings are point-in-time and reproduce the live formulas exactly:
  ticker pctile : `edge/factors.py::rs_percentile` = 100 * mean(rel >= r for
                  r in universe rels), i.e. a max-method cross-sectional rank
                  over the watchlist, on `relative_return` = the ticker's
                  W-bar return minus SPY's over the same W bars.
  sector pctile : `edge/factors.py::sector_rs_percentile` = the same rank of
                  this ticker's sector ETF among the fetched sector ETFs.
Both are vectorized over the whole history as rank panels; `--verify-rs`
asserts the panels reproduce the real functions bar for bar before any
number below is trusted (the NO-LOOKAHEAD / same-instrument guard v33's EMA
check plays for the trend gate).

NO-LOOKAHEAD: every reading at entry bar `d` is `Close[d]/Close[d-W] - 1`,
which touches no bar after `d`. Nothing is forward-filled or resampled.

WINDOW: the live path computes `rs_pctile` ONCE PER TICKER with the default
`RS_WINDOW = 63` (engine.py:958) for every horizon. `HORIZONS[hk]["rs_window"]`
(v34 Task 3) currently has zero consumers, so the shipped gate is a 63-day
gate. `w63` is therefore the primary arm; the per-horizon arm (`whz`) is
reported as secondary evidence for a future spec, never as the shipped gate.

SELECTION RULE, stated before the grid was read (the anti-dredging
commitment -- v32 and v33 both FAILed VALIDATION off favourable-looking
TRAIN point estimates):
  1. The two arms are INDEPENDENT by construction: the bullish arm's keep
     rule reads only `leader`, the bearish arm's only `laggard`. Each
     threshold is therefore chosen from its own arm's 5 cells, not from the
     25-cell product (which is just their outer product).
  2. Within an arm: among thresholds whose arm volume loss is <= 30% (the
     plan's budget), pick the largest delta-WR. Ties -> the lower volume loss.
  3. If an arm's best delta-WR is <= 0, that arm gets NO gate -- the honest
     outcome is a one-sided gate, not a symmetric one for tidiness.
  4. Separation is reported, never used to pick: if the chosen cell's
     before/after Wilson intervals overlap, the choice is a point estimate
     inside noise and must be written up as such.
  5. Sector RS is KEPT only if the `rs_combined` arm beats the ticker-only
     `rs` arm at the chosen thresholds on delta-WR. Otherwise Task 5's wiring
     is reverted -- shipping unused wiring is what this spec family exists to
     stop.

TRAIN by default. `--validation` exists for v34 Task 8's ONE pre-registered
shot and for nothing else -- do not run it to "check" anything.

Prints one flushed line per ticker (CLAUDE.md).

Run: python scripts/backtest/measure_rs_gate_effect.py --train \
         --cache-dir <main checkout>/data/backtest_cache --json data/v34_train.json
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest  # noqa: E402
from swingbot.core.edge import factors as rs_factors  # noqa: E402
from swingbot.core.marketdata import universe  # noqa: E402
from swingbot.core.marketdata.asset_class import is_rs_eligible  # noqa: E402
from swingbot.core.marketdata.backtest_cache import cache_path  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402

CACHE_DIR = ROOT / "data" / "backtest_cache"
TRAIN = ("2020-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")  # verbatim run_backtest_range.py

HKEYS = list(HORIZONS)
BENCHMARK = "SPY"

# The brief's grid.
LEADERS = (55, 60, 65, 70, 75)
LAGGARDS = (25, 30, 35, 40, 45)

# Plan budget: the gate may not cost more than this share of alert volume.
VOLUME_BUDGET_PCT = 30.0

RS_WINDOWS = sorted({rs_factors.RS_WINDOW} |
                    {HORIZONS[hk]["rs_window"] for hk in HKEYS})


# --------------------------------------------------------------------------
# statistics (verbatim copies -- see measure_trend_signal_overlap.py's note on
# why these are copied rather than imported between independent instruments)
# --------------------------------------------------------------------------
def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple:
    if n <= 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _wins_and_evaluated(rows: list) -> tuple:
    ev = [r for r in rows if r["outcome"] in ("win", "loss")]
    return sum(1 for r in ev if r["outcome"] == "win"), len(ev)


def _wr_block(rows: list) -> dict:
    wins, n_ev = _wins_and_evaluated(rows)
    lo, hi = wilson_interval(wins, n_ev)
    rs = [r["r_multiple"] for r in rows if r["r_multiple"] is not None]
    return {"scenarios": len(rows), "evaluated": n_ev, "wins": wins,
            "wr": wins / n_ev if n_ev else 0.0, "wilson": [lo, hi],
            # methodology's second acceptance gate: expectancy over ALL
            # closed trades, not just win/loss.
            "expectancy_r": float(np.mean(rs)) if rs else 0.0}


# --------------------------------------------------------------------------
# RS panels
# --------------------------------------------------------------------------
def rel_panel(frames: dict, spy: pd.DataFrame, window: int) -> pd.DataFrame:
    """{date -> {symbol -> relative_return}} for one lookback window.

    `relative_return` is positional per frame (iloc[-1] vs iloc[-window-1]),
    which is exactly `Close.pct_change(window)` evaluated at that bar; the two
    frames are then aligned on DATE, the same way the live code compares a
    ticker's own last bar to SPY's own last bar."""
    spy_rel = spy["Close"].pct_change(window)
    cols = {}
    for sym, df in frames.items():
        rel = df["Close"].pct_change(window)
        cols[sym] = rel - spy_rel.reindex(rel.index)
    return pd.DataFrame(cols)


def pctile_panel(rel: pd.DataFrame) -> pd.DataFrame:
    """100 * mean(mine >= other) across the row = a max-method percent rank.
    NaNs are excluded from both numerator and denominator, exactly like
    `rs_percentile`'s `[r for r in universe_rels if r is not None]`."""
    return (rel.rank(axis=1, method="max", pct=True) * 100.0).round(1)


def sector_pctile_panel(rel: pd.DataFrame) -> pd.DataFrame:
    """Same rank, but `sector_rs_percentile` returns its 50.0 sentinel when
    fewer than two sectors have a reading on that bar."""
    out = pctile_panel(rel)
    thin = rel.notna().sum(axis=1) < 2
    out.loc[thin, :] = 50.0
    return out


def verify_rs_panels(frames: dict, spy: pd.DataFrame, pct63: pd.DataFrame,
                     samples: int = 200) -> int:
    """Assert the vectorized panel reproduces `rs_percentile` bar for bar on
    randomly spread sample bars. Must be 0 mismatches -- otherwise every
    number this script prints is measuring something other than the gate."""
    mismatches = checked = 0
    syms = sorted(frames)[:6]
    for sym in syms:
        df = frames[sym]
        idx = df.index
        step = max(1, (len(idx) - 300) // max(1, samples // len(syms)))
        for i in range(300, len(idx), step):
            d = idx[i]
            if d not in pct63.index:
                continue
            # The live call: this ticker's frame up to bar i, SPY up to the
            # same DATE, universe rels = every watchlist ticker's rel on that
            # date (what refresh_rs_cache would have written that morning).
            spy_win = spy.loc[:d]
            rels = [v for v in _REL63.loc[d].tolist() if not pd.isna(v)]
            real = rs_factors.rs_percentile(df.iloc[:i + 1], spy_win,
                                            universe_rels=rels)
            mine = pct63.at[d, sym]
            if pd.isna(mine):
                continue
            checked += 1
            mismatches += abs(float(real) - float(mine)) > 0.051
    print(f"RS panel check: {checked} sampled (symbol, bar) pairs, "
          f"{mismatches} mismatches", flush=True)
    return mismatches


# --------------------------------------------------------------------------
# population
# --------------------------------------------------------------------------
def collect(frames: dict, pct: dict, sector_pct: dict, sector_of_ticker: dict,
            etf_of_sector: dict, date_range: tuple) -> list:
    """One row per trade entry bar inside `date_range`, carrying the RS
    readings the gate keys on, for the primary 63-day window and for this
    horizon's own window.

    Same population call as v33's instrument -- run_backtest(..., exit_model=
    "v2", scale_out=True) over ALL_STRATEGIES x HORIZONS -- so the scenario
    count is directly comparable with v33's published 4337."""
    rows = []
    for ticker, df in frames.items():
        eligible = is_rs_eligible(ticker)
        sector = sector_of_ticker.get(ticker)
        etf = etf_of_sector.get(sector) if sector else None
        n_rows = 0
        for hk in HKEYS:
            hz_w = HORIZONS[hk]["rs_window"]
            for strategy in ALL_STRATEGIES:
                summary = run_backtest(ticker, df, strategy, hk,
                                       exit_model="v2", scale_out=True)
                for t in summary.trades:
                    if not (date_range[0] <= t.entry_date <= date_range[1]):
                        continue
                    d = pd.Timestamp(t.entry_date)
                    if d not in pct[rs_factors.RS_WINDOW].index:
                        continue
                    row = {"ticker": ticker, "horizon": hk,
                           "strategy": strategy, "direction": t.direction,
                           "outcome": t.outcome, "r_multiple": t.r_multiple,
                           "eligible": eligible, "sector": sector,
                           "entry_date": t.entry_date}
                    for tag, w in (("w63", rs_factors.RS_WINDOW), ("whz", hz_w)):
                        v = pct[w].at[d, ticker] if ticker in pct[w].columns else np.nan
                        # rs_percentile() returns its 50.0 sentinel rather
                        # than None when it cannot compute, and the live gate
                        # treats that as an AVAILABLE reading. Reproduced,
                        # not smoothed over -- see the report.
                        synthetic = bool(pd.isna(v))
                        tv = 50.0 if synthetic else float(v)
                        sv = None
                        if etf is not None and etf in sector_pct[w].columns:
                            s = sector_pct[w].at[d, etf]
                            sv = 50.0 if pd.isna(s) else float(s)
                        row[f"rs_{tag}"] = tv
                        row[f"sector_{tag}"] = sv
                        row[f"combined_{tag}"] = (
                            rs_factors.rs_score(tv, sv) if sv is not None else tv)
                        row[f"synthetic_{tag}"] = synthetic
                    rows.append(row)
                    n_rows += 1
        print(f"{ticker}: {n_rows} entry-bar samples", flush=True)
    return rows


# --------------------------------------------------------------------------
# the gate, simulated
# --------------------------------------------------------------------------
def keeps(row: dict, key: str, leader: float | None,
          laggard: float | None) -> bool:
    """edge/rs_gate.py::rs_verdict, minus the strings. A None threshold means
    that direction is NOT gated (the one-sided outcome Step 2 allows)."""
    if not row["eligible"]:
        return True                       # exempt, never a pass
    v = row[key]
    if row["direction"] == "bullish":
        return True if leader is None else v >= leader
    return True if laggard is None else v <= laggard


def gate_block(rows: list, key: str, leader, laggard) -> dict:
    before = _wr_block(rows)
    after = _wr_block([r for r in rows if keeps(r, key, leader, laggard)])
    dropped = before["scenarios"] - after["scenarios"]
    return {
        "before": before, "after": after, "dropped": dropped,
        "volume_loss_pct": (100 * dropped / before["scenarios"]
                            if before["scenarios"] else 0.0),
        "wr_delta_pp": 100 * (after["wr"] - before["wr"]),
        "expectancy_delta": after["expectancy_r"] - before["expectancy_r"],
        # Nested samples, so this is a descriptive overlap check and can only
        # be conservative -- reported, never used to select (see the header).
        "separated": not (after["wilson"][0] <= before["wilson"][1]
                          and before["wilson"][0] <= after["wilson"][1]),
    }


def arm_sweep(rows: list, key: str, direction: str, thresholds: tuple) -> dict:
    """One direction's 5 cells. Only that direction's threshold is active."""
    bucket = [r for r in rows if r["direction"] == direction]
    out = {}
    for th in thresholds:
        lo, la = (th, None) if direction == "bullish" else (None, th)
        out[str(th)] = gate_block(bucket, key, lo, la)
    return out


def full_grid(rows: list, key: str) -> dict:
    out = {}
    for L in LEADERS:
        for G in LAGGARDS:
            out[f"{L}/{G}"] = gate_block(rows, key, L, G)
    return out


def one_sided(rows: list, key: str, direction: str, thresholds: tuple) -> dict:
    """The same sweep, but scored over the WHOLE population with only one
    arm gated -- which is what a one-sided gate actually ships as, and the
    only reading against which the plan's AGGREGATE <=30% volume budget can
    be judged. `arm_sweep` scores inside one arm; this scores the same gate
    against every scenario the bot would produce."""
    out = {}
    for th in thresholds:
        lo, la = (th, None) if direction == "bullish" else (None, th)
        out[str(th)] = gate_block(rows, key, lo, la)
    return out


def per_horizon(rows: list, key: str, leader, laggard) -> dict:
    out = {}
    for hk in HKEYS + ["ALL"]:
        bucket = rows if hk == "ALL" else [r for r in rows if r["horizon"] == hk]
        out[hk] = gate_block(bucket, key, leader, laggard)
    return out


def pick(sweep: dict, budget: float = VOLUME_BUDGET_PCT):
    """Selection rule 2-3 from the header, applied mechanically."""
    ok = [(k, v) for k, v in sweep.items() if v["volume_loss_pct"] <= budget]
    if not ok:
        return None, "every threshold blows the volume budget"
    best = max(ok, key=lambda kv: (kv[1]["wr_delta_pp"],
                                   -kv[1]["volume_loss_pct"]))
    if best[1]["wr_delta_pp"] <= 0:
        return None, "no threshold improved win rate -- this arm gets no gate"
    return best[0], "selected"


# --------------------------------------------------------------------------
def _fmt(b: dict) -> str:
    return (f"n={b['scenarios']:>5} ev={b['evaluated']:>5} w={b['wins']:>4} "
            f"WR={b['wr']*100:5.2f}% [{b['wilson'][0]*100:4.1f},"
            f"{b['wilson'][1]*100:4.1f}] E[R]={b['expectancy_r']:+.3f}")


def print_sweep(title: str, sweep: dict) -> None:
    print(f"\n{title}")
    for th, d in sweep.items():
        print(f"  th={th:>3}  {_fmt(d['before'])}  ->  {_fmt(d['after'])}  "
              f"cut={d['volume_loss_pct']:6.2f}%  dWR={d['wr_delta_pp']:+6.2f}pp"
              f"  dE[R]={d['expectancy_delta']:+.3f}  "
              f"sep={'yes' if d['separated'] else 'no'}", flush=True)


def print_grid(title: str, grid: dict) -> None:
    print(f"\n{title}")
    print(f"  {'L/G':>7}  {'cut':>7}  {'WR after':>9}  {'dWR':>8}  "
          f"{'dE[R]':>7}  sep")
    for k, d in grid.items():
        print(f"  {k:>7}  {d['volume_loss_pct']:6.2f}%  "
              f"{d['after']['wr']*100:8.2f}%  {d['wr_delta_pp']:+7.2f}pp  "
              f"{d['expectancy_delta']:+7.3f}  "
              f"{'yes' if d['separated'] else 'no'}", flush=True)


def rotation_table(sector_rel: pd.DataFrame, window: tuple) -> dict:
    """Step 4: does this window span leadership rotations?

    An RS gate is procyclical -- it is most confident about a leader right
    before that leader stops leading -- so a window with a single, stable
    leadership regime flatters it. Measured, not asserted: per calendar
    quarter, which sector ETF has the highest 63-day relative return on the
    quarter's last bar, and how often that leader changes."""
    per_q, order = {}, []
    sub = sector_rel.loc[window[0]:window[1]].dropna(how="all")
    for q, chunk in sub.groupby(pd.PeriodIndex(sub.index, freq="Q")):
        last = chunk.iloc[-1].dropna()
        if last.empty:
            continue
        key = str(q)
        per_q[key] = {"leader": str(last.idxmax()),
                      "laggard": str(last.idxmin()),
                      "leader_rel_pct": round(100 * float(last.max()), 2),
                      "laggard_rel_pct": round(100 * float(last.min()), 2)}
        order.append(key)
    changes = sum(1 for a, b in zip(order, order[1:])
                  if per_q[a]["leader"] != per_q[b]["leader"])
    return {"quarters": per_q, "n_quarters": len(order),
            "leader_changes": changes,
            "distinct_leaders": sorted({v["leader"] for v in per_q.values()})}


_REL63: pd.DataFrame | None = None


def main() -> int:
    global _REL63
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--train", action="store_true", help="the TRAIN window")
    g.add_argument("--validation", action="store_true",
                   help="the VALIDATION window -- v34 Task 8's ONE shot only")
    ap.add_argument("--json", default=None)
    ap.add_argument("--cache-dir", default=None,
                    help="OHLCV CSV cache. Defaults to <repo>/data/backtest_cache, "
                         "which is EMPTY inside a git worktree -- point this at "
                         "the main checkout's cache when running from one.")
    ap.add_argument("--limit", type=int, default=None,
                    help="only the first N watchlist tickers (smoke test)")
    ap.add_argument("--verify-rs", action="store_true",
                    help="run the panel/real-function agreement check, then exit")
    ap.add_argument("--rows-out", default=None,
                    help="cache the collected scenario rows here, so the "
                         "analysis can be re-cut without re-running the "
                         "~55-minute population collection")
    ap.add_argument("--rows-in", default=None,
                    help="re-use a --rows-out cache instead of collecting. "
                         "The window/cache-dir must match the run that wrote "
                         "it -- this re-cuts an existing measurement, it does "
                         "not take a new one")
    ap.add_argument("--rotations-only", action="store_true",
                    help="print only the sector-leadership rotation table "
                         "(Step 4) -- panels only, no backtest population")
    args = ap.parse_args()

    window = VALIDATION if args.validation else TRAIN
    label = "VALIDATION" if args.validation else "TRAIN"
    cache = Path(args.cache_dir) if args.cache_dir else CACHE_DIR

    def load(sym):
        p = Path(cache) / cache_path(sym).name
        if not p.exists():
            return None
        df = pd.read_csv(p, index_col="Date", parse_dates=True)
        return df if len(df) else None

    # Scenario universe = the WATCHLIST, not every CSV in the cache: SPY and
    # the sector ETFs now live there too and are inputs, not subjects.
    wl_path = ROOT / "data" / "watchlist.json"
    if not wl_path.exists():
        # `data/` is gitignored, so a worktree has its own near-empty copy.
        # Fall back to the checkout the cache belongs to (same reason
        # --cache-dir exists at all).
        wl_path = Path(cache).parent / "watchlist.json"
    watchlist = json.loads(wl_path.read_text())
    frames = {}
    for sym in sorted(watchlist):
        df = load(sym)
        if df is not None:
            frames[sym] = df
    if args.limit:
        frames = dict(list(frames.items())[:args.limit])
    spy = load(BENCHMARK)
    if not frames or spy is None:
        print(f"Need watchlist CSVs and {BENCHMARK}.csv in {cache} -- run "
              f"scripts/data/fetch_backtest_data.py, or pass --cache-dir.",
              file=sys.stderr)
        return 1

    # The live scan's sector-ETF side-fetch, reproduced (engine.py's
    # _sector_etfs_for_tickers / _etf_symbol_of_sector).
    sector_of_ticker = universe.sector_map("sp500")
    etf_of_symbol = universe.sector_map("etfs")
    etf_of_sector = {sec: sym for sym, sec in etf_of_symbol.items()}
    needed = sorted({etf_of_sector[sector_of_ticker[t]] for t in frames
                     if sector_of_ticker.get(t) in etf_of_sector})
    sector_frames = {s: load(s) for s in needed}
    sector_frames = {s: d for s, d in sector_frames.items() if d is not None}
    print(f"Window: {label} {window[0]}..{window[1]} | {len(frames)} tickers | "
          f"{len(sector_frames)}/{len(needed)} sector ETFs | benchmark "
          f"{BENCHMARK}", flush=True)
    if len(sector_frames) != len(needed):
        print(f"  missing sector ETFs: {sorted(set(needed) - set(sector_frames))}",
              flush=True)

    sector_rel63 = rel_panel(sector_frames, spy, rs_factors.RS_WINDOW)
    rot = rotation_table(sector_rel63, window)
    print(f"\nSTEP 4 -- sector leadership by quarter ({label}): "
          f"{rot['leader_changes']} leader changes over {rot['n_quarters']} "
          f"quarters, {len(rot['distinct_leaders'])} distinct leaders "
          f"{rot['distinct_leaders']}")
    for q, d in rot["quarters"].items():
        print(f"  {q}: leader {d['leader']:>4} ({d['leader_rel_pct']:+.2f}% "
              f"vs SPY, 63d)   laggard {d['laggard']:>4} "
              f"({d['laggard_rel_pct']:+.2f}%)", flush=True)
    if args.rotations_only:
        return 0

    pct, sector_pct = {}, {}
    for w in RS_WINDOWS:
        pct[w] = pctile_panel(rel_panel(frames, spy, w))
        sector_pct[w] = sector_pctile_panel(rel_panel(sector_frames, spy, w))
    _REL63 = rel_panel(frames, spy, rs_factors.RS_WINDOW)

    if verify_rs_panels(frames, spy, pct[rs_factors.RS_WINDOW]) != 0:
        print("ABORT: the RS panel disagrees with edge/factors.py::rs_percentile "
              "-- every number below would be measuring something else.",
              file=sys.stderr)
        return 1
    if args.verify_rs:
        return 0

    if args.rows_in:
        rows = json.loads(Path(args.rows_in).read_text())
        print(f"Re-cut from {args.rows_in}: {len(rows)} cached rows "
              f"(no new measurement taken)", flush=True)
    else:
        rows = collect(frames, pct, sector_pct, sector_of_ticker,
                       etf_of_sector, window)
        if args.rows_out:
            Path(args.rows_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.rows_out).write_text(json.dumps(rows))
            print(f"Cached {len(rows)} rows to {args.rows_out}", flush=True)
    print(f"\nTotal {label} scenarios: {len(rows)}", flush=True)
    print(f"Directions: {dict(Counter(r['direction'] for r in rows))}", flush=True)
    print(f"Outcomes: {dict(Counter(r['outcome'] for r in rows))}", flush=True)
    n_exempt = sum(1 for r in rows if not r["eligible"])
    n_synth = sum(1 for r in rows if r["synthetic_w63"])
    n_nosector = sum(1 for r in rows if r["sector_w63"] is None)
    print(f"RS-exempt (index/fx/future): {n_exempt} | synthetic-50 RS "
          f"(rs_percentile's sentinel): {n_synth} | no sector ETF "
          f"(ticker-only rs_combined): {n_nosector}", flush=True)

    result = {"window": {"label": label, "from": window[0], "to": window[1]},
              "n_tickers": len(frames), "n_scenarios": len(rows),
              "n_exempt": n_exempt, "n_synthetic_rs": n_synth,
              "n_without_sector": n_nosector,
              "leaders": list(LEADERS), "laggards": list(LAGGARDS),
              "volume_budget_pct": VOLUME_BUDGET_PCT,
              "outcomes": dict(Counter(r["outcome"] for r in rows)),
              "directions": dict(Counter(r["direction"] for r in rows)),
              "sector_leadership_rotations": rot}

    for tag, wlabel in (("w63", "PRIMARY: shipped 63-day RS window"),
                        ("whz", "SECONDARY: per-horizon rs_window (no live "
                                "consumer -- evidence only)")):
        for key, kname in ((f"combined_{tag}", "rs_combined (0.7 ticker / 0.3 sector)"),
                           (f"rs_{tag}", "rs_percentile (ticker only)")):
            bull = arm_sweep(rows, key, "bullish", LEADERS)
            bear = arm_sweep(rows, key, "bearish", LAGGARDS)
            print_sweep(f"[{wlabel}] {kname} -- BULLISH arm "
                        f"(leader threshold):", bull)
            print_sweep(f"[{wlabel}] {kname} -- BEARISH arm "
                        f"(laggard threshold):", bear)
            pb, rb = pick(bull)
            pg, rg = pick(bear)
            print(f"  -> selection rule: leader={pb or 'NONE'} ({rb}); "
                  f"laggard={pg or 'NONE'} ({rg})", flush=True)
            grid = full_grid(rows, key)
            print_grid(f"[{wlabel}] {kname} -- full 5x5 grid (both arms "
                       f"active, whole population):", grid)
            # One-sided: the same thresholds scored over the WHOLE
            # population with only one arm live. This is the reading the
            # plan's AGGREGATE <=30% budget applies to, and the shape a
            # one-sided gate actually ships as.
            ob = one_sided(rows, key, "bullish", LEADERS)
            og = one_sided(rows, key, "bearish", LAGGARDS)
            print_sweep(f"[{wlabel}] {kname} -- BULLISH-ONLY gate, scored on "
                        f"the WHOLE population (aggregate budget):", ob)
            print_sweep(f"[{wlabel}] {kname} -- BEARISH-ONLY gate, scored on "
                        f"the WHOLE population (aggregate budget):", og)
            result[f"{key}"] = {"bullish_arm": bull, "bearish_arm": bear,
                                "grid": grid,
                                "bullish_only_whole_population": ob,
                                "bearish_only_whole_population": og,
                                "selected": {"leader": pb, "leader_reason": rb,
                                             "laggard": pg, "laggard_reason": rg}}

    # Per-horizon cost of the shapes actually under consideration, so a
    # single horizon paying an outsized share is visible (v33's `2w` lesson).
    result["per_horizon"] = {
        "bearish_only_laggard_25": per_horizon(rows, "combined_w63", None, 25),
        "bearish_only_laggard_40": per_horizon(rows, "combined_w63", None, 40),
        "bullish_only_leader_55": per_horizon(rows, "combined_w63", 55, None),
        "symmetric_55_45": per_horizon(rows, "combined_w63", 55, 45),
    }
    for name, tab in result["per_horizon"].items():
        print(f"\nPer-horizon -- {name}")
        for hk, d in tab.items():
            print(f"  {hk:>3}: {_fmt(d['before'])}  ->  {_fmt(d['after'])}  "
                  f"cut={d['volume_loss_pct']:6.2f}%  "
                  f"dWR={d['wr_delta_pp']:+6.2f}pp  "
                  f"sep={'yes' if d['separated'] else 'no'}", flush=True)

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2))
        print(f"\nWrote {args.json}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
