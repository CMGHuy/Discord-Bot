# v173 Execution fidelity, part 4: report script, API route and the SPA slice

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-11:" -A 400 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §4 (one evaluation, written once), §5 (report script, API, panel) and `## Plan panel review` (the verdict read from `preregistration_verdicts`, the script and the API only read, the mirror as a standing procedure)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`), the task ledger, `## Handoff` and `## Revision 2026-10-19`. Every task below implicitly includes those Global Constraints, in particular **Report payload**, **Verdict**, **jsonl mirror**, **I/O glue**, **Report script** and **UI copy (verbatim)**.

Tasks: V173-11, V173-12, V173-13 (rewritten 2026-10-19; V173-14, the panel, moved to part 4b). V173-11 and V173-12 need V173-26 committed on the branch (both import `override_io`); they are disjoint (`scripts/reports/` + the results doc vs `analytics.py`) and may run together. V173-13 depends only on the payload contract and may run in Wave A. Part 4b's V173-14 needs V173-13.

`$WT = E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides`. Every path below is under `$WT`; commands spell it out in full because shell variables do not persist between Bash calls.

**What earlier tasks created** (check with `git -C $WT grep -n "<name>" -- swingbot/core/analytics/`; a missing one means an earlier task is not on the branch: stop and report, never re-create it): V173-7 `latest_completed_session(now) -> date`, `OverrideRow` (20 fields, `to_dict()` writes `close_date` as ISO text), `ROW_FIELDS`, `STATUSES` (eight, with `unstamped`), `LEDGER_ID`; V173-9/V173-22/V173-23 `replay_override(plan, bars, asof, trade=None)`; V173-10 `override_verdict.build_report(plans, trades_by_plan, bars_fn, asof, recorded, currency_symbol)`, `verdict_payload(rows, recorded)` (never evaluates), `evaluate_verdict(rows)`, `verdict_record(...)`, `mirror_ledger_row(record) -> dict`, `RESULTS_RECORD`, and `override_fidelity.summarise(rows)` (with `sum_delta_r_gross`); V173-26 `override_io.load_inputs()` (imports `PlanStore` and `TradeLog` lazily inside the function, so tests patch the source modules, never `override_io.PlanStore`), `override_io.stored_verdict(repo=None) -> dict | None`, `override_io.run_daily_check(...)` (the one evaluator) and `RESULT_RECORDED`/`RESULT_ALREADY`/`RESULT_WAITING`. **Every verdict function accepts rows in their `to_dict()` form.** Part 3 test helpers: `tests.analytics.test_override_fidelity_replay` (`plan(...)`, `frame(rows=None, *, n=26)`, `STOP_BAR`, `LAST_DAY = date(2026, 10, 19)`).

**Value shapes** (Global Constraints and § Handoff): `n_by_status` is `{status: int}` over all eight statuses, counting **eligible** (individual, not approx) rows only; bulk rows count only in `bulk_n`, non-bulk approx rows only in `approx_n`, so no exclusion note counts a row twice. `bulk_dates` is `{iso_date: int}` sorted by date. `sum_delta_r` and `sum_delta_r_gross` (3 dp) and `sum_delta_usd` (2 dp) cover counted rows, `0.0` with none. `engine_flags` is `{"stall_exit_enabled": bool, "runner_structure_exit": str}`. The verdict carries 17 keys: once a record is stored, `state, n, weeks, recorded_on, mean_delta_r, mean_delta_r_gross, ci, sum_delta_r, sum_delta_usd, bar_close_n` come from it and `open_n, excluded_share, evaluable, waiting_on` stay live; with no record, `state` is `WAITING` (even when `evaluable` is true), `recorded_on` and the mean/CI/sum fields are `null`, `bar_close_n` is live. `waiting_on` is the failing subset of `("count", "weeks", "open", "excluded")`, in that order, as a JSON list. `ci` is `[lo, hi]` or `null`. `rows` are newest `close_date` first. **Neither the script nor the API evaluates or writes**: only the bot's daily job does (`override_io.run_daily_check`, V173-26/V173-27). **Tests never touch a database** (Global Constraints): fixture plans, fakes and monkeypatched seams (`verdict_fn`/`inputs_fn` on the script, `analytics._override_inputs`/`analytics._override_verdict` on the route); never the production replica. Frontend specs use stubs and `HttpTestingController`.

# Phase 4: Report, API and the SPA slice (V173-11..V173-13)

### Task V173-11: Read-only report script `execution_fidelity_report.py` and the mirror procedure

**Model:** sonnet — a CLI over finished helpers

**Files:**
- Create: `scripts/reports/execution_fidelity_report.py`
- Create: `tests/scripts/test_execution_fidelity_report.py` (`tests/scripts/` is the `tooling` suite; `tests/suites.toml` is not edited)
- Create: `docs/superpowers/results/v173-override-fidelity.md` (the mirror row's `record` path; `tests/backtesting/test_preregistration_ledger_file.py` requires it to exist before any mirror)

**Interfaces:**
- Consumes:
  - V173-7: `override_fidelity.latest_completed_session(now: datetime) -> date`; `OverrideRow(...).to_dict()`; `ROW_FIELDS`; `STATUSES`.
  - V173-10: `override_verdict.build_report(plans, trades_by_plan, bars_fn, asof, recorded: dict | None, currency_symbol) -> dict` (never evaluates), `verdict_payload(rows, recorded) -> dict`, `mirror_ledger_row(record: dict) -> dict`, `RESULTS_RECORD` (`"docs/superpowers/results/v173-override-fidelity.md"`).
  - V173-26: `override_io.load_inputs() -> tuple[list, dict[str, dict]]`, `override_io.stored_verdict(repo=None) -> dict | None`; `run_daily_check` is **not** called here (the test makes it raise).
  - Existing: `stats.validate_ledger_row(row)` (`swingbot/core/backtesting/instrument/stats.py:160`, raises on a malformed row), `stats.append_ledger_row` and `stats.LEDGER_PATH` (only the test touches them, to prove nothing writes); `runner_path.cached_daily_bars` (`runner_path.py:191`); `config.CURRENCY_SYMBOL`.
  - Test helpers: Part 3's `plan`, `frame`, `STOP_BAR`, `LAST_DAY` (`tests/analytics/test_override_fidelity_replay.py`); `tests.backtesting.test_pullback_dryup_witness.pin_code_defaults`.
- Produces (V173-19 runs it on the VM; the results doc's procedure names it):
  - `DEV_BANNER = "DEV DATABASE: fixture data, not the real book. This report never writes a verdict."`; `NO_VERDICT = "no verdict recorded"`.
  - `mirror_line(record: dict | None) -> tuple[str, dict]`: `(NO_VERDICT, {})` without a record, else `(json.dumps(row), row)` for `row = ov.mirror_ledger_row(record)` after `stats.validate_ledger_row(row)`.
  - `render(payload: dict) -> list[str]`: the printed lines (engine flags, the row table, summary and splits, exclusion counts, verdict state, and the recorded figures when a verdict is stored).
  - `main(argv: list[str] | None = None, *, inputs_fn=None, bars_fn=None, now: datetime | None = None, verdict_fn=None) -> dict`: flags `--production`, `--json PATH`, `--mirror-row`. Returns the payload it printed; under `--mirror-row` it returns the mirror row (`{}` when none) and builds no report.
  - VM commands: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/execution_fidelity_report.py --production --json /tmp/v173-report.json"` (V173-19) and the same with `--production --mirror-row` (the standing procedure).
  - The results doc with `## Standing procedure: mirroring the recorded verdict`.

**What the script does, and why it never evaluates** (Global Constraints, **The one evaluator** and **Report script**; spec `## Plan panel review`). The verdict is evaluated once, by the bot's daily job, at a moment nobody picks after seeing the sums. The script is a reader: it loads plans and trades through `override_io.load_inputs`, reads the stored verdict through `override_io.stored_verdict`, calls `build_report(..., recorded, ...)` and prints. It never calls `evaluate_verdict`, `verdict_record`, `run_daily_check`, the repository's `insert_once` or `stats.append_ledger_row`, under any flag. `--production` only drops the banner. `--mirror-row` prints the stored record as one jsonl ledger line (or `no verdict recorded`, exit code 0) so the operator can mirror it on `main`; it needs no replay, so it builds no report. The bars come only from `runner_path.cached_daily_bars`, looked up at call time, never fetched.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/scripts/test_execution_fidelity_report.py`:

```python
"""v173 §5: the report script is read-only -- the dev banner, the stored
verdict shown as stored, the mirror row, and never an evaluation or a write."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.reports import execution_fidelity_report as report
from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_io as oio
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.backtesting.instrument import stats
from tests.analytics.test_override_fidelity_replay import LAST_DAY, STOP_BAR, frame, plan
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)   # Mon 17:00 ET, after the close
PAYLOAD_KEYS = {"rows", "summary", "verdict", "engine_flags", "asof", "currency_symbol"}
VERDICT_KEYS = {"state", "n", "needed", "weeks", "week_floor", "open_n", "excluded_share",
                "evaluable", "waiting_on", "recorded", "recorded_on", "mean_delta_r",
                "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n"}
FLAGS = {"stall_exit_enabled": False, "runner_structure_exit": "off"}
RECORD = {"ledger_id": "v173-override-fidelity", "verdict": "COST", "recorded_on": "2026-12-04",
          "n": 31, "weeks": 12, "mean_delta_r": -0.22, "mean_delta_r_gross": -0.2,
          "ci": [-0.24, -0.2], "sum_delta_r": -6.82, "sum_delta_usd": -1364.0,
          "bar_close_n": 2, "excluded_share": 0.0, "engine_flags": FLAGS, "rows": []}
SUMMARY = {"n_by_status": {s: 0 for s in of.STATUSES}, "bulk_n": 0, "bulk_dates": {},
           "approx_n": 0, "counted_n": 0, "sum_delta_r": 0.0, "sum_delta_r_gross": 0.0,
           "sum_delta_usd": 0.0, "usd_missing_n": 0, "helped": 0, "hurt": 0, "neutral": 0,
           "splits": {"state_at_close": {}, "horizon": {}, "direction": {}}}


def _boom(*_args, **_kwargs):
    raise AssertionError("the report script never evaluates and never writes")


@pytest.fixture(autouse=True)
def _pinned(monkeypatch, tmp_path):
    """Code defaults, and every evaluating or writing call made to raise."""
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(stats, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    for module, name in ((ov, "evaluate_verdict"), (ov, "verdict_record"),
                         (oio, "run_daily_check"), (stats, "append_ledger_row")):
        monkeypatch.setattr(module, name, _boom)


def _no_inputs():
    return [], {}


def _rows(n: int, weeks: int, delta_r: float = -0.2) -> list[dict]:
    """n counted rows (individual, stamped, resolved) over `weeks` ISO weeks."""
    start = date(2026, 9, 7)                                  # a Monday
    return [of.OverrideRow(
        plan_id=f"p{i}", ticker="AAPL", horizon="2w", direction="bullish",
        state_at_close="ACTIVE", close_date=start + timedelta(weeks=i % weeks), bulk=False,
        approx=False, price_source="quote", status="resolved", actual_r=0.2 + delta_r,
        engine_r=0.2, delta_r=delta_r, delta_r_gross=delta_r + 0.02, actual_usd=None,
        engine_usd=None, delta_usd=round(delta_r * 200, 2), engine_exit_reason="stop",
        outcome="hurt").to_dict() for i in range(n)]


def _stub_report(monkeypatch, rows):
    """Stub build_report with these rows; the verdict part is the real
    verdict_payload over whatever stored record the script hands in."""
    seen = {}

    def fake(plans, trades, bars_fn, asof, recorded, currency_symbol):
        seen.update(asof=asof, recorded=recorded)
        return {"rows": rows, "summary": SUMMARY, "verdict": ov.verdict_payload(rows, recorded),
                "engine_flags": FLAGS, "asof": asof.isoformat(),
                "currency_symbol": currency_symbol}

    monkeypatch.setattr(ov, "build_report", fake)
    return seen


# -- the banner -----------------------------------------------------------------------

def test_a_dev_run_prints_the_banner_first(monkeypatch, capsys):
    _stub_report(monkeypatch, _rows(30, 10))
    out = report.main([], inputs_fn=_no_inputs, verdict_fn=lambda: None, now=NOW)
    printed = capsys.readouterr().out.splitlines()
    assert printed[0] == report.DEV_BANNER
    assert report.DEV_BANNER == ("DEV DATABASE: fixture data, not the real book. "
                                 "This report never writes a verdict.")
    assert (out["verdict"]["state"], out["verdict"]["evaluable"]) == ("WAITING", True)


def test_production_only_drops_the_banner_and_still_never_evaluates(monkeypatch, capsys):
    _stub_report(monkeypatch, _rows(30, 10))                 # the floors hold
    out = report.main(["--production"], inputs_fn=_no_inputs, verdict_fn=lambda: None, now=NOW)
    assert report.DEV_BANNER not in capsys.readouterr().out.splitlines()
    verdict = out["verdict"]
    assert (verdict["state"], verdict["evaluable"], verdict["recorded"]) == ("WAITING", True, False)
    assert not stats.LEDGER_PATH.exists()                    # nothing written anywhere


# -- the stored verdict ---------------------------------------------------------------

def test_the_stored_verdict_is_shown_as_stored(monkeypatch, capsys):
    seen = _stub_report(monkeypatch, _rows(12, 4, delta_r=0.8))   # live rows now look SAVED
    calls = []

    def verdict_fn():
        calls.append(1)
        return RECORD

    out = report.main(["--production"], inputs_fn=_no_inputs, verdict_fn=verdict_fn, now=NOW)
    assert calls == [1]
    assert seen == {"asof": LAST_DAY, "recorded": RECORD}
    v = out["verdict"]
    assert (v["state"], v["recorded"], v["recorded_on"], v["n"], v["weeks"]) == (
        "COST", True, "2026-12-04", 31, 12)
    assert (v["mean_delta_r"], v["mean_delta_r_gross"], list(v["ci"])) == (-0.22, -0.2, [-0.24, -0.2])
    assert (v["sum_delta_r"], v["sum_delta_usd"], v["bar_close_n"]) == (-6.82, -1364.0, 2)
    assert (v["evaluable"], list(v["waiting_on"])) == (False, ["count", "weeks"])   # live
    text = capsys.readouterr().out
    assert "verdict COST" in text
    assert "recorded 2026-12-04 from 31 overrides over 12 weeks" in text
    assert "before costs -0.200R" in text and "bar_close 2" in text


# -- the mirror row -------------------------------------------------------------------

def test_mirror_row_prints_one_validated_ledger_line(monkeypatch, capsys):
    monkeypatch.setattr(ov, "build_report", _boom)           # --mirror-row needs no replay
    out = report.main(["--production", "--mirror-row"], inputs_fn=_boom,
                      verdict_fn=lambda: RECORD, now=NOW)
    printed = capsys.readouterr().out.splitlines()
    assert len(printed) == 1
    row = json.loads(printed[0])
    stats.validate_ledger_row(row)
    assert row == out == ov.mirror_ledger_row(RECORD)
    assert (row["id"], row["date"], row["verdict"], row["instrument"], row["record"]) == (
        "v173-override-fidelity", "2026-12-04", "COST", "v2", ov.RESULTS_RECORD)


def test_mirror_row_without_a_verdict_says_so(capsys):
    out = report.main(["--production", "--mirror-row"], inputs_fn=_boom,
                      verdict_fn=lambda: None, now=NOW)
    assert capsys.readouterr().out.splitlines() == ["no verdict recorded"]
    assert out == {}


# -- the real pipeline on fixture data ------------------------------------------------

def test_the_real_pipeline_replays_from_the_cache_and_writes_json(capsys, tmp_path):
    seen = []

    def bars_fn(ticker):
        seen.append(ticker)
        return frame({19: STOP_BAR})

    target = tmp_path / "out.json"
    out = report.main(["--json", str(target)],
                      inputs_fn=lambda: ([plan()], {"p1": {"id": "t1", "shares": 10}}),
                      bars_fn=bars_fn, verdict_fn=lambda: None, now=NOW)
    assert seen == ["T"]
    assert set(out) == PAYLOAD_KEYS and set(out["verdict"]) == VERDICT_KEYS
    assert (out["asof"], out["currency_symbol"]) == (LAST_DAY.isoformat(), "$")
    [row] = out["rows"]
    assert set(row) == set(of.ROW_FIELDS)
    assert (row["plan_id"], row["status"], row["bulk"], row["approx"]) == (
        "p1", "resolved", False, False)
    assert row["delta_usd"] is not None and row["delta_r_gross"] is not None
    assert json.loads(target.read_text(encoding="utf-8")) == out
    printed = capsys.readouterr().out
    assert "stall_exit_enabled=False" in printed and "runner_structure_exit=off" in printed
    assert "resolved" in printed and "verdict WAITING" in printed


def test_render_lists_exclusions_waiting_on_and_the_bulk_dates():
    summary = SUMMARY | {"n_by_status": SUMMARY["n_by_status"] | {"stale": 2, "unstamped": 1,
                                                                  "open": 1},
                         "bulk_n": 15, "bulk_dates": {"2026-09-30": 15}, "approx_n": 3}
    payload = {"rows": [], "engine_flags": {"stall_exit_enabled": True, "runner_structure_exit": "on"},
               "asof": "2026-10-19", "currency_symbol": "$", "summary": summary,
               "verdict": {"state": "WAITING", "n": 0, "needed": 30, "weeks": 0, "week_floor": 10,
                           "open_n": 1, "excluded_share": 1.0, "evaluable": False,
                           "waiting_on": ["count", "weeks", "open", "excluded"],
                           "recorded": False, "recorded_on": None, "mean_delta_r": None,
                           "mean_delta_r_gross": None, "ci": None, "sum_delta_r": None,
                           "sum_delta_usd": None, "bar_close_n": 0}}
    text = "\n".join(report.render(payload))
    assert "No manual overrides in scope." in text
    assert "bulk clear 2026-09-30: 15 (not decisions, left out)" in text
    assert "approx (estimated exit): 3 (shown, not counted)" in text
    assert "stale: 2" in text and "unstamped: 1" in text and "open: 1" in text
    assert "before costs +0.000R" in text
    assert ("verdict WAITING: 0 of 30 counted rows, 0 of 10 weeks, open 1, excluded share "
            "100.0%, evaluable False; waiting on count, weeks, open, excluded") in text
    assert "recorded" not in text.split("verdict WAITING")[1]


# -- the results doc ------------------------------------------------------------------

def test_the_results_doc_carries_the_standing_procedure():
    assert ov.RESULTS_RECORD == "docs/superpowers/results/v173-override-fidelity.md"
    text = (ROOT / ov.RESULTS_RECORD).read_text(encoding="utf-8")
    assert "## Standing procedure: mirroring the recorded verdict" in text
    assert "execution_fidelity_report.py --production --mirror-row" in text
    assert "stats.append_ledger_row" in text
```

The autouse fixture makes `evaluate_verdict`, `verdict_record`, `run_daily_check` and `stats.append_ledger_row` raise in **every** test, so each run, dev or production, with or without `--json` or `--mirror-row`, proves the script neither evaluates nor writes. `_rows` uses the same `OverrideRow` keyword set as V173-26's `_row` (`source` takes its default `"manual"`).

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/scripts/test_execution_fidelity_report.py
```

Expected: collection error, `ModuleNotFoundError: No module named 'scripts.reports.execution_fidelity_report'`.

- [ ] **Step 3: Write the script**

Create `$WT/scripts/reports/execution_fidelity_report.py`:

```python
#!/usr/bin/env python3
"""v173: manual overrides against the engine left alone (spec §4-§5). Read-only.

Replays every manual close from its real fill through the v2 exit engine and
prints one row per override with exactly one status, the descriptive summary
and the verdict state. Reads plans, linked trades, the live scan's bar cache
(market_data/daily, never fetched) and the stored verdict in the Postgres
table preregistration_verdicts.

This script never evaluates the verdict and never writes it: the bot's daily
job (override_io.run_daily_check) is the only evaluator. --production only
drops the dev banner. --mirror-row prints the stored verdict as one jsonl
ledger line for the standing mirror procedure
(docs/superpowers/results/v173-override-fidelity.md).

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot \
        python scripts/reports/execution_fidelity_report.py --production"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot import config  # noqa: E402
from swingbot.core.analytics import override_fidelity as of  # noqa: E402
from swingbot.core.analytics import override_io as oio  # noqa: E402
from swingbot.core.analytics import override_verdict as ov  # noqa: E402
from swingbot.core.analytics import runner_path as rp  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402

DEV_BANNER = "DEV DATABASE: fixture data, not the real book. This report never writes a verdict."
NO_VERDICT = "no verdict recorded"


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="v173 manual overrides vs the engine (read-only)")
    parser.add_argument("--production", action="store_true",
                        help="the real book on the VM: drops the dev banner, still read-only")
    parser.add_argument("--json", metavar="PATH", help="also write the payload (the API body)")
    parser.add_argument("--mirror-row", action="store_true",
                        help="print the stored verdict as one ledger JSON line, then stop")
    return parser.parse_args(argv)


def mirror_line(record: dict | None) -> tuple[str, dict]:
    """The stored record as one validated jsonl ledger line, or NO_VERDICT."""
    if record is None:
        return NO_VERDICT, {}
    row = ov.mirror_ledger_row(record)
    stats.validate_ledger_row(row)
    return json.dumps(row, ensure_ascii=False), row


# -- rendering ---------------------------------------------------------------------

def _num(value, fmt: str) -> str:
    return "—" if value is None else format(value, fmt)


def _pair(row: dict, key: str, currency: str) -> str:
    usd = row[f"{key}_usd"]
    money = "—" if usd is None else f"{usd:+.2f}{currency}"
    return f"{_num(row[f'{key}_r'], '+.3f')}R/{money}"


def _row_line(row: dict, currency: str) -> str:
    flags = " ".join(name for name, on in (("bulk", row["bulk"]), ("approx", row["approx"])) if on)
    return (f"{row['close_date'] or '—'}  {row['ticker']:<6} {row['horizon']:<3} "
            f"{row['state_at_close']:<7} actual {_pair(row, 'actual', currency)}  "
            f"engine {_pair(row, 'engine', currency)}  delta {_pair(row, 'delta', currency)}  "
            f"exit {row['engine_exit_reason'] or '—'}  {row['status']}  {flags}").rstrip()


def _split_lines(splits: dict, currency: str) -> list[str]:
    return [f"split {key}={value}: n={cell['n']} "
            f"{cell['sum_delta_r']:+.3f}R / {cell['sum_delta_usd']:+.2f}{currency}"
            for key, groups in splits.items() for value, cell in groups.items()]


def _summary_lines(summary: dict, currency: str) -> list[str]:
    lines = [f"counted rows: {summary['counted_n']}  sum delta {summary['sum_delta_r']:+.3f}R"
             f" / {summary['sum_delta_usd']:+.2f}{currency}, before costs "
             f"{summary['sum_delta_r_gross']:+.3f}R"
             f"  (counted rows without dollars: {summary['usd_missing_n']})",
             f"helped / hurt / neutral: {summary['helped']} / {summary['hurt']} / "
             f"{summary['neutral']}  (counts ignore size)"]
    lines += [f"bulk clear {day}: {n} (not decisions, left out)"
              for day, n in summary["bulk_dates"].items()]
    if summary["approx_n"]:
        lines.append(f"approx (estimated exit): {summary['approx_n']} (shown, not counted)")
    lines += [f"{status}: {n}" for status, n in summary["n_by_status"].items() if n]
    return lines + _split_lines(summary["splits"], currency)


def _recorded_tail(verdict: dict) -> str:
    return (f"; recorded {verdict['recorded_on']} from {verdict['n']} overrides over "
            f"{verdict['weeks']} weeks, mean delta {_num(verdict['mean_delta_r'], '+.3f')}R "
            f"(before costs {_num(verdict['mean_delta_r_gross'], '+.3f')}R), "
            f"95% CI {verdict['ci']}, sum {_num(verdict['sum_delta_r'], '+.3f')}R / "
            f"{_num(verdict['sum_delta_usd'], '+.2f')}, bar_close {verdict['bar_close_n']}")


def _verdict_line(verdict: dict) -> str:
    line = (f"verdict {verdict['state']}: {verdict['n']} of {verdict['needed']} counted rows, "
            f"{verdict['weeks']} of {verdict['week_floor']} weeks, open {verdict['open_n']}, "
            f"excluded share {verdict['excluded_share']:.1%}, evaluable {verdict['evaluable']}")
    if verdict["waiting_on"]:
        line += "; waiting on " + ", ".join(verdict["waiting_on"])
    return line + (_recorded_tail(verdict) if verdict["recorded"] else "")


def render(payload: dict) -> list[str]:
    """The printed report: flags, rows, summary and splits, verdict."""
    currency = payload["currency_symbol"]
    flags = " ".join(f"{key}={value}" for key, value in payload["engine_flags"].items())
    lines = [f"v173 overrides vs engine, asof {payload['asof']}  engine flags: {flags}", ""]
    lines += [_row_line(r, currency) for r in payload["rows"]] or ["No manual overrides in scope."]
    lines += ["", *_summary_lines(payload["summary"], currency), "",
              _verdict_line(payload["verdict"])]
    return lines


def main(argv: list[str] | None = None, *, inputs_fn=None, bars_fn=None,
         now: datetime | None = None, verdict_fn=None) -> dict:
    args = _parse(argv)
    if not args.production:
        print(DEV_BANNER)
    recorded = (verdict_fn or oio.stored_verdict)()
    if args.mirror_row:
        line, row = mirror_line(recorded)
        print(line)
        return row
    now = now or datetime.now(timezone.utc)
    plans, trades = (inputs_fn or oio.load_inputs)()
    payload = ov.build_report(plans, trades, bars_fn or rp.cached_daily_bars,
                              of.latest_completed_session(now), recorded,
                              config.CURRENCY_SYMBOL)
    print("\n".join(render(payload)))
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
    return payload


if __name__ == "__main__":
    main()
```

`verdict_fn or oio.stored_verdict`, `inputs_fn or oio.load_inputs` and `bars_fn or rp.cached_daily_bars` resolve the attribute at call time, so a patched module attribute is honoured; none is bound as a default argument. `main` returns normally on every path, including `no verdict recorded`, so the exit code is 0. The script imports nothing that writes: no repository, no `stats.append_ledger_row` call.

- [ ] **Step 4: Write the results doc with the standing procedure**

Create `$WT/docs/superpowers/results/v173-override-fidelity.md`:

````markdown
# v173 override fidelity: manual overrides vs the v2 engine

**Spec:** `docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md` (§4, frozen pre-registration; moves to `specs/implemented/` at close-out)
**Ledger id:** `v173-override-fidelity` (`preregistration-ledger.jsonl`, instrument `v2`)
**Authority:** the Postgres table `preregistration_verdicts` on production. This file and the jsonl row are the record, filled by the mirror below.

## What is measured

Each manual close (`reason == "manual"`, individual, stamped, `resolved`) is replayed from its real fill through the v2 exit engine left alone. Delta R = actual R minus engine R, both through one `costs.book` call each, net of modelled costs and pre-tax. The rule is frozen in the spec §4: at least 30 counted overrides over at least 10 distinct ISO weeks, no eligible row open, left-out rows at most 20% of eligible rows; then a week-cluster bootstrap 95% interval on the mean delta R: wholly below 0 is `COST`, wholly above 0 is `SAVED`, otherwise `INCONCLUSIVE`.

The bot's daily job `override_verdict_check` (`swingbot/commands/scanning/loops.py`, 23:50 Europe/Berlin on weekdays) is the only evaluator. It writes the verdict once; the table's primary key makes a second write impossible. Nobody runs the evaluation by hand.

## Recorded verdict

Not recorded yet.

## Standing procedure: mirroring the recorded verdict

Run this when the bot logs the WARNING `override_verdict_check: <VERDICT> verdict v173-override-fidelity recorded on <date> and frozen. ...`, or when a report or the Analytics panel shows a recorded verdict while `docs/superpowers/results/preregistration-ledger.jsonl` has no `v173-override-fidelity` row.

1. Print the stored row on the VM (read-only):

   ```bash
   bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/execution_fidelity_report.py --production --mirror-row" > "$SCRATCH/v173-mirror-row.json"
   ```

   The file must hold exactly one line starting `{"id": "v173-override-fidelity"`. `no verdict recorded` means there is nothing to mirror: stop.
2. On `main` in the repo root, append it through the validating writer `stats.append_ledger_row` (it refuses a duplicate id):

   ```bash
   python -c "import json, pathlib, sys; from swingbot.core.backtesting.instrument import stats; stats.append_ledger_row(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').strip()))" "$SCRATCH/v173-mirror-row.json"
   ```

3. Replace "Not recorded yet." under `## Recorded verdict` above with the row's verdict, date, `n`, mean delta R (`exp_r`) and the CI from its hypothesis.
4. Commit both files on `main`:

   ```bash
   git add docs/superpowers/results/preregistration-ledger.jsonl docs/superpowers/results/v173-override-fidelity.md
   git commit -m "docs(v173): mirror the recorded override-fidelity verdict"
   ```

Never edit or delete the table row, and never evaluate again. If the jsonl row and the table ever disagree, the table wins: re-mirror from step 1.
````

`$SCRATCH` is the session scratchpad of whoever runs the procedure.

- [ ] **Step 5: Run the test to verify it passes**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/scripts/test_execution_fidelity_report.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py
```

Expected: both PASS, `0 failed`, `0 xfailed`. No test runs a bootstrap (nothing evaluates), so the first file takes seconds.

If `test_the_stored_verdict_is_shown_as_stored` reads a live `n` (12) rather than 31, V173-10's `verdict_payload` is not taking the recorded fields from the record: report it, never adjust this test. If `test_the_real_pipeline...` reads a status other than `resolved`, compare with Part 3's payload-shape test (the same `plan()` and `frame({19: STOP_BAR})`); never edit Part 3's helpers from here.

- [ ] **Step 6: Read-only, complexity and a help smoke run**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides grep -n "evaluate_verdict\|verdict_record\|run_daily_check\|insert_once\|append_ledger_row" -- scripts/reports/execution_fidelity_report.py
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/reports/execution_fidelity_report.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/reports/execution_fidelity_report.py --help
```

Expected: the grep prints only the docstring line that names `run_daily_check` as the evaluator (no call); `radon` prints nothing; `--help` lists `--production`, `--json` and `--mirror-row`. Do not run the script without `--help` here: the dev database is not the book, and the V173-19 run on the VM is the real one.

- [ ] **Step 7: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add scripts/reports/execution_fidelity_report.py tests/scripts/test_execution_fidelity_report.py docs/superpowers/results/v173-override-fidelity.md
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): read-only execution fidelity report script and the mirror procedure"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-12: `GET /api/v1/analytics/override-fidelity`

**Model:** sonnet — an admin endpoint over `build_report`

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (the `datetime` import at the top; two seams and the route after `analytics_partials`, around line 697)
- Create: `tests/admin/test_api_v1_analytics_override_fidelity.py` (`tests/admin/` is the `admin` suite)

**Interfaces:**
- Consumes:
  - V173-7: `override_fidelity.latest_completed_session(now) -> date`; `ROW_FIELDS`.
  - V173-10: `override_verdict.build_report(plans, trades_by_plan, bars_fn, asof, recorded: dict | None, currency_symbol) -> dict` (never evaluates).
  - V173-26: `override_io.load_inputs() -> tuple[list, dict[str, dict]]`, `override_io.stored_verdict(repo=None) -> dict | None`; `run_daily_check` is **not** called (the test makes it raise).
  - Existing: `runner_path.cached_daily_bars`, `config.CURRENCY_SYMBOL`, `require_auth`, `api_v1`, `jsonify` (all already in `analytics.py`).
  - Test helpers: Part 3's `plan`, `frame`, `STOP_BAR`, `LAST_DAY`; `tests.admin.api_v1_contract.assert_error`; the `admin_app`/`client` fixtures of `tests/admin/conftest.py`.
- Produces:
  - Route `analytics_override_fidelity()` at `GET /api/v1/analytics/override-fidelity`, behind `require_auth`. Body = the `build_report` payload, keys exactly `rows, summary, verdict, engine_flags, asof, currency_symbol` (V173-13's `OverrideFidelity` type reads it).
  - Seam `_override_inputs() -> tuple[list, dict[str, dict]]`: delegates to `override_io.load_inputs()`.
  - Seam `_override_verdict() -> dict | None`: delegates to `override_io.stored_verdict()` (the `preregistration_verdicts` row, or `None`).
  - Tests monkeypatch both seams on the module; nothing in the route touches a store directly.

**Why it is computed on request, and why it only reads.** About 36 rows, a replay each, read from the local bar cache: no store and no cron for the rows (spec §5). The verdict is the stored record from `preregistration_verdicts`, read through `override_io.stored_verdict` and handed to `build_report`, which shows it as stored or `WAITING`. The route **never evaluates** and never writes: only the bot's daily job does (`override_io.run_daily_check`, V173-26/V173-27). The override set is global, not scoped: the panel shows every manual close, so the route takes no scope parameters. The ledger file is not read here any more (revised 2026-10-19); a database error reading the stored verdict surfaces through the blueprint's ordinary 500 handling.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/admin/test_api_v1_analytics_override_fidelity.py`:

```python
"""v173 §5: GET /api/v1/analytics/override-fidelity -- computed on request,
the verdict read from preregistration_verdicts and never evaluated."""
import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_io as oio
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.analytics import runner_path as rp
from tests.admin.api_v1_contract import assert_error
from tests.analytics.test_override_fidelity_replay import LAST_DAY, STOP_BAR, frame, plan
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

_LOGIN = {"username": "admin", "password": "admin"}
_URL = "/api/v1/analytics/override-fidelity"
PAYLOAD_KEYS = {"rows", "summary", "verdict", "engine_flags", "asof", "currency_symbol"}
ROW_KEYS = {"plan_id", "ticker", "horizon", "direction", "state_at_close", "close_date",
            "bulk", "approx", "price_source", "status", "actual_r", "engine_r", "delta_r",
            "delta_r_gross", "actual_usd", "engine_usd", "delta_usd", "engine_exit_reason",
            "outcome", "source"}
VERDICT_KEYS = {"state", "n", "needed", "weeks", "week_floor", "open_n", "excluded_share",
                "evaluable", "waiting_on", "recorded", "recorded_on", "mean_delta_r",
                "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n"}
RECORD = {"ledger_id": "v173-override-fidelity", "verdict": "COST", "recorded_on": "2027-03-01",
          "n": 31, "weeks": 12, "mean_delta_r": -0.25, "mean_delta_r_gross": -0.23,
          "ci": [-0.4, -0.1], "sum_delta_r": -7.75, "sum_delta_usd": -1550.0,
          "bar_close_n": 2, "excluded_share": 0.0,
          "engine_flags": {"stall_exit_enabled": False, "runner_structure_exit": "off"},
          "rows": []}
SHARES = 10          # dollar risk = 10 x |100 - 95| = 50


def _boom(*_args, **_kwargs):
    raise AssertionError("the API never evaluates and never writes the verdict")


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def api(admin_app, monkeypatch):
    """One stamped individual override (a), one bulk-clear close (b), no DB,
    no stored verdict. The analytics module is imported here, after
    admin_app's reloads; each evaluating or writing call raises."""
    import swingbot.admin.api_v1.analytics as analytics_api

    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    plans = [plan(plan_id="a", ticker="AAA"),
             plan(plan_id="b", ticker="BBB", reason="manual_bulk",
                  close_at="2026-10-08T18:00:00+00:00")]
    monkeypatch.setattr(analytics_api, "_override_inputs",
                        lambda: (plans, {"a": {"id": "t-a", "plan_id": "a", "shares": SHARES}}))
    monkeypatch.setattr(analytics_api, "_override_verdict", lambda: None)
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: frame({19: STOP_BAR}))
    monkeypatch.setattr(of, "latest_completed_session", lambda now: LAST_DAY)
    for module, name in ((ov, "evaluate_verdict"), (ov, "verdict_record"),
                         (oio, "run_daily_check")):
        monkeypatch.setattr(module, name, _boom)
    return analytics_api


def test_requires_auth(client):
    assert_error(client.get(_URL), "auth", 401)


def test_shape_and_the_bulk_exclusion(api, logged_in):
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == PAYLOAD_KEYS
    assert (body["asof"], body["currency_symbol"]) == ("2026-10-19", "$")
    assert body["engine_flags"] == {"stall_exit_enabled": False, "runner_structure_exit": "off"}
    assert [r["plan_id"] for r in body["rows"]] == ["b", "a"]        # newest close first
    assert set(of.ROW_FIELDS) == ROW_KEYS
    assert all(set(r) == ROW_KEYS for r in body["rows"])
    by_id = {r["plan_id"]: r for r in body["rows"]}
    assert (by_id["b"]["bulk"], by_id["a"]["bulk"]) == (True, False)
    summary = body["summary"]
    assert (summary["bulk_n"], summary["bulk_dates"]) == (1, {"2026-10-08": 1})
    assert summary["counted_n"] == 1                                  # bulk shown, never summed
    assert sum(summary["n_by_status"].values()) == 1                  # eligible rows only
    assert "sum_delta_r_gross" in summary
    verdict = body["verdict"]
    assert set(verdict) == VERDICT_KEYS
    assert (verdict["state"], verdict["recorded"], verdict["recorded_on"]) == ("WAITING", False, None)
    assert (verdict["mean_delta_r"], verdict["ci"], verdict["sum_delta_r"]) == (None, None, None)
    assert verdict["waiting_on"] == ["count", "weeks"]                # 1 row, 1 week
    assert verdict["bar_close_n"] == 0                                # a's stamp is a quote


def test_dollars_sit_beside_every_r_figure(api, logged_in):
    rows = {r["plan_id"]: r for r in logged_in.get(_URL).get_json()["rows"]}
    a = rows["a"]
    assert a["status"] == "resolved"
    for key in ("actual", "engine", "delta"):
        assert a[f"{key}_usd"] == pytest.approx(a[f"{key}_r"] * 50, abs=0.01)
    b = rows["b"]                                                     # no linked trade
    assert (b["actual_usd"], b["engine_usd"], b["delta_usd"]) == (None, None, None)


def test_the_stored_verdict_is_returned_as_stored(api, logged_in, monkeypatch):
    seen = []
    monkeypatch.setattr(api, "_override_verdict", lambda: seen.append(1) or RECORD)
    verdict = logged_in.get(_URL).get_json()["verdict"]
    assert seen == [1]
    assert (verdict["state"], verdict["recorded"], verdict["recorded_on"]) == (
        "COST", True, "2027-03-01")
    assert (verdict["n"], verdict["weeks"]) == (31, 12)               # the recorded figures
    assert (verdict["mean_delta_r"], verdict["mean_delta_r_gross"], verdict["ci"]) == (
        -0.25, -0.23, [-0.4, -0.1])
    assert (verdict["sum_delta_r"], verdict["sum_delta_usd"], verdict["bar_close_n"]) == (
        -7.75, -1550.0, 2)
    assert (verdict["open_n"], verdict["evaluable"]) == (0, False)    # live fields stay live
    assert verdict["waiting_on"] == ["count", "weeks"]


def test_build_report_gets_the_stored_record_and_nothing_else(api, logged_in, monkeypatch):
    calls = []

    def fake(plans, trades, bars_fn, asof, recorded, currency_symbol):
        calls.append((len(plans), asof, recorded, currency_symbol))
        return {"rows": [], "summary": {}, "verdict": {}, "engine_flags": {}, "asof": "",
                "currency_symbol": currency_symbol}

    monkeypatch.setattr(ov, "build_report", fake)
    monkeypatch.setattr(api, "_override_verdict", lambda: RECORD)
    assert logged_in.get(_URL).status_code == 200
    assert calls == [(2, LAST_DAY, RECORD, "$")]


def test_the_seams_delegate_to_override_io(admin_app, monkeypatch):
    import swingbot.admin.api_v1.analytics as analytics_api

    monkeypatch.setattr(oio, "load_inputs", lambda: (["plan-a"], {"a": {"id": "t1"}}))
    monkeypatch.setattr(oio, "stored_verdict", lambda repo=None: RECORD)
    assert analytics_api._override_inputs() == (["plan-a"], {"a": {"id": "t1"}})
    assert analytics_api._override_verdict() is RECORD
```

The `api` fixture makes `evaluate_verdict`, `verdict_record` and `run_daily_check` raise for every request, so each test that reaches the route proves it never evaluates. `test_the_seams_delegate_to_override_io` patches the `override_io` module attributes, which the seams look up at call time (lazy import inside each seam).

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_override_fidelity.py
```

Expected: `test_requires_auth` fails with a 404 (the route does not exist); the `api` tests fail on `monkeypatch.setattr(analytics_api, "_override_inputs", ...)` with `AttributeError: ... has no attribute '_override_inputs'`.

- [ ] **Step 3: Add the seams and the route**

In `$WT/swingbot/admin/api_v1/analytics.py`, change the top import

```python
from datetime import datetime
```

to

```python
from datetime import datetime, timezone
```

Then insert directly after the `analytics_partials` route (it ends with `return jsonify({**report, **echo(scope, len(plans))})`):

```python
def _override_inputs() -> tuple[list, dict[str, dict]]:
    """Every plan, and every paper trade keyed by its plan id (v173 override_io)."""
    from swingbot.core.analytics import override_io as oio

    return oio.load_inputs()


def _override_verdict() -> dict | None:
    """The stored v173 verdict record from preregistration_verdicts, or None. Read only."""
    from swingbot.core.analytics import override_io as oio

    return oio.stored_verdict()


@api_v1.route("/analytics/override-fidelity", methods=["GET"])
@require_auth
def analytics_override_fidelity():
    """Manual overrides vs the engine left alone (spec v173 §5).

    Computed on request: each manual close replayed from its fill through
    the v2 exit engine on the live scan's bar cache (never fetched). The
    verdict is the stored preregistration_verdicts record, or WAITING; this
    route never evaluates or writes it -- only the bot's daily job does.
    Global, not scoped: every manual close is in the table."""
    from swingbot import config
    from swingbot.core.analytics import override_fidelity as of
    from swingbot.core.analytics import override_verdict as ov
    from swingbot.core.analytics import runner_path as rp

    recorded = _override_verdict()
    plans, trades = _override_inputs()
    asof = of.latest_completed_session(datetime.now(timezone.utc))
    return jsonify(ov.build_report(plans, trades, rp.cached_daily_bars, asof, recorded,
                                   config.CURRENCY_SYMBOL))
```

Every name is looked up on its module at request time (`rp.cached_daily_bars`, `of.latest_completed_session`, `ov.build_report`, the two seams), which is what lets the test pin the bars, the clock and the stored verdict without a database.

- [ ] **Step 4: Run the test to verify it passes**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_override_fidelity.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_partials.py
```

Expected: both PASS, `0 failed`, `0 xfailed` (the second confirms the neighbouring route is untouched).

If `test_dollars_sit_beside_every_r_figure` fails on `abs=0.01`, check the rounding order: `to_usd` rounds `r * risk` where `r` is already rounded to 3 dp, so the difference is at most `0.0005 * 50 = 0.025`. Widen to `abs=0.03` only if the observed gap is exactly that rounding; any larger gap is a wrong dollar risk (it must be `10 x 5 = 50`). If `test_the_stored_verdict_is_returned_as_stored` reads a live `n` (1), V173-10's `verdict_payload` is not taking the recorded fields from the record: report it, never adjust this test.

- [ ] **Step 5: Read-only and complexity**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides grep -n "evaluate_verdict\|verdict_record\|run_daily_check\|insert_once\|append_ledger_row" -- swingbot/admin/
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/admin/api_v1/analytics.py
```

Expected: the grep prints nothing; `radon` prints no line for `_override_inputs`, `_override_verdict` or `analytics_override_fidelity` (all grade A). Any other line printed must already be in `complexity_baseline.json`.

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics_override_fidelity.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): GET /api/v1/analytics/override-fidelity, verdict read from the table"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-13: SPA: models, `ApiClient.analyticsOverrideFidelity`, store slice `overrideFidelity`, research tone map

**Model:** sonnet — client and store following the partials slice

**Files:**
- Modify: `frontend/src/app/api/models.ts` (a new block directly before `export interface AnalyticsPlans {`, around line 717)
- Modify: `frontend/src/app/api/api-client.ts` (the `./models` import block, lines 7-72; a method after `analyticsPartials`, around line 275)
- Modify: `frontend/src/app/stores/analytics.store.ts` (models import :15-31, state interface :~379, `PanelKey` :203-206, initial state :~468, `loadExecution` :718-722, `resolveExecution` :856-860, `reload()` map :927-937)
- Modify: `frontend/src/app/workspaces/research/research.ts` (`VERDICT_TONE` :32-42: exported, three entries added)
- Modify: `frontend/src/app/workspaces/research/research.spec.ts` (one `describe` for the tone map; the spec assertion the revision asks for)
- Create: `frontend/src/app/workspaces/analytics/tabs/override-fidelity.fixture.ts` (test data shared by this task's spec and V173-14's specs, after the `partials.fixture.ts` precedent)
- Create: `frontend/src/app/stores/analytics.override-fidelity.spec.ts`

**Interfaces:**
- Consumes: the V173-12 payload (Global Constraints **Report payload**, with the value shapes in this part's header).
- Produces (part 4b's V173-14 imports these by name):
  - In `api/models.ts`: `OverrideStatus` (eight), `OverrideVerdictState`, `OverrideWaitingOn`, `OverrideOutcome`, `OverrideRowDto` (20 fields), `OverrideSplit`, `OverrideSummary`, `OverrideVerdict` (17 fields), `OverrideFidelity` (exact shapes in Step 3).
  - `ApiClient.analyticsOverrideFidelity(): Observable<OverrideFidelity>`: `GET /api/v1/analytics/override-fidelity`, no query parameters (global, never scoped).
  - `AnalyticsStore`: state `overrideFidelity: OverrideFidelity | null`, `overrideFidelityError: string | null` (signals of the same names); `PanelKey` gains `'overrideFidelity'`; the Execution tab's load and resolve fetch it; `reload('overrideFidelity')` refetches only it.
  - In `override-fidelity.fixture.ts`: `OVERRIDE_FIDELITY_FIXTURE: OverrideFidelity` (WAITING, 1 counted row; one bulk, one approx and one stale row), `overrideFixture(patch?: { verdict?: Partial<OverrideVerdict>; summary?: Partial<OverrideSummary>; rows?: OverrideRowDto[] }): OverrideFidelity`, and three whole verdicts: `VERDICT_WAITING_ON` (count met, other floors not), `VERDICT_FLOORS_MET` (evaluable, not recorded), `VERDICT_RECORDED_COST` (a stored COST record).
  - In `research.ts`: `export const VERDICT_TONE` with `SAVED: 'good'`, `COST: 'bad'`, `INCONCLUSIVE: 'neutral'` added.

**Why global.** The override set is every manual close in the book. The scope bar's date range, strategy and ledger filters would silently cut rows out of a verdict population that the spec defines over all of them, so the request carries no scope. It never feeds `scopeN` either (the scope bar's N counts closed trades in scope).

- [ ] **Step 1: Write the fixture and the failing specs**

Create `$WT/frontend/src/app/workspaces/analytics/tabs/override-fidelity.fixture.ts`:

```ts
import { OverrideFidelity, OverrideRowDto, OverrideSummary, OverrideVerdict } from '../../../api/models';

/* v173 — one payload per row kind: a stamped individual override (counted),
 * an estimated (approx) row, a bulk-clear row and a stale row; plus the three
 * verdict states the badge words differently. Figures are illustrative, in the
 * shape GET /api/v1/analytics/override-fidelity returns. */

const row = (patch: Partial<OverrideRowDto>): OverrideRowDto => ({
  plan_id: 'p', ticker: 'AAA', horizon: '2w', direction: 'bullish', state_at_close: 'ACTIVE',
  close_date: '2026-10-07', bulk: false, approx: false, price_source: 'quote', status: 'resolved',
  actual_r: 0.168, engine_r: -1.019, delta_r: 1.187, delta_r_gross: 1.207, actual_usd: 8.4,
  engine_usd: -50.95, delta_usd: 59.35, engine_exit_reason: 'stop', outcome: 'helped',
  source: 'manual', ...patch,
});

const WAITING: OverrideVerdict = {
  state: 'WAITING', n: 1, needed: 30, weeks: 1, week_floor: 10, open_n: 0,
  excluded_share: 0.5, evaluable: false, waiting_on: ['count', 'weeks', 'excluded'],
  recorded: false, recorded_on: null, mean_delta_r: null, mean_delta_r_gross: null, ci: null,
  sum_delta_r: null, sum_delta_usd: null, bar_close_n: 0,
};

export const OVERRIDE_FIDELITY_FIXTURE: OverrideFidelity = {
  rows: [
    row({ plan_id: 'a', ticker: 'AAA' }),
    row({ plan_id: 'b', ticker: 'BBB', close_date: '2026-10-06', approx: true,
      price_source: 'session_close', actual_r: -0.5, engine_r: -0.2, delta_r: -0.3,
      delta_r_gross: -0.28, actual_usd: null, engine_usd: null, delta_usd: null,
      engine_exit_reason: 'runner_trail', outcome: 'hurt' }),
    row({ plan_id: 'c', ticker: 'CCC', close_date: '2026-09-30', bulk: true,
      actual_usd: null, engine_usd: null, delta_usd: null }),
    row({ plan_id: 'd', ticker: 'DDD', close_date: '2026-09-22', status: 'stale',
      state_at_close: 'PARTIAL', actual_r: null, engine_r: null, delta_r: null,
      delta_r_gross: null, actual_usd: null, engine_usd: null, delta_usd: null,
      engine_exit_reason: null, outcome: null }),
  ],
  summary: {
    n_by_status: { resolved: 1, open: 0, unstamped: 0, stale: 1, ambiguous: 0,
      parity_mismatch: 0, split_affected: 0, unreplayable: 0 },
    bulk_n: 1, bulk_dates: { '2026-09-30': 1 }, approx_n: 1, counted_n: 1,
    sum_delta_r: 1.187, sum_delta_r_gross: 1.207, sum_delta_usd: 59.35, usd_missing_n: 0,
    helped: 1, hurt: 0, neutral: 0,
    splits: {
      state_at_close: { ACTIVE: { n: 1, sum_delta_r: 1.187, sum_delta_usd: 59.35 } },
      horizon: { '2w': { n: 1, sum_delta_r: 1.187, sum_delta_usd: 59.35 } },
      direction: { bullish: { n: 1, sum_delta_r: 1.187, sum_delta_usd: 59.35 } },
    },
  },
  verdict: WAITING,
  engine_flags: { stall_exit_enabled: false, runner_structure_exit: 'off' },
  asof: '2026-10-19',
  currency_symbol: '$',
};

/** WAITING with the count met: 34 counted, but 8 of 10 weeks, 2 open, 25% left out. */
export const VERDICT_WAITING_ON: OverrideVerdict = {
  ...WAITING, n: 34, weeks: 8, open_n: 2, excluded_share: 0.25,
  waiting_on: ['weeks', 'open', 'excluded'],
};

/** WAITING with every floor met and nothing recorded yet. */
export const VERDICT_FLOORS_MET: OverrideVerdict = {
  ...WAITING, n: 34, weeks: 11, open_n: 0, excluded_share: 0.1, evaluable: true, waiting_on: [],
};

/** A stored COST record: state, n, weeks, the mean/CI/sums and bar_close_n are the
 *  recorded figures; open_n, excluded_share, evaluable and waiting_on are live. */
export const VERDICT_RECORDED_COST: OverrideVerdict = {
  ...WAITING, state: 'COST', n: 31, weeks: 12, open_n: 0, excluded_share: 0.05, evaluable: true,
  waiting_on: [], recorded: true, recorded_on: '2026-12-04', mean_delta_r: -0.22,
  mean_delta_r_gross: -0.2, ci: [-0.24, -0.2], sum_delta_r: -6.82, sum_delta_usd: -1364,
  bar_close_n: 2,
};

/** The fixture with a patched verdict, summary or row list (the specs' one builder). */
export function overrideFixture(patch: {
  verdict?: Partial<OverrideVerdict>; summary?: Partial<OverrideSummary>; rows?: OverrideRowDto[];
} = {}): OverrideFidelity {
  const base = OVERRIDE_FIDELITY_FIXTURE;
  return {
    ...base,
    rows: patch.rows ?? base.rows,
    summary: { ...base.summary, ...patch.summary },
    verdict: { ...base.verdict, ...patch.verdict },
  };
}
```

Create `$WT/frontend/src/app/stores/analytics.override-fidelity.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { OVERRIDE_FIDELITY_FIXTURE } from '../workspaces/analytics/tabs/override-fidelity.fixture';
import { AnalyticsStore } from './analytics.store';

/* v173 — the "Overrides vs engine" slice: global, its own error, loaded with Execution. */

const URL = '/api/v1/analytics/override-fidelity';

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();
  changes(name: string): Signal<number> {
    if (!this.counters.has(name)) this.counters.set(name, signal(0));
    return this.counters.get(name)!.asReadonly();
  }
}

describe('AnalyticsStore — overrideFidelity slice', () => {
  let store: InstanceType<typeof AnalyticsStore>;
  let backend: HttpTestingController;

  const flushOthers = (): void =>
    backend.match((req) => req.url !== URL).forEach((request) => request.flush({}));

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        AnalyticsStore,
      ],
    });
    store = TestBed.inject(AnalyticsStore);
    backend = TestBed.inject(HttpTestingController);
  });

  it('starts empty, with no error', () => {
    expect(store.overrideFidelity()).toBeNull();
    expect(store.overrideFidelityError()).toBeNull();
  });

  it('loads with the Execution tab and is never scoped', () => {
    store.setScope({ strategy: 'RSI', from: '2026-09-01' });
    backend.match(() => true).forEach((request) => request.flush({}));   // the Overview load
    store.setTab('execution');
    const request = backend.expectOne((req) => req.url === URL);
    expect(request.request.params.keys()).toEqual([]);
    request.flush(OVERRIDE_FIDELITY_FIXTURE);
    flushOthers();
    backend.verify();
    const loaded = store.overrideFidelity();
    expect(loaded?.summary.counted_n).toBe(1);
    expect(loaded?.summary.sum_delta_r_gross).toBe(1.207);
    expect(loaded?.verdict.state).toBe('WAITING');
    expect(loaded?.verdict.waiting_on).toEqual(['count', 'weeks', 'excluded']);
    expect(loaded?.rows[0].delta_r_gross).toBe(1.207);
  });

  it('is not fetched by another tab', () => {
    store.setTab('partials');
    expect(backend.match((req) => req.url === URL)).toEqual([]);
    backend.match(() => true).forEach((request) => request.flush({}));
  });

  it('keeps its own error and retries only itself', () => {
    store.setTab('execution');
    backend.expectOne((req) => req.url === URL)
      .flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });
    flushOthers();
    expect(store.overrideFidelityError()).not.toBeNull();
    store.reload('overrideFidelity');
    backend.expectOne((req) => req.url === URL).flush(OVERRIDE_FIDELITY_FIXTURE);
    backend.verify();                                // nothing else was refetched
    expect(store.overrideFidelityError()).toBeNull();
    expect(store.overrideFidelity()?.rows.length).toBe(4);
  });
});
```

In `$WT/frontend/src/app/workspaces/research/research.spec.ts`, change the import `import { DISCLAIMER, Research } from './research';` to `import { DISCLAIMER, Research, VERDICT_TONE } from './research';` and append at the end of the file:

```ts
describe('VERDICT_TONE', () => {
  it('colours the v173 override verdicts by how the measurement came out', () => {
    expect(VERDICT_TONE['SAVED']).toBe('good');
    expect(VERDICT_TONE['COST']).toBe('bad');
    expect(VERDICT_TONE['INCONCLUSIVE']).toBe('neutral');
    expect(VERDICT_TONE['PASS']).toBe('good');          // the existing entries are untouched
    expect(VERDICT_TONE['SCREEN-UNDERPOWERED']).toBe('warn');
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/stores/analytics.override-fidelity.spec.ts
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/research/research.spec.ts
```

Expected: the first FAILS at compile time: `Module '"../../../api/models"' has no exported member 'OverrideFidelity'` (and `store.overrideFidelity` is not a function). The second FAILS: `'./research'` has no exported member `VERDICT_TONE`.

- [ ] **Step 3: Add the types**

In `$WT/frontend/src/app/api/models.ts`, insert directly before `export interface AnalyticsPlans {`:

```ts
/* v173 — manual overrides vs the engine (GET /analytics/override-fidelity).
 * Every figure is computed server-side (`swingbot/core/analytics/
 * override_fidelity.py`, `override_verdict.py`); R and dollars are net of
 * modelled costs and pre-tax, dollars at the plan's modelled position size.
 * Global, never scoped. */
export type OverrideStatus =
  | 'resolved' | 'open' | 'unstamped' | 'stale' | 'ambiguous' | 'parity_mismatch'
  | 'split_affected' | 'unreplayable';
export type OverrideVerdictState = 'WAITING' | 'COST' | 'SAVED' | 'INCONCLUSIVE';
/** The verdict floors still failing, in this order. */
export type OverrideWaitingOn = 'count' | 'weeks' | 'open' | 'excluded';
export type OverrideOutcome = 'helped' | 'hurt' | 'neutral';
export interface OverrideRowDto {
  plan_id: string; ticker: string; horizon: string; direction: string;
  state_at_close: 'ACTIVE' | 'PARTIAL';
  /** ISO session date of the manual close, or null when it could not be assigned. */
  close_date: string | null;
  /** A bulk-clear close: shown, never counted. */
  bulk: boolean;
  /** Estimated exit (no stamp, or a bar-close stamp older than the close session). Shown, never counted. */
  approx: boolean;
  price_source: string;
  status: OverrideStatus;
  actual_r: number | null; engine_r: number | null; delta_r: number | null;
  /** The same delta before modelled costs: descriptive only, never in the verdict. */
  delta_r_gross: number | null;
  /** Null when the plan has no linked trade with shares: the row shows R only. */
  actual_usd: number | null; engine_usd: number | null; delta_usd: number | null;
  engine_exit_reason: string | null;
  outcome: OverrideOutcome | null;
  source: string;
}
export interface OverrideSplit { n: number; sum_delta_r: number; sum_delta_usd: number; }
export interface OverrideSummary {
  /** Eligible (individual, not estimated) rows only; bulk and approx rows are counted apart. */
  n_by_status: Record<OverrideStatus, number>;
  bulk_n: number;
  /** ISO date -> closes in that bulk clear, sorted by date. */
  bulk_dates: Record<string, number>;
  approx_n: number;
  counted_n: number;
  sum_delta_r: number; sum_delta_r_gross: number; sum_delta_usd: number; usd_missing_n: number;
  helped: number; hurt: number; neutral: number;
  splits: Record<'state_at_close' | 'horizon' | 'direction', Record<string, OverrideSplit>>;
}
export interface OverrideVerdict {
  /** WAITING until a verdict is stored, even when `evaluable` is true. */
  state: OverrideVerdictState;
  /** Recorded figures once `recorded`; live counts before. */
  n: number; needed: number; weeks: number; week_floor: number;
  /** Always live. */
  open_n: number; excluded_share: number; evaluable: boolean; waiting_on: OverrideWaitingOn[];
  recorded: boolean; recorded_on: string | null;
  /** Null until recorded. */
  mean_delta_r: number | null; mean_delta_r_gross: number | null; ci: [number, number] | null;
  sum_delta_r: number | null; sum_delta_usd: number | null;
  /** Counted overrides priced from a bar close, not a quote. */
  bar_close_n: number;
}
export interface OverrideFidelity {
  rows: OverrideRowDto[];
  summary: OverrideSummary;
  verdict: OverrideVerdict;
  engine_flags: { stall_exit_enabled: boolean; runner_structure_exit: string };
  asof: string;
  currency_symbol: string;
}

```

- [ ] **Step 4: Add the client method**

In `$WT/frontend/src/app/api/api-client.ts`, add `OverrideFidelity,` to the `import { ... } from './models';` block (keep the block's order: put it after the last `Analytics...` name), then insert directly after the `analyticsPartials(...)` method:

```ts
  /** v173 — manual overrides vs the engine. Global: every manual close, never scoped. */
  analyticsOverrideFidelity(): Observable<OverrideFidelity> {
    return this.http.get<OverrideFidelity>(`${this.base}/analytics/override-fidelity`);
  }
```

- [ ] **Step 5: Add the store slice**

In `$WT/frontend/src/app/stores/analytics.store.ts`:

1. Add `OverrideFidelity,` to the `import { ... } from '../api/models';` block (after `LiveLossWatch,`).
2. `PanelKey`: change the last line `| 'byHorizon' | 'byDirection' | 'byDow' | 'partials';` to

```ts
  | 'byHorizon' | 'byDirection' | 'byDow' | 'partials' | 'overrideFidelity';
```

3. State interface, directly after `partials: AnalyticsPartials | null;         partialsError: string | null;`:

```ts
  /** v173 — the Execution tab's "Overrides vs engine" panel. Global, never
   *  scoped, and never feeds scopeN. */
  overrideFidelity: OverrideFidelity | null; overrideFidelityError: string | null;
```

4. Initial state, directly after `partials: null, partialsError: null,`:

```ts
      overrideFidelity: null, overrideFidelityError: null,
```

5. Directly after `const s = (): BookScope => store.scope();`, add one loader the three call sites share:

```ts
    /** v173 — global: no scope argument, so a scope change cannot cut the override set. */
    const loadOverrideFidelity = (): void =>
      fetchPanel(api.analyticsOverrideFidelity(), 'overrideFidelity', 'overrideFidelityError');
```

6. `loadExecution` becomes:

```ts
    const loadExecution = (): void => {
      fetchPanel(api.analyticsExitQuality(s()), 'exitQuality', 'exitQualityError');
      fetchPanel(api.analyticsJournal(s()), 'journal', 'journalError');
      fetchPanel(api.analyticsPerformance(s()), 'performance', 'performanceError');
      loadOverrideFidelity();
    };
```

7. `resolveExecution` becomes:

```ts
    const resolveExecution = (): Observable<void> =>
      resolveOne(api.analyticsExitQuality(s()), 'exitQuality', 'exitQualityError', () => {
        fetchPanel(api.analyticsJournal(s()), 'journal', 'journalError');
        fetchPanel(api.analyticsPerformance(s()), 'performance', 'performanceError');
        loadOverrideFidelity();
      });
```

8. In `reload()`'s `one: Record<PanelKey, () => void>` map, after the `partials:` entry:

```ts
          overrideFidelity: loadOverrideFidelity,
```

`Record<PanelKey, ...>` makes the compiler reject a `PanelKey` without a reload entry, so step 8 is not optional.

- [ ] **Step 6: Export and extend the research tone map**

In `$WT/frontend/src/app/workspaces/research/research.ts`, change `const VERDICT_TONE: Record<string, ChipTone> = {` to `export const VERDICT_TONE: Record<string, ChipTone> = {` and add, after `'SCREEN-UNDERPOWERED': 'warn',`:

```ts
  // v173 override fidelity: how the overrides came out against the engine.
  SAVED: 'good',
  COST: 'bad',
  INCONCLUSIVE: 'neutral',
```

The comment above the map (a colour says how the measurement came out, never whether to act on it) covers the new entries unchanged. `INCONCLUSIVE` is listed explicitly even though the fallback is `'neutral'`, so the spec assertion pins it.

- [ ] **Step 7: Run the new specs and the neighbouring store specs**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/stores/analytics.override-fidelity.spec.ts
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/research/research.spec.ts
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include "src/app/stores/analytics*.spec.ts"
```

Expected: all three PASS with no failures. The third run covers the existing analytics store specs: any of them that does `backend.verify()` after `setTab('execution')` without flushing every request now sees one more request. Fix such a spec by flushing the override request too (`backend.match((r) => r.url === '/api/v1/analytics/override-fidelity').forEach((r) => r.flush({}))`); never drop the fetch from the store.

- [ ] **Step 8: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.override-fidelity.spec.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity.fixture.ts frontend/src/app/workspaces/research/research.ts frontend/src/app/workspaces/research/research.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(ui): override-fidelity types, client, store slice and verdict tones (v173)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Add any existing store spec fixed in Step 7 to the same commit. The last command checks the main tree stayed clean of branch edits.
