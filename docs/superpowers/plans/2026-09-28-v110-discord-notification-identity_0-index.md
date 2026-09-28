# v110 — Distinct, colourful Discord notifications (one registry of kinds) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-09-28-v110-discord-notification-identity-design.md`](../specs/2026-09-28-v110-discord-notification-identity-design.md)
**Bump:** bot minor
**Edge:** none (integrity)

**Goal:** Every message the bot pushes unprompted is recognisable by kind from its phone push preview alone, and again from its stripe colour plus badge in the channel. All styling comes from one registry, and three send bugs are fixed along the way.

**Architecture:** A new pure module `swingbot/core/presentation/kinds.py` holds `Family` (6), `Kind` (one per pushed event), the stripe ramps and four helpers: `title`, `content_line`, `stripe`, `footer`. `components.py` gains `PushEmbed`, a `discord.Embed` subclass that carries its push line in a `push_text` slot. Every pushed builder returns one, and every sender calls `send(**ui.push_kwargs(embed))`, so the push line reaches `content` without changing any alert-tuple shape. `apply_chrome` gains `kind=`: pushed builders pass it and get the registry stripe and footer, while command replies keep passing `accent=` and look exactly as before. System messages become SYSTEM embeds through a new `commands/scanning/notices.py`.

**Tech Stack:** Python 3.11, discord.py 2.7 (`discord.Embed` with `__slots__`), pytest (`asyncio.run`, no pytest-asyncio), radon.

## Global Constraints

Copied from the spec. Every task's requirements include this section.

- **In scope:** every message the bot pushes unprompted: full scan alert, strategy signal, v2 simple ticket (PLACE and DO NOT PLACE), legacy simple mirror, execution-feed lifecycle posts and their HISTORY copies, plan-event status posts, closed trade, near close, top-plans digest, weekend deep scan, scan summary, health alert and recovered, bot online, config-change notices, retrospective, and the per-tick healthcheck line.
- **Out of scope:** command replies (`!trade`, `!today`, `!plans`, stats, help, breakdown, command errors, the manual `!check` progress edits), chart images, the admin UI, and any change to what is sent, when, or to which channel. The one exception is the closed-trade icons: `commands/trades.py` reads the registry's outcome marks, but its title shape is not redesigned.
- **Glyph rules, everywhere in pushed messages:** ▲/▼ mean direction only. ✅/❌ mean outcome only. 🟢/🔴 are retired from pushed titles. A family badge is never reused as an outcome or direction mark.
- **Families** (spec §1): NEW SETUP 🆕 (blue ramp by confidence Lv1→Lv5; muted grey-blue when blocked / DO NOT PLACE), ENTRY 🎯 (teal), MANAGE 🛡️ (event emoji 🛡️ break-even, 💰 TP1, ✂️ move stop, 🚫 cancel / risk cap; amber), WATCH 👀 (orange nearing stop, lime nearing TP), RESULT 🏁 + outcome ✅ win, ❌ loss, ⚪ scratch, 🔒 manual, ⏹️ expired/invalidated (green or red ramp by abs(R); grey for scratch / manual / expired / invalidated), SYSTEM 🩺 (🚨 health alert, ✅ recovered, ⚙️ config, 🤖 online, 📜 retrospective, 🔭 deep scan; slate, red for health alert, green for recovered).
- **Registry helpers** (spec §2), and the only way a pushed builder styles a message: `title(kind, ticker, direction=None, detail="") -> str`, `content_line(kind, ticker, direction=None, detail="") -> str`, `stripe(kind, level=None, r=None, blocked=False) -> int`, `footer(kind, plan_id=None) -> str`. `disclaimer` is true only for NEW SETUP kinds.
- `tokens.py` (`ACCENT_RAMP`, `accent_for_level`, `accent_for_outcome`, `confidence_label`) is **not changed**, because command replies still use it. The new ramps are separate constants in `kinds.py`.
- **ANSI block** (spec §3): NEW SETUP, ENTRY and RESULT embeds carry a fenced `ansi` block built with `presentation/ansi.py` (`paint`, `block`, 32-visible-character cap). ▲ LONG is green and ▼ SHORT red, entry cyan, stop red, TP1/TP2 green, R multiples yellow, and on RESULT the realised R green (win) or red (loss). Every line must stay readable with the escapes stripped. The full alert's existing headline is restyled, and no second block is added.
- **Push text and footer** (spec §4): every pushed embed is sent with `content=content_line(kind, …)`. The closed-trade `✅ WIN — **TICK**` header and the digest's `📌 **Top plans today**` header are replaced by the registry line. The digest keeps one content line for the batch. Silent/notify flags are unchanged. NEW SETUP keeps `DISCLAIMER` (plus `· plan xxxxxxxx`). Every other family's footer is `<FAMILY> · plan xxxxxxxx`, or `<FAMILY>` alone.
- **System messages** (spec §5) become slate SYSTEM embeds with a content line. The retrospective stays chunked, one embed per chunk, each within 4096 characters. The per-tick healthcheck stays a plain text line prefixed with 🩺.
- **Send fixes** (spec §6):
  1. The strategy-alert mirror gets a real `Embed`, never a `str`.
  2. Each main alert send in a batch is guarded, logged with `exc_info`, and the batch continues.
  3. The bot-online post and the retrospective chunk sends get the same guard.
  4. The stale notes in `known-traps.md` are refreshed.
- `tests/presentation/test_no_adhoc_color.py` still holds: no `discord.Color` / `Embed(color=…)` outside `swingbot/core/presentation/`.
- Every function written or changed ends at cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`), and a legacy function already at 15 or more never gets worse. Legacy baselines, measured 2026-09-28: `build_embed` 41, `build_closed_trade_embed` 20, `_send_alerts` 26, `_session_scan_tick` 30, `config_watcher` 27, `on_ready` 17, `summary_cmd` 54, `_build_trade_detail_embed` 17. Every one of these must end **lower** than its baseline, because each task removes branches from it.
- Engine re-exports stay: `swingbot/core/scanning/engine.py` and `embeds.py` keep every name in their `__all__` (`known-traps.md`: an "unused import" here is a re-export).
- Never `cd` in Bash; use absolute paths or the worktree root.

## Spec gaps resolved in this plan (not design changes)

1. **Hex values** (spec §3 delegates them). NEW SETUP `0xA5CDFF 0x74AEFF 0x3D8BFF 0x1F66E0 0x0B44B0` (Lv1→Lv5), blocked `0x7D8CA3`. ENTRY `0x14B8A6`. MANAGE `0xF5A524`. WATCH stop `0xFF6A13`, TP `0xA3E635`. RESULT greens `0x86EFAC 0x22C55E 0x15803D` and reds `0xFCA5A5 0xEF4444 0xB91C1C` (abs(R) `< 1`, `1–2`, `≥ 2`), grey `0x9CA3AF`. SYSTEM slate `0x5B6B82`, health red `0xE11D48`, recovered green `0x34D399`. `test_kinds.py` proves that no value is shared across families.
2. **Weekend deep scan.** The spec's §1 lists "weekend deep scan" under NEW SETUP, but §1's SYSTEM row and §5 make the deep-scan *header* a slate SYSTEM embed (🔭). Today the deep scan is one message, header plus candidate lines. It stays one message (spec: no change to what is sent): a SYSTEM `Kind.DEEP_SCAN` embed whose candidate lines each carry their ▲/▼. It has no disclaimer, because the report says "NOT alerts".
3. **RESULT outcome mark.** RESULT kinds carry no event emoji. The outcome mark rides in the `detail` argument through `kinds.outcome_detail(outcome, r)` (`✅ WIN +1.8R`), because one kind (closed trade, EXITED) can end in any outcome. This keeps the spec's four-helper signatures unchanged.
4. **Fallback kind.** `notify_plan_events` posts a history-only embed for transitions outside the feed (e.g. `pyramid_add`, covered by `test_non_feed_events_stay_history_only`). The spec's table has no kind for it, so one MANAGE kind is added: `Kind.PLAN_UPDATE` (🛡️, "PLAN UPDATE").
5. **Strategy mirror (§6.1).** A new `alert_embeds.build_strategy_simple_embed(plan)` of kind `STRATEGY_SIGNAL` (levels block plus one context line), rather than the v2 ticket. The ticket needs `PLAN_ENGINE_V2`-gated item state that a strategy plan does not have. The dead `strategy_pass.simple_line` is deleted.
6. **Non-outcome check marks in pushed builders.** The VALIDATED badge line (strategy and plan-event embeds) drops its ✅ (`kinds.plan_badge_text`). The intraday "✅ confirms", the scan summary's "✅ qualifying" and the healthcheck's ✅/❌ bullets become ✔/✖. This is required by "no glyph carries two meanings".
7. **`presentation/test_tokens.py`** is listed in the spec's Testing section, but `tokens.py` is deliberately unchanged, so that file needs no edit and must stay green untouched.
8. **`!top`** reuses `build_embed` (the digest's builder). It inherits the new full-alert look, as the digest must. `tests/test_stats_commands.py` is updated for that.

## Parallelisation

- **Group A (parallel):** V110-1 and V110-2.
  - V110-1 touches `kinds.py` and `tests/presentation/test_kinds.py`.
  - V110-2 touches `ansi.py`, `components.py`, `presentation/__init__.py`, `test_ansi.py` and `test_components.py`.
  - The files are disjoint, and neither consumes the other.
- **Sequential:** V110-3 comes after Group A. It edits `components.py` / `__init__.py` again (after V110-2) and consumes `kinds.stripe` / `kinds.footer` (V110-1).
- **Group B (parallel, after V110-3):** four streams.
  - **Stream 1 (chain):** V110-4 → V110-5 → V110-6.
    - V110-4 and V110-5 share `tests/scanning/test_simple_alerts.py`.
    - V110-5 and V110-6 share `tests/scanning/test_execution_feed_routing.py`.
    - V110-4 and V110-6 share `tests/scanning/test_embeds_v3.py`.
    - V110-6 consumes V110-4's `strategy_plan_line` and V110-5's `plan_levels_block` / `plan_result_block`.
  - **Stream 2:** V110-7 (`commands/trades.py`, `tests/test_trades_display.py`). It consumes only V110-1.
  - **Stream 3:** V110-9 (`commands/scanning/alerts.py`, `tests/commands/test_send_alerts_v110.py`). It consumes V110-1 and V110-3.
  - **Stream 4:** V110-10 (new `commands/scanning/notices.py`, `tests/commands/test_system_notices.py`). It consumes V110-1 and V110-3.
  - All four streams have disjoint files.
- **Sequential edges into Phase C:**
  - V110-8 (`strategy_pass.py`, `tests/scanning/test_strategy_pass_emit.py`) comes after V110-4, because it consumes `build_strategy_simple_embed`. It may run beside V110-5 / V110-6 (disjoint files).
  - V110-11 (`loops.py`, `tests/scanning/test_heartbeat_outcome.py`, `tests/commands/test_loops_notices.py`) comes after V110-10, because it consumes the `notices` builders.
  - V110-12 (`recap.py`, `tests/commands/test_recap_notices.py`) comes after V110-9 (the deep-scan report text it posts) and V110-10.
  - V110-11 and V110-12 may run in parallel (disjoint files).
- **V110-13** (docs: `known-traps.md`, `architecture.md`) may run any time after V110-3, since it names `PushEmbed` / `push_kwargs`. Its files are disjoint from every code task.
- **Sequential from here on:**
  - V110-14 (the one full-suite run, the complexity sweep and the rendered before/after) comes after every code task.
  - V110-15 (merge and release) comes after V110-14.
  - V110-16 (production verification and close-out) comes after V110-15's deploy.
- All parallel tasks share one worktree. Each stages only its own files and commits with an explicit pathspec. If a commit fails on `index.lock`, wait and retry. Never `git add -A`.

## Conventions for every task

- V110-1..V110-14 run in the worktree `.claude/worktrees/2026-09-28-v110-discord-notification-identity` on branch `2026-09-28-v110-discord-notification-identity`, created from `main` before V110-1 (`worktree-lifecycle` skill). V110-15 merges it. Run every command from the worktree root.
- Load the `alert-surface` skill before V110-4, V110-5, V110-6 and V110-9. Its gate (a rendered before/after) is run once, in V110-14.
- Per-task check: `python scripts/dev/testrun.py file <the task's test file(s)>`, never `full`, because V110-14 is the one full run.
- Complexity check per task: `python -m radon cc -s -n C <the task's modified .py files>`. Every function the task wrote or changed must be absent from the output (below C means < 11), or sit at C with a value < 15, or be a listed legacy function now **below** its baseline.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Throughout the plan, `ui` means `from swingbot.core import presentation as ui`, `kinds` means `from swingbot.core.presentation import kinds`, and `Kind` / `Family` are imported from `swingbot.core.presentation.kinds`.

## Parts

| File | Tasks |
|---|---|
| `2026-09-28-v110-discord-notification-identity_0-index.md` | header, goal, constraints, resolved gaps, parallelisation, conventions (this file) |
| `2026-09-28-v110-discord-notification-identity_1-registry.md` | Phase A — registry and presentation parts (V110-1..V110-3) |
| `2026-09-28-v110-discord-notification-identity_2-builders.md` | Phase B — pushed builders (V110-4..V110-7) |
| `2026-09-28-v110-discord-notification-identity_3-senders-release.md` | Phase C — senders and system notices (V110-8..V110-12), Phase D — docs, verification, release (V110-13..V110-16) |

Pull one task with `grep -n "^### Task V110-4" -A 260 docs/superpowers/plans/2026-09-28-v110-discord-notification-identity_*.md` or `/task-brief V110-4`. Never read a part whole.
