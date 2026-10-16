"""v162 AH23: the §5 re-baseline tooling. A frozen, hashed yfinance snapshot,
one explicit ticker set for every leg, and a report that checks each leg's
provenance and window before it computes paired week-clustered intervals."""
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

import snapshot_backtest_cache as snap
from swingbot import config
from swingbot.core.marketdata import training_data

ROOT = Path(__file__).resolve().parents[2]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a @dataclass resolves its module through sys.modules
    spec.loader.exec_module(module)
    return module


rbr = _load("rbr_v162_ah23", "scripts/backtest/run_backtest_range.py")
rep = _load("v162_rebaseline_report", "scripts/reports/v162_rebaseline_report.py")


def _cache(folder: Path, tickers, start="2014-01-02", days=600):
    folder.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start, periods=days, name="Date")
    for t in tickers:
        frame = pd.DataFrame({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 100.0},
                             index=idx)
        frame.to_csv(folder / f"{t}.csv")
    return folder


# --- tickers file ------------------------------------------------------------

def test_tickers_file_is_upper_cased_deduplicated_sorted_with_comments(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("msft\n# a comment line\nAAPL  # trailing comment\n\nmsft\n", encoding="utf-8")
    assert snap.read_tickers_file(f) == ["AAPL", "MSFT"]


def test_csv_name_follows_the_cache_naming():
    assert snap.csv_name("AAPL") == "AAPL.csv"
    assert snap.csv_name("GC=F") == "GC_F.csv"


# --- snapshot ----------------------------------------------------------------

def test_snapshot_copies_bytes_and_hashes_every_file(tmp_path):
    src = _cache(tmp_path / "cache", ["AAPL", "SPY"])
    manifest = snap.snapshot(src, tmp_path / "snap")
    assert sorted(manifest["files"]) == ["AAPL.csv", "SPY.csv"]
    assert (tmp_path / "snap" / "AAPL.csv").read_bytes() == (src / "AAPL.csv").read_bytes()
    on_disk = json.loads((tmp_path / "snap" / "_hashes.json").read_text(encoding="utf-8"))
    assert on_disk == manifest
    assert manifest["hash"] == snap.combined_hash(manifest["files"])
    assert manifest["start"] is None and manifest["src"] == str(src)
    assert snap.verify(tmp_path / "snap") == []


def test_start_drops_earlier_rows_and_keeps_the_date_header(tmp_path):
    src = _cache(tmp_path / "cache", ["AAPL"], start="2015-06-01")
    snap.snapshot(src, tmp_path / "snap", start="2016-01-01")
    out = pd.read_csv(tmp_path / "snap" / "AAPL.csv", index_col="Date", parse_dates=True)
    assert out.index.min() >= pd.Timestamp("2016-01-01")
    assert out.index.min() < pd.Timestamp("2016-01-08")
    full = pd.read_csv(src / "AAPL.csv", index_col="Date", parse_dates=True)
    assert len(out) == int((full.index >= pd.Timestamp("2016-01-01")).sum())
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_a_ticker_list_copies_exactly_those_and_fails_on_a_missing_one(tmp_path):
    src = _cache(tmp_path / "cache", ["AAPL", "MSFT", "SPY"])
    manifest = snap.snapshot(src, tmp_path / "snap", tickers=["AAPL", "SPY"])
    assert sorted(manifest["files"]) == ["AAPL.csv", "SPY.csv"]
    with pytest.raises(FileNotFoundError, match="NVDA.csv"):
        snap.snapshot(src, tmp_path / "snap2", tickers=["AAPL", "NVDA"])
    assert not (tmp_path / "snap2").exists()


def test_a_non_empty_target_is_never_overwritten(tmp_path):
    src = _cache(tmp_path / "cache", ["AAPL"])
    snap.snapshot(src, tmp_path / "snap")
    with pytest.raises(FileExistsError):
        snap.snapshot(src, tmp_path / "snap")


def test_verify_names_changed_missing_and_extra_files(tmp_path):
    src = _cache(tmp_path / "cache", ["AAPL", "MSFT"])
    out = tmp_path / "snap"
    snap.snapshot(src, out)
    (out / "AAPL.csv").write_text("Date,Open\n", encoding="utf-8")
    (out / "MSFT.csv").unlink()
    (out / "NVDA.csv").write_text("Date,Open\n", encoding="utf-8")
    assert snap.verify(out) == ["CHANGED AAPL.csv", "MISSING MSFT.csv", "EXTRA NVDA.csv"]


def test_cli_adds_the_benchmark_to_a_ticker_list(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    src = _cache(tmp_path / "cache", ["AAPL", "MSFT", "SPY"])
    tickers = tmp_path / "t.txt"
    tickers.write_text("AAPL\n", encoding="utf-8")
    out = tmp_path / "snap"
    assert snap.main(["--src", str(src), "--out", str(out), "--tickers-file", str(tickers)]) == 0
    assert sorted(json.loads((out / "_hashes.json").read_text(encoding="utf-8"))["files"]) == ["AAPL.csv", "SPY.csv"]
    assert snap.main(["--verify", str(out)]) == 0
    (out / "AAPL.csv").write_text("x\n", encoding="utf-8")
    assert snap.main(["--verify", str(out)]) == 1


def test_cli_reports_a_refusal_as_exit_1(tmp_path, capsys):
    src = _cache(tmp_path / "cache", ["AAPL"])
    snap.snapshot(src, tmp_path / "snap")
    assert snap.main(["--src", str(src), "--out", str(tmp_path / "snap")]) == 1
    assert "never overwritten" in capsys.readouterr().err


# --- intersection --------------------------------------------------------------

def _manifest(statuses):
    return {"timeframe": "daily", "feed": "sip", "adjustment": "all", "hash": "h",
            "tickers": {t: {"status": s} for t, s in statuses.items()}}


def test_intersection_keeps_watchlist_tickers_ok_in_the_store_and_cached(tmp_path):
    cache = _cache(tmp_path / "cache", ["AAPL", "MSFT", "SPY", "TSLA"])
    manifest = _manifest({"AAPL": "ok", "MSFT": "flagged: price-mismatch", "SPY": "ok",
                          "NVDA": "ok", "TSLA": "ok"})
    watchlist = ["aapl", "MSFT", "NVDA", "TSLA"]
    assert snap.intersection_tickers(watchlist, manifest, cache) == ["AAPL", "TSLA"]


def test_cli_writes_the_intersection_from_the_store_manifest(tmp_path, store_root):
    daily = store_root / "daily"
    daily.mkdir(parents=True)
    (daily / "_manifest.json").write_text(json.dumps(_manifest({"AAPL": "ok", "MSFT": "ok"})),
                                          encoding="utf-8")
    cache = _cache(tmp_path / "cache", ["AAPL"])
    watch = tmp_path / "watch.txt"
    watch.write_text("AAPL\nMSFT\n", encoding="utf-8")
    out = tmp_path / "tickers.txt"
    assert snap.main(["--intersect-out", str(out), "--watchlist-file", str(watch),
                      "--src", str(cache)]) == 0
    assert out.read_text(encoding="utf-8") == "AAPL\n"


def test_cli_intersection_without_a_store_is_an_error(tmp_path, store_root, capsys):
    watch = tmp_path / "watch.txt"
    watch.write_text("AAPL\n", encoding="utf-8")
    assert snap.main(["--intersect-out", str(tmp_path / "t.txt"), "--watchlist-file", str(watch),
                      "--src", str(_cache(tmp_path / "cache", ["AAPL"]))]) == 1
    assert "_manifest.json" in capsys.readouterr().err


# --- run_backtest_range --tickers-file ---------------------------------------

def test_tickers_file_replaces_the_watchlist(tmp_path, monkeypatch):
    f = tmp_path / "t.txt"
    f.write_text("msft\nAAPL\n", encoding="utf-8")
    monkeypatch.setattr(rbr, "load_watchlist", lambda: pytest.fail("the watchlist was read"))
    assert rbr._tickers_for_run(None, str(f)) == ["AAPL", "MSFT"]


def test_without_a_file_the_watchlist_is_used(monkeypatch):
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["MSFT", "AAPL"])
    assert rbr._tickers_for_run(None) == ["AAPL", "MSFT"]


def test_tickers_file_and_universe_are_exclusive(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("AAPL\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="exclusive"):
        rbr._tickers_for_run("etfs", str(f))


def test_an_empty_tickers_file_is_an_error(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("# nothing\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="names no ticker"):
        rbr._tickers_from_file(str(f))


def test_both_run_modes_pass_the_file_through():
    src = (ROOT / "scripts" / "backtest" / "run_backtest_range.py").read_text(encoding="utf-8")
    assert '"--tickers-file"' in src
    assert "tickers = _tickers_for_run(args.universe, args.tickers_file)" in src
    assert "tickers = _tickers_for_run(universe, tickers_file)" in src
    assert "tickers_file=args.tickers_file" in src


# --- report ------------------------------------------------------------------

WEEKS = ("2021-01-04", "2021-01-11", "2021-01-18", "2021-01-25")


def _row(ticker, day, outcome, r):
    return {"ticker": ticker, "strategy": "RSI", "horizon_key": "swing", "entry_date": day,
            "exit_date": day, "direction": "long", "entry": 10.0, "stop_loss": 9.0,
            "take_profit": 12.0, "outcome": outcome, "exit_price": 11.0, "return_pct": 1.0,
            "r_multiple": r, "holding_days": 3, "runner_outcome": None, "context": None}


def _snapshot_dir(tmp_path, name="snap", digest="snaphash"):
    folder = tmp_path / name
    folder.mkdir(exist_ok=True)
    (folder / "_hashes.json").write_text(json.dumps({"hash": digest, "files": {}}), encoding="utf-8")
    return folder


def _write_leg(tmp_path, name, rows, *, source, store_dir):
    path = tmp_path / f"{name}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    prov = {"data_source": source, "feed": "sip" if source == "alpaca" else "yfinance",
            "adjustment": "all" if source == "alpaca" else "auto_adjust",
            "manifest_hash": "mhash" if source == "alpaca" else None,
            "store_dir": str(store_dir), "excluded": {}}
    training_data.provenance_path(path).write_text(json.dumps(prov), encoding="utf-8")
    return path


A_ROWS = [_row("AAPL", WEEKS[0], "win", 2.0), _row("AAPL", WEEKS[1], "loss", -1.0),
          _row("MSFT", WEEKS[2], "win", 2.0), _row("MSFT", WEEKS[3], "loss", -1.0)]
C_ROWS = [_row("AAPL", WEEKS[0], "win", 2.0), _row("AAPL", WEEKS[1], "win", 2.0),
          _row("MSFT", WEEKS[2], "win", 2.0), _row("MSFT", WEEKS[3], "loss", -1.0),
          _row("MSFT", WEEKS[3], "not_triggered", 0.0)]


@pytest.fixture
def legs(tmp_path):
    yf = _snapshot_dir(tmp_path)
    return {"a": _write_leg(tmp_path, "a", A_ROWS, source="yfinance", store_dir=yf),
            "b": _write_leg(tmp_path, "b", A_ROWS, source="yfinance", store_dir=yf),
            "c": _write_leg(tmp_path, "c", C_ROWS, source="alpaca", store_dir=tmp_path / "store")}


def _report(legs, window="train", resamples=300):
    trades = {k: rep.load_trades([p]) for k, p in legs.items()}
    prov = {k: rep.load_provenance(k, [p]) for k, p in legs.items()}
    return rep.build_report(trades, prov, window, n_resamples=resamples)


def test_parse_leg():
    assert rep.parse_leg("a=x.jsonl") == ("a", [Path("x.jsonl")])
    assert rep.parse_leg("C=x.jsonl,y.jsonl") == ("c", [Path("x.jsonl"), Path("y.jsonl")])
    for bad in ("d=x.jsonl", "a", "a="):
        with pytest.raises(Exception):
            rep.parse_leg(bad)


def test_leg_stats_match_the_runner_pool(legs):
    report = _report(legs)
    a, c = report["legs"]["a"], report["legs"]["c"]
    assert (a["trades"], a["n_eval"], a["wins"], a["win_rate"], a["expectancy_r"]) == (4, 4, 2, 50.0, 0.5)
    assert (c["trades"], c["n_eval"], c["wins"], c["win_rate"], c["expectancy_r"]) == (4, 4, 3, 75.0, 1.25)
    assert c["tickers"] == 2


def test_differences_carry_paired_week_clustered_intervals(legs):
    report = _report(legs)
    total = next(x for x in report["comparisons"] if (x["base"], x["comp"]) == ("a", "c"))
    assert total["expectancy_r"]["point"] == pytest.approx(0.75)
    assert total["win_rate"]["point"] == pytest.approx(25.0)
    lo, hi = total["expectancy_r"]["ci95"]
    assert lo <= 0.75 <= hi and total["expectancy_r"]["draws"] == 300
    same = next(x for x in report["comparisons"] if (x["base"], x["comp"]) == ("a", "b"))
    assert same["expectancy_r"]["point"] == 0.0 and same["expectancy_r"]["ci95"] == [0.0, 0.0]
    assert [(x["base"], x["comp"]) for x in report["comparisons"]] == [("a", "b"), ("b", "c"), ("a", "c")]


def test_provenance_and_snapshot_hash_are_recorded(legs):
    report = _report(legs)
    assert report["legs"]["a"]["provenance"]["snapshot_hash"] == "snaphash"
    assert report["legs"]["c"]["provenance"]["manifest_hash"] == "mhash"
    assert (report["window"], report["from"], report["to"]) == ("train", "2020-01-01", "2023-12-31")


def test_per_ticker_counts(legs):
    assert _report(legs)["per_ticker"] == {"AAPL": {"a": 2, "b": 2, "c": 2},
                                           "MSFT": {"a": 2, "b": 2, "c": 2}}


def test_a_leg_with_the_wrong_source_is_refused(tmp_path):
    path = _write_leg(tmp_path, "c", C_ROWS, source="yfinance", store_dir=_snapshot_dir(tmp_path))
    with pytest.raises(ValueError, match="leg c must be alpaca"):
        rep.load_provenance("c", [path])


def test_a_yfinance_leg_off_a_live_cache_is_refused(tmp_path):
    path = _write_leg(tmp_path, "a", A_ROWS, source="yfinance", store_dir=tmp_path / "live_cache")
    with pytest.raises(ValueError, match="not a v162 snapshot"):
        rep.load_provenance("a", [path])


def test_chunk_files_must_agree_on_provenance(tmp_path):
    one = _write_leg(tmp_path, "c1", C_ROWS, source="alpaca", store_dir=tmp_path / "store")
    two = _write_leg(tmp_path, "c2", C_ROWS, source="alpaca", store_dir=tmp_path / "other")
    with pytest.raises(ValueError, match="disagree"):
        rep.load_provenance("c", [one, two])
    assert len(rep.load_trades([one, one])) == 8


def test_a_missing_sidecar_is_refused(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_text(json.dumps(A_ROWS[0]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no provenance sidecar"):
        rep.load_provenance("a", [path])


def test_a_trade_outside_the_window_is_refused(legs):
    with pytest.raises(ValueError, match="outside fold-train"):
        trades = {k: rep.load_trades([p]) for k, p in legs.items()}
        trades["a"].append(rep.Trade("AAPL", "RSI", "2023-06-01", "win", 2.0))
        prov = {k: rep.load_provenance(k, [p]) for k, p in legs.items()}
        rep.build_report(trades, prov, "fold-train", n_resamples=50)


def test_a_closed_trade_without_r_is_an_error(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text(json.dumps(_row("AAPL", WEEKS[0], "win", None)) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="without r_multiple"):
        rep.load_trades([path])


def test_markdown_puts_difference_interval_window_and_n_in_one_sentence(legs):
    md = rep.render_markdown(_report(legs))
    line = next(l for l in md.splitlines() if l.startswith("- total"))
    assert "ExpR +0.750 R" in line and "95% CI" in line
    assert "window train 2020-01-01..2023-12-31" in line and "N 4 -> 4" in line
    assert "not a lift" in md


def test_cli_merges_both_windows_into_one_json(legs, tmp_path):
    out = tmp_path / "rebaseline.json"
    md = tmp_path / "train.md"
    args = [f"--leg=a={legs['a']}", f"--leg=b={legs['b']}", f"--leg=c={legs['c']}",
            "--out", str(out), "--resamples", "100"]
    assert rep.main(args + ["--window", "train", "--md", str(md)]) == 0
    assert rep.main(args + ["--window", "fold-train"]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert sorted(doc["windows"]) == ["fold-train", "train"]
    assert md.read_text(encoding="utf-8").startswith("### Window train")


def test_cli_needs_each_leg_once(legs):
    with pytest.raises(SystemExit):
        rep.main([f"--leg=a={legs['a']}", f"--leg=c={legs['c']}", "--window", "train",
                  "--out", "x.json"])


def test_cli_turns_a_provenance_problem_into_exit_1(tmp_path, capsys):
    yf = _snapshot_dir(tmp_path)
    a = _write_leg(tmp_path, "a", A_ROWS, source="yfinance", store_dir=yf)
    c = _write_leg(tmp_path, "c", C_ROWS, source="yfinance", store_dir=yf)
    code = rep.main([f"--leg=a={a}", f"--leg=b={a}", f"--leg=c={c}", "--window", "train",
                     "--out", str(tmp_path / "o.json"), "--resamples", "50"])
    assert code == 1 and "leg c must be alpaca" in capsys.readouterr().err
