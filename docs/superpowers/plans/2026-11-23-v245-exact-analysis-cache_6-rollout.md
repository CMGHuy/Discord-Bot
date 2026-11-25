# v245 — Exact analysis caching — Part 6: rollout, results, scaffolding removal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V245-16" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v245-exact-analysis-cache-design.md](../specs/2026-11-23-v245-exact-analysis-cache-design.md) (§ Switch criteria, § Rollout steps 2–7, § Observability)
**Index:** [2026-11-23-v245-exact-analysis-cache_0-index.md](2026-11-23-v245-exact-analysis-cache_0-index.md): Global Constraints, Parallelisation and the task ledger apply to every task here.

Scope: V245-15 ships Phase B with `ANALYSIS_CACHE=off`, switches production
to `shadow` and runs the 5-trading-day soak with a small report script.
V245-16 switches to `on`, measures one trading day, records `## Results` in
the spec and aligns `known-traps.md` and the deploy doc. V245-17, after 10
trading days of `on`, deletes the shadow mode, the comparator and the jsonl,
leaving `off|on` as the rollback switch.

All three run only if V245-6 missed the exit criterion. They are strictly
sequential (index § Parallelisation: V245-14 → V245-15 → V245-16 → V245-17)
and each holds on a production wait. **Every production change goes through
the `mirror-prod` skill and `bash scripts/ops/ssh-hetzner.sh`; read-only
checks need no asking (CLAUDE.md standing permission).** The VM `.env` is a
single-file bind mount: it is edited in place with
`python3 scripts/ops/env_set.py KEY value`, never `sed -i`
(`docs/claude/known-traps.md` § Editing production `.env` with `sed -i`
changes nothing live).

Small refinements of the ledger's file lists (no cross-part contract moves):
- V245-15 also modifies `docs/deploy/DEPLOY_HETZNER.md`: the `shadow` switch
  is a production `.env` change, and `mirror-prod` mirrors it into the deploy
  doc in the same session.
- V245-16 also modifies `AGENTS.md` (the Codex mirror of the
  `known-traps.md` topic line; CLAUDE.md § Claude is the operator).
- V245-17 also modifies `swingbot/core/scanning/structure.py`
  (`cache_for_mode`), `tests/scanning/test_analysis_cache_wiring.py`,
  `tests/scanning/test_analysis_cache_telemetry.py`,
  `docs/claude/known-traps.md` and `docs/deploy/DEPLOY_HETZNER.md`: each one
  names the `shadow` mode that the task removes.

Clock note for every wait below: Git Bash on this machine has no timezone
data (`TZ=... date` prints UTC). Compute New York time from `date -u`
(UTC−5 in winter, UTC−4 from the second Sunday of March); the NYSE regular
session is 09:30–16:00 New York.

---

# Phase C — rollout

### Task V245-15: Deploy `off`, then `shadow`; soak report

**Model:** sonnet — a small pure report script plus a runbook of fixed production steps; the pass rule is the spec's, the judgement calls are escalations.

Spec § Rollout steps 2–3 and § Switch criteria: Phase B ships with
`ANALYSIS_CACHE=off` (output unchanged, nothing cached), then production
switches to `shadow` for **5 trading days with zero diffs**. A single diff
is a bug: it is fixed, deployed, and the count restarts. The script turns
`data/scan_telemetry.jsonl` into the soak verdict so nobody counts days by
hand.

**Decisions this task fixes (spec silent):**
- **What a soak row is.** Only rows V245-14 wrote in `shadow`:
  `cache_mode == "shadow"` with integer `cache_compared` and `cache_diffs`
  (they are `None` in `off`/`on`). Deploy markers, `off` and `on` rows are
  ignored, so `--since-deploy` restarts the count at a fix's deploy and an
  `off` stretch never counts.
- **What a trading day is.** A New York date that is a weekday and not in
  `swingbot.core.market.session.NYSE_HOLIDAYS`, with at least one compared
  ticker. Weekend scans run on a frozen bar: their diffs still FAIL the soak,
  but they never count toward the 5. Today counts only after 16:00 New York
  (`open_day`), so a verdict is never reached on a half session.
- **Verdict.** `FAIL` when any day has a diff; else `PASS` with at least
  `need` counted days; else `WAIT`.
- **Reuse.** Piped as `python -` into the bot container, the working
  directory is `/app` (Dockerfile `WORKDIR`, `COPY . .`), so the V245-6
  imports and `swingbot` resolve there as from the repo root.

**Files:**
- Create: `scripts/perf/analysis_cache_soak_report.py`
- Create: `tests/scripts/test_analysis_cache_soak_report.py` (suite `tooling`)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (new `### v245 analysis cache rollout` table under `## Updating settings without a code deploy`, after the v171 subsection)

**Interfaces:**
- Consumes: V245-6 `scripts/perf/analysis_phase_report.py` (`_read(path) -> tuple[list[dict], int]`, `_when(stamp) -> datetime`, `last_deploy_at(rows, component="bot") -> str | None`); V245-14's telemetry keys `cache_mode`, `cache_compared`, `cache_diffs`; V245-13's `logs/analysis_cache_shadow.jsonl` (`SHADOW_LOG_PATH`) and the swallowed tag `scan.analysis_cache_shadow` (log text `analysis cache shadow: comparison failed for <ticker>`); V245-12's summary text `analysis cache off`.
- Produces (ledger): `soak_days(rows: list[dict]) -> list[dict]` (per New York date, sorted: `date, scans, compared, diffs`); `verdict(days: list[dict], need: int = 5, *, open_day: str | None = None) -> str` (`PASS` / `WAIT` / `FAIL`); `main(argv=None) -> int`. Also `trading_day(day: str) -> bool`, `counted_days(days, session_open=None) -> list[str]`, `open_day(now: datetime) -> str | None`, `NEED_DAYS = 5`.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_analysis_cache_soak_report.py`:

```python
"""v245 V245-15: the shadow soak verdict from scan telemetry."""
import json
from datetime import date, datetime, timezone

import pytest

from scripts.perf import analysis_cache_soak_report as soak

DEPLOY = {"type": "deploy", "component": "bot", "sha": "abc", "at": "2026-11-23T12:00:00Z"}
# Mon 2026-11-23 .. Mon 2026-11-30, without Thu 2026-11-26 (Thanksgiving, closed).
WEEK = ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-27", "2026-11-30"]


@pytest.fixture(autouse=True)
def holidays(monkeypatch):
    monkeypatch.setattr(soak, "_HOLIDAYS", frozenset({date(2026, 11, 26)}))


def _row(at, compared=31, diffs=0, mode="shadow"):
    return {"at": at, "duration_s": 300.0, "tickers": 92, "phases_s": {"analysis": 60.0},
            "cache_mode": mode, "cache_compared": compared if mode == "shadow" else None,
            "cache_diffs": diffs if mode == "shadow" else None}


def _days(dates, **kw):
    return [{"date": d, "scans": 70, "compared": 2170, "diffs": 0, **kw} for d in dates]


def test_soak_days_groups_shadow_rows_by_new_york_date():
    rows = [DEPLOY,
            _row("2026-11-24T15:00:00+00:00"),
            _row("2026-11-25T03:00:00+00:00", compared=30, diffs=1),   # 22:00 New York, Nov 24
            _row("2026-11-25T15:00:00+00:00", compared=0),
            _row("2026-11-25T15:05:00+00:00", mode="on"),
            _row("2026-11-25T15:10:00+00:00", mode="off"),
            {**_row("2026-11-25T15:15:00+00:00"), "cache_compared": None}]
    assert soak.soak_days(rows) == [
        {"date": "2026-11-24", "scans": 2, "compared": 61, "diffs": 1},
        {"date": "2026-11-25", "scans": 1, "compared": 0, "diffs": 0}]
    assert soak.soak_days([]) == []


def test_trading_day_skips_weekends_and_holidays():
    assert soak.trading_day("2026-11-25")
    assert not soak.trading_day("2026-11-26")      # the patched holiday
    assert not soak.trading_day("2026-11-28")      # Saturday


def test_counted_days_need_a_compared_ticker_on_a_trading_day():
    days = _days(["2026-11-24", "2026-11-25"]) + _days(["2026-11-26", "2026-11-28"]) \
        + _days(["2026-11-27"], compared=0)
    assert soak.counted_days(days) == ["2026-11-24", "2026-11-25"]
    assert soak.counted_days(days, session_open="2026-11-25") == ["2026-11-24"]


@pytest.mark.parametrize("days, today, expect", [
    (_days(WEEK), None, "PASS"),
    (_days(WEEK[:4]), None, "WAIT"),
    (_days(WEEK), "2026-11-30", "WAIT"),                       # today's session is not over
    (_days(WEEK[:4]) + _days(["2026-11-28"]), None, "WAIT"),   # a Saturday never counts
    (_days(WEEK[:4]) + _days(["2026-11-28"], diffs=1), None, "FAIL"),  # but its diff does
    (_days(WEEK) + _days(["2026-12-01"], diffs=2), None, "FAIL"),
    ([], None, "WAIT"),
])
def test_verdict(days, today, expect):
    assert soak.verdict(days, open_day=today) == expect


def test_verdict_need_is_a_parameter():
    assert soak.verdict(_days(WEEK[:2]), need=2) == "PASS"


@pytest.mark.parametrize("now, expect", [
    (datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc), "2026-11-25"),   # 13:00 New York
    (datetime(2026, 11, 25, 21, 30, tzinfo=timezone.utc), None),          # 16:30, closed
    (datetime(2026, 11, 28, 18, 0, tzinfo=timezone.utc), None),           # Saturday
    (datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc), None),           # holiday
])
def test_open_day(now, expect):
    assert soak.open_day(now) == expect


def _write(path, rows, bad=False):
    lines = [json.dumps(r) for r in rows] + (["{not json"] if bad else [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_main_since_deploy_restarts_the_count(tmp_path, capsys):
    path = tmp_path / "scan_telemetry.jsonl"
    before = _row("2026-11-20T15:00:00+00:00", diffs=3)          # a diff before the fix's deploy
    rows = [before, DEPLOY] + [_row(f"{d}T15:00:00+00:00") for d in WEEK]
    _write(path, rows, bad=True)
    argv = ["--path", str(path), "--since-deploy", "--now", "2026-11-30T22:00:00+00:00"]
    assert soak.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "PASS" and out["counted"] == WEEK
    assert out["since"] == DEPLOY["at"] and out["bad_lines"] == 1 and out["need"] == 5
    assert soak.main(["--path", str(path), "--now", "2026-11-30T22:00:00+00:00"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"


def test_main_excludes_the_open_session(tmp_path, capsys):
    path = tmp_path / "scan_telemetry.jsonl"
    _write(path, [_row(f"{d}T15:00:00+00:00") for d in WEEK])
    assert soak.main(["--path", str(path), "--now", "2026-11-30T18:00:00+00:00"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["open_day"] == "2026-11-30" and out["verdict"] == "WAIT"


def test_main_missing_file(tmp_path):
    assert soak.main(["--path", str(tmp_path / "absent.jsonl")]) == 1
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_analysis_cache_soak_report.py`
Expected: FAIL — `ImportError: cannot import name 'analysis_cache_soak_report'`.

- [ ] **Step 3: Write the script**

Create `scripts/perf/analysis_cache_soak_report.py`:

```python
"""Shadow soak verdict from scan telemetry (v245, spec § Switch criteria).

Usage:
    python scripts/perf/analysis_cache_soak_report.py [--since ISO | --since-deploy] [--need 5] [--path FILE]

On production, read-only, piped to the bot container (working directory /app):
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since-deploy" < scripts/perf/analysis_cache_soak_report.py

Reads only rows written in ANALYSIS_CACHE=shadow (cache_mode "shadow" with
integer cache_compared / cache_diffs), groups them by New York date and prints
one JSON object. Verdict: FAIL on any diff; PASS once `need` trading days
(weekday, not an NYSE holiday, session over, at least one compared ticker)
have zero diffs; WAIT otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from scripts.perf.analysis_phase_report import _read, _when, last_deploy_at

try:  # the NYSE calendar; importable from the repo root and in the bot container
    from swingbot.core.market.session import NYSE_HOLIDAYS as _HOLIDAYS
except ImportError:  # anywhere else: weekdays only
    _HOLIDAYS = frozenset()

DEFAULT_PATH = os.path.join("data", "scan_telemetry.jsonl")
NEW_YORK = ZoneInfo("America/New_York")
SESSION_CLOSE = time(16, 0)
NEED_DAYS = 5


def _is_shadow_row(row: dict) -> bool:
    return (row.get("cache_mode") == "shadow" and bool(row.get("at"))
            and isinstance(row.get("cache_compared"), int)
            and isinstance(row.get("cache_diffs"), int))


def _ny_date(stamp: str) -> str:
    return _when(stamp).astimezone(NEW_YORK).date().isoformat()


def soak_days(rows: list[dict]) -> list[dict]:
    """Shadow rows summed per New York date: date, scans, compared, diffs."""
    days: dict[str, dict] = {}
    for row in filter(_is_shadow_row, rows):
        day = days.setdefault(_ny_date(row["at"]), {"scans": 0, "compared": 0, "diffs": 0})
        day["scans"] += 1
        day["compared"] += row["cache_compared"]
        day["diffs"] += row["cache_diffs"]
    return [{"date": d, **totals} for d, totals in sorted(days.items())]


def trading_day(day: str) -> bool:
    d = date.fromisoformat(day)
    return d.weekday() < 5 and d not in _HOLIDAYS


def open_day(now: datetime) -> str | None:
    """Today's New York date while its regular session is not over, else None."""
    local = now.astimezone(NEW_YORK)
    today = local.date().isoformat()
    return today if trading_day(today) and local.time() < SESSION_CLOSE else None


def counted_days(days: list[dict], session_open: str | None = None) -> list[str]:
    """Dates that count toward the soak; `session_open` (today, unfinished) never does."""
    return [d["date"] for d in days
            if d["compared"] > 0 and trading_day(d["date"]) and d["date"] != session_open]


def verdict(days: list[dict], need: int = NEED_DAYS, *, open_day: str | None = None) -> str:
    if any(d["diffs"] for d in days):
        return "FAIL"
    return "PASS" if len(counted_days(days, open_day)) >= need else "WAIT"


def _after(rows: list[dict], since: str | None) -> list[dict]:
    if not since:
        return rows
    start = _when(since)
    return [r for r in rows if r.get("at") and _when(r["at"]) >= start]


def _parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--since", default=None, help="ISO timestamp or date (UTC)")
    parser.add_argument("--since-deploy", action="store_true", help="from the last bot deploy marker")
    parser.add_argument("--need", type=int, default=NEED_DAYS)
    parser.add_argument("--now", default=None, help="ISO 'now' (tests and replays); default: the clock")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    if not os.path.exists(args.path):
        print(f"no telemetry file at {args.path}", file=sys.stderr)
        return 1
    rows, bad = _read(args.path)
    since = last_deploy_at(rows) if args.since_deploy else args.since
    days = soak_days(_after(rows, since))
    now = _when(args.now) if args.now else datetime.now(timezone.utc)
    current = open_day(now)
    print(json.dumps({"days": days, "counted": counted_days(days, current), "need": args.need,
                      "open_day": current, "since": since, "bad_lines": bad,
                      "verdict": verdict(days, args.need, open_day=current)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test and the gate**

```bash
python scripts/dev/testrun.py file tests/scripts/test_analysis_cache_soak_report.py
python scripts/dev/testrun.py file tests/scripts/test_analysis_phase_report.py
python scripts/dev/complexity_gate.py
```

Expected: PASS, `0 failed`; every new function below 6.

- [ ] **Step 5: Commit the script**

```bash
git add scripts/perf/analysis_cache_soak_report.py tests/scripts/test_analysis_cache_soak_report.py
git commit -m "feat(v245): shadow soak verdict from scan telemetry (V245-15)"
```

- [ ] **Step 6: Controller — merge Phase B and deploy with the cache `off`**

The controller merges V245-7..V245-15 (code) to `main` and deploys per
`docs/deploy/DEPLOY_HETZNER.md` (index Decision 9). The VM `.env` gets no
`ANALYSIS_CACHE` line yet, so the field default `off` applies. The
implementer waits here. Then, read-only:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && git log -1 --format=%h && python3 scripts/ops/env_set.py --get ANALYSIS_CACHE; tail -n 300 data/scan_telemetry.jsonl | grep -c '\"type\":\"deploy\"'"
```

Expected: the merged `main` short sha; `ANALYSIS_CACHE` absent or `off`; a
deploy-marker count of at least 1. If `.env` already says `shadow` or `on`,
stop and report: the soak must start from a deliberate switch.

Write this read-only helper to the scratchpad once (it prints the cache
fields of the newest scan rows; reused in Steps 7 and V245-16):

```bash
cat > "$SCRATCH/v245_rows.py" <<'PY'
import json, sys
rows = [json.loads(l) for l in open("data/scan_telemetry.jsonl", encoding="utf-8") if l.strip()]
for r in [r for r in rows if "duration_s" in r][-int(sys.argv[1] if len(sys.argv) > 1 else 3):]:
    print(r.get("at"), r.get("cache_mode"), r.get("cache_hits"), r.get("cache_misses"),
          r.get("cache_compared"), r.get("cache_diffs"), r.get("errors"))
PY
```

(`$SCRATCH` = this session's scratchpad.) After three scans:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - 3" < "$SCRATCH/v245_rows.py"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && grep -c 'analysis cache off' logs/bot.log"
```

Expected: the three rows show `cache_mode` `off`, `None` for every cache
count and the usual `errors`; the summary-line count is at least 3.
Anything else (`cache_mode` missing, a traceback in `logs/bot.log` naming
`structure` or `scan_run`): stop and report.

- [ ] **Step 7: Switch production to `shadow` (mirror-prod)**

Run the `mirror-prod` skill first. Do the switch **before a session opens**
(before 09:30 New York on a trading day), so the first soak day is a full
session. The change, in one sentence: set `ANALYSIS_CACHE=shadow` in
`/opt/swing-bot/.env` in place and SIGHUP the bot.

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py ANALYSIS_CACHE shadow && docker compose kill -s HUP bot && sleep 5 && docker compose exec -T bot grep '^ANALYSIS_CACHE' /app/.env"
```

Expected: `ANALYSIS_CACHE=shadow` read back from inside the container. Note
the UTC time printed first: it goes in the deploy doc. After the next scan:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - 1" < "$SCRATCH/v245_rows.py"
```

Expected: `shadow`, an integer `cache_compared` near a third of the
watchlist (about 31 of 92) and `cache_diffs` `0`. A `None` count means the
SIGHUP did not reach the bot: verify per the known-traps section named in
this part's header (never `sed -i`), then retry.

- [ ] **Step 8: Mirror the switch into the deploy doc**

In `docs/deploy/DEPLOY_HETZNER.md`, under `## Updating settings without a
code deploy`, after the v171 subsection's rollback paragraph (ends "The
`v171_001` tables stay on every rollback.") and before
`## Not scheduled yet: the option-chain archive`, add:

```markdown
### v245 analysis cache rollout

| Flag | Production value | Set |
|---|---|---|
| `ANALYSIS_CACHE` | `shadow` | <UTC from Step 7> (V245-15; Phase B deployed <deploy marker `at`> with `off`) |

Soak: 5 trading days of `shadow` with zero diffs (`cache_diffs` in
`data/scan_telemetry.jsonl`, one JSON line per diff in
`logs/analysis_cache_shadow.jsonl`). Read-only verdict:
`bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since-deploy" < scripts/perf/analysis_cache_soak_report.py`.
Rollback: `python3 scripts/ops/env_set.py ANALYSIS_CACHE off` plus
`docker compose kill -s HUP bot` (same alerts, slower scans).
```

```bash
git add docs/deploy/DEPLOY_HETZNER.md
git commit -m "docs(v245): production ANALYSIS_CACHE=shadow, soak started (V245-15)"
```

The `mirror-prod` gate is this commit in `git log`.

- [ ] **Step 9: Daily soak check (read-only, after each session close)**

After 16:00 New York on each trading day:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since-deploy" < scripts/perf/analysis_cache_soak_report.py > logs/v245-soak-report.json
cat logs/v245-soak-report.json
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && ls -l logs/analysis_cache_shadow.jsonl* 2>/dev/null; grep -c 'analysis cache shadow: comparison failed' logs/bot.log"
```

Read the result:
- **`WAIT`**, no jsonl file, comparison-failure count `0`: the soak goes on;
  repeat after the next close. A counted day whose `compared` is far below
  ~31 × `scans` means sampling is broken: stop and report.
- **Comparison-failure count above 0**: a comparison that fails checks
  nothing. Treat it like a diff (next bullet), with the traceback from
  `logs/bot.log` as the evidence.
- **`FAIL`**: a diff is a cache bug. Copy the jsonl lines
  (`bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && tail -n 50 logs/analysis_cache_shadow.jsonl"`)
  into the report and stop. The controller switches production back to
  `off` (Step 7's command with `off`, and a new row in the deploy-doc
  table), fixes the bug with `superpowers:systematic-debugging` and a
  regression test that reproduces the diff from the logged ticker's frame
  (in `tests/scanning/test_analysis_cache_property.py`; the V245-1 golden is
  never regenerated), deploys, switches back to `shadow`, and the count
  restarts: `--since-deploy` starts from the fix's deploy marker.
- **`PASS`**: go to Step 10.

The rotated jsonl (20 MB × 3) is never deleted during the soak; it is the
evidence.

- [ ] **Step 10: Record the passed soak**

Append to the `ANALYSIS_CACHE` row's `Set` cell in
`docs/deploy/DEPLOY_HETZNER.md`: `; soak passed <last counted date>:
<counted days> trading days, <sum of compared> comparisons, 0 diffs`, with
the figures from `logs/v245-soak-report.json`.

```bash
git add docs/deploy/DEPLOY_HETZNER.md
git commit -m "docs(v245): shadow soak passed, 5 trading days with zero diffs (V245-15)"
```

Report `PASS` and the counted dates to the controller; keep
`logs/v245-soak-report.json` for V245-16.

### Task V245-16: Switch `on`, measure, record `## Results`, align docs

**Model:** sonnet — fixed production steps with V245-6's report script, then a results section and two doc sections written from measured values; no code.

Spec § Switch criteria (switch to `on`, measure analysis p50 per ticker in
production over one trading day), § Rollout steps 4 and 6. The verdict is
V245-6's: p50 ≤ 0.7 s per ticker. The laptop never gives it (index § Global
Constraints).

**Decisions this task fixes (spec silent):**
- **Window.** From the `on` switch (its UTC time, noted when made) through
  the close of the first full regular session after it; at least 50 scans,
  else wait one more session (the window is never cut short for a verdict).
  The switch is a SIGHUP, not a deploy, so the report runs with
  `--since <switch time>`, never `--since-deploy`.
- **Missed is a result, not a retry.** A MISSED verdict is recorded as is.
  The cache stays `on` (it is faster than `off` and byte-identical), and the
  spec's § Deferred alternative returns to the partner as its own decision
  (index § What follows). No knob is tuned to reach 0.7 s inside this plan.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-23-v245-exact-analysis-cache-design.md` (`## Results`: new `### Phase C` subsection after V245-6's `### Phase A`)
- Modify: `docs/claude/known-traps.md` (new last section `## Analysis prefix cache (v245): exact, and rollback by off only before growth`)
- Modify: `AGENTS.md` (the `known-traps.md` topic line, Codex mirror)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (V245-15's `### v245 analysis cache rollout` subsection)

**Interfaces:**
- Consumes: V245-15's PASS (`logs/v245-soak-report.json`, the deploy-doc row) and its scratch helper `$SCRATCH/v245_rows.py` (rewrite it from V245-15 Step 6 if the scratchpad was cleared); V245-6's `scripts/perf/analysis_phase_report.py` (`--since ISO`; output keys `scans, p50, p90, prefix_p50, cache_hit_rate, rss_mb_max, since, bad_lines, target_s, verdict`) and its `## Results` / `### Phase A` section in the spec; V245-12's telemetry keys and the build-failure WARNING text `analysis cache: building <unit> failed for <ticker>` (V245-7), `analysis cache: keying <unit> failed for <ticker>` (V245-9).
- Produces: none (ledger). V245-17 reads the deploy-doc row for the `on` date.

- [ ] **Step 1: Confirm the soak still passes (read-only)**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since-deploy" < scripts/perf/analysis_cache_soak_report.py > logs/v245-soak-report.json
python -c "import json; r = json.load(open('logs/v245-soak-report.json')); print(r['verdict'], len(r['counted']))"
```

Expected: `PASS 5` (or more). `FAIL`: a diff arrived after V245-15 closed;
go back to V245-15 Step 9's `FAIL` bullet, this task waits.

- [ ] **Step 2: Switch production to `on` (mirror-prod)**

Run the `mirror-prod` skill first. Switch **before a session opens**
(before 09:30 New York on a trading day). The change, in one sentence: set
`ANALYSIS_CACHE=on` in `/opt/swing-bot/.env` in place and SIGHUP the bot.

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py ANALYSIS_CACHE on && docker compose kill -s HUP bot && sleep 5 && docker compose exec -T bot grep '^ANALYSIS_CACHE' /app/.env"
```

Expected: `ANALYSIS_CACHE=on` from inside the container. Keep the printed
UTC time as `SWITCH_AT`. After two scans:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - 2" < "$SCRATCH/v245_rows.py"
```

Expected: both rows `on`; integer `cache_hits`/`cache_misses`;
`cache_compared` and `cache_diffs` `None`. The SIGHUP cleared the cache
(index Global Constraints: every config-changing reload clears it), so the
first row is mostly misses and the second mostly hits. A second row with
`cache_hits` `0`: stop and report (the cache is not keeping entries).

- [ ] **Step 3: Mirror the switch into the deploy doc**

In `docs/deploy/DEPLOY_HETZNER.md`, `### v245 analysis cache rollout`: set
the `ANALYSIS_CACHE` row's `Production value` to `on` and append to its
`Set` cell `; on since <SWITCH_AT> (V245-16)`.

```bash
git add docs/deploy/DEPLOY_HETZNER.md
git commit -m "docs(v245): production ANALYSIS_CACHE=on (V245-16)"
```

- [ ] **Step 4: Wait one full trading day, then measure (read-only)**

After the first full regular session after `SWITCH_AT` has closed (16:00
New York):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since <SWITCH_AT>" < scripts/perf/analysis_phase_report.py > logs/v245-on-report.json
cat logs/v245-on-report.json
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && grep -c 'analysis cache: \(building\|keying\) .* failed' logs/bot.log; docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | grep bot"
```

Expected: `scans` ≥ 50 (fewer: wait one more session and rerun with the
same `--since`); a `verdict` of `MET` or `MISSED`; a `cache_hit_rate` well
above 0.5; the failure count and the bot container's memory line. A
non-zero failure count is not a stop by itself (each failure computes that
ticker uncached, same output) but it goes in the results with the unit and
ticker from the log line. `NO DATA` or exit code 1: stop and report.

- [ ] **Step 5: Record `### Phase C` in the spec's `## Results`**

In `docs/superpowers/specs/2026-11-23-v245-exact-analysis-cache-design.md`,
append this subsection at the end of `## Results` (after V245-6's
`### Phase A`, before `## Deferred alternative: frozen completed-bar
structure`), every value from `logs/v245-on-report.json`,
`logs/v245-soak-report.json`, `logs/v245-exit-report.json` (Phase A's
p50/p90; else copy them from the `### Phase A` table) and the deploy doc:

```markdown
### Phase C (V245-15, V245-16, <YYYY-MM-DD>)

Prefix cache deployed <deploy marker `at`> with `off`; `shadow` from
<shadow switch UTC>; soak passed on <counted dates>: <sum of compared>
comparisons, 0 diffs<, restarted after <fix sha> if a diff occurred>.
`on` from <SWITCH_AT>; measured over <scans> production scans to <last row
`at`>, 92 tickers, `SCAN_WORKERS=1`, `cpus: 1.0`.

| Measure | Before (spec § Why) | After Phase A | After `on` |
|---|---|---|---|
| Analysis per ticker, p50 | ~3.2 s (293.5 s / 92) | <A p50> s | <p50> s |
| Analysis per ticker, p90 | — | <A p90> s | <p90> s |
| Prefix building per ticker, p50 | — | — | <prefix_p50> s |
| Cache hit rate | — | — | <cache_hit_rate> |
| Bot RSS, max | — | — | <rss_mb_max> MB |
| Build/keying failures | — | — | <count; unit and ticker if any> |

**Verdict: <MET | MISSED>** against 0.7 s per ticker (p50).

<MET: "The goal is met. `ANALYSIS_CACHE=on` stays; the shadow scaffolding
is removed after 10 trading days of `on` with no incident (V245-17)."
MISSED: "The goal is missed by <p50 − 0.7> s. `on` stays (faster than
`off`, identical alerts); § Deferred alternative returns to the partner as
its own decision. The shadow scaffolding is still removed after 10 trading
days of `on` (V245-17).">
```

```bash
git add docs/superpowers/specs/2026-11-23-v245-exact-analysis-cache-design.md
git commit -m "docs(v245): Phase C production results, ANALYSIS_CACHE=on (V245-16)"
```

- [ ] **Step 6: Add the known-traps section and its Codex mirror**

Append to `docs/claude/known-traps.md` (last section, after
`## Market-on-open and the gap-reclaim veto (v192): two knobs, both off`):

```markdown
## Analysis prefix cache (v245): exact, and rollback by off only before growth

`ANALYSIS_CACHE` (`off` | `on`, hot-reloaded; production `on` since
<SWITCH_AT date>) caches, per ticker, work that is a pure function of the
frame minus its last bar: the units in
`swingbot/core/scanning/structure.py:PREFIX_UNITS` (the trendline pair
search per side, and any unit the v245 profile added). Alerts are
byte-identical to `off`, pinned by the `_scan_one` golden
`tests/fixtures/scanning/v245_scan_one_golden.json`. A golden that moves is
a behaviour change, never a fixture to refresh.

- **Never cached.** Anything reading the last row, the forming bar, `now`
  or `current_price`: `_apply_pullback_dryup`, `_band_live`, floor pivots,
  rolling S/R, indicator series, `_cluster_levels`, scenarios, confluence,
  confidence, requirements. A new cached unit must be a pure function of
  `frame.iloc[:m]` under `prefix_fingerprint(frame, m)`, frozen (tuples),
  and named per horizon if it depends on one.
- **One code path.** Each refactored function takes an optional prefix
  result and builds it itself when given none. Replay (`scan_replay.py`)
  and the outlook (`outlook_run.py`) pass no cache, so they never see it.
- **Clearing.** Every config-changing SIGHUP clears the whole cache
  (`structure.apply_config_change`); a moved fingerprint is a rebuild,
  never a stale hit. A build or keying failure logs
  `analysis cache: building|keying <unit> failed for <ticker>` at WARNING
  and computes that ticker uncached for the scan.
- **Telemetry.** `scan_telemetry` rows carry `cache_mode`, `cache_hits`,
  `cache_misses`, `cache_evictions`, `cache_entries`, `rss_mb` and
  `phases_s.analysis_prefix`; `scripts/perf/analysis_phase_report.py`
  turns them into seconds per ticker.
- **Rollback.** Before any watchlist growth, `ANALYSIS_CACHE=off` alone is
  a full rollback (same alerts, ~3.2 s per ticker). After growth, `off`
  must come with shrinking the watchlist to the last size whose scan p90
  was under 300 s without the cache (92 tickers in 2026-11), or scans run
  back to back past the interval. The removed tickers' open trades stay
  monitored.
- **Shadow mode** (`shadow`, comparing a third of the watchlist uncached
  into `logs/analysis_cache_shadow.jsonl`) exists until V245-17 removes it;
  a stale `shadow` in `.env` then reads as `off` with a warning.
```

In `AGENTS.md`, extend the `known-traps.md` topic line so it reads:

```markdown
- `known-traps.md`: data caching (every provider call goes through `core/marketdata/shared/`), scan output, embeds, the 2% stop
  cap/clamp, the liquidity floor, production `.env` (never `sed -i`), the v245 analysis prefix cache (`ANALYSIS_CACHE`).
```

Check the new section is addressable and the mirror test is green:

```bash
python scripts/dev/doc_section.py docs/claude/known-traps.md "Analysis prefix cache (v245): exact, and rollback by off only before growth"
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
```

Expected: the section prints; `0 failed`.

```bash
git add docs/claude/known-traps.md AGENTS.md
git commit -m "docs(v245): known trap for the analysis prefix cache, Codex mirror (V245-16)"
```

- [ ] **Step 7: Rollback rule in the deploy doc**

In `docs/deploy/DEPLOY_HETZNER.md`, `### v245 analysis cache rollout`,
replace V245-15's `Rollback:` sentence with:

```markdown
Rollback (spec § Rollout step 6): before any watchlist growth,
`python3 scripts/ops/env_set.py ANALYSIS_CACHE off` plus
`docker compose kill -s HUP bot` is a full rollback (same alerts, slower
scans). After growth, `off` alone brings back ~3.2 s of analysis per ticker
on the bigger list: switch `off` **and** have the partner shrink the
watchlist to the last size whose scan p90 was under 300 s without the cache
(92 tickers in 2026-11). The bot keeps the removed tickers' open trades
monitored. Watchlist growth itself is not part of v245: it waits for
sub-project B (fetch path) and goes in steps, each held a full trading day
with scan p90 < 300 s.
```

```bash
git add docs/deploy/DEPLOY_HETZNER.md
git commit -m "docs(v245): analysis cache rollback rule before and after growth (V245-16)"
```

Report the verdict, the p50 and the `on` date to the controller, and the
earliest date V245-17 may start: the 10th trading day after `SWITCH_AT`
(count weekdays that are not in `swingbot.core.market.session.NYSE_HOLIDAYS`).

### Task V245-17: Remove the shadow scaffolding (after 10 trading days of `on`)

**Model:** sonnet — deletions and small edits whose behaviour is pinned by the golden and the cache tests; `_sync_run_scan` only shrinks.

Spec § Rollout step 7: once `on` has run for 10 trading days with no
incident, delete the `shadow` mode, the comparator and the jsonl, leaving
`off`/`on` as the rollback switch (index Decision 10: a stale `shadow`
reads as `off` with the existing `_cast_mode` warning). Nothing `off` or
`on` does changes: the V245-1 golden and V245-9/V245-10/V245-12's tests
stay green unchanged except where they name `shadow`.

**Decisions this task fixes (spec silent):**
- **What "no incident" means.** Since the `on` switch: `.env` still reads
  `on` (no rollback), no `prod-incident` run named the cache, and no scan
  in `scan_telemetry` has `errors` above its pre-switch level with a
  traceback in `logs/bot.log` through `structure` or `scan_run`. A build or
  keying WARNING alone is not an incident (that ticker computed uncached,
  same output), but each one is listed in the report.
- **`_AnalysisCtx` keeps three fields.** `scan_seq`, `compared` and
  `diffs` exist only for the shadow, so the dataclass becomes
  `_AnalysisCtx(mode: str, cache: object, scan_now: datetime)` and the call
  site builds it directly; `_scan_ticker` stays (it is the base lane's one
  `_scan_one` call with the cache and the scan clock).
- **The soak report stays.** `scripts/perf/analysis_cache_soak_report.py`
  reads history and is named in the deploy doc; it writes nothing and
  imports nothing that this task deletes.

**Files:**
- Delete: `swingbot/core/scanning/cache_shadow.py`, `tests/scanning/test_cache_shadow.py`, `tests/scanning/test_cache_shadow_wiring.py`
- Modify: `swingbot/core/scanning/scan_run.py` (imports; V245-14's helpers; the analysis call site; the telemetry dict)
- Modify: `swingbot/core/scanning/structure.py` (`analysis_cache_mode` docstring, `cache_for_mode`)
- Modify: `swingbot/config.py` (the `ANALYSIS_CACHE` `Field`, `_MODE_VALUES`)
- Modify: `.env.example` (the `ANALYSIS_CACHE` comment)
- Modify: `tests/scanning/test_structure_cache.py`, `tests/scanning/test_analysis_cache_wiring.py`, `tests/scanning/test_analysis_cache_telemetry.py`
- Modify: `docs/claude/known-traps.md` (the v245 section's shadow bullet), `docs/deploy/DEPLOY_HETZNER.md` (the v245 row)

**Interfaces:**
- Consumes: V245-16's `on` date (deploy-doc row `on since <SWITCH_AT>`); V245-14's `_AnalysisCtx`, `_scan_ticker`, `_new_analysis_ctx`, `_shadow_sampled`, `_shadow_compare`, `_count_shadow`, `_shadow_telemetry`, `_SHADOW_LOCK`, `import threading`, `from . import cache_shadow`, the call-site line `analysis_ctx = _new_analysis_ctx(cache_mode, analysis_cache)` and the telemetry line `**_shadow_telemetry(analysis_ctx),`; V245-7's `structure.cache_for_mode`, the `ANALYSIS_CACHE` `Field`, `_MODE_VALUES["ANALYSIS_CACHE"]`, `.env.example` lines, `tests/scanning/test_structure_cache.py::test_cache_for_mode` / `test_config_fields_parse_and_fall_back`; V245-9's `test_analysis_cache_wiring.py::test_analysis_cache_follows_the_mode`; V245-12's `test_analysis_cache_telemetry.py::test_cache_summary_text`.
- Produces (ledger): `_MODE_VALUES["ANALYSIS_CACHE"] = ("off", "on")`; `_AnalysisCtx(mode, cache, scan_now)`.

- [ ] **Step 1: Check the gate (read-only)**

Count 10 trading days from the deploy doc's `on since <SWITCH_AT>` (weekdays
not in `NYSE_HOLIDAYS`; today counts only after 16:00 New York). Then:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py --get ANALYSIS_CACHE; grep -c 'analysis cache: \(building\|keying\) .* failed' logs/bot.log; grep -n 'Traceback' -A 12 logs/bot.log | grep -c 'structure.py\|scan_run.py'"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since <SWITCH_AT>" < scripts/perf/analysis_phase_report.py > logs/v245-on-10d-report.json
```

Expected: `on`; the failure count (listed, not a stop); a traceback count
of `0`; a report whose `p50` is in line with V245-16's. Fewer than 10
trading days, `.env` not `on`, or a cache traceback: stop and report, this
task waits (an incident restarts the 10 days once fixed). `logs/bot.log`
rotates: if the switch is older than the current file, also grep the
rotated files (`ls logs/bot.log*`).

- [ ] **Step 2: Rewrite the tests that name `shadow` (failing first)**

In `tests/scanning/test_structure_cache.py`, replace `test_cache_for_mode`
and extend `test_config_fields_parse_and_fall_back`, then add a removal pin
at the end of the file:

```python
def test_cache_for_mode(fresh):
    assert structure.cache_for_mode("off") is None
    assert structure.cache_for_mode("on") is fresh
    assert structure.cache_for_mode("shadow") is None      # removed in V245-17


def test_config_fields_parse_and_fall_back():
    fields = {f.attr: f for f in config.FIELDS}
    assert config._cast(fields["ANALYSIS_CACHE"], "ON") == "on"
    assert config._cast(fields["ANALYSIS_CACHE"], "bogus") == "off"
    assert config._cast(fields["ANALYSIS_CACHE"], "shadow") == "off"   # a stale .env value
    assert config._MODE_VALUES["ANALYSIS_CACHE"] == ("off", "on")
    assert [o if isinstance(o, str) else o[0] for o in fields["ANALYSIS_CACHE"].options] == ["off", "on"]
    assert fields["ANALYSIS_CACHE"].default == "off"
    assert isinstance(config._cast(fields["STRUCTURE_CACHE_MAX"], "250"), int)
    assert fields["ANALYSIS_CACHE"].hot_reloadable and fields["STRUCTURE_CACHE_MAX"].hot_reloadable


def test_the_shadow_scaffolding_is_gone():
    import importlib.util

    from swingbot.core.scanning import scan_run

    assert importlib.util.find_spec("swingbot.core.scanning.cache_shadow") is None
    for name in ("_new_analysis_ctx", "_shadow_sampled", "_shadow_compare", "_count_shadow",
                 "_shadow_telemetry", "_SHADOW_LOCK", "cache_shadow"):
        assert not hasattr(scan_run, name), name
    assert [f.name for f in scan_run._AnalysisCtx.__dataclass_fields__.values()] == [
        "mode", "cache", "scan_now"]
```

(Keep the rest of the existing `test_config_fields_parse_and_fall_back`
body if it has assertions beyond the ones above; V245-7 wrote exactly
these.)

In `tests/scanning/test_analysis_cache_wiring.py`, change the
`test_analysis_cache_follows_the_mode` parameters to

```python
@pytest.mark.parametrize("mode,expect", [("off", False), ("shadow", False), ("on", True)])
```

(a `shadow` that bypassed the cast gets no cache), and add, after it, the
`_scan_ticker` test that used to live in the deleted wiring file:

```python
@pytest.mark.parametrize("mode", ["off", "on"])
def test_scan_ticker_passes_the_cache_and_the_scan_clock(mode, monkeypatch):
    seen = []
    monkeypatch.setattr(analyze, "_scan_one", lambda t, df, **kw: seen.append(kw) or {"items": []})
    cache = StructureCache(4) if mode == "on" else None
    ctx = scan_run._AnalysisCtx(mode, cache, GOLDEN_NOW)
    assert scan_run._scan_ticker("T", object(), {"progress": "P"}, ctx) == {"items": []}
    (kwargs,) = seen
    assert kwargs["structure"] is cache and kwargs["now"] is GOLDEN_NOW and kwargs["progress"] == "P"
    assert "io" not in kwargs
```

(`analyze`, `scan_run`, `StructureCache` and `GOLDEN_NOW` are already
imported there by V245-9.)

In `tests/scanning/test_analysis_cache_telemetry.py`, change
`test_cache_summary_text`'s first assertion to the `on` mode:

```python
    assert scan_run._cache_summary("on", _warm(StructureCache(5))) == \
        "analysis cache on: 1 hit(s), 1 miss(es)"
```

Run:

```bash
python scripts/dev/testrun.py file tests/scanning/test_structure_cache.py
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_wiring.py
```

Expected: FAIL — `cache_for_mode("shadow")` returns the cache, `_cast`
keeps `shadow`, `cache_shadow` still imports, `_AnalysisCtx` has six
fields, and `_AnalysisCtx(mode, cache, GOLDEN_NOW)` misses `scan_seq`. The
wiring test needs the local Postgres for its scan-row tests: run
`/replicate-prod-db` first unless a sibling task in this session did.

- [ ] **Step 3: Delete the shadow module and its tests**

```bash
git rm swingbot/core/scanning/cache_shadow.py tests/scanning/test_cache_shadow.py tests/scanning/test_cache_shadow_wiring.py
```

- [ ] **Step 4: Shrink `scan_run.py`**

1. Remove `from . import cache_shadow`. Remove `import threading` if
   `git grep -n "threading" swingbot/core/scanning/scan_run.py` shows no
   other use.
2. Replace V245-14's `_AnalysisCtx`, `_SHADOW_LOCK`, `_new_analysis_ctx`,
   `_shadow_sampled`, `_scan_ticker`, `_shadow_compare`, `_count_shadow` and
   `_shadow_telemetry` with:

```python
@dataclass
class _AnalysisCtx:
    """The base lane's analysis settings for one scan (v245): the cache mode
    and cache read once, and one clock for every ticker."""
    mode: str
    cache: object
    scan_now: datetime


def _scan_ticker(ticker: str, df, scan_kwargs: dict, ctx: _AnalysisCtx) -> dict:
    """One base-lane `_scan_one` (v245) with the scan's cache and clock."""
    return analyze._scan_one(ticker, df, **scan_kwargs, structure=ctx.cache, now=ctx.scan_now)
```

3. At the analysis call site in `_sync_run_scan`, replace
   `analysis_ctx = _new_analysis_ctx(cache_mode, analysis_cache)   # ...` with:

```python
    analysis_ctx = _AnalysisCtx(cache_mode, analysis_cache, datetime.now(timezone.utc))  # one clock per scan (v245)
```

4. In the telemetry dict, delete the line `**_shadow_telemetry(analysis_ctx),`.
   Scan rows stop carrying `cache_compared`/`cache_diffs`; their readers
   use `.get` (V245-15's soak report reads only `shadow` rows).

- [ ] **Step 5: `structure.py`, `config.py`, `.env.example`**

In `swingbot/core/scanning/structure.py`:

```python
def analysis_cache_mode() -> str:
    """``ANALYSIS_CACHE`` as config parsed it: off | on."""
    return getattr(config, "ANALYSIS_CACHE", "off")


def cache_for_mode(mode: str) -> StructureCache | None:
    """The live cache for ``on``, synced to the current config; ``None``
    otherwise. Called once per scan, never per ticker."""
    if mode != "on":
        return None
    STRUCTURE_CACHE.sync_config(store_generation.generation("settings"),
                                getattr(config, "STRUCTURE_CACHE_MAX", DEFAULT_MAX_ENTRIES))
    return STRUCTURE_CACHE
```

In `swingbot/config.py`, the `ANALYSIS_CACHE` field becomes:

```python
    Field("ANALYSIS_CACHE", "ANALYSIS_CACHE", "Universe & Scanning", "Analysis prefix cache",
          type="select", default="off", options=["off", "on"],
          help="v245. on = work that is a pure function of the frame minus its last bar is "
               "cached per ticker; the last bar and the live price are recomputed every scan, so "
               "alerts are byte-identical to off. off is the rollback switch (same alerts, slower)."),
```

and in `_MODE_VALUES`: `"ANALYSIS_CACHE": ("off", "on"),`.

In `.env.example`, the two comment lines above `ANALYSIS_CACHE=off` become:

```bash
# v245 analysis prefix cache: off | on. Alerts are byte-identical in both;
# off is the rollback switch (slower scans).
```

- [ ] **Step 6: Nothing names the shadow any more**

```bash
git grep -n "cache_shadow\|analysis_cache_shadow\|_shadow_telemetry\|_new_analysis_ctx\|_SHADOW_LOCK\|scan_seq\|cache_compared" -- swingbot tests .env.example
git grep -n "shadow" -- swingbot/core/scanning/structure.py
```

Expected: no output from either (the soak report under `scripts/perf/` and
its test keep `cache_compared`; docs keep the history).

- [ ] **Step 7: Run the tests and the gate**

```bash
python scripts/dev/testrun.py file tests/scanning/test_structure_cache.py
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_wiring.py
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_telemetry.py
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_property.py
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
python scripts/dev/testrun.py file tests/scanning/test_mtf_gate.py
python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py
python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS, `0 failed`, `0 xfailed`; the golden unchanged (a golden
failure here is a behaviour change: stop and report, never regenerate);
`_sync_run_scan` at or below 94.

- [ ] **Step 8: Commit the code**

```bash
git add swingbot/core/scanning/scan_run.py swingbot/core/scanning/structure.py swingbot/config.py .env.example tests/scanning/test_structure_cache.py tests/scanning/test_analysis_cache_wiring.py tests/scanning/test_analysis_cache_telemetry.py
git commit -m "refactor(v245): remove the analysis cache shadow mode, leaving off|on (V245-17)"
```

(The `git rm` from Step 3 is staged and lands in this commit.)

- [ ] **Step 9: Align the docs**

In `docs/claude/known-traps.md`, section `## Analysis prefix cache (v245):
exact, and rollback by off only before growth`, replace the `**Shadow
mode**` bullet with:

```markdown
- **No shadow mode.** `shadow` (the soak's uncached comparison) was removed
  in V245-17; a stale `ANALYSIS_CACHE=shadow` in `.env` reads as `off` with
  an `invalid ANALYSIS_CACHE` warning, so a "slow again" bot after an
  `.env` restore is this first.
```

Run `python scripts/dev/doc_section.py docs/claude/known-traps.md "Analysis prefix cache (v245): exact, and rollback by off only before growth"`
(prints the section). `AGENTS.md`'s topic line names no mode, so it stays.

```bash
git add docs/claude/known-traps.md
git commit -m "docs(v245): known trap reflects the removed shadow mode (V245-17)"
```

- [ ] **Step 10: Controller — deploy, then remove the jsonl (mirror-prod)**

Before deploying, re-check `python3 scripts/ops/env_set.py --get
ANALYSIS_CACHE` reads `on` on the VM (a stale `shadow` would silently run
`off` after this deploy). The controller merges and deploys per
`docs/deploy/DEPLOY_HETZNER.md`. After two scans (read-only; the scratch
helper is V245-15 Step 6's):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - 2" < "$SCRATCH/v245_rows.py"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && grep -c 'invalid ANALYSIS_CACHE' logs/bot.log"
```

Expected: both rows `on` with integer hits and `None` for
`cache_compared`/`cache_diffs` (keys absent); the warning count `0`.

Then run the `mirror-prod` skill. The change, in one sentence: delete the
now-unwritten `logs/analysis_cache_shadow.jsonl*` on the VM (their content
is summarised in the spec's `## Results`).

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && ls -l logs/analysis_cache_shadow.jsonl* 2>/dev/null; rm -f logs/analysis_cache_shadow.jsonl*; ls logs | grep -c analysis_cache_shadow"
```

Expected: the listing (possibly empty), then `0`. Mirror it: in
`docs/deploy/DEPLOY_HETZNER.md`, `### v245 analysis cache rollout`, append
to the `ANALYSIS_CACHE` row's `Set` cell `; shadow mode removed <deploy
date> (V245-17), logs/analysis_cache_shadow.jsonl* deleted`.

```bash
git add docs/deploy/DEPLOY_HETZNER.md
git commit -m "docs(v245): shadow mode removed in production, jsonl deleted (V245-17)"
```

Report to the controller: V245-17 done, `/close-out` follows (the bot
patch bump per index Decision 9, skills citing `cache_shadow` or `shadow`
for this cache aligned in close-out Step 5b).
