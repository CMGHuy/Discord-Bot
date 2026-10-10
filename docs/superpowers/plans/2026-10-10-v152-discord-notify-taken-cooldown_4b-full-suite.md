# v152 part 4b: the full suites

**Spec:** [`docs/superpowers/specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md`](../specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md) § Testing ("One full suite, as the plan's final task"), § Complexity
**Index:** [`2026-10-10-v152-discord-notify-taken-cooldown_0-index.md`](2026-10-10-v152-discord-notify-taken-cooldown_0-index.md): Global Constraints, decisions, the task ledger and `## Parallelisation` live there. Part 4 overflowed the 1500-line cap after V152-19, so its last task lives here; ledger id, files and order are unchanged.

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

