# v138 Instrument v2, phase 4: Statistics. Part 3: Phases C and D, IS8-IS11

> Part of `2026-10-06-v138-instrument-v2-statistics_0-index.md` (header, where to work, global constraints, file map, review focus and `## Parallelisation` live there). Read that index's Global Constraints with every task. Steps use `- [ ]` for tracking. All paths are relative to the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v138-instrument-v2-statistics` unless a command names an absolute path.

# Phase C: the ledger

### Task IS8: Ledger append helper (`scripts/reports/preregistration_ledger.py`)

**Files:**
- Create: `scripts/reports/preregistration_ledger.py`
- Test: `tests/scripts/test_preregistration_ledger_cli.py`

**Interfaces:**
- Consumes: `stats.append_ledger_row`, `stats.ledger_qvalues`, `stats.LEDGER_PATH`, `stats.INSTRUMENTS`, `stats.VERDICTS` (IS3).
- Produces: CLI `python scripts/reports/preregistration_ledger.py --id ID --hypothesis TEXT --instrument v1|v2 --verdict VERDICT --record PATH [--date YYYY-MM-DD] [--n INT|null] [--exp-r FLOAT|null] [--p FLOAT|null] [--ledger PATH]`. Exit 0 and one stdout line `"<id>: verdict <V>, p=<p|null>, BH q=<q|n/a (no p-value)> across <m> ledger p-values (<rows> rows). Reported, not gating."`; exit 2 with `refused: ...` on stderr when the row is invalid or the id exists. Functions `build_parser()`, `row_from_args(args) -> dict`, `format_report(row, rows) -> str`, `main(argv=None) -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_preregistration_ledger_cli.py`:

```python
"""v136 §4: append a verdict to the ledger and print its BH q-value."""
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import preregistration_ledger as cli  # noqa: E402

from swingbot.core.backtesting.instrument import stats  # noqa: E402


def _args(ledger, **over):
    base = {"--id": "v999-demo", "--date": "2026-10-06", "--hypothesis": "Demo gate",
            "--instrument": "v2", "--n": "120", "--exp-r": "0.12", "--p": "0.03",
            "--verdict": "FAIL", "--record": "docs/superpowers/results/demo.md",
            "--ledger": str(ledger)}
    base.update(over)
    return [part for pair in base.items() for part in pair]


def _old_row():
    return {"id": "old", "date": "2026-10-01", "hypothesis": "Earlier gate",
            "instrument": "v1", "n": 50, "exp_r": 0.1, "p": 0.01,
            "verdict": "NO-LIFT", "record": "docs/superpowers/results/old.md"}


def test_append_prints_the_bh_q_value_across_the_ledger(tmp_path, capsys):
    ledger = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(_old_row(), path=ledger)
    assert cli.main(_args(ledger, **{"--p": "0.04"})) == 0
    out = capsys.readouterr().out
    assert out.strip() == ("v999-demo: verdict FAIL, p=0.0400, BH q=0.0400 across "
                           "2 ledger p-values (2 rows). Reported, not gating.")
    assert [row["id"] for row in stats.load_ledger(ledger)] == ["old", "v999-demo"]


def test_the_row_is_written_with_typed_values(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    assert cli.main(_args(ledger)) == 0
    row = stats.load_ledger(ledger)[0]
    assert (row["n"], row["exp_r"], row["p"], row["instrument"]) == (120, 0.12, 0.03, "v2")


def test_null_values_round_trip(tmp_path, capsys):
    ledger = tmp_path / "ledger.jsonl"
    assert cli.main(_args(ledger, **{"--n": "null", "--exp-r": "null",
                                     "--p": "null"})) == 0
    row = stats.load_ledger(ledger)[0]
    assert (row["n"], row["exp_r"], row["p"]) == (None, None, None)
    assert "p=null, BH q=n/a (no p-value) across 0 ledger p-values" in capsys.readouterr().out


def test_date_defaults_to_today(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    args = _args(ledger)
    i = args.index("--date")
    del args[i:i + 2]
    assert cli.main(args) == 0
    assert stats.load_ledger(ledger)[0]["date"] == date.today().isoformat()


def test_a_duplicate_id_is_refused_with_exit_2(tmp_path, capsys):
    ledger = tmp_path / "ledger.jsonl"
    assert cli.main(_args(ledger)) == 0
    assert cli.main(_args(ledger)) == 2
    assert "refused: duplicate id" in capsys.readouterr().err
    assert len(stats.load_ledger(ledger)) == 1


def test_an_out_of_range_p_is_refused(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    assert cli.main(_args(ledger, **{"--p": "1.5"})) == 2
    assert not ledger.exists()


def test_verdict_choices_come_from_stats(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(_args(tmp_path / "ledger.jsonl", **{"--verdict": "MAYBE"}))


def test_default_ledger_is_the_committed_file():
    args = cli.build_parser().parse_args(_args(Path("x"))[:-2])
    assert args.ledger == stats.LEDGER_PATH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_preregistration_ledger_cli.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'preregistration_ledger'`.

- [ ] **Step 3: Implement**

Create `scripts/reports/preregistration_ledger.py`:

```python
#!/usr/bin/env python3
"""Append one pre-registration verdict to the ledger and print its BH q-value.

v136 §4: docs/superpowers/results/preregistration-ledger.jsonl holds one row
per pre-registration. Run this once per new verdict, then commit the ledger
with the results doc. The q-value is REPORTED, NEVER GATING: no acceptance
threshold reads it, and a closed pre-registration is never re-run to move it.

    python scripts/reports/preregistration_ledger.py --id v140-demo \
        --hypothesis "..." --instrument v2 --n 412 --exp-r 0.21 --p 0.03 \
        --verdict FAIL --record docs/superpowers/results/2026-10-20-v140-validation.md
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.instrument import stats  # noqa: E402

_NULLS = ("null", "none", "")


def _optional(cast):
    def parse(text: str):
        return None if text.strip().lower() in _NULLS else cast(text)
    parse.__name__ = cast.__name__   # argparse names the type in its errors
    return parse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--id", required=True, help="unique, e.g. v140-confluence")
    p.add_argument("--date", default=None, help="YYYY-MM-DD of the verdict; default today")
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--instrument", choices=stats.INSTRUMENTS, required=True)
    p.add_argument("--n", type=_optional(int), default=None, help="int or null")
    p.add_argument("--exp-r", type=_optional(float), default=None, help="float or null")
    p.add_argument("--p", type=_optional(float), default=None, help="float in [0,1] or null")
    p.add_argument("--verdict", choices=stats.VERDICTS, required=True)
    p.add_argument("--record", required=True, help="repo-relative results doc path")
    p.add_argument("--ledger", type=Path, default=stats.LEDGER_PATH)
    return p


def row_from_args(args) -> dict:
    return {"id": args.id, "date": args.date or date.today().isoformat(),
            "hypothesis": args.hypothesis, "instrument": args.instrument,
            "n": args.n, "exp_r": args.exp_r, "p": args.p,
            "verdict": args.verdict, "record": args.record}


def _fmt(value) -> str:
    return "null" if value is None else f"{value:.4f}"


def format_report(row: dict, rows: list) -> str:
    q = stats.ledger_qvalues(rows)[row["id"]]
    m = sum(1 for r in rows if r["p"] is not None)
    q_text = "n/a (no p-value)" if q is None else f"{q:.4f}"
    return (f"{row['id']}: verdict {row['verdict']}, p={_fmt(row['p'])}, "
            f"BH q={q_text} across {m} ledger p-values ({len(rows)} rows). "
            "Reported, not gating.")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    row = row_from_args(args)
    try:
        rows = stats.append_ledger_row(row, path=args.ledger)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(format_report(row, rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scripts/test_preregistration_ledger_cli.py`
Expected: PASS, 0 failed.

Run: `python -m radon cc -s -n C scripts/reports/preregistration_ledger.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/preregistration_ledger.py tests/scripts/test_preregistration_ledger_cli.py
git commit -m "feat(v138): preregistration_ledger.py appends a verdict and prints its BH q-value"
```

---

### Task IS9: Backfill the ledger and document it

**Files:**
- Create: `docs/superpowers/results/preregistration-ledger.jsonl`
- Modify: `docs/claude/backtest-methodology.md` (one paragraph before "**The v72 procedure change does not reopen anything below.**")
- Modify: `AGENTS.md` (one sentence after "funnel and must name the gate they use instead.")
- Test: `tests/backtesting/test_preregistration_ledger_file.py`

**Interfaces:**
- Consumes: `stats.load_ledger`, `stats.LEDGER_PATH` (IS3); the CLI command name (IS8).
- Produces: the committed ledger, 53 rows, all `"instrument": "v1"`.

**Backfill rule (applied to every row below; the row content is final, do not re-derive it).** Source: every row of the `### Closed pre-registrations` table in `docs/claude/backtest-methodology.md` at `6485b8bb`, plus the two pre-registrations closed without a table row (v118, v119). A table row covering several separately-spent shots becomes one ledger row per shot (v31's four VALIDATION shots, v35's two AVWAP shots, v17 P1's stops and targets, v104 Part A's four holdout cells plus its eleven Stage 1/2 closures). `n`/`exp_r` are the decisive population the record names (the selected or shot cell; for a single-population check, that population); `null` where the record names no single one, or names only a delta. `p` is `null` wherever the record holds no p-value; the only recorded p is v92 Hypothesis 2's `p=1.0000` (`results/2026-09-16-v92-stall-exit-train.md`, lines 30 and 41). Verdict mapping: `PASS` a shot that shipped; `FAIL` a VALIDATION/holdout shot spent and failed; `NO-LIFT` closed before spending a shot; `UNMEASURABLE` refused or degenerate by construction; `WITHDRAWN` withdrawn before measurement; `OPEN` registered with no verdict yet (v86; v104's two sealed-thin cells, whose shot is unspent). `record` is the results doc that states the figures, falling back to the pre-registration plan or spec the table names. In-flight pre-registrations (v124, v134, v135) are **not** backfilled; each appends its own row with IS8's helper at its verdict.

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_preregistration_ledger_file.py`:

```python
"""The committed pre-registration ledger (v136 §4): valid, traceable, complete."""
import re
from pathlib import Path

from swingbot.core.backtesting.instrument import stats

ROOT = Path(__file__).resolve().parents[2]
METHODOLOGY = ROOT / "docs" / "claude" / "backtest-methodology.md"

#: The 2026-10-06 backfill (v138 IS9). These rows are never deleted or
#: rewritten; a re-measurement is a new pre-registration with a new id.
BACKFILL_IDS = (
    "e33-avwap-levels", "v17-regime-allow", "v17-level-lifecycle-stops",
    "v17-level-lifecycle-targets", "edge-v4-data-driven-stops", "v34-rs-gate-bearish",
    "v35-avwap-levels", "v31-break-retest", "v31-macd", "v31-vwap",
    "v31-volume-profile", "v36-level-touch-strength", "v49-effective-confluence",
    "v68-dcb-veto", "v69-double-pattern", "legacy-badge-refresh-2026-09-10",
    "v84-ema-crossover", "v84-break-retest-horizon-gate", "v84-vwap-4w",
    "v84-rsi-divergence-persistence", "v84-ma-ribbon-confirm-bars",
    "v84-sr-min-level-touches", "v84-fib-extension-1-0", "v84-elliott-rescue",
    "v86-cohort-label", "v82-earnings-blackout", "v88-armed-confluence",
    "v92-h1-adaptive-runner-trail", "v92-h2-stall-exit", "v90-rejection-armed",
    "v93-bearish-arms", "v98-q-inv", "v101-fib-rescue-v2", "v102-fib-rolling-sr",
    "v103-a-fib-level-stop", "v103-c-fib-continuation", "v104-a-macd-bullish",
    "v104-a-sr-bullish", "v104-a-break-retest-bullish",
    "v104-a-volume-profile-bullish", "v104-a-other-cells", "v104-b-short-mechanisms",
    "v105-pending-range", "v108-e-ema-rearm", "v113-a-downtrend-fade",
    "v113-b-legacy-1w", "v113-d-inverse-etf-longs", "v118-short-universe",
    "v123-hl-trail", "v123-progress-stall", "v119-compression-short",
    "v122-strategy", "v122-confluence",
)


def _rows():
    return stats.load_ledger()   # validates every row and refuses duplicate ids


def test_the_committed_ledger_loads_and_validates():
    assert len(_rows()) >= len(BACKFILL_IDS) == 53


def test_the_backfill_is_present_and_instrument_v1():
    by_id = {row["id"]: row for row in _rows()}
    assert [i for i in BACKFILL_IDS if i not in by_id] == []
    assert {by_id[i]["instrument"] for i in BACKFILL_IDS} == {"v1"}


def test_every_record_points_at_a_file_in_the_repo():
    missing = [row["record"] for row in _rows() if not (ROOT / row["record"]).is_file()]
    assert missing == []


def _closed_table_tags() -> set:
    lines = METHODOLOGY.read_text(encoding="utf-8").splitlines()
    start = lines.index("### Closed pre-registrations — do not re-run these")
    tags = set()
    for line in lines[start + 1:]:
        if line.startswith("|"):
            tags.update(re.findall(r"\((v\d+)", line))
        elif line.strip():
            break
    return tags


def test_every_closed_table_version_has_a_ledger_row():
    """A new closed-table row must land in the ledger too (one row per pre-registration)."""
    tags = _closed_table_tags()
    assert len(tags) >= 24
    ids = [row["id"] for row in _rows()]
    assert sorted(t for t in tags if not any(i.startswith(f"{t}-") for i in ids)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py`
Expected: FAIL (`load_ledger` returns `[]`, so `0 >= 53` fails).

- [ ] **Step 3: Write the ledger**

Create `docs/superpowers/results/preregistration-ledger.jsonl` with exactly these 53 lines (LF line endings, one trailing newline):

```jsonl
{"id": "e33-avwap-levels", "date": "2026-07-26", "hypothesis": "AVWAP_LEVELS_ENABLED first shot, improvement gate (E33)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "FAIL", "record": "docs/superpowers/plans/implemented/v35-avwap-preregistration.md"}
{"id": "v17-regime-allow", "date": "2026-08-08", "hypothesis": "REGIME_ALLOW regime gate, per strategy x regime cell (v17 P2a)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-08-08-regime-allow-train.md"}
{"id": "v17-level-lifecycle-stops", "date": "2026-08-08", "hypothesis": "Level-lifecycle stops (v17 P1)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "PASS", "record": "docs/superpowers/results/2026-08-08-level-lifecycle-stops-validation.md"}
{"id": "v17-level-lifecycle-targets", "date": "2026-08-08", "hypothesis": "Level-lifecycle targets (v17 P1)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-08-08-level-lifecycle-folds.md"}
{"id": "edge-v4-data-driven-stops", "date": "2026-08-08", "hypothesis": "DATA_DRIVEN_STOPS_ENABLED (edge-engine v4); unmeasurable, the backtest sized through _trade_plan_at", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "UNMEASURABLE", "record": "docs/superpowers/specs/implemented/2026-08-08-v17-market-context-and-level-lifecycle-design.md"}
{"id": "v34-rs-gate-bearish", "date": "2026-08-16", "hypothesis": "RS_GATE bearish-only arm, RS_LAGGARD_PERCENTILE=25 on rs_combined (v34)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "PASS", "record": "docs/superpowers/plans/implemented/v34-train-preregistration.md"}
{"id": "v35-avwap-levels", "date": "2026-08-16", "hypothesis": "AVWAP_LEVELS_ENABLED with 52-week extreme anchors, non-inferiority (v35)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "PASS", "record": "docs/superpowers/plans/implemented/v35-avwap-preregistration.md"}
{"id": "v31-break-retest", "date": "2026-08-17", "hypothesis": "Structural target selection, Break & Retest badge, VALIDATION pooled across horizons (v31)", "instrument": "v1", "n": 112, "exp_r": 0.195, "p": null, "verdict": "FAIL", "record": "docs/superpowers/results/2026-08-17-structural-target-validation.md"}
{"id": "v31-macd", "date": "2026-08-17", "hypothesis": "Structural target selection, MACD badge, VALIDATION pooled across horizons (v31)", "instrument": "v1", "n": 112, "exp_r": 0.219, "p": null, "verdict": "PASS", "record": "docs/superpowers/results/2026-08-17-structural-target-validation.md"}
{"id": "v31-vwap", "date": "2026-08-17", "hypothesis": "Structural target selection, VWAP badge, VALIDATION pooled across horizons (v31)", "instrument": "v1", "n": 75, "exp_r": 0.302, "p": null, "verdict": "FAIL", "record": "docs/superpowers/results/2026-08-17-structural-target-validation.md"}
{"id": "v31-volume-profile", "date": "2026-08-17", "hypothesis": "Structural target selection, Volume Profile badge, VALIDATION pooled across horizons (v31)", "instrument": "v1", "n": 32, "exp_r": 0.547, "p": null, "verdict": "PASS", "record": "docs/superpowers/results/2026-08-17-structural-target-validation.md"}
{"id": "v36-level-touch-strength", "date": "2026-08-22", "hypothesis": "LEVEL_TOUCH_STRENGTH target tiebreak and confidence factor (v36)", "instrument": "v1", "n": 550, "exp_r": 0.0057, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-08-22-level-touch-strength-train.md"}
{"id": "v49-effective-confluence", "date": "2026-08-23", "hypothesis": "EFFECTIVE_CONFLUENCE_ENABLED participation-ratio confluence count (v49)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "UNMEASURABLE", "record": "docs/superpowers/results/2026-08-23-v49-confluence-redundancy.md"}
{"id": "v68-dcb-veto", "date": "2026-08-30", "hypothesis": "DEAD_CAT_BOUNCE_VETO cell d15_gN_voff (v68)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "FAIL", "record": "docs/superpowers/results/2026-08-30-v68-dcb-veto-validation.md"}
{"id": "v69-double-pattern", "date": "2026-08-30", "hypothesis": "Double Pattern strategy, 12-cell TRAIN grid (v69)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-08-30-v69-double-pattern-train.md"}
{"id": "legacy-badge-refresh-2026-09-10", "date": "2026-09-10", "hypothesis": "Legacy badge refresh: Fibonacci, RSI, Support/Resistance under current arithmetic", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-10-legacy-badge-refresh-train.md"}
{"id": "v84-ema-crossover", "date": "2026-09-10", "hypothesis": "EMA Crossover pullback re-measurement (v84)", "instrument": "v1", "n": 55, "exp_r": 0.494, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-10-v84-ema-crossover-preregistration.md"}
{"id": "v84-break-retest-horizon-gate", "date": "2026-09-10", "hypothesis": "Break & Retest horizon gate {2m,3m,4m} badge (v84)", "instrument": "v1", "n": 105, "exp_r": 0.308, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-10-v84-break-retest-preregistration.md"}
{"id": "v84-vwap-4w", "date": "2026-09-10", "hypothesis": "VWAP narrowed-to-4w gate + slope-persistence fallback badge (v84)", "instrument": "v1", "n": 68, "exp_r": 0.335, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-10-v84-vwap-preregistration.md"}
{"id": "v84-rsi-divergence-persistence", "date": "2026-09-10", "hypothesis": "RSI Divergence min_consecutive_rsi_turn persistence gate (v84)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-10-v84-rsidiv-train.md"}
{"id": "v84-ma-ribbon-confirm-bars", "date": "2026-09-10", "hypothesis": "MA Ribbon confirm_bars alignment-persistence gate (v84)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-10-v84-maribbon-train.md"}
{"id": "v84-sr-min-level-touches", "date": "2026-09-10", "hypothesis": "Support/Resistance min_level_touches significance gate (v84)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-10-v84-sr-train.md"}
{"id": "v84-fib-extension-1-0", "date": "2026-09-10", "hypothesis": "Fibonacci 1.0 extension target candidate (v84)", "instrument": "v1", "n": 245, "exp_r": 0.233, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-10-v84-fib-extension-train.md"}
{"id": "v84-elliott-rescue", "date": "2026-09-10", "hypothesis": "Elliott Wave retracement-depth and volume-confirmation rescue (v84)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "WITHDRAWN", "record": "docs/superpowers/results/2026-09-10-v84-elliott-hypothesis-invalidated.md"}
{"id": "v86-cohort-label", "date": "2026-09-14", "hypothesis": "COHORT_POOR plans close at ExpR <= non-POOR - 0.20R, n >= 150 per group (v86)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "OPEN", "record": "docs/superpowers/specs/implemented/2026-09-14-v86-cohort-risk-label-design.md"}
{"id": "v82-earnings-blackout", "date": "2026-09-15", "hypothesis": "EARNINGS_BLACKOUT_SESSIONS K in {1,2,3,5} (v82)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-15-v82-earnings-blackout-stage1.md"}
{"id": "v88-armed-confluence", "date": "2026-09-16", "hypothesis": "Armed confluence entries, test + reaction at the stop level, 24-cell grid (v88)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-16-v88-armed-stage1.md"}
{"id": "v92-h1-adaptive-runner-trail", "date": "2026-09-16", "hypothesis": "ADAPTIVE_RUNNER_TRAIL_ENABLED 9-cell grid (v92 Hypothesis 1)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-16-v92-adaptive-trail-train.md"}
{"id": "v92-h2-stall-exit", "date": "2026-09-16", "hypothesis": "STALL_EXIT_ENABLED (v92 Hypothesis 2); unmeasurable, arms byte-identical", "instrument": "v1", "n": 4258, "exp_r": null, "p": 1.0, "verdict": "UNMEASURABLE", "record": "docs/superpowers/results/2026-09-16-v92-stall-exit-train.md"}
{"id": "v90-rejection-armed", "date": "2026-09-17", "hypothesis": "Rejection-only armed entries, R2/R3 void the arm, 30-cell grid (v90)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-17-v90-rejection-stage1.md"}
{"id": "v93-bearish-arms", "date": "2026-09-17", "hypothesis": "Bearish-arm re-derivation, seven bullish-only masks (v93)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-17-v93-bearish-arms-train.md"}
{"id": "v98-q-inv", "date": "2026-09-21", "hypothesis": "Q-INV inverse-instrument horizons, PSQ/SH/RWM/DOG (v98)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-21-v98-q-inv-train.md"}
{"id": "v101-fib-rescue-v2", "date": "2026-09-24", "hypothesis": "Fibonacci rescue v2: structural-stop filter / deeper-ratio stop / reclaim entry, long and short (v101)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-24-v101-fib-diagnostic.md"}
{"id": "v102-fib-rolling-sr", "date": "2026-09-24", "hypothesis": "Fibonacci x Rolling S/R confluence, tol in {0.25,0.5,0.75,1.0} ATR (v102)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-24-v102-stage12.md"}
{"id": "v103-a-fib-level-stop", "date": "2026-09-25", "hypothesis": "Fibonacci level-stop, b ATR past the tested level, bullish winner b=0.1 VALIDATION (v103 A)", "instrument": "v1", "n": 190, "exp_r": 0.313, "p": null, "verdict": "FAIL", "record": "docs/superpowers/results/2026-09-25-v103-validation.md"}
{"id": "v103-c-fib-continuation", "date": "2026-09-25", "hypothesis": "Fibonacci Continuation, d_max in {0.5,0.618,0.786}, bullish winner d_max=0.618 (v103 C)", "instrument": "v1", "n": 1199, "exp_r": 0.243, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-25-v103-stage12.md"}
{"id": "v104-a-macd-bullish", "date": "2026-09-28", "hypothesis": "Structural stops with fixed-dollar-risk sizing, MACD bullish, 2026 holdout (v104 Part A)", "instrument": "v1", "n": 27, "exp_r": 0.053, "p": null, "verdict": "FAIL", "record": "docs/superpowers/results/2026-09-28-v104-holdout.md"}
{"id": "v104-a-sr-bullish", "date": "2026-09-28", "hypothesis": "Structural stops with fixed-dollar-risk sizing, Support/Resistance bullish, 2026 holdout (v104 Part A)", "instrument": "v1", "n": 45, "exp_r": 0.139, "p": null, "verdict": "FAIL", "record": "docs/superpowers/results/2026-09-28-v104-holdout.md"}
{"id": "v104-a-break-retest-bullish", "date": "2026-09-28", "hypothesis": "Structural stops with fixed-dollar-risk sizing, Break & Retest bullish, 2026 holdout sealed-thin, one shot unspent (v104 Part A)", "instrument": "v1", "n": 4, "exp_r": null, "p": null, "verdict": "OPEN", "record": "docs/superpowers/results/2026-09-28-v104-holdout.md"}
{"id": "v104-a-volume-profile-bullish", "date": "2026-09-28", "hypothesis": "Structural stops with fixed-dollar-risk sizing, Volume Profile bullish, 2026 holdout sealed-thin, one shot unspent (v104 Part A)", "instrument": "v1", "n": 9, "exp_r": null, "p": null, "verdict": "OPEN", "record": "docs/superpowers/results/2026-09-28-v104-holdout.md"}
{"id": "v104-a-other-cells", "date": "2026-09-28", "hypothesis": "Structural stops with fixed-dollar-risk sizing, the 11 cells closed at Stage 1/2 (v104 Part A)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-28-v104-partA.md"}
{"id": "v104-b-short-mechanisms", "date": "2026-09-28", "hypothesis": "Bull Trap, Vol Expansion Breakdown, Earnings Gap Drift short-only mechanisms (v104 Part B)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-28-v104-partB.md"}
{"id": "v105-pending-range", "date": "2026-09-29", "hypothesis": "Pending range continuation, N in {10,15,20} x d in {0.25,0.50,0.75}, long and short (v105)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-29-v105-train.md"}
{"id": "v108-e-ema-rearm", "date": "2026-09-29", "hypothesis": "EMA Crossover re-arm, first K in {2,3} pullback touch events per held cross (v108 E)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-29-v108-stage12.md"}
{"id": "v113-a-downtrend-fade", "date": "2026-09-30", "hypothesis": "Downtrend Overbought Fade on the masked 1w horizon, m in {1.0,1.25,1.5} (v113 Part A)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-30-v113-partA.md"}
{"id": "v113-b-legacy-1w", "date": "2026-09-30", "hypothesis": "22 legacy strategy x direction cells on the masked 1w horizon (v113 Part B)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-30-v113-partB.md"}
{"id": "v113-d-inverse-etf-longs", "date": "2026-09-30", "hypothesis": "Inverse-ETF longs, all admitted strategy x horizon cells pooled (v113 Part D)", "instrument": "v1", "n": 109, "exp_r": 0.0749, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-09-30-v113-partD.md"}
{"id": "v118-short-universe", "date": "2026-10-02", "hypothesis": "SHORT candidate universe, broad and isolated lanes (v118)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "UNMEASURABLE", "record": "docs/superpowers/results/2026-10-02-v118-short-universe-result.md"}
{"id": "v123-hl-trail", "date": "2026-10-02", "hypothesis": "RUNNER_STRUCTURE_EXIT=hl_trail, b in {0, 0.25, 0.5} (v123)", "instrument": "v1", "n": 8737, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-10-02-v123-hl-trail.md"}
{"id": "v123-progress-stall", "date": "2026-10-02", "hypothesis": "RUNNER_STRUCTURE_EXIT=progress_stall, c in {0.70, 0.85, 1.00} (v123)", "instrument": "v1", "n": 439, "exp_r": null, "p": null, "verdict": "UNMEASURABLE", "record": "docs/superpowers/results/2026-10-02-v123-progress-stall.md"}
{"id": "v119-compression-short", "date": "2026-10-04", "hypothesis": "Compression short, broad and isolated arms (v119)", "instrument": "v1", "n": null, "exp_r": null, "p": null, "verdict": "UNMEASURABLE", "record": "docs/superpowers/results/2026-10-04-v119-compression-short-result.md"}
{"id": "v122-strategy", "date": "2026-10-04", "hypothesis": "Pullback volume dry-up gate, strategy scope, d in {0.60, 0.75, 0.90} (v122)", "instrument": "v1", "n": 10541, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-10-04-v122-strategy.md"}
{"id": "v122-confluence", "date": "2026-10-05", "hypothesis": "Pullback volume dry-up gate, confluence scope, d in {0.60, 0.75, 0.90} (v122)", "instrument": "v1", "n": 10541, "exp_r": null, "p": null, "verdict": "NO-LIFT", "record": "docs/superpowers/results/2026-10-05-v122-confluence.md"}
```

Then confirm the line endings: `python -c "import pathlib; b = pathlib.Path('docs/superpowers/results/preregistration-ledger.jsonl').read_bytes(); print(b.count(b'\n'), b'\r' in b, b.endswith(b'\n'))"`
Expected: `53 False True`. If `\r` is present (a Windows editor), rewrite the file with LF endings before continuing.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py`
Expected: PASS, 0 failed.

Run: `python scripts/reports/preregistration_ledger.py --help`
Expected: usage text listing `--id`, `--instrument {v1,v2}`, `--verdict {PASS,FAIL,NO-LIFT,UNMEASURABLE,WITHDRAWN,OPEN}`. (Do **not** run an append against the real ledger here.)

- [ ] **Step 5: Document the ledger in the methodology**

In `docs/claude/backtest-methodology.md`, directly before the line that starts `**The v72 procedure change does not reopen anything below.**`, insert this paragraph and a blank line after it:

```markdown
**Pre-registration ledger (v136 §4).** `docs/superpowers/results/preregistration-ledger.jsonl`
holds one row per pre-registration: `id, date, hypothesis, instrument, n,
exp_r, p, verdict, record`. Every new verdict appends its row with
`python scripts/reports/preregistration_ledger.py --id … --instrument v1|v2
--verdict … --record …`, which prints the Benjamini–Hochberg q-value across
every ledger p-value. **Reported, never gating:** no threshold in this file
reads it, and a weak q never reopens or re-runs anything. Rows are never
edited; a re-measurement is a new pre-registration with a new id. The
2026-10-06 backfill (v138) covers every row of the table below plus v118 and
v119; `n`/`exp_r` are the decisive population the record names and `null`
where it names none, and `p` is `null` wherever no p-value was recorded.
```

- [ ] **Step 6: Mirror it for Codex**

In `AGENTS.md`, replace

```markdown
strategy-badge threshold. `Edge: harvest` features are out of scope for this
funnel and must name the gate they use instead.
```

with

```markdown
strategy-badge threshold. `Edge: harvest` features are out of scope for this
funnel and must name the gate they use instead. Every pre-registration verdict
appends one row to `docs/superpowers/results/preregistration-ledger.jsonl` with
`python scripts/reports/preregistration_ledger.py`, which prints a
Benjamini–Hochberg q-value across the ledger; the q-value is reported, never
gating, and ledger rows are never edited.
```

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/results/preregistration-ledger.jsonl tests/backtesting/test_preregistration_ledger_file.py docs/claude/backtest-methodology.md AGENTS.md
git commit -m "docs(v138): pre-registration ledger, backfilled with 53 closed rows; methodology + AGENTS mirror"
```

---

# Phase D: verification and release

### Task IS10: Complexity sweep and pyflakes over every touched file

**Files:**
- Read only: every file IS1–IS9 created or modified.

**Interfaces:**
- Consumes: everything above. Produces: nothing new; a fix commit only if a check fails.

- [ ] **Step 1: Complexity**

Run:

```bash
python -m radon cc -s -n C swingbot/core/backtesting/instrument/stats.py swingbot/core/backtesting/acceptance.py swingbot/core/backtesting/acceptance_harvest.py swingbot/core/backtesting/arms/selection.py scripts/backtest/funnel.py scripts/backtest/harvest_select.py scripts/reports/preregistration_ledger.py
```

Expected: no output (every function below C, i.e. complexity < 11, comfortably under the 15 limit). If a line prints, split that function into named helpers without changing behaviour, re-run the task's tests and IS4's pin, and commit the split as `refactor(v138): ...`.

- [ ] **Step 2: Syntax and unused names**

Run: `python -m py_compile swingbot/core/backtesting/instrument/__init__.py swingbot/core/backtesting/instrument/stats.py swingbot/core/backtesting/acceptance.py swingbot/core/backtesting/acceptance_harvest.py swingbot/core/backtesting/arms/selection.py scripts/backtest/funnel.py scripts/backtest/harvest_select.py scripts/reports/preregistration_ledger.py`
Expected: no output.

Run: `python -m pyflakes swingbot/core/backtesting/instrument scripts/reports/preregistration_ledger.py tests/backtesting/_cluster_fixture.py tests/backtesting/test_instrument_stats_bootstrap.py tests/backtesting/test_instrument_stats_bh.py tests/backtesting/test_instrument_stats_ledger.py tests/backtesting/test_ticker_cluster_pin.py tests/backtesting/test_acceptance_cluster_unit.py tests/backtesting/test_acceptance_harvest_cluster_unit.py tests/backtesting/test_verdict_helpers_cluster_unit.py tests/backtesting/test_preregistration_ledger_file.py tests/scripts/test_preregistration_ledger_cli.py`
Expected: no output.

- [ ] **Step 3: The diff-selected run**

Run: `python scripts/dev/testrun.py changed`
Expected: `0 failed`, `0 xfailed`.

- [ ] **Step 4: Commit (only if Step 1 or 2 needed a fix)**

```bash
git add <the fixed files>
git commit -m "refactor(v138): <what was split or cleaned>"
```

---

### Task IS11: Full suite, merge, release, close-out

**Files:**
- Modify (on `main`): `VERSION.json`, `swingbot/admin/version_history.json`
- Move (on `main`): the four `docs/superpowers/plans/2026-10-06-v138-instrument-v2-statistics_*.md` parts → `docs/superpowers/plans/implemented/`

**Interfaces:**
- Consumes: everything above. Produces: phase 4 on `main`; `stats.week_cluster_bootstrap` and `cluster=` ready for phase 6 to wire.

- [ ] **Step 1: The one full-suite run**

Dispatch the `test-runner` subagent in the worktree with: `python scripts/dev/testrun.py full`.
Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). On any failure: fix it in the worktree, re-run the failing file, and re-dispatch the full run. Do not proceed red.

- [ ] **Step 2: Merge into `main`**

Invoke the `worktree-lifecycle` skill (another session may be committing to `main`; memory: concurrent session commits). Then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -3 main
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-10-06-v138-instrument-v2-statistics -m "merge(v138): instrument v2 phase 4 -- week-clustered bootstrap, pre-registration ledger"
```

**If the merge reports an add/add conflict on `swingbot/core/backtesting/instrument/__init__.py`** (phase 1, v137, landed first and created it): keep `main`'s version (`git -C E:/Documents/Private/Projects/Discord-Bot checkout --ours swingbot/core/backtesting/instrument/__init__.py`, then `git add` it). This plan's file was a docstring only and nothing here imports from the package `__init__`. Any other conflict: stop and resolve it by reading both sides; never take one side wholesale.

After the merge, on `main`: run `python scripts/dev/testrun.py file tests/backtesting/test_ticker_cluster_pin.py` and `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_cluster_unit.py`.
Expected: both PASS. If phase 1 or 2 merged first and changed `acceptance`'s ticker path on purpose, the pin's failure is that phase's v1-golden question, not this plan's: stop and report it to the partner rather than re-pinning.

- [ ] **Step 3: Release commit (bot minor)**

Read `VERSION.json` on `main` now (never this header, never memory). Increment the `bot` line's **minor** component, reset its patch to 0, leave `ui` untouched, and set `bot_updated` to the current UTC time in the `YYYY-MM-DD HH-MM-SS` format. Commit only that file:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add VERSION.json
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "release(bot): <new bot version> -- instrument v2 statistics: week-clustered bootstrap, pre-registration ledger"
```

- [ ] **Step 4: Regenerate the version history**

```bash
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/build_version_matrix.py
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git -C E:/Documents/Private/Projects/Discord-Bot add swingbot/admin/version_history.json
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "chore(bot): <new bot version> -- instrument v2 statistics: week-clustered bootstrap, pre-registration ledger"
```

Expected: the version-matrix test PASSES before the commit.

- [ ] **Step 5: Close out the plan**

The umbrella spec v136 stays live (phases 1–3, 5 and 6 are still open); only this plan moves. Update the `## Progress` block in `_0-index.md` to "Done: IS1–IS11 on `main`, <merge sha>. Phase 6 wires `--instrument v2` to `cluster="week"`." then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot mv docs/superpowers/plans/2026-10-06-v138-instrument-v2-statistics_0-index.md docs/superpowers/plans/implemented/
git -C E:/Documents/Private/Projects/Discord-Bot mv docs/superpowers/plans/2026-10-06-v138-instrument-v2-statistics_1-stats-module.md docs/superpowers/plans/implemented/
git -C E:/Documents/Private/Projects/Discord-Bot mv docs/superpowers/plans/2026-10-06-v138-instrument-v2-statistics_2-cluster-selector.md docs/superpowers/plans/implemented/
git -C E:/Documents/Private/Projects/Discord-Bot mv docs/superpowers/plans/2026-10-06-v138-instrument-v2-statistics_3-ledger-and-release.md docs/superpowers/plans/implemented/
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v138): close out -- instrument v2 statistics plan implemented"
```

- [ ] **Step 6: Remove the worktree**

With the `worktree-lifecycle` skill: confirm `git -C E:/Documents/Private/Projects/Discord-Bot rev-list --count main..2026-10-06-v138-instrument-v2-statistics` prints `0`, then remove the worktree and delete the branch (its name contains neither `backup` nor `stable-`).

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree remove .claude/worktrees/2026-10-06-v138-instrument-v2-statistics
git -C E:/Documents/Private/Projects/Discord-Bot branch -d 2026-10-06-v138-instrument-v2-statistics
```
