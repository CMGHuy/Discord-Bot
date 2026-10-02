"""v111 §4: level and wording fixes to existing log lines."""
import asyncio
import logging

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core.marketdata import data as data_mod
from swingbot.core.scanning import scan_run


def _records(caplog, logger):
    return [r for r in caplog.records if r.name == logger.name]


def test_earnings_inside_the_window_is_info_not_warning(monkeypatch, caplog):
    monkeypatch.setattr(scan_run, "earnings_within_window", lambda ticker, days: ("2026-10-01", 3))
    with caplog.at_level(logging.DEBUG, logger=scan_run.log.name):
        assert scan_run._earnings_in_window("AAPL", 20) == ("2026-10-01", 3)
    [record] = _records(caplog, scan_run.log)
    assert record.levelno == logging.INFO and "AAPL has earnings 2026-10-01 (3d away)" in record.getMessage()


def test_an_earnings_lookup_error_is_none_at_debug(monkeypatch, caplog):
    def boom(ticker, days):
        raise RuntimeError("yahoo")

    monkeypatch.setattr(scan_run, "earnings_within_window", boom)
    with caplog.at_level(logging.DEBUG, logger=scan_run.log.name):
        assert scan_run._earnings_in_window("AAPL", 20) is None
    assert [r.levelno for r in _records(caplog, scan_run.log)] == [logging.DEBUG]


def test_trade_monitor_batch_price_failure_is_a_warning(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise TimeoutError("hung")

    monkeypatch.setattr(loops, "_run_bounded", boom)
    with caplog.at_level(logging.DEBUG, logger=loops.log.name):
        assert asyncio.run(loops._live_price_batch(["AAPL"])) == {}
    [record] = _records(caplog, loops.log)
    assert record.levelno == logging.WARNING and record.exc_info is not None


def test_trade_monitor_with_no_open_tickers_fetches_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(loops, "_run_bounded", lambda *args, **kwargs: calls.append(args))
    assert asyncio.run(loops._live_price_batch([])) == {}
    assert calls == []


def test_prefetch_batch_failure_is_a_warning(monkeypatch, caplog):
    def boom(tickers):
        raise ConnectionError("down")

    monkeypatch.setattr(data_mod, "get_current_price_batch", boom)
    with caplog.at_level(logging.DEBUG, logger=data_mod.log.name):
        data_mod.prefetch_prices(["AAPL"])
    [record] = [r for r in _records(caplog, data_mod.log) if "prefetch_prices" in r.getMessage()]
    assert record.levelno == logging.WARNING and record.exc_info is not None


def test_admin_trigger_names_the_real_setting(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(loops, "auto_reload_if_changed", lambda: {}, raising=False)
    monkeypatch.setattr(loops.runstate, "is_trigger_requested", lambda: True)
    monkeypatch.setattr(loops.runstate, "clear_trigger", lambda: None)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "")
    with caplog.at_level(logging.WARNING, logger=loops.log.name):
        asyncio.run(loops.config_watcher.coro())
    assert "DISCORD_CHANNEL_TRADES_ID not set; cannot post scan results." in [
        r.getMessage() for r in _records(caplog, loops.log)]
