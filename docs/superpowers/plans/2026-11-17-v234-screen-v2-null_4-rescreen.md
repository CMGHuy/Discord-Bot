# v234 — Screen v2 null: Part 4, the one-shot re-screen

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md), A3–A5, Constraints and Testing.

Read the [index](2026-11-17-v234-screen-v2-null_0-index.md) for the Goal, architecture, global constraints, task ledger and sequential edges. This part consumes V234-9's `with_event_clause` and all preceding v2 contracts. It creates the limited re-screen route, its safeguards and the batch record; it does not implement Parts B or C.

## Parallelisation

V234-10 → V234-10b → V234-11 → V234-12 is sequential: the hook pins the policy module, and the measurement requires the code, hook and dated methodology exception committed together in the implementation checkout. All tasks here require V234-8 to record **ACCEPT** first. The unresolved `p_month_turn` refusal in the index Handoff is not acceptance. A STOP, refusal or missing gate result blocks execution of this entire part; writing the plan grants no measurement permission.

# Phase 4 — Re-screen policy, safeguards and the batch

### Task V234-10: Re-screen policy, run marker and the summary script
**Model:** sonnet — the frozen one-shot policy and reporting contract stay inside the screen package.

**Prerequisite:** V234-8 records ACCEPT and V234-9 is committed. Only synthetic fixtures run during this task. Read `writing-plans`' interfaces through this task; load `backtest-gate` before any later measurement.

**Files:**
- Create: `swingbot/core/backtesting/screen/rescreen.py`
- Create: `tests/backtesting/screen/test_rescreen.py`
- Create: `scripts/backtest/rescreen_summary.py`
- Modify: `tests/backtesting/instrument/test_date_literal_guard.py`

**Interfaces:** consumes `stats.load_ledger(path)`, `stats.ledger_qvalues(rows)`, `screen_idea.ledger_row`, `publish`, `_run_info`, `_run_screens`, `refusal`, `build_parser`, `_mode_runner`, `_utf8_stdout`, `record_path` (brief and `git grep` verified), plus V234-9's `with_event_clause(..., gating=not args.rescreen_v1)`. Creates the ledger's `RESCREEN_V1`, `RESCREEN_PREFIX`, `rescreen_id`, `v1_row`, `rescreen_refusal`, `rescreen_hypothesis`, `RunMarker`, `MEANS_RE`, `summary_rows`, `render_summary` and `rescreen_summary.main`. Private helpers below are created here. No existing signature changes; `ledger_id(name)` keeps returning `screen-<name>`.

- [ ] **Step 1: Write the policy and crash tests**

Create `tests/backtesting/screen/test_rescreen.py`:

```python
import json

import pytest

from swingbot.core.backtesting.screen import rescreen as rs


def old(name="high52w"):
    return {"id": f"screen-{name}", "instrument": "screen-v1",
            "verdict": "SCREEN-FAIL", "record": f"old-{name}.md"}


def test_only_the_twelve_original_rows_are_licensed(tmp_path):
    assert len(rs.RESCREEN_V1) == len(set(rs.RESCREEN_V1)) == 12
    assert rs.RESCREEN_V1[0] == "high52w"
    assert rs.RESCREEN_V1[-1] == "fvg_overhead_aged"
    for name in rs.RESCREEN_V1:
        assert rs.rescreen_refusal(name, [old(name)], tmp_path) is None
    assert rs.rescreen_refusal("range_breakdown_stop", [], tmp_path)
    assert rs.rescreen_refusal("high52w", [], tmp_path)
    wrong = {**old(), "instrument": "screen-v2"}
    assert rs.v1_row([wrong], "high52w") is None


def test_row_or_any_dated_result_spends_the_shot(tmp_path):
    rows = [old(), {"id": "screen2-high52w"}]
    assert "already" in rs.rescreen_refusal("high52w", rows, tmp_path)
    (tmp_path / "2099-01-01-screen2-high52w.md").write_text("read")
    assert "result" in rs.rescreen_refusal("high52w", [old()], tmp_path)
    assert "screen-high52w" in rs.rescreen_hypothesis("base", old())
    assert "old-high52w.md" in rs.rescreen_hypothesis("base", old())


def test_marker_allows_one_crash_restart_and_records_it(tmp_path):
    first = rs.RunMarker(tmp_path)
    assert first.start() is None
    assert first.crash_note() is None
    first.close()  # process loss releases its OS lock, leaves attempt 1 unfinished
    retry = rs.RunMarker(tmp_path)
    assert retry.start() is None
    assert "attempt 1" in retry.crash_note()
    assert json.loads((tmp_path / "crash.json").read_text())["attempt"] == 1
    retry.close()
    third = rs.RunMarker(tmp_path)
    assert "retry" in third.start()
    third.close()


def test_marker_rejects_live_owner_and_completed_run(tmp_path):
    first, other = rs.RunMarker(tmp_path), rs.RunMarker(tmp_path)
    assert first.start() is None
    assert "active" in other.start()
    other.close()
    first.finish()
    assert "completed" in rs.RunMarker(tmp_path).start()


def test_corrupt_marker_fails_closed(tmp_path):
    (tmp_path / "run-marker.json").write_text("not json")
    marker = rs.RunMarker(tmp_path)
    assert "unreadable" in marker.start()
    marker.close()


def test_summary_uses_each_record_and_discloses_missing_old_means(tmp_path):
    rows = []
    for name in rs.RESCREEN_V1:
        before = old(name)
        after = {"id": rs.rescreen_id(name), "instrument": "screen-v2",
                 "verdict": "SCREEN-PASS", "record": f"new-{name}.md"}
        (tmp_path / before["record"]).write_text("Old report without arms.\n")
        (tmp_path / after["record"]).write_text(
            "Mean R_event +0.1234R; mean R_null (each event's null mean, "
            "averaged) -0.0500R. Both after costs.\n")
        rows.extend((before, after))
    result = rs.summary_rows(rows, tmp_path)
    assert len(result) == 12
    assert result[0]["v1_event"] is None
    assert result[0]["v2_event"] == pytest.approx(0.1234)
    assert result[0]["v2_null"] == pytest.approx(-0.05)
    text = rs.render_summary(result, date="2099-01-02")
    assert "not recorded" in text and "supersedes" in text
    assert "SCREEN-FAIL" in text and "SCREEN-PASS" in text
    with pytest.raises(ValueError, match="missing"):
        rs.summary_rows(rows[:-1], tmp_path)
```

Run `python scripts/dev/testrun.py file tests/backtesting/screen/test_rescreen.py`; expect import failure for the new module.

- [ ] **Step 2: Implement the policy and persistent attempt record**

Create `swingbot/core/backtesting/screen/rescreen.py`. The file lock prevents a second process mistaking an active run for a crash; closing it does not erase attempts. An unreadable marker never grants a new shot. The same checkpoint directory must be retained on restart (the batch runbook pins it per idea).

```python
"""v230 A5: the dated twelve-idea exception; no measurement logic."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

RESCREEN_V1 = (
    "high52w", "uptrend_pullback", "gap_volume", "turn_of_month",
    "bond_spike_rebound", "dollar_drop", "sweep_reclaim_bos", "turtle_soup",
    "range_breakdown_close", "shock_support_break_short",
    "shock_failed_bounce_short", "fvg_overhead_aged",
)
RESCREEN_PREFIX = "screen2-"


def rescreen_id(name):
    return RESCREEN_PREFIX + name


def v1_row(rows, name):
    return next((r for r in rows if r["id"] == f"screen-{name}"
                 and r.get("instrument") == "screen-v1"), None)


def rescreen_refusal(name, rows, results_dir):
    if name not in RESCREEN_V1:
        return "--rescreen-v1 is limited to the twelve v230 A5 names"
    if v1_row(rows, name) is None:
        return f"missing screen-v1 row: screen-{name}"
    ident = rescreen_id(name)
    if any(r["id"] == ident for r in rows):
        return f"{ident} already in the ledger: one shot"
    if any(Path(results_dir).glob(f"*-{ident}.md")):
        return f"{ident} result exists: shot spent even without its ledger row"
    return None


def rescreen_hypothesis(base, v1):
    return (f"{base}; v230 partner decision 2 (2026-11-16), once under screen-v2; "
            f"supersedes {v1['id']} ({v1['record']}); frozen first-run definition")


def _write_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _lock_file(path):
    stream = path.open("a+b")
    try:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise
    return stream


class RunMarker:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "run-marker.json"
        self.lock = None
        self.state = None

    def start(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            self.lock = _lock_file(self.directory / "run.lock")
        except OSError:
            return "run already active or marker lock unavailable"
        try:
            reason = self._begin()
        except (OSError, ValueError, TypeError, KeyError):
            reason = "unreadable run marker; inspect it, never reset the shot"
        if reason:
            self.close()
        return reason

    def _begin(self):
        previous = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else None
        if previous is not None:
            if previous["status"] == "complete":
                return "run completed; no second shot"
            if previous["status"] != "running" or previous["attempt"] not in (1, 2):
                return "unreadable run marker"
            if previous["attempt"] == 2:
                return "one crash retry already spent"
            _write_json(self.directory / "crash.json", previous)
        self.state = {"attempt": 1 if previous is None else 2, "status": "running",
                      "started_utc": datetime.now(timezone.utc).isoformat()}
        _write_json(self.path, self.state)
        return None

    def crash_note(self):
        path = self.directory / "crash.json"
        if not path.exists():
            return None
        previous = json.loads(path.read_text(encoding="utf-8"))
        return (f"Resumed once after unfinished attempt {previous['attempt']} "
                f"started {previous['started_utc']}; same checkpoints and frozen inputs.")

    def finish(self):
        _write_json(self.path, {**self.state, "status": "complete"})
        self.close()

    def close(self):
        if self.lock is not None:
            self.lock.close()
            self.lock = None
```

`finish()` is called only after both results and ledger writes succeed. `close()` in a `finally` releases only the OS lock; it never calls `finish()` on an exception or a refused run. A result written before a ledger failure already spends the shot through `rescreen_refusal`; do not erase it to resume. The marker contains no invented crash cause; its timestamp and unfinished state are the evidence.

- [ ] **Step 3: Add the read-only summary and CLI**

Append to `rescreen.py`. Parse the existing exact arm-means sentence, never reconstruct a missing historical mean from rounded delta. Missing old means are disclosed; missing v2 means or either record fail the final summary. `record` remains a repository path in the ledger; `results_dir` selects its basename for isolated fixtures and relocated results directories.

```python
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
MEANS_RE = re.compile(
    rf"Mean R_event (?P<event>{_NUMBER})R; mean R_null \(each event's\s+"
    rf"null mean, averaged\) (?P<null>{_NUMBER})R\.")


def _means(row, results_dir, required):
    path = Path(results_dir) / Path(row["record"]).name
    text = path.read_text(encoding="utf-8")
    match = MEANS_RE.search(text)
    if match is None:
        if required:
            raise ValueError(f"missing arm means in {path}")
        return None, None
    return float(match["event"]), float(match["null"])


def summary_rows(rows, results_dir):
    by_id = {r["id"]: r for r in rows}
    result = []
    for name in RESCREEN_V1:
        before, after = v1_row(rows, name), by_id.get(rescreen_id(name))
        if before is None or after is None or after.get("instrument") != "screen-v2":
            raise ValueError(f"missing original or screen-v2 row for {name}")
        old_event, old_null = _means(before, results_dir, False)
        new_event, new_null = _means(after, results_dir, True)
        result.append({"idea": name, "v1_verdict": before["verdict"],
                       "v2_verdict": after["verdict"], "v1_event": old_event,
                       "v1_null": old_null, "v2_event": new_event, "v2_null": new_null,
                       "v1_record": before["record"], "v2_record": after["record"]})
    return result


def _mean_text(value):
    return "not recorded" if value is None else f"{value:+.4f}R"


def render_summary(rows, *, date):
    lines = [f"# v230 re-screen summary — {date}", "",
             "The screen-v2 verdict supersedes screen-v1 for licensing. A v2 pass "
             "earns the replication ladder only; no funnel row is reopened.", "",
             "The fifth clause is reported-only for edge-mode re-screens and absent "
             "in avoid mode. Missing historical means are not recorded; no old run "
             "was repeated to fill them. Means below are transcribed from the linked "
             "results, not estimates of the live book.", "",
             "| Idea | v1 verdict | v2 verdict | v1 event | v1 null | v2 event | v2 null |",
             "|---|---|---|---|---|---|---|"]
    for row in rows:
        values = [_mean_text(row[key]) for key in
                  ("v1_event", "v1_null", "v2_event", "v2_null")]
        lines.append(f"| {row['idea']} | [{row['v1_verdict']}]({Path(row['v1_record']).name}) "
                     f"| [{row['v2_verdict']}]({Path(row['v2_record']).name}) | "
                     + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"
```

Create `scripts/backtest/rescreen_summary.py`; script bootstrap follows `screen_idea.py` and adds no replay window:

```python
"""Render the twelve completed v230 re-screens; never run a screen."""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import rescreen
import screen_idea


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=screen_idea._iso_day, default=date.today().isoformat())
    parser.add_argument("--ledger", type=Path, default=stats.LEDGER_PATH)
    parser.add_argument("--results-dir", type=Path, default=screen_idea.RESULTS_DIR)
    args = parser.parse_args(argv)
    screen_idea._utf8_stdout()
    try:
        rows = rescreen.summary_rows(stats.load_ledger(args.ledger), args.results_dir)
    except (OSError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    path = args.results_dir / f"{args.date}-v230-rescreen-summary.md"
    path.write_text(rescreen.render_summary(rows, date=args.date), encoding="utf-8", newline="\n")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Add `"scripts/backtest/rescreen_summary.py": "v230 reports existing ledger rows only; runs no replay"` to `NO_REPLAY` in `tests/backtesting/instrument/test_date_literal_guard.py`.

- [ ] **Step 4: Verify and commit the policy module**

Run `python scripts/dev/testrun.py file tests/backtesting/screen/test_rescreen.py`, `python scripts/dev/testrun.py file tests/backtesting/instrument/test_date_literal_guard.py` and `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`. Run `python scripts/dev/complexity_gate.py`. Expected: 0 failed, 0 xfailed; this task opens no run path. V234-10b tests the CLI and screen publication wiring.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/rescreen.py scripts/backtest/rescreen_summary.py tests/backtesting/screen/test_rescreen.py tests/backtesting/instrument/test_date_literal_guard.py
git commit -m "feat(v234): define the re-screen policy and bounded crash retry"
```

### Task V234-10b: Wire the re-screen flag and publication lifecycle
**Model:** sonnet — thin script wiring consumes the policy and existing fifth-clause contract.

Split from V234-10 because the combined task exceeded 20 KB. Requires V234-10 and V234-9, and an explicit V234-8 ACCEPT. No real runs in this task.

**Files:**
- Modify: `scripts/backtest/screen_idea.py`
- Create: `tests/backtest_scripts/test_screen_rescreen.py`

**Interfaces:** consumes V234-10's `rescreen.rescreen_id`, `v1_row`, `rescreen_refusal`, `rescreen_hypothesis`, `RunMarker.start/finish/crash_note/close`, and `rescreen_summary.main`; V234-9's fifth-clause routing already reads `args.rescreen_v1`. Produces `--rescreen-v1`, `_is_rescreen(args)`, `_result_id(args)`, `_rescreen_options(args)`, `_shot_refusal(args, rows)`, `_rescreen_row(args, row, rows)`, `_rescreen_text(args, text, rows)` and `_execute_screen(args, idea, universe, rows, data, spy)`. Existing script signatures stay unchanged; V234-11 consumes only the public flag/policy names.

**Test-first order:** write the complete test file in Step 2 before applying Step 1's code; run `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_rescreen.py`, expecting the unknown flag and missing `_execute_screen` failures.

- [ ] **Step 1: Wire the flag, identities and attempt lifecycle**

Import `rescreen` with the other screen modules. Add `p.add_argument("--rescreen-v1", action="store_true", help="v230: once for the twelve frozen screen-v1 ideas")` in `build_parser`. Add these helpers:

```python
def _is_rescreen(args):
    return getattr(args, "rescreen_v1", False)


def _result_id(args):
    return rescreen.rescreen_id(args.idea) if _is_rescreen(args) else ledger_id(args.idea)


def _rescreen_options(args):
    if NULL_VERSION != "v2":
        return "--rescreen-v1 requires null v2"
    if args.count_only or args.pin_context:
        return "--rescreen-v1 cannot accompany --count-only or --pin-context"
    if not args.dry_run and args.checkpoint_dir is None:
        return "--rescreen-v1 needs --checkpoint-dir"
    return None


def _shot_refusal(args, rows):
    if _is_rescreen(args):
        return (_rescreen_options(args) or
                rescreen.rescreen_refusal(args.idea, rows, args.results_dir))
    if any(row["id"] == ledger_id(args.idea) for row in rows):
        return (f"{ledger_id(args.idea)} is already in the ledger: one shot per idea; "
                "a changed parameter is a new idea with a new name")
    return None


def _rescreen_row(args, row, rows):
    if not _is_rescreen(args):
        return row
    original = rescreen.v1_row(rows, args.idea)
    return {**row, "id": _result_id(args),
            "hypothesis": rescreen.rescreen_hypothesis(row["hypothesis"], original)}


def _rescreen_text(args, text, rows):
    if not _is_rescreen(args):
        return text
    original = rescreen.v1_row(rows, args.idea)
    note = getattr(args, "rescreen_crash_note", None) or "No crash restart."
    return (text + f"\n## Re-screen provenance\n\nSupersedes `{original['id']}` "
            f"({original['record']}); partner decision 2, 2026-11-16. "
            f"Original definition, race, mode, cap, window, universe, source and costs frozen.\n\n{note}\n")


def _execute_screen(args, idea, universe, rows, data, spy):
    marker = None
    if _is_rescreen(args) and not args.dry_run:
        marker = rescreen.RunMarker(args.checkpoint_dir)
        reason = marker.start()
        if reason:
            print(f"refused: {reason}", file=sys.stderr)
            return 2
    try:
        if marker is not None:
            args.rescreen_crash_note = marker.crash_note()
        summary = _run_screens(args, idea, universe, data, spy)
        code = publish(args, idea, universe, summary, rows, data=data)
        if code == 0 and marker is not None:
            marker.finish()
        return code
    except null_v2.NullRefusal as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    finally:
        if marker is not None:
            marker.close()
```

Keep every existing window and ticker check at the start of `refusal`; replace only its old-id duplicate check and final `return None` with `return _shot_refusal(args, rows)`. In `main`, check `_rescreen_options(args)` before `_mode_runner` when `_is_rescreen(args)`; return 2 with `refused:` on failure, so count-only and pin-context cannot bypass the policy. Replace the final V234-7b try/except/run/publish block with `return _execute_screen(args, IDEAS[args.idea], universe, rows, data, spy)`; this keeps `main` under 15.

In `publish` use `path = Path(args.results_dir) / f"{args.date}-{_result_id(args)}.md"`; build `row = _rescreen_row(args, ledger_row(idea, v, record_path(path), args.date), rows)` before validation and BH q. Render through `text = _rescreen_text(args, render_results(idea, summary, universe, run), rows)`. In `_run_info` change only the id value to `_result_id(args)`. Leave write-doc-before-append ordering intact. V234-9 already makes the fifth clause reported-only through the parsed flag; do not apply it twice.

- [ ] **Step 2: Test wiring with synthetic summaries and ledger bytes**

Create `tests/backtest_scripts/test_screen_rescreen.py`. These tests mock the expensive pipeline, but exercise real publication and ledger append. The verdict comes from synthetic paired rows; no cache is read.

```python
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import screen_idea as si
import rescreen_summary
from swingbot.core.backtesting.screen import rescreen, verdict


def _args(tmp_path, *extra):
    return si.build_parser().parse_args([
        "--idea", "high52w", "--rescreen-v1", "--results-dir", str(tmp_path),
        "--ledger", str(tmp_path / "ledger.jsonl"),
        "--checkpoint-dir", str(tmp_path / "checkpoint"), *extra])


def _row():
    return {"id": "screen-high52w", "instrument": "screen-v1", "date": "2026-10-08",
            "hypothesis": "frozen", "n": 0, "exp_r": None, "p": None,
            "verdict": "SCREEN-UNDERPOWERED", "record": "old.md", "data_source": "yfinance"}


def test_publish_keeps_original_bytes_and_uses_new_id(tmp_path, monkeypatch):
    args, before = _args(tmp_path), json.dumps(_row()) + "\n"
    args.ledger.write_text(before, encoding="utf-8", newline="\n")
    monkeypatch.setattr(si, "NULL_VERSION", "v2")
    monkeypatch.setattr(si, "render_results", lambda idea, summary, universe, run:
                        f"id={run['ledger_id']}; instrument={run['instrument']}\n")
    monkeypatch.setattr(si, "_context_hash_refusal", lambda *a: None)
    monkeypatch.setattr(si, "_pin_context_hashes", lambda *a: None)
    summary = {"verdict": verdict.decide([], n_resamples=20)}
    assert si.publish(args, si.IDEAS["high52w"], None, summary, [_row()]) == 0
    content = args.ledger.read_bytes()
    assert content.startswith(before.encode())
    after = json.loads(content.splitlines()[-1])
    assert after["id"] == "screen2-high52w" and after["instrument"] == "screen-v2"
    assert "screen-high52w" in after["hypothesis"]
    doc = (tmp_path / f"{args.date}-screen2-high52w.md").read_text(encoding="utf-8")
    assert "id=screen2-high52w" in doc and "No crash restart" in doc
    assert si.refusal(args, [_row(), after])


def test_real_rescreen_needs_checkpoint_and_cannot_use_other_modes(tmp_path, monkeypatch):
    monkeypatch.setattr(si, "NULL_VERSION", "v2")
    args = _args(tmp_path)
    args.checkpoint_dir = None
    assert "checkpoint" in si.refusal(args, [_row()])
    for flag in ("--count-only", "--pin-context"):
        assert si.main(["--idea", "high52w", "--rescreen-v1", flag]) == 2


def test_execute_releases_lock_but_preserves_crash(tmp_path, monkeypatch):
    args = _args(tmp_path)
    monkeypatch.setattr(si, "_run_screens", lambda *a: (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(RuntimeError, match="crash"):
        si._execute_screen(args, si.IDEAS[args.idea], None, [_row()], None, None)
    monkeypatch.setattr(si, "_run_screens", lambda *a: {})
    monkeypatch.setattr(si, "publish", lambda *a, **k: 0)
    assert si._execute_screen(args, si.IDEAS[args.idea], None, [_row()], None, None) == 0
    assert "attempt 1" in args.rescreen_crash_note
    assert si._execute_screen(args, si.IDEAS[args.idea], None, [_row()], None, None) == 2


def test_summary_cli_writes_only_after_complete_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(rescreen_summary.stats, "load_ledger", lambda path: [])
    argv = ["--results-dir", str(tmp_path), "--date", "2099-01-02"]
    assert rescreen_summary.main(argv) == 2
    assert not list(tmp_path.glob("*summary.md"))
    monkeypatch.setattr(rescreen, "summary_rows", lambda rows, directory: [])
    assert rescreen_summary.main(argv) == 0
    assert (tmp_path / "2099-01-02-v230-rescreen-summary.md").exists()
```

Run `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_rescreen.py`, then `tests/backtest_scripts/test_screen_v2_wiring.py` (fifth-clause routing), `tests/backtesting/instrument/test_date_literal_guard.py` and `tests/backtesting/screen/test_import_guard.py`, each through `python scripts/dev/testrun.py file <path>`. Run `python scripts/dev/complexity_gate.py`. Expected: 0 failed, 0 xfailed; no real measurement. Use a separate subprocess crash fixture if the OS lock test exposes platform-specific lock lifetime; never weaken the live-owner refusal.

- [ ] **Step 3: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_rescreen.py
git commit -m "feat(v234): license the one-shot v1 batch and record crash resumes"
```

### Task V234-11: Guardrail: one --rescreen-v1 run per licensed name
**Model:** sonnet — a narrow, test-pinned widening of a stdlib hook plus doc and mirror edits whose wording is fixed below.

Split from the ledger's single V234-11 because the combined task passed 20 KB; V234-11b carries the methodology doc, the skill and the Codex mirror.

**Prerequisite:** V234-8 records ACCEPT; V234-10 and V234-10b are committed in the worktree (the drift test imports `rescreen.RESCREEN_V1`, the parity test reads `screen_idea.build_parser()` with `--rescreen-v1`). No real screen run, dry run or `--count-only` in this task.

**Files:**
- Modify: `.claude/hooks/guardrails.py` (the screen block, lines 304–570 today: constants, `_screen_flags`, `_screen_ledger_row`, `_screen_results_doc`, `_screen_deny_reason`)
- Modify: `tests/hooks/test_guardrails.py` (two flag-dict tests updated, a v234 block appended)
- Verify only: `.codex/hooks.json` (it registers `python .claude/hooks/guardrails.py`, the same file; no registration changes, so it is not edited)

**Interfaces:**
- Consumes: `rescreen.RESCREEN_V1`, `rescreen.RESCREEN_PREFIX` (V234-10); `screen_idea.build_parser()` with `--rescreen-v1` and `--checkpoint-dir` (V234-10b; `--checkpoint-dir` exists today at `screen_idea.py:1031`).
- Produces: `guardrails._RESCREEN_V1: tuple[str, ...]`, `_RESCREEN_PREFIX = "screen2-"`, `"--rescreen-v1"` in `_SCREEN_FLAG_OPTIONS`, `"--checkpoint-dir"` in `_SCREEN_OPTIONS` (value key `checkpoint_dir`), `flags["rescreen_v1"]`, `flags["checkpoint_dir"]`, `_ledger_row(ident) -> dict | None`, `_results_doc(ident) -> str | None`, `_screen_dry_run_reason(flags) -> str | None`, `_screen_paths_reason(flags) -> str | None`, `_rescreen_record_reason(idea) -> str | None`, `_rescreen_deny_reason(flags) -> str | None`. V234-12 relies on the hook allowing exactly one real `--rescreen-v1` run per licensed name.

Abbreviation note: with `--rescreen-v1` beside `--results-dir`, `--re`/`--res` become ambiguous in the hook **and** in argparse (both refuse them), so the existing abbreviation test moves to `--resu`. `--c` was already ambiguous; `--ch` now resolves to `--checkpoint-dir`, `--co` still to `--count-only`.

- [ ] **Step 1: Write the failing hook tests**

In `tests/hooks/test_guardrails.py`, update the two exact flag dicts: in `test_screen_flags_read_every_checked_option` and `test_screen_flags_resolve_unique_abbreviations_like_argparse` add `"rescreen_v1": False, "checkpoint_dir": None` to the expected dict, and in the second test replace the token `"--res=r"` with `"--resu=r"`. Then append:

```python
# --- v234: --rescreen-v1, the twelve v230 A5 names once each -----------------

_RESCREEN = (f"{_SCREEN} --idea high52w --rescreen-v1 "
             "--checkpoint-dir logs/v230-rescreen/high52w")


def _v1_screened(results, *extra_rows, idea="high52w", instrument="screen-v1"):
    """`idea` screened under v1: its row, its doc, plus any extra rows."""
    record = f"docs/superpowers/results/2026-10-08-screen-{idea}.md"
    _ledger_rows(results, {"id": f"screen-{idea}", "instrument": instrument,
                           "date": "2026-10-08", "verdict": "SCREEN-FAIL",
                           "record": record}, *extra_rows)
    (results / f"2026-10-08-screen-{idea}.md").write_text("# r\n", encoding="utf-8")


def test_rescreen_names_match_the_policy_module():
    from swingbot.core.backtesting.screen import rescreen
    assert guardrails._RESCREEN_V1 == rescreen.RESCREEN_V1
    assert guardrails._RESCREEN_PREFIX == rescreen.RESCREEN_PREFIX


def test_every_hook_screen_option_is_a_real_screen_option(monkeypatch):
    monkeypatch.syspath_prepend(str(_REPO_ROOT / "scripts" / "backtest"))
    import screen_idea
    real = set(screen_idea.build_parser()._option_string_actions)
    assert set(guardrails._SCREEN_OPTIONS) <= real


def test_screen_flags_read_the_rescreen_flag_and_checkpoint_dir():
    flags = guardrails._screen_flags(
        ["python", "screen_idea.py", "--idea", "x", "--resc", "--ch", "c"])
    assert flags["rescreen_v1"] is True and flags["checkpoint_dir"] == "c"


def test_a_first_rescreen_of_a_licensed_idea_is_allowed(screen_repo):
    _v1_screened(screen_repo)
    assert _bash(_RESCREEN) is None
    assert _bash(_RESCREEN.replace("--rescreen-v1", "--resc")) is None


def test_the_plain_rerun_of_a_licensed_idea_stays_denied(screen_repo):
    _v1_screened(screen_repo)
    assert "already in the ledger" in _screen_denial(f"{_SCREEN} --idea high52w")


def test_a_thirteenth_name_is_denied(screen_repo):
    _v1_screened(screen_repo, idea="range_breakdown_stop")
    reason = _screen_denial(_RESCREEN.replace("high52w", "range_breakdown_stop"))
    assert "twelve" in reason


def test_a_rescreen_needs_the_original_screen_v1_row(screen_repo):
    assert "screen-v1 row" in _screen_denial(_RESCREEN)
    _v1_screened(screen_repo, instrument="screen-v2")
    assert "screen-v1 row" in _screen_denial(_RESCREEN)


def test_a_rescreen_is_one_shot_by_row(screen_repo):
    _v1_screened(screen_repo, {"id": "screen2-high52w", "date": "2026-11-20",
                               "verdict": "SCREEN-FAIL", "record": "r.md"})
    reason = _screen_denial(_RESCREEN)
    assert "screen2-high52w is already in the ledger (2026-11-20" in reason


def test_a_rescreen_doc_without_a_row_spends_the_shot(screen_repo):
    _v1_screened(screen_repo)
    (screen_repo / "2026-11-20-screen2-high52w.md").write_text("# r\n", encoding="utf-8")
    reason = _screen_denial(_RESCREEN)
    assert "2026-11-20-screen2-high52w.md exists with no ledger row" in reason


def test_a_real_rescreen_needs_a_checkpoint_dir(screen_repo):
    _v1_screened(screen_repo)
    cmd = f"{_SCREEN} --idea high52w --rescreen-v1"
    assert "--checkpoint-dir" in _screen_denial(cmd)


def test_a_rescreen_keeps_the_default_ledger_and_results_dir(screen_repo):
    _v1_screened(screen_repo)
    _screen_denial(f"{_RESCREEN} --ledger fresh.jsonl")
    _screen_denial(f"{_RESCREEN} --results-dir elsewhere")


def test_a_rescreen_with_count_only_is_denied(screen_repo):
    _v1_screened(screen_repo)
    assert "--count-only" in _screen_denial(f"{_RESCREEN} --count-only")


def test_a_rescreen_dry_run_follows_the_smoke_rule(screen_repo):
    _v1_screened(screen_repo)
    smoke = f"{_SCREEN} --idea high52w --rescreen-v1 --dry-run"
    assert _bash(f"{smoke} --tickers AAPL,MSFT") is None
    _screen_denial(smoke)
    _screen_denial(f"{smoke} --tickers A,B,C,D")

```

Run `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`. Expected: the new tests and the two updated dict tests FAIL (`_RESCREEN_V1` missing, unknown flag keys); every other test passes.

- [ ] **Step 2: Widen the hook narrowly**

In `.claude/hooks/guardrails.py` replace the option constants (lines 316–322) with:

```python
#: Valueless screen flags (v182: --count-only beside --dry-run; v234: --rescreen-v1).
_SCREEN_FLAG_OPTIONS = ("--dry-run", "--count-only", "--rescreen-v1")
_SCREEN_OPTIONS = ("--idea", "--cache-dir", "--membership", "--start", "--end",
                   "--date", "--ledger", "--results-dir", "--tickers",
                   "--checkpoint-dir", *_SCREEN_FLAG_OPTIONS)
_SCREEN_VALUE_KEYS = {"--idea": "idea", "--ledger": "ledger",
                      "--results-dir": "results_dir",
                      "--checkpoint-dir": "checkpoint_dir"}
#: v230 partner decision 2 (2026-11-16): the twelve screen-v1 rows, re-screened
#: once each under screen-v2. A copy of rescreen.RESCREEN_V1 (this hook is
#: stdlib-only); tests/hooks/test_guardrails.py pins the two equal.
_RESCREEN_V1 = (
    "high52w", "uptrend_pullback", "gap_volume", "turn_of_month",
    "bond_spike_rebound", "dollar_drop", "sweep_reclaim_bos", "turtle_soup",
    "range_breakdown_close", "shock_support_break_short",
    "shock_failed_bounce_short", "fvg_overhead_aged",
)
_RESCREEN_PREFIX = "screen2-"
```

In `_screen_flags`, the initial dict becomes:

```python
    flags = {"idea": None, "dry_run": False, "count_only": False, "tickers": False,
             "ticker_count": 0, "ledger": None, "results_dir": None,
             "rescreen_v1": False, "checkpoint_dir": None}
```

(`flags[opt[2:].replace("-", "_")] = True` already maps `--rescreen-v1` to `rescreen_v1`.)

Replace `_screen_ledger_row` and `_screen_results_doc` with an id-generic pair and two thin wrappers (names and behaviour of the wrappers unchanged; the glob for `screen-<idea>` is the same string as before and never matches a `screen2-` doc):

```python
def _ledger_row(ident: str) -> dict | None:
    """The ledger row whose id is exactly `ident`, or None. A missing or
    unreadable ledger reads as no row; a malformed line is skipped."""
    try:
        with open(SCREEN_LEDGER_PATH, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None
    for line in lines:
        row = _json_row(line)
        if row is not None and row.get("id") == ident:
            return row
    return None


def _results_doc(ident: str) -> str | None:
    """The first `*-<ident>.md` in SCREEN_RESULTS_DIR, or None."""
    pattern = os.path.join(glob.escape(SCREEN_RESULTS_DIR),
                           f"*-{glob.escape(ident)}.md")
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else None


def _screen_ledger_row(idea: str) -> dict | None:
    """The ledger row whose id is exactly screen-<idea>, or None."""
    return _ledger_row(f"screen-{idea}")


def _screen_results_doc(idea: str) -> str | None:
    """The first `*-screen-<idea>.md` in SCREEN_RESULTS_DIR, or None."""
    return _results_doc(f"screen-{idea}")
```

Replace `_screen_deny_reason` with the behaviour-preserving split plus the re-screen branch:

```python
def _screen_dry_run_reason(flags: dict) -> str | None:
    """A dry run is decided by --tickers alone."""
    if flags["tickers"] and flags["ticker_count"] > _SCREEN_MAX_SMOKE_TICKERS:
        return _screen_text(
            f"--dry-run with more than {_SCREEN_MAX_SMOKE_TICKERS} --tickers "
            "re-reads the verdict across the universe and writes nothing; "
            "a smoke test names two or three symbols with --tickers")
    if flags["tickers"]:
        return None
    return _screen_text(
        "--dry-run without --tickers reads the whole universe and writes "
        "nothing; a smoke test names two or three symbols with --tickers")


def _screen_paths_reason(flags: dict) -> str | None:
    """A real run on a non-default ledger or results dir."""
    ledger, results_dir = flags["ledger"], flags["results_dir"]
    if ledger is not None and not _is_default_ledger(ledger):
        return _screen_text(
            f"--ledger other than the default ({ledger}) hides the rows of "
            "ideas already screened; a real run uses the default ledger")
    if results_dir is not None and not _is_default_results_dir(results_dir):
        return _screen_text(
            f"--results-dir other than the default ({results_dir}) hides the "
            "results docs of ideas already screened; a real run uses the "
            "default results dir")
    return None


def _rescreen_record_reason(idea: str) -> str | None:
    """v230 A5: the original screen-v1 row must exist; the screen2- id must
    have neither a ledger row nor a results doc."""
    original = _ledger_row(f"screen-{idea}")
    if original is None or original.get("instrument") != "screen-v1":
        return _screen_text(
            f"--rescreen-v1 needs the screen-v1 row screen-{idea}; it "
            "re-screens only the twelve original rows")
    ident = _RESCREEN_PREFIX + idea
    row = _ledger_row(ident)
    if row is not None:
        return _screen_text(
            f"{ident} is already in the ledger ({row.get('date')}, "
            f"{row.get('verdict')}, {row.get('record')}); the v230 re-screen "
            "was one shot")
    doc = _results_doc(ident)
    if doc is not None:
        return _screen_text(
            f"results doc {_repo_relative(doc)} exists with no ledger row; the "
            "re-screen that wrote it spent the shot -- say so to the human "
            "partner, do not re-run")
    return None


def _rescreen_deny_reason(flags: dict) -> str | None:
    """--rescreen-v1 (v230 partner decision 2): only the twelve names, never
    beside --count-only, dry runs as any smoke test, a real run on the default
    paths with --checkpoint-dir and while its screen2- id is unspent."""
    if flags["idea"] not in _RESCREEN_V1:
        return _screen_text(
            f"--rescreen-v1 is limited to the twelve v230 A5 names; "
            f"{flags['idea']} is not one of them")
    if flags["count_only"]:
        return _screen_text("--rescreen-v1 cannot accompany --count-only")
    if flags["dry_run"]:
        return _screen_dry_run_reason(flags)
    reason = _screen_paths_reason(flags)
    if reason is not None:
        return reason
    if not flags["checkpoint_dir"]:
        return _screen_text(
            "a real --rescreen-v1 run needs --checkpoint-dir: its run marker "
            "and crash record live beside the checkpoints")
    return _rescreen_record_reason(flags["idea"])


def _screen_deny_reason(flags: dict) -> str | None:
    """The deny text for one screen segment, or None to allow it. A
    --rescreen-v1 segment has its own rule; otherwise --count-only is allowed
    first (it races nothing and writes nothing), a dry run is decided by
    --tickers alone, and a real run is denied on a non-default ledger or
    results dir, then on a record (the index's Decision 10)."""
    if flags["rescreen_v1"]:
        return _rescreen_deny_reason(flags)
    if flags["count_only"]:
        return None   # v182: counts only -- no race, no R, writes nothing, any idea
    if flags["dry_run"]:
        return _screen_dry_run_reason(flags)
    return _screen_paths_reason(flags) or _screen_record_reason(flags["idea"])
```

Run `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`. Expected: 0 failed, 0 xfailed. Confirm `.codex/hooks.json` still names `python .claude/hooks/guardrails.py` and `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py` passes (the hook file is shared; nothing to mirror). Run `python scripts/dev/complexity_gate.py`: no new function at complexity 15 or more (`_rescreen_deny_reason` is the largest, about 7), and `_screen_deny_reason` drops below its old count.

- [ ] **Step 3: Commit the hook**

```bash
git add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py
git commit -m "feat(v234): the screen hook allows one --rescreen-v1 run per v230 A5 name"
```

### Task V234-11b: Methodology paragraphs, screen skill and Codex mirror
**Model:** sonnet — doc and skill wording fixed below, pinned by a doc test and the mirror test.

Second half of the ledger's V234-11 (split at 20 KB). Requires V234-11 (the skill and AGENTS.md describe the hook it widened) and V234-10 (the doc test imports `rescreen.RESCREEN_V1`). No real screen run.

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (inside the Stage −2 bullet only, after the avoid-mode paragraph)
- Modify: `tests/hooks/test_doc_sections.py`
- Modify: `.claude/skills/screen/SKILL.md`
- Modify (generated): `.agents/skills/screen/SKILL.md` via `python scripts/dev/sync_codex.py`
- Modify: `AGENTS.md` (the Screen-header paragraph and the guardrails paragraph)

**Interfaces:**
- Consumes: `rescreen.RESCREEN_V1` (V234-10); `STAGE_MINUS_TWO` and `_lines` in `tests/hooks/test_doc_sections.py` (exist today); the hook behaviour from V234-11; `scripts/backtest/rescreen_summary.py` (V234-10).
- Produces: the dated partner-decision-2 paragraph that licenses V234-12's runs; the skill's "Re-screen mode" section V234-12's runbook follows.

- [ ] **Step 1: Write the failing doc test**

Append to `tests/hooks/test_doc_sections.py`:

```python
def test_v230_paragraphs_sit_inside_the_stage_minus_two_bullet():
    """v230 A4/A5: the v2 null, the fifth clause, SCOPE and the dated
    partner-decision-2 exception live inside the Stage -2 bullet, no heading."""
    from swingbot.core.backtesting.screen import rescreen
    lines = _lines("backtest-methodology.md")
    start = next(i for i, line in enumerate(lines) if line.startswith(STAGE_MINUS_TWO))
    end = next(i for i, line in enumerate(lines)
               if line.startswith("- **The acceptance funnel."))
    body = lines[start + 1:end]
    assert all(not line or line.startswith("  ") for line in body)
    text = " ".join(line.strip() for line in body)
    for needle in ("**Screen v2 (v230, partner 2026-11-16).**", "`screen-v2`",
                   '`SCOPE = "market"`', "`SCOPE_MISMATCH`", "`NULL_STARVED`",
                   "**Fifth clause:**", "partner decision 2, 2026-11-16",
                   "`--rescreen-v1`", "`screen2-<name>`", "`run-marker.json`",
                   "those twelve rows and nothing else", "never gates them"):
        assert needle in text, needle
    for name in rescreen.RESCREEN_V1:
        assert f"`{name}`" in text, name
```

Run `python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py`. Expected: the new test FAILS on the first needle.

- [ ] **Step 2: Add the dated paragraphs inside the Stage −2 bullet**

In `docs/claude/backtest-methodology.md`, directly after the line `  the unchanged funnel on the bot's own replay.` (the avoid-mode paragraph's last line, before `- **The acceptance funnel.**`), insert, two-space indented like the rest of the bullet and with no blank line and no heading:

```markdown
  **Screen v2 (v230, partner 2026-11-16).** From v230's merge
  `screen_idea.py` runs the v2 null only (`screen/null_v2.py`, ledger
  instrument `screen-v2`; v1 rows keep `screen-v1` and are never edited).
  v1 drew its null from the event's own month, which conditions on the
  future. A ticker-scope idea's null is K = 20 bars from **other tickers
  on the event's own date**, same trend state and same ATR% tercile of
  that date's eligible cross-section, none with this idea's event that
  day; seed `null_seed(idea + ":v2", date)`. A market-scope idea
  (`SCOPE = "market"` in its module, default `"ticker"`, frozen like `RACE`
  and `MODE`: a trigger that fires for every member on one date) draws from
  the same ticker and trend state in the 252 trading sessions before the
  event, excluding every bar within `CAP` bars of any of its event bars;
  seed `null_seed(idea + ":v2", ticker)`. Floor 5 candidates: more than
  half of the event dates under the floor is refused before any outcome is
  read, `SCOPE_MISMATCH` (ticker scope) or `NULL_STARVED` (market scope);
  a refusal writes no verdict and goes to the partner. A same-date null
  removes market timing: a ticker-scope pass says the trigger picks better
  names than its peers that day, and every v2 results doc says so. v2
  passed the placebo harness (`*-v230-null-placebo.md`, where v1 showed
  its bias) before it read any real idea. **Fifth clause:** a first-shot
  `MODE = "edge"` idea under `screen-v2` also needs the week-clustered
  lower 95% bound of mean R_event, net of costs, above zero; avoid mode's
  six clauses are unchanged, read against the v2 pool. Every q is reported
  over the whole ledger, one Benjamini-Hochberg family, and never gates.
  **The re-screen exception (partner decision 2, 2026-11-16).** The twelve
  `screen-v1` rows (`high52w`, `uptrend_pullback`, `gap_volume`,
  `turn_of_month`, `bond_spike_rebound`, `dollar_drop`,
  `sweep_reclaim_bos`, `turtle_soup`, `range_breakdown_close`,
  `shock_support_break_short`, `shock_failed_bounce_short`,
  `fvg_overhead_aged`) are re-screened once each, as one batch, under
  `screen-v2` through `screen_idea.py --rescreen-v1`, with every
  parameter, race shape, mode, cap, window, universe, data source and cost
  model as first run. Ids are `screen2-<name>`, one shot each; a crashed
  run that wrote no result may resume once, recorded in `run-marker.json`
  and `crash.json` beside its checkpoints and in its results doc. The
  exception exists because the instrument was defective, not because a
  result was unwelcome, and it covers those twelve rows and nothing else:
  no other closed row, no second re-screen, no changed parameter (the
  guardrails hook and `rescreen.py` enforce it). The fifth clause is
  reported for the twelve and never gates them: their event arm was already
  read. The v2 verdict supersedes v1 for licensing: a v1 pass that fails v2
  licenses nothing, a v1 fail that passes v2 earns the replication ladder
  only. Side-by-side summary: `<date>-v230-rescreen-summary.md`.
```

Run `python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py`. Expected: 0 failed, 0 xfailed (`test_stage_minus_two_stays_a_bullet_inside_funnel_stages` still finds one bullet start and no heading with "Stage").

- [ ] **Step 3: Update the screen skill**

In `.claude/skills/screen/SKILL.md`:

1. Replace the `Arguments:` line with:
   `Arguments: `$ARGUMENTS` (one idea name, written `<idea>` below, optionally followed by `--rescreen-v1` for the v230 batch; see "Re-screen mode").`
2. In Step 3, replace "the shared `race.py`, `null.py` and `verdict.py`" with "the shared `race.py`, `null.py`, `null_v2.py`, `screen_v2.py`, `rescreen.py` and `verdict.py`".
3. After the "# Idea screen" opening paragraph, add:

```markdown
Since v230 every run uses the **v2 null** (same-date peers for a ticker-scope idea; the idea's own trailing 252 sessions for a `SCOPE = "market"` idea) and writes ledger instrument `screen-v2`. A first-shot `edge` idea also needs the fifth clause (lower 95% bound of mean R_event, net of costs, above zero). A run may stop with `refused: SCOPE_MISMATCH` or `refused: NULL_STARVED` (exit 2) before any outcome is read: report it to the partner, never re-run or change the idea to get past it.
```

4. Append before `## The gate`:

```markdown
## Re-screen mode (v230 A5, the twelve only)

Only for the twelve names in `rescreen.RESCREEN_V1`
(`swingbot/core/backtesting/screen/rescreen.py`), once each, under partner
decision 2 (the dated paragraph in Step 1's section). Steps 2, 3 and 8 are
unchanged; the others become:

- **Step 4:** `grep -n '"id": "screen-<idea>"' docs/superpowers/results/preregistration-ledger.jsonl`
  must find the original row with `"instrument": "screen-v1"`;
  `grep -n '"id": "screen2-<idea>"' ...` and `ls docs/superpowers/results/*-screen2-<idea>.md`
  must both find nothing.
- **Step 5:** skipped: the name list is fixed.
- **Step 6:** the smoke test adds `--rescreen-v1` to the same command.
- **Step 7:** `backtest-runner` runs `python scripts/backtest/screen_idea.py --idea <idea> --rescreen-v1 --checkpoint-dir logs/v230-rescreen/<idea>`,
  defaults otherwise. Keep that directory: a crash may resume once from it
  (`run-marker.json`, `crash.json`); a second crash, or a run that already
  wrote its results doc, is reported to the partner, never retried.
- The results doc is `<date>-screen2-<idea>.md`; its fifth clause is
  reported only. After all twelve rows exist, `python scripts/backtest/rescreen_summary.py`
  writes the side-by-side summary.
```

Then run `python scripts/dev/sync_codex.py` (regenerates `.agents/skills/screen/SKILL.md`).

- [ ] **Step 4: Update AGENTS.md (condensed mirror)**

In `AGENTS.md`, in the Screen-header paragraph, replace `a fail is closed, never re-screened;` with:
`a fail is closed, never re-screened (sole exception, v230 partner decision 2: the twelve screen-v1 rows once each as screen2-<name> under screen-v2, its v2 same-date null; a first-shot edge idea also needs mean R_event's lower bound > 0);`

In the guardrails paragraph, the two lines

```text
knobs, a re-run or full-universe dry run of a screened idea
(`_rule_screen_rerun`) and malformed spec/plan names, and warns on bare
```

become

```text
knobs, a re-run or full-universe dry run of a screened idea
(`_rule_screen_rerun`; `--rescreen-v1` passes once per v230 name, with
`--checkpoint-dir`) and malformed spec/plan names, and warns on bare
```

- [ ] **Step 5: Verify**

Run each through `python scripts/dev/testrun.py file <path>`: `tests/hooks/test_codex_mirror.py`, `tests/hooks/test_doc_sections.py`, `tests/hooks/test_guardrails.py`. Run `python scripts/dev/complexity_gate.py`. Expected: 0 failed, 0 xfailed; no new function at complexity ≥ 15 (`_rescreen_deny_reason` is the largest, about 7).

- [ ] **Step 6: Commit the docs, skill and mirror together**

```bash
git add docs/claude/backtest-methodology.md tests/hooks/test_doc_sections.py .claude/skills/screen/SKILL.md .agents/skills/screen/SKILL.md AGENTS.md
git commit -m "docs(v234): record screen v2 and the dated twelve-row re-screen exception; skill and Codex mirror"
```


### Task V234-12: Run: the batch re-screen and its summary
**Model:** sonnet — an operations runbook with fixed commands and a fixed outcome table; every judgement call is routed to the partner.

**Run task: no code.** It executes only when all of these hold, checked in Step 1: V234-8 recorded **ACCEPT** in the index `## Handoff` (a STOP, a refused placebo cell still awaiting the partner, or no recorded result means this task does not run, and writing the plan grants no measurement); V234-9, V234-10, V234-10b, V234-11 and V234-11b are committed in the plan's worktree. Load the `backtest-gate` skill before Step 3 and follow the `screen` skill's "Re-screen mode" (V234-11b) for each idea. The runs go to the `backtest-runner` agent, one idea at a time, on this machine (the screen's cache, `data/backtest_cache_ext`, is local). **Never quote a run's command line in a commit message or in a quoted wrapper**: the guardrails hook reads that as a wrapped run and denies it.

**Files:**
- Create: `docs/superpowers/results/<date>-screen2-<name>.md` (twelve, written by `screen_idea.py`)
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (twelve rows appended by `screen_idea.py`, `instrument: "screen-v2"`; no existing byte changes)
- Create: `docs/superpowers/results/<date>-v230-rescreen-summary.md` (written by `rescreen_summary.py`)
- Modify: `docs/superpowers/plans/2026-11-17-v234-screen-v2-null_0-index.md` (`## Handoff`: one dated line per refusal or crash, and the batch outcome)
- Scratch, not committed: `logs/v230-rescreen/<name>/` (checkpoints, `run-marker.json`, `crash.json`, `run.lock`), `logs/v230-rescreen/ledger-before.jsonl`

**Interfaces:**
- Consumes: `screen_idea.py --rescreen-v1 --checkpoint-dir` (V234-10b); `rescreen.RESCREEN_V1`, `rescreen.rescreen_refusal`, `RunMarker` (V234-10); `rescreen_summary.main` (V234-10); `stats.load_ledger`, `stats.validate_ledger_row`, `stats.LEDGER_PATH` (exist); the hook's one-run allowance (V234-11); the dated licence paragraph (V234-11b).
- Produces: twelve `screen2-<name>` ledger rows and results docs; the summary doc. Parts B and C read the v2 verdicts from these rows.

- [ ] **Step 1: Pre-flight (read-only)**

1. `grep -n "ACCEPT" docs/superpowers/plans/2026-11-17-v234-screen-v2-null_0-index.md` must show V234-8's dated acceptance line in `## Handoff`. No such line: stop and report; do not continue.
2. `git status --short swingbot/core/backtesting/screen/ scripts/backtest/screen_idea.py` prints nothing. Record `git log -1 --format=%H -- swingbot/core/backtesting/screen/ scripts/backtest/screen_idea.py` as the definition hash.
3. Snapshot the ledger and check every licence is unspent:

```bash
mkdir -p logs/v230-rescreen
cp docs/superpowers/results/preregistration-ledger.jsonl logs/v230-rescreen/ledger-before.jsonl
python - <<'EOF'
from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import rescreen
rows = stats.load_ledger(stats.LEDGER_PATH)
problems = {n: rescreen.rescreen_refusal(n, rows, stats.LEDGER_PATH.parent)
            for n in rescreen.RESCREEN_V1}
bad = {n: p for n, p in problems.items() if p}
print("unspent: 12" if not bad else f"BLOCKED: {bad}")
EOF
```

Expected: `unspent: 12`. Anything else: stop and ask the partner (`AskUserQuestion`); never edit the ledger or delete a results doc to clear it.

4. `ls logs/v230-rescreen/*/run-marker.json` should find nothing on a first start. If a marker exists, this is a resume: go to Step 4's crash row for that idea, never delete the directory.

- [ ] **Step 2: Optional smoke test (one idea)**

Dispatch `backtest-runner` with `python scripts/backtest/screen_idea.py --idea high52w --rescreen-v1 --dry-run --tickers AAPL,MSFT`. It writes nothing and starts no marker. Expected: a verdict table whose head (`_render_head`, V234-7b) names null version v2 and scope `ticker` and the fifth clause marked reported-only. Under v2, stage 1 still builds the whole cached cross-section (the pool is the cross-section), so this takes minutes, not seconds. A traceback here is a code defect: stop and report; it is not a crash retry (no marker was written).

- [ ] **Step 3: The batch, one idea at a time, in ledger order**

For each `<name>` in `rescreen.RESCREEN_V1`, in this order: `high52w`, `uptrend_pullback`, `gap_volume`, `turn_of_month`, `bond_spike_rebound`, `dollar_drop`, `sweep_reclaim_bos`, `turtle_soup`, `range_breakdown_close`, `shock_support_break_short`, `shock_failed_bounce_short`, `fvg_overhead_aged`, dispatch `backtest-runner` with:

```bash
python scripts/backtest/screen_idea.py --idea <name> --rescreen-v1 --checkpoint-dir logs/v230-rescreen/<name>
```

Defaults otherwise: no `--ledger`, `--results-dir`, `--start`, `--end`, `--cache-dir` or `--membership` (the hook denies non-default paths; the frozen first-run window and universe are the defaults). The runner relays the verdict line, the exit code and the results path only. The run checkpoints stage 1 and stage 3 per ticker and stage 2 as one artefact under `logs/v230-rescreen/<name>/`; it prints a percent on runs past 15 minutes. Then apply Step 4's outcome table before starting the next idea.

- [ ] **Step 4: Outcome table (apply after every run)**

| What the run did | What you do |
|---|---|
| Exit 0, results path printed | Step 5 for this idea, then the next idea. |
| Exit 2, stderr `refused: NULL_STARVED: ...` or `refused: SCOPE_MISMATCH: ...` | No outcome was read and no doc or row was written. Append a dated line to the index `## Handoff` (idea, code, the detail text). Continue with the next idea (a refusal reads nothing, so the batch is not contaminated). The index Handoff already expects `turn_of_month`-type market-scope ideas (`turn_of_month`, `bond_spike_rebound`, `dollar_drop`) may starve. The marker stays at attempt 1 "running"; leave its directory untouched. After the batch, ask the partner with `AskUserQuestion` what the refused idea's record is; never re-run it, change its `SCOPE`, cap or window, or delete its marker to get past the refusal. |
| Exit 2, stderr `refused:` naming the ledger, a spent shot, `--checkpoint-dir`, the run marker (`run already active`, `run completed`, `one crash retry already spent`, `unreadable run marker`) | Stop the batch. Report the line to the partner with `AskUserQuestion`; do not edit the ledger, the results dir or the marker. |
| Hook deny (`screen_idea: ...`) | Stop. The hook is the rule: report it, never route round it. |
| Crash: traceback, killed process or machine loss, **and no `*-screen2-<name>.md` written** | Re-dispatch the identical command once with the same `--checkpoint-dir`; finished units are skipped, `RunMarker` records attempt 1 in `crash.json` and the results doc prints the crash note. Append a dated Handoff line. A second crash of the same idea: stop and ask the partner. |
| Crash **after** `*-screen2-<name>.md` was written but before the ledger row | The shot is spent (`rescreen_refusal` refuses it; the hook denies it). Stop and ask the partner; never delete the doc to re-run. |

- [ ] **Step 5: Check and commit each finished idea**

After each exit 0:

```bash
python - <<'EOF'
from pathlib import Path
from swingbot.core.backtesting.instrument import stats
before = Path("logs/v230-rescreen/ledger-before.jsonl").read_bytes()
after = stats.LEDGER_PATH.read_bytes()
assert after.startswith(before), "a pre-batch ledger byte changed"
rows = stats.load_ledger(stats.LEDGER_PATH)
for row in rows:
    stats.validate_ledger_row(row)
new = [r for r in rows if r["id"].startswith("screen2-")]
assert all(r["instrument"] == "screen-v2" for r in new)
print(f"ok: {len(new)} screen2 rows, v1 bytes intact")
EOF
```

Expected: `ok: <k> screen2 rows, v1 bytes intact`. Open the new results doc and confirm, without re-deriving anything: its head names null version v2 and the idea's scope; `## Fifth clause (v230 A3)` saying "This clause is reported only and never gates"; `## Re-screen provenance` naming the `screen-<name>` row and "No crash restart." (or the crash note); the `v2_report.OMITTED_V2_BLOCKS` list. Add `**Definition commit:** <hash from Step 1>` under its title. Commit the doc and the ledger together, naming the idea and the verdict exactly as printed, never the command line:

```bash
git add docs/superpowers/results/<date>-screen2-<name>.md docs/superpowers/results/preregistration-ledger.jsonl
git commit -m "results(v234): screen2-<name> <VERDICT> under screen-v2 (v230 A5 re-screen)"
```

A results doc with no ledger row, or a check failure: stop and ask the partner.

- [ ] **Step 6: The summary**

Only when all twelve `screen2-` rows exist (refused ideas have none, so with any refusal open this step waits for the partner's ruling in the Handoff; `summary_rows` raises `missing original or screen-v2 row` and the CLI exits 2 writing nothing):

```bash
python scripts/backtest/rescreen_summary.py
```

Expected: it prints `docs/superpowers/results/<date>-v230-rescreen-summary.md`. Check that it lists twelve rows, links each v1 and v2 record, prints "not recorded" for every old mean its v1 doc lacks (no old run is repeated to fill one) and states that the v2 verdict supersedes v1 for licensing. Commit:

```bash
git add docs/superpowers/results/*-v230-rescreen-summary.md
git commit -m "results(v234): v230 re-screen summary, twelve screen-v1 rows against screen-v2"
```

- [ ] **Step 7: Record the batch in the index**

Append one dated line to `## Handoff` in `docs/superpowers/plans/2026-11-17-v234-screen-v2-null_0-index.md`: the count of `SCREEN-PASS` / `SCREEN-FAIL` / `SCREEN-UNDERPOWERED` / `SCREEN-AVOID-PASS` under v2, which v1 verdicts flipped, any refusal or crash restart, and the summary path. State verdicts exactly as the docs print them; quote no pooled number beyond those docs. Then run `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py` and `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`; expected 0 failed, 0 xfailed (the hook now denies a second `--rescreen-v1` run of each finished idea).

```bash
git add docs/superpowers/plans/2026-11-17-v234-screen-v2-null_0-index.md
git commit -m "docs(v234): record the v230 re-screen batch outcome in the index handoff"
```

