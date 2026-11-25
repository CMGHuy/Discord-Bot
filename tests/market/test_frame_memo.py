"""v245 V245-5: a per-_scan_one memo for indicator calls repeated across horizons.

Results doc rows F2 (Bollinger 20/2), F3 (Donchian 20) and F4 (FVG
candidates): each horizon of one `_scan_one` call recomputed them on the same
`df` object with the same parameters. These tests pin the memo's contract,
count the shared call and compare the memoised candidates against the
unshared path float for float (float.hex).
"""
import dataclasses
import threading

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import frame_memo, levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning import analyze
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv
from tests.market.fvg_frames import witness_frame
from tests.scanning.v245_golden_cases import CASE_BY_NAME, frozen_clock, run_case


def _frame(n: int = 420) -> pd.DataFrame:
    i = np.arange(n)
    closes = 100.0 + 0.05 * i + 6.0 * np.sin(i / 9.0) + 2.0 * np.sin(i / 3.1)
    return make_ohlcv(list(closes))


def _count(monkeypatch, module, name) -> dict:
    calls = {"n": 0}
    real = getattr(module, name)

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, counting)
    return calls


def _hexed(candidates: list) -> list:
    return [(float.hex(float(price)), label) for price, label in candidates]


def _all_horizons(df: pd.DataFrame) -> list:
    price = float(df["Close"].iloc[-1])
    return [_hexed(levels.collect_candidate_levels(df, h, price, trendline_candidates=[]))
            for h in HORIZONS.values()]


# -- the memo's contract ---------------------------------------------------

def test_memo_without_a_scope_computes_every_time():
    df, calls = _frame(), []
    for _ in range(2):
        frame_memo.memo(df, ("k",), lambda: calls.append(1) or len(calls))
    assert len(calls) == 2


def test_memo_in_a_scope_returns_the_first_result():
    df, calls = _frame(), []
    with frame_memo.ticker_memo():
        first = frame_memo.memo(df, ("k", 1), lambda: calls.append(1) or object())
        second = frame_memo.memo(df, ("k", 1), lambda: calls.append(1) or object())
        other_key = frame_memo.memo(df, ("k", 2), lambda: calls.append(1) or object())
    assert first is second and other_key is not first
    assert len(calls) == 2


def test_memo_never_serves_another_frame():
    a, b = _frame(), _frame()            # equal values, different objects
    with frame_memo.ticker_memo():
        va = frame_memo.memo(a, ("k", 14), lambda: "from a")
        vb = frame_memo.memo(b, ("k", 14), lambda: "from b")
        again = frame_memo.memo(a, ("k", 14), lambda: "recomputed")
    assert (va, vb, again) == ("from a", "from b", "from a")


def test_memo_does_not_store_exceptions():
    df = _frame()
    with frame_memo.ticker_memo():
        with pytest.raises(ValueError):
            frame_memo.memo(df, ("k",), lambda: (_ for _ in ()).throw(ValueError("x")))
        assert frame_memo.memo(df, ("k",), lambda: 7) == 7


def test_memo_stores_a_none_result():
    df, calls = _frame(), []
    with frame_memo.ticker_memo():
        for _ in range(2):
            frame_memo.memo(df, ("k",), lambda: calls.append(1))
    assert len(calls) == 1


def test_scopes_nest_and_restore():
    df = _frame()
    with frame_memo.ticker_memo():
        frame_memo.memo(df, ("k",), lambda: "outer")
        with frame_memo.ticker_memo():
            assert frame_memo.memo(df, ("k",), lambda: "inner") == "inner"
        assert frame_memo.memo(df, ("k",), lambda: "late") == "outer"
    assert frame_memo.memo(df, ("k",), lambda: "none") == "none"


def test_scope_is_thread_local():
    df, seen = _frame(), []
    with frame_memo.ticker_memo():
        frame_memo.memo(df, ("k",), lambda: "main")
        worker = threading.Thread(
            target=lambda: seen.append(frame_memo.memo(df, ("k",), lambda: "thread")))
        worker.start()
        worker.join()
    assert seen == ["thread"]


def test_decorator_keeps_the_function_identity():
    assert analyze._scan_one.__name__ == "_scan_one"
    assert hasattr(analyze._scan_one, "__wrapped__")


# -- F2: Bollinger 20/2 ----------------------------------------------------

def test_bollinger_is_shared_across_horizons_and_unchanged(monkeypatch):
    df = _frame()
    plain = _all_horizons(df)
    bb = _count(monkeypatch, levels, "bollinger_bands")
    with frame_memo.ticker_memo():
        memoed = _all_horizons(df)
    assert memoed == plain
    assert bb["n"] == 1


@pytest.mark.parametrize("name", ["wave_completed", "wave_forming"])
def test_scan_one_computes_bollinger_once(name, monkeypatch):
    frozen_clock(monkeypatch)
    case = CASE_BY_NAME[name]
    assert len(case.horizons) > 1
    bb = _count(monkeypatch, levels, "bollinger_bands")
    run_case(case)
    assert bb["n"] == 1


# -- F3: Donchian 20 -------------------------------------------------------

def test_donchian_is_shared_across_horizons_and_unchanged(monkeypatch):
    df = _frame()
    plain = _all_horizons(df)
    donchian = _count(monkeypatch, levels, "_donchian_20")
    with frame_memo.ticker_memo():
        memoed = _all_horizons(df)
    assert memoed == plain
    assert donchian["n"] == 1


def test_donchian_helper_matches_the_inline_expressions():
    df = _frame()
    high, low = levels._donchian_20(df)
    assert float.hex(float(high)) == float.hex(float(df["High"].rolling(20).max().shift(1).iloc[-1]))
    assert float.hex(float(low)) == float.hex(float(df["Low"].rolling(20).min().shift(1).iloc[-1]))


def test_donchian_on_a_short_frame_still_emits_nothing():
    df = _frame(10)
    labels = {label for _, label in levels.collect_candidate_levels(
        df, HORIZONS["3m"], float(df["Close"].iloc[-1]), trendline_candidates=[])}
    assert not labels & {"Donchian high", "Donchian low"}


@pytest.mark.parametrize("name", ["wave_completed", "wave_forming"])
def test_scan_one_computes_donchian_once(name, monkeypatch):
    frozen_clock(monkeypatch)
    donchian = _count(monkeypatch, levels, "_donchian_20")
    run_case(CASE_BY_NAME[name])
    assert donchian["n"] == 1


# -- F4: FVG candidates ----------------------------------------------------

def _params(**fields) -> ScanParams:
    return dataclasses.replace(ScanParams.from_config(), **fields)


def _fvg_hexed(df, params) -> list:
    return _hexed(levels._fvg_candidates(df, params))


@pytest.mark.parametrize("mode, k", [("all", 1.5), ("displacement", 0.5)])
def test_fvg_is_shared_across_horizons_and_unchanged(mode, k, monkeypatch):
    df = witness_frame()
    params = _params(fvg_levels_mode=mode, fvg_displacement_atr_k=k)
    plain = _fvg_hexed(df, params)
    fvg = _count(monkeypatch, levels, "find_fair_value_gaps")
    with frame_memo.ticker_memo():
        memoed = [_fvg_hexed(df, params) for _ in HORIZONS]
    assert plain and memoed == [plain] * len(HORIZONS)
    assert fvg["n"] == 1


def test_fvg_memo_keys_on_the_mode_and_k_read_per_call(monkeypatch):
    df = witness_frame()
    every = _params(fvg_levels_mode="all")
    displaced = _params(fvg_levels_mode="displacement", fvg_displacement_atr_k=0.5)
    tighter = _params(fvg_levels_mode="displacement", fvg_displacement_atr_k=1.0)
    plain = [_fvg_hexed(df, p) for p in (every, displaced, tighter)]
    assert plain[1] and plain[1] != plain[2]
    fvg = _count(monkeypatch, levels, "find_fair_value_gaps")
    with frame_memo.ticker_memo():
        memoed = [_fvg_hexed(df, p) for p in (every, displaced, tighter, every)]
    assert memoed == plain + plain[:1]
    assert fvg["n"] == 3


def test_fvg_off_computes_nothing(monkeypatch):
    fvg = _count(monkeypatch, levels, "find_fair_value_gaps")
    with frame_memo.ticker_memo():
        assert levels._fvg_candidates(_frame(), _params(fvg_levels_mode="off")) == []
    assert fvg["n"] == 0


@pytest.mark.parametrize("name", ["wave_completed", "wave_forming"])
def test_scan_one_computes_fvg_once(name, monkeypatch):
    frozen_clock(monkeypatch)
    fvg = _count(monkeypatch, levels, "find_fair_value_gaps")
    run_case(CASE_BY_NAME[name])
    assert fvg["n"] == 1
