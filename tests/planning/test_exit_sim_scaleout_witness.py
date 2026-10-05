"""Byte-identity witness for the scale-out walk (v123 V123-3 refactor, V123-5 off mode)."""
import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from swingbot.core.planning.plan_engine import simulate_exit
from tests.planning.test_exit_sim_single import _plan

FIXTURE = Path(__file__).parent / "fixtures" / "scale_out_witness.sha256"


def _frames():
    rng = np.random.default_rng(123)
    for _ in range(4):
        close = 100.0 + np.cumsum(rng.integers(-3, 4, 260) * 0.25)
        high = close + rng.integers(1, 8, 260) * 0.125
        low = close - rng.integers(1, 8, 260) * 0.125
        open_ = np.r_[close[0], close[:-1]]
        idx = pd.bdate_range("2020-01-02", periods=260)
        yield pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                            "Volume": rng.integers(5, 30, 260) * 1e5}, index=idx)


def _rounded(value):
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rounded(v) for v in value]
    return value


def witness_rows():
    rows = []
    for f, df in enumerate(_frames()):
        for i in range(20, 240, 5):
            c = float(df["Close"].iloc[i])
            for direction, sign in (("bullish", 1), ("bearish", -1)):
                for tp2 in (None, c + sign * 3.0):
                    plan = _plan(direction=direction, stop_loss=c - sign * 3.0,
                                 tp1=c + sign * 2.0, tp2=tp2, horizon_key="4w")
                    res = simulate_exit(df, i, plan, scale_out=True)
                    rows.append([f, i, direction, tp2 is not None, _rounded(dataclasses.asdict(res))])
    return rows


def witness_hash():
    return hashlib.sha256(json.dumps(witness_rows(), sort_keys=True).encode()).hexdigest()


def write_witness():
    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_text(witness_hash() + "\n", encoding="utf-8")


def test_scale_out_walk_is_byte_identical_to_the_frozen_witness():
    assert witness_hash() == FIXTURE.read_text(encoding="utf-8").strip()


def test_witness_exercises_every_runner_reason():
    reasons = {row[4]["runner_outcome"] for row in witness_rows()}
    assert {"runner_be", "runner_trail", "runner_tp2", "runner_timeout"} <= reasons
