# v62 part 3 — the command modules

Index and global constraints C1–C9: `2026-08-25-v62-discord-message-system_0-index.md`.
Read that first.

Worktree: `2026-08-25-v62-discord-message-system_3-commands`.

**Tasks M21–M26 are the plan's one wide parallel group.** Each owns exactly one
command module, none shares a file, and all six consume only the kit Part 1
froze. See the index's Parallelisation section before dispatching.

**The measured surface** (`git grep -cE "discord\.Colou?r\." -- 'swingbot/commands/*.py'`):

| Module | Colour sites | Task |
|---|---|---|
| `trades.py` | 7 | M21 |
| `stats.py` | 3 | M23 |
| `info.py` | 1 | M24 |
| `plans.py` | 1 | M22 |
| `slash.py` | 1 | M26 |
| `views.py` | 1 | M25 |

`history.py`, `growth.py`, `account.py`, `data.py`, `backtest.py`,
`watchlist.py` and `scanning.py` register zero colour sites today; M27 sweeps
them for formatters and glyphs rather than colour.

---

# Phase 7 — The migration

## The shared procedure

M21–M26 are the same five steps against different files. It is written once
here, and each task names only what is specific to it. **Read this before
starting any of them.**

1. **Inventory the module.**

   ```bash
   git grep -nE "discord\.Colou?r\.|Embed\(|:\.[0-9]f|▲|▼|🔴|🟠|🟡|🟢|1️⃣" -- swingbot/commands/<module>.py
   ```

   Every hit is a migration candidate: a colour, an embed construction, a
   hand-rolled number format, or a deleted-vocabulary glyph.

2. **Write the failing test** in the module's own test file, asserting the
   post-migration shape. Every task below gives its own test code.

3. **Migrate.** The substitutions are always these:

   | Found | Becomes |
   |---|---|
   | `discord.Color.green()` on a good outcome | `ui.accent_for_outcome("win")` |
   | `discord.Color.red()` on a bad outcome | `ui.accent_for_outcome("loss")` |
   | `discord.Color.blue()` / `blurple()` / any hue meaning "neutral" | `ui.accent_for_outcome("scratch")` |
   | a confidence-driven colour | `ui.accent_for_level(level)` |
   | `discord.Color.X()` on an informational listing | `ui.accent_for_outcome("scratch")` |
   | `embed.set_footer(...)` + `embed.timestamp = ...` | `ui.apply_chrome(embed, accent=..., plan_id=...)` |
   | `f"{price:.2f}"` | `ui.fmt_price(price)` |
   | `f"{pct:+.1f}%"` | `ui.fmt_pct(pct)` |
   | `f"{r:+.2f}R"` | `ui.fmt_r(r)` |
   | `"▲" if bull else "▼"` | `ui.direction_glyph(direction)` |
   | `Lv{n}` built by hand, or a keycap emoji | `ui.confidence_label(level, score)` |

   Import as `from swingbot.core import presentation as ui`.

4. **Run the module's own test file** — `python scripts/dev/testrun.py file tests/<its test>.py`.
   Never `full`; that is C7 and it is Task M29's job.

5. **Commit**, one commit per module.

> **A command embed still needs `apply_chrome`.** It is easy to migrate the
> colour and forget the footer, which leaves a command response as the only
> embed in the bot with no disclaimer and no timestamp. The tests below check
> for it.

---

### Task M21: `trades.py` — 7 colour sites

**Files:**
- Modify: `swingbot/commands/trades.py`
- Test: `tests/test_trades_display.py`

**Interfaces:**
- Consumes: `presentation.accent_for_outcome`, `accent_for_level`,
  `apply_chrome`, `fmt_price`, `fmt_pct`, `fmt_r`, `direction_glyph`.
- Produces: nothing.

The heaviest module in the group — it renders open positions, closed history
and per-trade detail, so it touches every colour axis at once.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_trades_display.py
import ast
import pathlib

from swingbot.core.presentation import tokens as tk

MODULE = pathlib.Path("swingbot/commands/trades.py")


def test_no_direct_colour_remains():
    """The same rule test_no_adhoc_color.py enforces globally, asserted
    here too so this module's own suite fails first and names itself."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr in ("Color", "Colour")]
    assert not hits, f"discord.Color still set at lines {hits}"


def test_a_winning_trade_embed_takes_the_ramps_green(win_trade_ctx):
    embed = build_trade_embed(win_trade_ctx)
    assert embed.color.value == tk.ACCENT_RAMP[5]


def test_every_embed_this_module_builds_carries_chrome(win_trade_ctx):
    """apply_chrome sets accent, footer and timestamp together precisely
    so a builder cannot migrate the colour and forget the disclaimer."""
    embed = build_trade_embed(win_trade_ctx)
    assert embed.footer.text and tk.DISCLAIMER in embed.footer.text
    assert embed.timestamp is not None


def test_prices_render_through_the_kit(win_trade_ctx):
    """So a sub-1.00 ticker keeps four decimals here exactly as it does in
    an alert. Hand-rolled :.2f was what made the two disagree."""
    embed = build_trade_embed(win_trade_ctx)
    assert tk.fmt_price(win_trade_ctx["entry"]) in embed.description
```

Replace `build_trade_embed` / `win_trade_ctx` with whatever this module and
its existing tests actually name — read the test file's head first.

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/test_trades_display.py -v -k "colour or chrome"`
Expected: FAIL — seven `discord.Color` attributes remain.

- [ ] **Step 3: Migrate, using the shared substitution table above**

- [ ] **Step 4: Run the module's tests**

Run: `python scripts/dev/testrun.py file tests/test_trades_display.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/trades.py tests/test_trades_display.py
git commit -m "refactor(v62): trades commands onto the presentation kit"
```

---

### Task M22: `plans.py` and `history.py`

**Files:**
- Modify: `swingbot/commands/plans.py`, `swingbot/commands/history.py`
- Test: `tests/test_plans_board.py`, `tests/test_info_plans.py`

**Interfaces:** as the shared procedure.

Both render plan *boards* — lists of un-filled plans — so their accent axis is
confidence, not outcome. `history.py` has no colour site today but does
hand-roll prices.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_plans_board.py
import ast, pathlib
from swingbot.core.presentation import tokens as tk


def test_no_direct_colour_remains_in_either_module():
    for path in ("swingbot/commands/plans.py", "swingbot/commands/history.py"):
        tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
        hits = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Attribute) and n.attr in ("Color", "Colour")]
        assert not hits, f"{path}: discord.Color at {hits}"


def test_the_board_accents_on_confidence_not_outcome(plans_ctx):
    """A board lists plans that have not resolved. There is no outcome to
    colour, so the axis is confidence -- C2's 'good/bad' read as 'how
    strong', which is what the ramp means on an alert too."""
    embed = build_plans_embed(plans_ctx)
    assert embed.color.value in set(tk.ACCENT_RAMP.values())


def test_rows_use_the_shared_direction_glyph(plans_ctx):
    embed = build_plans_embed(plans_ctx)
    assert "▲" in embed.description or "▼" in embed.description
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/test_plans_board.py -v -k colour`
Expected: FAIL

- [ ] **Step 3: Migrate both modules**

- [ ] **Step 4: Run both test files**

Run:

```bash
python scripts/dev/testrun.py file tests/test_plans_board.py
python scripts/dev/testrun.py file tests/test_info_plans.py
```

Expected: `VERDICT: PASS` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/plans.py swingbot/commands/history.py tests/test_plans_board.py tests/test_info_plans.py
git commit -m "refactor(v62): plan boards onto the presentation kit"
```

---

### Task M23: `stats.py` — 3 colour sites

**Files:**
- Modify: `swingbot/commands/stats.py`
- Test: `tests/test_stats_commands.py`

**Interfaces:** as the shared procedure.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_stats_commands.py
import ast, pathlib
from swingbot.core.presentation import tokens as tk


def test_no_direct_colour_remains():
    tree = ast.parse(pathlib.Path("swingbot/commands/stats.py").read_text(encoding="utf-8"))
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr in ("Color", "Colour")]
    assert not hits, f"discord.Color at {hits}"


def test_expectancy_and_win_rate_render_through_the_kit(stats_ctx):
    """A win rate is a percentage and an expectancy is an R-multiple. Both
    used to be hand-rolled here, which is why the same figure could show
    two decimals in !stats and one in an alert."""
    embed = build_stats_embed(stats_ctx)
    assert tk.fmt_pct(stats_ctx["win_rate"]) in embed.description
    assert tk.fmt_r(stats_ctx["expectancy_r"]) in embed.description


def test_the_embed_carries_chrome(stats_ctx):
    embed = build_stats_embed(stats_ctx)
    assert tk.DISCLAIMER in embed.footer.text
```

- [ ] **Steps 2–5:** as the shared procedure.

Run: `python scripts/dev/testrun.py file tests/test_stats_commands.py`

```bash
git add swingbot/commands/stats.py tests/test_stats_commands.py
git commit -m "refactor(v62): stats commands onto the presentation kit"
```

---

### Task M24: `info.py` — 1 colour site

**Files:**
- Modify: `swingbot/commands/info.py`
- Test: `tests/test_views.py`

**Interfaces:** as the shared procedure.

`info.py` renders help and command listings — informational, so its accent is
the neutral grey, not a hue chosen for prettiness.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_views.py
import ast, pathlib
from swingbot.core.presentation import tokens as tk


def test_info_has_no_direct_colour():
    tree = ast.parse(pathlib.Path("swingbot/commands/info.py").read_text(encoding="utf-8"))
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr in ("Color", "Colour")]
    assert not hits, f"discord.Color at {hits}"


def test_help_output_is_neutral_not_decorative():
    """A command listing is not good news or bad news. Under C2 the bar
    is ordinal, so an informational embed sits at the neutral point rather
    than picking a hue because it looks nice."""
    embed = build_help_embed()
    assert embed.color.value == tk.ACCENT_RAMP[3]
```

- [ ] **Steps 2–5:** as the shared procedure.

Run: `python scripts/dev/testrun.py file tests/test_views.py`

```bash
git add swingbot/commands/info.py tests/test_views.py
git commit -m "refactor(v62): info commands onto the presentation kit"
```

---

### Task M25: `views.py` — 1 colour site

**Files:**
- Modify: `swingbot/commands/views.py`
- Test: `tests/test_views.py`

> **Shares a test file with M24.** If M24 and M25 are dispatched in parallel
> they will both write `tests/test_views.py` and the second silently overwrites
> the first. Either run them sequentially, or have M25 write its tests to
> `tests/test_views_components.py`. **Sequential is the safe default.**

`views.py` holds the interactive components (buttons, selects) attached to
alerts. Its embed colour must match the alert it is attached to, so it takes
the level accent, not a colour of its own.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_views.py (or tests/test_views_components.py — see above)
import ast, pathlib
from swingbot.core.presentation import tokens as tk


def test_views_has_no_direct_colour():
    tree = ast.parse(pathlib.Path("swingbot/commands/views.py").read_text(encoding="utf-8"))
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr in ("Color", "Colour")]
    assert not hits, f"discord.Color at {hits}"


def test_a_component_response_matches_its_alerts_accent(view_ctx):
    """A button's follow-up embed hanging off a level-5 alert must not
    render at a different level's colour -- that reads as a different
    plan."""
    embed = build_view_response(view_ctx)
    assert embed.color.value == tk.ACCENT_RAMP[view_ctx.level]
```

- [ ] **Steps 2–5:** as the shared procedure.

```bash
git add swingbot/commands/views.py tests/test_views.py
git commit -m "refactor(v62): alert view components onto the presentation kit"
```

---

### Task M26: `slash.py` — 1 colour site

**Files:**
- Modify: `swingbot/commands/slash.py`
- Test: `tests/test_views.py` → use `tests/test_slash_commands.py`; create it
  if it does not exist (check with `ls tests/ | grep slash`)

**Interfaces:** as the shared procedure.

`slash.py` mirrors the prefix commands as `/` equivalents. Its embeds must be
**identical** to their prefix twins — the same command answered two ways
should not look like two commands.

- [ ] **Step 1: Write the failing test**

```python
import ast, pathlib
from swingbot.core.presentation import tokens as tk


def test_slash_has_no_direct_colour():
    tree = ast.parse(pathlib.Path("swingbot/commands/slash.py").read_text(encoding="utf-8"))
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr in ("Color", "Colour")]
    assert not hits, f"discord.Color at {hits}"


def test_a_slash_response_matches_its_prefix_twin(slash_ctx, prefix_ctx):
    """The same question asked two ways must not produce two different
    embeds -- the drift this whole plan exists to remove, in miniature."""
    assert build_slash_embed(slash_ctx).color == build_prefix_embed(prefix_ctx).color
```

- [ ] **Steps 2–5:** as the shared procedure.

```bash
git add swingbot/commands/slash.py tests/test_slash_commands.py
git commit -m "refactor(v62): slash commands onto the presentation kit"
```

---

# Phase 8 — Closing the surface

### Task M27: Sweep the remaining command modules

**Files:**
- Modify: `swingbot/commands/growth.py`, `account.py`, `data.py`,
  `backtest.py`, `watchlist.py`, `scanning.py`
- Test: `tests/test_growth_command.py` and each module's existing test file

**Interfaces:**
- Consumes: `presentation.fmt_price`, `fmt_pct`, `fmt_r`, `direction_glyph`,
  `apply_chrome`.
- Produces: nothing.

**These six register zero `discord.Color` sites**, so the guard would pass
without them. They still hand-roll number formats, which is C8's half of the
problem: `!growth` printing `+12.34%` where an alert prints `+12.3%` is the
same inconsistency in a quieter form.

Must run **after** M21–M26: `scanning.py` calls into the alert builders those
tasks touch.

- [ ] **Step 1: Inventory all six at once**

Run:

```bash
git grep -nE ':\.[0-9]f|\{[a-z_]+:\+?\.[0-9]f\}' -- \
  swingbot/commands/growth.py swingbot/commands/account.py \
  swingbot/commands/data.py swingbot/commands/backtest.py \
  swingbot/commands/watchlist.py swingbot/commands/scanning.py
```

- [ ] **Step 2: Write one failing test covering the shared rule**

```python
# tests/test_growth_command.py — append
from swingbot.core.presentation import tokens as tk


def test_growth_percentages_match_the_alert_format(growth_ctx):
    """One decimal and a U+2212 minus, the same as everywhere else. This
    module printed two decimals and a hyphen."""
    body = build_growth_response(growth_ctx)
    assert tk.fmt_pct(growth_ctx["total_return_pct"]) in body
    assert "-" not in body or "−" in body
```

- [ ] **Step 3: Substitute the formatters in all six**

Do not change what any command says, only how its numbers are formatted.

- [ ] **Step 4: Run the affected test files**

Run:

```bash
python scripts/dev/testrun.py file tests/test_growth_command.py
python scripts/dev/testrun.py fast
```

Expected: `VERDICT: PASS` for both. `fast` here rather than one file, because
this task's blast radius genuinely crosses six modules — that is the exception
C7 allows.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/ tests/
git commit -m "refactor(v62): the remaining command modules format through the kit"
```

---

### Task M28: Widen the guard to the whole surface

**Files:**
- Modify: `tests/presentation/test_no_adhoc_color.py` — `GUARDED_PACKAGES`

**Interfaces:**
- Consumes: nothing.
- Produces: the finished invariant. After this task, **`swingbot/` has exactly
  one place colour is defined.**

- [ ] **Step 1: Widen the tuple**

```python
GUARDED_PACKAGES: tuple[str, ...] = (
    "swingbot/core/presentation",
    "swingbot/core/scanning",      # v62 Part 2 (M20)
    "swingbot/commands",           # v62 Part 3 (M28) -- the whole surface
)
```

- [ ] **Step 2: Run it and fix what it names**

Run: `python -m pytest tests/presentation/test_no_adhoc_color.py -v`

Every failure names a file and a line. Route each through the kit. **Do not
extend `ALLOWED` and do not add a skip** — a guard with an exception list is a
guard that grows exceptions, which is how the 32 original call sites
accumulated.

- [ ] **Step 3: Confirm the guard is actually inspecting files now**

Run:

```bash
python -m pytest tests/presentation/test_no_adhoc_color.py -v | grep -c PASSED
```

Expected: substantially more than the two detector tests — one parametrised
case per `.py` file across three packages. A count of 2 means
`GUARDED_PACKAGES` did not take.

- [ ] **Step 4: Commit**

```bash
git add tests/presentation/test_no_adhoc_color.py
git commit -m "test(v62): the colour guard now covers every module the bot posts from"
```

---

### Task M29: Full-suite verification

Run `python scripts/dev/testrun.py full` **once**, over everything all three
parts implemented. Expect `0 failed`, `0 xfailed`.

**If it is not green, fix forward from those failures** — they are this plan's
regressions, and the task is not done until the run is. Do not re-litigate
earlier tasks; fix from what the run names.

- [ ] **Step 1: Check nothing else is competing for the CPU**

```powershell
Get-Process python -ErrorAction SilentlyContinue | Where-Object CPU -gt 300 | Select-Object Id, StartTime, CPU
```

A hit means a multi-hour walk-forward is live; wait rather than reading a
contended timing as a problem.

- [ ] **Step 2: Syntax pass**

```powershell
python -m py_compile bot.py admin_ui.py
python -c "import compileall,sys; sys.exit(0 if compileall.compile_dir('swingbot', quiet=2) else 1)"
```

- [ ] **Step 3: Python suite**

Run: `python scripts/dev/testrun.py full`
Expected: `VERDICT: PASS`, `0 failed`.

- [ ] **Step 4: Frontend suite**

Part 2's M10 edited `tokens.css`, so the SPA suite is in this plan's blast
radius too.

Run: `cd frontend && npx ng test --watch=false`
Expected: all files passed.

- [ ] **Step 5: Confirm the invariant by hand, once**

```bash
git grep -nE "discord\.Colou?r\." -- 'swingbot/**/*.py' | grep -v "swingbot/core/presentation"
```

Expected: **nothing**. This is the plan's actual deliverable, stated as one
command.

- [ ] **Step 6: Release**

Only after Steps 3–5 are green, and as its own commit (C9):

```bash
# VERSION.json: bot 1.4.3 -> 1.5.0, bot_updated to now (UTC, YYYY-MM-DD HH-MM-SS)
git add VERSION.json
git commit -m "release(bot): 1.5.0 -- the Discord message system"
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(bot): 1.5.0 -- the Discord message system"
```

The regeneration is not optional and the order matters: the generator walks
`git log` for `VERSION.json`, so running it before the bump commit records the
placeholder `"commit": "uncommitted", "subject": "working tree"` in the frozen
file. See `working-conventions.md`.
