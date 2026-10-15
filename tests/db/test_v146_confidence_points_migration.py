"""v146_001: backfill confidence_points / confidence_unevaluated from the
breakdown text, once. The parser is loaded from the revision file itself --
it exists nowhere else, so no reader can ever parse the text again."""
from __future__ import annotations

import importlib.util
import logging
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.scanning import factors
from swingbot.core.scanning.confidence import score_confidence
from tests.scanning.test_confidence_points import _scenario, scenario_matrix

REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION_FILE = (REPO / "swingbot" / "core" / "db" / "migrations" / "versions"
                 / "v146_001_confidence_points.py")
TS = "2026-10-01T10:00:00+00:00"


def _load_revision():
    spec = importlib.util.spec_from_file_location("v146_001_confidence_points", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIG = _load_revision()
MATRIX = scenario_matrix()
BY_LABEL = dict(MATRIX)


# --- the parser against both scorers ----------------------------------

@pytest.mark.parametrize("label,result", MATRIX, ids=[label for label, _ in MATRIX])
def test_parser_reproduces_the_legacy_scorer(label, result):
    points, unevaluated, unparsed = MIG.parse_breakdown(result.breakdown)
    assert points == result.points
    assert unevaluated == result.unevaluated
    assert unparsed == []


def test_parser_reproduces_the_unified_scorer(monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    result = score_confidence(
        _scenario(), regime_trend="bullish", df=None, gap_fragile=True,
        macro_verdict={"status": "opposed", "reason": "disagrees", "trend": "bearish"})
    points, unevaluated, unparsed = MIG.parse_breakdown(result.breakdown)
    assert (points, unevaluated, unparsed) == (result.points, result.unevaluated, [])
    assert "Confirming methods" not in points


@pytest.mark.parametrize("scenario_kw", [
    {"tight_stop": True, "atr_floor_pct": 4.0, "stop_distance_pct": 1.0},
    {"tight_stop": True, "atr_floor_pct": 2.0, "stop_distance_pct": 1.98},   # rounds to 0
])
def test_parser_reads_the_unified_tight_stop_line(scenario_kw):
    result = factors.factor_tight_stop(factors.FactorContext(scenario=_scenario(**scenario_kw)))
    points, _, unparsed = MIG.parse_breakdown({result.name: result.line})
    assert points == {result.name: result.points}
    assert unparsed == []


def test_non_factor_keys_are_skipped_not_unparsed():
    breakdown = {
        "Strategies confirmed (base level)": "3 strategies agree on the target -> base Level 3",
        "Quality score": "73/100 (quality score 73/100 -> no adjustment)",
        "Track record (expectancy)": "50% assumed win rate, 3.0:1 reward:risk -> expectancy +1.00R",
        "Level adjustment": "base Level 3 +1 -> final Level 4 (High)",
        "Confirming methods": "3 independent method(s) -> base Level 5",
    }
    assert MIG.parse_breakdown(breakdown) == ({}, [], [])


def test_an_unparseable_line_is_reported_not_fatal():
    points, unevaluated, unparsed = MIG.parse_breakdown({
        "ADX trend strength": "ADX 31.0 (strong trend) (+15)",
        "Mystery factor": "no integer at the end",
        "Odd value": None,
    })
    assert points == {"ADX trend strength": 15}
    assert unevaluated == []
    assert unparsed == ["Mystery factor", "Odd value"]


# --- the backfill on a real trades table ------------------------------

@pytest.fixture
def trades_conn(db_conn):
    db_conn.execute(sa.text("DELETE FROM trades"))   # rolled back with the fixture
    return db_conn


def _trade(conn, trade_id, **doc):
    TradeRepository().insert({"trade_id": trade_id, "ticker": "AAPL",
                              "strategy": "S/R Confluence", "horizon": "2w",
                              "direction": "bullish", "status": "win",
                              "opened_at": TS, **doc}, conn=conn)


def _row(conn, trade_id):
    return TradeRepository().get(trade_id, conn=conn)


def test_backfill_writes_both_fields_from_the_breakdown(trades_conn):
    result = BY_LABEL["regime unavailable"]
    _trade(trades_conn, "T1", confidence_breakdown=result.breakdown)
    stamped, _counts = MIG.backfill(trades_conn)
    row = _row(trades_conn, "T1")
    assert stamped == 1
    assert row["confidence_points"] == result.points
    assert sorted(row["confidence_unevaluated"]) == sorted(result.unevaluated)


def test_backfill_leaves_rows_without_a_breakdown_or_already_stamped(trades_conn):
    _trade(trades_conn, "T-null", confidence_breakdown=None)
    _trade(trades_conn, "T-strategy")
    _trade(trades_conn, "T-new", confidence_breakdown={"ADX trend strength": "ADX 30 (+15)"},
           confidence_points={"sentinel": 1}, confidence_unevaluated=[])
    stamped, _counts = MIG.backfill(trades_conn)
    assert stamped == 0
    assert "confidence_points" not in _row(trades_conn, "T-null")
    assert "confidence_points" not in _row(trades_conn, "T-strategy")
    assert _row(trades_conn, "T-new")["confidence_points"] == {"sentinel": 1}


def test_backfill_counts_parsed_skipped_and_unparsed_per_key(trades_conn):
    _trade(trades_conn, "T1", confidence_breakdown={
        "Quality score": "73/100 (quality score 73/100 -> no adjustment)",
        "ADX trend strength": "ADX 30 (strong trend) (+15)",
        "Mystery factor": "no integer here",
    })
    _stamped, counts = MIG.backfill(trades_conn)
    assert counts["ADX trend strength"]["parsed"] == 1
    assert counts["Quality score"]["skipped"] == 1
    assert counts["Mystery factor"]["unparsed"] == 1
    assert _row(trades_conn, "T1")["confidence_points"] == {"ADX trend strength": 15}


def test_upgrade_logs_counts_and_downgrade_drops_both_fields(trades_conn, caplog):
    _trade(trades_conn, "T1", confidence_breakdown=BY_LABEL["tight stop"].breakdown)
    with Operations.context(MigrationContext.configure(trades_conn)):
        with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
            MIG.upgrade()
        assert _row(trades_conn, "T1")["confidence_points"]["Tight stop penalty"] == -11
        MIG.downgrade()
    row = _row(trades_conn, "T1")
    assert "confidence_points" not in row
    assert "confidence_unevaluated" not in row
    assert "v146_001 Tight stop penalty: parsed=1 skipped=0 unparsed=0" in caplog.text
    assert "v146_001: stamped 1 trade row(s)" in caplog.text


# --- the revision graph -----------------------------------------------

def test_revision_chains_after_v147_and_leaves_one_head():
    """v147_001 also branched off v152_001 on main; v146_001 sits on top of it."""
    script = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    assert MIG.down_revision == "v147_001"
    assert script.get_heads() == ["v146_001"]


def test_revision_sits_on_an_existing_revision_and_runs_up_and_down(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert MIG.revision == "v146_001"
    assert script.get_revision(MIG.down_revision) is not None
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        downgrade(cfg, MIG.down_revision)
        upgrade(cfg, "head")
