"""v147: `measure_arms.py --record-blocked` -- TRAIN compression gate rows, own parser, early dispatch."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

from swingbot.core.backtesting.arms import compression_research as cr  # noqa: E402
from swingbot.core.backtesting.blocked_recorder import gate_row  # noqa: E402


def _row(ticker):
    return gate_row(population="train", arm="blocked", source="strategy", ticker=ticker,
                    strategy="Compression Short", horizon="2w", direction="bearish",
                    signal_date="2021-03-01", gate="compression", reason="earnings_unknown", margin=None,
                    cf_status="filled", cf_r=-0.4, win=False, expiry_bars=3, in_sample=True)


@pytest.mark.parametrize("extra", [["--validation"], ["--from", "2019-01-01"], ["--to", "2024-01-31"]])
def test_refuses_outside_train_before_loading_anything(monkeypatch, tmp_path, extra):
    monkeypatch.setattr(ma, "cached_universe", lambda: pytest.fail("loaded the universe"))
    monkeypatch.setattr(cr, "offline_context", lambda: pytest.fail("built the context"))
    out = tmp_path / "rows.jsonl"
    with pytest.raises(SystemExit) as exc:
        ma.cli(["--record-blocked", str(out), *extra])
    assert exc.value.code == 2 and not out.exists()


def test_writes_one_jsonl_file_from_the_backtest_cache_frames(monkeypatch, tmp_path, capsys):
    frames = {"AAA": "frame-a", "BBB": None, "CCC": "frame-c"}
    monkeypatch.setattr(ma, "cached_universe", lambda: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(ma, "load_frame", lambda ticker: frames[ticker])
    monkeypatch.setattr(cr, "offline_context", lambda: "ctx")
    calls = []

    def fake(frames_, window, *, context, horizons=("2w",)):
        calls.append((dict(frames_), window, context))
        return [_row(ticker) for ticker in frames_]

    monkeypatch.setattr(cr, "record_blocked_compression", fake)
    out = tmp_path / "nested" / "rows.jsonl"
    assert ma.cli(["--record-blocked", str(out)]) == 0
    assert calls == [({"AAA": "frame-a"}, ("2020-01-01", "2023-12-31"), "ctx"),
                     ({"CCC": "frame-c"}, ("2020-01-01", "2023-12-31"), "ctx")]
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [row["ticker"] for row in rows] == ["AAA", "CCC"]
    assert "3/3" in capsys.readouterr().out                    # flushed per-ticker progress


def test_cli_without_the_flag_is_main_unchanged(monkeypatch):
    monkeypatch.setattr(ma, "main", lambda argv: ("main", argv))
    assert ma.cli(["--knob", "X=1", "--stage", "pilot"]) == ("main", ["--knob", "X=1", "--stage", "pilot"])


def test_record_blocked_takes_instrument_v1_and_refuses_v2_before_loading_anything(monkeypatch, tmp_path):
    monkeypatch.setattr(ma, "cached_universe", lambda: pytest.fail("loaded the universe"))
    monkeypatch.setattr(cr, "offline_context", lambda: pytest.fail("built the context"))
    out = tmp_path / "rows.jsonl"
    with pytest.raises(SystemExit) as exc:
        ma.cli(["--record-blocked", str(out), "--instrument", "v2"])
    assert exc.value.code != 0 and "v147" in str(exc.value) and not out.exists()
    monkeypatch.setattr(ma, "cached_universe", lambda: [])
    monkeypatch.setattr(cr, "offline_context", lambda: "ctx")
    assert ma.cli(["--record-blocked", str(out), "--instrument", "v1"]) == 0
