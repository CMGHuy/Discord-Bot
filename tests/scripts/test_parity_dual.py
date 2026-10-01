"""parity_report --dual: compare only stores that are at dual right now."""
from swingbot import config
from scripts.db import parity_report as pr


def test_every_parity_store_belongs_to_exactly_one_stage():
    covered = [store for stores in pr.STAGE_STORES.values() for store in stores]
    assert sorted(covered) == sorted(pr.STORES)


def test_dual_stores_follows_db_stores(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:dual,state:db,tuning:dual")
    assert pr.dual_stores() == ["tuning", "tuning_proposals", "watchlist"]


def test_dual_is_a_no_op_when_nothing_is_dual(monkeypatch, capsys):
    monkeypatch.setattr(config, "DB_STORES", "")
    assert pr.main(["--dual"]) == 0
    assert "no-op" in capsys.readouterr().out


def test_dual_runs_parity_for_each_dual_store(monkeypatch):
    class Clean:
        ok = True

        def render(self):
            return "clean"

    seen = []
    monkeypatch.setattr(config, "DB_STORES", "watchlist:dual")
    monkeypatch.setattr(pr, "parity", lambda name, source_path=None: seen.append(name) or Clean())
    assert pr.main(["--dual"]) == 0
    assert seen == ["watchlist"]
