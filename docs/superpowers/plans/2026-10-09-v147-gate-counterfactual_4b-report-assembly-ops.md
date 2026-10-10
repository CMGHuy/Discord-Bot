# v147 Gate counterfactual: Part 4b, report assembly and operations (V147-15..V147-18)

> Part of the v147 plan, split from Part 4 to stay under the 1500-line cap. Header, Global Constraints, deviations, parallelisation and the task ledger are in [`_0-index`](2026-10-09-v147-gate-counterfactual_0-index.md); the controller decisions and the notes for v150 this part applies are at the top of [`_4-report-ops`](2026-10-09-v147-gate-counterfactual_4-report-ops.md). **Never read this file whole**: `/task-brief V147-15` or `grep -n "^### Task V147-15:" -A 400 docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_4b-report-assembly-ops.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v147-gate-counterfactual-design.md`](../specs/2026-10-09-v147-gate-counterfactual-design.md) § The report, § Pre-registered verdict, § Production progress cron, § TRAIN side (runs), § Testing.

All commands run inside the plan's worktree `.claude/worktrees/2026-10-09-v147-gate-counterfactual` (created by V147-1). Paths below are relative to it.

---

# Phase 5 (continued): Report assembly

### Task V147-15: `build_report`, cells/rows, persistence, script wrapper

**Model:** sonnet — assembles V147-13's statistics and V147-14's inputs into the fixed v150 shape; every rule it applies is already pinned by those tasks and the decisions at the top of this part.

**Files:**
- Modify: `swingbot/core/analytics/gate_counterfactual_report.py`
- Create: `scripts/reports/gate_counterfactual_report.py`
- Create: `tests/analytics/test_gate_counterfactual_report.py`
- Create: `tests/scripts/test_gate_counterfactual_report_script.py`

**Interfaces:**
- Consumes: V147-13 (`cell_key`, `distinct_setups`, `arm_stats`, `difference_reading`, `family_qvalues`, `classify`, `CELLS`, `CELL_GATE`, `VERDICT_FLOOR`, `NEAR_MISS_BANDS`, `WAITING`, `_mean`, `_filled`); V147-14 (`load_train_rows`, `default_train_paths`, `load_live`); V147-8 (`gate_counterfactual_store.write_report(result, path=None) -> dict` carries every complete on-disk `verdict_of_record` forward; `load_report(path=None)`); `blocked_recorder.gate_row` (V147-4; tests); `strategy_types.COMPRESSION_SHORT` (exists).
- Produces (ledger): `build_report(*, train_rows=None, live_blocked=None, live_taken=None, today=None, write=True, path=None) -> dict` (`generated_at, live_window, cells[], rows[]` plus additive `bh_family, seed, limitations`); `_cell(state, q, today) -> dict`; `_row(key, reason, population, blocked, taken) -> dict`; `load_report` re-exported from the infra store. Script: `scripts/reports/gate_counterfactual_report.py` with `main(argv=None) -> int`, `cell_lines(result) -> list[str]`, `row_lines(result) -> list[str]`.

**Rules fixed here:**
- Cells: the five `CELLS` in order, then three note cells: `rs` × `train` (`"no TRAIN population"`), `no_qualifying_target` × `live` and × `train` (`"no verdict — no-plan"`). Every note cell has `verdict = "WAITING"`, `n = 0`, `latest = None`, `verdict_of_record = None`.
- Per verdict cell: blocked arm = distinct setups of the population's blocked rows with that `cell_key`; taken arm = distinct setups of the population's taken rows whose `gate` is `CELL_GATE[key]`, whose `(source family, direction)` appears among the blocked rows (`short_lane` → `confluence`), and, for `compression`, whose `strategy == COMPRESSION_SHORT`. `n` and `taken_n` count distinct **filled** setups.
- Order of the cell checks: blocked `n < 30` → `WAITING`, no note; taken arm empty → note (`EMPTY_TAKEN_NOTES[(gate, population)]`, default `"no <POPULATION> taken arm"`); taken `taken_n < 30` → note `"taken arm below the floor (<k> distinct filled setups < 30)"`; otherwise the reading. A note cell's verdict is `WAITING` and it carries no `latest`, no record, and enters BH as p = 1.0.
- `verdict_of_record` is seeded `{verdict, date: today, n}` whenever the reading is not `WAITING`; `write_report` keeps the first one on disk forever. With `write=False` nothing is merged: the returned seed is the current reading's, not the frozen record (the script prints `--no-write` output as a reading only).
- Rows: one per gate × reason × population (live first, then train; gates `rs`, `risk_cap`, `no_qualifying_target`, `compression`; reasons sorted), each `gate` equal to its cell's key. `risk_cap` rows: `over_cap = True`, `dollar_risk` = mean over filled rows. Near-miss split only for gates in `NEAR_MISS_BANDS` (`|margin| <= band`); other gates carry `None` in the four split fields. `taken_realised_exp_r` is printed beside the re-walk, never compared.
- `train_rows=None` loads `default_train_paths()`; `live_blocked` and `live_taken` are given together or loaded together through `load_live()`.

- [ ] **Step 1: Write the failing report tests**

Create `tests/analytics/test_gate_counterfactual_report.py`:

```python
"""v147 V147-15: build_report -- cells, rows, the frozen verdict of record, the v150 shape."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from swingbot.core.analytics import gate_counterfactual_inputs as gci
from swingbot.core.analytics import gate_counterfactual_report as gcr
from swingbot.core.backtesting.blocked_recorder import gate_row
from swingbot.core.infra import gate_counterfactual_store as store
from swingbot.core.market.strategy_types import COMPRESSION_SHORT

CELL_KEYS = {"gate", "population", "verdict", "n", "verdict_of_record", "latest", "in_sample", "note"}
ROW_KEYS = {"gate", "reason", "population", "blocked_n", "no_plan_n", "fill_rate", "blocked_exp_r",
            "blocked_win_rate", "taken_exp_r", "taken_win_rate", "near_miss_n", "near_miss_exp_r",
            "rest_n", "rest_exp_r", "dollar_risk", "over_cap", "in_sample"}


@pytest.fixture(autouse=True)
def _fast_bootstrap(monkeypatch):
    monkeypatch.setattr(gcr, "BOOTSTRAP_RESAMPLES", 300)


def _row(arm="blocked", *, i=0, gate="rs", reason="rs_blocked", r=0.5, status="filled", population="live",
         source="strategy", direction="bearish", strategy="Fibonacci", margin=None, loss=None, start="2026-10-05"):
    day = (dt.date.fromisoformat(start) + dt.timedelta(weeks=i)).isoformat()
    filled = status == "filled"
    return gate_row(population=population, arm=arm, source=source, ticker=f"T{i}", strategy=strategy,
                    horizon="2w", direction=direction, signal_date=day, gate=gate,
                    reason=reason if arm == "blocked" else None, margin=margin, cf_status=status,
                    cf_r=r if filled else None, win=(r > 0) if filled else None,
                    planned_loss_pct=loss, expiry_bars=5, in_sample=gate == "compression" and population == "train")


def _arm(arm, rs, **kw):
    return [_row(arm, i=i, r=r, **kw) for i, r in enumerate(rs)]


def _cell(result, gate, population):
    (cell,) = [c for c in result["cells"] if (c["gate"], c["population"]) == (gate, population)]
    return cell


def _build(rows, **kw):
    return gcr.build_report(train_rows=[r for r in rows if r["population"] == "train"],
                            live_blocked=[r for r in rows if r["population"] == "live" and r["arm"] == "blocked"],
                            live_taken=[r for r in rows if r["population"] == "live" and r["arm"] == "taken"],
                            write=False, **kw)


def test_the_report_has_v150s_shape_and_is_json_serialisable():
    result = _build(_arm("blocked", [0.5, -1.0]) + _arm("taken", [1.0]))
    assert {"generated_at", "live_window", "cells", "rows"} <= set(result)
    assert all(CELL_KEYS <= set(cell) for cell in result["cells"])
    assert all(ROW_KEYS <= set(row) for row in result["rows"])
    json.dumps(result)


def test_five_verdict_cells_then_three_note_cells():
    result = _build([])
    assert [(c["gate"], c["population"]) for c in result["cells"]] == [
        ("rs", "live"), ("risk_cap", "live"), ("compression", "live"), ("risk_cap", "train"),
        ("compression", "train"), ("rs", "train"), ("no_qualifying_target", "live"),
        ("no_qualifying_target", "train")]
    notes = {(c["gate"], c["population"]): c["note"] for c in result["cells"][5:]}
    assert notes == {("rs", "train"): "no TRAIN population",
                     ("no_qualifying_target", "live"): "no verdict — no-plan",
                     ("no_qualifying_target", "train"): "no verdict — no-plan"}
    assert result["bh_family"] == 5 and result["seed"] == 42


def test_waiting_below_thirty_distinct_filled_blocked_setups():
    cell = _cell(_build(_arm("blocked", [-1.0] * 29) + _arm("taken", [1.0] * 40)), "rs", "live")
    assert (cell["verdict"], cell["n"], cell["latest"], cell["verdict_of_record"], cell["note"]) == \
        ("WAITING", 29, None, None, None)


def test_a_reading_at_the_floor_seeds_the_verdict_of_record():
    result = _build(_arm("blocked", [-1.0, -0.5] * 20) + _arm("taken", [1.0, 0.5] * 20), today="2026-12-04")
    cell = _cell(result, "rs", "live")
    assert cell["verdict"] == "GATE EARNS" and cell["n"] == 40 and cell["taken_n"] == 40
    assert cell["verdict_of_record"] == {"verdict": "GATE EARNS", "date": "2026-12-04", "n": 40}
    assert cell["latest"]["ci_high"] < 0 and cell["latest"]["q"] < 0.10


def test_the_first_reading_stays_the_verdict_of_record(tmp_path):
    path = tmp_path / "reports" / "gate-counterfactual.json"
    first = _arm("blocked", [-1.0, -0.5] * 20) + _arm("taken", [1.0, 0.5] * 20)
    gcr.build_report(train_rows=[], live_blocked=first[:40], live_taken=first[40:], today="2026-12-04",
                     path=path)
    later = _arm("blocked", [1.0, -1.0] * 30) + _arm("taken", [-1.0, 1.0] * 30)
    result = gcr.build_report(train_rows=[], live_blocked=later[:60], live_taken=later[60:],
                              today="2027-01-08", path=path)
    cell = _cell(result, "rs", "live")
    assert (cell["verdict"], cell["n"]) == ("INCONCLUSIVE", 60)
    assert cell["verdict_of_record"] == {"verdict": "GATE EARNS", "date": "2026-12-04", "n": 40}


def test_build_report_writes_the_file_load_report_reads_back_unchanged(tmp_path):
    path = tmp_path / "reports" / "gate-counterfactual.json"
    assert gcr.load_report(path) is None
    assert gcr.load_report is store.load_report                 # one loader, re-exported for v150
    rows = _arm("blocked", [0.5, -1.0]) + _arm("taken", [1.0])
    result = gcr.build_report(train_rows=[], live_blocked=rows[:2], live_taken=rows[2:], path=path)
    assert gcr.load_report(path) == result
    json.dumps(gcr.load_report(path))


def test_an_empty_taken_arm_gets_a_note_and_no_verdict():
    blocked = _arm("blocked", [1.0, -1.0, 0.5] * 14, gate="compression", reason="earnings_unknown",
                   population="train", strategy=COMPRESSION_SHORT)
    cell = _cell(_build(blocked), "compression", "train")
    assert cell["n"] == 42 and cell["taken_n"] == 0
    assert cell["note"] == "no TRAIN taken arm — no as-of earnings archive"
    assert (cell["verdict"], cell["latest"], cell["verdict_of_record"], cell["in_sample"]) == \
        ("WAITING", None, None, True)


def test_a_below_floor_taken_arm_gets_a_note_and_no_verdict():
    blocked = _arm("blocked", [-1.0] * 40, gate="plan_rejected", reason="risk_cap", population="train",
                   source="confluence", loss=2.5, margin=0.5)
    taken = _arm("taken", [1.0] * 10, gate="plan_rejected", population="train", source="confluence")
    cell = _cell(_build(blocked + taken), "risk_cap", "train")
    assert cell["note"] == "taken arm below the floor (10 distinct filled setups < 30)"
    assert (cell["verdict"], cell["latest"], cell["verdict_of_record"]) == ("WAITING", None, None)


def test_a_note_cell_enters_bh_as_p_one(monkeypatch):
    seen = {}
    real = gcr.family_qvalues

    def spy(pvalues):
        seen["p"] = list(pvalues)
        return real(pvalues)

    monkeypatch.setattr(gcr, "family_qvalues", spy)
    blocked = _arm("blocked", [1.0] * 40, gate="compression", reason="earnings_unknown",
                   population="train", strategy=COMPRESSION_SHORT)
    _build(blocked)
    assert seen["p"] == [None] * 5


def test_the_taken_arm_is_scoped_by_source_family_and_direction():
    blocked = _arm("blocked", [-1.0] * 3)                                  # rs, strategy, bearish
    taken = (_arm("taken", [1.0] * 2) + _arm("taken", [1.0], direction="bullish")
             + _arm("taken", [1.0], source="confluence"))
    (row,) = [r for r in _build(blocked + taken)["rows"] if r["gate"] == "rs"]
    assert row["taken_n"] == 2


def test_short_lane_blocks_are_scoped_against_confluence_taken_plans():
    blocked = _arm("blocked", [-1.0] * 2, gate="plan_rejected", reason="risk_cap", source="short_lane",
                   loss=2.4, margin=0.4)
    taken = _arm("taken", [1.0] * 3, gate="plan_rejected", source="confluence")
    (row,) = [r for r in _build(blocked + taken)["rows"] if r["gate"] == "risk_cap"]
    assert row["taken_n"] == 3


def test_the_compression_taken_arm_is_compression_short_only():
    blocked = _arm("blocked", [-1.0] * 2, gate="compression", reason="no_mode", strategy=COMPRESSION_SHORT)
    taken = (_arm("taken", [1.0] * 2, gate="compression", strategy=COMPRESSION_SHORT)
             + _arm("taken", [1.0] * 5, gate="compression", strategy="RSI"))
    (row,) = [r for r in _build(blocked + taken)["rows"] if r["gate"] == "compression"]
    assert row["taken_n"] == 2


def test_risk_cap_rows_are_over_cap_with_a_dollar_risk_column_and_a_near_miss_split():
    blocked = [_row(i=0, gate="plan_rejected", reason="risk_cap", source="confluence", r=-1.0, loss=2.4, margin=0.4),
               _row(i=1, gate="plan_rejected", reason="risk_cap", source="confluence", r=1.0, loss=3.0, margin=1.0),
               _row(i=2, gate="plan_rejected", reason="risk_cap", source="confluence", status="no-fill",
                    loss=2.2, margin=0.2)]
    (row,) = [r for r in _build(blocked)["rows"] if r["gate"] == "risk_cap"]
    assert row["over_cap"] is True and row["reason"] == "risk_cap"
    assert row["dollar_risk"] == pytest.approx((-1.0 * 2.4 / 2.0 + 1.0 * 3.0 / 2.0) / 2)
    assert (row["near_miss_n"], row["near_miss_exp_r"], row["rest_n"], row["rest_exp_r"]) == \
        (2, pytest.approx(-1.0), 1, pytest.approx(1.0))
    assert row["fill_rate"] == pytest.approx(2 / 3) and row["blocked_n"] == 3


def test_compression_rows_are_unsplit_one_per_reason_and_in_sample_on_train():
    blocked = (_arm("blocked", [1.0] * 2, gate="compression", reason="earnings_unknown",
                    population="train", strategy=COMPRESSION_SHORT)
               + [_row(i=9, gate="compression", reason="mode_not_allowed", population="train",
                       strategy=COMPRESSION_SHORT)])
    rows = [r for r in _build(blocked)["rows"] if r["gate"] == "compression"]
    assert [r["reason"] for r in rows] == ["earnings_unknown", "mode_not_allowed"]
    assert all(r["in_sample"] and r["near_miss_n"] is None and r["rest_exp_r"] is None for r in rows)
    assert all(r["over_cap"] is False and r["dollar_risk"] is None for r in rows)


def test_no_qualifying_target_rows_are_no_plan_counts_without_an_exp_r():
    blocked = _arm("blocked", [0.0] * 3, gate="plan_rejected", reason="no_qualifying_target",
                   source="confluence", status="no-plan")
    (row,) = [r for r in _build(blocked)["rows"] if r["gate"] == "no_qualifying_target"]
    assert (row["blocked_n"], row["no_plan_n"], row["blocked_exp_r"], row["fill_rate"]) == (3, 3, None, None)
    assert _cell(_build(blocked), "no_qualifying_target", "live")["note"] == "no verdict — no-plan"


def test_live_and_train_are_never_pooled():
    live = _arm("blocked", [1.0] * 3, gate="plan_rejected", reason="risk_cap", source="confluence", loss=2.5)
    train = _arm("blocked", [-1.0] * 5, gate="plan_rejected", reason="risk_cap", source="confluence",
                 loss=2.5, population="train")
    rows = {r["population"]: r for r in _build(live + train)["rows"] if r["gate"] == "risk_cap"}
    assert (rows["live"]["blocked_n"], rows["live"]["blocked_exp_r"]) == (3, pytest.approx(1.0))
    assert (rows["train"]["blocked_n"], rows["train"]["blocked_exp_r"]) == (5, pytest.approx(-1.0))


def test_realised_r_rides_beside_the_rewalk_and_is_never_the_taken_exp_r():
    taken = _arm("taken", [1.0, 1.0])
    for row, realised in zip(taken, (0.2, None)):
        row["realised_r"] = realised
    (row,) = [r for r in _build(_arm("blocked", [-1.0]) + taken)["rows"] if r["gate"] == "rs"]
    assert row["taken_exp_r"] == pytest.approx(1.0) and row["taken_realised_exp_r"] == pytest.approx(0.2)


def test_the_live_window_is_recorded_as_seen():
    assert _build([])["live_window"] is None
    train = _row(i=50, gate="plan_rejected", reason="risk_cap", source="confluence", population="train")
    result = _build(_arm("blocked", [1.0] * 3) + [train])
    assert result["live_window"] == "2026-10-05..2026-10-19"


def test_the_limitations_state_the_gap_floor_and_the_portfolio_state():
    text = " ".join(_build([])["limitations"])
    assert "-1.0R" in text and "understated" in text
    assert "heat" in text and "holdout" in text and "in-sample" in text


def test_defaults_load_the_train_files_and_the_live_table(monkeypatch):
    calls = []
    monkeypatch.setattr(gci, "default_train_paths", lambda: ["a.jsonl"])
    monkeypatch.setattr(gci, "load_train_rows", lambda paths: calls.append(("train", paths)) or [])
    monkeypatch.setattr(gci, "load_live", lambda **kw: calls.append(("live",)) or ([], []))
    gcr.build_report(write=False)
    assert calls == [("train", ["a.jsonl"]), ("live",)]
```

- [ ] **Step 2: Write the failing script tests**

Create `tests/scripts/test_gate_counterfactual_report_script.py`:

```python
"""v147 V147-15: scripts/reports/gate_counterfactual_report.py stays a thin wrapper over build_report."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.analytics import gate_counterfactual_report as gcr
from swingbot.core.backtesting.blocked_recorder import gate_row, write_gate_rows

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("gcr_script", ROOT / "scripts" / "reports" / "gate_counterfactual_report.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(gcr, "BOOTSTRAP_RESAMPLES", 200)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))


def _train_file(tmp_path) -> Path:
    rows = [gate_row(population="train", arm="blocked", source="confluence", ticker=f"T{i}", strategy="Fibonacci",
                     horizon="2w", direction="bullish", signal_date=f"2021-03-{i + 1:02d}", gate="plan_rejected",
                     reason="risk_cap", margin=0.3, cf_status="filled", cf_r=-1.0, win=False,
                     planned_loss_pct=2.3, expiry_bars=0)
            for i in range(3)]
    path = tmp_path / "v147-blocked-confluence.jsonl"
    write_gate_rows(rows, path)
    return path


def test_a_train_only_reading_prints_cells_rows_and_limitations_without_writing(tmp_path, capsys):
    out = tmp_path / "out.json"
    code = script.main(["--train", str(_train_file(tmp_path)), "--no-live", "--no-write", "--json", str(out)])
    printed = capsys.readouterr().out
    assert code == 0
    assert "WAITING (3/30" in printed and "no TRAIN population" in printed
    assert "over-cap" in printed and "-1.0R" in printed
    assert "reading only" in printed                             # --no-write is never a verdict of record
    assert json.loads(out.read_text(encoding="utf-8"))["cells"]
    assert gcr.load_report() is None                             # nothing written


def test_a_written_run_persists_what_load_report_reads(tmp_path, capsys):
    assert script.main(["--train", str(_train_file(tmp_path)), "--no-live"]) == 0
    loaded = gcr.load_report()
    assert loaded is not None and [r["population"] for r in loaded["rows"]] == ["train"]


def test_a_verdict_line_shows_the_reading_and_the_record():
    cell = {"gate": "risk_cap", "population": "train", "verdict": "GATE COSTS", "n": 41, "note": None,
            "in_sample": False, "latest": {"difference": 0.21, "ci_low": 0.05, "ci_high": 0.4, "q": 0.03, "p": 0.006},
            "verdict_of_record": {"verdict": "GATE COSTS", "date": "2026-12-04", "n": 31}}
    (line,) = script.cell_lines({"cells": [cell]})[1:]
    assert "GATE COSTS" in line and "n=41" in line and "+0.21" in line and "q=0.030" in line
    assert "of record: GATE COSTS (2026-12-04, n=31)" in line
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_gate_counterfactual_report.py tests/scripts/test_gate_counterfactual_report_script.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'build_report'` and `FileNotFoundError` for the script.

- [ ] **Step 4: Add `build_report` to the module**

In `swingbot/core/analytics/gate_counterfactual_report.py`, extend the import block (after `from swingbot.core.backtesting.instrument import stats`):

```python
from swingbot.core.analytics import gate_counterfactual_inputs as inputs
from swingbot.core.infra import gate_counterfactual_store as store
from swingbot.core.infra.gate_counterfactual_store import load_report  # noqa: F401  -- re-export for v150
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
```

and update the module docstring's last sentence to: "`build_report` writes through the light `swingbot.core.infra.gate_counterfactual_store` (atomic `os.replace` lives there); `load_report` is that module's, re-exported." Then append to the end of the module:

```python
# --- V147-15: the report -------------------------------------------------------------

NOTE_NO_TRAIN_RS = "no TRAIN population"
NOTE_NO_PLAN = "no verdict — no-plan"
NOTE_CELLS = (("rs", "train", NOTE_NO_TRAIN_RS), ("no_qualifying_target", "live", NOTE_NO_PLAN),
              ("no_qualifying_target", "train", NOTE_NO_PLAN))
EMPTY_TAKEN_NOTES = {("compression", "train"): "no TRAIN taken arm — no as-of earnings archive"}
IN_SAMPLE_CELLS = frozenset({("compression", "train")})
ROW_GATES = ("rs", "risk_cap", "no_qualifying_target", "compression")
SOURCE_FAMILY = {"strategy": "strategy", "confluence": "confluence", "short_lane": "confluence"}
LIMITATIONS = (
    "Portfolio state: every blocked candidate is simulated as a lone trade; the portfolio heat and "
    "correlated-cluster caps are ignored, and heat at block time is not stored (null).",
    "Gap floor: simulate_exit books a stop at the stop price, so a gap through the stop reads -1.0R; "
    "counterfactual losses on gaps are understated, so the blocked arm's losses are understated.",
    "R is per-trade risk-normalised (every trade sized to 1R). risk_cap rows add dollar_risk -- the "
    "outcome in units of the 2% dollar cap -- and are over-cap: never a tradable alternative.",
    "TRAIN compression is in-sample (v119 fitted the gate on TRAIN); TRAIN has no as-of earnings "
    "archive, so its taken arm is expected to be empty and the cell carries a note, not a verdict.",
    "Live rows from 2026-10 sit inside the 2026 holdout; a follow-on screen built on a live verdict "
    "must name a holdout this report has not seen.",
    "Short-lane blocked rows are scoped against confluence taken plans (issued plans carry no lane "
    "marker); live taken plans store no signal-day close, so their re-walk is never re-anchored.",
    "A verdict changes nothing: GATE COSTS licenses one Stage -2 screen under a new idea name (for "
    "risk_cap, with the partner); no closed pre-registration is reopened.",
)


def _blocked_rows(rows, key: str, population: str) -> list:
    return [r for r in rows
            if r["population"] == population and r["arm"] == "blocked" and cell_key(r) == key]


def _taken_match(row, key: str, population: str, scope: set) -> bool:
    if row["population"] != population or row["arm"] != "taken" or row["gate"] != CELL_GATE[key]:
        return False
    if key == "compression" and row["strategy"] != COMPRESSION_SHORT:
        return False
    return (SOURCE_FAMILY[row["source"]], row["direction"]) in scope


def _arms(rows, key: str, population: str) -> tuple[list, list]:
    """(blocked, taken) distinct setups of one cell, the taken arm in the blocked arm's scope."""
    blocked = distinct_setups(_blocked_rows(rows, key, population))
    scope = {(SOURCE_FAMILY[r["source"]], r["direction"]) for r in blocked}
    taken = distinct_setups([r for r in rows if _taken_match(r, key, population, scope)])
    return blocked, taken


def _note_for(key: str, population: str, n: int, taken_n: int) -> str | None:
    if n < VERDICT_FLOOR:
        return None
    if taken_n == 0:
        return EMPTY_TAKEN_NOTES.get((key, population), f"no {population.upper()} taken arm")
    if taken_n < VERDICT_FLOOR:
        return f"taken arm below the floor ({taken_n} distinct filled setups < {VERDICT_FLOOR})"
    return None


def _evaluate(rows, key: str, population: str) -> dict:
    blocked, taken = _arms(rows, key, population)
    n, taken_n = len(_filled(blocked)), len(_filled(taken))
    note = _note_for(key, population, n, taken_n)
    eligible = note is None and n >= VERDICT_FLOOR
    return {"gate": key, "population": population, "n": n, "taken_n": taken_n, "note": note,
            "reading": difference_reading(blocked, taken) if eligible else None}


def _cell(state: dict, q, today: str) -> dict:
    """One verdict cell (v150 shape); the record is seeded here and frozen by the store."""
    reading = state["reading"]
    verdict = WAITING if state["note"] else classify(reading, q, state["n"])
    latest = None if reading is None else {"difference": reading["difference"], "ci_low": reading["ci_low"],
                                           "ci_high": reading["ci_high"], "q": q, "p": reading["p"]}
    record = None if verdict == WAITING else {"verdict": verdict, "date": today, "n": state["n"]}
    return {"gate": state["gate"], "population": state["population"], "verdict": verdict, "n": state["n"],
            "taken_n": state["taken_n"], "verdict_of_record": record, "latest": latest,
            "in_sample": (state["gate"], state["population"]) in IN_SAMPLE_CELLS, "note": state["note"]}


def _note_cell(key: str, population: str, note: str) -> dict:
    return {"gate": key, "population": population, "verdict": WAITING, "n": 0, "taken_n": 0,
            "verdict_of_record": None, "latest": None, "in_sample": False, "note": note}


def _cells(rows, today: str) -> list[dict]:
    states = [_evaluate(rows, key, population) for key, population in CELLS]
    qvalues = family_qvalues([s["reading"]["p"] if s["reading"] else None for s in states])
    cells = [_cell(state, q, today) for state, q in zip(states, qvalues)]
    return cells + [_note_cell(key, population, note) for key, population, note in NOTE_CELLS]


def _near_miss(key: str, blocked) -> dict:
    band = NEAR_MISS_BANDS.get(key)
    if band is None:
        return {"near_miss_n": None, "near_miss_exp_r": None, "rest_n": None, "rest_exp_r": None}
    inside = [r["margin"] is not None and abs(r["margin"]) <= band for r in blocked]
    near = [r for r, flag in zip(blocked, inside) if flag]
    rest = [r for r, flag in zip(blocked, inside) if not flag]
    return {"near_miss_n": len(near), "near_miss_exp_r": arm_stats(near)["exp_r"],
            "rest_n": len(rest), "rest_exp_r": arm_stats(rest)["exp_r"]}


def _dollar_risk(key: str, blocked) -> float | None:
    if key != "risk_cap":
        return None
    return _mean(r["dollar_risk"] for r in _filled(blocked) if r.get("dollar_risk") is not None)


def _row(key: str, reason, population: str, blocked, taken) -> dict:
    """One detail row: gate x reason x population (v150 shape)."""
    b, t = arm_stats(blocked), arm_stats(taken)
    return {"gate": key, "reason": reason, "population": population,
            "blocked_n": b["n"], "no_plan_n": b["no_plan_n"], "fill_rate": b["fill_rate"],
            "blocked_exp_r": b["exp_r"], "blocked_win_rate": b["win_rate"],
            "taken_n": t["filled_n"], "taken_exp_r": t["exp_r"], "taken_win_rate": t["win_rate"],
            "taken_realised_exp_r": _mean(r["realised_r"] for r in taken if r.get("realised_r") is not None),
            **_near_miss(key, blocked), "dollar_risk": _dollar_risk(key, blocked),
            "over_cap": key == "risk_cap", "in_sample": (key, population) in IN_SAMPLE_CELLS}


def _rows_for(rows, key: str, population: str) -> list[dict]:
    blocked, taken = _arms(rows, key, population)
    by_reason = defaultdict(list)
    for row in blocked:
        by_reason[row["reason"]].append(row)
    return [_row(key, reason, population, members, taken)
            for reason, members in sorted(by_reason.items(), key=lambda item: str(item[0]))]


def _report_rows(rows) -> list[dict]:
    return [row for population in ("live", "train") for key in ROW_GATES
            for row in _rows_for(rows, key, population)]


def _live_window(rows) -> str | None:
    dates = sorted(r["signal_date"] for r in rows if r["population"] == "live")
    return f"{dates[0]}..{dates[-1]}" if dates else None


def build_report(*, train_rows=None, live_blocked=None, live_taken=None, today=None, write=True,
                 path=None) -> dict:
    """The gate-counterfactual report (v150 shape); written through the light store unless write=False."""
    if train_rows is None:
        train_rows = inputs.load_train_rows(inputs.default_train_paths())
    if live_blocked is None or live_taken is None:
        live_blocked, live_taken = inputs.load_live()
    rows = [*train_rows, *live_blocked, *live_taken]
    now = dt.datetime.now(dt.timezone.utc)
    today = today or now.date().isoformat()
    result = {"generated_at": now.isoformat(timespec="seconds"), "live_window": _live_window(rows),
              "bh_family": len(CELLS), "seed": BOOTSTRAP_SEED, "limitations": list(LIMITATIONS),
              "cells": _cells(rows, today), "rows": _report_rows(rows)}
    return store.write_report(result, path) if write else result
```

- [ ] **Step 5: Write the script**

Create `scripts/reports/gate_counterfactual_report.py`:

```python
"""v147: print the gate-counterfactual report and persist it to data/reports/gate-counterfactual.json.

A thin wrapper: every figure comes from
swingbot.core.analytics.gate_counterfactual_report.build_report().

Run on production (the live table and the market_data/ cache live there):
    python scripts/reports/gate_counterfactual_report.py
TRAIN only, nothing written (a reading, never a verdict of record):
    python scripts/reports/gate_counterfactual_report.py --train logs/v147-blocked-confluence.jsonl \
        logs/v147-blocked-compression.jsonl --no-live --no-write --json logs/v147-train-report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.analytics import gate_counterfactual_inputs as inputs  # noqa: E402
from swingbot.core.analytics import gate_counterfactual_report as report  # noqa: E402


def _num(value, spec: str = "+.2f") -> str:
    return "-" if value is None else format(value, spec)


def _cell_line(cell: dict) -> str:
    head = f"  {cell['gate']:<22}{cell['population']:<6}"
    if cell["note"]:
        return f"{head}{cell['note']}"
    if cell["verdict"] == report.WAITING:
        return f"{head}WAITING ({cell['n']}/{report.VERDICT_FLOOR} distinct filled setups)"
    latest, record = cell["latest"], cell["verdict_of_record"] or {}
    tag = " [in-sample]" if cell["in_sample"] else ""
    return (f"{head}{cell['verdict']}{tag} n={cell['n']} diff={_num(latest['difference'])} "
            f"CI=[{_num(latest['ci_low'])}, {_num(latest['ci_high'])}] q={_num(latest['q'], '.3f')} | "
            f"of record: {record.get('verdict')} ({record.get('date')}, n={record.get('n')})")


def cell_lines(result: dict) -> list[str]:
    return ["Verdicts -- blocked ExpR - taken ExpR, gate x population, never pooled:"] + \
        [_cell_line(cell) for cell in result["cells"]]


ROW_HEADER = (f"  {'gate':<22}{'reason':<24}{'pop':<6}{'N':>5}{'noplan':>7}{'fill':>6}{'blkExpR':>9}"
              f"{'blkWR':>7}{'tknExpR':>9}{'tknWR':>7}{'nearN':>6}{'nearExpR':>9}{'$risk':>7}  labels")


def _row_line(row: dict) -> str:
    labels = [name for name, on in (("over-cap", row["over_cap"]), ("in-sample", row["in_sample"])) if on]
    return (f"  {row['gate']:<22}{str(row['reason']):<24}{row['population']:<6}{row['blocked_n']:>5}"
            f"{row['no_plan_n']:>7}{_num(row['fill_rate'], '.0%'):>6}{_num(row['blocked_exp_r']):>9}"
            f"{_num(row['blocked_win_rate'], '.0%'):>7}{_num(row['taken_exp_r']):>9}"
            f"{_num(row['taken_win_rate'], '.0%'):>7}{_num(row['near_miss_n'], 'd'):>6}"
            f"{_num(row['near_miss_exp_r']):>9}{_num(row['dollar_risk']):>7}  {' '.join(labels)}")


def row_lines(result: dict) -> list[str]:
    return ["Rows -- gate x reason x population (R per trade; $risk in units of the 2% cap):", ROW_HEADER] + \
        [_row_line(row) for row in result["rows"]]


def _parse(argv):
    parser = argparse.ArgumentParser(description="v147 gate-counterfactual report")
    parser.add_argument("--train", nargs="*", type=Path, default=None,
                        help="TRAIN gate-row JSONL files (default: logs/ and data/reports/inputs/)")
    parser.add_argument("--no-live", action="store_true", help="leave the live table out")
    parser.add_argument("--no-write", action="store_true", help="print a reading; write nothing")
    parser.add_argument("--json", type=Path, default=None, help="also dump the result to this path")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    train = None if args.train is None else inputs.load_train_rows(args.train)
    live = ([], []) if args.no_live else (None, None)
    result = report.build_report(train_rows=train, live_blocked=live[0], live_taken=live[1],
                                 write=not args.no_write)
    status = "reading only (--no-write): not a verdict of record" if args.no_write else "written"
    print(f"gate counterfactual {result['generated_at']}  live window {result['live_window']}  [{status}]")
    for line in cell_lines(result) + [""] + row_lines(result) + ["", "Limitations:"]:
        print(line)
    for text in result["limitations"]:
        print(f"  - {text}")
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/analytics/test_gate_counterfactual_report.py tests/scripts/test_gate_counterfactual_report_script.py tests/analytics/test_gate_counterfactual_stats.py tests/analytics/test_gate_counterfactual_inputs.py tests/infra/test_gate_counterfactual_store.py`
Expected: PASS, `0 failed`.

- [ ] **Step 7: Complexity and syntax**

Run: `python -m radon cc -s -n C swingbot/core/analytics/gate_counterfactual_report.py scripts/reports/gate_counterfactual_report.py && python -m py_compile swingbot/core/analytics/gate_counterfactual_report.py scripts/reports/gate_counterfactual_report.py`
Expected: no radon output, no error.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/analytics/gate_counterfactual_report.py scripts/reports/gate_counterfactual_report.py tests/analytics/test_gate_counterfactual_report.py tests/scripts/test_gate_counterfactual_report_script.py
git commit -m "feat(v147): gate-counterfactual build_report, v150 shape, script wrapper (V147-15)"
```

# Phase 6: Operations and close

### Task V147-16: Production progress script + weekly cron installer

**Model:** sonnet — a read-only count script and a cron installer copied from an existing idempotent pattern; no statistics of its own.

**Files:**
- Create: `scripts/ops/gate_counterfactual_progress.py`
- Create: `scripts/ops/install_gate_counterfactual_cron.sh`
- Create: `tests/scripts/test_gate_counterfactual_progress.py`

**Interfaces:**
- Consumes: `gate_rejections_repo().list_since(None)` (V147-7); `gate_counterfactual_inputs.live_blocked_rows(records)` (V147-14); `gate_counterfactual_report.cell_key`, `distinct_setups`, `VERDICT_FLOOR` (V147-13). Pattern: `scripts/ops/install_intraday_coverage_cron.sh` (exists; marker line, `grep -vF` replace, `crontab -`).
- Produces (ledger): `progress_lines(records) -> list[str]`; `main() -> int` (1 when the table cannot be read).

**What it prints:** the row count and signal-date span; per cell (`rs`, `risk_cap`, `compression`, then `no_qualifying_target`) the count per `cf_status` and, for the three live verdict cells, distinct filled setups against 30 (`READY` at or past it); a last line saying whether every live verdict cell is past the floor. It reads, counts and prints; it never writes, resolves or deletes. The cron runs it every Saturday 07:30 UTC and appends to `/opt/swing-bot/logs/gate-counterfactual.log`. **The installer runs only after the v147 deploy, at close-out** (V147-18 lists it); this task does not touch the VM.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_gate_counterfactual_progress.py`:

```python
"""v147 V147-16: the read-only production progress check and its idempotent cron installer."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("gcp", ROOT / "scripts" / "ops" / "gate_counterfactual_progress.py")
gcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gcp)
INSTALLER = ROOT / "scripts" / "ops" / "install_gate_counterfactual_cron.sh"


def _record(i=0, *, gate="rs", reason="rs_blocked", status="filled", day=None):
    filled = status == "filled"
    return {"id": i, "ticker": f"T{i}", "gate": gate, "reason": reason, "strategy": "Fibonacci",
            "horizon": "2w", "direction": "bearish", "source": "strategy",
            "signal_date": day or f"2026-10-{5 + (i % 20):02d}", "cf_status": status, "margin": None,
            "plan": None, "cf_r": 0.5 if filled else None, "win": True if filled else None}


def test_counts_per_cell_and_status_with_distinct_filled_against_the_floor():
    records = ([_record(i) for i in range(31)] + [_record(100 + i, status="pending") for i in range(2)]
               + [_record(200 + i, gate="plan_rejected", reason="risk_cap") for i in range(3)]
               + [_record(300 + i, gate="plan_rejected", reason="no_qualifying_target", status="no-plan")
                  for i in range(2)])
    lines = gcp.progress_lines(records)
    text = "\n".join(lines)
    assert lines[0].startswith("gate_rejections: 38 rows")
    (rs,) = [l for l in lines if l.strip().startswith("rs ")]
    assert "pending=2" in rs and "filled=31" in rs and "distinct filled 31/30 READY" in rs
    (cap,) = [l for l in lines if l.strip().startswith("risk_cap ")]
    assert "filled=3" in cap and "distinct filled 3/30" in cap and "READY" not in cap
    assert "compression" in text and "no_qualifying_target" in text
    assert lines[-1] == "ALL LIVE VERDICT CELLS PAST THE FLOOR: no"


def test_consecutive_day_reblocks_count_once():
    records = [_record(0, day=f"2026-10-0{d}") for d in (5, 6, 7)]
    records = [dict(r, ticker="AAPL") for r in records]
    (rs,) = [l for l in gcp.progress_lines(records) if l.strip().startswith("rs ")]
    assert "filled=3" in rs and "distinct filled 1/30" in rs


def test_every_live_cell_past_the_floor_says_so():
    records = [_record(i, gate=g, reason=r) for g, r in (("rs", "rs_blocked"), ("plan_rejected", "risk_cap"),
                                                        ("compression", "earnings_unknown"))
               for i in range(30)]
    records = [dict(r, ticker=f"{r['gate']}-{r['id']}") for r in records]
    assert gcp.progress_lines(records)[-1].startswith("ALL LIVE VERDICT CELLS PAST THE FLOOR: yes")


def test_an_empty_table_prints_zero_rows():
    lines = gcp.progress_lines([])
    assert lines[0] == "gate_rejections: 0 rows"
    assert lines[-1] == "ALL LIVE VERDICT CELLS PAST THE FLOOR: no"


def test_an_unreadable_table_exits_one(monkeypatch, capsys):
    from swingbot.core.db.repositories import gate_rejections

    class _Down:
        def list_since(self, since=None, *, conn=None):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(gate_rejections, "gate_rejections_repo", lambda: _Down())
    assert gcp.main() == 1
    assert "unreadable" in capsys.readouterr().out


def test_the_installer_follows_the_idempotent_pattern():
    text = INSTALLER.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash") and "set -euo pipefail" in text
    assert "scripts/ops/gate_counterfactual_progress.py" in text
    assert "/opt/swing-bot/logs/gate-counterfactual.log" in text
    assert "30 7 * * 6 " in text                                  # weekly, Saturday 07:30 UTC
    assert 'grep -vF "$MARKER"' in text


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX bash")
def test_the_installer_is_idempotent_against_a_fake_crontab(tmp_path):
    store, bindir = tmp_path / "crontab.txt", tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "crontab"
    fake.write_text('#!/usr/bin/env bash\n'
                    'if [ "$1" = "-l" ]; then [ -f "$FAKE_CRONTAB" ] && cat "$FAKE_CRONTAB" || exit 1;\n'
                    'elif [ "$1" = "-" ]; then cat > "$FAKE_CRONTAB"; fi\n', encoding="utf-8")
    fake.chmod(0o755)
    store.write_text("0 1 * * * echo keep-me\n", encoding="utf-8")
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "FAKE_CRONTAB": str(store)}
    for _ in range(2):
        done = subprocess.run(["bash", str(INSTALLER)], env=env, capture_output=True, text=True, timeout=30)
        assert done.returncode == 0, done.stderr
    lines = store.read_text(encoding="utf-8").splitlines()
    assert "0 1 * * * echo keep-me" in lines
    assert sum("gate_counterfactual_progress.py" in line for line in lines) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_gate_counterfactual_progress.py`
Expected: FAIL — `FileNotFoundError` for `scripts/ops/gate_counterfactual_progress.py`.

- [ ] **Step 3: Write the progress script**

Create `scripts/ops/gate_counterfactual_progress.py`:

```python
#!/usr/bin/env python3
"""v147: how far is each live gate-counterfactual cell from its verdict floor?

Read-only. Counts `gate_rejections` rows per cell x cf_status and the distinct
filled setups of each live verdict cell against the floor (30). Installed
weekly on the VM by install_gate_counterfactual_cron.sh; it decides nothing,
resolves nothing and removes nothing. When every live cell is past the floor,
the next Claude session runs scripts/reports/gate_counterfactual_report.py
and records the reading.

    docker compose exec -T bot python scripts/ops/gate_counterfactual_progress.py
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.analytics.gate_counterfactual_inputs import live_blocked_rows  # noqa: E402
from swingbot.core.analytics.gate_counterfactual_report import (  # noqa: E402
    VERDICT_FLOOR, cell_key, distinct_setups)

LIVE_CELLS = ("rs", "risk_cap", "compression")
STATUSES = ("pending", "filled", "no-fill", "no-plan", "no-data")


def _span(records) -> str:
    dates = sorted(str(r.get("signal_date")) for r in records if r.get("signal_date"))
    return f", signal dates {dates[0]}..{dates[-1]}" if dates else ""


def _cell_line(key: str, counts: Counter, filled: int | None) -> str:
    statuses = " ".join(f"{status}={counts[status]}" for status in STATUSES)
    if filled is None:
        return f"  {key:<22}{statuses}  (no-plan: no verdict)"
    ready = " READY" if filled >= VERDICT_FLOOR else ""
    return f"  {key:<22}{statuses}  distinct filled {filled}/{VERDICT_FLOOR}{ready}"


def progress_lines(records) -> list[str]:
    """Plain-text progress of every cell toward its verdict floor."""
    records = list(records)
    counts = defaultdict(Counter)
    for record in records:
        counts[cell_key(record)][record.get("cf_status")] += 1
    filled = Counter(cell_key(row) for row in distinct_setups(live_blocked_rows(records))
                     if row["cf_status"] == "filled")
    lines = [f"gate_rejections: {len(records)} rows{_span(records)}"]
    lines += [_cell_line(key, counts[key], filled[key]) for key in LIVE_CELLS]
    lines.append(_cell_line("no_qualifying_target", counts["no_qualifying_target"], None))
    ready = all(filled[key] >= VERDICT_FLOOR for key in LIVE_CELLS)
    lines.append("ALL LIVE VERDICT CELLS PAST THE FLOOR: "
                 + ("yes -- run scripts/reports/gate_counterfactual_report.py and record it" if ready else "no"))
    return lines


def main() -> int:
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    try:
        records = gate_rejections_repo().list_since(None)
    except Exception as exc:  # a read-only check reports and exits non-zero; it never retries or repairs
        print(f"gate_rejections unreadable: {exc!r}")
        return 1
    for line in progress_lines(records):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Write the cron installer**

Create `scripts/ops/install_gate_counterfactual_cron.sh`:

```bash
#!/usr/bin/env bash
# Installs (idempotently) a weekly crontab entry on the Hetzner VM that runs
# scripts/ops/gate_counterfactual_progress.py inside the bot container and
# appends timestamped output to logs/gate-counterfactual.log.
#
# Added for plan v147 (docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_0-index.md)
# Task V147-16: the live gate-counterfactual verdicts need weeks of rows; this
# gives a progress reading every Saturday whether or not a Claude session is
# open. It reads and prints only -- it decides, resolves and removes nothing.
#
# Install AFTER the v147 deploy (close-out), ON the VM as root, e.g. from a dev machine via:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_gate_counterfactual_cron.sh
#
# Safe to re-run: it replaces any prior line this script installed rather
# than appending a duplicate.
set -euo pipefail

MARKER='# v147 gate counterfactual progress (installed by install_gate_counterfactual_cron.sh)'
CRON_LINE='30 7 * * 6 cd /opt/swing-bot && { echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ==="; /usr/bin/docker compose exec -T bot python scripts/ops/gate_counterfactual_progress.py; } >> /opt/swing-bot/logs/gate-counterfactual.log 2>&1'

{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "gate_counterfactual_progress.py" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
```

Then mark it executable in git: `git update-index --chmod=+x scripts/ops/install_gate_counterfactual_cron.sh` after `git add` (Step 7).

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_gate_counterfactual_progress.py`
Expected: PASS, `0 failed` (the fake-crontab test is skipped only on a machine without a POSIX bash).

- [ ] **Step 6: Complexity and syntax**

Run: `python -m radon cc -s -n C scripts/ops/gate_counterfactual_progress.py && python -m py_compile scripts/ops/gate_counterfactual_progress.py && bash -n scripts/ops/install_gate_counterfactual_cron.sh`
Expected: no output, no error.

- [ ] **Step 7: Commit**

```bash
git add scripts/ops/gate_counterfactual_progress.py scripts/ops/install_gate_counterfactual_cron.sh tests/scripts/test_gate_counterfactual_progress.py
git update-index --chmod=+x scripts/ops/install_gate_counterfactual_cron.sh
git commit -m "feat(v147): weekly gate-counterfactual progress check and cron installer (V147-16)"
```

