# v153 Slash command parity through shared handlers. Implementation Plan, part 1b (`/notify` check)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `/task-brief SP4` or `grep -n "^### Task SP4:" -A 150 docs/superpowers/plans/2026-10-10-v153-slash-command-parity_1b-notify-check.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`](../specs/2026-10-09-v153-slash-command-parity-design.md) (section "New top-level names")
**Index:** [`2026-10-10-v153-slash-command-parity_0-index.md`](2026-10-10-v153-slash-command-parity_0-index.md): header block, `## Where to work`, `## Global Constraints`, `## Parallelisation` and the task ledger bind every task below.

Part 1 is split in two files only to stay under 1500 lines (audit 2026-10-10): [`_1-foundation`](2026-10-10-v153-slash-command-parity_1-foundation.md) holds SP1–SP3, this file SP4. Same part, same ledger rows, same contracts, and part 1's conventions paragraph (`$R`, `$WT`, never `cd`, radon < 15) applies unchanged. SP4 needs SP1 (`InteractionReply`) and SP3 (both edit `swingbot/commands/slash.py`).

# Phase A (continued): Foundation

### Task SP4: `/notify` out of `slash.py` (only if v152 landed)

**Model:** sonnet — a conditional, verbatim block move onto `InteractionReply`; usually a no-op.

**Files (only if Step 1 prints a line; otherwise none):**
- Create: `swingbot/commands/notify.py`
- Modify: `swingbot/commands/slash.py`
- Modify: `bot.py`

**Why:** spec "New top-level names": if v152 has landed, `/notify` (slash-only) moves out of `slash.py` into `swingbot/commands/notify.py` with its handler, unchanged. On this branch v152 is **not** merged (brief §0.1; its `/notify` is v152 task V152-19, not yet written), so the expected outcome is the no-op path.

- [ ] **Step 1: Check whether `/notify` exists**

```bash
git -C $WT grep -n 'name="notify"' -- swingbot/commands/slash.py
```

- [ ] **Step 2a: Empty output (expected) — record the no-op, commit nothing**

```bash
mkdir -p /home/user/Discord-Bot/.superpowers/sdd
echo "$(date -I) v153 SP4: no-op -- /notify not in slash.py (v152 not landed); SP18 count stays 41" >> /home/user/Discord-Bot/.superpowers/sdd/progress.md
```

Report `SP4: no-op` and stop. Skip Steps 2b–5.

- [ ] **Step 2b: `/notify` exists — move it**

Create `$WT/swingbot/commands/notify.py` with this frame, then move into it, **verbatim**, the `/notify` decorator stack and every helper only it uses (V152-19 names `_notify_summary(prefs) -> str`), plus their imports:

```python
"""/notify -- per-user notify settings (v152 D1). Slash-only (v153 SP4)."""
import discord
from discord import app_commands

from swingbot.bot_core import bot
from swingbot.commands.reply import InteractionReply

SLASH_ONLY = {"notify"}   # read by tests/commands/test_slash_parity.py (SP18)


async def handle_notify(reply, event: str, enabled: bool | None = None,
                        watch_mode: str | None = None) -> None:
    """The moved body. Mechanical rewrites only:
    interaction.user -> reply.author;
    interaction.response.defer(...) -> await reply.defer(ephemeral=True);
    interaction.response.send_message(x, ephemeral=True) and
    interaction.followup.send(x, ephemeral=True) -> await reply.send(x, ephemeral=True)."""
```

Match `handle_notify`'s parameters to the moved command's options exactly (names, defaults). The twin keeps its decorators, function name and options verbatim and becomes:

```python
async def slash_notify(interaction: discord.Interaction, event: app_commands.Choice[str],
                       enabled: bool | None = None,
                       watch_mode: app_commands.Choice[str] | None = None):
    await handle_notify(InteractionReply(interaction), event.value, enabled,
                        watch_mode.value if watch_mode else None)
```

Delete the block and its helpers from `slash.py`. In `$WT/bot.py`, after the `from swingbot.commands import slash` line, add:

```python
from swingbot.commands import notify     # noqa: F401  — /notify (slash-only, v152)
```

In v152's `tests/commands/test_slash_notify.py`, replace `slash._notify_summary` with `notify._notify_summary` (import `from swingbot.commands import notify`) and append:

```python
def test_notify_is_registered_by_its_own_module():
    import pathlib
    from swingbot.bot_core import bot
    from swingbot.commands import notify

    assert notify.SLASH_ONLY == {"notify"}
    assert "notify" in {cmd.name for cmd in bot.tree.get_commands()}
    assert 'name="notify"' not in pathlib.Path("swingbot/commands/slash.py").read_text(encoding="utf-8")
```

- [ ] **Step 3: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_notify.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_error_handler.py
```

Expected: `0 failed`, `0 xfailed`.

- [ ] **Step 4: Complexity** — `python -m radon cc -s -n C $WT/swingbot/commands/notify.py $WT/swingbot/commands/slash.py` prints nothing; paste it into the report.

- [ ] **Step 5: Commit**

```bash
git -C $WT add swingbot/commands/notify.py swingbot/commands/slash.py bot.py tests/commands/test_slash_notify.py
git -C $WT commit -m "refactor(v153): /notify moves to its own module on InteractionReply (SP4)"
git -C /home/user/Discord-Bot status --short
```
