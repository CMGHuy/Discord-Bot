# v148 Ops hardening, part 3b: earnings conversion (part 3 split only to stay under 1500 lines)

> **For agentic workers:** pull one task at a time (`grep -n "^### Task OH14:" -A 260 <this file>`), never this file whole.

**Spec:** `docs/superpowers/specs/2026-10-09-v148-ops-hardening-design.md` (§ O5 "Conversion — this spec's ratchet step")
**Index:** `docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md` — Global Constraints, Parallelisation and the task ledger are binding here and are not repeated.
**Bump:** ui patch · bot patch (applied at close-out, never by a task)
**Edge:** none (integrity)

`$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening`. Never `cd`; use absolute paths and `git -C $WT`.

Shared rules for every conversion in this part (index § Global Constraints, "Behaviour-preserving conversion"; the same rules as OH9 in part 2):
- `swallowed()` (OH6) calls the logger's own level method (`log.warning`, `log.error`, `log.debug`, …) with the site's message, args and `exc_info`, plus `extra={"swallowed_tag": tag}` and `stacklevel=2`. A test that patches `log.warning` or reads `caplog` still sees the same call.
- Each handler's single log call becomes one `swallowed(log, "<tag>", <exc>, <same message>, <same args>, level=..., exc_info=...)` call. Omit `level=` for WARNING (the default) and omit `exc_info=` when it was absent. `log.exception(m, *a)` becomes `level=logging.ERROR, exc_info=True`. Every other statement in the handler (`return`, `continue`, assignments) stays exactly where it is.
- A handler that logged nothing (`pass`, `continue`, `return None`) gains `swallowed(log, "<tag>", exc, level=logging.DEBUG)` as its first statement and keeps the rest. With no message, OH6 logs `"swallowed <tag>: <Type: message>"` at DEBUG.
- A handler without `as` gains `as exc`. A handler that already binds a name (`as e`, `as _ce`, `as _je`) keeps that name and passes it.
- A handler containing a `raise` anywhere (even nested) is not converted.
- **Helper-logged sites.** Four handlers log through a throttling helper rather than `log` directly: `lifecycle_embeds._warn_throttled` (OH11) and `spot_metals._note_failure` (OH13). The throttle is behaviour, so the helper call stays exactly as it is. The handler gains `swallowed(log, "<tag>", exc, level=logging.DEBUG)` as its first statement, so every failure is counted while the WARNING output stays throttled as before. This is the "logged nothing directly" rule applied to the handler's own body; it adds a statement, never a branch.
- Tags are final once written: OH15's ratchet asserts that tags are unique per `except` handler repo-wide, and OH20's panel shows them. Part 2 already owns every `scan.run_scan.*`, `scan.unrealized_pnl.*`, `scan.scan_replay.regimes`, `scan.run_bounded` and the other OH9 tags. Every tag below is new.
- The import is `from swingbot.core.infra.swallowed import swallowed`. `swallowed.py` is a leaf module (no `swingbot` imports), so adding it to a low-level module such as `ticker_directory.py` creates no import cycle.
- A conversion adds no branch, so every function's radon score is unchanged. Each task proves this with a before/after `radon cc` diff.
- If a narrow test fails, the conversion changed behaviour: re-check the site against the task's table (level, message, args, `exc_info`, what follows the log call). The only new output allowed is one DEBUG record at a site that logged nothing, or at a helper-logged site. If a test fails only because it asserts the absence of that DEBUG record, stop and report it to the controller; do not edit the test.

# Phase C — remaining conversions


### Task OH14: Earnings conversion

**Model:** sonnet — a mechanical one-for-one conversion of 6 handlers in two files; small, but each DEBUG message and its args must be carried over exactly.

**Files:**
- Modify: `swingbot/core/market/events.py` (5 handlers)
- Modify: `swingbot/core/market/earnings_history.py` (1 handler; adds `import logging` and `log`)

**Contract:** `earnings.*` tags as listed below, including `earnings.next_date` (spec § O5 names it). No function signature, return value or fallback changes. `events.py` already has `import logging` and `log = logging.getLogger(__name__)` (`:15`, `:28`).

| File:line (today) | Function | Tag | Level / `exc_info` |
|---|---|---|---|
| `events.py:63` | `get_next_earnings_date` (candidate loop) | `earnings.next_date` | DEBUG / — |
| `events.py:155` | `warm_earnings_cache_background._run` | `earnings.warmup` | DEBUG / True |
| `events.py:170` | `_fetch_next_earnings_datetime` (candidate loop) | `earnings.next_datetime` | DEBUG / — |
| `events.py:200` | `get_earnings_datetimes` (candidate loop) | `earnings.datetimes` | DEBUG / — |
| `events.py:254` | `earnings_snapshot` (candidate loop) | `earnings.snapshot` | DEBUG / — |
| `earnings_history.py:47` | `refresh_watchlist_earnings` (per-symbol future) | `earnings.history_refresh` | DEBUG / — (logged nothing; `continue` kept) |

- [ ] **Step 1: Record the before-state**

Save the scratch script (OH15's rule, the same as OH10 Step 1; not committed):

```bash
mkdir -p /tmp/claude-oh14 && cat > /tmp/claude-oh14/untagged.py <<'PY'
"""Untagged except-Exception handlers per file (OH15's rule)."""
import ast
import sys
from pathlib import Path


def _untagged(h):
    if not isinstance(h, ast.ExceptHandler) or h.type is None:
        return False
    names = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    if not any(isinstance(n, ast.Name) and n.id == "Exception" for n in names):
        return False
    nodes = list(ast.walk(h))
    calls = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "swallowed"
                for n in nodes)
    return not calls and not any(isinstance(n, ast.Raise) for n in nodes)


for name in sys.argv[1:]:
    lines = sorted(h.lineno for h in ast.walk(ast.parse(Path(name).read_text(encoding="utf-8")))
                   if _untagged(h))
    print(f"{name}: {len(lines)} untagged {lines}")
PY
K=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/market
python /tmp/claude-oh14/untagged.py $K/events.py $K/earnings_history.py
```

Expected: `events.py: 5 untagged`, `earnings_history.py: 1 untagged`. If a count differs, the file has drifted since the brief (2026-10-10): convert what the AST lists, keeping the same rules.

- [ ] **Step 2: Convert `events.py`**

Add `from swingbot.core.infra.swallowed import swallowed` before `from swingbot.core.marketdata.spot_metals import is_spot_metal` (`:23`).

`:63` (`get_next_earnings_date`):
```python
        except Exception as e:
            swallowed(log, "earnings.next_date", e, "Calendar fetch failed for %s: %s", candidate, e,
                      level=logging.DEBUG)
            continue
```

`:155` (`warm_earnings_cache_background`'s nested `_run`):
```python
                except Exception as exc:
                    swallowed(log, "earnings.warmup", exc,
                              "background earnings warm-up failed for %s", ticker,
                              level=logging.DEBUG, exc_info=True)
```

One listing for these sites; each `# :NNN` comment only names the site and is not written into the file:
```python
        # :170 (_fetch_next_earnings_datetime)
        except Exception as e:
            swallowed(log, "earnings.next_datetime", e, "Earnings-dates fetch failed for %s: %s",
                      candidate, e, level=logging.DEBUG)
            continue

        # :200 (get_earnings_datetimes)
        except Exception as exc:
            swallowed(log, "earnings.datetimes", exc, "Earnings-dates fetch failed for %s: %s",
                      candidate, exc, level=logging.DEBUG)
            continue

        # :254 (earnings_snapshot)
        except Exception as exc:
            swallowed(log, "earnings.snapshot", exc, "Earnings snapshot fetch failed for %s: %s",
                      candidate, exc, level=logging.DEBUG)
            continue
```

- [ ] **Step 3: Convert `earnings_history.py`**

The file has no logger. Make the import block (`:8-16`) read:

```python
from __future__ import annotations

import datetime as dt
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json, read_json
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market.events import get_earnings_datetimes

log = logging.getLogger(__name__)
```

followed by the two blank lines before `def _path()` that are there today. Then `refresh_watchlist_earnings`'s handler (`:47`):

```python
            try:
                dates = future.result()
            except Exception as exc:
                swallowed(log, "earnings.history_refresh", exc, level=logging.DEBUG)
                continue
```

`refresh_watchlist_earnings` runs from the bot's `weekly_earnings_refresh` loop, so the count reaches the heartbeat directly.

- [ ] **Step 4: Verify nothing is left untagged and the tags are unique**

```bash
K=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/market
python /tmp/claude-oh14/untagged.py $K/events.py $K/earnings_history.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening grep -hoE 'swallowed\((log|_?[a-z_]+), "[a-z_.]+"' -- swingbot | sed -E 's/.*"([a-z_.]+)"/\1/' | sort | uniq -d
```

Expected: `0 untagged []` for both files, and an empty `uniq -d` (or only `scan.run_bounded` once OH7 has landed).

Then prove converted sites still behave and now count, in a throwaway process that imports the worktree copy:

```bash
cd /tmp && python - <<'PY'
import sys, tempfile
sys.path.insert(0, "/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening")
from swingbot import config
from swingbot.core.infra import swallowed as sw
from swingbot.core.market import earnings_history, events
from swingbot.core.marketdata.ticker_utils import candidate_symbols

def boom(*a, **k):
    raise RuntimeError("probe")

events.yf.Ticker = boom
assert events.get_next_earnings_date("AAPL") is None
config.DATA_DIR = tempfile.mkdtemp()
earnings_history.get_earnings_datetimes = boom
earnings_history.refresh_watchlist_earnings(["AAPL"])
snap = sw.snapshot()
assert snap["earnings.next_date"]["count"] == len(candidate_symbols("AAPL")), snap
assert snap["earnings.history_refresh"]["last_error"] == "RuntimeError: probe", snap
print("OK", sorted(snap))
PY
```

Expected: `OK ['earnings.history_refresh', 'earnings.next_date']`. The script patches `yfinance.Ticker` and `config.DATA_DIR` inside a throwaway process only.

- [ ] **Step 5: Run the narrow tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/market/test_events.py
python $WT/scripts/dev/testrun.py file tests/market/test_events_spot.py
python $WT/scripts/dev/testrun.py file tests/market/test_earnings_history.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_compression_earnings_gate.py
python $WT/scripts/dev/testrun.py file tests/commands/test_scheduled_jobs.py
python $WT/scripts/dev/testrun.py changed
```

Expected: every run `0 failed`, `0 xfailed`. If `changed` escalates to the full suite, let it run.

- [ ] **Step 6: Complexity**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C $WT/swingbot/core/market/events.py $WT/swingbot/core/market/earnings_history.py > /tmp/claude-oh14/cc_after.txt
for f in events earnings_history; do git -C $WT show HEAD:swingbot/core/market/$f.py > /tmp/claude-oh14/$f.py; done
python -m radon cc -s -n C /tmp/claude-oh14/events.py /tmp/claude-oh14/earnings_history.py > /tmp/claude-oh14/cc_before.txt
norm() { sed -E 's#.*/##; s/ [0-9]+:[0-9]+ / /' "$1"; }   # basename only, line:col dropped (conversions shift lines)
diff <(norm /tmp/claude-oh14/cc_before.txt) <(norm /tmp/claude-oh14/cc_after.txt) && echo "complexity unchanged"
```

Expected: `complexity unchanged`. `refresh_watchlist_earnings` may be listed (its loop body is long); it is listed in both files with the same score.

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/core/market/events.py swingbot/core/market/earnings_history.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH14: count swallowed errors in earnings events and history"
```
