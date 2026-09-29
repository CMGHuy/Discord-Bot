"""The trades importer must hand the repository repo-shaped records."""
import json

from scripts.db.import_trades import load_source
from swingbot.core.db.codec import RESERVED_KEYS, split_doc


def _write(tmp_path, records):
    path = tmp_path / "trades.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return str(path)


def test_load_source_renames_id_to_trade_id(tmp_path):
    path = _write(tmp_path, [{"id": "abc123", "ticker": "AMD",
                              "horizon_key": "3m", "status": "open"}])
    record = load_source(path)[0]
    assert record["trade_id"] == "abc123"
    assert "id" not in record


def test_load_source_renames_horizon_key_to_horizon(tmp_path):
    path = _write(tmp_path, [{"id": "abc123", "ticker": "AMD",
                              "horizon_key": "3m", "status": "open"}])
    record = load_source(path)[0]
    assert record["horizon"] == "3m"
    assert "horizon_key" not in record


def test_loaded_records_use_no_reserved_key(tmp_path):
    """The exact failure that lost all 802 rows on the first production import."""
    path = _write(tmp_path, [{"id": "abc123", "ticker": "AMD",
                              "horizon_key": "3m", "status": "open"}])
    for record in load_source(path):
        assert not RESERVED_KEYS.intersection(record)


def test_loaded_records_survive_split_doc(tmp_path):
    """split_doc is where the ReservedKeyError was actually raised."""
    path = _write(tmp_path, [{"id": "abc123", "ticker": "AMD",
                              "horizon_key": "3m", "status": "open"}])
    columns, doc = split_doc(load_source(path)[0],
                             ["trade_id", "ticker", "horizon", "status"])
    assert columns["trade_id"] == "abc123"


def test_missing_source_file_yields_no_records(tmp_path):
    assert load_source(str(tmp_path / "absent.json")) == []
