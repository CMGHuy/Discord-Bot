"""v183 impact report: closed shorts re-sized under the gap rule at fixed risk (read-only)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.analytics.risk_metrics import max_drawdown_r
from swingbot.core.market import opex
from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import short_gap_sizing_impact as imp  # noqa: E402

BAL, RISK = 10_000.0, 1.0          # fixed risk: $100 per trade


def _bars(up_pct, n=300, start="2024-01-01"):
    """Close 100 every day; even days open up_pct above the prior close, odd days 0.5% below,
    so every up-gap equals up_pct (p99 == up_pct) and n_up is about n / 2."""
    rows = []
    for i in range(n):
        o = 100.0 * (1 + up_pct / 100.0) if i % 2 == 0 else 99.5
        rows.append((o, max(o, 100.0) * 1.001, min(o, 100.0) * 0.999, 100.0))
    return make_ohlcv(rows, start=start)


def _short(tid="t1", ticker="AAA", exit_price=103.0, status="loss", opened="2025-03-01T15:00:00+00:00",
           closed="2025-03-05T15:00:00+00:00", **kw):
    t = {"id": tid, "ticker": ticker, "direction": "bearish", "status": status,
         "entry": 100.0, "stop_loss": 101.0, "exit_price": exit_price,
         "opened_at": opened, "closed_at": closed}
    t.update(kw)
    return t


def _run(trades, frames):
    return imp.resize_closed_shorts(trades, frames, balance=BAL, risk_pct=RISK)


def test_gap_wider_than_stop_cuts_shares_and_keeps_the_real_r():
    out = _run([_short()], {"AAA": _bars(3.0)})
    (row,) = out["rows"]
    assert row["p99_source"] == "bars"
    assert row["p99"] == pytest.approx(3.0)
    assert row["shares_before"] == pytest.approx(100.0)          # $100 / $1 stop
    assert row["shares_after"] == pytest.approx(33.33)           # $100 / max($1, 100 x 3%)
    assert row["gap_sized"] is True
    assert row["r"] == pytest.approx(-3.0)                       # gapped through to 103: real R, not -1
    assert row["pnl_before"] == pytest.approx(-300.0)
    assert row["pnl_after"] == pytest.approx(-99.99)
    s = out["summary"]
    assert s["n_gap_sized"] == 1 and s["share_gap_sized_pct"] == pytest.approx(100.0)
    assert s["mean_cut_pct_gap_sized"] == pytest.approx(66.67, abs=0.01)


def test_stop_wider_than_gap_leaves_the_size_alone():
    (row,) = _run([_short()], {"AAA": _bars(0.5)})["rows"]
    assert row["shares_after"] == row["shares_before"]
    assert row["gap_sized"] is False
    assert row["pnl_after"] == row["pnl_before"]


def test_too_few_up_gaps_means_no_p99_and_no_cut():
    out = _run([_short()], {"AAA": _bars(3.0, n=40)})
    (row,) = out["rows"]
    assert (row["p99"], row["p99_source"]) == (None, "none")
    assert row["shares_after"] == row["shares_before"]
    assert out["summary"]["n_no_p99"] == 1


def test_missing_bars_mean_no_p99():
    (row,) = _run([_short()], {})["rows"]
    assert row["p99_source"] == "none"


def test_only_bars_before_the_open_count():
    early = _bars(0.5, n=300, start="2023-01-02")
    first_late = early.index[-1] + pd.offsets.BDay(1)
    late = _bars(3.0, n=300, start=str(first_late.date()))
    opened = first_late.strftime("%Y-%m-%dT14:00:00+00:00")     # 10:00 New York on the first stormy day
    (row,) = _run([_short(opened=opened)], {"AAA": pd.concat([early, late])})["rows"]
    assert row["p99"] == pytest.approx(0.5)
    assert row["gap_sized"] is False


def test_stored_stamp_wins_over_bars():
    stamp = {"rule": "gap_p99", "up_gap_p99_pct": 2.0, "n_up_gaps": 120}
    (row,) = _run([_short(gap_sizing=stamp)], {})["rows"]
    assert (row["p99"], row["p99_source"]) == (2.0, "stamp")
    assert row["shares_after"] == pytest.approx(50.0)


def test_longs_open_trades_and_unpriceable_records_are_left_out():
    trades = [_short(), _short(tid="o", status="open"), _short(tid="l", direction="bullish"),
              _short(tid="z", stop_loss=100.0)]
    out = _run(trades, {"AAA": _bars(3.0)})
    assert out["n_closed_shorts"] == 2                            # t1 and the zero-risk z
    assert [r["id"] for r in out["rows"]] == ["t1"]


def test_worst_five_are_sorted_per_side_and_capped_at_five():
    trades = [_short(tid=f"t{i}", exit_price=100.0 + i, closed=f"2025-03-{10 + i}T15:00:00+00:00")
              for i in range(1, 7)]
    s = _run(trades, {"AAA": _bars(3.0)})["summary"]
    assert len(s["worst_before"]) == 5 and len(s["worst_after"]) == 5
    assert [w["pnl_before"] for w in s["worst_before"]] == sorted(w["pnl_before"] for w in s["worst_before"])
    assert s["worst_before"][0]["pnl_before"] == pytest.approx(-600.0)


def test_drawdown_is_taken_in_close_order_on_each_side():
    trades = [_short(tid="b", exit_price=103.0, closed="2025-03-03T15:00:00+00:00"),
              _short(tid="a", exit_price=98.0, closed="2025-03-02T15:00:00+00:00"),
              _short(tid="c", exit_price=99.0, closed="2025-03-04T15:00:00+00:00")]
    out = _run(trades, {"AAA": _bars(3.0)})
    ordered = sorted(out["rows"], key=lambda r: r["closed_at"])   # a (+2R), b (-3R), c (+1R)
    dd = out["summary"]["drawdown"]
    assert dd["before"]["max_dd_dollars"] == pytest.approx(max_drawdown_r([r["pnl_before"] for r in ordered]))
    assert dd["before"]["max_dd_dollars"] == pytest.approx(300.0)
    assert dd["after"]["max_dd_dollars"] == pytest.approx(max_drawdown_r([r["pnl_after"] for r in ordered]))
    assert dd["after"]["max_dd_dollars"] < dd["before"]["max_dd_dollars"]
    assert set(dd["before"]) >= {"bootstrap_dd_p50", "bootstrap_dd_p95"}


def test_opex_scaling_never_changes_the_fixed_risk(monkeypatch):
    monkeypatch.setattr(opex, "size_mult", lambda *a, **k: 0.5)
    (row,) = _run([_short()], {"AAA": _bars(3.0)})["rows"]
    assert row["shares_before"] == pytest.approx(100.0)


def test_empty_book_renders_without_numbers():
    out = _run([], {})
    assert out["summary"]["n_analysed"] == 0
    text = imp.render_markdown(out, run_date="2026-11-02", db_name="swingbot_prod_replica",
                               balance=BAL, risk_pct=RISK)
    assert "n/a" in text and "not a gate" in text


def test_markdown_carries_every_measure_and_the_rollback_note():
    out = _run([_short()], {"AAA": _bars(3.0)})
    text = imp.render_markdown(out, run_date="2026-11-02", db_name="swingbot_prod_replica",
                               balance=BAL, risk_pct=RISK)
    for needle in ("# v183 gap sizing impact", "## Result", "## Worst five dollar losses",
                   "## Short-book drawdown", "## Limits", "## Rollback", "SHORT_GAP_SIZING=false",
                   "SHORT_RISK_NOTICE=false", "rollback_to.sh", "stay in the book as recorded",
                   "-$300.00", "-$99.99", "not a gate"):
        assert needle in text, needle


def test_db_name_swap_keeps_credentials_and_host():
    url = "postgresql+psycopg://u:secret@db.local:5432/swingbot"
    assert imp._with_db(url, "swingbot_prod_replica") == \
        "postgresql+psycopg://u:secret@db.local:5432/swingbot_prod_replica"


def test_target_accepts_a_name_or_a_full_url():
    cfg = "postgresql+psycopg://u:p@h:5/swingbot"
    assert imp._target("replica", cfg) == ("postgresql+psycopg://u:p@h:5/replica", "replica")
    full = "postgresql+psycopg://x:y@127.0.0.1:9/other"
    assert imp._target(full, cfg) == (full, "other")


def test_csv_frames_pick_the_freshest_file_per_ticker(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    _bars(0.5, n=5, start="2024-01-01").to_csv(a / "AAA.csv")
    _bars(0.5, n=9, start="2024-01-01").to_csv(b / "AAA.csv")
    out = imp._csv_frames(["AAA", "ZZZ"], [a, b])
    assert len(out["AAA"]) == 9 and out["ZZZ"] is None


# --- v191: --side long / both ----------------------------------------------------------------

def _down_bars(down_pct, n=300, start="2024-01-01"):
    """Close 100 every day; even days open down_pct below the prior close, odd days 0.5% above,
    so every down-gap equals down_pct (p99 == down_pct) and n_down is about n / 2."""
    rows = []
    for i in range(n):
        o = 100.0 * (1 - down_pct / 100.0) if i % 2 == 0 else 100.5
        rows.append((o, max(o, 100.0) * 1.001, min(o, 100.0) * 0.999, 100.0))
    return make_ohlcv(rows, start=start)


def _long(tid="l1", ticker="AAA", exit_price=97.0, status="loss", **kw):
    t = {"id": tid, "ticker": ticker, "direction": "bullish", "status": status,
         "entry": 100.0, "stop_loss": 99.0, "exit_price": exit_price,
         "opened_at": "2025-03-01T15:00:00+00:00", "closed_at": "2025-03-05T15:00:00+00:00"}
    t.update(kw)
    return t


def _run_long(trades, frames):
    return imp.resize_closed(trades, frames, side=imp.LONG, balance=BAL, risk_pct=RISK)


def test_sides_table():
    assert imp.SIDES == {"short": imp.SHORT, "long": imp.LONG}
    assert (imp.LONG.direction, imp.LONG.stamp_key, imp.LONG.stats_key, imp.LONG.count_key) == \
        ("bullish", "down_gap_p99_pct", "p99_down_gap_pct", "n_down")
    assert imp.LONG.min_gaps == imp.MIN_DOWN_GAPS == 60
    assert (imp.SHORT.direction, imp.SHORT.stamp_key) == ("bearish", "up_gap_p99_pct")


def test_long_down_gap_wider_than_stop_cuts_shares_and_counts_the_exceedance():
    out = _run_long([_long()], {"AAA": _down_bars(3.0)})
    (row,) = out["rows"]
    assert out["n_closed_longs"] == 1
    assert (row["p99"], row["p99_source"]) == (pytest.approx(3.0), "bars")
    assert row["shares_before"] == pytest.approx(100.0)
    assert row["shares_after"] == pytest.approx(33.33)
    assert row["r"] == pytest.approx(-3.0)                       # gapped through 99 to 97
    assert (row["pnl_before"], row["pnl_after"]) == (pytest.approx(-300.0), pytest.approx(-99.99))
    s = out["summary"]
    assert (s["n_exceed_before"], s["n_exceed_after"]) == (1, 0)


def test_long_stamp_wins_and_too_few_down_gaps_mean_no_cut():
    stamp = {"rule": "gap_p99", "down_gap_p99_pct": 2.0, "n_down_gaps": 120}
    (row,) = _run_long([_long(gap_sizing=stamp)], {})["rows"]
    assert (row["p99"], row["p99_source"], row["shares_after"]) == (2.0, "stamp", pytest.approx(50.0))
    (row,) = _run_long([_long()], {"AAA": _down_bars(3.0, n=40)})["rows"]
    assert (row["p99"], row["p99_source"]) == (None, "none")
    assert row["shares_after"] == row["shares_before"]


def test_each_side_reads_only_its_own_direction():
    trades = [_long(), _short()]
    assert [r["id"] for r in _run_long(trades, {"AAA": _down_bars(3.0)})["rows"]] == ["l1"]
    assert [r["id"] for r in _run(trades, {"AAA": _bars(3.0)})["rows"]] == ["t1"]


def test_short_summary_counts_exceedances_but_its_markdown_is_unchanged():
    out = _run([_short()], {"AAA": _bars(3.0)})
    assert (out["summary"]["n_exceed_before"], out["summary"]["n_exceed_after"]) == (1, 0)
    text = imp.render_markdown(out, run_date="2026-11-02", db_name="swingbot_prod_replica",
                               balance=BAL, risk_pct=RISK)
    assert "Losses past the fixed risk" not in text
    assert "| Closed shorts in the book | 1 |" in text
    assert "| Mean size cut, gap-sized shorts |" in text


def test_long_markdown_carries_every_measure_and_the_coupled_rollback():
    out = _run_long([_long()], {"AAA": _down_bars(3.0)})
    text = imp.render_long_markdown(out, run_date="2026-11-02", db_name="swingbot_prod_replica",
                                    balance=BAL, risk_pct=RISK)
    for needle in ("# v191 gap sizing impact: the live book's closed longs re-sized",
                   "| Closed longs in the book | 1 |", "| Losses past the fixed risk, before | 1 |",
                   "| Losses past the fixed risk, after | 0 |", "## Long-book drawdown",
                   "## Limits", "## Rollback", "LONG_GAP_SIZING=false",
                   "CONFLUENCE_ATR_STOP_FLOOR", "stay in the book as recorded",
                   "-$300.00", "-$99.99", "not a gate", "--side long"):
        assert needle in text, needle


def _main(monkeypatch, tmp_path, capsys, name, *extra):
    from swingbot import config
    from swingbot.core.db import engine
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://u:p@h:5/swingbot")
    monkeypatch.setattr(engine, "reset_engine", lambda: None)
    monkeypatch.setattr(imp, "_trades", lambda: [_short(), _long()])
    monkeypatch.setattr(imp, "_frames", lambda tickers: {"AAA": _bars(3.0)})
    out = tmp_path / name
    assert imp.main(["--out", str(out), *extra]) == 0
    return capsys.readouterr().out, out.read_text(encoding="utf-8")


def test_default_side_is_short_and_byte_identical(monkeypatch, tmp_path, capsys):
    default_out, default_md = _main(monkeypatch, tmp_path, capsys, "a.md")
    short_out, short_md = _main(monkeypatch, tmp_path, capsys, "b.md", "--side", "short")
    assert (default_out, default_md) == (short_out, short_md)
    result = imp.resize_closed_shorts([_short(), _long()], {"AAA": _bars(3.0)},
                                      balance=BAL, risk_pct=RISK)
    assert default_out == "\n".join(imp._stdout_lines(result)) + "\n"
    run_date = default_md.split("**Run:** ")[1][:10]
    assert default_md == imp.render_markdown(result, run_date=run_date,
                                             db_name="swingbot_prod_replica", balance=BAL, risk_pct=RISK)


def test_both_sides_print_and_write_short_then_long(monkeypatch, tmp_path, capsys):
    out, md = _main(monkeypatch, tmp_path, capsys, "c.md", "--side", "both")
    lines = out.splitlines()
    assert lines[0].startswith("closed_shorts: ")
    assert any(line.startswith("closed_longs: ") for line in lines)
    assert lines[-1].startswith("exceed_before/after: ")
    assert md.index("closed shorts re-sized") < md.index("closed longs re-sized")


def test_short_report_matches_pre_v191_output_bytes():
    import hashlib
    result = _run([_short()], {"AAA": _bars(3.0)})
    markdown = imp.render_markdown(result, run_date="2026-11-02", db_name="swingbot_prod_replica",
                                   balance=BAL, risk_pct=RISK)
    stdout = "\n".join(imp._stdout_lines(result)) + "\n"
    assert hashlib.sha256(markdown.encode()).hexdigest() == \
        "a938a65ea93b4f037e8d990c168b22ffc88086380abe94559dcf26dd3a67817e"
    assert hashlib.sha256(stdout.encode()).hexdigest() == \
        "02d2dc5180e06f2e58070db6364fa16ef98492fc083419cc2c08dc272a9c07fe"


def test_long_p99_ignores_open_session_and_future_bars():
    early = _down_bars(0.5, n=300, start="2023-01-02")
    first_late = early.index[-1] + pd.offsets.BDay(1)
    late = _down_bars(9.0, n=300, start=str(first_late.date()))
    trade = _long(opened_at=first_late.strftime("%Y-%m-%dT14:00:00+00:00"))
    full = imp.trade_p99(trade, pd.concat([early, late]), imp.LONG)
    truncated = imp.trade_p99(trade, early, imp.LONG)
    assert full == truncated == (pytest.approx(0.5), "bars")


def test_empty_long_book_renders_without_numbers():
    result = _run_long([], {})
    assert result["n_closed_longs"] == 0
    text = imp.render_long_markdown(result, run_date="2026-11-02", db_name="replica",
                                    balance=BAL, risk_pct=RISK)
    assert "n/a" in text
    assert "| Losses past the fixed risk, after | 0 |" in text
