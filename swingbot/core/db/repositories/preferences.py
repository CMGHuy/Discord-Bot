"""Per-user UI state: column-picker visibility, and whatever follows.

Still deliberately NOT a config.Field -- see the reasoning in
admin/api_v1/system.py's get_preferences docstring, which the move to Postgres
does not change. What it does change is that a row does not need the whole .env
rewritten to toggle one column.
"""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import ui_preferences

DEFAULT_OWNER = "admin"


class PreferencesRepository(Repository):
    def __init__(self):
        super().__init__(ui_preferences, key="owner")

    def load(self, owner: str = DEFAULT_OWNER, *, conn=None) -> dict:
        row = self.get(owner, conn=conn)
        if row is None:
            return {}
        return {k: v for k, v in row.items() if k != "owner"}

    def save(self, prefs: dict, owner: str = DEFAULT_OWNER, *, conn=None) -> None:
        self.upsert({"owner": owner, **prefs}, conn=conn)


_repo: PreferencesRepository | None = None


def preferences_repo() -> PreferencesRepository:
    global _repo
    if _repo is None:
        _repo = PreferencesRepository()
    return _repo
