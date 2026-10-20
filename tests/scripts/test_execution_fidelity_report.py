"""v173 §5: the report script is read-only -- the dev banner, the stored
verdict shown as stored, the mirror row, and never an evaluation or a write."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.reports import execution_fidelity_report as report
from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_io as oio
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.backtesting.instrument import stats
from tests.analytics.test_override_fidelity_replay import LAST_DAY, STOP_BAR, frame, plan
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)   # Mon 17:00 ET, after the close
PAYLOAD_KEYS = {"rows", "summary", "verdict", "engine_flags", "asof", "currency_symbol"}
VERDICT_KEYS = {"state", "n", "needed", "weeks", "week_floor", "open_n", "excluded_share",
                "evaluable", "waiting_on", "recorded", "recorded_on", "mean_delta_r",
                "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n"}
FLAGS = {"stall_exit_enabled": False, "runner_structure_exit": "off"}
RECORD = {"ledger_id": "v173-override-fidelity", "verdict": "COST", "recorded_on": "2026-12-04",
          "n": 31, "weeks": 12, "mean_delta_r": -0.22, "mean_delta_r_gross": -0.2,
          "ci": [-0.24, -0.2], "sum_delta_r": -6.82, "sum_delta_usd": -1364.0,
          "bar_close_n": 2, "excluded_share": 0.0, "engine_flags": FLAGS, "rows": []}
SUMMARY = {"n_by_status": {s: 0 for s in of.STATUSES}, "bulk_n": 0, "bulk_dates": {},
           "approx_n": 0, "counted_n": 0, "sum_delta_r": 0.0, "sum_delta_r_gross": 0.0,
           "sum_delta_usd": 0.0, "usd_missing_n": 0, "helped": 0, "hurt": 0, "neutral": 0,
           "splits": {"state_at_close": {}, "horizon": {}, "direction": {}}}


def _boom(*_args, **_kwargs):
    raise AssertionError("the report script never evaluates and never writes")


@pytest.fixture(autouse=True)
def _pinned(monkeypatch, tmp_path):
    """Code defaults, and every evaluating or writing call made to raise."""
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(stats, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    for module, name in ((ov, "evaluate_verdict"), (ov, "verdict_record"),
                         (oio, "run_daily_check"), (stats, "append_ledger_row")):
        monkeypatch.setattr(module, name, _boom)


def _no_inputs():
    return [], {}


def _rows(n: int, weeks: int, delta_r: float = -0.2) -> list[dict]:
    """n counted rows (individual, stamped, resolved) over `weeks` ISO weeks."""
    start = date(2026, 9, 7)                                  # a Monday
    return [of.OverrideRow(
        plan_id=f"p{i}", ticker="AAPL", horizon="2w", direction="bullish",
        state_at_close="ACTIVE", close_date=start + timedelta(weeks=i % weeks), bulk=False,
        approx=False, price_source="quote", status="resolved", actual_r=0.2 + delta_r,
        engine_r=0.2, delta_r=delta_r, delta_r_gross=delta_r + 0.02, actual_usd=None,
        engine_usd=None, delta_usd=round(delta_r * 200, 2), engine_exit_reason="stop",
        outcome="hurt").to_dict() for i in range(n)]


def _stub_report(monkeypatch, rows):
    """Stub build_report with these rows; the verdict part is the real
    verdict_payload over whatever stored record the script hands in."""
    seen = {}

    def fake(plans, trades, bars_fn, asof, recorded, currency_symbol):
        seen.update(asof=asof, recorded=recorded)
        return {"rows": rows, "summary": SUMMARY, "verdict": ov.verdict_payload(rows, recorded),
                "engine_flags": FLAGS, "asof": asof.isoformat(),
                "currency_symbol": currency_symbol}

    monkeypatch.setattr(ov, "build_report", fake)
    return seen


# -- the banner -----------------------------------------------------------------------

def test_a_dev_run_prints_the_banner_first(monkeypatch, capsys):
    _stub_report(monkeypatch, _rows(30, 10))
    out = report.main([], inputs_fn=_no_inputs, verdict_fn=lambda: None, now=NOW)
    printed = capsys.readouterr().out.splitlines()
    assert printed[0] == report.DEV_BANNER
    assert report.DEV_BANNER == ("DEV DATABASE: fixture data, not the real book. "
                                 "This report never writes a verdict.")
    assert (out["verdict"]["state"], out["verdict"]["evaluable"]) == ("WAITING", True)


def test_production_only_drops_the_banner_and_still_never_evaluates(monkeypatch, capsys):
    _stub_report(monkeypatch, _rows(30, 10))                 # the floors hold
    out = report.main(["--production"], inputs_fn=_no_inputs, verdict_fn=lambda: None, now=NOW)
    assert report.DEV_BANNER not in capsys.readouterr().out.splitlines()
    verdict = out["verdict"]
    assert (verdict["state"], verdict["evaluable"], verdict["recorded"]) == ("WAITING", True, False)
    assert not stats.LEDGER_PATH.exists()                    # nothing written anywhere


# -- the stored verdict ---------------------------------------------------------------

def test_the_stored_verdict_is_shown_as_stored(monkeypatch, capsys):
    seen = _stub_report(monkeypatch, _rows(12, 4, delta_r=0.8))   # live rows now look SAVED
    calls = []

    def verdict_fn():
        calls.append(1)
        return RECORD

    out = report.main(["--production"], inputs_fn=_no_inputs, verdict_fn=verdict_fn, now=NOW)
    assert calls == [1]
    assert seen == {"asof": LAST_DAY, "recorded": RECORD}
    v = out["verdict"]
    assert (v["state"], v["recorded"], v["recorded_on"], v["n"], v["weeks"]) == (
        "COST", True, "2026-12-04", 31, 12)
    assert (v["mean_delta_r"], v["mean_delta_r_gross"], list(v["ci"])) == (-0.22, -0.2, [-0.24, -0.2])
    assert (v["sum_delta_r"], v["sum_delta_usd"], v["bar_close_n"]) == (-6.82, -1364.0, 2)
    assert (v["evaluable"], list(v["waiting_on"])) == (False, ["count", "weeks"])   # live
    text = capsys.readouterr().out
    assert "verdict COST" in text
    assert "recorded 2026-12-04 from 31 overrides over 12 weeks" in text
    assert "before costs -0.200R" in text and "bar_close 2" in text


# -- the mirror row -------------------------------------------------------------------

def test_mirror_row_prints_one_validated_ledger_line(monkeypatch, capsys):
    monkeypatch.setattr(ov, "build_report", _boom)           # --mirror-row needs no replay
    out = report.main(["--production", "--mirror-row"], inputs_fn=_boom,
                      verdict_fn=lambda: RECORD, now=NOW)
    printed = capsys.readouterr().out.splitlines()
    assert len(printed) == 1
    row = json.loads(printed[0])
    stats.validate_ledger_row(row)
    assert row == out == ov.mirror_ledger_row(RECORD)
    assert (row["id"], row["date"], row["verdict"], row["instrument"], row["record"]) == (
        "v173-override-fidelity", "2026-12-04", "COST", "v2", ov.RESULTS_RECORD)


def test_mirror_row_without_a_verdict_says_so(capsys):
    out = report.main(["--production", "--mirror-row"], inputs_fn=_boom,
                      verdict_fn=lambda: None, now=NOW)
    assert capsys.readouterr().out.splitlines() == ["no verdict recorded"]
    assert out == {}


# -- the real pipeline on fixture data ------------------------------------------------

def test_the_real_pipeline_replays_from_the_cache_and_writes_json(capsys, tmp_path):
    seen = []

    def bars_fn(ticker):
        seen.append(ticker)
        return frame({19: STOP_BAR})

    target = tmp_path / "out.json"
    out = report.main(["--json", str(target)],
                      inputs_fn=lambda: ([plan()], {"p1": {"id": "t1", "shares": 10}}),
                      bars_fn=bars_fn, verdict_fn=lambda: None, now=NOW)
    assert seen == ["T"]
    assert set(out) == PAYLOAD_KEYS and set(out["verdict"]) == VERDICT_KEYS
    assert (out["asof"], out["currency_symbol"]) == (LAST_DAY.isoformat(), "$")
    [row] = out["rows"]
    assert set(row) == set(of.ROW_FIELDS)
    assert (row["plan_id"], row["status"], row["bulk"], row["approx"]) == (
        "p1", "resolved", False, False)
    assert row["delta_usd"] is not None and row["delta_r_gross"] is not None
    assert json.loads(target.read_text(encoding="utf-8")) == out
    printed = capsys.readouterr().out
    assert "stall_exit_enabled=False" in printed and "runner_structure_exit=off" in printed
    assert "resolved" in printed and "verdict WAITING" in printed


def test_render_lists_exclusions_waiting_on_and_the_bulk_dates():
    summary = SUMMARY | {"n_by_status": SUMMARY["n_by_status"] | {"stale": 2, "unstamped": 1,
                                                                  "open": 1},
                         "bulk_n": 15, "bulk_dates": {"2026-09-30": 15}, "approx_n": 3}
    payload = {"rows": [], "engine_flags": {"stall_exit_enabled": True, "runner_structure_exit": "on"},
               "asof": "2026-10-19", "currency_symbol": "$", "summary": summary,
               "verdict": {"state": "WAITING", "n": 0, "needed": 30, "weeks": 0, "week_floor": 10,
                           "open_n": 1, "excluded_share": 1.0, "evaluable": False,
                           "waiting_on": ["count", "weeks", "open", "excluded"],
                           "recorded": False, "recorded_on": None, "mean_delta_r": None,
                           "mean_delta_r_gross": None, "ci": None, "sum_delta_r": None,
                           "sum_delta_usd": None, "bar_close_n": 0}}
    text = "\n".join(report.render(payload))
    assert "No manual overrides in scope." in text
    assert "bulk clear 2026-09-30: 15 (not decisions, left out)" in text
    assert "approx (estimated exit): 3 (shown, not counted)" in text
    assert "stale: 2" in text and "unstamped: 1" in text and "open: 1" in text
    assert "before costs +0.000R" in text
    assert ("verdict WAITING: 0 of 30 counted rows, 0 of 10 weeks, open 1, excluded share "
            "100.0%, evaluable False; waiting on count, weeks, open, excluded") in text
    assert "recorded" not in text.split("verdict WAITING")[1]


# -- the results doc ------------------------------------------------------------------

def test_the_results_doc_carries_the_standing_procedure():
    assert ov.RESULTS_RECORD == "docs/superpowers/results/v173-override-fidelity.md"
    text = (ROOT / ov.RESULTS_RECORD).read_text(encoding="utf-8")
    assert "## Standing procedure: mirroring the recorded verdict" in text
    assert "execution_fidelity_report.py --production --mirror-row" in text
    assert "stats.append_ledger_row" in text
