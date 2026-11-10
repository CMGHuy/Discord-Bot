"""v204: the snapshot job adds no Discord message, alert or push (spec: no extra notification volume)."""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARDED = sorted((ROOT / "swingbot" / "refresher").glob("*.py")) + [
    ROOT / "swingbot" / "core" / "analytics" / "admin_snapshots.py",
    ROOT / "swingbot" / "core" / "analytics" / "risk_payload.py",
    ROOT / "swingbot" / "core" / "marketdata" / "daily_readonly.py",
]
FORBIDDEN = ("discord", "swingbot.commands")


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


@pytest.mark.parametrize("path", GUARDED, ids=lambda p: p.name)
def test_guarded_module_imports_no_discord_sender(path):
    bad = [m for m in _imports(path) if any(m == f or m.startswith(f + ".") for f in FORBIDDEN)]
    assert bad == [], f"{path.relative_to(ROOT)} imports {bad}"


def test_guard_covers_the_refresher_modules():
    names = {p.name for p in GUARDED if p.parent.name == "refresher"}
    assert {"__main__.py", "loop.py", "quotes.py", "snapshot_job.py"} <= names


RUNTIME = '''
import importlib.abc
import sys


class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name.split(".")[0] == "discord" or name == "swingbot.commands" or name.startswith("swingbot.commands."):
            raise ImportError("blocked: " + name)
        return None


sys.meta_path.insert(0, Block())
from datetime import datetime, timezone

from swingbot.core.analytics.admin_snapshots import SnapshotResult
from swingbot.refresher import loop, snapshot_job  # noqa: F401


class Rows:
    def put(self, *a, **k):
        return True


class Marks:
    def mark(self, *a, **k):
        pass

    def clear(self, *a, **k):
        pass


sent = []
at = datetime(2026, 10, 28, 15, tzinfo=timezone.utc).isoformat()
w = snapshot_job.SnapshotWorker(
    builders_fn=lambda: {"risk": lambda: SnapshotResult({}, {"computed_at": at}, False)},
    repo_fn=Rows, marks_fn=Marks, publish=sent.append, budget_fn=lambda: 5.0)
assert w.run_batch(["risk"]) == ["risk"] and sent == ["market"]
leaked = sorted(m for m in sys.modules if m.split(".")[0] == "discord" or m.startswith("swingbot.commands"))
assert leaked == [], leaked
print("ok")
'''


def test_snapshot_job_runs_with_discord_unimportable():
    proc = subprocess.run([sys.executable, "-c", RUNTIME], cwd=ROOT, capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().endswith("ok")
