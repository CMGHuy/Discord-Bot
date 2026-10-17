"""v158 WC6: the shared --instrument flag, window resolution and v2 refusals
(v136 spec cross-cutting rule 2; section 1 "v2 spans")."""
import argparse

import pytest

from swingbot.core.backtesting.instrument import cli
from swingbot.core.backtesting.instrument.contract import VERSIONS, resolve


def _parser():
    ap = argparse.ArgumentParser(prog="demo")
    cli.add_instrument_arg(ap)
    return ap


# --- the flag -----------------------------------------------------------------

def test_flag_defaults_to_v1():
    args = _parser().parse_args([])
    assert args.instrument == "v1"
    assert cli.spec_from_args(args) is resolve("v1")


def test_flag_accepts_every_contract_version():
    for version in VERSIONS:
        args = _parser().parse_args(["--instrument", version])
        assert cli.spec_from_args(args) is resolve(version)


def test_flag_refuses_an_unknown_version(capsys):
    with pytest.raises(SystemExit) as exc:
        _parser().parse_args(["--instrument", "v3"])
    assert exc.value.code == 2
    assert "invalid choice: 'v3'" in capsys.readouterr().err


# --- run_instrument: v1 passes None, exactly as today ------------------------

def test_run_instrument_is_none_under_v1():
    assert cli.run_instrument(resolve("v1")) is None


def test_run_instrument_is_the_spec_under_v2():
    assert cli.run_instrument(resolve("v2")) is resolve("v2")


# --- window_for -----------------------------------------------------------------

def test_v1_windows_are_the_contract_objects():
    v1 = resolve("v1")
    assert cli.window_for(v1, "train") is v1.train_window
    assert cli.window_for(v1, "validation") is v1.validation_window
    assert cli.window_for(v1, "train") == ("2020-01-01", "2023-12-31")
    assert cli.window_for(v1, "validation") == ("2024-01-01", "2025-12-31")


def test_v2_train_is_the_research_span():
    assert cli.window_for(resolve("v2"), "train") == ("2010-01-01", "2025-12-31")


def test_v2_validation_is_the_sealed_holdout():
    with pytest.raises(SystemExit) as exc:
        cli.window_for(resolve("v2"), "validation")
    assert cli.HOLDOUT_SEALED in str(exc.value)
    assert "2026-01-01" in str(exc.value)


def test_unknown_stage_is_a_programming_error():
    with pytest.raises(ValueError, match="unknown stage 'holdout'"):
        cli.window_for(resolve("v1"), "holdout")


# --- check_inside_research --------------------------------------------------------

def test_v1_custom_windows_are_unchecked_as_today():
    cli.check_inside_research(resolve("v1"), "2018-06-01", "2025-12-31")   # no raise


@pytest.mark.parametrize("date_from, date_to", [
    ("2010-01-01", "2025-12-31"),     # the whole span, both ends inclusive
    ("2014-01-01", "2014-12-31"),
])
def test_v2_window_inside_the_research_span_is_accepted(date_from, date_to):
    cli.check_inside_research(resolve("v2"), date_from, date_to)


@pytest.mark.parametrize("date_from, date_to", [
    ("2009-12-31", "2012-12-31"),     # starts before the research span
    ("2024-01-01", "2026-01-01"),     # reaches the sealed holdout
    ("2015-06-01", "2015-01-01"),     # reversed
])
def test_v2_window_outside_the_research_span_is_refused(date_from, date_to):
    with pytest.raises(SystemExit) as exc:
        cli.check_inside_research(resolve("v2"), date_from, date_to)
    assert "research span 2010-01-01..2025-12-31" in str(exc.value)


# --- require_v1 ---------------------------------------------------------------------

def test_require_v1_is_silent_under_v1():
    cli.require_v1(resolve("v1"), "measure_arms.py", "phase 5")


def test_require_v1_names_the_script_and_the_owning_phase_under_v2():
    with pytest.raises(SystemExit) as exc:
        cli.require_v1(resolve("v2"), "measure_arms.py", "phase 5 (v2 stage table)")
    message = str(exc.value)
    assert "measure_arms.py" in message
    assert "--instrument v2" in message
    assert "phase 5 (v2 stage table)" in message
