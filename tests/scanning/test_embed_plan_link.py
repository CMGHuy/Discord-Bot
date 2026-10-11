"""Plan-carrying Discord titles use the current public admin URL."""
import ast
from pathlib import Path

import pytest

from swingbot import config
from swingbot.commands import trades
from swingbot.commands.trades import _build_trade_detail_embed
from swingbot.commands.views import breakdown_embed
from swingbot.core.scanning import alert_embeds, execution_embeds, lifecycle_embeds
from tests.commands.test_trades_display import _winning_trade
from tests.scanning.test_embeds_v3 import make_item, make_plan_v2


BASE = "https://swingbot.example.com"
PLAN_ID = "44444444-4444-4444-8444-444444444444"
LINK = "https://swingbot.example.com/plans/44444444-4444-4444-8444-444444444444"
MODULE_COUNTS = {
    "swingbot/core/scanning/alert_embeds.py": 4,
    "swingbot/core/scanning/execution_embeds.py": 1,
    "swingbot/core/scanning/lifecycle_embeds.py": 3,
    "swingbot/commands/views.py": 1,
    "swingbot/commands/trades.py": 1,
}


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", BASE)
    # Ticket sizing otherwise reads the account store; it does not affect links.
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)
    monkeypatch.setattr(trades, "get_currency_symbol", lambda ticker, fallback: "$")
    monkeypatch.setattr(lifecycle_embeds, "get_currency_symbol", lambda ticker, fallback: "$")


def _plan():
    return make_plan_v2(plan_id=PLAN_ID)


@pytest.mark.parametrize("builder", [
    alert_embeds.build_strategy_alert_embed,
    alert_embeds.build_strategy_simple_embed,
    breakdown_embed,
])
def test_strategy_and_breakdown_titles_link_to_the_plan(builder):
    assert builder(_plan()).to_dict()["url"] == LINK


def test_execution_ticket_title_links_to_the_plan():
    plan = _plan()
    embed = execution_embeds.build_ticket_embed(make_item(plan_v2=plan), plan)
    assert embed.to_dict()["url"] == LINK


def test_near_close_title_links_to_the_trade_plan():
    trade = _winning_trade()
    trade["plan_id"] = PLAN_ID
    warning = {"trade": trade, "near_which": "stop-loss", "sl_dist_pct": 0.5,
               "tp_dist_pct": 5.0, "current_price": 0.11}
    assert lifecycle_embeds.build_near_close_embed(warning).to_dict()["url"] == LINK


def test_trade_command_title_links_to_the_plan():
    trade = _winning_trade()
    trade["plan_id"] = PLAN_ID
    assert _build_trade_detail_embed(trade).to_dict()["url"] == LINK


def test_legacy_trade_command_has_no_title_link():
    assert "url" not in _build_trade_detail_embed(_winning_trade()).to_dict()


def test_unset_public_url_keeps_the_title_unlinked(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "")
    assert "url" not in alert_embeds.build_strategy_alert_embed(_plan()).to_dict()


def test_runtime_config_change_updates_the_next_embed(monkeypatch):
    first = alert_embeds.build_strategy_alert_embed(_plan())
    # Exercise the reload's field update without reading the real .env or
    # changing unrelated config globals used by other tests in this process.
    field = next(field for field in config.FIELDS if field.attr == "ADMIN_PUBLIC_URL")
    monkeypatch.setattr(config, "FIELDS", [field])
    monkeypatch.setenv("ADMIN_PUBLIC_URL", "https://new.example.com")
    config._apply_env()
    second = alert_embeds.build_strategy_alert_embed(_plan())
    assert first.url == LINK
    assert second.url == f"https://new.example.com/plans/{PLAN_ID}"


def test_rendered_link_changes_only_the_embed_url(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "")
    before = alert_embeds.build_strategy_alert_embed(_plan()).to_dict()
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", BASE)
    after = alert_embeds.build_strategy_alert_embed(_plan()).to_dict()
    assert "url" not in before
    assert after.pop("url") == LINK
    before.pop("timestamp")
    after.pop("timestamp")
    assert after == before


def _plan_chrome_calls(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "ui" and node.func.attr == "apply_chrome"
            and any(keyword.arg == "plan_id" for keyword in node.keywords)]


@pytest.mark.parametrize("path,expected_count", MODULE_COUNTS.items())
def test_all_plan_chrome_calls_read_the_current_url(path, expected_count):
    calls = _plan_chrome_calls(path)
    assert len(calls) == expected_count
    for call in calls:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert "link_base" in keywords, f"{path}:{call.lineno} missing link base"
        assert ast.dump(keywords["link_base"]) == ast.dump(
            ast.parse("config.ADMIN_PUBLIC_URL", mode="eval").body)
