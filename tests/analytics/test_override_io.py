"""v173: override_io -- the one evaluation (fires only when the floors hold,
writes once, never recomputes), the stored-verdict read and the inputs."""
import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_io as oio
from swingbot.core.analytics import override_verdict as ov

BERLIN = ZoneInfo("Europe/Berlin")
FRIDAY_SLOT = datetime(2026, 12, 4, 23, 50, tzinfo=BERLIN)     # after the 16:00 ET close
FRIDAY = date(2026, 12, 4)
RECORD_KEYS = {"ledger_id", "verdict", "recorded_on", "n", "weeks", "mean_delta_r",
               "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n",
               "excluded_share", "engine_flags", "rows"}
FLAGS = {"stall_exit_enabled": True, "runner_structure_exit": "off"}


class FakeEngine:
    def __init__(self):
        self.conns = []

    @contextmanager
    def begin(self):
        conn = object()
        self.conns.append(conn)
        yield conn


class FakeRepo:
    def __init__(self, stored=None, accept=True):
        self.stored, self.accept = stored, accept
        self.inserted, self.conns = [], []

    def recorded(self, ledger_id, *, conn=None):
        assert ledger_id == of.LEDGER_ID
        self.conns.append(conn)
        return self.stored

    def insert_once(self, record, *, conn=None):
        self.conns.append(conn)
        self.inserted.append(record)
        return self.accept


def _row(i: int, *, delta_r: float, price_source: str = "quote") -> dict:
    close = date(2026, 9, 1) + timedelta(days=7 * (i % 12) + i // 12)
    return of.OverrideRow(
        plan_id=f"p{i}", ticker="AAPL", horizon="swing", direction="bullish",
        state_at_close="ACTIVE", close_date=close, bulk=False, approx=False,
        price_source=price_source, status="resolved", actual_r=0.4 + delta_r, engine_r=0.4,
        delta_r=delta_r, delta_r_gross=delta_r + 0.02, actual_usd=None, engine_usd=None,
        delta_usd=round(delta_r * 200, 2), engine_exit_reason="stop", outcome="hurt",
    ).to_dict()


def _costly_rows(n: int = 31) -> list[dict]:
    """n counted rows over 12 ISO weeks, every delta clearly negative: COST."""
    return [_row(i, delta_r=-0.2 - 0.01 * (i % 5),
                 price_source="bar_close" if i < 2 else "quote") for i in range(n)]


@pytest.fixture
def report(monkeypatch):
    """Replace build_report; record its arguments; evaluable unless told otherwise."""
    seen = {}

    def fake(plans, trades, bars_fn, asof, recorded, currency_symbol):
        seen.update(plans=plans, trades=trades, bars_fn=bars_fn, asof=asof,
                    recorded=recorded, currency_symbol=currency_symbol)
        return {"rows": seen.get("rows", _costly_rows()), "summary": {},
                "verdict": {"evaluable": seen.get("evaluable", True)},
                "engine_flags": FLAGS, "asof": asof.isoformat(),
                "currency_symbol": currency_symbol}

    monkeypatch.setattr(ov, "build_report", fake)
    return seen


def _inputs():
    return (["plan-a"], {"a": {"shares": 5}})


def test_records_once_with_the_exact_record_shape_and_recorded_on_asof(report, caplog):
    repo, engine = FakeRepo(), FakeEngine()
    with caplog.at_level(logging.WARNING, logger=oio.log.name):
        result = oio.run_daily_check(FRIDAY_SLOT, inputs_fn=_inputs, bars_fn=lambda t: None,
                                    repo=repo, engine=engine)
    assert result == oio.RESULT_RECORDED == "recorded"
    (record,) = repo.inserted
    assert set(record) == RECORD_KEYS
    assert (record["ledger_id"], record["verdict"]) == (of.LEDGER_ID, ov.COST)
    assert record["recorded_on"] == FRIDAY.isoformat()
    assert (record["n"], record["weeks"], record["bar_close_n"]) == (31, 12, 2)
    assert record["engine_flags"] == FLAGS
    assert record["rows"] == _costly_rows()
    assert report["asof"] == FRIDAY and report["recorded"] is None
    assert report["currency_symbol"] == config.CURRENCY_SYMBOL
    assert report["plans"] == ["plan-a"]
    (conn,) = engine.conns                                # one transaction ...
    assert repo.conns == [conn, conn]                     # ... for the check and the insert
    (warning,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert "--mirror-row" in warning.getMessage()
    assert ov.RESULTS_RECORD in warning.getMessage()


def test_asof_is_the_latest_completed_session_not_the_wall_date(report):
    before_close = datetime(2026, 12, 4, 21, 0, tzinfo=BERLIN)   # 15:00 ET Friday
    repo = FakeRepo()
    oio.run_daily_check(before_close, inputs_fn=_inputs, repo=repo, engine=FakeEngine())
    assert report["asof"] == date(2026, 12, 3)
    assert repo.inserted[0]["recorded_on"] == "2026-12-03"


def test_waiting_when_the_floors_do_not_hold_and_nothing_is_inserted(report, caplog):
    report["evaluable"] = False
    report["rows"] = _costly_rows(29)
    repo = FakeRepo()
    with caplog.at_level(logging.WARNING, logger=oio.log.name):
        result = oio.run_daily_check(FRIDAY_SLOT, inputs_fn=_inputs, repo=repo, engine=FakeEngine())
    assert result == oio.RESULT_WAITING == "waiting"
    assert repo.inserted == []
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_waiting_on_an_empty_book_with_the_real_report(monkeypatch):
    repo = FakeRepo()
    result = oio.run_daily_check(FRIDAY_SLOT, inputs_fn=lambda: ([], {}),
                                bars_fn=lambda t: pytest.fail("no plan, no bars read"),
                                repo=repo, engine=FakeEngine())
    assert result == "waiting" and repo.inserted == []


def test_a_recorded_verdict_returns_before_any_input_is_read(monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("a recorded verdict is never recomputed")

    monkeypatch.setattr(ov, "build_report", never)
    monkeypatch.setattr(ov, "evaluate_verdict", never)
    repo = FakeRepo(stored={"ledger_id": of.LEDGER_ID, "verdict": "SAVED"})
    result = oio.run_daily_check(FRIDAY_SLOT, inputs_fn=never, bars_fn=never,
                                repo=repo, engine=FakeEngine())
    assert result == oio.RESULT_ALREADY == "already recorded"
    assert repo.inserted == []


def test_losing_the_insert_race_reports_already_recorded_without_the_warning(report, caplog):
    repo = FakeRepo(accept=False)            # a concurrent check inserted first
    with caplog.at_level(logging.WARNING, logger=oio.log.name):
        result = oio.run_daily_check(FRIDAY_SLOT, inputs_fn=_inputs, repo=repo, engine=FakeEngine())
    assert result == "already recorded"
    assert len(repo.inserted) == 1
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_a_failing_evaluation_writes_nothing_and_raises(report, monkeypatch):
    def boom(rows):
        raise RuntimeError("bootstrap failed")

    monkeypatch.setattr(ov, "evaluate_verdict", boom)
    repo = FakeRepo()
    with pytest.raises(RuntimeError):
        oio.run_daily_check(FRIDAY_SLOT, inputs_fn=_inputs, repo=repo, engine=FakeEngine())
    assert repo.inserted == []


def test_only_counted_rows_are_stored(report):
    bulk = {**_row(40, delta_r=1.5), "bulk": True}
    report["rows"] = _costly_rows() + [bulk]
    repo = FakeRepo()
    oio.run_daily_check(FRIDAY_SLOT, inputs_fn=_inputs, repo=repo, engine=FakeEngine())
    assert bulk not in repo.inserted[0]["rows"]
    assert len(repo.inserted[0]["rows"]) == 31


def test_stored_verdict_reads_the_ledger_id(monkeypatch):
    stored = {"ledger_id": of.LEDGER_ID, "verdict": "INCONCLUSIVE", "recorded_on": "2026-12-04"}
    assert oio.stored_verdict(FakeRepo(stored=stored)) == stored
    assert oio.stored_verdict(FakeRepo()) is None
    monkeypatch.setattr(oio, "verdict_repo", lambda: FakeRepo(stored=stored))
    assert oio.stored_verdict() == stored


def test_load_inputs_keys_trades_by_plan_id(monkeypatch):
    from swingbot.core.planning import plan_store
    from swingbot.core.tracking import performance

    class FakeStore:
        def all(self):
            return ["plan-a", "plan-b"]

    class FakeLog:
        def get_trades(self, status=None, limit=None, ledger=None):
            assert (status, limit, ledger) == (None, None, None)   # every trade, every ledger
            return [{"id": "t1", "plan_id": "a", "shares": 5},
                    {"id": "t2", "plan_id": None},
                    {"id": "t3", "plan_id": "a", "shares": 9}]

    monkeypatch.setattr(plan_store, "PlanStore", FakeStore)
    monkeypatch.setattr(performance, "TradeLog", FakeLog)
    plans, trades = oio.load_inputs()
    assert plans == ["plan-a", "plan-b"]
    assert trades == {"a": {"id": "t1", "plan_id": "a", "shares": 5}}
