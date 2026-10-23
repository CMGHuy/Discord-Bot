#!/usr/bin/env python3
"""v163 A/A calibration of the trail race shape (spec § Testing).

    python scripts/backtest/screen_trail_calibration.py
    python scripts/backtest/screen_trail_calibration.py --direction short --seed 0
    python scripts/backtest/screen_trail_calibration.py --direction short --entry level --seed 0
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

v182 adds the short A/A: a fixed cap-20 idea raced short on the same frames
and events, with the Wilson interval of the false-pass rate printed. v182 level
mode races a short sell-stop half an ATR under the prior close, filled on the
event bar, against the depth-copy null.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "scripts" / "backtest"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import screen_idea  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen import indicators, null, race, trail, verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import Idea  # noqa: E402
from swingbot.core.edge.frictions import BORROW_RATE_ANNUAL  # noqa: E402

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
SHORT_CAP = 20
CAL_IDEA_NAMES = {("long", "next_open"): "aa_trail_calibration",
                  ("short", "next_open"): "aa_short_calibration",
                  ("short", "level"): "aa_short_level_calibration"}
LEVEL_OFFSET_ATR = 0.5
LEVEL_RATE_SCALE = 2.5            # draw 2.5 x rate, keep the bars whose order fills
ENABLED_ENTRIES = ("next_open", "level")
_SPEC_ITEMS = {"next_open": "§ Part A (calibration item 2)",
               "level": "§ Part B (calibration item 4)"}
_DOC_SLUGS = {("long", "next_open"): "trail-race-calibration",
              ("short", "next_open"): "short-race-calibration",
              ("short", "level"): "short-level-race-calibration"}
_ENTRY_LABELS = {"next_open": "next-open entry", "level": "level entry"}
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


def _anchored_open_close(sigma, unit_t, gap) -> tuple[np.ndarray, np.ndarray]:
    """Open gaps off the prior close; Close = Open x exp(sigma x t)."""
    close = 100.0 * np.exp(np.cumsum(np.log(gap) + sigma * unit_t))
    return np.r_[100.0, close[:-1]] * gap, close


def synthetic_frame(rng, bars: int = BARS, start: str = START, *,
                    anchored: bool = False) -> pd.DataFrame:
    """One driftless OHLCV frame: unit-variance Student-t log returns scaled
    by the regime's sigma; the open gaps off the prior close; wicks beyond
    the open/close body. High >= max(Open, Close), Low <= min(Open, Close).
    Default: Close[t] = Close[t-1] x exp(sigma x t), so the open noise is
    coupled to the close. ``anchored`` (level A/A only): Close = Open x
    exp(sigma x t), so a bar's open noise (its fill depth) is independent of
    its own move; same rng calls in the same order."""
    sigma = np.asarray(VOL_STATES)[_regimes(rng, bars)]
    unit_t = rng.standard_t(T_DF, bars) / np.sqrt(T_DF / (T_DF - 2))
    if anchored:
        open_, close = _anchored_open_close(
            sigma, unit_t, np.exp(0.3 * sigma * rng.standard_normal(bars)))
    else:
        close = 100.0 * np.exp(np.cumsum(sigma * unit_t))
        open_ = np.r_[100.0, close[:-1]] * np.exp(0.3 * sigma * rng.standard_normal(bars))
    high =np.maximum(open_, close) * np.exp(np.abs(0.5 * sigma * rng.standard_normal(bars)))
    low = np.minimum(open_, close) * np.exp(-np.abs(0.5 * sigma * rng.standard_normal(bars)))
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": np.full(bars, 1e6)},
                        index=pd.bdate_range(start, periods=bars, name="Date"))


def random_events(index, rng, rate: float = EVENT_RATE) -> pd.Series:
    """Each bar an "event" independently with probability ``rate``."""
    return pd.Series(rng.random(len(index)) < rate, index=index)


def level_events(df: pd.DataFrame, rng, rate: float) -> tuple[pd.Series, pd.Series]:
    """Random bars whose short sell-stop fills: the level is Close[t-1] minus
    LEVEL_OFFSET_ATR x ATR14[t-1] (bars <= t-1 only); a bar is an event when
    it is drawn and Low[t] < level. One rng call, as random_events."""
    levels = df["Close"].shift(1) - LEVEL_OFFSET_ATR * indicators.atr(df).shift(1)
    return random_events(df.index, rng, rate) & (df["Low"] < levels), levels


def _replicate_idea(df: pd.DataFrame, rng, rate: float, direction: str, entry: str) -> Idea:
    if entry == "level":
        events, levels = level_events(df, rng, rate * LEVEL_RATE_SCALE)
        return _idea(events, direction=direction, entry=entry, levels=levels)
    return _idea(random_events(df.index, rng, rate), direction=direction, entry=entry)


def doc_name(direction: str, entry: str, day: str) -> str:
    if (direction, entry) not in _DOC_SLUGS:
        raise ValueError(f"no calibration doc for {direction} / {entry}")
    return f"{day}-{_DOC_SLUGS[(direction, entry)]}.md"


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials."""
    if n < 1:
        raise ValueError("the Wilson interval needs at least one trial")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _idea(events: pd.Series, *, direction: str = "long", entry: str = "next_open",
          levels=None) -> Idea:
    if (direction, entry) not in CAL_IDEA_NAMES:
        raise ValueError(f"no calibration idea for {direction} / {entry}")
    if direction == "long":
        return Idea(name=IDEA_NAME, events=lambda df: events, time_cap_bars=CAP,
                    race_shape="trail", summary="random events, no planted effect",
                    source="v163 A/A calibration")
    return Idea(name=CAL_IDEA_NAMES[(direction, entry)], events=lambda df: events,
                time_cap_bars=SHORT_CAP, direction="short", entry=entry,
                levels=None if levels is None else (lambda df: levels),
                summary="random events, no planted effect, raced short",
                source="v182 short A/A calibration")


def replicate(seed: int, *, tickers: int = TICKERS, bars: int = BARS,
              rate: float = EVENT_RATE,
              n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES,
              direction: str = "long", entry: str = "next_open") -> verdict.Verdict:
    """One synthetic universe through the real screen and the real verdict."""
    if entry not in ENABLED_ENTRIES:
        raise ValueError(f"entry mode {entry!r} is not enabled")
    rng = np.random.default_rng(seed)
    paired = []
    for i in range(tickers):
        df = synthetic_frame(rng, bars, anchored=(entry == "level"))
        idea = _replicate_idea(df, rng, rate, direction, entry)
        screen = screen_idea.screen_ticker(idea, f"R{seed}T{i:03d}", df, None)
        paired += [verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
                   for row in screen.events]
    return verdict.decide(paired, n_resamples=n_resamples)


def _covers_zero(v) -> bool:
    """An undefined interval (no events) does not cover."""
    return v.ci_low is not None and v.ci_low <= 0.0 <= v.ci_high


def calibrate(replicates: int = REPLICATES, seed: int = SEED, *, tickers: int = TICKERS,
              n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES, out=print,
              direction: str = "long", entry: str = "next_open") -> dict:
    if replicates < 1:
        raise ValueError("the calibration needs at least one replicate")
    verdicts = []
    for r in range(replicates):
        verdicts.append(replicate(seed + r, tickers=tickers, n_resamples=n_resamples,
                                  direction=direction, entry=entry))
        if (r + 1) % PROGRESS_EVERY == 0 or r + 1 == replicates:
            out(f"[calibration] {r + 1}/{replicates} replicates "
                f"({100.0 * (r + 1) / replicates:.0f}%)", flush=True)
    false_pass = sum(v.verdict == verdict.SCREEN_PASS for v in verdicts)
    covered = sum(_covers_zero(v) for v in verdicts)
    return {"replicates": replicates, "verdicts": verdicts, "false_pass": false_pass,
            "false_pass_rate": false_pass / replicates, "covered": covered,
            "coverage": covered / replicates,
            "mean_n": float(np.mean([v.n for v in verdicts]))}


def _generator_paragraph(entry: str = "next_open") -> str:
    if entry == "level":
        return (f"**Generator:** Student-t innovations t, df = {T_DF}, scaled to unit variance; "
                f"two-state volatility regime, daily sigma {VOL_STATES[0]} / {VOL_STATES[1]}, "
                f"per-bar switch probability {SWITCH_PROB[0]} (calm -> stressed) / "
                f"{SWITCH_PROB[1]} (stressed -> calm); no drift. Open-anchored bars: the open "
                "gaps off the prior close by exp(0.3 x sigma x N(0,1)) and Close = Open x "
                "exp(sigma x t), so a bar's open noise (its fill depth) is not coupled to its "
                "own move (the next-open A/A anchors Close to the prior close instead). "
                "Synthetic data only; no cached price file is read and no ledger row is written.")
    return (f"**Generator:** Student-t innovations, df = {T_DF}, scaled to unit variance; "
            f"two-state volatility regime, daily sigma {VOL_STATES[0]} / {VOL_STATES[1]}, "
            f"per-bar switch probability {SWITCH_PROB[0]} (calm -> stressed) / "
            f"{SWITCH_PROB[1]} (stressed -> calm); no drift. Events: every bar independently "
            f"with probability {EVENT_RATE}, no planted effect. Synthetic data only; no cached "
            "price file is read and no ledger row is written.")


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
        _generator_paragraph(), "",
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


def _race_paragraph(entry: str) -> str:
    if entry == "level":
        return (f"**Race:** the real `screen_ticker` with a fixed short level idea (cap {SHORT_CAP} bars; "
                f"a sell-stop at Close[t-1] - {LEVEL_OFFSET_ATR} x ATR14[t-1], placed before bar t opens "
                "and filled on bar t at the lower of the open and the level, entry slippage "
                f"{race.LEVEL_SLIPPAGE_FACTOR} x base; stop {race.STOP_ATR} x ATR14[t-1] above, target "
                f"{race.STOP_ATR * race.REWARD_RISK} x ATR14[t-1] below, only the stop counts on the fill "
                f"bar; borrow {BORROW_RATE_ANNUAL:.1%} a year on calendar days held) against a short "
                f"matched null that copies each event's fill depth (K = {null.K}, unfilled draws replaced "
                "on the child stream), pooled through the real `verdict.decide` (pass rule unchanged). "
                f"Events: a bar is drawn with probability {EVENT_RATE * LEVEL_RATE_SCALE:g} and is an "
                "event only when the order fills (Low[t] < level). Decision rule: false-pass rate "
                f"≤ {FALSE_PASS_MAX:.0%} (10 of 200 at the registered run); the Wilson 95% interval is "
                "printed, never gating. This A/A shows only that the level-mode code adds no false "
                "passes; it cannot show that the depth-copy null is fair to real events (check 5 on the "
                "real cache does that, for range_breakdown_stop).")
    return (f"**Race:** the real `screen_ticker` with a fixed short idea (cap {SHORT_CAP} bars; "
            f"entry next open, sold; stop {race.STOP_ATR} x ATR14[t] above, target "
            f"{race.STOP_ATR * race.REWARD_RISK} x ATR14[t] below; borrow "
            f"{BORROW_RATE_ANNUAL:.1%} a year on calendar days held) against a short matched "
            f"null (K = {null.K}), pooled through the real `verdict.decide` (pass rule "
            f"unchanged). Decision rule: false-pass rate ≤ {FALSE_PASS_MAX:.0%} (10 of 200 at "
            "the registered run); the Wilson 95% interval is printed, never gating.")


def _render_head_short(result: dict, params: dict, day: str) -> list:
    holds = result["false_pass_rate"] <= FALSE_PASS_MAX
    entry = params["entry"]
    command = (f"python scripts/backtest/screen_trail_calibration.py --replicates "
               f"{params['replicates']} --seed {params['seed']} --tickers {params['tickers']} "
               f"--resamples {params['resamples']} --direction short --entry {entry}")
    return [
        f"# v182 short race A/A calibration ({_ENTRY_LABELS[entry]}) -> "
        f"{'within' if holds else '**over**'} the {FALSE_PASS_MAX:.0%} false-pass limit", "",
        "**Spec:** `docs/superpowers/specs/2026-10-21-v182-short-screen-range-breakdown-design.md` "
        f"{_SPEC_ITEMS[entry]}.", "",
        f"**Run:** {day}; `{command}`; replicate r uses seed {params['seed']} + r; "
        f"{params['tickers']} tickers x {BARS} business days from {START}; bootstrap "
        f"{params['resamples']:,} week resamples, seed {stats.WEEK_BOOTSTRAP_SEED}.", "",
        _generator_paragraph(entry), "",
        _race_paragraph(entry),
    ]


def _render_result_short(result: dict) -> list:
    lines = _render_result(result)
    low, high = wilson_interval(result["false_pass"], result["replicates"])
    lines.insert(5, f"| Wilson 95% interval of the false-pass rate | {low:.1%} .. {high:.1%} "
                    "| reported, not gated |")
    return lines


def render(result: dict, params: dict, day: str) -> str:
    if params.get("direction", "long") == "long":
        sections = [_render_head(result, params, day), _render_result(result),
                    _render_replicates(result, params["seed"])]
    else:
        sections = [_render_head_short(result, params, day), _render_result_short(result),
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
    p.add_argument("--direction", choices=("long", "short"), default="long")
    p.add_argument("--entry", choices=("next_open", "level"), default="next_open")
    p.add_argument("--date", type=screen_idea._iso_day, default=date.today().isoformat(),
                   help="results-doc date; default today")
    p.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--dry-run", action="store_true", help="print the doc, write nothing")
    return p


def _progress(message: str, flush: bool = False) -> None:
    print(message, file=sys.stderr, flush=flush)


def _mode_refusal(direction: str, entry: str) -> str | None:
    if (direction, entry) == ("long", "level"):
        return "the level-mode long mirror is defined but unused (v182)"
    if entry not in ENABLED_ENTRIES:
        return "--entry level is not enabled yet (V182-12)"
    return None


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    refusal = _mode_refusal(args.direction, args.entry)
    if refusal:
        parser.error(refusal)
    screen_idea._utf8_stdout()
    result = calibrate(args.replicates, args.seed, tickers=args.tickers,
                       n_resamples=args.resamples, out=_progress,
                       direction=args.direction, entry=args.entry)
    params = {"replicates": args.replicates, "seed": args.seed,
              "tickers": args.tickers, "resamples": args.resamples,
              "direction": args.direction, "entry": args.entry}
    text = render(result, params, args.date)
    if args.dry_run:
        print(text)
    else:
        path = Path(args.out_dir) / doc_name(args.direction, args.entry, args.date)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"false-pass {result['false_pass']}/{result['replicates']} = "
              f"{result['false_pass_rate']:.1%}, coverage {result['coverage']:.1%} -> {path}")
    return 0 if result["false_pass_rate"] <= FALSE_PASS_MAX else 1


if __name__ == "__main__":
    sys.exit(main())
