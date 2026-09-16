"""The manual-release-only kill switch."""
from __future__ import annotations

import datetime as dt

from swingbot import config
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import killswitch


KEY = "global"


class KillswitchRepository(Repository):
    def __init__(self):
        super().__init__(killswitch, key="key")

    def state(self, *, conn=None) -> dict:
        row = self.get(KEY, conn=conn)
        if row is None:
            return {"on": config.KILLSWITCH_DEFAULT_ON, "reason": None,
                    "at": None, "manual_release": False}
        engaged_at = row.get("engaged_at")
        if hasattr(engaged_at, "isoformat"):
            engaged_at = engaged_at.isoformat()
        return {
            "on": bool(row.get("engaged")),
            "reason": row.get("reason"),
            "at": engaged_at,
            "manual_release": bool(row.get("manual_release")),
        }

    def engage(self, reason: str, *, conn=None) -> dict:
        """Keep the original reason and honour a deliberate manual release."""
        current = self.state(conn=conn)
        if current.get("on") or (reason != "manual" and current.get("manual_release")):
            return current
        self.upsert({"key": KEY, "engaged": True, "reason": reason,
                     "engaged_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "manual_release": False}, conn=conn)
        return self.state(conn=conn)

    def release(self, *, conn=None) -> dict:
        self.upsert({"key": KEY, "engaged": False, "engaged_at":
                     dt.datetime.now(dt.timezone.utc).isoformat(),
                     "reason": None, "manual_release": True}, conn=conn)
        return self.state(conn=conn)


_repo: KillswitchRepository | None = None


def killswitch_repo() -> KillswitchRepository:
    global _repo
    if _repo is None:
        _repo = KillswitchRepository()
    return _repo
