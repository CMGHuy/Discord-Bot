"""v115 § Strategy work: the post-09-22 strategy work (v92, v103, v104, v108,
v113) closed no-lift or ships default-off, and must STAY off -- at the code
default and in .env.example -- so a later change cannot silently switch one on.
Spec: docs/superpowers/specs/2026-09-30-v115-restore-sep22-issuance-design.md"""
from pathlib import Path

import pytest
from dotenv import dotenv_values

from swingbot import config
from swingbot.core.market import strategy_types as st
from swingbot.core.market.entry_filters import DEFAULT_PARAMS
from swingbot.core.scanning import scan_run

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"
WHY = "must stay off (v115 § Strategy work)"

FLAGS_OFF = [
    ("v92", "ADAPTIVE_RUNNER_TRAIL_ENABLED", False),
    ("v92", "DATA_DRIVEN_STOPS_ENABLED", False),
    ("v92", "STALL_EXIT_ENABLED", False),
    ("v103", "FIB_LEVEL_STOP_ATR", 0.0),
    ("v103", "FIB_LEVEL_STOP_DIRECTIONS", ""),
    ("v104", "STRUCTURAL_STOP_SCOPE", ""),
]

MASKED_STRATEGIES = [
    ("v103", "Fibonacci Continuation"),
    ("v104", "Bull Trap"),
    ("v104", "Vol Expansion Breakdown"),
    ("v104", "Earnings Gap Drift"),
    ("v113", "Downtrend Overbought Fade"),
]


def _field(key):
    return next(f for f in config.FIELDS if f.key == key)


@pytest.mark.parametrize("spec,key,off", FLAGS_OFF)
def test_flag_code_default_is_off(spec, key, off):
    value = config._cast(_field(key), _field(key).default)
    assert value == off, f"{spec}: {key} code default is {value!r}, {WHY}: {off!r}"


@pytest.mark.parametrize("spec,key,off", FLAGS_OFF)
def test_flag_in_env_example_is_off(spec, key, off):
    raw = dotenv_values(ENV_EXAMPLE).get(key)
    assert raw is not None, f"{spec}: {key} is missing from .env.example, {WHY}"
    value = config._cast(_field(key), raw)
    assert value == off, f"{spec}: .env.example ships {key}={raw!r}, {WHY}: {off!r}"


def test_the_masked_names_are_the_real_strategy_names():
    assert st.V104_SHORTS == ("Bull Trap", "Vol Expansion Breakdown", "Earnings Gap Drift"), \
        "v104: the short-strategy names changed -- update MASKED_STRATEGIES here"
    assert st.FADE_STRATEGY == "Downtrend Overbought Fade", \
        "v113: the fade strategy's name changed -- update MASKED_STRATEGIES here"


@pytest.mark.parametrize("spec,name", MASKED_STRATEGIES)
def test_masked_strategy_admits_no_direction_and_no_horizon(spec, name):
    gates = st.STRATEGY_GATES.get(name)
    assert gates is not None and gates.get("directions") == (), \
        f"{spec}: STRATEGY_GATES[{name!r}] = {gates!r}, {WHY}: directions=()"
    admitted = [(d, hk) for d in ("bullish", "bearish") for hk in st.HORIZONS
                if st.admits(name, d, hk)]
    assert admitted == [], f"{spec}: {name!r} admits {admitted}, {WHY}"


def test_v108_ema_crossover_takes_the_first_touch_only():
    p = DEFAULT_PARAMS["EMA Crossover"]
    assert (p["max_touches_bull"], p["max_touches_bear"]) == (1, 1), \
        f"v108: EMA Crossover max_touches = {p['max_touches_bull']}/{p['max_touches_bear']}, {WHY}: 1/1"


def test_v113_one_week_horizon_stays_masked():
    assert "1w" in st.MASKED_BY_DEFAULT_HORIZONS, f"v113: 1w left MASKED_BY_DEFAULT_HORIZONS, {WHY}"
    cells = {k: g["cells"] for k, g in st.STRATEGY_GATES.items() if g.get("cells")}
    assert cells == {}, f"v113: STRATEGY_GATES cells {cells} admit a masked horizon, {WHY}"
    assert "1w" not in st.live_horizons(), f"v113: 1w is a live strategy horizon, {WHY}"


def test_v113_confluence_scan_skips_one_week():
    assert "1w" not in st.LEGACY_HORIZONS, f"v113: 1w is in LEGACY_HORIZONS, {WHY}"
    assert "1w" not in scan_run.LEGACY_HORIZONS, \
        f"v113: the confluence scan (scan_run) iterates 1w, {WHY}"
