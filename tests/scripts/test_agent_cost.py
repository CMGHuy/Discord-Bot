"""agent_cost.py: transcript discovery, events, dedup, lookups and image reads (V199-7)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "agent_cost", ROOT / "scripts" / "dev" / "agent_cost.py")
agent_cost = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = agent_cost  # V199-8's dataclass resolves its annotations through it
_SPEC.loader.exec_module(agent_cost)

TS = "2026-10-21T16:22:28.527Z"
USAGE = {"input_tokens": 3, "cache_creation_input_tokens": 1200,
         "cache_read_input_tokens": 30000, "output_tokens": 40}
# One assistant message streamed as two lines that share message.id.
ASSISTANT_TEXT = {
    "type": "assistant", "timestamp": TS, "requestId": "req_1",
    "message": {"model": "claude-sonnet", "id": "msg_01A", "type": "message", "role": "assistant",
                "content": [{"type": "text", "text": "Reading the module."}],
                "stop_reason": None, "usage": dict(USAGE, output_tokens=1)}}
ASSISTANT_TOOL = {
    "type": "assistant", "timestamp": TS, "requestId": "req_1",
    "message": {"model": "claude-sonnet", "id": "msg_01A", "type": "message", "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_01B", "name": "Bash",
                             "input": {"command": "grep -n x a.py", "description": "Find x"},
                             "caller": {"type": "direct"}}],
                "stop_reason": "tool_use", "usage": USAGE}}
IMAGE_RESULT_BLOCK = {
    "tool_use_id": "toolu_01A11LEMBA2G39qUiDRcLm4J", "type": "tool_result",
    "content": [{"type": "image",
                 "source": {"type": "base64", "data": "iVBORw0KGgo=", "media_type": "image/png"}}]}
USER_RESULT = {"type": "user", "timestamp": TS, "toolUseResult": {"type": "image"},
               "message": {"role": "user", "content": [IMAGE_RESULT_BLOCK]}}
USER_PROMPT = {"type": "user", "timestamp": "2026-10-21T16:20:00.000Z",
               "message": {"role": "user", "content": "Implement Task V179-3."}}
ATTACHMENT = {"type": "attachment", "timestamp": TS, "attachment": {"type": "skill_listing"}}
API_REQUEST = {"type": "api-request", "timestamp": TS}


def _lines(*records):
    return [json.dumps(record) for record in records]


def _run(root, session, agent_id, meta):
    sub = root / session / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    jsonl = sub / f"agent-{agent_id}.jsonl"
    jsonl.write_text("\n".join(_lines(USER_PROMPT)) + "\n", encoding="utf-8")
    if meta is not None:
        (sub / f"agent-{agent_id}.meta.json").write_text(meta, encoding="utf-8")
    return jsonl


@pytest.mark.parametrize("path, slug", [
    (PureWindowsPath(r"E:\Documents\Private\Projects\Discord-Bot"),
     "E--Documents-Private-Projects-Discord-Bot"),
    (PurePosixPath("/opt/swing-bot"), "-opt-swing-bot"),
    (PurePosixPath("/home/u/my_repo.v2"), "-home-u-my-repo-v2"),
])
def test_repo_slug_matches_claude_code_folder_names(path, slug):
    assert agent_cost.repo_slug(path) == slug


def test_transcript_root_prefers_claude_config_dir(tmp_path):
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path / "cfg")}
    assert (agent_cost.transcript_root(env, tmp_path / "home", "slug")
            == tmp_path / "cfg" / "projects" / "slug")


@pytest.mark.parametrize("env", [{}, {"CLAUDE_CONFIG_DIR": ""}, {"CLAUDE_CONFIG_DIR": "  "}])
def test_transcript_root_falls_back_to_home_dot_claude(tmp_path, env):
    assert (agent_cost.transcript_root(env, tmp_path, "slug")
            == tmp_path / ".claude" / "projects" / "slug")


def test_find_runs_reads_agent_type_from_meta(tmp_path):
    a = _run(tmp_path, "s1", "a1", json.dumps({"agentType": "task-implementer", "spawnDepth": 1}))
    b = _run(tmp_path, "s2", "b2", json.dumps({"agentType": "task-reviewer"}))
    assert agent_cost.find_runs(tmp_path) == [
        agent_cost.RunFile(a, "task-implementer"), agent_cost.RunFile(b, "task-reviewer")]


def test_find_runs_counts_a_run_without_meta_as_unknown(tmp_path):
    missing = _run(tmp_path, "s1", "a", None)
    broken = _run(tmp_path, "s1", "b", "{not json")
    no_type = _run(tmp_path, "s1", "c", json.dumps({"description": "x"}))
    not_dict = _run(tmp_path, "s1", "d", json.dumps(["task-implementer"]))
    assert agent_cost.find_runs(tmp_path) == [
        agent_cost.RunFile(path, agent_cost.UNKNOWN_AGENT)
        for path in (missing, broken, no_type, not_dict)]


def test_find_runs_ignores_session_files_and_orphan_meta(tmp_path):
    (tmp_path / "s1.jsonl").write_text("{}\n", encoding="utf-8")
    sub = tmp_path / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-x.meta.json").write_text(json.dumps({"agentType": "task-implementer"}))
    assert agent_cost.find_runs(tmp_path) == []
    assert agent_cost.find_runs(tmp_path / "absent") == []


def test_iter_events_classifies_real_line_kinds():
    events = list(agent_cost.iter_events(_lines(
        USER_PROMPT, ASSISTANT_TEXT, ASSISTANT_TOOL, USER_RESULT, ATTACHMENT, API_REQUEST)))
    assert [e.kind for e in events] == ["user", "assistant", "assistant", "user", "other", "other"]
    assert events[0].blocks == ()
    assert events[0].timestamp == "2026-10-21T16:20:00.000Z"
    assert events[1].msg_id == events[2].msg_id == "msg_01A"
    assert events[2].usage["cache_read_input_tokens"] == 30000
    assert events[3].blocks == (IMAGE_RESULT_BLOCK,)
    assert {e.kind for e in events} <= set(agent_cost.EVENT_KINDS)


@pytest.mark.parametrize("line", [
    "{not json",
    json.dumps(["a", "list"]),
    json.dumps({"message": {"id": "m"}}),
    json.dumps({"type": "assistant"}),
    json.dumps({"type": "assistant", "message": {"id": "m", "content": []}}),
    json.dumps({"type": "assistant", "message": {"usage": {}, "content": []}}),
    json.dumps({"type": "assistant", "message": {"id": "m", "usage": {}, "content": "x"}}),
    json.dumps({"type": "user", "message": {"content": 7}}),
])
def test_iter_events_counts_bad_lines_as_unparsed(line):
    assert [e.kind for e in agent_cost.iter_events([line])] == ["unparsed"]


def test_iter_events_skips_blank_lines():
    assert list(agent_cost.iter_events(["", "   "])) == []


def test_dedup_merges_lines_sharing_a_message_id():
    events = list(agent_cost.iter_events(_lines(
        USER_PROMPT, ASSISTANT_TEXT, ASSISTANT_TOOL, ASSISTANT_TOOL, USER_RESULT)))
    merged = agent_cost.dedup(events)
    assert [e.kind for e in merged] == ["user", "assistant", "user"]
    turn = merged[1]
    assert [b["type"] for b in turn.blocks] == ["text", "tool_use"]  # toolu_01B kept once
    assert turn.usage["output_tokens"] == 40                         # largest output wins
    assert turn.usage["cache_read_input_tokens"] == 30000


def test_dedup_keeps_distinct_messages_in_order():
    second = json.loads(json.dumps(ASSISTANT_TEXT))
    second["message"]["id"] = "msg_02"
    merged = agent_cost.dedup(agent_cost.iter_events(
        _lines(ASSISTANT_TEXT, USER_RESULT, second, ATTACHMENT)))
    assert [(e.kind, e.msg_id) for e in merged] == [
        ("assistant", "msg_01A"), ("user", None), ("assistant", "msg_02"), ("other", None)]


@pytest.mark.parametrize("name, tool_input, expected", [
    ("Read", {"file_path": "a.py"}, True),
    ("Grep", {"pattern": "x"}, True),
    ("Glob", {"pattern": "**/*.py"}, True),
    ("Bash", {"command": "grep -n def a.py"}, True),
    ("Bash", {"command": "sed -n 10,40p a.py"}, True),
    ("Bash", {"command": "python scripts/dev/testrun.py file t.py 2>&1 | tail -3"}, True),
    ("Bash", {"command": "ls frontend/scripts"}, True),
    ("Bash", {"command": "git -C /wt log --oneline -3"}, False),
    ("Bash", {"command": "sed -i 's/a/b/' a.py"}, False),
    ("Bash", {"command": "python concatenate.py --category x"}, False),
    ("Bash", {"description": "grep for x"}, False),
    ("Edit", {"file_path": "a.py"}, False),
    ("Write", {"file_path": "a.py", "content": "cat"}, False),
])
def test_is_lookup_follows_the_fixed_definition(name, tool_input, expected):
    assert agent_cost.is_lookup(name, tool_input) is expected


def test_is_image_read_matches_the_real_tool_result_shape():
    assert agent_cost.is_image_read(IMAGE_RESULT_BLOCK)


@pytest.mark.parametrize("block", [
    {"type": "tool_result", "tool_use_id": "t", "content": "text result"},
    {"type": "tool_result", "tool_use_id": "t", "content": [{"type": "text", "text": "ok"}]},
    {"type": "image", "source": {}},
    "not a block",
])
def test_is_image_read_rejects_other_blocks(block):
    assert not agent_cost.is_image_read(block)
