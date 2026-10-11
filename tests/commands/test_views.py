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
import ast
import os
import pathlib
import tempfile
import types
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from swingbot import config
from swingbot.commands import views as views_module
from swingbot.core.presentation import tokens as tk
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_manager_pending import _pending
from swingbot.commands.views import (
    PLAN_BUTTONS,
    PlanActionView,
    PlanBoardView,
    breakdown_embed,
    paginate,
    star_plan,
    starred_ids,
    unstar_plan,
)

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
PID_404 = "11111111-1111-4111-8111-111111111111"
PID_X = "22222222-2222-4222-8222-222222222222"
AUTHOR = 123456789012345678
OTHER = 876543210987654321


def _button(view, action: str):
    """The panel's button for one action (`chart`, `breakdown`, ...)."""
    return next(item for item in view.children if item.custom_id.split(":")[1] == action)


def _fake_interaction(user_id: int) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def test_info_has_no_direct_colour():
    tree = ast.parse(pathlib.Path("swingbot/commands/info.py").read_text(encoding="utf-8"))
    assert not [node.lineno for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and node.attr in ("Color", "Colour")]


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


def test_plan_action_view_has_one_button_per_action_chart_first():
    view = PlanActionView(PID, author_id=AUTHOR)
    assert view.timeout is None
    assert len(view.children) == len(PLAN_BUTTONS)
    assert [item.custom_id.split(":")[1] for item in view.children] == [cls.ACTION for cls in PLAN_BUTTONS]
    assert view.children[0].custom_id == f"plan:chart:{PID}:{AUTHOR}"


def test_interaction_check_rejects_wrong_user():
    view = PlanActionView(PID, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=OTHER)

    allowed = asyncio.run(_button(view, "chart").interaction_check(interaction))

    assert allowed is False
    interaction.response.send_message.assert_awaited_once_with(
        "Not your panel.", ephemeral=True
    )


def test_interaction_check_accepts_matching_user():
    view = PlanActionView(PID, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)

    allowed = asyncio.run(_button(view, "chart").interaction_check(interaction))

    assert allowed is True
    interaction.response.send_message.assert_not_awaited()


def test_chart_button_plan_not_found_sends_ephemeral_message():
    view = PlanActionView(PID_404, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)

    with patch.object(views_module.PlanStore, "get", return_value=None) as mock_get, \
         patch.object(views_module, "get_daily_data") as mock_get_daily_data, \
         patch.object(views_module, "generate_trade_chart") as mock_generate_chart:
        asyncio.run(view.children[0].callback(interaction))

    mock_get.assert_called_once_with(PID_404)
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    interaction.followup.send.assert_awaited_once_with(
        "This plan no longer exists (closed/cancelled and pruned).", ephemeral=True
    )
    mock_get_daily_data.assert_not_called()
    mock_generate_chart.assert_not_called()


def test_chart_button_happy_path_sends_chart_file():
    view = PlanActionView(PID, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)
    plan = _fake_plan()

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(tmp_fd)
    with open(tmp_path, "wb") as f:
        f.write(b"fake png bytes -- content never actually read, followup.send is mocked")

    sent_file = None
    try:
        with patch.object(views_module.PlanStore, "get", return_value=plan), \
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
    view = PlanActionView(PID, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)
    plan = _fake_plan()

    with patch.object(views_module.PlanStore, "get", return_value=plan), \
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
    view = PlanActionView(PID, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)
    plan = _fake_plan()

    with patch.object(views_module.PlanStore, "get", return_value=plan), \
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
        plan_id="abcd1234-plan", ticker="NVDA", confidence_level=5, badge="VALIDATED", quality_score=82,
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


def test_views_has_no_direct_colour_and_breakdown_matches_plan_confidence():
    tree = ast.parse(pathlib.Path("swingbot/commands/views.py").read_text(encoding="utf-8"))
    assert not [node.lineno for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and node.attr in ("Color", "Colour")]
    embed = breakdown_embed(_fixture_plan())
    assert embed.color.value == tk.ACCENT_RAMP[_fixture_plan().confidence_level]
    assert tk.DISCLAIMER in embed.footer.text


def test_breakdown_button_sends_ephemeral():
    view = PlanActionView(PID, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)
    with patch.object(views_module.PlanStore, "get", return_value=_fixture_plan()):
        asyncio.run(_button(view, "breakdown").callback(interaction))
    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True
    assert "embed" in kwargs


def _seed_plans(*plan_ids):
    from swingbot.core.planning.plan_engine import plan_to_dict
    from tests.store_seed import seed_store
    from tests.planning.test_plan_engine_model import _plan
    seed_store("plans", [plan_to_dict(_plan(plan_id=plan_id)) for plan_id in plan_ids])


def test_star_unstar_roundtrip():
    _seed_plans("p1", "p2")
    assert starred_ids() == set()
    star_plan("p1")
    star_plan("p2")
    assert starred_ids() == {"p1", "p2"}
    unstar_plan("p1")
    assert starred_ids() == {"p2"}
    assert starred_ids() == {"p2"}


def test_watch_button_toggles_star():
    _seed_plans(PID_X)
    view = PlanActionView(PID_X, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)
    asyncio.run(_button(view, "watch").callback(interaction))
    assert PID_X in starred_ids()
    asyncio.run(_button(view, "watch").callback(interaction))
    assert PID_X not in starred_ids()


def test_dismiss_button_removes_view_keeps_embed():
    view = PlanActionView(PID_X, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)
    asyncio.run(_button(view, "dismiss").callback(interaction))
    interaction.response.edit_message.assert_awaited_once_with(view=None)


def test_any_author_id_none_interaction_check_true_for_any_user():
    view = PlanActionView(PID_X, author_id=None)
    for uid in (1, AUTHOR, OTHER):
        assert asyncio.run(_button(view, "chart").interaction_check(_fake_interaction(user_id=uid))) is True


def _stub_render_fn(calls):
    def render(status, level, badge):
        calls.append((status, level, badge))
        return "content", discord.Embed(title="board")
    return render


def test_plan_board_view_has_4_children_and_apply_calls_render_fn():
    calls = []
    view = PlanBoardView(_stub_render_fn(calls), author_id=1)
    # 3 selects + refresh + prev + next -- prev/next are decorated methods
    # (Task B14) so they're present on every instance regardless of `items`.
    assert len(view.children) == 6
    asyncio.run(view._apply(status="ACTIVE", level="5", badge="All"))
    assert calls == [("ACTIVE", "5", "All")]


def test_paginate_middle_page():
    items, page_num, max_page = paginate(list(range(20)), page=2, per_page=8)
    assert items == [16, 17, 18, 19]
    assert page_num == 2
    assert max_page == 2  # 0-indexed: pages 0,1,2 for 20 items at 8/page


def test_paginate_clamps_out_of_range_page():
    items, page_num, max_page = paginate(list(range(5)), page=99, per_page=8)
    assert items == [0, 1, 2, 3, 4]
    assert page_num == 0
    assert max_page == 0


def test_plan_board_view_has_6_children_after_pagination():
    calls = []
    view = PlanBoardView(_stub_render_fn(calls), author_id=1, items=list(range(20)))
    assert len(view.children) == 6  # 3 selects + refresh + prev + next

def test_breakdown_button_reads_plan_created_after_views_import(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    plan = _pending(plan_id=PID, ticker="MSFT")
    PlanStore().add(plan)
    view = PlanActionView(plan.plan_id, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)

    asyncio.run(_button(view, "breakdown").callback(interaction))

    interaction.response.send_message.assert_awaited_once()
