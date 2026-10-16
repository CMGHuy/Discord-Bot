"""v162 AH19: the history store routes to its reader tests, and neither the
store nor the frozen snapshot can ever be committed."""
import importlib.util
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
READERS = ["tests/history_store/test_history_store.py",
           "tests/history_store/test_training_data.py"]


@pytest.fixture(scope="module")
def sel():
    spec = importlib.util.spec_from_file_location(
        "select_tests_v162", REPO / "scripts" / "dev" / "select_tests.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass resolves annotations through sys.modules
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", [
    "data/market_data/daily/AAPL.csv",
    "data/market_data/15min/_manifest.json",
])
def test_a_store_path_selects_its_reader_tests(sel, monkeypatch, path):
    # The threshold can only widen; stubbing it keeps the check about routing.
    monkeypatch.setattr(sel, "_threshold_reason", lambda *_a: None)
    result = sel.select([path], REPO)
    assert (result.full, result.targets) == (False, READERS)


def test_the_root_live_cache_is_not_routed_as_the_store(sel):
    """`market_data/` (live, data_store.py) and `data/market_data/` (v162) share
    folder names; only the second one is the history store."""
    assert sel._readers_of("market_data/daily/AAPL.csv") == ()


@pytest.mark.parametrize("path", [
    "data/market_data/daily/AAPL.csv",
    "data/backtest_cache_snapshot_v162/AAPL.csv",
    "data/backtest_cache_snapshot_v162/_hashes.json",
    "data/backtest_cache_snapshot_v162_2016/AAPL.csv",
])
def test_store_and_snapshot_are_gitignored(path):
    rc = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", path]).returncode
    assert rc == 0, f"{path} is not ignored"
