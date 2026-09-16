"""The four cross-container runtime flags."""
from __future__ import annotations
import datetime as dt
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import runtime_flags

FLAGS = ("scan_running", "scan_paused", "trigger_check", "stop_scan")

class FlagRepository(Repository):
    def __init__(self):
        super().__init__(runtime_flags, key="name")
    @staticmethod
    def _check(name):
        if name not in FLAGS:
            raise ValueError(f"{name!r} is not a known flag; expected one of {', '.join(FLAGS)}")
        return name
    def is_set(self, name, *, conn=None):
        return self.get(self._check(name), conn=conn) is not None
    def set(self, name, *, conn=None):
        self.upsert({"name": self._check(name), "set_at": dt.datetime.now(dt.timezone.utc).isoformat()}, conn=conn)
    def clear(self, name, *, conn=None):
        self.delete(self._check(name), conn=conn)
    def set_at(self, name, *, conn=None):
        row = self.get(self._check(name), conn=conn)
        return None if row is None else row.get("set_at")

_repo = None
def flags_repo():
    global _repo
    if _repo is None:
        _repo = FlagRepository()
    return _repo
