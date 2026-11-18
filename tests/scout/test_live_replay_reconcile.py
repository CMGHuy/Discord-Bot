"""v232 V232-15: the CLI end to end on fixtures (no network, no database)."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from swingbot import config

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer2, layer2_run, render, table  # noqa: E402
from tests.scout.test_reconcile_layer1_run import BARS, _rec  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "live_replay_reconcile_script", REPO / "scripts" / "reports" / "live_replay_reconcile.py")
cli = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cli)

SIGNAL = layer2.ReplaySignal(lane="base", ticker="AAA", direction="bullish", source="confluence",
                             mode=None, decision_date="2026-10-06", horizon_key="2w",
                             strategy="RSI", entry=100.0, stop=98.0, target=104.0)
COVERAGE = {"window": ["2026-10-05", "2026-10-20"], "sessions": 12, "spy_missing": False,
            "base_missing_days": {"AAA": 2}, "panel_gaps": {}, "snapshot_missing": [],
            "extra_missing": {}}


class Provider:
    def __init__(self):
        self.calls = 0

    def daily_bars_between(self, tickers, start, end, *, adjustment):
        self.calls += 1
        kind = 0 if adjustment.value == "raw" else 1
        return {t: BARS[t][kind] for t in tickers if t in BARS}


@pytest.fixture
def env(monkeypatch, tmp_path):
    for name, value in (("SLIPPAGE_BPS", 5.0), ("COMMISSION_PER_TRADE", 1.0),
                        ("COMMISSION_RISK_BASIS", 100.0)):
        monkeypatch.setattr(config, name, value, raising=False)
    provider, lanes = Provider(), []

    def run_layer2(frames, window, params, *, base_tickers, modes, checkpoint_dir, out=print):
        lanes.append((window, tuple(base_tickers), tuple(sorted(modes))))
        return [SIGNAL]

    monkeypatch.setattr(cli, "make_provider", lambda: provider)
    monkeypatch.setattr(layer2_run, "params_digest", lambda params: "d" * 64)
    monkeypatch.setattr(layer2_run, "live_short_modes", lambda: frozenset({"broad"}))
    monkeypatch.setattr(layer2_run, "reference_symbols", lambda modes: ("SPY",))
    monkeypatch.setattr(layer2_run, "load_frames", lambda symbols: ({}, ["SPY"]))
    monkeypatch.setattr(layer2_run, "coverage", lambda frames, window, **kw: dict(COVERAGE))
    monkeypatch.setattr(layer2_run, "run_layer2", run_layer2)
    recs = [_rec("P1", "AAA"), _rec("P2", "BBB", "bearish"), _rec("P3", "AAA", klass="unfilled"),
            _rec("P4", "CCC"), _rec("P5", "AAA", klass="manual")]
    lines = [{"kind": "plan", "plan": r.plan, "trade": r.trade, "journal": r.journal} for r in recs]
    lines += [{"kind": "watchlist", "ticker": "AAA", "added_at": "2026-01-02T00:00:00+00:00"},
              {"kind": "deploy", "entry": {"ts": "2026-10-07T12:00:00+00:00", "git_sha": "abc1"}}]
    export = tmp_path / "reconcile.jsonl"
    export.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return {"tmp": tmp_path, "export": export, "provider": provider, "lanes": lanes}


def _argv(env, *extra, since="2026-10-05"):
    t = env["tmp"]
    return ["--export", str(env["export"]), "--since", since, "--until", "2026-10-20",
            "--bars-root", str(t / "bars"), "--work-dir", str(t / "work"),
            "--results-dir", str(t / "results"), "--date", "2026-11-17", "--fetch-bars",
            "--resamples", "200", "--seed", "42", *extra]


def _out(env):
    stem = env["tmp"] / "results" / "2026-11-17-v232-live-replay-reconciliation"
    return Path(f"{stem}.json"), Path(f"{stem}.md")


def _json(env):
    return json.loads(_out(env)[0].read_text(encoding="utf-8"))


def test_trade_rows_are_checkpointed_and_hashed(env):
    assert cli.main(_argv(env)) == 0
    report, markdown = _json(env), _out(env)[1].read_text(encoding="utf-8")
    assert markdown.splitlines()[2] == f"> {render.CAVEAT}"
    assert render.leaks(report, markdown) == []
    assert report["meta"]["window"] == ["2026-10-05", "2026-10-20"]
    assert report["meta"]["inputs"] == {
        "reconcile.jsonl": hashlib.sha256(env["export"].read_bytes()).hexdigest()}
    assert report["populations"]["long"]["headline"]["refused_tickers"]["split_in_window"] == ["CCC"]
    assert '"r_as_backtest"' not in _out(env)[0].read_text(encoding="utf-8")
    rows = env["tmp"] / "work" / "trade-rows.jsonl"
    assert len(rows.read_text(encoding="utf-8").splitlines()) == 5
    assert report["meta"]["rows_sha256"] == hashlib.sha256(rows.read_bytes()).hexdigest()
    assert report["layer1"]["long"]["headline"]["v1"]["table"][-1]["n"] == 3


def test_a_rerun_resumes_and_writes_the_same_report(env):
    assert cli.main(_argv(env)) == 0
    first, calls = _json(env), env["provider"].calls
    assert cli.main(_argv(env)) == 0
    assert env["provider"].calls == calls
    second = _json(env)
    first.pop("meta"), second.pop("meta")
    assert first == second


def test_layer2_gets_the_window_tickers_and_live_modes(env):
    assert cli.main(_argv(env)) == 0
    assert env["lanes"] == [(("2026-10-05", "2026-10-20"), ("AAA", "BBB", "CCC"), ("broad",))]
    assert cli.main(_argv(env, "--short-modes", "none")) == 0
    assert env["lanes"][-1][2] == ()


@pytest.mark.parametrize("guard", ["self_check", "leaks"])
def test_a_failed_guard_writes_nothing(env, monkeypatch, guard):
    def tampered(*args, **kwargs):
        raise table.ReconcileError("tampered")

    if guard == "self_check":
        monkeypatch.setattr(table, "self_check", tampered)
    else:
        monkeypatch.setattr(render, "leaks", lambda report, markdown: ["json x: forbidden key"])
    assert cli.main(_argv(env)) == 2
    assert not _out(env)[0].exists() and not _out(env)[1].exists()
