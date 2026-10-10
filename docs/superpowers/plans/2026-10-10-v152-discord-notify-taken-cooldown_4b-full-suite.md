# v152 part 4b: `/notify` and the full suites

**Spec:** [`docs/superpowers/specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md`](../specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md) § Testing ("One full suite, as the plan's final task"), § Complexity
**Index:** [`2026-10-10-v152-discord-notify-taken-cooldown_0-index.md`](2026-10-10-v152-discord-notify-taken-cooldown_0-index.md): Global Constraints, decisions, the task ledger and `## Parallelisation` live there. Part 4 overflowed the 1500-line cap, so its last two tasks (V152-19, moved here by the 2026-10-10 audit, and V152-20) live here; ledger ids, files and order are unchanged. V152-19 is not v151-gated. The contracts V152-19 consumes (V152-14's `NOTIFY_EVENTS`, `EVENT_LABELS`, `WATCH_DEFAULTS`; V152-3's `notify_prefs_repo().prefs / .set_pref`) are listed in [part 4's preamble](2026-10-10-v152-discord-notify-taken-cooldown_4-notifier-and-suite.md).

# Phase 2: `/notify`

### Task V152-19: `/notify` slash command

**Model:** sonnet — one slash command in an established style, reading fixed tables; the only I/O is one repository behind `to_thread`.

**Swallowed-error ratchet (audit 2026-10-10):** this task adds `except Exception` handlers. If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), apply the index Global Constraints bullet "Swallowed-error ratchet (v148)" to every one that does not re-raise (`except Exception as exc:` + `swallowed(log, "ops.<module>.<function>", exc, level=logging.DEBUG)` first, keep the existing log line, unique tag) and run `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` before the commit. Otherwise write them as planned.

**Files:**
- Modify: `swingbot/commands/slash.py` (imports at the top; choice lists beside the others at `:27-56`; the command after `/lessons`, the file's last command)
- Create: `tests/commands/test_slash_notify.py`

**Contract (ledger):** `/notify` with `event: Choice[str]` (the six `NOTIFY_EVENTS` plus `all`), `enabled: bool`, `watch_mode: Choice[str]` (`mention` | `silent`); `slash._notify_summary(prefs: dict) -> str` (pure). Not v151-gated: it reads only V152-14's tables (`NOTIFY_EVENTS`, `EVENT_LABELS`, `FOLLOWING_ONLY`, `mentions_user`) and V152-3's `notify_prefs_repo`. Parallel with V152-16..V152-18 (disjoint files).

**Behaviour (spec § `/notify` and per-user defaults):**
- No arguments → an ephemeral list of the six events this channel announces, the `closed_other` Following-only rule, and the caller's effective setting for each, for a Following plan and for a Watch-only plan. The setting is computed by V152-14's `mentions_user`, so `/notify` can never disagree with what the notifier does.
- `event:` + `enabled:` sets one event (or all six); `watch_mode:` sets the Watch-only mode. Both may come in one call. Every reply is ephemeral and ends with the summary after the change.
- `event:` without `enabled:` (or the reverse) changes nothing and says so — a half-specified toggle is never guessed.
- A store failure replies ephemerally that settings could not be read or saved and logs one WARNING; it never raises into discord.py.
- The repository call runs in `asyncio.to_thread` (Global Constraints).
- Importing `swingbot.commands.scanning.follow_notify` at the top of `slash.py` imports the `swingbot.commands.scanning` package; `bot.py` imports it anyway and nothing in that package imports `slash`, so there is no cycle. Run the registration test file alone (Step 4) to prove it.

- [ ] **Step 0: Precondition — v153 SP4 shape (audit 2026-10-10)**

Run `git grep -n SLASH_TWIN -- swingbot/commands`. If it prints nothing (v153 not merged), continue with Step 1 as written. If it is non-empty (v153 merged), build `/notify` in v153's SP4 shape instead: a new `swingbot/commands/notify.py` with `handle_notify(reply, …)` on `InteractionReply` and `SLASH_ONLY = {"notify"}`, imported from `bot.py`; `_notify_summary` lives there and the tests import it from `swingbot.commands.notify`; do **not** edit `slash.py`; the expected resync command count is 42. Read the exact frame first: `grep -n "^### Task SP4" -A 150 docs/superpowers/plans/2026-10-10-v153-slash-command-parity_1*.md` (SP4 sits in `_1b-notify-check` since the 2026-10-10 audit) (or the plan's `implemented/` copy).

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_slash_notify.py`:

```python
"""v152 D1: /notify -- which plan updates mention the caller.

The command is registered explicitly by importing swingbot.commands.slash
(see test_slash_commands.py for why under -n 4). Prefs are real rows on the
per-worker test Postgres. No pytest-asyncio: coroutines run through asyncio.run.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from discord import app_commands

import swingbot.commands.slash as slash
from swingbot.bot_core import bot
from swingbot.commands.scanning.follow_notify import EVENT_LABELS, NOTIFY_EVENTS
from swingbot.core.db.repositories.notify_prefs import notify_prefs_repo

USER = 123456789012345678


def _interaction(user_id: int = USER) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _choice(value: str) -> app_commands.Choice:
    return app_commands.Choice(name=value, value=value)


def _run(**kwargs) -> str:
    interaction = _interaction()
    asyncio.run(slash.slash_notify.callback(interaction, **kwargs))
    interaction.response.send_message.assert_awaited_once()
    args, sent = interaction.response.send_message.call_args
    assert sent.get("ephemeral") is True
    return args[0] if args else sent["content"]


def _line(text: str, event: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(f"• `{event}`"))


def test_notify_is_registered_with_its_three_options():
    command = bot.tree.get_command("notify")
    assert command is not None
    assert {p.name for p in command.parameters} == {"event", "enabled", "watch_mode"}
    assert [c.value for c in command.get_parameter("event").choices] == [*NOTIFY_EVENTS, "all"]
    assert [c.value for c in command.get_parameter("watch_mode").choices] == ["mention", "silent"]
    assert all(not p.required for p in command.parameters)


def test_the_summary_lists_every_announced_event_with_its_label():
    text = slash._notify_summary({})
    for event in NOTIFY_EVENTS:
        assert EVENT_LABELS[event] in _line(text, event)
    assert "not advice" in text
    assert "only when a plan has a Following follower" in text
    assert "Watch-only plans: mention." in text


def test_the_summary_shows_the_defaults():
    text = slash._notify_summary({})
    assert _line(text, "near_stop").endswith("Following: on · Watch: off")
    assert _line(text, "expired").endswith("Following: on · Watch: off")
    for event in ("tp1", "tp2", "stopped"):
        assert _line(text, event).endswith("Following: on · Watch: on")
    assert _line(text, "closed_other").endswith("Following: on · Watch: never")


def test_the_summary_shows_a_toggle_and_silent_mode():
    text = slash._notify_summary({"tp2": False, "near_stop": True, "watch_mode": "silent"})
    assert _line(text, "tp2").endswith("Following: off · Watch: off")
    assert _line(text, "near_stop").endswith("Following: on · Watch: off")   # silent drops Watch
    assert "Watch-only plans: silent." in text


def test_no_arguments_shows_the_summary_and_stores_nothing():
    text = _run()
    assert _line(text, "tp1")
    assert notify_prefs_repo().prefs(USER) == {}


def test_one_event_toggles_for_the_caller_only():
    text = _run(event=_choice("near_stop"), enabled=True)
    assert notify_prefs_repo().prefs(USER).get("near_stop") is True
    assert notify_prefs_repo().prefs(USER + 1) == {}
    assert _line(text, "near_stop").endswith("Following: on · Watch: on")


def test_all_sets_every_event():
    _run(event=_choice("all"), enabled=False)
    prefs = notify_prefs_repo().prefs(USER)
    assert all(prefs.get(event) is False for event in NOTIFY_EVENTS)


def test_watch_mode_is_stored_and_can_ride_with_a_toggle():
    text = _run(event=_choice("tp1"), enabled=False, watch_mode=_choice("silent"))
    prefs = notify_prefs_repo().prefs(USER)
    assert prefs.get("watch_mode") == "silent" and prefs.get("tp1") is False
    assert "Watch-only plans: silent." in text


def test_a_half_specified_toggle_changes_nothing():
    for kwargs in ({"event": _choice("tp1")}, {"enabled": True}):
        text = _run(**kwargs)
        assert "together" in text
    assert notify_prefs_repo().prefs(USER) == {}


def test_a_store_failure_replies_instead_of_raising(monkeypatch):
    def broken(*args):
        raise RuntimeError("db down")

    monkeypatch.setattr(slash, "_apply_notify_change", broken)
    assert "could not" in _run(event=_choice("tp1"), enabled=True).lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_slash_notify.py`
Expected: FAIL — `AttributeError: module 'swingbot.commands.slash' has no attribute 'slash_notify'` (and `_notify_summary`); the registration test sees `None`.

- [ ] **Step 3: Add `/notify` to `slash.py`**

Add to the imports at the top of `swingbot/commands/slash.py` (`import logging` beside `import asyncio`; the rest after the existing `swingbot` imports):

```python
import logging

from swingbot.commands.scanning.follow_notify import (
    EVENT_LABELS, FOLLOWING_ONLY, NOTIFY_EVENTS, mentions_user,
)

log = logging.getLogger(__name__)
```

Add beside the other choice lists (after `PERIOD_CHOICES`):

```python
WATCH_MODES = ("mention", "silent")
NOTIFY_EVENT_CHOICES = [app_commands.Choice(name=n, value=n) for n in (*NOTIFY_EVENTS, "all")]
WATCH_MODE_CHOICES = [app_commands.Choice(name=m, value=m) for m in WATCH_MODES]
```

Append after the `/lessons` command:

```python
# ──────────────────────────────────────────────
# /notify  (v152 D1)
# ──────────────────────────────────────────────

_ON_OFF = {True: "on", False: "off"}
NOTIFY_PAIRING = ("Pass `event:` and `enabled:` together to change one update. "
                  "Nothing was changed.")
NOTIFY_STORE_DOWN = "Could not read or save your notify settings right now. Try again shortly."


def _notify_line(event: str, prefs: dict) -> str:
    following = _ON_OFF[mentions_user(frozenset({"taken"}), event, prefs)]
    watch = ("never" if event in FOLLOWING_ONLY
             else _ON_OFF[mentions_user(frozenset({"watch"}), event, prefs)])
    return f"• `{event}` — {EVENT_LABELS[event]}. Following: {following} · Watch: {watch}"


def _notify_summary(prefs: dict) -> str:
    """Which events the notify channel announces, and when it mentions the caller."""
    mode = prefs.get("watch_mode") if prefs.get("watch_mode") in WATCH_MODES else "mention"
    return "\n".join([
        "**The notify channel posts these paper plan updates** (facts, not advice):",
        *(_notify_line(event, prefs) for event in NOTIFY_EVENTS),
        f"Watch-only plans: {mode}.",
        "`closed_other` posts only when a plan has a Following follower, and mentions only them. "
        "Your settings decide whether you are mentioned, never whether a message posts.",
        "Change: `/notify event:<name|all> enabled:<true|false>` · `/notify watch_mode:<mention|silent>`",
    ])


def _apply_notify_change(user_id: int, event: str | None, enabled: bool | None,
                         watch_mode: str | None) -> dict:
    """Store the caller's change (sync; run in a thread) and return their prefs."""
    from swingbot.core.db.repositories.notify_prefs import notify_prefs_repo
    repo = notify_prefs_repo()
    if event is not None and enabled is not None:
        for name in (NOTIFY_EVENTS if event == "all" else (event,)):
            repo.set_pref(user_id, name, bool(enabled))
    if watch_mode is not None:
        repo.set_pref(user_id, "watch_mode", watch_mode)
    return repo.prefs(user_id)


@bot.tree.command(name="notify", description="Choose which paper plan updates mention you in the notify channel")
@app_commands.describe(event="The update to change, or all",
                       enabled="Mention me for it (true) or not (false)",
                       watch_mode="On plans I only Watch: mention me, or stay silent")
@app_commands.choices(event=NOTIFY_EVENT_CHOICES, watch_mode=WATCH_MODE_CHOICES)
async def slash_notify(interaction: discord.Interaction, event: app_commands.Choice[str] = None,
                       enabled: bool = None, watch_mode: app_commands.Choice[str] = None):
    event_name = event.value if event else None
    if (event_name is None) != (enabled is None):
        await interaction.response.send_message(NOTIFY_PAIRING, ephemeral=True)
        return
    mode = watch_mode.value if watch_mode else None
    try:
        prefs = await asyncio.to_thread(_apply_notify_change, interaction.user.id,
                                        event_name, enabled, mode)
    except Exception:
        log.warning("/notify: could not read or save prefs for user %s",
                    interaction.user.id, exc_info=True)
        await interaction.response.send_message(NOTIFY_STORE_DOWN, ephemeral=True)
        return
    await interaction.response.send_message(_notify_summary(prefs), ephemeral=True)
```

`NOTIFY_PAIRING` contains "together", which the half-specified test reads.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_slash_notify.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/commands/test_slash_commands.py`, then the same for `tests/commands/test_stats_commands.py`
Expected: PASS (`test_slash_has_no_direct_colour` covers the new code; the registration tests still find every command).
Run: `python -c "import swingbot.commands.slash"`
Expected: no output, exit 0 (no import cycle from the new top-level import).

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/slash.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/slash.py tests/commands/test_slash_notify.py
git commit -m "feat(v152): /notify -- per-user mention settings for the notify channel (V152-19)"
```

V152-20 continues in [`_4b-full-suite`](2026-10-10-v152-discord-notify-taken-cooldown_4b-full-suite.md) (this file sits at the 1500-line cap).

# Phase 3: the full suites

### Task V152-20: Full suites + complexity check

**Model:** haiku — runs fixed commands and compares their output with stated expectations; no code is written.

**Files:** none (verification only).

Runs after **every** other task, including the v151-gated V152-16..V152-18. It is the plan's single full-suite run (index § Global Constraints); per-task runs were narrow.

- [ ] **Step 1: Every task is committed**

Run: `git log --oneline main..HEAD | grep -o "V152-[0-9]*" | sort -t- -k2 -n -u`
Expected: `V152-2` through `V152-19` each appear (V152-1 is a results note; check `git ls-files "docs/superpowers/results/*v152-notify-cooldown-volume.md"` prints one path). Any missing id → stop and report which; do not run the suites over a partial plan.
Run: `git status --short`
Expected: no modified tracked file.

- [ ] **Step 2: Full Python suite**

Dispatch the `test-runner` agent with `python scripts/dev/testrun.py full` (or run it directly; it prints a one-line verdict).
Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). Store tests need `db-test` up; skipped store tests with the start command in the reason mean the database was down — start it and re-run, a skip is not a pass.
On a failure: read only the failing test's output, fix it in a separate commit that names the task it repairs (`fix(v152): ... (V152-n)`), re-run that file with `python scripts/dev/testrun.py file <test>`, then re-run this step once.

If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), also run `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py`. Expected: PASS (every new handler carries its `swallowed()` call; `BASELINE` is never raised). If `scripts/dev/complexity_gate.py` exists (v149 merged), also run `python scripts/dev/complexity_gate.py`. Expected: no `new`/`risen` verdict (v152 moves no legacy function, so the baseline needs no edit).

- [ ] **Step 3: Full SPA suite**

Run: `npm --prefix frontend test -- --watch=false`
Expected: every spec passes, including `stores/analytics.store.spec.ts` and `workspaces/analytics/tabs/attribution.spec.ts` from V152-10.

- [ ] **Step 4: Complexity against the base**

Run: `pip install radon` (once), then:

```bash
python - <<'COMPLEXITY_EOF'
"""Every function v152 wrote or changed is < 15; a legacy one >= 15 is no worse."""
import json
import pathlib
import subprocess
import sys
import tempfile

FILES = [
    "swingbot/core/db/schema.py",
    "swingbot/core/db/repositories/followers.py",
    "swingbot/core/db/repositories/notify_prefs.py",
    "swingbot/core/db/repositories/notifications.py",
    "swingbot/core/db/repositories/alert_posts.py",
    "swingbot/config.py",
    "swingbot/commands/views.py",
    "swingbot/bot_core.py",
    "swingbot/core/tracking/performance.py",
    "swingbot/core/analytics/aggregate.py",
    "swingbot/commands/scanning/cooldown.py",
    "swingbot/commands/scanning/alerts.py",
    "swingbot/core/planning/plan_manager.py",
    "swingbot/core/scanning/lifecycle_embeds.py",
    "swingbot/commands/scanning/follow_notify.py",
    "swingbot/commands/scanning/loops.py",
    "swingbot/commands/slash.py",
]


def scores(path: str) -> dict:
    out = subprocess.check_output([sys.executable, "-m", "radon", "cc", "-j", path], text=True)
    blocks = next(iter(json.loads(out).values()))
    return {f"{b.get('classname') or ''}.{b['name']}": b["complexity"]
            for b in blocks if b.get("type") in ("function", "method")}


base = subprocess.check_output(["git", "merge-base", "main", "HEAD"], text=True).strip()
tmp = pathlib.Path(tempfile.mkdtemp())
bad = []
for path in FILES:
    now = scores(path)
    try:
        source = subprocess.check_output(["git", "show", f"{base}:{path}"], text=True,
                                         stderr=subprocess.DEVNULL)
        copy = tmp / pathlib.Path(path).name
        copy.write_text(source, encoding="utf-8")
        old = scores(str(copy))
    except subprocess.CalledProcessError:
        old = {}                                   # a file this plan created
    for name, score in now.items():
        if score >= 15 and score > old.get(name, 0):
            bad.append(f"{path} {name}: {old.get(name, 'new')} -> {score}")
print("\n".join(bad) if bad else "complexity OK")
sys.exit(1 if bad else 0)
COMPLEXITY_EOF
```

Expected: `complexity OK`. The legacy figures this checks implicitly: `PlanManager.poll` stays 20, `_step_active` stays 21 (not edited); `notify_plan_events` 13, `_send_alerts` 10 and `close_plan_trade` 8 are under 15 and pass as any changed function must. A line printed → split the named function into helpers per `docs/claude/code-complexity.md` in a separate `fix(v152)` commit, then re-run Steps 2 and 4.

- [ ] **Step 5: Syntax pass and copy-rule spot checks**

Run: `python -m py_compile bot.py admin_ui.py swingbot/commands/scanning/follow_notify.py swingbot/commands/scanning/cooldown.py swingbot/commands/slash.py swingbot/commands/views.py swingbot/commands/scanning/loops.py`
Expected: no output.
Run: `git grep -n "Kind.MOVE_STOP\|Kind.CANCEL\|discord.Colo" swingbot/commands/scanning/follow_notify.py swingbot/commands/views.py swingbot/commands/slash.py`
Expected: no output (imperative kinds are never used by the notifier; no direct colour).
Run: `git grep -n "silence(" swingbot/commands/scanning/follow_notify.py`
Expected: no output (the notify channel is never silenced).
Run: `git grep -n "apply_cooldown=True" swingbot/`
Expected: exactly one line, the scheduled `send_then_short` call in `_session_scan_tick` (`swingbot/commands/scanning/loops.py`, V152-15).
Run: `git grep -n "DISCORD_CHANNEL_NOTIFY_ID=\|ALERT_SYMBOL_COOLDOWN_HOURS=" .env.example`
Expected: two lines.
Run: `git diff --name-only main..HEAD -- VERSION.json version_history.json`
Expected: no output (`/close-out` bumps `bot minor · ui patch`, not a task).

- [ ] **Step 6: Record the verdict and hand off**

Append one line to `.superpowers/sdd/progress.md` (append only; never `cat` the file): `v152 V152-20: full suite <N passed, 0 failed, 0 xfailed>, SPA suite green, complexity OK`.
Nothing else is committed by this task: it changes no tracked file. The plan is then ready for `/panel veteran-trader,financial-advisor,staff-engineer` over the diff (the spec's `Panel:` line) and `/close-out`; the production steps (`alembic upgrade head`, `DISCORD_CHANNEL_NOTIFY_ID` via `scripts/ops/env_set.py` under `mirror-prod`, the channel topic) are the index's "After merge" list, not this task.

