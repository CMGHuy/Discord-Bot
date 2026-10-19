# v173 Execution fidelity, part 4: report script, API route, SPA slice and the panel

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-11:" -A 400 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §4 (one evaluation, written once) and §5 (report script, API, panel)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`) and the task ledger. Every task below implicitly includes those Global Constraints, in particular **Report payload**, **Verdict**, **Report script**, **UI copy (verbatim)** and **UI layout**. Tasks: V173-11..V173-14. V173-11 needs V173-10 committed on the branch; V173-12 needs V173-11 (same payload; it is the only task touching `analytics.py`). V173-13 depends only on the payload contract and may run in Wave A. V173-14 needs V173-13. V173-12 and V173-14 are disjoint and may run together.

`$WT = E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides`. Every path below is under `$WT`; commands spell it out in full because shell variables do not persist between Bash calls.

**What earlier tasks created** (check with `git -C $WT grep -n "<name>" -- swingbot/core/analytics/`; a missing one means an earlier task is not on the branch: stop and report, never re-create it): V173-7 `latest_completed_session(now) -> date`, `OverrideRow`, `ROW_FIELDS`, `STATUSES`, `LEDGER_ID`; V173-9 `replay_override(plan, bars, asof, trade=None)`; V173-10 `override_verdict.build_report(plans, trades_by_plan, bars_fn, asof, ledger_rows, currency_symbol)`, `evaluate_verdict(rows)`, `verdict_payload(rows, ledger_rows)`, `ledger_row(verdict, *, today)`, `SPEC_PATH`, and `override_fidelity.summarise(rows)`. **Every verdict function accepts rows in their `to_dict()` form**, so the script passes `payload["rows"]` straight in. Part 3 test helpers: `tests.analytics.test_override_fidelity_replay` (`plan(...)`, `frame(rows=None, *, n=26)`, `STOP_BAR`, `LAST_DAY = date(2026, 10, 19)`) and `tests.analytics.test_override_verdict.spread(n, weeks, delta)`. **Value shapes fixed by Part 3:** `n_by_status` is `{status: int}` over all seven statuses, counting **eligible** (individual, stamped) rows only; bulk rows count only in `bulk_n`, non-bulk approx rows only in `approx_n`, so no exclusion note counts a row twice. `bulk_dates` is `{iso_date: int}` sorted by date. `sum_delta_r` (3 dp) and `sum_delta_usd` (2 dp) cover counted rows, `0.0` with none. `engine_flags` is `{"stall_exit_enabled": bool, "runner_structure_exit": str}`. `verdict.ci` is `[lo, hi]` or `null`. **Without a ledger row, `verdict_payload` reports `WAITING` even when `evaluable` is true** (only the script under `--production` evaluates); the panel words that case "floors met, awaiting the recorded evaluation", never "34 of 30 needed". `rows` are newest `close_date` first. A PARTIAL plan whose live TP1 falls on the override session is `ambiguous` (no new status). **Tests never touch a database** (Global Constraints): fixture plans, fakes and monkeypatched seams (`report.PlanStore`, `report.TradeLog`, `analytics._override_inputs`, `stats.LEDGER_PATH` to a `tmp_path` file); never the production replica. Frontend specs use stubs and `HttpTestingController`.

# Phase 4: Report, API and panel (V173-11..V173-14)

### Task V173-11: Report script `execution_fidelity_report.py`

**Model:** sonnet — a CLI over finished helpers

**Files:**
- Create: `scripts/reports/execution_fidelity_report.py`
- Create: `tests/scripts/test_execution_fidelity_report.py` (`tests/scripts/` is the `tooling` suite; `tests/suites.toml` is not edited)

**Interfaces:**
- Consumes:
  - V173-7: `override_fidelity.latest_completed_session(now: datetime) -> date`; `OverrideRow.to_dict()`; `STATUSES`.
  - V173-10: `override_verdict.build_report(plans, trades_by_plan, bars_fn, asof, ledger_rows, currency_symbol) -> dict`, `evaluate_verdict(rows) -> dict`, `verdict_payload(rows, ledger_rows) -> dict`, `ledger_row(verdict, *, today: date) -> dict` (raises `ValueError` unless the verdict is a fresh COST/SAVED/INCONCLUSIVE evaluation); `override_fidelity.summarise(rows)`.
  - Existing: `stats.LEDGER_PATH`, `stats.load_ledger(path)`, `stats.append_ledger_row(row, path)` (`swingbot/core/backtesting/instrument/stats.py:110,193,204`; append refuses a duplicate id); `runner_path.cached_daily_bars` (`runner_path.py:191`); `PlanStore().all()` (`swingbot/core/planning/plan_store.py`); `TradeLog().get_trades(status=None, limit=None, ledger=None)` (`performance.py:1204`, the call `analytics._all_trades` makes); `config.CURRENCY_SYMBOL`.
  - Test helpers: Part 3's `plan`, `frame`, `STOP_BAR`, `LAST_DAY` (`tests/analytics/test_override_fidelity_replay.py`) and `spread` (`tests/analytics/test_override_verdict.py`).
- Produces (V173-19 runs it on the VM):
  - `DEV_BANNER = "DEV DATABASE: fixture data, not the real book. The ledger is never written."`
  - `load_inputs() -> tuple[list, dict[str, dict]]`: every plan from `PlanStore().all()`, and every trade from `TradeLog` keyed by `plan_id` (first record wins; trades without a `plan_id` are skipped).
  - `render(payload: dict) -> list[str]`: the printed lines (engine flags, the row table, summary and splits, exclusion counts, verdict state).
  - `main(argv: list[str] | None = None, *, inputs_fn=None, bars_fn=None, now: datetime | None = None, ledger_path: Path | None = None) -> dict`: flags `--production` and `--json PATH`; returns the payload it printed.
  - VM command (V173-19): `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/execution_fidelity_report.py --production"`.

**What the script does, and why it is the only evaluator.** §4 freezes the rule: the verdict is evaluated once, on the first run where its floors hold, and written to the ledger. A later run must never recompute it, because watching a live interval until it crosses zero inflates false positives. So the order inside `main` is fixed:

1. Without `--production`, print `DEV_BANNER` first. That run is fixture data and never writes the ledger, whatever the verdict says.
2. Load plans and trades, read the ledger, compute `asof = latest_completed_session(now)`, and call `build_report`. `build_report` never evaluates: it shows the recorded verdict or `WAITING`.
3. Only under `--production`, and only when `verdict.evaluable` is true and `verdict.recorded` is false: call `evaluate_verdict(payload["rows"])` once, build the row with `ledger_row(..., today=<UTC date of now>)`, append it with `stats.append_ledger_row`, and replace `payload["verdict"]` with `verdict_payload(rows, <re-read ledger>)`, so the printout shows the recorded verdict.
4. Print the report. If a row was written, print a mirroring instruction and then the row as **one JSON line**, the last line of output. The ledger lives in the container's copy of the repo, and V173-19 mirrors that line into `docs/superpowers/results/preregistration-ledger.jsonl` and commits it.
5. `--json PATH` writes the payload (the API body shape) to `PATH`.

The bars come only from `runner_path.cached_daily_bars`, looked up at call time, and are never fetched.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/scripts/test_execution_fidelity_report.py`:

```python
"""v173 §4-§5: the report script -- dev banner, one evaluation, ledger written once."""
import json
from datetime import datetime, timezone

import pytest

from scripts.reports import execution_fidelity_report as report
from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.backtesting.instrument import stats
from tests.analytics.test_override_fidelity_replay import LAST_DAY, STOP_BAR, frame, plan
from tests.analytics.test_override_verdict import spread
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

NOW = datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)   # Mon 17:00 ET, after the close
PAYLOAD_KEYS = {"rows", "summary", "verdict", "engine_flags", "asof", "currency_symbol"}


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "ledger.jsonl"


def _no_inputs():
    return [], {}


def _stub_report(monkeypatch, rows):
    """Stub build_report with these rows. The verdict part is the real
    verdict_payload over the ledger rows the script hands in."""
    dicts = [r.to_dict() for r in rows]

    def fake(plans, trades, bars_fn, asof, ledger_rows, currency_symbol):
        return {"rows": dicts, "summary": of.summarise(rows),
                "verdict": ov.verdict_payload(dicts, ledger_rows),
                "engine_flags": {"stall_exit_enabled": False, "runner_structure_exit": "off"},
                "asof": asof.isoformat(), "currency_symbol": currency_symbol}

    monkeypatch.setattr(report.ov, "build_report", fake)


def _evaluable(monkeypatch, delta=lambda w: -0.5 + 0.02 * w):
    """30 counted rows over 10 weeks: the floors hold (Part 3's COST spread)."""
    _stub_report(monkeypatch, spread(30, 10, delta))


# -- the dev run -------------------------------------------------------------------

def test_a_dev_run_prints_the_banner_first_and_never_writes_the_ledger(
        monkeypatch, capsys, ledger):
    _evaluable(monkeypatch)
    out = report.main([], inputs_fn=_no_inputs, now=NOW, ledger_path=ledger)
    printed = capsys.readouterr().out.splitlines()
    assert printed[0] == report.DEV_BANNER
    assert report.DEV_BANNER == ("DEV DATABASE: fixture data, not the real book. "
                                 "The ledger is never written.")
    assert not ledger.exists()
    assert (out["verdict"]["state"], out["verdict"]["evaluable"]) == ("WAITING", True)


# -- the production run: evaluate once, write once ------------------------------------

def test_the_first_evaluable_production_run_writes_one_ledger_row(monkeypatch, capsys, ledger):
    _evaluable(monkeypatch)
    out = report.main(["--production"], inputs_fn=_no_inputs, now=NOW, ledger_path=ledger)
    printed = capsys.readouterr().out.splitlines()
    assert report.DEV_BANNER not in printed
    rows = stats.load_ledger(ledger)
    assert [r["id"] for r in rows] == ["v173-override-fidelity"]
    assert (rows[0]["verdict"], rows[0]["date"], rows[0]["instrument"]) == (
        "COST", "2026-10-19", "v2")
    assert json.loads(printed[-1]) == rows[0]          # one JSON line, for mirroring
    assert (out["verdict"]["state"], out["verdict"]["recorded"]) == ("COST", True)
    assert out["verdict"]["recorded_on"] == "2026-10-19"


def test_a_recorded_verdict_is_never_recomputed(monkeypatch, ledger):
    _evaluable(monkeypatch)
    report.main(["--production"], inputs_fn=_no_inputs, now=NOW, ledger_path=ledger)
    before = ledger.read_text(encoding="utf-8")
    _evaluable(monkeypatch, delta=0.8)                 # live rows now look SAVED

    def boom(_rows):
        raise AssertionError("a recorded verdict must not be re-evaluated")

    monkeypatch.setattr(report.ov, "evaluate_verdict", boom)
    out = report.main(["--production"], inputs_fn=_no_inputs, now=NOW, ledger_path=ledger)
    assert ledger.read_text(encoding="utf-8") == before
    assert (out["verdict"]["state"], out["verdict"]["recorded"]) == ("COST", True)


def test_a_production_run_below_the_floors_writes_nothing(monkeypatch, ledger):
    _stub_report(monkeypatch, spread(29, 10, -0.5))
    out = report.main(["--production"], inputs_fn=_no_inputs, now=NOW, ledger_path=ledger)
    assert not ledger.exists()
    assert (out["verdict"]["state"], out["verdict"]["evaluable"]) == ("WAITING", False)


# -- the real pipeline on fixture data ---------------------------------------------------

def test_the_real_pipeline_replays_from_the_cache_and_writes_json(capsys, ledger, tmp_path):
    seen = []

    def bars_fn(ticker):
        seen.append(ticker)
        return frame({19: STOP_BAR})

    target = tmp_path / "out.json"
    out = report.main(["--json", str(target)],
                      inputs_fn=lambda: ([plan()], {"p1": {"id": "t1", "shares": 10}}),
                      bars_fn=bars_fn, now=NOW, ledger_path=ledger)
    assert seen == ["T"]
    assert set(out) == PAYLOAD_KEYS
    assert (out["asof"], out["currency_symbol"]) == (LAST_DAY.isoformat(), "$")
    [row] = out["rows"]
    assert (row["plan_id"], row["status"], row["bulk"], row["approx"]) == (
        "p1", "resolved", False, False)
    assert row["delta_usd"] is not None
    assert json.loads(target.read_text(encoding="utf-8")) == out
    printed = capsys.readouterr().out
    assert "stall_exit_enabled=False" in printed and "runner_structure_exit=off" in printed
    assert "resolved" in printed and "verdict WAITING" in printed
    assert not ledger.exists()


def test_render_lists_exclusions_and_the_bulk_dates():
    payload = {"rows": [], "engine_flags": {"stall_exit_enabled": True, "runner_structure_exit": "on"},
               "asof": "2026-10-19", "currency_symbol": "$",
               "summary": {"n_by_status": {s: 0 for s in of.STATUSES} | {"stale": 2},
                           "bulk_n": 15, "bulk_dates": {"2026-09-30": 15}, "approx_n": 3,
                           "counted_n": 0, "sum_delta_r": 0.0, "sum_delta_usd": 0.0,
                           "usd_missing_n": 0, "helped": 0, "hurt": 0, "neutral": 0,
                           "splits": {"state_at_close": {}, "horizon": {}, "direction": {}}},
               "verdict": {"state": "WAITING", "n": 0, "needed": 30, "weeks": 0,
                           "week_floor": 10, "open_n": 0, "excluded_share": 1.0,
                           "evaluable": False, "recorded": False, "recorded_on": None,
                           "mean_delta_r": None, "ci": None}}
    text = "\n".join(report.render(payload))
    assert "No manual overrides in scope." in text
    assert "bulk clear 2026-09-30: 15 (not decisions, left out)" in text
    assert "approx (estimated exit): 3 (shown, not counted)" in text
    assert "stale: 2" in text
    assert "verdict WAITING: 0 of 30 counted rows, 0 of 10 weeks" in text


# -- inputs ---------------------------------------------------------------------------

def test_load_inputs_keys_trades_by_plan_id(monkeypatch):
    class FakeStore:
        def all(self):
            return ["plan-a", "plan-b"]

    class FakeLog:
        def get_trades(self, status=None, limit=None, ledger=None):
            assert (status, limit, ledger) == (None, None, None)   # every trade, every ledger
            return [{"id": "t1", "plan_id": "a", "shares": 5},
                    {"id": "t2", "plan_id": None},
                    {"id": "t3", "plan_id": "a", "shares": 9}]

    monkeypatch.setattr(report, "PlanStore", FakeStore)
    monkeypatch.setattr(report, "TradeLog", FakeLog)
    plans, trades = report.load_inputs()
    assert plans == ["plan-a", "plan-b"]
    assert trades == {"a": {"id": "t1", "plan_id": "a", "shares": 5}}
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/scripts/test_execution_fidelity_report.py
```

Expected: collection error, `ModuleNotFoundError: No module named 'scripts.reports.execution_fidelity_report'`.

- [ ] **Step 3: Write the script**

Create `$WT/scripts/reports/execution_fidelity_report.py`:

```python
#!/usr/bin/env python3
"""v173: manual overrides against the engine left alone (spec §4-§5).

Replays every manual close from its real fill through the v2 exit engine,
prints one row per override with exactly one status, the descriptive
summary and the verdict state. Reads plans, linked trades and the live
scan's bar cache (market_data/daily); never fetches.

The verdict rule is frozen and evaluated ONCE: the first --production run
where its floors hold writes one ledger row, printed as a JSON line to be
mirrored into the repo. Every later run shows that row and never
recomputes it. Without --production (any dev database) a banner says the
data is fixture data, and the ledger is never written.

    # on the VM, against the real book:
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot \
        python scripts/reports/execution_fidelity_report.py --production"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot import config  # noqa: E402
from swingbot.core.analytics import override_fidelity as of  # noqa: E402
from swingbot.core.analytics import override_verdict as ov  # noqa: E402
from swingbot.core.analytics import runner_path as rp  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.planning.plan_store import PlanStore  # noqa: E402
from swingbot.core.tracking.performance import TradeLog  # noqa: E402

DEV_BANNER = "DEV DATABASE: fixture data, not the real book. The ledger is never written."
_MIRROR = ("LEDGER ROW WRITTEN in this checkout. Mirror the next line into "
           "docs/superpowers/results/preregistration-ledger.jsonl and commit it:")


def load_inputs() -> tuple[list, dict[str, dict]]:
    """Every plan, and every paper trade keyed by its plan id (first wins)."""
    plans = PlanStore().all()
    trades = TradeLog().get_trades(status=None, limit=None, ledger=None) or []
    by_plan: dict[str, dict] = {}
    for trade in trades:
        plan_id = trade.get("plan_id")
        if plan_id and plan_id not in by_plan:
            by_plan[plan_id] = trade
    return plans, by_plan


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="v173 manual overrides vs the engine")
    parser.add_argument("--production", action="store_true",
                        help="the real book on the VM: the only run that may write the ledger")
    parser.add_argument("--json", metavar="PATH", help="also write the payload (the API body)")
    return parser.parse_args(argv)


def _utc_day(now: datetime) -> date:
    aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).date()


def _evaluate_once(payload: dict, ledger_path: Path, today: date) -> dict | None:
    """The one evaluation (spec §4): only when the floors hold and nothing is
    recorded yet. Writes the ledger row and shows it as the verdict."""
    verdict = payload["verdict"]
    if verdict["recorded"] or not verdict["evaluable"]:
        return None
    entry = ov.ledger_row(ov.evaluate_verdict(payload["rows"]), today=today)
    stats.append_ledger_row(entry, ledger_path)
    payload["verdict"] = ov.verdict_payload(payload["rows"], stats.load_ledger(ledger_path))
    return entry


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
             f" / {summary['sum_delta_usd']:+.2f}{currency}"
             f"  (counted rows without dollars: {summary['usd_missing_n']})",
             f"helped / hurt / neutral: {summary['helped']} / {summary['hurt']} / "
             f"{summary['neutral']}  (counts ignore size)"]
    lines += [f"bulk clear {day}: {n} (not decisions, left out)"
              for day, n in summary["bulk_dates"].items()]
    if summary["approx_n"]:
        lines.append(f"approx (estimated exit): {summary['approx_n']} (shown, not counted)")
    lines += [f"{status}: {n}" for status, n in summary["n_by_status"].items() if n]
    return lines + _split_lines(summary["splits"], currency)


def _verdict_line(verdict: dict) -> str:
    line = (f"verdict {verdict['state']}: {verdict['n']} of {verdict['needed']} counted rows, "
            f"{verdict['weeks']} of {verdict['week_floor']} weeks, open {verdict['open_n']}, "
            f"excluded share {verdict['excluded_share']:.1%}, evaluable {verdict['evaluable']}")
    if verdict["recorded"]:
        line += (f"; recorded {verdict['recorded_on']}, mean delta "
                 f"{_num(verdict['mean_delta_r'], '+.3f')}R, 95% CI {verdict['ci']}")
    return line


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
         now: datetime | None = None, ledger_path: Path | None = None) -> dict:
    args = _parse(argv)
    if not args.production:
        print(DEV_BANNER)
    now = now or datetime.now(timezone.utc)
    path = Path(ledger_path) if ledger_path is not None else stats.LEDGER_PATH
    plans, trades = (inputs_fn or load_inputs)()
    payload = ov.build_report(plans, trades, bars_fn or rp.cached_daily_bars,
                              of.latest_completed_session(now), stats.load_ledger(path),
                              config.CURRENCY_SYMBOL)
    entry = _evaluate_once(payload, path, _utc_day(now)) if args.production else None
    print("\n".join(render(payload)))
    if entry is not None:
        print(_MIRROR)
        print(json.dumps(entry, ensure_ascii=False))
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
    return payload


if __name__ == "__main__":
    main()
```

`bars_fn or rp.cached_daily_bars` resolves the attribute at call time, so a patched `runner_path.cached_daily_bars` is honoured. `stats.LEDGER_PATH` is read inside `main`, never bound as a default, for the same reason (the precedent is `research.py:61-67`). `load_inputs` is the only function that touches the database; the tests replace it through `inputs_fn` or patch `report.PlanStore`/`report.TradeLog`.

- [ ] **Step 4: Run the test to verify it passes**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/scripts/test_execution_fidelity_report.py
```

Expected: PASS, `0 failed`, `0 xfailed`. The two evaluating tests run the real seeded bootstrap (10,000 resamples); a few seconds is normal. Never lower the resample count to speed it up.

If `test_the_first_evaluable_production_run_writes_one_ledger_row` reads `INCONCLUSIVE` rather than `COST`, the stub is not Part 3's COST spread (`-0.5 + 0.02 * w` over 10 weeks): fix the stub, not the expectation. If `test_the_real_pipeline...` reads a status other than `resolved`, compare with Part 3's `test_report_payload_shape` (the same `plan()` and `frame({19: STOP_BAR})`); never edit Part 3's helpers from here.

- [ ] **Step 5: Complexity and a help smoke run**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/reports/execution_fidelity_report.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/reports/execution_fidelity_report.py --help
```

Expected: `radon` prints nothing; `--help` lists `--production` and `--json`. Do not run the script without `--help` here: the dev database is not the book, and the V173-19 run on the VM is the real one.

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add scripts/reports/execution_fidelity_report.py tests/scripts/test_execution_fidelity_report.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): execution fidelity report script, one evaluation written once"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-12: `GET /api/v1/analytics/override-fidelity`

**Model:** sonnet — an admin endpoint over `build_report`

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (the `datetime` import at the top; a new seam and route after `analytics_partials`, around line 697)
- Create: `tests/admin/test_api_v1_analytics_override_fidelity.py` (`tests/admin/` is the `admin` suite)

**Interfaces:**
- Consumes:
  - V173-7: `override_fidelity.latest_completed_session(now) -> date`.
  - V173-10: `override_verdict.build_report(plans, trades_by_plan, bars_fn, asof, ledger_rows, currency_symbol) -> dict` (never evaluates), `ledger_row`, `SPEC_PATH`.
  - Existing: `analytics._all_trades(tl)` (`analytics.py:84`), `stats.LEDGER_PATH`/`stats.load_ledger` (read at call time, as `research.py:61-67` does), `runner_path.cached_daily_bars`, `config.CURRENCY_SYMBOL`, `require_auth`, `ApiError`.
  - Test helpers: Part 3's `plan`, `frame`, `STOP_BAR`, `LAST_DAY`; `tests.admin.api_v1_contract.assert_error`.
- Produces:
  - Route `analytics_override_fidelity()` at `GET /api/v1/analytics/override-fidelity`, behind `require_auth`. Body = the `build_report` payload, keys exactly `rows, summary, verdict, engine_flags, asof, currency_symbol` (V173-13's `OverrideFidelity` type reads it).
  - Seam `_override_inputs() -> tuple[list, dict[str, dict]]`: every plan from `PlanStore().all()`, and trades from `_all_trades(TradeLog())` keyed by `plan_id` (first wins, missing `plan_id` skipped). Tests monkeypatch it.
  - A malformed ledger is a `500` with code `ledger_invalid`, the research route's convention, never a payload with a silently missing verdict.

**Why it is computed on request.** About 36 rows, a replay each, read from the local bar cache: no store and no cron (spec §5). The route reads the frozen verdict from the ledger and **never evaluates** it; only the report script under `--production` does (V173-11). The override set is global, not scoped: the panel shows every manual close, so the route takes no scope parameters.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/admin/test_api_v1_analytics_override_fidelity.py`:

```python
"""v173 §5: GET /api/v1/analytics/override-fidelity -- computed on request,
the verdict read from the ledger and never evaluated."""
import json

import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.analytics import runner_path as rp
from swingbot.core.backtesting.instrument import stats
from tests.admin.api_v1_contract import assert_error
from tests.analytics.test_override_fidelity_replay import LAST_DAY, STOP_BAR, frame, plan
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

_LOGIN = {"username": "admin", "password": "admin"}
_URL = "/api/v1/analytics/override-fidelity"
PAYLOAD_KEYS = {"rows", "summary", "verdict", "engine_flags", "asof", "currency_symbol"}
ROW_KEYS = {"plan_id", "ticker", "horizon", "direction", "state_at_close", "close_date",
            "bulk", "approx", "price_source", "status", "actual_r", "engine_r", "delta_r",
            "actual_usd", "engine_usd", "delta_usd", "engine_exit_reason", "outcome",
            "source"}
VERDICT_KEYS = {"state", "n", "needed", "weeks", "week_floor", "open_n", "excluded_share",
                "evaluable", "recorded", "recorded_on", "mean_delta_r", "ci"}
SHARES = 10          # dollar risk = 10 x |100 - 95| = 50


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def book(admin_app, monkeypatch, tmp_path):
    """One stamped individual override (a), one bulk-clear close (b), no DB.
    The analytics module is imported here, after admin_app's reloads."""
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
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: frame({19: STOP_BAR}))
    monkeypatch.setattr(of, "latest_completed_session", lambda now: LAST_DAY)
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(stats, "LEDGER_PATH", ledger)

    def never(_rows):
        raise AssertionError("the API never evaluates the verdict")

    monkeypatch.setattr(ov, "evaluate_verdict", never)
    return ledger


def test_requires_auth(client):
    assert_error(client.get(_URL), "auth", 401)


def test_shape_and_the_bulk_exclusion(book, logged_in):
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == PAYLOAD_KEYS
    assert (body["asof"], body["currency_symbol"]) == ("2026-10-19", "$")
    assert body["engine_flags"] == {"stall_exit_enabled": False, "runner_structure_exit": "off"}
    assert [r["plan_id"] for r in body["rows"]] == ["b", "a"]        # newest close first
    assert all(set(r) == ROW_KEYS for r in body["rows"])
    by_id = {r["plan_id"]: r for r in body["rows"]}
    assert (by_id["b"]["bulk"], by_id["a"]["bulk"]) == (True, False)
    summary = body["summary"]
    assert (summary["bulk_n"], summary["bulk_dates"]) == (1, {"2026-10-08": 1})
    assert summary["counted_n"] == 1                                  # bulk shown, never summed
    assert sum(summary["n_by_status"].values()) == 1                  # eligible rows only
    assert set(body["verdict"]) == VERDICT_KEYS
    assert (body["verdict"]["state"], body["verdict"]["recorded"]) == ("WAITING", False)


def test_dollars_sit_beside_every_r_figure(book, logged_in):
    rows = {r["plan_id"]: r for r in logged_in.get(_URL).get_json()["rows"]}
    a = rows["a"]
    assert a["status"] == "resolved"
    for key in ("actual", "engine", "delta"):
        assert a[f"{key}_usd"] == pytest.approx(a[f"{key}_r"] * 50, abs=0.01)
    b = rows["b"]                                                     # no linked trade
    assert (b["actual_usd"], b["engine_usd"], b["delta_usd"]) == (None, None, None)


def test_the_verdict_is_read_from_the_ledger_never_evaluated(book, logged_in):
    stats.append_ledger_row({
        "id": "v173-override-fidelity", "date": "2027-03-01",
        "hypothesis": "Manual overrides vs the v2 engine left alone: mean delta R over "
                      "stamped individual resolved overrides, week-cluster bootstrap "
                      "95% CI [-0.400, -0.100]",
        "instrument": "v2", "n": 30, "exp_r": -0.25, "p": None, "verdict": "COST",
        "record": ov.SPEC_PATH}, book)
    verdict = logged_in.get(_URL).get_json()["verdict"]
    assert (verdict["state"], verdict["recorded"], verdict["recorded_on"]) == (
        "COST", True, "2027-03-01")
    assert (verdict["mean_delta_r"], verdict["ci"]) == (-0.25, [-0.4, -0.1])
    assert verdict["n"] == 1                                          # live counts stay live


def test_a_malformed_ledger_is_a_500(book, logged_in):
    book.write_text(json.dumps({"id": "x", "verdict": "MAYBE"}) + "\n", encoding="utf-8")
    assert_error(logged_in.get(_URL), "ledger_invalid", 500)


def test_override_inputs_keys_trades_by_plan(admin_app, monkeypatch):
    import swingbot.admin.api_v1.analytics as analytics_api

    class FakeStore:
        def all(self):
            return ["plan-a"]

    monkeypatch.setattr("swingbot.core.planning.plan_store.PlanStore", FakeStore)
    monkeypatch.setattr(analytics_api, "_all_trades", lambda tl: [
        {"id": "t1", "plan_id": "a"}, {"id": "t2"}, {"id": "t3", "plan_id": "a"}])
    monkeypatch.setattr(analytics_api, "TradeLog", lambda: object())
    plans, trades = analytics_api._override_inputs()
    assert plans == ["plan-a"]
    assert trades == {"a": {"id": "t1", "plan_id": "a"}}
```

`test_override_inputs_keys_trades_by_plan` patches `PlanStore` where the seam imports it (inside the function, `from swingbot.core.planning.plan_store import PlanStore`), and `TradeLog`/`_all_trades` on the module, so no store is touched.

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_override_fidelity.py
```

Expected: `test_requires_auth` fails with a 404 (the route does not exist); the `book` tests fail on `monkeypatch.setattr(analytics_api, "_override_inputs", ...)` with `AttributeError: ... has no attribute '_override_inputs'`.

- [ ] **Step 3: Add the seam and the route**

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
    """Every plan, and every paper trade keyed by its plan id (first wins).

    The override report needs the linked trade's record shares for the
    dollar figures (v170: dollars = R x shares x initial risk per share)."""
    from swingbot.core.planning.plan_store import PlanStore

    trades: dict[str, dict] = {}
    for trade in _all_trades(TradeLog()):
        plan_id = trade.get("plan_id")
        if plan_id and plan_id not in trades:
            trades[plan_id] = trade
    return PlanStore().all(), trades


@api_v1.route("/analytics/override-fidelity", methods=["GET"])
@require_auth
def analytics_override_fidelity():
    """Manual overrides vs the engine left alone (spec v173 §5).

    Computed on request: each manual close replayed from its fill through
    the v2 exit engine on the live scan's bar cache (never fetched). The
    verdict is the frozen ledger row, or WAITING; this route never
    evaluates it -- only the report script does, once, on the VM. Global,
    not scoped: every manual close is in the table."""
    from swingbot import config
    from swingbot.core.analytics import override_fidelity as of
    from swingbot.core.analytics import override_verdict as ov
    from swingbot.core.analytics import runner_path as rp
    from swingbot.core.backtesting.instrument import stats

    try:
        ledger_rows = stats.load_ledger(stats.LEDGER_PATH)
    except ValueError as exc:
        raise ApiError("ledger_invalid", str(exc), 500) from exc
    plans, trades = _override_inputs()
    asof = of.latest_completed_session(datetime.now(timezone.utc))
    return jsonify(ov.build_report(plans, trades, rp.cached_daily_bars, asof, ledger_rows,
                                   config.CURRENCY_SYMBOL))
```

Every name is looked up on its module at request time (`stats.LEDGER_PATH`, `rp.cached_daily_bars`, `of.latest_completed_session`, `ov.evaluate_verdict` inside `build_report`), which is what lets the test pin the ledger, the bars and the clock without a database.

- [ ] **Step 4: Run the test to verify it passes**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_override_fidelity.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_partials.py
```

Expected: both PASS, `0 failed`, `0 xfailed` (the second confirms the neighbouring route is untouched).

If `test_dollars_sit_beside_every_r_figure` fails on `abs=0.01`, check the rounding order: `to_usd` rounds `r * risk` where `r` is already rounded to 3 dp, so the difference is at most `0.0005 * 50 = 0.025`. Widen to `abs=0.03` only if the observed gap is exactly that rounding; any larger gap is a wrong dollar risk (it must be `10 x 5 = 50`).

- [ ] **Step 5: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/admin/api_v1/analytics.py
```

Expected: no line for `_override_inputs` or `analytics_override_fidelity` (both grade A). Any other line printed must already be in `complexity_baseline.json`.

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics_override_fidelity.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): GET /api/v1/analytics/override-fidelity, verdict read from the ledger"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-13: SPA: models, `ApiClient.analyticsOverrideFidelity`, store slice `overrideFidelity`

**Model:** sonnet — client and store following the partials slice

**Files:**
- Modify: `frontend/src/app/api/models.ts` (a new block directly before `export interface AnalyticsPlans {`, around line 717)
- Modify: `frontend/src/app/api/api-client.ts` (the `./models` import block, lines 7-72; a method after `analyticsPartials`, around line 275)
- Modify: `frontend/src/app/stores/analytics.store.ts` (models import :15-31, state interface :~379, `PanelKey` :203-206, initial state :~468, `loadExecution` :718-722, `resolveExecution` :856-860, `reload()` map :927-937)
- Create: `frontend/src/app/workspaces/analytics/tabs/override-fidelity.fixture.ts` (test data shared by this task's spec and V173-14's specs, after the `partials.fixture.ts` precedent; not listed in the index ledger, test-only)
- Create: `frontend/src/app/stores/analytics.override-fidelity.spec.ts`

**Interfaces:**
- Consumes: the V173-12 payload (Global Constraints **Report payload**, with Part 3's value shapes in this part's header).
- Produces (V173-14 imports these by name):
  - In `api/models.ts`: `OverrideStatus`, `OverrideVerdictState`, `OverrideOutcome`, `OverrideRowDto`, `OverrideSplit`, `OverrideSummary`, `OverrideVerdict`, `OverrideFidelity` (exact shapes in Step 3).
  - `ApiClient.analyticsOverrideFidelity(): Observable<OverrideFidelity>`: `GET /api/v1/analytics/override-fidelity`, no query parameters (global, never scoped).
  - `AnalyticsStore`: state `overrideFidelity: OverrideFidelity | null`, `overrideFidelityError: string | null` (signals of the same names); `PanelKey` gains `'overrideFidelity'`; the Execution tab's load and resolve fetch it; `reload('overrideFidelity')` refetches only it.
  - `OVERRIDE_FIDELITY_FIXTURE: OverrideFidelity` and `overrideFixture(patch?: { verdict?: Partial<OverrideVerdict>; summary?: Partial<OverrideSummary>; rows?: OverrideRowDto[] }): OverrideFidelity` in `override-fidelity.fixture.ts`.

**Why global.** The override set is every manual close in the book. The scope bar's date range, strategy and ledger filters would silently cut rows out of a verdict population that the spec defines over all of them, so the request carries no scope. It never feeds `scopeN` either (the scope bar's N counts closed trades in scope).

- [ ] **Step 1: Write the fixture and the failing store test**

Create `$WT/frontend/src/app/workspaces/analytics/tabs/override-fidelity.fixture.ts`:

```ts
import { OverrideFidelity, OverrideRowDto, OverrideSummary, OverrideVerdict } from '../../../api/models';

/* v173 — one payload per row kind: a stamped individual override (counted),
 * an estimated (approx) row, a bulk-clear row and a stale row. Figures are
 * illustrative, in the shape GET /api/v1/analytics/override-fidelity returns. */

const row = (patch: Partial<OverrideRowDto>): OverrideRowDto => ({
  plan_id: 'p', ticker: 'AAA', horizon: '2w', direction: 'bullish', state_at_close: 'ACTIVE',
  close_date: '2026-10-07', bulk: false, approx: false, price_source: 'quote', status: 'resolved',
  actual_r: 0.168, engine_r: -1.019, delta_r: 1.187, actual_usd: 8.4, engine_usd: -50.95,
  delta_usd: 59.35, engine_exit_reason: 'stop', outcome: 'helped', source: 'manual', ...patch,
});

export const OVERRIDE_FIDELITY_FIXTURE: OverrideFidelity = {
  rows: [
    row({ plan_id: 'a', ticker: 'AAA' }),
    row({ plan_id: 'b', ticker: 'BBB', close_date: '2026-10-06', approx: true,
      price_source: 'session_close', actual_r: -0.5, engine_r: -0.2, delta_r: -0.3,
      actual_usd: null, engine_usd: null, delta_usd: null, engine_exit_reason: 'runner_trail',
      outcome: 'hurt' }),
    row({ plan_id: 'c', ticker: 'CCC', close_date: '2026-09-30', bulk: true,
      actual_usd: null, engine_usd: null, delta_usd: null }),
    row({ plan_id: 'd', ticker: 'DDD', close_date: '2026-09-22', status: 'stale',
      state_at_close: 'PARTIAL', actual_r: null, engine_r: null, delta_r: null,
      actual_usd: null, engine_usd: null, delta_usd: null, engine_exit_reason: null,
      outcome: null }),
  ],
  summary: {
    n_by_status: { resolved: 1, open: 0, stale: 1, ambiguous: 0, parity_mismatch: 0,
      split_affected: 0, unreplayable: 0 },
    bulk_n: 1, bulk_dates: { '2026-09-30': 1 }, approx_n: 1, counted_n: 1,
    sum_delta_r: 1.187, sum_delta_usd: 59.35, usd_missing_n: 0, helped: 1, hurt: 0, neutral: 0,
    splits: {
      state_at_close: { ACTIVE: { n: 1, sum_delta_r: 1.187, sum_delta_usd: 59.35 } },
      horizon: { '2w': { n: 1, sum_delta_r: 1.187, sum_delta_usd: 59.35 } },
      direction: { bullish: { n: 1, sum_delta_r: 1.187, sum_delta_usd: 59.35 } },
    },
  },
  verdict: {
    state: 'WAITING', n: 1, needed: 30, weeks: 1, week_floor: 10, open_n: 0,
    excluded_share: 0.5, evaluable: false, recorded: false, recorded_on: null,
    mean_delta_r: null, ci: null,
  },
  engine_flags: { stall_exit_enabled: false, runner_structure_exit: 'off' },
  asof: '2026-10-19',
  currency_symbol: '$',
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
    expect(store.overrideFidelity()?.summary.counted_n).toBe(1);
    expect(store.overrideFidelity()?.verdict.state).toBe('WAITING');
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

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/stores/analytics.override-fidelity.spec.ts
```

Expected: FAIL at compile time: `Module '"../../../api/models"' has no exported member 'OverrideFidelity'` (and `store.overrideFidelity` is not a function).

- [ ] **Step 3: Add the types**

In `$WT/frontend/src/app/api/models.ts`, insert directly before `export interface AnalyticsPlans {`:

```ts
/* v173 — manual overrides vs the engine (GET /analytics/override-fidelity).
 * Every figure is computed server-side (`swingbot/core/analytics/
 * override_fidelity.py`, `override_verdict.py`); R and dollars are net of
 * modelled costs and pre-tax. Global, never scoped. */
export type OverrideStatus =
  | 'resolved' | 'open' | 'stale' | 'ambiguous' | 'parity_mismatch' | 'split_affected' | 'unreplayable';
export type OverrideVerdictState = 'WAITING' | 'COST' | 'SAVED' | 'INCONCLUSIVE';
export type OverrideOutcome = 'helped' | 'hurt' | 'neutral';
export interface OverrideRowDto {
  plan_id: string; ticker: string; horizon: string; direction: string;
  state_at_close: 'ACTIVE' | 'PARTIAL';
  /** ISO session date of the manual close, or null when it could not be assigned. */
  close_date: string | null;
  /** A bulk-clear close: shown, never counted. */
  bulk: boolean;
  /** No stamp: the exit price is the session's open or close, not the fill. Shown, never counted. */
  approx: boolean;
  price_source: string;
  status: OverrideStatus;
  actual_r: number | null; engine_r: number | null; delta_r: number | null;
  /** Null when the plan has no linked trade with shares: the row shows R only. */
  actual_usd: number | null; engine_usd: number | null; delta_usd: number | null;
  engine_exit_reason: string | null;
  outcome: OverrideOutcome | null;
  source: string;
}
export interface OverrideSplit { n: number; sum_delta_r: number; sum_delta_usd: number; }
export interface OverrideSummary {
  /** Eligible (individual, stamped) rows only; bulk and approx rows are counted apart. */
  n_by_status: Record<OverrideStatus, number>;
  bulk_n: number;
  /** ISO date -> closes in that bulk clear, sorted by date. */
  bulk_dates: Record<string, number>;
  approx_n: number;
  counted_n: number;
  sum_delta_r: number; sum_delta_usd: number; usd_missing_n: number;
  helped: number; hurt: number; neutral: number;
  splits: Record<'state_at_close' | 'horizon' | 'direction', Record<string, OverrideSplit>>;
}
export interface OverrideVerdict {
  /** WAITING until a verdict is recorded in the ledger, even when `evaluable` is true. */
  state: OverrideVerdictState;
  n: number; needed: number; weeks: number; week_floor: number; open_n: number;
  excluded_share: number; evaluable: boolean; recorded: boolean; recorded_on: string | null;
  mean_delta_r: number | null; ci: [number, number] | null;
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

- [ ] **Step 6: Run the new spec and the neighbouring store specs**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/stores/analytics.override-fidelity.spec.ts
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include "src/app/stores/analytics*.spec.ts"
```

Expected: both PASS with no failures. The second run covers the existing analytics store specs: any of them that does `backend.verify()` after `setTab('execution')` without flushing every request now sees one more request. Fix such a spec by flushing the override request too (`backend.match((r) => r.url === '/api/v1/analytics/override-fidelity').forEach((r) => r.flush({}))`); never drop the fetch from the store.

- [ ] **Step 7: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.override-fidelity.spec.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity.fixture.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(ui): override-fidelity types, client and store slice (v173)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Add any existing store spec fixed in Step 6 to the same commit. The last command checks the main tree stayed clean of branch edits.

### Task V173-14: Panel "Overrides vs engine" on the Execution tab

**Model:** sonnet — one panel component following the tab's pieces

**Files:**
- Create: `frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts`, `override-fidelity.model.spec.ts`
- Create: `frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts`, `override-fidelity-panel.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/tabs/execution.ts` (mount the panel), `execution.spec.ts` (store stub, mount test)

**Interfaces:**
- Consumes: V173-13's types (`OverrideFidelity`, `OverrideRowDto`, `OverrideStatus`, `OverrideSummary`, `OverrideVerdict`), store signals `overrideFidelity`/`overrideFidelityError`, `reload('overrideFidelity')`, and `OVERRIDE_FIDELITY_FIXTURE`/`overrideFixture`; existing `Panel` (`ui/layout`), `PanelHeader`, `PanelError`, `EmptyStateComponent`, `PaginationComponent` (`ui/pagination`), `createClientPage` (`ui/data-table/client-page`), `tablePerPage` (`ui/table-per-page`), `reasonLabel` (`workspaces/trades/exit-reasons`).
- Produces: `OverrideFidelityPanel` (selector `sb-override-fidelity-panel`); in `override-fidelity.model.ts`: `CAPTION`, `EMPTY_COPY`, `APPROX_LABEL`, `COUNTS_HINT`, `STATUS_LABEL: Record<OverrideStatus, string>`, `signedUsd(x: number | null, currency: string): string`, `signedR(x: number | null): string`, `netEffect(summary, currency): string`, `badgeCopy(verdict, summary, currency): string`, `badgeTone(verdict): 'pos' | 'neg' | 'neutral'`, `exclusionNotes(summary): string[]`, `isCounted(row): boolean`. V173-15 checks this panel at three widths.

**Layout per device class** (`ui-design.md`; media queries only at declared breakpoints):

- **Desktop (≥ 1024px):** four tiles in one row; the row table below, Δ cells right-aligned, tabular figures.
- **Tablet (640–1023px):** tiles two per row; the same table inside `.table-wrap` (`overflow-x: auto`), so a narrow viewport scrolls the table box, never the page.
- **Phone (< 640px):** tiles two per row, badge text wraps and never truncates; the table is hidden and each row is a card: the lead line is ticker, close date and Δ ($ and R), then secondary lines for engine exit and status, and the estimate label on approx rows.
- **Pager:** client-paged with `tablePerPage('override-fidelity')` (default 10 desktop, 5 tablet/phone, saved per device class); no pager at 5 rows or fewer. The pager's own controls are the panel's only touch targets besides the retry button, both at least 44px (`sb-pagination`/`sb-panel-error` already are). Cards are not interactive.
- Rows that are not counted (bulk, approx, or a status other than `resolved`) are dimmed, shown and never summed.

**Copy.** Every string in the index's **UI copy (verbatim)** is used as written. One addition, per Part 3: `verdict_payload` reports `WAITING` with `evaluable: true` when the floors hold but no ledger row exists yet. "34 of 30 needed" would contradict itself, so that case reads `Floors met (34 of 30). Awaiting the one recorded evaluation.` It names no action and sets no target.

- [ ] **Step 1: Write the failing model test**

Create `$WT/frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import {
  APPROX_LABEL, CAPTION, EMPTY_COPY, badgeCopy, badgeTone, exclusionNotes, isCounted, netEffect,
  signedR, signedUsd,
} from './override-fidelity.model';
import { OVERRIDE_FIDELITY_FIXTURE, overrideFixture } from './override-fidelity.fixture';

const F = OVERRIDE_FIDELITY_FIXTURE;

describe('override-fidelity model', () => {
  it('signs dollars and R with a true minus, and prints a dash for none', () => {
    expect(signedUsd(59.35, '$')).toBe('+$59.35');
    expect(signedUsd(-1234.5, '€')).toBe('−€1,234.50');
    expect(signedUsd(0, '$')).toBe('$0.00');
    expect(signedUsd(null, '$')).toBe('—');
    expect(signedR(1.187)).toBe('+1.19 R');
    expect(signedR(-0.3)).toBe('−0.30 R');
    expect(signedR(null)).toBe('—');
  });

  it('leads the net effect with dollars, then R', () => {
    expect(netEffect(F.summary, '$')).toBe('+$59.35 · +1.19 R');
  });

  it('words each badge state as the spec does, never as a policy', () => {
    const cost = { sum_delta_usd: -120.5, sum_delta_r: -2.4 };
    expect(badgeCopy(F.verdict, F.summary, '$')).toBe('1 of 30 needed. No conclusion yet.');
    expect(badgeCopy({ ...F.verdict, state: 'COST' }, { ...F.summary, ...cost }, '$'))
      .toBe('Your overrides cost $120.50 (2.40 R) vs the engine');
    expect(badgeCopy({ ...F.verdict, state: 'SAVED' }, F.summary, '$'))
      .toBe('Your overrides saved $59.35 (1.19 R) vs the engine');
    expect(badgeCopy({ ...F.verdict, state: 'INCONCLUSIVE' }, F.summary, '$'))
      .toBe('No clear difference vs the engine');
  });

  it('never reads "34 of 30 needed" once the floors hold but nothing is recorded', () => {
    const ready = overrideFixture({ verdict: { n: 34, evaluable: true } }).verdict;
    expect(badgeCopy(ready, F.summary, '$'))
      .toBe('Floors met (34 of 30). Awaiting the one recorded evaluation.');
  });

  it('tones only a recorded direction', () => {
    expect(badgeTone(F.verdict)).toBe('neutral');
    expect(badgeTone({ ...F.verdict, state: 'COST' })).toBe('neg');
    expect(badgeTone({ ...F.verdict, state: 'SAVED' })).toBe('pos');
    expect(badgeTone({ ...F.verdict, state: 'INCONCLUSIVE' })).toBe('neutral');
  });

  it('writes one exclusion note per non-zero count', () => {
    expect(exclusionNotes(F.summary)).toEqual([
      '1 closes from one bulk clear on 2026-09-30 are not decisions, so they are left out',
      '1 estimated rows are shown but not counted',
      '1 stale data rows are left out',
    ]);
    const quiet = { ...F.summary, bulk_dates: {}, approx_n: 0,
      n_by_status: { ...F.summary.n_by_status, stale: 0 } };
    expect(exclusionNotes(quiet)).toEqual([]);
  });

  it('counts only individual, stamped, resolved rows', () => {
    expect(F.rows.map(isCounted)).toEqual([true, false, false, false]);
  });

  it('keeps the fixed copy verbatim', () => {
    expect(CAPTION).toBe('Compares the overrides you made with what the engine would have done. '
      + 'Past closes only, not advice on future ones. A close for a reason the engine cannot see '
      + '(a gap, earnings, needing the cash) can still be right. Figures are after modelled costs '
      + 'and before tax. Closing early can also change the tax holding period. There is no target '
      + 'number of overrides.');
    expect(EMPTY_COPY).toBe('No manual overrides in scope.');
    expect(APPROX_LABEL).toBe('estimated exit: daily close, not your fill');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts
```

Expected: FAIL, cannot resolve `./override-fidelity.model`.

- [ ] **Step 3: Write the model**

Create `$WT/frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts`:

```ts
import { OverrideRowDto, OverrideStatus, OverrideSummary, OverrideVerdict } from '../../../api/models';

/* v173 — copy and formatting for "Overrides vs engine". Every figure is
 * computed server-side; these helpers only word it. The copy is frozen by
 * the spec (§5): scoped to overrides already made, never a policy. */

export const CAPTION = 'Compares the overrides you made with what the engine would have done. '
  + 'Past closes only, not advice on future ones. A close for a reason the engine cannot see '
  + '(a gap, earnings, needing the cash) can still be right. Figures are after modelled costs '
  + 'and before tax. Closing early can also change the tax holding period. There is no target '
  + 'number of overrides.';
export const EMPTY_COPY = 'No manual overrides in scope.';
export const APPROX_LABEL = 'estimated exit: daily close, not your fill';
export const COUNTS_HINT = 'counts ignore size';

/** Lower-case: each label also sits inside an exclusion sentence. */
export const STATUS_LABEL: Record<OverrideStatus, string> = {
  resolved: 'resolved', open: 'still open', stale: 'stale data', ambiguous: 'ambiguous',
  parity_mismatch: 'replay mismatch', split_affected: 'split-affected', unreplayable: 'unreplayable',
};

/** U+2212, not a hyphen: negatives line up with positives in tabular figures. */
const MINUS = '\u2212';
const sign = (x: number): string => (x > 0 ? '+' : x < 0 ? MINUS : '');
const known = (x: number | null): x is number => x !== null && Number.isFinite(x);
const magnitude = (x: number, currency: string): string =>
  `${currency}${Math.abs(x).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function signedUsd(x: number | null, currency: string): string {
  return known(x) ? `${sign(x)}${magnitude(x, currency)}` : '—';
}

export function signedR(x: number | null): string {
  return known(x) ? `${sign(x)}${Math.abs(x).toFixed(2)} R` : '—';
}

/** Expectancy before counts: the net ΣΔ leads the tiles, dollars first. */
export function netEffect(summary: OverrideSummary, currency: string): string {
  return `${signedUsd(summary.sum_delta_usd, currency)} · ${signedR(summary.sum_delta_r)}`;
}

export function badgeCopy(verdict: OverrideVerdict, summary: OverrideSummary, currency: string): string {
  const x = magnitude(summary.sum_delta_usd, currency);
  const y = `${Math.abs(summary.sum_delta_r).toFixed(2)} R`;
  if (verdict.state === 'COST') return `Your overrides cost ${x} (${y}) vs the engine`;
  if (verdict.state === 'SAVED') return `Your overrides saved ${x} (${y}) vs the engine`;
  if (verdict.state === 'INCONCLUSIVE') return 'No clear difference vs the engine';
  return verdict.evaluable
    ? `Floors met (${verdict.n} of ${verdict.needed}). Awaiting the one recorded evaluation.`
    : `${verdict.n} of ${verdict.needed} needed. No conclusion yet.`;
}

export function badgeTone(verdict: OverrideVerdict): 'pos' | 'neg' | 'neutral' {
  if (verdict.state === 'COST') return 'neg';
  if (verdict.state === 'SAVED') return 'pos';
  return 'neutral';
}

/** One line per non-zero count. `n_by_status` counts eligible rows only, so
 *  no row appears in two notes. */
export function exclusionNotes(summary: OverrideSummary): string[] {
  const bulk = Object.entries(summary.bulk_dates).map(
    ([day, n]) => `${n} closes from one bulk clear on ${day} are not decisions, so they are left out`);
  const approx = summary.approx_n ? [`${summary.approx_n} estimated rows are shown but not counted`] : [];
  const statuses = (Object.keys(STATUS_LABEL) as OverrideStatus[])
    .filter((s) => s !== 'resolved' && summary.n_by_status[s] > 0)
    .map((s) => `${summary.n_by_status[s]} ${STATUS_LABEL[s]} rows are left out`);
  return [...bulk, ...approx, ...statuses];
}

export function isCounted(row: OverrideRowDto): boolean {
  return !row.bulk && !row.approx && row.status === 'resolved';
}
```

- [ ] **Step 4: Run the model test to verify it passes**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Write the failing panel test**

Create `$WT/frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { OverrideFidelity } from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { OverrideFidelityPanel } from './override-fidelity-panel';
import { APPROX_LABEL, CAPTION } from './override-fidelity.model';
import { OVERRIDE_FIDELITY_FIXTURE, overrideFixture } from './override-fidelity.fixture';

function render(payload: OverrideFidelity | null, error: string | null = null) {
  const reloads: string[] = [];
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: AnalyticsStore, useValue: { overrideFidelity: signal(payload),
        overrideFidelityError: signal(error), reload: (k: string) => reloads.push(k) } },
      { provide: PreferencesStore, useValue: { values: () => ({}), update: () => {} } },
    ],
  });
  const fixture = TestBed.createComponent(OverrideFidelityPanel);
  fixture.detectChanges();
  return { el: fixture.nativeElement as HTMLElement, reloads };
}

const text = (el: Element | null): string => (el?.textContent ?? '').replace(/\s+/g, ' ').trim();

describe('OverrideFidelityPanel', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('leads with net dollars and R, then counted, helped/hurt/neutral, the badge', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    const tiles = [...el.querySelectorAll('.tiles > div')].map((t) => text(t.querySelector('dt')));
    expect(tiles).toEqual(['Net effect vs engine', 'Overrides counted', 'Helped / hurt / neutral', 'Verdict']);
    expect(text(el.querySelector('.tiles > div dd'))).toBe('+$59.35 · +1.19 R');
    expect(text(el.querySelector('.tiles'))).toContain('counts ignore size');
    expect(text(el.querySelector('.badge-text'))).toBe('1 of 30 needed. No conclusion yet.');
    expect(text(el.querySelector('h2'))).toBe('Overrides vs engine');
  });

  it('shows a recorded COST verdict in its scoped words', () => {
    const { el } = render(overrideFixture({ verdict: { state: 'COST', recorded: true },
      summary: { sum_delta_usd: -120.5, sum_delta_r: -2.4 } }));
    expect(text(el.querySelector('.badge-text'))).toBe('Your overrides cost $120.50 (2.40 R) vs the engine');
    expect(el.querySelector('.badge')?.getAttribute('data-tone')).toBe('neg');
  });

  it('prints the fixed caption and one note per exclusion', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    expect(text(el.querySelector('.caption'))).toBe(CAPTION);
    expect([...el.querySelectorAll('.note')].map(text)).toEqual([
      '1 closes from one bulk clear on 2026-09-30 are not decisions, so they are left out',
      '1 estimated rows are shown but not counted',
      '1 stale data rows are left out',
    ]);
  });

  it('labels the estimated row beside its delta, in the table and the card', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    const rows = el.querySelectorAll('table.rows tbody tr');
    expect(rows.length).toBe(4);
    expect(text(rows[1].querySelector('td.delta'))).toContain(APPROX_LABEL);
    expect(text(rows[0].querySelector('td.delta'))).not.toContain(APPROX_LABEL);
    expect(rows[1].classList.contains('excluded')).toBe(true);
    expect([...el.querySelectorAll('table.rows th')].map(text)).toEqual(
      ['Close date', 'Ticker', 'Horizon', 'State at close', 'Actual', 'Engine', 'Δ', 'Engine exit', 'Status']);
  });

  it('builds one card per row, leading with ticker, close date and delta in $ and R', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    const cards = el.querySelectorAll('ul.cards > li');
    expect(cards.length).toBe(4);
    const lead = text(cards[0].querySelector('.lead'));
    expect(lead.indexOf('AAA')).toBeLessThan(lead.indexOf('2026-10-07'));
    expect(lead).toContain('+$59.35 · +1.19 R');
    expect([...cards[1].querySelectorAll('.sub')].map(text)).toContain(APPROX_LABEL);
    expect(text(cards[2])).toContain('bulk clear');
  });

  it('shows no pager for five rows or fewer', () => {
    expect(render(OVERRIDE_FIDELITY_FIXTURE).el.querySelector('sb-pagination')).toBeNull();
  });

  it('says so plainly when there are no overrides', () => {
    const { el } = render(overrideFixture({ rows: [] }));
    expect(text(el)).toContain('No manual overrides in scope.');
    expect(el.querySelector('.tiles')).toBeNull();
  });

  it('keeps its own error and retries only itself', () => {
    const { el, reloads } = render(null, 'boom');
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
    (el.querySelector('sb-panel-error button') as HTMLButtonElement | null)?.click();
    expect(reloads).toEqual(['overrideFidelity']);
  });
});

describe('override-fidelity-panel.ts breakpoints', () => {
  it('uses only declared breakpoint values in width queries', () => {
    const src = readFileSync(
      join(process.cwd(), 'src/app/workspaces/analytics/tabs/override-fidelity-panel.ts'), 'utf8');
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
```

If `sb-panel-error`'s retry button has a different selector, read `ui/panel-error.ts` and use its button; keep the assertion that only `'overrideFidelity'` is reloaded.

- [ ] **Step 6: Write the panel**

Create `$WT/frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { OverrideRowDto } from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { createClientPage } from '../../../ui/data-table/client-page';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { Panel } from '../../../ui/layout';
import { PaginationComponent } from '../../../ui/pagination';
import { PanelError } from '../../../ui/panel-error';
import { PanelHeader } from '../../../ui/panel-header';
import { tablePerPage } from '../../../ui/table-per-page';
import { reasonLabel } from '../../trades/exit-reasons';
import {
  APPROX_LABEL, CAPTION, COUNTS_HINT, EMPTY_COPY, STATUS_LABEL, badgeCopy, badgeTone, exclusionNotes,
  isCounted, netEffect, signedR, signedUsd,
} from './override-fidelity.model';

/* v173 — manual overrides vs the engine left alone. Descriptive until the
 * frozen verdict is recorded; the badge shows that recorded verdict or WAITING. */
@Component({
  selector: 'sb-override-fidelity-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, PanelError, EmptyStateComponent, PaginationComponent],
  template: `
    <sb-panel><sb-panel-header title="Overrides vs engine" [n]="data()?.summary?.counted_n ?? null"
      hint="Each manual close replayed through the engine from its real fill. Δ is your exit minus the engine's, in dollars and R." />
      @if (store.overrideFidelityError(); as error) {
        <sb-panel-error [message]="error" (retry)="store.reload('overrideFidelity')" />
      } @else if (data(); as d) {
        @if (!d.rows.length) { <sb-empty-state [title]="emptyCopy" reason="measured-zero" /> }
        @else {
          <dl class="tiles">
            <div><dt>Net effect vs engine</dt><dd>{{ net() }}</dd></div>
            <div><dt>Overrides counted</dt><dd>{{ d.summary.counted_n }}</dd></div>
            <div><dt>Helped / hurt / neutral</dt><dd>{{ d.summary.helped }} / {{ d.summary.hurt }} / {{ d.summary.neutral }}</dd><small>{{ countsHint }}</small></div>
            <div class="badge" [attr.data-tone]="tone()"><dt>Verdict</dt><dd class="badge-text">{{ badge() }}</dd></div>
          </dl>
          <p class="caption">{{ caption }}</p>
          @for (note of notes(); track note) { <p class="note">{{ note }}</p> }
          <div class="table-wrap"><table class="rows">
            <thead><tr><th>Close date</th><th>Ticker</th><th>Horizon</th><th>State at close</th><th class="num">Actual</th><th class="num">Engine</th><th class="num">Δ</th><th>Engine exit</th><th>Status</th></tr></thead>
            <tbody>@for (r of page.visible(); track r.plan_id) {
              <tr [class.excluded]="!counted(r)">
                <td>{{ r.close_date ?? '—' }}</td><td>{{ r.ticker }}</td><td>{{ r.horizon }}</td><td>{{ r.state_at_close }}</td>
                <td class="num">{{ pair(r.actual_usd, r.actual_r) }}</td><td class="num">{{ pair(r.engine_usd, r.engine_r) }}</td>
                <td class="num delta">{{ pair(r.delta_usd, r.delta_r) }}@if (r.approx) { <small class="approx">{{ approxLabel }}</small> }</td>
                <td>{{ exit(r) }}</td><td>{{ status(r) }}</td>
              </tr>
            }</tbody>
          </table></div>
          <ul class="cards">@for (r of page.visible(); track r.plan_id) {
            <li class="card" [class.excluded]="!counted(r)">
              <div class="lead"><strong>{{ r.ticker }}</strong><span>{{ r.close_date ?? '—' }}</span><span class="num">{{ pair(r.delta_usd, r.delta_r) }}</span></div>
              <div class="sub">Engine exit: {{ exit(r) }}</div><div class="sub">Status: {{ status(r) }}</div>
              @if (r.approx) { <div class="sub approx">{{ approxLabel }}</div> }
            </li>
          }</ul>
          @if (d.rows.length > 5) {
            <sb-pagination [pagination]="page.pageSpec()" [showPerPage]="true" [announce]="true"
              (pageChange)="page.setPage($event)" (perPageChange)="perPage.set($event)" />
          }
        }
      }
    </sb-panel>
  `,
  styles: `.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--space-10);margin:0}.tiles div{min-width:0;padding:var(--space-10);border:1px solid var(--border);border-radius:var(--panel-radius)}dt{font-size:var(--text-micro);text-transform:uppercase;letter-spacing:.1em;color:var(--text-faint)}dd{margin:var(--space-4) 0;color:var(--text);font-variant-numeric:tabular-nums}small{font-size:var(--text-micro);color:var(--text-faint)}.badge-text{white-space:normal;overflow-wrap:anywhere}.badge[data-tone=neg] .badge-text{color:var(--neg)}.badge[data-tone=pos] .badge-text{color:var(--pos)}.caption,.note{margin:var(--space-8) 0 0;font-size:var(--text-micro);color:var(--text-faint)}.table-wrap{overflow-x:auto;margin-top:var(--space-10)}.rows{width:100%;border-collapse:collapse;font-size:var(--text-table)}.rows th,.rows td{padding:var(--space-4) var(--space-8);text-align:left;border-bottom:1px solid var(--border)}.rows .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.excluded,.excluded td{color:var(--text-faint)}.approx{display:block;color:var(--warn);white-space:normal}.cards{display:none;list-style:none;margin:var(--space-10) 0 0;padding:0;gap:var(--space-8)}.cards li{padding:var(--space-10);border:1px solid var(--border);border-radius:var(--panel-radius)}.lead{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--space-6) var(--space-10)}.lead .num{margin-left:auto;font-variant-numeric:tabular-nums}.sub{font-size:var(--text-micro);color:var(--text-secondary)}@media(max-width:1023px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:639px){.table-wrap{display:none}.cards{display:grid}}`,
})
export class OverrideFidelityPanel {
  readonly store = inject(AnalyticsStore);
  readonly data = computed(() => this.store.overrideFidelity());
  readonly perPage = tablePerPage('override-fidelity');
  readonly page = createClientPage<OverrideRowDto>(() => this.data()?.rows ?? [], () => this.perPage.value());
  readonly caption = CAPTION;
  readonly emptyCopy = EMPTY_COPY;
  readonly approxLabel = APPROX_LABEL;
  readonly countsHint = COUNTS_HINT;
  readonly counted = isCounted;

  private readonly currency = computed(() => this.data()?.currency_symbol ?? '');
  readonly net = computed(() => { const d = this.data(); return d ? netEffect(d.summary, this.currency()) : ''; });
  readonly badge = computed(() => { const d = this.data(); return d ? badgeCopy(d.verdict, d.summary, this.currency()) : ''; });
  readonly tone = computed(() => { const d = this.data(); return d ? badgeTone(d.verdict) : 'neutral'; });
  readonly notes = computed(() => { const d = this.data(); return d ? exclusionNotes(d.summary) : []; });

  /** Every R figure carries its signed dollars beside it (the v170 convention). */
  pair(usd: number | null, r: number | null): string {
    return `${signedUsd(usd, this.currency())} · ${signedR(r)}`;
  }

  exit(r: OverrideRowDto): string {
    return reasonLabel(r.engine_exit_reason) ?? '—';
  }

  status(r: OverrideRowDto): string {
    return r.bulk ? `${STATUS_LABEL[r.status]} · bulk clear` : STATUS_LABEL[r.status];
  }
}
```

If `PaginationComponent`'s inputs differ from the ones `tuning.ts:214` uses (`pagination`, `showPerPage`, `announce`, `pageChange`, `perPageChange`), follow `tuning.ts`.

- [ ] **Step 7: Mount it on the Execution tab**

In `$WT/frontend/src/app/workspaces/analytics/tabs/execution.ts`: add `import { OverrideFidelityPanel } from './override-fidelity-panel';`, add `OverrideFidelityPanel` to the component's `imports: [...]`, and insert `<sb-override-fidelity-panel />` on its own line between the closing `</sb-panel>` of "Execution verdict" and `<div class="panels">`. It sits full width, after the verdict tiles and before the charts: it is a second verdict, on the human's exits.

In `$WT/frontend/src/app/workspaces/analytics/tabs/execution.spec.ts`:

1. Add `import { OVERRIDE_FIDELITY_FIXTURE } from './override-fidelity.fixture';`.
2. In `render()`'s `AnalyticsStore` stub add `overrideFidelity: signal(OVERRIDE_FIDELITY_FIXTURE), overrideFidelityError: signal(null),`, and give the `PreferencesStore` stub `update: () => {}` beside `values`.
3. Add inside `describe('ExecutionTab', ...)`:

```ts
  it('mounts Overrides vs engine full width after the verdict, before the charts', () => { const { el } = render(); const panel = el.querySelector('sb-override-fidelity-panel')!; expect(panel).not.toBeNull(); expect(panel.parentElement?.classList.contains('panels')).toBe(false); expect(el.querySelector('.verdict')!.compareDocumentPosition(panel)).toBe(Node.DOCUMENT_POSITION_FOLLOWING); expect(panel.compareDocumentPosition(el.querySelector('sb-histogram')!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING); });
```

(One line, matching the file's dense style.)

- [ ] **Step 8: Run the three specs**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/execution.spec.ts
```

Expected: all PASS. Never loosen a copy assertion to make one pass: the strings are frozen by the spec, so a mismatch is a template bug.

- [ ] **Step 9: Type-check the app build**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng build --configuration development
```

Expected: the build succeeds with no new errors or warnings in the four files. The real three-width check runs in V173-15.

- [ ] **Step 10: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts frontend/src/app/workspaces/analytics/tabs/execution.ts frontend/src/app/workspaces/analytics/tabs/execution.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(ui): Overrides vs engine panel on the Execution tab (v173)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.
