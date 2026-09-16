"""Account configuration and balance history."""

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import account, account_balance_history

CONFIG_KEY = "config"


class AccountRepository(Repository):
    def __init__(self):
        super().__init__(account, key="key")
        self._history = Repository(account_balance_history, key="ts")

    def load(self, *, conn=None) -> dict:
        row = self.get(CONFIG_KEY, conn=conn)
        if row is None:
            return {}
        result = {key: value for key, value in row.items() if key != "key"}
        result.pop("balance_history", None)
        return result

    def save(self, cfg: dict, *, conn=None) -> None:
        payload = {key: value for key, value in cfg.items() if key != "balance_history"}
        for entry in cfg.get("balance_history") or []:
            self.append_history(entry, conn=conn)
        self.upsert({"key": CONFIG_KEY, **payload}, conn=conn)

    def append_history(self, entry: dict, *, conn=None) -> dict:
        return self._history.upsert(dict(entry), conn=conn)

    def history(self, *, limit: int | None = None, conn=None) -> list[dict]:
        if limit is None:
            return self._history.list_all(conn=conn, order_by=account_balance_history.c.ts.asc())
        latest = self._history.list_all(conn=conn, order_by=account_balance_history.c.ts.desc(), limit=limit)
        return list(reversed(latest))


_repo: AccountRepository | None = None


def account_repo() -> AccountRepository:
    global _repo
    if _repo is None:
        _repo = AccountRepository()
    return _repo
