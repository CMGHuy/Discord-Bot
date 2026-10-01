"""Market-data refresh bookkeeping, one row per `SYMBOL|timeframe` (v116).

The whole map is saved at once, exactly like the JSON file it replaces, so a
pair the refresh no longer tracks disappears from the table too."""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import market_data_state


class MarketDataStateRepository(Repository):
    def __init__(self):
        super().__init__(market_data_state, key="key")

    def load(self, *, conn=None) -> dict[str, dict]:
        state: dict[str, dict] = {}
        for row in self.list_all(conn=conn):
            key = row.pop("key")
            state[key] = row
        return state

    def save(self, state: dict[str, dict], *, conn=None) -> None:
        with transaction(conn) as connection:
            connection.execute(sa.delete(market_data_state)
                               .where(market_data_state.c.key.notin_(list(state))))
            for key, record in state.items():
                self.upsert({**record, "key": key}, conn=connection)


_repo: MarketDataStateRepository | None = None


def market_data_state_repo() -> MarketDataStateRepository:
    global _repo
    if _repo is None:
        _repo = MarketDataStateRepository()
    return _repo
