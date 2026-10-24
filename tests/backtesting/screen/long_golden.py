"""v182 golden long outputs (partner rule 2026-10-21: the long side stays
byte-identical). Captured once, on engine code identical to main @ 9536ce09,
before any v182 engine edit; compared exactly by test_long_byte_identical.py.

    python tests/backtesting/screen/long_golden.py --write   # V182-1 only

Frames use integer draws and + - * / only, so every float is the same bits
on Windows and Linux (no np.exp: see test_screen_context_runner.py:28-31).
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from collections import Counter
from functools import partial
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
for _path in (ROOT, ROOT / "scripts" / "backtest"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import screen_idea  # noqa: E402
from swingbot.core.backtesting.screen import indicators, race, verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402
from swingbot.core.edge.frictions import commission_r  # noqa: E402

GOLDEN_PATH = Path(__file__).with_name("golden") / "long_v182.json"
#: The nine ideas registered on main @ 9536ce09, frozen. Never list(IDEAS):
#: V182-14/15 register two short ideas that must not enter this capture.
LONG_IDEAS = ("high52w", "uptrend_pullback", "gap_volume", "turn_of_month",
              "turtle_soup", "quiet_pullback", "bond_spike_rebound", "dollar_drop",
              "sweep_reclaim_bos")
TRAIL_VARIANT = "high52w_trail"        # covers trail race, trail null, stressed book
SEEDS = (7, 11, 13)
BARS = 2600
START = "2010-01-04"
CONTEXT_SEEDS = {"TLT": 101, "UUP": 102}
CONTEXT_BARS, CONTEXT_START = 2800, "2009-06-01"
TAIL_ODDS = 40                         # one bar in 40 moves 4x / gaps 8x
ALWAYS = [("2000-01-01", "9999-12-31")]
RACE_ALL_EVERY = 5                     # race_all: every 5th warm bar
RACE_ALL_CAPS = {"fixed": 20, "trail": 60}
GOLDEN_RESAMPLES = 500
GOLDEN_DATE = "2026-10-21"
SCREEN_FIELDS = ("ticker", "counters", "events", "null_outcomes", "excess", "rank",
                 "null_timeout_r", "stressed", "restricted")


def fixture_frame(seed: int, n: int = BARS, start: str = START) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    step = rng.integers(-40, 43, n)                       # close move in 1/2048ths, slight up-drift
    step = np.where(rng.integers(0, TAIL_ODDS, n) == 0, 4 * step, step)
    gap = rng.integers(-24, 25, n)
    big_gap = rng.integers(0, TAIL_ODDS, n) == 0
    gap = np.where(big_gap, 8 * gap, gap)
    # A big gap-up holds into the close (else gap_volume, which needs close >= open, never fires).
    step = np.where(big_gap & (gap > 0), np.maximum(step, gap // 2), step)
    close = 100.0 * np.cumprod(1.0 + step / 2048.0)
    open_ = np.r_[100.0, close[:-1]] * (1.0 + gap / 4096.0)
    high = np.maximum(open_, close) * (1.0 + rng.integers(0, 40, n) / 4096.0)
    low = np.minimum(open_, close) * (1.0 - rng.integers(0, 40, n) / 4096.0)
    # A big gap carries a volume spike (the news proxy), else gap_volume never fires.
    spike = np.where((rng.integers(0, 50, n) == 0) | big_gap, 3.0, 1.0)
    volume = rng.integers(500_000, 3_000_000, n).astype(float) * spike
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": volume}, index=pd.bdate_range(start, periods=n))


def _exact_frame(df: pd.DataFrame) -> dict:
    return {"columns": [str(c) for c in df.columns], "index": [str(i) for i in df.index],
            "values": _exact(df.to_numpy().tolist())}


def _exact(value):
    """Recursive JSON-safe conversion; every float becomes its repr string."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return repr(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, np.ndarray):
        return _exact(value.tolist())
    if isinstance(value, (Counter, dict)):
        return {str(k): _exact(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_exact(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return _exact_frame(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _exact(getattr(value, f.name)) for f in dataclasses.fields(value)}
    raise TypeError(f"cannot capture {type(value).__name__}: {value!r}")


def _ideas() -> dict:
    ideas = {name: IDEAS[name] for name in LONG_IDEAS}
    ideas[TRAIL_VARIANT] = dataclasses.replace(IDEAS["high52w"], name=TRAIL_VARIANT,
                                               race_shape="trail")
    return ideas


def _context() -> dict[str, pd.DataFrame]:
    return {name: fixture_frame(seed, CONTEXT_BARS, CONTEXT_START)
            for name, seed in CONTEXT_SEEDS.items()}


def _screen_fields(screen) -> dict:
    return {name: getattr(screen, name) for name in SCREEN_FIELDS}


def _race_positions(df, atr, cap: int) -> np.ndarray:
    warm = race.warm_mask(atr, indicators.sma(df["Close"], 200))
    ok = [p for p in range(len(df)) if warm[p] and p + cap <= len(df) - 1]
    return np.asarray(ok[::RACE_ALL_EVERY], dtype=int)


def _race_all(df) -> dict:
    atr = indicators.atr(df)
    return {shape: race.race_for(shape)(df, _race_positions(df, atr, cap), cap, atr=atr)
            for shape, cap in RACE_ALL_CAPS.items()}


def _results_doc(idea, summary) -> str:
    members = ["S7", "S11", "S13"]
    universe = screen_idea.Universe({}, members, members, [])
    run = {"ledger_id": screen_idea.ledger_id(idea.name), "q": 0.5, "date": GOLDEN_DATE,
           "start": screen_idea.WINDOW_START, "end": screen_idea.WINDOW_END,
           "slippage_bps": screen_idea.base_slippage(None), "commission": commission_r()}
    return screen_idea.render_results(idea, summary, universe, run)


def _capture_idea(payload: dict, idea, frames: dict, context: dict) -> None:
    name = idea.name
    screens = []
    for seed, df in frames.items():
        screen = screen_idea.screen_ticker(idea, f"S{seed}", df, ALWAYS, context=context)
        screens.append(screen)
        for field, value in _screen_fields(screen).items():
            payload[f"{name}/{seed}/{field}"] = _exact(value)
    summary = screen_idea.summarise(screens)
    for key, value in summary.items():
        payload[f"{name}/summary/{key}"] = _exact(value)
    payload[f"{name}/hypothesis"] = screen_idea.hypothesis(idea)
    if not idea.context:
        payload[f"{name}/results_doc"] = _results_doc(idea, summary)


def capture() -> dict:
    decide = partial(verdict.decide, n_resamples=GOLDEN_RESAMPLES)
    payload: dict = {}
    with mock.patch.object(screen_idea.verdict, "decide", decide):
        context = _context()
        frames = {seed: fixture_frame(seed) for seed in SEEDS}
        for idea in _ideas().values():
            _capture_idea(payload, idea, frames, context)
        for seed, df in frames.items():
            for shape, result in _race_all(df).items():
                payload[f"race_all/{seed}/{shape}"] = _exact(result)
    return payload


def digests(payload: dict) -> dict[str, str]:
    return {key: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"))
                                .encode("utf-8")).hexdigest()
            for key, value in payload.items()}


def counts(payload: dict) -> dict[str, int]:
    return {name: sum(len(payload[f"{name}/{seed}/events"]) for seed in SEEDS)
            for name in _ideas()}


def write() -> Path:
    payload = capture()
    body = {"captured_on": "main @ 9536ce09 (engine unchanged)",
            "counts": counts(payload), "digests": digests(payload)}
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(body, indent=1, sort_keys=True), encoding="utf-8",
                           newline="\n")
    return GOLDEN_PATH


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    if parser.parse_args(argv).write:
        print(write())
    else:
        print(counts(capture()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
