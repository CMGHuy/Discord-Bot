"""The v116 soak: what the nightly check logs and how a gate reads it."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import v116_soak as soak  # noqa: E402
from scripts.db.parity_report import STAGE_STORES  # noqa: E402

DUAL_OPS = {name: "dual" for name in soak.GROUPS["ops"]}


def _line(day, result="CLEAN", stage="dual", trading="yes", group="ops"):
    return (f"VERDICT day={day} trading_day={trading} group={group} "
            f"stage={stage} result={result} errors=0")


def test_every_stage_name_is_in_exactly_one_group():
    names = [name for group in soak.GROUPS.values() for name in group]
    assert len(names) == len(set(names))
    assert set(STAGE_STORES) <= set(names)


def test_group_stage_reports_mixed_mid_flip():
    assert soak.group_stage(DUAL_OPS, "ops") == "dual"
    assert soak.group_stage({**DUAL_OPS, "flags": "db"}, "ops") == "mixed"
    assert soak.group_stage({}, "trading") == "json"


def test_check_is_clean_only_with_parity_clean_and_no_errors():
    clean = soak.check_lines("2026-10-05", True, 0, DUAL_OPS, lambda _n: True)
    assert clean[-1] == _line("2026-10-05")
    dirty = soak.check_lines("2026-10-05", True, 3, DUAL_OPS, lambda _n: True)
    assert dirty[-1].endswith("result=DIRTY errors=3")
    parity_bad = soak.check_lines("2026-10-05", True, 0, DUAL_OPS, lambda n: n != "jobs")
    assert "result=DIRTY" in parity_bad[-1]
    assert any("parity[jobs] DIRTY" in line for line in parity_bad)


def test_check_skips_groups_still_at_json():
    assert soak.check_lines("2026-10-05", True, 0, {}, lambda _n: True) == []


def test_five_consecutive_clean_trading_days_pass():
    days = ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]
    assert soak.gate([_line(d) for d in days], "ops", "dual") == ("PASS", 5)


def test_four_days_wait():
    days = ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"]
    assert soak.gate([_line(d) for d in days], "ops", "dual") == ("WAIT", 4)


def test_a_dirty_day_fails_and_restarts_the_count():
    lines = [_line("2026-10-05"), _line("2026-10-06", "DIRTY")]
    assert soak.gate(lines, "ops", "dual") == ("DIRTY", 0)
    lines += [_line("2026-10-07"), _line("2026-10-08")]
    assert soak.gate(lines, "ops", "dual") == ("WAIT", 2)


def test_a_missing_weekday_breaks_the_streak_but_a_logged_holiday_does_not():
    gap = [_line("2026-10-05"), _line("2026-10-06"), _line("2026-10-08")]
    assert soak.gate(gap, "ops", "dual") == ("WAIT", 1)
    holiday = [_line("2026-10-05"), _line("2026-10-06"),
               _line("2026-10-07", trading="no"), _line("2026-10-08")]
    assert soak.gate(holiday, "ops", "dual") == ("WAIT", 3)


def test_days_at_another_stage_do_not_count():
    lines = [_line("2026-10-05", stage="db"), _line("2026-10-06")]
    assert soak.gate(lines, "ops", "dual") == ("WAIT", 1)


def test_the_cron_script_counts_database_errors_and_calls_check():
    text = (ROOT / "scripts" / "ops" / "v116_parity_check.sh").read_text(encoding="utf-8")
    assert "logs/v116_parity.log" in text
    assert "StoreWriteHalt" in text and "sqlalchemy" in text and "dual\[" in text
    assert "v116_soak.py check --error-lines" in text
    assert b"\r" not in (ROOT / "scripts" / "ops" / "v116_parity_check.sh").read_bytes()
    installer = (ROOT / "scripts" / "ops" / "install_v116_soak_cron.sh").read_text(encoding="utf-8")
    assert "15 22 * * 1-5" in installer
