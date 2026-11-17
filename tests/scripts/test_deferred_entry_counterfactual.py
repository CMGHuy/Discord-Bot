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
