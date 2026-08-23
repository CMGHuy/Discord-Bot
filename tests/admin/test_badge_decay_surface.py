"""Decay is visible at every badge surface -- and gates nothing.

The four consumers the v52 plan named (plan_engine, admin queries, insights,
snapshots) plus two it did not: `scanning/embeds.badge_field_for` and
`commands/views.py`'s /breakdown embed both render a badge too.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from unittest.mock import patch

from swingbot.core.analytics import calibration
from swingbot.core.analytics.insights import edge_decay_report
from swingbot.core.backtesting import registry
from swingbot.core.planning.plan_engine import badge_stats_line, stamp_badge

from tests.planning.test_plan_engine_model import _plan


def _reg(run_date: str) -> list[dict]:
    return [{"source": "strategy", "strategy": "Fibonacci", "horizon": None,
             "status": "VALIDATED", "n": 203, "win_rate": 82.3, "expectancy_r": 0.105,
             "window": "2024-01-01..2025-12-31", "run_date": run_date}]


def _stamped(run_date: str):
    with patch("swingbot.core.backtesting.registry.load_registry",
               return_value=_reg(run_date)):
        p = _plan(strategy="Fibonacci")
        stamp_badge(p)
    return p


# --- the constraint: decay must not change what gets traded ------------------

def test_stale_and_fresh_badges_produce_identical_plans():
    fresh = dataclasses.asdict(_stamped(dt.date.today().isoformat()))
    stale = dataclasses.asdict(_stamped("2019-01-01"))
    # run_date is the one fact that legitimately differs; nothing derived from
    # it may. Strip it and the two plans must be byte-identical.
    fresh["badge_stats"].pop("run_date")
    stale["badge_stats"].pop("run_date")
    assert fresh == stale


def test_decay_verdict_is_never_persisted_into_a_plan():
    # badge_stats is written to plans.json. A stored verdict is wrong the day
    # after it is written -- only the raw run_date may be carried through.
    p = _stamped("2019-01-01")
    assert "decay" not in p.badge_stats
    assert p.badge_stats["run_date"] == "2019-01-01"


# --- the surfaces ------------------------------------------------------------

def test_decay_note_is_shared_vocabulary_and_silent_when_fresh():
    assert registry.decay_note("fresh") == ""
    assert "aging" in registry.decay_note("aging")
    assert "stale" in registry.decay_note("stale")


def test_unknown_reads_as_undated_not_as_a_warning():
    note = registry.decay_note("unknown")
    assert note and "stale" not in note and "aging" not in note
    assert "undated" in note        # an unstamped legacy row is not a stale one


def test_badge_stats_line_carries_the_qualifier():
    stale = badge_stats_line(registry.Badge(
        status="VALIDATED", n=203, win_rate=82.3, expectancy_r=0.105,
        window="2024-01-01..2025-12-31", run_date="2019-01-01",
        decay="stale"))
    assert "stale" in stale
    fresh = badge_stats_line(registry.Badge(
        status="VALIDATED", n=203, win_rate=82.3, expectancy_r=0.105,
        window="2024-01-01..2025-12-31",
        run_date=dt.date.today().isoformat(), decay="fresh"))
    assert "stale" not in fresh and "aging" not in fresh


def test_admin_registry_rows_carry_evidence_decay():
    # Named `evidence_decay`, not `decay`: the row already has a `decayed` key
    # meaning the pre-registered live-vs-OOS win-rate drift alert, which is a
    # different fact entirely.
    from swingbot.admin import queries
    with patch("swingbot.admin.queries.load_registry", return_value=_reg("2019-01-01")), \
         patch("swingbot.admin.queries.load_snapshot", return_value={}), \
         patch("swingbot.admin.queries.refresh_snapshot", return_value={}):
        rows = queries._registry_rows()
    assert rows and rows[0]["evidence_decay"] == "stale"
    assert rows[0]["decayed"] is False   # unrelated key, untouched


def test_badge_drift_rows_carry_the_run_date_not_the_verdict():
    rows = calibration.badge_drift([], _reg("2019-01-01"))
    assert rows[0]["oos_run_date"] == "2019-01-01"
    assert "oos_decay" not in rows[0]    # derived at render time, never stored


def _live_t(status):
    return {"target_sources": ["Fib 61.8%"], "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0}


def test_digest_drift_line_qualifies_stale_evidence():
    live = [_live_t("win") for _ in range(14)] + [_live_t("loss") for _ in range(11)]
    with patch("swingbot.core.backtesting.registry.load_registry",
               return_value=_reg("2019-01-01")):
        lines = edge_decay_report(live)
    assert len(lines) == 1 and "stale" in lines[0]


def test_embed_badge_field_qualifies_from_the_plans_own_run_date():
    from swingbot.core.scanning.embeds import badge_field_for
    p = _stamped("2019-01-01")
    p.badge = "VALIDATED"
    name, value = badge_field_for(p)
    assert "stale" in value
