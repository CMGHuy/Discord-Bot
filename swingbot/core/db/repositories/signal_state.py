"""Per-ticker/strategy/horizon signal debounce state."""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import signal_state


class SignalStateRepository(Repository):
    """One opaque state document per debounce key."""

    def __init__(self):
        super().__init__(signal_state, key="key")

    def entry(self, key: str, *, conn=None) -> dict:
        row = self.get(key, conn=conn)
        return {} if row is None else {name: value for name, value in row.items() if name != "key"}

    def put(self, key: str, entry: dict, *, conn=None) -> None:
        self.upsert({"key": key, **entry}, conn=conn)

    def all_entries(self, *, conn=None) -> dict[str, dict]:
        return {
            row["key"]: {name: value for name, value in row.items() if name != "key"}
            for row in self.list_all(conn=conn)
        }


_repo: SignalStateRepository | None = None


def signal_state_repo() -> SignalStateRepository:
    global _repo
    if _repo is None:
        _repo = SignalStateRepository()
    return _repo
