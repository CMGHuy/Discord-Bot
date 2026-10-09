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


def test_a_plan_whose_compute_raises_is_unavailable_and_the_rest_still_stamp(monkeypatch):
    store = _seed()
    real = rp.compute_runner_path

    def flaky(plan, bars, *, source="live"):
        if plan.plan_id == "p2":
            raise ValueError("NaN bars")
        return real(plan, bars, source=source)

    store.get("p2").ticker = "AAPL"                                  # give p2 bars so it reaches compute
    plan2 = store.get("p2")
    plan2.ticker = "AAPL"
    store.update(plan2)
    monkeypatch.setattr(rp, "compute_runner_path", flaky)
    assert brp.main(["--apply"], store=store, bars_fn=_bars) == {"stamped": 1, "skipped": 1,
                                                                 "unavailable": 1}
    assert store.get("p1").runner_path["source"] == "backfill"
    assert store.get("p2").runner_path is None


def test_a_live_stamp_landing_mid_run_is_not_overwritten(monkeypatch):
    store = _seed()
    real = rp.compute_runner_path

    def racing(plan, bars, *, source="live"):
        live = store.get(plan.plan_id)
        live.runner_path = {"source": "live"}
        store.update(live)                                           # a live close stamps meanwhile
        return real(plan, bars, source=source)

    monkeypatch.setattr(rp, "compute_runner_path", racing)
    brp.main(["--apply"], store=store, bars_fn=_bars)
    assert store.get("p1").runner_path == {"source": "live"}
