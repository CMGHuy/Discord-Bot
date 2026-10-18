#!/usr/bin/env python3
"""v163 A/A calibration of the trail race shape (spec § Testing).

    python scripts/backtest/screen_trail_calibration.py
    python scripts/backtest/screen_trail_calibration.py --replicates 3 --tickers 2 --resamples 500 --dry-run

Each replicate builds a synthetic universe of TICKERS fat-tailed,
volatility-clustered daily frames (Student-t innovations, df = 3, under a
two-state volatility regime), marks random "events" with no planted effect,
runs every ticker through the real screen_ticker with a trail idea (cap 60)
and the pooled pairs through the real verdict.decide. Reported: the
full-verdict false-pass rate and the coverage of the 95% interval for
dExpR = 0. Exit 0 iff the false-pass rate is at most FALSE_PASS_MAX (5%);
coverage is reported, not gated. Synthetic data only: no cached price file
is ever read, and nothing is written to the pre-registration ledger.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "scripts" / "backtest"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import screen_idea  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen import null, race, trail, verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import Idea  # noqa: E402

REPLICATES = 200
SEED = 20261015
TICKERS = 24
BARS = 2600                       # 2010-01-04 .. December 2019, business days
EVENT_RATE = 0.02
T_DF = 3
VOL_STATES = (0.010, 0.025)       # daily log-return sigma: calm, stressed
SWITCH_PROB = (0.02, 0.05)        # per-bar chance of leaving calm, leaving stressed
CAP = 60
FALSE_PASS_MAX = 0.05
IDEA_NAME = "aa_trail_calibration"
START = "2010-01-04"
RESULTS_DIR = ROOT / "docs" / "superpowers" / "results"
PROGRESS_EVERY = 10


def _regimes(rng, bars: int) -> np.ndarray:
    """A two-state Markov volatility path: 0 calm, 1 stressed."""
    flips = rng.random(bars)
    state = np.empty(bars, dtype=int)
    current = 0
    for i in range(bars):
        state[i] = current
        if flips[i] < SWITCH_PROB[current]:
            current = 1 - current
    return state


def synthetic_frame(rng, bars: int = BARS, start: str = START) -> pd.DataFrame:
    """One driftless OHLCV frame: unit-variance Student-t log returns scaled
    by the regime's sigma; the open gaps off the prior close; wicks beyond
    the open/close body. High >= max(Open, Close), Low <= min(Open, Close)."""
    sigma = np.asarray(VOL_STATES)[_regimes(rng, bars)]
    unit_t = rng.standard_t(T_DF, bars) / np.sqrt(T_DF / (T_DF - 2))
    close = 100.0 * np.exp(np.cumsum(sigma * unit_t))
    open_ = np.r_[100.0, close[:-1]] * np.exp(0.3 * sigma * rng.standard_normal(bars))
    high = np.maximum(open_, close) * np.exp(np.abs(0.5 * sigma * rng.standard_normal(bars)))
    low = np.minimum(open_, close) * np.exp(-np.abs(0.5 * sigma * rng.standard_normal(bars)))
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": np.full(bars, 1e6)},
                        index=pd.bdate_range(start, periods=bars, name="Date"))


def random_events(index, rng, rate: float = EVENT_RATE) -> pd.Series:
    """Each bar an "event" independently with probability ``rate``."""
    return pd.Series(rng.random(len(index)) < rate, index=index)


def _idea(events: pd.Series) -> Idea:
    return Idea(name=IDEA_NAME, events=lambda df: events, time_cap_bars=CAP,
                race_shape="trail", summary="random events, no planted effect",
                source="v163 A/A calibration")


def replicate(seed: int, *, tickers: int = TICKERS, bars: int = BARS,
              rate: float = EVENT_RATE,
              n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES) -> verdict.Verdict:
    """One synthetic universe through the real screen and the real verdict."""
    rng = np.random.default_rng(seed)
    paired = []
    for i in range(tickers):
        df = synthetic_frame(rng, bars)
        screen = screen_idea.screen_ticker(_idea(random_events(df.index, rng, rate)),
                                           f"R{seed}T{i:03d}", df, None)
        paired += [verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
                   for row in screen.events]
    return verdict.decide(paired, n_resamples=n_resamples)


def _covers_zero(v) -> bool:
    """An undefined interval (no events) does not cover."""
    return v.ci_low is not None and v.ci_low <= 0.0 <= v.ci_high


def calibrate(replicates: int = REPLICATES, seed: int = SEED, *, tickers: int = TICKERS,
              n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES, out=print) -> dict:
    if replicates < 1:
        raise ValueError("the calibration needs at least one replicate")
    verdicts = []
    for r in range(replicates):
        verdicts.append(replicate(seed + r, tickers=tickers, n_resamples=n_resamples))
        if (r + 1) % PROGRESS_EVERY == 0 or r + 1 == replicates:
            out(f"[calibration] {r + 1}/{replicates} replicates "
                f"({100.0 * (r + 1) / replicates:.0f}%)", flush=True)
    false_pass = sum(v.verdict == verdict.SCREEN_PASS for v in verdicts)
    covered = sum(_covers_zero(v) for v in verdicts)
    return {"replicates": replicates, "verdicts": verdicts, "false_pass": false_pass,
            "false_pass_rate": false_pass / replicates, "covered": covered,
            "coverage": covered / replicates,
            "mean_n": float(np.mean([v.n for v in verdicts]))}


def _render_head(result: dict, params: dict, day: str) -> list:
    holds = result["false_pass_rate"] <= FALSE_PASS_MAX
    command = (f"python scripts/backtest/screen_trail_calibration.py --replicates "
               f"{params['replicates']} --seed {params['seed']} --tickers {params['tickers']} "
               f"--resamples {params['resamples']}")
    return [
        f"# v163 trail race A/A calibration -> {'within' if holds else '**over**'} "
        f"the {FALSE_PASS_MAX:.0%} false-pass limit", "",
        "**Spec:** `docs/superpowers/specs/implemented/2026-10-15-v163-screen-trail-race-design.md` "
        "§ Testing (A/A calibration).", "",
        f"**Run:** {day}; `{command}`; replicate r uses seed {params['seed']} + r; "
        f"{params['tickers']} tickers x {BARS} business days from {START}; bootstrap "
        f"{params['resamples']:,} week resamples, seed {stats.WEEK_BOOTSTRAP_SEED}.", "",
        f"**Generator:** Student-t innovations, df = {T_DF}, scaled to unit variance; "
        f"two-state volatility regime, daily sigma {VOL_STATES[0]} / {VOL_STATES[1]}, "
        f"per-bar switch probability {SWITCH_PROB[0]} (calm -> stressed) / "
        f"{SWITCH_PROB[1]} (stressed -> calm); no drift. Events: every bar independently "
        f"with probability {EVENT_RATE}, no planted effect. Synthetic data only; no cached "
        "price file is read and no ledger row is written.", "",
        f"**Race:** the real `screen_ticker` with a trail idea (cap {CAP} bars, chandelier "
        f"{trail.TRAIL_ATR} x ATR14[t], initial stop {race.STOP_ATR} x ATR14[t]) against a "
        f"trail matched null (K = {null.K}), pooled through the real `verdict.decide` "
        "(pass rule unchanged).",
    ]


def _render_result(result: dict) -> list:
    n = result["replicates"]
    labels = Counter(v.verdict for v in result["verdicts"])
    tally = ", ".join(f"{name} {labels.get(name, 0)}" for name in
                      (verdict.SCREEN_PASS, verdict.SCREEN_FAIL, verdict.SCREEN_UNDERPOWERED))
    return [
        "## Result", "", "| | value | rule |", "|---|---|---|",
        f"| full-verdict false-pass rate | {result['false_pass']} of {n} = "
        f"{result['false_pass_rate']:.1%} | ≤ {FALSE_PASS_MAX:.0%} (gating) |",
        f"| coverage of the 95% interval for ΔExpR = 0 | {result['covered']} of {n} = "
        f"{result['coverage']:.1%} | reported, not gated |",
        f"| mean kept events N per replicate | {result['mean_n']:.1f} | — |", "",
        f"Verdicts: {tally}. A replicate with no interval (no events) counts as not covering.",
    ]


def _render_replicates(result: dict, seed: int) -> list:
    lines = ["## Per replicate", "",
             "| seed | verdict | N | ΔExpR | lower 95% | upper 95% |",
             "|---|---|---|---|---|---|"]
    fmt = screen_idea._fmt
    lines += [f"| {seed + r} | {v.verdict} | {v.n} | {fmt(v.delta_exp_r)} | "
              f"{fmt(v.ci_low)} | {fmt(v.ci_high)} |"
              for r, v in enumerate(result["verdicts"])]
    return lines


def render(result: dict, params: dict, day: str) -> str:
    sections = [_render_head(result, params, day), _render_result(result),
                _render_replicates(result, params["seed"])]
    return "\n\n".join("\n".join(lines) for lines in sections) + "\n"


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--replicates", type=_positive, default=REPLICATES)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--tickers", type=_positive, default=TICKERS)
    p.add_argument("--resamples", type=_positive, default=stats.WEEK_BOOTSTRAP_RESAMPLES)
    p.add_argument("--date", type=screen_idea._iso_day, default=date.today().isoformat(),
                   help="results-doc date; default today")
    p.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--dry-run", action="store_true", help="print the doc, write nothing")
    return p


def _progress(message: str, flush: bool = False) -> None:
    print(message, file=sys.stderr, flush=flush)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    screen_idea._utf8_stdout()
    result = calibrate(args.replicates, args.seed, tickers=args.tickers,
                       n_resamples=args.resamples, out=_progress)
    params = {"replicates": args.replicates, "seed": args.seed,
              "tickers": args.tickers, "resamples": args.resamples}
    text = render(result, params, args.date)
    if args.dry_run:
        print(text)
    else:
        path = Path(args.out_dir) / f"{args.date}-trail-race-calibration.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"false-pass {result['false_pass']}/{result['replicates']} = "
              f"{result['false_pass_rate']:.1%}, coverage {result['coverage']:.1%} -> {path}")
    return 0 if result["false_pass_rate"] <= FALSE_PASS_MAX else 1


if __name__ == "__main__":
    sys.exit(main())
