"""v171 D1/D4: one tolerance home, one atomic CSV writer with unique temp names."""
import inspect
import os
import re
import threading

import pandas as pd
import pytest

from swingbot.core.marketdata import adjustments, data_refresh, data_store, history_splice
from tests.helpers import make_ohlcv


def _read(path):
    return pd.read_csv(path, index_col=0, parse_dates=True)


def test_adjustments_owns_the_three_tolerances():
    assert adjustments.ADJUSTMENT_MISMATCH_TOLERANCE == 0.01
    assert adjustments.MIN_OVERLAP_BARS == 3
    assert adjustments.DELTA_OVERLAP_TOLERANCE == 1e-4
    for mod in (data_refresh, history_splice):
        assert mod.ADJUSTMENT_MISMATCH_TOLERANCE is adjustments.ADJUSTMENT_MISMATCH_TOLERANCE
        assert mod.MIN_OVERLAP_BARS is adjustments.MIN_OVERLAP_BARS
        src = inspect.getsource(mod)
        assert not re.search(r"^_?(ADJUSTMENT_MISMATCH_TOLERANCE|MIN_OVERLAP_BARS|"
                             r"_?ADJUSTMENT_RATIO_DISPERSION)\s*=", src, re.M), mod.__name__


def test_write_round_trips_and_leaves_only_the_target(tmp_path):
    df = make_ohlcv([100.0, 101.0, 102.0])
    path = str(tmp_path / "AAPL.csv")
    data_store.atomic_write_csv(df, path)
    pd.testing.assert_frame_equal(_read(path), df, check_freq=False)
    assert os.listdir(tmp_path) == ["AAPL.csv"]


def test_parent_directory_is_created(tmp_path):
    path = str(tmp_path / "daily_alpaca" / "AAPL_daily.csv")
    data_store.atomic_write_csv(make_ohlcv([1.0, 2.0]), path)
    assert os.path.exists(path)


def test_every_write_uses_its_own_temp_name(monkeypatch, tmp_path):
    seen = []
    real = data_store._replace_with_retry
    monkeypatch.setattr(data_store, "_replace_with_retry",
                        lambda tmp, path: (seen.append(tmp), real(tmp, path)))
    path = str(tmp_path / "AAPL.csv")
    data_store.atomic_write_csv(make_ohlcv([1.0]), path)
    data_store.atomic_write_csv(make_ohlcv([2.0]), path)
    assert len(set(seen)) == 2
    assert all(t.startswith(f"{path}.{os.getpid()}.") and t.endswith(".tmp") for t in seen)
    assert path + ".tmp" not in seen


def test_failed_replace_removes_its_temp_and_keeps_the_old_file(monkeypatch, tmp_path):
    path = str(tmp_path / "AAPL.csv")
    old = make_ohlcv([100.0, 101.0])
    data_store.atomic_write_csv(old, path)

    def boom(tmp, target):
        raise OSError("disk full")
    monkeypatch.setattr(data_store, "_replace_with_retry", boom)
    with pytest.raises(OSError):
        data_store.atomic_write_csv(make_ohlcv([1.0, 2.0, 3.0]), path)
    pd.testing.assert_frame_equal(_read(path), old, check_freq=False)
    assert os.listdir(tmp_path) == ["AAPL.csv"]


def _read_like(df, tmp_path):
    probe = str(tmp_path / "probe.csv.cmp")
    df.to_csv(probe)
    out = _read(probe)
    os.remove(probe)
    return out


def test_concurrent_writers_never_tear_the_file(tmp_path):
    path = str(tmp_path / "AAPL.csv")
    frames = [make_ohlcv([float(i)] * 50) for i in range(8)]

    def work(df):
        for _ in range(10):
            data_store.atomic_write_csv(df, path)
    threads = [threading.Thread(target=work, args=(f,)) for f in frames]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = _read(path)
    assert any(final.equals(_read_like(f, tmp_path)) for f in frames)
    assert os.listdir(tmp_path) == ["AAPL.csv"]


def test_every_existing_writer_goes_through_it(monkeypatch, tmp_path):
    calls = []
    real = data_store.atomic_write_csv

    def rec(df, path):
        calls.append(os.path.basename(path))
        real(df, path)
    monkeypatch.setattr(data_store, "atomic_write_csv", rec)
    monkeypatch.setattr(data_refresh, "atomic_write_csv", rec)
    base = str(tmp_path)
    data_store.save_to_disk(make_ohlcv([1.0, 2.0, 3.0, 4.0]), "AAPL", "daily", base_dir=base)
    data_store.update_cache(["AAPL"], "1d", base_dir=base,
                            fetch_fn=lambda s, start: make_ohlcv([4.0, 5.0], start="2024-01-05"))
    data_refresh._merge_save(None, make_ohlcv([1.0]), "MSFT", "daily", base)
    assert calls == ["AAPL.csv", "AAPL.csv", "MSFT.csv"]


def test_spot_writes_are_still_refused(tmp_path):
    with pytest.raises(ValueError):
        data_store.save_to_disk(make_ohlcv([1.0]), "XAUUSD", "daily", base_dir=str(tmp_path))
