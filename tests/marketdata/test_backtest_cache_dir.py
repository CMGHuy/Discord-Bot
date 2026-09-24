"""v102: BACKTEST_CACHE_DIR redirects the backtest cache; unset keeps the default."""
from pathlib import Path

from swingbot import config
from swingbot.core.marketdata import backtest_cache as bc


def test_default_is_data_backtest_cache(monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    assert bc._cache_dir() == Path(config.DATA_DIR) / "backtest_cache"


def test_relative_override_resolves_against_project_root(monkeypatch):
    monkeypatch.setenv("BACKTEST_CACHE_DIR", "data/backtest_cache_ext")
    assert bc._cache_dir() == Path(config.DATA_DIR).parent / "data" / "backtest_cache_ext"


def test_absolute_override_is_used_verbatim(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(tmp_path / "ext"))
    assert bc._cache_dir() == tmp_path / "ext"


def test_empty_override_means_default(monkeypatch):
    monkeypatch.setenv("BACKTEST_CACHE_DIR", "")
    assert bc._cache_dir() == Path(config.DATA_DIR) / "backtest_cache"
