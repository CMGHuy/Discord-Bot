"""v158 WC11: the date-literal guard (v136 rule 2, "Scripts never define
dates") and the --instrument census over scripts/backtest/.

A live script holds no date or year literal: its windows come from the
instrument contract. Closed, historical scripts that must keep reproducing
their committed results sit on ALLOW: they stay v1-only and take no flag
(partner decision 3). Utilities that never run a backtest sit on NO_REPLAY and
take no flag. Every other script must take --instrument."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKTEST = ROOT / "scripts" / "backtest"

#: A string constant that IS a date or a year: "2020-01-01", "2020-01", "2021".
DATE_TEXT = re.compile(r"^(19|20)\d{2}(-\d{2}){0,2}$")
#: An int constant that reads as a year, e.g. range(2013, 2026). Slice bounds
#: such as stderr[-2000:] stay below it.
YEARS = range(2005, 2036)

#: Closed, historical scripts (rel path -> why it keeps its own windows).
ALLOW = {
    "scripts/backtest/funnel.py": "v102-v104 funnel; its FOLD_YEARS reproduce those committed results",
    "scripts/backtest/fvg_attribution.py": "v128 FVG attribution; closed pre-registration",
    "scripts/backtest/fvg_select.py": "v128 Stage 0/1 FVG judge; closed pre-registration",
    "scripts/backtest/make_v68_fixture.py": "regenerates v68's committed VALIDATION fixture",
    "scripts/backtest/measure_acceptance_exits.py": "v129 acceptance-exit funnel; closed pre-registration",
    "scripts/backtest/measure_adjacent_gate_effect.py": "v33 adjacent-horizon gate measurement; closed",
    "scripts/backtest/measure_alert_density.py": "v51 alert-density measurement; closed, TRAIN-only by its plan",
    "scripts/backtest/measure_armed_entries.py": "v88 armed-entry grid; closed pre-registration",
    "scripts/backtest/measure_bearish_arms.py": "bearish-arm TRAIN measurement; closed",
    "scripts/backtest/measure_confluence_stop.py": "v139 one-shot pre-registered measurement; windows frozen in its record",
    "scripts/backtest/measure_dcb_veto.py": "v68 dead-cat-bounce veto grid; closed TRAIN and VALIDATION shots",
    "scripts/backtest/measure_earnings_blackout.py": "v82 earnings-blackout table; closed pre-registration",
    "scripts/backtest/measure_factor_lift.py": "v32 per-factor lift; closed TRAIN measurement",
    "scripts/backtest/measure_fib_anchor_diagnostic.py": "v124 anchor diagnostic; reproduces v103 on frozen windows",
    "scripts/backtest/measure_fib_confluence.py": "v102 Fibonacci x S/R confluence on the extended cache; closed",
    "scripts/backtest/measure_fib_diagnostic.py": "v101 Fibonacci diagnostic; closed",
    "scripts/backtest/measure_fib_extension.py": "v84 Fibonacci 1.0 extension arms; closed",
    "scripts/backtest/measure_fib_limit.py": "v131 Fibonacci limit; its holdout shot is spent, windows frozen",
    "scripts/backtest/measure_fib_v103.py": "v103/v108 measurement funnel; closed",
    "scripts/backtest/measure_fvg_bullish_diagnostic.py": "v143 FVG bullish diagnostic; its one TRAIN replay is closed",
    "scripts/backtest/measure_rs_gate_effect.py": "v34 relative-strength gate measurement; closed",
    "scripts/backtest/measure_structure_arm.py": "v127 structure-break armed entry; closed pre-registration",
    "scripts/backtest/measure_trend_signal_overlap.py": "v33 trend-signal overlap; closed TRAIN measurement",
    "scripts/backtest/measure_v104.py": "v104 measurement; its holdout end is frozen",
    "scripts/backtest/measure_v113.py": "v113 measurement; its holdout end is frozen",
    "scripts/backtest/run_confluence_validation.py": "plan Task 41 one-shot confluence VALIDATION run; spent",
    "scripts/backtest/screen_idea.py": "v140 Stage -2 screen; its window is part of the pre-registration",
    "scripts/backtest/screen_trail_calibration.py": "v163 A/A calibration on synthetic frames; its 2010 start is a frame label, not a replay window",
}

#: Utilities that run no backtest and choose no window.
NO_REPLAY = {
    "scripts/backtest/cache_dir_source.py": "v162 shared --cache-dir helper; no CLI, runs no backtest",
    "scripts/backtest/compare_backtest_json.py": "diffs two run_backtest_range --json outputs; runs no backtest",
    "scripts/backtest/harvest_select.py": "v123 harvest selection over stamped arm files; runs no backtest",
    "scripts/backtest/validate_component.py": "v100 acceptance funnel over stamped arm files; runs no backtest",
}

#: The live scripts this plan wired (WC8, WC9, WC10).
WIRED = {f"scripts/backtest/{name}.py" for name in (
    "run_backtest_range", "tune_strategy", "tune_exit_v2", "tune_confluence_gates",
    "measure_arms", "wf_run", "wf_components", "permutation_test", "quarterly_revalidation",
    "emit_cohort_registry", "ablation", "measure_strategy_arm")}


def _docstrings(tree) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def _is_date(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in YEARS
    return isinstance(value, str) and DATE_TEXT.match(value) is not None


def date_literals(text: str) -> list[tuple[int, object]]:
    """(line, value) of every date or year constant outside docstrings. Comments
    never reach the AST; a date inside a longer string (a results-doc path,
    help prose) is not a window and is not flagged."""
    tree = ast.parse(text)
    skip = _docstrings(tree)
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and id(node) not in skip and _is_date(node.value)]


def takes_instrument_flag(text: str) -> bool:
    """True when the script calls add_instrument_arg (bare or as an attribute)."""
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "add_instrument_arg":
                return True
    return False


def _scripts() -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(BACKTEST.glob("*.py"))}


def test_the_scanner_flags_iso_dates_year_ranges_and_year_strings():
    source = (
        'TRAIN = ("2020-01-01", "2023-12-31")\n'
        "FOLD_YEARS = tuple(range(2013, 2026))\n"
        'LABELS = ("2021", "2022")\n'
        'MONTH = "2024-06"\n'
    )
    assert {value for _, value in date_literals(source)} == {
        "2020-01-01", "2023-12-31", 2013, 2026, "2021", "2022", "2024-06"}


def test_the_scanner_ignores_docstrings_comments_prose_and_other_numbers():
    source = (
        '"""Window 2020-01-01..2023-12-31; see 2024-01-01."""\n'
        '# TRAIN = ("2020-01-01", "2023-12-31")\n'
        'OUT = "docs/superpowers/results/2026-07-26-edge-folds.md"\n'
        "HELP = \"e.g. '2024-01-01:2025-12-31'\"\n"
        "TAIL = text[-2000:]\n"
        "BARS, PCT, FLAG, OLD = 260, 0.5, True, 1999\n"
        "\n"
        "def f():\n"
        '    """Docstring 2021-01-01."""\n'
        "    return 4096\n"
    )
    assert date_literals(source) == []


def test_no_live_script_holds_a_date_literal():
    offenders = {rel: hits for rel, text in _scripts().items()
                 if rel not in ALLOW and (hits := date_literals(text))}
    assert offenders == {}, ("a live script defines a date: read it from the instrument "
                             "contract (v136 rule 2), or allow-list a closed script with a reason")


def test_every_live_script_takes_the_instrument_flag():
    missing = [rel for rel, text in _scripts().items()
               if rel not in ALLOW and rel not in NO_REPLAY and not takes_instrument_flag(text)]
    assert missing == [], "call instrument.cli.add_instrument_arg (v136 rule 2)"


def test_closed_and_non_replay_scripts_stay_v1_only():
    flagged = [rel for rel, text in _scripts().items()
               if (rel in ALLOW or rel in NO_REPLAY) and takes_instrument_flag(text)]
    assert flagged == []


def test_each_listed_script_exists_with_a_one_line_reason():
    scripts = _scripts()
    for listing in (ALLOW, NO_REPLAY):
        for rel, reason in listing.items():
            assert rel in scripts, f"stale entry: {rel}"
            assert reason.strip() and "\n" not in reason, rel
    assert not set(ALLOW) & set(NO_REPLAY)


def test_no_wired_script_is_listed_away():
    live = {rel for rel in _scripts() if rel not in ALLOW and rel not in NO_REPLAY}
    assert WIRED <= live
