"""v173 §4: the frozen verdict rule, the stored record and its jsonl mirror,
the payload (never evaluates) and build_report."""
import ast
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.backtesting.instrument import stats
from tests.analytics.test_override_fidelity_replay import LAST_DAY, STOP_BAR, frame, plan
from tests.analytics.test_override_summary import row
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

W0 = date(2026, 8, 3)
RECORDED_ON = date(2027, 3, 1)
FLAGS = {"stall_exit_enabled": False, "runner_structure_exit": "off"}
CONDITION_KEYS = {"n", "weeks", "open_n", "excluded_share", "evaluable", "waiting_on"}
EVAL_KEYS = {"state", "n", "weeks", "mean_delta_r", "mean_delta_r_gross", "ci",
             "sum_delta_r", "sum_delta_usd", "bar_close_n", "excluded_share"}
RECORD_KEYS = {"ledger_id", "verdict", "recorded_on", "n", "weeks", "mean_delta_r",
               "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n",
               "excluded_share", "engine_flags", "rows",
               "asof", "engine_config", "engine_config_sha256", "bars_last_date"}
REPO = Path(__file__).resolve().parents[2]
#: The exit engine the replay walks: exit_sim_v2.walk_v2 / fill_bar_exit, the
#: exit_sim helpers they call, and the replay module itself.
ENGINE_ROOTS = ("swingbot/core/planning/exit_sim.py", "swingbot/core/planning/exit_sim_v2.py",
                "swingbot/core/analytics/override_fidelity.py")
_CONFIG_READ = re.compile(r"config\.([A-Z][A-Z0-9_]+)|getattr\(\s*config\s*,\s*[\"']([A-Z0-9_]+)")
VERDICT_KEYS = {"state", "n", "needed", "weeks", "week_floor", "open_n", "excluded_share",
                "evaluable", "waiting_on", "recorded", "recorded_on", "mean_delta_r",
                "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n"}
ROW_KEYS = {"plan_id", "ticker", "horizon", "direction", "state_at_close", "close_date",
            "bulk", "approx", "price_source", "status", "actual_r", "engine_r", "delta_r",
            "delta_r_gross", "actual_usd", "engine_usd", "delta_usd", "engine_exit_reason",
            "outcome", "source"}


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)


def spread(n, weeks, delta=0.3, **kw):
    """n counted rows over `weeks` distinct ISO weeks; `delta` may be a
    function of the week number."""
    return [row(delta(i % weeks) if callable(delta) else delta,
                W0 + timedelta(weeks=i % weeks), plan_id=f"p{i}", **kw) for i in range(n)]


def cost_rows(**kw):
    return spread(30, 10, lambda w: -0.5 + 0.02 * w, **kw)


def record_of(verdict, rows, *, plans=(), bars=None, asof=RECORDED_ON):
    """verdict_record with the live engine snapshot; synthetic rows have no plan."""
    return ov.verdict_record(verdict, rows, FLAGS, recorded_on=RECORDED_ON, asof=asof,
                             engine_config=ov.engine_config(), plans=plans,
                             bars={} if bars is None else bars)


def cost_record():
    rows = cost_rows(usd=-10.0)
    return record_of(ov.evaluate_verdict(rows), rows)


def _no_bootstrap(*_a, **_k):
    raise AssertionError("the bootstrap must not run here")


# -- constants and ledger vocabulary ---------------------------------------------

def test_the_rule_constants_are_the_spec_values():
    assert (of.VERDICT_FLOOR, of.WEEK_FLOOR, of.EXCLUDED_CAP, of.DEAD_BAND) == (30, 10, 0.20, 0.05)
    assert of.LEDGER_ID == "v173-override-fidelity"
    assert ov.RESULTS_RECORD == "docs/superpowers/results/v173-override-fidelity.md"
    for gone in ("SPEC_PATH", "ledger_row", "recorded_verdict"):
        assert not hasattr(ov, gone)


def test_the_ledger_accepts_the_three_outcomes_and_never_waiting():
    assert stats.VERDICTS[-3:] == ("COST", "SAVED", "INCONCLUSIVE")
    assert ov.WAITING not in stats.VERDICTS


# -- conditions: every floor, and which ones fail ------------------------------------

@pytest.mark.parametrize("rows, waiting_on", [
    pytest.param(spread(29, 10), ["count"], id="29-rows"),
    pytest.param(spread(30, 9), ["weeks"], id="9-weeks"),
    pytest.param(spread(30, 10) + [row(status="open")], ["open"], id="one-open"),
    pytest.param(spread(30, 10) + [row(status="ambiguous", plan_id=f"x{i}") for i in range(8)],
                 ["excluded"], id="over-the-cap"),
    pytest.param(spread(29, 9) + [row(status="open")]
                 + [row(status="stale", plan_id=f"x{i}") for i in range(8)],
                 ["count", "weeks", "open", "excluded"], id="all-four-in-order"),
    pytest.param(spread(30, 10), [], id="evaluable"),
])
def test_conditions_name_every_failing_floor_in_order(rows, waiting_on):
    out = ov.conditions(rows)
    assert set(out) == CONDITION_KEYS
    assert out["waiting_on"] == waiting_on
    assert out["evaluable"] is (waiting_on == [])


def test_exclusions_above_20_percent_wait_and_exactly_20_percent_does_not():
    over = spread(30, 10) + [row(status="ambiguous", plan_id=f"x{i}") for i in range(8)]
    assert ov.conditions(over)["excluded_share"] == pytest.approx(8 / 38)
    at_cap = spread(40, 10) + [row(status="stale", plan_id=f"x{i}") for i in range(10)]
    assert ov.conditions(at_cap)["excluded_share"] == 0.2
    assert ov.conditions(at_cap)["evaluable"] is True


def test_unstamped_rows_are_eligible_and_count_against_the_cap():
    rows = spread(30, 10) + [row(status="unstamped", price_source="none", plan_id=f"u{i}")
                             for i in range(8)]
    out = ov.conditions(rows)
    assert (out["n"], out["waiting_on"]) == (30, ["excluded"])
    assert len(ov.eligible(rows)) == 38


def test_open_bulk_or_approx_rows_do_not_hold_it():
    rows = spread(30, 10) + [row(status="open", bulk=True), row(status="open", approx=True)]
    assert ov.conditions(rows)["evaluable"] is True


def test_bulk_and_approx_rows_never_count_toward_n():
    rows = spread(29, 10) + [row(bulk=True)] * 5 + [row(approx=True)] * 5
    assert ov.conditions(rows)["n"] == 29
    assert [r.plan_id for r in ov.counted(rows)] == [f"p{i}" for i in range(29)]
    assert len(ov.eligible(rows)) == 29


# -- one evaluation ----------------------------------------------------------------

def test_evaluate_refuses_rows_that_are_not_evaluable():
    with pytest.raises(ValueError, match="count"):
        ov.evaluate_verdict(spread(29, 10))


@pytest.mark.parametrize("delta, state", [
    (lambda w: -0.5 + 0.02 * w, "COST"),
    (lambda w: 0.5 - 0.02 * w, "SAVED"),
    (lambda w: 0.6 if w % 2 == 0 else -0.6, "INCONCLUSIVE"),
])
def test_seeded_delta_sets_give_each_outcome(delta, state):
    rows = spread(30, 10, delta)
    out = ov.evaluate_verdict(rows)
    assert set(out) == EVAL_KEYS
    assert (out["state"], out["n"], out["weeks"]) == (state, 30, 10)
    lo, hi = out["ci"]
    assert lo <= out["mean_delta_r"] <= hi
    assert ov.evaluate_verdict(rows) == out          # seeded: the same draw every time


def test_the_evaluation_carries_the_gross_mean_the_sums_and_bar_close_n():
    rows = cost_rows(usd=-10.0)
    for i in (0, 1, 2):
        rows[i] = row(rows[i].delta_r, rows[i].close_date, usd=-10.0,
                      price_source="bar_close", plan_id=rows[i].plan_id)
    rows += [row(-0.4, approx=True, price_source="bar_close")]      # shown, never counted
    out = ov.evaluate_verdict(rows)
    assert out["mean_delta_r"] == pytest.approx(-0.41, abs=1e-9)    # -0.5 + 0.02 x 4.5
    assert out["mean_delta_r_gross"] == pytest.approx(-0.40, abs=1e-9)
    assert out["sum_delta_r"] == pytest.approx(-12.3, abs=1e-9)
    assert out["sum_delta_usd"] == pytest.approx(-300.0, abs=1e-9)
    assert out["bar_close_n"] == 3
    assert out["excluded_share"] == 0.0


def test_no_dollars_on_any_counted_row_gives_no_dollar_sum():
    assert ov.evaluate_verdict(cost_rows())["sum_delta_usd"] is None


def test_dict_rows_evaluate_like_override_rows():
    rows = cost_rows()
    assert ov.evaluate_verdict([r.to_dict() for r in rows]) == ov.evaluate_verdict(rows)


# -- the stored record and its jsonl mirror ------------------------------------------

def test_the_record_has_the_stored_shape():
    rows = cost_rows(usd=-10.0) + [row(bulk=True), row(status="stale", plan_id="s")]
    verdict = ov.evaluate_verdict(rows)
    record = record_of(verdict, rows, asof=date(2027, 2, 26))
    assert set(record) == RECORD_KEYS
    assert (record["ledger_id"], record["verdict"], record["recorded_on"]) == (
        "v173-override-fidelity", "COST", "2027-03-01")
    for key in ("n", "weeks", "mean_delta_r", "mean_delta_r_gross", "ci", "sum_delta_r",
                "sum_delta_usd", "bar_close_n", "excluded_share"):
        assert record[key] == verdict[key]
    assert record["engine_flags"] == FLAGS
    _assert_provenance(record)
    assert json.loads(json.dumps(record, allow_nan=False)) == record   # JSONB-ready


def _assert_provenance(record):
    """The widened fields (panel review, 2026-10-20) on synthetic, plan-less rows."""
    assert record["asof"] == "2027-02-26"
    assert record["engine_config"] == ov.engine_config()
    assert record["engine_config_sha256"] == ov.config_sha256(ov.engine_config())
    assert record["bars_last_date"] == {"T": None}               # no cache frame for T
    assert [r["plan_id"] for r in record["rows"]] == [f"p{i}" for i in range(30)]
    assert all(set(r) == ROW_KEYS | {"bars_sha256"} for r in record["rows"])
    assert all(r["bars_sha256"] is None for r in record["rows"])  # no plan to place


@pytest.mark.parametrize("verdict", [{"state": "WAITING"}, {"state": "OPEN"}, {}])
def test_only_an_evaluated_outcome_is_recorded(verdict):
    with pytest.raises(ValueError):
        record_of(verdict, [])


# -- the exit-engine config snapshot ---------------------------------------------------

def _module_file(module: str) -> Path | None:
    path = REPO / Path(*module.split("."))
    for candidate in (path.with_suffix(".py"), path / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imported_modules(tree: ast.AST, package: str) -> set[str]:
    """Every swingbot module an ImportFrom names, relative ones resolved."""
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        base = f"{package}.{node.module}" if node.level else (node.module or "")
        names.add(base)
        names.update(f"{base}.{alias.name}" for alias in node.names)
    return {name for name in names if name.startswith("swingbot.")}


def _engine_files() -> set[Path]:
    """The engine roots and every swingbot module they import (one level)."""
    files = set()
    for root in ENGINE_ROOTS:
        path = REPO / root
        package = ".".join(Path(root).with_suffix("").parts[:-1])
        files.add(path)
        imported = _imported_modules(ast.parse(path.read_text(encoding="utf-8")), package)
        files.update(f for f in map(_module_file, imported) if f is not None)
    return {f for f in files if f.name != "__init__.py" and f != REPO / "swingbot/config.py"}


def _config_reads(path: Path) -> set[str]:
    return {a or b for a, b in _CONFIG_READ.findall(path.read_text(encoding="utf-8"))}


def test_the_snapshot_holds_every_config_name_the_exit_engine_reads():
    files = _engine_files()
    assert REPO / "swingbot/core/planning/lifecycle.py" in files      # the scan reached imports
    read = set().union(*map(_config_reads, files))
    assert {"RUNNER_HL_TRAIL_ATR_BUFFER", "RUNNER_STALL_RANGE_MAX", "RUNNER_GIVEBACK_PCT"} <= read
    missing = read - set(ov.engine_config())
    assert not missing, f"engine_config() misses config the exit engine reads: {sorted(missing)}"


def test_the_snapshot_carries_the_module_level_giveback_basis(monkeypatch):
    from swingbot.core.planning import exit_sim
    assert ov.engine_config()["exit_sim.GIVEBACK_EXTREME_BASIS"] == exit_sim.GIVEBACK_EXTREME_BASIS
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "high_low")
    assert ov.engine_config()["exit_sim.GIVEBACK_EXTREME_BASIS"] == "high_low"


def test_the_snapshot_keeps_the_flag_values_and_is_json_ready():
    snapshot = ov.engine_config()
    flags = ov.engine_flags()
    assert snapshot["STALL_EXIT_ENABLED"] is flags["stall_exit_enabled"]
    assert snapshot["RUNNER_STRUCTURE_EXIT"] == flags["runner_structure_exit"]
    assert json.loads(json.dumps(snapshot, allow_nan=False)) == snapshot


def test_the_config_hash_is_stable_and_moves_with_any_engine_setting(monkeypatch):
    first = ov.config_sha256(ov.engine_config())
    assert first == ov.config_sha256(dict(reversed(list(ov.engine_config().items()))))
    canonical = json.dumps(ov.engine_config(), sort_keys=True, separators=(",", ":"))
    assert first == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", 0.25)
    assert ov.config_sha256(ov.engine_config()) != first


# -- the bars each counted row was replayed on ----------------------------------------

def _replayed_a(bars):
    p = plan(plan_id="a", ticker="AAA")
    replayed = of.replay_override(p, bars, LAST_DAY, None)
    assert replayed.status == "resolved"
    return p, replayed


def _stored_row(bars):
    p, replayed = _replayed_a(bars)
    record = record_of(ov.evaluate_verdict(cost_rows()), [replayed], plans=[p],
                       bars={"AAA": bars}, asof=LAST_DAY)
    (stored,) = record["rows"]
    return record, stored


def test_a_counted_row_stores_its_delta_and_the_hash_of_its_fill_to_asof_bars():
    bars = frame({19: STOP_BAR})
    p, replayed = _replayed_a(bars)
    record, stored = _stored_row(bars)
    assert (stored["plan_id"], stored["delta_r"]) == ("a", replayed.delta_r)
    walked = of.replay_slice(p, bars, LAST_DAY)
    assert (walked.index[0].date(), walked.index[-1].date()) == (date(2026, 10, 5), LAST_DAY)
    assert stored["bars_sha256"] == ov.frame_sha256(walked)
    assert (record["asof"], record["bars_last_date"]) == ("2026-10-19", {"AAA": "2026-10-19"})


def test_the_bar_hash_moves_with_a_walked_bar_only():
    _, base = _stored_row(frame({19: STOP_BAR}))
    _, warm = _stored_row(frame({19: STOP_BAR, 3: (99.0, 99.5, 98.5, 99.0)}))
    _, walked = _stored_row(frame({19: STOP_BAR, 20: (96.0, 97.0, 95.5, 96.5)}))
    later, after = _stored_row(frame({19: STOP_BAR}, n=27))
    assert warm["bars_sha256"] == base["bars_sha256"]          # before the fill
    assert after["bars_sha256"] == base["bars_sha256"]         # after asof: trimmed
    assert walked["bars_sha256"] != base["bars_sha256"]
    assert later["bars_last_date"] == {"AAA": "2026-10-20"}    # the cache's own last bar


def test_the_frame_hash_is_sha256_of_the_canonical_bar_json():
    bars = frame()
    expected = json.dumps({"columns": ["Open", "High", "Low", "Close", "Volume"],
                           "bars": [[stamp.isoformat(), *map(float, values)]
                                    for stamp, values in zip(bars.index, bars.to_numpy())]},
                          separators=(",", ":"), allow_nan=False)
    assert ov.frame_sha256(bars) == hashlib.sha256(expected.encode("utf-8")).hexdigest()


def test_an_unplaceable_fill_stores_no_bar_hash():
    assert of.replay_slice(plan(plan_id="a", fill_at=None), frame(), LAST_DAY) is None
    assert of.replay_slice(plan(plan_id="a"), None, LAST_DAY) is None


def test_the_mirror_row_is_a_valid_ledger_line(tmp_path):
    record = cost_record()
    entry = ov.mirror_ledger_row(record)
    stats.validate_ledger_row(entry)
    assert set(entry) == set(stats.LEDGER_FIELDS)
    assert (entry["id"], entry["date"], entry["instrument"], entry["verdict"]) == (
        "v173-override-fidelity", "2027-03-01", "v2", "COST")
    assert (entry["n"], entry["exp_r"], entry["p"], entry["record"]) == (
        30, record["mean_delta_r"], None, ov.RESULTS_RECORD)
    lo, hi = record["ci"]
    assert entry["hypothesis"] == ("Manual overrides vs the v2 engine: mean delta R, "
                                   f"week-cluster bootstrap 95% CI [{lo:.3f}, {hi:.3f}]")
    path = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(entry, path=path)
    assert stats.load_ledger(path) == [entry]
    with pytest.raises(ValueError):
        stats.append_ledger_row(entry, path=path)      # one line per id


# -- verdict_payload: never evaluates -------------------------------------------------

def test_a_recorded_verdict_wins_and_the_live_fields_stay_live(monkeypatch):
    record = cost_record()
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    live = spread(40, 12, 0.5) + [row(status="open", plan_id="o")]   # live rows now look SAVED
    shown = ov.verdict_payload(live, record)
    assert set(shown) == VERDICT_KEYS
    assert (shown["state"], shown["recorded"], shown["recorded_on"]) == ("COST", True, "2027-03-01")
    for key in ("n", "weeks", "mean_delta_r", "mean_delta_r_gross", "ci", "sum_delta_r",
                "sum_delta_usd", "bar_close_n"):
        assert shown[key] == record[key]
    assert (shown["open_n"], shown["evaluable"], shown["waiting_on"]) == (1, False, ["open"])
    assert shown["excluded_share"] == 0.0
    assert (shown["needed"], shown["week_floor"]) == (30, 10)


def test_without_a_record_the_payload_waits_even_when_evaluable(monkeypatch):
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    rows = spread(30, 10, 0.5, price_source="bar_close")
    out = ov.verdict_payload(rows, None)
    assert set(out) == VERDICT_KEYS
    assert (out["state"], out["evaluable"], out["waiting_on"], out["recorded"]) == (
        "WAITING", True, [], False)
    assert all(out[k] is None for k in ("recorded_on", "mean_delta_r", "mean_delta_r_gross",
                                        "ci", "sum_delta_r", "sum_delta_usd"))
    assert (out["n"], out["weeks"], out["bar_close_n"]) == (30, 10, 30)


def test_waiting_with_the_count_met_lists_what_it_waits_on(monkeypatch):
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    out = ov.verdict_payload(spread(30, 9), None)
    assert (out["state"], out["n"], out["evaluable"], out["waiting_on"]) == (
        "WAITING", 30, False, ["weeks"])


# -- build_report ------------------------------------------------------------------

def _book():
    return [plan(plan_id="a", ticker="AAA"),
            plan(plan_id="b", ticker="BBB", reason="manual_bulk",
                 close_at="2026-10-08T18:00:00+00:00"),
            plan(plan_id="c", ticker="AAA", reason="tp1_runner_trail"),   # not an override
            plan(plan_id="d", ticker="BAD")]


def _bars_fn(calls):
    def bars_fn(ticker):
        calls.append(ticker)
        if ticker == "BAD":
            raise OSError("corrupt cache file")
        return frame({19: STOP_BAR})
    return bars_fn


def _assert_row_contract(out):
    assert [r["plan_id"] for r in out["rows"]] == ["b", "d", "a"]   # newest close first
    assert set(of.ROW_FIELDS) == ROW_KEYS                       # V173-7's row contract
    assert all(set(r) == ROW_KEYS for r in out["rows"])
    by_id = {r["plan_id"]: r for r in out["rows"]}
    assert by_id["d"]["status"] == "unreplayable"
    assert by_id["b"]["bulk"] is True
    assert by_id["a"]["delta_usd"] is not None and by_id["b"]["delta_usd"] is None
    assert by_id["a"]["delta_r_gross"] is not None


def test_report_payload_shape(monkeypatch):
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    calls = []
    out = ov.build_report(_book(), {"a": {"id": "t", "shares": 10}}, _bars_fn(calls),
                          LAST_DAY, None, "$")
    assert set(out) == {"rows", "summary", "verdict", "engine_flags", "asof", "currency_symbol"}
    assert (out["asof"], out["currency_symbol"]) == ("2026-10-19", "$")
    assert out["engine_flags"] == FLAGS == ov.engine_flags()
    assert sorted(calls) == ["AAA", "BAD", "BBB"]               # once per ticker
    _assert_row_contract(out)
    assert out["summary"]["bulk_dates"] == {"2026-10-08": 1}
    assert set(out["verdict"]) == VERDICT_KEYS
    assert out["verdict"]["state"] == "WAITING"


def test_report_fills_the_bar_cache_its_caller_hands_it():
    cache = {}
    ov.build_report(_book(), {}, _bars_fn([]), LAST_DAY, None, "$", cache=cache)
    assert set(cache) == {"AAA", "BBB", "BAD"} and cache["BAD"] is None


def test_report_shows_the_stored_record(monkeypatch):
    record = cost_record()
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    out = ov.build_report(_book(), {}, _bars_fn([]), LAST_DAY, record, "$")
    assert (out["verdict"]["state"], out["verdict"]["recorded_on"]) == ("COST", "2027-03-01")
    assert out["verdict"]["n"] == 30                     # the record's, not the live 1


def test_report_with_no_overrides_is_empty_not_an_error():
    out = ov.build_report([plan(reason="tp1_runner_trail")], {}, lambda t: None, LAST_DAY,
                          None, "$")
    assert out["rows"] == []
    assert out["summary"]["counted_n"] == 0
    assert out["verdict"]["state"] == "WAITING"
