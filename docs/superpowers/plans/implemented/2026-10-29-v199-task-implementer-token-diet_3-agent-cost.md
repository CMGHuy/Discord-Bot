# Task-implementer token diet, part 3: the cost instrument

**Spec:** [Task-implementer token diet](../specs/2026-10-29-v199-task-implementer-token-diet.md)
**Index:** [Plan index](2026-10-29-v199-task-implementer-token-diet_0-index.md) (Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below)

This part builds `scripts/dev/agent_cost.py` (spec § 5) in two seams, then
uses it. V199-7 finds subagent transcripts and turns their lines into
deduplicated events, with the spec's fixed lookup definition and the image
read test. V199-8 computes one `RunMetrics` per run, checks the reviewer's
report shape against the `task_handoff.py` constants, renders the table and
adds the CLI. V199-9 runs it with `--until` and reconciles the result with
the spec's Evidence table. V199-7 and V199-8 edit the same script, so the
chain is sequential; V199-8 also needs V199-4 merged.

Transcript facts, confirmed against the real transcripts at authoring
(2026-10-29, 626 subagent files under
`$CLAUDE_CONFIG_DIR/projects/E--Documents-Private-Projects-Discord-Bot/`):

- A run is `<session>/subagents/agent-<id>.jsonl`; its type is
  `agentType` in the sibling `agent-<id>.meta.json`. One meta file had no
  jsonl beside it (a run still in flight).
- Line `type`s seen in implementer runs: `user`, `assistant`, `attachment`,
  `api-request`, `api-request-shape`, `api-request-blob`. Only `user` and
  `assistant` carry `message`; the rest are counted as kind `other`, not
  `unparsed`.
- One assistant message is streamed as several lines, one block each,
  sharing `message.id`; every line repeats the input-side usage.
  Summing `output_tokens` over every line gives 1.39M; one value per id
  gives 0.66M.
- An image read is a `tool_result` block whose `content` is a list holding
  `{"type": "image", "source": {"type": "base64", "data": ..., "media_type": "image/png"}}`
  (sampled from `08622925-.../subagents/agent-a66e5605a28b9bf5c.jsonl`).
- Every one of the 97 reviewer runs, and 181 of the 185 implementer runs,
  returns its report as the `message` of a `SubagentHandback` tool call;
  77 reviewer runs have no text block at all.

# Phase 3 — the cost instrument

### Task V199-7: Transcript discovery, events, dedup and lookups
**Model:** sonnet — new pure-function module over an external, undocumented format; no legacy code touched.

**Files:**
- Create: `scripts/dev/agent_cost.py`
- Create: `tests/scripts/test_agent_cost.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (stdlib only).
- Produces (final names; V199-8 builds on them): `repo_slug(path: Path) -> str`; `transcript_root(env: Mapping[str, str], home: Path, slug: str) -> Path`; `class RunFile(NamedTuple): path: Path; agent: str`; `UNKNOWN_AGENT = "unknown"`; `find_runs(root: Path) -> list[RunFile]`; `class Event(NamedTuple): kind: str; msg_id: str | None; usage: dict | None; blocks: tuple; timestamp: str | None` with `kind` one of `EVENT_KINDS = ("assistant", "user", "other", "unparsed")`; `iter_events(lines: Iterable[str]) -> Iterator[Event]`; `dedup(events: Iterable[Event]) -> list[Event]`; `LOOKUP_RE`; `LOOKUP_TOOLS = ("Read", "Grep", "Glob")`; `EDIT_TOOLS = ("Edit", "Write")`; `is_lookup(name: str, tool_input: Mapping) -> bool`; `is_image_read(block: object) -> bool`; private `_output(usage: Mapping | None) -> int` (reused by V199-8).

Rules this task pins (spec § 5, fixed verbatim): **Lookup** = a `Read`, `Grep` or `Glob` call, or a `Bash` call whose `command` matches `\b(grep|rg|cat|sed -n|head|tail|ls|find)\b` (case-sensitive, the command only, never its `description`). **Turn** = a distinct assistant `message.id`, so `dedup` folds every line of one id into one event at the position of its first line: blocks concatenated in line order, a `tool_use` whose `id` was already seen for that message dropped, `usage` taken from the line with the largest `output_tokens` (the input-side fields are identical across a message's lines). Non-assistant events pass through in order. **Unparsed** = a non-blank line that is not a JSON object with a string `type`; a `user`/`assistant` line without a `message` object; an `assistant` message missing a string `id`, a `usage` object or a `content` list; a `user` message whose `content` is neither a string nor a list. Every other `type` (`attachment`, `api-request*`, …) is `other`. A run whose meta file is missing, not JSON, not an object or without a non-empty string `agentType` is `RunFile(path, "unknown")`: counted, not dropped, not crashed on. A meta file without its jsonl is not a run. Transcripts are only read.

- [ ] **Step 1: Write the failing tests** in `tests/scripts/test_agent_cost.py`. The record constants are trimmed copies of real lines (field names and nesting as in the transcripts, values shortened).

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_agent_cost.py`
Expected: FAIL — collection error, `scripts/dev/agent_cost.py` does not exist.

- [ ] **Step 3: Create `scripts/dev/agent_cost.py`** in the `doc_section.py` style (module docstring with usage and exit codes, `from __future__ import annotations`, small pure functions). The docstring is the final one; V199-8 adds the CLI it describes.

```python
"""Measure what subagent runs cost, from Claude Code's local transcripts.

    python scripts/dev/agent_cost.py [--agent task-implementer] [--since YYYY-MM-DD]
                                     [--until YYYY-MM-DD] [--root <dir>]

Reads <root>/*/subagents/agent-*.jsonl (the agent type is `agentType` in the
sibling .meta.json; "unknown" without one), folds the lines of one assistant
message into one turn, and prints one Markdown table per agent: runs, turns,
input-side tokens, lookups before the first edit, image reads, plan-file
touches, reviewer report shape and unparsed lines. Read-only: it never writes
under the transcript root. Dates are inclusive, on a run's first timestamp.

Default root: $CLAUDE_CONFIG_DIR/projects/<main checkout slug>/, else
~/.claude/projects/<slug>/. Exit 1 with a one-line reason on stderr when no
transcript matches. The format is Claude Code's internal one: a non-zero
"Unparsed lines" count is the signal that a CLI update changed it.

Fixed definitions (spec v199 section 5): lookup = a Read, Grep or Glob call,
or a Bash call matching LOOKUP_RE; first edit = the first Edit or Write call;
turn = a distinct assistant message.id; input tokens = input_tokens +
cache_read_input_tokens + cache_creation_input_tokens.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Iterator, Mapping, NamedTuple

LOOKUP_RE = re.compile(r"\b(grep|rg|cat|sed -n|head|tail|ls|find)\b")
LOOKUP_TOOLS = ("Read", "Grep", "Glob")
EDIT_TOOLS = ("Edit", "Write")
EVENT_KINDS = ("assistant", "user", "other", "unparsed")
UNKNOWN_AGENT = "unknown"


def repo_slug(path: Path) -> str:
    """Claude Code's project folder name for a checkout: non-alphanumerics become '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def transcript_root(env: Mapping[str, str], home: Path, slug: str) -> Path:
    """$CLAUDE_CONFIG_DIR/projects/<slug>, else <home>/.claude/projects/<slug>."""
    config = env.get("CLAUDE_CONFIG_DIR", "").strip()
    base = Path(config) if config else home / ".claude"
    return base / "projects" / slug


class RunFile(NamedTuple):
    path: Path  # <session>/subagents/agent-<id>.jsonl
    agent: str  # agentType from the sibling .meta.json, or UNKNOWN_AGENT


def _agent_type(meta: Path) -> str:
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UNKNOWN_AGENT
    agent = data.get("agentType") if isinstance(data, dict) else None
    return agent if isinstance(agent, str) and agent else UNKNOWN_AGENT


def find_runs(root: Path) -> list[RunFile]:
    """Every subagent transcript under root, sorted by path; never drops one."""
    paths = sorted(root.glob("*/subagents/*.jsonl"))
    return [RunFile(path, _agent_type(path.with_suffix(".meta.json"))) for path in paths]


class Event(NamedTuple):
    kind: str             # one of EVENT_KINDS
    msg_id: str | None    # assistant message.id
    usage: dict | None    # assistant message.usage
    blocks: tuple         # message content blocks; () for a string prompt
    timestamp: str | None


UNPARSED = Event("unparsed", None, None, (), None)


def _assistant(message: dict, timestamp: str | None) -> Event:
    msg_id, usage, content = message.get("id"), message.get("usage"), message.get("content")
    if not (isinstance(msg_id, str) and isinstance(usage, dict) and isinstance(content, list)):
        return UNPARSED
    return Event("assistant", msg_id, usage, tuple(content), timestamp)


def _user(message: dict, timestamp: str | None) -> Event:
    content = message.get("content")
    if isinstance(content, str):
        return Event("user", None, None, (), timestamp)
    if isinstance(content, list):
        return Event("user", None, None, tuple(content), timestamp)
    return UNPARSED


def _event(line: str) -> Event:
    try:
        data = json.loads(line)
    except ValueError:
        return UNPARSED
    if not isinstance(data, dict) or not isinstance(data.get("type"), str):
        return UNPARSED
    stamp = data.get("timestamp")
    timestamp = stamp if isinstance(stamp, str) else None
    if data["type"] not in ("assistant", "user"):
        return Event("other", None, None, (), timestamp)
    message = data.get("message")
    if not isinstance(message, dict):
        return UNPARSED
    build = _assistant if data["type"] == "assistant" else _user
    return build(message, timestamp)


def iter_events(lines: Iterable[str]) -> Iterator[Event]:
    """One Event per non-blank transcript line, in order."""
    for line in lines:
        if line.strip():
            yield _event(line)


def _output(usage: Mapping | None) -> int:
    return int((usage or {}).get("output_tokens") or 0)


def _tool_id(block: object) -> str | None:
    if isinstance(block, Mapping) and block.get("type") == "tool_use":
        return block.get("id")
    return None


def _merge(first: Event, later: Event) -> Event:
    seen = {_tool_id(block) for block in first.blocks} - {None}
    extra = tuple(block for block in later.blocks if _tool_id(block) not in seen)
    usage = later.usage if _output(later.usage) > _output(first.usage) else first.usage
    return first._replace(usage=usage, blocks=first.blocks + extra)


def dedup(events: Iterable[Event]) -> list[Event]:
    """One assistant event per message.id, at its first line; others pass through."""
    merged: list[Event] = []
    position: dict[str, int] = {}
    for event in events:
        if event.kind != "assistant":
            merged.append(event)
        elif event.msg_id in position:
            index = position[event.msg_id]
            merged[index] = _merge(merged[index], event)
        else:
            position[event.msg_id] = len(merged)
            merged.append(event)
    return merged


def is_lookup(name: str, tool_input: Mapping) -> bool:
    """A Read/Grep/Glob call, or a Bash call whose command matches LOOKUP_RE."""
    if name in LOOKUP_TOOLS:
        return True
    command = tool_input.get("command") if name == "Bash" else None
    return isinstance(command, str) and bool(LOOKUP_RE.search(command))


def is_image_read(block: object) -> bool:
    """A tool_result block whose content list holds an image block."""
    if not isinstance(block, Mapping) or block.get("type") != "tool_result":
        return False
    content = block.get("content")
    return isinstance(content, list) and any(
        isinstance(item, Mapping) and item.get("type") == "image" for item in content)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_agent_cost.py`
Expected: PASS, 40 passed, 0 failed.

- [ ] **Step 5: Check complexity**

Run: `git -C <wt> add scripts/dev/agent_cost.py tests/scripts/test_agent_cost.py`, then `python -m radon cc -s -n C <wt>/scripts/dev/agent_cost.py` (prints nothing) and `python <wt>/scripts/dev/complexity_gate.py` (exit 0).

- [ ] **Step 6: Commit**

```bash
git -C <wt> add scripts/dev/agent_cost.py tests/scripts/test_agent_cost.py
git -C <wt> commit -m "feat(dev): agent_cost.py reads subagent transcripts into deduplicated events (V199-7)" -m "<attribution lines from the controller>"
```

### Task V199-8: Run metrics and the reviewer report shape
**Model:** sonnet — extends a module this plan created; the report-shape grammar is a cross-file contract with `task_handoff.py`.

**Files:**
- Modify: `scripts/dev/agent_cost.py`
- Create: `tests/scripts/test_agent_cost_metrics.py`

**Interfaces:**
- Consumes: V199-7's `iter_events`, `dedup`, `Event`, `is_lookup`, `is_image_read`, `EDIT_TOOLS`, `_output`; V199-4's `NO_HANDOFF_LINE = "DELIVERABLES: n/a (no handoff)"` and `REVIEWER_STATES = ("done", "missing", "different")` from `scripts/dev/task_handoff.py` (needs V199-4 merged).
- Produces (V199-8b renders them): `@dataclass(frozen=True) class RunMetrics` with fields, in order, `agent: str`, `started: str | None`, `turns: int`, `input_tokens: int`, `output_tokens: int`, `lookups_before_edit: int`, `edited: bool`, `image_reads: int`, `plan_touch: bool`, `report_shaped: bool`, `missing: int`, `different: int`, `no_handoff: bool`, `unparsed: int`, `lines: int`; `run_metrics(events: list[Event], agent: str) -> RunMetrics` (takes events as `iter_events` yields them and dedups itself); `report_shaped(text: str) -> bool`; constants `INPUT_FIELDS`, `HANDBACK_TOOL = "SubagentHandback"`, `PLAN_DIR = "docs/superpowers/plans/"`, `FINDING_TAGS`, and `NO_HANDOFF_LINE` re-exported by the import.

Rules this task pins. **Input tokens** = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`, once per turn; **output** = `output_tokens` once per turn. **Lookups before first edit** stop at the first `Edit` or `Write` call; a run with neither counts every lookup and has `edited=False` (90 of the 185 baseline runs never call either: they write through Bash). **Plan touch** = any tool call other than `SubagentHandback` whose JSON-encoded input, with backslashes normalised to `/`, contains `docs/superpowers/plans/`. **Image reads** = `tool_result` blocks of `user` events for which `is_image_read` holds. **The report** is the `message` of the run's last `SubagentHandback` call, else its last non-blank text block, else `""`. **Required shape**: the first non-blank line is exactly `VERDICT: CLEAN`, `VERDICT: FINDINGS` or `VERDICT: BLOCKED: <text>`; every other non-blank line is a deliverable line (`D<n>[.<k>] done`, `D<n>[.<k>] missing -- <text>`, `D<n>[.<k>] different -- <text>`, states from `REVIEWER_STATES`, or exactly `NO_HANDOFF_LINE`), a finding line `<n>. [spec|correctness|complexity|test] <file>:<line> -- <text>`, or an indented `fix: <text>` line; and no deliverable line follows the first finding line. `missing`/`different` count the flagged deliverable lines of the report.

- [ ] **Step 1: Write the failing tests** in `tests/scripts/test_agent_cost_metrics.py`.

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_agent_cost_metrics.py`
Expected: FAIL — `AttributeError: module 'agent_cost' has no attribute 'run_metrics'` (a `ModuleNotFoundError: task_handoff` instead means V199-4 is not merged: stop and report `BLOCKED:`).

- [ ] **Step 3: Extend `scripts/dev/agent_cost.py`.** Add `import sys` and `from dataclasses import dataclass` to the import block; put this block between the imports and `LOOKUP_RE`:

```python
# scripts/dev is sys.path[0] when run directly, but not when a test loads this
# file via spec_from_file_location (same reason as testrun.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_handoff import NO_HANDOFF_LINE, REVIEWER_STATES  # noqa: E402

INPUT_FIELDS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
HANDBACK_TOOL = "SubagentHandback"
PLAN_DIR = "docs/superpowers/plans/"
FINDING_TAGS = ("spec", "correctness", "complexity", "test")
VERDICT_RE = re.compile(r"^VERDICT: (CLEAN|FINDINGS|BLOCKED: \S.*)$")
_DONE, *_FLAGGED = REVIEWER_STATES
DELIVERABLE_RE = re.compile(
    rf"^D\d+(?:\.\d+)? (?:(?P<done>{_DONE})|(?P<flag>{'|'.join(_FLAGGED)}) -- \S.*)$")
FINDING_RE = re.compile(rf"^\d+\. \[(?:{'|'.join(FINDING_TAGS)})\] \S+:\d+ -- \S.*$")
FIX_RE = re.compile(r"^\s+fix: \S.*$")
```

and append after `is_image_read` (radon counts every comprehension clause, so the helpers keep `run_metrics` at 9):

```python
@dataclass(frozen=True)
class RunMetrics:
    agent: str
    started: str | None        # first timestamp in the transcript (UTC ISO)
    turns: int
    input_tokens: int
    output_tokens: int
    lookups_before_edit: int   # every lookup when the run never edits
    edited: bool
    image_reads: int
    plan_touch: bool
    report_shaped: bool
    missing: int               # reviewer `D<n> missing -- ...` lines
    different: int             # reviewer `D<n> different -- ...` lines
    no_handoff: bool           # the report carries NO_HANDOFF_LINE
    unparsed: int
    lines: int                 # events read, unparsed included


def _input_tokens(usage: Mapping) -> int:
    return sum(int(usage.get(field) or 0) for field in INPUT_FIELDS)


def _tool_calls(turns: list[Event]) -> list[tuple[str, Mapping]]:
    calls = []
    for event in turns:
        for block in event.blocks:
            if isinstance(block, Mapping) and block.get("type") == "tool_use":
                calls.append((str(block.get("name", "")), block.get("input") or {}))
    return calls


def _lookups_before_edit(calls: list[tuple[str, Mapping]]) -> int:
    count = 0
    for name, tool_input in calls:
        if name in EDIT_TOOLS:
            break
        count += is_lookup(name, tool_input)
    return count


def _touches_plan(name: str, tool_input: Mapping) -> bool:
    if name == HANDBACK_TOOL:
        return False
    return PLAN_DIR in json.dumps(tool_input, ensure_ascii=False).replace("\\\\", "/")


def _handbacks(calls: list[tuple[str, Mapping]]) -> list[str]:
    return [tool_input.get("message") for name, tool_input in calls
            if name == HANDBACK_TOOL and isinstance(tool_input.get("message"), str)]


def _texts(turns: list[Event]) -> list[str]:
    blocks = [b for e in turns for b in e.blocks if isinstance(b, Mapping) and b.get("type") == "text"]
    return [str(b.get("text") or "") for b in blocks if str(b.get("text") or "").strip()]


def _report_text(turns: list[Event], calls: list[tuple[str, Mapping]]) -> str:
    found = _handbacks(calls) or _texts(turns)
    return found[-1] if found else ""


def _flag_counts(report: str) -> tuple[int, int]:
    matches = (DELIVERABLE_RE.match(line.strip()) for line in report.splitlines())
    flags = [m.group("flag") for m in matches if m and m.group("flag")]
    return flags.count(_FLAGGED[0]), flags.count(_FLAGGED[1])


def _line_kind(line: str) -> str:
    if line == NO_HANDOFF_LINE or DELIVERABLE_RE.match(line):
        return "deliverable"
    if FINDING_RE.match(line) or FIX_RE.match(line):
        return "finding"
    return "other"


def report_shaped(text: str) -> bool:
    """The reviewer's required shape: VERDICT line, deliverable lines, then findings."""
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    if not lines or not VERDICT_RE.match(lines[0]):
        return False
    kinds = [_line_kind(line) for line in lines[1:]]
    if "other" in kinds:
        return False
    first_finding = kinds.index("finding") if "finding" in kinds else len(kinds)
    return "deliverable" not in kinds[first_finding:]


def _started(events: list[Event]) -> str | None:
    return next((e.timestamp for e in events if e.timestamp), None)


def _image_reads(events: list[Event]) -> int:
    return sum(is_image_read(b) for e in events if e.kind == "user" for b in e.blocks)


def run_metrics(events: list[Event], agent: str) -> RunMetrics:
    """One run's measures from its raw events (dedup is applied here)."""
    merged = dedup(events)
    turns = [e for e in merged if e.kind == "assistant"]
    calls = _tool_calls(turns)
    report = _report_text(turns, calls)
    missing, different = _flag_counts(report)
    return RunMetrics(
        agent=agent, started=_started(events), turns=len(turns),
        input_tokens=sum(_input_tokens(e.usage) for e in turns),
        output_tokens=sum(_output(e.usage) for e in turns),
        lookups_before_edit=_lookups_before_edit(calls),
        edited=any(name in EDIT_TOOLS for name, _ in calls),
        image_reads=_image_reads(merged),
        plan_touch=any(_touches_plan(name, tool_input) for name, tool_input in calls),
        report_shaped=report_shaped(report), missing=missing, different=different,
        no_handoff=NO_HANDOFF_LINE in [line.strip() for line in report.splitlines()],
        unparsed=sum(e.kind == "unparsed" for e in events), lines=len(events))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_agent_cost_metrics.py` and `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_agent_cost.py`
Expected: PASS, 29 passed and 40 passed, 0 failed.

- [ ] **Step 5: Check complexity**

Run: `git -C <wt> add tests/scripts/test_agent_cost_metrics.py`, then `python -m radon cc -s -n C <wt>/scripts/dev/agent_cost.py` (prints nothing) and `python <wt>/scripts/dev/complexity_gate.py` (exit 0).

- [ ] **Step 6: Commit**

```bash
git -C <wt> add scripts/dev/agent_cost.py tests/scripts/test_agent_cost_metrics.py
git -C <wt> commit -m "feat(dev): agent_cost.py per-run metrics and reviewer report shape (V199-8)" -m "<attribution lines from the controller>"
```

### Task V199-8b: The table and the command line
**Model:** sonnet — rendering and argparse over functions this plan created; one subprocess call to git.

**Files:**
- Modify: `scripts/dev/agent_cost.py`
- Create: `tests/scripts/test_agent_cost_cli.py`

**Interfaces:**
- Consumes: V199-7's `find_runs`, `iter_events`, `transcript_root`, `repo_slug`; V199-8's `RunMetrics`, `run_metrics`, `NO_HANDOFF_LINE`.
- Produces (V199-9, V199-12 and V199-13 run the CLI; nothing imports these): `render_table(rows: list[RunMetrics]) -> str`; `main(argv: list[str] | None = None) -> int`. CLI: `python scripts/dev/agent_cost.py [--agent task-implementer] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--root <dir>]`.

Rules this task pins. One Markdown block per agent, agents sorted: `## <agent>`, a blank line, `| Measure | Value |`, `|---|---|`, then exactly these rows in this order: `Runs / turns`; `Turns per run, median / p90`; `Input-side tokens, total / median run`; `Output tokens, total`; `Lookups before first edit, median / p90`; `Runs with no Edit or Write call`; `Runs that touched a plan file` (`<n> of <runs>`); `Image reads, total / runs with any / max per run`; `Reports in the required shape` (`<n> of <runs>`); `Deliverable lines missing / different`; ``Reports with `DELIVERABLES: n/a (no handoff)` `` (label built from `NO_HANDOFF_LINE`); `Unparsed lines` (`<unparsed> of <lines>`). Medians by `statistics.median`; p90 by `statistics.quantiles(values, n=10, method="inclusive")[-1]` (the method that reproduces the spec's turns p90 of 32; the default `exclusive` gives 34.4), the single value when there is one. Numbers print as `f"{round(x, 1):g}"`; token counts as `206.0M` (`>= 1e6`, one decimal) or `518k` (`>= 1e3`, none). **Dates** are inclusive, compared with the UTC date (`[:10]`) of the run's first timestamp; under a date filter a run with no or a malformed timestamp is excluded. Runs are filtered on `RunFile.agent` before their file is read; files are read with `encoding="utf-8", errors="replace"`. Exit 1, nothing on stdout and `agent_cost: no <agent> transcripts under <root> for the given dates` on stderr when no run matches (a missing root included). Default root: `transcript_root(os.environ, Path.home(), repo_slug(<main checkout>))`, the main checkout from `git -C <this file's dir> rev-parse --git-common-dir` (made absolute against that dir, then `.resolve().parent`) — the same rule as V199-6b's `main_checkout`, duplicated privately so chain C needs only V199-4.

- [ ] **Step 1: Write the failing tests** in `tests/scripts/test_agent_cost_cli.py`.

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_agent_cost_cli.py`
Expected: FAIL — `AttributeError: module 'agent_cost' has no attribute 'render_table'`.

- [ ] **Step 3: Extend `scripts/dev/agent_cost.py`.** Add `argparse`, `os`, `statistics`, `subprocess` and `from datetime import date` to the import block, append the code below after `run_metrics`, and end the file with `if __name__ == "__main__": sys.exit(main())`. `_agent_rows` takes its aggregates from `_values`/`_total` rather than inline generators, so it stays far below 15.

```python
def _values(rows: list[RunMetrics], field: str) -> list:
    return [getattr(row, field) for row in rows]


def _total(rows: list[RunMetrics], field: str) -> int:
    return sum(_values(rows, field))


def _num(value: float) -> str:
    return f"{round(value, 1):g}"


def _tokens(count: float) -> str:
    if count >= 1e6:
        return f"{count / 1e6:.1f}M"
    if count >= 1e3:
        return f"{count / 1e3:.0f}k"
    return _num(count)


def _spread(values: list) -> str:
    """'<median> / <p90>'; inclusive p90 reproduces the spec's baseline (turns p90 32)."""
    p90 = statistics.quantiles(values, n=10, method="inclusive")[-1] if len(values) > 1 else values[0]
    return f"{_num(statistics.median(values))} / {_num(p90)}"


def _agent_rows(rows: list[RunMetrics]) -> list[tuple[str, str]]:
    runs = len(rows)
    images = _values(rows, "image_reads")
    tokens = _values(rows, "input_tokens")
    return [
        ("Runs / turns", f"{runs} / {_total(rows, 'turns')}"),
        ("Turns per run, median / p90", _spread(_values(rows, "turns"))),
        ("Input-side tokens, total / median run",
         f"{_tokens(sum(tokens))} / {_tokens(statistics.median(tokens))}"),
        ("Output tokens, total", _tokens(_total(rows, "output_tokens"))),
        ("Lookups before first edit, median / p90", _spread(_values(rows, "lookups_before_edit"))),
        ("Runs with no Edit or Write call", str(runs - _total(rows, "edited"))),
        ("Runs that touched a plan file", f"{_total(rows, 'plan_touch')} of {runs}"),
        ("Image reads, total / runs with any / max per run",
         f"{sum(images)} / {runs - images.count(0)} / {max(images)}"),
        ("Reports in the required shape", f"{_total(rows, 'report_shaped')} of {runs}"),
        ("Deliverable lines missing / different",
         f"{_total(rows, 'missing')} / {_total(rows, 'different')}"),
        (f"Reports with `{NO_HANDOFF_LINE}`", str(_total(rows, "no_handoff"))),
        ("Unparsed lines", f"{_total(rows, 'unparsed')} of {_total(rows, 'lines')}"),
    ]


def render_table(rows: list[RunMetrics]) -> str:
    """One Markdown table per agent, agents sorted; '' for no rows."""
    blocks = []
    for agent in sorted({row.agent for row in rows}):
        lines = [f"| {measure} | {value} |"
                 for measure, value in _agent_rows([r for r in rows if r.agent == agent])]
        blocks.append(f"## {agent}\n\n| Measure | Value |\n|---|---|\n" + "\n".join(lines) + "\n")
    return "\n".join(blocks)
```

Then the CLI helpers, each a few lines (signatures and behaviour fixed by the rules above; the bodies are the implementer's):

- `_main_checkout() -> Path` and `_default_root() -> Path`.
- `_in_window(started: str | None, since: date | None, until: date | None) -> bool` — no filter: `True`; a filter and `date.fromisoformat(started[:10])` raising `TypeError`/`ValueError`: `False`.
- `_collect(root: Path, agent: str, since: date | None, until: date | None) -> list[RunMetrics]`.
- `_parser() -> argparse.ArgumentParser` — `--agent` default `task-implementer`; `--since`/`--until` with `type=date.fromisoformat`; `--root` with `type=Path`, default `None` (resolved by `_default_root()` only when absent, so tests never touch git).
- `main(argv)` — prints `render_table(rows)` and returns 0, or the stderr line and 1.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_agent_cost_cli.py`, then the same for `test_agent_cost_metrics.py` and `test_agent_cost.py`.
Expected: PASS, 12, 29 and 40 passed, 0 failed.

- [ ] **Step 5: Smoke-run against the real transcripts and check complexity**

Run: `python <wt>/scripts/dev/agent_cost.py --until 2026-10-28`
Expected: exit 0; a `## task-implementer` table whose first row is `| Runs / turns | 185 / 3216 |` and whose `Unparsed lines` row starts `| Unparsed lines | 0 of`. (V199-9 reconciles the whole table; a different first row is reported under NOTES, not fixed here.)

Run: `git -C <wt> add tests/scripts/test_agent_cost_cli.py`, then `python -m radon cc -s -n C <wt>/scripts/dev/agent_cost.py` (prints nothing) and `python <wt>/scripts/dev/complexity_gate.py` (exit 0).

- [ ] **Step 6: Commit**

```bash
git -C <wt> add scripts/dev/agent_cost.py tests/scripts/test_agent_cost_cli.py
git -C <wt> commit -m "feat(dev): agent_cost.py table and command line (V199-8b)" -m "<attribution lines from the controller>"
```

### Task V199-9: Reproduce the spec's baseline table
**Model:** opus — judges whether each delta against the spec's Evidence table is explained or a broken definition, and records it in the spec.

**Files:**
- Modify: `docs/superpowers/specs/2026-10-29-v199-task-implementer-token-diet.md` (append a `## Baseline reproduction` section at the end)
- Only if a definition must be reconciled (decision rule below): `scripts/dev/agent_cost.py` and the one test file covering the changed seam (`tests/scripts/test_agent_cost.py`, `test_agent_cost_metrics.py` or `test_agent_cost_cli.py`).

**Interfaces:**
- Consumes: the V199-8b CLI, `python <wt>/scripts/dev/agent_cost.py [--agent <type>] [--until YYYY-MM-DD]`. Run from the worktree, its default root resolves through `git rev-parse --git-common-dir` to the main checkout's folder, `$CLAUDE_CONFIG_DIR/projects/E--Documents-Private-Projects-Discord-Bot/`.
- Produces: no code contract. The spec section is the baseline of record that the post-merge Success check (outside this plan) compares against.

Controller note (2026-10-29, after this part was written): the spec's Evidence table was corrected to the Reproduced column below for lookups, plan touches, reviewer shape, output tokens and the lookup-regex row. Step 3's delta table therefore holds only rows that still differ from the corrected spec.

What the plan writer reproduced on 2026-10-29 with the V199-7..8b code, run over the real transcripts. The spec's Evidence numbers came from an ad-hoc script that was not kept, so a few of them cannot be matched under the definitions the spec fixes. Each such delta has a known cause, listed here:

| Measure | Spec Evidence | Reproduced at authoring | Verdict and cause |
|---|---|---|---|
| Runs / turns | 185 / 3216 | 185 / 3216 | match |
| Input-side tokens, total / median run | 206M / 517k | 206.0M / 518k | match (rounding: 205.97M, 517,917) |
| Turns per run, median / p90 | 11 / 32 | 11 / 32 | match with `method="inclusive"` (exclusive gives 34.4) |
| Image reads | 49 full-page screenshot reads | 49 (8 runs, max 9 in one run) | match |
| Lookups before first edit, median / p90 | 8 / 20 | 7 / 18.6 | delta, no definition within the spec's wording gives 8 / 20. Edit-only first edit gives 8 / 24; leaving out the 90 runs that never call Edit or Write gives 7 / 16.4; matching the regex against the whole input JSON or case-insensitively changes nothing. |
| Runs that touched a plan file | 99 | 101 | delta, the spec does not define "touch". Tool calls naming `docs/superpowers/plans/`, `SubagentHandback` excluded, give 101; Read/Grep/Glob only give 13; leaving out Bash calls containing `git ` gives 95. |
| Reviewer reports in the required shape | 7 of 97 | 0 of 97 (strict) | delta: the 7 counted the last *text* block containing `VERDICT`, but every reviewer returns its report as the `SubagentHandback` message, and 77 of 97 runs have no text block at all. On the handback message, 67 start with `VERDICT:` and 39 have an exact `VERDICT:` first line, yet none passes the strict shape (all carry prose). |
| Output tokens (Goal paragraph) | 1.4M | 664k | delta, 1.39M summed `output_tokens` over every streamed line, so each message counted several times. One value per message id gives 664k. |
| Bash calls that are lookups | 1139 of 2803 | 2517 of 2803 | not in the table. The 1139 used `grep/sed/cat/head` only; the fixed regex also counts `tail`, `ls`, `find`, `rg`, and `tail` follows most `testrun.py` calls. |
| Unparsed lines | (none) | 0 of 23683 | the format check is clean |

**Decision rule.**

- **Must reproduce:** runs, turns, input tokens (total within ±0.5M, median within ±1k) and image reads. The Success target "median input tokens down at least 30%" is the only target relative to the baseline, and these are its inputs. A mismatch here is investigated in this order, and the cause is recorded:
  1. Transcripts pruned by Claude Code's `cleanupPeriodDays`: fewer session folders than at authoring, so runs fall below 185. Record it and keep the authoring numbers as the baseline of record.
  2. A non-zero `Unparsed lines`: the format changed. Fix the parser seam with a fixture test.
  3. `agent_cost.py` deviating from a fixed definition: fix it test-first in the owning test file.
  4. Anything else: `BLOCKED:` with the two numbers and what was ruled out.
- **Expected deltas** (lookups 7 / 18.6, plan touches 101, reviewer shape 0 of 97, output 664k): record them with the causes above. Do **not** change a fixed definition to chase the un-kept script's number. Their Success targets are absolute (lookups ≤ 3, plan touches 0, shape ≥ 90%), so before and after are measured by the same code and stay like for like. If the controller's dispatch carries a partner decision on the lookup delta, that decision wins over this rule.
- **A value that differs from the authoring column**, not just from the spec, is treated like a "must reproduce" mismatch.
- **A definition change**, if one is needed, is made test-first. It is recorded in the section as `Definition change: <what>, because <why>`, and the index's Global Constraints line on fixed definitions is not edited (only this task may change a definition).

- [ ] **Step 1: Run the instrument for both agents and both cut-offs**

Run, saving each output verbatim:
- `python <wt>/scripts/dev/agent_cost.py --until 2026-10-28`
- `python <wt>/scripts/dev/agent_cost.py --until 2026-10-29`
- `python <wt>/scripts/dev/agent_cost.py --agent task-reviewer --until 2026-10-28`

Expected: each exits 0. The `--until 2026-10-28` implementer table matches the authoring column above. If the two implementer cut-offs differ, the extra runs were dispatched on 2026-10-29 after the baseline was taken, for example this plan's own implementers. The 2026-10-28 table is then the one compared, and the section says so: the spec names `--until 2026-10-29` because at authoring both cut-offs selected the same 185 runs.

- [ ] **Step 2: Compare and apply the decision rule**

Compare every row with the table above. If a definition must change, write the failing test first in the owning test file. Then run `python <wt>/scripts/dev/testrun.py file <that test file>` (expected: FAIL, then PASS after the fix), and re-run Step 1.

- [ ] **Step 3: Append `## Baseline reproduction` to the spec**

Append at the end of `docs/superpowers/specs/2026-10-29-v199-task-implementer-token-diet.md`, after `## Panel review`. The section holds:

- the date;
- the three commands;
- the short sha of the commit holding the `agent_cost.py` that produced the numbers (`git -C <wt> log -1 --format=%h -- scripts/dev/agent_cost.py`);
- both agents' tables, pasted verbatim from Step 1;
- a delta table with the columns `Measure | Spec Evidence | Reproduced | Cause`, holding only the rows that differ, with causes in one sentence each;
- every definition change, if any;
- a closing line naming the baseline of record for the post-merge Success check: the median input tokens per run, plus the four absolute targets unchanged.

Do not edit the Evidence table itself. It stays as written, and the new section corrects it.

- [ ] **Step 4: Verify the diff is what this task owns**

Run: `git -C <wt> diff --stat`
Expected: the spec only. If a definition changed, add `scripts/dev/agent_cost.py` and its one test file, and run `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_agent_cost.py`, `... test_agent_cost_metrics.py` and `... test_agent_cost_cli.py` (all PASS, 0 failed), plus `python <wt>/scripts/dev/complexity_gate.py` (exit 0).

- [ ] **Step 5: Commit**

```bash
git -C <wt> add docs/superpowers/specs/2026-10-29-v199-task-implementer-token-diet.md
git -C <wt> commit -m "docs(v199): reproduce the baseline with agent_cost.py (V199-9)" -m "<attribution lines from the controller>"
```

Stage `scripts/dev/agent_cost.py` and its test file in the same commit only if Step 2 changed a definition. The NOTES line of the report names every delta beyond rounding and its verdict.

