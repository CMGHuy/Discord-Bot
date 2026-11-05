"""v205: revision v205_001 -- fx_daily_rates, one FX rate per major-code pair per
Berlin day, and the repository that writes it insert-if-absent."""
import pathlib
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema
from swingbot.core.db.repositories import market_refresh as mr

REPO = pathlib.Path(__file__).resolve().parents[2]
PROMOTED = ("base", "account", "day", "rate", "bar_date", "snapped_at", "source")
T0 = datetime(2026, 11, 4, 7, 0, tzinfo=timezone.utc)


def _row(day, rate, *, base="USD", account="EUR", bar=None, source="snap", at=T0):
    return {"base": base, "account": account, "day": day, "rate": rate,
            "bar_date": bar or day - timedelta(days=1), "snapped_at": at,
            "source": source}


def test_registered_with_reasons_contract_and_no_sse():
    table = schema.METADATA.tables["fx_daily_rates"]
    assert schema.promoted_for("fx_daily_rates") == PROMOTED
    assert set(schema.PROMOTION_REASONS["fx_daily_rates"]) == set(PROMOTED)
    assert schema.contract_violations(table) == []
    assert [c.name for c in table.primary_key.columns] == ["base", "account", "day"]
    assert all(table.c[name].nullable is False for name in PROMOTED)
    assert list(table.indexes) == []
    assert "fx_daily_rates" not in events.TABLE_CHANNELS


def test_column_types():
    t = schema.fx_daily_rates
    assert isinstance(t.c.day.type, sa.Date) and isinstance(t.c.bar_date.type, sa.Date)
    assert isinstance(t.c.rate.type, sa.Float)
    assert t.c.snapped_at.type.timezone is True
    assert isinstance(t.c.base.type, sa.Text) and isinstance(t.c.source.type, sa.Text)


def test_v205_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v205_001")
    assert scripts.get_revision(revision.down_revision) is not None
    heads = scripts.get_heads()
    assert len(heads) == 1      # later revisions may stack on v205_001; never branch
    assert "v205_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_downgrade_drops_it_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert "fx_daily_rates" in sa.inspect(connection).get_table_names()
        downgrade(cfg, ScriptDirectory.from_config(cfg).get_revision("v205_001").down_revision)
        remaining = set(sa.inspect(connection).get_table_names())
        assert "fx_daily_rates" not in remaining and "quote_currencies" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert "fx_daily_rates" in sa.inspect(connection).get_table_names()


# --- the repository ----------------------------------------------------------

def test_insert_if_absent_keeps_the_first_value_of_a_day(db_conn):
    repo = mr.FxDailyRateRepository()
    day = date(2026, 11, 4)
    assert repo.insert_if_absent([_row(day, 0.86)], conn=db_conn) == 1
    assert repo.insert_if_absent([_row(day, 0.99, source="backfill"),
                                  _row(date(2026, 11, 5), 0.87)], conn=db_conn) == 1
    rates = repo.all_rates(conn=db_conn)
    assert [(r["day"], r["rate"]) for r in rates] == [(day, 0.86), (date(2026, 11, 5), 0.87)]
    assert set(rates[0]) == {"base", "account", "day", "rate", "bar_date"}


def test_nothing_to_insert_writes_nothing(db_conn):
    assert mr.FxDailyRateRepository().insert_if_absent([], conn=db_conn) == 0


@pytest.mark.parametrize("bad", [{"source": "live"}, {"rate": 0.0}, {"rate": -1.0}])
def test_a_bad_row_is_refused(db_conn, bad):
    with pytest.raises(ValueError):
        mr.FxDailyRateRepository().insert_if_absent([{**_row(date(2026, 11, 4), 0.86), **bad}],
                                                    conn=db_conn)


def test_all_rates_orders_by_pair_then_day_and_upper_cases_codes(db_conn):
    repo = mr.FxDailyRateRepository()
    repo.insert_if_absent([_row(date(2026, 11, 5), 0.87),
                           _row(date(2026, 11, 4), 1.15, base="gbp"),
                           _row(date(2026, 11, 4), 0.86)], conn=db_conn)
    assert [(r["base"], r["account"], r["day"]) for r in repo.all_rates(conn=db_conn)] == [
        ("GBP", "EUR", date(2026, 11, 4)), ("USD", "EUR", date(2026, 11, 4)),
        ("USD", "EUR", date(2026, 11, 5))]


def test_version_is_count_and_latest_snap(db_conn):
    repo = mr.FxDailyRateRepository()
    assert repo.version(conn=db_conn) == (0, None)
    later = datetime(2026, 11, 5, 7, 0, tzinfo=timezone.utc)
    repo.insert_if_absent([_row(date(2026, 11, 4), 0.86),
                           _row(date(2026, 11, 5), 0.87, at=later)], conn=db_conn)
    assert repo.version(conn=db_conn) == (2, later)


def test_days_present_is_per_pair(db_conn):
    repo = mr.FxDailyRateRepository()
    repo.insert_if_absent([_row(date(2026, 11, 4), 0.86),
                           _row(date(2026, 11, 3), 1.15, base="GBP")], conn=db_conn)
    assert repo.days_present("USD", "EUR", conn=db_conn) == {date(2026, 11, 4)}
    assert repo.days_present("usd", "eur", conn=db_conn) == {date(2026, 11, 4)}
    assert repo.days_present("ZAR", "EUR", conn=db_conn) == set()


def test_known_codes_are_the_distinct_known_answers(db_conn):
    codes = mr.QuoteCurrencyRepository()
    codes.put("AAPL", "USD", "known", checked_at=T0, conn=db_conn)
    codes.put("MSFT", "USD", "known", checked_at=T0, conn=db_conn)
    codes.put("VOD.L", "GBp", "known", checked_at=T0, conn=db_conn)
    codes.put("ZZZ", None, "unknown", checked_at=T0, retry_after=T0, conn=db_conn)
    assert codes.known_codes(conn=db_conn) == {"USD", "GBp"}


def test_the_accessor_is_a_singleton():
    assert mr.fx_daily_rate_repo() is mr.fx_daily_rate_repo()
    assert isinstance(mr.fx_daily_rate_repo(), mr.FxDailyRateRepository)
