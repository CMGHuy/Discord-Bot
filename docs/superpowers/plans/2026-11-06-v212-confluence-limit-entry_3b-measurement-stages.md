# v212 — Confluence limit entry, part 3b: measurement (clauses, stages, disclosures)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v212 — Confluence limit entry partway to the support](../specs/2026-11-06-v212-confluence-limit-entry.md) (rule 6 as corrected in e5dd654f: a gap through the stop fills at the open and exits at that open, about 0R less frictions, outcome `"loss"`; the from-L reading is only the disclosed `gap_stop_r_from_limit`)
**Index:** [`2026-11-06-v212-confluence-limit-entry_0-index.md`](2026-11-06-v212-confluence-limit-entry_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.
**Brief:** `.superpowers/briefs/2026-11-06-v212-confluence-limit-entry.md`

Continuation of part 3 (`2026-11-06-v212-confluence-limit-entry_3-measurement.md`,
V212-11 .. V212-13), split off because part 3 reached the 1500-line cap.
Tasks V212-13b, V212-13c, V212-14 and V212-14b (V212-14c is in part 3c): the measure script's populations,
clauses, plateau, thin seal and portfolio pass; its Stage −1..3 chain and
ledger rows; and the disclosures module. Same worktree
(`.claude/worktrees/2026-11-06-v212-confluence-limit-entry`), same data and
windows as part 3's header. Every task's verification is the narrow run; no
task runs the full suite or reads the database.

# Phase D — measurement (continued)


### Task V212-13b: Measure script, part 2: Stage −1 census, populations, the three clauses, plateau, thin seal, portfolio pass

**Model:** opus — the pass clauses, the plateau rule, the thin seal and the portfolio pass are the pre-registration in code; an off-by-one or a wrong population changes a verdict.

**Files:**
- Modify: `scripts/backtest/measure_confluence_limit.py` (imports; `# --- census`, `# --- populations and clauses` and `# --- portfolio pass` sections between `build` and `# --- CLI`)
- Test: `tests/backtest_scripts/test_measure_confluence_limit_clauses.py`

**Interfaces:**
- Consumes: V212-13 (`FILLS_SHARE`, `WR_SLACK_PP`, `THIN_PER_DIRECTION`, `DIRECTIONS`, `CLAUSE_NAMES`); V212-11/11b row keys (`key`, `arm`, `filled`, `dropped`, `outcome`, `r_net`, `planned_rr`, `strategy`, `horizon_key`, `direction`, `ticker`, `entry_date`, `fill_date`, `exit_date`, `stop_pct`, `entry`, `stop_loss`) and `clr.CELLS`; V212-12 `portfolio_replay(..., max_position_pct, max_position_value, cluster_fn, track_keys)` and its `taken_keys`, `skip_reasons`, `notional_capped`; existing `acceptance.ArmTrade`, `CLOSED`, `expectancy_r`, `win_rate`, `correlation.cluster_exposure` / `cluster_check`, `universe.sector_map`.
- Produces (consumed by V212-13c, V212-14):
  - `stage_minus1(rows) -> dict` — the Stage −1 verdict over census rows: per cell `in_scope`, `drops` (by reason), `kept`, `observed_n` (filled kept alerts), `fill_states`, `filled_by_direction`, `d_range`; `REACHABLE` when any cell has a fill, else `refused:zero-diff`.
  - `closed(rows, arm) -> list[dict]` (filled rows of `arm` whose outcome is in `CLOSED`); `cell_keys(rows, cell) -> set[str]` (the cell's non-dropped alert keys); `reference_rows(rows, cell) -> list[dict]` (closed reference rows on those keys); `to_trade(row) -> ArmTrade` (R = `r_net`).
  - `clauses(arm_rows, ref_rows) -> dict` — keys `n`, `ref_n`, `expr`, `ref_expr`, `wr`, `ref_wr`, `expr_beats_reference`, `fills_half_of_reference`, `wr_within_2pp`, `passes`.
  - `neighbours(key) -> list[str]`; `plateau(results: dict[str, dict]) -> str | None` (each value carries `passes` and `expr`); `thin(rows) -> bool`.
  - `run_portfolio(rows, *, sectors, cluster_fn) -> tuple[list[dict], dict]` (kept rows, `portfolio_replay` result); `portfolio_pass(rows, arm, *, sectors, cluster_fn) -> list[dict]`; `make_cluster_fn(frames, sectors) -> Callable[[list, dict, float], bool]`; `load_sectors() -> dict`.

**Decisions fixed here** (spec § Pass rule, § The rule 7–8; index Global Constraints):
- **The comparison.** A cell's arm side is its filled, closed rows; its reference side is the reference rows on that cell's **non-dropped** in-scope alerts — "each cell's reference arm is that cell's own in-scope plans" (spec § The rule, Grid). Each side passes through its own portfolio pass before the clauses read it (V212-13c does this).
- **Clauses, point estimates, pooled directions:** (1) arm ExpR > reference ExpR; (2) arm trades ≥ 50% of reference trades, with a non-empty reference; (3) arm win rate ≥ reference − 2.0 pp (inclusive). ExpR and win rate are `acceptance.expectancy_r` / `win_rate` over `r_net`.
- **Plateau:** the passing cell with the highest arm ExpR whose every grid neighbour also passes; ⅓ and ⅔ have one neighbour each; a tie goes to the smaller f (`max` keeps the first).
- **Thin seal:** fewer than 30 kept arm trades in either direction.
- **Portfolio pass** (rules 7–8): signals dated at the **fill** date, so pending limits reserve nothing; caps read live config (`RISK_PER_TRADE_PCT`, `PORTFOLIO_HEAT_CAP_PCT`, `SECTOR_HEAT_CAP_PCT`, `MAX_OPEN_POSITIONS`, `MAX_POSITION_SIZE_PCT`, `MAX_POSITION_VALUE_ABSOLUTE`); `throttles=False` (drawdown throttling is not part of the rule and would tie each arm's verdict to its own equity path); cluster from `correlation.cluster_exposure` on frames cut **before** the fill bar (no lookahead).

- [ ] **Step 1: Write the failing test** `tests/backtest_scripts/test_measure_confluence_limit_clauses.py`

```python
"""V212-13b: populations, the three clauses, plateau, thin seal and the
portfolio pass of the v212 measure script. Rows are hand-built; V212-13c's
stage tests import `row` from here."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_confluence_limit as mcl  # noqa: E402

from swingbot import config
from tests.helpers import make_ohlcv


def row(arm, n, r, *, direction="bullish", year=2021, dropped=None, filled=True, ticker=None):
    """One replay row; `n` makes the alert key, so a ref and an arm row pair."""
    ticker = ticker or f"T{n:03d}"
    day = f"{year}-03-{(n % 27) + 1:02d}"
    outcome = "dropped" if dropped else ("not_triggered" if not filled else
                                         ("win" if r > 0 else "loss"))
    return {"key": f"{ticker}|4w|{day}|{direction}", "arm": arm, "ticker": ticker,
            "horizon_key": "4w", "strategy": "S/R Confluence", "direction": direction,
            "entry_date": day, "fill_date": day, "exit_date": f"{year}-04-{(n % 27) + 1:02d}",
            "filled": filled and not dropped, "dropped": dropped, "outcome": outcome,
            "r_net": r if filled and not dropped else None, "planned_rr": 2.0,
            "stop_pct": 1.5, "entry": 100.0, "stop_loss": 98.5}


def census(i, drops=None, filled=True, direction="bullish"):
    drops = drops or {}
    return {"key": f"T{i}|4w|2021-03-01|{direction}", "direction": direction, "d_pct": 2.5 + i,
            "drops": {cell: drops.get(cell) for cell in ("f0.333", "f0.5", "f0.667")},
            "fill_state": {cell: None if drops.get(cell) else ("filled" if filled else "expired")
                           for cell in ("f0.333", "f0.5", "f0.667")},
            "filled": {cell: filled and not drops.get(cell) for cell in ("f0.333", "f0.5", "f0.667")}}


def test_stage_minus1_counts_scope_drops_fills_and_d_range():
    rows = [census(0, {"f0.333": "limit_stop_beyond_cap"}), census(1), census(2, filled=False),
            census(3, direction="bearish")]
    out = mcl.stage_minus1(rows)
    third, half = out["cells"][0], out["cells"][1]
    assert (out["verdict"], out["alerts"]) == ("REACHABLE", 4)
    assert (third["in_scope"], third["kept"], third["drops"]) == (4, 3, {"limit_stop_beyond_cap": 1})
    assert (half["observed_n"], half["d_range"]) == (3, [2.5, 5.5])
    assert half["filled_by_direction"] == {"bullish": 2, "bearish": 1}
    assert half["fill_states"] == {"filled": 3, "expired": 1}


def test_a_census_without_fills_is_zero_diff():
    assert mcl.stage_minus1([census(0, filled=False)])["verdict"] == "refused:zero-diff"
    assert mcl.stage_minus1([])["cells"][0]["d_range"] is None


def _res(passes, expr):
    return {"passes": passes, "expr": expr}


def test_neighbours_and_plateau():
    assert mcl.neighbours("f0.333") == ["f0.5"]
    assert mcl.neighbours("f0.5") == ["f0.333", "f0.667"]
    assert mcl.neighbours("f0.667") == ["f0.5"]
    assert mcl.plateau({"f0.333": _res(True, .30), "f0.5": _res(True, .31),
                        "f0.667": _res(True, .29)}) == "f0.5"
    assert mcl.plateau({"f0.333": _res(True, .40), "f0.5": _res(False, .50),
                        "f0.667": _res(True, .45)}) is None   # no cell has passing neighbours
    assert mcl.plateau({"f0.333": _res(True, .30), "f0.5": _res(True, .30),
                        "f0.667": _res(False, .1)}) == "f0.333"   # tie -> smaller f
    assert mcl.plateau({"f0.333": _res(False, .3), "f0.5": _res(True, .2),
                        "f0.667": _res(True, .4)}) == "f0.667"    # an edge cell, one neighbour


def test_clauses_score_all_three():
    ref = [row("ref", n, 1.0 if n < 5 else -1.0) for n in range(10)]      # ExpR 0, WR 50
    arm = [row("f0.5", n, 1.5 if n < 3 else -1.0) for n in range(6)]       # ExpR 0.25, WR 50
    out = mcl.clauses(arm, ref)
    assert (out["n"], out["ref_n"]) == (6, 10)
    assert out["expr"] == pytest.approx(0.25) and out["ref_expr"] == pytest.approx(0.0)
    assert out["expr_beats_reference"] and out["fills_half_of_reference"] and out["wr_within_2pp"]
    assert out["passes"] is True
    assert mcl.clauses(arm[:4], ref)["fills_half_of_reference"] is False   # 4 < 5
    assert mcl.clauses([], [])["passes"] is False
    assert mcl.clauses(arm, [])["fills_half_of_reference"] is False        # empty reference


def test_the_win_rate_clause_allows_exactly_two_points():
    ref = [row("ref", n, 1.0 if n < 50 else -1.0) for n in range(100)]     # 50.0%
    arm = [row("f0.5", n, 3.0 if n < 48 else -1.0) for n in range(100)]    # 48.0%
    assert mcl.clauses(arm, ref)["wr_within_2pp"] is True
    arm[47] = row("f0.5", 47, -1.0)                                         # 47.0%
    assert mcl.clauses(arm, ref)["wr_within_2pp"] is False


def test_populations_follow_the_cells_kept_alerts():
    rows = [row("ref", 1, 1.0), row("ref", 2, -1.0), row("ref", 3, None, filled=False),
            row("f0.5", 1, 1.0), row("f0.5", 2, None, dropped="limit_stop_beyond_cap"),
            row("f0.5", 3, None, filled=False)]
    assert mcl.cell_keys(rows, "f0.5") == {rows[0]["key"], rows[2]["key"]}
    assert [r["key"] for r in mcl.reference_rows(rows, "f0.5")] == [rows[0]["key"]]
    assert [r["key"] for r in mcl.closed(rows, "f0.5")] == [rows[3]["key"]]
    trade = mcl.to_trade(rows[3])
    assert (trade.r_multiple, trade.entry_date, trade.source) == (1.0, rows[3]["entry_date"],
                                                                  "confluence")


def test_thin_needs_thirty_per_direction():
    bulls = [row("f0.5", n, 1.0) for n in range(30)]
    bears = [row("f0.5", n, 1.0, direction="bearish") for n in range(30)]
    assert mcl.thin(bulls + bears) is False
    assert mcl.thin(bulls + bears[:29]) is True
    assert mcl.thin(bulls) is True


@pytest.fixture
def caps(monkeypatch):
    for attr, value in (("RISK_PER_TRADE_PCT", 1.0), ("PORTFOLIO_HEAT_CAP_PCT", 6.0),
                        ("SECTOR_HEAT_CAP_PCT", 3.0), ("MAX_OPEN_POSITIONS", 30),
                        ("MAX_POSITION_SIZE_PCT", 100.0), ("MAX_POSITION_VALUE_ABSOLUTE", 0.0)):
        monkeypatch.setattr(config, attr, value, raising=False)
    return monkeypatch


def _same_day(n):
    rows = [row("f0.5", i, 1.0, ticker=f"T{i}") for i in range(n)]
    for r in rows:
        r["fill_date"], r["exit_date"] = "2021-03-01", "2021-03-10"
    return rows


def test_portfolio_pass_keeps_what_the_caps_allow(caps):
    rows = _same_day(3)
    assert len(mcl.portfolio_pass(rows, "f0.5", sectors={}, cluster_fn=None)) == 3
    caps.setattr(config, "MAX_OPEN_POSITIONS", 1)
    kept, result = mcl.run_portfolio(rows, sectors={}, cluster_fn=None)
    assert [r["key"] for r in kept] == [rows[0]["key"]]
    assert result["skip_reasons"] == {"max_open": 2}


def test_a_notional_cap_cuts_risk_not_trades(caps):
    caps.setattr(config, "MAX_POSITION_VALUE_ABSOLUTE", 1000.0)
    kept, result = mcl.run_portfolio(_same_day(3), sectors={}, cluster_fn=None)
    assert (len(kept), result["notional_capped"]) == (3, 3)
    assert result["r_multiples_taken"] == [1.0, 1.0, 1.0]       # R stays on the plan's stop


def test_cluster_fn_reads_frames_before_the_fill_bar(monkeypatch):
    monkeypatch.setattr(config, "CORRELATED_HEAT_CAP_PCT", 3.0, raising=False)
    closes = list(100 + np.cumsum(np.random.default_rng(7).normal(0, 1, 150)))
    frames = {"AAA": make_ohlcv(closes), "BBB": make_ohlcv(closes)}
    fill_day = str(frames["AAA"].index[140].date())
    cluster_fn = mcl.make_cluster_fn(frames, {})
    sig = {"ticker": "AAA", "date": fill_day}
    held = lambda risk: [{"ticker": "BBB", "risk_pct": risk, "sector": None}]   # noqa: E731
    assert cluster_fn(held(2.5), sig, 1.0) is True          # 2.5 + 1.0 > 3.0, corr 1.0
    assert cluster_fn(held(1.0), sig, 1.0) is False
    assert cluster_fn([], sig, 1.0) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit_clauses.py`
Expected: FAIL — `AttributeError: module 'measure_confluence_limit' has no attribute 'neighbours'`.

- [ ] **Step 3: Add the imports** to the import block of `scripts/backtest/measure_confluence_limit.py` (`Counter` joins the stdlib block)

```python
from collections import Counter

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.acceptance import (CLOSED, ArmTrade, expectancy_r,  # noqa: E402
                                                  win_rate)
from swingbot.core.backtesting.backtest_wf import portfolio_replay  # noqa: E402
```

- [ ] **Step 4: Add the three sections** between `build` and `# --- CLI`

```python
# --- census (Stage -1, outcome-blind) ---------------------------------------------

def _census_cell(rows, cell) -> dict:
    kept = [r for r in rows if cell in r["drops"] and r["drops"][cell] is None]
    filled = [r for r in kept if r["filled"][cell]]
    ds = [r["d_pct"] for r in kept]
    return {"cell": cell, "in_scope": sum(cell in r["drops"] for r in rows),
            "drops": dict(Counter(r["drops"][cell] for r in rows if r["drops"].get(cell))),
            "kept": len(kept), "observed_n": len(filled),
            "fill_states": dict(Counter(r["fill_state"][cell] for r in kept)),
            "filled_by_direction": {d: sum(r["direction"] == d for r in filled) for d in DIRECTIONS},
            "d_range": [min(ds), max(ds)] if ds else None}


def stage_minus1(rows) -> dict:
    """Scope, drops, fills and the D range each cell reaches; no outcome read."""
    cells = [_census_cell(rows, cell) for cell in clr.CELLS]
    verdict = "REACHABLE" if any(cell["observed_n"] for cell in cells) else "refused:zero-diff"
    return {"stage": -1, "verdict": verdict, "alerts": len(rows), "cells": cells}


# --- populations and clauses ----------------------------------------------------

def closed(rows, arm) -> list:
    return [r for r in rows if r["arm"] == arm and r["filled"] and r["outcome"] in CLOSED]


def cell_keys(rows, cell) -> set:
    """The cell's in-scope alerts it did not drop -- its slice of D."""
    return {r["key"] for r in rows if r["arm"] == cell and r["dropped"] is None}


def reference_rows(rows, cell) -> list:
    keys = cell_keys(rows, cell)
    return [r for r in closed(rows, "ref") if r["key"] in keys]


def to_trade(r) -> ArmTrade:
    """A row as the harvest helpers read it: R after frictions, paired on the
    signal date."""
    return ArmTrade(ticker=r["ticker"], strategy=r["strategy"], horizon_key=r["horizon_key"],
                    entry_date=r["entry_date"], outcome=r["outcome"], r_multiple=r["r_net"],
                    planned_rr=r["planned_rr"], source="confluence", direction=r["direction"])


def clauses(arm_rows, ref_rows) -> dict:
    """Spec § Pass rule, point estimates, pooled directions."""
    arm, ref = [to_trade(r) for r in arm_rows], [to_trade(r) for r in ref_rows]
    exp, ref_exp, wr, ref_wr = expectancy_r(arm), expectancy_r(ref), win_rate(arm), win_rate(ref)
    out = {"n": len(arm), "ref_n": len(ref), "expr": exp, "ref_expr": ref_exp,
           "wr": wr, "ref_wr": ref_wr,
           "expr_beats_reference": exp is not None and ref_exp is not None and exp > ref_exp,
           "fills_half_of_reference": bool(ref) and len(arm) >= FILLS_SHARE * len(ref),
           "wr_within_2pp": wr is not None and ref_wr is not None
           and wr >= ref_wr - WR_SLACK_PP - 1e-9}
    out["passes"] = all(out[name] for name in CLAUSE_NAMES)
    return out


def neighbours(key: str) -> list[str]:
    index = clr.CELLS.index(key)
    return [clr.CELLS[j] for j in (index - 1, index + 1) if 0 <= j < len(clr.CELLS)]


def plateau(results: dict) -> str | None:
    """The passing cell with the highest ExpR whose neighbours all pass; a
    tie keeps the smaller f (max keeps the first maximum)."""
    pool = [key for key in clr.CELLS if results[key]["passes"]
            and all(results[other]["passes"] for other in neighbours(key))]
    return max(pool, key=lambda key: results[key]["expr"]) if pool else None


def thin(rows) -> bool:
    """Stage 3 seal: fewer than 30 kept arm trades in either direction."""
    return any(sum(r["direction"] == d for r in rows) < THIN_PER_DIRECTION for d in DIRECTIONS)


# --- portfolio pass (spec rules 7 and 8) --------------------------------------------

def _signal(r) -> dict:
    return {"ticker": r["ticker"], "date": r["fill_date"], "exit_date": r["exit_date"],
            "r_multiple": r["r_net"], "direction": r["direction"], "outcome": r["outcome"],
            "strategy": r["strategy"], "stop_pct": r["stop_pct"], "key": r["key"],
            "entry": r["entry"], "stop_loss": r["stop_loss"]}


def run_portfolio(rows, *, sectors, cluster_fn) -> tuple:
    """One portfolio pass over closed rows dated at the fill: heat, sector,
    cluster, max-open and the notional caps re-run against the then-open
    book. Returns (kept rows, portfolio_replay result)."""
    result = portfolio_replay(
        [_signal(r) for r in rows], risk_pct=float(getattr(config, "RISK_PER_TRADE_PCT", 1.0)),
        heat_cap_pct=float(getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)),
        sector_cap_pct=float(getattr(config, "SECTOR_HEAT_CAP_PCT", 3.0)),
        max_open=getattr(config, "MAX_OPEN_POSITIONS", None), sectors=sectors, throttles=False,
        max_position_pct=float(config.MAX_POSITION_SIZE_PCT),
        max_position_value=float(config.MAX_POSITION_VALUE_ABSOLUTE),
        cluster_fn=cluster_fn, track_keys=True)
    taken = set(result["taken_keys"])
    return [r for r in rows if r["key"] in taken], result


def portfolio_pass(rows, arm, *, sectors, cluster_fn) -> list:
    """Kept rows of one arm. For a cell's reference, pass rows already
    restricted to that cell's keys (reference_rows)."""
    return run_portfolio(closed(rows, arm), sectors=sectors, cluster_fn=cluster_fn)[0]


def make_cluster_fn(frames, sectors):
    """cluster_fn for portfolio_replay: correlation on frames cut BEFORE the
    fill bar, sector fallback on thin data (correlation.cluster_exposure)."""
    from swingbot.core.edge.correlation import cluster_check, cluster_exposure

    def cluster_fn(open_pos, sig, eff_risk) -> bool:
        names = {sig["ticker"], *(p["ticker"] for p in open_pos)}
        dfs = {t: frames[t].loc[:sig["date"]].iloc[:-1] for t in names if t in frames}
        exposure = cluster_exposure(open_pos, sig["ticker"], dfs, 10_000.0, sectors=sectors)
        return not cluster_check(exposure, eff_risk)["allowed"]
    return cluster_fn


def load_sectors() -> dict:
    from swingbot.core.marketdata.universe import sector_map
    return {**sector_map("etfs"), **sector_map("sp500")}
```

`open_pos` entries carry `risk_pct`, which `heat.trade_risk_pct` reads first, so the balance passed to `cluster_exposure` never matters.

- [ ] **Step 5: Run both script test files**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit_clauses.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit.py
```
Expected: PASS.

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: PASS (`clauses` is the busiest function, about 9).

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/measure_confluence_limit.py tests/backtest_scripts/test_measure_confluence_limit_clauses.py
git commit -m "feat(v212): measure script -- clauses, plateau, thin seal, portfolio pass (V212-13b)"
```


### Task V212-13c: Measure script, part 3: Stage 0..3, the stage runner, one-shot refusal, ledger rows, `stage` / `ledger` CLI

**Model:** opus — the stage chain enforces the funnel order and the one VALIDATION shot; a missed refusal lets a closed arm advance or reads VALIDATION for a cell that was not selected.

**Files:**
- Modify: `scripts/backtest/measure_confluence_limit.py` (imports; a `# --- stages` and a `# --- ledger` section before `# --- CLI`; `stage` and `ledger` subcommands)
- Test: `tests/backtest_scripts/test_measure_confluence_limit_stages.py`

**Interfaces:**
- Consumes: V212-13 (constants, `require_preregistration`, `build`, `universe`, `stage_path`, `rows_file`, `_previous`, `_load`/`_write`/`_refuse`, `COMMANDS`, `_common`, `_parser`); V212-13b (`stage_minus1`, `closed`, `reference_rows`, `to_trade`, `clauses`, `plateau`, `thin`, `run_portfolio`, `make_cluster_fn`, `load_sectors`); existing `acceptance.project_target_n`, `acceptance_exit_funnel.MDE_CEILING_R`/`MDE_POWER`/`TRAIN_DAYS`/`VALIDATION_DAYS`, `acceptance_harvest.mde_expectancy_r_paired`, `backtest_wf.gate_expectancy_harvest`.
- Produces (V212-14; the V212-15/16 runs): `stage0(rows)`, `score_cell(rows, cell, *, sectors, cluster_fn) -> (scored, {"arm", "ref", "arm_result", "ref_result"})`, `stage1`/`stage2`/`stage3(rows[, cell], *, sectors, cluster_fn)`; `run_stage(stage, out_dir, *, build, preregistration, sectors=None, cluster_fn=None)`; `STAGE_RUNNERS` (V212-14 wraps entries 1 and 3); `ledger_rows(out_dir, run_date, record)` (the `preregistration-ledger.jsonl` shape plus `stage_verdict`); CLI `stage --stage {-1..3}` and `ledger --run-date --record` (one JSON line per look, which V212-16 appends).

**Rules** (spec § Pass rule; `backtest-methodology.md` § Funnel stages):
- Stage −1 is V212-13b's `stage_minus1` over the TRAIN census rows.
- Stage 0 (TRAIN rows, no portfolio pass): paired MDE over keys closed in the arm and in the cell's reference; any cell above `MDE_CEILING_R` closes the run `UNDERPOWERED`, budget intact.
- Stage 1: each side through its own portfolio pass, clauses pooled (the per-direction table is a disclosure, V212-14), `plateau` → `SELECTED` / `NO_ELIGIBLE_CELL`. Stage 2: folds 2021–2023 by signal date on Stage 1's kept rows, `n_tp1` = the smaller win count (`validate_component._harvest_fold_rows` precedent), `gate_expectancy_harvest`. Stage 3: VALIDATION for the selected cell only, refused once its file exists; `THIN`, else `PASS` / `FAIL` on the clauses.
- Ledger: `PASS` → `PASS`; `FAIL` or not selected → `NO-LIFT`; `UNDERPOWERED` / `THIN` / `refused:zero-diff` → `UNMEASURABLE`; undecided → `OPEN`; `p` None. `--tickers` is refused for Stage 3 and into `RESULTS` (v139 precedent).

- [ ] **Step 1: Write the failing test** `tests/backtest_scripts/test_measure_confluence_limit_stages.py`

```python
"""V212-13c: the v212 stage chain -- census verdicts, the paired MDE, the
portfolio-passed clauses and plateau, the fold gate, the one VALIDATION shot
on the selected cell only, and one ledger row per look. `build` is faked."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_confluence_limit as mcl  # noqa: E402

from swingbot import config
from swingbot.core.backtesting import confluence_limit_replay as clr
from tests.backtest_scripts.test_measure_confluence_limit_clauses import row


@pytest.fixture(autouse=True)
def _open_caps(monkeypatch):
    monkeypatch.setattr(mcl, "require_preregistration", lambda path: None)
    for attr, value in (("RISK_PER_TRADE_PCT", 1.0), ("PORTFOLIO_HEAT_CAP_PCT", 1e9),
                        ("SECTOR_HEAT_CAP_PCT", 1e9), ("MAX_OPEN_POSITIONS", None),
                        ("MAX_POSITION_SIZE_PCT", 1e9), ("MAX_POSITION_VALUE_ABSOLUTE", 0.0)):
        monkeypatch.setattr(config, attr, value, raising=False)


def alerts(years, cells=clr.CELLS, n=100):
    """Reference: WR 50, ExpR 0. Every cell: 80% fills, WR 50, ExpR +0.1."""
    out = []
    for year in years:
        for i in range(n):
            out.append(row("ref", i, 1.0 if i % 2 == 0 else -1.0, year=year))
            for cell in cells:
                filled = i % 5 != 4
                r = (1.2 if i % 2 == 0 else -1.0) if filled else None
                out.append(row(cell, i, r, year=year, filled=filled))
    return out


def census_rows(filled=True):
    return [{"key": f"T{i}|4w|2021-03-01|bullish", "direction": "bullish", "d_pct": 2.5 + i,
             "drops": {cell: None for cell in clr.CELLS},
             "fill_state": {cell: "filled" if filled else "expired" for cell in clr.CELLS},
             "filled": {cell: filled for cell in clr.CELLS}} for i in range(3)]


def fake_build(calls, census=None):
    def build(kind, window, *, touch=False, cells=clr.F_GRID):
        calls.append((kind, tuple(window), touch, tuple(round(c, 3) for c in cells)))
        if kind == "census":
            return census_rows() if census is None else census
        years = (2024,) if tuple(window) == mcl.VALIDATION else (2021, 2022, 2023)
        return alerts(years, [clr.cell_key(c) for c in cells])
    return build


def _run(stage, out, calls, **kw):
    return mcl.run_stage(stage, out, build=fake_build(calls, **kw), preregistration="p.md")


def test_every_stage_refuses_without_the_preregistration(tmp_path, monkeypatch):
    monkeypatch.undo()
    with pytest.raises(SystemExit, match="no-preregistration"):
        mcl.run_stage(-1, tmp_path, build=fake_build([]), preregistration=None)


def test_stage0_refuses_without_the_census(tmp_path):
    with pytest.raises(SystemExit, match="run stage -1 first"):
        _run(0, tmp_path, [])


def test_a_census_without_fills_closes_the_run(tmp_path):
    out = _run(-1, tmp_path, [], census=census_rows(filled=False))
    assert out["verdict"] == "refused:zero-diff"
    with pytest.raises(SystemExit, match="closed at stage -1"):
        _run(0, tmp_path, [])


def test_the_full_chain_reads_validation_for_the_selected_cell_only(tmp_path):
    calls = []
    verdicts = [_run(stage, tmp_path, calls)["verdict"] for stage in (-1, 0, 1, 2, 3)]
    assert verdicts == ["REACHABLE", "POWERED", "SELECTED", "PASS", "THIN"]   # no bearish fills
    stage1 = mcl._load(mcl.stage_path(tmp_path, 1))
    assert stage1["selected"] == {"cell": "f0.333", "f": pytest.approx(1 / 3)}   # tie -> smaller f
    assert all(cell["passes"] for cell in stage1["cells"])
    folds = mcl._load(mcl.stage_path(tmp_path, 2))["folds"]
    assert [(f["year"], f["n_tp1"]) for f in folds] == [(2021, 40), (2022, 40), (2023, 40)]
    assert all(f["delta_expectancy_r"] == pytest.approx(0.1) for f in folds)
    validation = [c for c in calls if c[1] == mcl.VALIDATION]
    assert validation == [("rows", mcl.VALIDATION, False, (0.333,))]
    train_rows = [c for c in calls if c[0] == "rows" and c[1] == mcl.TRAIN]
    assert len(train_rows) == 1                          # TRAIN rows built once, then reused


def test_stage3_is_one_shot(tmp_path):
    for stage in (-1, 0, 1, 2, 3):
        _run(stage, tmp_path, [])
    with pytest.raises(SystemExit, match="one VALIDATION shot is spent"):
        _run(3, tmp_path, [])


def test_ledger_rows_one_per_look(tmp_path):
    for stage in (-1, 0, 1, 2, 3):
        _run(stage, tmp_path, [])
    rows = mcl.ledger_rows(tmp_path, "2026-11-20", "docs/superpowers/results/x.md")
    assert [r["id"] for r in rows] == ["v212-f0.333", "v212-f0.5", "v212-f0.667"]
    assert [(r["verdict"], r["stage_verdict"]) for r in rows] == [
        ("UNMEASURABLE", "THIN"), ("NO-LIFT", "NOT_SELECTED"), ("NO-LIFT", "NOT_SELECTED")]
    assert {r["instrument"] for r in rows} == {"v2"} and rows[0]["n"] == 80


def test_an_underpowered_stage0_makes_every_look_unmeasurable(tmp_path):
    mcl._write(mcl.stage_path(tmp_path, -1), {"verdict": "REACHABLE"})
    mcl._write(mcl.stage_path(tmp_path, 0), {"verdict": "UNDERPOWERED"})
    rows = mcl.ledger_rows(tmp_path, "2026-11-20", "r.md")
    assert {(r["verdict"], r["stage_verdict"]) for r in rows} == {("UNMEASURABLE", "UNDERPOWERED")}
    assert {r["verdict"] for r in mcl.ledger_rows(tmp_path / "none", "d", "r")} == {"OPEN"}


def test_the_cli_refuses_a_partial_validation_shot():
    with pytest.raises(SystemExit, match="partial-validation"):
        mcl.main(["stage", "--stage", "3", "--tickers", "5", "--preregistration", "p.md"])
    with pytest.raises(SystemExit, match="smoke-run"):
        mcl.main(["stage", "--stage", "0", "--tickers", "5", "--preregistration", "p.md"])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit_stages.py`
Expected: FAIL — `AttributeError: module 'measure_confluence_limit' has no attribute 'run_stage'`.

- [ ] **Step 3: Add the imports** to `scripts/backtest/measure_confluence_limit.py`

```python
import functools

from swingbot.core.backtesting.acceptance import project_target_n  # noqa: E402
from swingbot.core.backtesting.acceptance_exit_funnel import (MDE_CEILING_R, MDE_POWER,  # noqa: E402
                                                              TRAIN_DAYS, VALIDATION_DAYS)
from swingbot.core.backtesting.acceptance_harvest import mde_expectancy_r_paired  # noqa: E402
from swingbot.core.backtesting.backtest_wf import gate_expectancy_harvest  # noqa: E402
```

(`functools` joins the stdlib block; `expectancy_r` is already imported by V212-13b.)

- [ ] **Step 4: Add the stages and the ledger** before `# --- CLI` (`stage_minus1`, `stage_path`, `rows_file` and `_previous` already exist)

```python
# --- stages ----------------------------------------------------------------------

def _rows(ctx, kind, window_name, *, touch=False, cells=clr.F_GRID) -> list:
    """Rows from their file, built (per-ticker checkpointed) and saved when absent."""
    path = rows_file(ctx["out"], kind, window_name, touch)
    if not path.exists():
        _write(path, ctx["build"](kind, WINDOWS[window_name], touch=touch, cells=cells), indent=None)
    return _load(path)


def _mde_cell(rows, cell) -> dict:
    arm = [to_trade(r) for r in closed(rows, cell)]
    ref = [to_trade(r) for r in reference_rows(rows, cell)]
    observed_n = len({t.key for t in arm} & {t.key for t in ref})
    target_n = project_target_n(observed_n=observed_n, observed_days=TRAIN_DAYS,
                                target_days=VALIDATION_DAYS)
    mde = mde_expectancy_r_paired(ref, arm, target_n=target_n, power=MDE_POWER)
    return {"cell": cell, "observed_n": observed_n, "target_n": target_n, "mde_r": mde,
            "powered": mde is not None and mde <= MDE_CEILING_R}


def stage0(rows) -> dict:
    cells = [_mde_cell(rows, cell) for cell in clr.CELLS]
    verdict = "POWERED" if all(cell["powered"] for cell in cells) else "UNDERPOWERED"
    return {"stage": 0, "verdict": verdict, "mde_ceiling_r": MDE_CEILING_R,
            "power": MDE_POWER, "cells": cells}


def score_cell(rows, cell, *, sectors, cluster_fn) -> tuple:
    """Both sides through their own portfolio pass, then the clauses."""
    arm, arm_result = run_portfolio(closed(rows, cell), sectors=sectors, cluster_fn=cluster_fn)
    ref, ref_result = run_portfolio(reference_rows(rows, cell), sectors=sectors,
                                    cluster_fn=cluster_fn)
    scored = {"cell": cell, **clauses(arm, ref)}
    return scored, {"arm": arm, "ref": ref, "arm_result": arm_result, "ref_result": ref_result}


def stage1(rows, *, sectors, cluster_fn) -> dict:
    results = {cell: score_cell(rows, cell, sectors=sectors, cluster_fn=cluster_fn)[0]
               for cell in clr.CELLS}
    pick = plateau(results)
    selected = None if pick is None else {"cell": pick, "f": clr.F_GRID[clr.CELLS.index(pick)]}
    return {"stage": 1, "verdict": "SELECTED" if selected else "NO_ELIGIBLE_CELL",
            "selected": selected, "cells": list(results.values())}


def _fold(kept, year) -> dict:
    arm = [to_trade(r) for r in kept["arm"] if r["entry_date"][:4] == str(year)]
    ref = [to_trade(r) for r in kept["ref"] if r["entry_date"][:4] == str(year)]
    exp, ref_exp = expectancy_r(arm), expectancy_r(ref)
    delta = None if exp is None or ref_exp is None else exp - ref_exp
    wins = min(sum(t.outcome == "win" for t in arm), sum(t.outcome == "win" for t in ref))
    return {"year": year, "n": len(arm), "ref_n": len(ref), "delta_expectancy_r": delta,
            "n_tp1": wins}


def stage2(rows, cell, *, sectors, cluster_fn) -> dict:
    _, kept = score_cell(rows, cell, sectors=sectors, cluster_fn=cluster_fn)
    folds = [_fold(kept, year) for year in FOLD_YEARS]
    return {"stage": 2, "cell": cell, "verdict": gate_expectancy_harvest({"folds": folds}),
            "folds": folds}


def stage3(rows, cell, *, sectors, cluster_fn) -> dict:
    scored, kept = score_cell(rows, cell, sectors=sectors, cluster_fn=cluster_fn)
    verdict = "THIN" if thin(kept["arm"]) else ("PASS" if scored["passes"] else "FAIL")
    return {"stage": 3, "cell": cell, "verdict": verdict, "score": scored}


def _env(ctx) -> dict:
    return {"sectors": ctx["sectors"], "cluster_fn": ctx["cluster_fn"]}


def _run_m1(ctx):
    return stage_minus1(_rows(ctx, "census", "train"))


def _run_0(ctx):
    _previous(ctx["out"], 0)
    return stage0(_rows(ctx, "rows", "train"))


def _run_1(ctx):
    _previous(ctx["out"], 1)
    return stage1(_rows(ctx, "rows", "train"), **_env(ctx))


def _run_2(ctx):
    selected = _previous(ctx["out"], 2)["selected"]
    return stage2(_rows(ctx, "rows", "train"), selected["cell"], **_env(ctx))


def _run_3(ctx):
    _previous(ctx["out"], 3)
    selected = _load(stage_path(ctx["out"], 1))["selected"]
    rows = _rows(ctx, "rows", "validation", cells=(selected["f"],))
    return stage3(rows, selected["cell"], **_env(ctx))


STAGE_RUNNERS = {-1: _run_m1, 0: _run_0, 1: _run_1, 2: _run_2, 3: _run_3}


def run_stage(stage, out_dir, *, build, preregistration, sectors=None, cluster_fn=None) -> dict:
    """One stage, its verdict JSON written. Stages -1..2 are TRAIN-only and
    may be re-run; stage 3 may not."""
    require_preregistration(preregistration)
    target = stage_path(out_dir, stage)
    if stage == 3 and target.exists():
        _refuse(f"{target.name} exists -- v212's one VALIDATION shot is spent")
    ctx = {"out": Path(out_dir), "build": build, "sectors": sectors or {},
           "cluster_fn": cluster_fn}
    out = STAGE_RUNNERS[stage](ctx)
    _write(target, out)
    return out


# --- ledger ----------------------------------------------------------------------

LEDGER_VERDICTS = {"PASS": "PASS", "FAIL": "NO-LIFT", "NOT_SELECTED": "NO-LIFT",
                   "NO_ELIGIBLE_CELL": "NO-LIFT", "THIN": "UNMEASURABLE",
                   "UNDERPOWERED": "UNMEASURABLE", "refused:zero-diff": "UNMEASURABLE",
                   "OPEN": "OPEN"}


def _gate_verdict(stages) -> str | None:
    """The verdict of the first stage that closed the run, else None."""
    for stage, advancing in ((-1, "REACHABLE"), (0, "POWERED"), (1, "SELECTED")):
        verdict = stages.get(stage, {}).get("verdict")
        if verdict is None:
            return "OPEN"
        if verdict != advancing:
            return verdict
    return None


def _look_verdict(cell, stages) -> str:
    closed_by = _gate_verdict(stages)
    if closed_by is not None:
        return closed_by
    if stages[1]["selected"]["cell"] != cell:
        return "NOT_SELECTED"
    if 3 in stages:
        return stages[3]["verdict"]
    return stages[2]["verdict"] if stages.get(2, {}).get("verdict") == "FAIL" else "OPEN"


def _look_stats(cell, stages) -> dict:
    if 3 in stages and stages[3].get("cell") == cell:
        return stages[3]["score"]
    return next((c for c in stages.get(1, {}).get("cells", []) if c["cell"] == cell), {})


def ledger_rows(out_dir, run_date, record) -> list:
    """One preregistration-ledger row per look (spec: 3 looks, BH family)."""
    stages = {s: _load(stage_path(out_dir, s)) for s in STAGE_RUNNERS
              if stage_path(out_dir, s).exists()}
    rows = []
    for cell in clr.CELLS:
        raw, stats = _look_verdict(cell, stages), _look_stats(cell, stages)
        rows.append({"id": f"v212-{cell}", "date": run_date,
                     "hypothesis": f"Confluence limit entry partway to the support, f={cell[1:]} "
                                   "of M-S, stop 0.25% beyond S, clamped confluence plans; ExpR "
                                   "above the reference, fills >= 50%, WR within 2pp (v212)",
                     "instrument": "v2", "n": stats.get("n"), "exp_r": stats.get("expr"),
                     "p": None, "verdict": LEDGER_VERDICTS[raw], "stage_verdict": raw,
                     "record": record})
    return rows
```

- [ ] **Step 5: Add the `stage` and `ledger` subcommands** — extend `_parser()` before its `return`, and add the commands:

```python
    stage = subs.add_parser("stage")
    _common(stage)
    stage.add_argument("--stage", required=True, type=int, choices=sorted(STAGE_RUNNERS))
    ledger = subs.add_parser("ledger")
    _common(ledger)
    ledger.add_argument("--run-date", required=True)
    ledger.add_argument("--record", required=True)
```

```python
def _cli_refusal(args) -> str | None:
    if args.tickers and args.stage == 3:
        return "partial-validation -- stage 3 is the one shot and runs the full universe"
    if args.tickers and Path(args.out).resolve() == RESULTS.resolve():
        return "smoke-run -- --tickers needs a scratch --out, never the results directory"
    return None


def _portfolio_env(stage) -> dict:
    """Sectors and the cluster callback for stages 1-3 (frames from the cache)."""
    if stage < 1:
        return {}
    from measure_arms import load_frame
    frames = {t: f for t in universe() if (f := load_frame(t)) is not None}
    sectors = load_sectors()
    return {"sectors": sectors, "cluster_fn": make_cluster_fn(frames, sectors)}


def _cmd_stage(args):
    refusal = _cli_refusal(args)
    if refusal:
        _refuse(refusal)
    build_fn = functools.partial(build, tickers=args.tickers, workers=args.workers,
                                 checkpoint_dir=args.checkpoint_dir)
    out = run_stage(args.stage, args.out, build=build_fn, preregistration=args.preregistration,
                    **_portfolio_env(args.stage))
    print(f"v212 stage {args.stage}: {out['verdict']} -> {stage_path(args.out, args.stage)}",
          flush=True)
    return 0 if out["verdict"] in ADVANCING else 1


def _cmd_ledger(args):
    for line in ledger_rows(args.out, args.run_date, args.record):
        print(json.dumps(line, ensure_ascii=False))
    return 0


COMMANDS.update({"stage": _cmd_stage, "ledger": _cmd_ledger})
```

Drop "(V212-13c)" from the module docstring's `stage`/`ledger` lines.

- [ ] **Step 6: Run the three script test files**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit_stages.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit_clauses.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit.py
```
Expected: PASS (the fixture's paired deltas are 0.2R or 0, so its MDE is a few hundredths of an R; never raise `MDE_CEILING_R` to pass).

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: PASS (`_look_verdict` and `_fold` are the busiest, both under 10).

- [ ] **Step 8: Commit**

```bash
git add scripts/backtest/measure_confluence_limit.py tests/backtest_scripts/test_measure_confluence_limit_stages.py
git commit -m "feat(v212): measure script stage chain, one-shot VALIDATION, ledger rows (V212-13c)"
```



### Task V212-14: Disclosures module, part 1: scope and D range, alert volume, paired ΔR and dollars, adverse and gap stops, ATR, SPY down days, earnings

**Model:** sonnet — small pure aggregations over dict rows against a written list; nothing gates on them, but each figure must read the right population.

**Files:**
- Create: `swingbot/core/backtesting/confluence_limit_disclosures.py`
- Create: `tests/backtesting/test_confluence_limit_disclosures.py`

**Interfaces:**
- Consumes: V212-11/11b row keys (`key`, `arm`, `ticker`, `direction`, `entry_date`, `fill_date`, `exit_date`, `expiry_date`, `market`, `stop_loss`, `filled`, `dropped`, `outcome`, `r_net`, `gap_stopped`, `gap_stop_r_from_limit`, `early_stop`, `wick_through`, `atr14_pct`) and census keys (`entry_date`, `d_pct`, `drops`, `fill_state`); existing `acceptance.CLOSED` / `DECIDED` (`acceptance.py:98-100`). Nothing from V212-6..10 (the live path moved to v216).
- Produces (V212-14b assembles them into `disclosures`; V212-14c):
  - `scope_counts(census_rows, cell) -> dict` (`in_scope`, `kept`, `drops`, `d_range`, `fill_states`, `tp1_cancel_share`, `expiry_share`); `alert_volume_per_day(census_rows, arm_rows) -> float`.
  - `paired_delta(arm_rows, ref_rows) -> dict` (`alerts`, `mean_delta_r`, `share_positive`, `dollar_per_alert_arm`, `dollar_per_alert_ref`); `filled_dollars(arm_rows) -> dict` (`fills`, `total`, `per_fill`).
  - `adverse(arm_rows) -> dict` (`fills`, `effective_stop_from_m_pct`, `early_stop_share`, `wick_through_share`, `gap_stops`, `gap_stop_mean_r`, `gap_stop_worst_r`, `gap_stop_mean_r_from_limit`, `gap_stop_worst_r_from_limit`, `gap_stop_max_per_day`).
  - `by_atr(arm_rows) -> list[dict]` (`bucket`, `alerts`, `fills`, `fill_rate`, `expr`); `spy_changes(frame) -> dict[str, float]`; `spy_days(arm_rows, spy) -> dict` (`down`, `other` as `_stats` dicts, `distinct_fill_days`, `spy_missing`); `earnings_share(arm_rows, earnings) -> dict` (`fills`, `with_earnings`, `share`, `tickers_without_calendar`).
  - Private helpers V212-14b reuses: `_mean`, `_share`, `_day`, `_closed(rows)`, `_stats(rows) -> {"n", "expr", "wr"}`. Constants `RISK_DOLLARS = 100.0`, `ATR_EDGES = (2.0, 3.0, 4.5)`, `ATR_LABELS`, `SPY_DOWN_PCT = -1.0`, `DIRECTIONS`.

**Decisions fixed here** (spec § Pass rule, Disclosures; § The rule 6):
- **Printed, never gating.** Nothing in `measure_confluence_limit.py` reads a disclosure back into a verdict.
- `arm_rows` = every row of one cell (dropped and unfilled included); `ref_rows` = the stream's `"ref"` rows. **Paired ΔR over every in-scope alert:** joined on `key`; an arm row counts `r_net` only when filled and closed, else 0R (unfilled and dropped alike); a reference row still open at the window end counts 0R. Dollar P&L per alert = mean alert R × `RISK_DOLLARS`.
- **Gap-through-stop:** count, mean and worst `r_net` (about 0R less frictions, spec rule 6), the pessimistic from-L `gap_stop_r_from_limit` (mean, worst), and the most gap stops on one fill day (clustering). **Stop-run** = wick-through share of filled losses.
- **Earnings window** = a report date after the signal date and on or before `expiry_date` (bars t+1..t+3); `earnings` is `{ticker: [iso dates]}`. **SPY down day** = a fill date whose SPY change is below −1%; a date missing from `spy` counts as an other day and in `spy_missing`. **ATR buckets** `<2%`, `2-3%`, `3-4.5%`, `>=4.5%`, `unknown`, over non-dropped alerts.
- **Alert volume** = the cell's non-dropped alerts over the weekdays from the first to the last census signal date, inclusive.
- Optional row keys are read with `.get`, so V212-13b's slim test rows still disclose (V212-14c runs the stage tests through this module).

- [ ] **Step 1: Write the failing test** `tests/backtesting/test_confluence_limit_disclosures.py`

```python
"""V212-14/14b: v212 disclosures -- each figure reads the right population;
nothing here gates."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import confluence_limit_disclosures as cld


def row(arm, n, r, *, filled=True, dropped=None, direction="bullish", **kw):
    day = f"2021-03-{n + 1:02d}"
    outcome = "dropped" if dropped else ("not_triggered" if not filled else
                                         ("win" if r > 0 else "loss"))
    base = {"key": f"T{n}|4w|{day}|{direction}", "arm": arm, "ticker": f"T{n}",
            "direction": direction, "entry_date": day, "fill_date": day,
            "exit_date": f"2021-03-{n + 3:02d}", "expiry_date": f"2021-03-{n + 4:02d}",
            "market": 100.0, "stop_loss": 97.0, "filled": filled and not dropped,
            "dropped": dropped, "outcome": outcome,
            "r_net": r if filled and not dropped else None, "gap_stopped": False,
            "gap_stop_r_from_limit": None, "early_stop": False, "wick_through": False,
            "atr14_pct": 2.5}
    return {**base, **kw}


def census(n, *, drop=None, state="filled"):
    return {"key": f"T{n}|4w|2021-03-{n + 1:02d}|bullish", "entry_date": f"2021-03-{n + 1:02d}",
            "d_pct": 2.0 + n, "drops": {"f0.5": drop},
            "fill_state": {"f0.5": None if drop else state}}


ARM = [row("f0.5", 0, 2.0), row("f0.5", 1, -1.0, early_stop=True, wick_through=True),
       row("f0.5", 2, -0.05, gap_stopped=True, gap_stop_r_from_limit=-1.4, atr14_pct=5.0),
       row("f0.5", 3, None, filled=False), row("f0.5", 4, None, dropped="limit_rr_fail")]
REF = [row("ref", n, r) for n, r in enumerate((1.0, -1.0, -1.0, 1.5, 0.5))]
CENSUS = [census(0), census(1), census(2, state="gap_stopped"), census(3, state="tp1_cancel"),
          census(4, drop="limit_rr_fail")]
SPY = {"2021-03-01": -1.5, "2021-03-02": 0.3}
EARNINGS = {"T1": ["2021-03-04"], "T0": ["2021-03-01"]}


@pytest.fixture(autouse=True)
def _risk(monkeypatch):
    monkeypatch.setattr(config, "RISK_PER_TRADE_PCT", 1.0, raising=False)


def test_paired_delta_scores_unfilled_and_dropped_alerts_as_zero():
    paired = cld.paired_delta(ARM, REF)
    assert paired["alerts"] == 5
    # arm 2, -1, -0.05, 0, 0 against ref 1, -1, -1, 1.5, 0.5
    assert paired["mean_delta_r"] == pytest.approx((1 + 0 + 0.95 - 1.5 - 0.5) / 5)
    assert paired["share_positive"] == pytest.approx(2 / 5)
    assert paired["dollar_per_alert_arm"] == pytest.approx(100 * 0.95 / 5)
    assert paired["dollar_per_alert_ref"] == pytest.approx(100 * 1.0 / 5)
    assert cld.filled_dollars(ARM) == {"fills": 3, "total": pytest.approx(95.0),
                                       "per_fill": pytest.approx(95.0 / 3)}


def test_scope_d_range_and_binding_shares_come_from_the_census():
    scope = cld.scope_counts(CENSUS, "f0.5")
    assert (scope["in_scope"], scope["kept"], scope["drops"]) == (5, 4, {"limit_rr_fail": 1})
    assert scope["d_range"] == [2.0, 5.0]
    assert (scope["tp1_cancel_share"], scope["expiry_share"]) == (0.25, 0.0)
    assert scope["fill_states"] == {"filled": 2, "gap_stopped": 1, "tp1_cancel": 1}


def test_adverse_gap_and_stop_run():
    adv = cld.adverse(ARM)
    assert adv["effective_stop_from_m_pct"] == pytest.approx(3.0)
    assert (adv["early_stop_share"], adv["wick_through_share"]) == (pytest.approx(1 / 3), 0.5)
    assert (adv["gap_stops"], adv["gap_stop_worst_r"], adv["gap_stop_worst_r_from_limit"]) == (
        1, -0.05, -1.4)
    assert adv["gap_stop_max_per_day"] == 1


def test_atr_buckets_count_non_dropped_alerts():
    assert [(b["bucket"], b["alerts"], b["fills"]) for b in cld.by_atr(ARM)] == [
        ("2-3%", 3, 2), (">=4.5%", 1, 1)]


def test_spy_down_days_and_distinct_fill_days():
    spy = cld.spy_days(ARM, SPY)
    assert (spy["down"]["n"], spy["other"]["n"], spy["distinct_fill_days"]) == (1, 2, 3)
    assert spy["down"]["expr"] == pytest.approx(2.0) and spy["spy_missing"] == 1


def test_earnings_inside_the_three_bar_window():
    # T1's report (03-04) falls after its signal (03-02) and by its expiry (03-05);
    # T0's report is on the signal date itself, so outside the window
    out = cld.earnings_share(ARM, EARNINGS)
    assert (out["with_earnings"], out["fills"]) == (1, 3)
    assert out["share"] == pytest.approx(1 / 3) and out["tickers_without_calendar"] == 1


def test_alert_volume_per_day_counts_weekdays_spanned():
    cen = [census(0), census(4)]                       # Mon 2021-03-01 .. Fri 03-05
    arm = [row("f0.5", n, 1.0) for n in range(4)] + [row("f0.5", 4, None, dropped="x")]
    assert cld.alert_volume_per_day(cen, arm) == pytest.approx(4 / 5)
    assert cld.alert_volume_per_day([], arm) == 0.0


def test_spy_changes():
    frame = pd.DataFrame({"Close": [100.0, 98.0, 99.0]},
                         index=pd.to_datetime(["2021-03-01", "2021-03-02", "2021-03-03"]))
    assert cld.spy_changes(frame) == {"2021-03-02": pytest.approx(-2.0),
                                      "2021-03-03": pytest.approx((99.0 / 98.0 - 1) * 100)}


def test_slim_rows_and_empty_inputs_do_not_crash():
    slim = [{"key": "k", "arm": "f0.5", "ticker": "T", "direction": "bullish",
             "entry_date": "2021-03-01", "fill_date": "2021-03-01", "exit_date": "2021-03-05",
             "filled": True, "dropped": None, "outcome": "loss", "r_net": -1.0}]
    assert cld.adverse(slim)["effective_stop_from_m_pct"] is None
    assert cld.earnings_share(slim, {"T": ["2021-03-02"]})["with_earnings"] == 0
    assert [b["bucket"] for b in cld.by_atr(slim)] == ["unknown"]
    assert cld.paired_delta([], [])["mean_delta_r"] is None
    assert cld.scope_counts([], None)["d_range"] is None
    assert cld.filled_dollars([])["per_fill"] is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_limit_disclosures.py`
Expected: FAIL — `ImportError: cannot import name 'confluence_limit_disclosures'`.

- [ ] **Step 3: Create** `swingbot/core/backtesting/confluence_limit_disclosures.py`

```python
"""v212 disclosures (spec § Pass rule, Disclosures): figures printed beside
the verdict and never read by a gate. One cell at a time; the measure script
(V212-14c) collects the cells and the touch-fill sensitivity, and
`render_disclosures` (V212-14b) prints them as Markdown for the results doc."""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from swingbot.core.backtesting.acceptance import CLOSED, DECIDED

RISK_DOLLARS = 100.0                       # dollar P&L is quoted per $100 of fixed risk
ATR_EDGES = (2.0, 3.0, 4.5)                # ATR14 as % of the signal close
ATR_LABELS = ("<2%", "2-3%", "3-4.5%", ">=4.5%")
SPY_DOWN_PCT = -1.0                        # SPY close below prior close - 1%
DIRECTIONS = ("bullish", "bearish")


def _mean(values) -> float | None:
    return float(np.mean(values)) if values else None


def _share(part, whole) -> float | None:
    return part / whole if whole else None


def _day(value) -> str:
    return str(value or "")[:10]


def _closed(rows) -> list:
    return [r for r in rows if r.get("filled") and r.get("outcome") in CLOSED
            and r.get("r_net") is not None]


def _alert_r(r) -> float:
    return float(r["r_net"]) if _closed([r]) else 0.0


def _stats(rows) -> dict:
    """n, ExpR and WR (percent of decided) -- acceptance.expectancy_r / win_rate."""
    closed = _closed(rows)
    decided = [r for r in closed if r["outcome"] in DECIDED]
    wins = sum(r["outcome"] == "win" for r in decided)
    return {"n": len(closed), "expr": _mean([r["r_net"] for r in closed]),
            "wr": 100.0 * wins / len(decided) if decided else None}


def scope_counts(census_rows, cell) -> dict:
    """Scope, drops, the D range the cell reaches, and how often the TP1
    cancel or the expiry bound (census, outcome-blind)."""
    in_scope = [r for r in census_rows if cell in (r.get("drops") or {})]
    kept = [r for r in in_scope if r["drops"][cell] is None]
    ds = [r["d_pct"] for r in kept]
    states = Counter(r["fill_state"][cell] for r in kept)
    return {"in_scope": len(in_scope), "kept": len(kept),
            "drops": dict(Counter(r["drops"][cell] for r in in_scope if r["drops"][cell])),
            "d_range": [min(ds), max(ds)] if ds else None, "fill_states": dict(states),
            "tp1_cancel_share": _share(states["tp1_cancel"], len(kept)),
            "expiry_share": _share(states["expired"], len(kept))}


def alert_volume_per_day(census_rows, arm_rows) -> float:
    """Orders the cell would send per trading day: its non-dropped alerts over
    the weekdays from the first to the last census signal date, inclusive."""
    dates = sorted({_day(r["entry_date"]) for r in census_rows if r.get("entry_date")})
    if not dates:
        return 0.0
    end = np.datetime64(dates[-1]) + np.timedelta64(1, "D")
    days = int(np.busday_count(np.datetime64(dates[0]), end))
    sent = len({r["key"] for r in arm_rows if r.get("dropped") is None})
    return sent / days if days else 0.0


def paired_delta(arm_rows, ref_rows) -> dict:
    """Per in-scope alert: arm R (0 when dropped or unfilled) minus reference R."""
    arm, ref = {r["key"]: r for r in arm_rows}, {r["key"]: r for r in ref_rows}
    keys = sorted(arm.keys() & ref.keys())
    arm_r = [_alert_r(arm[k]) for k in keys]
    ref_r = [_alert_r(ref[k]) for k in keys]
    deltas = [a - b for a, b in zip(arm_r, ref_r)]
    return {"alerts": len(keys), "mean_delta_r": _mean(deltas),
            "share_positive": _share(sum(x > 0 for x in deltas), len(deltas)),
            "dollar_per_alert_arm": RISK_DOLLARS * _mean(arm_r) if keys else None,
            "dollar_per_alert_ref": RISK_DOLLARS * _mean(ref_r) if keys else None}


def filled_dollars(arm_rows) -> dict:
    """Dollar P&L at fixed risk on filled trades only."""
    rs = [r["r_net"] for r in _closed(arm_rows)]
    return {"fills": len(rs), "total": RISK_DOLLARS * sum(rs),
            "per_fill": RISK_DOLLARS * _mean(rs) if rs else None}


def _effective_stop_pct(fills) -> float | None:
    return _mean([abs(r["market"] - r["stop_loss"]) / r["market"] * 100.0
                  for r in fills if r.get("market")])


def _gap_stops(fills) -> dict:
    gaps = [r for r in fills if r.get("gap_stopped")]
    rs = [r["r_net"] for r in gaps]
    from_l = [r["gap_stop_r_from_limit"] for r in gaps
              if r.get("gap_stop_r_from_limit") is not None]
    per_day = Counter(_day(r["fill_date"]) for r in gaps)
    return {"gap_stops": len(gaps), "gap_stop_mean_r": _mean(rs),
            "gap_stop_worst_r": min(rs, default=None),
            "gap_stop_mean_r_from_limit": _mean(from_l),
            "gap_stop_worst_r_from_limit": min(from_l, default=None),
            "gap_stop_max_per_day": max(per_day.values(), default=0)}


def adverse(arm_rows) -> dict:
    """v131's adverse-selection diagnostics, the effective stop from M, the
    stop-run share and the gap-through-stop fills."""
    fills = _closed(arm_rows)
    losses = [r for r in fills if r["outcome"] == "loss"]
    return {"fills": len(fills), "effective_stop_from_m_pct": _effective_stop_pct(fills),
            "early_stop_share": _share(sum(bool(r.get("early_stop")) for r in fills), len(fills)),
            "wick_through_share": _share(sum(bool(r.get("wick_through")) for r in losses),
                                         len(losses)),
            **_gap_stops(fills)}


def _atr_bucket(atr) -> str:
    if atr is None:
        return "unknown"
    return ATR_LABELS[int(np.searchsorted(ATR_EDGES, float(atr), side="right"))]


def by_atr(arm_rows) -> list:
    groups = defaultdict(list)
    for r in arm_rows:
        if r.get("dropped") is None:
            groups[_atr_bucket(r.get("atr14_pct"))].append(r)
    out = []
    for label in (*ATR_LABELS, "unknown"):
        rows = groups.get(label)
        if rows:
            fills = len(_closed(rows))
            out.append({"bucket": label, "alerts": len(rows), "fills": fills,
                        "fill_rate": _share(fills, len(rows)), "expr": _stats(rows)["expr"]})
    return out


def spy_changes(frame) -> dict:
    """ISO date -> SPY close-to-close change in percent (the first bar has none)."""
    pct = frame["Close"].astype(float).pct_change() * 100.0
    return {idx.date().isoformat(): float(v) for idx, v in pct.dropna().items()}


def spy_days(arm_rows, spy) -> dict:
    fills = _closed(arm_rows)
    is_down = [spy.get(_day(r["fill_date"]), 0.0) < SPY_DOWN_PCT for r in fills]
    return {"down": _stats([r for r, down in zip(fills, is_down) if down]),
            "other": _stats([r for r, down in zip(fills, is_down) if not down]),
            "distinct_fill_days": len({_day(r["fill_date"]) for r in fills}),
            "spy_missing": sum(_day(r["fill_date"]) not in spy for r in fills)}


def _in_window(r, earnings) -> bool:
    """A report after the signal date and on or before the limit's expiry."""
    start, end = _day(r["entry_date"]), _day(r.get("expiry_date"))
    return bool(end) and any(start < day <= end for day in earnings.get(r["ticker"], ()))


def earnings_share(arm_rows, earnings) -> dict:
    fills = _closed(arm_rows)
    hits = sum(_in_window(r, earnings) for r in fills)
    return {"fills": len(fills), "with_earnings": hits, "share": _share(hits, len(fills)),
            "tickers_without_calendar": len({r["ticker"] for r in fills} - set(earnings))}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_limit_disclosures.py`
Expected: PASS (9 tests). A failing hand-computed figure is fixed in the module, never by editing the expected value, unless the comment beside it shows the arithmetic was wrong.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: PASS (`scope_counts` is the busiest, under 10 — each comprehension `for`/`if` counts).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/confluence_limit_disclosures.py tests/backtesting/test_confluence_limit_disclosures.py
git commit -m "feat(v212): disclosures part 1 -- scope, D range, paired dR, adverse, gap stops, ATR, SPY, earnings (V212-14)"
```


### Task V212-14b: Disclosures module, part 2: notional and heat-at-fill skips, per-direction table, risk and ruin, `disclosures()`, `render_disclosures`

**Model:** sonnet — assembly and Markdown over finished helpers plus two portfolio aggregations; the care points are reading heat from the portfolio pass and labelling the open-risk bound honestly.

**Files:**
- Modify: `swingbot/core/backtesting/confluence_limit_disclosures.py` (imports; append a portfolio-and-risk section, `disclosures`, and a `# --- render` section)
- Modify: `tests/backtesting/test_confluence_limit_disclosures.py` (append)

**Interfaces:**
- Consumes: V212-14 (`scope_counts`, `alert_volume_per_day`, `paired_delta`, `filled_dollars`, `adverse`, `by_atr`, `spy_days`, `earnings_share`, `_share`, `_day`, `_closed`, `_stats`, `RISK_DOLLARS`, `DIRECTIONS`); V212-12 `portfolio_replay` result keys `trades_taken`, `trades_skipped`, `max_dd_pct`, `notional_capped`, `skip_reasons`; V212-13c `score_cell(...)[1]` shape `{"arm", "ref", "arm_result", "ref_result"}`; existing `risk_metrics.max_drawdown_r(r_multiples)` (`analytics/risk_metrics.py:174`), `ruin.simulate(r_multiples, *, risk_pct, n_trades, n_paths, seed)` (`edge/ruin.py:18`, raises on an empty list), `config.RISK_PER_TRADE_PCT`. Nothing from V212-6..10: heat at fill is read from the portfolio pass, not the live path (v216).
- Produces (V212-14c; V212-16 renders it):
  - `disclosures(arm_rows, ref_rows, census_rows, *, spy, earnings, portfolio) -> dict` — one cell; keys `cell`, `scope`, `alert_volume_per_day`, `paired`, `filled_dollars`, `adverse`, `atr`, `spy`, `earnings`, `portfolio` (`{"arm", "ref"}` of `cap_skips`), `per_direction`, `risk` (`{"arm", "ref"}` of `risk_and_ruin`).
  - `cap_skips(result) -> dict` (`submitted`, `taken`, `notional_capped`, `notional_capped_share`, `heat_at_fill`, `skip_reasons`, `max_dd_pct`); `per_direction(arm, ref) -> list[dict]`; `risk_and_ruin(kept, risk_pct) -> dict` (`n`, `worst_day_r`, `max_open_positions`, `max_open_risk_pct`, `max_drawdown_r`, `p_ruin`, `max_dd_p95`).
  - `render_disclosures(d: dict) -> str` — Markdown; takes one cell's dict or the stage blob `{"window", "cells": [...], "touch": [...]}` (`touch`: V212-13b `clauses` dicts, each carrying `cell`). Always prints the literal words `D range` and `direction` (V212-16 greps them).
  - Constants `CAP_REASONS = ("heat", "sector", "cluster", "max_open")`, `RUIN_RUNS`, `RISK_ROWS`.

**Decisions fixed here** (spec § Pass rule, Disclosures; § The rule 7–8):
- **Heat at fill = the portfolio pass's cap skips** (signals dated at the fill, V212-13b): `skip_reasons` for `heat`, `sector`, `cluster`, `max_open`. **Notional share** = `notional_capped / (trades_taken + trades_skipped)` (the cut is counted before the capacity check, V212-12).
- **Risk and ruin** on each side's portfolio-kept rows: worst exit-day sum of R; the most positions open at one open (filled on or before the day, exiting on or after it) × `RISK_PER_TRADE_PCT`, printed as an upper bound because a notional cut carries less; `max_drawdown_r` in exit order; `ruin.simulate(..., n_trades=1000, n_paths=2000, seed=42)` `p_ruin` and `max_dd_p95`, `None` with no trades. The worst gap-through-stop R and its per-day clustering are V212-14's `adverse`.
- **Per-direction table** on the portfolio-kept rows, arm against reference (the pooled verdict stays pooled; this is the disclosure).
- `render_disclosures` prints every number with `n/a` for `None`, heads the block "printed, never gating", and takes JSON-loaded dicts (V212-16 reads the stage file).

- [ ] **Step 1: Append the failing tests** to `tests/backtesting/test_confluence_limit_disclosures.py`

```python
KEPT = {"arm": ARM[:3], "ref": REF,
        "arm_result": {"trades_taken": 3, "trades_skipped": 1, "max_dd_pct": 1.2,
                       "notional_capped": 1, "skip_reasons": {"heat": 1}},
        "ref_result": {"trades_taken": 5, "trades_skipped": 0, "max_dd_pct": 2.0,
                       "notional_capped": 0, "skip_reasons": {}}}


@pytest.fixture
def book():
    return cld.disclosures(ARM, REF, CENSUS, spy=SPY, earnings=EARNINGS, portfolio=KEPT)


def test_disclosures_assemble_every_section(book):
    assert book["cell"] == "f0.5"
    assert book["paired"] == cld.paired_delta(ARM, REF)
    assert book["scope"] == cld.scope_counts(CENSUS, "f0.5")
    assert book["adverse"] == cld.adverse(ARM) and book["atr"] == cld.by_atr(ARM)
    assert book["spy"] == cld.spy_days(ARM, SPY)
    assert book["earnings"] == cld.earnings_share(ARM, EARNINGS)
    assert book["alert_volume_per_day"] == cld.alert_volume_per_day(CENSUS, ARM)


def test_portfolio_skips_are_the_heat_at_fill_cancels(book):
    arm = book["portfolio"]["arm"]
    assert (arm["heat_at_fill"], arm["notional_capped_share"]) == (1, 0.25)
    assert (arm["submitted"], arm["taken"]) == (4, 3)
    assert book["portfolio"]["ref"]["heat_at_fill"] == 0
    reasons = {"heat": 1, "sector": 2, "cluster": 3, "max_open": 4, "one_per_ticker": 9}
    assert cld.cap_skips({"skip_reasons": reasons})["heat_at_fill"] == 10


def test_per_direction_and_risk(book):
    bull = book["per_direction"][0]
    assert (bull["direction"], bull["arm"]["n"], bull["ref"]["n"]) == ("bullish", 3, 5)
    assert bull["arm"]["wr"] == pytest.approx(100 / 3)
    assert book["per_direction"][1]["arm"] == {"n": 0, "expr": None, "wr": None}
    risk = book["risk"]["arm"]
    assert risk["worst_day_r"] == pytest.approx(-1.0)
    # 03-03: T0 (03-01..03-03), T1 (03-02..03-04) and T2 (03-03..03-05) all open
    assert (risk["max_open_positions"], risk["max_open_risk_pct"]) == (3, 3.0)
    assert risk["max_drawdown_r"] == pytest.approx(1.05)      # +2, then -1 and -0.05
    assert 0.0 <= risk["p_ruin"] <= 1.0


def test_empty_inputs_disclose_without_crashing():
    empty = {"arm": [], "ref": [], "arm_result": {}, "ref_result": {}}
    d = cld.disclosures([], [], [], spy={}, earnings={}, portfolio=empty)
    assert d["cell"] is None and d["paired"]["alerts"] == 0
    assert d["risk"]["arm"] == {"n": 0, "worst_day_r": None, "max_open_positions": 0,
                                "max_open_risk_pct": 0.0, "max_drawdown_r": None,
                                "p_ruin": None, "max_dd_p95": None}
    assert d["portfolio"]["arm"]["notional_capped_share"] is None
    assert "D range n/a" in cld.render_disclosures(d)


def test_render_prints_every_section_and_the_touch_sensitivity(book):
    text = cld.render_disclosures({"window": "train", "cells": [book],
                                   "touch": [{"cell": "f0.5", "n": 4, "ref_n": 5, "expr": 0.1,
                                              "ref_expr": 0.0, "wr": 50.0, "ref_wr": 60.0,
                                              "passes": False}]})
    for needle in ("## Disclosures (train", "### Cell f0.5", "D range 2.00%-5.00%",
                   "direction", "Paired per-alert", "Gap-through-stop", "Stop-run",
                   "ATR14%", "SPY down day", "Earnings", "Notional cap cut (arm)", "heat 1",
                   "Worst day R", "P(ruin)", "upper bound", "Touch-fill sensitivity", "n/a"):
        assert needle in text, needle
    assert "never gating" in text


def test_render_reads_a_json_round_trip(book):
    import json
    blob = json.loads(json.dumps({"window": "validation", "cells": [book], "touch": []}))
    assert cld.render_disclosures(blob) == cld.render_disclosures(
        {"window": "validation", "cells": [book]})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_limit_disclosures.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'disclosures'` (V212-14's 9 tests still pass).

- [ ] **Step 3: Extend the imports** of `swingbot/core/backtesting/confluence_limit_disclosures.py`

```python
from swingbot import config
from swingbot.core.analytics.risk_metrics import max_drawdown_r
from swingbot.core.edge import ruin
```

(added beside the `acceptance` import; the module docstring already names V212-14b.)

- [ ] **Step 4: Append the portfolio-and-risk section and `disclosures`**

```python
# --- portfolio pass, risk and ruin --------------------------------------------

CAP_REASONS = ("heat", "sector", "cluster", "max_open")
RUIN_RUNS = {"n_trades": 1000, "n_paths": 2000, "seed": 42}


def cap_skips(result) -> dict:
    """The portfolio pass's notional cuts and the fills a cap cancelled at
    fill (heat, sector, cluster, max open -- spec rule 8)."""
    reasons = dict(result.get("skip_reasons") or {})
    submitted = result.get("trades_taken", 0) + result.get("trades_skipped", 0)
    capped = result.get("notional_capped", 0)
    return {"submitted": submitted, "taken": result.get("trades_taken", 0),
            "notional_capped": capped, "notional_capped_share": _share(capped, submitted),
            "heat_at_fill": sum(reasons.get(k, 0) for k in CAP_REASONS),
            "skip_reasons": reasons, "max_dd_pct": result.get("max_dd_pct")}


def per_direction(arm, ref) -> list:
    return [{"direction": d, "arm": _stats([r for r in arm if r["direction"] == d]),
             "ref": _stats([r for r in ref if r["direction"] == d])} for d in DIRECTIONS]


def _max_open(rows) -> int:
    """Most positions open at one open: filled on or before the day and
    exiting on or after it."""
    spans = [(_day(r["fill_date"]), _day(r["exit_date"])) for r in rows]
    return max((sum(f <= day <= e for f, e in spans) for day, _ in spans), default=0)


def risk_and_ruin(kept, risk_pct) -> dict:
    closed = sorted(_closed(kept), key=lambda r: (_day(r["exit_date"]), r["key"]))
    rs = [float(r["r_net"]) for r in closed]
    by_day = defaultdict(float)
    for r in closed:
        by_day[_day(r["exit_date"])] += float(r["r_net"])
    sim = ruin.simulate(rs, risk_pct=risk_pct, **RUIN_RUNS) if rs else {}
    most = _max_open(closed)
    return {"n": len(rs), "worst_day_r": min(by_day.values(), default=None),
            "max_open_positions": most, "max_open_risk_pct": most * risk_pct,
            "max_drawdown_r": max_drawdown_r(rs), "p_ruin": sim.get("p_ruin"),
            "max_dd_p95": sim.get("max_dd_p95")}


def disclosures(arm_rows, ref_rows, census_rows, *, spy, earnings, portfolio) -> dict:
    """Every spec disclosure for one cell. Printed, never gating."""
    risk_pct = float(getattr(config, "RISK_PER_TRADE_PCT", 1.0))
    cell = next((r["arm"] for r in arm_rows), None)
    sides = ("arm", "ref")
    return {"cell": cell, "scope": scope_counts(census_rows, cell),
            "alert_volume_per_day": alert_volume_per_day(census_rows, arm_rows),
            "paired": paired_delta(arm_rows, ref_rows), "filled_dollars": filled_dollars(arm_rows),
            "adverse": adverse(arm_rows), "atr": by_atr(arm_rows),
            "spy": spy_days(arm_rows, spy), "earnings": earnings_share(arm_rows, earnings),
            "portfolio": {s: cap_skips(portfolio.get(f"{s}_result") or {}) for s in sides},
            "per_direction": per_direction(portfolio.get("arm", []), portfolio.get("ref", [])),
            "risk": {s: risk_and_ruin(portfolio.get(s, []), risk_pct) for s in sides}}
```

- [ ] **Step 5: Append the render section**

```python
# --- render ----------------------------------------------------------------------

RISK_ROWS = (("Worst day R", "worst_day_r", "+.3f"),
             ("Max open positions", "max_open_positions", "d"),
             ("Max open risk % (upper bound: notional cuts carry less)", "max_open_risk_pct", ".2f"),
             ("Max drawdown R", "max_drawdown_r", ".3f"), ("P(ruin)", "p_ruin", ".4f"),
             ("Drawdown p95 (bootstrap)", "max_dd_p95", ".3f"))


def _f(value, spec=".3f", suffix="") -> str:
    return "n/a" if value is None else f"{value:{spec}}{suffix}"


def _pct(share) -> str:
    return "n/a" if share is None else f"{100.0 * share:.1f}%"


def _table(header, rows) -> list:
    return ["", "| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(row) + " |" for row in rows)]


def _render_head(d) -> list:
    s, p, fd = d["scope"], d["paired"], d["filled_dollars"]
    lo_hi = "n/a" if s["d_range"] is None else f"{s['d_range'][0]:.2f}%-{s['d_range'][1]:.2f}%"
    risk = f"${RISK_DOLLARS:.0f}"
    return [f"### Cell {d['cell']}", "",
            f"- Scope: {s['in_scope']} in scope, drops {s['drops'] or 'none'}, {s['kept']} kept;"
            f" D range {lo_hi}",
            f"- Alert volume: {d['alert_volume_per_day']:.2f} orders per trading day",
            f"- Paired per-alert ΔR (unfilled and dropped = 0R): mean "
            f"{_f(p['mean_delta_r'], '+.3f')} over {p['alerts']} alerts, "
            f"{_pct(p['share_positive'])} positive",
            f"- Dollar P&L per alert at {risk} risk: arm {_f(p['dollar_per_alert_arm'], '+.2f')},"
            f" reference {_f(p['dollar_per_alert_ref'], '+.2f')}",
            f"- Filled trades at {risk} fixed risk: {fd['fills']} fills, total "
            f"{_f(fd['total'], '+.2f')}, per fill {_f(fd['per_fill'], '+.2f')}"]


def _render_adverse(d) -> list:
    a, s, e = d["adverse"], d["scope"], d["earnings"]
    return [f"- Effective stop from M on fills: {_f(a['effective_stop_from_m_pct'], '.2f', '%')};"
            f" stopped within 3 bars: {_pct(a['early_stop_share'])}; TP1 cancel binds "
            f"{_pct(s['tp1_cancel_share'])}, expiry binds {_pct(s['expiry_share'])}",
            f"- Gap-through-stop fills: {a['gap_stops']}, mean R {_f(a['gap_stop_mean_r'], '+.3f')},"
            f" worst R {_f(a['gap_stop_worst_r'], '+.3f')}; from L (pessimistic): mean "
            f"{_f(a['gap_stop_mean_r_from_limit'], '+.3f')}, worst "
            f"{_f(a['gap_stop_worst_r_from_limit'], '+.3f')}; most on one day "
            f"{a['gap_stop_max_per_day']}",
            f"- Stop-run: {_pct(a['wick_through_share'])} of stopped fills wicked through and "
            "closed back (never grounds to widen the buffer)",
            f"- Earnings inside the 3-bar window: {e['with_earnings']} of {e['fills']} fills "
            f"({_pct(e['share'])}); {e['tickers_without_calendar']} tickers without a calendar"]


def _render_caps(d) -> list:
    lines = []
    for side, label in (("arm", "arm"), ("ref", "reference")):
        c = d["portfolio"][side]
        reasons = ", ".join(f"{k} {c['skip_reasons'].get(k, 0)}" for k in CAP_REASONS)
        lines.append(f"- Notional cap cut ({label}): {c['notional_capped']} of {c['submitted']}"
                     f" ({_pct(c['notional_capped_share'])}); cancelled at fill by caps: "
                     f"{c['heat_at_fill']} ({reasons})")
    return lines


def _stat_cells(st) -> tuple:
    return str(st["n"]), _f(st["expr"], "+.3f"), _f(st["wr"], ".1f")


def _render_tables(d) -> list:
    atr = [(b["bucket"], str(b["alerts"]), str(b["fills"]), _pct(b["fill_rate"]),
            _f(b["expr"], "+.3f")) for b in d["atr"]]
    spy = [(name, *_stat_cells(d["spy"][key]))
           for key, name in (("down", "SPY down day (< -1%)"), ("other", "other days"))]
    dirs = [(x["direction"], *_stat_cells(x["arm"]), *_stat_cells(x["ref"]))
            for x in d["per_direction"]]
    return [*_table(("ATR14%", "alerts", "fills", "fill rate", "ExpR"), atr),
            *_table(("SPY day", "fills", "ExpR", "WR"), spy), "",
            f"Distinct fill days: {d['spy']['distinct_fill_days']} "
            f"(SPY missing on {d['spy']['spy_missing']} fills)",
            *_table(("direction", "arm n", "arm ExpR", "arm WR", "ref n", "ref ExpR", "ref WR"),
                    dirs)]


def _render_risk(d) -> list:
    arm, ref = d["risk"]["arm"], d["risk"]["ref"]
    rows = [(label, _f(arm[key], spec), _f(ref[key], spec)) for label, key, spec in RISK_ROWS]
    return _table(("risk and ruin", "arm", "reference"), rows)


def _render_touch(touch) -> list:
    rows = [(t["cell"], str(t["n"]), str(t["ref_n"]), _f(t["expr"], "+.3f"),
             _f(t["ref_expr"], "+.3f"), _f(t["wr"], ".1f"), _f(t["ref_wr"], ".1f"),
             "yes" if t["passes"] else "no") for t in touch]
    return ["", "### Touch-fill sensitivity (same clauses, never gating)",
            *_table(("cell", "n", "ref n", "ExpR", "ref ExpR", "WR", "ref WR", "passes"), rows)]


def render_disclosures(d: dict) -> str:
    """Markdown for the results doc: one cell's dict, or the stage blob."""
    blob = d if "cells" in d else {"cells": [d]}
    lines = [f"## Disclosures ({blob.get('window', 'window not named')}; printed, never gating)",
             ""]
    for cell in blob["cells"]:
        lines += [*_render_head(cell), *_render_adverse(cell), *_render_caps(cell),
                  *_render_tables(cell), *_render_risk(cell), ""]
    if blob.get("touch"):
        lines += _render_touch(blob["touch"])
    return "\n".join(lines) + "\n"
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_limit_disclosures.py`
Expected: PASS (15 tests).

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: PASS (`_render_tables` and `risk_and_ruin` are the busiest, both under 10).

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/backtesting/confluence_limit_disclosures.py tests/backtesting/test_confluence_limit_disclosures.py
git commit -m "feat(v212): disclosures part 2 -- cap skips, per-direction, risk and ruin, render (V212-14b)"
```
