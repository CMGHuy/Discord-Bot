# v229 — Deferred-entry counterfactual: Part 2b — the CLI (V229-10, V229-10b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V229-10b" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-14-v229-deferred-entry-counterfactual-design.md](../../specs/implemented/2026-11-14-v229-deferred-entry-counterfactual-design.md)
**Index:** [2026-11-15-v229-deferred-entry-counterfactual_0-index.md](2026-11-15-v229-deferred-entry-counterfactual_0-index.md) — Goal, `## Global Constraints`, `## Parallelisation`, the task ledger, the shared PAIR shape and the `## Handoff` resolutions bind every task below.

Part 2 of the ledger, second file: part 2 split at the 1500-line cap, never compressed. V229-6..V229-9 (pair log, statistics, frozen rule, report) are in `2026-11-15-v229-deferred-entry-counterfactual_2-analysis.md`; the common test import pattern described in part 1 applies here too (put `scripts/reports` on `sys.path`, import `deferred_entry.<module>`).

# Phase 2 (continued) — the CLI

### Task V229-10: The CLI: export, funnel and append mode

**Model:** sonnet — wiring of modules whose contracts are fixed; the refusals it surfaces are decided in V229-3 and V229-8.

Split from the ledger's V229-10 (past 20 KB): this task creates the CLI with the shared front half (frictions, export, classification, append) and the `append` mode; **V229-10b** adds the `exploratory` and `verdict` modes.

**Files:**
- Create: `scripts/reports/deferred_entry_counterfactual.py`
- Create: `tests/scripts/test_deferred_entry_counterfactual.py`

**Interfaces:**
- Consumes: V229-1 `bars.load_bars`, `to_utc`, `et_date`, `archive_last_bar`, `DEFER_AT`, `horizon_end`; V229-3 `arms.assert_frictions`, `FrictionsError`, `DEFERRED_BPS_MULT`; V229-5 `pairs.read_export`, `pairs.classify(row, bars, *, archive_end)` (passed a `pd.Timestamp | None`), `pairs.build_pair(row, bars, *, rule_hash, earnings_lookup=None)`; V229-6 `pairlog.read_pairs`, `append_pair(..., known=)`, `DEFAULT_LOG`; V229-7 `analysis.LOWER_PCT`, `CALIBRATION_MIN`; V229-8 `verdict.rule_hash`, `phase`, `FROZEN`, `VerdictRefused`; `stats.LEDGER_PATH`.
- Produces (index ledger): `main(argv=None) -> int`; flags `--mode {append,exploratory,verdict}` (choices `("append", *MODES)`; V229-10b fills `MODES`), `--rows`, `--bars-dir` (default `market_data/5min`), `--pairs-log` (default `data/v229/pairs.jsonl`), `--t0` (required, ISO UTC), `--out-dir` (default `data/v229`), `--ledger` (default `stats.LEDGER_PATH`), `--today` (default UTC today), plus additive `--git-sha` (default env `V229_GIT_SHA`, else `git rev-parse HEAD` beside the script, else `unknown`; Handoff 12). `append` prints `v229 pairs: appended <a>, total <t>, forward <f>`. Exit 0 on success, 2 on any refusal (stderr, prefixed `v229 refused:`).
- Produces for V229-10b: `MODES: dict[str, Callable[[args, scanned, logged, run], int]]` (empty here); `EARNINGS_LOOKUP` (module constant, `None` = the production lookup inside `build_pair`; tests replace it so no test touches the earnings cache or the network); `build_pair_for(row, frame) -> dict`; `row_phase(row, t0) -> str | None`; `select(pairs, t0, phase) -> list[dict]`; `resolve_git_sha(given) -> str`; the `run` dict `{"t0": pd.Timestamp, "archive_last_bar": str | None, "git_sha": str, "today": dt.date}`; `scanned` = `list[(row, frame, reason)]`; `logged` = `pairlog.read_pairs` result after the append.

Flow, every mode: refuse zero frictions; read the export by name; classify each row against its ticker's bars (loaded once per ticker; `archive_end` = the archive's last bar); append every eligible **bullish** plan not yet logged (the log is the checkpoint: a restart rebuilds nothing already logged, and a killed run redoes only its torn last line). `append` then prints the count line; an empty export prints zeros and exits 0 (spec § Edge cases).

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_deferred_entry_counterfactual.py`:

```python
"""v229 CLI: append / exploratory / verdict wiring, refusals, and the frozen constants."""
import datetime as dt
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import deferred_entry_counterfactual as cli  # noqa: E402
from deferred_entry import analysis, arms, bars, pairlog, verdict  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.market.strategy_types import BREAKEVEN_TRIGGER_FRACTION  # noqa: E402
from tests.scripts.v229_fixtures import five_min, write_bars  # noqa: E402

T0 = "2026-11-19T15:00:00+00:00"


def _leg(arm, r, outcome="loss"):
    return {"arm": arm, "taken": True, "fill": 100.0, "stop": 98.0, "tp1": 104.0, "outcome": outcome,
            "r_net": r, "r_gross": r, "exit_ts": None, "gap_stop": False}


def _pair(tid, day, direction="bullish"):
    return {"trade_id": tid, "ticker": "AAPL", "direction": direction, "entry_date": day, "bucket": "open",
            "arms": {"C": _leg("C", -1.0), "A": _leg("A", 1.0, "win"), "B": _leg("B", 1.0, "win")},
            "live": {"reason": "loss", "outcome": "loss", "r_realized": -1.0},
            "tradeability": {"fill_above_entry": True, "event_day": False}, "rule_hash": verdict.rule_hash()}


def _row(tid, day, reason, direction="bullish", r="-1.0"):
    return {"row_kind": "trade", "trade_id": tid, "ticker": "AAPL", "direction": direction,
            "opened_at": f"{day} 15:00:00+00", "r_realized": r, "reason": reason}


@pytest.fixture
def fake_book(monkeypatch):
    """Rows carry their funnel reason; build_pair returns a hand-built pair."""
    book = SimpleNamespace(rows=[], built=[])
    monkeypatch.setattr(cli.pairs_mod, "read_export", lambda path: list(book.rows))
    monkeypatch.setattr(cli.pairs_mod, "classify", lambda row, frame, *, archive_end: row["reason"])

    def build(row, frame, *, rule_hash, earnings_lookup=None):
        book.built.append(row["trade_id"])
        return _pair(row["trade_id"], row["opened_at"][:10], row["direction"])

    monkeypatch.setattr(cli.pairs_mod, "build_pair", build)
    return book


def _run(tmp_path, mode, *extra):
    return cli.main(["--mode", mode, "--rows", str(tmp_path / "rows.csv"), "--bars-dir", str(tmp_path / "5min"),
                     "--pairs-log", str(tmp_path / "pairs.jsonl"), "--out-dir", str(tmp_path / "out"),
                     "--ledger", str(tmp_path / "ledger.jsonl"), "--t0", T0, "--git-sha", "abc1234", *extra])


def test_defaults_match_the_ledger_contract():
    args = cli.build_parser().parse_args(["--mode", "append", "--rows", "r.csv", "--t0", T0])
    assert (args.bars_dir, args.pairs_log, args.out_dir) == ("market_data/5min", pairlog.DEFAULT_LOG, "data/v229")
    assert Path(args.ledger) == Path(stats.LEDGER_PATH) and args.today is None


def test_the_frozen_rule_matches_the_constants_the_code_runs_on():
    f = verdict.FROZEN
    assert analysis.LOWER_PCT == f["lower_pct"] and analysis.CALIBRATION_MIN == f["calibration_min"]
    assert stats.WEEK_BOOTSTRAP_SEED == f["seed"] and stats.WEEK_BOOTSTRAP_RESAMPLES == f["resamples"]
    assert BREAKEVEN_TRIGGER_FRACTION == f["be_fraction"] and arms.DEFERRED_BPS_MULT == f["deferred_entry_bps_mult"]
    assert bars.DEFER_AT.strftime("%H:%M") == f["defer_et"]
    assert inspect.signature(bars.horizon_end).parameters["sessions"].default == f["hold_sessions"]


def test_append_logs_new_eligible_longs_once_and_prints_one_line(tmp_path, fake_book, capsys):
    fake_book.rows = [_row("t-1", "2026-11-02", "eligible"), _row("t-2", "2026-11-24", "eligible"),
                      _row("t-3", "2026-11-24", "eligible", direction="bearish"),
                      _row("t-4", "2026-11-24", "no_coverage"), _row("t-5", "2026-11-25", "pending")]
    assert _run(tmp_path, "append") == 0
    assert capsys.readouterr().out.strip() == "v229 pairs: appended 2, total 2, forward 1"
    assert list(pairlog.read_pairs(tmp_path / "pairs.jsonl")) == ["t-1", "t-2"]
    assert _run(tmp_path, "append") == 0                                   # restart: nothing rebuilt
    assert capsys.readouterr().out.strip() == "v229 pairs: appended 0, total 2, forward 1"
    assert fake_book.built == ["t-1", "t-2"]


def test_an_empty_export_prints_zero_and_exits_zero(tmp_path, fake_book, capsys):
    assert _run(tmp_path, "append") == 0
    assert capsys.readouterr().out.strip() == "v229 pairs: appended 0, total 0, forward 0"


def test_zero_frictions_are_refused_before_anything_is_logged(tmp_path, fake_book, monkeypatch, capsys):
    def refuse():
        raise arms.FrictionsError("SLIPPAGE_BPS is 0")

    monkeypatch.setattr(cli.arms, "assert_frictions", refuse)
    fake_book.rows = [_row("t-1", "2026-11-02", "eligible")]
    assert _run(tmp_path, "append") == 2
    assert "v229 refused" in capsys.readouterr().err and not (tmp_path / "pairs.jsonl").exists()


def test_a_malformed_pair_log_is_refused_not_overwritten(tmp_path, fake_book, capsys):
    (tmp_path / "pairs.jsonl").write_text("not json\n{}\n", encoding="utf-8")
    fake_book.rows = [_row("t-1", "2026-11-02", "eligible")]
    assert _run(tmp_path, "append") == 2
    assert "line 1" in capsys.readouterr().err
    assert (tmp_path / "pairs.jsonl").read_text(encoding="utf-8") == "not json\n{}\n"


def test_git_sha_prefers_the_flag_then_the_environment(monkeypatch):
    monkeypatch.setenv("V229_GIT_SHA", "fromenv")
    assert cli.resolve_git_sha(None) == "fromenv" and cli.resolve_git_sha("given") == "given"


def test_end_to_end_on_real_modules_logs_one_flat_pair(tmp_path, monkeypatch, capsys):
    """Part 1's modules on a flat archive: one eligible long, raced to its five-session mark."""
    monkeypatch.setattr(cli, "EARNINGS_LOOKUP", lambda *a, **k: [])
    days = [dt.date(2026, 11, 2) + dt.timedelta(days=i) for i in range(9)]   # Nov 2..10
    write_bars(tmp_path / "5min", "AAPL", five_min(days))
    columns = ("row_kind trade_id plan_id ticker strategy horizon direction plan_created_at plan_first_status_at "
               "plan_status plan_status_reason entry_type expiry_bars valid_session planned_entry opened_at entry "
               "stop_loss take_profit target2 closed_at exit_price close_reason last_leg_reason outcome r_realized "
               "mfe_r mae_r exit_efficiency holding_days stop_width_atr atr_pct regime2_state session_bucket "
               "days_to_earnings rs_percentile plan_issued_at plan_issued_at_source").split()
    values = dict.fromkeys(columns, "")
    values.update(row_kind="trade", trade_id="t-1", plan_id="p-1", ticker="AAPL", strategy="RSI", horizon="1m",
                  direction="bullish", plan_created_at="2026-11-02 14:40:00+00", plan_status="CLOSED",
                  entry_type="market", expiry_bars="3", planned_entry="100", opened_at="2026-11-02 15:02:10+00",
                  entry="100", stop_loss="98", take_profit="104", target2="108", closed_at="2026-11-02 18:00:00+00",
                  exit_price="98", close_reason="loss", last_leg_reason="loss", outcome="loss", r_realized="-1.0",
                  session_bucket="open")
    (tmp_path / "rows.csv").write_text(",".join(columns) + "\n" + ",".join(values[c] for c in columns) + "\n",
                                       encoding="utf-8")
    assert _run(tmp_path, "append") == 0
    assert capsys.readouterr().out.strip() == "v229 pairs: appended 1, total 1, forward 0"
    pair = pairlog.read_pairs(tmp_path / "pairs.jsonl")["t-1"]
    assert pair["rule_hash"] == verdict.rule_hash() and set(pair["arms"]) == {"C", "A", "B"}
    assert pair["entry_date"] == "2026-11-02" and pair["bucket"] == "open"
    json.dumps(pair, allow_nan=False)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_counterfactual.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'deferred_entry_counterfactual'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/reports/deferred_entry_counterfactual.py`:

```python
#!/usr/bin/env python3
"""v229 deferred-entry counterfactual: do late-session entries beat early ones?

Spec: docs/superpowers/specs/implemented/2026-11-14-v229-deferred-entry-counterfactual-design.md

Modes:
  append       log every eligible LONG plan not yet in the pair log; one count line (weekly cron)
  exploratory  append, then the one exploratory read (plans opened before T0): calibration, no verdict
  verdict      append, then the forward verdict, once, on or after verdict_open_date(T0)

On the VM (bot container, cwd /app; the host writes the export first):
  docker compose exec -T bot python scripts/reports/deferred_entry_counterfactual.py \
      --mode append --rows /app/data/v229/rows.csv --t0 <T0>
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _path in (str(ROOT), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from deferred_entry import arms, bars, pairlog, verdict  # noqa: E402
from deferred_entry import pairs as pairs_mod  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402

EARNINGS_LOOKUP = None          # None = the production earnings lookup inside build_pair
MODES: dict = {}                # V229-10b: "exploratory" and "verdict" handlers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", required=True, choices=("append", *MODES))
    parser.add_argument("--rows", required=True, help="export_book_rows.sh rows CSV")
    parser.add_argument("--bars-dir", default="market_data/5min")
    parser.add_argument("--pairs-log", default=pairlog.DEFAULT_LOG)
    parser.add_argument("--t0", required=True, help="freeze commit timestamp, ISO with offset")
    parser.add_argument("--out-dir", default="data/v229")
    parser.add_argument("--ledger", default=str(stats.LEDGER_PATH))
    parser.add_argument("--today", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--git-sha", default=None)
    return parser


def resolve_git_sha(given: str | None) -> str:
    if given:
        return given
    if os.environ.get("V229_GIT_SHA"):
        return os.environ["V229_GIT_SHA"]
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


def row_phase(row: dict, t0) -> str | None:
    """The read an export row belongs to; None without a parseable opened_at (plan rows)."""
    try:
        return verdict.phase(bars.et_date(bars.to_utc(row.get("opened_at"))), t0)
    except ValueError:
        return None


def select(pairs, t0, phase: str) -> list[dict]:
    return [p for p in pairs if verdict.phase(dt.date.fromisoformat(p["entry_date"]), t0) == phase]


def classify_rows(rows, bars_dir, archive_end) -> list[tuple[dict, object, str]]:
    cache: dict[str, object] = {}
    out = []
    for row in rows:
        frame = None
        if row.get("row_kind") == "trade":
            ticker = row.get("ticker") or ""
            if ticker not in cache:
                cache[ticker] = bars.load_bars(bars_dir, ticker)
            frame = cache[ticker]
        out.append((row, frame, pairs_mod.classify(row, frame, archive_end=archive_end)))
    return out


def build_pair_for(row: dict, frame) -> dict:
    return pairs_mod.build_pair(row, frame, rule_hash=verdict.rule_hash(), earnings_lookup=EARNINGS_LOOKUP)


def append_new(scanned, log_path) -> tuple[int, dict]:
    logged = pairlog.read_pairs(log_path)
    known = set(logged)
    added = 0
    for row, frame, reason in scanned:
        if reason != "eligible" or row.get("direction") != "bullish" or row.get("trade_id") in known:
            continue
        pair = build_pair_for(row, frame)
        pairlog.append_pair(log_path, pair, known=known)
        logged[pair["trade_id"]] = pair
        added += 1
    return added, logged


def _run(args) -> int:
    arms.assert_frictions()
    t0 = bars.to_utc(args.t0)
    last = bars.archive_last_bar(args.bars_dir)
    scanned = classify_rows(pairs_mod.read_export(args.rows), args.bars_dir, bars.to_utc(last) if last else None)
    added, logged = append_new(scanned, args.pairs_log)
    if args.mode == "append":
        forward = len(select(logged.values(), t0, "forward"))
        print(f"v229 pairs: appended {added}, total {len(logged)}, forward {forward}")
        return 0
    run = {"t0": t0, "archive_last_bar": last, "git_sha": resolve_git_sha(args.git_sha),
           "today": args.today or dt.datetime.now(dt.timezone.utc).date()}
    return MODES[args.mode](args, scanned, logged, run)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except (arms.FrictionsError, verdict.VerdictRefused, ValueError) as exc:  # ArchiveError, PairLogError: ValueError
        print(f"v229 refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_counterfactual.py`
Expected: PASS, `0 failed`. If `test_end_to_end_on_real_modules_logs_one_flat_pair` fails, print the reason `pairs.classify` returned for the row in a scratch run and fix the fixture row to the V229-5 contract, never the contract to the fixture.

- [ ] **Step 5: Complexity check and syntax pass**

Run: `python scripts/dev/complexity_gate.py` then `python -m py_compile scripts/reports/deferred_entry_counterfactual.py`
Expected: both exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/reports/deferred_entry_counterfactual.py tests/scripts/test_deferred_entry_counterfactual.py
git commit -m "feat(v229): CLI export, funnel and append mode (V229-10)"
```

### Task V229-10b: The CLI: exploratory and verdict modes

**Model:** sonnet — wiring of V229-7..V229-9 into two read modes; every refusal it surfaces is decided in V229-8.

Second half of the ledger's V229-10 (split past 20 KB). Needs V229-10 (it extends `scripts/reports/deferred_entry_counterfactual.py` and its test file, reusing `MODES`, `build_pair_for`, `row_phase`, `select`, `fake_book`, `_row`, `_run`).

**Files:**
- Modify: `scripts/reports/deferred_entry_counterfactual.py` (imports; new functions and the `MODES` entries placed after `append_new`, before `_run`)
- Modify: `tests/scripts/test_deferred_entry_counterfactual.py` (append tests)

**Interfaces:**
- Consumes: V229-10's helpers above; V229-7/7b `analysis.week_count`; V229-8 `verdict.guard`, `assert_one_rule`, `study_verdict`, `exploratory_close`, `VerdictRefused`; V229-9 `report.build_payload`, `render_markdown`; `stats.load_ledger`.
- Produces (index ledger): `--mode exploratory` writes `<out-dir>/exploratory.{md,json}` and prints `v229 exploratory: n=<n>, agreement <a>, CALIBRATED|UNCALIBRATED`; `--mode verdict` writes `<out-dir>/forward-verdict.{md,json}` and prints `v229 verdict: <study> (ledger <verdict>, n=<n>, p=<p>)`. Part 3 (V229-13, V229-15) copies those files into `docs/superpowers/results/` and appends the ledger row itself.

Rules:

- `exploratory` reads the logged pairs whose `entry_date` phase is `exploratory`. It refuses when `exploratory.json` already exists (the read runs once), when there are no such pairs (a wrong `--rows`/`--bars-dir` must never close the study as UNCALIBRATED), and via `assert_one_rule`. Payload `verdict = exploratory_close(calibration, n)`: `None` when calibrated, the INCONCLUSIVE close otherwise.
- `verdict` refuses when `forward-verdict.json` already exists, then `verdict.guard` (ledger already holds the id, before the open date, mixed rule hashes). It reads the `forward` pairs and sets `payload["verdict"] = study_verdict(deltas=payload["deltas"], calibration=payload["calibration"], ...)`, so the 10,000-resample bootstrap runs once. The CLI never writes the ledger.
- The funnel counts bullish rows whose entry phase matches the read, plus rows with no parseable `opened_at` (plan rows, `not_trade`). The context line is the live R of bullish `close_bucket` rows of the read's phase. Bearish eligible plans of the read's phase are built in memory for the disclosure and never logged (Handoff 15).

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_deferred_entry_counterfactual.py`:

```python
def test_exploratory_writes_both_outputs_once(tmp_path, fake_book, capsys):
    fake_book.rows = [_row("t-1", "2026-11-02", "eligible"), _row("t-2", "2026-11-10", "eligible"),
                      _row("t-3", "2026-11-03", "eligible", direction="bearish"),
                      _row("t-4", "2026-11-04", "close_bucket", r="0.5"), _row("t-5", "2026-11-24", "eligible")]
    assert _run(tmp_path, "exploratory") == 0
    assert "v229 exploratory: n=2" in capsys.readouterr().out
    payload = json.loads((tmp_path / "out" / "exploratory.json").read_text(encoding="utf-8"))
    assert payload["phase"] == "exploratory" and payload["arms"]["C"]["n"] == 2 and payload["verdict"] is None
    assert payload["bearish"]["n"] == 1 and payload["close_bucket"] == {"n": 1, "exp_r": 0.5}
    assert payload["funnel"] == {"eligible": 2, "close_bucket": 1} and payload["git_sha"] == "abc1234"
    assert "EXPLORATORY" in (tmp_path / "out" / "exploratory.md").read_text(encoding="utf-8")
    assert "t-3" not in pairlog.read_pairs(tmp_path / "pairs.jsonl")      # bearish never logged
    assert _run(tmp_path, "exploratory") == 2                              # the read runs once
    assert "once" in capsys.readouterr().err


def test_an_uncalibrated_exploratory_read_carries_the_inconclusive_close(tmp_path, fake_book, monkeypatch):
    fake_book.rows = [_row("t-1", "2026-11-02", "eligible")]
    hand_built = cli.pairs_mod.build_pair

    def disagreeing(row, frame, **kw):
        pair = hand_built(row, frame, **kw)
        pair["live"]["reason"] = "tp1_partial"                             # simulated loss, live TP1
        return pair

    monkeypatch.setattr(cli.pairs_mod, "build_pair", disagreeing)
    assert _run(tmp_path, "exploratory") == 0
    payload = json.loads((tmp_path / "out" / "exploratory.json").read_text(encoding="utf-8"))
    assert payload["verdict"]["ledger"] == {"verdict": "INCONCLUSIVE", "n": 1, "exp_r": None, "p": None}
    assert "UNCALIBRATED" in (tmp_path / "out" / "exploratory.md").read_text(encoding="utf-8")


def test_exploratory_with_no_exploratory_pairs_is_refused(tmp_path, fake_book, capsys):
    fake_book.rows = [_row("t-1", "2026-11-24", "eligible")]
    assert _run(tmp_path, "exploratory") == 2
    assert "no exploratory pairs" in capsys.readouterr().err
    assert not (tmp_path / "out" / "exploratory.json").exists()


def test_the_verdict_is_refused_before_its_open_date(tmp_path, fake_book, capsys):
    fake_book.rows = [_row("t-1", "2026-11-24", "eligible")]
    assert _run(tmp_path, "verdict", "--today", "2027-02-22") == 2
    assert "2027-02-23" in capsys.readouterr().err
    assert not (tmp_path / "out" / "forward-verdict.json").exists()


def test_the_verdict_is_written_once_on_its_open_date(tmp_path, fake_book, capsys):
    fake_book.rows = [_row("t-1", "2026-11-24", "eligible"), _row("t-2", "2026-12-01", "eligible"),
                      _row("t-0", "2026-11-02", "eligible")]                # exploratory: not in the verdict
    assert _run(tmp_path, "verdict", "--today", "2027-02-23") == 0
    payload = json.loads((tmp_path / "out" / "forward-verdict.json").read_text(encoding="utf-8"))
    assert payload["phase"] == "forward" and payload["verdict"]["study"] == "UNDERPOWERED"
    assert payload["verdict"]["ledger"]["verdict"] == "NO-LIFT" and payload["verdict"]["ledger"]["n"] == 2
    assert "VERDICT: UNDERPOWERED" in (tmp_path / "out" / "forward-verdict.md").read_text(encoding="utf-8")
    assert "v229 verdict: UNDERPOWERED (ledger NO-LIFT, n=2" in capsys.readouterr().out
    assert _run(tmp_path, "verdict", "--today", "2027-02-23") == 2                # computed once


def test_the_verdict_is_refused_once_the_ledger_holds_the_row(tmp_path, fake_book, capsys):
    (tmp_path / "ledger.jsonl").write_text(json.dumps({
        "id": verdict.LEDGER_ID, "date": "2027-02-23", "hypothesis": "h", "instrument": "v1", "n": 400,
        "exp_r": 0.1, "p": 0.2, "verdict": "NO-LIFT", "record": "docs/x.md"}) + "\n", encoding="utf-8")
    assert _run(tmp_path, "verdict", "--today", "2027-03-01") == 2
    assert "already" in capsys.readouterr().err


def test_the_verdict_refuses_a_log_written_under_another_rule(tmp_path, fake_book, capsys):
    stale = {**_pair("t-9", "2026-11-25"), "rule_hash": "ffffffffffffffff"}
    pairlog.append_pair(tmp_path / "pairs.jsonl", stale)
    fake_book.rows = [_row("t-1", "2026-11-24", "eligible")]
    assert _run(tmp_path, "verdict", "--today", "2027-02-23") == 2
    assert "another rule" in capsys.readouterr().err


def test_every_mode_is_offered():
    args = cli.build_parser().parse_args(["--mode", "verdict", "--rows", "r.csv", "--t0", T0])
    assert args.mode == "verdict" and set(cli.MODES) == {"exploratory", "verdict"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_counterfactual.py`
Expected: the new tests FAIL (`argparse` rejects `--mode exploratory`, exit code 2 raised as `SystemExit`); V229-10's tests still pass.

- [ ] **Step 3: Write the implementation**

In `scripts/reports/deferred_entry_counterfactual.py`, extend the imports to:

```python
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
```

```python
from deferred_entry import analysis, arms, bars, pairlog, report, verdict  # noqa: E402
```

Insert after `append_new` and before `_run`:

```python
OUTPUT_NAMES = {"exploratory": "exploratory", "verdict": "forward-verdict"}


def _context(scanned, t0, phase: str) -> dict:
    """Funnel, close-bucket context and bearish disclosure pairs for one read."""
    longs = [(row, reason) for row, _, reason in scanned if row.get("direction") == "bullish"]
    funnel = Counter(reason for row, reason in longs if row_phase(row, t0) in (phase, None))
    close_r = [float(row["r_realized"]) for row, reason in longs
               if reason == "close_bucket" and row_phase(row, t0) == phase and row.get("r_realized")]
    bearish = [build_pair_for(row, frame) for row, frame, reason in scanned
               if reason == "eligible" and row.get("direction") == "bearish" and row_phase(row, t0) == phase]
    return {"funnel": dict(funnel), "bearish": bearish,
            "close_bucket": {"n": len(close_r), "exp_r": sum(close_r) / len(close_r) if close_r else None}}


def _outputs(out_dir, mode: str) -> tuple[Path, Path]:
    stem = Path(out_dir) / OUTPUT_NAMES[mode]
    md, js = stem.with_suffix(".md"), stem.with_suffix(".json")
    if js.exists():
        raise verdict.VerdictRefused(f"{js} already exists: this read runs once")
    return md, js


def _write(paths: tuple[Path, Path], payload: dict) -> None:
    md, js = paths
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(report.render_markdown(payload), encoding="utf-8")
    js.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _payload(phase: str, sel: list[dict], ctx: dict, run: dict) -> dict:
    return report.build_payload(phase=phase, t0=run["t0"].isoformat(), pairs=sel, bearish=ctx["bearish"],
                                funnel=ctx["funnel"], close_bucket=ctx["close_bucket"],
                                archive_last_bar=run["archive_last_bar"], git_sha=run["git_sha"])


def run_exploratory(args, scanned, logged: dict, run: dict) -> int:
    paths = _outputs(args.out_dir, "exploratory")
    sel = select(logged.values(), run["t0"], "exploratory")
    if not sel:
        raise verdict.VerdictRefused("no exploratory pairs: check --rows, --bars-dir and --t0")
    verdict.assert_one_rule(sel)
    payload = _payload("exploratory", sel, _context(scanned, run["t0"], "exploratory"), run)
    payload["verdict"] = verdict.exploratory_close(payload["calibration"], len(sel))
    _write(paths, payload)
    cal = payload["calibration"]
    word = "CALIBRATED" if cal["calibrated"] else "UNCALIBRATED"
    print(f"v229 exploratory: n={len(sel)}, agreement {cal['agreement']}, {word}")
    return 0


def run_verdict(args, scanned, logged: dict, run: dict) -> int:
    paths = _outputs(args.out_dir, "verdict")
    verdict.guard(today=run["today"], t0=run["t0"], ledger_rows=stats.load_ledger(args.ledger),
                  pairs=list(logged.values()))
    sel = select(logged.values(), run["t0"], "forward")
    payload = _payload("forward", sel, _context(scanned, run["t0"], "forward"), run)
    payload["verdict"] = verdict.study_verdict(deltas=payload["deltas"], calibration=payload["calibration"],
                                               n_pairs=len(sel), weeks=analysis.week_count(sel))
    _write(paths, payload)
    ledger = payload["verdict"]["ledger"]
    print(f"v229 verdict: {payload['verdict']['study']} (ledger {ledger['verdict']}, n={ledger['n']}, "
          f"p={ledger['p']})")
    return 0


MODES.update(exploratory=run_exploratory, verdict=run_verdict)
```

`MODES` is filled at import time, before `build_parser()` runs, so `choices=("append", *MODES)` offers all three modes.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_counterfactual.py`
Expected: PASS, `0 failed` (V229-10's tests included).

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/reports/deferred_entry_counterfactual.py tests/scripts/test_deferred_entry_counterfactual.py
git commit -m "feat(v229): CLI exploratory and verdict modes (V229-10b)"
```
