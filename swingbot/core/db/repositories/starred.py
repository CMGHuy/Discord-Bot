"""Starred plan ids, represented as a set."""
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import starred_plans


class StarredRepository(Repository):
    def __init__(self):
        super().__init__(starred_plans, key="plan_id")

    def ids(self, *, conn=None) -> set[str]:
        return {row["plan_id"] for row in self.list_all(conn=conn)}

    def star(self, plan_id: str, *, conn=None) -> None:
        self.upsert({"plan_id": plan_id}, conn=conn)

    def unstar(self, plan_id: str, *, conn=None) -> None:
        self.delete(plan_id, conn=conn)


_repo: StarredRepository | None = None


def starred_repo() -> StarredRepository:
    global _repo
    if _repo is None:
        _repo = StarredRepository()
    return _repo
