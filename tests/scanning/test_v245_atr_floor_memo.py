"""v245 V245-4 (results doc F1): `_scan_one` computes ATR(14) once per frame.

`atr_floor_pct` used to call `atr(df, 14)` once per horizon on the same `df`;
the horizon only scales the last value afterwards. These tests count the
calls and pin the shared value against the unshared path, float for float.
"""
import math

import pandas as pd
import pytest

from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning import analyze
from tests.scanning.v245_golden_cases import CASE_BY_NAME, frozen_clock, run_case


def _count_atr(monkeypatch) -> list:
    calls = []
    real = levels.atr

    def counting(df, *args, **kwargs):
        calls.append(id(df))
        return real(df, *args, **kwargs)

    monkeypatch.setattr(levels, "atr", counting)
    return calls


@pytest.mark.parametrize("name, horizons_run", [
    ("wave_completed", 10), ("wave_forming", 10), ("short_history_forming", 4)])
def test_scan_one_computes_atr14_once_per_frame(name, horizons_run, monkeypatch):
    frozen_clock(monkeypatch)
    calls = _count_atr(monkeypatch)
    case = CASE_BY_NAME[name]
    assert horizons_run > 1 and len(case.horizons) >= horizons_run
    run_case(case)
    assert len(calls) == 1


def test_no_frame_computes_no_atr(monkeypatch):
    frozen_clock(monkeypatch)
    calls = _count_atr(monkeypatch)
    run_case(CASE_BY_NAME["no_frame"])
    assert calls == []


def _same_float(a: float, b: float) -> bool:
    return (math.isnan(a) and math.isnan(b)) or float.hex(a) == float.hex(b)


@pytest.mark.parametrize("name", ["wave_completed", "wave_forming", "down_forming",
                                  "short_history_completed"])
@pytest.mark.parametrize("horizon_key", sorted(HORIZONS))
def test_shared_atr14_equals_the_unshared_floor(name, horizon_key):
    df = CASE_BY_NAME[name].frame()
    h = HORIZONS[horizon_key]
    price = float(df["Close"].iloc[-1]) * 1.013
    shared = levels.atr14_last(df)
    assert _same_float(levels.atr_floor_pct(df, price, h, atr14=shared),
                       levels.atr_floor_pct(df, price, h))


def test_atr14_last_is_none_when_atr_raises():
    assert levels.atr14_last(pd.DataFrame()) is None


def test_none_atr14_falls_back_to_the_unshared_path():
    df = CASE_BY_NAME["wave_completed"].frame()
    h = HORIZONS["3m"]
    assert levels.atr_floor_pct(df, 100.0, h, atr14=None) == levels.atr_floor_pct(df, 100.0, h)
    assert levels.atr_floor_pct(pd.DataFrame(), 100.0, h, atr14=None) == 0.0


def test_shared_atr14_keeps_the_guards():
    h = HORIZONS["3m"]
    assert levels.atr_floor_pct(None, 100.0, h, atr14=0.0) == 0.0
    assert levels.atr_floor_pct(None, 0.0, h, atr14=2.0) == 0.0
    assert levels.atr_floor_pct(None, 100.0, h, atr14=2.0) == 2.0 * h.get("atr_stop_multiple", 1.5)


def test_rescenario_still_computes_its_own_atr14(monkeypatch):
    calls = _count_atr(monkeypatch)
    df = CASE_BY_NAME["wave_completed"].frame()
    build = analyze._horizon_scenarios(df, HORIZONS["3m"], float(df["Close"].iloc[-1]), [],
                                       analyze._default_hard_filters(None))
    assert isinstance(build, analyze.HorizonBuild)
    assert len(calls) == 1
