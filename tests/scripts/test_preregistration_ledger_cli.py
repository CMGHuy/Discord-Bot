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
