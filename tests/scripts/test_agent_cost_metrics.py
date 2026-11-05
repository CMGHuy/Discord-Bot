"""agent_cost.py: per-run metrics and the reviewer's report shape (V199-8)."""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "agent_cost", ROOT / "scripts" / "dev" / "agent_cost.py")
agent_cost = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = agent_cost  # the dataclass resolves its annotations through it
_SPEC.loader.exec_module(agent_cost)
task_handoff = importlib.import_module("task_handoff")  # on sys.path once agent_cost loaded

TS = "2026-10-20T09:00:00.000Z"
PROMPT = json.dumps({"type": "user", "timestamp": TS,
                     "message": {"role": "user", "content": "Implement Task V1-1."}})
IMAGE = [{"type": "image", "source": {"type": "base64", "data": "iVBO", "media_type": "image/png"}}]


def assistant(msg_id, *blocks, output=5, ts=TS):
    usage = {"input_tokens": 2, "cache_creation_input_tokens": 300,
             "cache_read_input_tokens": 7000, "output_tokens": output}
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {
        "id": msg_id, "role": "assistant", "content": list(blocks), "usage": usage}})


def tool(tool_id, name, **tool_input):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}


def text(value):
    return {"type": "text", "text": value}


def result(tool_id, content="ok"):
    return json.dumps({"type": "user", "timestamp": TS, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": content}]}})


def metrics(*lines, agent="task-implementer"):
    return agent_cost.run_metrics(list(agent_cost.iter_events(lines)), agent)


def test_turns_and_tokens_count_each_message_once():
    m = metrics(PROMPT, assistant("m1", text("a"), output=1),
                assistant("m1", tool("t1", "Read", file_path="a.py"), output=9),
                result("t1"), assistant("m2", text("done")))
    assert (m.turns, m.input_tokens, m.output_tokens) == (2, 2 * 7302, 9 + 5)
    assert (m.agent, m.started) == ("task-implementer", TS)


@pytest.mark.parametrize("edit", ["Edit", "Write"])
def test_lookups_stop_at_the_first_edit_or_write(edit):
    m = metrics(assistant("m1", tool("t1", "Read", file_path="a.py"),
                          tool("t2", "Bash", command="grep -n x a.py"),
                          tool("t3", "Bash", command="git status")),
                assistant("m2", tool("t4", edit, file_path="a.py")),
                assistant("m3", tool("t5", "Grep", pattern="y")))
    assert (m.lookups_before_edit, m.edited) == (2, True)


def test_a_run_that_never_edits_counts_every_lookup():
    m = metrics(assistant("m1", tool("t1", "Read", file_path="a"), tool("t2", "Glob", pattern="*")),
                assistant("m2", tool("t3", "Bash", command="cat x | head")))
    assert (m.lookups_before_edit, m.edited) == (3, False)


@pytest.mark.parametrize("call, touched", [
    (tool("t", "Read", file_path=r"E:\repo\docs\superpowers\plans\2026-10-29-v199-x_3-a.md"), True),
    (tool("t", "Bash", command='grep -n "Task V1-1" docs/superpowers/plans/x.md'), True),
    (tool("t", "Grep", pattern="Task", path="docs/superpowers/plans/"), True),
    (tool("t", "Read", file_path="docs/superpowers/specs/x.md"), False),
    (tool("t", "SubagentHandback", message="read docs/superpowers/plans/x.md"), False),
])
def test_plan_touch_follows_paths_under_the_plans_folder(call, touched):
    assert metrics(assistant("m1", call)).plan_touch is touched


def test_image_reads_count_tool_results_holding_an_image():
    m = metrics(assistant("m1", tool("t1", "Read", file_path="a.png")), result("t1", IMAGE),
                assistant("m2", tool("t2", "Read", file_path="b.png")), result("t2", IMAGE),
                result("t3", "text only"))
    assert m.image_reads == 2


def test_report_is_the_handback_message_else_the_last_text():
    handback = metrics(assistant("m1", text("VERDICT: CLEAN, with notes")),
                       assistant("m2", tool("t9", "SubagentHandback", message="VERDICT: CLEAN\nD1 done")),
                       agent="task-reviewer")
    assert handback.report_shaped is True
    text_only = metrics(assistant("m1", text("Looks fine.")), assistant("m2", text("VERDICT: CLEAN")),
                        assistant("m3", text("  ")), agent="task-reviewer")
    assert text_only.report_shaped is True
    assert metrics(assistant("m1", tool("t1", "Read", file_path="a"))).report_shaped is False


def test_flagged_deliverables_and_no_handoff_are_counted():
    report = ("VERDICT: FINDINGS\nD1 done\nD2 missing -- tests/x.py\n"
              "D2.1 different -- asserts 3, plan says 4\nD3 missing -- step 4\n"
              "1. [spec] a.py:3 -- D2 missing\n   fix: add it")
    m = metrics(assistant("m1", tool("t", "SubagentHandback", message=report)), agent="task-reviewer")
    assert (m.missing, m.different, m.no_handoff, m.report_shaped) == (2, 1, False, True)
    fallback = f"VERDICT: CLEAN\n{task_handoff.NO_HANDOFF_LINE}"
    m = metrics(assistant("m1", tool("t", "SubagentHandback", message=fallback)), agent="task-reviewer")
    assert (m.no_handoff, m.report_shaped) == (True, True)


def test_unparsed_lines_are_counted_not_dropped():
    m = metrics(PROMPT, "{broken", json.dumps({"type": "assistant"}), assistant("m1", text("x")))
    assert (m.unparsed, m.lines, m.turns) == (2, 4, 1)


@pytest.mark.parametrize("report", [
    "VERDICT: CLEAN",
    "VERDICT: CLEAN\nD1 done\nD1.1 done\nD2 done",
    "VERDICT: FINDINGS\nD1 done\nD2 different -- returns a list\n"
    "1. [spec] scripts/dev/x.py:12 -- D2 differs\n   fix: return a tuple",
    "VERDICT: BLOCKED: which table owns the column?",
    "VERDICT: CLEAN\nDELIVERABLES: n/a (no handoff)",
    "\nVERDICT: FINDINGS\n\n1. [test] tests/a.py:4 -- asserts nothing\n   fix: assert the value\n",
])
def test_report_shaped_accepts_the_required_shape(report):
    assert agent_cost.report_shaped(report)


@pytest.mark.parametrize("report", [
    "",
    "VERDICT: CLEAN. No findings.",
    "**VERDICT:** CLEAN",
    "VERDICT: CLEAN\n\nSpec compliance: all files present.",
    "VERDICT: FINDINGS\n1. [spec] a.py:1 -- x\nD1 done",
    "VERDICT: CLEAN\nD1 ok",
    "VERDICT: FINDINGS\nD1 missing",
    "VERDICT: FINDINGS\n1. [ADVISORY, correctness] a.py:1 -- x",
    "Looks good.\nVERDICT: CLEAN",
])
def test_report_shaped_rejects_free_form_reports(report):
    assert not agent_cost.report_shaped(report)


def test_deliverable_states_come_from_task_handoff():
    done, *flagged = task_handoff.REVIEWER_STATES
    lines = [f"D1 {done}"] + [f"D{i} {state} -- why" for i, state in enumerate(flagged, 2)]
    assert agent_cost.report_shaped("VERDICT: FINDINGS\n" + "\n".join(lines))
    assert agent_cost.NO_HANDOFF_LINE == task_handoff.NO_HANDOFF_LINE
