"""v142: the runner_path backfill -- dry run writes nothing, --apply is idempotent."""
from scripts.data import backfill_runner_path as brp
from swingbot.core.analytics import runner_path as rp
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore
from tests.analytics.test_runner_path import LONG_BARS, _closed
from tests.planning.test_plan_engine_model import _plan


def _seed():
    store = PlanStore()
    covered = _closed("tp1_runner_tp2", 120.0)                       # p1, AAPL: bars cover it
    uncovered = _closed("tp1_runner_tp2", 120.0)
    uncovered.plan_id, uncovered.ticker = "p2", "MSFT"               # no cache file
    stamped = _closed("tp1_runner_tp2", 120.0)
    stamped.plan_id, stamped.runner_path = "p3", {"source": "live"}  # already stamped
    active = _plan(plan_id="p4", status=PlanStatus.ACTIVE)           # never a candidate
    for plan in (covered, uncovered, stamped, active):
        store.add(plan)
    return store


def _bars(ticker):
    return LONG_BARS if ticker == "AAPL" else None


def test_dry_run_counts_and_writes_nothing(capsys):
    store = _seed()
    assert brp.main([], bars_fn=_bars) == {"stamped": 1, "skipped": 1, "unavailable": 1}
    assert store.get("p1").runner_path is None
    assert "DRY RUN: stamped=1 skipped=1 unavailable=1" in capsys.readouterr().out


def test_apply_twice_stamps_once():
    store = _seed()
    assert brp.main(["--apply"], bars_fn=_bars)["stamped"] == 1
    path = store.get("p1").runner_path
    assert (path["source"], path["mfe_r"]) == ("backfill", 4.2)
    assert brp.main(["--apply"], bars_fn=_bars) == {"stamped": 0, "skipped": 2, "unavailable": 1}
    assert store.get("p3").runner_path == {"source": "live"}         # never overwritten


def test_the_default_bar_source_is_the_disk_cache(monkeypatch):
    _seed()
    seen = []
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: seen.append(ticker))
    brp.main([])
    assert sorted(seen) == ["AAPL", "MSFT"]                           # one read per ticker


def test_an_unreadable_cache_is_unavailable_not_a_crash():
    _seed()

    def boom(ticker):
        raise OSError("bad csv")

    assert brp.main([], bars_fn=boom)["unavailable"] == 2
