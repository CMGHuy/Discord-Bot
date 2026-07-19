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
import os
import tempfile
import types
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from swingbot.commands import views as views_module
from swingbot.commands.views import (
    PlanActionView,
    breakdown_embed,
    star_plan,
    starred_ids,
    unstar_plan,
)


def _fake_interaction(user_id: int) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _fake_plan(**overrides) -> types.SimpleNamespace:
    defaults = dict(
        ticker="AAPL",
        horizon_key="2w",
        trigger_price=100.0,
        stop_loss=95.0,
        tp1=110.0,
        tp2=120.0,
        direction="long",
        strategy="RSI",
        plan_id="plan-123",
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def test_plan_action_view_has_one_chart_button():
    view = PlanActionView("plan-123", author_id=42)
    assert view.timeout == 180
    assert len(view.children) == 4
    custom_ids = [item.custom_id for item in view.children]
    assert "plan:chart" in custom_ids
    assert "plan:breakdown" in custom_ids
    assert "plan:watch" in custom_ids
    assert "plan:dismiss" in custom_ids
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


def test_on_timeout_disables_children_and_edits_message():
    view = PlanActionView("plan-123", author_id=42)
    message = MagicMock()
    message.edit = AsyncMock()
    view.message = message

    asyncio.run(view.on_timeout())

    assert view.children  # sanity: there is at least the chart button
    assert all(item.disabled for item in view.children)
    message.edit.assert_awaited_once_with(view=view)


def test_on_timeout_without_message_does_not_raise():
    view = PlanActionView("plan-123", author_id=42)
    assert view.message is None

    asyncio.run(view.on_timeout())  # must not raise despite no message to edit

    assert all(item.disabled for item in view.children)


def test_chart_button_plan_not_found_sends_ephemeral_message():
    view = PlanActionView("plan-404", author_id=42)
    interaction = _fake_interaction(user_id=42)

    with patch.object(views_module._plan_store, "get", return_value=None) as mock_get, \
         patch.object(views_module, "get_daily_data") as mock_get_daily_data, \
         patch.object(views_module, "generate_trade_chart") as mock_generate_chart:
        asyncio.run(view.children[0].callback(interaction))

    mock_get.assert_called_once_with("plan-404")
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    interaction.followup.send.assert_awaited_once_with(
        "This plan no longer exists (closed/cancelled and pruned).", ephemeral=True
    )
    mock_get_daily_data.assert_not_called()
    mock_generate_chart.assert_not_called()


def test_chart_button_happy_path_sends_chart_file():
    view = PlanActionView("plan-123", author_id=42)
    interaction = _fake_interaction(user_id=42)
    plan = _fake_plan()

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(tmp_fd)
    with open(tmp_path, "wb") as f:
        f.write(b"fake png bytes -- content never actually read, followup.send is mocked")

    sent_file = None
    try:
        with patch.object(views_module._plan_store, "get", return_value=plan), \
             patch.object(views_module, "get_daily_data", return_value=MagicMock()) as mock_get_daily_data, \
             patch.object(views_module, "get_currency_symbol", return_value="$"), \
             patch.object(views_module, "generate_trade_chart", return_value=tmp_path) as mock_generate_chart:
            asyncio.run(view.children[0].callback(interaction))

        mock_get_daily_data.assert_called_once_with(plan.ticker)
        mock_generate_chart.assert_called_once()
        interaction.followup.send.assert_awaited_once()
        _, kwargs = interaction.followup.send.call_args
        assert kwargs["ephemeral"] is True
        sent_file = kwargs["file"]
        assert isinstance(sent_file, discord.File)
        assert sent_file.filename == os.path.basename(tmp_path)
    finally:
        if sent_file is not None:
            sent_file.close()  # release the OS handle discord.File opened on tmp_path
        os.remove(tmp_path)


def test_chart_button_data_fetch_failure_sends_ephemeral_error():
    view = PlanActionView("plan-123", author_id=42)
    interaction = _fake_interaction(user_id=42)
    plan = _fake_plan()

    with patch.object(views_module._plan_store, "get", return_value=plan), \
         patch.object(views_module, "get_daily_data", side_effect=ValueError("no data available")) as mock_get_daily_data, \
         patch.object(views_module, "generate_trade_chart") as mock_generate_chart:
        asyncio.run(view.children[0].callback(interaction))

    mock_get_daily_data.assert_called_once_with(plan.ticker)
    mock_generate_chart.assert_not_called()
    interaction.followup.send.assert_awaited_once()
    args, kwargs = interaction.followup.send.call_args
    assert "Could not fetch price data for AAPL" in args[0]
    assert kwargs["ephemeral"] is True


def test_chart_button_render_failure_sends_ephemeral_error():
    view = PlanActionView("plan-123", author_id=42)
    interaction = _fake_interaction(user_id=42)
    plan = _fake_plan()

    with patch.object(views_module._plan_store, "get", return_value=plan), \
         patch.object(views_module, "get_daily_data", return_value=MagicMock()), \
         patch.object(views_module, "get_currency_symbol", return_value="$"), \
         patch.object(views_module, "generate_trade_chart", side_effect=RuntimeError("render exploded")) as mock_generate_chart:
        asyncio.run(view.children[0].callback(interaction))

    mock_generate_chart.assert_called_once()
    interaction.followup.send.assert_awaited_once()
    args, kwargs = interaction.followup.send.call_args
    assert "Chart render failed" in args[0]
    assert kwargs["ephemeral"] is True


def _fixture_plan():
    return types.SimpleNamespace(
        plan_id="abcd1234-plan", ticker="NVDA", tier="A", badge="VALIDATED", quality_score=82,
        quality_breakdown=[("Trend alignment", 20), ("Volume confirmation", 15), ("Multi-strategy confluence", 47)],
        badge_stats={"status": "VALIDATED", "n": 206, "win_rate": 81.6, "expectancy_r": 0.42, "window": "2024-2025"},
        regime_aligned=True, created_at="2026-07-11",
        status="ACTIVE",
        status_history=[
            {"status": "PENDING", "reason": None, "at": "2026-07-10T09:00:00+00:00"},
            {"status": "ACTIVE", "reason": "trigger_hit", "at": "2026-07-11T10:15:00+00:00"},
        ],
    )


def test_breakdown_embed_has_one_field_per_section_and_every_quality_line():
    embed = breakdown_embed(_fixture_plan())
    names = [f.name for f in embed.fields]
    assert any("quality" in n.lower() for n in names)
    assert any("track record" in n.lower() or "badge" in n.lower() for n in names)
    assert any("follow" in n.lower() for n in names)
    assert any("timeline" in n.lower() or "status" in n.lower() for n in names)
    quality_field = next(f for f in embed.fields if "quality" in f.name.lower())
    for label, pts in _fixture_plan().quality_breakdown:
        assert label in quality_field.value and str(pts) in quality_field.value


def test_breakdown_button_sends_ephemeral():
    view = PlanActionView("abcd1234-plan", author_id=1)
    interaction = _fake_interaction(user_id=1)
    with patch.object(views_module._plan_store, "get", return_value=_fixture_plan()):
        asyncio.run(view.breakdown_button.callback(interaction))
    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True
    assert "embed" in kwargs


def test_star_unstar_roundtrip(tmp_path, monkeypatch):
    star_path = str(tmp_path / "starred_plans.json")
    monkeypatch.setattr("swingbot.commands.views._STARRED_PATH", star_path)
    assert starred_ids() == set()
    star_plan("p1")
    star_plan("p2")
    assert starred_ids() == {"p1", "p2"}
    unstar_plan("p1")
    assert starred_ids() == {"p2"}
    assert starred_ids() == {"p2"}


def test_watch_button_toggles_star(tmp_path, monkeypatch):
    star_path = str(tmp_path / "starred_plans.json")
    monkeypatch.setattr("swingbot.commands.views._STARRED_PATH", star_path)
    view = PlanActionView("plan-x", author_id=1)
    interaction = _fake_interaction(user_id=1)
    asyncio.run(view.watch_button.callback(interaction))
    assert "plan-x" in starred_ids()
    asyncio.run(view.watch_button.callback(interaction))
    assert "plan-x" not in starred_ids()


def test_dismiss_button_removes_view_keeps_embed():
    view = PlanActionView("plan-x", author_id=1)
    interaction = _fake_interaction(user_id=1)
    asyncio.run(view.dismiss_button.callback(interaction))
    interaction.response.edit_message.assert_awaited_once_with(view=None)


def test_any_author_id_none_interaction_check_true_for_any_user():
    view = PlanActionView("plan-x", author_id=None)
    for uid in (1, 2, 999999):
        assert asyncio.run(view.interaction_check(_fake_interaction(user_id=uid))) is True
