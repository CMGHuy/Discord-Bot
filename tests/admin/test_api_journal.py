"""SR55 — the journal, on the wire for the first time.

`JournalStore`, `weekly_digest()` and `top_lessons()` have existed and been
rendered by `pages.py:journal_page` all along; what was missing was an API in
front of them, which is why the parity audit found seven rows with nothing on
the wire at all.

The load-bearing assertion is `test_unjournaled_trade_is_a_state_not_an_error`.
Journal entries are written at close, so an OPEN position having no entry is
the normal case, not a failure — and a client that has to catch an exception
to discover the normal case will eventually render it as one.
"""
import json

import pytest

from tests.admin.api_v1_contract import NULLABLE_NUMBER, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}


def _entry(trade_id, *, outcome="loss", tags=(), note="", lesson=None,
           mfe_r=1.4, mae_r=0.2, exit_efficiency=0.31, closed_at="2026-08-12T15:00:00+00:00"):
    """One journal.json record, as `build_entry` writes it."""
    return {
        "trade_id": trade_id, "ticker": "AAPL", "strategy": "RSI Divergence",
        "horizon_key": "1m", "direction": "bullish", "tier": "A",
        "badge": "VALIDATED", "quality_score": 72, "outcome": outcome,
        "r_realized": -1.0, "mfe_r": mfe_r, "mae_r": mae_r,
        "exit_efficiency": exit_efficiency, "holding_days": 3.2,
        "tags": list(tags), "auto_lesson": lesson, "note": note,
        "opened_at": "2026-08-09T10:00:00+00:00", "closed_at": closed_at,
        "created_at": "2026-08-12T15:00:01+00:00",
    }


def _trade(trade_id, *, status="win"):
    return {
        "id": trade_id, "plan_id": None, "ticker": "AAPL",
        "strategy": "RSI Divergence", "horizon_key": "1m",
        "direction": "bullish", "confidence_level": 4,
        "confidence_label": "High", "confidence_score": 81.0,
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "target2": None,
        "risk_reward_ratio": 1.8, "tier": "A", "badge": "VALIDATED",
        "quality_score": 72, "source": "strategy", "legs": [],
        "opened_at": "2026-08-09T10:00:00+00:00", "status": status,
        "closed_at": "2026-08-12T15:00:00+00:00" if status != "open" else None,
        "exit_price": 108.0 if status != "open" else None,
        "realized_pnl_amount": 70.0 if status != "open" else None,
        "shares": 10, "position_value": 1000.0, "target_sources": [],
        "stop_sources": [], "target2_sources": [], "confirmed_by": [],
        "explanation": None, "confidence_breakdown": None,
    }


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=(), entries=()):
        (tmp_path / "plans.json").write_text("[]", encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
        (tmp_path / "journal.json").write_text(json.dumps(list(entries)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


_ENTRY_SHAPE = {
    "trade_id": str, "ticker": str, "strategy": str, "horizon_key": str,
    "direction": str, "tier": (str, type(None)), "badge": (str, type(None)),
    "quality_score": NULLABLE_NUMBER, "outcome": str,
    "r_realized": NULLABLE_NUMBER, "mfe_r": NULLABLE_NUMBER,
    "mae_r": NULLABLE_NUMBER, "exit_efficiency": NULLABLE_NUMBER,
    "holding_days": NULLABLE_NUMBER, "tags": list,
    "auto_lesson": (str, type(None)), "note": str,
    "opened_at": (str, type(None)), "closed_at": (str, type(None)),
    # Stamped by `JournalStore.add` on every write, so it means "when this
    # record was last written", not "when the trade closed". Declared rather
    # than stripped: a re-journal after a correction is a real thing to be
    # able to see, and `closed_at` already carries the trade's own date.
    "created_at": (str, type(None)),
}


# ------------------------------------------------- one trade's journal entry

def test_journal_entry_carries_the_excursion_figures(seed, logged_in):
    """MFE, MAE and exit efficiency — the three the gap table calls out, and
    the reason the Notes tab could show a note but never why it was written."""
    seed(trades=[_trade("a" * 16)],
         entries=[_entry("a" * 16, mfe_r=1.4, mae_r=0.2, exit_efficiency=0.31)])

    body = logged_in.get("/api/v1/trades/" + "a" * 16 + "/journal").get_json()

    assert body["journaled"] is True
    assert_shape(body["entry"], _ENTRY_SHAPE, where="entry")
    assert body["entry"]["mfe_r"] == 1.4
    assert body["entry"]["mae_r"] == 0.2
    assert body["entry"]["exit_efficiency"] == 0.31


def test_journal_entry_carries_tags_and_the_auto_lesson(seed, logged_in):
    seed(trades=[_trade("b" * 16)],
         entries=[_entry("b" * 16, tags=["gave-it-back", "a-tier"],
                         lesson="Trade went 1.4R in favor before stopping out.")])

    entry = logged_in.get("/api/v1/trades/" + "b" * 16 + "/journal").get_json()["entry"]

    assert entry["tags"] == ["gave-it-back", "a-tier"]
    assert "1.4R" in entry["auto_lesson"]


def test_unjournaled_trade_is_a_state_not_an_error(seed, logged_in):
    """An OPEN trade has no entry, and that is the normal case.

    200 with `journaled: false`, deliberately NOT the 404 that
    `PUT /trades/:id/note` returns. The PUT's 404 is right because the write
    genuinely did nothing; a GET asking "is there an entry" has a perfectly
    good answer, and making the client catch an error to hear it is how
    "not journaled yet" ends up rendered as a failure.
    """
    seed(trades=[_trade("c" * 16, status="open")], entries=[])

    response = logged_in.get("/api/v1/trades/" + "c" * 16 + "/journal")

    assert response.status_code == 200
    body = response.get_json()
    assert body["journaled"] is False
    assert body["entry"] is None


def test_unknown_trade_id_is_still_a_clean_state(seed, logged_in):
    seed(trades=[], entries=[])
    body = logged_in.get("/api/v1/trades/" + "d" * 16 + "/journal").get_json()
    assert body == {"journaled": False, "entry": None}


def test_journal_entry_requires_auth(client, seed):
    seed(trades=[_trade("e" * 16)], entries=[_entry("e" * 16)])
    assert client.get("/api/v1/trades/" + "e" * 16 + "/journal").status_code == 401


# ------------------------------------------------------ digest and lessons

def test_analytics_journal_returns_the_digest_and_top_lessons(seed, logged_in):
    seed(trades=[_trade("f" * 16), _trade("g" * 16, status="loss")],
         entries=[
             _entry("f" * 16, outcome="win", note="Held to target."),
             _entry("g" * 16, outcome="loss", note="Chased the entry."),
         ])

    body = logged_in.get("/api/v1/analytics/journal").get_json()

    assert_shape(body, {"digest": list, "lessons": list, "entries_n": int})
    assert body["entries_n"] == 2
    assert all(isinstance(line, str) for line in body["digest"])
    assert all(isinstance(line, str) for line in body["lessons"])


def test_analytics_journal_is_empty_but_shaped_on_a_fresh_install(seed, logged_in):
    """No journal file yet must not 500 — the same self-healing posture the
    snapshot route has."""
    seed(trades=[], entries=[])
    body = logged_in.get("/api/v1/analytics/journal").get_json()
    assert_shape(body, {"digest": list, "lessons": list, "entries_n": int})
    assert body["entries_n"] == 0


def test_analytics_journal_requires_auth(client, seed):
    seed()
    assert client.get("/api/v1/analytics/journal").status_code == 401


def test_lessons_limit_is_a_positive_integer(seed, logged_in):
    seed(trades=[], entries=[_entry("h" * 16, note="one")])
    assert logged_in.get("/api/v1/analytics/journal?lessons=0").status_code == 400
    assert logged_in.get("/api/v1/analytics/journal?lessons=abc").status_code == 400
