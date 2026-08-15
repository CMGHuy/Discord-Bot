"""Regression tests for !growth command-layer argument validation (Task E9
review round 2). growth_path()'s pct_to_target does math.log(current) /
math.log(target_multiple) * 100 -- target_multiple <= 0 raises ValueError
(math domain error) and target_multiple == 1.0 raises ZeroDivisionError
(math.log(1) == 0). growth_command() must reject target <= 1 BEFORE any of
that math ever runs."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from swingbot.commands.growth import growth_command, killswitch_command

# ~85% of suite runtime lives in nine files like this one; excluded from
# the fast tier (scripts/dev/testrun.py fast). See docs/claude/testing-cost.md.
pytestmark = pytest.mark.slow


@pytest.mark.parametrize("target", [1.0, 0.0, -3.0])
def test_growth_command_rejects_non_positive_target(target):
    ctx = MagicMock()
    ctx.send = AsyncMock()

    asyncio.run(growth_command.callback(ctx, target=target))

    ctx.send.assert_awaited_once()
    args, kwargs = ctx.send.call_args
    message = args[0] if args else kwargs.get("content", "")
    assert "target" in message.lower()
    assert "1x" in message
    # Must NOT be the normal report (which is fenced in a code block).
    assert "```" not in message
    assert "GROWTH REALITY CHECK" not in message


def test_growth_command_normal_target_proceeds_past_validation(monkeypatch):
    # A valid target (> 1x) must NOT hit the early-return validation path --
    # it should reach growth_report() and produce the normal fenced report.
    from swingbot.core import account as account_module

    # Empty/fresh account state: load_account_config with no balance history
    # is enough to prove _collect_stats/growth_report ran without needing to
    # thread real numbers through growth_path (that's already covered by
    # tests/test_edge_growth.py and tests/test_account_legs.py).
    monkeypatch.setattr(account_module, "load_account_config",
                        lambda: {"risk_pct": 1.0, "base_balance": None, "balance": None})
    monkeypatch.setattr(account_module, "get_balance_history_points", lambda: [])

    ctx = MagicMock()
    ctx.send = AsyncMock()

    asyncio.run(growth_command.callback(ctx, target=5.0))

    ctx.send.assert_awaited_once()
    args, _ = ctx.send.call_args
    message = args[0]
    assert "```" in message
    assert "GROWTH REALITY CHECK" in message
    assert "target 5x" in message


# --- !growth Monte Carlo fan attachment (Task E70) --------------------------

def _mc_trade(entry, stop, exit_price, direction="bullish"):
    return {"entry": entry, "stop_loss": stop, "exit_price": exit_price, "direction": direction}


def test_growth_command_attaches_mc_fan_with_enough_history(monkeypatch, tmp_path):
    import discord
    from swingbot.commands import growth as growth_mod
    from swingbot.core import account as account_module

    monkeypatch.setattr(account_module, "load_account_config",
                        lambda: {"risk_pct": 1.0, "base_balance": 10_000.0, "balance": 10_000.0})
    monkeypatch.setattr(account_module, "get_balance_history_points", lambda: [])
    monkeypatch.setattr(growth_mod.config, "EXPORT_DIR", str(tmp_path))

    trades = [_mc_trade(100, 98, 102) for _ in range(6)] + [_mc_trade(100, 98, 97) for _ in range(4)]
    fake_log = MagicMock()
    fake_log.get_trades.return_value = trades
    monkeypatch.setattr(growth_mod, "TradeLog", lambda: fake_log)

    ctx = MagicMock()
    ctx.send = AsyncMock()

    asyncio.run(growth_command.callback(ctx, target=10.0))

    ctx.send.assert_awaited_once()
    _, kwargs = ctx.send.call_args
    assert isinstance(kwargs.get("file"), discord.File)


def test_growth_command_no_chart_below_min_history(monkeypatch, tmp_path):
    from swingbot.commands import growth as growth_mod
    from swingbot.core import account as account_module

    monkeypatch.setattr(account_module, "load_account_config",
                        lambda: {"risk_pct": 1.0, "base_balance": 10_000.0, "balance": 10_000.0})
    monkeypatch.setattr(account_module, "get_balance_history_points", lambda: [])
    monkeypatch.setattr(growth_mod.config, "EXPORT_DIR", str(tmp_path))

    fake_log = MagicMock()
    fake_log.get_trades.return_value = [_mc_trade(100, 98, 102) for _ in range(3)]  # below MC_MIN_CLOSED_TRADES
    monkeypatch.setattr(growth_mod, "TradeLog", lambda: fake_log)

    ctx = MagicMock()
    ctx.send = AsyncMock()

    asyncio.run(growth_command.callback(ctx, target=10.0))

    ctx.send.assert_awaited_once()
    _, kwargs = ctx.send.call_args
    assert kwargs.get("file") is None


# --- !killswitch (Task E47 review Finding 2b) ------------------------------
# The command's own logic (status/on/off replies) is tested via
# killswitch_command.callback(ctx, action=...) directly -- same pattern as
# growth_command above, bypassing discord.py's command-invocation machinery
# so no real Discord connection is needed. The @commands.has_permissions
# guard is tested separately below since it lives on the Command wrapper
# (killswitch_command.checks), not inside the callback -- calling .callback
# directly, as the reply tests do, would never exercise it.

def test_killswitch_command_status_reports_off_by_default(monkeypatch, tmp_path):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "killswitch.json"))

    ctx = MagicMock()
    ctx.send = AsyncMock()

    asyncio.run(killswitch_command.callback(ctx, action="status"))

    ctx.send.assert_awaited_once()
    message = ctx.send.call_args[0][0]
    assert "off" in message


def test_killswitch_command_on_engages_and_status_reflects_it(monkeypatch, tmp_path):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "killswitch.json"))

    ctx = MagicMock()
    ctx.send = AsyncMock()

    asyncio.run(killswitch_command.callback(ctx, action="on"))
    message = ctx.send.call_args[0][0]
    assert "engaged" in message
    assert throttle.kill_state()["on"] is True

    ctx.send.reset_mock()
    asyncio.run(killswitch_command.callback(ctx, action="status"))
    message = ctx.send.call_args[0][0]
    assert "ON" in message and "manual" in message


def test_killswitch_command_off_releases(monkeypatch, tmp_path):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "killswitch.json"))
    throttle.set_kill(True, reason="manual")

    ctx = MagicMock()
    ctx.send = AsyncMock()

    asyncio.run(killswitch_command.callback(ctx, action="off"))
    message = ctx.send.call_args[0][0]
    assert "released" in message
    assert throttle.kill_state()["on"] is False


def test_killswitch_command_has_administrator_permission_guard():
    """The decorator must actually be present -- not just documented in the
    docstring -- so !killswitch can't be engaged/released by a non-admin."""
    assert killswitch_command.checks, (
        "killswitch_command must carry at least one check "
        "(the @commands.has_permissions(administrator=True) guard)"
    )


def test_killswitch_command_permission_check_rejects_non_administrator():
    from discord.ext.commands.errors import MissingPermissions

    ctx = MagicMock()
    ctx.permissions = discord.Permissions.none()

    with pytest.raises(MissingPermissions):
        killswitch_command.checks[0](ctx)


def test_killswitch_command_permission_check_allows_administrator():
    ctx = MagicMock()
    ctx.permissions = discord.Permissions.all()

    assert killswitch_command.checks[0](ctx) is True
