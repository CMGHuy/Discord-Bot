"""DB_STORES parsing must fail closed to the existing JSON behaviour."""
from unittest.mock import patch

import pytest

from swingbot import config
from swingbot.core.db import stages


def test_empty_config_means_every_store_is_json(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    assert stages.stage_for("trades") == stages.JSON


def test_a_store_not_listed_defaults_to_json(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    assert stages.stage_for("plans") == stages.JSON


@pytest.mark.parametrize("raw,expected", [
    ("trades:db", "db"),
    ("plans:dual,trades:db", "db"),
    ("  trades : db , plans:dual ", "db"),
    ("TRADES:DB", "db"),
])
def test_parsing_is_whitespace_and_case_tolerant(monkeypatch, raw, expected):
    monkeypatch.setattr(config, "DB_STORES", raw)
    assert stages.stage_for("trades") == expected


@pytest.mark.parametrize("raw", [
    "trades:postgres", "trades", "trades:db:extra", ":db", "trades:",
])
def test_malformed_entries_fail_closed_and_are_logged(monkeypatch, raw):
    monkeypatch.setattr(config, "DB_STORES", raw)
    # Assert the diagnostic at its source. Handler capture is intentionally
    # outside this unit's contract: the bot/admin configure process logging.
    with patch.object(stages.log, "error") as error:
        assert stages.stage_for("trades") == stages.JSON
    error.assert_called_once()
    assert "DB_STORES" in error.call_args.args[0]


def test_one_bad_entry_does_not_discard_good_ones(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "trades:nonsense,plans:db")
    assert stages.stage_for("trades") == stages.JSON
    assert stages.stage_for("plans") == stages.DB


@pytest.mark.parametrize("stage,json_write,db_write,db_read", [
    ("json", True, False, False),
    ("dual", True, True, False),
    ("db", False, True, True),
])
def test_stage_predicates(monkeypatch, stage, json_write, db_write, db_read):
    monkeypatch.setattr(config, "DB_STORES", f"trades:{stage}")
    assert stages.writes_json("trades") is json_write
    assert stages.writes_db("trades") is db_write
    assert stages.reads_db("trades") is db_read


def test_a_later_duplicate_wins(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "trades:db,trades:json")
    assert stages.stage_for("trades") == stages.JSON
