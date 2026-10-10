# v153 Slash command parity. Part 5: help catalog, parity test, superseded tests, resync script, tip date, full suite

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Index:** `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`. Global Constraints, Parallelisation and the task ledger live there and are binding here. Read `## Global Constraints` before any task.

These six tasks run **after every module task (SP5–SP16) has landed**. Order: SP17, SP18, then SP19 and SP20 in parallel (disjoint files), then SP21, then SP22.

**Shared conventions for this part** (they restate the index; the index wins on any conflict):

- `$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity`. Never `cd`; use `git -C $WT` and absolute paths. Python commands that import the package run with `PYTHONPATH=$WT`.
- Consumed from SP1 (`swingbot/commands/reply.py`): `SLASH_TWIN`, `PREFIX_TIP_UNTIL`, `prefix_tip`, `send_prefix_tip`, `_today`, `CtxReply`, `InteractionReply`. From SP1's harness: `ParityCase`, `run_both`, `comparable`.
- Consumed from SP4: `SLASH_ONLY` in `swingbot/commands/notify.py`, **only if v152 landed** (then `bot.py` imports `notify`). SP18 reads `SLASH_ONLY` off whatever module defines it, so it needs no branch of its own.
- Consumed from SP7: `growth.slash_killswitch`. From SP9: `info.HELP_DESCRIPTION`, `info.handle_help`, and the `info_help` parity case with its `_freeze_clock` stub.
- `send_error` answers carry no tip. `ui.apply_chrome` stamps `discord.utils.utcnow()` on an embed; a test that builds a chromed embed twice and compares them freezes that clock.
- Narrow test runs only: `python $WT/scripts/dev/testrun.py file <test>`. The full suite runs once, in SP22.
- **discord.py must be installed** where the tests run (index, "Where to work").

# Phase 5: Catalog, parity, rollback remedy, close

