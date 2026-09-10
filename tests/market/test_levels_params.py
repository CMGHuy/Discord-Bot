"""Level-family flags are explicit scan parameters, not process globals."""
import dataclasses

import numpy as np
import pandas as pd

from swingbot.core.market import levels
from swingbot.scan_params import ScanParams


def _frame():
    index = pd.date_range("2023-01-02", periods=200, freq="B")
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 1.2, 200))
    return pd.DataFrame({"Open": close - 0.3, "High": close + 1.2,
                         "Low": close - 1.2, "Close": close,
                         "Volume": rng.integers(500_000, 2_000_000, 200).astype(float)},
                        index=index)


def test_params_none_matches_the_config_globals():
    frame = _frame()
    price = float(frame["Close"].iloc[-1])
    horizon = {"bars": 60, "label": "3m", "sr_lookback": 60}
    plain = levels.build_level_map(frame, horizon, price)
    explicit = levels.build_level_map(frame, horizon, price, params=ScanParams.from_config())
    assert [level.price for level in plain[0]] == [level.price for level in explicit[0]]
    assert [level.price for level in plain[1]] == [level.price for level in explicit[1]]


def test_disabling_avwap_removes_its_levels():
    frame = _frame()
    price = float(frame["Close"].iloc[-1])
    horizon = {"bars": 60, "label": "3m", "sr_lookback": 60}
    enabled = dataclasses.replace(ScanParams.from_config(), avwap_levels_enabled=True)
    disabled = dataclasses.replace(ScanParams.from_config(), avwap_levels_enabled=False)
    on = levels.collect_candidate_levels(frame, horizon, price, params=enabled)
    off = levels.collect_candidate_levels(frame, horizon, price, params=disabled)
    assert sum("Anchored VWAP" in source for _, source in off) == 0
    assert len(off) < len(on)
