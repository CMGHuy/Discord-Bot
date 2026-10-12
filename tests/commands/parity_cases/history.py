"""Reply-parity cases for swingbot/commands/history.py (v153 SP8).

The trade-log query and the backtest generator are stubbed; every case
passes explicit dates so the header text never depends on today's date.
"""
from types import SimpleNamespace

from swingbot.commands import history as history_mod
from tests.commands.reply_harness import ParityCase

_WINDOW = {"date_from": "2026-07-01", "date_to": "2026-09-30"}


def _logged(i: int, status: str) -> dict:
    return {
        "id": f"T{i:04d}", "ticker": "TSLA", "direction": "bullish" if i % 2 else "bearish",
        "status": status, "entry_price": 250.0 + i, "stop_loss": 240.0, "take_profit": 280.0,
        "confidence_level": 3, "strategy": "Break & Retest", "horizon_key": "4w",
        "opened_at": f"2026-08-{10 + i:02d}T14:30:00",
    }


def _setup(i: int, outcome: str):
    trade = SimpleNamespace(
        direction="bullish", outcome=outcome, r_multiple=1.8 if outcome == "win" else -1.0,
        entry_date=f"2026-07-{1 + i:02d}", exit_date=None if outcome == "timeout" else f"2026-07-{2 + i:02d}",
        holding_days=3, entry=100.0 + i, stop_loss=95.0, take_profit=110.0,
    )
    return ("Break & Retest", "4w", trade, "$")


def _stub_recorded(monkeypatch):
    rows = [_logged(1, "win"), _logged(2, "loss"), _logged(3, "open")]
    monkeypatch.setattr(history_mod, "_query_trade_log", lambda *a, **k: list(rows))


def _stub_generated(n: int):
    setups = [_setup(i, ("win", "loss", "timeout")[i % 3]) for i in range(n)]

    def stub(monkeypatch):
        monkeypatch.setattr(history_mod, "_query_trade_log", lambda *a, **k: [])
        monkeypatch.setattr(history_mod, "_sync_generate_plans", lambda *a, **k: (list(setups), 500))
    return stub


def _stub_generate_fails(monkeypatch):
    monkeypatch.setattr(history_mod, "_query_trade_log", lambda *a, **k: [])

    def boom(*_a, **_k):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(history_mod, "_sync_generate_plans", boom)


CASES = [
    ParityCase("plans_recorded", history_mod.handle_plans, args=("tsla",), kwargs=dict(_WINDOW),
               stub=_stub_recorded, expect="edit"),
    ParityCase("plans_generated_batched", history_mod.handle_plans, args=("tsla", "4w", "Break & Retest"),
               kwargs=dict(_WINDOW), stub=_stub_generated(16), expect="edit"),
    ParityCase("plans_generated_none", history_mod.handle_plans, args=("tsla",), kwargs=dict(_WINDOW),
               stub=_stub_generated(0), expect="edit"),
    ParityCase("plans_generate_fails", history_mod.handle_plans, args=("tsla",), kwargs=dict(_WINDOW),
               stub=_stub_generate_fails, expect="error"),
    ParityCase("plans_no_ticker", history_mod.handle_plans, args=(None,), expect="error"),
    ParityCase("plans_date_in_ticker_slot", history_mod.handle_plans, args=("from:2026-01-01",),
               expect="error"),
]
