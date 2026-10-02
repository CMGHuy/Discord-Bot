"""The decision logic of scripts/ops/market_cache_repair.py (no network, fake frames)."""
import importlib.util
import pathlib

import numpy as np
import pandas as pd

SPEC = importlib.util.spec_from_file_location(
    "market_cache_repair", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ops" / "market_cache_repair.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def frame(start, rows, base=100.0, drift=0.0, source=None):
    idx = pd.bdate_range(start, periods=rows)
    close = base * (1 + drift) ** np.arange(rows)
    df = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1.0}, index=idx)
    if source:
        df.attrs["source"] = source
    return df


def test_identical_frames_are_not_flagged():
    cache = frame("2024-01-01", 400)
    stats = mod.summarise(cache, cache.copy(), "daily")
    assert stats["median"] == 1.0 and not mod.is_flagged(stats)


def test_a_cache_with_another_instruments_prices_is_flagged():
    fresh = frame("2024-01-01", 400)
    cache = fresh * 2.4
    assert mod.is_flagged(mod.summarise(cache, fresh, "daily"))


def test_a_cache_that_starts_decades_before_the_listing_is_flagged_even_if_recent_bars_agree():
    fresh = frame("2021-01-04", 300)
    older = frame("2000-08-30", 400, base=5.0)
    cache = pd.concat([older, fresh])
    stats = mod.summarise(cache, fresh, "daily")
    assert stats["early"] and mod.is_flagged(stats)


def test_the_early_start_rule_does_not_apply_to_hourly_files():
    fresh = frame("2024-01-01", 300)
    cache = pd.concat([frame("2016-01-01", 100, base=3.0), fresh])
    assert not mod.summarise(cache, fresh, "hourly")["early"]


def test_too_little_overlap_cannot_be_judged():
    assert mod.summarise(frame("2024-01-01", 10), frame("2024-01-01", 10), "daily") is None


def test_alpaca_agreement_is_required_for_a_daily_replacement():
    fresh = frame("2024-01-01", 300)
    assert mod.alpaca_verdict(fresh, frame("2024-01-01", 300, source="alpaca"))[0] == "ok"
    assert mod.alpaca_verdict(fresh, frame("2024-01-01", 300, base=130.0, source="alpaca"))[0] == "disagrees"
    assert mod.alpaca_verdict(fresh, frame("2024-01-01", 300, source="yfinance-fallback"))[0] == "no-alpaca"
    assert mod.alpaca_verdict(fresh, None)[0] == "no-alpaca"


def test_timezone_aware_indexes_are_compared_after_normalising(tmp_path):
    fresh = frame("2024-01-01", 300)
    aware = fresh.copy()
    aware.index = aware.index.tz_localize("UTC")
    assert mod.summarise(aware, fresh, "hourly")["median"] == 1.0


def test_the_script_defaults_to_plan_and_quarantines_before_refetching():
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert 'argv[1] if len(argv) > 1 else "plan"' in src
    assert src.index("shutil.move(src, dst)") < src.index("data_refresh.refresh_symbol(")
    assert 'if __name__ == "__main__"' in src
