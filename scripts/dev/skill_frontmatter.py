"""Strict reader for the frontmatter of .claude/skills/*/SKILL.md and
.claude/agents/*.md -- the one parser behind scripts/dev/sync_codex.py,
tests/hooks/test_skill_shape.py and tests/hooks/test_agent_shape.py.

The three lenient `line.split(":", 1)` readers it replaces accepted
frontmatter the real loader rejects: an unquoted `description:` holding an
inner `: ` is not valid YAML, the skill then lists under its title-cased name
and never triggers, and the suite stayed green (v154). This reader raises
instead. Stdlib only: PyYAML is not a dependency of this repo.

Every value comes back as a `str` -- `disable-model-invocation: true` is the
string "true", an inline `[a, b]` list is that literal text.
"""
from __future__ import annotations

import re

_FENCE = "---\n"
_CLOSE = "\n---\n"
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*))?$")
# What YAML reads as something other than text inside an unquoted scalar:
# `: ` starts a nested mapping (a parse error), ` #` starts a comment (the
# rest of the value is silently dropped).
_UNQUOTED_TRAPS = (": ", " #")
_ESCAPABLE = ('"', "\\")


class FrontmatterError(ValueError):
    """Frontmatter the real skill/agent loader rejects or misreads."""


def quote_value(value: str) -> str:
    """Return `value` as a double-quoted scalar, `\\` and `"` escaped."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _fail(lineno: int, reason: str) -> FrontmatterError:
    return FrontmatterError(f"frontmatter line {lineno}: {reason}")


def _unquote(raw: str, lineno: int) -> str:
    """Value of a scalar that opens with a double quote."""
    out, i = [], 1
    while i < len(raw):
        char = raw[i]
        if char == '"':
            if raw[i + 1:].strip():
                raise _fail(lineno, 'text after the closing quote -- write an '
                                    'inner double quote as \\"')
            return "".join(out)
        if char == "\\":
            escaped = raw[i + 1:i + 2]
            if escaped not in _ESCAPABLE:
                raise _fail(lineno, f"unsupported escape \\{escaped} -- only "
                                    '\\" and \\\\ are read')
            out.append(escaped)
            i += 2
            continue
        out.append(char)
        i += 1
    raise _fail(lineno, "quoted value has no closing quote")


def _scalar(raw: str, lineno: int) -> str:
    if raw.startswith('"'):
        return _unquote(raw, lineno)
    # _KEY_RE already ate the whitespace after the colon, so a value that
    # opens with `#` needs the space put back for the ` #` trap to see it.
    padded = " " + raw
    for trap in _UNQUOTED_TRAPS:
        if trap in padded:
            raise _fail(lineno, f"unquoted value contains {trap!r} -- wrap the "
                                "whole value in double quotes")
    return raw


def _read_line(meta: dict[str, str], key: str | None, line: str,
               lineno: int) -> str:
    """Fold one frontmatter line into `meta`; return the key it belongs to."""
    stripped = line.strip()
    if stripped.startswith("- "):
        if key is None:
            raise _fail(lineno, f"list item before any key: {stripped!r}")
        meta[key] = ", ".join(filter(None, [meta[key], stripped[2:].strip()]))
        return key
    match = _KEY_RE.match(line)
    if match is None:
        raise _fail(lineno, f"not a `key: value` line: {line!r}")
    key = match.group(1)
    meta[key] = _scalar((match.group(2) or "").strip(), lineno)
    return key


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return ({key: value}, body) for a `---`-fenced markdown file.

    Line numbers in errors are file line numbers: the opening fence is line 1.
    """
    text = text.replace("\r\n", "\n")
    if not text.startswith(_FENCE):
        return {}, text
    head, close, body = text[len(_FENCE):].partition(_CLOSE)
    if not close:
        raise _fail(1, "opening --- has no closing --- line")
    meta: dict[str, str] = {}
    key = None
    for lineno, line in enumerate(head.split("\n"), start=2):
        if line.strip():
            key = _read_line(meta, key, line, lineno)
    return meta, body
