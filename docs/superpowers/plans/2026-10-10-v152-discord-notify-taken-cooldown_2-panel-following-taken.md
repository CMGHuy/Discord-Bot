# v152 part 2: persistent panel, Following, `taken` dimension

**Spec:** [`docs/superpowers/specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md`](../specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md) § D2
**Index:** [`2026-10-10-v152-discord-notify-taken-cooldown_0-index.md`](2026-10-10-v152-discord-notify-taken-cooldown_0-index.md): Global Constraints, Decisions fixed by this index, the task ledger and `## Parallelisation` live there and bind every task below.

Tasks V152-6 .. V152-9 (V152-10 lives in [`_2b-spa-followed-option`](2026-10-10-v152-discord-notify-taken-cooldown_2b-spa-followed-option.md); split only to stay under 1500 lines). None is v151-gated. Part 1's V152-3 creates `swingbot/core/db/repositories/followers.py` (`followers_repo()`, `FOLLOW_KINDS`), which V152-7 and V152-8 import; V152-2 creates the `plan_followers` table with its FK into `plans` (cascade). Every test that writes a follower row must therefore seed the plan first.

Test ids: every test file below defines its own `PID` (a 36-char dashed uuid) and `AUTHOR`/`OTHER` (18-digit snowflakes) — the persistent `custom_id` template rejects short ids such as `"plan-123"` or `42`.

# Phase 1: Persistent panel

### Task V152-6: Persistent plan panel, legacy fallback, `setup_hook`

**Model:** sonnet — a multi-file discord.py refactor with a fixed contract (DynamicItem template, registration hook), no schema or numerics.

**Swallowed-error ratchet (audit 2026-10-10):** this task adds `except Exception` handlers. If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), apply the index Global Constraints bullet "Swallowed-error ratchet (v148)" to every one that does not re-raise (`except Exception as exc:` + `swallowed(log, "ops.<module>.<function>", exc, level=logging.DEBUG)` first, keep the existing log line, unique tag) and run `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` before the commit. Otherwise write them as planned.

**Files:**
- Modify: `swingbot/commands/views.py` (imports; replace `class PlanActionView` at `:45-131`; module docstring first paragraph)
- Modify: `swingbot/bot_core.py` (add `setup_hook` after the `bot = commands.Bot(...)` line `:35` block, beside the other `@bot.event` handlers at `:322`)
- Modify: `tests/commands/test_views.py` (panel tests move from the view to its items; uuid plan ids, snowflake author ids)
- Create: `tests/commands/test_views_persistent.py`

**Contract (ledger):** `PLAN_TEMPLATE_RE`, `custom_id_for(action, plan_id, author_id) -> str`, `ChartButton`/`BreakdownButton`/`WatchButton`/`DismissButton` (`DynamicItem[discord.ui.Button]`, `__init__(self, plan_id: str, author_id: int | None = None)`, `from_custom_id`), `PLAN_BUTTONS`, `PlanActionView(plan_id, author_id)` with `timeout=None`, `chart_only_view(plan_id) -> discord.ui.View`, `LegacyPlanPanel`, `LEGACY_REPLY`, `register_persistent_views(bot) -> None`, `bot_core.setup_hook()`. V152-8 appends `FollowingButton` to `PLAN_BUTTONS` and swaps the Watch body; V152-17 consumes `chart_only_view`.

**Behaviour kept:** Chart, Breakdown, Watch (still the global star in this task; V152-8 makes it per-user) and Dismiss reply exactly as today. Changed: plan reads move to `asyncio.to_thread`; the view never times out; the author lock lives on each button, parsed from its `custom_id`, so a `!top` panel keeps its lock after a restart. `alerts.py:80` (digest), `_post_alert` in `alerts.py` (`view_cls(plan.plan_id, author_id=None)`) and `stats.py:123` need no edit: the constructor signature is unchanged except the dropped `timeout` keyword, which no caller passes. Their `view.message = ...` assignments stay harmless (the attribute is kept).

**Why a guard on the id:** `DynamicItem.__init__` raises `ValueError` when the `custom_id` does not match its template. Production plan ids are `uuid4` strings (`builders.py:461`, `:606`) and Discord user ids are 17-20 digits, but a malformed id must never cost an alert its post: `PlanActionView` logs a WARNING and builds an empty view instead of raising inside `_post_alert`.

- [ ] **Step 1: Write the failing persistence tests**

Create `tests/commands/test_views_persistent.py`:

```python
"""v152 D2: the plan panel survives a restart.

Every plan button is a discord.ui.DynamicItem whose custom_id carries the
plan id (and, for a `!top` panel, the author id), so discord.py can rebuild
the item from the custom_id alone after the process restarts. Pre-v152
alerts carry the old static ids (`plan:chart` ...); LegacyPlanPanel answers
them. No pytest-asyncio here: coroutines run through asyncio.run.
"""
import asyncio
import inspect
import logging
from unittest.mock import AsyncMock, MagicMock

import discord
from discord.ext import commands

from swingbot.commands import views
from swingbot.commands.views import (
    LEGACY_REPLY,
    PLAN_BUTTONS,
    ChartButton,
    LegacyPlanPanel,
    PlanActionView,
    chart_only_view,
    custom_id_for,
    register_persistent_views,
)

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
AUTHOR = 123456789012345678
OTHER = 876543210987654321


def _interaction(user_id: int) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _rebuild(button_cls, custom_id: str):
    """What discord.py does on a button press after a restart: fullmatch the
    custom_id against the registered template, then from_custom_id."""
    match = button_cls.__discord_ui_compiled_template__.fullmatch(custom_id)
    assert match is not None, custom_id
    return asyncio.run(button_cls.from_custom_id(_interaction(OTHER), MagicMock(), match))


def test_custom_id_carries_the_plan_and_optionally_the_author():
    assert custom_id_for("chart", PID, None) == f"plan:chart:{PID}"
    assert custom_id_for("chart", PID, AUTHOR) == f"plan:chart:{PID}:{AUTHOR}"


def test_every_custom_id_fits_discords_100_char_limit():
    longest = max(len(custom_id_for(cls.ACTION, PID, 10 ** 19)) for cls in PLAN_BUTTONS)
    assert longest <= 100


def test_each_button_rebuilds_from_its_custom_id_alone_without_author():
    for cls in PLAN_BUTTONS:
        item = _rebuild(cls, custom_id_for(cls.ACTION, PID, None))
        assert isinstance(item, cls)
        assert (item.plan_id, item.author_id) == (PID, None)
        assert item.custom_id == custom_id_for(cls.ACTION, PID, None)


def test_each_button_rebuilds_with_its_author_segment():
    for cls in PLAN_BUTTONS:
        item = _rebuild(cls, custom_id_for(cls.ACTION, PID, AUTHOR))
        assert (item.plan_id, item.author_id) == (PID, AUTHOR)


def test_the_top_panel_lock_holds_after_a_rebuild():
    item = _rebuild(ChartButton, custom_id_for("chart", PID, AUTHOR))
    stranger = _interaction(OTHER)
    assert asyncio.run(item.interaction_check(stranger)) is False
    stranger.response.send_message.assert_awaited_once_with("Not your panel.", ephemeral=True)
    assert asyncio.run(item.interaction_check(_interaction(AUTHOR))) is True


def test_an_alert_panel_with_no_author_accepts_anyone_after_a_rebuild():
    item = _rebuild(ChartButton, custom_id_for("chart", PID, None))
    for uid in (AUTHOR, OTHER):
        assert asyncio.run(item.interaction_check(_interaction(uid))) is True


def test_the_legacy_static_ids_match_no_dynamic_template():
    for legacy in ("plan:chart", "plan:breakdown", "plan:watch", "plan:dismiss"):
        assert all(cls.__discord_ui_compiled_template__.fullmatch(legacy) is None
                   for cls in PLAN_BUTTONS)


def test_plan_action_view_is_persistent_and_holds_one_button_per_action():
    view = PlanActionView(PID, author_id=None)
    assert view.timeout is None
    assert view.is_persistent()
    assert [type(item) for item in view.children] == list(PLAN_BUTTONS)
    assert [item.custom_id for item in view.children] == [
        custom_id_for(cls.ACTION, PID, None) for cls in PLAN_BUTTONS]


def test_a_malformed_plan_id_posts_an_empty_panel_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="swingbot.commands.views"):
        view = PlanActionView("not-a-uuid", author_id=None)
    assert view.children == []
    assert "persistent custom_id" in caplog.text


def test_chart_only_view_carries_just_the_chart_button():
    view = chart_only_view(PID)
    assert view.timeout is None
    assert [type(item) for item in view.children] == [ChartButton]


def test_legacy_panel_claims_the_four_static_ids_and_is_persistent():
    panel = LegacyPlanPanel()
    assert panel.timeout is None and panel.is_persistent()
    assert sorted(item.custom_id for item in panel.children) == [
        "plan:breakdown", "plan:chart", "plan:dismiss", "plan:watch"]


def test_legacy_chart_breakdown_watch_reply_with_the_predates_line():
    panel = LegacyPlanPanel()
    for custom_id in ("plan:chart", "plan:breakdown", "plan:watch"):
        item = next(i for i in panel.children if i.custom_id == custom_id)
        interaction = _interaction(OTHER)
        asyncio.run(item.callback(interaction))
        interaction.response.send_message.assert_awaited_once_with(LEGACY_REPLY, ephemeral=True)


def test_legacy_dismiss_still_removes_the_panel():
    panel = LegacyPlanPanel()
    item = next(i for i in panel.children if i.custom_id == "plan:dismiss")
    interaction = _interaction(OTHER)
    asyncio.run(item.callback(interaction))
    interaction.response.edit_message.assert_awaited_once_with(view=None)


def test_register_persistent_views_adds_every_dynamic_item_and_the_legacy_panel():
    bot = MagicMock()
    register_persistent_views(bot)
    bot.add_dynamic_items.assert_called_once_with(*PLAN_BUTTONS)
    (legacy,), _ = bot.add_view.call_args
    assert isinstance(legacy, LegacyPlanPanel)


def test_register_persistent_views_is_accepted_by_a_real_bot():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    register_persistent_views(bot)
    assert any(isinstance(view, LegacyPlanPanel) for view in bot.persistent_views)
    registered = set(bot._connection._view_store._dynamic_items.values())
    assert registered == set(PLAN_BUTTONS)


def test_bot_core_setup_hook_registers_the_persistent_views(monkeypatch):
    from swingbot import bot_core
    seen = []
    monkeypatch.setattr(views, "register_persistent_views", seen.append)
    asyncio.run(bot_core.bot.setup_hook())
    assert seen == [bot_core.bot]


def test_button_plan_reads_run_off_the_event_loop():
    for cls in (views.ChartButton, views.BreakdownButton):
        source = inspect.getsource(cls.callback) + inspect.getsource(views._send_chart)
        assert "PlanStore().get(" not in source
        assert "to_thread(_get_plan" in source
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_views_persistent.py`
Expected: FAIL at import (`ImportError: cannot import name 'LEGACY_REPLY'`).

- [ ] **Step 3: Replace `PlanActionView` with persistent buttons**

In `swingbot/commands/views.py`, add `import re` to the stdlib imports (after `import os`). Replace the first paragraph of the module docstring with:

```python
"""
Interactive discord.ui.View subclasses for the plan-centric UX: a
per-alert action panel (chart / breakdown / watch / dismiss buttons --
PlanActionView) and the filterable/paginated !plans board (PlanBoardView).

v152 D2: the plan panel is persistent. Each of its buttons is a
discord.ui.DynamicItem whose custom_id carries the plan id (plus the author
id for an author-locked `!top` panel), registered once in bot_core's
setup_hook, so a press on an alert posted before a restart still works.
LegacyPlanPanel answers the static ids pre-v152 alerts carry. PlanBoardView
keeps the TradesPaginator author-lock / timeout pattern
(swingbot/commands/trades.py:83).
"""
```

Then replace the whole `class PlanActionView(discord.ui.View):` block (from `class PlanActionView` down to, not including, `def breakdown_embed(plan)`) with:

```python
PLAN_TEMPLATE_RE = r"plan:{action}:(?P<plan_id>[0-9a-f-]{{36}})(?::(?P<author>\d{{17,20}}))?"
LEGACY_REPLY = "This alert predates v152 — use the plan page or `!plans`."
NOT_YOUR_PANEL = "Not your panel."
PLAN_GONE = "This plan no longer exists."
STARRED_REPLY = "⭐ Starred — it'll sort first on `!plans` at equal follow score."


def _template(action: str) -> str:
    return PLAN_TEMPLATE_RE.format(action=action)


def custom_id_for(action: str, plan_id: str, author_id: int | None) -> str:
    """The persistent custom_id of one plan button: always the plan id, and
    the author id only for an author-locked (`!top`) panel."""
    base = f"plan:{action}:{plan_id}"
    return base if author_id is None else f"{base}:{author_id}"


def _persistable(plan_id: str, author_id: int | None) -> bool:
    return re.fullmatch(_template("chart"), custom_id_for("chart", plan_id, author_id)) is not None


def _get_plan(plan_id: str):
    """Sync plan read; every button calls it through asyncio.to_thread."""
    return PlanStore().get(plan_id)


class _PlanButtonMixin:
    """The body every persistent plan button shares. A concrete button sets
    ACTION/LABEL/STYLE and passes `template=_template(ACTION)` to
    DynamicItem; this mixin must come first in the bases so its
    interaction_check overrides DynamicItem's pass-through."""

    ACTION = ""
    LABEL = ""
    STYLE = discord.ButtonStyle.secondary

    def __init__(self, plan_id: str, author_id: int | None = None):
        super().__init__(discord.ui.Button(
            label=self.LABEL, style=self.STYLE,
            custom_id=custom_id_for(self.ACTION, plan_id, author_id)))
        self.plan_id = plan_id
        self.author_id = author_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        author = match["author"]
        return cls(match["plan_id"], int(author) if author else None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id is None or interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(NOT_YOUR_PANEL, ephemeral=True)
        return False


async def _send_chart(interaction: discord.Interaction, plan_id: str) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)
    plan = await asyncio.to_thread(_get_plan, plan_id)
    if plan is None:
        await interaction.followup.send("This plan no longer exists (closed/cancelled and pruned).", ephemeral=True)
        return
    try:
        df = await asyncio.to_thread(get_daily_data, plan.ticker)
    except Exception as exc:
        log.warning("plan panel %s: could not fetch price data for %s", plan_id, plan.ticker, exc_info=True)
        await interaction.followup.send(f"Could not fetch price data for {plan.ticker}: {exc}", ephemeral=True)
        return
    h = HORIZONS.get(plan.horizon_key, {})
    filename = f"{plan.ticker}_{plan.plan_id}_panel.png"
    try:
        chart_path = await asyncio.to_thread(
            generate_trade_chart,
            plan.ticker, df, plan.trigger_price, plan.stop_loss, plan.tp1,
            plan.direction, plan.strategy, h.get("label", plan.horizon_key), config.TRADE_CHART_DIR,
            filename=filename, currency_symbol=get_currency_symbol(plan.ticker, config.CURRENCY_SYMBOL),
            target2=plan.tp2, trendline_lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
            horizon=h, plan_v2=plan,
        )
    except Exception as exc:
        log.warning("plan panel %s: chart render failed", plan_id, exc_info=True)
        await interaction.followup.send(f"Chart render failed: {exc}", ephemeral=True)
        return
    await interaction.followup.send(
        file=discord.File(chart_path, filename=os.path.basename(chart_path)), ephemeral=True,
    )


def _toggle_star(plan_id: str) -> bool:
    """Global star toggle (pre-v152 Watch). True = now starred."""
    if plan_id in starred_ids():
        unstar_plan(plan_id)
        return False
    star_plan(plan_id)
    return True


class ChartButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                  template=_template("chart")):
    ACTION = "chart"
    LABEL = "📊 Chart"
    STYLE = discord.ButtonStyle.primary

    async def callback(self, interaction: discord.Interaction) -> None:
        await _send_chart(interaction, self.plan_id)


class BreakdownButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                      template=_template("breakdown")):
    ACTION = "breakdown"
    LABEL = "🔍 Breakdown"

    async def callback(self, interaction: discord.Interaction) -> None:
        plan = await asyncio.to_thread(_get_plan, self.plan_id)
        if plan is None:
            await interaction.response.send_message(PLAN_GONE, ephemeral=True)
            return
        await interaction.response.send_message(embed=breakdown_embed(plan), ephemeral=True)


class WatchButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                  template=_template("watch")):
    ACTION = "watch"
    LABEL = "⭐ Watch"

    async def callback(self, interaction: discord.Interaction) -> None:
        starred = await asyncio.to_thread(_toggle_star, self.plan_id)
        await interaction.response.send_message(STARRED_REPLY if starred else "Unstarred.", ephemeral=True)


class DismissButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                    template=_template("dismiss")):
    ACTION = "dismiss"
    LABEL = "🔕 Dismiss"

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)


PLAN_BUTTONS: tuple[type, ...] = (ChartButton, BreakdownButton, WatchButton, DismissButton)


class PlanActionView(discord.ui.View):
    """One persistent action panel per posted plan. `author_id=None` lets
    any user press (scan and digest alerts: nobody ran a command);
    `!top` passes the caller's id, which rides in every custom_id so the
    lock survives a restart."""

    def __init__(self, plan_id: str, author_id: int | None):
        super().__init__(timeout=None)
        self.plan_id = plan_id
        self.author_id = author_id
        self.message: discord.Message | None = None
        if not _persistable(plan_id, author_id):
            log.warning("plan panel: plan %r / author %r cannot form a persistent custom_id"
                        " -- posting without buttons", plan_id, author_id)
            return
        for button_cls in PLAN_BUTTONS:
            self.add_item(button_cls(plan_id, author_id))


def chart_only_view(plan_id: str) -> discord.ui.View:
    """A persistent view with just the Chart button (the notify channel's
    messages, V152-17)."""
    view = discord.ui.View(timeout=None)
    if _persistable(plan_id, None):
        view.add_item(ChartButton(plan_id))
    return view


async def _legacy_reply(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(LEGACY_REPLY, ephemeral=True)


class LegacyPlanPanel(discord.ui.View):
    """Claims the four static ids every pre-v152 alert carries, so pressing
    one never shows "This interaction failed". Those ids hold no plan id:
    Chart/Breakdown/Watch can only point at the plan page; Dismiss needs no
    plan and still removes the panel."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📊 Chart", style=discord.ButtonStyle.primary, custom_id="plan:chart")
    async def chart_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _legacy_reply(interaction)

    @discord.ui.button(label="🔍 Breakdown", style=discord.ButtonStyle.secondary, custom_id="plan:breakdown")
    async def breakdown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _legacy_reply(interaction)

    @discord.ui.button(label="⭐ Watch", style=discord.ButtonStyle.secondary, custom_id="plan:watch")
    async def watch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _legacy_reply(interaction)

    @discord.ui.button(label="🔕 Dismiss", style=discord.ButtonStyle.secondary, custom_id="plan:dismiss")
    async def dismiss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)


def register_persistent_views(bot) -> None:
    """Called once from bot_core.setup_hook, before the gateway connects.
    Reads PLAN_BUTTONS at call time, so a button appended later registers too."""
    bot.add_dynamic_items(*PLAN_BUTTONS)
    bot.add_view(LegacyPlanPanel())
```

Keep `generate_trade_chart,` on its own line inside the `to_thread(...)` call exactly as shown: `tests/commands/test_stats_commands.py::test_no_direct_chart_render_calls_outside_to_thread` flags any line holding `generate_trade_chart(` without `to_thread`.

- [ ] **Step 4: Add `setup_hook` to `swingbot/bot_core.py`**

Directly above the existing `@bot.event` / `async def on_command(ctx):` (`:322`), insert:

```python
@bot.event
async def setup_hook() -> None:
    """discord.py awaits this once, after login and before the gateway
    connects: the one place persistent views must be registered so a button
    on an alert posted before a restart still dispatches (v152 D2). Lazy
    import: views.py imports the plan store, which bot_core must not load
    at import time."""
    from swingbot.commands import views
    views.register_persistent_views(bot)
```

(`bot.event` sets `bot.setup_hook` to this coroutine; `Client.login` awaits `self.setup_hook()`. Importing the module and calling `views.register_persistent_views` keeps the monkeypatch in the test effective.)

- [ ] **Step 5: Move the existing panel tests from the view to its items**

In `tests/commands/test_views.py`:

(a) Under the imports, add:

```python
PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
PID_404 = "11111111-1111-4111-8111-111111111111"
PID_X = "22222222-2222-4222-8222-222222222222"
AUTHOR = 123456789012345678
OTHER = 876543210987654321


def _button(view, action: str):
    """The panel's button for one action (`chart`, `breakdown`, ...)."""
    return next(item for item in view.children if item.custom_id.split(":")[1] == action)
```

and add `PLAN_BUTTONS` to the `from swingbot.commands.views import (...)` list.

(b) Replace `test_plan_action_view_has_one_chart_button`, `test_interaction_check_rejects_wrong_user`, `test_interaction_check_accepts_matching_user`, `test_on_timeout_disables_children_and_edits_message` and `test_on_timeout_without_message_does_not_raise` with:

```python
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
```

(c) In the four `test_chart_button_*` tests: `PlanActionView("plan-404", author_id=42)` → `PlanActionView(PID_404, author_id=AUTHOR)`, `mock_get.assert_called_once_with("plan-404")` → `mock_get.assert_called_once_with(PID_404)`, `PlanActionView("plan-123", author_id=42)` → `PlanActionView(PID, author_id=AUTHOR)`, `_fake_interaction(user_id=42)` → `_fake_interaction(user_id=AUTHOR)`. Keep `view.children[0].callback(interaction)` (Chart is first).

(d) Replace `test_breakdown_button_sends_ephemeral`, `test_watch_button_toggles_star`, `test_dismiss_button_removes_view_keeps_embed`, `test_any_author_id_none_interaction_check_true_for_any_user` and `test_breakdown_button_reads_plan_created_after_views_import` with:

```python
def test_breakdown_button_sends_ephemeral():
    view = PlanActionView(PID, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)
    with patch.object(views_module.PlanStore, "get", return_value=_fixture_plan()):
        asyncio.run(_button(view, "breakdown").callback(interaction))
    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True
    assert "embed" in kwargs


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


def test_breakdown_button_reads_plan_created_after_views_import(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    plan = _pending(plan_id=PID, ticker="MSFT")
    PlanStore().add(plan)
    view = PlanActionView(plan.plan_id, author_id=AUTHOR)
    interaction = _fake_interaction(user_id=AUTHOR)

    asyncio.run(_button(view, "breakdown").callback(interaction))

    interaction.response.send_message.assert_awaited_once()
```

Leave the module docstring, `test_star_unstar_roundtrip` (`"p1"`/`"p2"` never become buttons), the breakdown-embed tests and every `PlanBoardView`/`paginate` test as they are.

- [ ] **Step 6: Run both files and the suites that build panels**

Run: `python scripts/dev/testrun.py file tests/commands/test_views_persistent.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/commands/test_views.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/commands/test_send_alerts_v110.py`, then the same for `tests/infra/test_posted_log.py` and `tests/commands/test_stats_commands.py`
Expected: PASS (the first two monkeypatch `PlanActionView`; the third holds the `to_thread` render tripwire).
Run: `python scripts/dev/testrun.py changed --dry-run`; run any further listed file that builds `PlanActionView` with a short id.

- [ ] **Step 7: Complexity and colour guard**

Run: `pip install radon` (once), then `python -m radon cc -s -n C swingbot/commands/views.py swingbot/bot_core.py`
Expected: no new or changed function listed (every one < 15). `tests/commands/test_views.py::test_views_has_no_direct_colour_and_breakdown_matches_plan_confidence` already passed in Step 6.

- [ ] **Step 8: Commit**

```bash
git add swingbot/commands/views.py swingbot/bot_core.py tests/commands/test_views.py tests/commands/test_views_persistent.py
git commit -m "feat(v152): persistent plan panel via DynamicItem, legacy fallback, setup_hook (V152-6)"
```

# Phase 2: Following on the trade, per-user Watch

### Task V152-7: `TradeLog.mark_taken` + `taken_by` re-stamp at close

**Model:** opus — touches the trade ledger's close path inside the manager's transaction, where a failed read must neither abort the transaction nor block a close.

**Swallowed-error ratchet (audit 2026-10-10):** this task adds `except Exception` handlers. If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), apply the index Global Constraints bullet "Swallowed-error ratchet (v148)" to every one that does not re-raise (`except Exception as exc:` + `swallowed(log, "ops.<module>.<function>", exc, level=logging.DEBUG)` first, keep the existing log line, unique tag) and run `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` before the commit. Otherwise write them as planned.

**Files:**
- Modify: `swingbot/core/tracking/performance.py` (module helpers after `_LOCK = Lock()` `:39`; `TradeLog.mark_taken` after `mark_near_close` `:1259`; one statement in `close_plan_trade` `:737`)
- Create: `tests/tracking/test_taken_by.py`

**Consumes:** `followers_repo().user_ids(plan_id, kinds) -> list[int]` and `.add(...)` (V152-3, `swingbot/core/db/repositories/followers.py`); `plan_followers` with its FK into `plans` (V152-2).
**Produces (ledger):** `TradeLog.mark_taken(self, plan_id: str, user_ids: list[int]) -> bool`; `performance._taken_by(plan_id: str) -> list[int] | None`; trade doc key `taken_by: list[int]` (a doc-field add, no revision, no upcast).

**Design.** The followers table is the truth; the trade copy is denormalised and written twice, both idempotent:

1. At press (V152-8 calls it): `mark_taken` finds the plan's **open** trade (the PENDING placeholder or the filled trade) and patches `taken_by` (sorted, unique) with `trades_repo().patch` — JSONB `||`, no read-modify-write of the rest of the row — under the module `_LOCK`, like every other `TradeLog` mutator. It writes the full set, not an append, so a repeated press converges.
2. At close: `close_plan_trade` calls `_restamp_taken_by(t, plan_id)` just before `closed_trade = dict(t)` / the upsert, so the closed row and `_after_close` both see the table's current set. The read runs on its **own** connection, never the caller's `conn`: a failed statement inside the manager's transaction would abort it in Postgres and lose the close. A failed read returns `None`, keeps whatever the trade already carries and logs a WARNING. A trade whose plan never had a Following follower gets no `taken_by` key at all (the extractor in V152-9 reads a missing key as `paper`).

`close_plan_trade` gains one statement and no branch (7 stays 7; the index allows 8). `_LOCK` is a `threading.Lock` — `mark_taken` is only ever called from `asyncio.to_thread`.

- [ ] **Step 1: Write the failing tests**

Create `tests/tracking/test_taken_by.py`:

```python
"""v152 D2: the trade carries a denormalised copy of who followed its plan.

plan_followers (kind "taken") is the truth. TradeLog.mark_taken copies the
set onto the plan's open trade at press time; close_plan_trade re-stamps it
from the table just before the close is written, and never lets a failed
read block the close.
"""
import logging

import pytest

from swingbot import config
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
WIN_LEG = {"fraction": 1.0, "exit_price": 110.0, "r": 2.0, "reason": "win"}


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    PlanStore().add(_plan(plan_id=PID))
    return TradeLog()


def _open_trade(tlog) -> str:
    return tlog.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", confidence_level=4, confidence_label="High",
        entry=100.0, stop_loss=95.0, take_profit=110.0, plan_id=PID)


def _follow(user_id: int, kind: str = "taken") -> None:
    from swingbot.core.db.repositories.followers import followers_repo
    followers_repo().add(PID, user_id, kind, status_at_press="ACTIVE")


def test_mark_taken_writes_a_sorted_unique_set_on_the_open_trade(tlog):
    trade_id = _open_trade(tlog)
    first, second = 333333333333333333, 111111111111111111
    assert tlog.mark_taken(PID, [first, second, first]) is True
    assert tlog.get_trade_by_id(trade_id)["taken_by"] == [second, first]


def test_mark_taken_replaces_the_set_rather_than_appending(tlog):
    trade_id = _open_trade(tlog)
    tlog.mark_taken(PID, [5, 7])
    tlog.mark_taken(PID, [7])
    assert tlog.get_trade_by_id(trade_id)["taken_by"] == [7]


def test_mark_taken_leaves_every_other_field_alone(tlog):
    trade_id = _open_trade(tlog)
    before = tlog.get_trade_by_id(trade_id)
    tlog.mark_taken(PID, [5])
    after = tlog.get_trade_by_id(trade_id)
    assert {k: v for k, v in after.items() if k not in ("taken_by", "updated_at")} == \
        {k: v for k, v in before.items() if k != "updated_at"}


def test_mark_taken_is_false_without_an_open_trade(tlog):
    assert tlog.mark_taken(PID, [5]) is False
    trade_id = _open_trade(tlog)
    tlog.close_plan_trade(PID, WIN_LEG, "win")
    assert tlog.mark_taken(PID, [5]) is False
    assert "taken_by" not in tlog.get_trade_by_id(trade_id)


def test_close_restamps_taken_by_from_the_followers_table(tlog):
    trade_id = _open_trade(tlog)
    _follow(222222222222222222)
    _follow(111111111111111111)
    tlog.close_plan_trade(PID, WIN_LEG, "win")
    trade = tlog.get_trade_by_id(trade_id)
    assert trade["status"] == "win"
    assert trade["taken_by"] == [111111111111111111, 222222222222222222]


def test_close_clears_a_copy_whose_followers_all_left(tlog):
    trade_id = _open_trade(tlog)
    tlog.mark_taken(PID, [5])                 # copied at press; the row was later removed
    tlog.close_plan_trade(PID, WIN_LEG, "win")
    assert tlog.get_trade_by_id(trade_id)["taken_by"] == []


def test_close_without_followers_writes_no_taken_by_key(tlog):
    trade_id = _open_trade(tlog)
    tlog.close_plan_trade(PID, WIN_LEG, "win")
    assert "taken_by" not in tlog.get_trade_by_id(trade_id)


def test_watch_rows_never_count_as_followed(tlog):
    trade_id = _open_trade(tlog)
    _follow(5, kind="watch")
    tlog.close_plan_trade(PID, WIN_LEG, "win")
    assert "taken_by" not in tlog.get_trade_by_id(trade_id)


def test_a_failed_follower_read_keeps_the_copy_and_never_blocks_the_close(tlog, monkeypatch, caplog):
    trade_id = _open_trade(tlog)
    tlog.mark_taken(PID, [7])

    def boom():
        raise RuntimeError("followers table unreachable")

    monkeypatch.setattr("swingbot.core.db.repositories.followers.followers_repo", boom)
    with caplog.at_level(logging.WARNING, logger="swingbot.core.tracking.performance"):
        tlog.close_plan_trade(PID, WIN_LEG, "win")
    trade = tlog.get_trade_by_id(trade_id)
    assert trade["status"] == "win"
    assert trade["taken_by"] == [7]
    assert "could not read followers" in caplog.text


def test_taken_by_helper_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr("swingbot.core.db.repositories.followers.followers_repo",
                        lambda: (_ for _ in ()).throw(RuntimeError("down")))
    assert performance._taken_by(PID) is None
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/tracking/test_taken_by.py`
Expected: FAIL (`AttributeError: 'TradeLog' object has no attribute 'mark_taken'`).

- [ ] **Step 3: Add the helpers**

In `swingbot/core/tracking/performance.py`, directly below `_LOCK = Lock()`, add:

```python
def _taken_by(plan_id: str) -> list[int] | None:
    """The plan's Following followers (plan_followers kind "taken"), sorted --
    the truth the trade's `taken_by` copy is taken from. None when the read
    fails. Runs on its own connection: a failed statement inside the
    manager's close transaction would abort it and lose the close."""
    try:
        from swingbot.core.db.repositories.followers import followers_repo
        return followers_repo().user_ids(plan_id, ("taken",))
    except Exception:
        log.warning("taken_by: could not read followers of plan %s -- keeping the trade's copy",
                    plan_id, exc_info=True)
        return None


def _restamp_taken_by(trade: dict, plan_id: str) -> None:
    """Copy the followers table onto a trade about to close. Writes nothing
    when the read failed, or when the plan never had a follower and the
    trade carries no copy (a missing key reads as "paper")."""
    taken = _taken_by(plan_id)
    if taken is None:
        return
    if taken or "taken_by" in trade:
        trade["taken_by"] = taken
```

- [ ] **Step 4: Add `mark_taken` and the close re-stamp**

Directly after `TradeLog.mark_near_close` add:

```python
    def mark_taken(self, plan_id: str, user_ids: list[int]) -> bool:
        """v152 D2: copy the plan's Following followers onto its open trade
        as `taken_by` (sorted, unique -- the whole set, so a repeated press
        converges). A JSONB patch of that one key, never a read-modify-write
        of the row. False when the plan has no open trade."""
        from swingbot.core.db.repositories.trades import trades_repo
        taken = sorted({int(user_id) for user_id in user_ids})
        with _LOCK:
            repo = trades_repo()
            row = next((r for r in repo.open_trades() if r.get("plan_id") == plan_id), None)
            if row is None:
                return False
            repo.patch(row["trade_id"], {"taken_by": taken})
        return True
```

In `close_plan_trade`, insert one line between `self._settle_account_balance(t)` and `closed_trade = dict(t)`:

```python
            self._settle_account_balance(t)
            _restamp_taken_by(t, plan_id)
            closed_trade = dict(t)
            self._db_upsert(t, conn=conn)
```

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/tracking/test_taken_by.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py`, then `tests/tracking/test_discard_plan_placeholder.py`, then `tests/planning/test_plan_manager_pending.py`
Expected: PASS (closes without followers write no new key).

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/tracking/performance.py`
Expected: `close_plan_trade`, `mark_taken`, `_taken_by`, `_restamp_taken_by` absent from the output (all < 15); no legacy entry's score rose.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/tracking/performance.py tests/tracking/test_taken_by.py
git commit -m "feat(v152): taken_by copy on the trade, written at press and re-stamped at close (V152-7)"
```

### Task V152-8: Per-user Watch + `✅ Following` button + reply

**Model:** sonnet — button callbacks and a pure reply renderer over contracts V152-3/V152-6/V152-7 already fixed; the hindsight rule is a status-set membership test.

**Swallowed-error ratchet (audit 2026-10-10):** this task adds `except Exception` handlers. If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), apply the index Global Constraints bullet "Swallowed-error ratchet (v148)" to every one that does not re-raise (`except Exception as exc:` + `swallowed(log, "ops.<module>.<function>", exc, level=logging.DEBUG)` first, keep the existing log line, unique tag) and run `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` before the commit. Otherwise write them as planned.

**Files:**
- Modify: `swingbot/commands/views.py` (imports; constants and helpers after `STARRED_REPLY`; `WatchButton.callback`; new `FollowingButton`; `PLAN_BUTTONS`)
- Create: `tests/commands/test_views_following.py`

**Consumes:** `_PlanButtonMixin`, `_template`, `_get_plan`, `PLAN_BUTTONS`, `PLAN_GONE` (V152-6); `followers_repo()` with `add`/`remove`/`has`/`user_ids` (V152-3); `TradeLog.mark_taken` (V152-7).
**Produces (ledger):** `FollowingButton` (action `follow`, label `✅ Following`) in `PLAN_BUTTONS` between Watch and Dismiss (five buttons, Discord's one-row maximum); `FOLLOWABLE_STATUSES`; `following_reply(plan, price: float | None, now: dt.datetime | None = None) -> str` (pure); Watch toggles the presser's `watch` row, stars on the first watcher and unstars on the last.

**Rules (spec § D2):**
- **Watch** is per user. The first watcher stars the plan (`star_plan`), removing the last watcher unstars it, so `!plans` sorting keeps working. A legacy star with no watcher rows stays starred until someone watches and unwatches.
- **Following** (kind `taken`) records intent to follow, not a fill. Accepted only while the plan is PENDING, ACTIVE or PARTIAL; on CLOSED or CANCELLED it refuses ephemerally and writes nothing (a press after the outcome is known would let hindsight pick the winners). `status_at_press` is stored on the row.
- **The reply informs, never blocks.** It states status and entry validity — PENDING: sessions left of `expiry_bars`, plus `Plan stale.` when one or none is left; ACTIVE/PARTIAL: the latest cached close against `entry_price`, plus `Price already beyond entry by xR.` when it is — and ends `Recorded as followed — paper plan, not your fill.` The close comes from `get_daily_data` in `asyncio.to_thread`; a fetch failure drops only that line. Wording says "followed", never "executed" or "taken".
- After every toggle the trade copy is rewritten from the table (`mark_taken(plan_id, user_ids(plan_id, ("taken",)))`). A failure there is logged, not surfaced: the follower row is already correct and the close re-stamps the trade (V152-7), whereas reporting an error would invite a second press that toggles the row off again.
- Every DB call runs in `asyncio.to_thread`; the Following callback defers first because the toggle plus the price read can exceed Discord's 3-second window.

Sessions left: `expiry_bars` minus the NYSE sessions after the plan's creation date up to and including today's market date (`nyse_calendar().sessions(created + 1 day, market_today(now))`, floored at 0). It is informational; the manager's own expiry (`pending_expired`, bar count from the daily index) stays the authority.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_views_following.py`:

```python
"""v152 D2: per-user Watch and the Following button.

Following records that a user says they followed a paper plan -- intent,
never a fill -- and is refused once the outcome is known. Watch is a per-user
row; the global star follows the first/last watcher. No pytest-asyncio:
coroutines run through asyncio.run.
"""
import asyncio
import datetime as dt
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.commands import views
from swingbot.commands.views import (
    FOLLOWABLE_STATUSES,
    PLAN_BUTTONS,
    FollowingButton,
    PlanActionView,
    following_reply,
    starred_ids,
)
from swingbot.core.db import schema
from swingbot.core.db.engine import get_engine
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
AUTHOR = 123456789012345678
OTHER = 876543210987654321
WED = dt.datetime(2026, 10, 7, 16, 0, tzinfo=dt.timezone.utc)   # 12:00 ET, Wednesday


def _interaction(user_id: int) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _button(view, action):
    return next(item for item in view.children if item.custom_id.split(":")[1] == action)


def _reply_text(interaction) -> str:
    interaction.followup.send.assert_awaited_once()
    args, kwargs = interaction.followup.send.call_args
    assert kwargs.get("ephemeral") is True
    return args[0]


@pytest.fixture
def plan_env(tmp_path, monkeypatch):
    """A stored plan with an open trade; the price read is stubbed."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    monkeypatch.setattr(views, "_last_close", lambda ticker: 102.5)

    def make(status=PlanStatus.PENDING, **kw):
        PlanStore().add(_plan(plan_id=PID, status=status, **kw))
        trade_id = TradeLog().log_trade(
            ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
            direction="bullish", confidence_level=4, confidence_label="High",
            entry=100.0, stop_loss=95.0, take_profit=110.0, plan_id=PID)
        return trade_id
    return make


def _press(action: str, user_id: int) -> MagicMock:
    interaction = _interaction(user_id)
    asyncio.run(_button(PlanActionView(PID, author_id=None), action).callback(interaction))
    return interaction


def _follower_rows():
    table = schema.plan_followers
    with get_engine().connect() as conn:
        return conn.execute(sa.select(table.c.user_id, table.c.kind, table.c.doc)
                            .where(table.c.plan_id == PID)).all()


# -- panel shape -------------------------------------------------------------

def test_following_sits_between_watch_and_dismiss():
    assert [cls.ACTION for cls in PLAN_BUTTONS] == ["chart", "breakdown", "watch", "follow", "dismiss"]
    item = _button(PlanActionView(PID, author_id=None), "follow")
    assert isinstance(item, FollowingButton)
    assert item.item.label == "✅ Following"


def test_followable_statuses_are_the_open_ones():
    assert FOLLOWABLE_STATUSES == {PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL}


# -- the pure reply ------------------------------------------------------------

def test_pending_reply_counts_sessions_left():
    plan = _plan(plan_id=PID, created_at="2026-10-05", expiry_bars=5)     # Monday
    text = following_reply(plan, None, now=WED)                          # Tue + Wed elapsed
    assert "PENDING" in text
    assert "3 of 5 session(s) left" in text
    assert "stale" not in text
    assert text.endswith("Recorded as followed — paper plan, not your fill.")


def test_pending_reply_flags_a_stale_plan_at_one_or_no_session_left():
    for expiry, left in ((3, 1), (2, 0), (1, 0)):
        text = following_reply(_plan(plan_id=PID, created_at="2026-10-05", expiry_bars=expiry), None, now=WED)
        assert f"{left} of {expiry} session(s) left" in text
        assert "Plan stale." in text


def test_active_reply_states_price_against_entry_and_beyond_entry_in_r():
    plan = _plan(plan_id=PID, status=PlanStatus.ACTIVE, entry_price=100.0, stop_loss=95.0)
    text = following_reply(plan, 102.5)
    assert "Last 102.50 vs entry 100.00." in text
    assert "Price already beyond entry by 0.50R." in text


def test_bearish_beyond_entry_is_measured_downward():
    plan = _plan(plan_id=PID, status=PlanStatus.PARTIAL, direction="bearish",
                 entry_price=100.0, stop_loss=105.0, tp1=95.0, tp2=90.0)
    text = following_reply(plan, 97.5)
    assert "short" in text
    assert "Price already beyond entry by 0.50R." in text


def test_price_on_the_wrong_side_of_entry_is_not_called_beyond():
    plan = _plan(plan_id=PID, status=PlanStatus.ACTIVE, entry_price=100.0, stop_loss=95.0)
    text = following_reply(plan, 99.0)
    assert "Last 99.00 vs entry 100.00." in text
    assert "beyond" not in text


def test_a_failed_price_read_drops_only_the_price_line():
    plan = _plan(plan_id=PID, status=PlanStatus.ACTIVE, entry_price=100.0, stop_loss=95.0)
    text = following_reply(plan, None)
    assert "Last" not in text
    assert "ACTIVE" in text and "Recorded as followed" in text


def test_reply_wording_never_claims_an_execution():
    for status, price in ((PlanStatus.PENDING, None), (PlanStatus.ACTIVE, 103.0)):
        plan = _plan(plan_id=PID, status=status, entry_price=100.0, created_at="2026-10-05")
        text = following_reply(plan, price, now=WED).lower()
        assert "executed" not in text and "taken" not in text


# -- Following button ----------------------------------------------------------

def test_following_records_the_row_with_status_at_press_and_copies_it_to_the_trade(plan_env):
    trade_id = plan_env(status=PlanStatus.PENDING)
    text = _reply_text(_press("follow", AUTHOR))
    assert "Recorded as followed" in text
    rows = _follower_rows()
    assert [(r.user_id, r.kind) for r in rows] == [(AUTHOR, "taken")]
    assert rows[0].doc["status_at_press"] == PlanStatus.PENDING
    assert TradeLog().get_trade_by_id(trade_id)["taken_by"] == [AUTHOR]


def test_a_second_press_unfollows_and_rewrites_the_trade_copy(plan_env):
    trade_id = plan_env(status=PlanStatus.ACTIVE, entry_price=100.0)
    _press("follow", AUTHOR)
    _press("follow", OTHER)
    text = _reply_text(_press("follow", AUTHOR))
    assert text == "No longer recorded as followed."
    assert [(r.user_id, r.kind) for r in _follower_rows()] == [(OTHER, "taken")]
    assert TradeLog().get_trade_by_id(trade_id)["taken_by"] == [OTHER]


@pytest.mark.parametrize("status", [PlanStatus.CLOSED, PlanStatus.CANCELLED])
def test_following_is_refused_once_the_outcome_is_known(plan_env, status):
    trade_id = plan_env(status=status)
    text = _reply_text(_press("follow", AUTHOR))
    assert status in text and "not counted" in text
    assert _follower_rows() == []
    assert "taken_by" not in TradeLog().get_trade_by_id(trade_id)


def test_following_a_pruned_plan_says_so(plan_env):
    text = _reply_text(_press("follow", AUTHOR))
    assert text == "This plan no longer exists."


def test_a_failed_trade_copy_still_records_the_follow(plan_env, monkeypatch):
    plan_env(status=PlanStatus.PENDING)

    def boom(self, plan_id, user_ids):
        raise RuntimeError("trades table down")

    monkeypatch.setattr(TradeLog, "mark_taken", boom)
    text = _reply_text(_press("follow", AUTHOR))
    assert "Recorded as followed" in text
    assert [(r.user_id, r.kind) for r in _follower_rows()] == [(AUTHOR, "taken")]


# -- per-user Watch -------------------------------------------------------------

def test_watch_is_per_user_and_the_star_follows_first_and_last_watcher(plan_env):
    plan_env()
    _press("watch", AUTHOR)
    assert PID in starred_ids()
    _press("watch", OTHER)
    _press("watch", AUTHOR)                  # AUTHOR leaves; OTHER still watches
    assert PID in starred_ids()
    assert [(r.user_id, r.kind) for r in _follower_rows()] == [(OTHER, "watch")]
    _press("watch", OTHER)                   # the last watcher leaves
    assert PID not in starred_ids()


def test_watch_replies_ephemerally_on_and_off(plan_env):
    plan_env()
    on = _interaction(AUTHOR)
    asyncio.run(_button(PlanActionView(PID, author_id=None), "watch").callback(on))
    args, kwargs = on.response.send_message.call_args
    assert args[0].startswith("⭐ Watching") and kwargs["ephemeral"] is True
    off = _interaction(AUTHOR)
    asyncio.run(_button(PlanActionView(PID, author_id=None), "watch").callback(off))
    assert off.response.send_message.call_args[0][0] == "No longer watching."


def test_watch_and_following_are_independent_rows(plan_env):
    plan_env()
    _press("watch", AUTHOR)
    _press("follow", AUTHOR)
    assert sorted((r.user_id, r.kind) for r in _follower_rows()) == [(AUTHOR, "taken"), (AUTHOR, "watch")]


def test_button_db_calls_run_off_the_event_loop():
    for cls, helper in ((views.WatchButton, "_toggle_watch"), (views.FollowingButton, "_toggle_following")):
        source = inspect.getsource(cls)
        assert f"to_thread({helper}" in source
        assert "followers_repo()" not in source
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_views_following.py`
Expected: FAIL at import (`ImportError: cannot import name 'FOLLOWABLE_STATUSES'`).

- [ ] **Step 3: Imports and constants**

In `swingbot/commands/views.py`: add `import datetime as dt` to the stdlib imports; change `from swingbot.core.market.session import market_today` to `from swingbot.core.market.session import market_today, nyse_calendar`; add `from swingbot.core.planning.plan_types import PlanStatus` below the `PlanStore` import. After `STARRED_REPLY = ...` add:

```python
WATCH_ON = ("⭐ Watching — it sorts first on `!plans` at equal follow score; "
            "`/notify` sets which plan updates name you.")
WATCH_OFF = "No longer watching."
FOLLOWABLE_STATUSES = frozenset({PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL})
FOLLOW_RECORDED = "Recorded as followed — paper plan, not your fill."
FOLLOW_REMOVED = "No longer recorded as followed."
FOLLOW_REFUSED = ("This plan is already {status}: following is recorded only while a plan is "
                  "pending, active or partial, so a press after the outcome is known is not counted.")
FOLLOW_FAILED = "Could not record that just now; please try again."
_DIRECTION_WORD = {"bullish": "long", "bearish": "short"}
```

- [ ] **Step 4: The pure reply**

Below `_toggle_star`, add:

```python
def _sessions_left(plan, now: dt.datetime | None = None) -> int:
    """Sessions left of `expiry_bars`: NYSE sessions after the creation date
    up to today's market date count as spent. Informational only."""
    created = dt.date.fromisoformat(str(plan.created_at)[:10])
    spent = len(nyse_calendar().sessions(created + dt.timedelta(days=1), market_today(now)))
    return max(0, int(plan.expiry_bars) - spent)


def _pending_detail(plan, price, now) -> str:
    left = _sessions_left(plan, now)
    line = (f"Entry trigger {plan.trigger_price:.2f}; "
            f"{left} of {plan.expiry_bars} session(s) left before it expires.")
    return f"{line} Plan stale." if left <= 1 else line


def _open_detail(plan, price, now) -> str:
    if price is None:
        return ""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    line = f"Last {price:.2f} vs entry {entry:.2f}."
    risk = abs(entry - plan.stop_loss)
    sign = 1 if plan.direction == "bullish" else -1
    beyond = (price - entry) * sign / risk if risk else 0.0
    return f"{line} Price already beyond entry by {beyond:.2f}R." if beyond > 0 else line


_STATUS_DETAIL = {
    PlanStatus.PENDING: _pending_detail,
    PlanStatus.ACTIVE: _open_detail,
    PlanStatus.PARTIAL: _open_detail,
}


def following_reply(plan, price: float | None, now: dt.datetime | None = None) -> str:
    """The Following button's ephemeral reply: status and entry validity as
    facts. It informs and never blocks; `price=None` drops the price line."""
    word = _DIRECTION_WORD.get(plan.direction, plan.direction)
    head = f"{plan.ticker} {word} paper plan, status {plan.status}."
    detail = _STATUS_DETAIL.get(plan.status, lambda *_: "")(plan, price, now)
    return "\n".join(line for line in (head, detail, FOLLOW_RECORDED) if line)
```

- [ ] **Step 5: The sync DB helpers**

Below `following_reply`, add:

```python
def _followers():
    from swingbot.core.db.repositories.followers import followers_repo
    return followers_repo()


def _toggle_watch(plan, user_id: int) -> bool:
    """Toggle the presser's watch row. True = now watching. The first
    watcher stars the plan; the last one leaving unstars it."""
    repo = _followers()
    if repo.has(plan.plan_id, user_id, "watch"):
        repo.remove(plan.plan_id, user_id, "watch")
        if not repo.user_ids(plan.plan_id, ("watch",)):
            unstar_plan(plan.plan_id)
        return False
    first = not repo.user_ids(plan.plan_id, ("watch",))
    repo.add(plan.plan_id, user_id, "watch", status_at_press=plan.status)
    if first:
        star_plan(plan.plan_id)
    return True


def _copy_taken_to_trade(plan_id: str, repo) -> None:
    from swingbot.core.tracking.performance import TradeLog
    try:
        TradeLog().mark_taken(plan_id, repo.user_ids(plan_id, ("taken",)))
    except Exception:
        log.warning("Following: could not copy followers onto plan %s's trade"
                    " -- close_plan_trade re-stamps it", plan_id, exc_info=True)


def _toggle_following(plan, user_id: int) -> bool:
    """Toggle the presser's `taken` row, then rewrite the trade copy from the
    table. True = now following. Callers have checked FOLLOWABLE_STATUSES."""
    repo = _followers()
    following = not repo.has(plan.plan_id, user_id, "taken")
    if following:
        repo.add(plan.plan_id, user_id, "taken", status_at_press=plan.status)
    else:
        repo.remove(plan.plan_id, user_id, "taken")
    _copy_taken_to_trade(plan.plan_id, repo)
    return following


def _last_close(ticker: str) -> float | None:
    """Latest cached daily close, None on any failure (the reply drops the line)."""
    try:
        return float(get_daily_data(ticker)["Close"].iloc[-1])
    except Exception:
        log.debug("Following: no cached close for %s", ticker, exc_info=True)
        return None
```

- [ ] **Step 6: Per-user Watch and the Following button**

Replace the body of `WatchButton.callback` with:

```python
    async def callback(self, interaction: discord.Interaction) -> None:
        plan = await asyncio.to_thread(_get_plan, self.plan_id)
        if plan is None:
            await interaction.response.send_message(PLAN_GONE, ephemeral=True)
            return
        watching = await asyncio.to_thread(_toggle_watch, plan, interaction.user.id)
        await interaction.response.send_message(WATCH_ON if watching else WATCH_OFF, ephemeral=True)
```

`_toggle_star` and `STARRED_REPLY` are now unused: delete both (`git grep -n "_toggle_star\|STARRED_REPLY"` must print nothing afterwards).

Directly below `WatchButton`, add:

```python
class FollowingButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                      template=_template("follow")):
    """Records that the presser followed this paper plan -- intent, never a
    fill -- while the plan is still open."""

    ACTION = "follow"
    LABEL = "✅ Following"
    STYLE = discord.ButtonStyle.success

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        plan = await asyncio.to_thread(_get_plan, self.plan_id)
        reply = await self._reply_for(plan, interaction.user.id)
        await interaction.followup.send(reply, ephemeral=True)

    async def _reply_for(self, plan, user_id: int) -> str:
        if plan is None:
            return PLAN_GONE
        if plan.status not in FOLLOWABLE_STATUSES:
            return FOLLOW_REFUSED.format(status=plan.status)
        try:
            following = await asyncio.to_thread(_toggle_following, plan, user_id)
        except Exception:
            log.warning("Following: could not toggle plan %s for user %s", self.plan_id, user_id, exc_info=True)
            return FOLLOW_FAILED
        if not following:
            return FOLLOW_REMOVED
        price = await asyncio.to_thread(_last_close, plan.ticker)
        return following_reply(plan, price)
```

Change the tuple to:

```python
PLAN_BUTTONS: tuple[type, ...] = (ChartButton, BreakdownButton, WatchButton, FollowingButton, DismissButton)
```

- [ ] **Step 7: Run the tests**

Run: `python scripts/dev/testrun.py file tests/commands/test_views_following.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/commands/test_views.py`, then `tests/commands/test_views_persistent.py`
Expected: PASS — both assert against `PLAN_BUTTONS`, and `test_watch_button_toggles_star` (one user, two presses on a seeded plan) still stars then unstars.

- [ ] **Step 8: Complexity and colour guard**

Run: `python -m radon cc -s -n C swingbot/commands/views.py`
Expected: no new function listed (each < 15).
Run: `python -m pytest tests/commands/test_views.py::test_views_has_no_direct_colour_and_breakdown_matches_plan_confidence -q`
Expected: PASS (no `discord.Color` added).

- [ ] **Step 9: Commit**

```bash
git add swingbot/commands/views.py tests/commands/test_views_following.py
git commit -m "feat(v152): per-user Watch and the Following button with an informing reply (V152-8)"
```

# Phase 3: The `taken` dimension

### Task V152-9: `taken` analytics dimension

**Model:** haiku — one tuple entry and one extractor lambda, with the exact-set test updated.

**Files:**
- Modify: `swingbot/core/analytics/aggregate.py` (`DIMENSIONS` `:107`, `_EXTRACTORS` `:112`)
- Modify: `tests/analytics/test_aggregate.py` (`test_all_ten_dimensions_present` `:50` becomes `test_all_dimensions_present`; new tests after `test_dimension_extractors`)

**Produces (ledger):** `"taken"` in `DIMENSIONS`; `_EXTRACTORS["taken"] = lambda t: "followed" if t.get("taken_by") else "paper"`. A trade with no `taken_by` key, or an empty list (every follower left before the close, V152-7), is `paper`. `GET /api/v1/analytics/by-dimension` (`swingbot/admin/api_v1/analytics.py:~411`) already validates `dim` against `DIMENSIONS`, so `?dim=taken` is served with no API edit; the existing `MIN_CELL_N = 20` withholding applies to the small `followed` cell unchanged.

- [ ] **Step 1: Write the failing tests**

In `tests/analytics/test_aggregate.py`, replace `test_all_ten_dimensions_present` with the test below. **Cross-plan (audit 2026-10-10):** do not copy the set from this plan blind — take the CURRENT asserted set in the file and add `"taken"` after `"ledger"`, keeping every entry already there (v146 adds `"confluence"`, `"rs_quintile"` if merged). The docstring states the count: 11 without v146, 13 with it. The literal below is the no-v146 shape:

```python
def test_all_dimensions_present():
    """v32 Task 11: "tier" (A/B/C) retired -- "confidence" already covered
    the same role, so DIMENSIONS dropped from 10 to 9. v93 then added
    "ledger" (main/weak), back to 10; v152 adds "taken" (followed/paper): 11."""
    assert set(DIMENSIONS) == {"strategy", "horizon", "badge", "confidence",
                               "direction", "dow", "month", "ticker", "source", "ledger",
                               "taken"}
```

and add after `test_dimension_extractors`:

```python
def test_taken_splits_followed_from_paper():
    followed = {**_full_trade(), "taken_by": [123456789012345678]}
    paper = _full_trade()
    emptied = {**_full_trade(), "taken_by": []}
    rows = {r.key: r for r in stats_by([followed, paper, emptied], "taken")}
    assert set(rows) == {"followed", "paper"}
    assert rows["followed"].n == 1
    assert rows["paper"].n == 2


def test_taken_never_buckets_as_unknown():
    assert [r.key for r in stats_by([_full_trade()], "taken")] == ["paper"]
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_aggregate.py`
Expected: FAIL (`test_all_dimensions_present` set mismatch; `stats_by(..., "taken")` raises on an unknown dimension).

- [ ] **Step 3: Add the dimension**

In `swingbot/core/analytics/aggregate.py`, add `"taken"` after `"ledger"` in the CURRENT `DIMENSIONS` tuple, keeping every entry already there (v146's `"confluence"`, `"rs_quintile"` if present) — do not replace the tuple from this text. The no-v146 result:

```python
DIMENSIONS = ("strategy", "horizon", "badge", "confidence",
             "direction", "dow", "month", "ticker", "source", "ledger", "taken")
```

and in `_EXTRACTORS`, after the `"ledger"` entry:

```python
    # v152 D2: a trade whose plan had a Following follower at close carries
    # `taken_by` (performance.close_plan_trade). "Followed" records intent,
    # never a fill -- the SPA caption says so.
    "taken": lambda t: "followed" if t.get("taken_by") else "paper",
```

- [ ] **Step 4: Run the tests and the API suite that walks the dimensions**

Run: `python scripts/dev/testrun.py file tests/analytics/test_aggregate.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: PASS (unchanged; it proves the route still validates against `DIMENSIONS`).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/aggregate.py tests/analytics/test_aggregate.py
git commit -m "feat(v152): taken analytics dimension, followed vs paper (V152-9)"
```
