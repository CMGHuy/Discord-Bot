"""v147 V147-16: the read-only production progress check and its idempotent cron installer."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("gcp", ROOT / "scripts" / "ops" / "gate_counterfactual_progress.py")
gcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gcp)
INSTALLER = ROOT / "scripts" / "ops" / "install_gate_counterfactual_cron.sh"


def _record(i=0, *, gate="rs", reason="rs_blocked", status="filled", day=None):
    filled = status == "filled"
    return {"id": i, "ticker": f"T{i}", "gate": gate, "reason": reason, "strategy": "Fibonacci",
            "horizon": "2w", "direction": "bearish", "source": "strategy",
            "signal_date": day or f"2026-10-{5 + (i % 20):02d}", "cf_status": status, "margin": None,
            "plan": None, "cf_r": 0.5 if filled else None, "win": True if filled else None}


def test_counts_per_cell_and_status_with_distinct_filled_against_the_floor():
    records = ([_record(i) for i in range(31)] + [_record(100 + i, status="pending") for i in range(2)]
               + [_record(200 + i, gate="plan_rejected", reason="risk_cap") for i in range(3)]
               + [_record(300 + i, gate="plan_rejected", reason="no_qualifying_target", status="no-plan")
                  for i in range(2)])
    lines = gcp.progress_lines(records)
    text = "\n".join(lines)
    assert lines[0].startswith("gate_rejections: 38 rows")
    (rs,) = [l for l in lines if l.strip().startswith("rs ")]
    assert "pending=2" in rs and "filled=31" in rs and "distinct filled 31/30 READY" in rs
    (cap,) = [l for l in lines if l.strip().startswith("risk_cap ")]
    assert "filled=3" in cap and "distinct filled 3/30" in cap and "READY" not in cap
    assert "compression" in text and "no_qualifying_target" in text
    assert lines[-1] == "ALL LIVE VERDICT CELLS PAST THE FLOOR: no"


def test_consecutive_day_reblocks_count_once():
    records = [_record(0, day=f"2026-10-0{d}") for d in (5, 6, 7)]
    records = [dict(r, ticker="AAPL") for r in records]
    (rs,) = [l for l in gcp.progress_lines(records) if l.strip().startswith("rs ")]
    assert "filled=3" in rs and "distinct filled 1/30" in rs


def test_every_live_cell_past_the_floor_says_so():
    records = [_record(i, gate=g, reason=r) for g, r in (("rs", "rs_blocked"), ("plan_rejected", "risk_cap"),
                                                        ("compression", "earnings_unknown"))
               for i in range(30)]
    records = [dict(r, ticker=f"{r['gate']}-{r['id']}") for r in records]
    assert gcp.progress_lines(records)[-1].startswith("ALL LIVE VERDICT CELLS PAST THE FLOOR: yes")


def test_an_empty_table_prints_zero_rows():
    lines = gcp.progress_lines([])
    assert lines[0] == "gate_rejections: 0 rows"
    assert lines[-1] == "ALL LIVE VERDICT CELLS PAST THE FLOOR: no"


def test_an_unreadable_table_exits_one(monkeypatch, capsys):
    from swingbot.core.db.repositories import gate_rejections

    class _Down:
        def list_since(self, since=None, *, conn=None):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(gate_rejections, "gate_rejections_repo", lambda: _Down())
    assert gcp.main() == 1
    assert "unreadable" in capsys.readouterr().out


def test_the_installer_follows_the_idempotent_pattern():
    text = INSTALLER.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash") and "set -euo pipefail" in text
    assert "scripts/ops/gate_counterfactual_progress.py" in text
    assert "/opt/swing-bot/logs/gate-counterfactual.log" in text
    assert "30 7 * * 6 " in text                                  # weekly, Saturday 07:30 UTC
    assert 'grep -vF "$MARKER"' in text


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="needs a POSIX bash")
def test_the_installer_is_idempotent_against_a_fake_crontab(tmp_path):
    store, bindir = tmp_path / "crontab.txt", tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "crontab"
    fake.write_text('#!/usr/bin/env bash\n'
                    'if [ "$1" = "-l" ]; then [ -f "$FAKE_CRONTAB" ] && cat "$FAKE_CRONTAB" || exit 1;\n'
                    'elif [ "$1" = "-" ]; then cat > "$FAKE_CRONTAB.new" && mv "$FAKE_CRONTAB.new" "$FAKE_CRONTAB"; fi\n',
                    encoding="utf-8")   # buffer like the real crontab: `-l | ... | -` must not truncate mid-read
    fake.chmod(0o755)
    store.write_text("0 1 * * * echo keep-me\n", encoding="utf-8")
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "FAKE_CRONTAB": str(store)}
    for _ in range(2):
        done = subprocess.run(["bash", str(INSTALLER)], env=env, capture_output=True, text=True, timeout=30)
        assert done.returncode == 0, done.stderr
    lines = store.read_text(encoding="utf-8").splitlines()
    assert "0 1 * * * echo keep-me" in lines
    assert sum("gate_counterfactual_progress.py" in line for line in lines) == 1
