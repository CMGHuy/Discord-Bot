"""The one-off journal repair: which rows it picks and what it keeps.

Before 2026-08-20 the legacy price monitor could journal a plan-linked
trade at its stop (-1.00R) before the plan manager wrote the real fill
over the trade, so the journal kept the first number."""
import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "rejournal_fill_mismatch.py"

_spec = importlib.util.spec_from_file_location("rejournal_fill_mismatch", SCRIPT)
rj = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rj)


def _trade(tid="t1", exit_price=393.4765):
    return {"id": tid, "ticker": "GD", "direction": "bearish", "status": "loss",
            "entry": 379.97, "stop_loss": 387.7317, "exit_price": exit_price,
            "legs": [{"fraction": 1.0, "exit_price": exit_price,
                      "r": (379.97 - exit_price) / (387.7317 - 379.97), "reason": "loss"}],
            "opened_at": "2026-07-30T16:23:03+00:00",
            "closed_at": "2026-07-31T10:14:51.218+00:00"}


def test_a_journal_at_minus_one_against_a_worse_fill_is_a_mismatch():
    found = rj.find_mismatches([_trade()], {"t1": {"trade_id": "t1", "r_realized": -1.0}})
    assert [t["id"] for t, _ in found] == ["t1"]


def test_a_journal_within_the_tolerance_is_left_alone():
    t = _trade()
    fill_r = t["legs"][0]["r"]
    assert rj.find_mismatches([t], {"t1": {"trade_id": "t1", "r_realized": fill_r + 0.04}}) == []


def test_a_trade_without_a_journal_row_or_r_is_skipped():
    no_r = dict(_trade("t2"), entry=None)
    assert rj.find_mismatches([_trade(), no_r], {}) == []


def test_open_trades_are_never_picked():
    t = dict(_trade(), status="open")
    assert rj.find_mismatches([t], {"t1": {"trade_id": "t1", "r_realized": -1.0}}) == []


def test_the_rebuilt_entry_keeps_the_partners_note():
    old = {"trade_id": "t1", "r_realized": -1.0, "note": "chased the gap"}
    new = rj.merge_entry({"trade_id": "t1", "r_realized": -1.74, "note": ""}, old)
    assert new["note"] == "chased the gap"
    assert new["r_realized"] == -1.74


def test_only_exit_derived_fields_are_replaced():
    """v86: the journal freezes what the plan was told at issuance
    (confidence, risk_features, entry_context); the repair never rewrites it."""
    old = {"trade_id": "t1", "r_realized": -1.0, "confidence_level": 4,
           "risk_features": {"a": 1}, "entry_context": {"b": 2}, "outcome": "loss"}
    rebuilt = {"trade_id": "t1", "r_realized": -1.74, "confidence_level": 5,
               "risk_features": {"a": 9}, "entry_context": {}, "outcome": "loss",
               "mfe_r": 0.2, "closed_at": "later"}
    new = rj.merge_entry(rebuilt, old)
    assert new["confidence_level"] == 4
    assert new["risk_features"] == {"a": 1}
    assert new["entry_context"] == {"b": 2}
    assert (new["r_realized"], new["mfe_r"], new["closed_at"]) == (-1.74, 0.2, "later")


def test_changed_fields_lists_only_real_changes():
    old = {"r_realized": -1.0, "outcome": "loss", "note": "x", "created_at": "a"}
    new = {"r_realized": -1.74, "outcome": "loss", "note": "x", "created_at": "b"}
    assert rj.changed_fields(old, new) == ["r_realized"]
