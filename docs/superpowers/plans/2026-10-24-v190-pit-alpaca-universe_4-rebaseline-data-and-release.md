# v190 — Instrument v3 on the PIT Alpaca store: Implementation Plan, Part 4 — re-baseline report, data, release (V190-16..V190-25)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V190-18:" -A 200 <this file>`.

**Spec:** [2026-10-24-v190-pit-alpaca-universe-design.md](../specs/2026-10-24-v190-pit-alpaca-universe-design.md)
**Index:** [2026-10-24-v190-pit-alpaca-universe_0-index.md](2026-10-24-v190-pit-alpaca-universe_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Contracts`, `## Review Focus`, `## Parallelisation` and the task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: the re-baseline report script (V190-16); the docs and their Codex mirror (V190-17); then the data tasks, strictly in order — complete the member backfill (V190-18), the context pass (V190-19), the rename aliases (V190-20), calibrate and freeze `_integrity.json` (V190-21), the v3 coverage gate and smoke run (V190-22), legs A and B through `backtest-runner` (V190-23), the results doc and the ledger DESCRIPTION row (V190-24); and the release with the plan's single full-suite run and the merge (V190-25). `/close-out` follows V190-25.

Consumed from Parts 1–3 (exact names in the index's `## Contracts`): `resolve("v3")` with `store="pit"` and research `2017-01-01..2025-12-31` (V190-1); worktree-aware `history_store.store_root(store)` (V190-2); `training_data.provenance()` keys `store` (`"watchlist"` | `"pit"`) and `integrity_sha256` (V190-4); `run_backtest_range.py --instrument v3` (V190-6, V190-7); `check_cache_coverage.py --instrument v3 [--store-root PATH] [--out PATH]` (V190-9); `stats.INSTRUMENTS` with `"v3"`, `stats.VERDICTS` with `"DESCRIPTION"` and the rule that a DESCRIPTION row carries `p` = null (V190-10); `fetch_alpaca_history.py --universe sp500_pit --aliases PATH` and `aliases.load_aliases` (V190-12); `pit_coverage` and `reuse.THRESHOLDS` constants (V190-13, V190-14); `check_history_store.py --pit --root --backtest-dir --results-dir` writing `<root>/_integrity.json` (V190-15).

**Where work happens.** Code tasks (V190-16, V190-17, V190-25) edit the worktree `.claude/worktrees/2026-10-24-v190-pit-alpaca-universe`; every repo path below is relative to it. Data tasks (V190-18..V190-24) run their commands from the worktree but read and write the **main checkout's** git-ignored data by absolute path:

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
WT=$MAIN/.claude/worktrees/2026-10-24-v190-pit-alpaca-universe
PIT=$MAIN/data/market_data_pit
EXT=$MAIN/data/backtest_cache_ext
OUT=$MAIN/data/backtest_results/v190
```

Committed artefacts of data tasks (results docs, `data/universe/symbol_aliases.json`, the ledger row) are committed on the worktree branch, never on `main`. **Do not commit on `main`** until V190-25's merge step.

**Order is the reproducibility contract (spec §5):** integrity frozen (V190-21) → legs run (V190-23) → result recorded (V190-24). From V190-21 on, no `fetch_alpaca_history.py` in any mode touches `$PIT` or `$MAIN/data/market_data/`; `training_data.StaleIntegrityError` enforces it for the PIT store. No strategy result (WR, ExpR) is read before V190-21's freeze commit exists.

# Phase 1 — Re-baseline tooling and documentation

### Task V190-16: v190 re-baseline report script

**Model:** opus — statistical reporting whose population, MDE design and seeds are frozen by the spec; a wrong population or a verdict mark would be quoted later as evidence.

**Files:**
- Create: `scripts/reports/v190_rebaseline_report.py`
- Create: `tests/history_store/test_v190_rebaseline.py` (suite `history-store`, an existing directory)

**Interfaces:**
- Consumes: `stats.INSTRUMENTS` holding `"v3"`, `stats.VERDICTS` holding `"DESCRIPTION"`, `stats.validate_ledger_row` refusing a DESCRIPTION row with a non-null `p` (V190-10); `resolve("v3")` (V190-1: research `2017-01-01..2025-12-31`, `holdout_start="2026-01-01"`, folds 2021..2025, `embargo_days=270`, `purge=True`); provenance sidecar keys `store` and `integrity_sha256` (V190-4). Existing at HEAD: `training_data.provenance_path`, `acceptance.CLOSED`, `acceptance.cluster_bootstrap`, `acceptance._Z_ALPHA_ONE_SIDED`, `acceptance._Z_POWER`, `acceptance.ALPHA`, `acceptance_harvest.mde_expectancy_r`, `stats.week_cluster_bootstrap`, `stats.iso_week_key`, `stats.WEEK_BOOTSTRAP_SEED`, `stats.WEEK_BOOTSTRAP_RESAMPLES`, `folds.anchored_folds`, `folds.split_fold`, `pit_membership.normalize_symbol`, `universe.universe_symbols`.
- Produces (consumed by V190-24):
  - `LEG_NAMES = {"A": "v3, PIT S&P 500", "C": "v3, watchlist PIT members", "B": "v1, watchlist"}`, `STANDING_LINE = "describes an instrument change; never a lift; selects nothing"`, `TICKER_BOOTSTRAP_SEED = 190`, `LEDGER_ID = "v190-v3-rebaseline"`, `RECORD = "docs/superpowers/results/2026-10-v190-v3-rebaseline.md"`.
  - `leg_c(trades, watchlist, members) -> list[Trade]`; `power_columns(trades, *, seed=TICKER_BOOTSTRAP_SEED, n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES) -> dict`; `build_report(legs, provenance, *, folds, integrity_sha, integrity_doc, n_resamples=..., seed=...) -> dict`; `render_markdown(report) -> str`; `ledger_row(report, *, date) -> dict`.
  - CLI: `python scripts/reports/v190_rebaseline_report.py --leg "A=<glob or comma list>" --leg "B=<glob or comma list>" --watchlist FILE --integrity PATH/_integrity.json --json OUT.json --md OUT.md [--resamples N] [--date YYYY-MM-DD]`; exit 0 with a last stdout line `LEDGER ROW: <json>`; exit 1 with `error: ...` on stderr for any refused input.

Decisions this task freezes (spec §5, index Global Constraints):
- **Populations.** Legs A and C: the v3 **fold-train** population, the purged train side of the last anchored fold (`split_fold(trades, folds[-1], embargo_days=270, purge=True)[0]`, entries 2017-01-01..2024-12-31). That is the union of every fold's train side, the v3 analogue of v1's fold-train (2018-06..2022, the train side of the funnel's last Stage 2 fold). Leg B: every trade of its `--train` run (2020-01-01..2023-12-31). Fold-test N is printed separately, per fold, beside each fold's effective (purged) train N.
- **MDE.** The frozen formula is the unpaired `mde_expectancy_r` at the observed N. It is printed as `mde_r_formula` (its own ticker design effect, no seed), then twice with a bootstrap standing in for the design effect: `mde_r_ticker` and `mde_r_week` = `(z_a + z_b) * sqrt(2) * SE`, with SE the standard deviation of the leg's ExpR over cluster-bootstrap draws (`2 * var(r) / n_eff` with `n_eff = N / DEFF` equals `2 * SE**2`). Ticker draws use `TICKER_BOOTSTRAP_SEED = 190`; week draws use `stats.WEEK_BOOTSTRAP_SEED` and nothing else. Draws are vectorised from per-cluster sums (about 850 tickers × 10,000 resamples is too slow through the generic bootstraps); a test pins them equal to `acceptance.cluster_bootstrap` and `stats.week_cluster_bootstrap`, draw for draw.
- **Confluence.** `run_backtest_range.py --scenarios` (the confluence replay) is refused under every non-v1 instrument (`_V2_UNWIRED`, phase 5), so legs A and C carry no confluence rows. The report prints a fixed `CONFLUENCE_NOTE` saying so; a v1 figure never stands in.
- **No verdict marks.** No per-cell pass/fail, no significance mark, no comparison to 0.10R. The markdown's first body line is the standing line in italics; WR and ExpR sit under a heading that says "description only".

- [ ] **Step 1: Write the failing tests `tests/history_store/test_v190_rebaseline.py`**

```python
"""v190 V190-16: the describe-only v3 re-baseline report. Populations, power
columns (formula, ticker and week MDE with named seeds), leg C, provenance and
holdout checks, and a ledger row that validates as DESCRIPTION."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.acceptance_harvest import mde_expectancy_r
from swingbot.core.backtesting.instrument import folds, stats
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.marketdata import training_data

ROOT = Path(__file__).resolve().parents[2]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module   # a @dataclass resolves its module through sys.modules
    spec.loader.exec_module(module)
    return module


rep = _load("v190_rebaseline_report", "scripts/reports/v190_rebaseline_report.py")
FOLDS = folds.anchored_folds(resolve("v3"))
PROV_A = {"data_source": "alpaca", "store": "pit", "manifest_hash": "m-pit"}
PROV_B = {"data_source": "alpaca", "store": "watchlist", "manifest_hash": "m-wl"}


def _row(ticker, entry, *, r=1.0, outcome="win", strategy="RSI", hk="3m",
         direction="bullish", exit_=None):
    return {"ticker": ticker, "strategy": strategy, "horizon_key": hk, "direction": direction,
            "entry_date": entry, "exit_date": exit_ or entry, "outcome": outcome,
            "r_multiple": r, "entry": 10.0}


def _trades(rows):
    return [rep._trade(row, Path("x.jsonl")) for row in rows]


def _write_leg(tmp_path, name, rows, prov):
    path = tmp_path / f"{name}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    training_data.provenance_path(path).write_text(json.dumps(prov), encoding="utf-8")
    return path


def _integrity(tmp_path):
    untrimmed = {"keep_from": None, "keep_before": None, "reason": None}
    doc = {"schema": 1, "no_bars": ["FB"],
           "tickers": {"AAA": {"admitted": True, "reason": None, "signal_cuts": [],
                               "trim": untrimmed},
                       "MON": {"admitted": True, "reason": None,
                               "signal_cuts": [["2017-03-01", "2017-04-01", "missing run"]],
                               "trim": {"keep_from": None, "keep_before": "2018-06-08",
                                        "reason": "reused symbol"}},
                       "ZZZ": {"admitted": False, "reason": "flagged: price-mismatch",
                               "signal_cuts": [], "trim": untrimmed}}}
    path = tmp_path / "_integrity.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path, doc, hashlib.sha256(path.read_bytes()).hexdigest()


# --- parsing and leg C ------------------------------------------------------------------

def test_parse_leg_expands_a_glob_and_refuses_leg_c(tmp_path):
    for name in ("leg-A-rsi", "leg-A-macd"):
        (tmp_path / f"{name}.jsonl").write_text("", encoding="utf-8")
    label, files = rep.parse_leg(f"A={tmp_path}/leg-A-*.jsonl")
    assert label == "A" and [f.name for f in files] == ["leg-A-macd.jsonl", "leg-A-rsi.jsonl"]
    with pytest.raises(Exception, match="leg C is derived"):
        rep.parse_leg(f"C={tmp_path}/leg-A-rsi.jsonl")
    with pytest.raises(Exception):
        rep.parse_leg(f"A={tmp_path}/nothing-*.jsonl")


def test_leg_c_keeps_watchlist_tickers_that_are_pit_members_only():
    trades = _trades([_row("AAPL", "2019-01-02"), _row("BRK-B", "2019-01-02"),
                      _row("MON", "2017-02-01"), _row("PLTR", "2021-01-04")])
    kept = rep.leg_c(trades, watchlist=["aapl", "BRK.B", "PLTR"], members=["AAPL", "BRK.B", "MON"])
    assert [t.ticker for t in kept] == ["AAPL", "BRK-B"]
    assert rep.leg_c([], watchlist=["AAPL"], members=["AAPL"]) == []


def test_load_trades_drops_non_closed_rows_and_refuses_a_closed_row_without_r(tmp_path):
    path = _write_leg(tmp_path, "a", [_row("AAA", "2019-01-02"),
                                      _row("AAA", "2019-01-03", outcome="not_triggered", r=None)],
                      PROV_A)
    assert len(rep.load_trades([path])) == 1
    bad = _write_leg(tmp_path, "b", [_row("AAA", "2019-01-02", r=None)], PROV_A)
    with pytest.raises(ValueError, match="without r_multiple"):
        rep.load_trades([bad])


# --- provenance and windows -------------------------------------------------------------

def test_leg_a_provenance_must_be_the_pit_store(tmp_path):
    assert rep.load_provenance("A", [_write_leg(tmp_path, "a", [], PROV_A)])["store"] == "pit"
    with pytest.raises(ValueError, match="leg A.*pit"):
        rep.load_provenance("A", [_write_leg(tmp_path, "w", [], PROV_B)])


def test_an_old_sidecar_without_store_reads_as_the_watchlist_store(tmp_path):
    path = _write_leg(tmp_path, "b", [], {"data_source": "alpaca", "manifest_hash": "m"})
    assert rep.load_provenance("B", [path])["store"] == "watchlist"


def test_a_legs_files_must_share_one_provenance(tmp_path):
    one = _write_leg(tmp_path, "one", [], PROV_A)
    two = _write_leg(tmp_path, "two", [], {**PROV_A, "manifest_hash": "other"})
    with pytest.raises(ValueError, match="disagree"):
        rep.load_provenance("A", [one, two])


def test_leg_a_refuses_any_trade_that_reaches_the_holdout():
    rep.check_window("A", _trades([_row("AAA", "2025-12-20", exit_="2025-12-31")]))
    with pytest.raises(ValueError, match="holdout"):
        rep.check_window("A", _trades([_row("AAA", "2025-12-20", exit_="2026-01-02")]))
    with pytest.raises(ValueError, match="holdout"):
        rep.check_window("A", _trades([_row("AAA", "2026-01-05")]))


def test_leg_b_refuses_an_entry_outside_v1_train():
    rep.check_window("B", _trades([_row("AAA", "2020-01-02"), _row("AAA", "2023-12-29")]))
    with pytest.raises(ValueError, match="leg B"):
        rep.check_window("B", _trades([_row("AAA", "2024-01-02")]))


# --- populations ------------------------------------------------------------------------

def test_fold_train_is_the_purged_train_side_of_the_last_fold():
    trades = _trades([_row("AAA", "2017-02-01"),
                      _row("AAA", "2024-12-20", exit_="2025-01-06"),    # purged: overlaps 2025
                      _row("AAA", "2024-12-02", exit_="2024-12-20"),
                      _row("AAA", "2025-03-03")])                       # a test-year entry
    assert [t.entry_date for t in rep.fold_train(trades, FOLDS)] == ["2017-02-01", "2024-12-02"]
    assert rep.fold_train([], FOLDS) == []
    assert rep.fold_train(trades, ()) == []


def test_fold_rows_give_effective_train_n_and_test_n_for_each_of_five_folds():
    trades = _trades([_row("AAA", "2017-02-01"), _row("AAA", "2021-05-03"),
                      _row("AAA", "2020-12-28", exit_="2021-01-04"), _row("AAA", "2025-06-02")])
    rows = rep.fold_rows(trades, FOLDS)
    assert [r["test_year"] for r in rows] == [2021, 2022, 2023, 2024, 2025]
    assert (rows[0]["train_n"], rows[0]["test_n"]) == (1, 1)    # 2020-12-28 purged
    assert (rows[1]["train_n"], rows[1]["test_n"]) == (3, 0)
    assert (rows[4]["train_n"], rows[4]["test_n"]) == (3, 1)


# --- power columns ----------------------------------------------------------------------

def _population(n_tickers=6, per=12, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_tickers):
        for j in range(per):
            r = float(rng.normal(0.05, 1.0))
            rows.append(_row(f"T{i}", f"2019-{1 + j:02d}-{1 + 2 * i:02d}", r=r,
                             outcome="win" if r > 0 else "loss"))
    return _trades(rows)


def _mean(base, _comp):
    return float(np.mean([t.r_multiple for t in base])) if base else None


def test_vectorised_draws_equal_the_library_bootstraps_draw_for_draw():
    trades = _population()
    ticker = acceptance.cluster_bootstrap(trades, [], _mean, n_resamples=200, seed=190)
    week = stats.week_cluster_bootstrap(trades, [], _mean, n_resamples=200, seed=42)
    assert rep.cluster_draws(trades, rep.by_ticker, n_resamples=200, seed=190) == \
        pytest.approx(ticker, rel=1e-9)
    assert rep.cluster_draws(trades, rep.by_week, n_resamples=200, seed=42) == \
        pytest.approx(week, rel=1e-9)
    assert rep.cluster_draws([], rep.by_ticker, n_resamples=10, seed=1).size == 0


def test_power_columns_name_both_seeds_and_carry_the_frozen_formula():
    trades = _population()
    cols = rep.power_columns(trades, n_resamples=300)
    assert cols["n"] == 72 and cols["tickers"] == 6
    assert (cols["ticker_seed"], cols["week_seed"]) == (190, stats.WEEK_BOOTSTRAP_SEED)
    assert cols["mde_r_formula"] == pytest.approx(mde_expectancy_r(trades, target_n=72))
    z = acceptance._Z_ALPHA_ONE_SIDED[acceptance.ALPHA] + acceptance._Z_POWER[0.80]
    draws = rep.cluster_draws(trades, rep.by_ticker, n_resamples=300, seed=190)
    assert cols["mde_r_ticker"] == pytest.approx(z * np.sqrt(2.0) * np.std(draws, ddof=1))
    assert cols["mde_r_week"] > 0


def test_power_columns_on_an_empty_population():
    cols = rep.power_columns([], n_resamples=50)
    assert cols["n"] == 0 and cols["tickers"] == 0
    assert cols["mde_r_formula"] is None and cols["mde_r_ticker"] is None
    assert cols["mde_r_week"] is None


# --- concentration and cells ------------------------------------------------------------

def test_concentration_reports_the_top_two_horizons_share_of_n_and_r():
    trades = _trades([_row("A", "2019-01-02", hk="3m"), _row("A", "2019-01-03", hk="3m"),
                      _row("A", "2019-01-04", hk="1m", r=-1.0, outcome="loss"),
                      _row("A", "2019-01-07", hk="6m", r=2.0)])
    out = rep.concentration(trades)
    assert out["top_horizons"] == ["3m", "1m"]
    assert out["n_share"] == pytest.approx(0.75)
    assert out["r_share"] == pytest.approx(1.0 / 3.0)
    assert rep.concentration([])["r_share"] is None


def test_cells_count_strategies_directions_horizons_and_legs():
    legs = {"A": _trades([_row("A", "2019-01-02"),
                          _row("A", "2019-01-02", strategy="MACD", direction="bearish")]),
            "B": _trades([_row("A", "2020-01-02", hk="1m")]), "C": []}
    cells = rep.cells(legs)
    assert (cells["strategies"], cells["directions"], cells["horizons"], cells["legs"]) == (2, 2, 2, 3)
    assert cells["product"] == 24 and cells["non_empty"] == 3


# --- report, markdown, ledger -----------------------------------------------------------

def _report(tmp_path, *, sha=None):
    _path, doc, real_sha = _integrity(tmp_path)
    a = _trades([_row("AAA", "2018-03-01"), _row("MON", "2017-05-01", r=-1.0, outcome="loss"),
                 _row("AAPL", "2022-02-01"), _row("AAA", "2025-02-03")])
    b = _trades([_row("AAPL", "2021-03-01", r=0.5)])
    legs = {"A": a, "B": b, "C": rep.leg_c(a, ["AAPL"], ["AAPL", "AAA", "MON"])}
    prov = {"A": {**PROV_A, "integrity_sha256": real_sha}, "B": PROV_B}
    return rep.build_report(legs, prov, folds=FOLDS, integrity_sha=sha or real_sha,
                            integrity_doc=doc, n_resamples=50)


def test_build_report_names_populations_ratios_and_coverage(tmp_path):
    report = _report(tmp_path)
    assert report["standing_line"] == rep.STANDING_LINE
    assert report["legs"]["A"]["population"] == "fold-train 2017-01-01..2024-12-31 (purged)"
    assert report["legs"]["A"]["power"]["n"] == 3 and report["legs"]["C"]["power"]["n"] == 1
    assert report["legs"]["B"]["population"] == "TRAIN 2020-01-01..2023-12-31"
    assert report["ratios"] == {"A/B": 3.0, "C/B": 1.0}
    assert report["coverage"] == {"tickers": 3, "admitted": 2,
                                  "excluded": {"flagged: price-mismatch": 1},
                                  "no_bars": 1, "trimmed": 1, "with_signal_cuts": 1}
    assert report["legs"]["A"]["first_counted"] == {"RSI": "2017-05-01"}
    assert [f["test_year"] for f in report["legs"]["A"]["folds"]] == [2021, 2022, 2023, 2024, 2025]
    assert report["legs"]["B"]["folds"] == []
    assert report["seeds"] == {"ticker": 190, "week": stats.WEEK_BOOTSTRAP_SEED}


def test_build_report_refuses_a_leg_a_run_on_another_integrity_freeze(tmp_path):
    with pytest.raises(ValueError, match="integrity"):
        _report(tmp_path, sha="0" * 64)


def test_markdown_leads_with_the_standing_line_and_carries_no_verdict_mark(tmp_path):
    md = rep.render_markdown(_report(tmp_path))
    assert md.splitlines()[2] == f"*{rep.STANDING_LINE}*"
    assert rep.IN_SAMPLE_NOTE in md and rep.CONFLUENCE_NOTE in md and rep.COST_NOTE in md
    for mark in ("PASS", "FAIL", "significant", "0.10R"):
        assert mark not in md
    assert "description only" in md


def test_ledger_row_validates_as_a_description_row(tmp_path):
    row = rep.ledger_row(_report(tmp_path), date="2026-11-02")
    stats.validate_ledger_row(row)
    assert (row["id"], row["instrument"], row["verdict"]) == ("v190-v3-rebaseline", "v3", "DESCRIPTION")
    assert row["p"] is None and row["exp_r"] is None and row["n"] == 3
    assert row["record"] == rep.RECORD and row["data_source"] == "alpaca"
    assert rep.STANDING_LINE in row["hypothesis"]


def test_main_writes_json_and_markdown_and_prints_the_ledger_row(tmp_path, monkeypatch, capsys):
    path, _doc, sha = _integrity(tmp_path)
    a = _write_leg(tmp_path, "leg-A-rsi", [_row("AAA", "2018-03-01"), _row("AAPL", "2019-03-01")],
                   {**PROV_A, "integrity_sha256": sha})
    b = _write_leg(tmp_path, "leg-B-rsi", [_row("AAPL", "2021-03-01")], PROV_B)
    watch = tmp_path / "watchlist.txt"
    watch.write_text("AAPL\n# comment\nPLTR\n", encoding="utf-8")
    monkeypatch.setattr(rep, "universe_symbols", lambda name: ["AAA", "AAPL"])
    out_json, out_md = tmp_path / "r.json", tmp_path / "r.md"
    code = rep.main(["--leg", f"A={a}", "--leg", f"B={b}", "--watchlist", str(watch),
                     "--integrity", str(path), "--json", str(out_json), "--md", str(out_md),
                     "--resamples", "50", "--date", "2026-11-02"])
    assert code == 0
    assert json.loads(out_json.read_text(encoding="utf-8"))["legs"]["C"]["power"]["n"] == 1
    assert out_md.read_text(encoding="utf-8").startswith("# ")
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("LEDGER ROW: ")
    stats.validate_ledger_row(json.loads(last[len("LEDGER ROW: "):]))


def test_main_exits_1_on_a_refused_input(tmp_path, capsys):
    path, _doc, _sha = _integrity(tmp_path)
    a = _write_leg(tmp_path, "leg-A-rsi", [], PROV_B)          # wrong store for leg A
    b = _write_leg(tmp_path, "leg-B-rsi", [], PROV_B)
    watch = tmp_path / "w.txt"
    watch.write_text("AAPL\n", encoding="utf-8")
    code = rep.main(["--leg", f"A={a}", "--leg", f"B={b}", "--watchlist", str(watch),
                     "--integrity", str(path), "--json", str(tmp_path / "r.json"),
                     "--md", str(tmp_path / "r.md")])
    assert code == 1 and "error:" in capsys.readouterr().err
```

- [ ] **Step 2: Run the file and confirm it fails**

Run: `python scripts/dev/testrun.py file tests/history_store/test_v190_rebaseline.py`
Expected: collection error — `FileNotFoundError` for `scripts/reports/v190_rebaseline_report.py`.

- [ ] **Step 3: Write `scripts/reports/v190_rebaseline_report.py`**

Head of the module, verbatim:

```python
"""v190 §5: the describe-only re-baseline of instrument v3.

Legs (each one or more `run_backtest_range.py --trades-jsonl` files with their
`<file>.provenance.json` sidecar):
  A  --instrument v3 (PIT S&P 500 on the PIT Alpaca store)
  B  --instrument v1 --train on the watchlist store (what the funnel runs today)
  C  leg A's trades on the watchlist tickers that are PIT members (no second run:
     v3 refuses --tickers-file, like v2)
Power columns (N, the A/B and C/B ratios, coverage, first counted dates, MDE) are
the only figures a later spec may cite. WR and ExpR are description only. These
numbers describe an instrument change; never a lift; selects nothing.

  python scripts/reports/v190_rebaseline_report.py --leg "A=OUT/leg-A-*.jsonl" \\
      --leg "B=OUT/leg-B-*.jsonl" --watchlist OUT/watchlist.txt \\
      --integrity data/market_data_pit/_integrity.json --json r.json --md r.md
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting import acceptance  # noqa: E402
from swingbot.core.backtesting.acceptance_harvest import mde_expectancy_r  # noqa: E402
from swingbot.core.backtesting.instrument import folds as folds_mod, stats  # noqa: E402
from swingbot.core.backtesting.instrument.contract import resolve  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402
from swingbot.core.marketdata.pit_membership import normalize_symbol  # noqa: E402
from swingbot.core.marketdata.universe import universe_symbols  # noqa: E402

LEG_NAMES = {"A": "v3, PIT S&P 500", "C": "v3, watchlist PIT members", "B": "v1, watchlist"}
LEG_INSTRUMENT = {"A": "v3", "C": "v3", "B": "v1"}
LEG_STORE = {"A": "pit", "B": "watchlist"}
STANDING_LINE = "describes an instrument change; never a lift; selects nothing"
IN_SAMPLE_NOTE = ("Every v3 fold is in-sample or tainted for today's strategies: test years "
                  "2021-2023 lie inside v1 TRAIN, which tuned every live setting, and 2024-2025 "
                  "is v1 VALIDATION. No out-of-fold figure below is out-of-sample, and the 2021 "
                  "fold has a little under four effective training years (the regime gate's "
                  "~320-bar warm-up eats into 2017).")
CONFLUENCE_NOTE = ("Confluence is not measured on legs A and C: run_backtest_range --scenarios "
                   "is refused under every non-v1 instrument (scan replay is unwired there). "
                   "No v1 figure stands in for it.")
COST_NOTE = ("Leg B uses the v1 cost model (zero commission and financing); legs A and C use "
             "v2/v3 fills and costs. WR and ExpR across legs are not like for like.")
TICKER_BOOTSTRAP_SEED = 190   # the ticker design's own seed; WEEK_BOOTSTRAP_SEED is the week design's
LEDGER_ID = "v190-v3-rebaseline"
RECORD = "docs/superpowers/results/2026-10-v190-v3-rebaseline.md"
CLOSED = acceptance.CLOSED
V1, V3 = resolve("v1"), resolve("v3")


@dataclass(frozen=True)
class Trade:
    ticker: str
    strategy: str
    horizon_key: str
    direction: str
    entry_date: str
    exit_date: str | None
    outcome: str
    r_multiple: float
```

Then these functions, in this order, each under complexity 15:

- `parse_leg(text) -> tuple[str, list[Path]]`: split at the first `=`; the label, upper-cased, must be `"A"` or `"B"`, else `argparse.ArgumentTypeError(f"--leg wants A|B=PATH[,PATH...] (leg C is derived from A), got {text!r}")`; a comma part containing `*` expands through `sorted(glob.glob(part))`, others are taken as given; an empty file list raises the same error.
- `_trade(row, path) -> Trade` and `load_trades(paths) -> list[Trade]`: as `v162_rebaseline_report._trade` / `load_trades` (a row whose `outcome` is outside `CLOSED` is dropped; a closed row with `r_multiple` None raises `ValueError(f"{path}: closed trade without r_multiple ({ticker} {entry_date})")`); `entry_date` and `exit_date` cut to `[:10]`; a None `exit_date` stays None; `direction` read with `row.get("direction") or ""`.
- `load_provenance(label, paths) -> dict`: each sidecar read through `training_data.provenance_path` (missing → `ValueError` naming the file); unequal sidecars → `ValueError(f"leg {label}: its files disagree on provenance")`; `data_source` must be `"alpaca"`; `prov.setdefault("store", "watchlist")` (a pre-v190 sidecar is the watchlist store); `prov["store"] != LEG_STORE[label]` → `ValueError(f"leg {label} must read the {LEG_STORE[label]} store, its sidecar says {prov['store']!r}")`.
- `check_window(label, trades) -> None`: leg A — with `lo, hi = V3.research_span`, any entry outside `lo..hi` or any non-None `exit_date >= V3.holdout_start` raises `ValueError(f"leg A: {n} trade(s) reach the sealed holdout or leave the research span, first {ticker} {entry_date}")`; leg B — any entry outside `V1.train_window` raises `ValueError(f"leg B: {n} trade(s) outside TRAIN ...")`.
- `leg_c(trades, watchlist, members) -> list[Trade]`: `keep = {normalize_symbol(s) for s in watchlist} & {normalize_symbol(s) for s in members}`; returns, in input order, the trades with `normalize_symbol(t.ticker) in keep`.
- `by_ticker(trade) -> str` (`trade.ticker`) and `by_week(trade) -> str` (`stats.iso_week_key(trade.entry_date)`).
- `cluster_draws` — verbatim:

```python
def cluster_draws(trades, key, *, n_resamples: int, seed: int) -> np.ndarray:
    """ExpR over cluster-bootstrap draws, vectorised from per-cluster sums. Same
    cluster order (sorted) and the same rng call as acceptance.cluster_bootstrap /
    stats.week_cluster_bootstrap, so the draws equal theirs draw for draw."""
    sums: dict[str, float] = defaultdict(float)
    counts: Counter = Counter()
    for trade in trades:
        sums[key(trade)] += trade.r_multiple
        counts[key(trade)] += 1
    names = sorted(counts)
    if not names:
        return np.array([])
    s = np.array([sums[n] for n in names])
    c = np.array([counts[n] for n in names], dtype=float)
    picks = np.random.default_rng(seed).integers(0, len(names), size=(n_resamples, len(names)))
    return s[picks].sum(axis=1) / c[picks].sum(axis=1)
```

- `_mde_from_draws(draws) -> float | None`: None when `draws.size < 2`; else `z * np.sqrt(2.0) * np.std(draws, ddof=1)` with `z = acceptance._Z_ALPHA_ONE_SIDED[acceptance.ALPHA] + acceptance._Z_POWER[0.80]`.
- `power_columns(trades, *, seed=TICKER_BOOTSTRAP_SEED, n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES) -> dict`: keys `n`, `tickers`, `weeks`, `mde_r_formula` (`mde_expectancy_r(trades, target_n=len(trades))`; None when empty), `mde_r_ticker` (`by_ticker` draws at `seed`), `mde_r_week` (`by_week` draws at `stats.WEEK_BOOTSTRAP_SEED`, always), `ticker_seed`, `week_seed`, `n_resamples`.
- `describe(trades) -> dict`: `n`, `n_eval` (win + loss), `win_rate` (percent wins over win + loss; None when none), `expectancy_r` (mean R; None when empty) — `v162_rebaseline_report.leg_stats` arithmetic.
- `first_counted(trades) -> dict[str, str]`: earliest `entry_date` per strategy, keys sorted.
- `by_year(trades) -> dict[str, dict]`: `describe` per entry year string, keys sorted.
- `fold_train(trades, folds) -> list[Trade]`: `[]` when `folds` is empty; else `folds_mod.split_fold(trades, folds[-1], embargo_days=V3.embargo_days, purge=V3.purge)[0]`.
- `fold_rows(trades, folds) -> list[dict]`: per fold `{"test_year", "train_n", "test_n", "test": describe(test)}` from the same `split_fold` call.
- `concentration(trades) -> dict`: horizons ranked by N descending, ties by name; `top_horizons` = the first two; `n_share` = their N over N (None when empty); `r_share` = their summed R over the total summed R (None when empty or the total is 0).
- `cells(legs) -> dict`: distinct strategies, directions and horizons over every leg's trades, `legs = len(legs)`, `product` of the four counts, `non_empty` = distinct `(leg, strategy, direction, horizon_key)` with at least one trade.
- `coverage_summary(doc) -> dict`: `tickers` (`len(doc["tickers"])`), `admitted`, `excluded` (`dict(sorted(Counter(reason of every non-admitted).items()))`), `no_bars` (`len(doc.get("no_bars") or [])`), `trimmed` (entries whose `trim` has `keep_from` or `keep_before`), `with_signal_cuts`.
- `_leg_block(label, trades, prov, folds, *, n_resamples, seed) -> dict`: A and C — population `fold_train(trades, folds)`, label `f"fold-train {V3.research_start}..{folds[-1].train_end} (purged)"`, `folds` = `fold_rows(trades, folds)`; B — population every trade, label `f"TRAIN {V1.train_window[0]}..{V1.train_window[1]}"`, `folds` = `[]`. Keys: `name`, `instrument`, `population`, `power`, `describe` (population), `describe_all` (every trade), `first_counted`, `by_year`, `folds`, `concentration`, `tickers_traded`, `provenance` (leg C carries leg A's).
- `build_report(legs, provenance, *, folds, integrity_sha, integrity_doc, n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES, seed=TICKER_BOOTSTRAP_SEED) -> dict`: `check_window("A", ...)` and `check_window("B", ...)` first (C is a subset of A); `provenance["A"].get("integrity_sha256") != integrity_sha` → `ValueError(f"leg A ran on another integrity freeze: sidecar {...} vs --integrity {...}")`; returns `standing_line`, `in_sample_note`, `confluence_note`, `cost_note`, `integrity_sha256`, `coverage`, `cells`, `legs` (A, C, B in that order), `ratios` (`{"A/B": nA / nB, "C/B": nC / nB}` on the population N, None when `nB == 0`), `seeds` (`{"ticker": seed, "week": stats.WEEK_BOOTSTRAP_SEED}`), `n_resamples`.
- `render_markdown(report) -> str`: line 0 `# v190 re-baseline: instrument v3`, line 1 blank, line 2 `*<STANDING_LINE>*`; then `IN_SAMPLE_NOTE`, `CONFLUENCE_NOTE` and `COST_NOTE` as paragraphs; `## Power (citable)` — one row per leg A, C, B (population, N, tickers, `mde_r_formula`, `mde_r_ticker` with its seed, `mde_r_week` with its seed), the A/B and C/B ratios, the sentence `cells: S strategies × D directions × H horizons × L legs = P (N non-empty)`, the coverage block and the first-counted table; `## Folds (legs A and C)` — test year, effective fold-train N, fold-test N; `## WR and ExpR (description only)` — per leg (population and all trades), per year, per fold test side, and the top-two-horizon shares. Formats: `+.3f` for R, `.1f` for percent, `n/a` for None. No words of judgement anywhere.
- `ledger_row(report, *, date) -> dict`: `{"id": LEDGER_ID, "date": date, "hypothesis": f"Instrument v3 re-baseline (PIT S&P 500 on Alpaca bars, research 2017-2025): {STANDING_LINE}", "instrument": "v3", "n": report["legs"]["A"]["power"]["n"], "exp_r": None, "p": None, "verdict": "DESCRIPTION", "record": RECORD, "data_source": "alpaca"}`, passed through `stats.validate_ledger_row` before it is returned.
- `read_watchlist(path) -> list[str]`: upper-cased non-blank lines with `#` comments stripped.
- `parse_args(argv)`: `--leg` (`type=parse_leg`, `action="append"`, required), `--watchlist`, `--integrity`, `--json`, `--md` (all `type=Path`, required), `--resamples` (int, default `stats.WEEK_BOOTSTRAP_RESAMPLES`), `--date` (default `date.today().isoformat()`); `ap.error` unless the labels are exactly `A` and `B`, once each.
- `main` — verbatim:

```python
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        files = dict(args.leg)
        legs = {label: load_trades(paths) for label, paths in files.items()}
        provenance = {label: load_provenance(label, paths) for label, paths in files.items()}
        raw = args.integrity.read_bytes()
        legs["C"] = leg_c(legs["A"], read_watchlist(args.watchlist), universe_symbols("sp500_pit"))
        report = build_report(legs, provenance, folds=folds_mod.anchored_folds(V3),
                              integrity_sha=hashlib.sha256(raw).hexdigest(),
                              integrity_doc=json.loads(raw), n_resamples=args.resamples)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    markdown = render_markdown(report)
    args.md.write_text(markdown, encoding="utf-8")
    print(markdown)
    print("LEDGER ROW: " + json.dumps(ledger_row(report, date=args.date)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and the complexity gate**

Run:
```bash
python scripts/dev/testrun.py file tests/history_store/test_v190_rebaseline.py
python scripts/dev/testrun.py file tests/history_store/test_rebaseline.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`, `0 xfailed` in both files (v162's report is untouched); the gate exits 0, every new function below 15.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/v190_rebaseline_report.py tests/history_store/test_v190_rebaseline.py
git commit -m "feat(reports): v190 V190-16 -- describe-only v3 re-baseline report: fold-train population, formula/ticker/week MDE with named seeds, leg C, DESCRIPTION ledger row"
```

### Task V190-17: Docs: methodology § Windows v3, known-traps, architecture, AGENTS.md

**Model:** haiku — prose insertions whose wording is fixed below, checked by the existing doc guards.

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (§ Windows: one bullet appended)
- Modify: `docs/claude/known-traps.md` (§ Two OHLCV caches: one bullet inserted after "Which data a backtest reads is one switch (v162)")
- Modify: `docs/claude/architecture.md` (the `core/marketdata/` sentence in the package list, lines 17-19)
- Modify: `AGENTS.md` (the "Training data (v162)" paragraph, about line 159)

**Interfaces:**
- Consumes: what V190-2 (`store_root(store)`, `resolve_data_root`), V190-3 (`pit_integrity.py`, frame trims), V190-4 (`select(name, store, until)`, `StaleIntegrityError`, `_pit_exclusions`), V190-6 (`apply_data_source` choosing the store from the instrument), V190-7 (signal cuts through `_membership_for_run`), V190-11 (`V3_FUNNEL_REFUSAL`), V190-12 (`--universe sp500_pit`, `symbol_aliases.json`) and V190-15 (`check_history_store.py --pit`) built. Read each one's committed code before writing if a sentence below no longer matches it; the sentence follows the code.
- Produces: nothing a later task reads.

Each `docs/claude/*.md` edit ships its `AGENTS.md` condensed mirror in the same commit (`tests/hooks/test_codex_mirror.py`).

- [ ] **Step 1: Append the v3 bullet to `docs/claude/backtest-methodology.md` § Windows**

After the "A new data source resets no budget (v162)" bullet:

```markdown
- **Instrument v3 (v190): the PIT S&P 500 on Alpaca bars.** `--instrument v3`
  is v2's contract (fills, costs, causal liquidity floor, PIT masking, purge,
  270-day embargo, holdout guard) on the PIT Alpaca store
  `data/market_data_pit/`: warm-up from 2016-01-04, research
  2017-01-01..2025-12-31 on five purged anchored yearly folds (test years
  2021–2025, `MIN_TRAIN_YEARS = 4` unchanged), holdout from 2026-01-01. Three
  rules come with it. **Every v3 fold is in-sample or tainted for every
  strategy, filter or knob that exists today:** 2021–2023 lie inside v1 TRAIN,
  which tuned them, and 2024–2025 is v1 VALIDATION; out-of-fold figures are
  never read as out-of-sample, and a component whose v1 VALIDATION shot is
  spent gets no gating use of the 2024 or 2025 folds. **The 2026 holdout
  budget is shared by v2 and v3:** a 2026 shot spent under one is spent under
  the other, and the v104 Part A retries keep their frozen 74-ticker universe.
  **The funnel does not accept v3 yet:** `validate_component.py --instrument
  v3` exits with `V3_FUNNEL_REFUSAL` until a methodology spec maps Stage 2
  and Stage 3 to five folds (on five folds "2 improving" would be looser than
  "2 of 3"). The v190 re-baseline
  (`docs/superpowers/results/2026-10-v190-v3-rebaseline.md`, ledger row
  `v190-v3-rebaseline`, verdict `DESCRIPTION`) describes an instrument
  change; never a lift; selects nothing. A later spec may cite only its power
  columns (N, the A/B and C/B ratios, coverage, first counted date, MDE),
  never its WR or ExpR, and any v3 badge rule is frozen before that table is
  read or is scored on the 2026 holdout alone. The default instrument stays
  `v1`, and no closed pre-registration re-runs on v3.
```

- [ ] **Step 2: Insert the PIT-store bullet in `docs/claude/known-traps.md` § Two OHLCV caches**

Directly after the "Which data a backtest reads is one switch (v162)" bullet:

```markdown
- **The PIT Alpaca store is a fourth directory, chosen only by instrument v3
  (v190).** `data/market_data_pit/{daily,hourly,15min}/{TICKER}.csv` has the
  v162 store's layout and manifests, holds every `sp500_pit` member (delisted
  names included) from 2016-01-04 plus SPY, the regime ticker and every
  `data/universe/etfs.json` symbol, and lives on this laptop only (never the
  VM, no cron). `history_store.store_root("pit")` never reads
  `HISTORY_STORE_DIR`; `store_root()` (the watchlist store) still does. **No
  universe name and no environment variable selects it:** `sp500_pit` is v2's
  universe too, and `training_data.available_tickers()` feeds about a dozen
  scripts their universe, so a store chosen by name would widen them. Only
  `contract.resolve("v3").store == "pit"` selects it, inside
  `fetch_backtest_data.apply_data_source`, which also cuts every frame
  (SPY and the ETFs included) at `research_end`; pool workers receive the
  choice through `training_data.selection_args()`. **Integrity before use:**
  `scripts/data/check_history_store.py --pit` writes
  `data/market_data_pit/_integrity.json`; selection refuses without it and
  raises `StaleIntegrityError` once the daily manifest's sha256 differs from
  the one frozen in it, so a `--mode update` after a freeze stops every v3 run
  until the report is rebuilt. It carries **frame trims** (a reused symbol's
  foreign bars, MON after mid-2018, removed in `history_store.load` before
  any indicator reads them) and **signal-date cuts** (runs of more than 5
  missing sessions; dates whose trailing 60 sessions hold under 95% of their
  bars), subtracted from the membership spans. `flagged: no-reference` is
  admitted on the PIT store only; the watchlist store's `_manifest_exclusions`
  is unchanged. Renamed members map through `data/universe/symbol_aliases.json`
  (`fetch_alpaca_history.py --universe sp500_pit`). **One fetcher per root at
  a time:** each process rewrites the whole per-timeframe manifest, so two on
  one root lose each other's entries. **Worktrees:** both store roots resolve
  through `history_store.resolve_data_root`, so a worktree without its own
  `data/market_data[_pit]` reads the main checkout's; a directory that exists
  in the worktree wins.
```

- [ ] **Step 3: Extend the `core/marketdata/` sentence in `docs/claude/architecture.md`**

Replace `(fetching and caching: both OHLCV caches, the v162 Alpaca history store` / `` `history_store.py` and the training-data switch `training_data.py`) `` with:

```markdown
(fetching and caching: both OHLCV caches, the v162 Alpaca history store
  `history_store.py`, the training-data switch `training_data.py`, and since
  v190 the PIT store's integrity reader `pit_integrity.py`; instrument v3
  selects that store through `training_data.select(name, store, until)`)
```

keeping the line wrap and indentation of the surrounding list.

- [ ] **Step 4: Mirror both in `AGENTS.md`**

Append to the "Training data (v162)" paragraph, before its `Detail:` sentence:

```markdown
`--instrument v3` (v190) alone reads the PIT Alpaca store `data/market_data_pit/`
(every S&P member from 2016, local only); no universe name or variable selects it,
it refuses without a fresh `_integrity.json`, and one fetcher runs per store root.
v3's folds are in-sample or tainted for today's strategies, the 2026 holdout is
shared with v2, and `validate_component.py` refuses v3 until a methodology spec
maps its stages.
```

- [ ] **Step 5: Run the doc guards**

Run:
```bash
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py
python scripts/dev/testrun.py file tests/hooks/test_guardrails.py
python scripts/dev/doc_section.py docs/claude/backtest-methodology.md "Windows"
```
Expected: `0 failed`, `0 xfailed` in all three; the last command prints § Windows ending with the v3 bullet.

- [ ] **Step 6: Commit (docs and mirror together)**

```bash
git add docs/claude/backtest-methodology.md docs/claude/known-traps.md docs/claude/architecture.md AGENTS.md
git commit -m "docs: v190 V190-17 -- instrument v3 in methodology Windows; the PIT store, its integrity seam and worktree resolution in known-traps; AGENTS.md mirror"
```

# Phase 2 — Data: complete the PIT store and freeze its integrity

Every step below runs from `$WT` with the variables from the header of this part. No step prints, echoes or logs `.env` values; the fetcher loads the Alpaca key itself. The fetcher refuses to start during the US regular session (09:30–16:00 ET, 15:30–22:00 Berlin in summer time; compute Berlin from `date -u`, Git Bash has no timezone data) — start passes outside it, and a pass stopped by the guard or a kill resumes by re-running the same command.

### Task V190-18: Wait for the member backfill; verify and complete it

**Model:** sonnet — long-running data operation with a fixed checklist; the judgement calls (re-fetching fallback-derived identities) are spelled out below.

**Files:**
- Data only: the main checkout's `data/market_data_pit/{daily,hourly,15min}/` (git-ignored)
- Create: `docs/superpowers/results/2026-10-v190-pit-backfill-log.md`

**Interfaces:**
- Consumes: `fetch_alpaca_history.py --universe sp500_pit --root --backtest-dir --timeframes --tickers --force` (V190-12: `--universe` sets no identity fallback; `--tickers` beside it is the list); `store_io.is_complete(entry, start)`; `universe.universe_symbols("sp500_pit")`; `data_store.safe_symbol`.
- Produces (consumed by V190-19..V190-21): every `sp500_pit` member present in the daily, hourly and 15min manifests of `$PIT`, each `ok` entry complete; the backfill log with every command, its UTC start and end, and its summary line.

Status at plan time (2026-10-24): only `$PIT/daily/_manifest.json` exists, 362 of 848 members in it (242 `ok`, 81 `flagged: no-reference`, 21 `flagged: price-mismatch`, 18 `skipped: no Alpaca bars`). That backfill was started before `--universe` existed, so it may have used the root `market_data/daily` identity fallback the spec forbids on this store (§2.2); Step 4 repairs exactly that.

- [ ] **Step 1: Find any running fetcher and record its command line**

```bash
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*fetch_alpaca_history*' } | Select-Object ProcessId, CreationDate, CommandLine | Format-List"
```

Copy the command line (it carries no key) into the log's `## Backfill as found` section. If the list is empty, also check `wsl -e pgrep -af fetch_alpaca_history`; still nothing means no fetcher runs.

- [ ] **Step 2: If one runs, wait for it to exit — never kill it, never start a second**

Run in the background (`run_in_background: true`), so the wait costs no context:

```bash
until ! powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*fetch_alpaca_history*' }" | grep -q CommandLine; do sleep 600; done; date -u +%FT%TZ
```

Expected when it returns: a UTC timestamp. Record it as the backfill's end.

- [ ] **Step 3: Measure the store against the member list**

```bash
cd "$WT" && python - "$PIT" <<'EOF'
import json, sys
from collections import Counter
from pathlib import Path
sys.path[:0] = [".", "scripts/data"]
from swingbot.core.marketdata.universe import universe_symbols
from alpaca_history import store_io
root, members = Path(sys.argv[1]), sorted({s.upper() for s in universe_symbols("sp500_pit")})
for tf in ("daily", "hourly", "15min"):
    path = root / tf / "_manifest.json"
    if not path.is_file():
        print(f"{tf}: no manifest"); continue
    man = json.loads(path.read_text(encoding="utf-8"))
    got = man.get("tickers") or {}
    absent = [m for m in members if m not in got]
    short = [m for m in members if (got.get(m) or {}).get("status") == "ok"
             and not store_io.is_complete(got[m], "2016-01-01")]
    status = Counter((got.get(m) or {}).get("status", "absent") for m in members)
    print(f"{tf}: hash {man.get('hash')} updated {man.get('updated_at')} members {len(members)}")
    print(f"  {dict(sorted(status.items()))}")
    print(f"  absent {len(absent)} {absent[:20]}  incomplete {len(short)} {short[:20]}")
EOF
```

Expected: one block per timeframe. Paste the output into the log under `## Measured after the backfill`.

- [ ] **Step 4: List daily identities derived against the forbidden fallback, and re-fetch them**

```bash
cd "$WT" && python - "$PIT" "$EXT" <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from swingbot.core.marketdata.data_store import safe_symbol
pit, ext = Path(sys.argv[1]), Path(sys.argv[2])
got = json.loads((pit / "daily" / "_manifest.json").read_text(encoding="utf-8"))["tickers"]
redo = sorted(t for t, e in got.items()
              if isinstance((e or {}).get("identity"), dict)
              and e["identity"].get("status") != "flagged: no-reference"
              and not (ext / f"{safe_symbol(t)}.csv").is_file())
print(len(redo)); print(",".join(redo))
EOF
```

These tickers have no `backtest_cache_ext` reference, so any identity status other than `flagged: no-reference` came from the root `market_data/daily` fallback. Outside the US regular session, re-fetch them with the fallback off:

```bash
cd "$WT" && python scripts/data/fetch_alpaca_history.py --universe sp500_pit --root "$PIT" --backtest-dir "$EXT" --timeframes daily --force --tickers "<the list printed above>"
```

Skip the fetch when the list is empty. Expected: the summary line (`written N, ..., requests N`), exit 0. Record both in the log.

- [ ] **Step 5: Complete the daily pass**

```bash
cd "$WT" && python scripts/data/fetch_alpaca_history.py --universe sp500_pit --root "$PIT" --backtest-dir "$EXT" --timeframes daily
```

Expected: exit 0; complete `ok` files are skipped, the absent members are fetched. Exit 1 (`refused: ...`) means a guard (session, disk floor): wait until outside the session or free disk, then re-run the same command. Exit 2 means the key was rejected: stop and report. Re-run Step 3; the daily block must show `absent 0` and `incomplete 0`.

- [ ] **Step 6: The hourly pass, then the 15min pass, one at a time**

```bash
cd "$WT" && python scripts/data/fetch_alpaca_history.py --universe sp500_pit --root "$PIT" --backtest-dir "$EXT" --timeframes hourly
cd "$WT" && python scripts/data/fetch_alpaca_history.py --universe sp500_pit --root "$PIT" --backtest-dir "$EXT" --timeframes 15min
```

Start each with `run_in_background: true` and wait for its exit notification; never start the second while the first runs. The 15min pass is the long one (a day or more). A pass that the session guard or a kill stops is resumed by re-running its command; finished tickers are skipped. Record start, end and summary of every attempt.

- [ ] **Step 7: Verify all three timeframes and close the log**

Re-run Step 3. Expected: every timeframe shows `absent 0` and `incomplete 0`; the remaining non-`ok` members carry their status (`flagged: ...`, `skipped: no Alpaca bars`), which V190-20 and V190-21 handle. Add to the log: the three manifest `hash` values, `du -sh "$PIT"`, free disk (`df -h "$MAIN"`), and the list of `skipped: no Alpaca bars` members (V190-20's input).

The log's shape: `# v190 PIT store: backfill log` · `**Spec:**`/`**Plan:**` links · `## Backfill as found` · `## Measured after the backfill` · `## Fallback identities re-fetched` · `## Passes` (one table: timeframe, command, UTC start, UTC end, summary line, exit) · `## Final state` (Step 7's output and the no-bars list).

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/results/2026-10-v190-pit-backfill-log.md
git commit -m "docs(results): v190 V190-18 -- PIT store member backfill completed and verified (daily, hourly, 15min)"
```

### Task V190-19: Context pass: SPY, regime ticker, `etfs.json`, all timeframes

**Model:** haiku — one fetcher command over a computed symbol list and a status check; no judgement unless a symbol fails, which stops the task.

**Files:**
- Data only: `$PIT` manifests and CSVs for the context symbols
- Modify: `docs/superpowers/results/2026-10-v190-pit-backfill-log.md` (`## Context pass`)

**Interfaces:**
- Consumes: V190-18's completed member passes (one fetcher per root); `--universe sp500_pit --tickers LIST` (V190-12); `config.MARKET_REGIME_TICKER`; `universe.universe_symbols("etfs")`.
- Produces (consumed by V190-21 and V190-6's `require_context_frames` at run time): SPY, the regime ticker and all 17 `etfs.json` symbols in all three PIT manifests.

- [ ] **Step 1: Confirm no fetcher runs**

Run V190-18 Step 1's command. Expected: no `fetch_alpaca_history` process.

- [ ] **Step 2: Build the context list**

```bash
cd "$WT" && CTX=$(python -c "import sys; sys.path.insert(0, '.'); from swingbot import config; from swingbot.core.marketdata.universe import universe_symbols; print(','.join(sorted({config.MARKET_REGIME_TICKER.upper(), *(s.upper() for s in universe_symbols('etfs'))})))") && echo "$CTX"
```

Expected: `DIA,GLD,IWM,QQQ,SPY,TLT,XLB,XLC,XLE,XLF,XLI,XLK,XLP,XLRE,XLU,XLV,XLY` (plus the regime ticker if it is not SPY).

- [ ] **Step 3: Fetch all three timeframes**

Outside the US regular session, with `run_in_background: true`:

```bash
cd "$WT" && python scripts/data/fetch_alpaca_history.py --universe sp500_pit --root "$PIT" --backtest-dir "$EXT" --tickers "$CTX"
```

Expected: exit 0 and a summary line. Record command, UTC start and end, and summary in the log.

- [ ] **Step 4: Check every context symbol is usable**

```bash
cd "$WT" && python - "$PIT" "$CTX" <<'EOF'
import json, sys
from pathlib import Path
root, ctx = Path(sys.argv[1]), sys.argv[2].split(",")
bad = []
for tf in ("daily", "hourly", "15min"):
    got = json.loads((root / tf / "_manifest.json").read_text(encoding="utf-8"))["tickers"]
    for sym in ctx:
        status = (got.get(sym) or {}).get("status", "absent")
        print(tf, sym, status, (got.get(sym) or {}).get("start"))
        if status not in ("ok", "flagged: no-reference"):
            bad.append((tf, sym, status))
print("BAD", bad)
EOF
```

Expected: `BAD []`. A context symbol excluded by status would make every v3 run refuse (`require_context_frames`), so a non-empty `BAD` stops the task: report the symbols and their statuses to the controller, who asks the partner. Never edit a manifest by hand.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/2026-10-v190-pit-backfill-log.md
git commit -m "docs(results): v190 V190-19 -- PIT store context pass (SPY, regime ticker, etfs.json; all timeframes)"
```

### Task V190-20: Rename aliases: map `no-bars` members, fetch them

**Model:** sonnet — research-backed mapping where a wrong entry splices two issuers; the rules for what counts as a rename are fixed below.

**Files:**
- Create: `data/universe/symbol_aliases.json` (committed; `data/universe/` is tracked)
- Modify: `docs/superpowers/results/2026-10-v190-pit-backfill-log.md` (`## Aliases`)

**Interfaces:**
- Consumes: `aliases.load_aliases(path)` and the file shape `{"aliases": [{"member", "alpaca", "start", "end", "note"}]}` (V190-12); `--aliases` defaulting to `<repo>/data/universe/symbol_aliases.json` beside `--universe`; manifest entry key `alias`; `pit_membership.load_intervals`.
- Produces (consumed by V190-21's integrity build and every v3 run): the committed alias table; aliased members fetched under their Alpaca symbol and stored under the membership symbol in all three timeframes.

Rules (spec §2.4): an alias maps a **ticker change of the same issuer** (FB→META, ANTM→ELV style). An acquisition, merger into another listed company, or spin-off is not a rename: mapping it would splice two issuers' bars, the exact MON failure. Those members stay `skipped: no Alpaca bars`, listed with a reason. `start` is `2016-01-04` (the store start) unless the Alpaca symbol belonged to another issuer before the rename, in which case `start` is the rename date; `end` is `null` unless the member symbol's issuer later changed symbol again. Every entry's `note` names the rename date and the public source (exchange notice or company press release).

- [ ] **Step 1: List the no-bars members with their membership spans**

```bash
cd "$WT" && python - "$PIT" <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from swingbot.core.marketdata import pit_membership
spans = pit_membership.load_intervals(Path("data/universe/sp500_membership.csv"))
got = json.loads((Path(sys.argv[1]) / "daily" / "_manifest.json").read_text(encoding="utf-8"))["tickers"]
for sym in sorted(t for t, e in got.items() if (e or {}).get("status") == "skipped: no Alpaca bars"):
    print(sym, spans.get(sym))
EOF
```

Expected: one line per member (18 at plan time), each with its `[start, end_excl)` spans.

- [ ] **Step 2: Map each one by the rules above**

For each member, establish whether it changed ticker as the same issuer and, if so, the successor symbol and date. Write `data/universe/symbol_aliases.json`, entries sorted by `member`, e.g.:

```json
{"aliases": [
  {"member": "FB", "alpaca": "META", "start": "2016-01-04", "end": null,
   "note": "Meta Platforms ticker change FB->META effective 2022-06-09 (Nasdaq notice)"}
]}
```

Validate it:

```bash
cd "$WT" && python -c "import sys; sys.path[:0] = ['.', 'scripts/data']; from pathlib import Path; from alpaca_history import aliases; m = aliases.load_aliases(Path('data/universe/symbol_aliases.json')); print(len(m), sorted(m))"
```

Expected: the count and member list, no `ValueError`. In the log's `## Aliases`, list every no-bars member as either mapped (alias, date, source) or unmapped with its reason (acquired by X on date; merged; no successor).

- [ ] **Step 3: Fetch the aliased members (all three timeframes)**

Confirm no fetcher runs (V190-18 Step 1), then outside the US regular session:

```bash
cd "$WT" && python scripts/data/fetch_alpaca_history.py --universe sp500_pit --root "$PIT" --backtest-dir "$EXT" --force --tickers "<the mapped members, comma-separated>"
```

Expected: exit 0; the summary counts them written or flagged.

- [ ] **Step 4: Check the manifests carry the alias**

```bash
cd "$WT" && python - "$PIT" <<'EOF'
import json, sys
from pathlib import Path
sys.path[:0] = [".", "scripts/data"]
from alpaca_history import aliases
table = aliases.load_aliases(Path("data/universe/symbol_aliases.json"))
for tf in ("daily", "hourly", "15min"):
    got = json.loads((Path(sys.argv[1]) / tf / "_manifest.json").read_text(encoding="utf-8"))["tickers"]
    for member, alias in sorted(table.items()):
        e = got.get(member) or {}
        print(tf, member, e.get("alias"), e.get("status"), e.get("start"))
        assert e.get("alias") == alias.alpaca, (tf, member)
EOF
```

Expected: every line shows the Alpaca symbol in the alias column and no `AssertionError`. A mapped member whose status comes back `flagged: price-mismatch` or `flagged: short-overlap` against its membership-symbol reference is evidence the mapping is wrong: drop that entry from the table, re-run Steps 2–4 for it (`--force` re-fetch records it as `skipped: no Alpaca bars` again), and list it unmapped with that evidence.

- [ ] **Step 5: Commit**

```bash
git add data/universe/symbol_aliases.json docs/superpowers/results/2026-10-v190-pit-backfill-log.md
git commit -m "data(universe): v190 V190-20 -- symbol_aliases.json: renamed S&P members mapped to their Alpaca symbol; unmapped no-bars members listed"
```

### Task V190-21: Calibrate and freeze the integrity report

**Model:** opus — freezes the data decisions every v3 result rests on; calibration must use the named calibration set only, never an outcome, and the in-span verdicts are judgement.

**Files:**
- Data: the main checkout's `data/market_data_pit/_integrity.json` (frozen; git-ignored)
- Modify (only if calibration moves a threshold): `scripts/data/alpaca_history/reuse.py` (`Thresholds` defaults), `scripts/data/alpaca_history/pit_coverage.py` (`MAX_MISSING_RUN`, `TRAILING_SESSIONS`, `MIN_TRAILING_SHARE`), and the tests that pin those values (`tests/history_store/test_reuse.py`, `tests/history_store/test_pit_coverage.py`)
- Create: `docs/superpowers/results/2026-10-v190-pit-integrity.md`; the tool's own summary `docs/superpowers/results/<YYYY-MM>-v190-pit-integrity-report.md` (V190-15 `SUMMARY_NAME`)

**Interfaces:**
- Consumes: `check_history_store.py --pit --root --backtest-dir --results-dir` (V190-15: writes `<root>/_integrity.json` atomically and the summary; excludes `in_span` and `unresolved` breaks with `"... resolve by hand"` / `"unresolved break ..."`; records `thresholds`, `detector_sha` (git blob ids of `reuse.py` and `pit_coverage.py`), `manifest_sha256` for all three timeframes); `training_data.select("alpaca", "pit", "2025-12-31")` and `StaleIntegrityError` (V190-4); the store completed by V190-18..V190-20.
- Produces (consumed by V190-22..V190-24): the frozen `_integrity.json` (its sha256 is what every leg-A sidecar must carry) and the results doc that states the freeze.

**Rule (spec §2.3, index Global Constraints):** thresholds are calibrated only against the calibration set below, and frozen before any strategy result is read. No backtest, grid or report of WR/ExpR runs in this task. The draft runs below may be repeated; the freeze is the last run, made after any threshold change is committed (the detector blob ids must match committed code).

Calibration set:
- **Reused symbol:** MON (Monsanto left the S&P 500 in June 2018; the symbol's later bars belong to another issuer). Expected: `trim.keep_before` on or just after the break following the last membership end, reason `break after last membership end`, admitted.
- **Delisted probe names:** TWTR, XLNX, ATVI, SIVB, FRC, CELG, CTXS. Expected: admitted (or excluded only by identity with that reason), `last_bar` at their exit, no trim, no break.
- **Forward splits:** AAPL (4:1, 2020-08-31), TSLA (5:1, 2020-08-31; 3:1, 2022-08-25), NVDA (4:1, 2021-07-20; 10:1, 2024-06-10). **Reverse split:** GE (1:8, 2021-08-02). Expected: no break (the store is `Adjustment.ALL`).

- [ ] **Step 1: Pre-flight: no fetcher, record the manifest hashes**

Run V190-18 Step 1's process check (expected: none), then:

```bash
sha256sum "$PIT"/daily/_manifest.json "$PIT"/hourly/_manifest.json "$PIT"/15min/_manifest.json
```

Record the three digests; Step 7 checks they did not move.

- [ ] **Step 2: Draft run**

```bash
cd "$WT" && python scripts/data/check_history_store.py --pit --root "$PIT" --backtest-dir "$EXT" --results-dir "$WT/docs/superpowers/results"
```

Expected: exit 0; `$PIT/_integrity.json` and `docs/superpowers/results/<YYYY-MM>-v190-pit-integrity-report.md` written.

- [ ] **Step 3: Read the calibration set and every break**

```bash
cd "$WT" && python - "$PIT/_integrity.json" <<'EOF'
import json, sys
from collections import Counter
doc = json.loads(open(sys.argv[1], encoding="utf-8").read())
t = doc["tickers"]
for sym in ("MON", "TWTR", "XLNX", "ATVI", "SIVB", "FRC", "CELG", "CTXS", "AAPL", "TSLA", "NVDA", "GE"):
    e = t.get(sym)
    if e is None:
        print(sym, "NO ENTRY", "no_bars" if sym in doc["no_bars"] else ""); continue
    print(sym, e["admitted"], e["reason"], e["first_bar"], e["last_bar"], e["trim"], e["breaks"], e.get("gaps"))
print("thresholds", doc["thresholds"])
print("resolutions", Counter(b["resolution"] for e in t.values() for b in e["breaks"]))
print("excluded", Counter(e["reason"].split(":")[0] for e in t.values() if not e["admitted"]))
for sym, e in sorted(t.items()):
    for b in e["breaks"]:
        if b["resolution"] in ("in_span", "unresolved"):
            print("HAND", sym, b, e["first_bar"], e["last_bar"])
EOF
```

Expected: MON trimmed as above; probe names and split names with no break and no trim. Every `HAND` line is a break the tool left for the builder.

- [ ] **Step 4: Recalibrate only if the calibration set fails**

If MON is not trimmed, or a probe or split name trips a break, change the smallest threshold that fixes it (`reuse.Thresholds` defaults; the coverage constants only if a probe name is cut for missing bars it actually has), update the value pins in `tests/history_store/test_reuse.py` / `tests/history_store/test_pit_coverage.py`, and run:

```bash
python scripts/dev/testrun.py file tests/history_store/test_reuse.py
python scripts/dev/testrun.py file tests/history_store/test_pit_coverage.py
python scripts/dev/testrun.py file tests/history_store/test_check_history_store_pit.py
```

Expected: `0 failed`, `0 xfailed`. Commit before the next draft run:

```bash
git add scripts/data/alpaca_history/reuse.py scripts/data/alpaca_history/pit_coverage.py tests/history_store/test_reuse.py tests/history_store/test_pit_coverage.py
git commit -m "fix(data): v190 V190-21 -- reuse/coverage thresholds calibrated on MON, the probe names and the split cases (before any strategy result)"
```

Re-run Steps 2–3. Record every change (old value, new value, the calibration ticker that forced it) for the results doc. No change is made for any other reason.

- [ ] **Step 5: Resolve every `HAND` break by hand, in writing**

For each `HAND` line, plot or print the daily close and volume 30 sessions either side of the break date (`pd.read_csv(f"{PIT}/daily/<SAFE>.csv", index_col="Date", parse_dates=True)`) and the member's membership spans, and decide: **issuer change** (exclusion stands) or **same-issuer event** (a spin-off, a restructuring; the exclusion would drop a real member). Write one row per break in the results doc: ticker · date · kind · resolution · verdict · evidence. The frozen report has no hand-override field, so exclusions stand as written: if any verdict is "same-issuer event", stop and report the list to the controller, who asks the partner (admitting it needs a contract change in a follow-up, not an edit of `_integrity.json`).

- [ ] **Step 6: Re-check the context symbols are admitted**

Any break on a context symbol (SPY, the regime ticker, an `etfs.json` ETF) excludes it (V190-14: a context symbol has no membership spans, so no side can be kept), and every v3 run would then refuse in `require_context_frames`. Check before freezing:

```bash
cd "$WT" && python - "$PIT/_integrity.json" <<'PY'
import json, sys
sys.path[:0] = [".", "scripts/data"]
import check_history_store as chk
doc = json.loads(open(sys.argv[1], encoding="utf-8").read())
bad = {s: (doc["tickers"].get(s) or {}).get("reason", "no entry") for s in chk.context_symbols()
       if not (doc["tickers"].get(s) or {}).get("admitted")}
print("CONTEXT NOT ADMITTED", bad)
PY
```

Expected: `CONTEXT NOT ADMITTED {}`. Otherwise resolve each one as in Step 5 (a context symbol's break is almost always a same-issuer event, so this usually means stop and report to the controller, who asks the partner); never freeze with a context symbol excluded.

- [ ] **Step 7: Freeze**

Confirm the manifest digests still equal Step 1's (`sha256sum` again), then make the final run with the committed detectors:

```bash
cd "$WT" && git status --porcelain scripts/data/alpaca_history/ && python scripts/data/check_history_store.py --pit --root "$PIT" --backtest-dir "$EXT" --results-dir "$WT/docs/superpowers/results"
sha256sum "$PIT/_integrity.json"
cd "$WT" && python -c "import sys; sys.path.insert(0, '.'); from swingbot.core.marketdata import training_data as td; print(td.select('alpaca', 'pit', '2025-12-31'), td.active_store(), len(td.available_tickers()), len(td.excluded()), td.provenance()['integrity_sha256'])"
```

Expected: `git status --porcelain` prints nothing (detectors committed); the check exits 0; the selection prints `alpaca pit <admitted count> <excluded count> <the same sha256>`. That sha256 is **the freeze**.

- [ ] **Step 8: Write `docs/superpowers/results/2026-10-v190-pit-integrity.md`**

Sections: `# v190 PIT store: frozen integrity report` · `**Spec:**`/`**Plan:**` links · `## Freeze` (UTC time, `_integrity.json` sha256, the three manifest sha256 values, both detector blob ids, the worktree HEAD sha, and the sentence: "Frozen before any strategy result was read. A `--mode update` on `data/market_data_pit/` after this point makes every v3 run stop with `StaleIntegrityError`.") · `## Thresholds` (final values; each recalibration from Step 4 with its reason, or "none changed") · `## Calibration set` (one row per ticker: expected, observed) · `## Hand resolutions` (Step 5's and Step 6's rows, or "none") · `## Counts` (tickers, admitted, excluded by reason, no bars, aliases, trimmed, with signal cuts) · `## Tool summary` (a link to `<YYYY-MM>-v190-pit-integrity-report.md`). V190-22 appends `## Coverage gate and smoke run`.

- [ ] **Step 9: Commit**

```bash
git add docs/superpowers/results/2026-10-v190-pit-integrity.md docs/superpowers/results/*-v190-pit-integrity-report.md
git commit -m "docs(results): v190 V190-21 -- PIT store integrity report calibrated and frozen (sha256 recorded before any strategy result)"
```

# Phase 3 — Gate, legs, record

### Task V190-22: v3 coverage gate and smoke run on the real store

**Model:** sonnet — runs two commands and checks their output against fixed acceptance rules; a gap that the rules do not explain stops the task.

**Files:**
- Modify: `docs/superpowers/results/2026-10-v190-pit-integrity.md` (`## Coverage gate and smoke run`)
- Data only: `$OUT/coverage-v3.md`, `$OUT/smoke-v3.json`, `$OUT/smoke-v3.jsonl` and their `.provenance.json` sidecars

**Interfaces:**
- Consumes: `check_cache_coverage.py --instrument v3 --store-root PATH --out PATH` (V190-9: exit 0 covered, 1 gaps listed, 2 nothing to check); `coverage.check_store_coverage(symbols, required_start, root)`, `coverage.research_members(spec)`, `coverage.first_membership(spec, symbols)`; `run_backtest_range.py --instrument v3` (V190-6, V190-7); the frozen `_integrity.json` (V190-21).
- Produces: the gate verdict V190-23 waits on.

**Gate rule.** The gate lists gaps and drops nothing, so exit 1 is expected (members listed after 2016-01-04 are late by construction). The gate is **green** when every listed symbol is explained by the frozen report: (a) it is in `no_bars`; or (b) its entry is not admitted, with a reason; or (c) it is late and admitted, and either its first stored bar is on or before its first membership date, or one of its `signal_cuts` ends after its first stored bar (the trailing-60 rule cut the span start). Anything else is an unexplained gap: stop, report it to the controller, run no leg.

- [ ] **Step 1: Run the gate**

```bash
mkdir -p "$OUT" && cd "$WT" && python scripts/data/check_cache_coverage.py --instrument v3 --store-root "$PIT" --out "$OUT/coverage-v3.md"; echo "exit $?"
```

Expected: `exit 0` or `exit 1`, and a stderr line `COVERAGE: ...`.

- [ ] **Step 2: Account for every gap**

```bash
cd "$WT" && python - "$PIT" <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from swingbot.core.backtesting.instrument import contract, coverage
root = Path(sys.argv[1])
spec = contract.resolve("v3")
doc = json.loads((root / "_integrity.json").read_text(encoding="utf-8"))
report = coverage.check_store_coverage(coverage.research_members(spec), spec.warmup_start, root)
late = dict(report.late)
firsts = coverage.first_membership(spec, list(late) + list(report.missing))
unexplained = []
for sym in sorted(set(late) | set(report.missing)):
    e = doc["tickers"].get(sym)
    if sym in doc["no_bars"] or (e and not e["admitted"]):
        continue
    first_bar = str(late.get(sym, ""))[:10]
    cut_after = any(cut[1] > first_bar for cut in (e or {}).get("signal_cuts", []))
    if e and first_bar and (first_bar <= firsts.get(sym, "") or cut_after):
        continue
    unexplained.append((sym, first_bar or "missing", firsts.get(sym)))
print("late", len(late), "missing", len(report.missing), "UNEXPLAINED", unexplained)
EOF
```

Expected: `UNEXPLAINED []`. A non-empty list stops the task here.

- [ ] **Step 3: Smoke run, through `backtest-runner`**

Dispatch the `backtest-runner` agent (it checks no heavy run is live first) with, from `$WT`:

```bash
python scripts/backtest/run_backtest_range.py --instrument v3 --exit-model v2 --scale-out --tp2 none --from 2019-01-01 --to 2019-12-31 --strategy "RSI" --json "$OUT/smoke-v3.json" --trades-jsonl "$OUT/smoke-v3.jsonl"
```

Ask it to return only: exit code, the `Wrote N trade rows` line, the number of tickers in the run header, and whether `CELG` appears in the per-ticker progress lines. Expected: exit 0; N > 0; `CELG` present (a member until its November 2019 acquisition, so survivorship is removed).

- [ ] **Step 4: Check the smoke run's provenance and rows**

```bash
cd "$WT" && python - "$OUT/smoke-v3.jsonl" "$PIT/_integrity.json" <<'EOF'
import hashlib, json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
prov = json.loads(open(sys.argv[1] + ".provenance.json", encoding="utf-8").read())
frozen = hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest()
print("store", prov.get("store"), "source", prov.get("data_source"),
      "integrity ok", prov.get("integrity_sha256") == frozen)
print("rows", len(rows), "MON rows", sum(r["ticker"] == "MON" for r in rows),
      "holdout rows", sum(str(r.get("exit_date") or "")[:10] >= "2026-01-01" for r in rows),
      "delisted traded", sorted({r["ticker"] for r in rows} & {"CELG", "TWTR", "XLNX", "ATVI", "SIVB", "FRC", "CTXS"}))
EOF
```

Expected: `store pit source alpaca integrity ok True`; `MON rows 0` (its frame ends at the 2018 trim); `holdout rows 0`. Any other value stops the task.

- [ ] **Step 5: Record and commit**

Append `## Coverage gate and smoke run` to `docs/superpowers/results/2026-10-v190-pit-integrity.md`: the gate's exit code and summary counts (covered, late, missing), `UNEXPLAINED []`, the smoke command, its row count, ticker count, and the Step 4 output. Copy `$OUT/coverage-v3.md`'s summary table in. No WR or ExpR from the smoke run is written anywhere: it is a plumbing check.

```bash
git add docs/superpowers/results/2026-10-v190-pit-integrity.md
git commit -m "docs(results): v190 V190-22 -- v3 coverage gate accounted for; v3 smoke run on the frozen PIT store"
```

### Task V190-23: Re-baseline legs A and B via `backtest-runner`

**Model:** sonnet — dispatches fixed commands chunked per strategy and checks provenance; reads no WR or ExpR.

**Files:**
- Data only (git-ignored): `$OUT/watchlist.txt`; `$OUT/leg-A-<slug>.jsonl` and `$OUT/leg-B-<slug>.jsonl` for each strategy, each with its `.json` and `.provenance.json` sidecars

**Interfaces:**
- Consumes: `run_backtest_range.py --instrument v3` (V190-6/V190-7; `--train` under v3 = research `2017-01-01..2025-12-31`, frames cut at `research_end`); the frozen `_integrity.json` (V190-21) and a green gate (V190-22); `backtest.ALL_STRATEGIES` (11 strategies, verified at HEAD); `fetch_backtest_data.load_watchlist()` (Postgres).
- Produces (consumed by V190-24): 11 leg-A and 11 leg-B trade-row files; every leg-A sidecar carries `store: "pit"` and the frozen `integrity_sha256`, every leg-B sidecar `store: "watchlist"`.

Legs (spec §5; every live strategy at its current settings, both directions wherever the strategy emits them — `run_backtest_range` writes each trade's `direction`):
- **Leg A:** `--instrument v3 --train --exit-model v2 --scale-out --tp2 none` (v3 pins the `sp500_pit` universe and refuses `--tickers-file`).
- **Leg B:** `--instrument v1 --train --data-source alpaca --exit-model v2 --scale-out --tickers-file "$OUT/watchlist.txt"` (`--tp2 levels` by default: the funnel's `_V1_EXIT_KWARGS`, what the funnel runs today).
- **Leg C** is not run: V190-24's report filters leg A's rows to the watchlist tickers that are PIT members.
- **Confluence** is not run on any leg: `--scenarios` is refused under v3 (`_V2_UNWIRED`), and a v1-only confluence figure has nothing to stand beside; the report says so (`CONFLUENCE_NOTE`).

Slugs: the strategy name lower-cased, every run of non-alphanumerics replaced by `-`, stripped (`Support/Resistance` → `support-resistance`, `Break & Retest` → `break-retest`).

- [ ] **Step 1: Replicate the production database, freeze the watchlist**

Run `/replicate-prod-db` (the watchlist lives in Postgres only). Then:

```bash
cd "$WT" && python -c "import sys; sys.path[:0] = ['.', 'scripts/data']; import fetch_backtest_data as f; print('\n'.join(sorted({t.upper() for t in f.load_watchlist()})))" > "$OUT/watchlist.txt" && wc -l "$OUT/watchlist.txt" && sha256sum "$OUT/watchlist.txt"
```

Expected: about 77 lines and a digest; V190-24 records both. Leg B and leg C read this one file.

- [ ] **Step 2: Confirm nothing moved since the freeze**

```bash
sha256sum "$PIT/_integrity.json" "$PIT"/daily/_manifest.json
```

Expected: both digests equal the ones in `docs/superpowers/results/2026-10-v190-pit-integrity.md`. A difference stops the task (V190-21 must be redone).

- [ ] **Step 3: Run leg A, one strategy per `backtest-runner` dispatch**

List the strategies:

```bash
cd "$WT" && python -c "import sys; sys.path.insert(0, '.'); from swingbot.core.backtesting.backtest import ALL_STRATEGIES; import re; [print(s + '|' + re.sub('[^a-z0-9]+', '-', s.lower()).strip('-')) for s in ALL_STRATEGIES]"
```

For each `<name>|<slug>` line, dispatch `backtest-runner` (one at a time; it checks no other heavy run is live) with, from `$WT`:

```bash
python scripts/backtest/run_backtest_range.py --instrument v3 --train --exit-model v2 --scale-out --tp2 none --strategy "<name>" --json "$OUT/leg-A-<slug>.json" --trades-jsonl "$OUT/leg-A-<slug>.jsonl"
```

Ask it to return only the exit code, the `Wrote N trade rows` line and the run's wall time, and **not** to quote WR or ExpR (they are read once, in V190-24's report). A chunk that fails is re-run alone; a completed chunk is never re-run.

- [ ] **Step 4: Run leg B, the same way**

For each strategy:

```bash
python scripts/backtest/run_backtest_range.py --instrument v1 --train --data-source alpaca --exit-model v2 --scale-out --tickers-file "$OUT/watchlist.txt" --strategy "<name>" --json "$OUT/leg-B-<slug>.json" --trades-jsonl "$OUT/leg-B-<slug>.jsonl"
```

- [ ] **Step 5: Check the 22 files and their provenance**

```bash
cd "$WT" && python - "$OUT" "$PIT/_integrity.json" <<'EOF'
import glob, hashlib, json, sys
out, frozen = sys.argv[1], hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest()
for leg, store in (("A", "pit"), ("B", "watchlist")):
    files = sorted(glob.glob(f"{out}/leg-{leg}-*.jsonl"))
    provs = [json.load(open(f + ".provenance.json", encoding="utf-8")) for f in files]
    rows = sum(sum(1 for l in open(f, encoding="utf-8") if l.strip()) for f in files)
    same = all(p == provs[0] for p in provs)
    print(leg, len(files), "files", rows, "rows", "one provenance", same,
          "store", {p.get("store") for p in provs}, "want", store,
          "integrity ok" if leg == "B" or all(p.get("integrity_sha256") == frozen for p in provs) else "INTEGRITY MISMATCH")
EOF
```

Expected: `A 11 files ... one provenance True store {'pit'} ... integrity ok` and `B 11 files ... one provenance True store {'watchlist'}`. Anything else stops the task; re-run only the offending chunk.

- [ ] **Step 6: Commit**

Nothing to commit: the leg files are git-ignored data. V190-24 records their sha256 digests and commands in the results doc. Confirm `git -C "$WT" status --porcelain` shows no stray file (`backtest_range_summary.txt` is git-ignored).

### Task V190-24: Re-baseline results doc and ledger DESCRIPTION row

**Model:** sonnet — runs the V190-16 report over fixed inputs and appends one validated ledger row; the wording rules are fixed.

**Files:**
- Create: `docs/superpowers/results/2026-10-v190-v3-rebaseline.md`, `docs/superpowers/results/2026-10-v190-v3-rebaseline.json`
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (one appended row)

**Interfaces:**
- Consumes: `scripts/reports/v190_rebaseline_report.py` CLI, `STANDING_LINE`, `LEDGER_ID`, `RECORD` (V190-16); the 22 leg files and `$OUT/watchlist.txt` (V190-23); the frozen `_integrity.json` (V190-21); `scripts/reports/preregistration_ledger.py` (existing; `--instrument` and `--verdict` take their choices from `stats.INSTRUMENTS` / `stats.VERDICTS`, which hold `v3` / `DESCRIPTION` after V190-10; `--exp-r` and `--p` default to null).
- Produces: the recorded description; ledger row `v190-v3-rebaseline` (`instrument v3`, `verdict DESCRIPTION`, `p null`, `exp_r null`, `data_source alpaca`).

Reading rule (spec Non-goals, §5): the report describes an instrument change; never a lift; selects nothing. The doc adds no interpretation of WR or ExpR, no per-cell judgement, and no recommendation about badges or the default instrument. A later spec may cite only the power columns.

- [ ] **Step 1: Generate the report**

```bash
cd "$WT" && python scripts/reports/v190_rebaseline_report.py --leg "A=$OUT/leg-A-*.jsonl" --leg "B=$OUT/leg-B-*.jsonl" --watchlist "$OUT/watchlist.txt" --integrity "$PIT/_integrity.json" --json docs/superpowers/results/2026-10-v190-v3-rebaseline.json --md "$OUT/rebaseline-body.md" --date "$(date -u +%F)" > "$OUT/rebaseline-stdout.txt"; echo "exit $?"; tail -1 "$OUT/rebaseline-stdout.txt"
```

Expected: `exit 0` and a `LEDGER ROW: {...}` line. Exit 1 prints the refused input on stderr: fix the input (never the report's checks) and re-run.

- [ ] **Step 2: Write `docs/superpowers/results/2026-10-v190-v3-rebaseline.md`**

Top block, in this order:
1. `# v190 re-baseline: instrument v3 (PIT S&P 500 on the Alpaca store)` and the standing line in italics: *describes an instrument change; never a lift; selects nothing*.
2. `**Spec:**` and `**Plan:**` links; `**Code:**` the worktree HEAD sha; `**Integrity:**` the frozen `_integrity.json` sha256 and a link to `2026-10-v190-pit-integrity.md`.
3. `## Inputs`: the two leg commands from V190-23 (with `<name>` placeholders) and their run dates; a table of the 22 files (leg, strategy, rows, sha256 from `sha256sum "$OUT"/leg-*.jsonl`); the watchlist file's line count and sha256; the seeds (`ticker 190`, `week stats.WEEK_BOOTSTRAP_SEED`) and resamples.
4. `## How this may be cited`: "A later spec may cite only the power columns (N, the A/B and C/B ratios, coverage, first counted dates, MDE). WR and ExpR below are description only. Any v3 badge or default-instrument rule is frozen before this table is read, or is scored on the 2026 holdout alone."

Then `$OUT/rebaseline-body.md` verbatim (it carries the in-sample, confluence and cost notes, the cell count, the concentration shares and the per-fold effective fold-train N).

- [ ] **Step 3: Append the ledger row**

Take the values from the `LEDGER ROW` line:

```bash
cd "$WT" && python scripts/reports/preregistration_ledger.py --id v190-v3-rebaseline --date "<row date>" --hypothesis "<row hypothesis>" --instrument v3 --n <row n> --verdict DESCRIPTION --record docs/superpowers/results/2026-10-v190-v3-rebaseline.md --data-source alpaca
tail -1 docs/superpowers/results/preregistration-ledger.jsonl
```

Expected: the CLI prints the BH table with `v190-v3-rebaseline` at q = `None`/null (outside the family); the last ledger line equals the `LEDGER ROW` JSON field for field (`exp_r` null, `p` null).

- [ ] **Step 4: Run the ledger tests**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py
python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
python scripts/dev/testrun.py file tests/scripts/test_preregistration_ledger_cli.py
```

Expected: `0 failed`, `0 xfailed` (the committed ledger, now with a DESCRIPTION row, still validates).

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/2026-10-v190-v3-rebaseline.md docs/superpowers/results/2026-10-v190-v3-rebaseline.json docs/superpowers/results/preregistration-ledger.jsonl
git commit -m "docs(results): v190 V190-24 -- instrument v3 re-baseline recorded (describes an instrument change; never a lift; selects nothing); ledger DESCRIPTION row"
```

# Phase 4 — Release

### Task V190-25: Version bump, full suite, merge

**Model:** sonnet — the release ritual with fixed commands; the only judgement is a concurrent-session check before the merge.

**Files:**
- Modify: `VERSION.json` (the `bot` line and `bot_updated` only)
- Modify: `swingbot/admin/version_history.json` (regenerated by `scripts/dev/build_version_matrix.py`)

**Interfaces:**
- Consumes: every earlier task committed on the worktree branch `2026-10-24-v190-pit-alpaca-universe`.
- Produces: the branch merged into `main`; `/close-out` follows.

`Bump: bot patch` (spec header). The order is the convention's (`docs/claude/working-conventions.md` § Versioning, How): green suite first, then the bump commit, then the regeneration commit, then the version-matrix test, then the merge. This is the plan's single full-suite run; there is none after the merge.

- [ ] **Step 1: Pre-flight on the worktree**

```bash
git -C "$WT" status --porcelain
python scripts/dev/complexity_gate.py
```

Expected: no output from `status`; the gate exits 0.

- [ ] **Step 2: The full suite, through `test-runner`**

Run `/replicate-prod-db` first if the local replica is older than this session (the suite reads the database). Dispatch the `test-runner` agent with, from `$WT`:

```bash
python scripts/dev/testrun.py full
```

Expected: `0 failed`, `0 xfailed` (a changed pass count is not a failure). A failing test is fixed in its own commit and re-run alone (`python scripts/dev/testrun.py file <that file>`), never by a second full run.

- [ ] **Step 3: Bump `VERSION.json` from `main`'s value**

```bash
git -C "$MAIN" show main:VERSION.json
```

Set the worktree's `bot` to that value with the patch part incremented (2.15.0 → 2.15.1 if `main` has not moved), `bot_updated` to `date -u +"%Y-%m-%d %H-%M-%S"`; leave `ui` and `ui_updated` as on `main`. Commit `VERSION.json` alone:

```bash
git add VERSION.json
git commit -m "release(bot): <version> -- instrument v3: point-in-time S&P 500 on the Alpaca store, integrity report, describe-only re-baseline"
```

- [ ] **Step 4: Regenerate and pin the version history**

```bash
python scripts/dev/build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(bot): <version> -- instrument v3: point-in-time S&P 500 on the Alpaca store, integrity report, describe-only re-baseline"
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
```

Expected: `0 failed`.

- [ ] **Step 5: Merge into `main`**

Follow the `worktree-lifecycle` skill. Before merging, check for concurrent work: `git -C "$MAIN" status --porcelain` (expected empty) and `git -C "$MAIN" log --oneline -5 main`; if another session is mid-change on `main`, pause and confirm with the partner. Then:

```bash
git -C "$MAIN" merge --no-ff 2026-10-24-v190-pit-alpaca-universe -m "merge: v190 -- instrument v3 on the PIT Alpaca store"
```

A `VERSION.json` conflict (another release landed meanwhile) is resolved by taking `main`'s `bot` value plus one patch, re-running Step 4's regeneration on `main`, and committing it. No full suite after the merge.

- [ ] **Step 6: Commit and hand over to `/close-out`**

The merge commit is this task's commit. Run `/close-out` next: its panel step runs the spec's `**Panel:**` roles (staff-engineer, quant-engineer, quant-researcher) over the merged diff and the recorded results; its bump steps find this task's release already committed for `Bump: bot patch` and do not bump again; it moves the plan and spec to `implemented/` and removes the worktree.
