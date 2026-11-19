"""scripts/dev/guide_layout_check.py: the v236 guide layout check (V236-11).

Only the Playwright loop goes without a unit test; every verdict the result
note records comes from the pure functions pinned here.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
import guide_layout_check as glc  # noqa: E402

USER, PASSWORD = "user-secret-1", "pw-secret-2"


def test_importing_the_check_does_not_import_playwright():
    assert "playwright" not in sys.modules


@pytest.mark.parametrize("width, mode", [
    (390, "picker"), (639, "picker"), (640, "drawer"), (820, "drawer"),
    (1023, "drawer"), (1024, "rail"), (1440, "rail")])
def test_expected_toc_follows_the_breakpoints(width, mode):
    assert glc.expected_toc(width) == mode


def test_toc_wants_its_own_mode_and_no_other():
    assert glc.toc_problems(820, {"drawer": True, "rail": False, "picker": False}) == []
    assert glc.toc_problems(390, {"picker": False, "rail": True, "drawer": False}) == [
        "390px: contents picker (sb-select.guide-picker) not shown",
        "390px: contents rail (nav.guide-rail) shown, expected only the picker"]


def test_overflow_allows_one_pixel_of_rounding():
    assert glc.overflow_problems(390, "glossary", 1.0) == []
    assert glc.overflow_problems(390, "glossary", 12.4) == ["390px glossary: page overflows sideways by 12px"]
    assert glc.overflow_problems(1440, "", 3) == ["1440px /: page overflows sideways by 3px"]


def test_targets_count_on_phone_and_tablet_only():
    targets = [{"name": "Contents", "w": 90.0, "h": 30.0}, {"name": "#", "w": 44.0, "h": 44.0}]
    assert glc.target_problems(820, "pipeline", targets) == ["820px pipeline: Contents hit area 90x30px < 44"]
    assert glc.target_problems(1440, "pipeline", targets) == []


def test_deep_link_must_land_in_the_top_half():
    assert glc.deep_link_problems(390, "glossary#r-multiple", 64.0) == []
    assert glc.deep_link_problems(390, "glossary#r-multiple", None) == [
        "390px glossary#r-multiple: heading not found"]
    assert glc.deep_link_problems(390, "glossary#r-multiple", 700.0) == [
        "390px glossary#r-multiple: heading at 700px, not scrolled into the top half"]
    assert glc.deep_link_problems(390, "x#y", -5.0)[0].endswith("not scrolled into the top half")


def test_report_lists_each_width_and_every_problem():
    text = glc.render_report([{"width": 390, "problems": []},
                              {"width": 820, "problems": ["820px pipeline: x"]}],
                             "http://localhost:1234", "2026-11-18")
    assert "| 390 | picker | 0 |" in text and "| 820 | drawer | 1 |" in text
    assert "FAIL: 1 problems." in text and "- 820px pipeline: x" in text


def _env(tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text(f"ADMIN_USERNAME={USER}\nADMIN_PASSWORD={PASSWORD}\n", encoding="utf-8")
    return env


def test_main_writes_the_note_exits_by_verdict_and_never_prints_credentials(tmp_path, capsys):
    report = tmp_path / "note.md"
    argv = ["--report", str(report), "--out", str(tmp_path / "shots")]
    seen = []

    def clean(args, credentials):
        seen.append(credentials)
        return [{"width": width, "problems": []} for width in glc.WIDTHS]

    assert glc.main(argv, runner=clean, env_path=_env(tmp_path)) == 0
    assert seen == [(USER, PASSWORD)]
    assert "PASS: no problems." in report.read_text(encoding="utf-8")

    def broken(args, credentials):
        return [{"width": 390, "problems": ["390px /: page overflows sideways by 9px"]}]

    assert glc.main(argv, runner=broken, env_path=_env(tmp_path)) == 1
    captured = capsys.readouterr()
    assert USER not in captured.out + captured.err and PASSWORD not in captured.out + captured.err
    assert USER not in report.read_text(encoding="utf-8")


def test_missing_credentials_exit_2_and_run_nothing(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("OTHER=1\n", encoding="utf-8")
    called = []
    report = tmp_path / "note.md"
    assert glc.main(["--report", str(report)], runner=lambda a, c: called.append(1), env_path=env) == 2
    assert called == [] and not report.exists()
    assert "cannot run" in capsys.readouterr().err
