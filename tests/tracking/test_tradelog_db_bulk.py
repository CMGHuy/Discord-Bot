"""TradeLog bulk mutators and delete paths at the db stage.

At stage `db`, `_all()` returns fresh copies from the database, but
`self._trades` is a stale snapshot loaded from trades.json at construction.
Every write must therefore come from the mutated copies (by trade id) and
every delete must hit the database rows -- never the stale in-memory list.
A fake in-memory repository keeps these tests independent of Postgres.
"""
import json
from unittest.mock import patch

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.tracking.performance import TradeLog, _db_record


class FakeTradesRepo:
    """In-memory stand-in for TradeRepository (rows in the table shape)."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.upserts: list[str] = []

    def seed(self, trade: dict) -> None:
        self.rows[trade["id"]] = _db_record(dict(trade))

    def list_all(self, **_kw):
        return [dict(r) for r in self.rows.values()]

    def upsert(self, record, conn=None):
        self.upserts.append(record["trade_id"])
        self.rows[record["trade_id"]] = dict(record)
        return dict(record)

    def delete(self, key, conn=None):
        return self.rows.pop(key, None) is not None

    def clear(self, *, status=None, conn=None):
        doomed = [k for k, r in self.rows.items()
                  if status is None
                  or (status == "open") == (r["status"] == "open")]
        for key in doomed:
            del self.rows[key]
        return len(doomed)


def _trade(tid, status="open", **over):
    t = {"id": tid, "ticker": "AAPL", "direction": "bullish", "status": status,
         "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
         "strategy": "RSI", "horizon_key": "2w", "confidence_label": "High",
         "confidence_level": 4, "opened_at": "2026-07-01T10:00:00+00:00"}
    t.update(over)
    return t


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "")
    repo = FakeTradesRepo()
    monkeypatch.setattr("swingbot.core.db.repositories.trades.trades_repo", lambda: repo)
    return tmp_path, repo, monkeypatch


def _log(env, stage, stale=()):
    """A TradeLog at `stage` whose in-memory list holds the (json) `stale` rows."""
    tmp, repo, monkeypatch = env
    (tmp / "trades.json").write_text(json.dumps(list(stale)), encoding="utf-8")
    log = TradeLog(path=str(tmp / "trades.json"))
    if stage:
        monkeypatch.setattr(config, "DB_STORES", f"trades:{stage}")
    return log, repo


def _db_log(env, stale=()):
    return _log(env, "db", stale)


STALE = [_trade("OLD", status="open", ticker="ZZZ")]


def _live(repo):
    return sorted(repo.rows)


def test_update_open_trades_upserts_only_the_closed_trade(env):
    log, repo = _db_log(env, stale=STALE)
    repo.seed(_trade("T1"))
    repo.seed(_trade("T2", ticker="MSFT"))
    df = pd.DataFrame({"Open": [100.0], "High": [101.0], "Low": [99.0]},
                      index=pd.to_datetime(["2026-07-02"]))
    closed = log.update_open_trades("AAPL", df, live_price=90.0)
    assert [t["id"] for t in closed] == ["T1"]
    assert repo.rows["T1"]["status"] == "loss"
    assert repo.rows["T2"]["status"] == "open"
    assert _live(repo) == ["T1", "T2"]          # stale OLD never resurrected
    assert repo.upserts == ["T1"]


def test_close_if_live_price_hit_upserts_only_the_closed_trade(env):
    log, repo = _db_log(env, stale=STALE)
    repo.seed(_trade("T1"))
    repo.seed(_trade("T2", ticker="MSFT"))
    closed = log.close_if_live_price_hit("AAPL", 90.0)
    assert [t["id"] for t in closed] == ["T1"]
    assert repo.rows["T1"]["status"] == "loss"
    assert repo.rows["T1"]["close_reason"] == "auto (price monitor)"
    assert _live(repo) == ["T1", "T2"]
    assert repo.upserts == ["T1"]


def test_check_near_tp_timeout_close_is_persisted(env):
    log, repo = _db_log(env, stale=STALE)
    repo.seed(_trade("T1", near_tp_since="2026-07-01T10:00:00+00:00",
                     near_tp_snapshots=[]))
    repo.seed(_trade("T2", ticker="MSFT"))
    with patch("swingbot.core.marketdata.data.get_daily_data", return_value=None):
        closed = log.check_near_tp_timeout("AAPL", live_price=109.5)
    assert [t["id"] for t in closed] == ["T1"]
    assert repo.rows["T1"]["status"] == "win"
    assert _live(repo) == ["T1", "T2"]
    assert repo.upserts == ["T1"]


def test_check_near_tp_timeout_start_clock_is_persisted(env):
    log, repo = _db_log(env)
    repo.seed(_trade("T1"))
    with patch("swingbot.core.marketdata.data.get_daily_data", return_value=None):
        assert log.check_near_tp_timeout("AAPL", live_price=109.5) == []
    assert repo.rows["T1"]["near_tp_since"] is not None
    assert repo.rows["T1"]["status"] == "open"


def test_bare_persist_does_not_resurrect_stale_rows(env):
    log, repo = _db_log(env, stale=STALE)
    log._persist()
    assert repo.rows == {} and repo.upserts == []


def test_delete_trade_removes_db_only_row(env):
    log, repo = _db_log(env, stale=STALE)
    repo.seed(_trade("T1"))
    assert log.delete_trade("T1") is True
    assert repo.rows == {}
    assert log.delete_trade("T1") is False


def test_delete_trade_does_not_resurrect_stale_rows(env):
    log, repo = _db_log(env, stale=STALE)
    repo.seed(_trade("T1"))
    repo.seed(_trade("T2"))
    log.delete_trade("T1")
    assert _live(repo) == ["T2"] and repo.upserts == []


def test_clear_history_deletes_closed_db_rows_only(env):
    log, repo = _db_log(env, stale=STALE)
    repo.seed(_trade("O1"))
    repo.seed(_trade("C1", status="win"))
    repo.seed(_trade("C2", status="loss"))
    assert log.clear_history() == 2
    assert _live(repo) == ["O1"] and repo.upserts == []


def test_clear_open_deletes_open_db_rows_only(env):
    log, repo = _db_log(env, stale=STALE)
    repo.seed(_trade("O1"))
    repo.seed(_trade("O2"))
    repo.seed(_trade("C1", status="win"))
    assert log.clear_open() == 2
    assert _live(repo) == ["C1"] and repo.upserts == []


def test_clear_all_deletes_every_db_row(env):
    log, repo = _db_log(env, stale=STALE)
    repo.seed(_trade("O1"))
    repo.seed(_trade("C1", status="win"))
    assert log.clear_all() == 2
    assert repo.rows == {} and repo.upserts == []


def test_clear_on_empty_db_returns_zero(env):
    log, repo = _db_log(env, stale=STALE)
    assert log.clear_history() == 0
    assert log.clear_open() == 0
    assert log.clear_all() == 0


def test_discard_plan_placeholder_deletes_the_db_row(env):
    log, repo = _db_log(env)
    repo.seed(_trade("T1", plan_id="p1"))
    repo.seed(_trade("T2", plan_id="p2"))
    assert log.discard_plan_placeholder("p1") is True
    assert _live(repo) == ["T2"]


# -- regression: json and dual stages behave as before ----------------------

def test_json_stage_bulk_close_writes_file_and_never_touches_db(env):
    tmp, _, _ = env
    log, repo = _log(env, "", stale=[_trade("T1")])
    assert len(log.close_if_live_price_hit("AAPL", 90.0)) == 1
    assert json.loads((tmp / "trades.json").read_text())[0]["status"] == "loss"
    assert repo.rows == {} and repo.upserts == []
    assert log.delete_trade("T1") is True
    assert json.loads((tmp / "trades.json").read_text()) == []


def test_dual_stage_bulk_close_writes_file_and_mirrors_to_db(env):
    tmp, _, _ = env
    log, repo = _log(env, "dual", stale=[_trade("T1"), _trade("T2", ticker="MSFT")])
    assert len(log.close_if_live_price_hit("AAPL", 90.0)) == 1
    on_disk = {t["id"]: t["status"]
               for t in json.loads((tmp / "trades.json").read_text())}
    assert on_disk == {"T1": "loss", "T2": "open"}
    assert repo.rows["T1"]["status"] == "loss"
    assert log.delete_trade("T2") is True
    assert "T2" not in repo.rows
    assert [t["id"] for t in json.loads((tmp / "trades.json").read_text())] == ["T1"]
    assert log.clear_all() == 1 and repo.rows == {}
