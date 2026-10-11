"""Reply-parity cases for swingbot/commands/account.py (v153 SP5).

Every handler runs once through CtxReply and once through InteractionReply
with the account store stubbed; SP1's test_reply_parity compares the two
event streams. Stubs return a fixed config so no account file is touched.
"""
from swingbot.commands import account as account_mod
from tests.commands.reply_harness import ParityCase

_CFG = {
    "balance": 10_500.0,
    "base_balance": 10_000.0,
    "risk_pct": 1.0,
    "position_pct": 10.0,
    "max_position_pct": 10.0,
    "max_position_value_absolute": 1000,
    "max_risk_amount_absolute": 100,
    "max_open_positions": 5,
    "sizing_mode": "risk_pct",
}


def _stub(name: str, **overrides):
    """Patch account_mod.<name> to return the fixed config plus overrides."""
    cfg = {**_CFG, **overrides}

    def stub(monkeypatch):
        monkeypatch.setattr(account_mod, name, lambda *_a, **_k: dict(cfg))
    return stub


def _stub_bad_sizing(monkeypatch):
    def boom(mode):
        raise ValueError(f"Unknown sizing mode '{mode}'. Use risk or account.")
    monkeypatch.setattr(account_mod, "set_sizing_mode", boom)


CASES = [
    ParityCase("account_show_risk_pct", account_mod.handle_account_show,
               stub=_stub("load_account_config")),
    ParityCase("account_show_account_pct", account_mod.handle_account_show,
               stub=_stub("load_account_config", sizing_mode="account_pct")),
    ParityCase("account_show_kelly", account_mod.handle_account_show,
               stub=_stub("load_account_config", sizing_mode="kelly")),
    ParityCase("account_balance", account_mod.handle_account_balance,
               args=(10_000.0,), stub=_stub("set_balance")),
    ParityCase("account_risk", account_mod.handle_account_risk,
               args=(1.5,), stub=_stub("set_risk_pct", risk_pct=1.5)),
    ParityCase("account_maxpositions", account_mod.handle_account_maxpositions,
               args=(7,), stub=_stub("set_max_open_positions", max_open_positions=7)),
    ParityCase("account_sizing_account", account_mod.handle_account_sizing,
               args=("account",), stub=_stub("set_sizing_mode", sizing_mode="account_pct")),
    ParityCase("account_sizing_vol_target", account_mod.handle_account_sizing,
               args=("vol_target",), stub=_stub("set_sizing_mode", sizing_mode="vol_target")),
    ParityCase("account_sizing_risk", account_mod.handle_account_sizing,
               args=("risk",), stub=_stub("set_sizing_mode")),
    ParityCase("account_sizing_invalid", account_mod.handle_account_sizing,
               args=("bogus",), stub=_stub_bad_sizing, expect="error"),
    ParityCase("account_positionpct", account_mod.handle_account_positionpct,
               args=(12.5,), stub=_stub("set_position_pct", position_pct=12.5)),
    ParityCase("account_maxpositionpct", account_mod.handle_account_maxpositionpct,
               args=(20.0,), stub=_stub("set_max_position_pct", max_position_pct=20.0)),
    ParityCase("account_maxposition", account_mod.handle_account_maxposition,
               args=(2500.0,), stub=_stub("set_max_position_value_absolute",
                                          max_position_value_absolute=2500.0)),
    ParityCase("account_maxrisk", account_mod.handle_account_maxrisk,
               args=(150.0,), stub=_stub("set_max_risk_amount_absolute",
                                         max_risk_amount_absolute=150.0)),
]
