"""The evidence a JSON file and its table hold the same records."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.infra.jsonio import atomic_write_json
from scripts.db.parity_report import STORES, parity


def _json_row(trade_id, **overrides):
    row = {"id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
           "direction": "bullish", "status": "open", "opened_at": "2026-01-02T15:00:00+00:00",
           "closed_at": None, "entry": None, "stop_loss": None}
    row.update(overrides)
    return row


def _db_row(trade_id, **overrides):
    row = {"trade_id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon": "2w",
           "direction": "bullish", "status": "open", "opened_at": "2026-01-02T15:00:00+00:00"}
    row.update(overrides)
    return row


@pytest.fixture
def isolated(tmp_path, monkeypatch, db_engine):
    from swingbot.core.db import engine as db_engine_module
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    db_engine_module.reset_engine()
    TradeRepository().clear()
    yield tmp_path
    db_engine_module.reset_engine()


def test_registered_stores_name_a_file_key_and_repository():
    for name, spec in STORES.items():
        assert spec.filename and spec.key and callable(spec.repo_factory), name


def test_matching_backends_report_ok(isolated):
    rows = [_json_row("T1"), _json_row("T2")]
    atomic_write_json(os.path.join(isolated, "trades.json"), rows)
    for trade_id in ("T1", "T2"):
        TradeRepository().upsert(_db_row(trade_id))
    assert parity("trades").ok


def test_parity_names_missing_extra_and_mismatched_rows(isolated):
    atomic_write_json(os.path.join(isolated, "trades.json"), [_json_row("T1", entry=100.0)])
    TradeRepository().upsert(_db_row("T1", entry=101.0))
    TradeRepository().upsert(_db_row("T9"))
    report = parity("trades")
    assert report.extra == ["T9"] and report.mismatched == ["T1"]


def test_unknown_store_raises_instead_of_reporting_clean(isolated):
    with pytest.raises(KeyError):
        parity("not-a-store")


def test_midnight_utc_created_at_renders_back_to_a_date():
    """plans.json stores date-only strings; the promoted timestamptz widens them."""
    import datetime as dt

    from scripts.db.parity_report import _plans_from_repo_shape
    row = {"plan_id": "p1",
           "created_at": dt.datetime(2026, 8, 11, tzinfo=dt.timezone.utc)}
    assert _plans_from_repo_shape(row)["created_at"] == "2026-08-11"


def test_a_created_at_with_a_real_time_is_left_alone():
    """Only midnight collapses -- a genuine timestamp must not lose its time."""
    import datetime as dt

    from scripts.db.parity_report import _plans_from_repo_shape
    row = {"plan_id": "p1",
           "created_at": dt.datetime(2026, 8, 11, 12, 3, 7, tzinfo=dt.timezone.utc)}
    assert _plans_from_repo_shape(row)["created_at"].startswith("2026-08-11T12:03:07")


def test_a_null_created_at_survives():
    from scripts.db.parity_report import _plans_from_repo_shape
    assert _plans_from_repo_shape({"plan_id": "p1", "created_at": None})["created_at"] is None


def test_a_plan_without_created_at_survives():
    from scripts.db.parity_report import _plans_from_repo_shape
    assert "created_at" not in _plans_from_repo_shape({"plan_id": "p1"})
