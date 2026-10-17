"""v158 WC7 (rule 1, partner decision 4): every v1 script window equals today's
literal AND is the contract's own tuple, so it can never drift from the contract.

The literals below are the only copies allowed outside contract.py: they are
the pin."""
import importlib
import sys
from pathlib import Path

import pytest

from swingbot.core.backtesting.instrument.contract import resolve

ROOT = Path(__file__).resolve().parents[3]
for _sub in ("scripts/backtest", "scripts/data"):
    if str(ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / _sub))

V1_TRAIN = ("2020-01-01", "2023-12-31")
V1_VALIDATION = ("2024-01-01", "2025-12-31")


def test_the_contract_holds_todays_v1_windows():
    v1 = resolve("v1")
    assert v1.train_window == V1_TRAIN
    assert v1.validation_window == V1_VALIDATION


@pytest.mark.parametrize("module", [
    "run_backtest_range", "tune_strategy", "tune_exit_v2", "tune_confluence_gates"])
def test_script_train_window_is_the_contract_alias(module):
    mod = importlib.import_module(module)
    assert mod.TRAIN == V1_TRAIN
    assert mod.TRAIN is resolve("v1").train_window


def test_run_backtest_range_validation_is_the_contract_alias():
    import run_backtest_range as rbr
    assert rbr.VALIDATION == V1_VALIDATION
    assert rbr.VALIDATION is resolve("v1").validation_window


def test_admin_job_windows_and_the_train_only_gate_are_unchanged():
    from swingbot.admin import jobs
    assert jobs.TRAIN_WINDOW == V1_TRAIN
    assert jobs.VALIDATION_WINDOW == V1_VALIDATION
    assert jobs.TRAIN_WINDOW is resolve("v1").train_window
    assert jobs.VALIDATION_WINDOW is resolve("v1").validation_window
    assert jobs._VALIDATION_START_TUPLE == (2024, 1, 1)


def test_arms_validation_start_and_stage_are_v1_validation():
    from swingbot.core.backtesting.arms import windows
    assert windows.VALIDATION_START == V1_VALIDATION[0]
    assert windows.STAGES["validation"].signal_window == V1_VALIDATION
    assert windows.STAGES["validation"].signal_window is resolve("v1").validation_window
