"""
Tests for swingbot/commands/views.py's PlanActionView -- the author-lock
skeleton plus the Chart button. These exercise real async coroutines
(interaction_check, chart_button) by driving them with asyncio.run(...)
directly rather than via @pytest.mark.asyncio -- pytest-asyncio is not a
dependency of this repo (verified: not installed, not in requirements.txt,
no pytest.ini) and Plan B's Global Constraints forbid adding a new one, so
plain functions + asyncio.run() exercise the identical code paths without
any new pip package or pytest config file.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from swingbot.commands.views import PlanActionView


def _fake_interaction(user_id: int) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def test_plan_action_view_has_one_chart_button():
    view = PlanActionView("plan-123", author_id=42)
    assert view.timeout == 180
    assert len(view.children) == 1
    assert view.children[0].custom_id == "plan:chart"


def test_interaction_check_rejects_wrong_user():
    view = PlanActionView("plan-123", author_id=42)
    interaction = _fake_interaction(user_id=999)

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False
    interaction.response.send_message.assert_awaited_once_with(
        "Not your panel.", ephemeral=True
    )


def test_interaction_check_accepts_matching_user():
    view = PlanActionView("plan-123", author_id=42)
    interaction = _fake_interaction(user_id=42)

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is True
    interaction.response.send_message.assert_not_awaited()
