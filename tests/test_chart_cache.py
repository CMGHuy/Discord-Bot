# tests/test_chart_cache.py
import os
import time

import pytest

from swingbot.core.charts.cache import _key_hash, cached_chart, purge


def _counting_render(calls):
    def render(target_path):
        calls.append(target_path)
        with open(target_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 100)  # minimal PNG-ish blob, enough to test file existence/size
        return target_path
    return render


def test_cached_chart_renders_once_for_same_key(tmp_path):
    calls = []
    key = {"trade_id": "T1", "closed_at": "2026-07-05", "v": 3}
    p1 = cached_chart(key, _counting_render(calls), cache_dir=str(tmp_path))
    p2 = cached_chart(key, _counting_render(calls), cache_dir=str(tmp_path))
    assert p1 == p2
    assert len(calls) == 1
    assert os.path.exists(p1)


def test_cached_chart_rerenders_on_changed_key(tmp_path):
    calls = []
    p1 = cached_chart({"trade_id": "T1", "v": 3}, _counting_render(calls), cache_dir=str(tmp_path))
    p2 = cached_chart({"trade_id": "T1", "v": 4}, _counting_render(calls), cache_dir=str(tmp_path))
    assert p1 != p2
    assert len(calls) == 2


def test_cached_chart_atomic_write_never_leaves_corrupt_file_on_failed_render(tmp_path):
    """A render that crashes partway through (after writing partial bytes
    to the path it was given) must never leave anything at the real cache
    path -- otherwise a future call would treat that corrupt partial file
    as a permanent valid cache hit forever."""
    def bad_render(path):
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"TRUNCATED")  # partial write
        raise RuntimeError("boom: crashed mid-render")

    key = {"trade_id": "T-crash", "v": 3}
    target_path = os.path.join(str(tmp_path), f"{_key_hash(key)}.png")

    with pytest.raises(RuntimeError, match="boom"):
        cached_chart(key, bad_render, cache_dir=str(tmp_path))

    assert not os.path.exists(target_path)
    # No leftover files at all should be treated as valid PNGs at the real
    # target path -- only an orphaned .tmp (if any) is acceptable.
    leftover = os.listdir(str(tmp_path))
    for name in leftover:
        assert name != f"{_key_hash(key)}.png"

    # A subsequent, successful call for the same key must still render
    # fresh rather than short-circuiting on the earlier failure's debris.
    calls = []
    p = cached_chart(key, _counting_render(calls), cache_dir=str(tmp_path))
    assert len(calls) == 1
    assert os.path.exists(p)
    assert p == target_path


def test_purge_removes_stale_files(tmp_path):
    calls = []
    p1 = cached_chart({"k": "a"}, _counting_render(calls), cache_dir=str(tmp_path))
    old_time = time.time() - 8 * 86400
    os.utime(p1, (old_time, old_time))
    removed = purge(max_age_days=7, cache_dir=str(tmp_path))
    assert removed == 1
    assert not os.path.exists(p1)
