import asyncio
from unittest.mock import MagicMock

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import loops as loops_mod
from swingbot.commands.scanning import recap
from swingbot.core.scanning import scan_run


def test_hard_filter_snapshot_survives_later_config_change(monkeypatch):
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 2.0)
    filters = scan_run._hard_filters_snapshot()
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 9.0)

    assert filters["min_risk_reward_ratio"] == 2.0


def test_weekend_scan_does_not_revert_hot_reloaded_value(monkeypatch):
    async def scan(**_kwargs):
        config.MIN_ALERT_CONFIDENCE_LEVEL = 5
        return []

    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 3)
    monkeypatch.setattr(recap.scan_engine, "run_scan", scan)

    asyncio.run(scanning_mod.weekend_deep_scan())

    assert config.MIN_ALERT_CONFIDENCE_LEVEL == 5


def test_enabling_market_refresh_starts_the_loop(monkeypatch):
    start = MagicMock()
    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", True)
    monkeypatch.setattr(scanning_mod.market_data_refresh, "is_running", lambda: False)
    monkeypatch.setattr(scanning_mod.market_data_refresh, "start", start)

    loops_mod._apply_market_data_refresh_config({"MARKET_DATA_AUTO_REFRESH": (False, True)})

    start.assert_called_once_with()
