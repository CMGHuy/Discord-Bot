"""v173 §4: the frozen verdict rule, the stored record and its jsonl mirror,
the payload (never evaluates) and build_report."""
import json
from datetime import date, timedelta

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
               "excluded_share", "engine_flags", "rows"}
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


def cost_record():
    rows = cost_rows(usd=-10.0)
    return ov.verdict_record(ov.evaluate_verdict(rows), rows, FLAGS, recorded_on=RECORDED_ON)


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
    record = ov.verdict_record(verdict, rows, FLAGS, recorded_on=RECORDED_ON)
    assert set(record) == RECORD_KEYS
    assert (record["ledger_id"], record["verdict"], record["recorded_on"]) == (
        "v173-override-fidelity", "COST", "2027-03-01")
    for key in ("n", "weeks", "mean_delta_r", "mean_delta_r_gross", "ci", "sum_delta_r",
                "sum_delta_usd", "bar_close_n", "excluded_share"):
        assert record[key] == verdict[key]
    assert record["engine_flags"] == FLAGS
    assert [r["plan_id"] for r in record["rows"]] == [f"p{i}" for i in range(30)]
    assert all(set(r) == ROW_KEYS for r in record["rows"])
    assert json.loads(json.dumps(record)) == record              # JSONB-ready


@pytest.mark.parametrize("verdict", [{"state": "WAITING"}, {"state": "OPEN"}, {}])
def test_only_an_evaluated_outcome_is_recorded(verdict):
    with pytest.raises(ValueError):
        ov.verdict_record(verdict, [], FLAGS, recorded_on=RECORDED_ON)


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


def test_report_payload_shape(monkeypatch):
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    calls = []
    out = ov.build_report(_book(), {"a": {"id": "t", "shares": 10}}, _bars_fn(calls),
                          LAST_DAY, None, "$")
    assert set(out) == {"rows", "summary", "verdict", "engine_flags", "asof", "currency_symbol"}
    assert (out["asof"], out["currency_symbol"]) == ("2026-10-19", "$")
    assert out["engine_flags"] == FLAGS == ov.engine_flags()
    assert sorted(calls) == ["AAA", "BAD", "BBB"]               # once per ticker
    assert [r["plan_id"] for r in out["rows"]] == ["b", "d", "a"]   # newest close first
    assert set(of.ROW_FIELDS) == ROW_KEYS                       # V173-7's row contract
    assert all(set(r) == ROW_KEYS for r in out["rows"])
    by_id = {r["plan_id"]: r for r in out["rows"]}
    assert by_id["d"]["status"] == "unreplayable"
    assert by_id["b"]["bulk"] is True
    assert by_id["a"]["delta_usd"] is not None and by_id["b"]["delta_usd"] is None
    assert by_id["a"]["delta_r_gross"] is not None
    assert out["summary"]["bulk_dates"] == {"2026-10-08": 1}
    assert set(out["verdict"]) == VERDICT_KEYS
    assert out["verdict"]["state"] == "WAITING"


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
