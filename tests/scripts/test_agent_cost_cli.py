"""agent_cost.py: the per-agent table and the command line (V199-8b)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "agent_cost.py"
_SPEC = importlib.util.spec_from_file_location("agent_cost", SCRIPT)
agent_cost = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = agent_cost  # the dataclass resolves its annotations through it
_SPEC.loader.exec_module(agent_cost)

TS = "2026-10-20T09:00:00.000Z"
IMAGE = [{"type": "image", "source": {"type": "base64", "data": "iVBO", "media_type": "image/png"}}]


def assistant(msg_id, *blocks, ts=TS):
    usage = {"input_tokens": 2, "cache_creation_input_tokens": 300,
             "cache_read_input_tokens": 7000, "output_tokens": 5}
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {
        "id": msg_id, "role": "assistant", "content": list(blocks), "usage": usage}})


def tool(tool_id, name, **tool_input):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}


def text(value):
    return {"type": "text", "text": value}


def result(tool_id, content):
    return json.dumps({"type": "user", "timestamp": TS, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": content}]}})


def metrics(*lines, agent="task-implementer"):
    return agent_cost.run_metrics(list(agent_cost.iter_events(lines)), agent)


def test_render_table_reports_every_measure_per_agent():
    rows = [
        metrics(json.dumps({"type": "user", "timestamp": TS, "message": {"content": "go"}}),
                assistant("m1", tool("t1", "Read", file_path="docs/superpowers/plans/p.md")),
                result("t1", IMAGE), assistant("m2", tool("t2", "Edit", file_path="a.py"))),
        metrics(assistant("m1", tool("t1", "Grep", pattern="x")),
                assistant("m2", tool("t2", "Grep", pattern="y")), assistant("m3", text("done")), "{broken"),
        metrics(assistant("m1", tool("t", "SubagentHandback", message="VERDICT: CLEAN\nD1 done")),
                agent="task-reviewer"),
    ]
    implementer, reviewer = agent_cost.render_table(rows).split("## task-reviewer")
    assert implementer.startswith("## task-implementer\n\n| Measure | Value |\n|---|---|\n")
    for row in ("| Runs / turns | 2 / 5 |",
                "| Turns per run, median / p90 | 2.5 / 2.9 |",
                "| Input-side tokens, total / median run | 37k / 18k |",
                "| Output tokens, total | 25 |",
                "| Lookups before first edit, median / p90 | 1.5 / 1.9 |",
                "| Runs with no Edit or Write call | 1 |",
                "| Runs that touched a plan file | 1 of 2 |",
                "| Image reads, total / runs with any / max per run | 1 / 1 / 1 |",
                "| Reports in the required shape | 0 of 2 |",
                "| Deliverable lines missing / different | 0 / 0 |",
                "| Reports with `DELIVERABLES: n/a (no handoff)` | 0 |",
                "| Unparsed lines | 1 of 8 |"):
        assert row in implementer
    assert implementer.index("| Runs / turns") < implementer.index("| Unparsed lines")
    assert "| Reports in the required shape | 1 of 1 |" in reviewer
    assert "| Runs / turns | 1 / 1 |" in reviewer
    assert agent_cost.render_table([]) == ""


def test_large_token_counts_print_in_millions():
    rows = [metrics(*[assistant(f"m{i}") for i in range(140)])]
    assert "| Input-side tokens, total / median run | 1.0M / 1.0M |" in agent_cost.render_table(rows)


def _write_run(root, session, agent_id, agent, *lines):
    sub = root / session / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / f"agent-{agent_id}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (sub / f"agent-{agent_id}.meta.json").write_text(json.dumps({"agentType": agent}), encoding="utf-8")


@pytest.fixture
def root(tmp_path):
    _write_run(tmp_path, "s1", "a", "task-implementer",
               assistant("m1", text("x"), ts="2026-10-20T09:00:00.000Z"))
    _write_run(tmp_path, "s2", "b", "task-implementer",
               assistant("m1", text("x"), ts="2026-10-30T09:00:00.000Z"),
               assistant("m2", text("y"), ts="2026-10-30T09:01:00.000Z"))
    _write_run(tmp_path, "s2", "c", "task-reviewer",
               assistant("m1", tool("t", "SubagentHandback", message="VERDICT: CLEAN"),
                         ts="2026-10-21T09:00:00.000Z"))
    _write_run(tmp_path, "s3", "d", "task-implementer",   # no timestamp anywhere
               json.dumps({"type": "assistant", "message": {"id": "m1", "content": [], "usage": {}}}))
    return tmp_path


@pytest.mark.parametrize("args, expected", [
    ([], "| Runs / turns | 3 / 4 |"),
    (["--until", "2026-10-29"], "| Runs / turns | 1 / 1 |"),
    (["--since", "2026-10-30"], "| Runs / turns | 1 / 2 |"),
    (["--since", "2026-10-20", "--until", "2026-10-20"], "| Runs / turns | 1 / 1 |"),
    (["--agent", "task-reviewer"], "| Reports in the required shape | 1 of 1 |"),
])
def test_cli_filters_by_agent_and_inclusive_dates(root, capsys, args, expected):
    assert agent_cost.main(["--root", str(root), *args]) == 0
    assert expected in capsys.readouterr().out


@pytest.mark.parametrize("sub, args", [
    ("nothing", []), ("", ["--since", "2026-11-01"]), ("", ["--agent", "plan-writer"])])
def test_cli_exits_1_when_no_transcripts_match(root, capsys, sub, args):
    assert agent_cost.main(["--root", str(root / sub), *args]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("agent_cost: no ")


def test_cli_never_writes_under_the_root(root, capsys):
    before = {path: path.stat().st_mtime_ns for path in root.rglob("*")}
    assert agent_cost.main(["--root", str(root)]) == 0
    assert {path: path.stat().st_mtime_ns for path in root.rglob("*")} == before


def test_script_runs_as_a_command(root):
    done = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--agent", "task-reviewer"],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("## task-reviewer")
    empty = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root / "nothing")],
                           capture_output=True, text=True, timeout=60)
    assert empty.returncode == 1
