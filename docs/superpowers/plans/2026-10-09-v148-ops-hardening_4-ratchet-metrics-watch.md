# v148 Ops hardening, part 4: swallowed-error ratchet, provider metrics, ops notices (OH15–OH17)

> **For agentic workers:** pull one task at a time (`grep -n "^### Task OH16:" -A 320 <this file>`), never this file whole.

**Spec:** `docs/superpowers/specs/2026-10-09-v148-ops-hardening-design.md` (§ O3 "In-bot watchdog", § O4, § O5 "Ratchet test")
**Index:** `docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md` — Global Constraints, Parallelisation and the task ledger are binding here and are not repeated.
**Bump:** ui patch · bot patch (applied at close-out, never by a task)
**Edge:** none (integrity)

`$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening`. Never `cd`; use absolute paths and `git -C $WT`.

Order inside this part: OH15 first (its `BASELINE` is the count after OH9–OH14). OH16 can run beside OH15, because the two touch disjoint files. OH17 needs OH5 and OH8. OH18 (watchdog loop and wiring, needs OH16 and OH17) moved to part 4b (`_4b-watchdog-wiring.md`) only to keep each file under 1500 lines. Every handler this part adds calls `swallowed()` with a new unique tag (`scan.provider_health`, `ops.scan_watchdog`, `ops.provider_health`), so none of them moves OH15's `BASELINE`.

# Phase D — ratchet, provider metrics, ops notices, watchdog

### Task OH15: Swallowed-error ratchet

**Model:** sonnet — one self-contained AST test with a measured constant; the rule is fully specified and touches no production code.

**Files:**
- Create: `tests/infra/test_swallowed_ratchet.py`

**Contract (ledger, final):** `SCOPES: tuple[str, ...]`, `EXCLUDED: dict[str, str]`, `BASELINE: int` (measured in Step 3), `untagged_handlers(path: Path) -> list[int]`. Nothing in production imports this file. Part 5's tasks (OH20 `ops_health.py`) must keep it green. Any handler they add calls `swallowed()` with a new unique tag, or the count assertion fails.

What the test pins (spec § O5 "Ratchet test", index § Global Constraints "Tags"):
- **Untagged** means the handler catches `Exception`, alone or in a tuple, its body calls no `swallowed`, and it contains no `raise` at any depth. This is the rule OH9 Step 1's scratch script uses. A bare `except:` and `except BaseException:` are not counted, because the spec counts `except Exception` only.
- **Scopes**: `swingbot/core/scanning/*.py` (flat, 36 files; it includes the unrelated `swingbot/core/scanning/runstate.py`, which has no handlers), `swingbot/core/marketdata/**/*.py`, `events.py`, `earnings_history.py` and `swingbot/commands/scanning/runstate.py`. `ops_watch.py` (OH17/OH18) is not a v148 scope, but its handlers are tagged anyway.
- **Repo-wide set**: `swingbot/**/*.py` plus `bot.py`, `admin_ui.py` and `admin_wsgi.py` (OH2). A missing root file fails one readable test and is skipped by the others.
- **Tag uniqueness is per `except` handler, not per call.** `fetch._run_bounded` (OH7) calls `swallowed(log, "scan.run_bounded", ...)` twice: once in its child-raised handler, and once on the timeout path, which is not a handler. A repo-wide count of `swallowed(` literals would flag that call as a duplicate, which would be wrong. A handler's own calls exclude those inside a handler nested in it, so a nested handler's tag is attributed once.
- **Tag shape**: `^(scan|marketdata|earnings|runstate|ops)\.[a-z0-9_]+(\.[a-z0-9_]+)*$`, string literal, second positional argument. This is checked on every `swallowed()` call, inside a handler or not.
- **Count message**: a higher count says "never raise BASELINE", and a lower one says "lower BASELINE to N". Both name the measured figure.

Before-state measured on `main` on 2026-10-10, with the same functions and no conversion yet: 327 untagged repo-wide, of which 107 are in the scopes (scan 65, marketdata 34, earnings 6, runstate 2). The expected post-conversion figure is therefore **220**. That is only an expectation. Step 3 measures the real figure, and that measurement is what gets committed.

- [ ] **Step 0: Confirm every conversion has landed and read any exclusion**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
git -C $WT log --oneline | grep -E "v148 OH(2|7|8|9|10|11|12|13|14)[: ]"
grep -n "EXCLUDED" /home/user/Discord-Bot/docs/superpowers/plans/2026-10-09-v148-ops-hardening_3-conversion.md || echo "no exclusions named"
test -f $WT/admin_wsgi.py && echo "admin_wsgi present"
```

Expected: nine commit lines, one each for OH2 and OH7–OH14, then `no exclusions named` and `admin_wsgi present`. If a conversion commit is missing, stop: `BASELINE` would be measured too high. If part 3 names an exclusion (a scope file left unconverted, with its reason), copy each `path: reason` into `EXCLUDED` in Step 1. The path is repo-relative and POSIX.

- [ ] **Step 1: Write the test**

Create `$WT/tests/infra/test_swallowed_ratchet.py`:

```python
"""v148 O5: the swallowed-error ratchet.

An ``except`` handler is *untagged* when it catches ``Exception`` (alone or in
a tuple), its body calls no ``swallowed()``, and it contains no ``raise``.
Three rules, all AST-based so comments and strings never count:

1. No untagged handler in the converted scopes (``SCOPES``), except a file
   named in ``EXCLUDED`` with its reason.
2. Repo-wide (``swingbot/**/*.py`` plus the root entry points) the untagged
   count equals ``BASELINE``. It can only fall: a lower count fails with
   "lower BASELINE to N", so the next person cannot quietly spend the slack.
3. Every ``swallowed()`` tag is a string literal ``<area>.<function>`` and no
   two ``except`` handlers share one. A tag may appear again outside any
   handler: ``fetch._run_bounded`` counts its timeout path, which is not a
   handler, under the same ``scan.run_bounded`` as its child-raised handler.
"""
from __future__ import annotations

import ast
import re
import textwrap
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: The scopes v148 converted; every handler in them is tagged.
SCOPES: tuple[str, ...] = (
    "swingbot/core/scanning/*.py",
    "swingbot/core/marketdata/**/*.py",
    "swingbot/core/market/events.py",
    "swingbot/core/market/earnings_history.py",
    "swingbot/commands/scanning/runstate.py",
)

#: Scope files deliberately left unconverted, path -> reason. Their untagged
#: handlers are counted in BASELINE, never silently exempted.
EXCLUDED: dict[str, str] = {}

ROOT_FILES: tuple[str, ...] = ("bot.py", "admin_ui.py", "admin_wsgi.py")

#: Repo-wide untagged handlers, measured after the v148 conversion (OH15).
BASELINE: int = 220

TAG_RE = re.compile(r"^(scan|marketdata|earnings|runstate|ops)\.[a-z0-9_]+(\.[a-z0-9_]+)*$")


def _catches_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return False
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(n, ast.Name) and n.id == "Exception" for n in names)


def _is_swallowed_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "swallowed")


def _is_untagged(handler: ast.ExceptHandler) -> bool:
    if not _catches_exception(handler):
        return False
    nodes = list(ast.walk(handler))
    return not any(_is_swallowed_call(n) for n in nodes) and not any(
        isinstance(n, ast.Raise) for n in nodes)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def untagged_handlers(path: Path) -> list[int]:
    """Line numbers of the untagged handlers in one file."""
    return sorted(h.lineno for h in ast.walk(_tree(path))
                  if isinstance(h, ast.ExceptHandler) and _is_untagged(h))


def _own_calls(handler: ast.ExceptHandler) -> list[ast.Call]:
    """The swallowed() calls of this handler, not of a handler nested in it."""
    calls, stack = [], list(ast.iter_child_nodes(handler))
    while stack:
        node = stack.pop()
        if isinstance(node, ast.ExceptHandler):
            continue
        if _is_swallowed_call(node):
            calls.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return calls


def _tag(call: ast.Call) -> str | None:
    if len(call.args) < 2:
        return None
    arg = call.args[1]
    return arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None


def handler_tags(path: Path) -> list[tuple[int, str]]:
    """(handler line, tag) once per distinct tag per handler."""
    pairs = []
    for handler in ast.walk(_tree(path)):
        if isinstance(handler, ast.ExceptHandler):
            tags = {_tag(call) for call in _own_calls(handler)}
            pairs += [(handler.lineno, tag) for tag in sorted(tags, key=str)]
    return pairs


def bad_tags(path: Path) -> list[tuple[int, object]]:
    """Every swallowed() call in the file whose tag is not a valid literal."""
    found = []
    for node in ast.walk(_tree(path)):
        if _is_swallowed_call(node):
            tag = _tag(node)
            if tag is None or not TAG_RE.match(tag):
                found.append((node.lineno, tag))
    return found


def duplicate_tags(paths: list[Path]) -> dict[str, list[str]]:
    sites = defaultdict(list)
    for path in paths:
        for line, tag in handler_tags(path):
            sites[tag].append(f"{path.relative_to(REPO).as_posix()}:{line}")
    return {tag: where for tag, where in sites.items() if len(where) > 1}


def _repo_files() -> list[Path]:
    """``test_every_scope_and_root_file_exists`` asserts the root files exist;
    skipping a missing one here keeps that the single, readable failure."""
    roots = [REPO / name for name in ROOT_FILES if (REPO / name).is_file()]
    return sorted(REPO.glob("swingbot/**/*.py")) + roots


def _scope_files() -> list[Path]:
    return sorted({path for pattern in SCOPES for path in REPO.glob(pattern)})


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


# --- the rule itself, on a sample -------------------------------------------

_SAMPLE = textwrap.dedent('''\
    def f(log):
        try:
            pass
        except Exception:
            pass
        try:
            pass
        except (ValueError, Exception) as exc:
            log.warning("x")
        try:
            pass
        except Exception as exc:
            swallowed(log, "scan.f", exc)
        try:
            pass
        except Exception:
            raise
        try:
            pass
        except ValueError:
            pass
        try:
            pass
        except:
            pass
        try:
            pass
        except BaseException:
            pass
    ''')


def test_the_untagged_rule_on_a_sample(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(_SAMPLE, encoding="utf-8")
    assert untagged_handlers(sample) == [4, 8]


def test_a_nested_handler_tag_belongs_to_the_inner_handler_only(tmp_path):
    sample = tmp_path / "nested.py"
    sample.write_text(textwrap.dedent('''\
        def g(log):
            try:
                pass
            except Exception as exc:
                swallowed(log, "scan.outer", exc)
                try:
                    pass
                except Exception as inner:
                    swallowed(log, "scan.inner", inner)
        '''), encoding="utf-8")
    assert handler_tags(sample) == [(4, "scan.outer"), (8, "scan.inner")]


def test_a_tag_reused_outside_any_handler_is_not_a_duplicate(tmp_path):
    """fetch._run_bounded's shape: one handler, one timeout path, one tag."""
    sample = tmp_path / "bounded.py"
    sample.write_text(textwrap.dedent('''\
        def run(log):
            try:
                pass
            except Exception as exc:
                swallowed(log, "scan.run_bounded", exc)
            swallowed(log, "scan.run_bounded", TimeoutError("x"))
        '''), encoding="utf-8")
    assert handler_tags(sample) == [(4, "scan.run_bounded")]


def test_bad_tags_are_found(tmp_path):
    sample = tmp_path / "bad.py"
    sample.write_text(textwrap.dedent('''\
        def h(log, name):
            swallowed(log, name, ValueError())
            swallowed(log, "Scan.Bad", ValueError())
            swallowed(log, "nope.area", ValueError())
            swallowed(log, "scan.ok", ValueError())
        '''), encoding="utf-8")
    assert bad_tags(sample) == [(2, None), (3, "Scan.Bad"), (4, "nope.area")]


# --- the ratchet on the repo --------------------------------------------------

def test_every_scope_and_root_file_exists():
    assert all(list(REPO.glob(pattern)) for pattern in SCOPES), SCOPES
    assert all((REPO / name).is_file() for name in ROOT_FILES), ROOT_FILES


def test_excluded_paths_are_in_scope_and_carry_a_reason():
    in_scope = {_rel(path) for path in _scope_files()}
    for path, reason in EXCLUDED.items():
        assert path in in_scope, f"EXCLUDED names {path}, which is not in SCOPES"
        assert reason.strip(), f"EXCLUDED[{path!r}] needs its reason"


def test_no_untagged_handler_in_the_converted_scopes():
    found = {_rel(path): untagged_handlers(path) for path in _scope_files()
             if _rel(path) not in EXCLUDED}
    found = {path: lines for path, lines in found.items() if lines}
    assert found == {}, (
        "untagged `except Exception` in a v148 scope -- call swallowed(log, '<area>.<function>', "
        f"exc, <same message>, level=<same level>) instead (spec O5): {found}")


def test_the_repo_wide_untagged_count_only_falls():
    count = sum(len(untagged_handlers(path)) for path in _repo_files())
    assert count <= BASELINE, (
        f"{count} untagged `except Exception` handlers, BASELINE is {BASELINE}: a new swallow "
        "must call swallowed(log, '<area>.<function>', exc, ...) -- never raise BASELINE")
    assert count == BASELINE, f"the untagged count fell to {count}: lower BASELINE to {count}"


def test_every_tag_is_a_valid_literal():
    found = {_rel(path): bad for path in _repo_files() if (bad := bad_tags(path))}
    assert found == {}, (
        "swallowed() tags are string literals '<area>.<function>' with area one of "
        f"scan, marketdata, earnings, runstate, ops: {found}")


def test_no_two_handlers_share_a_tag():
    assert duplicate_tags(_repo_files()) == {}, (
        "each except handler needs its own tag -- add a suffix naming what failed "
        "(scan.run_scan.telemetry)")
```

- [ ] **Step 2: Run it**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
```

Expected: `10 passed`. Two failures are possible, and each one stops the task until it is fixed:
- `test_no_untagged_handler_in_the_converted_scopes` names `path: [lines]`. A conversion task missed a site. Convert it in that file by the index's rules: same logger, level, message and `exc_info`, plus a unique tag. Commit that fix separately (`v148 OH15: convert <file>:<line> missed by OH<n>`), then re-run. Never add the file to `EXCLUDED` to make the test pass. `EXCLUDED` holds only what part 3 named in Step 0.
- `test_no_two_handlers_share_a_tag` or `test_every_tag_is_a_valid_literal` names the sites. Rename the later tag with a suffix naming what failed. The tags in OH9's table and in part 3's tables are final, so if one of those is the duplicate, rename the other one.

- [ ] **Step 3: Measure and pin `BASELINE`**

**Cross-plan (audit 2026-10-10):** Rebase onto `main` immediately before measuring (`git -C $WT rebase main`, then re-run Step 2). A difference from 220 may come from handlers other plans merged since this plan was written (v146, v147, v152 …): tag each new one per the index's § Cross-plan coordination swallowed-error ratchet rule (its own commit, `v148 OH15: tag <file>:<line> merged by vNNN`) rather than raising `BASELINE`. If a plan merges to `main` between this measurement and the v148 merge, re-run the ratchet on the merge result and tag its new handlers the same way.

If `test_the_repo_wide_untagged_count_only_falls` passed in Step 2, the measured count is 220 and the constant stands. If it failed, its message names the measured count N ("... handlers, BASELINE is 220" or "lower BASELINE to N"). Before writing N, account for the difference from 220:

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python - <<'PY'
import sys
sys.path.insert(0, "/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening")
from tests.infra import test_swallowed_ratchet as r
rows = [(r._rel(p), len(r.untagged_handlers(p))) for p in r._repo_files()]
print("total", sum(n for _, n in rows))
for path, n in rows:
    if n and (path.startswith("swingbot/admin/") or path in r.ROOT_FILES):
        print(path, n)
PY
git -C $WT diff --stat main -- 'swingbot/*.py' bot.py admin_ui.py admin_wsgi.py | tail -3
```

The total is N. A difference from 220 has to be explained by a handler that a v148 task added or removed outside the scopes (another plan's merged handlers were tagged above, so they no longer count). The admin lines printed above show where Phase A put any such handler. Set `BASELINE: int = N` in the file, and put the explanation in the commit message. A difference that cannot be explained means a conversion was incomplete. In that case go back to Step 2's first bullet, never raise the constant to cover it.

Re-run Step 2's command. Expected: `10 passed`.

- [ ] **Step 4: Prove the ratchet bites (scratch, reverted)**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
printf '\n\ndef _ratchet_probe():\n    try:\n        pass\n    except Exception:\n        pass\n' >> $WT/swingbot/core/scanning/telemetry.py
python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
git -C $WT checkout -- swingbot/core/scanning/telemetry.py
python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
```

Expected: the first run has `2 failed`: the scope assertion names `swingbot/core/scanning/telemetry.py`, and the count assertion says "never raise BASELINE". After the checkout, the second run shows `10 passed`. `git -C $WT status --short` then shows only the new test file.

- [ ] **Step 5: Complexity**

```bash
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/tests/infra/test_swallowed_ratchet.py
```

Expected: no output.

- [ ] **Step 6: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add tests/infra/test_swallowed_ratchet.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH15: swallowed-error ratchet -- scopes fully tagged, repo-wide BASELINE can only fall, one tag per handler"
```

### Task OH16: Provider degradation metrics

**Model:** opus — it adds fields to the scan's telemetry row inside `_sync_run_scan` (legacy, well above complexity 15) and moves the Risk page's formula, where a timezone or calendar slip silently mislabels the whole universe as stale.

**Files:**
- Modify: `swingbot/core/scanning/telemetry.py` (imports at the top; new section at the end)
- Modify: `swingbot/core/scanning/scan_run.py` (one import; `_provider_health_fields` after `_count_sources` `:56-65`; one line in the telemetry `try:` at `:1144-1160`)
- Modify: `swingbot/admin/api_v1/risk.py` (`_data_sources_summary`, `:82-103`)
- Create: `tests/scanning/test_provider_health.py`

**Contract (ledger, final):** `telemetry.fallback_rate(source_counts: list[dict]) -> float | None`; `telemetry.provider_health(tickers: list, frames: dict, data_sources: dict, price_sources: dict, today: dt.date) -> dict` with exactly the keys `provider_fallback_rate: float | None` (rounded to 4), `empty_symbols: int`, `empty_rate: float | None` (rounded to 4), `stale_symbols: int | None`. Every scan's telemetry row (`data/scan_telemetry.jsonl`) gains those four keys. OH17's `provider_verdict`, OH18's `check_provider_health` and OH20's `/system/health` read them under these names. `None` means "cannot say", never zero.

Facts this rests on (brief § 3 "scan_run.py:1135-1160", § 6; index § Global Constraints "Market dates are ET"):
- `fresh_data` is the scan's ticker → frame dict, and its values may be `None` (`_count_sources` guards that). The row's existing `errors` field is `len(tickers) - len(fresh_data)`, which counts missing keys only. `empty_symbols` counts per ticker, covering missing, `None` and empty frames, and `errors` stays as it is.
- `scan_stats["data_sources"]` comes from `_count_sources(fresh_data)`. `scan_stats["price_sources"]` comes from `**fetch.fetch_stats()`. Both are already in the dict when the new line runs, so the helper reads them from `scan_stats` and counts nothing twice.
- **The helper has its own guard.** `provider_health` runs inside the telemetry `try:`. If it raised there, the whole row would be lost: duration, slowdown and every other field. `_provider_health_fields` therefore catches its own failure under the new tag `scan.provider_health` (WARNING, `exc_info=True`) and returns `{}`. `_sync_run_scan` gains one `scan_stats.update(...)` line and no branch. The tag is unique and the handler is tagged, so OH15's ratchet stays green with `BASELINE` unchanged.
- `market_today()` (`swingbot/core/market/session.py:115`) is the ET date. `nyse_calendar().sessions(start, end)` (`:169`, `:219`) returns `[]` outside the frozen 2018–2030 table, and `_previous_session` returns `None` then. A tz-aware last bar is converted to `America/New_York` before `.date()`. A naive one is already a market date (daily bars).
- `risk._data_sources_summary` keeps its output exactly: `round(misses / (hits + misses), 4)` or `None`. The existing `tests/admin/test_api_v1_risk.py::test_scan_health_summarises_data_sources`, `::test_fallback_rate_pools_daily_frames_and_live_prices` and `::test_data_sources_fallback_rate_is_null_without_alpaca_traffic` pin the pooled figure on fixtures and must pass unchanged.
- The new telemetry fields are additive jsonl keys. Old rows lack them and readers treat that as `null` (index § Global Constraints, "Schema"). No migration is needed.

- [ ] **Step 0: Confirm OH9 has landed**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
git -C $WT log --oneline | grep -E "v148 OH(6|9)[: ]"
grep -n "from swingbot.core.infra.swallowed import swallowed\|scan.run_scan.telemetry\|def _count_sources\|telemetry.log_scan_telemetry(scan_stats)" $WT/swingbot/core/scanning/scan_run.py
```

Expected: the OH6 and OH9 commit lines, plus four `scan_run.py` hits: the import (OH9), `_count_sources`, the `log_scan_telemetry` call, and the converted handler tag.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/scanning/test_provider_health.py`:

```python
"""v148 O4: per-scan provider degradation metrics -- the fallback rate (one
formula, shared with the Risk page), empty symbols, and stale frames against
the previous NYSE session."""
import datetime as dt
import json
import logging

import pandas as pd
import pytest

from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.scanning import telemetry
from swingbot.core.scanning.telemetry import fallback_rate, provider_health

#: Monday 2026-01-19 (Martin Luther King Jr. Day) is an NYSE holiday, so the
#: session before Tuesday the 20th is Friday the 16th.
TUESDAY_AFTER_HOLIDAY = dt.date(2026, 1, 20)

NO_ALPACA = {"alpaca": 0, "yfinance": 4, "yfinance-fallback": 0, "cache": 0}
NO_PRICES = {"alpaca": 0, "yfinance": 0, "yfinance-fallback": 0, "none": 4}


def _frame(*stamps, tz=None):
    index = pd.DatetimeIndex([pd.Timestamp(s) for s in stamps])
    if tz:
        index = index.tz_localize(tz)
    return pd.DataFrame({"Close": [1.0] * len(index)}, index=index)


def _health(frames, tickers=None, data_sources=NO_ALPACA, price_sources=NO_PRICES,
            today=TUESDAY_AFTER_HOLIDAY):
    tickers = list(frames) if tickers is None else tickers
    return provider_health(tickers, frames, data_sources, price_sources, today)


# --- fallback_rate --------------------------------------------------------------

def test_fallback_rate_pools_every_count_dict():
    counts = [{"alpaca": 3, "yfinance-fallback": 1}, {"alpaca": 4, "yfinance-fallback": 2}]
    assert fallback_rate(counts) == pytest.approx(0.3)


def test_fallback_rate_reads_a_missing_bucket_as_zero():
    assert fallback_rate([{"yfinance-fallback": 1}, {"alpaca": 3}]) == pytest.approx(0.25)


def test_fallback_rate_is_none_when_alpaca_was_asked_for_nothing():
    assert fallback_rate([NO_ALPACA, NO_PRICES]) is None
    assert fallback_rate([]) is None


# --- provider_health: rates -------------------------------------------------------

def test_the_scan_rate_pools_daily_frames_and_live_prices():
    """The Risk page's own fixture (test_api_v1_risk.py), one scan: 6 / 80."""
    health = _health({"A": _frame("2026-01-16")},
                     data_sources={"alpaca": 2, "yfinance": 0, "yfinance-fallback": 0, "cache": 70},
                     price_sources={"alpaca": 72, "yfinance": 2, "yfinance-fallback": 6, "none": 0})
    assert health["provider_fallback_rate"] == 0.075


def test_the_scan_rate_is_none_without_alpaca():
    assert _health({"A": _frame("2026-01-16")})["provider_fallback_rate"] is None


def test_a_missing_price_sources_dict_is_tolerated():
    health = _health({"A": _frame("2026-01-16")},
                     data_sources={"alpaca": 1, "yfinance-fallback": 1}, price_sources=None)
    assert health["provider_fallback_rate"] == 0.5


def test_empty_symbols_count_missing_none_and_empty_frames():
    frames = {"A": _frame("2026-01-16"), "B": None, "C": pd.DataFrame()}
    health = _health(frames, tickers=["A", "B", "C", "D"])
    assert health["empty_symbols"] == 3
    assert health["empty_rate"] == 0.75


def test_an_empty_universe_has_no_empty_rate():
    health = _health({}, tickers=[])
    assert health == {"provider_fallback_rate": None, "empty_symbols": 0,
                      "empty_rate": None, "stale_symbols": 0}


# --- provider_health: stale frames ------------------------------------------------

def test_the_day_after_a_holiday_flags_nothing():
    frames = {t: _frame("2026-01-15", "2026-01-16") for t in ("A", "B", "C")}
    assert _health(frames)["stale_symbols"] == 0


def test_a_frame_ending_before_the_previous_session_is_stale():
    frames = {"FRESH": _frame("2026-01-16"), "TODAY": _frame("2026-01-20"),
              "OLD": _frame("2026-01-14", "2026-01-15")}
    assert _health(frames)["stale_symbols"] == 1


def test_a_tz_aware_index_is_read_in_new_york():
    """03:00 UTC on the 16th is 22:00 ET on the 15th: stale. 21:00 UTC on the
    16th is 16:00 ET on the 16th: fresh."""
    frames = {"LATE": _frame("2026-01-16 21:00", tz="UTC"),
              "EARLY": _frame("2026-01-16 03:00", tz="UTC")}
    assert _health(frames)["stale_symbols"] == 1


def test_a_naive_index_is_taken_as_market_dates():
    frames = {"A": _frame("2026-01-16 00:00"), "B": _frame("2026-01-15 23:59")}
    assert _health(frames)["stale_symbols"] == 1


def test_empty_frames_and_non_datetime_indexes_are_never_stale():
    frames = {"NONE": None, "EMPTY": pd.DataFrame(), "RANGE": pd.DataFrame({"Close": [1.0]})}
    assert _health(frames)["stale_symbols"] == 0


def test_outside_the_frozen_calendar_stale_is_unknown():
    health = _health({"A": _frame("2031-05-30")}, today=dt.date(2031, 6, 2))
    assert health["stale_symbols"] is None


def test_the_fields_are_json_ready():
    frames = {"A": _frame("2026-01-16"), "B": None}
    health = _health(frames, data_sources={"alpaca": 1, "yfinance-fallback": 0})
    assert set(health) == {"provider_fallback_rate", "empty_symbols", "empty_rate", "stale_symbols"}
    assert json.loads(json.dumps(health)) == health


# --- the scan row ---------------------------------------------------------------

@pytest.fixture
def clean_counts():
    swallowed_mod.reset()
    yield
    swallowed_mod.reset()


def test_the_scan_row_helper_returns_the_four_fields(monkeypatch):
    from swingbot.core.scanning import scan_run
    monkeypatch.setattr(scan_run, "market_today", lambda: TUESDAY_AFTER_HOLIDAY)
    stats = {"data_sources": {"alpaca": 3, "yfinance-fallback": 1}, "price_sources": {"alpaca": 0}}
    fields = scan_run._provider_health_fields(["A", "B"], {"A": _frame("2026-01-16")}, stats)
    assert fields == {"provider_fallback_rate": 0.25, "empty_symbols": 1,
                      "empty_rate": 0.5, "stale_symbols": 0}


def test_a_failing_metric_costs_its_fields_not_the_row(monkeypatch, caplog, clean_counts):
    from swingbot.core.scanning import scan_run

    def boom(*args, **kwargs):
        raise ValueError("bad frame")

    monkeypatch.setattr(telemetry, "provider_health", boom)
    with caplog.at_level(logging.WARNING, logger=scan_run.log.name):
        assert scan_run._provider_health_fields(["A"], {}, {}) == {}
    assert swallowed_mod.snapshot()["scan.provider_health"]["count"] == 1
    assert "provider health metrics failed" in caplog.text


def test_the_scan_merges_the_fields_into_its_telemetry_row():
    import inspect
    from swingbot.core.scanning import scan_run
    source = inspect.getsource(scan_run._sync_run_scan)
    assert "scan_stats.update(_provider_health_fields(tickers, fresh_data, scan_stats))" in source
```

- [ ] **Step 2: Run them to watch them fail**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_provider_health.py
```

Expected: collection error, `ImportError: cannot import name 'fallback_rate' from 'swingbot.core.scanning.telemetry'`.

- [ ] **Step 3: Add the metrics to `telemetry.py`**

In `$WT/swingbot/core/scanning/telemetry.py`, replace the module docstring and import block (lines 1-5, `"""Append-only scan telemetry and slowdown detection."""` … `from swingbot import config`) with:

```python
"""Append-only scan telemetry, slowdown detection and provider health."""
import datetime as dt
import json as _json
import os

import pandas as pd

from swingbot import config
from swingbot.core.market.session import nyse_calendar
```

`swingbot.core.market.session` imports only the standard library and `swingbot.config`, so the new import closes no cycle. `log_scan_telemetry`'s own local `import datetime as dt` stays as it is, because it is harmless and out of scope.

Append at the end of the file:

```python
# --- v148 O4: provider degradation metrics ------------------------------------

_MARKET_TZ = "America/New_York"


def fallback_rate(source_counts: list[dict]) -> float | None:
    """yfinance-fallback over everything Alpaca was asked for (hits + misses),
    pooled across `source_counts` -- daily-frame and live-price count dicts
    alike. None when Alpaca was asked for nothing (disabled, or its breaker
    open throughout). The one formula behind each scan's
    ``provider_fallback_rate`` and the Risk page's pooled rate (v106)."""
    hits = sum(int(d.get("alpaca", 0)) for d in source_counts)
    misses = sum(int(d.get("yfinance-fallback", 0)) for d in source_counts)
    return misses / (hits + misses) if hits + misses else None


def _is_empty(df) -> bool:
    return df is None or df.empty


def _previous_session(today: dt.date) -> dt.date | None:
    """The last NYSE session before `today` -- not BDay, which would flag the
    whole universe the day after a holiday. None outside the frozen calendar."""
    sessions = nyse_calendar().sessions(today - dt.timedelta(days=14),
                                        today - dt.timedelta(days=1))
    return sessions[-1] if sessions else None


def _last_bar_date(df) -> dt.date | None:
    """The last bar's market date: tz-aware -> New York; naive is taken as a
    market date already. None for a frame without a DatetimeIndex."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return None
    last = df.index[-1]
    if last.tzinfo is not None:
        last = last.tz_convert(_MARKET_TZ)
    return last.date()


def _is_stale(df, previous: dt.date) -> bool:
    if _is_empty(df):
        return False
    last = _last_bar_date(df)
    return last is not None and last < previous


def _stale_count(tickers: list, frames: dict, today: dt.date) -> int | None:
    previous = _previous_session(today)
    if previous is None:
        return None
    return sum(1 for ticker in tickers if _is_stale(frames.get(ticker), previous))


def provider_health(tickers: list, frames: dict, data_sources: dict | None,
                    price_sources: dict | None, today: dt.date) -> dict:
    """v148 O4: one scan's provider degradation, four telemetry-row fields.

    `today` is the ET market date (``market_today()``), never
    ``date.today()``. `frames` is the scan's ticker -> frame dict, whose
    values may be None.

    - ``provider_fallback_rate``: :func:`fallback_rate` over this scan's
      `data_sources` + `price_sources`. Blind to a price chunk whose child was
      killed on timeout (it lands in the ``none`` bucket); that shows as the
      ``scan.run_bounded`` swallowed count instead.
    - ``empty_symbols`` / ``empty_rate``: tickers with no frame or an empty one.
    - ``stale_symbols``: frames whose last bar predates the previous NYSE
      session; None when the calendar cannot say. Display only -- no
      threshold is measured yet.
    """
    rate = fallback_rate([d for d in (data_sources, price_sources) if isinstance(d, dict)])
    empty = sum(1 for ticker in tickers if _is_empty(frames.get(ticker)))
    return {
        "provider_fallback_rate": None if rate is None else round(rate, 4),
        "empty_symbols": empty,
        "empty_rate": round(empty / len(tickers), 4) if tickers else None,
        "stale_symbols": _stale_count(tickers, frames, today),
    }
```

- [ ] **Step 4: Wire the row in `scan_run.py`**

In `$WT/swingbot/core/scanning/scan_run.py`:

1. After `from swingbot.core.market.reversal import evaluate_reversal, reversals_for_ticker` (`:27`), add:

```python
from swingbot.core.market.session import market_today
```

2. Directly after `_count_sources` (it ends with `return counts`, `:65`), add:

```python
def _provider_health_fields(tickers: list, frames: dict, stats: dict) -> dict:
    """v148 O4: the four provider-degradation fields for this scan's telemetry
    row, from the source counts already in `stats`. Guarded here, not by the
    row's own try: a failure costs these four fields, never the row."""
    try:
        return telemetry.provider_health(tickers, frames, stats.get("data_sources"),
                                         stats.get("price_sources"), market_today())
    except Exception as exc:
        swallowed(log, "scan.provider_health", exc, "provider health metrics failed",
                  exc_info=True)
        return {}
```

3. In `_sync_run_scan`'s telemetry `try:` (`:1144`), between the closing `}` of `scan_stats = {...}` (the line after `**fetch.fetch_stats(),`) and `telemetry.log_scan_telemetry(scan_stats)`, insert one line at the same indent as `telemetry.log_scan_telemetry`:

```python
        scan_stats.update(_provider_health_fields(tickers, fresh_data, scan_stats))
```

The block now reads:

```python
            "short_funnel": funnel.snapshot(),
            **fetch.fetch_stats(),
        }
        scan_stats.update(_provider_health_fields(tickers, fresh_data, scan_stats))
        telemetry.log_scan_telemetry(scan_stats)
```

Nothing else in `_sync_run_scan` changes. `tickers` is the scan's list (`tickers = _scan_tickers()`, `:373`), and `fresh_data` is the crawl's dict (`:393`).

- [ ] **Step 5: One formula in `risk.py`**

In `$WT/swingbot/admin/api_v1/risk.py` `_data_sources_summary`:

1. Add one sentence to the end of the docstring's first paragraph (after `None when none of them asked Alpaca for anything.`): `The formula is telemetry.fallback_rate, shared with each scan's provider_fallback_rate (v148 O4).`
2. Below `from swingbot.core.marketdata.providers import router`, add `from swingbot.core.scanning.telemetry import fallback_rate`. This is a lazy import, the same way this module already reaches `swingbot.core.scanning.engine` at `:121`.
3. Replace

```python
    hits = sum(int(d.get("alpaca", 0)) for d in counts)
    misses = sum(int(d.get("yfinance-fallback", 0)) for d in counts)
```

with

```python
    rate = fallback_rate(counts)
```

and in the returned dict replace `"fallback_rate": round(misses / (hits + misses), 4) if hits + misses else None,` with `"fallback_rate": None if rate is None else round(rate, 4),`.

`fallback_rate` sums `int(d.get("alpaca", 0))` and `int(d.get("yfinance-fallback", 0))` over the same list, exactly as the removed lines did, so the output is identical.

- [ ] **Step 6: Run the tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/scanning/test_provider_health.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_scan_telemetry_sources.py
python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
python $WT/scripts/dev/testrun.py changed
```

Expected: `test_provider_health.py` `18 passed`. Every run shows `0 failed`, `0 xfailed`. The three Risk fallback-rate tests pass unchanged, which proves the pooled figure did not move. The ratchet passes with `BASELINE` unchanged, because the new handler is tagged and `scan.provider_health` is a new tag. `changed` widens to every test reaching `scan_run.py`. If it escalates to the full suite, let it run.

- [ ] **Step 7: Complexity**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C $WT/swingbot/core/scanning/telemetry.py $WT/swingbot/admin/api_v1/risk.py
python -m radon cc -s $WT/swingbot/core/scanning/scan_run.py | grep -E "_sync_run_scan|_provider_health_fields"
git -C $WT show HEAD:swingbot/core/scanning/scan_run.py > /tmp/claude-oh16-scan_run.py
python -m radon cc -s /tmp/claude-oh16-scan_run.py | grep -E "_sync_run_scan"
```

Expected: the first command prints nothing, or only a function already listed at `HEAD`. `_provider_health_fields` is grade A, and `_sync_run_scan` has the same score before and after: the added line is a call, not a branch.

- [ ] **Step 8: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/core/scanning/telemetry.py swingbot/core/scanning/scan_run.py swingbot/admin/api_v1/risk.py tests/scanning/test_provider_health.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH16: per-scan provider fallback, empty and stale symbol metrics; one fallback-rate formula for scan and Risk page"
```

### Task OH17: Ops notices and pure verdicts

**Model:** sonnet — two pure truth tables and four embed builders in an established pattern; no I/O, no wiring.

**Files:**
- Modify: `swingbot/commands/scanning/notices.py` (append a section at the end)
- Create: `swingbot/commands/scanning/ops_watch.py`
- Create: `tests/scanning/test_ops_watch.py`

**Contract (ledger, final):** `notices.stale_scan_embed(age_min: int, last_success: str)`, `notices.stale_scan_recovered_embed(last_success: str)`, `notices.provider_degraded_embed(row: dict, fallback_pct: float, empty_pct: float)`, `notices.provider_recovered_embed(row: dict)`; `ops_watch.BOOTED_AT: dt.datetime`; `ops_watch.stale_scan_verdict(now, last_success, interval_min, booted_at, *, in_session, paused, failure_alert_active, stale_alert_active) -> str | None`; `ops_watch.provider_verdict(row: dict | None, *, fallback_pct: float, empty_pct: float, alert_active: bool) -> str | None`. Two more names are used only by OH18 in this part: `ops_watch.parse_moment(iso) -> dt.datetime | None` and `ops_watch.STALE_FACTOR = 2`.

Design points the code encodes (spec § O3 "In-bot watchdog", § O4 "Alert"):
- **Stale** means `now - last_success > 2 × interval`, strictly older. The boot grace is `now - booted_at >= 2 × interval`. A missing or unreadable `last_success` is "unknown", never stale. A naive timestamp is read as UTC, because `runstate` writes aware UTC ISO strings.
- **Recovery** happens when a stale alert is open and `last_success` is fresh, whatever the session or pause state. `record_tick_success` stamps paused and off-session ticks too (`runstate.py:48`), so an evening recovery is real.
- **A failure-streak alert already open suppresses the stale alert.** That outage already has its page (`_maybe_escalate_health`).
- **Provider breach** means `rate > pct/100` on either field. A `None` rate never breaches. A row with neither v148 field (it predates v148) is unknown: it neither alerts nor recovers. `breach == alert_active` means nothing to say, which gives once per incident.
- **Embeds** use the existing HEALTH kinds through `system_embed`, as `health_alert_embed` (`notices.py:44`) does. A `None` figure renders `—`, never `0`.
- `ops_watch.py` imports only `datetime` in this task. OH18 adds the rest, and never `loops` at module level (index Global Constraint 7).

- [ ] **Step 0: Confirm the dependencies have landed**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
git -C $WT log --oneline | grep -E "v148 OH(5|8)[: ]"
test ! -e $WT/swingbot/commands/scanning/ops_watch.py && echo "ops_watch is new"
```

Expected: the OH5 and OH8 commit lines, then `ops_watch is new`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/scanning/test_ops_watch.py`:

```python
"""v148 O3/O4: ops_watch -- the stale-scan and provider verdicts, the ops
notices, and (OH18) the watchdog loop and provider check on a fake channel."""
import datetime as dt

import pytest

from swingbot.commands.scanning import notices, ops_watch
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind

NOW = dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.timezone.utc)
BOOT = NOW - dt.timedelta(hours=2)
INTERVAL = 5          # stale beyond 10 minutes

ROW_OK = {"at": "2026-10-12T14:55:00+00:00", "duration_s": 61.0, "tickers": 100,
          "provider_fallback_rate": 0.05, "empty_symbols": 1, "empty_rate": 0.01,
          "stale_symbols": 0}
ROW_BAD = {**ROW_OK, "provider_fallback_rate": 0.25, "empty_symbols": 6, "empty_rate": 0.06,
           "stale_symbols": 2}
ROW_PRE_V148 = {"at": "2026-10-01T14:55:00+00:00", "duration_s": 60.0, "tickers": 100}


def _ago(minutes: int) -> str:
    return (NOW - dt.timedelta(minutes=minutes)).isoformat()


def _stale(last="default", *, booted=BOOT, in_session=True, paused=False, failure=False,
           stale=False):
    last = _ago(11) if last == "default" else last
    return ops_watch.stale_scan_verdict(
        NOW, last, INTERVAL, booted, in_session=in_session, paused=paused,
        failure_alert_active=failure, stale_alert_active=stale)


# --- stale_scan_verdict ----------------------------------------------------------

@pytest.mark.parametrize("kwargs, expected", [
    ({}, "alert"),
    ({"last": _ago(10)}, None),                                   # exactly 2x: not older
    ({"last": _ago(3)}, None),
    ({"last": "2026-10-12T14:49:00"}, "alert"),                   # naive read as UTC
    ({"in_session": False}, None),
    ({"paused": True}, None),
    ({"failure": True}, None),                                    # failure streak owns it
    ({"stale": True}, None),                                      # once per incident
    ({"booted": NOW - dt.timedelta(minutes=9)}, None),            # boot grace
    ({"booted": NOW - dt.timedelta(minutes=10)}, "alert"),        # up exactly 2x
    ({"last": None}, None),                                       # unknown is not stale
    ({"last": "not a timestamp"}, None),
    ({"last": _ago(3), "stale": True}, "recover"),
    ({"last": _ago(3), "stale": True, "in_session": False}, "recover"),
    ({"last": _ago(3), "stale": True, "paused": True}, "recover"),
    ({"last": None, "stale": True}, None),
])
def test_stale_scan_verdict(kwargs, expected):
    assert _stale(**kwargs) == expected


def test_booted_at_is_an_aware_utc_moment():
    assert ops_watch.BOOTED_AT.utcoffset() == dt.timedelta(0)


# --- provider_verdict ------------------------------------------------------------

@pytest.mark.parametrize("row, active, expected", [
    (ROW_OK, False, None),
    (ROW_OK, True, "recover"),
    (ROW_BAD, False, "alert"),
    (ROW_BAD, True, None),                                        # once per incident
    ({**ROW_OK, "provider_fallback_rate": 0.20}, False, None),    # at the line: not above
    ({**ROW_OK, "empty_rate": 0.06}, False, "alert"),
    ({**ROW_OK, "provider_fallback_rate": None}, False, None),    # Alpaca asked for nothing
    ({**ROW_OK, "provider_fallback_rate": None, "empty_rate": 0.5}, False, "alert"),
    (ROW_PRE_V148, False, None),
    (ROW_PRE_V148, True, None),                                   # unknown never recovers
    (None, True, None),
    ({}, False, None),
])
def test_provider_verdict(row, active, expected):
    assert ops_watch.provider_verdict(row, fallback_pct=20, empty_pct=5,
                                      alert_active=active) == expected


# --- the notices -----------------------------------------------------------------

@pytest.mark.parametrize("build, kind, colour", [
    (lambda: notices.stale_scan_embed(14, _ago(14)), Kind.HEALTH_ALERT, kinds.HEALTH_RED),
    (lambda: notices.stale_scan_recovered_embed(_ago(1)), Kind.HEALTH_RECOVERED,
     kinds.HEALTH_GREEN),
    (lambda: notices.provider_degraded_embed(ROW_BAD, 20.0, 5.0), Kind.HEALTH_ALERT,
     kinds.HEALTH_RED),
    (lambda: notices.provider_recovered_embed(ROW_OK), Kind.HEALTH_RECOVERED,
     kinds.HEALTH_GREEN),
])
def test_ops_notices_are_health_pushes(build, kind, colour):
    embed = build()
    assert embed.push_text.startswith(f"{kinds.badge(kind)} SYSTEM · {kind.label}")
    assert embed.color.value == colour
    assert embed.footer.text == "SYSTEM"


def test_the_stale_alert_names_the_age_and_the_last_success():
    embed = notices.stale_scan_embed(14, _ago(14))
    assert embed.title == "🚨 HEALTH ALERT · no completed scan tick for 14 min"
    assert f"Last successful tick: {_ago(14)}" in embed.description


def test_the_stale_recovery_names_the_last_success():
    embed = notices.stale_scan_recovered_embed(_ago(1))
    assert embed.title == f"{kinds.badge(Kind.HEALTH_RECOVERED)} RECOVERED · scan ticks completing again"
    assert f"Last successful tick: {_ago(1)}" in embed.description


def test_the_provider_alert_carries_rates_and_thresholds():
    embed = notices.provider_degraded_embed(ROW_BAD, 20.0, 5.0)
    assert embed.title == "🚨 HEALTH ALERT · market-data provider degraded"
    assert "Alpaca fallback: 25.0%, alert above 20%" in embed.description
    assert "Empty symbols: 6 of 100 (6.0%), alert above 5%" in embed.description
    assert "Stale symbols: 2" in embed.description
    assert f"Scan at: {ROW_BAD['at']}" in embed.description


def test_a_missing_rate_reads_as_a_dash_not_zero():
    embed = notices.provider_degraded_embed({**ROW_BAD, "provider_fallback_rate": None}, 20.0, 5.0)
    assert "Alpaca fallback: —, alert above 20%" in embed.description


def test_the_provider_recovery_shows_the_healthy_figures():
    embed = notices.provider_recovered_embed(ROW_OK)
    assert embed.title.endswith("RECOVERED · market-data provider healthy again")
    assert "Alpaca fallback: 5.0%" in embed.description
    assert "Empty symbols: 1 of 100 (1.0%)" in embed.description
```

- [ ] **Step 2: Run them to watch them fail**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_ops_watch.py
```

Expected: collection error, `ImportError: cannot import name 'ops_watch' from 'swingbot.commands.scanning'`.

- [ ] **Step 3: Add the notices**

Append to `$WT/swingbot/commands/scanning/notices.py`:

```python
# --- v148 O3/O4: ops-watch notices --------------------------------------------

def _rate(rate) -> str:
    return "—" if rate is None else f"{rate * 100:.1f}%"


def _value(value) -> str:
    return "—" if value is None else str(value)


def stale_scan_embed(age_min: int, last_success: str):
    """v148 O3: the bot is up but no scan tick has completed -- a wedged tick.
    A dead bot cannot post this; the VM's heartbeat_watch cron reports that."""
    return system_embed(Kind.HEALTH_ALERT, f"no completed scan tick for {age_min} min", (
        f"• Last successful tick: {last_success}\n"
        "• The bot is up, but its scheduled scan has not finished a tick.\n"
        "No alerts are being produced until this clears."))


def stale_scan_recovered_embed(last_success: str):
    return system_embed(Kind.HEALTH_RECOVERED, "scan ticks completing again",
                        f"• Last successful tick: {last_success}")


def _provider_lines(row: dict) -> tuple[str, str]:
    fallback = f"• Alpaca fallback: {_rate(row.get('provider_fallback_rate'))}"
    empty = (f"• Empty symbols: {_value(row.get('empty_symbols'))} of "
             f"{_value(row.get('tickers'))} ({_rate(row.get('empty_rate'))})")
    return fallback, empty


def provider_degraded_embed(row: dict, fallback_pct: float, empty_pct: float):
    """v148 O4: the newest scan breached a provider threshold."""
    fallback, empty = _provider_lines(row)
    return system_embed(Kind.HEALTH_ALERT, "market-data provider degraded", (
        f"{fallback}, alert above {fallback_pct:g}%\n"
        f"{empty}, alert above {empty_pct:g}%\n"
        f"• Stale symbols: {_value(row.get('stale_symbols'))}\n"
        f"• Scan at: {_value(row.get('at'))}\n"
        "Scans continue: fallback tickers ran on yfinance data, empty ones were skipped."))


def provider_recovered_embed(row: dict):
    """v148 O4: a scan is back under both provider thresholds."""
    fallback, empty = _provider_lines(row)
    return system_embed(Kind.HEALTH_RECOVERED, "market-data provider healthy again",
                        f"{fallback}\n{empty}\n• Scan at: {_value(row.get('at'))}")
```

- [ ] **Step 4: Create `ops_watch.py` with the verdicts**

Create `$WT/swingbot/commands/scanning/ops_watch.py`:

```python
"""v148 O3/O4: the bot's own ops watch -- stale-scan and provider verdicts.

The verdicts are pure functions of their arguments, so the truth tables are
tested without a bot, a database or a clock. OH18 adds the
``scan_watchdog`` loop and ``check_provider_health``, which read the
heartbeat flags and post to the ops channel.

**Never import ``loops`` at module level here.** ``loops`` imports this
module at its top; the ops channel is looked up at call time instead
(``_channel()``, OH18), which also keeps tests' monkeypatching of
``loops._ops_channel`` effective.
"""
from __future__ import annotations

import datetime as dt

#: Process boot (UTC). The watchdog stays quiet until the process has been up
#: STALE_FACTOR x SCAN_INTERVAL_MINUTES, so a morning restart after an
#: overnight outage gets its first tick before anyone is paged.
BOOTED_AT: dt.datetime = dt.datetime.now(dt.timezone.utc)

#: A scan is stale when its last success is older than this many intervals.
STALE_FACTOR = 2

_PROVIDER_FIELDS = ("provider_fallback_rate", "empty_rate")


def parse_moment(iso: str | None) -> dt.datetime | None:
    """An ISO timestamp as an aware datetime (naive taken as UTC), or None."""
    try:
        moment = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def stale_scan_verdict(now: dt.datetime, last_success: str | None, interval_min: int,
                       booted_at: dt.datetime, *, in_session: bool, paused: bool,
                       failure_alert_active: bool, stale_alert_active: bool) -> str | None:
    """"alert", "recover" or None (spec § O3).

    - "alert": in session, not paused, no failure-streak alert already open,
      the last success older than STALE_FACTOR x the interval, the process up
      at least that long, and no stale alert already open.
    - "recover": a stale alert is open and the last success is fresh again,
      whatever the session (ticks stamp ``last_success`` off-session too).
    - None otherwise, and whenever ``last_success`` is missing or unreadable:
      unknown is never stale (the rule of ``runstate._read_heartbeat``).
    """
    last = parse_moment(last_success)
    if last is None:
        return None
    threshold = dt.timedelta(minutes=STALE_FACTOR * interval_min)
    stale = now - last > threshold
    if stale_alert_active:
        return None if stale else "recover"
    if not stale or not in_session or paused or failure_alert_active:
        return None
    return "alert" if now - booted_at >= threshold else None


def _above(rate: float | None, pct: float) -> bool:
    return rate is not None and rate > pct / 100


def provider_verdict(row: dict | None, *, fallback_pct: float, empty_pct: float,
                     alert_active: bool) -> str | None:
    """"alert", "recover" or None for the newest scan row (spec § O4).

    A breach is ``provider_fallback_rate > fallback_pct/100`` or
    ``empty_rate > empty_pct/100``; a None rate never breaches. A row that
    predates v148 (neither field present) is unknown: it neither alerts nor
    recovers. Once per incident: an open alert only ever recovers.
    """
    if not row or not any(key in row for key in _PROVIDER_FIELDS):
        return None
    breach = (_above(row.get("provider_fallback_rate"), fallback_pct)
              or _above(row.get("empty_rate"), empty_pct))
    if breach == alert_active:
        return None
    return "alert" if breach else "recover"
```

`except (TypeError, ValueError)` is a narrow handler, not `except Exception`, so OH15's ratchet does not count it. `fromisoformat(None)` raises `TypeError`, and a malformed string raises `ValueError`.

- [ ] **Step 5: Run the tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/scanning/test_ops_watch.py
python $WT/scripts/dev/testrun.py file tests/commands/test_system_notices.py
python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
```

Expected: `test_ops_watch.py` `38 passed`. Every run shows `0 failed`, `0 xfailed`. The ratchet stays green because no `except Exception` was added.

- [ ] **Step 6: Complexity**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C $WT/swingbot/commands/scanning/ops_watch.py $WT/swingbot/commands/scanning/notices.py
```

Expected: no output. `stale_scan_verdict` is about 9, which is below grade C.

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/commands/scanning/notices.py swingbot/commands/scanning/ops_watch.py tests/scanning/test_ops_watch.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH17: stale-scan and provider verdicts (pure) and their ops notices"
```

