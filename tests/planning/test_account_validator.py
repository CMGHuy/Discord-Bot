"""v187 D2: one validator for every account setter (index § Contracts)."""
import re

import pytest

from swingbot.core.edge.sizing import RISK_CEILING_PCT
from swingbot.core.planning import account as acct

NAN, INF = float("nan"), float("inf")
BAD_FLOATS = [NAN, INF, -INF, -1.0]

# key: (accepted values, refused values)
TABLE = {
    "risk_pct": ([0.01, 1.0, RISK_CEILING_PCT], BAD_FLOATS + [0, 0.0, RISK_CEILING_PCT + 0.01, 100]),
    "position_pct": ([0.001, 100, 100.0], BAD_FLOATS + [0, 100.01]),
    "max_position_pct": ([0.1, 100.0], BAD_FLOATS + [0, 100.01]),
    "max_position_value_absolute": ([0, 0.0, 1000.0, 1e9], BAD_FLOATS),
    "max_risk_amount_absolute": ([0, 100.0], BAD_FLOATS),
    "base_balance": ([0.01, 10_000, 1e8], BAD_FLOATS + [0]),
    "max_open_positions": ([1, 30, 3.0], BAD_FLOATS + [0, 2.5]),
}
CASES_OK = [(k, v) for k, (ok, _bad) in TABLE.items() for v in ok]
CASES_BAD = [(k, v) for k, (_ok, bad) in TABLE.items() for v in bad]
MESSAGES = {
    "risk_pct": "Risk per trade must be above 0% and at most 2.0% (got {v}).",
    "position_pct": "Position size must be above 0% and at most 100% of the account (got {v}).",
    "max_position_pct": "Max position size must be above 0% and at most 100% of the account (got {v}).",
    "max_position_value_absolute": "Max position value must be 0 (off) or more (got {v}).",
    "max_risk_amount_absolute": "Max risk per trade must be 0 (off) or more (got {v}).",
    "base_balance": "Balance must be above 0 (got {v}).",
    "max_open_positions": "Max open positions must be a whole number of 1 or more (got {v}).",
}


@pytest.mark.parametrize("key,value", CASES_OK, ids=[f"{k}={v}" for k, v in CASES_OK])
def test_accepts(key, value):
    got = acct._validated(key, value)
    assert got == value
    assert type(got) is (int if key == "max_open_positions" else float)


@pytest.mark.parametrize("key,value", CASES_BAD, ids=[f"{k}={v}" for k, v in CASES_BAD])
def test_refuses_with_the_setting_and_its_range(key, value):
    with pytest.raises(ValueError) as err:
        acct._validated(key, value)
    assert str(err.value) == MESSAGES[key].format(v=value)


def test_risk_message_is_rendered_from_the_ceiling_constant(monkeypatch):
    monkeypatch.setattr(acct, "RISK_CEILING_PCT", 1.5)
    with pytest.raises(ValueError, match=r"at most 1\.5% \(got 1\.6\)"):
        acct._validated("risk_pct", 1.6)
    assert acct._validated("risk_pct", 1.5) == 1.5


@pytest.mark.parametrize("key", sorted(TABLE))
def test_bool_and_text_are_refused_for_every_key(key):
    for value in (True, False, "1", None):
        with pytest.raises(ValueError):
            acct._validated(key, value)


def test_max_open_positions_stores_an_integral_float_as_int():
    assert acct._validated("max_open_positions", 3.0) == 3
    assert isinstance(acct._validated("max_open_positions", 3.0), int)


def test_an_int_too_large_for_a_float_is_refused():
    with pytest.raises(ValueError):
        acct._validated("max_open_positions", 10 ** 400)


def test_unknown_key_is_a_programming_error():
    with pytest.raises(KeyError):
        acct._validated("sizing_mode", "risk")


# ── setters: validate first, save nothing on refusal ────────────────────

SETTERS = [
    (acct.set_balance, "base_balance", 5000.0, -1.0),
    (acct.set_risk_pct, "risk_pct", 1.5, 10.0),
    (acct.set_max_open_positions, "max_open_positions", 7, 2.5),
    (acct.set_max_position_pct, "max_position_pct", 20.0, 0.0),
    (acct.set_max_position_value_absolute, "max_position_value_absolute", 0.0, NAN),
    (acct.set_max_risk_amount_absolute, "max_risk_amount_absolute", 150.0, -5.0),
    (acct.set_position_pct, "position_pct", 12.5, 100.5),
]


@pytest.fixture
def store(monkeypatch):
    saved = []
    monkeypatch.setattr(acct, "load_account_config",
                        lambda: {"base_balance": 10_000.0, "balance": 10_000.0, "balance_history": []})
    monkeypatch.setattr(acct, "save_account_config", lambda cfg: saved.append(dict(cfg)))
    monkeypatch.setattr(acct, "_sum_realized_pnl", lambda: 0.0)
    return saved


@pytest.mark.parametrize("setter,key,good,bad", SETTERS, ids=[s[1] for s in SETTERS])
def test_setter_refuses_an_invalid_value_and_saves_nothing(store, setter, key, good, bad):
    with pytest.raises(ValueError, match=re.escape(MESSAGES[key].split(" (got")[0])):
        setter(bad)
    assert store == []


@pytest.mark.parametrize("setter,key,good,bad", SETTERS, ids=[s[1] for s in SETTERS])
def test_setter_stores_the_validated_value(store, setter, key, good, bad):
    cfg = setter(good)
    assert cfg[key] == good and store[-1][key] == good


def test_max_open_positions_setter_stores_an_int(store):
    assert acct.set_max_open_positions(3.0)["max_open_positions"] == 3
    assert type(store[-1]["max_open_positions"]) is int

@pytest.mark.parametrize("setter,key,good,bad", SETTERS, ids=[s[1] for s in SETTERS])
def test_setter_refuses_before_loading_config(monkeypatch, setter, key, good, bad):
    def unexpected_load():
        pytest.fail("invalid settings must be rejected before loading config")

    monkeypatch.setattr(acct, "load_account_config", unexpected_load)
    with pytest.raises(ValueError):
        setter(bad)
