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


def test_singleton_formula_is_undefined_and_json_remains_finite():
    cols = rep.power_columns(_trades([_row("A", "2019-01-02")]), n_resamples=10)
    assert cols["mde_r_formula"] is None
    assert cols["mde_r_ticker"] == 0.0 and cols["mde_r_week"] == 0.0
    json.dumps(cols, allow_nan=False)


@pytest.mark.parametrize("resamples", [-1, 0, 1])
def test_power_refuses_insufficient_resamples(resamples):
    with pytest.raises(ValueError, match="resamples"):
        rep.power_columns([], n_resamples=resamples)


def test_ticker_seed_override_does_not_change_week_draws():
    population = _population()
    default = rep.power_columns(population, n_resamples=30)
    other = rep.power_columns(population, seed=27, n_resamples=30)
    assert other["ticker_seed"] == 27
    assert other["mde_r_ticker"] != default["mde_r_ticker"]
    assert other["mde_r_week"] == default["mde_r_week"]
    assert other["mde_r_formula"] == default["mde_r_formula"]


def test_sidecar_is_required_and_source_must_be_alpaca(tmp_path):
    path = tmp_path / "absent.jsonl"
    with pytest.raises(ValueError, match="provenance sidecar"):
        rep.load_provenance("A", [path])
    path = _write_leg(tmp_path, "vendor", [], {**PROV_A, "data_source": "yfinance"})
    with pytest.raises(ValueError, match="alpaca"):
        rep.load_provenance("A", [path])


def test_trade_dates_truncate_timestamps_and_preserve_missing_exit():
    row = _row("AAA", "2019-01-02T12:00:00Z", exit_="2019-01-03T12:00:00Z")
    trade = rep._trade(row, Path("x.jsonl"))
    assert (trade.entry_date, trade.exit_date) == ("2019-01-02", "2019-01-03")
    row.update(exit_date=None, direction=None)
    trade = rep._trade(row, Path("x.jsonl"))
    assert trade.exit_date is None and trade.direction == ""
    assert rep.fold_train([trade], FOLDS) == []


def test_describe_uses_decided_trades_for_wr_and_all_closed_trades_for_mean():
    trades = _trades([_row("A", "2019-01-02"),
                      _row("A", "2019-01-03", outcome="loss", r=-1),
                      _row("A", "2019-01-04", outcome="timeout", r=3)])
    assert rep.describe(trades) == {"n": 3, "n_eval": 2, "win_rate": 50.0, "expectancy_r": 1.0}
    assert rep.describe([]) == {"n": 0, "n_eval": 0, "win_rate": None, "expectancy_r": None}


def test_all_empty_legs_keep_null_ratios_and_render_na(tmp_path):
    _path, doc, sha = _integrity(tmp_path)
    report = rep.build_report({"A": [], "B": [], "C": []},
                              {"A": {**PROV_A, "integrity_sha256": sha}, "B": PROV_B},
                              folds=FOLDS, integrity_sha=sha, integrity_doc=doc, n_resamples=10)
    assert report["ratios"] == {"A/B": None, "C/B": None}
    assert report["legs"]["C"]["provenance"] == report["legs"]["A"]["provenance"]
    assert "n/a" in rep.render_markdown(report)
    json.dumps(report, allow_nan=False)


def test_markdown_contains_each_required_reporting_section(tmp_path):
    md = rep.render_markdown(_report(tmp_path))
    sections = ("Power (citable)", "mde_r_formula", "mde_r_ticker", "mde_r_week",
                "seed 190", f"seed {stats.WEEK_BOOTSTRAP_SEED}", "A/B", "C/B", "cells:",
                "Coverage", "Integrity SHA-256", "First counted entry", "Effective fold-train N",
                "Fold-test N", "Entry year (all trades)", "Fold test side", "Top two horizons")
    assert all(section in md for section in sections)


def _cli_args(tmp_path, monkeypatch):
    integrity, _doc, sha = _integrity(tmp_path)
    a = _write_leg(tmp_path, "a", [_row("AAA", "2018-03-01")],
                   {**PROV_A, "integrity_sha256": sha})
    b = _write_leg(tmp_path, "b", [_row("AAA", "2021-03-01")], PROV_B)
    watch = tmp_path / "watchlist.txt"
    watch.write_text("aaa # watchlist member\n", encoding="utf-8")
    monkeypatch.setattr(rep, "universe_symbols", lambda name: ["AAA"])
    return ["--leg", f"A={a}", "--leg", f"B={b}", "--watchlist", str(watch),
            "--integrity", str(integrity), "--json", str(tmp_path / "json" / "r.json"),
            "--md", str(tmp_path / "markdown" / "r.md"), "--resamples", "10"]


def test_main_creates_separate_output_directories(tmp_path, monkeypatch):
    args = _cli_args(tmp_path, monkeypatch)
    assert rep.main(args) == 0
    assert (tmp_path / "markdown" / "r.md").is_file()
    assert json.loads((tmp_path / "json" / "r.json").read_text())["legs"]["A"]["power"]["n"] == 1


def test_invalid_ledger_date_refuses_before_writing_outputs(tmp_path, monkeypatch, capsys):
    args = _cli_args(tmp_path, monkeypatch) + ["--date", "not-a-date"]
    assert rep.main(args) == 1
    assert "error:" in capsys.readouterr().err
    assert not (tmp_path / "json" / "r.json").exists()


def test_output_write_error_returns_one_without_ledger_row(tmp_path, monkeypatch, capsys):
    args = _cli_args(tmp_path, monkeypatch)
    (tmp_path / "markdown").write_text("a file blocks the output directory", encoding="utf-8")
    assert rep.main(args) == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err and "LEDGER ROW:" not in captured.out


def test_non_finite_trade_refuses_json_output(tmp_path, monkeypatch, capsys):
    args = _cli_args(tmp_path, monkeypatch)
    _write_leg(tmp_path, "b", [_row("AAA", "2021-03-01", r=float("inf"))], PROV_B)
    assert rep.main(args) == 1
    assert "error:" in capsys.readouterr().err
    assert not (tmp_path / "json" / "r.json").exists()
