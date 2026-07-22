"""Regression tests for !growth command-layer argument validation (Task E9
review round 2). growth_path()'s pct_to_target does math.log(current) /
math.log(target_multiple) * 100 -- target_multiple <= 0 raises ValueError
(math domain error) and target_multiple == 1.0 raises ZeroDivisionError
(math.log(1) == 0). growth_command() must reject target <= 1 BEFORE any of
that math ever runs."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from swingbot.commands.growth import growth_command


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
