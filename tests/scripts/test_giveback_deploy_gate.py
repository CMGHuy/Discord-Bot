"""v176 deploy gate: the per-plan old/new stop table shown before the push.

RKLB-like short (spec § Open trades at deploy): entry 63.0 and TP1 57.165 put
the runner floor at 59.11 (the live working stop), E = 49.94, last 52.30.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))

import giveback_deploy_gate as gate  # noqa: E402
import partial_runner_rows as prr  # noqa: E402

RKLB = {"plan_id": "47f7fd16-38d5-49d4-a917-d0fdb3376c85", "ticker": "RKLB",
        "direction": "bearish", "entry_price": 63.0, "stop_loss": 66.0, "tp1": 57.165,
        "working_stop": 59.11, "runner_high_close": 49.94, "last_price": 52.30}


def test_rklb_moves_to_its_giveback_and_stays_open():
    out = gate.gate_row(dict(RKLB), 5.0)
    assert out["floor"] == pytest.approx(59.11)
    assert out["current_stop"] == pytest.approx(59.11)
    assert out["extreme_used"] == pytest.approx(49.94)
    assert out["giveback_stop"] == pytest.approx(52.437)
    assert out["new_stop"] == pytest.approx(52.437)
    assert out["moves"] is True
    assert out["past"] is False                    # 52.30 < 52.437: no close on tick 1


def test_a_last_price_past_the_new_stop_closes_on_the_first_tick():
    out = gate.gate_row(dict(RKLB, last_price=52.50), 5.0)
    assert out["past"] is True


def test_a_new_extreme_on_the_first_tick_is_folded_in_first():
    out = gate.gate_row(dict(RKLB, last_price=48.0), 5.0)
    assert out["extreme_used"] == pytest.approx(48.0)
    assert out["new_stop"] == pytest.approx(50.4)
    assert out["past"] is False


def test_no_stored_extreme_takes_the_last_price_as_e():
    out = gate.gate_row(dict(RKLB, runner_high_close=None, last_price=55.0), 5.0)
    assert out["extreme_used"] == pytest.approx(55.0)
    assert out["new_stop"] == pytest.approx(57.75)
    assert out["past"] is False


def test_a_looser_giveback_never_moves_the_stop_long():
    row = {"plan_id": "p2", "ticker": "AAPL", "direction": "bullish", "entry_price": 100.0,
           "stop_loss": 95.0, "tp1": 110.0, "working_stop": None,
           "runner_high_close": 111.0, "last_price": 110.0}
    out = gate.gate_row(row, 5.0)
    assert out["current_stop"] == pytest.approx(100.0 + 20.0 / 3.0)
    assert out["giveback_stop"] == pytest.approx(105.45)
    assert out["new_stop"] == pytest.approx(out["current_stop"])
    assert out["moves"] is False


def test_unknown_last_price_leaves_past_unknown():
    out = gate.gate_row(dict(RKLB, last_price=None), 5.0)
    assert out["extreme_used"] == pytest.approx(49.94)
    assert out["past"] is None


def test_render_table_has_one_row_per_plan_and_names_the_columns():
    table = gate.render_table([gate.gate_row(dict(RKLB), 5.0)])
    lines = table.splitlines()
    assert lines[0].startswith("| plan | ticker | dir |")
    assert len(lines) == 3
    assert "47f7fd16" in lines[2] and "52.44" in lines[2] and "59.11" in lines[2]
    assert lines[2].rstrip().endswith("| no |")


def test_render_table_with_no_partial_plans_says_so():
    assert gate.render_table([]) == "No open PARTIAL plans: the give-back moves no stop at deploy."


def test_load_rows_ignores_log_noise_above_the_json_line():
    text = "INFO config loaded\n" + json.dumps([RKLB]) + "\n"
    assert gate.load_rows(text) == [RKLB]


def test_main_prints_the_table(tmp_path, capsys):
    path = tmp_path / "rows.txt"
    path.write_text(json.dumps([RKLB]) + "\n", encoding="utf-8")
    assert gate.main(["--rows", str(path), "--pct", "5.0"]) == 0
    assert "RKLB" in capsys.readouterr().out


def test_partial_rows_keeps_partial_plans_only_and_reads_the_price():
    def plan(pid, status, **kw):
        base = dict(plan_id=pid, ticker="RKLB", direction="bearish", entry_price=63.0,
                    stop_loss=66.0, tp1=57.165, working_stop=59.11,
                    runner_high_close=49.94, status=status)
        base.update(kw)
        return SimpleNamespace(**base)
    plans = [plan("a", "PARTIAL"), plan("b", "ACTIVE"), plan("c", "PENDING")]
    rows = prr.partial_rows(plans, lambda ticker: 52.30)
    assert [r["plan_id"] for r in rows] == ["a"]
    assert rows[0]["last_price"] == 52.30
    assert set(rows[0]) == {"plan_id", "ticker", "direction", "entry_price", "stop_loss",
                            "tp1", "working_stop", "runner_high_close", "last_price"}


def test_partial_rows_survives_a_price_failure():
    plans = [SimpleNamespace(plan_id="a", ticker="RKLB", direction="bearish", entry_price=63.0,
                             stop_loss=66.0, tp1=57.165, working_stop=None,
                             runner_high_close=None, status="PARTIAL")]

    def boom(ticker):
        raise RuntimeError("feed down")
    assert prr.partial_rows(plans, boom)[0]["last_price"] is None
