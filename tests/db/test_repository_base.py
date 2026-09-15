"""Unit-level contracts for the generic flat-dictionary repository."""
import pytest

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import trades


def test_repository_requires_an_actual_key_column():
    with pytest.raises(ValueError, match="not a table column"):
        Repository(trades, "not_a_column")


def test_repository_uses_the_schema_registry_for_promoted_fields():
    repository = Repository(trades, "trade_id")
    values = repository._values({
        "trade_id": "T1", "ticker": "AAPL", "strategy": "RSI", "confidence": 4,
    })
    assert values == {
        "trade_id": "T1", "ticker": "AAPL", "strategy": "RSI", "doc": {"confidence": 4},
    }
    assert repository._record(type("Row", (), {"_mapping": {
        "trade_id": "T1", "ticker": "AAPL", "strategy": "RSI", "doc": {"confidence": 4},
    }})()) == {"trade_id": "T1", "ticker": "AAPL", "strategy": "RSI", "confidence": 4}
