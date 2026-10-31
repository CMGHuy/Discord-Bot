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
